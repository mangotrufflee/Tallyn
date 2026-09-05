from pathlib import Path
from io import BytesIO
import json
from typing import List, Optional, Tuple

import pandas as pd

from fastapi import FastAPI, HTTPException, File, UploadFile
from pydantic import BaseModel

from fastapi.middleware.cors import CORSMiddleware
import ast

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


# ============================================================
# PROJECT IMPORTS
# ============================================================

from backend.app.database import (
    get_connection,
    initialize_database,
    load_bank_data,
    load_erp_data,
    seed_database,
    replace_active_batch,
)


from backend.app.reconciliation.matcher import (
    find_best_match,
    find_top_candidates,
    classify_match,
    get_exception_reason,
)


from backend.app.ai.ai_reasoner import (
    build_ai_prompt,
    validate_ai_response,
    safe_ask_ai,
)


from backend.app.reconciliation.verification_guard import (
    verify_ai_match,
    get_final_decision,
    verify_selected_candidate,
)


# ============================================================
# CONFIGURATION
# ============================================================

project_root = Path(__file__).resolve().parents[2]


def decode_original_fields(value):
    if not value:
        return {}
    try:
        data = json.loads(value)
        if isinstance(data, dict):
            return {
                k: (None if isinstance(v, float) and (pd.isna(v) or v != v) else v)
                for k, v in data.items()
            }
        return data
    except (TypeError, json.JSONDecodeError):
        return {"raw": value}


# ============================================================
# FASTAPI APPLICATION
# ============================================================

app = FastAPI(
    title="AI Finance Controller",
    description="AI-assisted financial reconciliation system",
    version="1.0.0",
)


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# REVIEW REQUEST MODEL
# ============================================================

class ReviewRequest(BaseModel):

    decision: str

    note: str = ""


REQUIRED_BANK_COLUMNS = {
    "transaction_id",
    "date",
    "amount",
    "counterparty",
}
REQUIRED_ERP_COLUMNS = {
    "invoice_id",
    "date",
    "amount",
    "vendor",
    "reference",
}


async def _read_upload_bytes(upload: UploadFile) -> Tuple[bytes, str]:
    contents = await upload.read()
    filename = upload.filename or "upload"
    return contents, filename


async def read_uploaded_records(upload: UploadFile, required_columns):
    """
    Backward-compatible upload reader.

    Uses the ingestion pipeline (alias normalization, PDF, validation)
    and returns canonical frames for the existing reconciliation engine.
    """
    from backend.app.ingestion.pipeline import ingest_file

    contents, filename = await _read_upload_bytes(upload)

    # Infer role from the historical required-column contract.
    if "transaction_id" in required_columns:
        hinted_role = "bank"
    else:
        hinted_role = "supporting"

    frame, info = ingest_file(
        contents,
        filename,
        hinted_role=hinted_role,
    )

    # Preserve legacy keys expected by the frontend.
    legacy = {
        "filename": info.get("filename"),
        "records": info.get("records", 0),
        "columns": info.get("columns") or info.get("detected_fields") or [],
        "valid": info.get("valid", False),
        "errors": list(info.get("errors") or []),
        "warnings": list(info.get("warnings") or []),
        "source_type": info.get("source_type"),
        "status": info.get("status"),
        "detected_fields": info.get("detected_fields") or [],
    }
    return frame, legacy


async def read_supporting_uploads(uploads):
    """Normalize one or more supporting documents independently."""
    from backend.app.ingestion.pipeline import ingest_supporting_files

    files = []
    for upload in uploads:
        contents, filename = await _read_upload_bytes(upload)
        files.append((contents, filename))

    combined, file_infos, summary = ingest_supporting_files(files)
    legacy = {
        "filename": summary.get("filename"),
        "records": summary.get("records", 0),
        "columns": summary.get("columns") or [],
        "valid": summary.get("valid", False),
        "errors": list(summary.get("errors") or []),
        "warnings": list(summary.get("warnings") or []),
        "source_type": summary.get("source_type"),
        "status": summary.get("status"),
        "detected_fields": summary.get("detected_fields") or [],
        "files": file_infos,
    }
    return combined, legacy


# ============================================================
# AI + VERIFICATION
# ============================================================

