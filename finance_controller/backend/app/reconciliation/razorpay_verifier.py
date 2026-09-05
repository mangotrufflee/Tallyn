from __future__ import annotations

from typing import Any, Dict, Optional


MATERIAL_AMOUNT_TOLERANCE = 500.0
DEFAULT_DATE_TOLERANCE_DAYS = 3


def _to_float(value: Any) -> float:
    """
    Safely convert a value to float.
    Missing or invalid values become 0.0.
    """
    if value is None or value == "":
        return 0.0

    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def calculate_expected_settlement(settlement: Dict[str, Any]) -> float:
    """
    Calculate the amount that should reach the merchant's bank account.

    Formula:

        gross
        - refunds
        - fees
        - tax
        + adjustments
    """

    gross = _to_float(
        settlement.get("gross_amount")
        or settlement.get("gross")
    )

    refunds = _to_float(
        settlement.get("refund_amount")
        or settlement.get("refunds")
    )

    fees = _to_float(
        settlement.get("fee_amount")
        or settlement.get("fees")
    )

    tax = _to_float(
        settlement.get("tax_amount")
        or settlement.get("tax")
    )

    adjustments = _to_float(
        settlement.get("adjustment_amount")
        or settlement.get("adjustments")
    )

    return round(
        gross
        - refunds
        - fees
        - tax
        + adjustments,
        2,
    )


def amount_difference(
    bank_amount: Any,
    expected_amount: Any,
) -> float:
    """
    Return absolute difference between bank and expected settlement.
    """

    bank = _to_float(bank_amount)
    expected = _to_float(expected_amount)

    return round(abs(bank - expected), 2)


def verify_settlement_amount(
    bank_amount: Any,
    settlement: Dict[str, Any],
    tolerance: float = 1.0,
) -> Dict[str, Any]:
    """
    Independently verify the bank settlement amount against
    the Razorpay settlement breakdown.
    """

    expected = calculate_expected_settlement(settlement)
    bank = _to_float(bank_amount)

    difference = round(bank - expected, 2)

    verified = abs(difference) <= tolerance

    return {
        "verified": verified,
        "bank_amount": round(bank, 2),
        "expected_amount": expected,
        "difference": difference,
        "absolute_difference": abs(difference),
        "tolerance": tolerance,
    }


def classify_settlement_exception(
    bank_amount: Any,
    settlement: Optional[Dict[str, Any]],
    *,
    bank_date: Any = None,
    settlement_date: Any = None,
    date_tolerance_days: int = DEFAULT_DATE_TOLERANCE_DAYS,
) -> Dict[str, Any]:
    """
    Classify the result of Bank -> Razorpay settlement verification.

    This function is deliberately deterministic.
    AI should explain the result, not decide it.
    """

    if settlement is None:
        return {
            "status": "EXCEPTION",
            "exception_type": "MISSING_SETTLEMENT",
            "root_cause": "No corresponding Razorpay settlement was found.",
            "recommended_action": "Review the settlement in the Razorpay dashboard.",
        }

    amount_result = verify_settlement_amount(
        bank_amount,
        settlement,
    )

    if not amount_result["verified"]:
        difference = amount_result["absolute_difference"]

        return {
            "status": "EXCEPTION",
            "exception_type": "AMOUNT_MISMATCH",
            "root_cause": (
                f"Bank credit differs from the calculated Razorpay "
                f"settlement by ₹{difference:,.2f}."
            ),
            "recommended_action": (
                "Review Razorpay settlement deductions and bank posting."
            ),
            "verification": amount_result,
        }

    # Date verification is intentionally lightweight here.
    # The existing verification guard remains responsible for
    # independent final approval.
    if bank_date is not None and settlement_date is not None:
        try:
            import pandas as pd

            bank_dt = pd.to_datetime(bank_date)
            settlement_dt = pd.to_datetime(settlement_date)

            date_difference = abs(
                (bank_dt - settlement_dt).days
            )

            if date_difference > date_tolerance_days:
                return {
                    "status": "EXCEPTION",
                    "exception_type": "DATE_MISMATCH",
                    "root_cause": (
                        f"Bank posting date differs from the "
                        f"Razorpay settlement date by "
                        f"{date_difference} days."
                    ),
                    "recommended_action": (
                        "Review settlement and bank posting dates."
                    ),
                    "verification": amount_result,
                    "date_difference_days": date_difference,
                }

        except Exception:
            # Never allow date parsing to break reconciliation.
            pass

    return {
        "status": "VERIFIED",
        "exception_type": None,
        "root_cause": None,
        "recommended_action": None,
        "verification": amount_result,
    }


def verify_razorpay_settlement(
    bank_record: Dict[str, Any],
    settlement: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Main entry point for Razorpay settlement verification.

    Matching identifies the candidate.
    This function independently verifies the candidate.
    """

    if settlement is None:
        return classify_settlement_exception(
            bank_record.get("amount"),
            None,
            bank_date=bank_record.get("date"),
            settlement_date=None,
        )

    result = classify_settlement_exception(
        bank_record.get("amount"),
        settlement,
        bank_date=bank_record.get("date"),
        settlement_date=settlement.get("settlement_date")
        or settlement.get("date"),
    )

    # Add settlement identity evidence to the verification result.
    result["settlement_id"] = (
        settlement.get("settlement_id")
        or settlement.get("invoice_id")
    )

    result["settlement_utr"] = (
        settlement.get("settlement_utr")
        or settlement.get("settlement_reference")
        or settlement.get("reference")
    )

    result["bank_utr"] = (
        bank_record.get("bank_utr")
        or bank_record.get("settlement_reference")
        or bank_record.get("bank_reference")
    )

    return result