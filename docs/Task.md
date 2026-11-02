# Task list: Recon Investigator

Rules: complete the tasks at once upon user request. move to new task  only when every acceptance item
passes and the verify commands have been run. After each task, follow
`docs/Rules.md` section 9. Task status lives in `docs/Memory.md`.

Conventions used below: `$` lines are commands the human runs and pastes
errors from. "Tests" means pytest tests in `tests/` mirroring `recon/`.

---

## T00 Bootstrap

**Goal:** runnable skeleton with tooling.
**Build:** package skeleton exactly as in `docs/Architecture.md` section 4
(empty modules with docstrings are fine), `requirements.txt`, `pytest.ini`
(`pythonpath = .`), `ruff` config in `pyproject.toml` (lint and format only),
`recon/config.py` (all settings and defaults from Architecture section 8 and
the LLM settings, loaded from environment and `.env`), `recon/errors.py`,
`recon/logging_setup.py`, `recon/__main__.py` and `recon/cli.py` with
`--help` and a `version` command, `recon/assets/tokens.css` from
`docs/Design.md`, `.gitignore` (include `.env`, `.venv`, `__pycache__`,
`.cache/`, `data/synthetic/*` except `.gitkeep`, `reports/*` except
`.gitkeep` and `final_eval.md`).
**Acceptance:** `python -m recon --help` works; config loads defaults with no
`.env`; one smoke test passes; `ruff check .` clean.
**Verify:**
```
$ python -m venv .venv
$ pip install -r requirements.txt
$ python -m recon --help
$ pytest -q
$ ruff check .
```

## T01 Domain models

**Build:** `recon/models.py`: `Transaction`, `Finding`, `ValidationIssue`,
`EvidencePacket`, `Explanation`, enums for finding types, status, severity.
Money helpers (`to_minor`, `from_minor`, `format_amount`) using `Decimal`.
**Acceptance:** models validate and serialize to JSON; money helpers
round-trip for positive, negative, and 3-decimal rounding cases; no floats in
money paths.
**Verify:** `$ pytest -q tests/test_models.py`

## T02 Ingestion

**Build:** `recon/ingest/`: CSV and single-sheet XLSX loaders (encoding
fallback, delimiter sniffing), column auto-mapping using the synonym lists
(date, amount, debit, credit, reference, description, currency,
counterparty), manual `column_map` override, `MappingError` listing the
headers found when a required column is missing. Enforce 10 MB and 50,000 row
limits.
**Acceptance:** works for fixtures with different header names, debit/credit
columns, semicolon delimiters, BOM; clear errors for empty file, missing
columns and oversize.
**Verify:** `$ pytest -q tests/ingest`

## T03 Normalization and validation

**Build:** `recon/normalize/` per Architecture section 7, `validate.py` with
row-level `ValidationIssue`s (missing date, unparsable amount, zero amount,
mixed currency, duplicate row id). Output `Transaction` lists with IDs
`L-000001` / `B-000001` from file row numbers.
**Acceptance:** tests cover date formats including Excel serials, `(123.45)`,
thousands separators, reference normalization, sign inversion, invalid rows
excluded with issues recorded.
**Verify:** `$ pytest -q tests/normalize`

## T04 Synthetic data generator

**Build:** `recon/synth/` per Architecture section 12: profiles `easy`,
`realistic`, `hard`, seeded generation, labeled injections with exact counts,
decoys, shuffled bank rows with IDs assigned after the shuffle,
`ground_truth.json`, CLI `generate`.
**Acceptance:** same seed gives byte-identical files; injected counts match the
profile table; ground truth IDs exist in the generated files; decoys are
present in ground truth as matches, not discrepancies.
**Verify:**
```
$ pytest -q tests/synth
$ python -m recon generate --profile realistic --seed 42 --out data/synthetic/realistic_42
```

## T05 Tier 1 exact matcher

**Build:** `recon/matching/keys.py`, `exact.py` with deterministic one-to-one
assignment and blocking.
**Acceptance:** one-to-one property holds; legitimate repeated payments match
pairwise; ties resolved by the documented sort key; unit tests plus a
5,000-row timing test.
**Verify:** `$ pytest -q tests/matching/test_exact.py`

## T06 Evaluation harness v1