def run_ai_on_transaction(
    bank_row,
    erp
):
    try:
        if isinstance(erp, pd.DataFrame) and not erp.empty and "date" in erp.columns:
            if not pd.api.types.is_datetime64_any_dtype(erp["date"]):
                erp = erp.copy()
                erp["date"] = pd.to_datetime(erp["date"])
        if isinstance(bank_row, (pd.Series, dict)) and "date" in bank_row:
            if not isinstance(bank_row.get("date"), (pd.Timestamp, pd.DatetimeIndex)):
                bank_row = bank_row.copy()
                bank_row["date"] = pd.to_datetime(bank_row["date"])

        candidates = find_top_candidates(
            bank_row,
            erp,
            top_n=5
        )
        # Note: enrich_candidates_with_source_rows is called inside
        # build_ai_prompt — do not call it again here to avoid double-enrichment.

        allowed_ids = [
            candidate.get("invoice_id")
            for candidate in candidates
            if candidate.get("invoice_id") not in (None, "")
        ]

        # No candidates → EXCEPTION without calling the model.
        if len(candidates) == 0:
            return {
                "ai_decision": "EXCEPTION",
                "ai_invoice": None,
                "ai_confidence": 0,
                "ai_reason": "No ERP candidates available",
                "ai_risk": "HIGH",
                "verification_decision": "EXCEPTION",
                "verification_reason": "No ERP candidates available",
                "verification_checks": None,
            }

        prompt = build_ai_prompt(
            bank_row,
            candidates,
            erp=erp,
        )

        ai_call = safe_ask_ai(prompt)
        if not ai_call["ok"]:
            return {
                "ai_decision": "REVIEW",
                "ai_invoice": None,
                "ai_confidence": 0,
                "ai_reason": ai_call["error"],
                "ai_risk": "HIGH",
                "verification_decision": "REVIEW",
                "verification_reason": f"AI unavailable or failed: {ai_call['error']}",
                "verification_checks": None,
            }

        validation = validate_ai_response(
            ai_call["raw"],
            allowed_invoice_ids=allowed_ids,
        )

        # Invalid / hallucinated AI output → REVIEW (never auto MATCH).
        if not validation["valid"]:
            return {
                "ai_decision": "REVIEW",
                "ai_invoice": None,
                "ai_confidence": 0,
                "ai_reason": validation["error"],
                "ai_risk": "HIGH",
                "verification_decision": "REVIEW",
                "verification_reason": (
                    "Invalid or unsafe AI response: "
                    f"{validation['error']}"
                ),
                "verification_checks": None,
            }

        result = validation["result"]
        ai_decision = result["decision"]
        ai_invoice = result["selected_invoice"]

        if not ai_invoice:
            verification_decision = (
                "EXCEPTION"
                if ai_decision == "EXCEPTION"
                else "REVIEW"
            )
            verification_reason = (
                result.get("reason")
                or (
                    "AI marked the case as EXCEPTION"
                    if verification_decision == "EXCEPTION"
                    else "AI could not confidently select a candidate"
                )
            )
            return {
                "ai_decision": ai_decision,
                "ai_invoice": None,
                "ai_confidence": result["confidence"],
                "ai_reason": result["reason"],
                "ai_risk": result["risk"],
                "verification_decision": verification_decision,
                "verification_reason": verification_reason,
                "verification_checks": None,
            }

        selection = verify_selected_candidate(
            ai_invoice,
            candidates,
        )
        selection_decision = (
            selection.get("decision")
            if isinstance(selection, dict)
            else None
        )
        if selection_decision == "EXCEPTION":
            return {
                "ai_decision": "REVIEW",
                "ai_invoice": ai_invoice,
                "ai_confidence": result["confidence"],
                "ai_reason": result["reason"],
                "ai_risk": "HIGH",
                "verification_decision": "REVIEW",
                "verification_reason": selection.get(
                    "reason",
                    "AI selected an invoice outside the candidate set",
                ),
                "verification_checks": None,
            }

        if selection_decision == "REVIEW" and selection.get("exception_type") == "DUPLICATE_SETTLEMENT":
            return {
                "ai_decision": ai_decision,
                "ai_invoice": ai_invoice,
                "ai_confidence": result["confidence"],
                "ai_reason": result["reason"],
                "ai_risk": result["risk"],
                "verification_decision": "REVIEW",
                "verification_reason": selection.get("reason"),
                "verification_checks": None,
            }

        # If AI itself did not recommend MATCH (e.g. REVIEW or EXCEPTION), preserve that decision
        if ai_decision != "MATCH":
            return {
                "ai_decision": ai_decision,
                "ai_invoice": ai_invoice,
                "ai_confidence": result["confidence"],
                "ai_reason": result["reason"],
                "ai_risk": result["risk"],
                "verification_decision": ai_decision,
                "verification_reason": result.get("reason") or f"AI recommended {ai_decision}",
                "verification_checks": None,
            }

        # AI recommended MATCH → Run Verification Guard
        selected_erp = None
        normalized_erp_invoice_ids = (
            pd.Series(erp["invoice_id"], copy=True)
            .astype("string")
            .fillna("")
            .str.strip()
            .str.lower()
        )
        target_invoice_id = str(ai_invoice).strip().lower()
        matches = erp.loc[normalized_erp_invoice_ids == target_invoice_id].copy()
        if not matches.empty:
            selected_erp = matches.iloc[0]

        verification_checks = verify_ai_match(
            bank_row,
            selected_erp,
        )
        verification_decision = get_final_decision(
            verification_checks,
        )

        if verification_decision == "MATCHED":
            verification_reason = "Verification Guard approved match"
        else:
            if not verification_checks.get("candidate_exists"):
                verification_reason = "Verification Guard rejected: candidate does not exist in ERP"
            elif verification_checks.get("material_amount_conflict"):
                verification_reason = f"Verification Guard rejected: material amount conflict (diff: {verification_checks.get('amount_difference')})"
            elif verification_checks.get("material_date_conflict"):
                verification_reason = f"Verification Guard rejected: material date conflict (diff: {verification_checks.get('date_difference')} days)"
            elif verification_checks.get("reference_conflict"):
                verification_reason = "Verification Guard rejected: cross-reference conflict"
            elif not verification_checks.get("amount_matches"):
                verification_reason = f"Verification Guard rejected: amount mismatch (diff: {verification_checks.get('amount_difference')})"
            elif not verification_checks.get("date_matches"):
                verification_reason = f"Verification Guard rejected: date mismatch (diff: {verification_checks.get('date_difference')} days)"
            elif verification_checks.get("vendor_similarity", 0) < 70:
                verification_reason = f"Verification Guard rejected: vendor similarity below threshold ({verification_checks.get('vendor_similarity')}%)"
            elif not (verification_checks.get("reference_matches") is True or verification_checks.get("settlement_reference_matches") is True):
                verification_reason = "Verification Guard rejected: unconfirmed cross-system reference"
            else:
                verification_reason = "Verification Guard rejected: verification criteria not satisfied"

        return {
            "ai_decision": ai_decision,
            "ai_invoice": ai_invoice,
            "ai_confidence": result["confidence"],
            "ai_reason": result["reason"],
            "ai_risk": result["risk"],
            "verification_decision": verification_decision,
            "verification_reason": verification_reason,
            "verification_checks": str(verification_checks),
        }

    except Exception as exc:
        return {
            "ai_decision": "REVIEW",
            "ai_invoice": None,
            "ai_confidence": 0,
            "ai_reason": f"AI routing error: {str(exc)}",
            "ai_risk": "HIGH",
            "verification_decision": "REVIEW",
            "verification_reason": f"AI routing error fallback: {str(exc)}",
            "verification_checks": None,
        }


