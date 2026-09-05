"""
Source normalization layer.

Converts heterogeneous bank / Razorpay source fields into
canonical internal fields consumed by the reconciliation engine.

Important:
- Raw source fields are preserved.
- Source-specific aliases belong here, NOT in matcher.py.
- This module does not make reconciliation decisions.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, Optional

import pandas as pd


# ============================================================
# Generic helpers
# ============================================================

def _clean_column_name(value: Any) -> str:
    """Normalize a column name for alias matching."""
    value = str(value).strip().lower()
    value = re.sub(r"[\n\r\t]+", " ", value)
    value = re.sub(r"[_\-/]+", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _clean_value(value: Any) -> Any:
    """Return None for empty/null values while preserving useful data."""
    if value is None:
        return None

    if pd.isna(value):
        return None

    if isinstance(value, str):
        value = value.strip()
        return value if value else None

    return value


def _parse_amount(value: Any) -> Optional[float]:
    """
    Convert common Indian banking amount formats to float.

    Handles examples such as:
        98,410.00
        ₹98,410.00
        INR 98,410
        (1,250.00)
        -1250
    """
    value = _clean_value(value)

    if value is None:
        return None

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()

    if not text:
        return None

    negative = (
        text.startswith("(")
        and text.endswith(")")
    )

    text = text.replace(",", "")
    text = text.replace("₹", "")
    text = text.replace("INR", "")
    text = text.replace("Rs.", "")
    text = text.replace("Rs", "")
    text = text.strip()

    text = re.sub(r"[^\d.\-]", "", text)

    if not text:
        return None

    try:
        amount = float(text)
    except ValueError:
        return None

    if negative:
        amount = -abs(amount)

    return amount


def _parse_date(value: Any) -> Optional[str]:
    """Normalize a date to ISO YYYY-MM-DD."""
    value = _clean_value(value)

    if value is None:
        return None

    try:
        parsed = pd.to_datetime(value, dayfirst=True, errors="coerce")

        if pd.isna(parsed):
            return None

        return parsed.strftime("%Y-%m-%d")

    except Exception:
        return None


def _find_column(
    columns: Iterable[Any],
    aliases: Iterable[str],
) -> Optional[Any]:
    """
    Find the first source column matching one of the aliases.
    Matching is case-insensitive and tolerant of spaces/underscores.
    """
    normalized = {
        _clean_column_name(column): column
        for column in columns
    }

    for alias in aliases:
        key = _clean_column_name(alias)

        if key in normalized:
            return normalized[key]

    return None


def _get_value(
    row: pd.Series,
    aliases: Iterable[str],
) -> Any:
    """Read a value from a row using source aliases."""
    column = _find_column(row.index, aliases)

    if column is None:
        return None

    return _clean_value(row[column])


# ============================================================
# Bank statement aliases
# ============================================================

BANK_DATE_ALIASES = [
    "date",
    "transaction date",
    "transaction_date",
    "tran date",
    "tran_date",
    "posting date",
    "posting_date",
]

BANK_VALUE_DATE_ALIASES = [
    "value date",
    "value_date",
]

BANK_NARRATION_ALIASES = [
    "narration",
    "transaction remarks",
    "transaction_remarks",
    "transaction particulars",
    "transaction_particulars",
    "description",
    "remarks",
    "particulars",
]

BANK_REFERENCE_ALIASES = [
    "cheque / ref no.",
    "cheque / ref no",
    "cheque/ref no",
    "cheque/ref no.",
    "cheque ref no",
    "cheque no",
    "chq no",
    "reference",
    "reference number",
    "ref no",
    "ref no.",
    "utr",
    "utr number",
    "bank utr",
    "bank reference",
]

BANK_DEBIT_ALIASES = [
    "withdrawal",
    "withdrawal (dr)",
    "withdrawal amount",
    "withdrawal amount (inr)",
    "debit",
    "debit amount",
    "debit(inr)",
    "debit (inr)",
]

BANK_CREDIT_ALIASES = [
    "deposit",
    "deposit (cr)",
    "deposit amount",
    "deposit amount (inr)",
    "credit",
    "credit amount",
    "credit(inr)",
    "credit (inr)",
]

BANK_AMOUNT_ALIASES = [
    "amount",
    "transaction amount",
]


# ============================================================
# Razorpay aliases
# ============================================================

RAZORPAY_SETTLEMENT_ID_ALIASES = [
    "settlement id",
    "settlement_id",
]

RAZORPAY_UTR_ALIASES = [
    "settlement utr",
    "settlement_utr",
    "utr",
    "utr number",
]

RAZORPAY_DATE_ALIASES = [
    "settlement date",
    "settlement_date",
    "date",
]

RAZORPAY_AMOUNT_ALIASES = [
    "settlement amount",
    "settlement_amount",
    "amount",
]

RAZORPAY_GROSS_ALIASES = [
    "gross amount",
    "gross_amount",
    "gross payments",
    "gross payment",
]

RAZORPAY_REFUND_ALIASES = [
    "refund",
    "refunds",
    "refund amount",
    "refund_amount",
]

RAZORPAY_FEE_ALIASES = [
    "fee",
    "fees",
    "fee amount",
    "fee_amount",
]

RAZORPAY_TAX_ALIASES = [
    "tax",
    "tax amount",
    "tax_amount",
]

RAZORPAY_ADJUSTMENT_ALIASES = [
    "adjustment",
    "adjustments",
    "adjustment amount",
    "adjustment_amount",
]

RAZORPAY_STATUS_ALIASES = [
    "status",
]


# ============================================================
# Bank normalization
# ============================================================

def normalize_bank_row(row: pd.Series) -> Dict[str, Any]:
    """
    Convert one heterogeneous bank statement row into
    the application's canonical representation.
    """

    date = _get_value(row, BANK_DATE_ALIASES)

    debit = _parse_amount(
        _get_value(row, BANK_DEBIT_ALIASES)
    )

    credit = _parse_amount(
        _get_value(row, BANK_CREDIT_ALIASES)
    )

    amount = _parse_amount(
        _get_value(row, BANK_AMOUNT_ALIASES)
    )

    # For banking statements, a credit/deposit is the amount
    # relevant to Razorpay settlement reconciliation.
    if credit is not None:
        canonical_amount = credit
        direction = "CREDIT"
    elif debit is not None:
        canonical_amount = debit
        direction = "DEBIT"
    else:
        canonical_amount = amount
        direction = None

    narration = _get_value(
        row,
        BANK_NARRATION_ALIASES,
    )

    reference = _get_value(
        row,
        BANK_REFERENCE_ALIASES,
    )

    normalized = {
        # Existing canonical fields
        "transaction_id": reference or f"ROW_{id(row)}",
        "date": _parse_date(date),
        "amount": canonical_amount,
        "counterparty": narration,

        # New canonical settlement evidence
        "bank_utr": reference,
        "bank_reference": reference,
        "settlement_reference": reference,

        # Useful banking metadata
        "direction": direction,
        "value_date": _parse_date(
            _get_value(row, BANK_VALUE_DATE_ALIASES)
        ),
        "description": narration,

        # Preserve source data for auditability
        "original_data": {
            str(key): _clean_value(value)
            for key, value in row.to_dict().items()
        },
    }

    return normalized


def normalize_bank_dataframe(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Normalize an entire bank statement dataframe.
    """
    records = [
        normalize_bank_row(row)
        for _, row in df.iterrows()
    ]

    return pd.DataFrame(records)


