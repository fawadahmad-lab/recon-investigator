# Recon Investigator

An AI-assisted system that detects, investigates and explains discrepancies
between a bank statement and an internal ledger.

**Principle:** deterministic code decides every match. The LLM only explains
unresolved findings from an evidence packet, and a verifier checks every LLM
output. Anything that fails verification is replaced by a deterministic
fallback.

Built for the Match Hire quest "Use Your Superpower". Synthetic data only.

## Requirements

- Python 3.11 or newer
- No API key is needed to run the demo, the tests, or the evaluation (the
  default LLM provider is `mock`)

## Setup

Windows (PowerShell):

```
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

macOS or Linux:

```
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## Run

Every command below was run against this repository before it was committed.

```
python -m recon demo                      # generate data, run the pipeline, print the report path
python -m recon generate --profile realistic --seed 42 --out data/synthetic/realistic_42
python -m recon run --bank data/synthetic/realistic_42/bank.csv --ledger data/synthetic/realistic_42/ledger.csv --out reports/my_run --llm mock
python -m recon eval --profiles easy realistic hard --seeds 1 2 3 --llm mock
python -m recon serve                     # web UI at http://127.0.0.1:8000
pytest -q                                 # tests
ruff check .                              # lint
```

- `demo` runs offline in about a second (the default is `--llm mock`; name
  `--llm groq` to use a real provider) and writes `reports/demo/report.html`.
- `run` and `serve` take the provider from `--llm` and from `LLM_PROVIDER`
  respectively, so set `LLM_PROVIDER=mock` (or pass `--llm mock`) to stay offline.
- `eval` writes `reports/eval_<profile>_<seed>.json` per run and finishes by
  rebuilding `reports/final_eval.md` from those files. A provider other than
  `none` or `mock` adds its name to the file name.
- `serve` listens on port 8000 unless `--port` says otherwise; if that port is
  taken, the command fails with `address already in use`.

## Using a real LLM (optional, free tier)

In `.env` set `LLM_PROVIDER=groq` and `LLM_API_KEY=<your key>`. Check that
`LLM_MODEL` is a model currently offered by your provider. Then add
`--llm groq` to `demo`, `run` or `eval`; `serve` has no flag and follows
`LLM_PROVIDER`. On a free tier the explanation stage is rate limited: one
measured run of 63 evidence packets returned 126 HTTP 429 responses against 55
successful completions, and the affected explanations fell back to deterministic
text instead of failing the run.

## Project documents

| File | Purpose |
|---|---|
| `docs/PRD.md` | what is built, for whom, and why |
| `docs/Architecture.md` | flow, structure, stack, matching rules, contracts |
| `docs/Rules.md` | rule book for the AI build agent |
| `docs/Design.md` | colors, typography, components, spacing |
| `docs/Task.md` | the build broken into small tasks |
| `docs/Memory.md` | decisions, status and bug log kept by the agent |
| `quest-submission/` | all quest deliverables |

## Outputs of a run

The `--out` folder of `run`, and `reports/demo/` for `demo`, contains
`report.html`, `findings.json`, `run_meta.json`, `audit_trail.jsonl` and, with a
provider, `verifier_log.jsonl`. The web UI writes the same files under
`reports/web/<run_id>/`. `python -m recon eval` writes
`reports/eval_<profile>_<seed>.json` per run and rebuilds
`reports/final_eval.md` from them.
