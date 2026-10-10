# unseeing

**Let the model work on the text without ever seeing the people in it.**

Reversible PII scrubbing around LLM calls. Before a prompt leaves your
machine, unseeing replaces emails, phones, IDs, and (in resume mode) names
with stable typed placeholders such as `<PERSON_1>` and `<EMAIL_2>`. After
the response comes back — including streamed chunks that split a
placeholder in half — it puts the originals back.

The name is borrowed from China Miéville's *The City & the City*, where
citizens learn to unsee the people of the other city.

```bash
pip install unseeing
```

Python 3.10+. The core has **zero required dependencies**.

## Why it matters

Job-matching apps, HR copilots, and support desks send resumes and profiles
to cheap LLM providers. Some of those providers train on prompts. Once a
legal name, personal email, or national ID is in a training corpus, you
cannot pull it back.

unseeing keeps the *structure* of the text (so the model can still match,
summarize, and extract) and holds the *people* in a local vault. It reduces
how much identifiable data you send. **It is not a compliance guarantee,
not legal advice, and not a substitute for a DPA, a no-train endpoint, or
human review.**

## 30-second quickstart

```python
from unseeing import scrub

text = "Email Ava Chen at ava.chen@example.com or +1-555-010-0142."
scrubbed, vault = scrub(text, resume=True)
print(scrubbed)
# Email <PERSON_1> at <EMAIL_1> or <PHONE_1>.

print(vault.restore("I would contact <PERSON_1>'s team at <EMAIL_1>."))
# I would contact Ava Chen's team at ava.chen@example.com.

print(vault.audit().format())
# EMAIL   1
# PERSON  1
# PHONE   1
# Total   3
```

Audit reports count types. They never include original values.

## OpenAI wrapper

Scrubs chat completions, the Responses API, tool-call arguments, and
streams:

```python
from openai import OpenAI
from unseeing import Scrubber
from unseeing.openai import UnseeingOpenAI

client = UnseeingOpenAI(OpenAI(), scrubber=Scrubber(resume=True))
completion = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Summarize Ava Chen, ava.chen@example.com"}],
)
print(completion.choices[0].message.content)  # originals restored
```

## Anthropic wrapper

```python
from anthropic import Anthropic
from unseeing import Scrubber
from unseeing.anthropic import UnseeingAnthropic

client = UnseeingAnthropic(Anthropic(), scrubber=Scrubber(resume=True))
message = client.messages.create(
    model="claude-sonnet-4-5",
    max_tokens=200,
    messages=[{"role": "user", "content": "Is Priya Nair a fit for payments?"}],
)
```

## freewhirr integration preview

