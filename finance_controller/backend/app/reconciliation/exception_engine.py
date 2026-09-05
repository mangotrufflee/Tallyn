from __future__ import annotations

from typing import Any, Dict, Optional


# ============================================================
# Exception Types
# ============================================================

MISSING_SETTLEMENT = "MISSING_SETTLEMENT"
AMOUNT_MISMATCH = "AMOUNT_MISMATCH"
FEE_MISMATCH = "FEE_MISMATCH"
TAX_MISMATCH = "TAX_MISMATCH"
REFUND_MISMATCH = "REFUND_MISMATCH"
ADJUSTMENT_MISMATCH = "ADJUSTMENT_MISMATCH"
DUPLICATE_SETTLEMENT = "DUPLICATE_SETTLEMENT"
AMBIGUOUS_SETTLEMENT = "AMBIGUOUS_SETTLEMENT"
MISSING_UTR = "MISSING_UTR"
DATE_MISMATCH = "DATE_MISMATCH"
LOW_CONFIDENCE = "LOW_CONFIDENCE"


EXCEPTION_METADATA = {
    MISSING_SETTLEMENT: {
        "severity": "HIGH",
        "category": "Settlement",
        "recommended_action": (
            "Check the Razorpay settlement dashboard "
            "or settlement API."
        ),
    },

    AMOUNT_MISMATCH: {
        "severity": "HIGH",
        "category": "Amount",
        "recommended_action": (
            "Review the Razorpay settlement breakdown "
            "and bank posting."
        ),
    },

    FEE_MISMATCH: {
        "severity": "MEDIUM",
        "category": "Fees",
        "recommended_action": (
            "Review Razorpay processing fees and "
            "settlement deductions."
        ),
    },

    TAX_MISMATCH: {
        "severity": "MEDIUM",
        "category": "Tax",
        "recommended_action": (
            "Review the tax component of the Razorpay "
            "settlement."
        ),
    },

    REFUND_MISMATCH: {
        "severity": "HIGH",
        "category": "Refund",
        "recommended_action": (
            "Review refunds associated with the "
            "Razorpay settlement."
        ),
    },

    ADJUSTMENT_MISMATCH: {
        "severity": "MEDIUM",
        "category": "Adjustment",
        "recommended_action": (
            "Review Razorpay adjustments applied "
            "to the settlement."
        ),
    },

    DUPLICATE_SETTLEMENT: {
        "severity": "HIGH",
        "category": "Duplicate",
        "recommended_action": (
            "Review duplicate settlement records "
            "before posting or approving."
        ),
    },

    AMBIGUOUS_SETTLEMENT: {
        "severity": "HIGH",
        "category": "Matching",
        "recommended_action": (
            "Review candidate settlements and confirm "
            "the correct settlement manually."
        ),
    },

    MISSING_UTR: {
        "severity": "MEDIUM",
        "category": "Identity",
        "recommended_action": (
            "Confirm the bank UTR or settlement reference "
            "before approving."
        ),
    },

    DATE_MISMATCH: {
        "severity": "MEDIUM",
        "category": "Date",
        "recommended_action": (
            "Review the settlement date and bank posting date."
        ),
    },

    LOW_CONFIDENCE: {
        "severity": "MEDIUM",
        "category": "Matching",
        "recommended_action": (
            "Review the transaction and settlement "
            "evidence manually."
        ),
    },
}


# ============================================================
# Exception Builder
# ============================================================

