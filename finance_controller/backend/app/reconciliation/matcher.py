import pandas as pd
from rapidfuzz.fuzz import ratio
import re


def normalize_vendor(name):
    """
    Normalize vendor names into a comparable form.
    """

    name = str(name).lower().strip()

    # Remove common company suffixes
    replacements = [
        "private limited",
        "pvt ltd",
        "private ltd",
        "pvt. ltd.",
        "limited",
        "ltd.",
        "ltd",
        "inc.",
        "inc",
        "corporation",
        "corp.",
        "corp",
        "services",
        "service",
        "software",
        "india",
        "internet",
        "platforms",
        "entertainment",
    ]

    for replacement in replacements:
        name = name.replace(
            replacement,
            ""
        )

    # Remove punctuation
    name = name.replace(".", "")
    name = name.replace(",", "")

    # Normalize whitespace
    name = " ".join(
        name.split()
    )

    return name


def vendor_similarity(bank_vendor, erp_vendor):
    """Return vendor similarity from 0 to 100."""

    bank_vendor = normalize_vendor(bank_vendor)
    erp_vendor = normalize_vendor(erp_vendor)

    return ratio(
        bank_vendor,
        erp_vendor
    )


def date_similarity(bank_date, erp_date):
    """Return date similarity from 0 to 100."""

    difference = abs(
        (bank_date - erp_date).days
    )

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
    """Return amount similarity from 0 to 100."""

    difference = abs(
        bank_amount - erp_amount
    )

    if difference == 0:
        return 100
    elif difference <= 100:
        return 80
    elif difference <= 500:
        return 50
    else:
        return 0


def normalize_settlement_reference(value):
    """Normalize settlement references for exact comparison."""

    if value is None or pd.isna(value):
        return ""

    normalized = str(value).strip().upper()

    return re.sub(r"[\s-]+", "", normalized)


def _first_settlement_reference(row, fields):
    for field in fields:
        value = normalize_settlement_reference(row.get(field, ""))
        if value:
            return value

    return ""


def settlement_reference_similarity(bank_row, erp_row):
    """Return 100 when bank and Razorpay settlement references match."""

    bank_reference = _first_settlement_reference(
        bank_row,
        [
            "settlement_reference",
            "bank_utr",
            "bank_reference",
            "reference",
            "description",
        ],
    )
    erp_reference = _first_settlement_reference(
        erp_row,
        [
            "settlement_reference",
            "settlement_utr",
        ],
    )

    if bank_reference and bank_reference == erp_reference:
        return 100

    return 0

def reference_similarity(bank_row, erp_row):
    """
    Check whether the ERP reference directly matches
    the bank transaction ID.
    """

    bank_id = str(
        bank_row["transaction_id"]
    ).strip().lower()

    erp_reference = str(
        erp_row["reference"]
    ).strip().lower()

    if bank_id == erp_reference:
        return 100

    return 0


