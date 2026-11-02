# Architecture: Recon Investigator

## 1. Tech stack

| Layer | Choice |
|---|---|
| Language | Python 3.11 or newer (if the machine has an older version, record it in Memory.md and adapt) |
| Data | pandas, openpyxl (Excel), `decimal.Decimal` and integer minor units for money |
| Fuzzy matching | rapidfuzz |
| Models and config | pydantic v2, python-dotenv |
| API and UI | FastAPI, uvicorn, python-multipart, vanilla HTML/CSS/JS (no build step) |
| Report | Jinja2 template rendered to one self-contained HTML file |
| LLM | `openai` SDK against any OpenAI-compatible endpoint (default Groq), plus a `mock` provider |
| Tests | pytest |
| Lint and format | ruff |

No database, no Docker, no agent framework. The pipeline is a plain, testable
sequence of pure functions.

## 2. User flow

1. User uploads (or points the CLI at) a bank file and a ledger file.
2. System detects columns and shows the mapping (override possible).
3. System normalizes and validates; shows row-level issues.
4. System runs the matching pipeline and lists matched and unresolved items.
5. For each discrepancy the investigator produces an explanation, verified.
6. User opens the audit-ready report and downloads `findings.json`.

## 3. Pipeline (single run)

```
bank file ─┐
           ├─> ingest ─> normalize ─> validate ─> matching engine ─> findings
ledger file┘                                          │
                                                      v
                                           evidence packets (per discrepancy)
                                                      │
                                                      v
                              LLM investigator ─> verifier ─┬─ pass ─> explanation (ai_verified)
                              (mock | groq)        │        └─ fail ─> retry once ─> fallback (deterministic)
                                                      v
                                              report + findings.json + audit_trail.jsonl
```

Trust boundary: everything left of "LLM investigator" is deterministic code.
The LLM and verifier only produce the `explanation` field of a finding.

## 4. Folder structure

```
recon-investigator/
├── AGENTS.md
├── README.md
├── .env.example
├── .gitignore
├── requirements.txt              (created in T00)
├── pytest.ini                    (created in T00)
├── docs/                         PRD, Architecture, Rules, Design, Task, Memory
├── prompts/                      first prompt and prompt templates
├── quest-submission/             all Match Hire quest deliverables
├── recon/
│   ├── __init__.py  __main__.py  cli.py  config.py  errors.py  logging_setup.py  models.py
│   ├── assets/tokens.css         design tokens shared by UI and report
│   ├── ingest/        loaders.py  column_map.py  validate.py
│   ├── normalize/     dates.py  amounts.py  references.py  text.py  pipeline.py
│   ├── matching/      keys.py  exact.py  fuzzy.py  duplicates.py  split.py  classify.py  engine.py
│   ├── evidence/      packet.py
│   ├── llm/           base.py  openai_compat.py  mock.py  prompts.py  schema.py
│   │                  verifier.py  explain.py  cache.py
│   ├── report/        builder.py  audit.py  templates/report.html.j2
│   ├── synth/         generator.py  profiles.py  truth.py
│   ├── evaluation/    metrics.py  runner.py
│   └── api/           app.py  routes.py  static/index.html  static/app.js  static/app.css
├── tests/                        mirrors the recon/ layout
├── data/synthetic/               generated data (gitignored except .gitkeep)
└── reports/                      run outputs and evaluation results
```

## 5. Components and how they connect

| Component | Input | Output |
|---|---|---|
| `ingest` | file path or bytes, optional column map | raw DataFrame plus detected mapping |
| `normalize` | raw DataFrame, source name, config | list of canonical `Transaction` plus validation issues |
| `matching.engine` | bank and ledger `Transaction` lists, config | list of `Finding` (matches and discrepancies) |
| `evidence.packet` | `Finding`, transactions, config | `EvidencePacket` |
| `llm.explain` | `EvidencePacket`, provider | `Explanation` (verified or fallback) |
| `report.builder` | findings, run metadata | `report.html`, `findings.json`, `audit_trail.jsonl` |
| `synth` | profile name, seed | `bank.csv`, `ledger.csv`, `ground_truth.json` |
| `evaluation` | findings, ground truth, explanations | metrics JSON and markdown table |
| `api` and `cli` | user input | calls the same `run_pipeline()` function |

