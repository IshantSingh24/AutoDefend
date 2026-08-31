"""
tests/test_fsm.py
─────────────────
End-to-end FSM integration tests for all 4 demo scenarios.

Verifies:
  - Scenario A (PAY_FIGHT_WIN) -> COMPILE -> SUBMITTED (CONTEST, PDF generated)
  - Scenario B (PAY_HALT_TRANSIT) -> HALTED_ACCEPT (SR_001)
  - Scenario C (PAY_API_TIMEOUT) -> HALTED_REVIEW (SR_002)
  - Scenario D (PAY_WEAK_EVIDENCE) -> HALTED_ACCEPT (low confidence < threshold)

Mocks Evaluator LLM via patch so tests are deterministic (no OPENAI_API_KEY needed).
"""

import os
import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.graph.state import DisputeState
from app.graph.fsm import dispute_graph, route_after_evaluation


def _build_state_for_scenario(scenario_id: str) -> DisputeState:
    """Build initial DisputeState from _SCENARIO_REGISTRY meta."""
    from app.mock.scenarios import _SCENARIO_REGISTRY

    scenario = _SCENARIO_REGISTRY[scenario_id]
    meta = scenario["meta"]
    return DisputeState(
        dispute_id=f"disp_test_{scenario_id.lower()}",
        payment_id=scenario_id,
        merchant_id=meta["merchant_id"],
        reason_code=meta["reason_code"],
        amount=meta["amount_paise"],
        phase=meta["phase"],
        raw_webhook={"demo": True, "scenario_id": scenario_id},
        evidence_collected={},
        audit_events=[],
        error_log=[],
    )


# ── Routing tests ─────────────────────────────────────────────────────────────

def test_route_after_evaluation():
    assert route_after_evaluation({"system_decision": "CONTEST"}) == "compile"
    assert route_after_evaluation({"system_decision": "RECOMMEND_ACCEPT"}) == "halt_accept"
    assert route_after_evaluation({"system_decision": "HUMAN_REVIEW"}) == "halt_review"
    assert route_after_evaluation({"system_decision": None}) == "halt_review"


# ── Scenario A: Strong evidence -> CONTEST -> PDF + SUBMITTED ─────────────────

@pytest.mark.asyncio
async def test_scenario_a_fight_win():
    """PAY_FIGHT_WIN: Delivered, 3DS passed, IP match -> CONTEST -> SUBMITTED."""
    state = _build_state_for_scenario("PAY_FIGHT_WIN")

    mock_llm = {"fight_confidence": 0.91, "reasoning": "Strong evidence: delivered, 3DS passed, IP match, repeat customer."}

    with patch("app.agents.evaluator.evaluate_evidence_strength", new_callable=AsyncMock, return_value=mock_llm):
        with patch("asyncio.sleep", new_callable=AsyncMock):  # speed up executors
            result = await dispute_graph.ainvoke(state)

    assert result["system_decision"] == "CONTEST"
    assert result["stopping_rule"] is None
    assert result["fight_confidence"] == 0.91
    assert result["rebuttal_pdf_path"] is not None
    assert os.path.exists(result["rebuttal_pdf_path"])
    # VISA_10_4 only gathers security+crm (fraud), so packet has security/crm, not logistics
    assert "security" in result["evidence_packet"]
    assert result["evidence_packet"]["security"]["three_ds_passed"] is True
    assert "crm" in result["evidence_packet"]
    # Audit trail: CLASSIFICATION + EVIDENCE_GATHERING (x executors) + EVALUATION + COMPILATION + SUBMITTED
    stages = [e["stage"] for e in result["audit_events"]]
    assert "CLASSIFICATION" in stages
    assert "EVALUATION" in stages
    assert "COMPILATION" in stages
    assert "SUBMITTED" in stages
    # Submission mock
    assert result["submission_response"]["mock"] is True or "mock_submitted" in str(result["submission_response"].get("status"))


# ── Scenario B: In-Transit -> HALTED_ACCEPT (SR_001) ──────────────────────────

