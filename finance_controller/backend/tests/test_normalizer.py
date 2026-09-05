import pandas as pd

from backend.app.ingestion.normalizer import (
    normalize_bank_dataframe,
    normalize_razorpay_dataframe,
)


def test_hdfc_style_bank_statement():
    df = pd.DataFrame([
        {
            "Date": "03/08/2026",
            "Narration": "NEFT CR-RAZORPAY-RZPAXIS26000001",
            "Cheque / Ref No.": "RZPAXIS26000001",
            "Value Date": "03/08/2026",
            "Withdrawal (Dr)": "",
            "Deposit (Cr)": "98,410.00",
            "Closing Balance": "343,410.00",
        }
    ])

    result = normalize_bank_dataframe(df)

    row = result.iloc[0]

    assert row["date"] == "2026-08-03"
    assert row["amount"] == 98410.0
    assert row["direction"] == "CREDIT"
    assert row["bank_utr"] == "RZPAXIS26000001"


def test_icici_style_bank_statement():
    df = pd.DataFrame([
        {
            "Transaction Date": "04/08/2026",
            "Transaction Remarks": "NEFT-RAZORPAY SETTLEMENT/RZPABC123",
            "Cheque/Ref No.": "RZPABC123",
            "Value Date": "04/08/2026",
            "Withdrawal Amount (INR)": "",
            "Deposit Amount (INR)": "72,500.00",
            "Balance (INR)": "500000.00",
        }
    ])

    result = normalize_bank_dataframe(df)

    row = result.iloc[0]

    assert row["date"] == "2026-08-04"
    assert row["amount"] == 72500.0
    assert row["bank_utr"] == "RZPABC123"


def test_axis_style_bank_statement():
    df = pd.DataFrame([
        {
            "Tran Date": "05-08-2026",
            "Transaction Particulars": "INB/NEFT/RAZORPAY/RZPXYZ789/SETTLEMENT",
            "Chq No": "RZPXYZ789",
            "Value Date": "05-08-2026",
            "Debit(INR)": "",
            "Credit(INR)": "61,250.00",
            "Balance(INR)": "561250.00",
        }
    ])

    result = normalize_bank_dataframe(df)

    row = result.iloc[0]

    assert row["date"] == "2026-08-05"
    assert row["amount"] == 61250.0
    assert row["direction"] == "CREDIT"
    assert row["bank_utr"] == "RZPXYZ789"


def test_utr_is_extracted_from_bank_description():
    df = pd.DataFrame([{
        "transaction_id": "RZP-TXN-001",
        "date": "2026-09-01",
        "counterparty": "UrbanCart",
        "amount": "13375",
        "bank_ref": "BNK-00001",
        "description": "RAZORPAY SETTLEMENT UTR RZP260001",
    }])

    row = normalize_bank_dataframe(df).iloc[0]

    assert row["description"] == "RAZORPAY SETTLEMENT UTR RZP260001"
    assert row["bank_reference"] == "BNK-00001"
    assert row["bank_utr"] == "RZP260001"
    assert row["settlement_reference"] == "RZP260001"


def test_explicit_bank_utr_takes_precedence_over_description():
    df = pd.DataFrame([{
        "transaction_id": "TXN-001",
        "date": "2026-09-01",
        "amount": "100",
        "bank_ref": "BNK-00001",
        "utr": "EXPLICIT-UTR-01",
        "description": "RAZORPAY SETTLEMENT UTR EXTRACTED-UTR-02",
    }])

    row = normalize_bank_dataframe(df).iloc[0]

    assert row["bank_reference"] == "BNK-00001"
    assert row["bank_utr"] == "EXPLICIT-UTR-01"
    assert row["settlement_reference"] == "EXPLICIT-UTR-01"


def test_description_without_utr_does_not_create_settlement_utr():
    df = pd.DataFrame([{
        "transaction_id": "TXN-001",
        "date": "2026-09-01",
        "amount": "100",
        "bank_ref": "BNK-00001",
        "description": "RAZORPAY SETTLEMENT PAYMENT",
    }])

    row = normalize_bank_dataframe(df).iloc[0]

    assert row["description"] == "RAZORPAY SETTLEMENT PAYMENT"
    assert row["bank_reference"] == "BNK-00001"
    assert pd.isna(row["bank_utr"])
    assert pd.isna(row["settlement_reference"])


def test_synthetic_utr_values_are_extracted_generically():
    df = pd.DataFrame([{
        "transaction_id": "TXN-001",
        "date": "2026-09-01",
        "amount": "100",
        "description": "Settlement reference: SYNTHETIC-UTR-98765",
    }])

    row = normalize_bank_dataframe(df).iloc[0]

    assert row["bank_utr"] == "SYNTHETIC-UTR-98765"
    assert row["settlement_reference"] == "SYNTHETIC-UTR-98765"


def test_razorpay_settlement():
    df = pd.DataFrame([
        {
            "Settlement ID": "setl_SYNTH0001",
            "Settlement UTR": "RZPAXIS26000001",
            "Settlement Date": "03/08/2026",
            "Status": "processed",
            "Amount": "98410.00",
            "Fees": "900.00",
            "Tax": "162.00",
            "Gross Payments": "100000.00",
            "Refunds": "500.00",
            "Adjustments": "0",
        }
    ])

    result = normalize_razorpay_dataframe(df)

    row = result.iloc[0]

    assert row["settlement_id"] == "setl_SYNTH0001"
    assert row["settlement_utr"] == "RZPAXIS26000001"
    assert row["settlement_amount"] == 98410.0
    assert row["gross_amount"] == 100000.0
    assert row["refund_amount"] == 500.0
    assert row["fee_amount"] == 900.0
    assert row["tax_amount"] == 162.0