# Changelog

## 0.1.0

- First public release of **unseeing** (`pip install unseeing`).
- Releases publish to PyPI via Trusted Publishing (OIDC). See
  [RELEASING.md](https://github.com/andymccutcheon/unseeing/blob/main/RELEASING.md).
- Built-in regex/validator layer: email, phone, URL, IP, credit card (Luhn),
  SSN and other national IDs, IBAN, street addresses, dates of birth,
  LinkedIn and GitHub profile URLs.
- Optional extras: `unseeing[ner]` (spaCy) and `unseeing[presidio]`.
- Reversible session vault with stable placeholders, possessives / bracket
  tolerance, streamed restore, and optional encrypted-at-rest files.
- Resume / HR mode with consistent pseudonyms across a document and a
  conversation. Configurable employer / school scrubbing and allow/deny lists.
- Realistic surrogate mode for models that behave worse with tags.
- OpenAI (chat completions + Responses) and Anthropic wrappers, including
  tool-call arguments. ASGI middleware and a `ScrubberProtocol` for freewhirr.
- CLI: `unseeing scan`, `unseeing scrub`, `unseeing restore`, `unseeing demo`.
- Audit reports count entity types and never log original values.
