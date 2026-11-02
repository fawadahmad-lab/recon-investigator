# Final evaluation

Every number below is read from the JSON files listed here; none of it is typed
by hand. Regenerate the tables with:

```
$ python -m recon eval --profiles easy realistic hard --seeds 1 2 3 --llm mock
```

Input files: `eval_easy_1.json`, `eval_easy_1_faulty_mock.json`, `eval_easy_2.json`, `eval_easy_2_faulty_mock.json`, `eval_easy_3.json`, `eval_easy_3_faulty_mock.json`, `eval_hard_1.json`, `eval_hard_1_faulty_mock.json`, `eval_hard_2.json`, `eval_hard_2_faulty_mock.json`, `eval_hard_3.json`, `eval_hard_3_faulty_mock.json`, `eval_realistic_1.json`, `eval_realistic_1_faulty_mock.json`, `eval_realistic_1_groq.json`, `eval_realistic_2.json`, `eval_realistic_2_faulty_mock.json`, `eval_realistic_3.json`, `eval_realistic_3_faulty_mock.json`.

Matching is decided by deterministic code alone, so the per-type and match-pair
tables are identical for every provider listed here; only the cause accuracy and
verifier statistics differ between providers. Ratios are micro-averaged: the TP,
FP and FN counts are summed over the runs of a section before precision, recall
and F1 are computed.

## Provider `mock`

Offline template provider (the shipped default). Runs: 9 (easy seed 1, easy seed 2, easy seed 3, hard seed 1, hard seed 2, hard seed 3, realistic seed 1, realistic seed 2, realistic seed 3, 5,379 ledger and 5,580 bank rows). Tier: R1-R7.

| Type | TP | FP | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|
| ambiguous_split | 39 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| amount_mismatch | 61 | 0 | 26 | 1.000 | 0.701 | 0.824 |
| date_mismatch | 52 | 0 | 35 | 1.000 | 0.598 | 0.748 |
| duplicate_in_bank | 69 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| duplicate_in_ledger | 69 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| fee_difference | 57 | 0 | 30 | 1.000 | 0.655 | 0.792 |
| match_exact | 3083 | 92 | 92 | 0.971 | 0.971 | 0.971 |
| match_fuzzy | 1646 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| match_split | 84 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| missing_in_bank | 105 | 91 | 0 | 0.536 | 1.000 | 0.698 |
| missing_in_ledger | 105 | 91 | 0 | 0.536 | 1.000 | 0.698 |
| overall | 5370 | 274 | 183 | 0.951 | 0.967 | 0.959 |

### Match-pair accuracy

| Type | TP | FP | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|
| all matches | 4813 | 92 | 92 | 0.981 | 0.981 | 0.981 |

### Per-type metrics by profile

`easy` (seeds 1, 2, 3):

| Type | TP | FP | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|
| ambiguous_split | 15 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| amount_mismatch | 15 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| date_mismatch | 15 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| duplicate_in_bank | 15 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| duplicate_in_ledger | 15 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| fee_difference | 15 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| match_exact | 531 | 12 | 12 | 0.978 | 0.978 | 0.978 |
| match_split | 12 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| missing_in_bank | 15 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| missing_in_ledger | 15 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| overall | 663 | 12 | 12 | 0.982 | 0.982 | 0.982 |

`hard` (seeds 1, 2, 3):

| Type | TP | FP | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|
| ambiguous_split | 18 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| amount_mismatch | 27 | 0 | 21 | 1.000 | 0.562 | 0.720 |
| date_mismatch | 18 | 0 | 30 | 1.000 | 0.375 | 0.545 |
| duplicate_in_bank | 36 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| duplicate_in_ledger | 36 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| fee_difference | 27 | 0 | 21 | 1.000 | 0.562 | 0.720 |
| match_exact | 1487 | 54 | 54 | 0.965 | 0.965 | 0.965 |
| match_fuzzy | 1309 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| match_split | 48 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| missing_in_bank | 60 | 72 | 0 | 0.455 | 1.000 | 0.625 |
| missing_in_ledger | 60 | 72 | 0 | 0.455 | 1.000 | 0.625 |
| overall | 3126 | 198 | 126 | 0.940 | 0.961 | 0.951 |

