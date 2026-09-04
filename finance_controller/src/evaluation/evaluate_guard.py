import sys
from pathlib import Path

import pandas as pd

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from src.reconciliation.matcher import (
    find_best_match,
    classify_match,
)


# ============================================================
# LOAD DATA
# ============================================================

bank = pd.read_csv(
    project_root / "data" / "bank.csv",
    parse_dates=["date"],
)
erp = pd.read_csv(
    project_root / "data" / "erp.csv",
    parse_dates=["date"],
)
ground_truth = pd.read_csv(project_root / "data" / "verification.csv")
ai_results = pd.read_csv(
    project_root / "data" / "results" / "ai_results.csv"
)


print("=" * 70)
print("AI FINANCE CONTROLLER — VERIFICATION GUARD EVALUATION")
print("=" * 70)

print(f"Bank records       : {len(bank)}")
print(f"ERP records        : {len(erp)}")
print(f"Ground truth       : {len(ground_truth)}")
print(f"AI results         : {len(ai_results)}")


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def normalize_invoice(invoice):
    """
    Removes the synthetic _DUP suffix so that duplicate ERP
    records are treated as the same underlying invoice.
    """

    if pd.isna(invoice):
        return None

    invoice = str(invoice).strip()

    if invoice.endswith("_DUP"):
        invoice = invoice[:-4]

    return invoice


def invoice_correct(predicted, expected):
    """
    Checks whether two invoice IDs represent the same
    underlying invoice.
    """

    predicted = normalize_invoice(predicted)
    expected = normalize_invoice(expected)

    if predicted is None or expected is None:
        return False

    return predicted == expected


# ============================================================
# STEP 1 — RECREATE DETERMINISTIC RESULTS
# ============================================================

deterministic_results = []

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

    if best_match is None:
        invoice = None
    else:
        invoice = best_match["invoice_id"]

    deterministic_results.append({
        "transaction_id": bank_row["transaction_id"],
        "deterministic_invoice": invoice,
        "deterministic_score": score,
        "deterministic_status": status,
    })


deterministic_df = pd.DataFrame(
    deterministic_results
)


# ============================================================
# STEP 2 — MERGE GROUND TRUTH
# ============================================================

evaluation = deterministic_df.merge(
    ground_truth[
        ["transaction_id", "expected_invoice"]
    ],
    on="transaction_id",
    how="left"
)


# ============================================================
# STEP 3 — MERGE AI + GUARD RESULTS
# ============================================================

evaluation = evaluation.merge(
    ai_results[
        [
            "transaction_id",
            "ai_decision",
            "ai_invoice",
            "ai_confidence",
            "ai_risk",
            "verification_decision",
        ]
    ],
    on="transaction_id",
    how="left"
)


# ============================================================
# STEP 4 — DETERMINISTIC ACCURACY
# ============================================================

evaluation["deterministic_correct"] = evaluation.apply(
    lambda row: invoice_correct(
        row["deterministic_invoice"],
        row["expected_invoice"]
    ),
    axis=1
)

deterministic_correct = (
    evaluation["deterministic_correct"].sum()
)

deterministic_accuracy = (
    deterministic_correct / len(evaluation)
) * 100


# ============================================================
# STEP 5 — AI MATCH ACCURACY
# ============================================================

ai_match_rows = evaluation[
    evaluation["ai_decision"] == "MATCH"
].copy()

if len(ai_match_rows) > 0:

    ai_match_rows["ai_correct"] = ai_match_rows.apply(
        lambda row: invoice_correct(
            row["ai_invoice"],
            row["expected_invoice"]
        ),
        axis=1
    )

    ai_correct = ai_match_rows["ai_correct"].sum()

    ai_match_accuracy = (
        ai_correct / len(ai_match_rows)
    ) * 100

else:

    ai_correct = 0
    ai_match_accuracy = 0


# ============================================================
# STEP 6 — VERIFIED MATCH ACCURACY
# ============================================================

verified_match_rows = evaluation[
    evaluation["verification_decision"] == "MATCHED"
].copy()

if len(verified_match_rows) > 0:

    verified_match_rows["verified_correct"] = (
        verified_match_rows.apply(
            lambda row: invoice_correct(
                row["ai_invoice"],
                row["expected_invoice"]
            ),
            axis=1
        )
    )

    verified_correct = (
        verified_match_rows["verified_correct"].sum()
    )

    verified_accuracy = (
        verified_correct /
        len(verified_match_rows)
    ) * 100

else:

    verified_correct = 0
    verified_accuracy = 0


# ============================================================
# STEP 7 — UNSAFE AI MATCHES
# ============================================================

unsafe_ai_matches = evaluation[
    (evaluation["ai_decision"] == "MATCH")
    &
    (evaluation["verification_decision"] != "MATCHED")
].copy()

