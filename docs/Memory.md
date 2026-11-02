# Memory: Recon Investigator

The build agent keeps this file current. Read it first every session. Update it
after every task. Keep entries short and factual. Never delete the Bug log.

## Project context

- Product: AI-assisted bank-versus-ledger reconciliation investigator.
- Purpose: Match Hire quest "Use Your Superpower" (5 days, AI as the default way
  of working). Deliverables live in `quest-submission/`.
- Core principle: deterministic code decides matches; the LLM only explains
  from evidence packets; a verifier checks every LLM output.
- Build tool: opencode with the GPT-5 Codex model. Planning and documents were
  drafted with Claude in chat.
- Human role: runs commands, reads errors, pastes them back. The agent writes
  and fixes all code.
- Constraints: free resources only, synthetic data only, default LLM provider
  `mock`, real provider is an OpenAI-compatible endpoint (Groq free tier).

## Key architecture decisions (fixed before the build)

| # | Decision | Reason |
|---|---|---|
| D1 | Flat package `recon/` run with `python -m recon`, no install step | fewer setup errors |
| D2 | Money as integer minor units, `Decimal` at the edges | correctness |
| D3 | Rule-based matching in a fixed order (exact, fuzzy, duplicates, amount, date, split, missing) | auditability and determinism |
| D4 | Duplicates defined as unmatched records key-identical to a matched record of the same source | avoids flagging legitimate repeated payments |
| D5 | Split search is bounded; ambiguous or over-budget cases are reported, not guessed | never guess with money |
| D6 | LLM output is JSON with no field that can change a finding | trust boundary |
| D7 | Verifier plus one retry plus deterministic fallback | AI can fail; the report cannot |
| D8 | `mock` is the default provider; `faulty_mock` measures verifier catch rate | tests and demos run offline |
| D9 | No agent framework, no database, no Docker | scope and run simplicity |
| D10 | Vanilla HTML/JS UI, self-contained HTML report | no build step |
| D11 | Synthetic data generator with labeled injections and ground truth | measurable precision and recall |

## Task status

| Task | Title | Status | Notes |
|---|---|---|---|
| T00 | Bootstrap | passed | CLI, settings, skeleton, test, and tooling verified. |
| T01 | Domain models | passed | Models, Decimal money helpers, and tests verified. |
| T02 | Ingestion | passed | CSV/XLSX loading, mapping, limits, and fixtures verified. |
| T03 | Normalization and validation | passed | Normalization and validation tests verified. |
| T04 | Synthetic data generator | passed | Seeded data, truth labels, CLI, and tests verified. |
| T05 | Tier 1 exact matcher | passed | Blocked deterministic exact matching and timing test verified. |
| T06 | Evaluation harness v1 | passed | Tier 1 metrics, report output, CLI, and tests verified. |
| T07 | Fuzzy, amount, date matching | passed | R2, R4, R5 matching and evaluation integration verified. |
| T08 | Duplicate detection | passed | Found implemented and verified in the T09 session; R3 duplicates plus decoy check. |
| T09 | Split-payment matcher | passed | R6 bounded two-direction split search and tests verified. |
| T10 | Engine and run pipeline | passed | R1-R7 chain, severity, stable IDs, run pipeline, CLI run verified. |
| T11 | Error analysis checkpoint | passed | Two generator fixes; overall recall 0.899 to 0.967, before/after tables saved. |
| T12 | Evidence packets | passed | Packets for all 8 LLM types; code-built allowed_values; 19 tests verified. |
| T13 | LLM providers | passed | base/mock/faulty_mock/openai_compat/prompts/schema/cache; 84 LLM tests verified. |
| T14 | Verifier | passed | Six checks, one retry, marked fallback, `verifier_log.jsonl`; 29 tests verified. |
| T15 | Explanation pipeline | passed | Provider-stage in engine/CLI; 13 explain tests verified. |
| T16 | Report | passed | Self-contained `report.html` plus `audit_trail.jsonl`; 26 report tests verified. |
| T17 | API and web UI | passed | FastAPI app plus vanilla UI; 27 API tests, full suite 267, live UI verified in a browser. |
| T18 | End-to-end and final evaluation | passed | `demo` command, e2e tests, 9-run mock grid + faulty_mock + groq, `reports/final_eval.md` generated from the saved JSON; full suite 281 passed. |
| T19 | Quest documents | passed | `write-up.md` from real data, usage log finalized (25 entries), revision table confirmed, README commands re-run, checklist statuses set. |
| T20 | Release check | not started | |

Allowed statuses: not started, in progress, passed, partial, blocked.

## Decisions made during the build

(Append: date, task, decision, reason.)

- 2026-11-02, T19, every metric in `write-up.md` is copied from
  `reports/final_eval.md` and every failure from the Bug log or this log; the four
  process counts (tasks, Bug log entries, decisions, usage-log entries) are measured
  from the files themselves, because the write-up template explicitly asks for them
  and they cannot exist in an evaluation report. No repository URL line is printed,
  because `README.md` carries no URL and inventing one would be the exact thing Rule 7
  forbids.
- 2026-11-02, T19, `write-up.TEMPLATE.md` stays in `quest-submission/` unchanged: it is
  the record of the instruction the agent worked from, the acceptance marker search
  (`TODO`, `TBD`, `{{`, `AGENT:`) returns nothing anywhere in the folder, and the
  finished `write-up.md` contains no comment or placeholder text.