# ============================================================
# RECONCILIATION ENGINE
# ============================================================

def run_reconciliation(bank=None, erp=None):

    if bank is None:
        bank = load_bank_data()

    if erp is None:
        erp = load_erp_data()

    if isinstance(bank, pd.DataFrame) and not bank.empty and "date" in bank.columns:
        if not pd.api.types.is_datetime64_any_dtype(bank["date"]):
            bank = bank.copy()
            bank["date"] = pd.to_datetime(bank["date"])

    if isinstance(erp, pd.DataFrame) and not erp.empty and "date" in erp.columns:
        if not pd.api.types.is_datetime64_any_dtype(erp["date"]):
            erp = erp.copy()
            erp["date"] = pd.to_datetime(erp["date"])


    deterministic_results = []


    # --------------------------------------------------------
    # Deterministic reconciliation
    # --------------------------------------------------------

    for _, bank_row in bank.iterrows():

        (
            best_match,
            score,
            second_best_score,
            _score_details,
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

            invoice_id = None

        else:

            invoice_id = best_match["invoice_id"]


        reason = get_exception_reason(
            bank_row,
            best_match,
            score,
            second_best_score,
        )


        deterministic_results.append({

            "transaction_id":
                bank_row["transaction_id"],

            "matched_invoice":
                invoice_id,

            "match_score":
                score,

            "deterministic_status":
                status,

            "reason":
                reason,
        })


    deterministic_df = pd.DataFrame(
        deterministic_results
    )


    # --------------------------------------------------------
    # AI gate
    # --------------------------------------------------------

    uncertain = deterministic_df[
        deterministic_df[
            "deterministic_status"
        ].isin(
            [
                "WARNING",
                "EXCEPTION"
            ]
        )
    ]


    # --------------------------------------------------------
    # Run AI
    # --------------------------------------------------------

    ai_results = []


    for _, row in uncertain.iterrows():

        transaction_id = row[
            "transaction_id"
        ]


        bank_row = bank[
            bank["transaction_id"]
            .astype(str)
            ==
            str(transaction_id)
        ].iloc[0]


        ai_result = run_ai_on_transaction(
            bank_row,
            erp
        )


        ai_results.append({

            "transaction_id":
                transaction_id,

            **ai_result,
        })


    ai_df = pd.DataFrame(
        ai_results
    )


    # --------------------------------------------------------
    # Save results
    # --------------------------------------------------------

    connection = get_connection()


    for _, row in deterministic_df.iterrows():

        ai_row = None


        if not ai_df.empty:

            matching_ai = ai_df[
                ai_df[
                    "transaction_id"
                ].astype(str)
                ==
                str(row["transaction_id"])
            ]


            if not matching_ai.empty:

                ai_row = matching_ai.iloc[0]


        # ----------------------------------------------------
        # No AI
        # ----------------------------------------------------

        if ai_row is None:

            ai_decision = None

            ai_invoice = None

            ai_confidence = None

            ai_reason = None

            ai_risk = None

            verification_decision = (
                row["deterministic_status"]
            )

            verification_reason = None

            verification_checks = None

            final_matched_invoice = row["matched_invoice"]


        # ----------------------------------------------------
        # AI result
        # ----------------------------------------------------

        else:

            ai_decision = ai_row[
                "ai_decision"
            ]

            ai_invoice = ai_row[
                "ai_invoice"
            ]

            ai_confidence = ai_row[
                "ai_confidence"
            ]

            ai_reason = ai_row[
                "ai_reason"
            ]

            ai_risk = ai_row[
                "ai_risk"
            ]

            verification_decision = (
                ai_row[
                    "verification_decision"
                ]
            )

            verification_reason = (
                ai_row.get(
                    "verification_reason",
                    None
                )
            )

            verification_checks = (
                ai_row.get(
                    "verification_checks",
                    None
                )
            )

            if verification_decision == "MATCHED":
                final_matched_invoice = ai_invoice or row["matched_invoice"]
            elif verification_decision == "REVIEW":
                final_matched_invoice = ai_invoice or row["matched_invoice"]
            else:
                final_matched_invoice = None

        score_val = row.get("match_score")
        try:
            if score_val is None:
                score_float = 0.0
            else:
                score_float = float(score_val)
                if pd.isna(score_float) or score_float != score_float:
                    score_float = 0.0
        except (TypeError, ValueError):
            try:
                if score_val is None:
                    score_float = 0.0
                else:
                    score_text = str(score_val).strip()
                    if score_text in {"", "nan", "NaN", "None", "null"}:
                        score_float = 0.0
                    else:
                        score_float = float(score_text)
                        if pd.isna(score_float) or score_float != score_float:
                            score_float = 0.0
            except (TypeError, ValueError):
                score_float = 0.0

        connection.execute(
            """
            INSERT INTO reconciliation_results (

                transaction_id,
                matched_invoice,
                match_score,
                deterministic_status,
                reason,

                ai_decision,
                ai_invoice,
                ai_confidence,
                ai_reason,
                ai_risk,

                verification_decision,
                verification_reason,
                verification_checks,

                review_status,
                review_decision,
                reviewer_note,
                reviewed_at,

                updated_at
            )

            VALUES (
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?,
                NULL, NULL, NULL, NULL,
                CURRENT_TIMESTAMP
            )
            ON CONFLICT(transaction_id) DO UPDATE SET
                matched_invoice = excluded.matched_invoice,
                match_score = excluded.match_score,
                deterministic_status = excluded.deterministic_status,
                reason = excluded.reason,
                ai_decision = excluded.ai_decision,
                ai_invoice = excluded.ai_invoice,
                ai_confidence = excluded.ai_confidence,
                ai_reason = excluded.ai_reason,
                ai_risk = excluded.ai_risk,
                verification_decision = CASE
                    WHEN reconciliation_results.review_status = 'COMPLETED'
                    THEN reconciliation_results.verification_decision
                    ELSE excluded.verification_decision
                END,
                verification_reason = excluded.verification_reason,
                verification_checks = excluded.verification_checks,
                updated_at = CURRENT_TIMESTAMP
            """,

            (
                str(row["transaction_id"]),

                final_matched_invoice,

                score_float,

                row["deterministic_status"],

                row["reason"],

                ai_decision,

                ai_invoice,

                ai_confidence,

                ai_reason,

                ai_risk,

                verification_decision,

                verification_reason,

                verification_checks,
            ),
        )


    connection.commit()

    connection.close()


    return {

        "total_transactions":
            len(bank),

        "deterministic_uncertain":
            len(uncertain),

        "ai_processed":
            len(ai_df),
    }


# ============================================================
# STARTUP
# ============================================================

@app.on_event("startup")
def startup():

    initialize_database()


    connection = get_connection()


    count = connection.execute(
        """
        SELECT COUNT(*)
        FROM transactions
        """
    ).fetchone()[0]


    connection.close()


    if count == 0:

        seed_database()


# ============================================================
# ROOT
# ============================================================

@app.get("/")
def root():

    return {

        "application":
            "AI Finance Controller",

        "status":
            "running",

        "version":
            "1.0.0",
    }


# ============================================================
# SUMMARY
# ============================================================

@app.get("/records")
def get_records():
    """Return datasets represented by the active reconciliation database."""
    connection = get_connection()
    row = connection.execute(
        """
        SELECT
            COUNT(t.transaction_id) AS transactions,
            MAX(r.updated_at) AS updated_at
        FROM transactions t
        LEFT JOIN reconciliation_results r
          ON t.transaction_id = r.transaction_id
        """
    ).fetchone()
    connection.close()

    if not row or not row["transactions"]:
        return []

    return [{
        "id": "active",
        "transactions": row["transactions"],
        "updated_at": row["updated_at"],
    }]

@app.get("/summary")
def get_summary():

    connection = get_connection()


    total = connection.execute(
        """
        SELECT COUNT(*)
        FROM transactions
        """
    ).fetchone()[0]


    matched = connection.execute(
        """
        SELECT COUNT(*)
        FROM reconciliation_results

        WHERE verification_decision =
        'MATCHED'
        """
    ).fetchone()[0]


    review = connection.execute(
        """
        SELECT COUNT(*)
        FROM reconciliation_results

        WHERE verification_decision =
        'REVIEW'
        """
    ).fetchone()[0]


    exceptions = connection.execute(
        """
        SELECT COUNT(*)
        FROM reconciliation_results

        WHERE verification_decision =
        'EXCEPTION'
        """
    ).fetchone()[0]


    connection.close()


    return {

        "total_transactions":
            total,

        "matched":
            matched,

        "review":
            review,

        "exceptions":
            exceptions,
    }


# ============================================================
# METRICS
# ============================================================

@app.get("/metrics")
def get_metrics():
    """Return reconciliation quality and control metrics.

    Precision/recall/F1 use a real binary reconciliation definition:
    a positive case has a ground-truth invoice; a positive prediction is
    a final MATCHED decision.  This avoids reporting accuracy as recall.
    """
    connection = get_connection()

    rows = connection.execute(
        """
        SELECT
            r.matched_invoice,
            r.verification_decision,
            r.ai_decision,
            r.ai_invoice,
            r.review_status,
            r.review_decision,
            g.expected_invoice
        FROM reconciliation_results r
        LEFT JOIN ground_truth g
          ON r.transaction_id = g.transaction_id
        """
    ).fetchall()

    def norm(value):
        if value is None:
            return ""
        text = str(value).strip().upper()
        if text in {"", "NONE", "NAN", "NULL"}:
            return ""
        return text

    total = len(rows)
    ai_cases = sum(1 for r in rows if r["ai_decision"] is not None)
    ai_recommendations = sum(1 for r in rows if r["ai_decision"] == "MATCH")
    ai_reviews = sum(1 for r in rows if r["ai_decision"] == "REVIEW")
    guard_approved = sum(
        1 for r in rows
        if r["ai_decision"] == "MATCH"
        and r["verification_decision"] == "MATCHED"
    )
    ai_matches_blocked = sum(
        1 for r in rows
        if r["ai_decision"] == "MATCH"
        and r["verification_decision"] != "MATCHED"
    )

    expected_positive = []
    expected_negative = []
    for r in rows:
        if norm(r["expected_invoice"]):
            expected_positive.append(r)
        else:
            expected_negative.append(r)

    true_positive = sum(
        1 for r in expected_positive
        if r["verification_decision"] == "MATCHED"
        and norm(r["matched_invoice"]) == norm(r["expected_invoice"])
    )

    false_negative = sum(
        1 for r in expected_positive
        if not (
            r["verification_decision"] == "MATCHED"
            and norm(r["matched_invoice"]) == norm(r["expected_invoice"])
        )
    )

    false_positive = sum(
        1 for r in expected_negative
        if r["verification_decision"] == "MATCHED"
    ) + sum(
        1 for r in expected_positive
        if r["verification_decision"] == "MATCHED"
        and norm(r["matched_invoice"]) != norm(r["expected_invoice"])
    )

    true_negative = sum(
        1 for r in expected_negative
        if r["verification_decision"] != "MATCHED"
    )

    accuracy = (
        (true_positive + true_negative) / total * 100
        if total else 0
    )
    precision = (
        true_positive / (true_positive + false_positive) * 100
        if true_positive + false_positive else 0
    )
    recall = (
        true_positive / (true_positive + false_negative) * 100
        if true_positive + false_negative else 0
    )
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall else 0
    )

    deterministic_correct = sum(
        1 for r in rows
        if norm(r["matched_invoice"]) == norm(r["expected_invoice"])
        and norm(r["expected_invoice"])
    )
    deterministic_accuracy = (
        deterministic_correct / len(expected_positive) * 100
        if expected_positive else 0
    )

    ai_match_rate = (
        ai_recommendations / ai_cases * 100
        if ai_cases else 0
    )

    ai_match_rows = [r for r in rows if r["ai_decision"] == "MATCH"]
    ai_correct = sum(
        1 for r in ai_match_rows
        if norm(r["ai_invoice"])
        == norm(r["expected_invoice"])
    )
    ai_recommendation_accuracy = (
        ai_correct / len(ai_match_rows) * 100
        if ai_match_rows else 0
    )

    final_matched = sum(
        1 for r in rows
        if r["verification_decision"] == "MATCHED"
    )
    review = sum(
        1 for r in rows
        if r["verification_decision"] == "REVIEW"
    )
    exceptions = sum(
        1 for r in rows
        if r["verification_decision"] == "EXCEPTION"
    )

    guard_correct = sum(
        1 for r in rows
        if r["ai_decision"] == "MATCH"
        and r["verification_decision"] == "MATCHED"
        and norm(r["ai_invoice"])
        == norm(r["expected_invoice"])
    )
    guard_approval_accuracy = (
        guard_correct / guard_approved * 100
        if guard_approved else 0
    )

    human_reviewed = sum(1 for r in rows if r["review_status"] == "COMPLETED")
    human_approved = sum(1 for r in rows if r["review_decision"] == "APPROVE")
    human_rejected = sum(1 for r in rows if r["review_decision"] == "REJECT")
    human_unresolved = sum(1 for r in rows if r["review_decision"] == "UNRESOLVED")

    connection.close()

    return {
        "deterministic_accuracy": round(deterministic_accuracy, 2),
        "accuracy": round(accuracy, 2),
        "precision": round(precision, 2),
        "recall": round(recall, 2),
        "f1": round(f1, 2),
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "true_negative": true_negative,
        "ai_cases": ai_cases,
        "ai_recommendations": ai_recommendations,
        "ai_match_rate": round(ai_match_rate, 2),
        "ai_review_recommendations": ai_reviews,
        "ai_recommendation_accuracy": round(ai_recommendation_accuracy, 2),
        "guard_approved": guard_approved,
        "ai_matches_blocked": ai_matches_blocked,
        "guard_approval_accuracy": round(guard_approval_accuracy, 2),
        "final_match_rate": round(final_matched / total * 100, 2) if total else 0,
        "final_matched": final_matched,
        "review": review,
        "exceptions": exceptions,
        "human_reviewed": human_reviewed,
        "human_approved": human_approved,
        "human_rejected": human_rejected,
        "human_unresolved": human_unresolved,
    }