@pytest.mark.asyncio
async def test_scenario_b_halt_transit():
    """PAY_HALT_TRANSIT: IN_TRANSIT + non_receipt -> SR_001 -> RECOMMEND_ACCEPT -> HALTED_ACCEPT, no PDF."""
    state = _build_state_for_scenario("PAY_HALT_TRANSIT")

    with patch("asyncio.sleep", new_callable=AsyncMock):
        result = await dispute_graph.ainvoke(state)

    assert result["stopping_rule"] == "SR_001"
    assert result["system_decision"] == "RECOMMEND_ACCEPT"
    assert result["rebuttal_pdf_path"] is None
    assert result["evidence_packet"] is None  # compiler skipped
    stages = [e["stage"] for e in result["audit_events"]]
    assert "HALTED_ACCEPT" in stages
    assert "SUBMITTED" not in stages
    # Compile node is skipped for non-CONTEST -> no COMPILATION stage (correct FSM routing)
    assert "COMPILATION" not in stages


# ── Scenario C: API Timeout -> HALTED_REVIEW (SR_002) ─────────────────────────

@pytest.mark.asyncio
async def test_scenario_c_api_timeout():
    """PAY_API_TIMEOUT: logistics TIMEOUT -> SR_002 -> HUMAN_REVIEW -> HALTED_REVIEW, no PDF."""
    state = _build_state_for_scenario("PAY_API_TIMEOUT")

    with patch("asyncio.sleep", new_callable=AsyncMock):
        result = await dispute_graph.ainvoke(state)

    assert result["stopping_rule"] == "SR_002"
    assert result["system_decision"] == "HUMAN_REVIEW"
    assert result["rebuttal_pdf_path"] is None
    stages = [e["stage"] for e in result["audit_events"]]
    assert "HALTED_REVIEW" in stages
    assert "SUBMITTED" not in stages
    # Evidence should show TIMEOUT for logistics
    assert result["evidence_collected"]["logistics"]["status"] == "TIMEOUT"


# ── Scenario D: Weak evidence -> low confidence -> HALTED_ACCEPT ──────────────

@pytest.mark.asyncio
async def test_scenario_d_weak_evidence():
    """PAY_WEAK_EVIDENCE: low signals -> confidence 0.45 < 0.70 -> RECOMMEND_ACCEPT."""
    state = _build_state_for_scenario("PAY_WEAK_EVIDENCE")

    mock_llm = {"fight_confidence": 0.45, "reasoning": "Weak: no signature, 3DS failed, IP mismatch, first-time buyer."}

    with patch("app.agents.evaluator.evaluate_evidence_strength", new_callable=AsyncMock, return_value=mock_llm):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await dispute_graph.ainvoke(state)

    assert result["stopping_rule"] is None  # no deterministic rule, LLM decides
    assert result["fight_confidence"] == 0.45
    assert result["system_decision"] == "RECOMMEND_ACCEPT"
    assert result["rebuttal_pdf_path"] is None
    stages = [e["stage"] for e in result["audit_events"]]
    assert "HALTED_ACCEPT" in stages
    assert "SUBMITTED" not in stages


# ── High-value safeguard: amount > threshold -> HALTED_REVIEW even if CONTEST ─

@pytest.mark.asyncio
async def test_high_value_blocks_submission():
    """Even if Evaluator says CONTEST, high-value (> Rs.5000) should block submit -> HALTED_REVIEW."""
    state = _build_state_for_scenario("PAY_FIGHT_WIN")
    state["amount"] = 600_000  # Rs.6000 > 500000 paise threshold -> SR_003

    # SR_003 triggers before LLM, so no need to mock LLM
    with patch("asyncio.sleep", new_callable=AsyncMock):
        result = await dispute_graph.ainvoke(state)

    assert result["stopping_rule"] == "SR_003"
    assert result["system_decision"] == "HUMAN_REVIEW"
    assert result["rebuttal_pdf_path"] is None
    stages = [e["stage"] for e in result["audit_events"]]
    assert "HALTED_REVIEW" in stages
    assert "SUBMITTED" not in stages