The CLI and API are thin. All logic lives in a single `run_pipeline()` function
in `recon/matching/engine.py` plus `recon/llm/explain.py`, called by both.

## 6. Canonical models (pydantic v2)

`Transaction`: `id` (`L-000123` or `B-000123`, from the 1-based data row number
in the uploaded file), `source` (`bank` or `ledger`), `row_number`, `date`
(ISO date), `amount_minor` (signed int; cash in is positive), `currency`,
`reference_raw`, `reference_norm`, `description_raw`, `description_norm`,
`counterparty` (optional), `raw` (original row dict).

`Finding`: `id` (`F-0001`, stable ordering), `type`, `status`
(`matched`, `discrepancy`, `needs_review`), `ledger_ids`, `bank_ids`,
`rule_id`, `rule_version`, `score` (optional), `facts` (dict), `severity`,
`explanation` (optional).

Finding types:

- Matches: `match_exact`, `match_fuzzy`, `match_split`
- Discrepancies: `missing_in_bank`, `missing_in_ledger`, `duplicate_in_bank`,
  `duplicate_in_ledger`, `amount_mismatch`, `fee_difference`, `date_mismatch`,
  `ambiguous_split`, `invalid_record`

Severity (by absolute amount, thresholds in config): `high`, `medium`, `low`.

## 7. Normalization rules

- Dates: parse common formats (ISO, DD/MM/YYYY, MM/DD/YYYY via explicit config
  `DATE_DAYFIRST`, `DD-Mon-YYYY`), Excel serial dates. Unparsable becomes a
  validation issue.
- Amounts: strip currency symbols and thousands separators, handle `(123.45)`
  as negative, parse with `Decimal`, convert to integer minor units
  (2 decimals by default). Debit/credit columns combine into one signed amount.
  `LEDGER_SIGN_INVERTED=true` flips the ledger sign.
- References: uppercase, strip spaces, hyphens, underscores and common prefixes
  (`REF`, `INV`, `PAYMENT`, `TRF`) into `reference_norm`; keep `reference_raw`.
  Empty after normalization means "no reference".
- Descriptions: lowercase, collapse whitespace, strip punctuation and digits
  runs that are pure noise (card masks, timestamps).

## 8. Matching engine (order is fixed)

Records with validation errors are excluded first. Every step is one-to-one and
deterministic: candidate pairs are sorted by (score descending, date
difference ascending, ledger id, bank id) and taken greedily if both sides are
still free. Use blocking (index by amount or sorted structures) so 5,000 rows
per side runs in under 30 seconds.

1. **Tier 1, exact** (`match_exact`, rule `R1-EXACT`): same currency, same
   `amount_minor`, non-empty equal `reference_norm`, date difference at most
   `DATE_WINDOW_EXACT_DAYS`.
2. **Tier 2, fuzzy** (`match_fuzzy`, rule `R2-FUZZY`): same currency, same
   `amount_minor`, date difference at most `DATE_WINDOW_FUZZY_DAYS`.
   `score = 0.5*ref_sim + 0.35*desc_sim + 0.15*date_sim`, where `ref_sim` and
   `desc_sim` are rapidfuzz token-set ratios divided by 100 (0 if either side
   is empty) and `date_sim = 1 - days/DATE_WINDOW_FUZZY_DAYS`. Accept if
   `score >= FUZZY_ACCEPT`.
3. **Duplicates** (`duplicate_in_bank`, `duplicate_in_ledger`, rule
   `R3-DUP`): an unmatched record that is key-identical (same currency, amount,
   `reference_norm`, date within `DUP_DATE_WINDOW_DAYS`) to a record of the
   **same source that was matched** is a duplicate of it. Legitimate repeated
   payments exist on both sides, match one-to-one in steps 1 and 2, and are
   therefore never flagged. Duplicates are excluded from later steps and linked
   to their primary record.
