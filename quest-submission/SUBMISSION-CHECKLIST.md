# Submission checklist (Match Hire quest: Use Your Superpower)

Seven required items. Files can be PDF, image, document or zip, up to 25 MB
each. Upload `.md` files directly or attach as documents.

| # | Required item | What to attach | Source | Status |
|---|---|---|---|---|
| 1 | intent.md | upload `quest-submission/intent.md` | ready now | ready |
| 2 | Final directive.md | upload `quest-submission/Final-directive.md` | ready now; the revision table was confirmed complete at T19 (7 rows) | ready |
| 3 | A working solution | GitHub repository link (push this folder to a public repo, or one the evaluators can open) | built and verified by tasks T00 to T19 | not pushed yet: this folder is not a git repository, so the human has to create and push it (commands below) |
| 4 | A short write-up | upload `quest-submission/write-up.md` | written at T19 from `reports/final_eval.md`, the Bug log and the usage log | ready |
| 5 | Your AI usage log for the 5 days | upload `quest-submission/ai-usage-log.md` | 25 entries: 4 planning, 21 build (T00 to T19), plus the final tally | ready |
| 6 | Loom video (max 5 min) | Loom link | record with `loom-scripts.md` Part A | after T20 |
| 7 | Career Path and Career Leverage video (max 5 min) | Loom or Google Drive link | record with `loom-scripts.md` Part B | any time |

## Before you submit

- [x] `pytest -q` passes (281 tests, verified 2026-11-02 at T19)
- [x] `python -m recon demo` works from a fresh clone (offline in about a second;
  the folder still needs `.env` copied from `.env.example`)
- [x] `ruff check .` is clean (and `ruff format --check .`: 101 files formatted)
- [x] `.env` is not in the repository (only `.env.example`; `.env` is gitignored)
- [x] `reports/final_eval.md` exists (16 KB, rebuilt from the 19 saved JSON files;
  `reports/*` is gitignored except this file)
- [ ] The repository link opens without logging in
- [x] `write-up.md` has no placeholder text and no agent instruction lines: the four
  template marker strings that `docs/Task.md` T19 lists as the verify search return
  nothing anywhere in this folder (this line deliberately does not quote them)
- [ ] `write-up.md` prints within two pages on your page setup (915 words with an 11-row
  table; measured 3 pages at LibreOffice's default markdown import - Letter, 2 cm
  margins - so convert with tighter margins or trim section 4 if the quest counts pages)
- [ ] Both videos are under 5 minutes and the links open without logging in
- [ ] Each uploaded file is under 25 MB (`quest-submission/` is 96 KB total)

## Pushing the repository

```
git init
git add .
git commit -m "Recon Investigator: Match Hire quest submission"
git branch -M main
git remote add origin https://github.com/fawadahmad-lab/<repository-name>.git
git push -u origin main
```

Create the empty repository on GitHub first (no README, no license).
