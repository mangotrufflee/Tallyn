import sqlite3
from pathlib import Path
import sys

import pandas as pd

from fastapi import FastAPI, HTTPException

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from src.reconciliation.matcher import (
    find_best_match,
    find_top_candidates,
    classify_match,
    get_exception_reason,
)

from src.ai.ai_reasoner import (
    build_ai_prompt,
    ask_ai,
    validate_ai_response,
)

from src.reconciliation.verification_guard import (
    verify_ai_match,
    get_final_decision,
    verify_selected_candidate,
)


# ============================================================
# CONFIGURATION
# ============================================================

DATABASE_PATH = project_root / "data" / "finance_controller.db"

BANK_PATH = project_root / "data" / "bank.csv"
ERP_PATH = project_root / "data" / "erp.csv"
VERIFICATION_PATH = project_root / "data" / "verification.csv"


# ============================================================
# FASTAPI APPLICATION
# ============================================================

app = FastAPI(
    title="AI Finance Controller",
    description="AI-assisted financial reconciliation system",
    version="1.0.0",
)


# ============================================================
# DATABASE
# ============================================================

def get_connection():
    """
    Opens a connection to the SQLite database.
    """

    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(
        DATABASE_PATH
    )

    connection.row_factory = sqlite3.Row

    return connection


def initialize_database():
    """
    Creates the SQLite tables if they do not already exist.
    """

    connection = get_connection()

    cursor = connection.cursor()

    # --------------------------------------------------------
    # Bank transactions
    # --------------------------------------------------------

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS transactions (

            transaction_id TEXT PRIMARY KEY,

            date TEXT NOT NULL,

            counterparty TEXT,

            amount REAL,

            currency TEXT
        )
        """
    )

    # --------------------------------------------------------
    # ERP records
    # --------------------------------------------------------

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS erp_records (

            invoice_id TEXT PRIMARY KEY,

            reference TEXT,

            date TEXT,

            vendor TEXT,

            amount REAL,

            currency TEXT
        )
        """
    )

    # --------------------------------------------------------
    # Ground truth
    # --------------------------------------------------------

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS ground_truth (

            transaction_id TEXT PRIMARY KEY,

            expected_invoice TEXT
        )
        """
    )

    # --------------------------------------------------------
    # Reconciliation results
    # --------------------------------------------------------

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS reconciliation_results (

            transaction_id TEXT PRIMARY KEY,

            matched_invoice TEXT,

            match_score REAL,

            deterministic_status TEXT,

            reason TEXT,

            ai_decision TEXT,

            ai_invoice TEXT,

            ai_confidence REAL,

            ai_reason TEXT,

            ai_risk TEXT,

            verification_decision TEXT,

            verification_reason TEXT,

            verification_checks TEXT,

            FOREIGN KEY (
                transaction_id
            )
            REFERENCES transactions(transaction_id)
        )
        """
    )

    connection.commit()

    connection.close()


# ============================================================
# LOAD CSV DATA INTO SQLITE
# ============================================================

def seed_database():
    """
    Loads the existing CSV datasets into SQLite.
    """

    bank = pd.read_csv(
        BANK_PATH
    )

    erp = pd.read_csv(
        ERP_PATH
    )

    verification = pd.read_csv(
        VERIFICATION_PATH
    )

    connection = get_connection()

    # --------------------------------------------------------
    # Transactions
    # --------------------------------------------------------

    for _, row in bank.iterrows():

        cursor = connection.cursor()

        cursor.execute(
            """
            INSERT OR REPLACE INTO transactions (
                transaction_id,
                date,
                counterparty,
                amount,
                currency
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                str(row["transaction_id"]),
                str(row["date"]),
                str(row["counterparty"]),
                float(row["amount"]),
                str(row.get("currency", "INR")),
            ),
        )

    # --------------------------------------------------------
    # ERP records
    # --------------------------------------------------------

    for _, row in erp.iterrows():

        cursor = connection.cursor()

        cursor.execute(
            """
            INSERT OR REPLACE INTO erp_records (
                invoice_id,
                reference,
                date,
                vendor,
                amount,
                currency
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(row["invoice_id"]),
                str(row["reference"]),
                str(row["date"]),
                str(row["vendor"]),
                float(row["amount"]),
                str(row.get("currency", "INR")),
            ),
        )

    # --------------------------------------------------------
    # Ground truth
    # --------------------------------------------------------

    for _, row in verification.iterrows():

        cursor = connection.cursor()

        cursor.execute(
            """
            INSERT OR REPLACE INTO ground_truth (
                transaction_id,
                expected_invoice
            )
            VALUES (?, ?)
            """,
            (
                str(row["transaction_id"]),
                str(row["expected_invoice"]),
            ),
        )

    connection.commit()

    connection.close()


