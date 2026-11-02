# PRD: Recon Investigator

## 1. One-line summary

An AI-assisted system that detects, investigates and explains discrepancies
between a bank statement and an internal ledger, where **deterministic code
decides every match** and **AI only explains, under a verifier**.

## 2. The problem

Businesses keep two sets of financial records that should agree: the bank
statement and the internal accounting ledger. They rarely do. Analysts spend
hours matching lines by hand and chasing causes: missing transactions,
duplicate entries, amount differences, bank fees, date shifts, split payments
and inconsistent references.

Matching alone is a solved-enough problem. The hard problem is **trust**: if
an AI says "these match" or "this is a duplicate", how does a finance person
know it is right, and how does an auditor verify it later?

## 3. Target audience

| Audience | Need |
|---|---|
| Accountants and bookkeepers | Fast, correct matching and a clear list of what to investigate |
| Internal auditors | Evidence per finding, the rule that produced it, a reproducible trail |
| Finance managers | A one-page summary of what is unresolved and why |
| Hiring evaluators of this project | Proof that AI is used with a verifiable trust boundary |

## 4. Core principle

- Deterministic rules decide matches, duplicates, mismatches and missing items.
- The LLM receives an evidence packet per unresolved finding and explains the
  likely cause and recommended action. It never decides, changes or overrides
  a finding.
- A verifier rejects any LLM output that cites facts not in the evidence
  packet. Rejected output is replaced by a deterministic fallback explanation,
  and the rejection is logged.

## 5. Core features (MVP)

| ID | Feature | Description |
|---|---|---|
| F1 | Ingestion | Accept two CSV or single-sheet Excel files (bank, ledger). Auto-detect columns with manual override. Support one signed amount column or separate debit/credit columns. |
| F2 | Normalization and validation | Normalize dates, amounts (integer minor units), references, descriptions. Report row-level validation issues. Invalid rows become `invalid_record` findings and are excluded from matching. |
| F3 | Exact matching | One-to-one matching on amount, normalized reference and a date window. |
| F4 | Fuzzy matching | Scored matching for noisy references and descriptions with explicit, configurable thresholds. |
| F5 | Discrepancy detection | `missing_in_bank`, `missing_in_ledger`, `duplicate_in_bank`, `duplicate_in_ledger`, `amount_mismatch`, `fee_difference`, `date_mismatch`, `ambiguous_split`, `invalid_record`. |
| F6 | Split-payment matching | One-to-many and many-to-one matching with a bounded search. Ambiguous or over-budget cases are reported, never guessed. |
| F7 | Evidence packets | For each discrepancy: records, rule id and version, computed facts, top rejected candidates, allowed causes, allowed values. |
| F8 | AI investigator | LLM explains likely cause and recommended action from the evidence packet only. Output is strict JSON. |
| F9 | Verifier | Validates schema, enums, and that every cited figure, date and ID exists in the packet. Retry once, then deterministic fallback. All outcomes logged. |
| F10 | Audit-ready report | Self-contained HTML (printable to PDF), `findings.json`, `audit_trail.jsonl`. Includes input file hashes, config hash, rule versions, timestamps. |
| F11 | Synthetic data generator | Seeded generator producing bank and ledger files with labeled, injected discrepancies and a ground-truth file. Three difficulty profiles. |
| F12 | Evaluation harness | Precision, recall and F1 per discrepancy type, match accuracy, cause accuracy, and verifier statistics. |
| F13 | Interfaces | CLI (`python -m recon ...`) and a minimal web UI served by FastAPI (upload two files, run, open report). |

## 6. Out of scope

- Real financial data, real bank connections, authentication, user accounts
- Currency conversion (one currency per run; mixed currencies are flagged as
  validation issues)
- Multi-sheet Excel files, PDF statement parsing, OCR
- Learning or training models; matching is rule-based by design
- Writing back to any accounting system

## 7. Success metrics

These are targets to measure against, not guarantees. Actual results are
reported from real evaluation runs only.

| Metric | Target |
|---|---|
| Exact-tier precision on all profiles | at least 0.99 |
| Per-type precision and recall | reported for every discrepancy type, every profile, 3 seeds each |
| LLM-cited figures failing verification in the final report | 0 (any rejected output is replaced by the deterministic fallback) |
| Verifier catch rate on injected faulty LLM outputs | 100% on the fault types in the test suite |
| Run time without LLM, 5,000 rows per file | under 30 seconds on a laptop |
| Reproducibility | same inputs and config produce identical findings and identical config hash |

## 8. Non-functional requirements

- Runs locally. Free resources only. The default LLM provider is `mock`, so
  the whole system and test suite run with no API key and no network.
- The real LLM provider is any OpenAI-compatible endpoint (default: Groq free
  tier).
- Deterministic: seeded generation, stable ordering, no reliance on dict or set
  iteration order for results.
- Money is never a float.
- Works on Windows, macOS and Linux (pathlib, UTF-8, no shell-specific scripts).
- Synthetic data only. No real personal or financial data in the repository.

## 9. Acceptance for the project as a whole

1. `pytest -q` passes from a clean clone with no network and no API key.
2. `python -m recon demo` generates data, runs the pipeline and produces a
   report in under one minute.
3. `python -m recon eval` produces the per-type metrics table for all profiles.
4. The report shows, for every discrepancy, its rule, evidence, explanation
   source (AI verified or deterministic fallback) and recommended action.
5. All quest deliverables in `quest-submission/` are complete and consistent
   with the actual results in `reports/`.
