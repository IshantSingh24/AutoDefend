"""
tests/test_evaluator.py
───────────────────────
Unit tests for the Evaluator Agent (Gating Layer).

Tests:
  - Stopping Rule SR_001 (In Transit -> RECOMMEND_ACCEPT)
  - Stopping Rule SR_002 (API Timeout -> HUMAN_REVIEW)
  - Stopping Rule SR_003 (High Value -> HUMAN_REVIEW)
  - LLM Fallback (when no stopping rule triggers)
  - Decision threshold logic (CONTEST vs RECOMMEND_ACCEPT)
"""

import pytest
from unittest.mock import AsyncMock, patch

from app.agents.evaluator import evaluator_agent, apply_stopping_rules
from app.graph.state import DisputeState
from app.config import get_settings

settings = get_settings()

def _base_state() -> DisputeState:
    return DisputeState(
        dispute_id="disp_test_eval",
        payment_id="pay_test_001",
        merchant_id="merchant_test",
        reason_code="VISA_10_4",
        dispute_class="fraud",
        amount=100000, # 1000 INR
        phase="CHARGEBACK",
        initial_confidence=0.75,
        evidence_collected={},
        audit_events=[],
        error_log=[],
    )

# ── Stopping Rules Tests ──────────────────────────────────────────────────────

def test_sr_001_in_transit():
    state = _base_state()
    state["dispute_class"] = "non_receipt"
    state["evidence_collected"] = {
        "logistics": {"status": "IN_TRANSIT"}
    }
    rule = apply_stopping_rules(state)
    assert rule == "SR_001"

def test_sr_002_api_timeout():
    state = _base_state()
    state["evidence_collected"] = {
        "logistics": {"status": "DELIVERED"},
        "security": {"status": "TIMEOUT"}
    }
    rule = apply_stopping_rules(state)
    assert rule == "SR_002"

def test_sr_003_high_value():
    state = _base_state()
    state["amount"] = settings.autonomous_max_paise + 1
    rule = apply_stopping_rules(state)
    assert rule == "SR_003"

def test_no_stopping_rules():
    state = _base_state()
    state["evidence_collected"] = {
        "logistics": {"status": "DELIVERED"}
    }
    rule = apply_stopping_rules(state)
    assert rule is None


# ── Evaluator Agent Logic Tests ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_evaluator_sr_001():
    state = _base_state()
    state["dispute_class"] = "non_receipt"
    state["evidence_collected"] = {"logistics": {"status": "IN_TRANSIT"}}
    
    result = await evaluator_agent(state)
    
    assert result["stopping_rule"] == "SR_001"
    assert result["system_decision"] == "RECOMMEND_ACCEPT"
    assert result["fight_confidence"] == 0.0

@pytest.mark.asyncio
async def test_evaluator_llm_contest():
    state = _base_state()
    state["evidence_collected"] = {"logistics": {"status": "DELIVERED"}}
    
    mock_llm_result = {
        "fight_confidence": 0.85, # Above threshold (default 0.70)
        "reasoning": "Strong evidence."
    }
    
    with patch("app.agents.evaluator.evaluate_evidence_strength", new_callable=AsyncMock, return_value=mock_llm_result):
        result = await evaluator_agent(state)
        
    assert result["stopping_rule"] is None
    assert result["fight_confidence"] == 0.85
    assert result["system_decision"] == "CONTEST"
    assert result["evaluator_reasoning"] == "Strong evidence."

@pytest.mark.asyncio
async def test_evaluator_llm_recommend_accept():
    state = _base_state()
    state["evidence_collected"] = {"logistics": {"status": "DELIVERED"}}
    
    mock_llm_result = {
        "fight_confidence": 0.45, # Below threshold
        "reasoning": "Weak evidence."
    }
    
    with patch("app.agents.evaluator.evaluate_evidence_strength", new_callable=AsyncMock, return_value=mock_llm_result):
        result = await evaluator_agent(state)
        
    assert result["stopping_rule"] is None
    assert result["fight_confidence"] == 0.45
    assert result["system_decision"] == "RECOMMEND_ACCEPT"