# ============================================================
# BENCHMARK
# ============================================================

@app.get("/benchmark")
def get_benchmark():
    """Expose the latest measured Track 04 benchmark when available."""
    benchmark_path = (
        PROJECT_ROOT
        / "data"
        / "results"
        / "final_benchmark_results.csv"
    )

    if not benchmark_path.exists():
        return {"available": False}

    frame = pd.read_csv(benchmark_path)
    total = len(frame)
    matched = int((frame["final_status"] == "MATCHED").sum())
    review = int((frame["final_status"] == "REVIEW").sum())
    exceptions = int((frame["final_status"] == "EXCEPTION").sum())
    correct = int(frame["correct"].astype(bool).sum())

    return {
        "available": True,
        "records": total,
        "matched": matched,
        "review": review,
        "exceptions": exceptions,
        "match_rate": round(matched / total * 100, 2) if total else 0,
        "accuracy": round(correct / total * 100, 2) if total else 0,
        "incorrect_automatic": int(
            ((frame["final_status"] == "MATCHED") & (~frame["correct"].astype(bool))).sum()
        ),
        "ai_processed": int(frame["ai_decision"].notna().sum()) if "ai_decision" in frame else 0,
        "ai_matches": int((frame["ai_decision"] == "MATCH").sum()) if "ai_decision" in frame else 0,
        "guard_verified": int((frame["resolution"] == "AI_GUARD_VERIFIED").sum()) if "resolution" in frame else 0,
    }

