import pandas as pd


def evaluate_predictions(results_df, ground_truth_df):
    """
    Compare matcher predictions against the independent
    ground truth.

    Returns:
        metrics
        evaluation_df
        incorrect_predictions
    """

    evaluation_df = results_df.merge(
        ground_truth_df,
        on="transaction_id",
        how="left"
    )

    # ---------------------------------------------------------
    # 1. Exact invoice correctness
    # ---------------------------------------------------------

    evaluation_df["correct_match"] = (
        evaluation_df["matched_invoice"]
        == evaluation_df["expected_invoice"]
    )

    # ---------------------------------------------------------
    # 2. Actual valid matches
    # ---------------------------------------------------------

    evaluation_df["actual_match"] = (
        evaluation_df["expected_invoice"].notna()
    )

    # ---------------------------------------------------------
    # 3. Predicted matches
    # ---------------------------------------------------------

    evaluation_df["predicted_match"] = (
        evaluation_df["matched_invoice"].notna()
    )

    # ---------------------------------------------------------
    # 4. True positives
    #
    # A true positive means:
    # The system predicted an invoice AND
    # it was the correct invoice.
    # ---------------------------------------------------------

    true_positives = (
        evaluation_df["actual_match"]
        & evaluation_df["predicted_match"]
        & (
            evaluation_df["matched_invoice"]
            == evaluation_df["expected_invoice"]
        )
    ).sum()

    # ---------------------------------------------------------
    # 5. False positives
    #
    # System predicted an invoice but it was wrong.
    # ---------------------------------------------------------

    false_positives = (
        evaluation_df["predicted_match"]
        & (
            evaluation_df["matched_invoice"]
            != evaluation_df["expected_invoice"]
        )
    ).sum()

    # ---------------------------------------------------------
    # 6. False negatives
    #
    # A valid invoice existed but the system failed
    # to identify it correctly.
    # ---------------------------------------------------------

    false_negatives = (
        evaluation_df["actual_match"]
        & (
            ~evaluation_df["predicted_match"]
            |
            (
                evaluation_df["matched_invoice"]
                != evaluation_df["expected_invoice"]
            )
        )
    ).sum()

    # ---------------------------------------------------------
    # 7. Accuracy
    # ---------------------------------------------------------

    total_records = len(evaluation_df)

    correct_predictions = (
        evaluation_df["correct_match"]
    ).sum()

    accuracy = (
        correct_predictions / total_records * 100
        if total_records > 0
        else 0
    )

    # ---------------------------------------------------------
    # 8. Precision
    # ---------------------------------------------------------

    precision = (
        true_positives
        / (true_positives + false_positives)
        * 100
        if (true_positives + false_positives) > 0
        else 0
    )

    # ---------------------------------------------------------
    # 9. Recall
    # ---------------------------------------------------------

    recall = (
        true_positives
        / (true_positives + false_negatives)
        * 100
        if (true_positives + false_negatives) > 0
        else 0
    )

    # ---------------------------------------------------------
    # 10. F1 Score
    # ---------------------------------------------------------

    if precision + recall > 0:

        f1 = (
            2
            * precision
            * recall
            / (precision + recall)
        )

    else:
        f1 = 0

    # ---------------------------------------------------------
    # 11. Auto-resolution rate
    #
    # How many records were automatically classified
    # as MATCHED?
    # ---------------------------------------------------------

    matched_records = (
        results_df["status"] == "MATCHED"
    ).sum()

    auto_resolution_rate = (
        matched_records / total_records * 100
        if total_records > 0
        else 0
    )

    # ---------------------------------------------------------
    # 12. Exception rate
    # ---------------------------------------------------------

    exception_records = (
        results_df["status"] == "EXCEPTION"
    ).sum()

    exception_rate = (
        exception_records / total_records * 100
        if total_records > 0
        else 0
    )

    # ---------------------------------------------------------
    # 13. Warning rate
    # ---------------------------------------------------------

    warning_records = (
        results_df["status"] == "WARNING"
    ).sum()

    warning_rate = (
        warning_records / total_records * 100
        if total_records > 0
        else 0
    )

    # ---------------------------------------------------------
    # 14. Incorrect predictions
    # ---------------------------------------------------------

    incorrect_predictions = evaluation_df[
        ~evaluation_df["correct_match"]
    ].copy()

    # ---------------------------------------------------------
    # 15. Final metrics dictionary
    # ---------------------------------------------------------

    metrics = {
        "accuracy": round(accuracy, 2),
        "precision": round(precision, 2),
        "recall": round(recall, 2),
        "f1": round(f1, 2),

        "auto_resolution_rate": round(
            auto_resolution_rate,
            2
        ),

        "exception_rate": round(
            exception_rate,
            2
        ),

        "warning_rate": round(
            warning_rate,
            2
        ),

        "total_records": total_records,

        "matched_records": int(
            matched_records
        ),

        "warning_records": int(
            warning_records
        ),

        "exception_records": int(
            exception_records
        ),

        "true_positives": int(
            true_positives
        ),

        "false_positives": int(
            false_positives
        ),

        "false_negatives": int(
            false_negatives
        ),
    }

    return (
        metrics,
        evaluation_df,
        incorrect_predictions
    )