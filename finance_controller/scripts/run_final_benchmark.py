import sys
import time
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.reconciliation.matcher import find_best_match
from backend.app.reconciliation.verification_guard import (
    verify_ai_match,
    get_final_decision,
)


BANK_PATH = PROJECT_ROOT / "data" / "raw" / "bank.csv"
ERP_PATH = PROJECT_ROOT / "data" / "raw" / "erp.csv"
GROUND_TRUTH_PATH = (
    PROJECT_ROOT / "data" / "raw" / "verification.csv"
)


# ============================================================
# HELPERS
# ============================================================

def normalize_id(value):
    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except Exception:
        pass

    return str(value).strip().lower()


def safe_float(value):
    try:
        if value is None or pd.isna(value):
            return None

        return float(value)

    except (TypeError, ValueError):
        return None


def normalize_text(value):
    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass

    return (
        str(value)
        .strip()
        .lower()
        .replace(" ", "")
        .replace("-", "")
        .replace("_", "")
    )


def load_data():

    bank_df = pd.read_csv(BANK_PATH)
    erp_df = pd.read_csv(ERP_PATH)
    ground_truth_df = pd.read_csv(
        GROUND_TRUTH_PATH
    )

    bank_df["date"] = pd.to_datetime(
        bank_df["date"]
    )

    erp_df["date"] = pd.to_datetime(
        erp_df["date"]
    )

    return (
        bank_df,
        erp_df,
        ground_truth_df,
    )


def build_ground_truth(ground_truth_df):

    mapping = {}

    for _, row in ground_truth_df.iterrows():

        bank_id = normalize_id(
            row.get("transaction_id")
        )

        expected_invoice = row.get(
            "expected_invoice"
        )

        if bank_id:
            mapping[bank_id] = expected_invoice

    return mapping


# ============================================================
# DUPLICATE DETECTION
# ============================================================

def candidate_signature(row):

    invoice_id = normalize_text(
        row.get("invoice_id")
    )

    amount = safe_float(
        row.get("amount")
    )

    vendor = normalize_text(
        row.get("vendor")
    )

    date = row.get("date")

    try:
        date = str(
            pd.to_datetime(date).date()
        )
    except Exception:
        date = normalize_text(date)

    reference = normalize_text(
        row.get("reference")
    )

    return (
        invoice_id,
        amount,
        vendor,
        date,
        reference,
    )


def equivalent_candidate_signature(row):

    """
    Evidence signature excluding invoice_id.

    If two ERP records have identical financial
    evidence, the matcher must not automatically
    choose one of them.
    """

    amount = safe_float(
        row.get("amount")
    )

    vendor = normalize_text(
        row.get("vendor")
    )

    date = row.get("date")

    try:
        date = str(
            pd.to_datetime(date).date()
        )
    except Exception:
        date = normalize_text(date)

    reference = normalize_text(
        row.get("reference")
    )

    return (
        amount,
        vendor,
        date,
        reference,
    )


def has_duplicate_candidate(
    bank_row,
    selected_match,
    erp_df,
):

    if selected_match is None:
        return False

    selected_signature = (
        equivalent_candidate_signature(
            selected_match
        )
    )

    duplicate_count = 0

    for _, erp_row in erp_df.iterrows():

        if (
            equivalent_candidate_signature(
                erp_row
            )
            == selected_signature
        ):
            duplicate_count += 1

    return duplicate_count > 1


# ============================================================
# DETERMINISTIC MATCHING
# ============================================================

