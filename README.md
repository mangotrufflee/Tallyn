# Tallyn

**AI-powered finance reconciliation system** that matches transactions across banks, ERP systems, and payment settlement sources.

> AI investigates. Rules verify. Humans decide.

## What it does

Finance teams need to reconcile the same transaction across multiple systems, even when it looks completely different in each one:

| Bank | ERP |
|---|---|
| Transaction ID: `RZP-TXN-001` | Invoice ID: `RZP-SET-001` |
| Amount: ₹13,375 | Amount: ₹13,375 |
| Vendor: UrbanCart | Vendor: Urban Cart |
| Description: "...UTR RZP260001" | Reference: RZP260001 |

The IDs don't match, but the shared UTR proves it's the same transaction. Auto-Verify is built to catch cases like this — and just as importantly, to **not** force a match when the evidence conflicts (e.g. ₹20,775 vs ₹21,625 for an otherwise similar record).

## How it works

```
Bank / ERP / Razorpay data
        ↓
   Ingestion & normalization
        ↓
   Deterministic matcher (amount, vendor, date, reference)
        ↓
   ┌─────────────┬───────────────┐
 Matched      Uncertain
                  ↓
            AI Reasoner (LLM)
                  ↓
          Verification Guard  ← independent rule-based check
                  ↓
      Matched / Review / Exception
                  ↓
          Human review (if needed)
```

**The core idea:** deterministic rules handle the easy cases. An LLM only gets involved when the rules can't confidently decide — and even then, the AI's recommendation is never final. A separate, independent "Verification Guard" double-checks it before anything counts as a match.

During testing, the AI produced confident-but-wrong matches (95% confidence, wrong invoice) multiple times. The Verification Guard caught and rejected all of them. That's the whole point of the architecture: **AI confidence is not proof.**

## Matching logic

Each bank record is scored against ERP candidates:

| Signal | Weight |
|---|---|
| Amount | 40% |
| Vendor | 25% |
| Reference / UTR | 20% |
| Date | 15% |

- **Score ≥ 90 and a clear margin over runner-up** → auto-matched
- **Weak or conflicting evidence** → sent for review
- **No credible candidate** → flagged as an exception

The system never assumes bank and ERP IDs are the same — it looks for shared evidence (UTR, reference numbers, amount, date, vendor) instead.

## Tech stack

- **Backend:** Python, FastAPI, Pandas, Pydantic, SQLite, Uvicorn
- **AI:** Ollama running Qwen2.5 locally, via an OpenAI-compatible endpoint (swappable)
- **Frontend:** React (Vite)

## Project structure

```
Tallyn/
├── backend/
│   ├── app/
│   │   ├── ai/               # AI reasoner
│   │   ├── ingestion/        # File parsing & normalization
│   │   ├── reconciliation/   # Matcher, verification guard, exceptions
│   │   ├── database.py
│   │   └── main.py
│   └── tests/
├── frontend/src/
├── scripts/                  # Data generation, benchmarking
├── data/results/
└── requirements.txt
```
## Automatic Setup

Double click from file explorer

Backend: http://127.0.0.1:8000 · Docs: http://127.0.0.1:8000/docs Frontend: URL printed by start.bat (Vite dev server)

```powershell
git clone 
cd Tallyn

setup.bat     # creates venv, installs backend + frontend deps, pulls the Ollama model
start.bat     # starts backend + frontend
stop.bat      # stops both
```

## Manual Setup

```powershell
git clone 
cd Tallyn

python -m venv .venv
.\.venv\Scripts\activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Set up the local model:

```powershell
ollama pull qwen2.5:3b
ollama list
```

Run the backend:

```powershell
python -m uvicorn backend.app.main:app --reload
```
Backend: `http://127.0.0.1:8000` · Docs: `http://127.0.0.1:8000/docs`

Run the frontend:

```powershell
cd frontend
npm install
npm run dev
```

## Testing

```powershell
# Everything
python -m pytest backend/tests -q

# Just the matcher
python -m pytest backend/tests -k matcher -v -s

# Just the AI reasoner
python -m pytest backend/tests/test_ai_reasoner.py -v -s
```

## Benchmark

```powershell
python scripts/run_final_benchmark.py
```

Reports match rate, precision, recall, F1, throughput, and any unsafe automatic matches — measured separately from live dashboard stats.

## Design decisions

- **Why not send every record to AI?** Most reconciliation is obvious and doesn't need an LLM — it would only add latency and reduce auditability.
- **Why not lower the matching threshold to automate more?** The goal is safe automation with an honest exception list, not maximum automation. A wrong auto-match is worse than a manual review.
- **Why not let the AI decide?** LLMs can be confidently wrong. AI recommends; deterministic rules verify.

## Current limitations

- PDF extraction is tuned for bank statements specifically
- Missing vendor/reference data is never fabricated — it becomes a review item instead
- Local LLM inference is slower than rule-based matching (by design, it's only used when needed)

## Roadmap

More settlement/ERP format support, better PDF extraction, human-feedback loops, historical learning, cash-position forecasting, tax/refund/adjustment reconciliation, and role-based approvals.