def build_exception(
    exception_type: str,
    *,
    transaction_id: Optional[str] = None,
    settlement_id: Optional[str] = None,
    bank_amount: Optional[float] = None,
    expected_amount: Optional[float] = None,
    difference: Optional[float] = None,
    root_cause: Optional[str] = None,
    recommended_action: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:

    metadata = EXCEPTION_METADATA.get(
        exception_type,
        {
            "severity": "MEDIUM",
            "category": "Other",
            "recommended_action": (
                "Review the transaction manually."
            ),
        },
    )

    return {
        "exception_type": exception_type,
        "severity": metadata["severity"],
        "category": metadata["category"],

        "transaction_id": transaction_id,
        "settlement_id": settlement_id,

        "bank_amount": bank_amount,
        "expected_amount": expected_amount,
        "difference": difference,

        "root_cause": (
            root_cause
            or f"Transaction requires review due to "
               f"{exception_type.lower().replace('_', ' ')}."
        ),

        "recommended_action": (
            recommended_action
            or metadata["recommended_action"]
        ),

        "details": details or {},
    }


# ============================================================
# Exception Classification
# ============================================================

def classify_razorpay_exception(
    verification_result: Dict[str, Any],
    *,
    transaction_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Convert the Verification Guard's result into a
    structured exception object.

    VERIFIED transactions return None.
    """

    status = verification_result.get("status")

    if status == "VERIFIED":
        return None

    exception_type = (
        verification_result.get("exception_type")
        or LOW_CONFIDENCE
    )

    checks = verification_result.get(
        "checks",
        {},
    )

    amount_check = checks.get(
        "amount",
        {},
    )

    return build_exception(
        exception_type,

        transaction_id=transaction_id,

        settlement_id=(
            verification_result.get(
                "settlement_id"
            )
        ),

        bank_amount=(
            amount_check.get(
                "bank_amount"
            )
        ),

        expected_amount=(
            amount_check.get(
                "expected_amount"
            )
        ),

        difference=(
            amount_check.get(
                "absolute_difference"
            )
        ),

        root_cause=(
            verification_result.get(
                "root_cause"
            )
        ),

        recommended_action=(
            verification_result.get(
                "recommended_action"
            )
        ),

        details=checks,
    )


# ============================================================
# Fee / Tax / Refund / Adjustment Diagnostics
# ============================================================

def diagnose_settlement_breakdown(
    bank_amount: float,
    settlement: Dict[str, Any],
    *,
    tolerance: float = 1.0,
) -> Optional[Dict[str, Any]]:
    """
    Determine whether a settlement discrepancy can be
    explained by a specific settlement component.

    This is deterministic.

    AI should explain the diagnosis, not create it.
    """

    try:
        gross = float(
            settlement.get(
                "gross_amount",
                0,
            )
        )

        refunds = float(
            settlement.get(
                "refund_amount",
                0,
            )
        )

        fees = float(
            settlement.get(
                "fee_amount",
                0,
            )
        )

        tax = float(
            settlement.get(
                "tax_amount",
                0,
            )
        )

        adjustments = float(
            settlement.get(
                "adjustment_amount",
                0,
            )
        )

        bank_amount = float(
            bank_amount
        )

    except (
        TypeError,
        ValueError,
    ):
        return None

    expected = (
        gross
        - refunds
        - fees
        - tax
        + adjustments
    )

    difference = round(
        bank_amount - expected,
        2,
    )

    if abs(difference) <= tolerance:
        return None

    # --------------------------------------------------------
    # Identify a single-component discrepancy.
    # --------------------------------------------------------

    if abs(
        abs(difference) - abs(fees)
    ) <= tolerance:

        return build_exception(
            FEE_MISMATCH,
            bank_amount=bank_amount,
            expected_amount=expected,
            difference=abs(difference),
            root_cause=(
                "The settlement discrepancy is consistent "
                "with the fee component."
            ),
            details={
                "fee_amount": fees,
                "gross_amount": gross,
                "refund_amount": refunds,
                "tax_amount": tax,
                "adjustment_amount": adjustments,
            },
        )

    if abs(
        abs(difference) - abs(tax)
    ) <= tolerance:

        return build_exception(
            TAX_MISMATCH,
            bank_amount=bank_amount,
            expected_amount=expected,
            difference=abs(difference),
            root_cause=(
                "The settlement discrepancy is consistent "
                "with the tax component."
            ),
            details={
                "tax_amount": tax,
                "gross_amount": gross,
                "refund_amount": refunds,
                "fee_amount": fees,
                "adjustment_amount": adjustments,
            },
        )

    if abs(
        abs(difference) - abs(refunds)
    ) <= tolerance:

        return build_exception(
            REFUND_MISMATCH,
            bank_amount=bank_amount,
            expected_amount=expected,
            difference=abs(difference),
            root_cause=(
                "The settlement discrepancy is consistent "
                "with the refund component."
            ),
            details={
                "refund_amount": refunds,
                "gross_amount": gross,
                "fee_amount": fees,
                "tax_amount": tax,
                "adjustment_amount": adjustments,
            },
        )

    if abs(
        abs(difference) - abs(adjustments)
    ) <= tolerance:

        return build_exception(
            ADJUSTMENT_MISMATCH,
            bank_amount=bank_amount,
            expected_amount=expected,
            difference=abs(difference),
            root_cause=(
                "The settlement discrepancy is consistent "
                "with the adjustment component."
            ),
            details={
                "adjustment_amount": adjustments,
                "gross_amount": gross,
                "refund_amount": refunds,
                "fee_amount": fees,
                "tax_amount": tax,
            },
        )

    return build_exception(
        AMOUNT_MISMATCH,
        bank_amount=bank_amount,
        expected_amount=expected,
        difference=abs(difference),
        root_cause=(
            "Bank credit does not match the calculated "
            "Razorpay settlement amount."
        ),
        details={
            "gross_amount": gross,
            "refund_amount": refunds,
            "fee_amount": fees,
            "tax_amount": tax,
            "adjustment_amount": adjustments,
        },
    )

def detect_duplicate_settlements(
    settlements,
):
    """
    Detect multiple Razorpay settlement records
    sharing the same settlement UTR/reference.
    """

    groups = {}

    for settlement in settlements:

        utr = (
            settlement.get(
                "settlement_utr"
            )
            or settlement.get(
                "settlement_reference"
            )
        )

        if not utr:
            continue

        key = str(
            utr
        ).strip().upper().replace(
            " ",
            "",
        ).replace(
            "-",
            "",
        )

        if not key:
            continue

        groups.setdefault(
            key,
            [],
        ).append(
            settlement
        )

    duplicates = []

    for utr, records in groups.items():

        if len(records) <= 1:
            continue

        duplicates.append(
            build_exception(
                DUPLICATE_SETTLEMENT,
                settlement_id=(
                    records[0].get(
                        "settlement_id"
                    )
                ),
                root_cause=(
                    f"Multiple Razorpay settlement "
                    f"records share the same UTR/reference "
                    f"{utr}."
                ),
                details={
                    "settlement_count": len(
                        records
                    ),
                    "settlement_ids": [
                        (
                            r.get(
                                "settlement_id"
                            )
                            or r.get(
                                "invoice_id"
                            )
                        )
                        for r in records
                    ],
                    "settlement_utr": utr,
                },
            )
        )

    return duplicates

def detect_ambiguous_candidates(
    candidates,
    *,
    score_margin=5,
):
    """
    Detect cases where multiple settlement candidates
    have nearly identical matching scores.
    """

    if not candidates:
        return None

    if len(candidates) < 2:
        return None

    first = candidates[0]
    second = candidates[1]

    first_score = float(
        first.get(
            "score",
            0,
        )
    )

    second_score = float(
        second.get(
            "score",
            0,
        )
    )

    margin = (
        first_score
        - second_score
    )

    if margin >= score_margin:
        return None

    return build_exception(
        AMBIGUOUS_SETTLEMENT,
        settlement_id=(
            first.get(
                "settlement_id"
            )
        ),
        root_cause=(
            "Multiple Razorpay settlements have "
            "similar matching evidence."
        ),
        details={
            "candidate_count": len(
                candidates
            ),
            "top_score": first_score,
            "second_score": second_score,
            "score_margin": margin,
        },
    )