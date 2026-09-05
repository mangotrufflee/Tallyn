"""
Production ingestion pipeline.

RAW FILE → source detection → normalization → validation → canonical records
"""

from __future__ import annotations

import tempfile
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from .normalizer import (
    detect_source_type,
    detected_fields,
    normalize_bank_dataframe,
    normalize_erp_dataframe,
    normalize_razorpay_dataframe,
)
from .pdf_extractor import extract_bank_pdf


SUPPORTED_SUFFIXES = {".csv", ".xlsx", ".xls", ".pdf"}


def _empty_info(filename: str, **extra) -> Dict[str, Any]:
    info = {
        "filename": filename,
        "records": 0,
        "columns": [],
        "detected_fields": [],
        "source_type": extra.get("source_type", "OTHER"),
        "valid": False,
        "status": "FATAL",
        "errors": [],
        "warnings": [],
    }
    info.update(extra)
    return info


def load_raw_dataframe(
    contents: bytes,
    filename: str,
) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    """Load CSV/XLSX/XLS/PDF into a raw dataframe. Returns (frame, fatal_error)."""

    suffix = Path(filename or "").suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        return None, "Supported formats are CSV, XLSX, XLS, and PDF."

    if not contents:
        return None, "File is empty or unreadable."

    try:
        if suffix == ".pdf":
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as handle:
                handle.write(contents)
                temp_path = handle.name
            try:
                frame = extract_bank_pdf(temp_path)
            finally:
                try:
                    Path(temp_path).unlink()
                except OSError:
                    pass
            return frame, None

        buffer = BytesIO(contents)
        if suffix == ".csv":
            frame = pd.read_csv(buffer)
        else:
            frame = pd.read_excel(buffer)
        return frame, None
    except Exception as exc:
        return None, f"File could not be read: {exc}"


def normalize_by_source(
    frame: pd.DataFrame,
    source_type: str,
    filename: str,
) -> pd.DataFrame:
    if source_type == "BANK":
        return normalize_bank_dataframe(
            frame,
            source_file=filename,
            source="BANK",
        )
    if source_type == "RAZORPAY":
        return normalize_razorpay_dataframe(
            frame,
            source_file=filename,
            source="RAZORPAY",
        )
    if source_type in {"ERP", "INVOICE"}:
        return normalize_erp_dataframe(
            frame,
            source_file=filename,
            source=source_type,
        )

    if any("invoice" in str(c).lower() for c in frame.columns):
        return normalize_erp_dataframe(
            frame,
            source_file=filename,
            source="OTHER",
        )
    return normalize_bank_dataframe(
        frame,
        source_file=filename,
        source="OTHER",
    )


def _nonempty(series: pd.Series) -> pd.Series:
    text = series.astype("string")
    return series.notna() & text.str.strip().ne("") & text.str.lower().ne("none")


