import pandas as pd

from .matcher import vendor_similarity


def _safe_float(value):
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def calculate_expected_settlement(razorpay_row):
    """
    Calculate the expected bank settlement:

    gross - refunds - fees - tax + adjustments
    """

    if razorpay_row is None:
        return None

    gross = _safe_float(
        razorpay_row.get("gross_amount")
    )
    refunds = _safe_float(
        razorpay_row.get("refund_amount")
    )
    fees = _safe_float(
        razorpay_row.get("fee_amount")
    )
    tax = _safe_float(
        razorpay_row.get("tax_amount")
    )
    adjustments = _safe_float(
        razorpay_row.get("adjustment_amount")
    )

    if gross is None:
        return None

    refunds = refunds or 0.0
    fees = fees or 0.0
    tax = tax or 0.0
    adjustments = adjustments or 0.0

    return round(
        gross
        - refunds
        - fees
        - tax
        + adjustments,
        2,
    )


def get_bank_settlement_reference(bank_row):
    """
    Extract the strongest settlement identifier
    available on the bank side.
    """

    for column in [
        "settlement_reference",
        "bank_utr",
        "bank_reference",
        "reference",
    ]:
        value = bank_row.get(column)

        if (
            value is not None
            and not pd.isna(value)
            and str(value).strip()
        ):
            return str(value).strip()

    description = bank_row.get("description")

    if (
        description is not None
        and not pd.isna(description)
    ):
        return str(description).strip()

    return ""


def get_razorpay_settlement_reference(razorpay_row):
    """
    Extract Razorpay's strongest settlement identifier.
    """

    for column in [
        "settlement_reference",
        "settlement_utr",
        "settlement_id",
        "reference",
    ]:
        value = razorpay_row.get(column)

        if (
            value is not None
            and not pd.isna(value)
            and str(value).strip()
        ):
            return str(value).strip()

    return ""


def normalize_reference(value):
    if value is None:
        return ""

    return (
        str(value)
        .strip()
        .lower()
        .replace(" ", "")
        .replace("-", "")
        .replace("/", "")
    )


def verify_settlement_reference(
    bank_row,
    razorpay_row,
):
    bank_reference = normalize_reference(
        get_bank_settlement_reference(bank_row)
    )

    razorpay_reference = normalize_reference(
        get_razorpay_settlement_reference(
            razorpay_row
        )
    )

    if not bank_reference:
        return False

    if not razorpay_reference:
        return False

    return (
        bank_reference == razorpay_reference
        or bank_reference in razorpay_reference
        or razorpay_reference in bank_reference
    )


def verify_settlement_amount(
    bank_row,
    razorpay_row,
):
    bank_amount = _safe_float(
        bank_row.get("amount")
    )

    settlement_amount = _safe_float(
        razorpay_row.get("settlement_amount")
    )

    if settlement_amount is None:
        settlement_amount = _safe_float(
            razorpay_row.get("amount")
        )

    if (
        bank_amount is None
        or settlement_amount is None
    ):
        return False

    return abs(
        bank_amount - settlement_amount
    ) == 0


def verify_settlement_date(
    bank_row,
    razorpay_row,
):
    bank_date = bank_row.get("date")

    settlement_date = razorpay_row.get(
        "settlement_date"
    )

    if settlement_date is None:
        settlement_date = razorpay_row.get(
            "date"
        )

    if (
        bank_date is None
        or settlement_date is None
    ):
        return False

    try:
        bank_date = pd.to_datetime(bank_date)
        settlement_date = pd.to_datetime(
            settlement_date
        )

        return (
            abs(
                (bank_date - settlement_date).days
            )
            <= 1
        )

    except Exception:
        return False


def verify_razorpay_settlement(
    bank_row,
    razorpay_row,
):
    """
    Independent verification of a Razorpay
    settlement against a bank transaction.

    The guard is the final authority.
    """

    checks = {}

    if razorpay_row is None:
        checks["candidate_exists"] = False
        checks["decision"] = "REVIEW"
        checks["exception_type"] = (
            "MISSING_SETTLEMENT"
        )
        checks["reason"] = (
            "No Razorpay settlement candidate"
        )
        return checks

    checks["candidate_exists"] = True

    checks["reference_matches"] = (
        verify_settlement_reference(
            bank_row,
            razorpay_row,
        )
    )

    checks["amount_matches"] = (
        verify_settlement_amount(
            bank_row,
            razorpay_row,
        )
    )

    checks["date_matches"] = (
        verify_settlement_date(
            bank_row,
            razorpay_row,
        )
    )

    expected_settlement = (
        calculate_expected_settlement(
            razorpay_row
        )
    )

    bank_amount = _safe_float(
        bank_row.get("amount")
    )

    checks["expected_settlement"] = (
        expected_settlement
    )

    checks["breakdown_matches"] = (
        expected_settlement is not None
        and bank_amount is not None
        and abs(
            bank_amount
            - expected_settlement
        ) <= 1
    )

    # ---------------------------------------------------------
    # FINAL DECISION
    # ---------------------------------------------------------

    if not checks["reference_matches"]:

        checks["decision"] = "REVIEW"
        checks["exception_type"] = (
            "MISSING_UTR"
        )
        checks["reason"] = (
            "Settlement reference could not be verified"
        )

        return checks

    if not checks["amount_matches"]:

        checks["decision"] = "REVIEW"
        checks["exception_type"] = (
            "AMOUNT_MISMATCH"
        )
        checks["reason"] = (
            "Bank settlement amount does not "
            "match Razorpay settlement amount"
        )

        return checks

    if not checks["breakdown_matches"]:

        checks["decision"] = "REVIEW"
        checks["exception_type"] = (
            "SETTLEMENT_BREAKDOWN_MISMATCH"
        )
        checks["reason"] = (
            "Bank amount does not reconcile "
            "with Razorpay settlement breakdown"
        )

        return checks

    if not checks["date_matches"]:

        checks["decision"] = "REVIEW"
        checks["exception_type"] = (
            "DATE_MISMATCH"
        )
        checks["reason"] = (
            "Settlement dates do not match"
        )

        return checks

    checks["decision"] = "VERIFIED"
    checks["exception_type"] = None
    checks["reason"] = (
        "Settlement reference, amount, "
        "date and breakdown verified"
    )

    return checks