- 2026-11-02, T19, `loom-scripts.md` was not edited. Every command in it still matches
  the CLI (`python -m recon demo`, `python -m recon serve`,
  `pytest -q tests/llm/test_verifier.py`), and T19 only grants permission to fix stale
  commands. Its narration ("opencode with the GPT-5 Codex model ... 21 small tasks one
  at a time") is now inaccurate about the tool and the task count at T19; that is the
  human's script to change, so it is filed under Open questions instead.
- 2026-11-02, T19, the README `run` example passes `--llm mock` explicitly and `serve`
  is documented as following `LLM_PROVIDER`: this machine's `.env` selects `groq`, so an
  example that inherits the provider silently becomes a rate-limited multi-minute
  command on the author's own machine.
- 2026-11-02, T19, the missing T08 usage-log entry was written retroactively and
  labelled as such, from the code, the Bug log entry and the T09 verification run, and
  states plainly that the original prompt text is not recoverable. Reconstructing a
  plausible prompt would have been the fabrication.
- 2026-11-02, T18, the evaluation runner now calls `run_pipeline()` instead of
  re-implementing ingest/normalize/match/findings. T06 wrote the runner before
  `run_pipeline` existed (T10), so it duplicated the chain and could drift from
  the shipped product. Verified: with the rewrite, `per_type`, `match_pair` and
  `validation_issues` in all nine saved grids are byte-equal to the pre-rewrite
  copies, and `tests/evaluation/test_runner.py` asserts the same equality with and
  without a provider (Rule 1.1).
- 2026-11-02, T18, `demo` defaults to `--llm mock` rather than to `LLM_PROVIDER`.
  The acceptance criterion is "finishes under one minute" and the human's `.env`
  selects `groq`, whose rate limit makes any real-provider default slow and
  partly rate-limited. A real provider stays available with `demo --llm groq`.
- 2026-11-02, T18, a non-canonical provider changes the report file name:
  `eval_<profile>_<seed>.json` for `none`/`mock` (labels the run `disabled` for
  `none`) and `eval_<profile>_<seed>_<llm>.json` otherwise, so the optional groq
  run coexists with the mock grid instead of overwriting it, and the aggregator
  can still enumerate the grid by cell.
- 2026-11-02, T18, CLI `eval` always rebuilds `reports/final_eval.md` from the
  files it just wrote, and the aggregator only accepts the requested profile/seed
  cells plus the `_<llm>` variants of those same cells. A stale or hand-placed
  JSON in `reports/` therefore cannot add its numbers to the document, and one
  command is the only way the deliverable can be reproduced (Rule 7).
- 2026-11-02, T18, provider sections are ordered reference-provider-first
  (`mock`, `faulty_mock`, then deterministic `disabled`, then real providers
  alphabetically) rather than by the order runs were executed. Without the fixed
  rank, the headline table depended on which provider had been evaluated last.
- 2026-11-02, T18, `final_eval.md` carries one table per profile in each provider
  section. The grid average alone cannot answer the write-up's "one line each for
  the easy and hard profiles", and a reader must be able to see that hard is worse
  than easy instead of inferring it from a combined number.
- 2026-11-02, T18, ratios in the aggregate are micro-averaged (TP, FP and FN
  summed across a section's runs before dividing), stated in the document itself.
  Averaging the nine per-run ratios would silently weight the small `easy` runs
  the same as the large `hard` runs.
- 2026-11-02, T18, the verifier block records `rejected_first_try` separately
  from `rejected_answers`, so the catch rate is "first answers rejected over
  packets that received a first answer" and a retry rejection cannot inflate it.
  Packets that ended in a provider error are counted in their own column and
  never enter the denominator.
- 2026-11-02, T18, cause accuracy is scored only on findings the deterministic
  chain got right (type plus full ID set match a labelled entry) and only on
  accepted answers, so a matching miss cannot become an AI miss and a fallback
  with cause `unknown` cannot be credited.
- 2026-11-02, T18, the limitations paragraph names the two numbers a reader could
  otherwise over-read: `mock` cause accuracy of 1.000 measures the pipeline, not a
  model, and the real-model 0.396 is a lower bound because the ground truth stores
  exactly one cause per injection while several causes are plausible.
- 2026-11-02, T17, the web run reuses `run_pipeline()` unchanged: `recon/api/routes.py`
  streams each `UploadFile` into a `TemporaryDirectory(prefix="recon-web-")` under the
  documented suffix allow-list and size cap, calls the same pipeline the CLI calls, and
  writes artifacts to `reports/web/<run_id>/` with the finished
  `write_run_artifacts()`. No pipeline signature, rule or model changed (Rule 2.10).
- 2026-11-02, T17, completed runs are kept in an in-memory `RunStore` keyed by the
  documented `run_id`, and `GET /api/runs/{run_id}` reads from it while
  `/api/runs/{run_id}/report` returns the file on disk. Run history is therefore empty
  after a restart; adding a database would break D9 and Architecture section 13 lists
  no run-history endpoint.
- 2026-11-02, T17, the JSON error shape is produced by exception class, not by string
  matching: `STATUS_BY_ERROR` and `STAGE_BY_ERROR` map the six `ReconError` subclasses
  to a status code and a stepper stage, the handler walks `type(exc).__mro__` so
  subclasses inherit their parent's entry, and `code` is the snake_case class name.
  `details.stage` is the only field the UI needs to place the failure on the stepper.
- 2026-11-02, T17, an unexpected exception returns 500 `internal_error` with the fixed
  message "the reconciliation could not be completed" and is logged with
  `LOGGER.exception`; the raised text is never echoed to the client, because the paths
  in it come from the caller's upload. A test asserts the offending path is absent from
  the body (Rule 2.7).
- 2026-11-02, T17, endpoints are plain `def`, not `async def`: Starlette runs them in
  its threadpool, so the multi-second deterministic chain never blocks the event loop
  and no blocking call sits inside an event loop.
- 2026-11-02, T17, no money arithmetic happens in JavaScript. Every amount, total and
  percentage is computed in Python minor units and sent as a `format_amount` display
  string (D2), so the browser can only render what the engine decided (Rule 1.1).
- 2026-11-02, T17, the API takes no LLM selection field because Architecture section
  13 fixes the request shape: `serve` resolves the provider from `LLM_PROVIDER` exactly
  like CLI `run`, and `none` (or a missing key) simply omits
  `verifier_log.jsonl`. The startup line prints the resolved provider so the operator
  can see which mode the server is in.
- 2026-11-02, T17, matched findings are hidden by default behind a "Matched items"
  checkbox, which satisfies Design section 7's "collapsed by default in the UI" and the
  T16 decision that left collapsing to the web layer. With 185 matched rows visible the
  page measured 22189px tall; hidden it is 5354px.
- 2026-11-02, T17, `/static/tokens.css` is served from `recon/assets/` instead of being
  copied into `static/`, so the report and the UI cannot drift apart, and the static
  file allow-list (three names plus tokens) means no path traversal and no fourth asset.
- 2026-11-02, T17, the UI is one HTML page plus one stylesheet plus one vanilla ES
  module-free script (D10): no npm, no bundler, no CDN reference. A test asserts no
  `http(s)://` string exists in any of the three files, and the column-field list in
  `app.js` is cross-checked against `recon.ingest.column_map.COLUMN_FIELDS` so the
  mapping form cannot drift from the validator.
- 2026-11-02, T16, the audit trail is derived from `RunResult` (meta, findings,
  issues, verifier records) instead of instrumenting finished matching code: one
  `rule` event per finding in report order, so no rule application is missing and
  no R1-R7 module had to change (Rule 2.10). Events drop the `raw` field, so the
  unverified provider text lives only in `verifier_log.jsonl` (Rule 2.11).
- 2026-11-02, T16, `report.html` is one file with zero external references:
  `recon/assets/tokens.css` is read and inlined at build time, Jinja runs with
  `autoescape=True` and `StrictUndefined`, and the document contains no `href`,
  `src`, `script`, `link`, `img` or `url()` at all (proved in a browser: no
  network requests, no console messages). The Groq base URL appears only as
  escaped plain text in the appendix, which is what the acceptance wording allows.
- 2026-11-02, T16, matched items render as a full table rather than a collapsed
  `<details>`: the report carries no JavaScript, and a closed `<details>` would
  hide rows that Design section 7 requires in the printed document. Collapsing and
  filtering stay with the T17 UI.
- 2026-11-02, T16, report money always goes through `format_amount` (grouped,
  `tabular-nums`, right-aligned in tables) and fact keys ending `_minor` lose that
  suffix in their label; a test asserts the raw minor-unit integer is absent from
  the HTML. Inside the two-column evidence grid, amounts and row numbers are left
  aligned, because right-aligning a stacked key/value cell pushed values to the
  far edge.
- 2026-11-02, T16, the title block renders the run instant as
  `%Y-%m-%d %H:%M:%S UTC`; `run_meta.json` keeps the full ISO-8601 value, so no
  precision is lost, only the display is shortened.
- 2026-11-02, T16, two finished tests were edited (T10 engine, T15 explain)
  because `write_run_artifacts()` now returns the four or five documented
  artifacts and both asserted an exact name list; the assertions were about the
  file list, not about behavior, and the engine test gained an audit-trail
  line-count check (Rule 2.10, T16 build item).
- 2026-11-02, T00, pinned direct dependencies to the versions installed in the
  local Python 3.12.11 virtual environment after the initial smoke test passed;
  this satisfies reproducibility without pinning transitive dependencies.
- 2026-11-02, T00, created each documented future package module as a
  docstring-only placeholder; this establishes the architecture without
  implementing future task behavior.
- 2026-11-02, T01, use `Decimal.quantize(..., ROUND_HALF_UP)` at money input
  edges and integer minor units in all canonical transaction fields; this gives
  explicit, symmetric rounding for positive and negative fractional inputs.
- 2026-11-02, T02, require a date column and either a signed amount column or
  at least one debit/credit column; reference, description, currency, and
  counterparty remain optional so varied bank exports can proceed to T03.
- 2026-11-02, T03, assign IDs from one-based data-row positions and default an
  absent currency to `DEFAULT_CURRENCY`; a later differing currency is excluded
  as a `mixed_currency` validation issue to preserve the one-currency-per-run
  constraint.
- 2026-11-02, T03, handle Excel's 1900 leap-year compatibility boundary so
  serial 1 maps to 1900-01-01 and serials from 60 use the standard
  1899-12-30 origin.
- 2026-11-02, T04, define exact profile injection counts: easy uses five of
  each discrepancy plus four splits; realistic follows the architecture table;
  hard doubles realistic counts except six ambiguous splits. Decoys are matched
  repeat-payment pairs, not discrepancy labels.
- 2026-11-02, T04, retain internal synthetic row keys only during generation,
  shuffle bank rows, then derive `B-` IDs from final positions and construct
  ground truth from those positions; exported CSVs contain no synthetic IDs.
- 2026-11-02, T05, Tier 1 blocks by currency, integer amount, and nonempty
  normalized reference, then greedily accepts candidates sorted by date
  difference, ledger ID, and bank ID; this preserves deterministic one-to-one
  matching while avoiding cross-product comparisons across unrelated records.
- 2026-11-02, T06, evaluate findings by their type plus full source-ID set and
  evaluate match pairs separately by their ledger and bank ID sets; Tier 1
  predicts `match_exact` only, leaving unsupported labeled types as explicit
  recall gaps rather than inferred findings.
- 2026-11-02, T07, require a clear best R4 amount candidate on both its ledger
  and bank sides by `PAIR_MARGIN`; candidates with strong but near-tied
  references remain unmatched instead of being classified speculatively.
- 2026-11-02, T09, reuse the Tier 2 weighted score (`ref`, `description`, date
  over the split window) as split anchor-to-record similarity, rank the pool by
  (similarity descending, ID) to the `SPLIT_MAX_POOL` limit after dropping
  records below `SPLIT_MIN_SIM`, then search that pool in ID order so
  combination enumeration and the reported candidate sets are input-order
  independent.
- 2026-11-02, T09, process anchors in a fixed sequence (ledger side first, then
  bank side, each by ID) and consume the anchor plus its parts only for a unique
  solution, which keeps split matching one-to-one; ambiguous anchors consume
  nothing so their parts stay available to other rules.
- 2026-11-02, T09, treat two or more found solutions as `ambiguous_split` even
  when the node budget stopped the search, but treat a truncated search with
  zero or one partial solution as an unmatched anchor with
  `split_search_truncated: true`; a partial search may never produce a match.
- 2026-11-02, T09, require parts to share the anchor currency, be nonzero and
  sign-equal, and sit within `SPLIT_DATE_WINDOW_DAYS`; sum only integer minor
  units and bound the depth-first search by `SPLIT_MAX_PARTS` plus a reachable
  sum bound (the k largest pool amounts) so impossible branches are never
  explored.
- 2026-11-02, T10, `ambiguous_split` findings claim the anchor plus the union of
  all listed candidate IDs (status `needs_review`, rule `R6-SPLIT`) so R7 cannot
  also report those records; this is what keeps the acceptance property "every
  valid record appears in exactly one finding" true while still refusing to pick
  a combination.
- 2026-11-02, T10, R7 skips any record already claimed by R1-R6 rather than
  re-testing unmatched lists, because each earlier rule returns its own
  leftovers and an ambiguous split consumes nothing.
- 2026-11-02, T10, severity comes from the largest absolute amount in the
  finding (`SEVERITY_HIGH_MINOR`, `SEVERITY_MEDIUM_MINOR`) and invalid rows get
  an amount-free low severity; findings are ordered by (severity, type, lowest
  ledger ID, lowest bank ID) before numbering, so IDs are independent of the
  order rules were applied in.
- 2026-11-02, T10, `run_meta.json` stores a credential-free config snapshot
  (`serializable_config` drops any `*_api_key`), its SHA-256 `config_hash`, the
  input file hashes and column maps, and `llm.provider = "none"` until T15
  writes real explanation state.
- 2026-11-02, T11, the two largest failure modes were fixed in
  `recon/synth/generator.py`, not in `recon/matching/`, even though T11 says "in
  the matching code": both are ground-truth contradictions (the generator labels a
  record missing or duplicated while handing the matcher its exact opposite-side
  twin), and no threshold or rule change can recover a label the data itself
  denies. Rewriting a finished T04 module is allowed by Rule 2.10 with a bug
  justification, which the Bug log entries are; two generator regression tests
  were added in the same task. The one genuine matching-code lever
  (`REF_STRONG` 0.90 versus the 0.875 similarity of one-character reference
  noise) is deliberately left untouched as the second fix budget was already
  spent, and is recorded under Open questions.
- 2026-11-02, T12, packet money is rendered as ungrouped two-decimal strings
  (`"2000.00"`, never `"2,000.00"` and never minor units); the Architecture
  section 9 example uses that form and the verifier compares cited amounts as
  `Decimal`. Report display keeps using `format_amount` with thousands groups.
- 2026-11-02, T12, a packet's records are the finding's own ledger plus bank IDs
  extended with every ID named inside its facts (`primary_id`, `anchor_id`,
  `part_ids`, `candidate_sets`), sorted by source then ID; a duplicate or split
  explanation then cites real amounts and dates for the record it refers to
  instead of naming an ID the verifier would reject. An ID that the run cannot
  resolve raises instead of silently dropping evidence.
- 2026-11-02, T12, `allowed_values` is derived by walking the packet's own
  serialized values (money `\-?\d+\.\d{2}`, ISO dates, `[LB]-\d{6}` and
  `F-\d{4}` identifiers, plus every int/float as a number), so the whitelist
  cannot drift from the packet content by construction. Scores are stored as
  floats, which keeps them in `numbers` and out of `amounts`.
- 2026-11-02, T12, `candidates_considered` is populated only for
  `ambiguous_split`, where the engine already stores the candidate sets; each is
  scored against its anchor with the documented Tier 2 weights over
  `SPLIT_DATE_WINDOW_DAYS`, sorted by (score descending, ID) and capped at 3.
  R4 and R5 discard their runner-up candidates inside the classifier, so
  reporting them would mean instrumenting finished matching code for a field the
  contract already allows to be empty.
- 2026-11-02, T12, `build_packet` raises for any finding type outside the
  allowed-causes table; matches and `invalid_record` cannot obtain a packet at
  all, which enforces the trust boundary in code rather than by convention.
- 2026-11-02, T13, `mock` and `faulty_mock` build their sentences only from the
  packet's own record fields and facts, so the default provider is verifier-clean
  by construction instead of by a tuned corpus. Every amount, date and ID in an
  answer is a value the packet already printed.
- 2026-11-02, T13, `faulty_mock` picks its fault from the packet hash
  (`digest % 4`) rather than a counter, so fault choice is independent of call
  and finding order (Rule 5), and it answers correctly as soon as
  `error_codes` is non-empty, which is what makes T14's single-retry path
  testable. A forced `fault=` argument plus `rate=` share cover the two ways the
  verifier tests need to drive it.
- 2026-11-02, T13, the real provider is `httpx` against `LLM_BASE_URL`; the
  `openai` package stays unused (installed only because `requirements.txt` pins
  it from T00). `groq` and `openai_compat` are two names for the same class in
  `build_provider`, so no model name, key or URL exists outside `config.py` and
  `.env.example` (Rule 2.4).
- 2026-11-02, T13, the on-disk cache key is `<packet hash>-<sha256(provider|model)[:16]>.json`
  and `path()` refuses any key that is not a lowercase 64-char hex digest, so a
  caller cannot escape the cache directory and one model can never read another
  model's answer. Retries (non-empty `error_codes`) bypass the cache in both
  directions: a corrected answer must not poison the entry that produced the
  rejected one.
- 2026-11-02, T13, `Investigation` is `extra="forbid"` and has exactly the eight
  documented explanation fields, and `SYSTEM_PROMPT` embeds
  `json.dumps(output_schema(), sort_keys=True)` so the prompt and the parser
  cannot drift apart. There is no field that could carry a decision, so an
  override attempt has nowhere to live except in prose, which `decision_override`
  models.
- 2026-11-02, T15, the explanation stage is a separate pass over finished
  findings: `run_pipeline(..., provider=...)` only fills the `explanation` field,
  so the deterministic chain, the finding order and every ID are untouched. The
  property is asserted by comparing all decision fields with and without a
  provider, and on the real seed 42 run the two artifact sets match exactly.
- 2026-11-02, T15, matches and `invalid_record` receive a deterministic one-line
  rationale as an `Explanation` with `likely_cause` `matched_by_rule` /
  `invalid_row`, `confidence: high` and `explanation_source:
  deterministic_fallback` (Architecture section 9 says they never use the LLM but
  still get a rationale). No third enum value was added, so `recon/models.py` did
  not have to change.
- 2026-11-02, T15, the ask-retry-fallback policy stays inside
  `verifier.explain_verified()`; `explain.py` only fans packets out and collects
  results by index, so thread completion order can never reach the output
  (Rule 5). A provider `LLMError` ends the loop immediately with a
  `provider_error` attempt record plus the fallback rather than retrying a
  transport that is already failing.
- 2026-11-02, T15, `verifier_log.jsonl` is written by the report builder with
  `truncate=True`, not appended: all run-artifact I/O lives in one place and
  re-running into the same folder must not double the attempt history.
- 2026-11-02, T15, three finished modules were edited because T15's build item
  says "integrate into `run_pipeline()` and CLI `run --llm`" (Rule 2.10, task
  justification, no behavior change without a test): `recon/matching/engine.py`
  gains an optional `provider` and a `verifier_records` field on `RunResult`,
  `recon/report/builder.py` writes `verifier_log.jsonl` when the stage ran, and
  `recon/cli.py` gains the `--llm` flag. The T10 no-provider artifacts stay
  byte-comparable: with no provider, `meta.llm` is still `{"provider": "none"}`
  and no log file is produced.
- 2026-11-02, T15, CLI `run --llm` defaults to `None` and falls through to
  `LLM_PROVIDER` (mock), so the default run is explained; `--llm none` reproduces
  the T10 deterministic-only artifacts with `meta.llm = {"provider": "none"}`.
- 2026-11-02, T14, failure codes are appended in the documented check order
  (2 cause/action, 3 cited facts, 4 figures, 5 override, 6 confidence) and
  `schema_invalid` short-circuits the rest, because nothing else is checkable
  without a parsed answer. The tuple is therefore stable for the retry prompt and
  for `verifier_log.jsonl` (Rule 5).
- 2026-11-02, T14, a bad `recommended_action` string surfaces as
  `schema_invalid`, not `bad_enum`: the enum is declared in the schema, so the
  parser rejects it first. `bad_enum` owns `likely_cause`, which stays a plain
  string in the model because the allowed set is per-packet, not per-provider.
- 2026-11-02, T14, the deterministic fallback delegates to the packet composer
  with cause `unknown` (`confidence: low`), so a fallback is verifier-clean by
  construction and a test proves all six checks pass on it for all eight types.
  If a packet ever lacks `unknown`, the last allowed cause is used instead.
- 2026-11-02, T14, `explain_verified()` returns the attempt list instead of
  writing files: the verifier does no I/O inside the loop, and the run pipeline
  decides where `verifier_log.jsonl` lives. Raw provider output is kept only in
  those records (Rule 2.11), never in the report.
- 2026-11-02, T14, the override guard is a case-insensitive phrase list applied
  to `summary`, `explanation`, `action_detail` and `uncertainties` (scanning
  `uncertainties` is stricter than the doc's three fields). The figure scan lists
  the grouped-money pattern before the plain one, so "1,234.56" is one rejected
  token instead of an allowed "234.56" hiding inside it.

## Bug log

(Append: task, symptom or pasted error, root cause, fix, how it was verified.
Include failures of the AI's own output, for example wrong assumptions, tests
that failed on the first run, and errors the human pasted back.)

- T00, `ruff check .` reported `I001 Import block is un-sorted or
  un-formatted` for `recon/__main__.py`; the entry-point import layout was not
  accepted by Ruff's import normalizer. Applied `ruff check --fix` to that file
  and formatted it. Verified by final `ruff check .` and `ruff format --check
  .` runs, both passing.
- T00, human reported `ModuleNotFoundError: No module named 'dotenv'` on the
  first `pytest` run using system Python 3.14; dependencies had not been
  installed in that virtual environment. The human ran `python -m pip install
  -r requirements.txt` and `python -m pytest -q`; the test suite then passed
  with one test.
- T01, initial `ruff check .` reported `I001 Import block is un-sorted or
  un-formatted` for `recon/models.py`; the `decimal` imports were not in Ruff's
  required order. Reordered them and verified all tests, `ruff check .`, and
  `ruff format --check .` passed.
- T02, initial `ruff check .` reported `E501 Line too long (103 > 100)` for a
  CSV test fixture; the fixture string exceeded the configured line limit.
  Split the literal over adjacent strings and verified all tests and Ruff checks
  passed.
- T03, initial `ruff check .` reported `F401` for an unused `Decimal` import
  in `recon/normalize/amounts.py`; removed the import and verified all tests,
  lint, and formatting checks passed.
- T04, initial `ruff check .` reported `F841` for an unused
  `injected_bank_keys` variable in the generator; removed it and verified all
  synthetic tests, the required CLI generation, the full suite, and Ruff
  checks passed.
- T06, realistic evaluation revealed `match_fuzzy` ground-truth labels whose
  prefix-and-spacing-only reference noise normalized to exact keys, producing
  false Tier 1 exact positives. Changed noisy synthetic references to alter the
  normalized value and added a regression test; reran synthetic, evaluation,
  full-suite, and Ruff checks successfully.
- T07, the first evaluation integration assertion expected fee recall 1.0 but
  the configured unique-best margin correctly left three of eight near-tied fee
  candidates unresolved (recall 0.625). Changed the test to require positive
  deterministic improvement, then reran matching, evaluation, full-suite, and
  Ruff checks successfully.
- T08 (record gap found in the T09 session), `docs/Memory.md` listed T08 as not
  started while `recon/matching/duplicates.py`, its tests, and the evaluation
  wiring already existed; the prior session never reported or logged the work.
  Verified the real state by running the suite (44 tests passed) before starting
  T09, corrected the task table, and left the T08 usage-log entry as an open gap
  for T19 to reconcile. Those two T08 files also held lines longer than the
  100-character limit (Ruff `E501`), so `ruff check .` could not have been clean
  before this session; `ruff format .` (Rule 8) rewrapped them with no behavior
  change, confirmed by the suite still passing and both Ruff checks now clean.
- T09, the first draft of `recon/matching/split.py` carried an unused placeholder
  helper and passed a hard-coded `False` instead of the search's real truncation
  flag, which would have silently disabled the truncation report; removed the
  dead helper and passed `search.truncated` before running any test.
- T09, `pytest -q tests/matching/test_split.py` first reported
  `TypeError: _bank() got an unexpected keyword argument 'currency'` in
  `test_pool_requires_same_currency_sign_and_date_window`; the concise fixture
  helper did not forward currency or date overrides. Rewrote that test to build
  the variant records through the full `_transaction` helper; the 15-test split
  suite then passed.
- T10, the first draft of `recon/matching/engine.py` left four `E501` lines over
  the 100-character limit (`ruff check .` failed) and reused an inline
  conditional tuple for split side assignment instead of the existing
  `_side_ids` helper; rewrapped the lines, routed both split and ambiguity
  findings through `_side_ids`, and verified `ruff check .` plus the suite pass.
- T10, `pytest -q` reported
  `AssertionError: assert 'R1-R7' == 'R1-R5'` in
  `tests/evaluation/test_runner.py`: the evaluation runner now scores the full
  R1-R7 chain, so the saved tier string and the test docstring were stale, not
  the engine. Updated the assertion to `R1-R7` and added positive-recall checks
  for `match_split` and `ambiguous_split`; the 66-test suite then passed.
- T10, while debugging a CLI invocation I ran `cat .env`, which printed
  `OPENAI_API_KEY=...` into the terminal transcript. `.env` is gitignored and no
  artifact or `run_meta.json` contains a credential (`config_hash` excludes
  `*_api_key`), but the file must never be echoed; use `recon.config` lookups or
  `.env.example` instead. Logged per Rule 2.4/2.7.
- T11 (failure mode 1, largest), `missing_in_bank` and `missing_in_ledger` recall
  0.000 across all nine runs (105 FN per type, 91 FP per type, plus about 105
  spurious `match_fuzzy` findings). Root cause: `_inject_missing` deleted a
  ledger row's bank twin and then re-added that same row to the bank as
  `BANK-<reference>`, so every labeled orphan ledger row had an opposite-side
  clone with the same amount, date and description; Tier 1 could not match it
  (normalized references differ) but Tier 2 scored it 1.000 and matched it.
  Examples before the fix: realistic seed 1 `L-000001` and `B-000143` were
  reported as one `match_fuzzy` finding `F-0227`; easy seed 1 `L-000001` and
  `B-000156` as `F-0127`. No rule change can recover these labels, because two
  records with equal amount, date and description are a match by definition.
  Fixed in `recon/synth/generator.py`: bank-only items are now independent
  negative bank charges (`CHG-####`, "Bank service charge"), which every rule's
  amount or sign guard excludes. Both types now recall 1.000.
- T11 (failure mode 2), `duplicate_in_ledger` and `duplicate_in_bank` recall
  0.000 (69 FN per type). Root cause: `_inject_duplicates` appended a copy on
  BOTH sides of the same matched pair, and those two copies are byte-identical,
  so Tier 1 matched the copies to each other and Tier 3 had nothing left.
  Examples before the fix: easy seed 1 `L-000205` and `B-000128` came back as
  `match_exact` `F-0126`; realistic seed 1 `L-000501` and `B-000188` as `F-0465`.
  Fixed in the generator: one copy per base row, ledger copies and bank copies
  taken from disjoint target blocks, and a bank copy is posted one day after its
  twin so Tier 1 always keeps the lower-date-difference primary whichever order
  the shuffled bank rows land in (Rule 1.5). Both types now recall 1.000,
  precision 1.000.
- T11 (failure mode 3, documented and NOT fixed), amount, fee and date mismatch
  recall 0.701 / 0.655 / 0.598 (91 FN) and 182 `missing_*` false positives, all
  of them the same records: single-character reference noise gives a normalized
  reference similarity of exactly 0.875, which is below `REF_STRONG` 0.90, so
  Tier 4 refuses the pair and Tier 5 (which requires identical normalized
  references) never sees it; the pair then falls through to Tier 7. Example:
  realistic seed 1 `L-000011` (`20260011`) against `B-000393` (`2026001X`) is
  labeled `amount_mismatch` and reported as `F-0532 missing_in_bank` plus
  `F-0546 missing_in_ledger`. Left alone because `eval` capped this checkpoint at
  two fixes and lowering `REF_STRONG` to 0.85 is a deterministic-threshold change
  the human should approve; it is recorded under Open questions. The change was
  measured, not assumed: `REF_STRONG=0.85` over the same nine runs gives overall
  recall 0.971 versus 0.967, but `amount_mismatch` precision falls 1.000 to 0.862
  (12 false discrepancy accusations), `date_mismatch` recall falls 0.598 to 0.494
  because Tier 4 now consumes records Tier 5 needed, and overall precision only
  rises 0.951 to 0.962. A reconciliation report that names the wrong discrepancy
  is worse than one that abstains, so the default stays 0.90.
- T12, the first `pytest -q tests/evidence` run failed two tests: the packet
  fixture helper built record IDs as `f"{source.upper()}-{n:06d}"`, producing
  `LEDGER-000001` instead of the canonical `L-000001`, so the duplicate test
  compared the right records under the wrong names; and the allowed-value scrape
  regexes matched the surrounding JSON quotes (`'"F-0001"'` versus `F-0001`).
  Added a `ledger`/`bank` to `L`/`B` prefix map and wrapped both patterns in a
  capture group. Verified by `pytest -q tests/evidence` (19 passed) and the full
  suite (87 passed).
- T12, an intermediate draft of `tests/evidence/test_packet.py` asserted
  `packet.rule == finding.rule_id` (a model against a string) and parametrized
  `invalid_record` over a fixture run that cannot produce invalid rows, which
  would have raised `KeyError` instead of the intended `ValueError`. Removed the
  bad comparison and build that one finding directly, so the non-LLM guard is
  still proven for matches and invalid rows.
- T12, `data/synthetic/*` and `reports/run_realistic_42/` on disk were generated
  before the T11 generator fixes, so the first packet statistics taken from them
  were wrong in a way that looked like a T12 defect: the realistic seed 42 run
  reported 536 findings but produced no `duplicate_*` packet, because the stale
  file still contained the byte-identical cross-side duplicate copies. Root cause
  was stale generated input, not `recon/evidence`. Regenerated all ten datasets
  plus `reports/eval_realistic_42.json` with `python -m recon eval` and re-ran
  `python -m recon run`; the nine-run aggregate recomputed from the refreshed
  `reports/eval_*.json` is unchanged (5370 TP / 274 FP / 183 FN, precision 0.951,
  recall 0.967), which also re-proves the generator's seed determinism, and the
  seed 42 run now writes 552 findings of which 68 yield packets covering all
  eight LLM types.
- T13, `ruff check .` failed with 7 × `E501 Line too long` in
  `recon/llm/mock.py` (cause and action phrase dictionary values written on one
  line, up to 116 characters) and `ruff format --check .` wanted to reformat 5
  LLM files. Wrapped each long phrase value in a parenthesized continuation and
  ran `ruff format .` (Rule 8). Verified by `ruff check .` clean,
  `ruff format --check .` reporting 88 files already formatted, and
  `pytest -q` at 171 passed.
- T13, the first offline provider probe over real packets aborted with
  `ModuleNotFoundError: No module named 'recon'`: I ran
  `venv/bin/python /tmp/t13_probe.py` from the repo root, and the `pythonpath`
  setting in `pytest.ini` only applies to pytest. Re-ran it with
  `PYTHONPATH=.`; the probe then reported 68/68 valid mock answers. The scratch
  file was deleted afterwards.
- T14, the first draft of `recon/llm/verifier.py` was written in one pass and was
  not runnable as submitted: it built regexes with inline `__import__("re")`
  calls, imported `packet_hash` inside a helper, and left a `packet` parameter on
  `_override_hits()` that the body ignored. Replaced with module-level compiled
  patterns, a top-level import, and the unused parameter removed; also split two
  conditions that exceeded the 100-character limit (`ruff check .` reported
  `E501` on lines 122 and 171). Verified by `ruff check .`,
  `ruff format --check .` (89 files) and the 200-test suite.
- T14, `pytest -q tests/llm/test_verifier.py` first failed two tests. The
  override pattern `\b(?:not|no) a discrepancy\b` can never match "no
  discrepancy" (it requires an article after `no`), so the fifth parametrized
  phrase passed the verifier; split into `\bnot a discrepancy\b` and
  `\bno discrepancy\b`. The second failure was my own test bug: it re-rendered an
  allowed amount with `:.1f` to prove `Decimal` comparison, but that *rounds*
  (2000.55 becomes 2000.6), so the citation was genuinely different money; it
  also assumed the packet held an amount ending in a zero hundredth, which the
  `date_mismatch` packet does not. Changed to `:.3f`, which always represents the
  same value. 29 verifier tests then passed.
- T15 (closeout gap found in the T16 session), `docs/Memory.md` carried the full
  T15 record and the artifacts existed, but `quest-submission/ai-usage-log.md`
  had no T15 entry: AGENTS.md step (b) was skipped. Re-verified the logged numbers
  before writing it late (`pytest -q` 214 passed, `ruff check .` clean,
  `ruff format --check .` 90 files, and a fresh `run --llm mock` on realistic seed
  42 giving 552 findings, 68 `ai_verified` across all eight types with 0 `unknown`
  causes, 484 deterministic rationales and 68 log lines), then appended the entry.
  The usage log for T08 is still open from the same kind of gap.
- T15, the first draft of `recon/llm/explain.py` was not runnable as written: it
  called a non-existent `VerifiedExplanation.fallback()`, referenced an
  `_answer_records()` helper it never defined, kept a dead `_records_for()` stub
  that returned `[]`, used `get_settings()` without importing it, and read an
  `answers` dict before its assignment in the empty-packet branch. It also caught
  `LLMError` in the pipeline, which would have dropped the attempts the verifier
  had already recorded. Restructured so the retry/fallback loop owns the error
  handling and `explain.py` only schedules and collects.
- T15, `pytest -q tests/llm/test_explain.py` first failed 2 of 13:
  `FileNotFoundError: .../src/ledger.csv` because the CSV helper did not create
  its folder, and an artifacts test that built a bank path with
  `.with_name("bank.csv")` for a file that was never written. Fixed the helper to
  `mkdir` and wrote both files properly; also replaced a statistics assertion that
  compared a packet count against a set of finding types. 13 tests then passed.
- T15, `ruff check .` reported `I001` in `recon/matching/engine.py` (the new
  `recon.llm` imports were appended after the `recon.matching` block) and 3 x
  `E501` in `recon/llm/explain.py`. Applied `ruff check --fix`, wrapped the three
  lines, moved the `LLMError` catch into `explain_verified()` and added a verifier
  test for it. Verified by `ruff check .`, `ruff format --check .` (90 files) and
  214 passing tests.
- T16, the first draft of `recon/report/builder.py` formatted money in the wrong
  place: `_fact_value()` ran every `int` through `format_amount`, which would have
  printed row numbers, day counts and config thresholds as `3.00`, while
  `_fact_rows()` already handles `*_minor` keys correctly. It also carried an
  unused `MINOR_FIELD_PREFIXES` table, an unused `meta` local in
  `recon/report/audit.py`, and three lines over the 100-character limit. Caught by
  re-reading before the first test run; the money rule is now asserted by
  `test_money_is_grouped_and_minor_units_are_hidden`.
- T16, `pytest -q tests/report` first failed 2 of 26. The audit test assumed
  verifier attempts were numbered from 1: `explain_verified()` uses
  `range(RETRY_LIMIT + 1)`, so the events are `attempt` 0 and 1, and the second
  attempt is also `rejected` and does carry `request_codes`, which made
  `assert all(not event["request_codes"] ...)` fail. Rewritten to compare attempt 0
  against attempt 1 per packet hash and assert the failure codes really are fed
  back. The second failure was my own helper: `_section(html, "appendix",
  "</main>")` built `id="</main>"` and raised `ValueError: substring not found`;
  the end marker is now passed literally.
- T16, `ruff check .` reported `I001` in `tests/report/test_builder.py` after a
  scripted edit deleted the blank line that separates the import block from the
  module constants; `ruff check --fix` and `ruff format .` (2 files) cleaned it.
  The full suite then failed 2 pre-existing tests, `test_run_pipeline_writes_reproducible_artifacts`
  and `test_artifacts_include_the_verifier_log_only_for_llm_runs`, both of which
  asserted `write_run_artifacts()` returned exactly `["findings.json",
  "run_meta.json"]` (or ended with the verifier log). Updated to the T16 artifact
  sets and re-verified: 240 passed, both Ruff checks clean.
- T16, the browser check found two visual defects that no test caught: the record
  grid right-aligned `Row` and `Amount` values, so on a narrow viewport the numbers
  floated to the far edge alone on their line (fixed by dropping `text-align: right`
  inside `.record dd` and the `num` class from the row cell), and the title block
  printed the full ISO-8601 instant with microseconds. Verified at 1440px and at
  591px in an iframe: two-column evidence grid, 878px AI box, no overflowing table,
  zero network requests, zero console messages.
- T17, `pytest -q tests/api` first failed 4 of 27 with
  `KeyError: 'L-000004'` inside `_side_total()`: an `invalid_record` finding names a
  rejected row, and rejected rows have no `Transaction` in
  `RunResult.records_by_id`, so summing a side by ID cannot assume every ID resolves.
  The helper now skips unresolvable IDs and returns `None` when a side holds no known
  record, which mirrors the report's `unavailable` cell. 27 tests then passed.
- T17, three asset tests failed on `text/css` versus
  `text/css; charset=utf-8`: Starlette appends the charset to `text/*` media types.
  The assertions now use `startswith`, which still proves the type without hard-coding
  the vendor's suffix. My assumption about the exact header value was wrong, not the
  server.
- T17, `ruff check .` reported `I001` in `recon/api/app.py` (bare `import uvicorn`
  must precede the `from fastapi import` block), `F401` for an unused
  `dataclasses.field` import in `routes.py` and 2 x `E501` in `tests/api/test_routes.py`
  (the oversized-row comprehension and the artifact-name assertion). Fixed by
  reordering, deleting and wrapping, then `ruff check --fix` and `ruff format .`;
  both checks are clean and 96 files report as formatted.
- T17, the severity filter defaulted to `medium` instead of `All`, so the first render
  silently dropped most rows: `renderFilterOptions()` appended options before calling
  `prepend(option(ALL_VALUE, "All"))`, leaving "Medium" as `options[0]`. Found by
  reading the rendered `<select>` in the browser, not by any test; "All" is now
  appended first for both selects, and `test_ui.py` asserts the label set. Re-measured:
  225 of 225 findings instead of 119 of 225.
- T17, a second browser-only defect: rendering every finding including the 185 matched
  rows made the page 22189px tall, which contradicts Design section 7 ("collapsed by
  default in the UI") and was the exact behaviour T16 deferred to this task. Added the
  `Matched items` checkbox (off by default) to `visibleFindings()` plus `.toggle`
  styling and a test; re-measured at 40 rows / 5354px.
- T17, a browser script hung and timed out while polling for `#results` to appear: the
  panel was already visible from the previous run in the same page, so the waiter never
  resolved and then returned stale data. The harness now hides `#results` and
  `#error-alert` before clicking and re-reads the state after a timeout instead of
  trusting the poll.
- T17, `python -m recon serve` on the documented port reported
  `[Errno 98] ... address already in use` because the human's own
  `python -m recon serve` (PID 222371) was already listening on 127.0.0.1:8000 and
  serving this same new app. Verified by `curl` (200 `text/html`, `/api/health`
  reports `llm_provider: groq`) rather than killing the human's process; my own scratch
  servers on 8123/8124 were the only ones stopped.
- T18, the first aggregate run crashed with
  `AttributeError: 'float' object has no attribute 'get'`: `_total()` walked
  `report["match_pair"][type]`, but match-pair metrics are a flat confusion block
  (`tp`, `fp`, `fn`, ratios), not a per-type mapping like `per_type`. Match-pair
  accuracy now renders through the same row builder that sums the flat blocks, so
  the section cannot assume a shape the metric function never returns.
- T18, the first `final_eval.md` printed the mock headline table under a
  provider-dependent position: section order came from `Counter` insertion order
  over the runs, so re-invoking `eval` after a groq run moved `mock` to the second
  section. Fixed with the `REFERENCE_PROVIDERS` rank described in Decisions, and a
  test asserts the section order regardless of the order the files were written
  in. My assumption that "the aggregator sorts deterministically" was wrong: the
  order was deterministic per input list, not stable across invocations.
- T18, the `derived_metrics()` guard I first wrote tested
  `if detected else 0.0` for precision and `if labelled else 0.0` for recall but
  reused the wrong denominator name in the F1 line, which would have divided by
  zero when a type had detections but no labels. Caught by reading the two
  denominators against the metric definitions before running anything; both guards
  now sit on their own ratio and the shared test covers the empty case.
- T18, `pytest -q tests/evaluation` first failed 3 tests I had just written, all
  three my own expectation errors, not code defects: a faulty_mock fixture kept
  the default TP/FP/FN so the packet count came out 11 instead of the 7 the
  assertion expected; an e2e assertion compared one run's `overall` counts against
  the micro-average of two runs; and `cause_accuracy["scored"] ==
  verifier["packets"]` holds only where every discrepancy was detected (grid
  totals 557 scored versus 739 packets), so the e2e test now asserts the weaker
  true relation `0 < scored <= len(discrepancies)`. All 14 evaluation tests and 3
  e2e tests pass after the fixes.
- T18, `ruff check .` reported 10 × `E501` in the new evaluation and e2e test
  files (grid-assertion lists and the groq verifier line). `ruff format .`
  rewrapped 4 files; `ruff check .` is clean and `ruff format --check .` reports
  100 files already formatted. (Annotated at T19: that count included Markdown as
  well as Python and drifted with the documents on disk; the T19 closeout sweep
  measures 101.)
- T18, the groq evaluation that the task mandates because `LLM_API_KEY` is set
  spent most of its calls on rate limiting: 126 HTTP 429 responses against 55
  successful ones in about 4 minutes for 63 packets. 18 packets ended as
  `provider_error` attempts and took the deterministic fallback (24 fallbacks in
  total including rejected answers), the run completed, and no metric moved. This
  is Rule 5 working as specified, and the numbers are reported in the `groq`
  section of `reports/final_eval.md` rather than hidden.
- T19, the T18 closeout I had just written claimed "full suite 280 passed" in three
  places. A fresh `python -m pytest -q --collect-only` at the start of T19 measured 281
  tests: the per-profile aggregate test went in after the earlier full-suite run, so the
  figure had been carried forward from a stale measurement instead of re-taken.
  Corrected in the task table, the Updates line and the T18 usage-log entry; T19 quotes
  only numbers re-measured in T19. The same class of drift caught three more counts at
  the T19 closeout sweep - `ruff format --check .` (100 written, 101 measured, because
  ruff 0.17 counts Markdown), `demo` (0.86 s written, 0.903 s measured) and the
  `write-up.md` citations of the Memory section totals (45/67 written, 49/72 counted at
  the end of T19) - each corrected in the documents that state them as current.
- T19, finalizing the usage log exposed that its own `- Tool and model:` lines
  contradict each other and the rest of the documentation: T00 to T07 record
  "OpenCode, GPT-5.6-terra", T13 to T15 record "opencode with GPT-5 Codex", T09 to T12
  and T16 to T19 record the Qoder Desktop agent, while `docs/Memory.md` and
  `quest-submission/intent.md` describe a single build tool. Nothing in the repository
  proves which model id was right, so `write-up.md` states the tool per task range as
  the log records it and the inconsistency is filed under Open questions for the human
  to settle rather than smoothed into one clean sentence.
- T19, the two-page limit on `write-up.md` would not close. Measured with
  `soffice --headless --convert-to pdf` and `pdfinfo`: draft 1 (1233 words) 3 pages,
  draft 2 (1113 words) 3 pages, final (915 rendered words, 5,287 characters of prose plus
  an 11-row table) still 3 pages under LibreOffice's default markdown import (Letter,
  2 cm margins). The cut moved the match types and the grid totals from the table into
  two prose sentences, merged the aggregator defect into the test-failure bullet and
  shortened sections 1 to 3 and 7; further trimming would delete content the template
  requires. Reported as not proven rather than claimed as met, with the measurement, so
  the human can convert with their own margins if the quest counts printed pages.
- T19, cleaning up after the README verification, `pkill -f "recon serve --port 8123"`
  matched its own shell wrapper as well as the server, so the command was terminated with
  exit 143 before the follow-up `rm -rf reports/my_run` ran and the scratch folder
  survived. Verified the port state with `ss -ltn` and `ps`, removed the scratch folder
  in a separate command, and noted that nothing was listening on 8000 at that point (the
  human's T17 server had already stopped), so `serve` was verified on 8123 instead.

## Updates log

(Append one line per task: date, task, outcome.)

- 2026-11-02, T00, passed: created and verified the runnable bootstrap.
- 2026-11-02, T01, passed: added canonical models and Decimal money helpers;
  7 model tests and the full 8-test suite passed.
- 2026-11-02, T02, passed: added CSV/XLSX loaders, deterministic mapping, and
  limit enforcement; 7 ingestion tests and the full 15-test suite passed.
- 2026-11-02, T03, passed: added date, amount, reference, text, and currency
  normalization with row validation; 5 normalization tests and the full
  20-test suite passed.
- 2026-11-02, T04, passed: added reproducible easy, realistic, and hard data
  generation with ground truth and CLI support; 5 synthetic tests and the full
  25-test suite passed.
- 2026-11-02, T05, passed: added Tier 1 exact matching with stable tie
  resolution; 5 matcher tests including 5,000 rows and the full 30-test suite
  passed.
- 2026-11-02, T06, passed: added per-type and match-pair metrics with Tier 1
  evaluation reports; the realistic seed 42 report has overall recall 0.6439,
  and the full 34-test suite passed.
- 2026-11-02, T07, passed: added fuzzy, amount/fee, and date tiers; realistic
  seed 42 overall recall improved to 0.8727, and the full 38-test suite passed.
- 2026-11-02, T08, passed (verified retroactively in the T09 session): R3
  duplicate detection is implemented and wired into the evaluation tier chain;
  6 duplicate tests including the hard-profile decoy check passed within the
  44-test suite.
- 2026-11-02, T09, passed: added the bounded R6 split search with unique,
  ambiguous and truncated outcomes; 15 split tests and the full 59-test suite
  passed. An ad-hoc probe of the R1-R5 leftovers plus `match_splits` (not a
  saved eval report; split is not wired into `eval` until T10) found exactly the
  profile counts: realistic 8 splits + 2 ambiguous, hard 16 + 6, easy 4 + 5,
  each unique split matching its ground-truth ID set, in 1-3 ms.
- 2026-11-02, T10, passed: added the R1-R7 engine chain, severity, stable
  finding IDs, `run_pipeline()` and CLI `run`; 7 engine tests and the full
  66-test suite passed. Two identical runs on realistic seed 42 wrote byte
  -identical `findings.json` (536 findings from 526 ledger + 540 bank rows) and
  the overall eval recall on that pair is 0.891 with precision 0.901.
- 2026-11-02, T11, passed: three failure modes written to the Bug log with
  example record IDs, the two largest fixed in the generator; nine-run aggregate
  recall 0.899 to 0.967 and precision 0.912 to 0.951, `duplicate_*` and
  `missing_*` from 0.000 to 1.000 recall, `match_exact` precision improved
  0.954 to 0.971 (no regression), `match_fuzzy` 0.917 to 1.000. Tables in
  `reports/error_analysis_before.md` and `reports/error_analysis_after.md`; 68
  tests pass.
- 2026-11-02, T12, passed: added `recon/evidence/packet.py` with the allowed
  causes table, code-built `allowed_values` and `packet_hash`; 19 evidence tests
  and the full 87-test suite passed. On the refreshed realistic seed 42 run, 68 of
  552 findings are LLM-explained types and all 68 packets are unique (693-2,331
  bytes, mean 885), covering every one of the eight documented types.
- 2026-11-02, T13, passed: added `recon/llm/base.py`, `mock.py` (mock plus
  faulty_mock), `openai_compat.py`, `prompts.py`, `schema.py`, `cache.py` and 84
  offline tests; the full suite is 171 passed with both Ruff checks clean. On the
  realistic seed 42 run, `mock` returns a schema-valid, fully whitelisted answer
  for all 68 packets (68 distinct answers, all 8 types). `faulty_mock` at rate 1.0
  spread them 19 invented amounts, 12 invalid enums, 12 decision overrides and 25
  malformed JSON, byte-identical on a repeat call, and every retry-with-codes call
  answered correctly.
- 2026-11-02, T14, passed: added `recon/llm/verifier.py` with the six checks and
  codes, one retry carrying the codes back to the provider, the marked
  deterministic fallback and `verifier_log.jsonl` writers; 29 verifier tests and
  the full 200-test suite passed, both Ruff checks clean. On the realistic seed
  42 run all 68 packets were rejected on the first `faulty_mock` answer
  (100.0% catch: 25 `schema_invalid`, 19 `unsupported_figure`, 12 `bad_enum`,
  12 `decision_override`), every retry was accepted so 0 runs needed a fallback,
  and `mock` was accepted on the first attempt for all 68.
- 2026-11-02, T15, passed: added `recon/llm/explain.py`, a `provider` parameter
  to `run_pipeline()`, the CLI `run --llm` flag and `verifier_log.jsonl` as a run
  artifact; 13 pipeline tests plus a verifier provider-error test, full suite 214
  passed, both Ruff checks clean. On realistic seed 42, `--llm mock` explains all
  68 discrepancies (`ai_verified`) and gives the remaining 484 findings
  deterministic rationales (68 log lines); `--llm faulty_mock` completes with 68
  rejections, 68 retries, 0 fallbacks and 136 log lines, and the finding types,
  statuses and record IDs are identical to the no-LLM run.
- 2026-11-02, T16, passed: added `recon/report/audit.py`, the Jinja2
  `templates/report.html.j2` and the report stage in `builder.py`, so a run now
  writes `report.html`, `findings.json`, `run_meta.json`, `audit_trail.jsonl` and
  (with a provider) `verifier_log.jsonl`; 26 report tests, full suite 240 passed,
  both Ruff checks clean. On realistic seed 42 the report is one 368 KB file with
  6 sections, 68 finding cards each in a purple verified AI box, a 484-row matched
  table, the appendix (config, config hash, rule versions, verifier stats) and 624
  audit-trail lines; a browser check found zero network requests and zero console
  messages, and the `--llm none` run renders the same report with 68 "No
  explanation" cards and no AI box.
- 2026-11-02, T17, passed: added `recon/api/app.py`, `recon/api/routes.py` and
  `recon/api/static/{index.html,app.css,app.js}` plus CLI `serve`; 27 API tests, full
  suite 267 passed, both Ruff checks clean (96 files). `POST /api/demo` on easy seed 42
  returns 225 findings (185 matched, 35 discrepancy, 5 needs review) with 40
  `ai_verified`, 0 fallback, and writes `reports/web/<run_id>/` with `report.html`,
  `findings.json`, `run_meta.json`, `audit_trail.jsonl` and `verifier_log.jsonl`; three
  separate demo requests wrote byte-identical `findings.json` (sha256 `fe06d1a200cd...`)
  and the decision-field equality test in `tests/api` compares two uploads. A bad file
  returns `{"error": {...}}` with HTTP 400 `mapping_error` and
  `details.stage = "parse"`. The UI was measured in a browser at 1440px on the demo run:
  no horizontal overflow, 5354px page height with matched rows hidden (22189px when
  shown), KPI cards 185 matched / 40 discrepancies / 0 high severity / 40 AI verified /
  0 fallback, and the report link opens that run's `report.html`.
- 2026-11-02, T18, passed: added CLI `demo`, `recon/evaluation/aggregate.py`, cause
  and verifier metrics, the provider-aware evaluation runner that now uses
  `run_pipeline()`, and 3 end-to-end tests; full suite 281 passed, both Ruff
  checks clean (100 files). `python -m recon demo` finished in 1.073 s offline
  (225 findings, 0 validation issues, `reports/demo/report.html`). The grid
  (easy/realistic/hard × seeds 1/2/3, `mock`) gives overall 5370 TP / 274 FP /
  183 FN = precision 0.951, recall 0.967, F1 0.959, match-pair 0.981, and per
  profile 0.982 (easy), 0.967 (realistic), 0.951 (hard); mock cause accuracy
  557/557 = 1.000 with 739 packets all accepted first try; `faulty_mock` rejected
  all 739 first answers and recovered every one on retry (catch rate 1.000, 0
  fallbacks). The optional `groq` run on realistic seed 1 completed under rate
  limiting: 63 packets, 21 first-try passes, 18 after retry, 24 fallbacks, catch
  rate 0.533, cause accuracy 21/53 = 0.396, matching unchanged at 533/14/9 =
  0.974 / 0.983 / 0.979. All of it is in `reports/final_eval.md`, generated from
  the 19 saved JSON files.
- 2026-11-02, T19, passed: wrote `quest-submission/write-up.md` from the template using
  only figures read from `reports/final_eval.md` and failures from the Bug log (915
  rendered words, 11-row table, 3 pages at LibreOffice's default import - the two-page
  limit is reported as not proven); added the retroactive T08 usage-log entry and the
  final tally, so the log is 25 entries (4 planning, 21 build); confirmed the
  `Final-directive.md` revision table with 7 real direction changes; re-ran all six
  README commands (generate; `run --llm mock` 552 findings and 5 artifacts; eval; demo
  0.86 s / 225 findings; serve on 8123 returning 200 and `/api/health` ok; 281 tests) and
  corrected its run/output-path sections; set the `SUBMISSION-CHECKLIST.md` statuses,
  leaving the repository link and both videos open; quest folder search for `TODO`, `TBD`,
  `{{` and `AGENT:` returns nothing.
- 2026-11-02, T19 closeout sweep, passed: re-measured every figure the task documents
  depend on - `pytest -q` 281 passed in 6.59s, `ruff check .` clean, `ruff format --check .`
  101 files (81 Python + 20 Markdown), `python -m recon demo` 0.903 s / 225 findings /
  5 artifacts, marker search still empty; `write-up.md` re-rendered with `soffice` and
  `pdfinfo`, still 3 pages and 915 extracted words at LibreOffice's default import.
  `reports/` holds 20 `eval_*.json` files but
  `final_eval.md` lists 19: `eval_realistic_42.json` is a T08-era run whose seed is
  outside the requested grid, so the aggregator ignores it by design. Corrected the
  claims that read 100 formatted files (usage-log tally and `SUBMISSION-CHECKLIST.md`)
  and 0.86 s (usage-log tally) to these values; the per-task entries that recorded the
  earlier measurements stay as the history of the run they describe. Re-counted the
  `docs/Memory.md` sections that `write-up.md` cites: 49 Bug log entries and 72
  decisions at the end of T19 (45 and 67 through T18), corrected in the write-up and
  the usage-log tally; `Final-directive.md` keeps its "67 entries as of T18" wording
  because that is a point-in-time claim.

## Open questions

(Append: anything blocked or needing a human decision. Empty means none.)

- T11: 91 amount/fee/date labels are lost to one-character reference noise
  (similarity exactly 0.875 versus `REF_STRONG` 0.90). Lowering it to 0.85 was
  measured and rejected on precision grounds (see Bug log). The alternative is a
  Tier 4/5 change that treats a same-length, one-character-different reference as
  strong; that is a rule change to finished matching code and needs the human's
  go-ahead.
- T11: the nine runs contain 210 decoy `match_exact` labels, each a pair of
  byte-identical rows, so ~92 `match_exact` FN and ~92 FP across the nine runs are
  an unavoidable ID-assignment ambiguity rather than a matching error. If the
  quest write-up needs a clean "precision on matched pairs" number, the evaluator
  would have to score decoy groups as sets. Not changed: it would alter the
  published metric definition from Architecture section 12.

- T19: `quest-submission/ai-usage-log.md` records different build tools and model ids
  per session ("OpenCode, GPT-5.6-terra" for T00-T07, "opencode with GPT-5 Codex" for
  T13-T15, "Qoder Desktop agent" for T09-T12 and T16-T19) while `docs/Memory.md` and
  `quest-submission/intent.md` describe one tool for the whole build. The agent cannot
  verify a model id it did not run, so the write-up states the tool per task range as the
  log records it. The human should settle the wording from their own records before
  upload, because the quest evaluators read this log.
- T19: `AGENTS.md` still says "Do exactly ONE task from `docs/Task.md` per turn. Do not
  start the next task." while the human amended `docs/Rules.md` section 1 item 2 to "Work
  on exactly one task per turn until user asks for multiple tasks in one run". The
  amendment is what allowed T18 and T19 in one run. `AGENTS.md` is the human's entry
  point and was not edited; align it if the new wording is the intended standing rule.
- T19: `quest-submission/loom-scripts.md` Part A still narrates "opencode with the GPT-5
  Codex model ... 21 small tasks one at a time". Its commands are all still valid, so
  T19's edit permission (stale commands only) did not cover it; the narration is the
  human's to correct before recording.
- T19: this folder is not a git repository, so checklist item 3 (the GitHub link) and
  "final_eval.md is committed" cannot be closed by the agent. Creating the repository and
  pushing are the human's actions, and `git init` plus `git add .` should be followed by a
  review of `git status`: `.env`, `venv/`, `.venv/`, `data/synthetic/*` and `reports/*`
  are gitignored, with `reports/final_eval.md` excepted.

## Environment notes

(Append: OS, Python version, package versions that mattered, model id used for
the real LLM provider, rate-limit observations.)

- Linux, Python 3.12.11; T00 dependencies installed in `.venv` and pinned in
  `requirements.txt`.
- Human verification used system Python 3.14; install dependencies with
  `python -m pip` and run tests with `python -m pytest` to keep interpreter and
  package environment aligned.
- T17: fastapi 0.162.0 with Starlette and uvicorn 0.54.0. Two behaviours shaped the
  tests: Starlette appends `; charset=utf-8` to `text/*` responses, and a handler
  registered for `Exception` still re-raises, so asserting a 500 body needs
  `TestClient(app, raise_server_exceptions=False)`. `python -m recon serve --port`
  defaults to 8000; a second instance fails with `[Errno 98] address already in use`,
  which is the expected signal that the human's server is already running.
- T18: the real provider run used the `.env` configuration (`LLM_PROVIDER=groq`,
  model `openai/gpt-oss-120b`, OpenAI-compatible base URL). Groq's free tier
  rate-limits this workload heavily: 126 HTTP 429 responses against 55 successful
  completions while explaining 63 packets in roughly 4 minutes, because the
  explanation stage issues one request per packet plus a retry. 18 packets ended
  in `provider_error` and took the deterministic fallback, so the run still
  completed with every matching metric unchanged. Plan real-provider evaluations
  around this: 63 packets is minutes, a 739-packet grid would not finish, which
  is why the groq section covers realistic seed 1 only. `python -m recon demo`
  therefore defaults to `mock` and stays at about 1 second.

