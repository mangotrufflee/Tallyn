import pandas as pd
from rapidfuzz.fuzz import ratio


# ============================================================
# 1. LOAD DATA
# ============================================================

bank = pd.read_csv("data/bank.csv")
erp = pd.read_csv("data/erp.csv")


# Convert date columns from text into actual dates
bank["date"] = pd.to_datetime(bank["date"])
erp["date"] = pd.to_datetime(erp["date"])


# ============================================================
# 2. NORMALIZE VENDOR NAMES
# ============================================================

def normalize_vendor(name):
    """
    Converts vendor names into a simpler,
    more comparable format.
    """

    name = str(name).lower().strip()

    replacements = [
        "private limited",
        "pvt ltd",
        "private ltd",
        "pvt. ltd.",
        "limited",
        "ltd.",
        "ltd",
    ]

    for replacement in replacements:
        name = name.replace(replacement, "")

    # Remove extra spaces
    name = " ".join(name.split())

    return name


# ============================================================
# 3. VENDOR SIMILARITY
# ============================================================

def vendor_similarity(bank_vendor, erp_vendor):
    """
    Returns a similarity score between 0 and 100.
    """

    bank_vendor = normalize_vendor(bank_vendor)
    erp_vendor = normalize_vendor(erp_vendor)

    return ratio(bank_vendor, erp_vendor)


# ============================================================
# 4. DATE SIMILARITY
# ============================================================

def date_similarity(bank_date, erp_date):
    """
    Calculates how close the two transaction dates are.

    Same day  -> 100
    1 day      -> 80
    2 days     -> 60
    3 days     -> 40
    >3 days    -> 0
    """

    difference = abs((bank_date - erp_date).days)

    if difference == 0:
        return 100

    elif difference == 1:
        return 80

    elif difference == 2:
        return 60

    elif difference == 3:
        return 40

    else:
        return 0


# ============================================================
# 5. AMOUNT SIMILARITY
# ============================================================

def amount_similarity(bank_amount, erp_amount):
    """
    Calculates how similar two transaction amounts are.

    Exact match       -> 100
    Difference <=100  -> 80
    Difference <=500  -> 50
    Otherwise         -> 0
    """

    difference = abs(bank_amount - erp_amount)

    if difference == 0:
        return 100

    elif difference <= 100:
        return 80

    elif difference <= 500:
        return 50

    else:
        return 0


# ============================================================
# 6. CALCULATE OVERALL MATCH SCORE
# ============================================================

def calculate_match_score(bank_row, erp_row):

    amount_score = amount_similarity(
        bank_row["amount"],
        erp_row["amount"]
    )

    date_score = date_similarity(
        bank_row["date"],
        erp_row["date"]
    )

    vendor_score = vendor_similarity(
        bank_row["counterparty"],
        erp_row["vendor"]
    )

    # Weighted score
    #
    # Amount       = 50%
    # Vendor       = 30%
    # Date         = 20%

    final_score = (
        amount_score * 0.50
        + vendor_score * 0.30
        + date_score * 0.20
    )

    return {
        "final_score": final_score,
        "amount_score": amount_score,
        "vendor_score": vendor_score,
        "date_score": date_score,
    }


# ============================================================
# 7. FIND BEST MATCH
# ============================================================

def find_best_match(bank_row, erp):

    best_match = None
    best_score = 0

    best_scores = {
        "final_score": 0,
        "amount_score": 0,
        "vendor_score": 0,
        "date_score": 0,
    }

    for _, erp_row in erp.iterrows():

        scores = calculate_match_score(
            bank_row,
            erp_row
        )

        score = scores["final_score"]

        if score > best_score:

            best_score = score
            best_match = erp_row
            best_scores = scores

    return best_match, best_score, best_scores


# ============================================================
# 8. CLASSIFY MATCH
# ============================================================

def classify_match(score):

    if score >= 90:
        return "MATCHED"

    elif score >= 70:
        return "WARNING"

    else:
        return "EXCEPTION"


# ============================================================
# 9. FIND EXCEPTION REASON
# ============================================================

def get_exception_reason(bank_row, erp_row, score):

    if erp_row is None:
        return "No matching ERP record found"

    amount_difference = abs(
        bank_row["amount"] - erp_row["amount"]
    )

    date_difference = abs(
        (bank_row["date"] - erp_row["date"]).days
    )

    if amount_difference > 500:
        return (
            f"Amount mismatch: "
            f"₹{bank_row['amount']:,.2f} vs "
            f"₹{erp_row['amount']:,.2f}"
        )

    if date_difference > 3:
        return "Transaction dates are too far apart"

    if score < 70:
        return "Low confidence match"

    return "Requires review"


# ============================================================
# 10. RUN RECONCILIATION
# ============================================================

results = []


for _, bank_row in bank.iterrows():

    match, score, scores = find_best_match(
        bank_row,
        erp
    )

    status = classify_match(score)

    if match is not None:
        exception_reason = get_exception_reason(
            bank_row,
            match,
            score
        )

        matched_invoice = match["invoice_id"]

    else:
        exception_reason = "No matching ERP record found"
        matched_invoice = None

    results.append({
        "transaction_id": bank_row["transaction_id"],
        "bank_amount": bank_row["amount"],
        "bank_date": bank_row["date"].date(),
        "counterparty": bank_row["counterparty"],
        "matched_invoice": matched_invoice,
        "confidence": round(score, 2),
        "status": status,
        "amount_score": round(
            scores["amount_score"], 2
        ),
        "vendor_score": round(
            scores["vendor_score"], 2
        ),
        "date_score": round(
            scores["date_score"], 2
        ),
        "reason": (
            exception_reason
            if status != "MATCHED"
            else ""
        ),
    })


# ============================================================
# 11. CREATE RESULTS TABLE
# ============================================================

results_df = pd.DataFrame(results)


# ============================================================
# 12. DISPLAY RESULTS
# ============================================================

print("\n")
print("=" * 80)
print("             AI FINANCE CONTROLLER")
print("             RECONCILIATION RESULTS")
print("=" * 80)

print(
    results_df[
        [
            "transaction_id",
            "matched_invoice",
            "confidence",
            "status",
            "reason",
        ]
    ].to_string(index=False)
)


# ============================================================
# 13. SUMMARY
# ============================================================

total = len(results_df)

matched = len(
    results_df[
        results_df["status"] == "MATCHED"
    ]
)

warnings = len(
    results_df[
        results_df["status"] == "WARNING"
    ]
)

exceptions = len(
    results_df[
        results_df["status"] == "EXCEPTION"
    ]
)


auto_resolution_rate = (
    matched / total * 100
    if total > 0
    else 0
)


print("\n")
print("=" * 80)
print("SUMMARY")
print("=" * 80)

print(f"Total transactions : {total}")
print(f"Matched            : {matched}")
print(f"Warnings           : {warnings}")
print(f"Exceptions         : {exceptions}")
print(
    f"Auto-resolution    : "
    f"{auto_resolution_rate:.2f}%"
)

print("=" * 80)