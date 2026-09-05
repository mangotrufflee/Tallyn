import pandas as pd

from backend.app.reconciliation.matcher import (
    calculate_match_score,
    classify_match,
    normalize_settlement_reference,
    settlement_reference_similarity,
)
from backend.app.ingestion.normalizer import normalize_bank_dataframe


def make_bank(**overrides):
    row = {
        "transaction_id": "TXN-001",
        "date": pd.Timestamp("2026-09-01"),
        "amount": 1000.0,
        "counterparty": "Razorpay",
    }
    row.update(overrides)
    return pd.Series(row)


def make_erp(**overrides):
    row = {
        "invoice_id": "SET-001",
        "date": pd.Timestamp("2026-09-01"),
        "amount": 1000.0,
        "vendor": "Razorpay Software Pvt Ltd",
        "reference": "INV-001",
    }
    row.update(overrides)
    return pd.Series(row)


def test_normalize_settlement_reference():
    assert normalize_settlement_reference(" utr-  Ab 12 ") == "UTRAB12"
    assert normalize_settlement_reference(None) == ""
    assert normalize_settlement_reference(float("nan")) == ""


def test_exact_settlement_utr_match():
    bank = make_bank(bank_utr="utr-abc 123")
    erp = make_erp(settlement_utr="UTRABC123")

    scores = calculate_match_score(bank, erp)

    assert settlement_reference_similarity(bank, erp) == 100
    assert scores["settlement_reference_score"] == 100
    assert scores["final_score"] == 100


def test_description_utr_matches_different_transaction_and_invoice_ids():
    bank = normalize_bank_dataframe(pd.DataFrame([{
        "transaction_id": "RZP-TXN-001",
        "date": "2026-09-01",
        "counterparty": "UrbanCart",
        "amount": 13375,
        "bank_ref": "BNK-00001",
        "description": "RAZORPAY SETTLEMENT UTR RZP260001",
    }])).iloc[0]
    bank["date"] = pd.Timestamp(bank["date"])
    erp = make_erp(
        invoice_id="RZP-SET-001",
        vendor="Urban Cart",
        amount=13375.0,
        reference="RZP260001",
    )

    scores = calculate_match_score(bank, erp)

    assert bank["transaction_id"] != erp["invoice_id"]
    assert scores["settlement_reference_score"] == 100
    assert scores["final_score"] == 100


def test_different_utr_does_not_match():
    bank = make_bank(bank_utr="UTR-ABC-123")
    erp = make_erp(settlement_utr="UTR-XYZ-999")

    assert settlement_reference_similarity(bank, erp) == 0


def test_missing_utr_does_not_match():
    bank = make_bank()
    erp = make_erp()

    assert settlement_reference_similarity(bank, erp) == 0


def test_generic_reference_matching_still_works():
    bank = make_bank(transaction_id="TXN-001")
    erp = make_erp(reference="txn-001")

    scores = calculate_match_score(bank, erp)

    assert scores["reference_score"] == 100
    assert scores["settlement_reference_score"] == 0
    assert scores["final_score"] == 100


def test_settlement_reference_with_material_amount_conflict_is_not_matched():
    bank = make_bank(bank_utr="UTR-ABC-123")
    erp = make_erp(settlement_utr="UTRABC123", amount=2500.0)

    scores = calculate_match_score(bank, erp)
    status = classify_match(
        scores["final_score"],
        0,
        erp,
    )

    assert scores["settlement_reference_score"] == 100
    assert scores["final_score"] < 90
    assert status != "MATCHED"