4. **Amount mismatch and fee difference** (`amount_mismatch`,
   `fee_difference`, rule `R4-AMT`): among the remaining records, pair a ledger
   and bank record with the same currency and sign, date within
   `DATE_WINDOW_FUZZY_DAYS`, `ref_sim >= REF_STRONG`, different amounts, and a
   unique best candidate (best score exceeds the runner-up by at least
   `PAIR_MARGIN`). If the bank absolute amount is lower than the ledger
   absolute amount and the difference is at most `FEE_MAX_MINOR`, classify as
   `fee_difference`; otherwise `amount_mismatch`.
5. **Date mismatch** (`date_mismatch`, rule `R5-DATE`): same currency, amount
   and non-empty equal `reference_norm`, date difference above
   `DATE_WINDOW_FUZZY_DAYS` and at most `DATE_MISMATCH_MAX_DAYS`.
6. **Split payments** (`match_split`, `ambiguous_split`, rule `R6-SPLIT`): for
   each remaining anchor record, search for 2 to `SPLIT_MAX_PARTS` records on
   the other side with the same sign and currency, date within
   `SPLIT_DATE_WINDOW_DAYS` of the anchor, whose amounts sum to the anchor
   amount within `SPLIT_TOLERANCE_MINOR`. The candidate pool is limited to the
   top `SPLIT_MAX_POOL` records by similarity to the anchor (minimum
   `SPLIT_MIN_SIM`). Exactly one solution: `match_split`. More than one:
   `ambiguous_split` listing up to 3 candidate sets, and nothing is matched.
   Search budget (`SPLIT_MAX_NODES`) exceeded: the anchor stays unmatched and
   its evidence records `split_search_truncated: true`. Never guess.
7. **Missing** (`missing_in_bank`, `missing_in_ledger`, rule `R7-MISSING`):
   every remaining unmatched record.
8. **Invalid** (`invalid_record`, rule `R0-INVALID`): rows rejected in
   validation.

### Config defaults (`recon/config.py`, overridable via environment)

| Name | Default |
|---|---|
| `DATE_WINDOW_EXACT_DAYS` | 3 |
| `DATE_WINDOW_FUZZY_DAYS` | 10 |
| `DATE_MISMATCH_MAX_DAYS` | 30 |
| `FUZZY_ACCEPT` | 0.75 |
| `REF_STRONG` | 0.90 |
| `PAIR_MARGIN` | 0.05 |
| `DUP_DATE_WINDOW_DAYS` | 3 |
| `FEE_MAX_MINOR` | 2500 |
| `SPLIT_MAX_PARTS` | 4 |
| `SPLIT_DATE_WINDOW_DAYS` | 7 |
| `SPLIT_TOLERANCE_MINOR` | 0 |
| `SPLIT_MAX_POOL` | 30 |
| `SPLIT_MIN_SIM` | 0.4 |
| `SPLIT_MAX_NODES` | 200000 |
| `SEVERITY_HIGH_MINOR` | 1000000 |
| `SEVERITY_MEDIUM_MINOR` | 100000 |
| `DEFAULT_CURRENCY` | `USD` |
| `DATE_DAYFIRST` | `false` |
| `LEDGER_SIGN_INVERTED` | `false` |

Every threshold must be recorded in the report's config appendix and hashed
into the config hash.

## 9. Evidence packet (contract)

```json
{
  "packet_version": "1",
  "finding_id": "F-0007",
  "finding_type": "amount_mismatch",
  "rule": {"id": "R4-AMT", "version": "1", "description": "..."},
  "records": [{"role": "ledger", "id": "L-000042", "row_number": 42,
               "date": "2026-03-04", "amount": "1250.00", "currency": "USD",
               "reference_raw": "INV-2031", "reference_norm": "2031",
               "description_raw": "Acme Supplies"}],
  "candidates_considered": [{"id": "B-000310", "score": 0.91,
               "components": {"ref_sim": 0.95, "desc_sim": 0.8, "date_sim": 0.7},
               "rejected_reason": "amount differs"}],
  "facts": {"amount_diff": "25.00", "date_diff_days": 2, "ref_similarity": 0.95},
  "allowed_causes": ["typo_or_transposition", "partial_payment",
                     "discount_or_adjustment", "fx_or_rounding", "unknown"],
  "allowed_values": {"amounts": ["1250.00", "1225.00", "25.00"],
                     "dates": ["2026-03-04", "2026-03-06"],
                     "ids": ["F-0007", "L-000042", "B-000310"],
                     "numbers": ["2", "0.95"]}
}
```

