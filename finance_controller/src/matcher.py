import pandas as pd
from rapidfuzz.fuzz import ratio


def normalize_vendor(name):
    """
    Normalize vendor names so that small naming differences
    do not prevent a match.
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

    name = " ".join(name.split())

    return name


def vendor_similarity(bank_vendor, erp_vendor):
    """
    Compare vendor names using fuzzy string matching.
    Returns a score between 0 and 100.
    """

    bank_vendor = normalize_vendor(bank_vendor)
    erp_vendor = normalize_vendor(erp_vendor)

    return ratio(bank_vendor, erp_vendor)


def date_similarity(bank_date, erp_date):
    """
    Compare transaction dates.

    Exact date = 100
    1 day difference = 80
    2 days difference = 60
    3 days difference = 40
    More than 3 days = 0
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


def amount_similarity(bank_amount, erp_amount):
    """
    Compare transaction amounts.

    Exact amount = 100
    Difference <= 100 = 80
    Difference <= 500 = 50
    Difference > 500 = 0
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


def calculate_match_score(bank_row, erp_row):
    """
    Calculate the overall match score between
    one bank transaction and one ERP transaction.
    """

    amount_score = amount_similarity(
        bank_row["amount"],
        erp_row["amount"]
    )

    vendor_score = vendor_similarity(
        bank_row["counterparty"],
        erp_row["vendor"]
    )

    date_score = date_similarity(
        bank_row["date"],
        erp_row["date"]
    )

    # Weighted scoring
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


def find_best_match(bank_row, erp):
    """
    Compare one bank transaction against every ERP record
    and return the best candidate.
    """

    best_match = None
    best_score = 0

    # Initialize as a dictionary so it can never be None.
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

    # Do not force a weak match.
    if best_score < 70:
        best_match = None

    return best_match, best_score, best_scores


def classify_match(score):
    """
    Convert confidence score into a business status.
    """

    if score >= 90:
        return "MATCHED"

    elif score >= 70:
        return "WARNING"

    else:
        return "EXCEPTION"


def get_exception_reason(bank_row, erp_row, score):
    """
    Explain why a transaction requires review.
    """

    if erp_row is None:
        return "No reliable ERP match found"

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


def reconcile(bank, erp):
    """
    Reconcile every bank transaction against ERP records.

    Returns a DataFrame containing:
    - predicted invoice
    - confidence
    - status
    - individual matching scores
    - exception reason
    """

    results = []

    for _, bank_row in bank.iterrows():

        match, score, scores = find_best_match(
            bank_row,
            erp
        )

        status = classify_match(score)

        if match is not None:

            matched_invoice = match["invoice_id"]

            reason = get_exception_reason(
                bank_row,
                match,
                score
            )

        else:

            matched_invoice = None
            reason = "No reliable ERP match found"

        results.append({
            "transaction_id": bank_row["transaction_id"],
            "bank_amount": bank_row["amount"],
            "bank_date": bank_row["date"],
            "counterparty": bank_row["counterparty"],
            "matched_invoice": matched_invoice,
            "confidence": round(score, 2),
            "status": status,
            "amount_score": round(
                scores["amount_score"],
                2
            ),
            "vendor_score": round(
                scores["vendor_score"],
                2
            ),
            "date_score": round(
                scores["date_score"],
                2
            ),
            "reason": (
                reason
                if status != "MATCHED"
                else ""
            ),
        })

    return pd.DataFrame(results)