`realistic` (seeds 1, 2, 3):

| Type | TP | FP | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|
| ambiguous_split | 6 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| amount_mismatch | 19 | 0 | 5 | 1.000 | 0.792 | 0.884 |
| date_mismatch | 19 | 0 | 5 | 1.000 | 0.792 | 0.884 |
| duplicate_in_bank | 18 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| duplicate_in_ledger | 18 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| fee_difference | 15 | 0 | 9 | 1.000 | 0.625 | 0.769 |
| match_exact | 1065 | 26 | 26 | 0.976 | 0.976 | 0.976 |
| match_fuzzy | 337 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| match_split | 24 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| missing_in_bank | 30 | 19 | 0 | 0.612 | 1.000 | 0.759 |
| missing_in_ledger | 30 | 19 | 0 | 0.612 | 1.000 | 0.759 |
| overall | 1581 | 64 | 45 | 0.961 | 0.972 | 0.967 |

### Cause accuracy

| Finding type | Scored | Correct | Accuracy |
|---|---:|---:|---:|
| ambiguous_split | 39 | 39 | 1.000 |
| amount_mismatch | 61 | 61 | 1.000 |
| date_mismatch | 52 | 52 | 1.000 |
| duplicate_in_bank | 69 | 69 | 1.000 |
| duplicate_in_ledger | 69 | 69 | 1.000 |
| fee_difference | 57 | 57 | 1.000 |
| missing_in_bank | 105 | 105 | 1.000 |
| missing_in_ledger | 105 | 105 | 1.000 |
| all types | 557 | 557 | 1.000 |

### Verifier statistics

| Packets | Pass first try | Pass after retry | Fallback | Provider errors | Rejected first answers | Rejected answers | Catch rate |
|---|---:|---:|---:|---:|---:|---:|---:|
| 739 | 739 | 0 | 0 | 0 | 0 | 0 | 0.000 |

## Provider `faulty_mock`

Offline provider that injects a fault into every packet to measure the verifier. Runs: 9 (easy seed 1, easy seed 2, easy seed 3, hard seed 1, hard seed 2, hard seed 3, realistic seed 1, realistic seed 2, realistic seed 3, 5,379 ledger and 5,580 bank rows). Tier: R1-R7.

| Type | TP | FP | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|
| ambiguous_split | 39 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| amount_mismatch | 61 | 0 | 26 | 1.000 | 0.701 | 0.824 |
| date_mismatch | 52 | 0 | 35 | 1.000 | 0.598 | 0.748 |
| duplicate_in_bank | 69 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| duplicate_in_ledger | 69 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| fee_difference | 57 | 0 | 30 | 1.000 | 0.655 | 0.792 |
| match_exact | 3083 | 92 | 92 | 0.971 | 0.971 | 0.971 |
| match_fuzzy | 1646 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| match_split | 84 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| missing_in_bank | 105 | 91 | 0 | 0.536 | 1.000 | 0.698 |
| missing_in_ledger | 105 | 91 | 0 | 0.536 | 1.000 | 0.698 |
| overall | 5370 | 274 | 183 | 0.951 | 0.967 | 0.959 |

### Match-pair accuracy

| Type | TP | FP | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|
| all matches | 4813 | 92 | 92 | 0.981 | 0.981 | 0.981 |

### Per-type metrics by profile

`easy` (seeds 1, 2, 3):

| Type | TP | FP | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|
| ambiguous_split | 15 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| amount_mismatch | 15 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| date_mismatch | 15 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| duplicate_in_bank | 15 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| duplicate_in_ledger | 15 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| fee_difference | 15 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| match_exact | 531 | 12 | 12 | 0.978 | 0.978 | 0.978 |
| match_split | 12 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| missing_in_bank | 15 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| missing_in_ledger | 15 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| overall | 663 | 12 | 12 | 0.982 | 0.982 | 0.982 |

