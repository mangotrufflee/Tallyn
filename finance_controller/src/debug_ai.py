import pandas as pd

from matcher import find_top_candidates


bank = pd.read_csv(
    "data/bank.csv",
    parse_dates=["date"]
)

erp = pd.read_csv(
    "data/erp.csv",
    parse_dates=["date"]
)

verification = pd.read_csv(
    "data/verification.csv"
)


transaction_ids = [
    "B0362",
    "B0375",
    "B0156"
]


for transaction_id in transaction_ids:

    print()
    print("=" * 70)
    print(f"TRANSACTION: {transaction_id}")
    print("=" * 70)

    bank_row = bank[
        bank["transaction_id"]
        == transaction_id
    ].iloc[0]

    expected = verification[
        verification["transaction_id"]
        == transaction_id
    ]["expected_invoice"].iloc[0]

    print()
    print("BANK TRANSACTION")
    print(
        f"Amount       : ₹{bank_row['amount']:,.2f}"
    )
    print(
        f"Date         : {bank_row['date']}"
    )
    print(
        f"Counterparty : {bank_row['counterparty']}"
    )

    print()
    print(
        f"GROUND TRUTH : {expected}"
    )

    candidates = find_top_candidates(
        bank_row,
        erp,
        top_n=5
    )

    print()
    print("TOP 5 CANDIDATES")
    print("-" * 70)

    for i, candidate in enumerate(
        candidates,
        start=1
    ):

        print(
            f"{i}. "
            f"{candidate['invoice_id']} | "
            f"Score: {candidate['final_score']:.2f} | "
            f"Amount: {candidate['amount_score']:.2f} | "
            f"Vendor: {candidate['vendor_score']:.2f} | "
            f"Date: {candidate['date_score']:.2f} | "
            f"Reference: {candidate['reference_score']:.2f}"
        )

    candidate_ids = [
        candidate["invoice_id"]
        for candidate in candidates
    ]

    print()

    if expected in candidate_ids:
        print(
            "✅ CORRECT INVOICE IS IN TOP 5"
        )
    else:
        print(
            "❌ CORRECT INVOICE IS NOT IN TOP 5"
        )