def deterministic_match(
    bank_row,
    erp_df,
):

    (
        best_match,
        best_score,
        second_score,
        scores,
    ) = find_best_match(
        bank_row,
        erp_df,
    )

    if best_match is None:

        return {
            "match": None,
            "score": best_score,
            "second_score": second_score,
            "status": "EXCEPTION",
            "duplicate": False,
        }

    margin = (
        best_score - second_score
    )

    duplicate = has_duplicate_candidate(
        bank_row,
        best_match,
        erp_df,
    )

    # --------------------------------------------------------
    # DUPLICATE CANDIDATE
    # --------------------------------------------------------

    if duplicate:

        return {
            "match": best_match,
            "score": best_score,
            "second_score": second_score,
            "status": "UNCERTAIN",
            "duplicate": True,
        }

    # --------------------------------------------------------
    # NORMAL CLASSIFICATION
    # --------------------------------------------------------

    if (
        best_score >= 90
        and margin >= 5
    ):

        status = "MATCHED"

    elif best_score >= 70:

        status = "UNCERTAIN"

    else:

        status = "EXCEPTION"

    return {
        "match": best_match,
        "score": best_score,
        "second_score": second_score,
        "status": status,
        "duplicate": False,
    }


# ============================================================
# MAIN BENCHMARK
# ============================================================