unseeing exposes a small stable protocol so
[freewhirr](https://github.com/andymccutcheon/freewhirr) can take it as an
optional dependency:

```python
from unseeing import Scrubber, UnseeingMiddleware
from unseeing.protocol import ScrubberProtocol

# freewhirr can wrap its OpenAI-compatible proxy:
app = UnseeingMiddleware(proxy_app, scrubber=Scrubber(resume=True))

# or call the protocol directly:
def send(scrubber: ScrubberProtocol, messages):
    outgoing = scrubber.scrub_messages(messages)
    reply = provider.complete(outgoing)
    return scrubber.restore_message(reply)
```

The names to depend on are `scrub_messages`, `restore_message`, and
`restore_stream` (plus `restore_async_stream` for async clients).

## Detection

A fast built-in regex / validator layer (stdlib only):

| Type | Notes |
| --- | --- |
| `EMAIL` | Typical addresses |
| `PHONE` | International, 10–15 digits, formatted |
| `URL` | `http(s)` and `www.` |
| `IP_ADDRESS` | IPv4 / IPv6 via `ipaddress` |
| `CREDIT_CARD` | 13–19 digits, IIN + Luhn |
| `SSN` | `AAA-GG-SSSS` with area/group/serial checks |
| `NATIONAL_ID` | UK NINO, Canadian SIN (Luhn) |
| `IBAN` | MOD-97 |
| `STREET_ADDRESS` | Best-effort street / PO Box / city-state-ZIP |
| `DATE_OF_BIRTH` | Dates with DOB / born / birthday context |
| `LINKEDIN` | `/in/` profile URLs |
| `GITHUB` | Profile URLs, not `org/repo` |

Optional extras:

```bash
pip install 'unseeing[ner]'          # spaCy PERSON / ORG / LOCATION
python -m spacy download en_core_web_sm
pip install 'unseeing[presidio]'     # Microsoft Presidio adapter
```

```python
from unseeing import CustomPattern, DenyItem, Scrubber

scrubber = Scrubber(
    resume=True,
    scrub_orgs=False,          # keep employer / school names (default)
    allow=["Acme Corp"],       # never scrub
    deny=[DenyItem("Ava Chen", "PERSON")],
    custom_patterns=[CustomPattern("EMPLOYEE_ID", r"EMP-\d{5}")],
    use_ner=False,
    use_presidio=False,
    use_surrogates=False,      # True → Faker-style stand-ins instead of tags
)
```

Same entity → same placeholder for the life of a `Vault` (one resume, or a
multi-turn conversation). Restoration tolerates `<person_1>`, `[PERSON_1]`,
`(PERSON_1)`, and `<PERSON_1>'s`.

Vaults live in memory. Persist them with optional password encryption:

```python
vault.save("session.vault", key="correct horse")
```

That lock is PBKDF2-HMAC-SHA256 + a SHA-256 keystream + HMAC. Convenience,
not an HSM.

## CLI

```bash
unseeing scan resume.txt          # type counts, never originals
unseeing scrub < resume.txt       # stdin → stdout
unseeing scrub resume.txt --vault session.vault --resume
unseeing restore --vault session.vault < scrubbed.txt
unseeing demo
```

## Evaluation

Held-out entity-level scores on a **public labeled dataset we did not tune
on**. Run locally with `scripts/benchmark.py` (not CI; it downloads data).

| | |
| --- | --- |
| Dataset | [`ai4privacy/pii-masking-400k`](https://huggingface.co/datasets/ai4privacy/pii-masking-400k) |
| Split / filter | `train`, `language == "en"` (68,275 English rows) |
| Sample | 2,000 rows, seed `20261010` |
| Revision | `414d0a3b5798a152588a0828f1c08a5787de10f4` |
| Date | 2026-10-10 |
| Matching | Entity-level, same mapped type, **span overlap** (not exact). 1-1 greedy, longer gold first |
| Configs | regex-only (default install, `resume=False`); same + `unseeing[ner]` (`en_core_web_sm`) |
| Overall | Micro-average over types that have gold in this sample |

Adjacent `GIVENNAME` + `SURNAME` gold spans are merged into one `PERSON`.
`LINKEDIN` / `GITHUB` predictions score as `URL`.

**Label mapping** (dataset → unseeing):

| Dataset label | unseeing type |
| --- | --- |
| `EMAIL` | `EMAIL` |
| `TELEPHONENUM` | `PHONE` |
| `CREDITCARDNUMBER` | `CREDIT_CARD` |
| `SOCIALNUM` | `SSN` |
| `IDCARDNUM` | `NATIONAL_ID` |
| `DATEOFBIRTH` | `DATE_OF_BIRTH` |
| `STREET` | `STREET_ADDRESS` |
| `GIVENNAME` / `SURNAME` | `PERSON` (merged when adjacent) |
| `CITY` | `LOCATION` |
| `IPV4` / `IPV6` | `IP_ADDRESS` |
| `URL` | `URL` |
| `IBAN` | `IBAN` |

Unseeing does not claim, and this eval does not score: `USERNAME`,
`PASSWORD`, `ACCOUNTNUM`, `TAXNUM`, `DRIVERLICENSENUM`, `BUILDINGNUM`,
`ZIPCODE`, `MAC`, `USERAGENT`, crypto addresses, `VEHICLEVIN` /
`VEHICLEVRM`, `PIN`, `JOBTITLE`, `HEIGHT`, `EYECOLOR`, `TIME`, `AGE`,
`TITLE`, `GENDER`, `SEX`, `PASSPORTNUM`.

This sample's gold schema is the public 17-class set. It has **no**
`URL` / `IPV4` / `IPV6` / `IBAN` labels. The regex layer still predicted
202 URLs, 8 IPs, and 1 IBAN in these 2,000 rows; those counts are omitted
from overall so unlabeled spans are not counted as errors.

### regex-only (default install)

| Type | Precision | Recall | F1 | TP | FP | FN |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| **Overall** | 0.85 | 0.24 | 0.38 | 380 | 69 | 1190 |
| CREDIT_CARD | 0.33 | 0.05 | 0.09 | 3 | 6 | 56 |
| DATE_OF_BIRTH | 1.00 | 0.19 | 0.32 | 19 | 0 | 80 |
| EMAIL | 1.00 | 0.95 | 0.97 | 200 | 1 | 10 |
| LOCATION | 0.00 | 0.00 | 0.00 | 0 | 0 | 236 |
| NATIONAL_ID | 0.00 | 0.00 | 0.00 | 0 | 0 | 105 |
| PERSON | 0.00 | 0.00 | 0.00 | 0 | 0 | 530 |
| PHONE | 0.79 | 0.66 | 0.72 | 108 | 29 | 55 |
| SSN | 0.53 | 0.38 | 0.45 | 35 | 31 | 56 |
| STREET_ADDRESS | 0.88 | 0.19 | 0.32 | 15 | 2 | 62 |

### regex + `unseeing[ner]`

| Type | Precision | Recall | F1 | TP | FP | FN |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| **Overall** | 0.44 | 0.45 | 0.44 | 705 | 901 | 865 |
| CREDIT_CARD | 0.33 | 0.05 | 0.09 | 3 | 6 | 56 |
| DATE_OF_BIRTH | 1.00 | 0.19 | 0.32 | 19 | 0 | 80 |
| EMAIL | 1.00 | 0.95 | 0.97 | 200 | 1 | 10 |
| LOCATION | 0.20 | 0.42 | 0.27 | 100 | 393 | 136 |
| NATIONAL_ID | 0.00 | 0.00 | 0.00 | 0 | 0 | 105 |
| PERSON | 0.34 | 0.42 | 0.38 | 225 | 439 | 305 |
| PHONE | 0.79 | 0.66 | 0.72 | 108 | 29 | 55 |
| SSN | 0.53 | 0.38 | 0.45 | 35 | 31 | 56 |
| STREET_ADDRESS | 0.88 | 0.19 | 0.32 | 15 | 2 | 62 |

A cell of 1.00 is rounding or a small support count (see TP / FP / FN),
not a claim that the detector is perfect.

Public synthetic data differs from your documents. Names, street-only
addresses, fail-Luhn card numbers, and IDs that are not SSN / NINO / SIN
are often missed on purpose by the default layer. This reduces how much
identifiable text you send. **It is not a compliance guarantee.**

Detectors were not tuned against this sample. No detector bugs were
changed for these numbers.

```bash
python3 -m pip install -e ".[ner]" datasets huggingface_hub 'numpy>=2'
python3 -m spacy download en_core_web_sm
python3 scripts/benchmark.py
```

### Fixture regression (not an accuracy claim)

The six fake resumes in `tests/fixtures/resumes.json` are a **regression
test** (`tests/test_benchmark.py`). They check that labeled entities in
those documents still get found after a detector change. They are not a
published accuracy number.

## Limitations

- Regex + heuristics, not a privacy program. Expect false negatives on
  names in prose unless you enable resume mode, NER, or a deny list.
- Street addresses and dates are best-effort. Employment dates are kept
  on purpose (job matching needs them); only DOB-context dates are
  scrubbed.
- A model that invents a new spelling of a name, or drops a placeholder
  entirely, cannot be restored.
- Surrogate mode can collide with text that already contains the fake
  value. Prefer tags unless the model mishandles them.
- Sending *less* PII is not the same as a no-train contract, residency
  control, or GDPR/CCPA compliance.

## Development

```bash
python -m pip install -e ".[dev]"
ruff check src tests examples scripts
ruff format src tests examples scripts
pytest
python -m build && twine check --strict dist/*
```

See [CONTRIBUTING.md](CONTRIBUTING.md) and [RELEASING.md](RELEASING.md).
Version is single-sourced from `src/unseeing/_version.py` (`0.1.0`).

## License

MIT. Copyright (c) 2026 Andy McCutcheon.
