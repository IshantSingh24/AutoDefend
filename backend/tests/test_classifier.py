"""
tests/test_classifier.py
─────────────────────────
Unit tests for the Classifier Agent.

Tests:
  - All 9 reason codes in the KB → correct class, executors, confidence
  - Unknown code → LLM fallback path triggered (mocked)
  - State is correctly populated after classification
  - Audit event is appended with required fields
"""

import pytest
from unittest.mock import AsyncMock, patch

from app.agents.classifier import classifier_agent, REASON_CODE_KB
from app.graph.state import DisputeState


# ── Helpers ───────────────────────────────────────────────────────────────────

def _base_state(reason_code: str) -> DisputeState:
    """Minimal state dict to feed into the classifier."""
    return DisputeState(
        dispute_id="disp_test_001",
        payment_id="pay_test_001",
        merchant_id="merchant_test",
        reason_code=reason_code,
        amount=100_000,
        phase="CHARGEBACK",
        raw_webhook={},
        evidence_collected={},
        audit_events=[],
        error_log=[],
    )


# ── KB coverage: all 9 known reason codes ─────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("code,expected_class,expected_confidence", [
    ("VISA_10_4",  "fraud",       0.75),
    ("VISA_13_1",  "non_receipt", 0.60),
    ("VISA_13_3",  "service",     0.55),
    ("VISA_13_7",  "policy",      0.50),
    ("MC_4853",    "service",     0.60),
    ("MC_4855",    "non_receipt", 0.55),
    ("MC_4863",    "fraud",       0.70),
    ("UPI_RC1",    "fraud",       0.65),
    ("UPI_RC2",    "non_receipt", 0.55),
])
async def test_known_reason_codes(code, expected_class, expected_confidence):
    """All KB codes should resolve deterministically without LLM."""
    state = await classifier_agent(_base_state(code))

    assert state["dispute_class"]      == expected_class
    assert state["initial_confidence"] == expected_confidence
    assert len(state["evidence_strategy"]) > 0


@pytest.mark.asyncio
@pytest.mark.parametrize("code", list(REASON_CODE_KB.keys()))
async def test_all_kb_codes_populate_executors(code):
    """Every KB code must specify at least one executor."""
    state = await classifier_agent(_base_state(code))
    assert state["evidence_strategy"]  # non-empty list
    for executor in state["evidence_strategy"]:
        assert executor in ("logistics", "security", "crm"), \
            f"Unknown executor '{executor}' for code {code}"


# ── Audit trail ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_audit_event_appended():
    """Classifier must append exactly one audit event with required fields."""
    state = await classifier_agent(_base_state("VISA_10_4"))

    assert len(state["audit_events"]) == 1
    event = state["audit_events"][0]

    assert event["stage"]   == "CLASSIFICATION"
    assert event["agent"]   == "ClassifierAgent"
    assert event["source"]  == "kb"
    assert "timestamp"      in event
    assert "reason_code"    in event
    assert "dispute_class"  in event
    assert "executors"      in event


# ── LLM fallback ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_unknown_code_triggers_llm_fallback():
    """An unknown reason code should trigger _llm_classify_unknown_code."""
    mock_strategy = {
        "dispute_class":     "fraud",
        "description":       "Mock unknown code",
        "required_evidence": ["security"],
        "optional_evidence": [],
        "executors":         ["security"],
        "base_confidence":   0.50,
        "llm_classified":    True,
    }

    with patch(
        "app.agents.classifier._llm_classify_unknown_code",
        new_callable=AsyncMock,
        return_value=mock_strategy,
    ) as mock_llm:
        state = await classifier_agent(_base_state("TOTALLY_UNKNOWN_XYZ"))
        mock_llm.assert_awaited_once_with("TOTALLY_UNKNOWN_XYZ")

    assert state["dispute_class"]      == "fraud"
    assert state["initial_confidence"] == 0.50
    assert state["audit_events"][0]["source"] == "llm"


@pytest.mark.asyncio
async def test_llm_failure_uses_safe_default():
    """If LLM also fails, system falls back to safe default (confidence=0.40)."""
    with patch(
        "app.agents.classifier._llm_classify_unknown_code",
        new_callable=AsyncMock,
        return_value={
            "dispute_class": "unknown",
            "description": "Unknown reason code: BAD_CODE",
            "required_evidence": ["logistics", "security", "crm"],
            "optional_evidence": [],
            "executors": ["logistics", "security", "crm"],
            "base_confidence": 0.40,
            "llm_classified": False,
            "fallback": True,
        },
    ):
        state = await classifier_agent(_base_state("BAD_CODE"))

    assert state["initial_confidence"] == 0.40
    assert state["dispute_class"]      == "unknown"
    assert state["audit_events"][0]["source"] == "fallback_default"


# ── State integrity ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_classifier_does_not_clobber_existing_state():
    """Classifier should only ADD fields, not overwrite existing ones."""
    state = _base_state("VISA_10_4")
    state["error_log"] = ["pre-existing-error"]

    result = await classifier_agent(state)

    # Pre-existing fields should be untouched
    assert result["error_log"] == ["pre-existing-error"]
    assert result["payment_id"] == "pay_test_001"