`allowed_values` is built by code from the packet itself. Amounts are strings
with 2 decimals. At most 3 candidates are included.

Allowed causes by finding type:

| Type | Allowed causes |
|---|---|
| `missing_in_bank` | `timing_delay_not_cleared`, `payment_not_sent`, `recorded_in_wrong_period`, `recorded_in_error`, `bank_statement_incomplete`, `unknown` |
| `missing_in_ledger` | `unrecorded_bank_item`, `bank_fee_or_interest`, `unexpected_or_unauthorized`, `recorded_in_other_account`, `unknown` |
| `duplicate_in_ledger` | `double_entry_in_ledger`, `bank_missing_second_payment`, `unknown` |
| `duplicate_in_bank` | `duplicate_bank_charge`, `ledger_missing_second_entry`, `unknown` |
| `amount_mismatch` | `typo_or_transposition`, `partial_payment`, `discount_or_adjustment`, `fx_or_rounding`, `unknown` |
| `fee_difference` | `bank_fee_deducted`, `rounding`, `unknown` |
| `date_mismatch` | `late_posting`, `wrong_period_entry`, `unknown` |
| `ambiguous_split` | `multiple_possible_combinations`, `unknown` |

`invalid_record` and all matches do not use the LLM; they get a deterministic
one-line rationale.

## 10. LLM investigator contract

Output must be a single JSON object:

```json
{
  "summary": "string, at most 200 chars",
  "likely_cause": "one value from allowed_causes",
  "explanation": "string, at most 800 chars, plain English, only facts from the packet",
  "cited_facts": [{"field": "string", "value": "string"}],
  "recommended_action": "investigate | request_bank_confirmation | post_adjusting_entry | reverse_duplicate | contact_counterparty | wait_and_recheck | no_action",
  "action_detail": "string, at most 300 chars",
  "confidence": "low | medium | high",
  "uncertainties": ["string"]
}
```

The output has no field for the finding type or any match decision. The system
prompt must state: the model never decides matches; it may cite only values
present in the packet; if the evidence is insufficient it must use `unknown`
with `low` confidence.

### Verifier (all checks mandatory)

1. Valid JSON that satisfies the schema; length limits respected.
2. `likely_cause` is in the packet's `allowed_causes`; action enum is valid.
3. Every `cited_facts[].value` is in `allowed_values` (amounts compared as
   `Decimal`, dates as ISO, IDs exact).
4. Every money amount, date and ID-like token found by regex in `summary`,
   `explanation` and `action_detail` is in `allowed_values`
   (`unsupported_figure` otherwise).
5. No decision-override language (regex list, for example "should be treated
   as matched", "these do match", "is not a duplicate" when the type says
   duplicate). Failure code `decision_override`.
6. `confidence` must be `low` when `likely_cause` is `unknown`.

On failure: retry once, passing the verifier's error codes back to the model.
On a second failure: use the deterministic fallback explanation
(`explanation_source: deterministic_fallback`). Every attempt is written to
`verifier_log.jsonl` with the failure codes and the raw output (raw output is
kept only in the log, never in the report).

### Providers

- `mock`: deterministic, rule-based explanations built from the packet. Default.
- `faulty_mock`: wraps `mock` and injects faults (invented amount, invalid enum,
  decision override, malformed JSON) at a configured rate. Used only in tests
  and in `eval` to measure the verifier catch rate.
- `groq` / `openai_compat`: real calls with `LLM_BASE_URL`, `LLM_API_KEY`,
  `LLM_MODEL`, JSON output mode, timeout, concurrency limit, backoff on rate
  limits, and an on-disk cache keyed by packet hash plus model name.

