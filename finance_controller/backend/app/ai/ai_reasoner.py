"""
Data-driven AI reconciliation reasoner.

Builds prompts from the actual uploaded bank row and candidate evidence.
Does not hardcode benchmark IDs, vendors, or expected answers.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, Iterable, List, Optional, Sequence

from openai import OpenAI


# Fields to surface when present on a bank/ERP record.
BANK_EVIDENCE_FIELDS = (
    ("transaction_id", "Transaction ID"),
    ("date", "Date"),
    ("amount", "Amount"),
    ("currency", "Currency"),
    ("counterparty", "Counterparty"),
    ("bank_utr", "Bank UTR"),
    ("utr", "UTR"),
    ("bank_reference", "Bank reference"),
    ("settlement_reference", "Settlement reference"),
    ("description", "Description"),
    ("direction", "Direction"),
    ("value_date", "Value date"),
    ("source", "Source"),
    ("source_file", "Source file"),
)

CANDIDATE_EVIDENCE_FIELDS = (
    ("invoice_id", "Invoice / settlement ID"),
    ("date", "Date"),
    ("amount", "Amount"),
    ("currency", "Currency"),
    ("vendor", "Vendor"),
    ("reference", "Reference"),
    ("settlement_utr", "Settlement UTR"),
    ("settlement_reference", "Settlement reference"),
    ("settlement_id", "Settlement ID"),
    ("settlement_amount", "Settlement amount"),
    ("gross_amount", "Gross amount"),
    ("fee_amount", "Fee amount"),
    ("tax_amount", "Tax amount"),
    ("refund_amount", "Refund amount"),
    ("adjustment_amount", "Adjustment amount"),
    ("status", "Status"),
    ("source", "Source"),
    ("source_file", "Source file"),
)

CANDIDATE_SCORE_FIELDS = (
    ("final_score", "Overall deterministic score"),
    ("amount_score", "Amount similarity"),
    ("vendor_score", "Vendor similarity"),
    ("date_score", "Date similarity"),
    ("reference_score", "Reference similarity"),
    ("settlement_reference_score", "Settlement reference similarity"),
)


def _row_get(row: Any, key: str) -> Any:
    if row is None:
        return None
    if isinstance(row, dict):
        return row.get(key)
    try:
        if hasattr(row, "index") and key in row.index:
            value = row[key]
        else:
            value = row.get(key) if hasattr(row, "get") else None
    except Exception:
        return None

    try:
        import pandas as pd

        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        if pd.isna(value):
            return None
    except Exception:
        if value is None:
            return None

    if isinstance(value, str) and not value.strip():
        return None
    return value


def _format_value(key: str, value: Any) -> str:
    if value is None:
        return "unavailable"

    if key in {
        "amount",
        "settlement_amount",
        "gross_amount",
        "fee_amount",
        "tax_amount",
        "refund_amount",
        "adjustment_amount",
    }:
        try:
            number = float(value)
            return f"{number:,.2f}"
        except (TypeError, ValueError):
            return str(value)

    return str(value)


def _format_evidence_block(
    row: Any,
    field_specs: Sequence[tuple],
) -> str:
    lines: List[str] = []
    for key, label in field_specs:
        value = _row_get(row, key)
        if value is None:
            continue
        lines.append(f"{label}: {_format_value(key, value)}")

    if not lines:
        return "(no additional fields available)"
    return "\n".join(lines)


def _unavailable_notes(row: Any, field_specs: Sequence[tuple]) -> List[str]:
    notes = []
    important_missing = {
        "bank_utr",
        "utr",
        "bank_reference",
        "settlement_reference",
        "reference",
        "settlement_utr",
        "vendor",
        "counterparty",
    }
    present_keys = {
        key for key, _ in field_specs if _row_get(row, key) is not None
    }
    for key, label in field_specs:
        if key in important_missing and key not in present_keys:
            # Only mention once per conceptual group
            if key in {"bank_utr", "utr"} and (
                "bank_utr" in present_keys or "utr" in present_keys
            ):
                continue
            notes.append(f"{label}: unavailable")
    # Deduplicate similar notes
    return list(dict.fromkeys(notes))


def enrich_candidates_with_source_rows(
    candidates: Iterable[Dict[str, Any]],
    erp,
) -> List[Dict[str, Any]]:
    """
    Attach extra normalized ERP/settlement fields to matcher candidates
    without changing matcher.py.
    """
    enriched: List[Dict[str, Any]] = []

    for index, candidate in enumerate(candidates, start=1):
        item = dict(candidate)
        item["candidate_id"] = f"C{index}"
        invoice_id = str(item.get("invoice_id", "")).strip()

        if erp is not None and invoice_id:
            try:
                matches = erp[
                    erp["invoice_id"].astype(str).str.strip() == invoice_id
                ]
                if not matches.empty:
                    source_row = matches.iloc[0]
                    for key, _ in CANDIDATE_EVIDENCE_FIELDS:
                        if key not in item or item.get(key) in (None, ""):
                            value = _row_get(source_row, key)
                            if value is not None:
                                item[key] = value
            except Exception:
                pass

        enriched.append(item)

    return enriched


def build_ai_prompt(bank_row, candidates, erp=None):
    """
    Build a prompt from the actual current bank row and candidates.

    Optional erp dataframe enriches candidates with settlement / source fields.
    """
    if erp is not None:
        candidates = enrich_candidates_with_source_rows(candidates, erp)
    else:
        candidates = enrich_candidates_with_source_rows(candidates, None)

    bank_block = _format_evidence_block(bank_row, BANK_EVIDENCE_FIELDS)
    bank_missing = _unavailable_notes(bank_row, BANK_EVIDENCE_FIELDS)

    prompt = f"""
