import pandas as pd

from .matcher import vendor_similarity


def verify_ai_match(bank_row, erp_row):
    """
    Independently verifies the evidence behind
    an AI-selected ERP candidate.
    """

    checks = {}

    # --------------------------------------------------
    # Check 1: Candidate exists
    # --------------------------------------------------

    if erp_row is None:
        checks["candidate_exists"] = False
        return checks

    checks["candidate_exists"] = True

    # --------------------------------------------------
    # Check 2: Reference
    # --------------------------------------------------

    bank_id = str(
        bank_row["transaction_id"]
    ).strip().lower()

    erp_reference = str(
        erp_row["reference"]
    ).strip().lower()

    checks["reference_matches"] = (
        bank_id == erp_reference
    )

    # --------------------------------------------------
    # Check 3: Amount
    # --------------------------------------------------

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

    # --------------------------------------------------
    # Check 4: Date
    # --------------------------------------------------

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

    # --------------------------------------------------
    # Check 5: Vendor
    # --------------------------------------------------

    vendor_score = vendor_similarity(
        bank_row["counterparty"],
        erp_row["vendor"]
    )

    checks["vendor_similarity"] = (
        vendor_score
    )

    return checks


def get_final_decision(checks):
    """
    Converts verification evidence into a final business decision.
    The AI's confidence is deliberately NOT used here.
    """

    # No ERP candidate exists at all
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

def verify_selected_candidate(ai_invoice, candidates):
    """
    Verifies that the invoice selected by AI
    was actually present in the candidate set.
    """

    if not ai_invoice:
        return False

    if isinstance(candidates, pd.DataFrame):
        candidate_invoices = {
            str(invoice_id).strip()
            for invoice_id in candidates["invoice_id"]
        }
    else:
        candidate_invoices = {
            str(candidate["invoice_id"]).strip()
            for candidate in candidates
        }

    return str(ai_invoice).strip() in candidate_invoices