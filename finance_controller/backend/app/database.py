import sqlite3
import json
from pathlib import Path

import pandas as pd


# ============================================================
# PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATABASE_PATH = PROJECT_ROOT / "data" / "finance_controller.db"

BANK_PATH = PROJECT_ROOT / "data" / "raw" / "bank.csv"

ERP_PATH = PROJECT_ROOT / "data" / "raw" / "erp.csv"

VERIFICATION_PATH = (
    PROJECT_ROOT / "data" / "raw" / "verification.csv"
)


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_connection():

    DATABASE_PATH.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    connection = sqlite3.connect(
        DATABASE_PATH
    )

    connection.row_factory = sqlite3.Row

    return connection


# ============================================================
# INITIALIZE DATABASE
# ============================================================

def initialize_database():

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
            currency TEXT,
            original_data TEXT
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
            currency TEXT,
            original_data TEXT
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

            review_status TEXT,
            review_decision TEXT,
            reviewer_note TEXT,
            reviewed_at TEXT,

            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (transaction_id)
                REFERENCES transactions(transaction_id)
        )
        """
    )


    # ========================================================
    # DATABASE MIGRATION
    # ========================================================

    columns = {
        row[1]
        for row in cursor.execute(
            "PRAGMA table_info(reconciliation_results)"
        ).fetchall()
    }


    # --------------------------------------------------------
    # Updated timestamp
    # --------------------------------------------------------

    if "updated_at" not in columns:

        cursor.execute(
            """
            ALTER TABLE reconciliation_results
            ADD COLUMN updated_at TEXT
            """
        )

        cursor.execute(
            """
            UPDATE reconciliation_results
            SET updated_at = CURRENT_TIMESTAMP
            WHERE updated_at IS NULL
            """
        )


    # --------------------------------------------------------
    # Human review status
    # --------------------------------------------------------

    if "review_status" not in columns:

        cursor.execute(
            """
            ALTER TABLE reconciliation_results
            ADD COLUMN review_status TEXT
            """
        )


    # --------------------------------------------------------
    # Human review decision
    # --------------------------------------------------------

    if "review_decision" not in columns:

        cursor.execute(
            """
            ALTER TABLE reconciliation_results
            ADD COLUMN review_decision TEXT
            """
        )


    # --------------------------------------------------------
    # Reviewer note
    # --------------------------------------------------------

    if "reviewer_note" not in columns:

        cursor.execute(
            """
            ALTER TABLE reconciliation_results
            ADD COLUMN reviewer_note TEXT
            """
        )


    # --------------------------------------------------------
    # Review timestamp
    # --------------------------------------------------------

    if "reviewed_at" not in columns:

        cursor.execute(
            """
            ALTER TABLE reconciliation_results
            ADD COLUMN reviewed_at TEXT
            """
        )

    table_columns = {
        row[1]
        for row in cursor.execute(
            "PRAGMA table_info(transactions)"
        ).fetchall()
    }
    if "original_data" not in table_columns:
        cursor.execute(
            "ALTER TABLE transactions ADD COLUMN original_data TEXT"
        )

    erp_columns = {
        row[1]
        for row in cursor.execute(
            "PRAGMA table_info(erp_records)"
        ).fetchall()
    }
    if "original_data" not in erp_columns:
        cursor.execute(
            "ALTER TABLE erp_records ADD COLUMN original_data TEXT"
        )


    connection.commit()

    connection.close()


# ============================================================
# SEED DATABASE
# ============================================================

def seed_database():

    bank = pd.read_csv(BANK_PATH)

    erp = pd.read_csv(ERP_PATH)

    verification = pd.read_csv(
        VERIFICATION_PATH
    )

    connection = get_connection()


    # --------------------------------------------------------
    # Bank data
    # --------------------------------------------------------

    for _, row in bank.iterrows():

        connection.execute(
            """
            INSERT OR REPLACE INTO transactions
            (
                transaction_id,
                date,
                counterparty,
                amount,
                currency,
                original_data
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(row["transaction_id"]),
                str(row["date"]),
                str(row["counterparty"]),
                float(row["amount"]),
                str(row.get("currency", "INR")),
                json.dumps(row.to_dict(), default=str),
            ),
        )


    # --------------------------------------------------------
    # ERP data
    # --------------------------------------------------------

    for _, row in erp.iterrows():

        connection.execute(
            """
            INSERT OR REPLACE INTO erp_records
            (
                invoice_id,
                reference,
                date,
                vendor,
                amount,
                currency,
                original_data
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(row["invoice_id"]),
                str(row["reference"]),
                str(row["date"]),
                str(row["vendor"]),
                float(row["amount"]),
                str(row.get("currency", "INR")),
                json.dumps(row.to_dict(), default=str),
            ),
        )


    # --------------------------------------------------------
    # Ground truth
    # --------------------------------------------------------

    for _, row in verification.iterrows():

        connection.execute(
            """
            INSERT OR REPLACE INTO ground_truth
            (
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
# LOAD BANK DATA
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


    data = pd.DataFrame(
        [dict(row) for row in rows]
    )


    if not data.empty:

        data["date"] = pd.to_datetime(
            data["date"]
        )


    return data


# ============================================================
# LOAD ERP DATA
# ============================================================

def load_erp_data():

    connection = get_connection()

    rows = connection.execute(
        """
        SELECT *
        FROM erp_records
        """
    ).fetchall()

    connection.close()


    data = pd.DataFrame(
        [dict(row) for row in rows]
    )


    if not data.empty:

        data["date"] = pd.to_datetime(
            data["date"]
        )


    return data


def replace_active_batch(bank, erp):
    """Replace the active input batch while retaining all row fields."""
    connection = get_connection()
    connection.execute("DELETE FROM reconciliation_results")
    connection.execute("DELETE FROM transactions")
    connection.execute("DELETE FROM erp_records")
    connection.execute("DELETE FROM ground_truth")

    for _, row in bank.iterrows():
        connection.execute(
            """INSERT INTO transactions
            (transaction_id, date, counterparty, amount, currency, original_data)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (
                str(row["transaction_id"]), str(row["date"]),
                str(row.get("counterparty", "")), float(row["amount"]),
                str(row.get("currency", "INR")),
                json.dumps(row.to_dict(), default=str),
            ),
        )

    for _, row in erp.iterrows():
        connection.execute(
            """INSERT INTO erp_records
            (invoice_id, reference, date, vendor, amount, currency, original_data)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                str(row["invoice_id"]), str(row.get("reference", "")),
                str(row["date"]), str(row.get("vendor", "")),
                float(row["amount"]), str(row.get("currency", "INR")),
                json.dumps(row.to_dict(), default=str),
            ),
        )

    connection.commit()
    connection.close()