`hard` (seeds 1, 2, 3):

| Type | TP | FP | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|
| ambiguous_split | 18 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| amount_mismatch | 27 | 0 | 21 | 1.000 | 0.562 | 0.720 |
| date_mismatch | 18 | 0 | 30 | 1.000 | 0.375 | 0.545 |
| duplicate_in_bank | 36 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| duplicate_in_ledger | 36 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| fee_difference | 27 | 0 | 21 | 1.000 | 0.562 | 0.720 |
| match_exact | 1487 | 54 | 54 | 0.965 | 0.965 | 0.965 |
| match_fuzzy | 1309 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| match_split | 48 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| missing_in_bank | 60 | 72 | 0 | 0.455 | 1.000 | 0.625 |
| missing_in_ledger | 60 | 72 | 0 | 0.455 | 1.000 | 0.625 |
| overall | 3126 | 198 | 126 | 0.940 | 0.961 | 0.951 |

`realistic` (seeds 1, 2, 3):

| Type | TP | FP | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|
| ambiguous_split | 6 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| amount_mismatch | 19 | 0 | 5 | 1.000 | 0.792 | 0.884 |
| date_mismatch | 19 | 0 | 5 | 1.000 | 0.792 | 0.884 |
| duplicate_in_bank | 18 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| duplicate_in_ledger | 18 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| fee_difference | 15 | 0 | 9 | 1.000 | 0.625 | 0.769 |
| match_exact | 1065 | 26 | 26 | 0.976 | 0.976 | 0.976 |
| match_fuzzy | 337 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| match_split | 24 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| missing_in_bank | 30 | 19 | 0 | 0.612 | 1.000 | 0.759 |
| missing_in_ledger | 30 | 19 | 0 | 0.612 | 1.000 | 0.759 |
| overall | 1581 | 64 | 45 | 0.961 | 0.972 | 0.967 |

### Cause accuracy

| Finding type | Scored | Correct | Accuracy |
|---|---:|---:|---:|
| ambiguous_split | 39 | 39 | 1.000 |
| amount_mismatch | 61 | 61 | 1.000 |
| date_mismatch | 52 | 52 | 1.000 |
| duplicate_in_bank | 69 | 69 | 1.000 |
| duplicate_in_ledger | 69 | 69 | 1.000 |
| fee_difference | 57 | 57 | 1.000 |
| missing_in_bank | 105 | 105 | 1.000 |
| missing_in_ledger | 105 | 105 | 1.000 |
| all types | 557 | 557 | 1.000 |

### Verifier statistics

| Packets | Pass first try | Pass after retry | Fallback | Provider errors | Rejected first answers | Rejected answers | Catch rate |
|---|---:|---:|---:|---:|---:|---:|---:|
| 739 | 0 | 739 | 0 | 0 | 739 | 739 | 1.000 |

## Provider `groq`

Real OpenAI-compatible endpoint configured by `.env`. Runs: 1 (realistic seed 1, 526 ledger and 540 bank rows). Tier: R1-R7.

| Type | TP | FP | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|
| ambiguous_split | 2 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| amount_mismatch | 6 | 0 | 2 | 1.000 | 0.750 | 0.857 |
| date_mismatch | 6 | 0 | 2 | 1.000 | 0.750 | 0.857 |
| duplicate_in_bank | 6 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| duplicate_in_ledger | 6 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| fee_difference | 7 | 0 | 1 | 1.000 | 0.875 | 0.933 |
| match_exact | 353 | 4 | 4 | 0.989 | 0.989 | 0.989 |
| match_fuzzy | 119 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| match_split | 8 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| missing_in_bank | 10 | 5 | 0 | 0.667 | 1.000 | 0.800 |
| missing_in_ledger | 10 | 5 | 0 | 0.667 | 1.000 | 0.800 |
| overall | 533 | 14 | 9 | 0.974 | 0.983 | 0.979 |

