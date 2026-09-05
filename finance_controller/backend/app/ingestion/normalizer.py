"""
Source normalization layer.

Converts heterogeneous bank / ERP / Razorpay source fields into
canonical internal fields consumed by the reconciliation engine.

Important:
- Raw source fields are preserved.
- Source-specific aliases belong here, NOT in matcher.py.
- This module does not make reconciliation decisions.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

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


def _has_any_column(columns: Iterable[Any], aliases: Iterable[str]) -> bool:
    return _find_column(columns, aliases) is not None


def _original_payload(row: pd.Series) -> Dict[str, Any]:
    return {
        str(key): _clean_value(value)
        for key, value in row.to_dict().items()
    }


# ============================================================
# Bank statement aliases
# ============================================================

BANK_TRANSACTION_ID_ALIASES = [
    "transaction_id",
    "transaction id",
    "txn_id",
    "txn id",
    "txnid",
    "transaction reference",
    "txn reference",
    "transaction no",
    "transaction number",
    "txn no",
]

BANK_DATE_ALIASES = [
    "date",
    "transaction date",
    "transaction_date",
    "txn date",
    "txn_date",
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

BANK_COUNTERPARTY_ALIASES = [
    "counterparty",
    "vendor",
    "merchant",
    "payee",
    "beneficiary",
    "party name",
    "party",
    "customer",
    "customer name",
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
    "ref",
    "reference number",
    "ref no",
    "ref no.",
    "bank reference",
    "transaction reference",
    "utr",
    "utr number",
    "bank utr",
]

BANK_UTR_ALIASES = [
    "utr",
    "utr number",
    "bank utr",
    "bank_utr",
]

BANK_SETTLEMENT_REFERENCE_ALIASES = [
    "settlement reference",
    "settlement_reference",
    "settlement utr",
    "settlement_utr",
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
    "value",
    "txn amount",
]


# ============================================================
# ERP / invoice aliases
# ============================================================

ERP_INVOICE_ALIASES = [
    "invoice_id",
    "invoice id",
    "invoice",
    "invoice number",
    "invoice no",
    "invoice no.",
    "bill number",
    "bill no",
    "bill_id",
]

ERP_DATE_ALIASES = [
    "date",
    "invoice date",
    "invoice_date",
    "bill date",
    "document date",
    "posting date",
]

ERP_AMOUNT_ALIASES = [
    "amount",
    "invoice amount",
    "bill amount",
    "value",
    "total",
    "net amount",
]

ERP_VENDOR_ALIASES = [
    "vendor",
    "supplier",
    "merchant",
    "counterparty",
    "party",
    "party name",
    "vendor name",
    "supplier name",
]

ERP_REFERENCE_ALIASES = [
    "reference",
    "ref",
    "payment reference",
    "payment_reference",
    "transaction reference",
    "txn reference",
    "utr",
    "utr number",
    "bank reference",
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

RAZORPAY_DETECT_ALIASES = (
    RAZORPAY_SETTLEMENT_ID_ALIASES
    + ["settlement utr", "settlement_utr", "gross payments", "gross amount"]
)


# ============================================================
# Source detection
# ============================================================

def detect_source_type(
    df: pd.DataFrame,
    filename: str = "",
    hinted_role: Optional[str] = None,
) -> str:
    """
    Detect BANK / ERP / RAZORPAY / INVOICE / OTHER from columns + filename.

    hinted_role: optional 'bank' or 'supporting' from the upload API.
    """
    name = (filename or "").lower()
    columns = list(df.columns)

    razorpay_hits = sum(
        1 for alias in RAZORPAY_DETECT_ALIASES
        if _has_any_column(columns, [alias])
    )
    bank_statement_shape = (
        _has_any_column(columns, BANK_DEBIT_ALIASES)
        or _has_any_column(columns, BANK_CREDIT_ALIASES)
        or _has_any_column(columns, BANK_NARRATION_ALIASES)
    )
    has_txn_id = _has_any_column(columns, BANK_TRANSACTION_ID_ALIASES)
    has_invoice = _has_any_column(columns, ERP_INVOICE_ALIASES)
    has_vendor = _has_any_column(columns, ERP_VENDOR_ALIASES)
    has_counterparty = _has_any_column(columns, BANK_COUNTERPARTY_ALIASES)

    if "razorpay" in name or "settlement" in name or razorpay_hits >= 2:
        return "RAZORPAY"

    if "invoice" in name and has_invoice:
        return "INVOICE"

    if hinted_role == "bank":
        return "BANK"

    if has_invoice and (has_vendor or _has_any_column(columns, ERP_REFERENCE_ALIASES)):
        if "invoice" in name:
            return "INVOICE"
        return "ERP"

    if hinted_role == "supporting":
        if has_invoice:
            return "INVOICE" if "invoice" in name else "ERP"
        if bank_statement_shape:
            return "BANK"
        return "OTHER"

    if has_txn_id and (has_counterparty or bank_statement_shape):
        return "BANK"

    if bank_statement_shape and not has_invoice:
        return "BANK"

    if has_invoice:
        return "ERP"

    return "OTHER"


def detected_fields(df: pd.DataFrame) -> List[str]:
    return [str(column) for column in df.columns]


# ============================================================
# Bank normalization
# ============================================================

def _derive_bank_amount(
    row: pd.Series,
) -> Tuple[Optional[float], Optional[str], Optional[str]]:
    """
    Derive canonical amount/direction.

    Returns (amount, direction, fatal_error_or_none).
    """
    debit = _parse_amount(_get_value(row, BANK_DEBIT_ALIASES))
    credit = _parse_amount(_get_value(row, BANK_CREDIT_ALIASES))
    amount = _parse_amount(_get_value(row, BANK_AMOUNT_ALIASES))

    debit_present = debit is not None and debit != 0
    credit_present = credit is not None and credit != 0

    has_debit_col = _has_any_column(row.index, BANK_DEBIT_ALIASES)
    has_credit_col = _has_any_column(row.index, BANK_CREDIT_ALIASES)

    if has_debit_col and has_credit_col:
        if debit_present and credit_present:
            return None, None, "ambiguous debit/credit values on the same row"
        if credit_present:
            return abs(credit), "CREDIT", None
        if debit_present:
            return abs(debit), "DEBIT", None
        if amount is not None:
            return abs(amount), None, None
        return None, None, None

    if credit_present:
        return abs(credit), "CREDIT", None
    if debit_present:
        return abs(debit), "DEBIT", None
    if amount is not None:
        return abs(amount), None, None
    return None, None, None


def normalize_bank_row(
    row: pd.Series,
    *,
    source_file: str = "",
    source: str = "BANK",
    original_row: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Convert one heterogeneous bank statement row into
    the application's canonical representation.
    """

    date = _get_value(row, BANK_DATE_ALIASES)
    if date is None:
        date = _get_value(row, BANK_VALUE_DATE_ALIASES)

    amount, direction, amount_error = _derive_bank_amount(row)

    narration = _get_value(row, BANK_NARRATION_ALIASES)
    counterparty = _get_value(row, BANK_COUNTERPARTY_ALIASES) or narration

    reference = _get_value(row, BANK_REFERENCE_ALIASES)
    utr = _get_value(row, BANK_UTR_ALIASES) or reference
    settlement_reference = (
        _get_value(row, BANK_SETTLEMENT_REFERENCE_ALIASES)
        or utr
        or reference
    )

    transaction_id = _get_value(row, BANK_TRANSACTION_ID_ALIASES)
    if transaction_id is None:
        # Usable identifier from real cross-system evidence only.
        transaction_id = utr or reference or settlement_reference

    normalized = {
        "transaction_id": transaction_id,
        "date": _parse_date(date),
        "amount": amount,
        "counterparty": counterparty,
        "bank_utr": utr,
        "bank_reference": reference,
        "settlement_reference": settlement_reference,
        "direction": direction,
        "value_date": _parse_date(
            _get_value(row, BANK_VALUE_DATE_ALIASES)
        ),
        "description": narration,
        "currency": _get_value(row, ["currency", "ccy"]) or "INR",
        "source": source,
        "source_file": source_file,
        "original_row": original_row,
        "original_data": _original_payload(row),
    }

    if amount_error:
        normalized["_row_error"] = amount_error

    return normalized


