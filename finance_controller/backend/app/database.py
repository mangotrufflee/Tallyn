import sqlite3
import json
import uuid
from datetime import datetime, timezone
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

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS batch_runs (
            batch_id TEXT PRIMARY KEY,
            uploaded_at TEXT NOT NULL,
            processing_status TEXT NOT NULL,
            error_message TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS active_batch (
            singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
            batch_id TEXT,
            FOREIGN KEY (batch_id) REFERENCES batch_runs(batch_id)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS batch_files (
            batch_id TEXT NOT NULL,
            source_file TEXT NOT NULL,
            source_type TEXT,
            role TEXT NOT NULL,
            record_count INTEGER NOT NULL,
            PRIMARY KEY (batch_id, source_file),
            FOREIGN KEY (batch_id) REFERENCES batch_runs(batch_id)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS batch_transactions (
            batch_id TEXT NOT NULL,
            transaction_id TEXT NOT NULL,
            date TEXT,
            amount REAL,
            counterparty TEXT,
            currency TEXT,
            bank_utr TEXT,
            bank_reference TEXT,
            settlement_reference TEXT,
            description TEXT,
            source TEXT,
            source_file TEXT,
            original_row INTEGER,
            original_data TEXT,
            PRIMARY KEY (batch_id, transaction_id),
            FOREIGN KEY (batch_id) REFERENCES batch_runs(batch_id)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS batch_erp_records (
            batch_id TEXT NOT NULL,
            invoice_id TEXT NOT NULL,
            date TEXT,
            amount REAL,
            vendor TEXT,
            reference TEXT,
            settlement_reference TEXT,
            settlement_utr TEXT,
            currency TEXT,
            source TEXT,
            source_file TEXT,
            original_row INTEGER,
            original_data TEXT,
            PRIMARY KEY (batch_id, invoice_id),
            FOREIGN KEY (batch_id) REFERENCES batch_runs(batch_id)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS batch_reconciliation_results (
            batch_id TEXT NOT NULL,
            transaction_id TEXT NOT NULL,
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
            exception_type TEXT,
            exception_reason TEXT,
            review_status TEXT,
            review_decision TEXT,
            reviewer_note TEXT,
            reviewed_at TEXT,
            processing_timestamp TEXT NOT NULL,
            PRIMARY KEY (batch_id, transaction_id),
            FOREIGN KEY (batch_id) REFERENCES batch_runs(batch_id)
        )
        """
    )

    batch_result_columns = {
        row[1]
        for row in cursor.execute(
            "PRAGMA table_info(batch_reconciliation_results)"
        ).fetchall()
    }
    for column, definition in {
        "review_status": "TEXT",
        "review_decision": "TEXT",
        "reviewer_note": "TEXT",
        "reviewed_at": "TEXT",
    }.items():
        if column not in batch_result_columns:
            cursor.execute(
                f"ALTER TABLE batch_reconciliation_results ADD COLUMN {column} {definition}"
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
    connection.execute(
        "INSERT INTO active_batch (singleton, batch_id) VALUES (1, NULL) "
        "ON CONFLICT(singleton) DO UPDATE SET batch_id = NULL"
    )

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


def _row_value(row, key, default=None):
    value = row.get(key, default) if hasattr(row, "get") else default
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    return value


def create_batch(files):
    """Create a durable batch and associate every uploaded source file with it."""
    batch_id = f"batch-{uuid.uuid4().hex}"
    uploaded_at = datetime.now(timezone.utc).isoformat()
    connection = get_connection()
    connection.execute(
        """
        INSERT INTO batch_runs (batch_id, uploaded_at, processing_status)
        VALUES (?, ?, 'PROCESSING')
        """,
        (batch_id, uploaded_at),
    )
    for file_info in files:
        connection.execute(
            """
            INSERT INTO batch_files
                (batch_id, source_file, source_type, role, record_count)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                batch_id,
                file_info.get("source_file") or file_info.get("filename") or "upload",
                file_info.get("source_type"),
                file_info.get("role", "supporting"),
                int(file_info.get("records") or 0),
            ),
        )
    connection.commit()
    connection.execute(
        """
        INSERT INTO active_batch (singleton, batch_id) VALUES (1, ?)
        ON CONFLICT(singleton) DO UPDATE SET batch_id = excluded.batch_id
        """,
        (batch_id,),
    )
    connection.commit()
    connection.close()
    return batch_id


def persist_batch_inputs(batch_id, bank, erp):
    """Persist the canonical input frames for one isolated batch."""
    connection = get_connection()
    for _, row in bank.iterrows():
        connection.execute(
            """
            INSERT INTO batch_transactions
                (batch_id, transaction_id, date, amount, counterparty, currency,
                 bank_utr, bank_reference, settlement_reference, description,
                 source, source_file, original_row, original_data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                batch_id, str(_row_value(row, "transaction_id", "")),
                str(_row_value(row, "date", "")), _row_value(row, "amount"),
                _row_value(row, "counterparty", ""), _row_value(row, "currency", "INR"),
                _row_value(row, "bank_utr"), _row_value(row, "bank_reference"),
                _row_value(row, "settlement_reference"), _row_value(row, "description"),
                _row_value(row, "source"), _row_value(row, "source_file"),
                _row_value(row, "original_row"), json.dumps(row.to_dict(), default=str),
            ),
        )
    for _, row in erp.iterrows():
        connection.execute(
            """
            INSERT INTO batch_erp_records
                (batch_id, invoice_id, date, amount, vendor, reference,
                 settlement_reference, settlement_utr, currency, source,
                 source_file, original_row, original_data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                batch_id, str(_row_value(row, "invoice_id", "")),
                str(_row_value(row, "date", "")), _row_value(row, "amount"),
                _row_value(row, "vendor", ""), _row_value(row, "reference"),
                _row_value(row, "settlement_reference"), _row_value(row, "settlement_utr"),
                _row_value(row, "currency", "INR"), _row_value(row, "source"),
                _row_value(row, "source_file"), _row_value(row, "original_row"),
                json.dumps(row.to_dict(), default=str),
            ),
        )
    connection.commit()
    connection.close()


def persist_batch_results(batch_id, results):
    """Persist final verified decisions for a batch."""
    connection = get_connection()
    timestamp = datetime.now(timezone.utc).isoformat()
    for result in results:
        connection.execute(
            """
            INSERT INTO batch_reconciliation_results
                (batch_id, transaction_id, matched_invoice, match_score,
                 deterministic_status, reason, ai_decision, ai_invoice,
                 ai_confidence, ai_reason, ai_risk, verification_decision,
                 verification_reason, verification_checks, exception_type,
                 exception_reason, processing_timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                batch_id, result.get("transaction_id"), result.get("matched_invoice"),
                result.get("match_score"), result.get("deterministic_status"),
                result.get("reason"), result.get("ai_decision"), result.get("ai_invoice"),
                result.get("ai_confidence"), result.get("ai_reason"), result.get("ai_risk"),
                result.get("verification_decision"), result.get("verification_reason"),
                result.get("verification_checks"), result.get("exception_type"),
                result.get("exception_reason"), timestamp,
            ),
        )
    connection.execute(
        "UPDATE batch_runs SET processing_status = 'COMPLETED' WHERE batch_id = ?",
        (batch_id,),
    )
    connection.commit()
    connection.close()


def mark_batch_failed(batch_id, error_message):
    connection = get_connection()
    connection.execute(
        """
        UPDATE batch_runs
        SET processing_status = 'FAILED', error_message = ?
        WHERE batch_id = ?
        """,
        (str(error_message), batch_id),
    )
    connection.commit()
    connection.close()


def get_latest_batch_id():
    connection = get_connection()
    row = connection.execute(
        """
        SELECT b.batch_id
        FROM active_batch a
        INNER JOIN batch_runs b ON b.batch_id = a.batch_id
        WHERE a.singleton = 1 AND b.processing_status = 'COMPLETED'
        """
    ).fetchone()
    connection.close()
    return row["batch_id"] if row else None