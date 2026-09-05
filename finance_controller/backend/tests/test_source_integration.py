import pandas as pd

from backend.app.ingestion.normalizer import (
    normalize_bank_dataframe,
    normalize_razorpay_dataframe,
)


def test_raw_bank_to_canonical():
    raw = pd.DataFrame([
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

    normalized = normalize_bank_dataframe(raw)

    assert "transaction_id" in normalized.columns
    assert "date" in normalized.columns
    assert "amount" in normalized.columns
    assert "counterparty" in normalized.columns
    assert "bank_utr" in normalized.columns

    assert normalized.iloc[0]["amount"] == 98410.0
    assert normalized.iloc[0]["bank_utr"] == "RZPAXIS26000001"


def test_raw_razorpay_to_canonical():
    raw = pd.DataFrame([
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

    normalized = normalize_razorpay_dataframe(raw)

    assert "settlement_id" in normalized.columns
    assert "settlement_utr" in normalized.columns
    assert "settlement_amount" in normalized.columns

    assert normalized.iloc[0]["settlement_id"] == "setl_SYNTH0001"
    assert normalized.iloc[0]["settlement_utr"] == "RZPAXIS26000001"
    assert normalized.iloc[0]["settlement_amount"] == 98410.0