You are a cautious AI finance reconciliation assistant.

Your job is to decide whether the BANK TRANSACTION matches
ONE of the PROVIDED CANDIDATES using only the evidence given.

Rules you must follow:
- You may ONLY select a candidate ID / invoice ID from the list below.
- You MUST NOT invent invoice IDs, UTRs, vendors, amounts, or dates.
- Missing evidence is UNAVAILABLE, not a mismatch.
- Conflicting evidence is a CONFLICT.
- Prefer REVIEW over an unsupported MATCH.
- Prefer EXCEPTION only when no candidate exists or none is usable.
- Confidence is advisory only; do not treat high confidence as proof.
- Do not choose a candidate merely because it has the highest numeric score.
  Explain the evidence.

Evidence priority (use only when present):
1. Cross-system reference / UTR / settlement reference
2. Amount consistency
3. Settlement arithmetic when gross/fee/tax/net fields are present
4. Date consistency
5. Vendor / counterparty similarity
6. Other available evidence
7. Conflicting evidence

Settlement arithmetic guidance (only if those fields exist):
- If gross, fees/tax/refunds/adjustments, and settlement/net amounts are present,
  check whether they are consistent with the bank amount.
- Do NOT invent fee or tax values.

Material amount differences are serious.
If amounts conflict materially and no supplied settlement evidence explains
the difference, choose REVIEW even if vendor/date/reference look similar.

==================================================
BANK TRANSACTION
==================================================
{bank_block}
"""

    if bank_missing:
        prompt += "\nUnavailable bank evidence:\n"
        prompt += "\n".join(f"- {note}" for note in bank_missing)
        prompt += "\n"

    prompt += """
==================================================
CANDIDATES
==================================================
"""

    if not candidates:
        prompt += "\nNo candidates were provided.\n"
    else:
        for candidate in candidates:
            prompt += f"""
---
Candidate ID: {candidate.get("candidate_id")}
"""
            prompt += _format_evidence_block(
                candidate,
                CANDIDATE_EVIDENCE_FIELDS,
            )
            prompt += "\nDeterministic scores:\n"
            prompt += _format_evidence_block(
                candidate,
                CANDIDATE_SCORE_FIELDS,
            )
            missing = _unavailable_notes(
                candidate,
                CANDIDATE_EVIDENCE_FIELDS,
            )
            if missing:
                prompt += "\nUnavailable on this candidate:\n"
                prompt += "\n".join(f"- {note}" for note in missing)
            prompt += "\n"

    allowed = [
        str(c.get("invoice_id")).strip()
        for c in candidates
        if c.get("invoice_id") not in (None, "")
    ]

    prompt += f"""
==================================================
ALLOWED SELECTED_INVOICE VALUES
==================================================
{json.dumps(allowed)}

If you cannot support a MATCH, set selected_invoice to null.

==================================================
OUTPUT FORMAT
==================================================
Return ONLY valid JSON with exactly this structure:
{{
  "decision": "MATCH",
  "selected_invoice": null,
  "confidence": 0,
  "reason": "Explain which evidence matched, conflicted, or was unavailable.",
  "risk": "LOW"
}}

