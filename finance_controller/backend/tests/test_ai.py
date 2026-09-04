import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd

print("=" * 70)
print("AI RECONCILIATION TEST")
print("=" * 70)

print("\n1. Script started")

from backend.app.reconciliation.matcher import find_top_candidates
print("2. Matcher imported")

from backend.app.ai.ai_reasoner import build_ai_prompt, ask_ai, validate_ai_response
print("3. AI reasoner imported")

# Load data
bank = pd.read_csv(project_root / "data" / "raw" / "bank.csv")
erp = pd.read_csv(project_root / "data" / "raw" / "erp.csv")

bank["date"] = pd.to_datetime(bank["date"])
erp["date"] = pd.to_datetime(erp["date"])

print("4. Data loaded")

# Test transaction
transaction_id = "B0375"

bank_row = bank[bank["transaction_id"] == transaction_id].iloc[0]

print("\n5. Transaction selected")
print(bank_row)

# Find candidates
candidates = find_top_candidates(
    bank_row,
    erp,
    top_n=5
)

print("\n6. Candidates found")

for i, candidate in enumerate(candidates, start=1):
    print(f"\nCandidate {i}:")
    print(candidate)

# Build prompt
prompt = build_ai_prompt(
    bank_row,
    candidates
)

print("\n7. Prompt created")

# PRINT EXACT PROMPT
print("\n" + "=" * 70)
print("PROMPT SENT TO AI")
print("=" * 70)
print(prompt)
print("=" * 70)

# Ask AI
print("\n8. Sending prompt to Qwen...")

raw_response = ask_ai(prompt)

print("\n" + "=" * 70)
print("AI RAW RESPONSE")
print("=" * 70)
print(raw_response)

# Validate
validation = validate_ai_response(raw_response)

print("\n" + "=" * 70)
print("VALIDATION RESULT")
print("=" * 70)
print(validation)

print("\n" + "=" * 70)
print("TEST COMPLETE")
print("=" * 70)