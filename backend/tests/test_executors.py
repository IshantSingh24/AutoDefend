"""
tests/test_executors.py
───────────────────────
Unit tests for Parallel Executor Agents.

Tests:
  - Parallel node dispatch (only calls requested executors)
  - Retry logic triggers on timeouts and returns TIMEOUT status
  - Audit events appended correctly
  - Mock API responses match test cases
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, patch
import httpx

from app.agents.executors import (
    with_retry,
    logistics_executor,
    security_executor,
    crm_executor,
    parallel_executor_node
)
from app.graph.state import DisputeState


# ── Helpers ───────────────────────────────────────────────────────────────────

def _base_state(strategy: list[str]) -> DisputeState:
    """Minimal state dict with a specific evidence strategy."""
    return DisputeState(
        dispute_id="disp_test_exec",
        payment_id="PAY_FIGHT_WIN",  # Maps to Scenario A in mocks
        merchant_id="merchant_test",
        reason_code="VISA_10_4",
        amount=85000,
        phase="CHARGEBACK",
        raw_webhook={},
        evidence_collected={},
        evidence_strategy=strategy,
        audit_events=[],
        error_log=[],
    )


# ── Retry Logic Tests ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_with_retry_success():
    """If the coro succeeds first try, it returns immediately."""
    async def mock_coro():
        return {"status": "SUCCESS", "data": 123}

    result = await with_retry(mock_coro)
    assert result["status"] == "SUCCESS"
    assert result["data"] == 123


@pytest.mark.asyncio
async def test_with_retry_timeout():
    """If the coro raises TimeoutException repeatedly, it should exhaust retries and return TIMEOUT."""
    call_count = 0

    async def mock_coro():
        nonlocal call_count
        call_count += 1
        raise httpx.TimeoutException("Mock timeout")

    # Fast delay for tests
    result = await with_retry(mock_coro, retries=2, delay=0.01)
    
    assert call_count == 3  # Initial + 2 retries
    assert result["status"] == "TIMEOUT"
    assert "Mock timeout" in result["error"]
    assert result["evidence_strength"] == "MISSING"


# ── Node Dispatch Tests ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_parallel_executor_all():
    """If strategy asks for all 3, all 3 are executed and stored."""
    state = _base_state(["logistics", "security", "crm"])
    result_state = await parallel_executor_node(state)

    collected = result_state["evidence_collected"]
    assert "logistics" in collected
    assert "security" in collected
    assert "crm" in collected
    
    # Check data from PAY_FIGHT_WIN scenario
    assert collected["logistics"]["status"] == "DELIVERED"
    assert collected["security"]["three_ds_passed"] is True
    assert collected["crm"]["customer_order_count"] == 5

    # Check audit events
    audit_agents = [e["agent"] for e in result_state["audit_events"]]
    assert "LogisticsExecutor" in audit_agents
    assert "SecurityExecutor" in audit_agents
    assert "CrmExecutor" in audit_agents


@pytest.mark.asyncio
async def test_parallel_executor_partial():
    """If strategy asks for only 1, only 1 is executed."""
    state = _base_state(["security"])
    result_state = await parallel_executor_node(state)

    collected = result_state["evidence_collected"]
    assert "security" in collected
    assert "logistics" not in collected
    assert "crm" not in collected

    assert len(result_state["audit_events"]) == 1
    assert result_state["audit_events"][0]["agent"] == "SecurityExecutor"


# ── Scenario Timeout Integration ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mock_api_timeout_scenario():
    """
    PAY_API_TIMEOUT scenario has a 'TIMEOUT' status mock. 
    Our executors should translate this into an httpx.TimeoutException to test retry logic.
    """
    state = DisputeState(
        dispute_id="disp_test_timeout",
        payment_id="PAY_API_TIMEOUT",
        merchant_id="merchant_test",
        reason_code="MC_4855",
        amount=450000,
        phase="CHARGEBACK",
        raw_webhook={},
        evidence_collected={},
        evidence_strategy=["logistics"],
        audit_events=[],
        error_log=[],
    )

    # We mock asyncio.sleep so we don't wait for actual retry delays during testing
    with patch("asyncio.sleep", new_callable=AsyncMock):
        result_state = await parallel_executor_node(state)
        
    collected = result_state["evidence_collected"]
    
    # Should be TIMEOUT status because the mock triggers TimeoutException and retry exhausts
    assert collected["logistics"]["status"] == "TIMEOUT"
    assert "Connection to Logistics API timed out" in collected["logistics"]["error"]
