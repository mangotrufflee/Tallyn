"""Production ingestion / normalization tests."""

from pathlib import Path
from io import BytesIO

import pandas as pd
import pytest

from backend.app.ingestion.normalizer import (
    normalize_bank_dataframe,
    detect_source_type,
)
from backend.app.ingestion.pipeline import (
    ingest_file,
    ingest_supporting_files,
    load_raw_dataframe,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW = PROJECT_ROOT / "data" / "raw"
PDF_PATH = RAW / "hdfc_synthetic_bank_statement.pdf"


def _csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def _xlsx_bytes(df: pd.DataFrame) -> bytes:
    buffer = BytesIO()
    df.to_excel(buffer, index=False)
    return buffer.getvalue()


def test_existing_canonical_bank_csv():
    frame = pd.read_csv(RAW / "bank.csv")
    assert detect_source_type(frame, "bank.csv") == "BANK"

    contents = (RAW / "bank.csv").read_bytes()
    normalized, info = ingest_file(contents, "bank.csv", hinted_role="bank")

    assert info["valid"] is True
    assert info["status"] in {"VALID", "WARNING"}
    assert normalized is not None
    assert len(normalized) == len(frame)
    assert set(["transaction_id", "date", "amount", "counterparty"]).issubset(
        normalized.columns
    )
    assert normalized.iloc[0]["transaction_id"] == str(frame.iloc[0]["transaction_id"])
    assert "original_data" in normalized.columns
    assert "source_file" in normalized.columns


def test_bank_alternative_column_names():
    df = pd.DataFrame(
        [
            {
                "Txn ID": "TXN-ALT-1",
                "Txn Date": "10/01/2026",
                "Transaction Amount": "1,250.50",
                "Merchant": "Acme Supplies",
                "Bank UTR": "UTR999",
            }
        ]
    )
    contents = _csv_bytes(df)
    normalized, info = ingest_file(contents, "alt_bank.csv", hinted_role="bank")

    assert info["valid"] is True
    assert normalized is not None
    row = normalized.iloc[0]
    assert row["transaction_id"] == "TXN-ALT-1"
    assert str(row["date"]).startswith("2026-01-10")
    assert float(row["amount"]) == 1250.50
    assert row["counterparty"] == "Acme Supplies"
    assert row["bank_utr"] == "UTR999"


def test_bank_debit_credit_columns():
    df = pd.DataFrame(
        [
            {
                "Date": "11/01/2026",
                "Narration": "NEFT CR-VENDOR",
                "Cheque/Ref No.": "UTR111",
                "Debit": "",
                "Credit": "2,000.00",
            }
        ]
    )
    result = normalize_bank_dataframe(df, source_file="debit_credit.csv")
    row = result.iloc[0]
    assert row["amount"] == 2000.0
    assert row["direction"] == "CREDIT"
    assert row["bank_utr"] == "UTR111"
    assert row["transaction_id"] == "UTR111"


def test_ambiguous_debit_credit_is_fatal():
    df = pd.DataFrame(
        [
            {
                "Date": "11/01/2026",
                "Narration": "CONFUSED",
                "Debit": "100.00",
                "Credit": "200.00",
            }
        ]
    )
    contents = _csv_bytes(df)
    normalized, info = ingest_file(contents, "ambiguous.csv", hinted_role="bank")
    assert normalized is None
    assert info["valid"] is False
    assert info["status"] == "FATAL"
    assert any("ambiguous debit/credit" in error.lower() for error in info["errors"])


def test_erp_alternative_column_names():
    df = pd.DataFrame(
        [
            {
                "Invoice Number": "INV-ALT-1",
                "Invoice Date": "2026-01-12",
                "Bill Amount": "999.00",
                "Supplier": "Beta Traders",
                "Payment Reference": "PAY-55",
            }
        ]
    )
    contents = _csv_bytes(df)
    normalized, info = ingest_file(contents, "alt_erp.csv", hinted_role="supporting")

    assert info["valid"] is True
    assert info["source_type"] in {"ERP", "INVOICE"}
    row = normalized.iloc[0]
    assert row["invoice_id"] == "INV-ALT-1"
    assert float(row["amount"]) == 999.0
    assert row["vendor"] == "Beta Traders"
    assert row["reference"] == "PAY-55"


def test_razorpay_settlement_csv():
    df = pd.DataFrame(
        [
            {
                "Settlement ID": "setl_1",
                "Settlement UTR": "RZPUTR1",
                "Settlement Date": "03/08/2026",
                "Status": "processed",
                "Amount": "1000.00",
                "Fees": "10.00",
                "Tax": "2.00",
                "Gross Payments": "1012.00",
                "Refunds": "0",
                "Adjustments": "0",
            }
        ]
    )
    contents = _csv_bytes(df)
    normalized, info = ingest_file(
        contents,
        "razorpay_settlements.csv",
        hinted_role="supporting",
    )
    assert info["valid"] is True
    assert info["source_type"] == "RAZORPAY"
    assert normalized.iloc[0]["invoice_id"] == "setl_1"
    assert normalized.iloc[0]["settlement_utr"] == "RZPUTR1"
    assert normalized.iloc[0]["vendor"] == "RAZORPAY"


def test_xlsx_bank_ingest():
    df = pd.DataFrame(
        [
            {
                "transaction_id": "TXN-XLSX-1",
                "date": "2026-02-01",
                "amount": 100.0,
                "counterparty": "Xlsx Vendor",
            }
        ]
    )
    contents = _xlsx_bytes(df)
    normalized, info = ingest_file(contents, "bank.xlsx", hinted_role="bank")
    assert info["valid"] is True
    assert normalized is not None
    assert normalized.iloc[0]["transaction_id"] == "TXN-XLSX-1"


def test_existing_hdfc_pdf_ingest():
    if not PDF_PATH.exists():
        pytest.skip("HDFC synthetic PDF not present")

    contents = PDF_PATH.read_bytes()
    normalized, info = ingest_file(
        contents,
        "hdfc_synthetic_bank_statement.pdf",
        hinted_role="bank",
    )
    assert info["valid"] is True
    assert info["source_type"] == "BANK"
    assert normalized is not None
    assert len(normalized) > 0
    assert normalized["amount"].notna().all()
    assert "original_data" in normalized.columns


def test_missing_required_field_is_fatal():
    df = pd.DataFrame(
        [
            {
                "transaction_id": "TXN1",
                "amount": 10.0,
                "counterparty": "Someone",
            }
        ]
    )
    contents = _csv_bytes(df)
    normalized, info = ingest_file(contents, "missing_date.csv", hinted_role="bank")
    assert normalized is None
    assert info["valid"] is False
    assert any("date" in error.lower() for error in info["errors"])


def test_missing_optional_reference_is_warning():
    df = pd.DataFrame(
        [
            {
                "invoice_id": "INV1",
                "date": "2026-01-01",
                "amount": 50.0,
                "vendor": "Vendor A",
            }
        ]
    )
    contents = _csv_bytes(df)
    normalized, info = ingest_file(contents, "erp_no_ref.csv", hinted_role="supporting")
    assert normalized is not None
    assert info["valid"] is True
    assert info["status"] == "WARNING"
    assert any("reference" in warning.lower() for warning in info["warnings"])


def test_multiple_supporting_files_keep_source_identity():
    erp1 = pd.DataFrame(
        [
            {
                "invoice_id": "INV-A",
                "date": "2026-01-01",
                "amount": 10.0,
                "vendor": "A",
                "reference": "R1",
            }
        ]
    )
    erp2 = pd.DataFrame(
        [
            {
                "Invoice Number": "INV-B",
                "Invoice Date": "2026-01-02",
                "Bill Amount": "20.0",
                "Supplier": "B",
                "Payment Reference": "R2",
            }
        ]
    )
    combined, infos, summary = ingest_supporting_files(
        [
            (_csv_bytes(erp1), "ERP_1.csv"),
            (_csv_bytes(erp2), "Invoices.csv"),
        ]
    )
    assert summary["valid"] is True
    assert combined is not None
    assert len(combined) == 2
    assert len(infos) == 2
    assert set(combined["source_file"]) == {"ERP_1.csv", "Invoices.csv"}
    assert set(combined["invoice_id"]) == {"INV-A", "INV-B"}


@pytest.mark.parametrize("n", [10, 50, 100, 500])
def test_ingestion_independent_of_record_count(n):
    frame = pd.read_csv(RAW / "bank.csv").head(n)
    contents = _csv_bytes(frame)
    normalized, info = ingest_file(contents, f"bank_{n}.csv", hinted_role="bank")
    assert info["valid"] is True
    assert info["records"] == len(frame)
    assert normalized is not None
    assert len(normalized) == len(frame)


def test_load_raw_rejects_unsupported_format():
    frame, error = load_raw_dataframe(b"hello", "notes.txt")
    assert frame is None
    assert "Supported formats" in error


def test_existing_canonical_erp_csv():
    contents = (RAW / "erp.csv").read_bytes()
    normalized, info = ingest_file(contents, "erp.csv", hinted_role="supporting")
    assert info["valid"] is True
    assert normalized is not None
    assert "invoice_id" in normalized.columns
    assert len(normalized) > 0