# ============================================================
# AI INSIGHTS
# ============================================================


@app.get("/ai-insights")
def get_ai_insights():

    connection = get_connection()

    rows = connection.execute(
        """
        SELECT

            t.transaction_id,
            t.date,
            t.counterparty,
            t.amount,
            t.currency,

            r.matched_invoice,
            r.match_score,
            r.deterministic_status,

            r.ai_decision,
            r.ai_invoice,
            r.ai_confidence,
            r.ai_reason,
            r.ai_risk,

            r.verification_decision,
            r.verification_reason

        FROM transactions t

        INNER JOIN reconciliation_results r

        ON t.transaction_id =
           r.transaction_id

        WHERE r.ai_decision IS NOT NULL

        ORDER BY t.transaction_id
        """
    ).fetchall()

    connection.close()

    return [
        dict(row)
        for row in rows
    ]

@app.get("/verification")
def get_verification_data():
    connection = get_connection()

    rows = connection.execute("""
        SELECT
            t.transaction_id,
            t.date,
            t.counterparty,
            t.amount,
            t.currency,

            r.matched_invoice,
            r.match_score,
            r.deterministic_status,

            r.ai_decision,
            r.ai_invoice,
            r.ai_confidence,
            r.ai_reason,
            r.ai_risk,

            r.verification_decision,
            r.verification_reason,
            r.verification_checks,

            r.review_status,
            r.review_decision,
            r.reviewer_note,
            r.reviewed_at

        FROM transactions t
        INNER JOIN reconciliation_results r
            ON t.transaction_id = r.transaction_id

        ORDER BY t.transaction_id
    """).fetchall()

    connection.close()

    results = []

    for row in rows:
        item = dict(row)

        # verification_checks is stored as a Python dictionary string.
        # literal_eval safely converts that string back into a dictionary.
        raw_checks = item.get("verification_checks")

        if raw_checks:
            try:
                item["verification_checks"] = ast.literal_eval(raw_checks)
            except (ValueError, SyntaxError):
                item["verification_checks"] = {
                    "raw": raw_checks
                }
        else:
            item["verification_checks"] = {}

        results.append(item)

    return results