def calculate_match_score(bank_row, erp_row):
    """
    Calculate combined reconciliation score.
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

    reference_score = reference_similarity(
        bank_row,
        erp_row
    )

    settlement_reference_score = settlement_reference_similarity(
        bank_row,
        erp_row
    )

    exact_amount = (
        bank_row["amount"]
        == erp_row["amount"]
    )

    exact_date = (
        bank_row["date"]
        == erp_row["date"]
    )

    # Base score
    final_score = (
        amount_score * 0.40
        + vendor_score * 0.25
        + date_score * 0.15
        + reference_score * 0.20
    )

    # Strong evidence bonuses
    if exact_amount and exact_date:
        final_score += 5

    if exact_amount and vendor_score >= 70:
        final_score += 5

    # Direct reference match is extremely strong evidence
    if reference_score == 100:
        final_score = 100

    if settlement_reference_score == 100:
        amount_difference = abs(
            bank_row["amount"]
            - erp_row["amount"]
        )

        if amount_difference <= 500:
            final_score = 100

    final_score = min(
        final_score,
        100
    )

    return {
        "final_score": final_score,
        "amount_score": amount_score,
        "vendor_score": vendor_score,
        "date_score": date_score,
        "reference_score": reference_score,
        "settlement_reference_score": settlement_reference_score,
    }

def find_top_candidates(bank_row, erp, top_n=5):
    """
    Find the top N ERP candidates for a bank transaction.

    The deterministic matcher ranks candidates.
    The AI will later reason over these candidates.
    """

    candidates = []

    for _, erp_row in erp.iterrows():

        scores = calculate_match_score(
            bank_row,
            erp_row
        )

        candidates.append({
            "invoice_id": erp_row["invoice_id"],
            "date": erp_row["date"],
            "amount": erp_row["amount"],
            "vendor": erp_row["vendor"],
            "reference": erp_row["reference"],
            "amount_score": scores["amount_score"],
            "vendor_score": scores["vendor_score"],
            "date_score": scores["date_score"],
            "reference_score": scores["reference_score"],
            "settlement_reference_score": scores[
                "settlement_reference_score"
            ],
            "final_score": scores["final_score"],
        })

    candidates.sort(
        key=lambda x: (
            x["settlement_reference_score"],
            x["final_score"],
        ),
        reverse=True
    )

    return candidates[:top_n]


def find_best_match(bank_row, erp):
    """
    Find the best ERP candidate.

    This function is kept for compatibility with
    the existing reconciliation pipeline.
    """

    candidates = find_top_candidates(
        bank_row,
        erp,
        top_n=5
    )

    if len(candidates) == 0:
        return (
            None,
            0,
            0,
            {
                "final_score": 0,
                "amount_score": 0,
                "vendor_score": 0,
                "date_score": 0,
            },
        )

    best_candidate = candidates[0]

    best_score = best_candidate["final_score"]

    if len(candidates) > 1:
        second_best_score = candidates[1]["final_score"]
    else:
        second_best_score = 0

    best_match = None

    if best_score >= 70:
        best_match = best_candidate

    best_scores = {
        "final_score": best_candidate["final_score"],
        "amount_score": best_candidate["amount_score"],
        "vendor_score": best_candidate["vendor_score"],
        "date_score": best_candidate["date_score"],
    }

    return (
        best_match,
        best_score,
        second_best_score,
        best_scores,
    )


def classify_match(
    score,
    second_best_score,
    erp_row
):
    """
    Classify the confidence of the match.

    MATCHED:
        Strong confidence and clear separation
        from the next candidate.

    WARNING:
        Possible match but requires review.

    EXCEPTION:
        No sufficiently reliable match.
    """

    if erp_row is None:
        return "EXCEPTION"

    margin = (
        score - second_best_score
    )

    # Strong and clearly better than alternatives
    if score >= 90 and margin >= 5:
        return "MATCHED"

    # Strong score but ambiguous
    if score >= 90 and margin < 5:
        return "WARNING"

    # Medium confidence
    if score >= 70:
        return "WARNING"

    return "EXCEPTION"


def get_exception_reason(
    bank_row,
    erp_row,
    score,
    second_best_score
):
    """Explain why a transaction needs review."""

    if erp_row is None:
        return "No reliable ERP match found"

    amount_difference = abs(
        bank_row["amount"]
        - erp_row["amount"]
    )

    date_difference = abs(
        (
            bank_row["date"]
            - erp_row["date"]
        ).days
    )

    margin = (
        score - second_best_score
    )

    if amount_difference > 500:
        return (
            f"Amount mismatch: "
            f"₹{bank_row['amount']:,.2f} vs "
            f"₹{erp_row['amount']:,.2f}"
        )

    if date_difference > 3:
        return (
            "Transaction dates are "
            "too far apart"
        )

    if margin < 5:
        return (
            "Ambiguous match: "
            "top candidates have similar scores"
        )

    if score < 70:
        return "Low confidence match"

    return "Requires review"


def reconcile(bank, erp):
    """
    Reconcile all bank transactions
    against ERP transactions.
    """

    results = []

    for _, bank_row in bank.iterrows():

        (
            match,
            score,
            second_best_score,
            scores,
        ) = find_best_match(bank_row, erp)

        candidates = find_top_candidates(
            bank_row, 
            erp,
            top_n=5
        )

        status = classify_match(
            score,
            second_best_score,
            match
        )

        if match is not None:

            matched_invoice = (
                match["invoice_id"]
            )

            reason = get_exception_reason(
                bank_row,
                match,
                score,
                second_best_score
            )

        else:

            matched_invoice = None

            reason = (
                "No reliable ERP match found"
            )

        margin = (
            score - second_best_score
        )

        results.append({

            "transaction_id":
                bank_row["transaction_id"],

            "bank_amount":
                bank_row["amount"],

            "bank_date":
                bank_row["date"],

            "counterparty":
                bank_row["counterparty"],

            "matched_invoice":
                matched_invoice,

            "confidence":
                round(score, 2),

            "second_best_score":
                round(
                    second_best_score,
                    2
                ),

            "confidence_margin":
                round(
                    margin,
                    2
                ),

            "status":
                status,

            "amount_score":
                round(
                    scores["amount_score"],
                    2
                ),

            "vendor_score":
                round(
                    scores["vendor_score"],
                    2
                ),

            "date_score":
                round(
                    scores["date_score"],
                    2
                ),

            "reason":
                reason
                if status != "MATCHED"
                else "",
        })

    return pd.DataFrame(results)