## 11. Run artifacts (`reports/<run_id>/`)

| File | Content |
|---|---|
| `report.html` | Self-contained, printable audit report |
| `findings.json` | All findings with evidence and explanations |
| `audit_trail.jsonl` | One line per step: ingest, normalize, each rule application, each LLM attempt and verifier outcome |
| `verifier_log.jsonl` | Verifier attempts and outcomes |
| `run_meta.json` | Run id, timestamps, tool version, SHA-256 of both input files, config and config hash, LLM provider and model |

`run_id` is `YYYYMMDD-HHMMSS-<first 8 chars of config hash>`.

## 12. Synthetic data and evaluation

Generator (`recon/synth`): seeded. Builds a base ledger (realistic vendors,
references like `INV-2026-0042`, descriptions), derives the bank file (date lag
0 to 3 days, reference noise: case, prefix removal, spacing, typos,
truncation), then injects labeled problems with exact counts. The bank file
rows are shuffled before IDs are assigned (IDs come from the final file row
numbers). Decoys are mandatory: legitimate repeated same-amount payments that
must not be flagged.

| Profile | Rows (ledger) | Injected per type | Noise |
|---|---|---|---|
| `easy` | 200 | 5 of each discrepancy type, 4 splits | low reference noise |
| `realistic` | 500 | 10 missing each side, 6 duplicates each side, 8 amount mismatch, 8 fee difference, 8 date mismatch, 8 splits, 2 ambiguous splits, 10 legitimate-repeat decoys | moderate |
| `hard` | 1000 | about double `realistic`, 6 ambiguous splits, 20 decoys | heavy: 15% of references missing, up to 5 days lag, near-duplicate decoys |

`ground_truth.json`:

```json
{"profile": "realistic", "seed": 42,
 "matches": [{"type": "match_exact", "ledger_ids": ["L-000001"], "bank_ids": ["B-000917"]}],
 "expected": [{"type": "amount_mismatch", "ledger_ids": ["L-000042"],
               "bank_ids": ["B-000310"], "cause": "typo_or_transposition"}]}
```

Metrics (`recon/evaluation`): a predicted finding is a true positive when its
type and its set of record IDs equal an expected entry. Report per type and
overall: precision, recall, F1, counts of TP, FP, FN; match-pair precision and
recall; `cause_accuracy` (LLM `likely_cause` against ground-truth `cause` on
correctly detected findings, per provider); verifier statistics (pass on first
try, pass after retry, fallback, catch rate on injected faults). Results are
written to `reports/eval_<profile>_<seed>.json` and aggregated to
`reports/final_eval.md`.

## 13. Interfaces

CLI (`python -m recon <command>`):

| Command | Purpose |
|---|---|
| `generate --profile realistic --seed 42 --out data/synthetic/realistic_42` | Create synthetic files and ground truth |
| `run --bank B.csv --ledger L.csv --out reports/my_run [--llm mock]` | Run the pipeline |
| `eval --profiles easy realistic hard --seeds 1 2 3 --llm mock` | Evaluate against ground truth |
| `demo` | Generate, run, and print the path to the report |
| `serve [--port 8000]` | Start the web UI and API |

API (FastAPI): `GET /` (UI), `POST /api/run` (multipart: `bank`, `ledger`,
optional `column_map` JSON), `GET /api/runs/{run_id}`,
`GET /api/runs/{run_id}/report`, `POST /api/demo`, `GET /api/health`.
Errors return `{"error": {"code": "...", "message": "...", "details": {}}}`.
Limits: 10 MB per file, 50,000 rows per file.

## 14. Error handling

Exception hierarchy in `recon/errors.py`: `ReconError` with `IngestError`,
`MappingError`, `ValidationError`, `MatchingError`, `LLMError`,
`VerificationError`, `ReportError`. The CLI prints a clean message and exits
with code 2. The API maps these to 400 or 422, unexpected errors to 500. LLM
failures never fail the run: they trigger the deterministic fallback and are
logged.