def run_final_benchmark():

    print("\n" + "=" * 75)
    print(
        "AI FINANCE CONTROLLER — FINAL BENCHMARK"
    )
    print("=" * 75)

    # --------------------------------------------------------
    # LOAD
    # --------------------------------------------------------

    bank_df, erp_df, ground_truth_df = (
        load_data()
    )

    ground_truth = build_ground_truth(
        ground_truth_df
    )

    total = len(bank_df)

    print(
        f"\nRecords: {total}"
    )

    if total < 50:

        raise ValueError(
            "Benchmark requires at least "
            "50 synthetic records."
        )

    # --------------------------------------------------------
    # TOTAL END-TO-END TIMER
    # --------------------------------------------------------

    benchmark_start = time.perf_counter()

    # --------------------------------------------------------
    # PHASE 1 — DETERMINISTIC MATCHING
    # --------------------------------------------------------

    deterministic_results = []

    deterministic_start = (
        time.perf_counter()
    )

    for _, bank_row in bank_df.iterrows():

        result = deterministic_match(
            bank_row,
            erp_df,
        )

        deterministic_results.append(
            {
                "bank_row": bank_row,
                **result,
            }
        )

    deterministic_time = (
        time.perf_counter()
        - deterministic_start
    )

    # --------------------------------------------------------
    # PHASE 2 — VERIFICATION
    # --------------------------------------------------------

    final_results = []

    uncertain_count = 0
    guard_verified_count = 0

    for item in deterministic_results:

        bank_row = item["bank_row"]
        match = item["match"]

        bank_id = normalize_id(
            bank_row[
                "transaction_id"
            ]
        )

        expected_invoice = (
            ground_truth.get(
                bank_id
            )
        )

        guard_checks = {}

        # ====================================================
        # NO CANDIDATE
        # ====================================================

        if match is None:

            final_status = "EXCEPTION"
            resolution = "NO_CANDIDATE"

            matched_invoice = None

        # ====================================================
        # DUPLICATE CANDIDATE
        # ====================================================

        elif item["duplicate"]:

            uncertain_count += 1

            final_status = "REVIEW"
            resolution = (
                "DUPLICATE_CANDIDATE"
            )

            matched_invoice = match[
                "invoice_id"
            ]

        # ====================================================
        # HIGH-CONFIDENCE NORMAL MATCH
        # ====================================================

        elif item["status"] == "MATCHED":

            final_status = "MATCHED"
            resolution = (
                "DETERMINISTIC_MATCH"
            )

            matched_invoice = match[
                "invoice_id"
            ]

        # ====================================================
        # UNCERTAIN
        # ====================================================

        else:

            uncertain_count += 1

            matched_invoice = match[
                "invoice_id"
            ]

            guard_checks = (
                verify_ai_match(
                    bank_row,
                    match,
                )
            )

            guard_decision = (
                get_final_decision(
                    guard_checks
                )
            )

            if guard_decision == "MATCHED":

                final_status = "MATCHED"

                resolution = (
                    "GUARD_VERIFIED"
                )

                guard_verified_count += 1

            else:

                final_status = "REVIEW"

                resolution = (
                    "HUMAN_REVIEW"
                )

        # ----------------------------------------------------
        # CORRECTNESS
        # ----------------------------------------------------

        correct = (
            normalize_id(
                matched_invoice
            )
            == normalize_id(
                expected_invoice
            )
        )

        final_results.append(
            {
                "transaction_id": bank_id,
                "expected_invoice": (
                    expected_invoice
                ),
                "matched_invoice": (
                    matched_invoice
                ),
                "deterministic_score": (
                    item["score"]
                ),
                "second_best_score": (
                    item["second_score"]
                ),
                "deterministic_status": (
                    item["status"]
                ),
                "duplicate_candidate": (
                    item["duplicate"]
                ),
                "final_status": (
                    final_status
                ),
                "resolution": (
                    resolution
                ),
                "correct": correct,
                "guard_checks": (
                    guard_checks
                ),
            }
        )

    # --------------------------------------------------------
    # END-TO-END TIME
    # --------------------------------------------------------

    total_processing_time = (
        time.perf_counter()
        - benchmark_start
    )

    results_df = pd.DataFrame(
        final_results
    )

    # ========================================================
    # METRICS
    # ========================================================

    total = len(results_df)

    correct = int(
        results_df["correct"].sum()
    )

    matched = int(
        (
            results_df["final_status"]
            == "MATCHED"
        ).sum()
    )

    review = int(
        (
            results_df["final_status"]
            == "REVIEW"
        ).sum()
    )

    exceptions = int(
        (
            results_df["final_status"]
            == "EXCEPTION"
        ).sum()
    )

    incorrect_automatic = int(
        (
            (
                results_df["final_status"]
                == "MATCHED"
            )
            &
            (
                ~results_df["correct"]
            )
        ).sum()
    )

    # --------------------------------------------------------
    # True reconciliation metrics
    # --------------------------------------------------------
    # Positive = a ground-truth invoice exists.
    # Positive prediction = controller final_status MATCHED.

    expected_positive = results_df[
        results_df["expected_invoice"].notna()
        & (results_df["expected_invoice"].astype(str).str.strip() != "")
        & (results_df["expected_invoice"].astype(str).str.lower() != "nan")
    ]

    expected_negative = results_df.drop(
        index=expected_positive.index
    )

    true_positive = int(
        (
            (expected_positive["final_status"] == "MATCHED")
            & expected_positive["correct"].astype(bool)
        ).sum()
    )

    false_negative = int(
        (
            (expected_positive["final_status"] != "MATCHED")
            | ~expected_positive["correct"].astype(bool)
        ).sum()
    )

    false_positive = int(
        (
            (expected_negative["final_status"] == "MATCHED")
            | (
                (expected_positive["final_status"] == "MATCHED")
                & ~expected_positive["correct"].astype(bool)
            )
        ).sum()
    )

    true_negative = int(
        (expected_negative["final_status"] != "MATCHED").sum()
    )

    accuracy = (
        (true_positive + true_negative) / total * 100
        if total
        else 0
    )

    match_rate = (
        matched / total * 100
        if total
        else 0
    )

    precision = (
        true_positive / (true_positive + false_positive) * 100
        if (true_positive + false_positive)
        else 0
    )

    recall = (
        true_positive / (true_positive + false_negative) * 100
        if (true_positive + false_negative)
        else 0
    )

    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0
    )

    # --------------------------------------------------------
    # Throughput
    # --------------------------------------------------------

    throughput = (
        total
        / total_processing_time
        if total_processing_time > 0
        else 0
    )

    # ========================================================
    # PRINT RESULTS
    # ========================================================

    print("\n" + "=" * 75)
    print("FINAL RESULTS")
    print("=" * 75)

    print(
        f"Total records       : {total}"
    )

    print(
        f"Matched             : {matched}"
    )

    print(
        f"Review              : {review}"
    )

    print(
        f"Exceptions          : {exceptions}"
    )

    print("\n" + "-" * 75)
    print("QUALITY")
    print("-" * 75)

    print(
        f"Accuracy            : "
        f"{accuracy:.2f}%"
    )

    print(
        f"Match rate          : "
        f"{match_rate:.2f}%"
    )

    print(
        f"Precision           : "
        f"{precision:.2f}%"
    )

    print(
        f"Recall              : "
        f"{recall:.2f}%"
    )

    print(
        f"F1 Score            : "
        f"{f1:.2f}%"
    )

    print(
        f"True positives      : {true_positive}"
    )

    print(
        f"False positives     : {false_positive}"
    )

    print(
        f"False negatives     : {false_negative}"
    )

    print("\n" + "-" * 75)
    print("VERIFICATION")
    print("-" * 75)

    print(
        f"Uncertain records   : "
        f"{uncertain_count}"
    )

    print(
        f"Guard verified      : "
        f"{guard_verified_count}"
    )

    print(
        f"Human review        : "
        f"{review}"
    )

    print(
        f"Incorrect automatic: "
        f"{incorrect_automatic}"
    )

    print("\n" + "-" * 75)
    print("PERFORMANCE")
    print("-" * 75)

    print(
        f"Deterministic time  : "
        f"{deterministic_time:.4f} sec"
    )

    print(
        f"Total time          : "
        f"{total_processing_time:.4f} sec"
    )

    print(
        f"Throughput          : "
        f"{throughput:.2f} records/sec"
    )

    # ========================================================
    # HONEST EXCEPTION LIST
    # ========================================================

    print("\n" + "-" * 75)
    print(
        "HONEST EXCEPTION / REVIEW LIST"
    )
    print("-" * 75)

    unresolved = results_df[
        results_df["final_status"]
        != "MATCHED"
    ]

    if unresolved.empty:

        print(
            "No unresolved records."
        )

    else:

        print(
            unresolved[
                [
                    "transaction_id",
                    "expected_invoice",
                    "matched_invoice",
                    "deterministic_score",
                    "duplicate_candidate",
                    "final_status",
                    "resolution",
                    "correct",
                ]
            ].to_string(
                index=False
            )
        )

    # ========================================================
    # INCORRECT AUTOMATIC MATCHES
    # ========================================================

    print("\n" + "-" * 75)
    print("INCORRECT AUTOMATIC MATCHES")
    print("-" * 75)

    incorrect = results_df[
        (
            results_df[
                "final_status"
            ]
            == "MATCHED"
        )
        &
        (
            ~results_df[
                "correct"
            ]
        )
    ]

    if incorrect.empty:

        print("None.")

    else:

        print(
            incorrect[
                [
                    "transaction_id",
                    "expected_invoice",
                    "matched_invoice",
                    "deterministic_score",
                    "resolution",
                ]
            ].to_string(
                index=False
            )
        )

    # ========================================================
    # EXCEPTION TYPES
    # ========================================================

    print("\n" + "-" * 75)
    print("EXCEPTION SUMMARY")
    print("-" * 75)

    duplicate_count = int(
        results_df[
            "duplicate_candidate"
        ].sum()
    )

    no_candidate_count = int(
        (
            results_df[
                "resolution"
            ]
            == "NO_CANDIDATE"
        ).sum()
    )

    human_review_count = int(
        (
            results_df[
                "resolution"
            ]
            == "HUMAN_REVIEW"
        ).sum()
    )

    print(
        f"Duplicate candidates : "
        f"{duplicate_count}"
    )

    print(
        f"No candidate         : "
        f"{no_candidate_count}"
    )

    print(
        f"Human review          : "
        f"{human_review_count}"
    )

    # ========================================================
    # SAVE
    # ========================================================

    output_dir = (
        PROJECT_ROOT
        / "data"
        / "results"
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    results_df.drop(
        columns=["guard_checks"],
        errors="ignore",
    ).to_csv(
        output_dir
        / "final_benchmark_results.csv",
        index=False,
    )

    # ========================================================
    # FINAL
    # ========================================================

    print("\n" + "=" * 75)
    print(
        "FINAL BENCHMARK COMPLETE"
    )
    print("=" * 75)

    print(
        "Results saved to:"
    )

    print(
        output_dir
        / "final_benchmark_results.csv"
    )


if __name__ == "__main__":
    run_final_benchmark()