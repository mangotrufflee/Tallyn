import sys
from pathlib import Path

import pandas as pd

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from src.matcher import (
    find_best_match,
    find_top_candidates,
    classify_match,
    get_exception_reason,
)

from src.ai_reasoner import (
    build_ai_prompt,
    ask_ai,
    validate_ai_response,
)

from src.verification_guard import (
    verify_ai_match,
    get_final_decision,
    verify_selected_candidate,
)


# ---------------------------------------------------------
# Load data
# ---------------------------------------------------------

bank = pd.read_csv(
    project_root / "data" / "bank.csv",
    parse_dates=["date"],
)
erp = pd.read_csv(
    project_root / "data" / "erp.csv",
    parse_dates=["date"],
)
verification = pd.read_csv(project_root / "data" / "verification.csv")


print("=" * 60)
print("AI FINANCE CONTROLLER")
print("=" * 60)

print(f"Bank records       : {len(bank)}")
print(f"ERP records        : {len(erp)}")
print(f"Ground truth       : {len(verification)}")


# ---------------------------------------------------------
# STEP 1: Deterministic reconciliation
# ---------------------------------------------------------

results = []

for _, bank_row in bank.iterrows():

    (
        best_match,
        score,
        second_best_score,
        scores,
    ) = find_best_match(
        bank_row,
        erp
    )

    status = classify_match(
        score,
        second_best_score,
        best_match,
    )

    invoice_id = (
        best_match["invoice_id"]
        if best_match is not None
        else None
    )

    reason = get_exception_reason(
        bank_row,
        best_match,
        score,
        second_best_score,
    )

    results.append({
        "transaction_id": bank_row["transaction_id"],
        "matched_invoice": invoice_id,
        "match_score": score,
        "status": status,
        "reason": reason,
    })


deterministic_results = pd.DataFrame(results)


# ---------------------------------------------------------
# Deterministic summary
# ---------------------------------------------------------

print("\n" + "=" * 60)
print("DETERMINISTIC RECONCILIATION")
print("=" * 60)

print(
    deterministic_results["status"]
    .value_counts()
)


# ---------------------------------------------------------
# STEP 2: Identify uncertain transactions
# ---------------------------------------------------------

uncertain = deterministic_results[
    deterministic_results["status"].isin(
        ["WARNING", "EXCEPTION"]
    )
]

print("\n" + "=" * 60)
print("AI RECONCILIATION GATE")
print("=" * 60)

print(
    f"Uncertain transactions sent to AI: {len(uncertain)}"
)


# ---------------------------------------------------------
# STEP 3: AI reasoning + verification guard
# ---------------------------------------------------------

def run_ai_on_transaction(bank_row, erp):
    """
    Sends one uncertain transaction to the local LLM.

    The LLM proposes a decision.
    The verification guard independently checks
    the evidence before allowing a MATCHED result.
    """

    # -----------------------------------------------------
    # Find candidate ERP records
    # -----------------------------------------------------

    candidates = find_top_candidates(
        bank_row,
        erp,
        top_n=5
    )

    # -----------------------------------------------------
    # Build AI prompt
    # -----------------------------------------------------

    prompt = build_ai_prompt(
        bank_row,
        candidates
    )

    # -----------------------------------------------------
    # Ask local AI
    # -----------------------------------------------------

    raw_response = ask_ai(
        prompt
    )

    # -----------------------------------------------------
    # Validate AI response
    # -----------------------------------------------------

    validation = validate_ai_response(
        raw_response
    )

    if not validation["valid"]:

        return {
            "ai_decision": "EXCEPTION",
            "ai_invoice": None,
            "ai_confidence": 0,
            "ai_reason": validation["error"],
            "ai_risk": "HIGH",
            "verification_decision": "EXCEPTION",
            "verification_reason": "Invalid AI response",
        }

    result = validation["result"]

    ai_decision = result["decision"]
    ai_invoice = result["selected_invoice"]

    # -----------------------------------------------------
    # CASE 1:
    # AI did not select an invoice
    # -----------------------------------------------------

    if not ai_invoice:

        # No candidates exist at all.
        if len(candidates) == 0:

            verification_decision = "EXCEPTION"
            verification_reason = (
                "No ERP candidates available"
            )

        # Candidates exist, but AI wants human review.
        else:

            verification_decision = "REVIEW"
            verification_reason = (
                "AI could not confidently select a candidate"
            )

        return {
            "ai_decision": ai_decision,
            "ai_invoice": None,
            "ai_confidence": result["confidence"],
            "ai_reason": result["reason"],
            "ai_risk": result["risk"],
            "verification_decision": verification_decision,
            "verification_reason": verification_reason,
        }

    # -----------------------------------------------------
    # CASE 2:
    # AI selected an invoice
    # -----------------------------------------------------

    # Make sure the AI-selected invoice was actually
    # present in the candidate set we gave it.

    candidate_is_valid = verify_selected_candidate(
        ai_invoice,
        candidates
    )

    if not candidate_is_valid:

        return {
            "ai_decision": ai_decision,
            "ai_invoice": ai_invoice,
            "ai_confidence": result["confidence"],
            "ai_reason": result["reason"],
            "ai_risk": "HIGH",
            "verification_decision": "EXCEPTION",
            "verification_reason": (
                "AI selected an invoice outside "
                "the candidate set"
            ),
        }

    # -----------------------------------------------------
    # Find the selected ERP record
    # -----------------------------------------------------

    selected_erp = None

    matches = erp[
        erp["invoice_id"]
        .astype(str)
        .str.strip()
        == str(ai_invoice).strip()
    ]

    if not matches.empty:
        selected_erp = matches.iloc[0]

    # -----------------------------------------------------
    # Independently verify AI's selection
    # -----------------------------------------------------

    verification_checks = verify_ai_match(
        bank_row,
        selected_erp
    )

    # -----------------------------------------------------
    # Convert verification evidence into
    # final business decision
    # -----------------------------------------------------

    verification_decision = get_final_decision(
        verification_checks
    )

    return {
        "ai_decision": ai_decision,
        "ai_invoice": ai_invoice,
        "ai_confidence": result["confidence"],
        "ai_reason": result["reason"],
        "ai_risk": result["risk"],
        "verification_decision": verification_decision,
        "verification_checks": str(
            verification_checks
        ),
    }


