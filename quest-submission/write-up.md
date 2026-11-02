# Write-up: Recon Investigator

**Author:** Fawad Ahmad  **Quest:** Use Your Superpower (Match Hire)

## 1. The problem

Banks and ledgers never fully agree: missing items, duplicates, amount typos, bank fees,
split payments, references typed differently. People reconcile them by hand. The hard
part is trust, not matching: if an AI says two transactions match, a finance person
cannot check its reasoning and an auditor cannot reproduce it later. My system
reconciles a bank statement against an internal ledger with deterministic rules,
explains each unresolved finding with a constrained LLM, and shows in the report that no
unverified AI sentence reached a decision.

## 2. What I unlearned

My instinct was to let the model judge two rows; it reads descriptions better than a
regex. The error-analysis checkpoint (T11) killed that: `missing_in_*` and
`duplicate_in_*` recall sat at 0.000 because my own generator labelled a record missing
while handing the matcher its exact opposite-side twin. A number can be right and the
ground truth wrong. At T18 the evaluation harness turned out to carry its own copy of the
matching chain, so the trust boundary was an assertion, not a measurement; repointing it
at the shipped pipeline gave byte-equal metrics in all nine grids. Code decides, the LLM
explains from an evidence packet, a verifier checks it.

## 3. How I used AI

- Planning: Claude in chat, for choosing the problem, critiquing the idea and drafting
  the six specification documents in `docs/`.
- Building: a coding agent worked through 20 of the 21 tasks in `docs/Task.md`, in order,
  guided by `AGENTS.md`, `Rules.md` and `Memory.md`: OpenCode with a GPT-5 model for
  T00-T08 and T13-T15, the Qoder Desktop agent for T09-T12 and T16-T19.
- My role: run commands, read errors, paste them back. One error was mine (a missing
  dependency at T00); every other failure came from the agent running its own verify
  commands - 49 Bug log entries, 72 decisions, 25 usage-log entries.
- In the product: an LLM (or the offline `mock` provider) writes explanations only; the
  verifier checks them and a deterministic fallback answers when it does not.

## 4. What failed

- The generator contradicted its own labels (T06, T11); two fixes took `duplicate_*` and
  `missing_*` recall from 0.000 to 1.000, caught by scoring against labelled truth.
- A threshold I measured and refused to change (T11): one-character reference noise
  normalizes to 0.875, below `REF_STRONG` 0.90, so 91 labelled mismatches stay unmatched
  and appear as `missing_in_*` false positives. Lowering it cost `amount_mismatch`
  precision, so abstaining beats accusing the wrong line.
- My own tests were wrong three times (T14, T18): one rounded 2000.55 to 2000.6 while
  "proving" decimal comparison, one compared a run against a two-run average, one equated
  cause counts with packet counts. The aggregator crashed on the flat match-pair block and
  ordered sections by which provider ran last.
- Two UI defects invisible to 27 API tests (T17): a `<select>` hiding 106 of 225 rows by
  defaulting to one severity, and a 22189px page from rendering matched rows.
- A credential in a transcript (T10): I ran `cat .env`; nothing was committed, but that
  file must never be echoed. And two closeout gaps (T08, T15), work verified but never
  logged.

## 5. Results

Synthetic grid: `easy`, `realistic`, `hard`, seeds 1, 2, 3, provider `mock` (5,379 ledger
and 5,580 bank rows). Every figure below is from `reports/final_eval.md`.

| Type (realistic, seeds 1-3) | Precision | Recall | F1 |
|---|---:|---:|---:|
| amount_mismatch | 1.000 | 0.792 | 0.884 |
| date_mismatch | 1.000 | 0.792 | 0.884 |
| fee_difference | 1.000 | 0.625 | 0.769 |
| duplicate_in_bank | 1.000 | 1.000 | 1.000 |
| duplicate_in_ledger | 1.000 | 1.000 | 1.000 |
| missing_in_bank | 0.612 | 1.000 | 0.759 |
| missing_in_ledger | 0.612 | 1.000 | 0.759 |
| ambiguous_split | 1.000 | 1.000 | 1.000 |
| overall (realistic) | 0.961 | 0.972 | 0.967 |
| overall (easy) | 0.982 | 0.982 | 0.982 |
| overall (hard) | 0.940 | 0.961 | 0.951 |

On the same profile and grid the matched types score 0.976 / 0.976 / 0.976
(`match_exact`) and 1.000 (`match_fuzzy`, `match_split`). Across all nine runs the
overall row is 0.951 / 0.967 / 0.959 and match pairs score 0.981 / 0.981 / 0.981.
Verifier statistics, 739 evidence packets. `mock`: 739 accepted first try, 0 after retry,
0 fallbacks, cause accuracy 557 of 557 = 1.000 - that measures the plumbing, not a model.
`faulty_mock`, one injected fault per packet: 0 first-try passes, 739 after retry, 0
fallbacks, catch rate 1.000. The real LLM was evaluated: `groq` on realistic seed 1, 63
packets, 21 first-try passes, 18 after retry, 24 fallbacks, 18 provider errors, catch
rate 0.533, cause accuracy 21 of 53 = 0.396, matching unchanged at 0.974 / 0.983 / 0.979.

## 6. Limitations

No real bank or ledger file has been evaluated, and synthetic data flatters these numbers.
A finding counts only when its type and full ID set match a label, so the decoy groups in
`realistic` and `hard` - byte-identical legitimate repeat payments - charge the system for
ID ambiguity. `mock` cause accuracy of 1.000 says nothing about any language model, and
the real model's 0.396 is a lower bound: ground truth stores one cause per injection while
several are plausible. The `groq` figure is one run under free-tier rate limiting. Out of
scope: multi-sheet Excel, OCR, live bank feeds, user accounts, more than one currency per
run.

## 7. What I would do next

- Recover the 91 lost labels with a Tier 4/5 rule that treats a same-length,
  one-character-different reference as strong instead of lowering a threshold.
- Score decoy groups as sets so `match_exact` stops being charged for ID ambiguity.
- Run the real provider over the whole grid, so cause accuracy and the catch rate stop
  being single-run numbers.

## Links

- Final evaluation: `reports/final_eval.md`