**Build:** `recon/evaluation/metrics.py` and `runner.py`, CLI `eval` for
matching only (LLM disabled for now). Per-type precision, recall, F1, match
pair precision and recall. Write `reports/eval_<profile>_<seed>.json`.
**Acceptance:** metrics are correct on hand-built toy cases; running on
`realistic` seed 42 with only Tier 1 shows meaningful recall gaps (expected at
this stage).
**Verify:** `$ python -m recon eval --profiles realistic --seeds 42 --llm mock`

## T07 Tier 2 fuzzy matcher, amount mismatch, fee difference, date mismatch

**Build:** `recon/matching/fuzzy.py` and `classify.py` implementing steps 2, 4
and 5 of Architecture section 8 with all thresholds from config.
**Acceptance:** tests for each step including unique-best-candidate margin and
fee versus amount classification; eval shows improved recall.
**Verify:**
```
$ pytest -q tests/matching
$ python -m recon eval --profiles realistic --seeds 42 --llm mock
```

## T08 Duplicate detection

**Build:** `recon/matching/duplicates.py` implementing step 3 (multiplicity
aware). Wire it into the engine order.
**Acceptance:** legitimate repeated payments on both sides are never flagged;
a doubled ledger entry becomes `duplicate_in_ledger` linked to its primary;
same for bank; decoys in `hard` do not produce false positives (check eval).
**Verify:** `$ pytest -q tests/matching/test_duplicates.py`

## T09 Split-payment matcher

**Build:** `recon/matching/split.py` implementing step 6: bounded search in
both directions, unique solution, ambiguous listing, truncation flag.
**Acceptance:** tests for 2, 3 and 4 part splits, both directions, ambiguity,
budget truncation producing an unmatched anchor with the flag, determinism.
**Verify:** `$ pytest -q tests/matching/test_split.py`

## T10 Engine, missing classification, run pipeline and CLI run

**Build:** `recon/matching/engine.py` with `run_pipeline()` (steps 1 to 8,
severity assignment, stable finding IDs), CLI `run` writing `findings.json`
and `run_meta.json` (no LLM yet).
**Acceptance:** every valid record appears in exactly one finding (property
test); output identical across two runs; `invalid_record` findings present for
bad rows.
**Verify:**
```
$ pytest -q
$ python -m recon run --bank data/synthetic/realistic_42/bank.csv --ledger data/synthetic/realistic_42/ledger.csv --out reports/run_realistic_42
```

## T11 Error analysis checkpoint (matching quality)

**Build:** run `eval` on all profiles and seeds 1, 2, 3. Write the three
largest failure modes into `docs/Memory.md` (Bug log), with example record
IDs. Fix at most two of them in the matching code (document each threshold or
rule change and why). Re-run eval.
**Acceptance:** before and after tables saved as
`reports/error_analysis_before.md` and `reports/error_analysis_after.md`;
changes explained; no regression on exact-tier precision.
**Verify:** `$ python -m recon eval --profiles easy realistic hard --seeds 1 2 3 --llm mock`

## T12 Evidence packets

**Build:** `recon/evidence/packet.py` per Architecture section 9 including
`allowed_values` and the allowed-causes table, packet hash.
**Acceptance:** a packet exists for every discrepancy type that uses the LLM;
`allowed_values` contains every amount, date and ID that appears in the
packet; packets serialize deterministically.
**Verify:** `$ pytest -q tests/evidence`

## T13 LLM providers

**Build:** `recon/llm/base.py`, `mock.py`, `openai_compat.py`, `prompts.py`,
`schema.py`, `cache.py`, and a `faulty_mock` provider. System prompt follows
Architecture section 10. Real provider: JSON mode, timeout, concurrency limit,
429 backoff, on-disk cache.
**Acceptance:** `mock` yields valid output for every allowed-cause case;
`faulty_mock` produces each fault type (invented amount, invalid enum, decision
override, malformed JSON) deterministically; real provider has unit tests with
a stubbed HTTP layer (no network).
**Verify:** `$ pytest -q tests/llm`

## T14 Verifier

**Build:** `recon/llm/verifier.py` with all six checks, failure codes
(`schema_invalid`, `bad_enum`, `unsupported_cited_fact`, `unsupported_figure`,
`decision_override`, `confidence_inconsistent`), retry once with error
feedback, deterministic fallback, `verifier_log.jsonl`.
**Acceptance:** a test per failure code using `faulty_mock`; verifier catches
100% of injected faults in the test suite; valid mock output passes; fallback
explanations are deterministic and marked.
**Verify:** `$ pytest -q tests/llm/test_verifier.py`

