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

## Benchmark (synthetic fixture set)

Measured by `tests/test_benchmark.py` on the six labeled fake resumes and
background-check form in `tests/fixtures/resumes.json` (37 unique entities).
These numbers describe **this fixture set**, not the open web.

| | Precision | Recall |
| --- | ---: | ---: |
| **Overall** | 1.00 | 1.00 |
| EMAIL / PHONE / PERSON (resume mode) | 1.00 | 1.00 |
| SSN / NATIONAL_ID / IBAN / CREDIT_CARD | 1.00 | 1.00 |
| LINKEDIN / GITHUB / URL / IP_ADDRESS | 1.00 | 1.00 |
| STREET_ADDRESS / DATE_OF_BIRTH | 1.00 | 1.00 |

A perfect score here means the detectors match the labels we wrote for these
synthetic documents. Real documents score lower: names without NER,
unconventional phones, and addresses that do not look like US/UK street
lines will be missed. GitHub *repositories* are deliberately not treated as
profiles.

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
ruff check src tests examples
ruff format src tests examples
pytest
python -m build && twine check --strict dist/*
```

See [CONTRIBUTING.md](CONTRIBUTING.md) and [RELEASING.md](RELEASING.md).
Version is single-sourced from `src/unseeing/_version.py` (`0.1.0`).

## License

MIT. Copyright (c) 2026 Andy McCutcheon.