### Match-pair accuracy

| Type | TP | FP | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|
| all matches | 480 | 4 | 4 | 0.992 | 0.992 | 0.992 |

### Per-type metrics by profile

`realistic` (seeds 1):

| Type | TP | FP | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|
| ambiguous_split | 2 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| amount_mismatch | 6 | 0 | 2 | 1.000 | 0.750 | 0.857 |
| date_mismatch | 6 | 0 | 2 | 1.000 | 0.750 | 0.857 |
| duplicate_in_bank | 6 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| duplicate_in_ledger | 6 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| fee_difference | 7 | 0 | 1 | 1.000 | 0.875 | 0.933 |
| match_exact | 353 | 4 | 4 | 0.989 | 0.989 | 0.989 |
| match_fuzzy | 119 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| match_split | 8 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| missing_in_bank | 10 | 5 | 0 | 0.667 | 1.000 | 0.800 |
| missing_in_ledger | 10 | 5 | 0 | 0.667 | 1.000 | 0.800 |
| overall | 533 | 14 | 9 | 0.974 | 0.983 | 0.979 |

### Cause accuracy

| Finding type | Scored | Correct | Accuracy |
|---|---:|---:|---:|
| ambiguous_split | 2 | 2 | 1.000 |
| amount_mismatch | 6 | 0 | 0.000 |
| date_mismatch | 6 | 5 | 0.833 |
| duplicate_in_bank | 6 | 3 | 0.500 |
| duplicate_in_ledger | 6 | 5 | 0.833 |
| fee_difference | 7 | 5 | 0.714 |
| missing_in_bank | 10 | 1 | 0.100 |
| missing_in_ledger | 10 | 0 | 0.000 |
| all types | 53 | 21 | 0.396 |

### Verifier statistics

| Packets | Pass first try | Pass after retry | Fallback | Provider errors | Rejected first answers | Rejected answers | Catch rate |
|---|---:|---:|---:|---:|---:|---:|---:|
| 63 | 21 | 18 | 24 | 18 | 24 | 28 | 0.533 |

## Limitations

1. Every metric comes from synthetic data: no real bank or ledger file has been evaluated, and one currency per run is assumed.
2. A predicted finding is correct only when its type and its full set of record IDs equal a labelled entry, so a re-grouped but equivalent pair counts as both a false positive and a false negative. The `realistic` and `hard` profiles inject legitimate repeated payments as decoys, and each decoy group is two byte-identical rows, so part of the `match_exact` error is unavoidable ID ambiguity rather than a matching mistake (documented under Open questions in `docs/Memory.md`).
3. Single-character reference noise normalizes to a similarity of 0.875, below the `REF_STRONG` threshold of 0.90, so those labelled mismatches stay unmatched and appear as `missing_in_*` false positives. Lowering the threshold was measured and rejected on precision grounds; see the Bug log in `docs/Memory.md` (T11).
4. `mock` is a deterministic template provider: it proves the packet, verifier and report plumbing end to end, and its cause accuracy measures that pipeline rather than a language model. A real provider is reported in its own section and only when an API key is configured. Cause labels are single-valued in the ground truth (each injected discrepancy carries exactly one cause), so a real model that names a different but plausible cause is counted wrong, and its cause accuracy is a lower bound rather than an error rate.
5. The catch rate is the share of first answers the verifier rejected. With `faulty_mock` every packet carries an injected fault, so 1.000 there means every injected fault was caught; a clean provider returns 0.000 by construction. Cause accuracy is measured on the accepted answer only, so an explanation corrected on retry scores the same as one accepted immediately.
6. The split search is bounded by the pool and node-budget thresholds in `recon/config.py`: an ambiguous or truncated anchor is reported as such instead of guessed, so those cases stay recall gaps by design.