# ============================================================
# Razorpay normalization
# ============================================================

def normalize_razorpay_row(
    row: pd.Series,
) -> Dict[str, Any]:
    """
    Convert one Razorpay settlement/reconciliation row
    into canonical settlement evidence.
    """

    settlement_id = _get_value(
        row,
        RAZORPAY_SETTLEMENT_ID_ALIASES,
    )

    settlement_utr = _get_value(
        row,
        RAZORPAY_UTR_ALIASES,
    )

    settlement_date = _get_value(
        row,
        RAZORPAY_DATE_ALIASES,
    )

    settlement_amount = _parse_amount(
        _get_value(row, RAZORPAY_AMOUNT_ALIASES)
    )

    normalized = {
        # Existing generic compatibility fields
        "invoice_id": settlement_id,
        "reference": settlement_utr or settlement_id,
        "date": _parse_date(settlement_date),
        "vendor": "RAZORPAY",
        "amount": settlement_amount,

        # Canonical Razorpay settlement evidence
        "settlement_id": settlement_id,
        "settlement_utr": settlement_utr,
        "settlement_reference": settlement_utr or settlement_id,
        "settlement_date": _parse_date(settlement_date),
        "settlement_amount": settlement_amount,

        # Settlement breakdown
        "gross_amount": _parse_amount(
            _get_value(row, RAZORPAY_GROSS_ALIASES)
        ),
        "refund_amount": _parse_amount(
            _get_value(row, RAZORPAY_REFUND_ALIASES)
        ) or 0.0,
        "fee_amount": _parse_amount(
            _get_value(row, RAZORPAY_FEE_ALIASES)
        ) or 0.0,
        "tax_amount": _parse_amount(
            _get_value(row, RAZORPAY_TAX_ALIASES)
        ) or 0.0,
        "adjustment_amount": _parse_amount(
            _get_value(row, RAZORPAY_ADJUSTMENT_ALIASES)
        ) or 0.0,

        "status": _get_value(
            row,
            RAZORPAY_STATUS_ALIASES,
        ),

        # Preserve source data
        "original_data": {
            str(key): _clean_value(value)
            for key, value in row.to_dict().items()
        },
    }

    return normalized


def normalize_razorpay_dataframe(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Normalize an entire Razorpay settlement dataframe.
    """
    records = [
        normalize_razorpay_row(row)
        for _, row in df.iterrows()
    ]

    return pd.DataFrame(records)