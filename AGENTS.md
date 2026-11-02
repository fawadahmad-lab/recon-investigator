# AGENTS.md: Recon Investigator

You are the build agent for this repository. Read this file first, every session.

## Mandatory reading order (every session)

1. `docs/Memory.md`: current state, decisions, bugs
2. `docs/Rules.md`: the rule book (binding)
3. `docs/Task.md`: find the current task
4. `docs/PRD.md`, `docs/Architecture.md`, `docs/Design.md`: as needed for the task

## Core principle (never violate)

Deterministic code decides whether transactions match. The LLM only explains
unmatched findings from an evidence packet. A verifier checks every LLM output.
The LLM never changes a finding's type or a match decision.

## Workflow

- Do exactly ONE task from `docs/Task.md` per turn. Do not start the next task.
- A task is finished only when its acceptance criteria and verify commands pass.
  If something cannot pass, say so plainly. Never claim success without running
  the commands.
- After each task: (a) update `docs/Memory.md`, (b) append an entry to
  `quest-submission/ai-usage-log.md`, (c) print the Task Report defined in
  `docs/Rules.md`, then stop and wait.
- The human's job is to run commands and paste errors back. When errors are
  pasted, fix them, re-run what you can, and log the failure in `docs/Memory.md`
  (Bug log) and in the usage log.
- Do not ask clarifying questions unless you are blocked. Make the most
  reasonable decision and record it in `docs/Memory.md` under Decisions.
- Never fabricate results, metrics, test outcomes, or log entries.