# ============================================================
# ALL TRANSACTIONS
# ============================================================

@app.get("/transactions")
def get_transactions():

    connection = get_connection()


    rows = connection.execute(
        """
        SELECT

            t.transaction_id,
            t.date,
            t.counterparty,
            t.amount,
            t.currency,
            t.original_data,

            r.matched_invoice,
            r.match_score,
            r.deterministic_status,

            r.ai_decision,
            r.ai_invoice,
            r.ai_confidence,
            r.ai_risk,

            r.verification_decision,
            r.verification_reason,

            r.review_status,
            r.review_decision,
            r.reviewer_note,
            r.reviewed_at

        FROM transactions t

        LEFT JOIN
        reconciliation_results r

        ON t.transaction_id =
           r.transaction_id

        ORDER BY
            t.transaction_id
        """
    ).fetchall()


    connection.close()


    results = []
    for row in rows:
        item = dict(row)
        for k, v in item.items():
            if isinstance(v, float) and (pd.isna(v) or v != v):
                item[k] = None
        item["bank_fields"] = decode_original_fields(
            item.pop("original_data", None)
        )
        results.append(item)
    return results


# ============================================================
# SINGLE TRANSACTION
# ============================================================

@app.get("/transactions/{transaction_id}")
def get_transaction(
    transaction_id: str
):

    connection = get_connection()


    row = connection.execute(
        """
        SELECT

            t.transaction_id,
            t.date,
            t.counterparty,
            t.amount,
            t.currency,
            t.original_data,

            r.matched_invoice,
            r.match_score,
            r.deterministic_status,
            r.reason,

            r.ai_decision,
            r.ai_invoice,
            r.ai_confidence,
            r.ai_reason,
            r.ai_risk,

            r.verification_decision,
            r.verification_reason,
            r.verification_checks,

            r.review_status,
            r.review_decision,
            r.reviewer_note,
            r.reviewed_at

        FROM transactions t

        LEFT JOIN
        reconciliation_results r

        ON t.transaction_id =
           r.transaction_id

        WHERE t.transaction_id = ?
        """,

        (transaction_id,)
    ).fetchone()


    connection.close()


    if row is None:

        raise HTTPException(
            status_code=404,
            detail="Transaction not found"
        )


    result = dict(row)
    for k, v in result.items():
        if isinstance(v, float) and (pd.isna(v) or v != v):
            result[k] = None
    result["bank_fields"] = decode_original_fields(
        result.pop("original_data", None)
    )

    if result.get("matched_invoice"):
        erp_connection = get_connection()
        erp_row = erp_connection.execute(
            "SELECT original_data FROM erp_records WHERE invoice_id = ?",
            (result["matched_invoice"],),
        ).fetchone()
        erp_connection.close()
        if erp_row:
            result["erp_fields"] = decode_original_fields(
                erp_row["original_data"]
            )
    else:
        result["erp_fields"] = {}
    return result


