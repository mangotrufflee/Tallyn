from pathlib import Path

import pandas as pd

from backend.app.ingestion.normalizer import (
    normalize_razorpay_dataframe,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]

RAZORPAY_PATH = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "razorpay_settlement_recon_raw.csv"
)


def test_razorpay_normalization():
    assert RAZORPAY_PATH.exists(), (
        f"Razorpay file not found: {RAZORPAY_PATH}"
    )

    raw_df = pd.read_csv(RAZORPAY_PATH)

    normalized_df = normalize_razorpay_dataframe(
        raw_df
    )

    assert not normalized_df.empty

    required_columns = {
        "invoice_id",
        "reference",
        "date",
        "amount",
        "vendor",
        "settlement_id",
        "settlement_utr",
        "settlement_reference",
        "settlement_date",
        "settlement_amount",
        "gross_amount",
        "refund_amount",
        "fee_amount",
        "tax_amount",
        "adjustment_amount",
        "status",
        "original_data",
    }

    missing = (
        required_columns
        - set(normalized_df.columns)
    )

    assert not missing, (
        f"Missing Razorpay columns: {missing}"
    )

    assert normalized_df["amount"].notna().all()

    assert normalized_df["settlement_id"].notna().all()


def test_razorpay_normalized_output():
    raw_df = pd.read_csv(RAZORPAY_PATH)

    normalized_df = normalize_razorpay_dataframe(
        raw_df
    )

    print(
        "\nNORMALIZED RAZORPAY DATA:"
    )

    print(
        normalized_df.head(5).to_string(
            index=False
        )
    )

    assert len(normalized_df) > 0