# ============================================================
# LOAD DATA FROM DATABASE
# ============================================================

def load_bank_data():

    connection = get_connection()

    rows = connection.execute(
        """
        SELECT *
        FROM transactions
        """
    ).fetchall()

    connection.close()

    data = pd.DataFrame([dict(row) for row in rows])
    if not data.empty:
        data["date"] = pd.to_datetime(data["date"])
    return data


def load_erp_data():

    connection = get_connection()

    rows = connection.execute(
        """
        SELECT *
        FROM erp_records
        """
    ).fetchall()

    connection.close()

    data = pd.DataFrame([dict(row) for row in rows])
    if not data.empty:
        data["date"] = pd.to_datetime(data["date"])
    return data


# ============================================================
# AI + VERIFICATION
# ============================================================

def run_ai_on_transaction(
    bank_row,
    erp
):
    """
    Runs AI reasoning and then independently verifies
    the AI recommendation.
    """

    # --------------------------------------------------------
    # Find candidates
    # --------------------------------------------------------

    candidates = find_top_candidates(
        bank_row,
        erp,
        top_n=5
    )

    # --------------------------------------------------------
    # Build AI prompt
    # --------------------------------------------------------

    prompt = build_ai_prompt(
        bank_row,
        candidates
    )

    # --------------------------------------------------------
    # Ask AI
    # --------------------------------------------------------

    raw_response = ask_ai(
        prompt
    )

    # --------------------------------------------------------
    # Validate AI response
    # --------------------------------------------------------

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
            "verification_decision": "EXCEPTION",
            "verification_reason": "Invalid AI response",
            "verification_checks": None,
        }

    result = validation["result"]

    ai_decision = result["decision"]
    ai_invoice = result["selected_invoice"]

    # --------------------------------------------------------
    # AI did not select an invoice
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
                "AI could not confidently select a candidate"
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

    # --------------------------------------------------------
    # Verify AI selected invoice belongs to candidates
    # --------------------------------------------------------

    candidate_is_valid = verify_selected_candidate(
        ai_invoice,
        candidates
    )

    if not candidate_is_valid:

        return {
            "ai_decision": ai_decision,
            "ai_invoice": ai_invoice,
            "ai_confidence": result["confidence"],
            "ai_reason": result["reason"],
            "ai_risk": "HIGH",
            "verification_decision": "EXCEPTION",
            "verification_reason": (
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
        == str(ai_invoice).strip()
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
        "ai_decision": ai_decision,
        "ai_invoice": ai_invoice,
        "ai_confidence": result["confidence"],
        "ai_reason": result["reason"],
        "ai_risk": result["risk"],
        "verification_decision": verification_decision,
        "verification_reason": None,
        "verification_checks": str(
            verification_checks
        ),
    }


# ============================================================
# RECONCILIATION ENGINE
# ============================================================

def run_reconciliation():
    """
    Runs reconciliation across the entire bank dataset.

    Deterministic matching is performed first.
    Only WARNING and EXCEPTION records go to AI.
    """

    bank = load_bank_data()

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
            "transaction_id": bank_row["transaction_id"],
            "matched_invoice": invoice_id,
            "match_score": score,
            "deterministic_status": status,
            "reason": reason,
        })

    deterministic_df = pd.DataFrame(
        deterministic_results
    )

    # --------------------------------------------------------
    # AI gate
    # --------------------------------------------------------

    uncertain = deterministic_df[
        deterministic_df["deterministic_status"].isin(
            ["WARNING", "EXCEPTION"]
        )
    ]

    # --------------------------------------------------------
    # Run AI
    # --------------------------------------------------------

    ai_results = []

    for _, row in uncertain.iterrows():

        transaction_id = row["transaction_id"]

        bank_row = bank[
            bank["transaction_id"].astype(str)
            == str(transaction_id)
        ].iloc[0]

        ai_result = run_ai_on_transaction(
            bank_row,
            erp
        )

        ai_results.append({
            "transaction_id": transaction_id,
            **ai_result,
        })

    ai_df = pd.DataFrame(
        ai_results
    )

    # --------------------------------------------------------
    # Save to database
    # --------------------------------------------------------

    connection = get_connection()

    for _, row in deterministic_df.iterrows():

        ai_row = None

        if not ai_df.empty:

            matching_ai = ai_df[
                ai_df["transaction_id"].astype(str)
                == str(row["transaction_id"])
            ]

            if not matching_ai.empty:

                ai_row = matching_ai.iloc[0]

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

        else:

            ai_decision = ai_row["ai_decision"]
            ai_invoice = ai_row["ai_invoice"]
            ai_confidence = ai_row["ai_confidence"]
            ai_reason = ai_row["ai_reason"]
            ai_risk = ai_row["ai_risk"]
            verification_decision = (
                ai_row["verification_decision"]
            )
            verification_reason = ai_row.get(
                "verification_reason",
                None
            )
            verification_checks = ai_row.get(
                "verification_checks",
                None
            )

        connection.execute(
            """
            INSERT OR REPLACE INTO reconciliation_results (

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
                verification_checks

            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        "total_transactions": len(bank),
        "deterministic_uncertain": len(uncertain),
        "ai_processed": len(ai_df),
    }


# ============================================================
# FASTAPI STARTUP
# ============================================================

@app.on_event("startup")
def startup():

    initialize_database()

    # Seed only if the transaction table is empty

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
# API ROUTES
# ============================================================

@app.get("/")
def root():

    return {
        "application": "AI Finance Controller",
        "status": "running",
        "version": "1.0.0",
    }


# ------------------------------------------------------------
# Summary
# ------------------------------------------------------------

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
        WHERE verification_decision = 'MATCHED'
        """
    ).fetchone()[0]

    review = connection.execute(
        """
        SELECT COUNT(*)
        FROM reconciliation_results
        WHERE verification_decision = 'REVIEW'
        """
    ).fetchone()[0]

    exceptions = connection.execute(
        """
        SELECT COUNT(*)
        FROM reconciliation_results
        WHERE verification_decision = 'EXCEPTION'
        """
    ).fetchone()[0]

    connection.close()

    return {
        "total_transactions": total,
        "matched": matched,
        "review": review,
        "exceptions": exceptions,
    }


