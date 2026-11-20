# Pinpoint with qwen2.5:7b

Run on 2026-11-20 with `openai --base-url http://host.docker.internal:11434/v1 --model qwen2.5:7b --report evals/results/qwen2.5-7b.md --json evals/results/qwen2.5-7b.json`.

- Documents: 30, fields: 240
- Field accuracy: **96.7%**
- Verified fields that were correct: **98.6%**
- Wrong values marked verified (confidently wrong): **3** of 8 wrong values
- Statuses: missing 19, review 6, unverified 2, verified 213
- Median time per document: 17.0 s

## Wrong values

| Document | Field | Expected | Got | Status |
|---|---|---|---|---|
| invoice-01 | iban | GB33 BUKB 2020 1555 5555 55 | None | missing |
| invoice-05 | iban | DE89 3704 0044 0532 0130 00 | None | missing |
| invoice-01-scan | supplier | Nordlicht Bürobedarf GmbH | Nordlicht Burobedarf GmbH | verified |
| invoice-01-scan | iban | GB33 BUKB 2020 1555 5555 55 | None | missing |
| invoice-05-scan | iban | DE89 3704 0044 0532 0130 00 | None | missing |
| invoice-09-scan | supplier | Nordlicht Bürobedarf GmbH | Nordlicht Burobedarf GmbH | verified |
| invoice-13-scan | iban | FR14 2004 1010 0505 0001 3M02 606 | None | missing |
| receipt-01-scan | merchant | Bäckerei Sonnenschein | Backerei Sonnenschein | verified |
