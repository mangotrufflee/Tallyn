import sqlite3
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATABASE_PATH = PROJECT_ROOT / "data" / "finance_controller.db"
BANK_PATH = PROJECT_ROOT / "data" / "raw" / "bank.csv"
ERP_PATH = PROJECT_ROOT / "data" / "raw" / "erp.csv"
VERIFICATION_PATH = PROJECT_ROOT / "data" / "raw" / "verification.csv"


def get_connection():
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database():
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            transaction_id TEXT PRIMARY KEY,
            date TEXT NOT NULL,
            counterparty TEXT,
            amount REAL,
            currency TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS erp_records (
            invoice_id TEXT PRIMARY KEY,
            reference TEXT,
            date TEXT,
            vendor TEXT,
            amount REAL,
            currency TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ground_truth (
            transaction_id TEXT PRIMARY KEY,
            expected_invoice TEXT
        )
    """)
    cursor.execute("""
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
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (transaction_id)
                REFERENCES transactions(transaction_id)
        )
    """)

    columns = {
        row[1]
        for row in cursor.execute(
            "PRAGMA table_info(reconciliation_results)"
        ).fetchall()
    }

    if "updated_at" not in columns:
        cursor.execute(
            """ALTER TABLE reconciliation_results
            ADD COLUMN updated_at TEXT"""
        )
        cursor.execute(
            """UPDATE reconciliation_results
            SET updated_at = CURRENT_TIMESTAMP
            WHERE updated_at IS NULL"""
        )

    connection.commit()
    connection.close()


def seed_database():
    bank = pd.read_csv(BANK_PATH)
    erp = pd.read_csv(ERP_PATH)
    verification = pd.read_csv(VERIFICATION_PATH)
    connection = get_connection()

    for _, row in bank.iterrows():
        connection.execute(
            """INSERT OR REPLACE INTO transactions
            (transaction_id, date, counterparty, amount, currency)
            VALUES (?, ?, ?, ?, ?)""",
            (str(row["transaction_id"]), str(row["date"]),
             str(row["counterparty"]), float(row["amount"]),
             str(row.get("currency", "INR"))),
        )

    for _, row in erp.iterrows():
        connection.execute(
            """INSERT OR REPLACE INTO erp_records
            (invoice_id, reference, date, vendor, amount, currency)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (str(row["invoice_id"]), str(row["reference"]),
             str(row["date"]), str(row["vendor"]), float(row["amount"]),
             str(row.get("currency", "INR"))),
        )

    for _, row in verification.iterrows():
        connection.execute(
            """INSERT OR REPLACE INTO ground_truth
            (transaction_id, expected_invoice)
            VALUES (?, ?)""",
            (str(row["transaction_id"]), str(row["expected_invoice"])),
        )

    connection.commit()
    connection.close()


def load_bank_data():
    connection = get_connection()
    rows = connection.execute("SELECT * FROM transactions").fetchall()
    connection.close()
    data = pd.DataFrame([dict(row) for row in rows])
    if not data.empty:
        data["date"] = pd.to_datetime(data["date"])
    return data


def load_erp_data():
    connection = get_connection()
    rows = connection.execute("SELECT * FROM erp_records").fetchall()
    connection.close()
    data = pd.DataFrame([dict(row) for row in rows])
    if not data.empty:
        data["date"] = pd.to_datetime(data["date"])
    return data