## T15 Explanation pipeline

**Build:** `recon/llm/explain.py` connecting packets, provider and verifier;
bounded concurrency; cache; deterministic one-line rationales for matches and
`invalid_record`; integrate into `run_pipeline()` and CLI `run --llm`.
**Acceptance:** with `mock`, every discrepancy has an explanation; with
`faulty_mock`, the run completes, all faults are caught, and fallbacks are
flagged; findings (types and record IDs) are identical with and without the
LLM (property test).
**Verify:**
```
$ pytest -q
$ python -m recon run --bank data/synthetic/realistic_42/bank.csv --ledger data/synthetic/realistic_42/ledger.csv --out reports/run_with_ai --llm mock
```

## T16 Report

**Build:** `recon/report/` producing `report.html` (Jinja2, inlined tokens, per
`docs/Design.md` section 7), `findings.json`, `audit_trail.jsonl`,
`run_meta.json` with SHA-256 hashes and config hash.
**Acceptance:** report is a single file with no external requests; contains
method statement, summary, inputs, findings with evidence and AI boxes,
matched table, appendix; prints cleanly (check `@media print` rules exist);
test asserts no `http://` or `https://` resource references except plain text.
**Verify:**
```
$ pytest -q tests/report
$ python -m recon run --bank data/synthetic/realistic_42/bank.csv --ledger data/synthetic/realistic_42/ledger.csv --out reports/run_report --llm mock
```
Open `reports/run_report/report.html` in a browser.

## T17 API and web UI

**Build:** `recon/api/` and `static/` per Architecture section 13 and
`docs/Design.md` section 6, CLI `serve`. Endpoints, error shape, limits,
"Load demo data" button, stepper, KPI cards, findings table with filters, link
to the report.
**Acceptance:** API tests with FastAPI `TestClient`; upload of the demo files
works end to end; bad file returns the JSON error shape; UI loads at
`http://127.0.0.1:8000`.
**Verify:**
```
$ pytest -q tests/api
$ python -m recon serve
```

## T18 End-to-end and final evaluation

**Build:** `demo` command; end-to-end test (generate, run, report, evaluate);
final evaluation across `easy`, `realistic`, `hard` with seeds 1, 2, 3 using
`mock`, plus verifier statistics using `faulty_mock`; aggregate
`reports/final_eval.md` with the per-type table (precision, recall, F1, TP, FP,
FN), match accuracy, cause accuracy (state the provider), verifier stats, and
an honest limitations paragraph. If `LLM_API_KEY` is set, also run `eval
--llm groq` on `realistic` seed 1 and add a separate section for it.
**Acceptance:** `final_eval.md` numbers come from saved JSON files; all tests
pass; `python -m recon demo` finishes under one minute.
**Verify:**
```
$ pytest -q
$ python -m recon eval --profiles easy realistic hard --seeds 1 2 3 --llm mock
$ python -m recon demo
```

## T19 Quest documents

**Build:** produce `quest-submission/write-up.md` from
`write-up.TEMPLATE.md` using only real data: the Bug log in `docs/Memory.md`,
`quest-submission/ai-usage-log.md`, and `reports/final_eval.md`. Finalize the
usage log (add the final tally). Update the revision table in
`quest-submission/Final-directive.md` with any direction changes that really
happened. Update `README.md` so every command is verified to work. Update
`quest-submission/SUBMISSION-CHECKLIST.md` statuses. Do not edit
`loom-scripts.md` except to fix commands that no longer match the CLI.
**Acceptance:** no placeholder text remains; every number in the write-up
appears in `reports/final_eval.md`; every failure in the write-up appears in the
Bug log or usage log; write-up is at most two pages.
**Verify:** search the quest folder for `TODO`, `TBD`, `{{` and `AGENT:`; none
may remain.

## T20 Release check

**Build:** from a clean checkout simulation: fresh venv, install, `pytest -q`,
`python -m recon demo`, `python -m recon serve` (start and stop), `ruff check .`.
Fix anything that fails. Confirm `.env` is ignored and no secrets are present.
Print the final submission checklist with the exact files to upload.
**Acceptance:** all commands succeed; Memory.md status shows T00 to T20 done.
**Verify:** the commands above, run by the human.
