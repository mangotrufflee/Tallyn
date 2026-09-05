"""
AI Reconciliation Benchmark Runner
===================================

Runs the full AI reconciliation pipeline against a dataset and produces
a summary report.

Usage:

  # 500-record benchmark dataset
  python scripts/run_ai_benchmark.py

  # Alternative dataset (new vendor formats, different ID patterns, etc.)
  python scripts/run_ai_benchmark.py \\
      --bank path/to/bank.csv \\
      --erp  path/to/erp.csv  \\
      --label "My New Dataset"

The script does NOT use verification.csv or any ground-truth file.
It reports AI behaviour only — it does not judge correctness against
a known answer key (that is the benchmark logic, which is out of scope).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.reconciliation.matcher import find_best_match, find_top_candidates, classify_match
from backend.app.ai.ai_reasoner import (
    build_ai_prompt,
    validate_ai_response,
    safe_ask_ai,
    enrich_candidates_with_source_rows,
)
from backend.app.reconciliation.verification_guard import (
    verify_ai_match,
    get_final_decision,
    verify_selected_candidate,
)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description="AI Reconciliation Benchmark Runner",
    )
    parser.add_argument(
        "--bank",
        default=str(PROJECT_ROOT / "data" / "raw" / "bank.csv"),
        help="Path to the bank CSV file",
    )
    parser.add_argument(
        "--erp",
        default=str(PROJECT_ROOT / "data" / "raw" / "erp.csv"),
        help="Path to the ERP / supporting CSV file",
    )
    parser.add_argument(
        "--label",
        default="500-Record Benchmark Dataset",
        help="Human-readable label for this run",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=5,
        help="Number of AI candidates per transaction (default: 5)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit to first N uncertain transactions (for quick smoke-test)",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_csv(path: str, parse_dates: list[str] | None = None) -> pd.DataFrame:
    df = pd.read_csv(path)
    if parse_dates:
        for col in parse_dates:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


# ---------------------------------------------------------------------------
# Deterministic pass
# ---------------------------------------------------------------------------

def run_deterministic(bank: pd.DataFrame, erp: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, bank_row in bank.iterrows():
        best_match, score, second_best_score, _ = find_best_match(bank_row, erp)
        status = classify_match(score, second_best_score, best_match)
        invoice_id = best_match["invoice_id"] if best_match is not None else None
        rows.append({
            "transaction_id": bank_row["transaction_id"],
            "matched_invoice": invoice_id,
            "match_score": score,
            "deterministic_status": status,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# AI pass (single transaction)
# ---------------------------------------------------------------------------

def run_ai_on_row(bank_row, erp: pd.DataFrame, top_n: int = 5) -> dict:
    t0 = time.perf_counter()

    candidates = find_top_candidates(bank_row, erp, top_n=top_n)

    allowed_ids = [
        c.get("invoice_id")
        for c in candidates
        if c.get("invoice_id") not in (None, "")
    ]

    if not candidates:
        return {
            "ai_decision": "EXCEPTION",
            "ai_invoice": None,
            "ai_confidence": 0,
            "ai_reason": "No ERP candidates available",
            "ai_risk": "HIGH",
            "verification_decision": "EXCEPTION",
            "verification_reason": "No ERP candidates available",
            "ai_error": None,
            "elapsed_s": round(time.perf_counter() - t0, 2),
        }

    prompt = build_ai_prompt(bank_row, candidates, erp=erp)
    ai_call = safe_ask_ai(prompt)

    if not ai_call["ok"]:
        return {
            "ai_decision": "REVIEW",
            "ai_invoice": None,
            "ai_confidence": 0,
            "ai_reason": ai_call["error"],
            "ai_risk": "HIGH",
            "verification_decision": "REVIEW",
            "verification_reason": "AI unavailable or failed",
            "ai_error": ai_call["error"],
            "elapsed_s": round(time.perf_counter() - t0, 2),
        }

    validation = validate_ai_response(ai_call["raw"], allowed_invoice_ids=allowed_ids)

    if not validation["valid"]:
        return {
            "ai_decision": "REVIEW",
            "ai_invoice": None,
            "ai_confidence": 0,
            "ai_reason": validation["error"],
            "ai_risk": "HIGH",
            "verification_decision": "REVIEW",
            "verification_reason": f"Invalid AI response: {validation['error']}",
            "ai_error": validation["error"],
            "elapsed_s": round(time.perf_counter() - t0, 2),
        }

    result = validation["result"]
    ai_decision = result["decision"]
    ai_invoice = result["selected_invoice"]

    if not ai_invoice:
        verification_decision = (
            "EXCEPTION" if ai_decision == "EXCEPTION" else "REVIEW"
        )
        return {
            "ai_decision": ai_decision,
            "ai_invoice": None,
            "ai_confidence": result["confidence"],
            "ai_reason": result["reason"],
            "ai_risk": result["risk"],
            "verification_decision": verification_decision,
            "verification_reason": "AI could not select a candidate",
            "ai_error": None,
            "elapsed_s": round(time.perf_counter() - t0, 2),
        }

    # Verify against candidate set
    selection = verify_selected_candidate(ai_invoice, candidates)
    if isinstance(selection, dict) and selection.get("decision") == "EXCEPTION":
        return {
            "ai_decision": "REVIEW",
            "ai_invoice": ai_invoice,
            "ai_confidence": result["confidence"],
            "ai_reason": result["reason"],
            "ai_risk": "HIGH",
            "verification_decision": "REVIEW",
            "verification_reason": selection.get(
                "reason", "AI selected invoice outside candidate set"
            ),
            "ai_error": "candidate_set_violation",
            "elapsed_s": round(time.perf_counter() - t0, 2),
        }

    if (
        isinstance(selection, dict)
        and selection.get("decision") == "REVIEW"
        and selection.get("exception_type") == "DUPLICATE_SETTLEMENT"
    ):
        return {
            "ai_decision": ai_decision,
            "ai_invoice": ai_invoice,
            "ai_confidence": result["confidence"],
            "ai_reason": result["reason"],
            "ai_risk": result["risk"],
            "verification_decision": "REVIEW",
            "verification_reason": selection.get("reason"),
            "ai_error": None,
            "elapsed_s": round(time.perf_counter() - t0, 2),
        }

    # Run Verification Guard
    selected_erp = None
    matches = erp[
        erp["invoice_id"].astype(str).str.strip() == str(ai_invoice).strip()
    ]
    if not matches.empty:
        selected_erp = matches.iloc[0]

    verification_checks = verify_ai_match(bank_row, selected_erp)
    verification_decision = get_final_decision(verification_checks)

    return {
        "ai_decision": ai_decision,
        "ai_invoice": ai_invoice,
        "ai_confidence": result["confidence"],
        "ai_reason": result["reason"],
        "ai_risk": result["risk"],
        "verification_decision": verification_decision,
        "verification_reason": None,
        "ai_error": None,
        "elapsed_s": round(time.perf_counter() - t0, 2),
    }


# ---------------------------------------------------------------------------
# Reporting helpers
# ---------------------------------------------------------------------------

def sep(char="=", width=62):
    print(char * width)


def section(title: str):
    sep()
    print(f"  {title}")
    sep()


def print_report(
    label: str,
    bank: pd.DataFrame,
    det_df: pd.DataFrame,
    ai_rows: list[dict],
    total_elapsed: float,
):
    ai_df = pd.DataFrame(ai_rows) if ai_rows else pd.DataFrame()

    n_total = len(bank)
    n_uncertain = len(det_df[det_df["deterministic_status"].isin(["WARNING", "EXCEPTION"])])
    n_det_matched = len(det_df[det_df["deterministic_status"] == "MATCHED"])

    n_ai_processed = len(ai_df)
    n_ai_match = 0
    n_ai_review = 0
    n_ai_exception = 0
    n_ai_errors = 0
    n_guard_approved = 0
    n_guard_rejected = 0

    if not ai_df.empty:
        n_ai_match = len(ai_df[ai_df["ai_decision"] == "MATCH"])
        n_ai_review = len(ai_df[ai_df["ai_decision"] == "REVIEW"])
        n_ai_exception = len(ai_df[ai_df["ai_decision"] == "EXCEPTION"])
        n_ai_errors = int(ai_df["ai_error"].notna().sum())
        n_guard_approved = len(
            ai_df[ai_df["verification_decision"].isin(["MATCHED", "APPROVED"])]
        )
        n_guard_rejected = len(
            ai_df[ai_df["verification_decision"].isin(["REVIEW", "EXCEPTION"])]
        )

    sep()
    print(f"  AI RECONCILIATION BENCHMARK REPORT")
    print(f"  {label}")
    sep()
    print(f"  Total transactions         : {n_total}")
    print(f"  Deterministic MATCHED      : {n_det_matched}")
    print(f"  Sent to AI (WARNING/EXCEPT): {n_uncertain}")
    sep("-")
    print(f"  AI cases processed         : {n_ai_processed}")
    print(f"  AI → MATCH                 : {n_ai_match}")
    print(f"  AI → REVIEW                : {n_ai_review}")
    print(f"  AI → EXCEPTION             : {n_ai_exception}")
    print(f"  AI errors                  : {n_ai_errors}")
    sep("-")
    print(f"  Guard approvals            : {n_guard_approved}")
    print(f"  Guard rejections           : {n_guard_rejected}")
    sep("-")
    print(f"  Total elapsed              : {total_elapsed:.1f}s")
    if n_ai_processed > 0:
        print(f"  Avg AI time per case       : {total_elapsed/n_ai_processed:.1f}s")
    sep()

    if not ai_df.empty and n_ai_errors > 0:
        print("\n  AI Error Samples:")
        error_rows = ai_df[ai_df["ai_error"].notna()].head(5)
        for _, row in error_rows.iterrows():
            print(f"    TXN={row.get('transaction_id','?')}  error={row['ai_error']}")
        sep()

    if not ai_df.empty:
        print("\n  AI Decision Breakdown by Verification Decision:")
        cross = pd.crosstab(
            ai_df["ai_decision"],
            ai_df["verification_decision"],
            margins=True,
        )
        print(cross.to_string())
        sep()

    # Save results CSV
    if not ai_df.empty:
        out_path = PROJECT_ROOT / "data" / "results" / "ai_benchmark_results.csv"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        ai_df.to_csv(out_path, index=False)
        print(f"\n  Full results saved to: {out_path}")
        sep()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = parse_args()

    print(f"\nLoading: {args.bank}")
    bank = load_csv(args.bank, parse_dates=["date"])
    print(f"Loading: {args.erp}")
    erp = load_csv(args.erp, parse_dates=["date"])

    print(f"Bank records  : {len(bank)}")
    print(f"ERP records   : {len(erp)}")

    # Deterministic pass
    print("\nRunning deterministic pass ...")
    det_df = run_deterministic(bank, erp)

    uncertain = det_df[det_df["deterministic_status"].isin(["WARNING", "EXCEPTION"])]
    print(f"Uncertain (WARNING/EXCEPTION): {len(uncertain)}")

    if args.limit:
        uncertain = uncertain.head(args.limit)
        print(f"Limited to first {args.limit} uncertain transactions")

    # AI pass
    ai_rows = []
    t_ai_start = time.perf_counter()

    for i, (_, row) in enumerate(uncertain.iterrows(), start=1):
        txn_id = str(row["transaction_id"])
        bank_matches = bank[bank["transaction_id"].astype(str) == txn_id]
        if bank_matches.empty:
            print(f"  [{i}/{len(uncertain)}] SKIPPED {txn_id} — not found in bank frame")
            continue

        bank_row = bank_matches.iloc[0]
        print(f"  [{i}/{len(uncertain)}] Processing {txn_id} ...", end=" ", flush=True)

        ai_result = run_ai_on_row(bank_row, erp, top_n=args.top_n)
        ai_result["transaction_id"] = txn_id

        decision = ai_result.get("ai_decision", "?")
        elapsed = ai_result.get("elapsed_s", 0)
        guard = ai_result.get("verification_decision", "?")
        err = f" [ERR: {ai_result.get('ai_error')}]" if ai_result.get("ai_error") else ""
        print(f"AI={decision}  Guard={guard}  {elapsed:.1f}s{err}")

        ai_rows.append(ai_result)

    total_elapsed = time.perf_counter() - t_ai_start

    print_report(args.label, bank, det_df, ai_rows, total_elapsed)


if __name__ == "__main__":
    main()
