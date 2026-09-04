import sys
from pathlib import Path

import pandas as pd

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from backend.app.reconciliation.matcher import find_best_match, classify_match


def run_deterministic_reconciliation(bank, erp):
    """
    Run the deterministic matcher across all bank transactions.
    """

    results = []

    for _, bank_row in bank.iterrows():

        best_match, best_score, second_best_score, score_details = (
            find_best_match(bank_row, erp)
        )

        decision = classify_match(
            best_score,
            second_best_score,
            best_match
        )

        if best_match is not None:
            invoice = best_match["invoice_id"]
        else:
            invoice = None

        results.append({
            "transaction_id": bank_row["transaction_id"],
            "deterministic_invoice": invoice,
            "deterministic_decision": decision,
            "deterministic_score": best_score
        })

    return pd.DataFrame(results)


def calculate_accuracy(predictions, ground_truth, prediction_column):
    """
    Calculate invoice-selection accuracy.

    A prediction is correct when the predicted invoice
    matches the expected invoice.
    """

    merged = predictions.merge(
        ground_truth,
        on="transaction_id",
        how="left"
    )

    merged["correct"] = (
        merged[prediction_column]
        == merged["expected_invoice"]
    )

    accuracy = merged["correct"].mean() * 100

    return accuracy, merged


def main():

    print()
    print("=" * 70)
    print("AI RECONCILIATION EVALUATION")
    print("=" * 70)

    # --------------------------------------------------
    # 1. LOAD DATA
    # --------------------------------------------------

    print()
    print("Loading data...")

    bank = pd.read_csv(project_root / "data" / "raw" / "bank.csv")
    erp = pd.read_csv(project_root / "data" / "raw" / "erp.csv")
    ground_truth = pd.read_csv(project_root / "data" / "raw" / "verification.csv")

    bank["date"] = pd.to_datetime(bank["date"])
    erp["date"] = pd.to_datetime(erp["date"])

    print(f"Bank records       : {len(bank)}")
    print(f"ERP records        : {len(erp)}")
    print(f"Verification rows  : {len(ground_truth)}")

    # --------------------------------------------------
    # 2. RUN DETERMINISTIC MATCHING ON ALL 500
    # --------------------------------------------------

    print()
    print("Running deterministic reconciliation...")

    deterministic_results = run_deterministic_reconciliation(
        bank,
        erp
    )

    print("Deterministic reconciliation completed.")

    # --------------------------------------------------
    # 3. EVALUATE DETERMINISTIC RESULTS
    # --------------------------------------------------

    deterministic_accuracy, comparison = (
        calculate_accuracy(
            deterministic_results,
            ground_truth,
            "deterministic_invoice"
        )
    )

    # --------------------------------------------------
    # 4. LOAD AI RESULTS
    # --------------------------------------------------

    try:
        ai_results = pd.read_csv(
            project_root / "data" / "results" / "ai_results.csv"
        )

        comparison = comparison.merge(
            ai_results[
                [
                    "transaction_id",
                    "ai_decision",
                    "ai_invoice",
                    "ai_confidence",
                    "ai_risk",
                    "ai_reason"
                ]
            ],
            on="transaction_id",
            how="left"
        )

    except FileNotFoundError:

        print()
        print("No AI results found.")

        ai_results = pd.DataFrame()

    # --------------------------------------------------
    # 5. AI EVALUATION
    # --------------------------------------------------

    if len(ai_results) > 0:

        ai_evaluated = comparison[
            comparison["ai_decision"].notna()
        ].copy()

        if len(ai_evaluated) > 0:

            ai_evaluated["ai_correct"] = (
                ai_evaluated["ai_invoice"]
                == ai_evaluated["expected_invoice"]
            )

            ai_accuracy = (
                ai_evaluated["ai_correct"].mean()
                * 100
            )

        else:
            ai_accuracy = 0

    else:

        ai_evaluated = pd.DataFrame()
        ai_accuracy = 0

    # --------------------------------------------------
    # 6. PRINT OVERALL RESULTS
    # --------------------------------------------------

    print()
    print("=" * 70)
    print("DETERMINISTIC BASELINE")
    print("=" * 70)

    print()
    print(
        f"Transactions evaluated : "
        f"{len(comparison)}"
    )

    print(
        f"Correct matches        : "
        f"{comparison['correct'].sum()}"
    )

    print(
        f"Accuracy               : "
        f"{deterministic_accuracy:.2f}%"
    )

    # --------------------------------------------------
    # 7. DETERMINISTIC DECISION COUNTS
    # --------------------------------------------------

    print()
    print("DETERMINISTIC DECISIONS")

    decision_counts = (
        comparison["deterministic_decision"]
        .value_counts()
    )

    for decision, count in decision_counts.items():

        print(
            f"{decision:<20}: {count}"
        )

    # --------------------------------------------------
    # 8. AI RESULTS
    # --------------------------------------------------

    print()
    print("=" * 70)
    print("AI EVALUATION")
    print("=" * 70)

    print()
    print(
        f"AI transactions evaluated : "
        f"{len(ai_evaluated)}"
    )

    if len(ai_evaluated) > 0:

        print(
            f"Correct AI matches        : "
            f"{ai_evaluated['ai_correct'].sum()}"
        )

        print(
            f"AI accuracy               : "
            f"{ai_accuracy:.2f}%"
        )

    else:

        print("No AI transactions available.")

    # --------------------------------------------------
    # 9. AI DECISION COUNTS
    # --------------------------------------------------

    if len(ai_evaluated) > 0:

        print()
        print("AI DECISIONS")

        ai_decision_counts = (
            ai_evaluated["ai_decision"]
            .value_counts()
        )

        for decision, count in (
            ai_decision_counts.items()
        ):

            print(
                f"{decision:<20}: {count}"
            )

    # --------------------------------------------------
    # 10. SAVE FULL EVALUATION
    # --------------------------------------------------

    comparison.to_csv(
        project_root / "data" / "results" / "ai_evaluation.csv",
        index=False
    )

    print()
    print(
        "Detailed evaluation saved to "
        "data/results/ai_evaluation.csv"
    )

    print()
    print("=" * 70)
    print("EVALUATION COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()