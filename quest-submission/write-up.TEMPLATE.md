<!--
AGENT INSTRUCTIONS (task T19). Turn this template into quest-submission/write-up.md.
- Use ONLY real data: the Bug log in docs/Memory.md, quest-submission/ai-usage-log.md,
  and reports/final_eval.md and the files in reports/.
- Every number must appear in reports/final_eval.md. Every failure must appear in the
  Bug log or the usage log. Never invent anything.
- Keep the finished write-up to at most two pages. Remove all HTML comments and all
  AGENT lines. No placeholder text may remain.
- Keep the section headings and their order.
-->

# Write-up: Recon Investigator

**Author:** Fawad Ahmad  **Quest:** Use Your Superpower (Match Hire)

## 1. The problem

(3 to 5 sentences. Bank statements and internal ledgers disagree; manual
matching and investigation is slow; the real difficulty is trusting an AI that
explains financial discrepancies. State what the system does in one sentence.)

## 2. What I unlearned

(One short paragraph. Starting instinct: let the LLM judge whether records
match. What changed: deterministic code decides, the LLM only explains from an
evidence packet, and a verifier checks it. Add one or two concrete moments from
the Bug log that changed my mind, if any exist. If none exist, say so.)

## 3. How I used AI

(Short bullet list or paragraph.)
- Planning: Claude in chat, for choosing the problem, critiquing the idea, and
  drafting the specification documents.
- Building: opencode with the GPT-5 Codex model, working through 21 small
  tasks from `docs/Task.md`, one at a time, guided by `AGENTS.md`, `Rules.md`
  and `Memory.md`.
- My role: running commands, reading errors, pasting them back.
- In the product: an OpenAI-compatible LLM (or the mock provider) writes
  explanations only; the verifier checks them.
(Add the real counts from the usage log: number of tasks completed, number of
error reports I pasted back.)

## 4. What failed

(A short list from the Bug log and the usage log: what the AI got wrong, how it
was caught, how it was fixed. Include failures in the build process and in the
product, for example matching errors found by the evaluation and verifier
rejections. Be specific and honest. If the list is short, say it is short.)

## 5. Results

(A compact table taken from reports/final_eval.md: per discrepancy type
precision, recall and F1 on the `realistic` profile, plus one line each for the
`easy` and `hard` profiles. State seeds used. Then verifier statistics: first-try
passes, passes after retry, fallbacks, and the catch rate on injected faults, and
which provider produced them. State clearly if the real LLM was or was not
evaluated.)

## 6. Limitations

(The synthetic data is easier than real data, which can make the metrics look
better than reality. List what is out of scope. Mention anything the evaluation
showed the system does badly.)

## 7. What I would do next

(Two or three concrete next steps.)

## Links

- Repository: (add the GitHub repository URL if it was provided in the repo
  README; otherwise omit this line)
- Final evaluation: `reports/final_eval.md`
