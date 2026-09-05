from io import BytesIO

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.app.database import get_connection, initialize_database, persist_batch_results
from backend.app.main import app


def csv_bytes(frame):
    return frame.to_csv(index=False).encode("utf-8")


@pytest.fixture(autouse=True)
def clean_batch_tables():
    initialize_database()
    connection = get_connection()
    for table in (
        "batch_reconciliation_results",
        "batch_erp_records",
        "batch_transactions",
        "batch_files",
        "batch_runs",
    ):
        connection.execute(f"DELETE FROM {table}")
    connection.commit()
    connection.close()
    yield


def make_upload_frames(prefix, count=30):
    bank = pd.DataFrame([
        {
            "transaction_id": f"{prefix}-TXN-{index:03d}",
            "date": "2026-09-01",
            "counterparty": "Urban Cart",
            "amount": 13375,
            "bank_ref": f"BNK-{prefix}-{index:03d}",
            "description": f"RAZORPAY SETTLEMENT UTR {prefix}-UTR-{index:03d}",
        }
        for index in range(count)
    ])
    erp = pd.DataFrame([
        {
            "invoice_id": f"{prefix}-SET-{index:03d}",
            "date": "2026-09-01",
            "vendor": "Urban Cart",
            "amount": 13375,
            "reference": f"{prefix}-UTR-{index:03d}",
        }
        for index in range(count)
    ])
    return bank, erp


def upload(client, bank, erp, bank_name, erp_name):
    response = client.post(
        "/reconcile/upload",
        files={
            "bank_file": (bank_name, csv_bytes(bank), "text/csv"),
            "erp_file": (erp_name, csv_bytes(erp), "text/csv"),
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_upload_persists_inputs_results_and_latest_batch_is_isolated():
    bank_a, erp_a = make_upload_frames("A")
    bank_b, erp_b = make_upload_frames("B")

    with TestClient(app) as client:
        result_a = upload(client, bank_a, erp_a, "bank_a.csv", "erp_a.csv")
        result_b = upload(client, bank_b, erp_b, "bank_b.csv", "erp_b.csv")

        assert result_a["batch_id"] != result_b["batch_id"]
        assert result_b["total_transactions"] == 30

        summary = client.get("/summary").json()
        assert summary == {
            "total_transactions": 30,
            "matched": 30,
            "review": 0,
            "exceptions": 0,
        }
        transactions = client.get("/transactions").json()
        assert len(transactions) == 30
        assert all(item["transaction_id"].startswith("B-TXN-") for item in transactions)
        records = client.get("/records").json()
        assert {item["batch_id"] for item in records} == {
            result_a["batch_id"], result_b["batch_id"]
        }

    connection = get_connection()
    assert connection.execute(
        "SELECT COUNT(*) FROM batch_transactions WHERE batch_id = ?",
        (result_a["batch_id"],),
    ).fetchone()[0] == 30
    assert connection.execute(
        "SELECT COUNT(*) FROM batch_transactions WHERE batch_id = ?",
        (result_b["batch_id"],),
    ).fetchone()[0] == 30
    normalized = connection.execute(
        """
        SELECT bank_utr, bank_reference, settlement_reference, description,
               source_file, original_row
        FROM batch_transactions
        WHERE batch_id = ? AND transaction_id = 'B-TXN-000'
        """,
        (result_b["batch_id"],),
    ).fetchone()
    assert normalized["bank_utr"] == "B-UTR-000"
    assert normalized["bank_reference"] == "BNK-B-000"
    assert normalized["settlement_reference"] == "B-UTR-000"
    assert normalized["description"] == "RAZORPAY SETTLEMENT UTR B-UTR-000"
    assert normalized["source_file"] == "bank_b.csv"
    assert normalized["original_row"] == 0
    assert connection.execute(
        "SELECT COUNT(*) FROM batch_reconciliation_results WHERE batch_id = ?",
        (result_b["batch_id"],),
    ).fetchone()[0] == 30
    connection.close()


def test_guard_rejected_ai_match_is_persisted_as_review():
    initialize_database()
    connection = get_connection()
    connection.execute(
        "INSERT INTO batch_runs (batch_id, uploaded_at, processing_status) VALUES (?, CURRENT_TIMESTAMP, 'PROCESSING')",
        ("batch-guard-test",),
    )
    connection.commit()
    connection.close()

    persist_batch_results("batch-guard-test", [{
        "transaction_id": "TXN-GUARD-001",
        "matched_invoice": None,
        "match_score": 75,
        "deterministic_status": "WARNING",
        "reason": "Ambiguous candidate",
        "ai_decision": "MATCH",
        "ai_invoice": "INV-1042",
        "ai_confidence": 96,
        "ai_reason": "AI recommendation",
        "ai_risk": "HIGH",
        "verification_decision": "REVIEW",
        "verification_reason": "Verification Guard rejected",
        "verification_checks": "{'decision': 'REVIEW'}",
        "exception_reason": "Verification Guard rejected",
    }])

    connection = get_connection()
    row = connection.execute(
        "SELECT ai_decision, verification_decision, matched_invoice FROM batch_reconciliation_results WHERE batch_id = ?",
        ("batch-guard-test",),
    ).fetchone()
    status = connection.execute(
        "SELECT processing_status FROM batch_runs WHERE batch_id = ?",
        ("batch-guard-test",),
    ).fetchone()[0]
    connection.close()

    assert row["ai_decision"] == "MATCH"
    assert row["verification_decision"] == "REVIEW"
    assert row["matched_invoice"] is None
    assert status == "COMPLETED"


def test_multiple_supporting_files_share_one_batch_and_keep_source_identity():
    bank, erp_a = make_upload_frames("MULTI", count=2)
    _, erp_b = make_upload_frames("MULTI-B", count=1)
    erp_b["invoice_id"] = ["MULTI-SET-002"]
    erp_b["reference"] = ["MULTI-UTR-002"]
    bank = bank.iloc[:2].copy()

    with TestClient(app) as client:
        response = client.post(
            "/reconcile/upload",
            files=[
                ("bank_file", ("multi_bank.csv", csv_bytes(bank), "text/csv")),
                ("supporting_files", ("multi_erp_a.csv", csv_bytes(erp_a), "text/csv")),
                ("supporting_files", ("multi_erp_b.csv", csv_bytes(erp_b), "text/csv")),
            ],
        )
        assert response.status_code == 200, response.text
        batch_id = response.json()["batch_id"]

    connection = get_connection()
    files = connection.execute(
        "SELECT source_file, role FROM batch_files WHERE batch_id = ? ORDER BY source_file",
        (batch_id,),
    ).fetchall()
    erp_sources = connection.execute(
        "SELECT DISTINCT source_file FROM batch_erp_records WHERE batch_id = ?",
        (batch_id,),
    ).fetchall()
    connection.close()

    assert {row["source_file"] for row in files} == {
        "multi_bank.csv", "multi_erp_a.csv", "multi_erp_b.csv"
    }
    assert all(row["role"] == "supporting" for row in files if row["source_file"] != "multi_bank.csv")
    assert {row["source_file"] for row in erp_sources} == {
        "multi_erp_a.csv", "multi_erp_b.csv"
    }
