# Prompt templates

Copy one of these into opencode. Replace only the task number or the pasted
output.

## A. Start the next task

```
Read docs/Memory.md, docs/Rules.md and docs/Task.md. Do task T## only, then update docs/Memory.md, append to quest-submission/ai-usage-log.md, print the Task Report and stop.
```

## B. Report errors after running the verify commands

```
I ran the verify commands for T##. They failed. Here is the exact output:

<paste the full terminal output here>

Fix the cause, re-run what you can, record the failure and the fix in the Bug log in docs/Memory.md and in quest-submission/ai-usage-log.md, then print an updated Task Report with the commands I should run again.
```

## C. Everything passed, move on

```
T## verified on my machine: all commands passed. Mark it passed in docs/Memory.md, then do the next task from docs/Task.md following the same rules.
```

## D. Something looks wrong but there is no error

```
For T##, the command ran without errors but the result looks wrong: <describe what you saw, or paste the output>. Investigate against the acceptance criteria in docs/Task.md, add a test that reproduces the problem, fix it, record it in the Bug log, and print an updated Task Report.
```

## E. Resume after a break or a new session

```
New session. Read AGENTS.md, docs/Memory.md, docs/Rules.md and docs/Task.md. Tell me in 5 lines which task is current and what is left, then continue that task following the rules.
```

## F. Check your own work (use before T11, T16 and T20)

```
Review the code and tests for the tasks completed so far against docs/Rules.md and docs/Architecture.md. List violations (for example floats for money, LLM influencing findings, swallowed exceptions, network use in tests, missing tests). Fix them one by one, run pytest -q and ruff check ., and report what you found and what you changed. Record anything notable in the Bug log.
```