unsafe_ai_match_count = len(
    unsafe_ai_matches
)


# ============================================================
# STEP 8 — AI MATCHES BLOCKED BY GUARD
# ============================================================

blocked_correct = 0
blocked_wrong = 0

if len(unsafe_ai_matches) > 0:

    for _, row in unsafe_ai_matches.iterrows():

        if invoice_correct(
            row["ai_invoice"],
            row["expected_invoice"]
        ):
            blocked_correct += 1
        else:
            blocked_wrong += 1


# ============================================================
# STEP 9 — FINAL DECISION DISTRIBUTION
# ============================================================

final_decisions = evaluation[
    evaluation["verification_decision"].notna()
]["verification_decision"].value_counts()


# ============================================================
# STEP 10 — VERIFIED MATCH SAFETY
# ============================================================

if len(verified_match_rows) > 0:

    unsafe_verified_matches = (
        len(verified_match_rows)
        - verified_correct
    )

else:

    unsafe_verified_matches = 0


# ============================================================
# STEP 11 — PRINT RESULTS
# ============================================================

print("\n" + "=" * 70)
print("1. DETERMINISTIC BASELINE")
print("=" * 70)

print(
    f"Total transactions       : {len(evaluation)}"
)

print(
    f"Correct invoice matches  : {deterministic_correct}"
)

print(
    f"Invoice accuracy         : "
    f"{deterministic_accuracy:.2f}%"
)

print("\nDecision distribution:")

print(
    evaluation["deterministic_status"]
    .value_counts()
)


print("\n" + "=" * 70)
print("2. AI RECOMMENDATIONS")
print("=" * 70)

print(
    f"AI MATCH recommendations : {len(ai_match_rows)}"
)

print(
    f"Correct AI matches       : {ai_correct}"
)

print(
    f"AI match accuracy        : "
    f"{ai_match_accuracy:.2f}%"
)


print("\n" + "=" * 70)
print("3. VERIFICATION GUARD")
print("=" * 70)

print(
    f"Verified MATCHED         : "
    f"{len(verified_match_rows)}"
)

print(
    f"Correct verified matches : "
    f"{verified_correct}"
)

print(
    f"Verified match accuracy  : "
    f"{verified_accuracy:.2f}%"
)

print(
    f"Incorrect verified MATCH : "
    f"{unsafe_verified_matches}"
)


print("\nVerification decisions:")

print(
    final_decisions
)


print("\n" + "=" * 70)
print("4. AI → GUARD SAFETY")
print("=" * 70)

print(
    f"AI MATCH recommendations : "
    f"{len(ai_match_rows)}"
)

print(
    f"Guard-approved MATCH     : "
    f"{len(verified_match_rows)}"
)

print(
    f"AI MATCHes blocked       : "
    f"{unsafe_ai_match_count}"
)

print(
    f"Blocked but actually correct : "
    f"{blocked_correct}"
)

print(
    f"Blocked incorrect AI matches : "
    f"{blocked_wrong}"
)


if len(ai_match_rows) > 0:

    guard_block_rate = (
        unsafe_ai_match_count /
        len(ai_match_rows)
    ) * 100

else:

    guard_block_rate = 0


print(
    f"Guard block rate         : "
    f"{guard_block_rate:.2f}%"
)


# ============================================================
# STEP 12 — SHOW BLOCKED AI MATCHES
# ============================================================

print("\n" + "=" * 70)
print("5. AI MATCHES BLOCKED BY VERIFICATION")
print("=" * 70)

if len(unsafe_ai_matches) == 0:

    print("No AI MATCHes were blocked.")

else:

    blocked_display = unsafe_ai_matches[
        [
            "transaction_id",
            "ai_invoice",
            "expected_invoice",
            "ai_confidence",
            "ai_risk",
            "verification_decision",
        ]
    ]

    print(
        blocked_display.to_string(
            index=False
        )
    )


# ============================================================
# STEP 13 — SHOW VERIFIED MATCHES
# ============================================================

print("\n" + "=" * 70)
print("6. VERIFIED AUTOMATIC MATCHES")
print("=" * 70)

if len(verified_match_rows) == 0:

    print("No verified automatic matches.")

else:

    verified_display = verified_match_rows[
        [
            "transaction_id",
            "ai_invoice",
            "expected_invoice",
            "ai_confidence",
            "ai_risk",
        ]
    ]

    print(
        verified_display.to_string(
            index=False
        )
    )


# ============================================================
# STEP 14 — SAVE COMPLETE EVALUATION
# ============================================================

evaluation.to_csv(
    project_root / "data" / "guard_evaluation.csv",
    index=False
)


print("\n" + "=" * 70)
print("EVALUATION COMPLETE")
print("=" * 70)

print(
    "Detailed results saved to:"
)

print(
    "data/results/guard_evaluation.csv"
)