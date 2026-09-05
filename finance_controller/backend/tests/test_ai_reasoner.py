"""
Pytest test suite for the AI reconciliation reasoner.

All records are synthetic and unrelated to the 500-record benchmark
dataset (no B0xxx / INV0xxx IDs, no benchmark vendors or amounts).

Structure:
  - Validation unit tests  : no Qwen required
  - Prompt builder tests   : no Qwen required
  - Live AI integration    : auto-skipped when Qwen is unavailable
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Path setup — allows running from any cwd
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.ai.ai_reasoner import (
    build_ai_prompt,
    validate_ai_response,
    safe_ask_ai,
    enrich_candidates_with_source_rows,
    _row_get,
    _format_value,
    _unavailable_notes,
    BANK_EVIDENCE_FIELDS,
    CANDIDATE_EVIDENCE_FIELDS,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def bank_row(**kwargs) -> Dict[str, Any]:
    """Build a minimal synthetic bank row dict."""
    defaults = {
        "transaction_id": "TXN-SYNTH-001",
        "date": "2026-01-15",
        "amount": 5000.0,
        "counterparty": "Sigma Corp",
        "direction": "debit",
        "source": "bank",
        "source_file": "synthetic_bank.csv",
    }
    defaults.update(kwargs)
    return defaults


def erp_candidate(
    invoice_id: str = "INV-SYNTH-001",
    amount: float = 5000.0,
    vendor: str = "Sigma Corp",
    date: str = "2026-01-15",
    reference: str = "",
    score: float = 75.0,
    **extra,
) -> Dict[str, Any]:
    """Build a minimal synthetic ERP candidate dict."""
    c = {
        "invoice_id": invoice_id,
        "date": date,
        "amount": amount,
        "vendor": vendor,
        "reference": reference,
        "final_score": score,
        "amount_score": 100.0 if amount == 5000.0 else 0.0,
        "vendor_score": 90.0,
        "date_score": 100.0,
        "reference_score": 0.0,
        "settlement_reference_score": 0.0,
        "source": "erp",
        "source_file": "synthetic_erp.csv",
    }
    c.update(extra)
    return c


def _mock_ai_response(
    decision: str = "MATCH",
    selected_invoice: Optional[str] = "INV-SYNTH-001",
    confidence: int = 85,
    reason: str = "Amounts and vendor match.",
    risk: str = "LOW",
) -> str:
    return json.dumps({
        "decision": decision,
        "selected_invoice": selected_invoice,
        "confidence": confidence,
        "reason": reason,
        "risk": risk,
    })


def qwen_available() -> bool:
    """Return True if the local Qwen/Ollama is reachable."""
    try:
        import urllib.request
        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2)
        return True
    except Exception:
        return False


SKIP_LIVE = pytest.mark.skipif(
    not qwen_available(),
    reason="Qwen/Ollama not available at localhost:11434",
)


# ===========================================================================
# SECTION A — validate_ai_response unit tests (no Qwen needed)
# ===========================================================================

class TestValidateAiResponse:

    def test_valid_match_response_accepted(self):
        raw = _mock_ai_response()
        result = validate_ai_response(raw, allowed_invoice_ids=["INV-SYNTH-001"])
        assert result["valid"] is True
        assert result["result"]["decision"] == "MATCH"
        assert result["result"]["selected_invoice"] == "INV-SYNTH-001"

    def test_valid_review_with_null_invoice(self):
        raw = _mock_ai_response(decision="REVIEW", selected_invoice=None,
                                 confidence=40, reason="Amounts conflict.", risk="MEDIUM")
        result = validate_ai_response(raw, allowed_invoice_ids=["INV-SYNTH-001"])
        assert result["valid"] is True
        assert result["result"]["decision"] == "REVIEW"
        assert result["result"]["selected_invoice"] is None

    def test_valid_exception_with_null_invoice(self):
        raw = _mock_ai_response(decision="EXCEPTION", selected_invoice=None,
                                 confidence=0, reason="No candidates.", risk="HIGH")
        result = validate_ai_response(raw)
        assert result["valid"] is True
        assert result["result"]["decision"] == "EXCEPTION"

    def test_match_requires_selected_invoice(self):
        raw = _mock_ai_response(decision="MATCH", selected_invoice=None)
        result = validate_ai_response(raw, allowed_invoice_ids=["INV-SYNTH-001"])
        assert result["valid"] is False
        assert "MATCH requires selected_invoice" in result["error"]

    def test_hallucinated_invoice_id_rejected(self):
        """AI invents an invoice ID not in the candidate set."""
        raw = _mock_ai_response(
            decision="MATCH",
            selected_invoice="INV-INVENTED-999",
        )
        result = validate_ai_response(raw, allowed_invoice_ids=["INV-SYNTH-001", "INV-SYNTH-002"])
        assert result["valid"] is False
        assert "not in the candidate set" in result["error"]

    def test_invalid_decision_rejected(self):
        payload = {
            "decision": "APPROVE",
            "selected_invoice": None,
            "confidence": 90,
            "reason": "Looks good.",
            "risk": "LOW",
        }
        result = validate_ai_response(json.dumps(payload))
        assert result["valid"] is False
        assert "Invalid decision" in result["error"]

    def test_invalid_risk_rejected(self):
        payload = {
            "decision": "REVIEW",
            "selected_invoice": None,
            "confidence": 50,
            "reason": "Uncertain.",
            "risk": "CRITICAL",
        }
        result = validate_ai_response(json.dumps(payload))
        assert result["valid"] is False
        assert "Invalid risk" in result["error"]

    def test_non_numeric_confidence_rejected(self):
        payload = {
            "decision": "REVIEW",
            "selected_invoice": None,
            "confidence": "high",
            "reason": "Not sure.",
            "risk": "MEDIUM",
        }
        result = validate_ai_response(json.dumps(payload))
        assert result["valid"] is False
        assert "Confidence must be numeric" in result["error"]

    def test_confidence_out_of_range_rejected(self):
        payload = {
            "decision": "REVIEW",
            "selected_invoice": None,
            "confidence": 150,
            "reason": "Very sure.",
            "risk": "LOW",
        }
        result = validate_ai_response(json.dumps(payload))
        assert result["valid"] is False
        assert "between 0 and 100" in result["error"]

    def test_empty_reason_rejected(self):
        payload = {
            "decision": "REVIEW",
            "selected_invoice": None,
            "confidence": 50,
            "reason": "   ",
            "risk": "MEDIUM",
        }
        result = validate_ai_response(json.dumps(payload))
        assert result["valid"] is False
        assert "non-empty string" in result["error"]

    def test_invalid_json_rejected(self):
        result = validate_ai_response("not json at all")
        assert result["valid"] is False
        assert "invalid JSON" in result["error"]

    def test_none_response_rejected(self):
        result = validate_ai_response(None)
        assert result["valid"] is False
        assert "Empty AI response" in result["error"]

    def test_empty_string_response_rejected(self):
        result = validate_ai_response("")
        assert result["valid"] is False

    def test_code_fence_stripped(self):
        """AI sometimes wraps JSON in markdown code fences."""
        raw = "```json\n" + _mock_ai_response() + "\n```"
        result = validate_ai_response(raw, allowed_invoice_ids=["INV-SYNTH-001"])
        assert result["valid"] is True

    def test_missing_field_rejected(self):
        payload = {
            "decision": "MATCH",
            "selected_invoice": "INV-SYNTH-001",
            "confidence": 90,
            # "reason" missing
            "risk": "LOW",
        }
        result = validate_ai_response(json.dumps(payload))
        assert result["valid"] is False
        assert "Missing field: reason" in result["error"]

    def test_case_insensitive_invoice_matching(self):
        """Candidate IDs should match case-insensitively."""
        raw = _mock_ai_response(selected_invoice="inv-synth-001")
        result = validate_ai_response(raw, allowed_invoice_ids=["INV-SYNTH-001"])
        assert result["valid"] is True

    def test_null_string_selected_invoice_normalized(self):
        payload = {
            "decision": "REVIEW",
            "selected_invoice": "null",
            "confidence": 40,
            "reason": "Cannot decide.",
            "risk": "MEDIUM",
        }
        result = validate_ai_response(json.dumps(payload))
        assert result["valid"] is True
        assert result["result"]["selected_invoice"] is None


# ===========================================================================
# SECTION B — build_ai_prompt unit tests (no Qwen needed)
# ===========================================================================

class TestBuildAiPrompt:

    def test_prompt_contains_bank_field_values(self):
        bank = bank_row(
            transaction_id="TXN-ALPHA-77",
            amount=12345.0,
            counterparty="Delta Industries",
            bank_utr="UTR-DELTA-77",
        )
        candidates = [erp_candidate()]
        prompt = build_ai_prompt(bank, candidates)
        assert "TXN-ALPHA-77" in prompt
        assert "12,345.00" in prompt
        assert "Delta Industries" in prompt
        assert "UTR-DELTA-77" in prompt

    def test_prompt_contains_candidate_invoice_id(self):
        bank = bank_row()
        candidates = [erp_candidate(invoice_id="INV-GAMMA-55")]
        prompt = build_ai_prompt(bank, candidates)
        assert "INV-GAMMA-55" in prompt

    def test_allowed_list_in_prompt(self):
        bank = bank_row()
        candidates = [
            erp_candidate(invoice_id="INV-X1"),
            erp_candidate(invoice_id="INV-X2"),
        ]
        prompt = build_ai_prompt(bank, candidates)
        assert "INV-X1" in prompt
        assert "INV-X2" in prompt

    def test_no_candidates_prompt(self):
        bank = bank_row()
        prompt = build_ai_prompt(bank, [])
        assert "No candidates were provided" in prompt

    def test_missing_field_not_shown_as_mismatch(self):
        """Fields absent from the bank row should not appear as explicit evidence values."""
        bank = bank_row()  # no bank_utr
        candidates = [erp_candidate()]
        prompt = build_ai_prompt(bank, candidates)
        # The prompt instructions legitimately contain the word 'mismatch' as a rule.
        # What must NOT happen: a missing field appearing as a populated evidence line
        # e.g. "Bank UTR: SOME_VALUE" when no UTR was provided.
        # We verify this by checking bank_utr is NOT shown as a non-unavailable value.
        lines = prompt.lower().splitlines()
        for line in lines:
            if "bank utr" in line:
                # Line must mention 'unavailable', not a concrete value
                assert "unavailable" in line, (
                    f"bank_utr line should say unavailable, not show a value: {line}"
                )

    def test_unavailable_fields_noted(self):
        """Important missing fields should be listed as 'unavailable'."""
        bank = bank_row()  # no bank_utr, bank_reference, etc.
        candidates = [erp_candidate()]
        prompt = build_ai_prompt(bank, candidates)
        assert "unavailable" in prompt.lower()

    def test_settlement_arithmetic_fields_surfaced(self):
        """If candidate has gross/fee/net, they should appear in the prompt."""
        bank = bank_row(amount=9800.0)
        candidate = erp_candidate(
            invoice_id="INV-RZP-01",
            amount=9800.0,
            gross_amount=10000.0,
            fee_amount=200.0,
            settlement_amount=9800.0,
        )
        prompt = build_ai_prompt(bank, [candidate])
        assert "10,000.00" in prompt
        assert "200.00" in prompt
        assert "9,800.00" in prompt

    def test_amount_formatted_with_commas(self):
        bank = bank_row(amount=1000000.0)
        prompt = build_ai_prompt(bank, [erp_candidate(amount=1000000.0)])
        assert "1,000,000.00" in prompt

    def test_enrichment_does_not_invent_fields(self):
        """enrich_candidates_with_source_rows should not add fake values."""
        bank = bank_row()
        candidates = [erp_candidate(invoice_id="INV-REAL-01")]
        enriched = enrich_candidates_with_source_rows(candidates, None)
        assert enriched[0]["invoice_id"] == "INV-REAL-01"
        assert enriched[0].get("settlement_utr") is None


# ===========================================================================
# SECTION C — Prompt content / mock-AI integration tests (no Qwen needed)
# ===========================================================================

class TestPromptIntegration:
    """
    Tests that verify the full prompt -> validate_ai_response round-trip
    using a mocked AI response (no real Qwen call required).
    """

    def _run_with_mock(
        self,
        bank: Dict,
        candidates: List[Dict],
        mock_response: str,
        erp_df=None,
    ):
        prompt = build_ai_prompt(bank, candidates, erp=erp_df)
        allowed_ids = [
            c["invoice_id"] for c in candidates
            if c.get("invoice_id") not in (None, "")
        ]
        return validate_ai_response(mock_response, allowed_invoice_ids=allowed_ids)

    # -----------------------------------------------------------------------
    # TEST 1 — Exact cross-system reference (UTR match)
    # -----------------------------------------------------------------------
    def test_1_exact_cross_system_reference(self):
        """
        Bank UTR = UTR-100, ERP reference = UTR-100, amounts match.
        AI should be capable of recommending INV-A9.
        """
        bank = bank_row(
            transaction_id="TXN-A1",
            bank_utr="UTR-100",
            amount=1000.0,
            date="2026-01-10",
            counterparty="Alpha Ltd",
        )
        candidates = [
            erp_candidate(
                invoice_id="INV-A9",
                reference="UTR-100",
                amount=1000.0,
                date="2026-01-10",
                vendor="Alpha Ltd",
                score=100.0,
                reference_score=100.0,
            )
        ]
        mock_resp = _mock_ai_response(
            decision="MATCH",
            selected_invoice="INV-A9",
            confidence=95,
            reason="UTR-100 matches on both sides; amounts are identical.",
            risk="LOW",
        )
        result = self._run_with_mock(bank, candidates, mock_resp)
        assert result["valid"] is True
        assert result["result"]["decision"] == "MATCH"
        assert result["result"]["selected_invoice"] == "INV-A9"

    # -----------------------------------------------------------------------
    # TEST 2 — Different ID formats (IDs need not match)
    # -----------------------------------------------------------------------
    def test_2_different_id_formats(self):
        """
        Bank ID = BANK-7788, ERP invoice ID = INVOICE-55.
        IDs are completely different; the link is through reference = UTR-7788.
        AI must NOT require IDs to match.
        """
        bank = bank_row(
            transaction_id="BANK-7788",
            amount=2500.0,
            date="2026-02-01",
            counterparty="Zeta Services",
            bank_utr="UTR-7788",
        )
        candidates = [
            erp_candidate(
                invoice_id="INVOICE-55",
                reference="UTR-7788",
                amount=2500.0,
                date="2026-02-01",
                vendor="Zeta Services",
                score=100.0,
                reference_score=100.0,
            )
        ]
        mock_resp = _mock_ai_response(
            decision="MATCH",
            selected_invoice="INVOICE-55",
            confidence=92,
            reason=(
                "UTR-7788 present in bank UTR and ERP reference. "
                "Amounts and vendor match. IDs differ but that is expected."
            ),
            risk="LOW",
        )
        result = self._run_with_mock(bank, candidates, mock_resp)
        assert result["valid"] is True
        assert result["result"]["selected_invoice"] == "INVOICE-55"

    # -----------------------------------------------------------------------
    # TEST 3 — Material amount conflict
    # -----------------------------------------------------------------------
    def test_3_material_amount_conflict(self):
        """
        Bank = 10000, ERP = 15000.
        AI must return REVIEW or EXCEPTION, not a confident MATCH.
        """
        bank = bank_row(amount=10000.0)
        candidates = [
            erp_candidate(
                invoice_id="INV-CONFLICT-01",
                amount=15000.0,
                score=30.0,
                amount_score=0.0,
            )
        ]
        mock_resp = _mock_ai_response(
            decision="REVIEW",
            selected_invoice=None,
            confidence=20,
            reason=(
                "Bank amount 10,000 conflicts materially with ERP 15,000. "
                "No settlement evidence to explain the difference."
            ),
            risk="HIGH",
        )
        result = self._run_with_mock(bank, candidates, mock_resp)
        assert result["valid"] is True
        assert result["result"]["decision"] in ("REVIEW", "EXCEPTION")
        assert result["result"]["selected_invoice"] is None

    # -----------------------------------------------------------------------
    # TEST 4 — Multiple candidates
    # -----------------------------------------------------------------------
    def test_4_multiple_candidates(self):
        """
        Three candidates; AI picks based on UTR evidence, not score alone.
        """
        bank = bank_row(
            transaction_id="TXN-MULTI-01",
            amount=7500.0,
            bank_utr="UTR-MULTI",
        )
        candidates = [
            erp_candidate(
                invoice_id="INV-MULTI-A",
                amount=7500.0,
                reference="UTR-MULTI",
                score=100.0,
                reference_score=100.0,
            ),
            erp_candidate(
                invoice_id="INV-MULTI-B",
                amount=7500.0,
                score=75.0,
                reference_score=0.0,
            ),
            erp_candidate(
                invoice_id="INV-MULTI-C",
                amount=8000.0,
                score=40.0,
                amount_score=0.0,
            ),
        ]
        mock_resp = _mock_ai_response(
            decision="MATCH",
            selected_invoice="INV-MULTI-A",
            confidence=96,
            reason=(
                "UTR-MULTI matches INV-MULTI-A reference. "
                "INV-MULTI-B has no UTR linkage. INV-MULTI-C has amount conflict."
            ),
            risk="LOW",
        )
        result = self._run_with_mock(bank, candidates, mock_resp)
        assert result["valid"] is True
        assert result["result"]["selected_invoice"] == "INV-MULTI-A"

    def test_4b_multiple_candidates_cannot_invent_winner(self):
        """AI cannot return a candidate ID not in the provided list."""
        bank = bank_row(amount=7500.0)
        candidates = [
            erp_candidate(invoice_id="INV-MULTI-A"),
            erp_candidate(invoice_id="INV-MULTI-B"),
        ]
        mock_resp = _mock_ai_response(
            decision="MATCH",
            selected_invoice="INV-MULTI-INVENTED",
        )
        result = self._run_with_mock(bank, candidates, mock_resp)
        assert result["valid"] is False
        assert "not in the candidate set" in result["error"]

    # -----------------------------------------------------------------------
    # TEST 5 — Candidate not provided
    # -----------------------------------------------------------------------
    def test_5_candidate_not_provided(self):
        """
        The correct invoice is absent. AI must not invent it.
        """
        bank = bank_row(amount=3300.0, bank_utr="UTR-ABSENT")
        candidates = [
            erp_candidate(invoice_id="INV-WRONG-X", amount=9999.0, score=10.0),
        ]
        mock_resp = _mock_ai_response(
            decision="REVIEW",
            selected_invoice=None,
            confidence=15,
            reason="No candidate matches UTR-ABSENT or the bank amount. Recommend review.",
            risk="HIGH",
        )
        result = self._run_with_mock(bank, candidates, mock_resp)
        assert result["valid"] is True
        assert result["result"]["selected_invoice"] is None

    def test_5b_ai_cannot_invent_absent_invoice(self):
        """
        Even if the AI tries to return an absent invoice, validation blocks it.
        """
        bank = bank_row(amount=3300.0)
        candidates = [erp_candidate(invoice_id="INV-WRONG-X")]
        mock_resp = _mock_ai_response(
            decision="MATCH",
            selected_invoice="INV-CORRECT-BUT-ABSENT",
        )
        result = self._run_with_mock(bank, candidates, mock_resp)
        assert result["valid"] is False
        assert "not in the candidate set" in result["error"]

    # -----------------------------------------------------------------------
    # TEST 6 — Missing reference (treated as unavailable)
    # -----------------------------------------------------------------------
    def test_6_missing_reference_treated_as_unavailable(self):
        """
        No UTR or reference on either side.
        Missing evidence must NOT be presented as a populated (mismatched) value.
        Missing fields should appear in the 'unavailable' notes section, not as
        fabricated evidence values.
        """
        bank = bank_row()  # no bank_utr, bank_reference
        candidates = [erp_candidate(reference="")]  # no ERP reference either
        prompt = build_ai_prompt(bank, candidates)

        # Missing fields must be acknowledged as unavailable
        assert "unavailable" in prompt.lower()

        # Data evidence lines have the form "Label: value" (with a colon).
        # Check that no UTR/reference field appears as a populated data value.
        # We only look at lines that look like evidence key:value pairs
        # (exclude instruction-prose lines that also mention 'settlement reference').
        lines = prompt.splitlines()
        for line in lines:
            stripped = line.strip()
            # Evidence lines are "Label: value" — colon present and not a numbered list
            if ":" in stripped and not stripped[0].isdigit() and not stripped.startswith("-"):
                label_part = stripped.split(":")[0].lower()
                value_part = ":".join(stripped.split(":")[1:]).strip().lower()
                if label_part in ("bank utr", "bank reference", "settlement reference"):
                    # If the field appears as an evidence line, value must be 'unavailable'
                    assert value_part == "unavailable", (
                        f"Field '{label_part}' should be 'unavailable' but got: '{value_part}'"
                    )

    def test_6b_missing_utr_noted_not_faulted(self):
        """
        Unavailable UTR should be listed as unavailable in the prompt.
        The prompt instructions legitimately contain 'mismatch' as a rule — that is fine.
        What must NOT happen: UTR shown as if it were present with some value.
        """
        bank = bank_row()  # no utr fields
        candidates = [erp_candidate()]
        prompt = build_ai_prompt(bank, candidates)
        # 'unavailable' must appear (for the missing UTR fields)
        assert "unavailable" in prompt.lower()
        # Verify no UTR is fabricated — any bank UTR line must say unavailable
        lines = prompt.lower().splitlines()
        for line in lines:
            if "bank utr" in line:
                assert "unavailable" in line, (
                    f"UTR must be listed as unavailable, not as a value: {line}"
                )

    # -----------------------------------------------------------------------
    # TEST 7 — Multi-source settlement evidence
    # -----------------------------------------------------------------------
    def test_7_multi_source_settlement_evidence(self):
        """
        Bank: 9,800 (UTR-SETTLE-01)
        ERP: gross 10,000, fee 200, net settlement 9,800
        All three amounts must appear in the prompt.
        """
        bank = bank_row(
            transaction_id="TXN-SETTLE-01",
            amount=9800.0,
            bank_utr="UTR-SETTLE-01",
        )
        candidate = erp_candidate(
            invoice_id="INV-SETTLE-01",
            amount=9800.0,
            gross_amount=10000.0,
            fee_amount=200.0,
            settlement_amount=9800.0,
            settlement_utr="UTR-SETTLE-01",
            score=100.0,
            settlement_reference_score=100.0,
        )
        prompt = build_ai_prompt(bank, [candidate])

        assert "10,000.00" in prompt
        assert "200.00" in prompt
        assert "9,800.00" in prompt

        mock_resp = _mock_ai_response(
            decision="MATCH",
            selected_invoice="INV-SETTLE-01",
            confidence=97,
            reason=(
                "UTR-SETTLE-01 matches. Gross 10,000 minus fee 200 = "
                "net settlement 9,800 = bank amount. Settlement arithmetic consistent."
            ),
            risk="LOW",
        )
        result = self._run_with_mock(bank, [candidate], mock_resp)
        assert result["valid"] is True
        assert result["result"]["decision"] == "MATCH"

    # -----------------------------------------------------------------------
    # TEST 8 — Completely different IDs/vendors (unrelated to benchmark)
    # -----------------------------------------------------------------------
    def test_8_completely_different_ids_and_vendors(self):
        """
        All identifiers and vendor names are entirely unrelated to the
        500-record benchmark dataset.
        AI must still operate normally.
        """
        bank = bank_row(
            transaction_id="WIRE-X-20260301-9981",
            amount=47250.0,
            counterparty="Polaris Trading FZE",
            bank_utr="NEFT20260301REF009981",
            date="2026-03-01",
            description="NEFT payment March batch",
        )
        candidates = [
            erp_candidate(
                invoice_id="PO-FZE-2026-0044",
                amount=47250.0,
                vendor="Polaris Trading FZE",
                reference="NEFT20260301REF009981",
                date="2026-03-01",
                score=100.0,
                reference_score=100.0,
            ),
            erp_candidate(
                invoice_id="PO-FZE-2026-0041",
                amount=47250.0,
                vendor="Polaris Trading FZE",
                date="2026-02-28",
                score=60.0,
                reference_score=0.0,
                date_score=80.0,
            ),
        ]
        prompt = build_ai_prompt(bank, candidates)
        assert "WIRE-X-20260301-9981" in prompt
        assert "PO-FZE-2026-0044" in prompt
        assert "PO-FZE-2026-0041" in prompt
        assert "NEFT20260301REF009981" in prompt
        assert "Polaris Trading FZE" in prompt

        mock_resp = _mock_ai_response(
            decision="MATCH",
            selected_invoice="PO-FZE-2026-0044",
            confidence=98,
            reason=(
                "NEFT reference matches exactly. Amount 47,250 matches. "
                "Vendor Polaris Trading FZE matches. Date matches. "
                "PO-FZE-2026-0041 is rejected due to date offset and no reference."
            ),
            risk="LOW",
        )
        result = self._run_with_mock(bank, candidates, mock_resp)
        assert result["valid"] is True
        assert result["result"]["selected_invoice"] == "PO-FZE-2026-0044"


# ===========================================================================
# SECTION D — Live AI integration tests (auto-skipped without Qwen)
# ===========================================================================

class TestLiveAI:
    """
    These tests call the real Qwen model.
    They are skipped automatically when Qwen is not reachable.
    """

    @SKIP_LIVE
    def test_live_exact_utr_match(self):
        """
        Live: strong UTR + amount + vendor evidence should produce MATCH or REVIEW,
        never EXCEPTION when a good candidate is present.
        """
        bank = bank_row(
            transaction_id="TXN-LIVE-001",
            bank_utr="UTR-LIVE-001",
            amount=5000.0,
            counterparty="Beta Logistics",
            date="2026-03-15",
        )
        candidates = [
            erp_candidate(
                invoice_id="INV-LIVE-001",
                reference="UTR-LIVE-001",
                amount=5000.0,
                vendor="Beta Logistics",
                date="2026-03-15",
                score=100.0,
                reference_score=100.0,
            )
        ]
        prompt = build_ai_prompt(bank, candidates)
        ai_result = safe_ask_ai(prompt)
        assert ai_result["ok"], f"AI call failed: {ai_result['error']}"

        allowed = ["INV-LIVE-001"]
        validation = validate_ai_response(ai_result["raw"], allowed_invoice_ids=allowed)
        assert validation["valid"], f"AI response invalid: {validation['error']}"

        decision = validation["result"]["decision"]
        assert decision in ("MATCH", "REVIEW"), (
            f"Expected MATCH or REVIEW for strong UTR evidence; got {decision}"
        )

    @SKIP_LIVE
    def test_live_material_amount_conflict_not_confident_match(self):
        """
        Live: bank 10,000 vs ERP 15,000 must not produce a high-confidence MATCH.
        """
        bank = bank_row(
            transaction_id="TXN-LIVE-CONFLICT",
            amount=10000.0,
            counterparty="Gamma Exports",
        )
        candidates = [
            erp_candidate(
                invoice_id="INV-LIVE-CONFLICT",
                amount=15000.0,
                vendor="Gamma Exports",
                score=25.0,
                amount_score=0.0,
            )
        ]
        prompt = build_ai_prompt(bank, candidates)
        ai_result = safe_ask_ai(prompt)
        assert ai_result["ok"], f"AI call failed: {ai_result['error']}"

        allowed = ["INV-LIVE-CONFLICT"]
        validation = validate_ai_response(ai_result["raw"], allowed_invoice_ids=allowed)
        assert validation["valid"], f"AI response invalid: {validation['error']}"

        result = validation["result"]
        if result["decision"] == "MATCH":
            assert result["confidence"] < 70, (
                f"Material amount conflict should yield low confidence; "
                f"got {result['confidence']}"
            )

    @SKIP_LIVE
    def test_live_no_candidates_returns_exception_or_review(self):
        """
        Live: with no candidates the AI should not hallucinate an invoice.
        """
        bank = bank_row(transaction_id="TXN-LIVE-EMPTY")
        prompt = build_ai_prompt(bank, [])
        ai_result = safe_ask_ai(prompt)
        assert ai_result["ok"], f"AI call failed: {ai_result['error']}"

        validation = validate_ai_response(ai_result["raw"], allowed_invoice_ids=[])
        assert validation["valid"], f"AI response invalid: {validation['error']}"
        assert validation["result"]["decision"] in ("EXCEPTION", "REVIEW")
        assert validation["result"]["selected_invoice"] is None

    @SKIP_LIVE
    def test_live_completely_synthetic_ids(self):
        """
        Live: end-to-end with identifiers unrelated to the benchmark.
        The AI must still produce a valid structured response.
        """
        bank = bank_row(
            transaction_id="OMEGA-TXN-2026-XJ99",
            amount=18500.0,
            counterparty="Crestwood Holdings LLC",
            bank_utr="RTGS-CRW-20260401-XJ99",
            date="2026-04-01",
        )
        candidates = [
            erp_candidate(
                invoice_id="CRW-INV-20260401-0099",
                reference="RTGS-CRW-20260401-XJ99",
                amount=18500.0,
                vendor="Crestwood Holdings LLC",
                date="2026-04-01",
                score=100.0,
                reference_score=100.0,
            )
        ]
        prompt = build_ai_prompt(bank, candidates)
        ai_result = safe_ask_ai(prompt)
        assert ai_result["ok"], f"AI call failed: {ai_result['error']}"

        allowed = ["CRW-INV-20260401-0099"]
        validation = validate_ai_response(ai_result["raw"], allowed_invoice_ids=allowed)
        assert validation["valid"], (
            f"AI response invalid for synthetic IDs: {validation['error']}\n"
            f"Raw: {ai_result['raw']}"
        )
