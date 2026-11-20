# Pinpoint verification layer: oracle evaluation

Run on 2026-11-20 with `oracle --check --report evals/results/oracle.md`.

- Documents: 30
- Correct answers given the expected status: **100.0%**
- Faulty answers caught (not verified): **100.0%**

| Case | As expected | Total |
|---|---|---|
| correct | 226 | 226 |
| wrong_page | 226 | 226 |
| hallucinated | 196 | 196 |
| contradicts_quote | 196 | 196 |
| near_miss | 196 | 196 |
| quote_not_in_document | 226 | 226 |
| missing_quote | 226 | 226 |
| invented_field | 14 | 14 |
| swapped_amounts | 40 | 40 |
| untouched | 7810 | 7810 |

Untouched fields sent to review because a check they take part in failed: 276 (counted as expected: when net + tax != total, Pinpoint cannot tell which amount is wrong, so all three go to review).

Fields on scans whose printed text the OCR did not read literally: 3 (for these, a correct value is expected to go to review rather than be verified).
