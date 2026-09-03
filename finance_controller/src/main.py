import time

import pandas as pd

from matcher import reconcile, find_top_candidates
from ai_reasoner import (
    build_ai_prompt,
    ask_ai,
    validate_ai_response,
)


def run_ai_on_transaction(bank_row, erp):
    """
    Send one uncertain transaction to the local LLM.
    """

    candidates = find_top_candidates(
        bank_row,
        erp,
        top_n=5
    )

    prompt = build_ai_prompt(
        bank_row,
        candidates
    )

    raw_response = ask_ai(prompt)

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
        }

    result = validation["result"]

    return {
        "ai_decision": result["decision"],
        "ai_invoice": result["selected_invoice"],
        "ai_confidence": result["confidence"],
        "ai_reason": result["reason"],
        "ai_risk": result["risk"],
    }


def main():

    print()
    print("=" * 70)
    print("AI FINANCE CONTROLLER")
    print("=" * 70)

    # --------------------------------------------------
    # 1. LOAD DATA
    # --------------------------------------------------

    print()
    print("Loading data...")

    bank = pd.read_csv(
        "data/bank.csv",
        parse_dates=["date"]
    )

    erp = pd.read_csv(
        "data/erp.csv",
        parse_dates=["date"]
    )

    ground_truth = pd.read_csv(
        "data/verification.csv"
    )

    print(f"Bank records: {len(bank)}")
    print(f"ERP records: {len(erp)}")
    print(f"Ground truth records: {len(ground_truth)}")

    # --------------------------------------------------
    # 2. RUN DETERMINISTIC MATCHER
    # --------------------------------------------------

    print()
    print("Running deterministic reconciliation...")

    start_time = time.time()

    results = reconcile(
        bank,
        erp
    )

    deterministic_time = time.time() - start_time

    print(
        f"Deterministic reconciliation completed "
        f"in {deterministic_time:.2f} seconds"
    )

    # --------------------------------------------------
    # 3. SHOW DETERMINISTIC SUMMARY
    # --------------------------------------------------

    print()
    print("=" * 70)
    print("DETERMINISTIC RESULTS")
    print("=" * 70)

    status_counts = results["status"].value_counts()

    matched_count = status_counts.get(
        "MATCHED",
        0
    )

    warning_count = status_counts.get(
        "WARNING",
        0
    )

    exception_count = status_counts.get(
        "EXCEPTION",
        0
    )

    print(f"Total transactions : {len(results)}")
    print(f"MATCHED            : {matched_count}")
    print(f"WARNING            : {warning_count}")
    print(f"EXCEPTION          : {exception_count}")

    # --------------------------------------------------
    # 4. SELECT UNCERTAIN TRANSACTIONS
    # --------------------------------------------------

    uncertain_results = results[
        results["status"].isin([
            "WARNING",
            "EXCEPTION"
        ])
    ].head(3)

    print()
    print("=" * 70)
    print("AI GATE")
    print("=" * 70)

    print(
        f"Uncertain transactions available: "
        f"{warning_count + exception_count}"
    )

    print(
        f"Sending only {len(uncertain_results)} "
        f"transactions to AI for this test."
    )

    # --------------------------------------------------
    # 5. SEND UNCERTAIN TRANSACTIONS TO AI
    # --------------------------------------------------

    ai_results = []

    for _, result_row in uncertain_results.iterrows():

        transaction_id = result_row[
            "transaction_id"
        ]

        print()
        print("-" * 70)
        print(
            f"Sending {transaction_id} to local Qwen..."
        )

        # Find original bank transaction
        bank_match = bank[
            bank["transaction_id"]
            == transaction_id
        ]

        if bank_match.empty:

            print(
                f"Could not find bank transaction "
                f"{transaction_id}"
            )

            continue

        bank_row = bank_match.iloc[0]

        # Run AI
        ai_result = run_ai_on_transaction(
            bank_row,
            erp
        )

        ai_result["transaction_id"] = (
            transaction_id
        )

        # Store deterministic result too
        ai_result["deterministic_invoice"] = (
            result_row["matched_invoice"]
        )

        ai_result["deterministic_status"] = (
            result_row["status"]
        )

        ai_result["deterministic_confidence"] = (
            result_row["confidence"]
        )

        ai_results.append(
            ai_result
        )

        # Print AI result
        print()
        print("AI DECISION")
        print(
            f"Decision   : "
            f"{ai_result['ai_decision']}"
        )
        print(
            f"Invoice    : "
            f"{ai_result['ai_invoice']}"
        )
        print(
            f"Confidence : "
            f"{ai_result['ai_confidence']}"
        )
        print(
            f"Risk       : "
            f"{ai_result['ai_risk']}"
        )
        print(
            f"Reason     : "
            f"{ai_result['ai_reason']}"
        )

    # --------------------------------------------------
    # 6. CREATE AI RESULTS DATAFRAME
    # --------------------------------------------------

    ai_results_df = pd.DataFrame(
        ai_results
    )

    # --------------------------------------------------
    # 7. FINAL REPORT
    # --------------------------------------------------

    print()
    print("=" * 70)
    print("AI ASSISTED RECONCILIATION")
    print("=" * 70)

    print(
        f"Total transactions       : "
        f"{len(results)}"
    )

    print(
        f"Deterministic MATCHED    : "
        f"{matched_count}"
    )

    print(
        f"Deterministic WARNING    : "
        f"{warning_count}"
    )

    print(
        f"Deterministic EXCEPTION  : "
        f"{exception_count}"
    )

    print(
        f"AI transactions tested   : "
        f"{len(ai_results_df)}"
    )

    if not ai_results_df.empty:

        print()
        print("AI DECISION COUNTS")

        ai_decision_counts = (
            ai_results_df["ai_decision"]
            .value_counts()
        )

        for decision, count in (
            ai_decision_counts.items()
        ):

            print(
                f"{decision:<20}: {count}"
            )

    # --------------------------------------------------
    # 8. SAVE AI RESULTS
    # --------------------------------------------------

    if not ai_results_df.empty:

        ai_results_df.to_csv(
            "data/ai_results.csv",
            index=False
        )

        print()
        print(
            "AI results saved to "
            "data/ai_results.csv"
        )

    print()
    print("=" * 70)
    print("PIPELINE COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()