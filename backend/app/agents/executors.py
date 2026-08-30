"""
agents/executors.py
────────────────────
Parallel Executor Agents — Step 2 of the LangGraph FSM.

These agents gather raw evidence from external APIs (logistics, security, crm).
They run concurrently via asyncio.gather() to minimize latency.
Includes robust retry logic for API timeouts.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

import httpx

from app.graph.state import DisputeState
from app.config import get_settings
from app.mock.scenarios import get_mock_response

logger = logging.getLogger(__name__)
settings = get_settings()


# ── Retry Logic ───────────────────────────────────────────────────────────────

async def with_retry(coro_func: Callable[[], Awaitable[Any]], retries: int = 2, delay: float = 1.0) -> dict:
    """
    Executes an awaitable-returning function with retry logic for network/timeout errors.
    Returns a TIMEOUT status dict if all retries fail.
    """
    for attempt in range(retries + 1):
        try:
            return await coro_func()
        except (httpx.TimeoutException, httpx.HTTPError) as e:
            logger.warning("API call failed (attempt %d/%d): %s", attempt + 1, retries + 1, str(e))
            if attempt == retries:
                logger.error("API call exhausted retries. Failing with TIMEOUT.")
                return {"status": "TIMEOUT", "error": str(e), "evidence_strength": "MISSING"}
            await asyncio.sleep(delay)
        except Exception as e:
            logger.exception("Unexpected error in executor")
            return {"status": "ERROR", "error": str(e), "evidence_strength": "MISSING"}


# ── Individual Executors ──────────────────────────────────────────────────────

async def _logistics_api_call(payment_id: str) -> dict:
    if settings.use_mock_apis:
        # Simulate network latency
        await asyncio.sleep(0.2)
        response = get_mock_response(payment_id, "logistics")
        if response.get("status") == "TIMEOUT":
            # Simulate a real httpx TimeoutException if mock data says TIMEOUT
            raise httpx.TimeoutException("Connection to Logistics API timed out")
        return response
    else:
        # Future: Real API call to Delhivery/Shiprocket
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.get(f"https://api.logistics.com/v1/track/{payment_id}")
            res.raise_for_status()
            return res.json()

async def logistics_executor(payment_id: str) -> dict:
    """Gathers delivery proof, signature, tracking history."""
    logger.info("Starting logistics_executor for payment_id=%s", payment_id)
    # The actual call is wrapped in with_retry
    return await with_retry(lambda: _logistics_api_call(payment_id))


async def _security_api_call(payment_id: str) -> dict:
    if settings.use_mock_apis:
        await asyncio.sleep(0.1)
        response = get_mock_response(payment_id, "security")
        if response.get("status") == "TIMEOUT":
            raise httpx.TimeoutException("Connection to Security API timed out")
        return response
    else:
        # Future: Real API call to Razorpay / Radar
        async with httpx.AsyncClient(timeout=3.0) as client:
            res = await client.get(f"https://api.razorpay.com/v1/payments/{payment_id}/risk")
            res.raise_for_status()
            return res.json()

async def security_executor(payment_id: str) -> dict:
    """Gathers 3DS, IP match, CVV match, device fingerprint."""
    logger.info("Starting security_executor for payment_id=%s", payment_id)
    return await with_retry(lambda: _security_api_call(payment_id))


async def _crm_api_call(payment_id: str) -> dict:
    if settings.use_mock_apis:
        await asyncio.sleep(0.1)
        response = get_mock_response(payment_id, "crm")
        if response.get("status") == "TIMEOUT":
            raise httpx.TimeoutException("Connection to CRM API timed out")
        return response
    else:
        # Future: Real API call to merchant Shopify/WooCommerce
        async with httpx.AsyncClient(timeout=4.0) as client:
            res = await client.get(f"https://api.merchant.com/v1/orders/{payment_id}")
            res.raise_for_status()
            return res.json()

async def crm_executor(payment_id: str) -> dict:
    """Gathers order history, LTV, prior disputes."""
    logger.info("Starting crm_executor for payment_id=%s", payment_id)
    return await with_retry(lambda: _crm_api_call(payment_id))


# ── Parallel Executor Node (LangGraph) ────────────────────────────────────────

async def parallel_executor_node(state: DisputeState) -> DisputeState:
    """
    LangGraph node: GATHER_EVIDENCE
    Input:  state with evidence_strategy (list of executors to run)
    Output: state with evidence_collected and updated audit_events
    """
    payment_id = state["payment_id"]
    strategy = state.get("evidence_strategy", [])
    
    logger.info("ParallelExecutor | dispute_id=%s | strategy=%s", state["dispute_id"], strategy)

    tasks: list[Awaitable[tuple[str, dict]]] = []
    
    # Helper to map executor name to its function and retain the name in gather results
    async def run_and_tag(name: str, coro: Awaitable[dict]) -> tuple[str, dict]:
        result = await coro
        return name, result

    # Dispatch only the requested executors
    if "logistics" in strategy:
        tasks.append(run_and_tag("logistics", logistics_executor(payment_id)))
    if "security" in strategy:
        tasks.append(run_and_tag("security", security_executor(payment_id)))
    if "crm" in strategy:
        tasks.append(run_and_tag("crm", crm_executor(payment_id)))

    # Execute all in parallel
    results = await asyncio.gather(*tasks, return_exceptions=True)

    evidence_collected = state.get("evidence_collected", {})
    
    for res in results:
        if isinstance(res, Exception):
            # This shouldn't normally happen because with_retry catches HTTP errors,
            # but we catch it here just in case of catastrophic failure (e.g. CancelledError)
            logger.exception("Catastrophic failure in executor task")
            state["error_log"].append(f"Executor failed completely: {str(res)}")
        else:
            name, data = res
            evidence_collected[name] = data
            
            # Append individual audit event for each executor result
            state["audit_events"].append({
                "stage":         "EVIDENCE_GATHERING",
                "agent":         f"{name.capitalize()}Executor",
                "timestamp":     datetime.now(timezone.utc).isoformat(),
                "status":        data.get("status", "SUCCESS"),
                "summary":       f"Gathered {name} evidence",
                "strength":      data.get("evidence_strength", "UNKNOWN")
            })

    state["evidence_collected"] = evidence_collected
    
    logger.info("ParallelExecutor done | dispute_id=%s | gathered=%s", 
                state["dispute_id"], list(evidence_collected.keys()))

    return state