# ------------------------------------------------------------
# Transactions
# ------------------------------------------------------------

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

            r.matched_invoice,
            r.match_score,
            r.deterministic_status,
            r.ai_decision,
            r.ai_invoice,
            r.ai_confidence,
            r.ai_risk,
            r.verification_decision,
            r.verification_reason

        FROM transactions t

        LEFT JOIN reconciliation_results r
        ON t.transaction_id = r.transaction_id

        ORDER BY t.transaction_id
        """
    ).fetchall()

    connection.close()

    return [
        dict(row)
        for row in rows
    ]


# ------------------------------------------------------------
# Single transaction
# ------------------------------------------------------------

@app.get("/transactions/{transaction_id}")
def get_transaction(transaction_id: str):

    connection = get_connection()

    row = connection.execute(
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
            r.reason,
            r.ai_decision,
            r.ai_invoice,
            r.ai_confidence,
            r.ai_reason,
            r.ai_risk,
            r.verification_decision,
            r.verification_reason,
            r.verification_checks

        FROM transactions t

        LEFT JOIN reconciliation_results r
        ON t.transaction_id = r.transaction_id

        WHERE t.transaction_id = ?
        """,
        (transaction_id,),
    ).fetchone()

    connection.close()

    if row is None:

        raise HTTPException(
            status_code=404,
            detail="Transaction not found",
        )

    return dict(row)


# ------------------------------------------------------------
# Exceptions
# ------------------------------------------------------------

@app.get("/exceptions")
def get_exceptions():

    connection = get_connection()

    rows = connection.execute(
        """
        SELECT *
        FROM reconciliation_results

        WHERE verification_decision
        IN ('REVIEW', 'EXCEPTION')

        ORDER BY transaction_id
        """
    ).fetchall()

    connection.close()

    return [
        dict(row)
        for row in rows
    ]


# ------------------------------------------------------------
# Run reconciliation
# ------------------------------------------------------------

@app.post("/reconcile")
def reconcile():

    result = run_reconciliation()

    return {
        "status": "completed",
        **result,
    }