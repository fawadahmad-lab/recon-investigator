# Loom scripts

Two separate videos, each maximum 5 minutes. Record with screen sharing. Read
the spoken text naturally; it is written to fit the time. Where a number is
needed, read it from the screen at that moment. Do not memorize numbers.

---

## Part A: Quest Loom (target 4:30)

**Before recording:** all tasks T00 to T20 are done, `pytest -q` passes, and you
have a terminal in the project folder plus a browser. Run
`python -m recon demo` once beforehand so you know it works. Close
notifications.

### 0:00 to 0:25: the problem (screen: README title or `docs/PRD.md`)

> Hi, I'm Fawad Ahmad. My quest project is the Recon Investigator. Businesses
> keep a bank statement and an internal ledger, and the two never fully match.
> People waste hours finding missing items, duplicates, fees and split
> payments. The real problem isn't matching, it's trust: if an AI tells you
> two transactions match, how do you know it's right?

### 0:25 to 0:55: the principle (screen: the pipeline diagram in `docs/Architecture.md`)

> My answer is a hard trust boundary. Deterministic code decides every match
> and every finding type. The AI only explains the unresolved items, using an
> evidence packet the code builds. Then a verifier checks that every amount,
> date and ID the AI mentions really exists in that evidence. If it doesn't, the
> explanation is thrown away and replaced by a deterministic fallback.

### 0:55 to 2:15: live demo (screen: terminal, then browser)

Run: `python -m recon demo` (or click "Load demo data" in the web UI at
`http://127.0.0.1:8000` after `python -m recon serve`).

> I'll generate synthetic bank and ledger files with injected problems, run the
> pipeline, and open the audit report. There's no real financial data anywhere
> in this project.

When the report opens, scroll through it:

> At the top is the method statement and the summary. Here are the inputs with
> their file hashes, so the run is reproducible. These are the findings,
> grouped by severity.

Open one discrepancy card:

> Each finding shows the ledger and bank records, the rule that produced it,
> and the computed facts. This purple box is the only AI-generated part. It
> shows its verifier status and the recommended action.

### 2:15 to 3:05: the verifier catching a bad AI output (screen: terminal)

Run the verifier tests: `pytest -q tests/llm/test_verifier.py`

> To prove the trust boundary, I built a faulty AI provider that deliberately
> invents amounts, returns invalid causes, and tries to override a match
> decision. The verifier has a test for every failure type. Here they all run
> and pass. In a real run, a rejected explanation is retried once and then
> replaced with a deterministic fallback, and the attempt is logged.

### 3:05 to 3:45: measuring it (screen: `reports/final_eval.md`)

> Because I generate the data myself, I know the ground truth. This table shows
> precision, recall and F1 for each discrepancy type, on three difficulty
> profiles and three seeds. (Read one or two numbers from the screen.) I also
> report where the system is weak, because synthetic data is easier than real
> data and I don't want the metrics to look better than they are.

### 3:45 to 4:30: how I used AI (screen: `docs/Task.md`, `docs/Memory.md`, `quest-submission/ai-usage-log.md`)

> I worked docs-first. With Claude I picked the problem and wrote a product
> requirements document, architecture, rules, design, a task list and a memory
> file. Then I handed that package to a coding agent, opencode with the GPT-5
> Codex model, and it executed 21 small tasks one at a time. My job was to run
> the code and paste errors back. The agent logged every task, and every
> failure is in the usage log and the bug log. The biggest lesson: I started
> by thinking the AI should judge the matches, and I ended up building the
> opposite, code decides and AI explains under a verifier. Thanks for watching.

---

## Part B: Career path and career leverage video (target 4:30)

**Before recording, do this check (1 minute):** open your GitHub profile
(`https://github.com/fawadahmad-lab`) and LinkedIn
(`https://linkedin.com/in/fawad-aiml`). Look at the oldest repository or post
that is clearly about AI agents, retrieval, voice AI or machine learning
systems, and note its month and year. If it is **more than 12 months old**, use
**Version A** for the "career leverage" segment. If not, use **Version B**.
Both are valid answers according to the quest.

Screen to share throughout: your CV, then LinkedIn, then GitHub.

### 0:00 to 0:20: intro

> Hi, I'm Fawad Ahmad, an AI engineer based in Pakistan. In this video I'll
> cover my career path, my career leverage, and how this quest connects to
> both.

### 0:20 to 1:50: career path (screen: CV)

> I studied Computer Science at PMAS Arid Agriculture University, from 2022 to
> 2026. That gave me the engineering foundation: algorithms, data, software
> design.
>
> In summer 2024 I was a machine learning intern at Bytewise Limited, where I
> started working on machine learning in a professional setting.
>
> From May 2025 to August 2026 I worked as an AI engineer at XABTA in
> Islamabad. There I built machine learning and data pipeline work, and I
> shipped AI systems end to end: Python and FastAPI back ends, retrieval and
> agent workflows, voice AI, and deployment with Docker and CI/CD.
>
> My portfolio projects reflect that: a data analysis agent, a multi-agent
> banking support bot, a real-time voice assistant for a car dealership, and a
> RAG document question-and-answer platform. What all this prepared me for is
> building complete AI systems, not just models: the data, the logic, the
> interface, and the guardrails.

### 1:50 to 3:20: career leverage (screen: GitHub, then LinkedIn)

**Version A (oldest relevant public work is more than 12 months old):**

> The direction I chose for myself is applied AI engineering: agents,
> retrieval and voice systems that actually work in production. I've been
> investing in it publicly for more than a year. (Open the oldest relevant
> repository or post and say the month and year shown on screen.) Here is where
> it started, and here is how it has grown: (scroll through two or three
> pinned repositories and say in one sentence what each does). The public
> record is on my GitHub and LinkedIn, and I keep building in the same
> direction, because it is where I want my career to compound.

**Version B (less than 12 months of public work):**

> I want to be honest: I don't yet have a full year of consistent public work
> in one direction, so I wouldn't claim career leverage in the strict sense.
> What I do have is a clear direction, applied AI engineering with agents,
> retrieval and voice systems, and a body of work I can show: (open GitHub and
> point at two or three repositories, saying what each does). I am now
> deliberately building in public in this direction, and this quest project is
> the first piece of that.

### 3:20 to 4:30: quest connection (screen: the quest repository, then `docs/PRD.md`)

> This quest connects directly to both. In the past I've worked with
> reconciliation logic, OCR, reference matching and rule-based processing, so I
> chose a problem where I already had engineering depth instead of spending
> days learning a new domain. It also combines what I do in my direction:
> data pipelines, fuzzy matching, and LLM agents, with one new principle that I
> care about, which is a hard trust boundary. Deterministic code decides, AI
> explains, and a verifier checks. That is the kind of AI engineering I want to
> keep doing: systems people can trust. Thanks for watching.
