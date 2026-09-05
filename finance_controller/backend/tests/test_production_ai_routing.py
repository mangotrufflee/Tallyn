"""
Tests for Production AI Routing and Verification Guard Integration.
===================================================================

Verifies the end-to-end routing behavior in production reconciliation:
  A. Deterministic high-confidence match that should NOT need AI.
  B. Ambiguous/review case that SHOULD reach AI.
  C. AI MATCH recommendation that Verification Guard APPROVES.
  D. AI MATCH recommendation that Verification Guard REJECTS.
  E. AI failure/error that safely falls back to REVIEW.
  F. Completely synthetic transaction/invoice IDs proving zero Track-04 coupling.
  G. End-to-end API response consistency (Guard decision reflected in summary,
     transactions, and verification endpoints).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.database import (
    get_connection,
    initialize_database,
    replace_active_batch,
)
from backend.app.main import (
    app,
    run_ai_on_transaction,
    run_reconciliation,
)
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def clean_db():
    """Ensure a fresh test database for each test."""
    initialize_database()
    conn = get_connection()
    conn.execute("DELETE FROM reconciliation_results")
    conn.execute("DELETE FROM transactions")
    conn.execute("DELETE FROM erp_records")
    conn.execute("DELETE FROM ground_truth")
    conn.commit()
    conn.close()
    yield


# ===========================================================================
# A. Deterministic high-confidence match that should NOT need AI
# ===========================================================================

def test_deterministic_match_does_not_call_ai():
    """
    When the deterministic matcher finds a high-confidence match (score >= 70, margin >= 10),
    the transaction is classified as MATCHED and must NOT be routed to AI.
    """
    bank_df = pd.DataFrame([{
        "transaction_id": "TXN-DET-001",
        "date": "2026-06-15",
        "counterparty": "Global Logistics Corp",
        "amount": 25000.0,
        "currency": "INR",
        "reference": "REF-GLC-999",
        "bank_reference": "REF-GLC-999",
        "settlement_reference": "REF-GLC-999",
    }])

    erp_df = pd.DataFrame([{
        "invoice_id": "INV-GLC-001",
        "reference": "REF-GLC-999",
        "date": "2026-06-15",
        "vendor": "Global Logistics Corp",
        "amount": 25000.0,
        "currency": "INR",
        "settlement_reference": "REF-GLC-999",
    }])

    with patch("backend.app.main.run_ai_on_transaction") as mock_ai:
        replace_active_batch(bank_df, erp_df)
        result = run_reconciliation(bank_df, erp_df)

        # AI should never have been invoked
        mock_ai.assert_not_called()

    assert result["total_transactions"] == 1
    assert result["deterministic_uncertain"] == 0
    assert result["ai_processed"] == 0

    # Verify database persistence
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM reconciliation_results WHERE transaction_id = ?",
        ("TXN-DET-001",),
    ).fetchone()
    conn.close()

    assert row is not None
    assert row["deterministic_status"] == "MATCHED"
    assert row["ai_decision"] is None
    assert row["ai_invoice"] is None
    assert row["verification_decision"] == "MATCHED"
    assert row["matched_invoice"] == "INV-GLC-001"


# ===========================================================================
# B. Ambiguous/review case that SHOULD reach AI
# ===========================================================================

def test_ambiguous_case_reaches_ai():
    """
    When deterministic scoring produces an uncertain status (WARNING or EXCEPTION),
    the transaction MUST be routed to AI reasoner.
    """
    # Vendor mismatch and no reference -> score drops below 70
    bank_df = pd.DataFrame([{
        "transaction_id": "TXN-AMBIG-001",
        "date": "2026-06-15",
        "counterparty": "Apex Tech Solutions",
        "amount": 14200.0,
        "currency": "INR",
    }])

    erp_df = pd.DataFrame([{
        "invoice_id": "INV-APX-888",
        "reference": "",
        "date": "2026-06-16",
        "vendor": "Apex Technologies Private Limited",
        "amount": 14200.0,
        "currency": "INR",
    }])

    mock_ai_response = {
        "ok": True,
        "raw": json.dumps({
            "decision": "REVIEW",
            "confidence": 65,
            "selected_invoice": "INV-APX-888",
            "reason": "Slight vendor name difference, recommends human review",
            "risk": "MEDIUM",
        }),
    }

    with patch("backend.app.main.safe_ask_ai", return_value=mock_ai_response) as mock_ask:
        replace_active_batch(bank_df, erp_df)
        result = run_reconciliation(bank_df, erp_df)

        # safe_ask_ai was called because this transaction was uncertain
        assert mock_ask.called
        assert result["deterministic_uncertain"] == 1
        assert result["ai_processed"] == 1

    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM reconciliation_results WHERE transaction_id = ?",
        ("TXN-AMBIG-001",),
    ).fetchone()
    conn.close()

    assert row is not None
    assert row["deterministic_status"] in ("WARNING", "EXCEPTION")
    assert row["ai_decision"] == "REVIEW"
    assert row["verification_decision"] == "REVIEW"


# ===========================================================================
# C. AI MATCH recommendation that Verification Guard APPROVES
# ===========================================================================

def test_ai_match_approved_by_guard():
    """
    When AI recommends MATCH and the candidate satisfies Verification Guard
    criteria (matching amount, date, vendor >= 70, reference match),
    Verification Guard must APPROVE the match (verification_decision = 'MATCHED')
    and persist the Guard-approved matched_invoice.
    """
    bank_row = pd.Series({
        "transaction_id": "TXN-APPROVE-777",
        "date": "2026-07-20",
        "counterparty": "Solaris Energy Ltd",
        "amount": 55000.0,
        "currency": "INR",
        "bank_utr": "UTR-SOLARIS-555",
        "settlement_reference": "UTR-SOLARIS-555",
        "source": "bank",
        "source_file": "bank.csv",
    })

    erp_df = pd.DataFrame([{
        "invoice_id": "INV-SOLARIS-001",
        "reference": "UTR-SOLARIS-555",
        "date": "2026-07-20",
        "vendor": "Solaris Energy Limited",
        "amount": 55000.0,
        "currency": "INR",
        "settlement_reference": "UTR-SOLARIS-555",
        "source": "erp",
        "source_file": "erp.csv",
    }])

    mock_ai_call = {
        "ok": True,
        "raw": json.dumps({
            "decision": "MATCH",
            "confidence": 95,
            "selected_invoice": "INV-SOLARIS-001",
            "reason": "Exact amount and confirmed UTR match across systems",
            "risk": "LOW",
        }),
    }

    with patch("backend.app.main.safe_ask_ai", return_value=mock_ai_call):
        ai_result = run_ai_on_transaction(bank_row, erp_df)

    assert ai_result["ai_decision"] == "MATCH"
    assert ai_result["ai_invoice"] == "INV-SOLARIS-001"
    assert ai_result["verification_decision"] == "MATCHED"
    assert "approved" in ai_result["verification_reason"].lower()

    # End-to-end run_reconciliation test to verify matched_invoice persistence
    bank_df = pd.DataFrame([bank_row.to_dict()])
    with patch("backend.app.main.safe_ask_ai", return_value=mock_ai_call):
        replace_active_batch(bank_df, erp_df)
        run_reconciliation(bank_df, erp_df)

    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM reconciliation_results WHERE transaction_id = ?",
        ("TXN-APPROVE-777",),
    ).fetchone()
    conn.close()

    assert row["verification_decision"] == "MATCHED"
    assert row["matched_invoice"] == "INV-SOLARIS-001"


# ===========================================================================
# D. AI MATCH recommendation that Verification Guard REJECTS
# ===========================================================================

def test_ai_match_rejected_by_guard_amount_conflict():
    """
    When AI hallucinates or erroneously recommends MATCH despite a material
    amount conflict (> 500), Verification Guard MUST REJECT the match.
    The final decision must be REVIEW (never MATCHED), and the reason must reflect Guard rejection.
    """
    bank_row = pd.Series({
        "transaction_id": "TXN-CONFLICT-101",
        "date": "2026-08-10",
        "counterparty": "Quantum Dynamics",
        "amount": 10000.0,
        "currency": "INR",
        "source": "bank",
        "source_file": "bank.csv",
    })

    # Material amount conflict: 10000 vs 15000 (diff: 5000 > 500)
    erp_df = pd.DataFrame([{
        "invoice_id": "INV-QD-999",
        "reference": "REF-QD-999",
        "date": "2026-08-10",
        "vendor": "Quantum Dynamics",
        "amount": 15000.0,
        "currency": "INR",
        "source": "erp",
        "source_file": "erp.csv",
    }])

    # AI erroneously claims MATCH
    mock_ai_call = {
        "ok": True,
        "raw": json.dumps({
            "decision": "MATCH",
            "confidence": 90,
            "selected_invoice": "INV-QD-999",
            "reason": "Hallucinated match despite amount difference",
            "risk": "LOW",
        }),
    }

    with patch("backend.app.main.safe_ask_ai", return_value=mock_ai_call):
        ai_result = run_ai_on_transaction(bank_row, erp_df)

    # Raw AI was MATCH
    assert ai_result["ai_decision"] == "MATCH"
    # Guard rejected it: final verification_decision is REVIEW, NOT MATCHED!
    assert ai_result["verification_decision"] == "REVIEW"
    assert "Verification Guard rejected" in ai_result["verification_reason"]
    assert "amount conflict" in ai_result["verification_reason"].lower()


def test_ai_match_rejected_by_guard_date_conflict():
    """
    When AI recommends MATCH but date difference exceeds 3 days,
    Verification Guard must reject the match to REVIEW.
    """
    bank_row = pd.Series({
        "transaction_id": "TXN-DATE-CONFLICT-102",
        "date": "2026-08-01",
        "counterparty": "Helios Systems",
        "amount": 5000.0,
        "currency": "INR",
        "source": "bank",
        "source_file": "bank.csv",
    })

    # Date conflict: 2026-08-01 vs 2026-08-15 (14 days > 3)
    erp_df = pd.DataFrame([{
        "invoice_id": "INV-HELIOS-102",
        "reference": "REF-HELIOS",
        "date": "2026-08-15",
        "vendor": "Helios Systems",
        "amount": 5000.0,
        "currency": "INR",
        "source": "erp",
        "source_file": "erp.csv",
    }])

    mock_ai_call = {
        "ok": True,
        "raw": json.dumps({
            "decision": "MATCH",
            "confidence": 85,
            "selected_invoice": "INV-HELIOS-102",
            "reason": "Matched ignoring date",
            "risk": "LOW",
        }),
    }

    with patch("backend.app.main.safe_ask_ai", return_value=mock_ai_call):
        ai_result = run_ai_on_transaction(bank_row, erp_df)

    assert ai_result["ai_decision"] == "MATCH"
    assert ai_result["verification_decision"] == "REVIEW"
    assert "Verification Guard rejected" in ai_result["verification_reason"]
    assert "date conflict" in ai_result["verification_reason"].lower()


# ===========================================================================
# E. AI failure/error that safely becomes REVIEW
# ===========================================================================

def test_ai_network_timeout_safely_falls_back_to_review():
    """
    When the model connection times out or fails (safe_ask_ai ok=False),
    it must gracefully fall back to REVIEW without raising an unhandled exception.
    """
    bank_row = pd.Series({
        "transaction_id": "TXN-ERR-001",
        "date": "2026-09-01",
        "counterparty": "Nebula Cloud",
        "amount": 7500.0,
        "currency": "INR",
    })

    erp_df = pd.DataFrame([{
        "invoice_id": "INV-NEB-001",
        "reference": "",
        "date": "2026-09-01",
        "vendor": "Nebula Cloud Inc",
        "amount": 7500.0,
        "currency": "INR",
    }])

    with patch("backend.app.main.safe_ask_ai", return_value={"ok": False, "error": "Connection timed out", "raw": None}):
        ai_result = run_ai_on_transaction(bank_row, erp_df)

    assert ai_result["ai_decision"] == "REVIEW"
    assert ai_result["ai_invoice"] is None
    assert ai_result["verification_decision"] == "REVIEW"
    assert "AI unavailable" in ai_result["verification_reason"]


def test_ai_malformed_json_safely_falls_back_to_review():
    """
    When AI returns invalid / unparseable JSON, it must safely become REVIEW.
    """
    bank_row = pd.Series({
        "transaction_id": "TXN-MALFORM-002",
        "date": "2026-09-01",
        "counterparty": "Orion Services",
        "amount": 3200.0,
        "currency": "INR",
    })

    erp_df = pd.DataFrame([{
        "invoice_id": "INV-ORN-002",
        "reference": "",
        "date": "2026-09-01",
        "vendor": "Orion Services",
        "amount": 3200.0,
        "currency": "INR",
    }])

    with patch("backend.app.main.safe_ask_ai", return_value={"ok": True, "raw": "I am not returning JSON today!"}):
        ai_result = run_ai_on_transaction(bank_row, erp_df)

    assert ai_result["ai_decision"] == "REVIEW"
    assert ai_result["verification_decision"] == "REVIEW"
    assert "Invalid or unsafe AI response" in ai_result["verification_reason"]


def test_ai_unhandled_exception_safely_falls_back_to_review():
    """
    If any unexpected exception occurs during routing, it is caught and converted to REVIEW.
    """
    bank_row = pd.Series({
        "transaction_id": "TXN-EXC-003",
        "date": "2026-09-01",
        "counterparty": "Zenith Labs",
        "amount": 1000.0,
        "currency": "INR",
    })

    erp_df = pd.DataFrame([{
        "invoice_id": "INV-ZEN-003",
        "reference": "",
        "date": "2026-09-01",
        "vendor": "Zenith Labs",
        "amount": 1000.0,
        "currency": "INR",
    }])

    with patch("backend.app.main.find_top_candidates", side_effect=RuntimeError("Simulated pipeline glitch")):
        ai_result = run_ai_on_transaction(bank_row, erp_df)

    assert ai_result["ai_decision"] == "REVIEW"
    assert ai_result["verification_decision"] == "REVIEW"
    assert "AI routing error fallback" in ai_result["verification_reason"]


# ===========================================================================
# F. Completely synthetic dataset (independent of Track-04)
# ===========================================================================

def test_production_routing_independent_of_track_04_data():
    """
    Proves that production routing functions correctly on an arbitrary synthetic dataset
    with unique IDs, non-standard dates, arbitrary amounts, and vendors.
    """
    bank_df = pd.DataFrame([
        {
            "transaction_id": "TXN-SYNTHETIC-ALPHA-001",
            "date": "2028-11-20",
            "counterparty": "Vortex Heavy Industries",
            "amount": 88420.0,
            "currency": "INR",
            "bank_utr": "UTR-VORTEX-ALPHA",
            "settlement_reference": "UTR-VORTEX-ALPHA",
        },
        {
            "transaction_id": "TXN-SYNTHETIC-BETA-002",
            "date": "2028-11-21",
            "counterparty": "Hyperion Labs",
            "amount": 12500.0,
            "currency": "INR",
            "bank_utr": "",
            "settlement_reference": "",
        },
    ])

    erp_df = pd.DataFrame([
        {
            "invoice_id": "INV-SYNTHETIC-ALPHA-001",
            "reference": "UTR-VORTEX-ALPHA",
            "date": "2028-11-20",
            "vendor": "Vortex Heavy Industries",
            "amount": 88420.0,
            "currency": "INR",
            "settlement_reference": "UTR-VORTEX-ALPHA",
        },
        {
            "invoice_id": "INV-SYNTHETIC-BETA-002",
            "reference": "",
            "date": "2028-11-25",  # 4 days difference -> ambiguous
            "vendor": "Hyperion Labs Pvt Ltd",
            "amount": 12500.0,
            "currency": "INR",
            "settlement_reference": "",
        },
    ])

    mock_ai_call = {
        "ok": True,
        "raw": json.dumps({
            "decision": "REVIEW",
            "confidence": 60,
            "selected_invoice": "INV-SYNTHETIC-BETA-002",
            "reason": "Date is 4 days apart, needs manual confirmation",
            "risk": "MEDIUM",
        }),
    }

    with patch("backend.app.main.safe_ask_ai", return_value=mock_ai_call):
        replace_active_batch(bank_df, erp_df)
        result = run_reconciliation(bank_df, erp_df)

    assert result["total_transactions"] == 2
    # TXN-SYNTHETIC-ALPHA-001 was a deterministic match
    # TXN-SYNTHETIC-BETA-002 was ambiguous and reached AI
    assert result["ai_processed"] == 1

    conn = get_connection()
    rows = {
        r["transaction_id"]: dict(r)
        for r in conn.execute("SELECT * FROM reconciliation_results").fetchall()
    }
    conn.close()

    assert rows["TXN-SYNTHETIC-ALPHA-001"]["verification_decision"] == "MATCHED"
    assert rows["TXN-SYNTHETIC-ALPHA-001"]["matched_invoice"] == "INV-SYNTHETIC-ALPHA-001"
    assert rows["TXN-SYNTHETIC-ALPHA-001"]["ai_decision"] is None

    assert rows["TXN-SYNTHETIC-BETA-002"]["verification_decision"] == "REVIEW"
    assert rows["TXN-SYNTHETIC-BETA-002"]["ai_decision"] == "REVIEW"


# ===========================================================================
# G. End-to-end API response consistency (Guard decision reflected)
# ===========================================================================

def test_api_endpoints_reflect_guard_decision():
    """
    Verifies that /summary, /transactions, and /verification endpoints accurately
    reflect the final Verification Guard decision and NOT raw unverified AI decisions.
    """
    client = TestClient(app)

    bank_df = pd.DataFrame([
        # 1. Deterministic match
        {
            "transaction_id": "TXN-API-001",
            "date": "2026-05-01",
            "counterparty": "Acme Tools",
            "amount": 3000.0,
            "currency": "INR",
            "bank_utr": "UTR-ACME-1",
            "settlement_reference": "UTR-ACME-1",
        },
        # 2. AI MATCH rejected by Guard (due to amount conflict) -> REVIEW
        {
            "transaction_id": "TXN-API-002",
            "date": "2026-05-01",
            "counterparty": "Beta Supplies",
            "amount": 4000.0,
            "currency": "INR",
        },
        # 3. AI EXCEPTION -> EXCEPTION
        {
            "transaction_id": "TXN-API-003",
            "date": "2026-05-01",
            "counterparty": "Gamma Services",
            "amount": 9999.0,
            "currency": "INR",
        },
    ])

    erp_df = pd.DataFrame([
        {
            "invoice_id": "INV-API-001",
            "reference": "UTR-ACME-1",
            "date": "2026-05-01",
            "vendor": "Acme Tools",
            "amount": 3000.0,
            "currency": "INR",
            "settlement_reference": "UTR-ACME-1",
        },
        {
            "invoice_id": "INV-API-002",
            "reference": "",
            "date": "2026-05-01",
            "vendor": "Beta Supplies",
            "amount": 6000.0,  # diff: 2000 > 500
            "currency": "INR",
        },
    ])

    def mock_ask(prompt):
        if "Gamma Services" in prompt:
            return {
                "ok": True,
                "raw": json.dumps({
                    "decision": "EXCEPTION",
                    "confidence": 95,
                    "selected_invoice": None,
                    "reason": "No matching vendor in ERP",
                    "risk": "HIGH",
                }),
            }
        return {
            "ok": True,
            "raw": json.dumps({
                "decision": "MATCH",
                "confidence": 90,
                "selected_invoice": "INV-API-002",
                "reason": "Erroneous AI match",
                "risk": "LOW",
            }),
        }

    with patch("backend.app.main.safe_ask_ai", side_effect=mock_ask):
        replace_active_batch(bank_df, erp_df)
        run_reconciliation(bank_df, erp_df)

    # 1. Test /summary
    summary_resp = client.get("/summary")
    assert summary_resp.status_code == 200
    summary = summary_resp.json()
    assert summary["total_transactions"] == 3
    assert summary["matched"] == 1   # Only TXN-API-001 is MATCHED
    assert summary["review"] == 1    # TXN-API-002 rejected by Guard -> REVIEW
    assert summary["exceptions"] == 1  # TXN-API-003 is EXCEPTION

    # 2. Test /transactions
    txns_resp = client.get("/transactions")
    assert txns_resp.status_code == 200
    txns = {t["transaction_id"]: t for t in txns_resp.json()}

    # TXN-API-002: AI suggested MATCH, but Guard rejected to REVIEW
    assert txns["TXN-API-002"]["ai_decision"] == "MATCH"
    assert txns["TXN-API-002"]["verification_decision"] == "REVIEW"
    assert "Verification Guard rejected" in txns["TXN-API-002"]["verification_reason"]

    # 3. Test /verification
    verif_resp = client.get("/verification")
    assert verif_resp.status_code == 200
    verif_items = {v["transaction_id"]: v for v in verif_resp.json()}
    assert verif_items["TXN-API-002"]["verification_decision"] == "REVIEW"
