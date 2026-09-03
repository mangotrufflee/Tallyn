import pandas as pd

from matcher import find_top_candidates
from ai_reasoner import build_ai_prompt, ask_ai, validate_ai_response


# Load data
bank = pd.read_csv(
    "data/bank.csv",
    parse_dates=["date"]
)

erp = pd.read_csv(
    "data/erp.csv",
    parse_dates=["date"]
)


# Pick ONE transaction
bank_row = bank.iloc[0]


# Find top 5 deterministic candidates
candidates = find_top_candidates(
    bank_row,
    erp,
    top_n=5
)


# Build AI prompt
prompt = build_ai_prompt(
    bank_row,
    candidates
)


# Ask AI
raw_response = ask_ai(prompt)


# Validate AI response
result = validate_ai_response(
    raw_response
)


print()
print("=" * 70)
print("AI RECONCILIATION TEST")
print("=" * 70)

print()
print("Transaction:")
print(bank_row["transaction_id"])

print()
print("AI RAW RESPONSE:")
print(raw_response)

print()
print("VALIDATION RESULT:")
print(result)

print("=" * 70)
