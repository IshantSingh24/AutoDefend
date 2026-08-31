"""
tests/test_demo.py
──────────────────
Demo-mode integration tests — no real Razorpay keys needed.

Runs the full AutoDefend pipeline as a merchant would via the demo endpoints:
  POST /webhook/demo/PAY_FIGHT_WIN etc -> FSM -> PDF -> mock Razorpay submit

Verifies:
  - Mock-first Razorpay client (is_mock=True) without real keys
  - Evidence payload mapping
  - Gated accept (merchant_approved required)
  - HMAC verification
  - All 4 scenarios end-to-end with demo-like assertions
"""
import hashlib
import hmac

import pytest
from unittest.mock import AsyncMock, patch

from app.config import get_settings
from app.graph.state import DisputeState
from app.graph.fsm import dispute_graph
from app.services.razorpay_client import RazorpayDisputeClient

settings = get_settings()


@pytest.mark.asyncio
async def test_razorpay_client_mock_mode():
    client = RazorpayDisputeClient()
    assert client.is_mock is True  # no real keys -> mock


@pytest.mark.asyncio
async def test_razorpay_submit_payload_mapping():
    client = RazorpayDisputeClient()
    evidence = {
        "logistics": {"status": "DELIVERED", "tracking_id": "DL123", "provider": "Delhivery"},
        "security": {"three_ds_passed": True, "three_ds_reference": "REF", "cvv_match": True},
        "crm": {"customer_order_count": 5},
    }
    res = await client.submit_contest("disp_demo", evidence, pdf_path="data/rebuttals/disp_demo.pdf")
    assert res["mock"] is True
    payload = res["evidence_payload"]
    assert payload["shipping_proof"] == "DL123"
    assert payload["payment_proof"] == "3ds_authenticated"
    assert payload["action"] == "contest"


@pytest.mark.asyncio
async def test_razorpay_accept_gated():
    client = RazorpayDisputeClient()
    blocked = await client.accept_dispute("disp_x", merchant_approved=False)
    assert blocked["status"] == "blocked"
    ok = await client.accept_dispute("disp_x", merchant_approved=True)
    assert ok["mock"] is True
    assert ok["status"] in ("mock_accepted", "accepted")


def test_webhook_hmac_verification():
    client = RazorpayDisputeClient()
    body = b'{"event":"payment.dispute.created"}'
    secret = settings.razorpay_webhook_secret
    good = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert client.verify_webhook_signature(body, good) is True
    assert client.verify_webhook_signature(body, "bad") is False


# ── Demo scenarios (mirror POST /webhook/demo/{id}) ─────────────────────────

def _demo_state(sid: str) -> DisputeState:
    from app.mock.scenarios import _SCENARIO_REGISTRY
    meta = _SCENARIO_REGISTRY[sid]["meta"]
    return DisputeState(
        dispute_id=f"disp_demo_{sid.lower()}",
        payment_id=sid,
        merchant_id=meta["merchant_id"],
        reason_code=meta["reason_code"],
        amount=meta["amount_paise"],
        phase=meta["phase"],
        raw_webhook={"demo": True, "scenario_id": sid},
        evidence_collected={},
        audit_events=[],
        error_log=[],
    )


@pytest.mark.asyncio
async def test_demo_scenario_fight_win():
    """Demo: PAY_FIGHT_WIN -> CONTEST -> PDF -> mock submit"""
    state = _demo_state("PAY_FIGHT_WIN")
    with patch("app.agents.evaluator.evaluate_evidence_strength", new_callable=AsyncMock, return_value={"fight_confidence": 0.91, "reasoning": "strong"}):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await dispute_graph.ainvoke(state)
    assert result["system_decision"] == "CONTEST"
    assert result["rebuttal_pdf_path"] is not None
    assert result["submission_response"]["mock"] is True
    assert "evidence_payload" in result["submission_response"]
    # audit contains full chain
    stages = [e["stage"] for e in result["audit_events"]]
    assert stages == ["CLASSIFICATION", "EVIDENCE_GATHERING", "EVIDENCE_GATHERING", "EVALUATION", "COMPILATION", "SUBMITTED"]


@pytest.mark.asyncio
async def test_demo_scenario_halt_transit():
    """Demo: PAY_HALT_TRANSIT -> SR_001 -> RECOMMEND_ACCEPT (graceful halt, no PDF)"""
    state = _demo_state("PAY_HALT_TRANSIT")
    with patch("asyncio.sleep", new_callable=AsyncMock):
        result = await dispute_graph.ainvoke(state)
    assert result["stopping_rule"] == "SR_001"
    assert result["system_decision"] == "RECOMMEND_ACCEPT"
    assert result["rebuttal_pdf_path"] is None
    assert "HALTED_ACCEPT" in [e["stage"] for e in result["audit_events"]]


@pytest.mark.asyncio
async def test_demo_scenario_api_timeout():
    """Demo: PAY_API_TIMEOUT -> SR_002 -> HUMAN_REVIEW"""
    state = _demo_state("PAY_API_TIMEOUT")
    with patch("asyncio.sleep", new_callable=AsyncMock):
        result = await dispute_graph.ainvoke(state)
    assert result["stopping_rule"] == "SR_002"
    assert result["system_decision"] == "HUMAN_REVIEW"
    assert result["rebuttal_pdf_path"] is None


@pytest.mark.asyncio
async def test_demo_scenario_weak_evidence():
    """Demo: PAY_WEAK_EVIDENCE -> low confidence -> RECOMMEND_ACCEPT"""
    state = _demo_state("PAY_WEAK_EVIDENCE")
    with patch("app.agents.evaluator.evaluate_evidence_strength", new_callable=AsyncMock, return_value={"fight_confidence": 0.45, "reasoning": "weak"}):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await dispute_graph.ainvoke(state)
    assert result["system_decision"] == "RECOMMEND_ACCEPT"
    assert result["rebuttal_pdf_path"] is None
