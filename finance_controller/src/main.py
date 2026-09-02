import time
import pandas as pd

from matcher import reconcile
from evaluator import evaluate_predictions


# ============================================================
# 1. LOAD DATA
# ============================================================

bank = pd.read_csv(
    "data/bank.csv"
)

erp = pd.read_csv(
    "data/erp.csv"
)

ground_truth = pd.read_csv(
    "data/verification.csv"
)


# ============================================================
# 2. CONVERT DATES
# ============================================================

bank["date"] = pd.to_datetime(
    bank["date"]
)

erp["date"] = pd.to_datetime(
    erp["date"]
)


# ============================================================
# 3. START RECONCILIATION
# ============================================================

print()
print("Running reconciliation...")
print()


start_time = time.perf_counter()


results_df = reconcile(
    bank,
    erp
)


end_time = time.perf_counter()


# ============================================================
# 4. CALCULATE PROCESSING PERFORMANCE
# ============================================================

processing_time = (
    end_time - start_time
)

records_processed = len(bank)

if processing_time > 0:

    throughput = (
        records_processed
        / processing_time
    )

else:

    throughput = 0


# ============================================================
# 5. EVALUATE RESULTS
# ============================================================

(
    metrics,
    evaluation_df,
    incorrect_predictions
) = evaluate_predictions(
    results_df,
    ground_truth
)


# ============================================================
# 6. DISPLAY RECONCILIATION RESULTS
# ============================================================

print("=" * 80)
print("RECONCILIATION RESULTS")
print("=" * 80)

print(
    results_df[
        [
            "transaction_id",
            "matched_invoice",
            "confidence",
            "status",
            "reason"
        ]
    ].to_string(index=False)
)


# ============================================================
# 7. DISPLAY PERFORMANCE REPORT
# ============================================================

print()
print("=" * 80)
print("PERFORMANCE REPORT")
print("=" * 80)

print(
    f"Records processed: "
    f"{metrics['total_records']}"
)

print(
    f"Matched: "
    f"{metrics['matched_records']}"
)

print(
    f"Warnings: "
    f"{metrics['warning_records']}"
)

print(
    f"Exceptions: "
    f"{metrics['exception_records']}"
)

print()

print(
    f"Accuracy: "
    f"{metrics['accuracy']}%"
)

print(
    f"Precision: "
    f"{metrics['precision']}%"
)

print(
    f"Recall: "
    f"{metrics['recall']}%"
)

print(
    f"F1 Score: "
    f"{metrics['f1']}%"
)

print()

print(
    f"Auto-resolution rate: "
    f"{metrics['auto_resolution_rate']}%"
)

print(
    f"Warning rate: "
    f"{metrics['warning_rate']}%"
)

print(
    f"Exception rate: "
    f"{metrics['exception_rate']}%"
)

print()

print(
    f"True positives: "
    f"{metrics['true_positives']}"
)

print(
    f"False positives: "
    f"{metrics['false_positives']}"
)

print(
    f"False negatives: "
    f"{metrics['false_negatives']}"
)

print()

print(
    f"Processing time: "
    f"{processing_time:.4f} seconds"
)

print(
    f"Throughput: "
    f"{throughput:.2f} records/second"
)


# ============================================================
# 8. DISPLAY INCORRECT PREDICTIONS
# ============================================================

print()
print("=" * 80)
print("INCORRECT PREDICTIONS / EXCEPTIONS")
print("=" * 80)


if len(incorrect_predictions) == 0:

    print(
        "No incorrect predictions."
    )

else:

    print(
        incorrect_predictions[
            [
                "transaction_id",
                "matched_invoice",
                "expected_invoice",
                "confidence",
                "status",
                "reason"
            ]
        ].to_string(index=False)
    )


# ============================================================
# 9. FINISH
# ============================================================

print()
print("=" * 80)
print("RECONCILIATION COMPLETE")
print("=" * 80)