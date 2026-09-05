from pathlib import Path
from io import BytesIO
import json

import pandas as pd

from fastapi import FastAPI, HTTPException, File, UploadFile
from pydantic import BaseModel

from fastapi.middleware.cors import CORSMiddleware
import ast


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
    ask_ai,
    validate_ai_response,
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
        return json.loads(value)
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


async def read_uploaded_records(upload: UploadFile, required_columns):
    filename = upload.filename or ""
    suffix = Path(filename).suffix.lower()
    if suffix not in {".csv", ".xlsx", ".xls"}:
        return None, {
            "filename": filename,
            "valid": False,
            "errors": ["Supported formats are CSV, XLSX, and XLS."],
        }

    contents = await upload.read()
    try:
        if suffix == ".csv":
            frame = pd.read_csv(BytesIO(contents))
        else:
            frame = pd.read_excel(BytesIO(contents))
    except Exception as exc:
        return None, {
            "filename": filename,
            "valid": False,
            "errors": [f"File could not be read: {exc}"],
        }

    errors = []
    missing = sorted(required_columns - set(frame.columns))
    if missing:
        errors.append(f"Missing required columns: {', '.join(missing)}")
    if frame.empty:
        errors.append("The file contains no records.")
    if "amount" in frame:
        amounts = pd.to_numeric(frame["amount"], errors="coerce")
        invalid_amounts = amounts.isna().sum()
        if invalid_amounts:
            errors.append(f"{invalid_amounts} amount value(s) are not numeric.")
    if "date" in frame:
        dates = pd.to_datetime(frame["date"], errors="coerce")
        invalid_dates = dates.isna().sum()
        if invalid_dates:
            errors.append(f"{invalid_dates} date value(s) are not parseable.")
    for column in required_columns & set(frame.columns):
        if frame[column].isna().any() or frame[column].astype(str).str.strip().eq("").any():
            errors.append(f"Column '{column}' contains blank required values.")

    identifier = "transaction_id" if "transaction_id" in frame else "invoice_id"
    if identifier in frame and frame[identifier].duplicated().any():
        duplicate_count = int(frame[identifier].duplicated().sum())
        errors.append(
            f"{duplicate_count} duplicate {identifier} value(s) found."
        )

    return frame, {
        "filename": filename,
        "records": len(frame),
        "columns": [str(column) for column in frame.columns],
        "valid": not errors,
        "errors": errors,
    }


# ============================================================
# AI + VERIFICATION
# ============================================================

def run_ai_on_transaction(
    bank_row,
    erp
):

    candidates = find_top_candidates(
        bank_row,
        erp,
        top_n=5
    )


    prompt = build_ai_prompt(
        bank_row,
        candidates
    )


    raw_response = ask_ai(
        prompt
    )


    validation = validate_ai_response(
        raw_response
    )


    # --------------------------------------------------------
    # Invalid AI response
    # --------------------------------------------------------

    if not validation["valid"]:

        return {

            "ai_decision": "EXCEPTION",

            "ai_invoice": None,

            "ai_confidence": 0,

            "ai_reason": validation["error"],

            "ai_risk": "HIGH",

            "verification_decision": "EXCEPTION",

            "verification_reason":
                "Invalid AI response",

            "verification_checks": None,
        }


    result = validation["result"]


    ai_decision = result["decision"]

    ai_invoice = result["selected_invoice"]


    # --------------------------------------------------------
    # AI did not select invoice
    # --------------------------------------------------------

    if not ai_invoice:

        if len(candidates) == 0:

            verification_decision = "EXCEPTION"

            verification_reason = (
                "No ERP candidates available"
            )

        else:

            verification_decision = "REVIEW"

            verification_reason = (
                "AI could not confidently select "
                "a candidate"
            )


        return {

            "ai_decision": ai_decision,

            "ai_invoice": None,

            "ai_confidence":
                result["confidence"],

            "ai_reason":
                result["reason"],

            "ai_risk":
                result["risk"],

            "verification_decision":
                verification_decision,

            "verification_reason":
                verification_reason,

            "verification_checks": None,
        }


    # --------------------------------------------------------
    # Verify candidate
    # --------------------------------------------------------

    candidate_is_valid = verify_selected_candidate(
        ai_invoice,
        candidates
    )


    if not candidate_is_valid:

        return {

            "ai_decision": ai_decision,

            "ai_invoice": ai_invoice,

            "ai_confidence":
                result["confidence"],

            "ai_reason":
                result["reason"],

            "ai_risk": "HIGH",

            "verification_decision":
                "EXCEPTION",

            "verification_reason":
                (
                    "AI selected an invoice outside "
                    "the candidate set"
                ),

            "verification_checks": None,
        }


    # --------------------------------------------------------
    # Find selected ERP record
    # --------------------------------------------------------

    selected_erp = None


    matches = erp[
        erp["invoice_id"]
        .astype(str)
        .str.strip()
        ==
        str(ai_invoice).strip()
    ]


    if not matches.empty:

        selected_erp = matches.iloc[0]


    # --------------------------------------------------------
    # Independent verification
    # --------------------------------------------------------

    verification_checks = verify_ai_match(
        bank_row,
        selected_erp
    )


    verification_decision = get_final_decision(
        verification_checks
    )


    return {

        "ai_decision":
            ai_decision,

        "ai_invoice":
            ai_invoice,

        "ai_confidence":
            result["confidence"],

        "ai_reason":
            result["reason"],

        "ai_risk":
            result["risk"],

        "verification_decision":
            verification_decision,

        "verification_reason":
            None,

        "verification_checks":
            str(verification_checks),
    }


