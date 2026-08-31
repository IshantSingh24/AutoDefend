"""
graph/fsm.py
────────────
LangGraph FSM — wires all agents into a deterministic state machine.

Flow: classify -> gather -> evaluate -> [compile -> submit | halt_accept | halt_review]

Rules:
  - No direct DB calls — all via DisputeState
  - Every node appends to audit_events
  - Bounded automation: high-value disputes routed to HUMAN_REVIEW, never auto-escalate
"""

import logging
from datetime import datetime, timezone

from langgraph.graph import END, StateGraph

from app.config import get_settings
from app.graph.state import DisputeState
from app.agents.classifier import classifier_agent
from app.agents.compiler import compiler_agent
from app.agents.evaluator import evaluator_agent
from app.agents.executors import parallel_executor_node

logger = logging.getLogger(__name__)
settings = get_settings()


# ── Routing ───────────────────────────────────────────────────────────────────

def route_after_evaluation(state: DisputeState) -> str:
    """
    Conditional edge after evaluate node.
    Maps Evaluator's system_decision to next node name.
    """
    decision = state.get("system_decision")
    if decision == "CONTEST":
        return "compile"
    elif decision == "RECOMMEND_ACCEPT":
        return "halt_accept"
    else:  # HUMAN_REVIEW or any unknown -> safe default
        return "halt_review"


# ── Halt nodes ────────────────────────────────────────────────────────────────

async def halt_accept_node(state: DisputeState) -> DisputeState:
    """Halted: evidence does not support filing. Merchant should accept."""
    logger.info("HALT_ACCEPT | dispute_id=%s | confidence=%.2f", state.get("dispute_id"), state.get("fight_confidence", 0))
    # Ensure compiler fields exist even when compile node was skipped
    state.setdefault("rebuttal_pdf_path", None)
    state.setdefault("evidence_packet", None)
    state["audit_events"].append({
        "stage": "HALTED_ACCEPT",
        "agent": "HaltAcceptNode",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "reason": state.get("evaluator_reasoning", "Recommendation: accept this dispute"),
        "stopping_rule": state.get("stopping_rule"),
        "fight_confidence": state.get("fight_confidence"),
        "decision": "RECOMMEND_ACCEPT",
    })
    return state


async def halt_review_node(state: DisputeState) -> DisputeState:
    """Halted: needs human review — API failure or high-value threshold."""
    reason = state.get("evaluator_reasoning", "Routed to human review")
    # Add extra context for high-value or timeout
    if state.get("stopping_rule") == "SR_002":
        reason = f"API timeout — evidence incomplete. {reason}"
    elif state.get("stopping_rule") == "SR_003":
        reason = f"Amount {state.get('amount')} paise exceeds autonomous limit ({settings.autonomous_max_paise}). {reason}"
    logger.info("HALT_REVIEW | dispute_id=%s | rule=%s", state.get("dispute_id"), state.get("stopping_rule"))
    state.setdefault("rebuttal_pdf_path", None)
    state.setdefault("evidence_packet", None)
    state["audit_events"].append({
        "stage": "HALTED_REVIEW",
        "agent": "HaltReviewNode",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
        "stopping_rule": state.get("stopping_rule"),
        "fight_confidence": state.get("fight_confidence"),
        "decision": "HUMAN_REVIEW",
        "error_log": state.get("error_log", []),
    })
    return state


# ── Submit node ───────────────────────────────────────────────────────────────

async def submit_node(state: DisputeState) -> DisputeState:
    """
    Submit compiled rebuttal to Razorpay. Bounded: high-value check before submission.
    In mock mode (use_mock_apis=True) or when Razorpay client unavailable, mock the submission.
    """
    # High-value safeguard — never auto-submit disputes above threshold
    if state.get("amount", 0) > settings.high_value_threshold_paise:
        logger.warning("Submit blocked — high value %s paise > threshold %s", state.get("amount"), settings.high_value_threshold_paise)
        state["audit_events"].append({
            "stage": "SUBMIT_BLOCKED_HIGH_VALUE",
            "agent": "SubmitNode",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "reason": f"Amount {state.get('amount')} exceeds high-value threshold {settings.high_value_threshold_paise} — requires merchant approval",
            "amount": state.get("amount"),
            "threshold": settings.high_value_threshold_paise,
        })
        return await halt_review_node(state)

    # Attempt real submission if client exists, else mock
    try:
        from app.services.razorpay_client import RazorpayDisputeClient  # lazy — Step 9

        client = RazorpayDisputeClient()
        result = await client.submit_contest(
            dispute_id=state["dispute_id"],
            evidence=state.get("evidence_packet", {}),
            pdf_path=state.get("rebuttal_pdf_path"),
        )
        state["submission_response"] = result
        state["submitted_at"] = datetime.now(timezone.utc).isoformat()
        state["audit_events"].append({
            "stage": "SUBMITTED",
            "agent": "SubmitNode",
            "timestamp": state["submitted_at"],
            "api_response": result,
            "pdf_path": state.get("rebuttal_pdf_path"),
        })
        logger.info("SUBMITTED | dispute_id=%s | response=%s", state.get("dispute_id"), result.get("status") if isinstance(result, dict) else result)
    except ImportError:
        # Step 9 not yet built — mock submission for demo/testing
        logger.info("Submit mock (razorpay_client not available) | dispute_id=%s", state.get("dispute_id"))
        state["submission_response"] = {"status": "mock_submitted", "mock": True, "dispute_id": state["dispute_id"]}
        state["submitted_at"] = datetime.now(timezone.utc).isoformat()
        state["audit_events"].append({
            "stage": "SUBMITTED",
            "agent": "SubmitNode",
            "timestamp": state["submitted_at"],
            "api_response": state["submission_response"],
            "pdf_path": state.get("rebuttal_pdf_path"),
            "mock": True,
        })
    except Exception as exc:
        logger.exception("Submit failed | dispute_id=%s", state.get("dispute_id"))
        state["error_log"].append(f"Submit error: {exc}")
        state["audit_events"].append({
            "stage": "SUBMIT_FAILED",
            "agent": "SubmitNode",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": str(exc),
        })
        # Route to human review on submission failure
        return await halt_review_node(state)

    return state


# ── Graph builder ─────────────────────────────────────────────────────────────

def build_dispute_graph():
    builder = StateGraph(DisputeState)

    builder.add_node("classify", classifier_agent)
    builder.add_node("gather", parallel_executor_node)
    builder.add_node("evaluate", evaluator_agent)
    builder.add_node("compile", compiler_agent)
    builder.add_node("submit", submit_node)
    builder.add_node("halt_accept", halt_accept_node)
    builder.add_node("halt_review", halt_review_node)

    builder.set_entry_point("classify")
    builder.add_edge("classify", "gather")
    builder.add_edge("gather", "evaluate")

    builder.add_conditional_edges(
        "evaluate",
        route_after_evaluation,
        {
            "compile": "compile",
            "halt_accept": "halt_accept",
            "halt_review": "halt_review",
        },
    )

    builder.add_edge("compile", "submit")
    builder.add_edge("submit", END)
    builder.add_edge("halt_accept", END)
    builder.add_edge("halt_review", END)

    return builder.compile()


# Compiled graph singleton — imported by webhooks.py background task
dispute_graph = build_dispute_graph()