# ============================================================
# EXCEPTIONS
# ============================================================

@app.get("/exceptions")
def get_exceptions():

    connection = get_connection()


    rows = connection.execute(
        """
        SELECT *

        FROM reconciliation_results

        WHERE verification_decision
        IN ('REVIEW', 'EXCEPTION')
        AND COALESCE(review_status, '') != 'COMPLETED'

        ORDER BY transaction_id
        """
    ).fetchall()


    connection.close()


    return [
        dict(row)
        for row in rows
    ]


# ============================================================
# HUMAN REVIEW
# ============================================================

@app.post(
    "/transactions/{transaction_id}/review"
)
def review_transaction(

    transaction_id: str,

    review: ReviewRequest

):

    allowed_decisions = {

        "APPROVE",

        "REJECT",

        "UNRESOLVED",
    }


    decision = (
        review.decision
        .upper()
        .strip()
    )


    # --------------------------------------------------------
    # Validate decision
    # --------------------------------------------------------

    if decision not in allowed_decisions:

        raise HTTPException(

            status_code=400,

            detail=(
                "Invalid decision. "
                "Use APPROVE, REJECT, "
                "or UNRESOLVED."
            )
        )


    connection = get_connection()


    existing = connection.execute(
        """
        SELECT *

        FROM reconciliation_results

        WHERE transaction_id = ?
        """,

        (transaction_id,)
    ).fetchone()


    if existing is None:

        connection.close()

        raise HTTPException(

            status_code=404,

            detail=(
                "Transaction reconciliation "
                "result not found"
            )
        )


    # --------------------------------------------------------
    # Convert human decision
    # --------------------------------------------------------

    if decision == "APPROVE":

        final_decision = "MATCHED"


    elif decision == "REJECT":

        final_decision = "EXCEPTION"


    else:

        final_decision = "REVIEW"


    # --------------------------------------------------------
    # Save human review
    # --------------------------------------------------------

    connection.execute(
        """
        UPDATE reconciliation_results

        SET

            verification_decision = ?,

            review_status =
                'COMPLETED',

            review_decision = ?,

            reviewer_note = ?,

            reviewed_at =
                CURRENT_TIMESTAMP,

            updated_at =
                CURRENT_TIMESTAMP

        WHERE transaction_id = ?
        """,

        (

            final_decision,

            decision,

            review.note.strip(),

            transaction_id,
        )
    )


    connection.commit()

    connection.close()


    return {

        "status":
            "completed",

        "transaction_id":
            transaction_id,

        "review_decision":
            decision,

        "final_decision":
            final_decision,
    }


