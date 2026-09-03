import pandas as pd


def calculate_accuracy(
    predictions,
    ground_truth,
    prediction_column
):
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
    # 1. LOAD RESULTS
    # --------------------------------------------------

    ai_results = pd.read_csv(
        "data/ai_results.csv"
    )

    ground_truth = pd.read_csv(
        "data/verification.csv"
    )

    # --------------------------------------------------
    # 2. DETERMINISTIC EVALUATION
    # --------------------------------------------------

    deterministic_accuracy, comparison = (
        calculate_accuracy(
            ai_results,
            ground_truth,
            "deterministic_invoice"
        )
    )

    # --------------------------------------------------
    # 3. AI EVALUATION
    # --------------------------------------------------

    ai_accuracy, comparison = (
        calculate_accuracy(
            ai_results,
            ground_truth,
            "ai_invoice"
        )
    )

    # --------------------------------------------------
    # 4. PRINT RESULTS
    # --------------------------------------------------

    print()
    print(
        f"Transactions evaluated : "
        f"{len(ai_results)}"
    )

    print()
    print(
        f"Deterministic accuracy  : "
        f"{deterministic_accuracy:.2f}%"
    )

    print(
        f"AI accuracy             : "
        f"{ai_accuracy:.2f}%"
    )

    print()

    improvement = (
        ai_accuracy
        - deterministic_accuracy
    )

    print(
        f"Accuracy improvement    : "
        f"{improvement:+.2f} percentage points"
    )

    # --------------------------------------------------
    # 5. SHOW TRANSACTION-LEVEL RESULTS
    # --------------------------------------------------

    print()
    print("=" * 70)
    print("TRANSACTION-LEVEL COMPARISON")
    print("=" * 70)

    for _, row in comparison.iterrows():

        print()
        print(
            f"Transaction: "
            f"{row['transaction_id']}"
        )

        print(
            f"Expected invoice      : "
            f"{row['expected_invoice']}"
        )

        print(
            f"Deterministic invoice : "
            f"{row['deterministic_invoice']}"
        )

        print(
            f"AI invoice            : "
            f"{row['ai_invoice']}"
        )

        print(
            f"AI decision           : "
            f"{row['ai_decision']}"
        )

        print(
            f"AI confidence         : "
            f"{row['ai_confidence']}"
        )

        print(
            f"AI risk               : "
            f"{row['ai_risk']}"
        )

        deterministic_correct = (
            row["deterministic_invoice"]
            == row["expected_invoice"]
        )

        ai_correct = (
            row["ai_invoice"]
            == row["expected_invoice"]
        )

        print(
            f"Deterministic correct : "
            f"{deterministic_correct}"
        )

        print(
            f"AI correct            : "
            f"{ai_correct}"
        )

    # --------------------------------------------------
    # 6. SAVE EVALUATION
    # --------------------------------------------------

    comparison.to_csv(
        "data/ai_evaluation.csv",
        index=False
    )

    print()
    print(
        "Detailed evaluation saved to "
        "data/ai_evaluation.csv"
    )

    print()
    print("=" * 70)


if __name__ == "__main__":
    main()