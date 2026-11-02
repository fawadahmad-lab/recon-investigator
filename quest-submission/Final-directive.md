# Final directive

This is the final standing directive that governed the AI build agent
(opencode with the GPT-5 Codex model) for the project "Recon Investigator".
The full rule book is in `docs/Rules.md`; the agent entry point is
`AGENTS.md`. This file records the directive as given, and every change of
direction made during the build.

## Mission

Build a system that detects, investigates and explains discrepancies between a
bank statement and an internal ledger, and produces an audit-ready report.

## Principle

Use deterministic code for financial correctness and AI for reasoning,
explanation and investigation assistance. The LLM never decides whether
financial transactions match. Every LLM output is checked by a verifier, and
anything that fails is replaced by a deterministic fallback.

## Operating model

1. Specification first: PRD, Architecture, Rules, Design, Task, Memory.
2. One small task at a time, in order, each with acceptance criteria and verify
   commands.
3. The human runs commands and pastes errors; the agent fixes them.
4. After every task the agent updates `docs/Memory.md`, appends to the AI usage
   log, and prints a Task Report.
5. No result, metric or log entry is ever invented. Numbers in the write-up come
   from saved evaluation files.

## Hard constraints given to the agent

- Money is never a float; integer minor units internally.
- The LLM can only produce the `explanation` field of a finding.
- No network in tests; default LLM provider is `mock`.
- Free resources only; synthetic data only; no real financial data.
- Allowed and forbidden libraries are listed in `docs/Rules.md`.
- No swallowed exceptions; LLM failures never fail a run.

## The first prompt (verbatim)

```
You are the build agent for the project in this repository: Recon Investigator, an AI-assisted bank-versus-ledger reconciliation system. I am a developer taking part in a 5-day hiring quest, and my role is only to run commands and paste errors back to you. You write and fix all the code.

Before doing anything else, read these files completely, in this order:
1. AGENTS.md
2. docs/Memory.md
3. docs/Rules.md
4. docs/Task.md
5. docs/PRD.md
6. docs/Architecture.md
7. docs/Design.md
8. quest-submission/Final-directive.md

The non-negotiable principle: deterministic code decides every match and every finding type. The LLM only explains unresolved findings from an evidence packet, and a verifier checks every LLM output. The LLM must never decide, change, create or remove a match.

How we will work:
- You do exactly ONE task per turn, taken from docs/Task.md, in order. Do not start the next task.
- Do not ask me clarifying questions unless you are truly blocked. Make the most reasonable decision and record it in docs/Memory.md under "Decisions made during the build".
- A task is finished only when its acceptance criteria are met and you have run its verify commands yourself where your environment allows. If you cannot run something, say so plainly. Never claim a test passed unless you ran it. Never invent results, numbers or log entries.
- When you finish a task: update docs/Memory.md (task status, decisions, bug log, updates log), append an entry to quest-submission/ai-usage-log.md using the entry format in that file, and print the Task Report exactly as defined in docs/Rules.md section 9. Then stop and wait for me.
- When I paste an error, fix it, re-run what you can, and record the failure and the fix in the Bug log in docs/Memory.md and in the usage log.

Your first job is T00 (Bootstrap) only. Start by confirming in at most 10 short lines that you understood the project, the trust boundary, and the workflow, then immediately implement T00 without waiting for my reply. At the end, print the Task Report with the exact commands I should run to verify T00.
```

## Follow-up prompts used

Short prompts from `prompts/02-prompt-templates.md`: start the next task,
report errors with the pasted output, confirm a task passed and continue,
describe a result that looks wrong, resume a session, and review the code
against the rules.

## Revision history

The agent appends a row here whenever the human changes the directive or the
direction of the build. At the end of the build (task T19) the agent confirms
this table is complete.

| Date | Task | Change to the directive | Reason |
|---|---|---|---|
| 2026-11-02 | planning | Initial directive and specification documents created | Start of the quest |
| 2026-11-02 | T09 to T12, T16 onward | The build agent changed from opencode to the Qoder Desktop agent; the human's role (run commands, paste errors) and the one-task-per-turn workflow stayed | The human continued the quest in a different tool; each usage-log entry records the tool that actually ran |
| 2026-11-02 | T11 | Fixes went into the synthetic generator instead of `recon/matching/`, and the third failure mode was documented rather than fixed | Two of the three were ground-truth contradictions the data itself created, so no rule change could recover them; the third needed a deterministic-threshold decision reserved for the human |
| 2026-11-02 | T11 | `REF_STRONG` stays 0.90 after being measured at 0.85 | Recall rose 0.967 to 0.971 but `amount_mismatch` precision fell to 0.862; naming the wrong discrepancy is worse than abstaining (Open questions in `docs/Memory.md`) |
| 2026-11-02 | T16 to T17 | Collapsing matched rows moved out of the HTML report and into the web UI | The report is a printed, script-free document; the UI is where "collapsed by default" belongs (Design section 7) |
| 2026-11-02 | T18 | `demo` defaults to the offline `mock` provider instead of following `LLM_PROVIDER` | The acceptance criterion is a demo that finishes under a minute, and a real provider on a free tier is rate limited |
| 2026-11-02 | T18 to T19 | Rule section 1 item 2 amended by the human: one task per turn unless the human asks for several in one run | The human asked for "T18 and T19" in a single run; `docs/Rules.md` was edited by the human and `AGENTS.md` still carries the original wording |

Confirmed complete at T19: these are the direction changes that happened during
the build. Decisions that did not change the direction of the quest live in the
Decisions section of `docs/Memory.md` (67 entries as of T18).