# ============================================================
# RUN RECONCILIATION
# ============================================================

@app.post("/reconcile/validate")
async def validate_reconciliation_upload(
    bank_file: UploadFile = File(...),
    erp_file: Optional[UploadFile] = File(None),
    supporting_files: Optional[List[UploadFile]] = File(None),
):
    _, bank_info = await read_uploaded_records(
        bank_file,
        REQUIRED_BANK_COLUMNS,
    )

    uploads = []
    if supporting_files:
        uploads.extend([item for item in supporting_files if item is not None])
    if erp_file is not None:
        uploads.append(erp_file)

    if not uploads:
        erp_info = {
            "filename": "",
            "records": 0,
            "columns": [],
            "valid": False,
            "errors": ["Upload at least one supporting document."],
            "warnings": [],
        }
    elif len(uploads) == 1:
        _, erp_info = await read_uploaded_records(
            uploads[0],
            REQUIRED_ERP_COLUMNS,
        )
    else:
        _, erp_info = await read_supporting_uploads(uploads)

    return {
        "valid": bank_info["valid"] and erp_info["valid"],
        "bank": bank_info,
        "erp": erp_info,
    }


@app.post("/reconcile/upload")
async def reconcile_uploaded_batch(
    bank_file: UploadFile = File(...),
    erp_file: Optional[UploadFile] = File(None),
    supporting_files: Optional[List[UploadFile]] = File(None),
):
    bank, bank_info = await read_uploaded_records(
        bank_file,
        REQUIRED_BANK_COLUMNS,
    )

    uploads = []
    if supporting_files:
        uploads.extend([item for item in supporting_files if item is not None])
    if erp_file is not None:
        uploads.append(erp_file)

    if not uploads:
        erp = None
        erp_info = {
            "filename": "",
            "records": 0,
            "columns": [],
            "valid": False,
            "errors": ["Upload at least one supporting document."],
            "warnings": [],
        }
    elif len(uploads) == 1:
        erp, erp_info = await read_uploaded_records(
            uploads[0],
            REQUIRED_ERP_COLUMNS,
        )
    else:
        erp, erp_info = await read_supporting_uploads(uploads)

    if (
        not bank_info["valid"]
        or not erp_info["valid"]
        or bank is None
        or erp is None
    ):
        raise HTTPException(
            status_code=422,
            detail={"bank": bank_info, "erp": erp_info},
        )

    initialize_database()
    replace_active_batch(bank, erp)
    result = run_reconciliation(bank, erp)
    return {
        "status": "completed",
        "bank": bank_info,
        "erp": erp_info,
        **result,
    }


@app.post("/reconcile")
def reconcile():

    result = run_reconciliation()


    return {

        "status":
            "completed",

        **result,
    }