def validate_canonical_bank(df: pd.DataFrame) -> Tuple[List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []

    if df is None or df.empty:
        return ["The file contains no records."], warnings

    if "_row_error" in df.columns:
        for idx, message in df["_row_error"].dropna().items():
            errors.append(f"Row {idx}: {message}")

    if "transaction_id" not in df.columns or not _nonempty(df["transaction_id"]).any():
        errors.append("No usable transaction identifier.")
    else:
        missing_id = int((~_nonempty(df["transaction_id"])).sum())
        if missing_id:
            errors.append(
                f"{missing_id} row(s) are missing a usable transaction identifier."
            )
        duplicate_count = int(
            df.loc[_nonempty(df["transaction_id"]), "transaction_id"]
            .astype(str)
            .str.strip()
            .duplicated()
            .sum()
        )
        if duplicate_count:
            errors.append(
                f"{duplicate_count} duplicate transaction_id value(s) found."
            )

    if "date" not in df.columns or not _nonempty(df["date"]).any():
        errors.append("No usable date.")
    else:
        missing_dates = int((~_nonempty(df["date"])).sum())
        if missing_dates:
            errors.append(f"{missing_dates} row(s) have unusable dates.")

    if "amount" not in df.columns or df["amount"].notna().sum() == 0:
        errors.append("No usable amount.")
    else:
        missing_amounts = int(df["amount"].isna().sum())
        if missing_amounts:
            errors.append(f"{missing_amounts} row(s) have unusable amounts.")

    if "counterparty" not in df.columns or not _nonempty(df["counterparty"]).all():
        missing = (
            0
            if "counterparty" not in df.columns
            else int((~_nonempty(df["counterparty"])).sum())
        )
        if missing:
            warnings.append(f"{missing} row(s) are missing counterparty/vendor.")

    ref_cols = [
        c for c in ("bank_utr", "bank_reference", "settlement_reference")
        if c in df.columns
    ]
    if ref_cols:
        has_ref = pd.Series(False, index=df.index)
        for col in ref_cols:
            has_ref = has_ref | _nonempty(df[col])
        missing_ref = int((~has_ref).sum())
        if missing_ref:
            warnings.append(f"{missing_ref} row(s) have no reference/UTR.")
    else:
        warnings.append("Reference/UTR fields are unavailable.")

    return errors, warnings


def validate_canonical_erp(df: pd.DataFrame) -> Tuple[List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []

    if df is None or df.empty:
        return ["The file contains no records."], warnings

    if "invoice_id" not in df.columns or not _nonempty(df["invoice_id"]).any():
        errors.append("No usable invoice identifier.")
    else:
        missing_id = int((~_nonempty(df["invoice_id"])).sum())
        if missing_id:
            errors.append(f"{missing_id} row(s) are missing invoice_id.")
        duplicate_count = int(
            df.loc[_nonempty(df["invoice_id"]), "invoice_id"]
            .astype(str)
            .str.strip()
            .duplicated()
            .sum()
        )
        if duplicate_count:
            errors.append(f"{duplicate_count} duplicate invoice_id value(s) found.")

    if "date" not in df.columns or not _nonempty(df["date"]).any():
        errors.append("No usable date.")
    else:
        missing_dates = int((~_nonempty(df["date"])).sum())
        if missing_dates:
            errors.append(f"{missing_dates} row(s) have unusable dates.")

    if "amount" not in df.columns or df["amount"].notna().sum() == 0:
        errors.append("No usable amount.")
    else:
        missing_amounts = int(df["amount"].isna().sum())
        if missing_amounts:
            errors.append(f"{missing_amounts} row(s) have unusable amounts.")

    if "vendor" not in df.columns or not _nonempty(df["vendor"]).all():
        missing = (
            0 if "vendor" not in df.columns else int((~_nonempty(df["vendor"])).sum())
        )
        if missing:
            warnings.append(f"{missing} row(s) are missing vendor.")

    if "reference" not in df.columns or not _nonempty(df["reference"]).all():
        missing = (
            0
            if "reference" not in df.columns
            else int((~_nonempty(df["reference"])).sum())
        )
        if missing:
            warnings.append(f"{missing} row(s) are missing reference.")

    return errors, warnings


def _prepare_for_engine(df: pd.DataFrame, role: str) -> pd.DataFrame:
    """Cast types expected by the existing reconciliation engine."""
    if df is None or df.empty:
        return df

    out = df.copy()
    if "_row_error" in out.columns:
        out = out.drop(columns=["_row_error"])

    if "date" in out.columns:
        out["date"] = pd.to_datetime(out["date"], errors="coerce")
    if "amount" in out.columns:
        out["amount"] = pd.to_numeric(out["amount"], errors="coerce")

    if role == "bank":
        if "counterparty" in out.columns:
            out["counterparty"] = out["counterparty"].fillna("").astype(str)
        if "transaction_id" in out.columns:
            out["transaction_id"] = out["transaction_id"].astype(str)
    else:
        if "vendor" in out.columns:
            out["vendor"] = out["vendor"].fillna("").astype(str)
        if "reference" in out.columns:
            out["reference"] = out["reference"].fillna("").astype(str)
        if "invoice_id" in out.columns:
            out["invoice_id"] = out["invoice_id"].astype(str)

    return out


def ingest_file(
    contents: bytes,
    filename: str,
    *,
    hinted_role: Optional[str] = None,
    source_type_override: Optional[str] = None,
) -> Tuple[Optional[pd.DataFrame], Dict[str, Any]]:
    """
    Ingest one uploaded file into canonical records.

    hinted_role: 'bank' or 'supporting'
    source_type_override: explicit BANK/ERP/RAZORPAY/INVOICE/OTHER when detection is uncertain
    """
    filename = filename or "upload"

    raw, load_error = load_raw_dataframe(contents, filename)
    if load_error:
        return None, _empty_info(filename, errors=[load_error])

    if raw is None or raw.empty:
        return None, _empty_info(
            filename,
            columns=detected_fields(raw) if raw is not None else [],
            errors=["The file contains no records."],
        )

    source_type = (source_type_override or "").upper() or detect_source_type(
        raw,
        filename=filename,
        hinted_role=hinted_role,
    )

    if source_type == "OTHER" and hinted_role == "supporting" and not source_type_override:
        info = _empty_info(
            filename,
            records=len(raw),
            columns=detected_fields(raw),
            detected_fields=detected_fields(raw),
            source_type="OTHER",
            errors=[
                "Unable to determine source type safely. "
                "Provide source_type as ERP, RAZORPAY, or INVOICE."
            ],
        )
        return None, info

    normalized = normalize_by_source(raw, source_type, filename)

    if source_type == "BANK" or hinted_role == "bank":
        errors, warnings = validate_canonical_bank(normalized)
        role = "bank"
    else:
        errors, warnings = validate_canonical_erp(normalized)
        role = "supporting"

    if errors:
        status = "FATAL"
        valid = False
    elif warnings:
        status = "WARNING"
        valid = True
    else:
        status = "VALID"
        valid = True

    info = {
        "filename": filename,
        "records": int(len(normalized)),
        "columns": detected_fields(raw),
        "detected_fields": detected_fields(raw),
        "source_type": source_type,
        "valid": valid,
        "status": status,
        "errors": errors,
        "warnings": warnings,
    }

    if not valid:
        return None, info

    return _prepare_for_engine(normalized, role), info


def ingest_supporting_files(
    files: List[Tuple[bytes, str]],
    *,
    source_type_overrides: Optional[List[Optional[str]]] = None,
) -> Tuple[Optional[pd.DataFrame], List[Dict[str, Any]], Dict[str, Any]]:
    """
    Normalize multiple supporting documents independently, then concatenate.

    Does not merge rows incorrectly during normalization — each file keeps
    source / source_file identity.
    """
    frames: List[pd.DataFrame] = []
    infos: List[Dict[str, Any]] = []
    overrides = source_type_overrides or [None] * len(files)

    for index, (contents, filename) in enumerate(files):
        override = overrides[index] if index < len(overrides) else None
        frame, info = ingest_file(
            contents,
            filename,
            hinted_role="supporting",
            source_type_override=override,
        )
        infos.append(info)
        if frame is not None and info.get("valid"):
            frames.append(frame)

    summary_errors = []
    summary_warnings = []
    for info in infos:
        if not info.get("valid"):
            summary_errors.append(
                f"{info.get('filename')}: "
                + "; ".join(info.get("errors") or ["invalid"])
            )
        summary_warnings.extend(
            [
                f"{info.get('filename')}: {warning}"
                for warning in info.get("warnings") or []
            ]
        )

    if not frames or summary_errors:
        combined_info = {
            "filename": ", ".join(info.get("filename") or "" for info in infos),
            "records": int(sum(info.get("records") or 0 for info in infos)),
            "columns": [],
            "detected_fields": [],
            "source_type": "MIXED",
            "valid": False,
            "status": "FATAL",
            "errors": summary_errors or ["No valid supporting documents."],
            "warnings": summary_warnings,
            "files": infos,
        }
        return None, infos, combined_info

    combined = pd.concat(frames, ignore_index=True)
    errors, warnings = validate_canonical_erp(combined)
    warnings = summary_warnings + warnings
    status = "FATAL" if errors else ("WARNING" if warnings else "VALID")
    combined_info = {
        "filename": ", ".join(info.get("filename") or "" for info in infos),
        "records": int(len(combined)),
        "columns": list(combined.columns.astype(str)),
        "detected_fields": list(combined.columns.astype(str)),
        "source_type": "MIXED" if len(infos) > 1 else infos[0].get("source_type"),
        "valid": not errors,
        "status": status,
        "errors": errors,
        "warnings": warnings,
        "files": infos,
    }
    if errors:
        return None, infos, combined_info

    return _prepare_for_engine(combined, "supporting"), infos, combined_info