# ============================================================
# RECONCILIATION ENGINE
# ============================================================

def run_reconciliation(bank=None, erp=None):

    if bank is None:
        bank = load_bank_data()

    if erp is None:
        erp = load_erp_data()


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

                row["matched_invoice"],

                float(row["match_score"]),

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

    connection = get_connection()


    # --------------------------------------------------------
    # Deterministic accuracy
    # --------------------------------------------------------

    deterministic_rows = connection.execute(
        """
        SELECT
            r.matched_invoice,
            g.expected_invoice

        FROM reconciliation_results r

        LEFT JOIN ground_truth g
        ON r.transaction_id =
           g.transaction_id

        WHERE g.expected_invoice
        IS NOT NULL
        """
    ).fetchall()


    deterministic_correct = 0


    for row in deterministic_rows:

        predicted = row[
            "matched_invoice"
        ]

        expected = row[
            "expected_invoice"
        ]


        if predicted is None:
            continue


        predicted = (
            str(predicted)
            .strip()
            .upper()
        )

        expected = (
            str(expected)
            .strip()
            .upper()
        )


        predicted = predicted.replace(
            "_DUP",
            ""
        )

        expected = expected.replace(
            "_DUP",
            ""
        )


        if predicted == expected:

            deterministic_correct += 1


    deterministic_accuracy = (

        deterministic_correct
        /
        len(deterministic_rows)
        *
        100

        if deterministic_rows
        else 0
    )


    # ========================================================
    # AI cases
    # ========================================================

    ai_cases = connection.execute(
        """
        SELECT COUNT(*)
        FROM reconciliation_results
        WHERE ai_decision IS NOT NULL
        """
    ).fetchone()[0]


    # ========================================================
    # AI recommendations
    # ========================================================

    ai_recommendations = connection.execute(
        """
        SELECT COUNT(*)
        FROM reconciliation_results
        WHERE ai_decision = 'MATCH'
        """
    ).fetchone()[0]


    # AI match rate
    ai_match_rate = (
        ai_recommendations
        / ai_cases
        * 100
        if ai_cases
        else 0
    )

    ai_review_recommendations = connection.execute(
        """
        SELECT COUNT(*)
        FROM reconciliation_results
        WHERE ai_decision = 'REVIEW'
        """
    ).fetchone()[0]

    ai_evaluation_rows = connection.execute(
        """
        SELECT r.ai_invoice, g.expected_invoice
        FROM reconciliation_results r
        JOIN ground_truth g ON r.transaction_id = g.transaction_id
        WHERE r.ai_decision = 'MATCH'
        """
    ).fetchall()

    ai_correct = sum(
        1
        for row in ai_evaluation_rows
        if row["ai_invoice"]
        and str(row["ai_invoice"]).strip().upper().replace("_DUP", "")
        == str(row["expected_invoice"]).strip().upper().replace("_DUP", "")
    )
    ai_recommendation_accuracy = (
        ai_correct / len(ai_evaluation_rows) * 100
        if ai_evaluation_rows
        else 0
    )


    # --------------------------------------------------------
    # Guard approved
    # --------------------------------------------------------

    guard_approved = connection.execute(
        """
        SELECT COUNT(*)

        FROM reconciliation_results

        WHERE ai_decision = 'MATCH'

        AND verification_decision =
        'MATCHED'
        """
    ).fetchone()[0]


    # --------------------------------------------------------
    # AI matches blocked
    # --------------------------------------------------------

    ai_matches_blocked = connection.execute(
        """
        SELECT COUNT(*)

        FROM reconciliation_results

        WHERE ai_decision = 'MATCH'

        AND verification_decision !=
        'MATCHED'
        """
    ).fetchone()[0]


    # --------------------------------------------------------
    # Guard approval accuracy
    # --------------------------------------------------------

    approved_rows = connection.execute(
        """
        SELECT
            r.ai_invoice,
            g.expected_invoice

        FROM reconciliation_results r

        LEFT JOIN ground_truth g
        ON r.transaction_id =
           g.transaction_id

        WHERE r.ai_decision = 'MATCH'

        AND r.verification_decision =
        'MATCHED'

        AND g.expected_invoice
        IS NOT NULL
        """
    ).fetchall()


    guard_correct = 0


    for row in approved_rows:

        predicted = row[
            "ai_invoice"
        ]

        expected = row[
            "expected_invoice"
        ]


        if predicted is None:
            continue


        predicted = (
            str(predicted)
            .strip()
            .upper()
            .replace("_DUP", "")
        )

        expected = (
            str(expected)
            .strip()
            .upper()
            .replace("_DUP", "")
        )


        if predicted == expected:

            guard_correct += 1


    guard_approval_accuracy = (

        guard_correct
        /
        len(approved_rows)
        *
        100

        if approved_rows
        else 0
    )


    # --------------------------------------------------------
    # Final match rate
    # --------------------------------------------------------

    total = connection.execute(
        """
        SELECT COUNT(*)
        FROM transactions
        """
    ).fetchone()[0]


    final_matched = connection.execute(
        """
        SELECT COUNT(*)

        FROM reconciliation_results

        WHERE verification_decision =
        'MATCHED'
        """
    ).fetchone()[0]

    human_reviewed = connection.execute(
        """
        SELECT COUNT(*)
        FROM reconciliation_results
        WHERE review_status = 'COMPLETED'
        """
    ).fetchone()[0]

    human_approved = connection.execute(
        """
        SELECT COUNT(*)
        FROM reconciliation_results
        WHERE review_decision = 'APPROVE'
        """
    ).fetchone()[0]

    human_rejected = connection.execute(
        """
        SELECT COUNT(*)
        FROM reconciliation_results
        WHERE review_decision = 'REJECT'
        """
    ).fetchone()[0]

    human_unresolved = connection.execute(
        """
        SELECT COUNT(*)
        FROM reconciliation_results
        WHERE review_decision = 'UNRESOLVED'
        """
    ).fetchone()[0]


    final_match_rate = (

        final_matched
        /
        total
        *
        100

        if total
        else 0
    )


    connection.close()


    return {
        "deterministic_accuracy":
            round(
                deterministic_accuracy,
                2
            ),

        "ai_cases":
            ai_cases,

        "ai_recommendations":
            ai_recommendations,

        "ai_match_rate":
            round(
                ai_match_rate,
                2
            ),

        "ai_review_recommendations": ai_review_recommendations,

        "ai_recommendation_accuracy": round(
            ai_recommendation_accuracy,
            2,
        ),

        "guard_approved":
            guard_approved,

        "ai_matches_blocked":
            ai_matches_blocked,

        "guard_approval_accuracy":
            round(
                guard_approval_accuracy,
                2
            ),

        "final_match_rate":
            round(
                final_match_rate,
                2
            ),

        "human_reviewed": human_reviewed,
        "human_approved": human_approved,
        "human_rejected": human_rejected,
        "human_unresolved": human_unresolved,
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
    erp_file: UploadFile = File(...),
):
    _, bank_info = await read_uploaded_records(
        bank_file,
        REQUIRED_BANK_COLUMNS,
    )
    _, erp_info = await read_uploaded_records(
        erp_file,
        REQUIRED_ERP_COLUMNS,
    )
    return {
        "valid": bank_info["valid"] and erp_info["valid"],
        "bank": bank_info,
        "erp": erp_info,
    }


@app.post("/reconcile/upload")
async def reconcile_uploaded_batch(
    bank_file: UploadFile = File(...),
    erp_file: UploadFile = File(...),
):
    bank, bank_info = await read_uploaded_records(
        bank_file,
        REQUIRED_BANK_COLUMNS,
    )
    erp, erp_info = await read_uploaded_records(
        erp_file,
        REQUIRED_ERP_COLUMNS,
    )
    if not bank_info["valid"] or not erp_info["valid"]:
        raise HTTPException(
            status_code=422,
            detail={"bank": bank_info, "erp": erp_info},
        )

    bank["date"] = pd.to_datetime(bank["date"])
    erp["date"] = pd.to_datetime(erp["date"])
    bank["amount"] = pd.to_numeric(bank["amount"])
    erp["amount"] = pd.to_numeric(erp["amount"])

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