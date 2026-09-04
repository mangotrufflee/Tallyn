import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

import pandas as pd
from backend.app.reconciliation.verification_guard import verify_ai_match
from backend.app.reconciliation.verification_guard import (
    verify_ai_match,
    get_final_decision
)

bank = pd.read_csv(
    project_root / "data" / "raw" / "bank.csv",
    parse_dates=["date"]
)

erp = pd.read_csv(
    project_root / "data" / "raw" / "erp.csv",
    parse_dates=["date"]
)


# Test 1: known strong match
bank_row = bank[
    bank["transaction_id"] == "B0183"
].iloc[0]

erp_row = erp[
    erp["invoice_id"] == "INV0183"
].iloc[0]

result = verify_ai_match(bank_row, erp_row)

print("TEST 1: B0183 → INV0183")
print(result)


# Test 2: no ERP candidate
result = verify_ai_match(bank_row, None)

print()
print("TEST 2: No ERP candidate")
print(result)

print()
print("TEST 3: Amount verification")

result = verify_ai_match(bank_row, erp_row)

print("Bank amount:", bank_row["amount"])
print("ERP amount:", erp_row["amount"])
print("Guard result:", result)

print()
print("TEST 4: B0156 → INV0156")
print(result)

print()
print("TEST 5: Final decision")

decision = get_final_decision(result)

print("Verification checks:")
print(result)

print("Final decision:", decision)