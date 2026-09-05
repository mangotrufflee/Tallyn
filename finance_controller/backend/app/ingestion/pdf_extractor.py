from pathlib import Path
import re

import pandas as pd


# Common bank-statement column names
DATE_ALIASES = {
    "date",
    "tran date",
    "transaction date",
    "transaction_date",
}

VALUE_DATE_ALIASES = {
    "value date",
    "value_date",
}

NARRATION_ALIASES = {
    "narration",
    "transaction remarks",
    "transaction particulars",
    "description",
    "remarks",
}

REFERENCE_ALIASES = {
    "cheque/ref no.",
    "cheque/ref no",
    "cheque no",
    "chq no",
    "reference",
    "reference no",
    "ref no",
}

WITHDRAWAL_ALIASES = {
    "withdrawal",
    "withdrawal amount",
    "debit",
    "debit amount",
}

DEPOSIT_ALIASES = {
    "deposit",
    "deposit amount",
    "credit",
    "credit amount",
}

BALANCE_ALIASES = {
    "closing balance",
    "balance",
}


def clean_column_name(value):
    """Normalize a PDF-extracted column name."""
    value = str(value).strip().lower()
    value = re.sub(r"\s+", " ", value)
    return value


def find_column(columns, aliases):
    """Find the first matching column from a set of aliases."""
    normalized = {
        clean_column_name(column): column
        for column in columns
    }

    for alias in aliases:
        if alias in normalized:
            return normalized[alias]

    return None


def clean_amount(value):
    """Convert bank-statement amount text into a numeric value."""
    if pd.isna(value):
        return None

    value = str(value).strip()

    if not value:
        return None

    # Remove currency symbols, commas and spaces.
    value = re.sub(r"[₹,$,\s]", "", value)

    # Handle accounting-style negatives such as (1234.50)
    if value.startswith("(") and value.endswith(")"):
        value = "-" + value[1:-1]

    try:
        return float(value)
    except ValueError:
        return None


def extract_bank_table(pdf_path):
    """
    Extract a bank statement table from a PDF.

    Uses pdfplumber when available. The output intentionally keeps
    the bank's original-style columns so the existing normalizer
    can process them afterwards.
    """
    pdf_path = Path(pdf_path)

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    try:
        import pdfplumber
    except ImportError as exc:
        raise ImportError(
            "pdfplumber is required for PDF bank statement extraction. "
            "Install it with: pip install pdfplumber"
        ) from exc

    extracted_tables = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()

            for table in tables:
                if not table:
                    continue

                # Remove completely empty rows.
                rows = [
                    row for row in table
                    if row and any(
                        cell is not None and str(cell).strip()
                        for cell in row
                    )
                ]

                if len(rows) < 2:
                    continue

                header = rows[0]

                # Clean header values.
                header = [
                    str(value).strip() if value is not None else ""
                    for value in header
                ]

                df = pd.DataFrame(rows[1:], columns=header)

                # Ignore tables which clearly aren't transaction tables.
                has_date = find_column(df.columns, DATE_ALIASES)
                has_narration = find_column(df.columns, NARRATION_ALIASES)
                has_balance = find_column(df.columns, BALANCE_ALIASES)

                if has_date and (has_narration or has_balance):
                    extracted_tables.append(df)

    if not extracted_tables:
        raise ValueError(
            "No recognizable bank transaction table found in PDF."
        )

    result = pd.concat(
        extracted_tables,
        ignore_index=True
    )

    # Drop fully empty columns.
    result = result.dropna(axis=1, how="all")

    # Drop fully empty rows.
    result = result.dropna(axis=0, how="all")

    return result


def prepare_bank_pdf_dataframe(pdf_path):
    """
    Extract a bank PDF and perform only safe structural cleanup.

    Business normalization is intentionally delegated to
    ingestion.normalizer.
    """
    df = extract_bank_table(pdf_path)

    date_col = find_column(df.columns, DATE_ALIASES)
    value_date_col = find_column(df.columns, VALUE_DATE_ALIASES)
    withdrawal_col = find_column(df.columns, WITHDRAWAL_ALIASES)
    deposit_col = find_column(df.columns, DEPOSIT_ALIASES)

    # Clean dates without changing the source column names.
    for column in [date_col, value_date_col]:
        if column:
            df[column] = pd.to_datetime(
                df[column],
                errors="coerce",
                dayfirst=True,
            )

    # Clean monetary columns.
    for column in [
        withdrawal_col,
        deposit_col,
        find_column(df.columns, BALANCE_ALIASES),
    ]:
        if column:
            df[column] = df[column].apply(clean_amount)

    # Remove rows without a transaction date.
    if date_col:
        df = df[df[date_col].notna()].copy()

    return df.reset_index(drop=True)


def extract_bank_pdf(pdf_path):
    """
    Public entry point used by the application.
    """
    return prepare_bank_pdf_dataframe(pdf_path)


def extract_bank_pdf_bytes(contents: bytes):
    """
    Extract a bank statement table from in-memory PDF bytes.
    Uses the existing extract_bank_pdf path via a temporary file.
    """
    import tempfile
    from pathlib import Path

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as handle:
        handle.write(contents)
        temp_path = handle.name
    try:
        return extract_bank_pdf(temp_path)
    finally:
        try:
            Path(temp_path).unlink()
        except OSError:
            pass