# ---------------------------------------------------------
# Run AI on all uncertain transactions
# ---------------------------------------------------------

ai_results = []

for _, row in uncertain.iterrows():

    transaction_id = row["transaction_id"]

    bank_row = bank[
        bank["transaction_id"].astype(str)
        == str(transaction_id)
    ].iloc[0]

    ai_result = run_ai_on_transaction(
        bank_row,
        erp
    )

    ai_results.append({
        "transaction_id": transaction_id,
        **ai_result,
    })

    print("\n" + "-" * 60)
    print(f"Transaction: {transaction_id}")

    print(
        f"AI Decision: {ai_result['ai_decision']}"
    )

    print(
        f"AI Invoice : {ai_result['ai_invoice']}"
    )

    print(
        f"Confidence : {ai_result['ai_confidence']}"
    )

    print(
        f"Risk       : {ai_result['ai_risk']}"
    )

    print(
        f"Reason     : {ai_result['ai_reason']}"
    )

    print(
        f"Verified   : {ai_result['verification_decision']}"
    )

    if "verification_reason" in ai_result:

        print(
            f"Verification reason: "
            f"{ai_result['verification_reason']}"
        )

    if "verification_checks" in ai_result:

        print(
            f"Checks     : "
            f"{ai_result['verification_checks']}"
        )


# ---------------------------------------------------------
# Convert AI results to DataFrame
# ---------------------------------------------------------

ai_results_df = pd.DataFrame(
    ai_results
)


# ---------------------------------------------------------
# Save AI results
# ---------------------------------------------------------

ai_results_df.to_csv(
    project_root / "data" / "ai_results.csv",
    index=False
)


# ---------------------------------------------------------
# STEP 4: AI + Verification summary
# ---------------------------------------------------------

print("\n" + "=" * 60)
print("AI RESULTS")
print("=" * 60)

if not ai_results_df.empty:

    print(
        ai_results_df["ai_decision"]
        .value_counts()
    )


print("\n" + "=" * 60)
print("VERIFICATION GUARD RESULTS")
print("=" * 60)

if not ai_results_df.empty:

    print(
        ai_results_df[
            "verification_decision"
        ].value_counts()
    )


# ---------------------------------------------------------
# STEP 5: Show AI → Guard transitions
# ---------------------------------------------------------

print("\n" + "=" * 60)
print("AI → VERIFICATION TRANSITIONS")
print("=" * 60)

if not ai_results_df.empty:

    transitions = pd.crosstab(
        ai_results_df["ai_decision"],
        ai_results_df["verification_decision"]
    )

    print(transitions)


# ---------------------------------------------------------
# STEP 6: Final decision summary
# ---------------------------------------------------------

print("\n" + "=" * 60)
print("FINAL SUMMARY")
print("=" * 60)

print(
    f"Total transactions       : {len(bank)}"
)

print(
    f"Deterministic uncertain  : {len(uncertain)}"
)

print(
    f"AI processed             : {len(ai_results_df)}"
)

if not ai_results_df.empty:

    matched_count = (
        ai_results_df[
            ai_results_df["verification_decision"]
            == "MATCHED"
        ].shape[0]
    )

    review_count = (
        ai_results_df[
            ai_results_df["verification_decision"]
            == "REVIEW"
        ].shape[0]
    )

    exception_count = (
        ai_results_df[
            ai_results_df["verification_decision"]
            == "EXCEPTION"
        ].shape[0]
    )

    print(
        f"Verified MATCHED         : {matched_count}"
    )

    print(
        f"Sent for REVIEW          : {review_count}"
    )

    print(
        f"EXCEPTION                : {exception_count}"
    )


print("\nPipeline completed.")