decision must be one of: MATCH, REVIEW, EXCEPTION
risk must be one of: LOW, MEDIUM, HIGH
confidence must be a number from 0 to 100
selected_invoice must be null or one of the allowed values above
"""

    return prompt


def _strip_code_fence(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    return cleaned


def _normalize_invoice_token(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def validate_ai_response(
    raw_response,
    allowed_invoice_ids: Optional[Iterable[Any]] = None,
):
    """
    Validate AI JSON and optionally enforce candidate-set membership.
    """
    try:
        if raw_response is None:
            return {
                "valid": False,
                "error": "Empty AI response",
                "result": None,
            }

        cleaned_response = _strip_code_fence(str(raw_response))
        result = json.loads(cleaned_response)

        required_fields = [
            "decision",
            "selected_invoice",
            "confidence",
            "reason",
            "risk",
        ]

        for field in required_fields:
            if field not in result:
                return {
                    "valid": False,
                    "error": f"Missing field: {field}",
                    "result": None,
                }

        decision = str(result["decision"]).strip().upper()
        if decision not in {"MATCH", "REVIEW", "EXCEPTION"}:
            return {
                "valid": False,
                "error": "Invalid decision",
                "result": None,
            }
        result["decision"] = decision

        if not isinstance(result["confidence"], (int, float)):
            return {
                "valid": False,
                "error": "Confidence must be numeric",
                "result": None,
            }

        if not 0 <= float(result["confidence"]) <= 100:
            return {
                "valid": False,
                "error": "Confidence must be between 0 and 100",
                "result": None,
            }

        risk = str(result["risk"]).strip().upper()
        if risk not in {"LOW", "MEDIUM", "HIGH"}:
            return {
                "valid": False,
                "error": "Invalid risk level",
                "result": None,
            }
        result["risk"] = risk

        selected = result.get("selected_invoice")
        if selected in ("", "null", "None", "none"):
            selected = None
            result["selected_invoice"] = None

        allowed = None
        if allowed_invoice_ids is not None:
            allowed = {
                _normalize_invoice_token(value)
                for value in allowed_invoice_ids
                if _normalize_invoice_token(value)
            }

        if decision == "MATCH":
            if selected is None:
                return {
                    "valid": False,
                    "error": "MATCH requires selected_invoice",
                    "result": None,
                }
            if allowed is not None and _normalize_invoice_token(selected) not in allowed:
                return {
                    "valid": False,
                    "error": "selected_invoice is not in the candidate set",
                    "result": None,
                }
        elif selected is not None and allowed is not None:
            if _normalize_invoice_token(selected) not in allowed:
                return {
                    "valid": False,
                    "error": "selected_invoice is not in the candidate set",
                    "result": None,
                }

        if not isinstance(result.get("reason"), str) or not result["reason"].strip():
            return {
                "valid": False,
                "error": "Reason must be a non-empty string",
                "result": None,
            }

        return {
            "valid": True,
            "error": None,
            "result": result,
        }

    except json.JSONDecodeError:
        return {
            "valid": False,
            "error": "AI returned invalid JSON",
            "result": None,
        }
    except Exception as exc:
        return {
            "valid": False,
            "error": f"AI response validation failed: {exc}",
            "result": None,
        }


def ask_ai(prompt, timeout_seconds: float = 120.0):
    """
    Send the reconciliation prompt to the local Qwen model via Ollama.

    Raises on transport/model failure so callers can convert to REVIEW.
    """
    print("10. Connecting to local Qwen...")

    client = OpenAI(
        base_url="http://localhost:11434/v1",
        api_key="ollama",
        timeout=timeout_seconds,
    )

    print("11. Sending request to Qwen...")

    inference_start = time.perf_counter()
    try:
        response = client.chat.completions.create(
            model="qwen2.5:3b",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a cautious finance reconciliation assistant. "
                        "Use only supplied evidence. Never invent candidates. "
                        "Prefer REVIEW over unsupported MATCH. "
                        "Treat missing fields as unavailable, not mismatches."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            temperature=0,
        )
    finally:
        print(
            f"[TIMING] AI inference: "
            f"{time.perf_counter() - inference_start:.2f}s"
        )

    print("12. Response received")

    if not response.choices:
        raise RuntimeError("AI returned no choices")

    content = response.choices[0].message.content
    if content is None:
        raise RuntimeError("AI returned empty content")
    return content


def safe_ask_ai(prompt, timeout_seconds: float = 120.0) -> Dict[str, Any]:
    """Wrapper that never raises; returns raw text or an error payload."""
    try:
        raw = ask_ai(prompt, timeout_seconds=timeout_seconds)
        return {"ok": True, "raw": raw, "error": None}
    except Exception as exc:
        return {
            "ok": False,
            "raw": None,
            "error": f"AI unavailable or failed: {exc}",
        }
