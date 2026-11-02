# Rules: Recon Investigator

These rules are binding for the build agent. If a rule conflicts with a task,
follow the rule and record the conflict in `docs/Memory.md`.

## 1. MUST

1. Read `docs/Memory.md`, `docs/Rules.md` and `docs/Task.md` at the start of
   every turn.
2. Work on exactly one task per turn until user asks for multiple tasks in one run .
3. Keep deterministic code as the only decision-maker for matches and finding
   types. The LLM may only produce the `explanation` of a finding.
4. Represent money as integer minor units internally and `Decimal` at the edges.
5. Make every run reproducible: seeded generation, stable sort keys, no
   dependence on dict or set iteration order for outputs.
6. Write tests for every module in the same task that creates it. Tests must run
   offline and without an API key.
7. Run the verify commands of the task before reporting. Report the real
   output. If a command fails, say so.
8. Use type hints on all functions, short docstrings on public functions, and
   `ruff` clean code (`ruff check .` and `ruff format .`).
9. Use `pathlib`, explicit UTF-8, and no shell-specific scripts (Windows,
   macOS and Linux must all work).
10. Load settings from environment via `recon/config.py`. Provide defaults for
    everything except API keys.
11. Log with the `logging` module (structured, no secrets). `print` is allowed
    only for CLI user output.
12. After every task, update `docs/Memory.md` and append to
    `quest-submission/ai-usage-log.md`.
13. Pin dependency versions in `requirements.txt` after confirming they install
    and the tests pass.
14. Keep functions under about 60 lines and modules focused on one job.

## 2. MUST NOT

1. Never let the LLM decide, change, create or remove a match or a finding.
2. Never use `float` for money, and never compare money using floats.
3. Never call the network in tests. Use the `mock` and `faulty_mock` providers.
4. Never hard-code API keys, model names or URLs outside `config.py` and
   `.env.example`. Never commit `.env`. Never log secrets.
5. Never use real financial or personal data. Synthetic data only.
6. Never swallow exceptions. No bare `except:`. Catch specific exceptions and
   re-raise as a `ReconError` subclass with a clear message.
7. Never fabricate or estimate results, metrics, test outcomes, or log entries.
   Numbers in the write-up must come from files in `reports/`.
8. Never mark a task done when its acceptance criteria are not met.
9. Never add features outside the PRD or start the next task early.
10. Never rewrite finished modules without a failing test or a bug that
    justifies it. Record the reason in `docs/Memory.md`.
11. Never put LLM raw output into the report. Only verified explanations or the
    deterministic fallback.

## 3. Allowed libraries

`fastapi`, `uvicorn`, `python-multipart`, `pandas`, `openpyxl`, `rapidfuzz`,
`pydantic` (v2), `python-dotenv`, `jinja2`, `openai`, `httpx`, `pytest`,
`ruff`, and the Python standard library.

## 4. Forbidden libraries and tools

`langchain`, `langgraph`, any ORM or database, `celery`, `redis`, Docker files,
`requests` (use `httpx`), `fuzzywuzzy` or `thefuzz` (use `rapidfuzz`), any npm
or JavaScript build tooling, any paid service or API, any telemetry package.
If a library outside the allowed list seems necessary, do not add it: record
the need in `docs/Memory.md` under Open questions and use the standard
library.

## 5. Error handling

- Exceptions derive from `ReconError` (see `docs/Architecture.md`).
- CLI: catch `ReconError`, print `error: <message>`, exit code 2. Unexpected
  exceptions show a traceback and exit code 1.
- API: map `ReconError` to 400 or 422 with the JSON error shape; unexpected
  errors to 500 with a generic message and a logged traceback.
- LLM errors (timeout, rate limit, bad JSON, verifier failure) never fail a
  run. Retry per the architecture, then use the deterministic fallback and
  log it.
- Validation problems in input data are data, not exceptions: they become
  validation issues and `invalid_record` findings.

## 6. Constraints

- Free resources only. Default LLM provider is `mock`.
- One currency per run.
- Limits: 10 MB and 50,000 rows per file.
- Performance target: 5,000 rows per side in under 30 seconds without the LLM.
- Windows-friendly paths and commands in all documentation.

## 7. Testing rules

- Unit tests for each module, plus integration tests for the pipeline and the
  report.
- Property-style tests where valuable (for example: matching is one-to-one;
  every record appears in exactly one finding; money round-trips through
  normalization).
- A test must exist for every verifier failure code, using `faulty_mock`.
- `pytest -q` must pass before any task is reported as done.

## 8. Logging the quest process

After every task, append one entry to `quest-submission/ai-usage-log.md` using
the entry format in that file. Record only what actually happened: the task
given, what you produced, what failed (including errors the human pasted
back), how it was fixed, and the verdict. Quote the human's pasted error text
in short form. Never invent prompts or outcomes.

## 9. Task Report format (print at the end of every task)

```
## Task Report: T## <title>
Status: PASSED | PARTIAL | BLOCKED
Files changed: <list>
What I built: <at most 3 bullets>
Commands for you to run:
<exact commands, one per line>
Expected result: <what a correct run shows>
Known issues and assumptions: <list or "none">
Memory.md updated: yes
Usage log updated: yes
```

Then stop and wait for the human.