def normalize_bank_dataframe(
    df: pd.DataFrame,
    *,
    source_file: str = "",
    source: str = "BANK",
) -> pd.DataFrame:
    """
    Normalize an entire bank statement dataframe.
    """
    records = [
        normalize_bank_row(
            row,
            source_file=source_file,
            source=source,
            original_row=int(index) if not isinstance(index, int) else index,
        )
        for index, row in df.iterrows()
    ]

    # Preserve stable integer positions for audit.
    for position, record in enumerate(records):
        if record.get("original_row") is None:
            record["original_row"] = position

    return pd.DataFrame(records)


# ============================================================
# ERP / invoice normalization
# ============================================================

def normalize_erp_row(
    row: pd.Series,
    *,
    source_file: str = "",
    source: str = "ERP",
    original_row: Optional[int] = None,
) -> Dict[str, Any]:
    """Convert one ERP / invoice row into canonical ERP fields."""

    invoice_id = _get_value(row, ERP_INVOICE_ALIASES)
    reference = _get_value(row, ERP_REFERENCE_ALIASES)
    vendor = _get_value(row, ERP_VENDOR_ALIASES)
    amount = _parse_amount(_get_value(row, ERP_AMOUNT_ALIASES))
    date = _parse_date(_get_value(row, ERP_DATE_ALIASES))

    return {
        "invoice_id": invoice_id,
        "date": date,
        "amount": amount,
        "vendor": vendor,
        "reference": reference,
        "currency": _get_value(row, ["currency", "ccy"]) or "INR",
        "source": source,
        "source_file": source_file,
        "original_row": original_row,
        "original_data": _original_payload(row),
    }


def normalize_erp_dataframe(
    df: pd.DataFrame,
    *,
    source_file: str = "",
    source: str = "ERP",
) -> pd.DataFrame:
    records = []
    for position, (index, row) in enumerate(df.iterrows()):
        records.append(
            normalize_erp_row(
                row,
                source_file=source_file,
                source=source,
                original_row=position,
            )
        )
    return pd.DataFrame(records)


# ============================================================
# Razorpay normalization
# ============================================================

def normalize_razorpay_row(
    row: pd.Series,
    *,
    source_file: str = "",
    source: str = "RAZORPAY",
    original_row: Optional[int] = None,
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
        # Existing generic compatibility fields for matcher/ERP path
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

        "currency": "INR",
        "source": source,
        "source_file": source_file,
        "original_row": original_row,

        # Preserve source data
        "original_data": _original_payload(row),
    }

    return normalized


def normalize_razorpay_dataframe(
    df: pd.DataFrame,
    *,
    source_file: str = "",
    source: str = "RAZORPAY",
) -> pd.DataFrame:
    """
    Normalize an entire Razorpay settlement dataframe.
    """
    records = []
    for position, (_, row) in enumerate(df.iterrows()):
        records.append(
            normalize_razorpay_row(
                row,
                source_file=source_file,
                source=source,
                original_row=position,
            )
        )
    return pd.DataFrame(records)
