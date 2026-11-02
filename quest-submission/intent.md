# intent.md: AI Reconciliation Investigator

**Author:** Fawad Ahmad
**Quest:** Use Your Superpower (Match Hire)

## The problem

Businesses keep two sets of financial records that should agree: the bank statement and their own internal accounting records. They rarely do. Someone then spends hours matching lines by hand and chasing the causes: missing transactions, duplicate entries, amount differences, bank fees, split payments, and references that were typed or formatted differently.

Reconciliation tools exist, but the hard part is not matching. The hard part is **trust**. If an AI says "these two transactions match" or "this one is a duplicate," how does a finance person know it is right, and how does an auditor verify it later?

## The question I am trying to answer

**How do you use AI around money without letting it make unverifiable financial decisions?**

## My position

- **Deterministic code decides** whether transactions match, using explicit, testable rules.
- **AI investigates and explains** the cases that did not match, working only from evidence that the code hands to it.
- **A verifier checks the AI.** Every amount, date and reference the AI cites must exist in the evidence it was given. Anything that fails is rejected and logged.

The LLM never decides a match.

## What I am building

1. Upload two CSV or Excel files (bank statement and internal records).
2. Normalize and validate records (dates, amounts, currencies, references).
3. Exact matching, then fuzzy matching for near-misses.
4. Detect missing, duplicated and mismatched transactions.
5. For each unresolved item, build an evidence packet and have an LLM explain the likely cause and recommend an action, constrained to that packet.
6. Generate an audit-ready report: every finding with its evidence, the rule that produced it, and the recommended next step.

## The hard part I am focusing on

Reconciliation is easy when records line up one-to-one. I am focusing on the cases where they do not:

- Split payments (one internal record vs. several bank lines, or the reverse)
- Noisy or inconsistent references
- Duplicates that look almost identical but are not the same transaction

## How I will measure it

I cannot use real bank data, so I am building a **synthetic data generator** that creates bank and ledger files with labeled, injected discrepancies (duplicates, amount typos, date shifts, fees, split payments, reference noise). That gives me ground truth.

Success criteria:

- Precision and recall reported **per discrepancy type**, not one blended number.
- Zero AI-cited figures in the final report that fail verification. Any that failed during development are logged and analyzed.
- Every finding in the report traces to a rule and to evidence.
- A reviewer can reproduce the results from the repo.

## Scope

**In:** CSV and Excel (single sheet), the matching and detection engine, evidence packets, LLM explanations with a verifier, an audit-ready report, synthetic data generator and evaluation.

**Out (for these 5 days):** multi-sheet Excel, currency conversion (one currency per run), live bank integrations, user accounts, OCR or PDF statements, real financial data.

## How I plan to use AI

AI is my default way of working for this build. I plan and write the specification documents with Claude (chat), then hand a docs-first workflow to a coding agent (opencode with the GPT-5 Codex model): a product requirements document, architecture, rules, design, a task list that is executed one small task at a time, and a memory file that the agent updates. My own role is to run the code, read the errors, and feed them back. The agent keeps the AI usage log as it works, and I record every failure. In the product itself, AI is limited to explanation and investigation, never to deciding matches.

## What I expect to unlearn

My starting instinct with LLMs is to let the model do the judging. For financial data that is the wrong default. I expect to learn where the trust boundary should sit and to measure it rather than assume it.

## Risks

- Synthetic data may be easier than real data, which would make my metrics look better than they should. I will say this plainly in the write-up and include deliberately hard cases.
- Split-payment matching is a combinatorial problem and could consume the time budget. I will cap the search and report what is left unmatched instead of guessing.
- The LLM may produce fluent but wrong explanations. The verifier exists for this, and its rejections are part of the results.

## 5-day plan

| Day | Focus |
|---|---|
| 1 | Specification documents, bootstrap, models, ingestion, normalization, synthetic data generator (tasks T00 to T04) |
| 2 | Exact and fuzzy matching, amount, fee and date mismatches, duplicates, first evaluation runs (T05 to T08) |
| 3 | Split payments, full pipeline, error analysis on all profiles (T09 to T11) |
| 4 | Evidence packets, LLM providers, verifier, explanation pipeline (T12 to T15) |
| 5 | Report, web UI, final evaluation, write-up, usage log, videos (T16 to T20) |
