from pathlib import Path

import pandas as pd

from backend.app.ingestion.pdf_extractor import extract_bank_pdf
from backend.app.ingestion.normalizer import normalize_bank_dataframe


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PDF_PATH = PROJECT_ROOT / "data" / "raw" / "hdfc_synthetic_bank_statement.pdf"


def test_hdfc_pdf_extraction():
    assert PDF_PATH.exists(), f"PDF not found: {PDF_PATH}"

    df = extract_bank_pdf(PDF_PATH)

    assert isinstance(df, pd.DataFrame)
    assert not df.empty

    columns = {
        str(column).strip().lower()
        for column in df.columns
    }

    assert "date" in columns
    assert "narration" in columns


def test_hdfc_pdf_to_canonical_normalization():
    assert PDF_PATH.exists(), f"PDF not found: {PDF_PATH}"

    raw_df = extract_bank_pdf(PDF_PATH)
    normalized_df = normalize_bank_dataframe(raw_df)

    assert not normalized_df.empty

    required_columns = {
        "transaction_id",
        "date",
        "amount",
        "counterparty",
        "description",
        "original_data",
    }

    assert required_columns.issubset(
        set(normalized_df.columns)
    )

    assert normalized_df["amount"].notna().all()
    assert normalized_df["date"].notna().all()