# ------------------------------------------------------------------
# EXISTING ERP VERIFICATION
# ------------------------------------------------------------------

def verify_ai_match(
    bank_row,
    erp_row,
):
    checks = {}

    if erp_row is None:
        checks["candidate_exists"] = False
        return checks

    checks["candidate_exists"] = True

    bank_id = str(
        bank_row["transaction_id"]
    ).strip().lower()

    erp_reference = str(
        erp_row["reference"]
    ).strip().lower()

    checks["reference_matches"] = (
        bank_id == erp_reference
    )

    bank_amount = float(
        bank_row["amount"]
    )

    erp_amount = float(
        erp_row["amount"]
    )

    amount_difference = abs(
        bank_amount - erp_amount
    )

    checks["amount_difference"] = (
        amount_difference
    )

    checks["amount_matches"] = (
        amount_difference == 0
    )

    bank_date = pd.to_datetime(
        bank_row["date"]
    )

    erp_date = pd.to_datetime(
        erp_row["date"]
    )

    date_difference = abs(
        (bank_date - erp_date).days
    )

    checks["date_difference"] = (
        date_difference
    )

    checks["date_matches"] = (
        date_difference == 0
    )

    vendor_score = vendor_similarity(
        bank_row["counterparty"],
        erp_row["vendor"],
    )

    checks["vendor_similarity"] = (
        vendor_score
    )

    return checks


def get_final_decision(checks):

    if not checks["candidate_exists"]:
        return "EXCEPTION"

    strong_match = (
        checks["reference_matches"]
        and checks["amount_matches"]
        and checks["date_matches"]
        and checks["vendor_similarity"] >= 70
    )

    if strong_match:
        return "MATCHED"

    return "REVIEW"


# ------------------------------------------------------------------
# DUPLICATE / AMBIGUITY PROTECTION
# ------------------------------------------------------------------

def _candidate_signature(row):
    """
    Build a stable signature from the evidence that
    makes two ERP records economically equivalent.
    """

    invoice_id = str(
        row.get("invoice_id", "")
    ).strip().lower()

    amount = _safe_float(
        row.get("amount")
    )

    vendor = str(
        row.get("vendor", "")
    ).strip().lower()

    date = row.get("date")

    try:
        date = str(
            pd.to_datetime(date).date()
        )
    except Exception:
        date = str(date)

    return (
        invoice_id,
        amount,
        vendor,
        date,
    )


def detect_duplicate_candidates(
    selected_candidate,
    candidates,
):
    """
    Detect whether the selected candidate is one of
    several equivalent records.

    candidates may be:
        - list of dicts
        - pandas DataFrame
    """

    if selected_candidate is None:
        return False

    if candidates is None:
        return False

    if isinstance(candidates, pd.DataFrame):
        candidate_rows = [
            row
            for _, row in candidates.iterrows()
        ]
    else:
        candidate_rows = list(candidates)

    selected_signature = _candidate_signature(
        selected_candidate
    )

    duplicate_count = 0

    for candidate in candidate_rows:

        if isinstance(candidate, dict):
            row = candidate
        else:
            row = candidate

        if (
            _candidate_signature(row)
            == selected_signature
        ):
            duplicate_count += 1

    return duplicate_count > 1


def verify_selected_candidate(
    ai_invoice,
    candidates,
):
    """
    Verify an AI-selected ERP candidate.

    Duplicate candidates are NEVER automatically
    approved.
    """

    if not candidates:
        return {
            "decision": "EXCEPTION",
            "reason": "No candidates available",
            "checks": {},
        }

    selected = None

    if isinstance(candidates, pd.DataFrame):

        matches = candidates[
            candidates["invoice_id"]
            .astype("string")
            .str.lower()
            == str(ai_invoice)
            .lower()
        ]

        if not matches.empty:
            selected = matches.iloc[0]

    else:

        for candidate in candidates:

            invoice_id = str(
                candidate.get(
                    "invoice_id",
                    ""
                )
            ).lower()

            if invoice_id == str(
                ai_invoice
            ).lower():

                selected = candidate
                break

    if selected is None:
        return {
            "decision": "EXCEPTION",
            "reason": (
                "AI-selected invoice not found "
                "in candidate set"
            ),
            "checks": {},
        }

    # ---------------------------------------------------------
    # NEW: duplicate protection
    # ---------------------------------------------------------

    if detect_duplicate_candidates(
        selected,
        candidates,
    ):
        return {
            "decision": "REVIEW",
            "reason": (
                "Selected candidate is duplicated "
                "or ambiguous in the candidate set"
            ),
            "exception_type": (
                "DUPLICATE_SETTLEMENT"
            ),
            "checks": {},
        }

    # Existing ERP verification.
    #
    # This function may receive only the candidate
    # set, so we preserve the existing behavior.
    return {
        "decision": "REVIEW",
        "reason": (
            "Candidate requires bank-level "
            "verification"
        ),
        "checks": {},
    }