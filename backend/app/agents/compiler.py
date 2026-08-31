"""
agents/compiler.py
──────────────────
Compiler Agent — Step 4 of the LangGraph FSM (after Evaluator).

Responsibility:
  - Build a sanitised evidence_packet (strip all None/empty fields) — anti-hallucination guarantee
  - Render Jinja2 template + generate ReportLab PDF via pdf_generator service
  - Only cites evidence that exists in evidence_collected
  - Appends COMPILATION event to audit trail

Rules:
  - NEVER use LLM for factual claims — template only
  - No direct DB calls — all via DisputeState
  - Every invocation appends to audit_events
"""

import logging
from datetime import datetime, timezone
from typing import Any

from app.graph.state import DisputeState
from app.services.pdf_generator import generate_rebuttal_pdf

logger = logging.getLogger(__name__)


def build_evidence_packet(evidence: dict[str, Any]) -> dict[str, Any]:
    """
    Anti-hallucination guarantee: only include evidence fields that are non-null.
    Any None field is excluded entirely. Logistics only included if DELIVERED.
    This is the sole source of truth for the PDF — template cannot hallucinate.
    """
    packet: dict[str, Any] = {}

    # Logistics — only if DELIVERED (otherwise Exhibit A omitted)
    logistics = evidence.get("logistics", {})
    if logistics.get("status") == "DELIVERED":
        packet["logistics"] = {k: v for k, v in logistics.items() if v is not None}
    # Note: IN_TRANSIT / TIMEOUT logistics intentionally excluded — prevents filing weak transit proof

    # Security — include if any keys present, strip None values
    security = evidence.get("security", {})
    if security:
        packet["security"] = {k: v for k, v in security.items() if v is not None}

    # CRM — include if present, strip None values
    crm = evidence.get("crm", {})
    if crm:
        packet["crm"] = {k: v for k, v in crm.items() if v is not None}

    return packet


async def compiler_agent(state: DisputeState) -> DisputeState:
    """
    LangGraph node: COMPILE
    Input:  state with system_decision == CONTEST and evidence_collected
    Output: state + evidence_packet, rebuttal_pdf_path (+ audit event)

    Guard: if decision is not CONTEST, skip PDF generation and log why.
    """
    dispute_id = state.get("dispute_id", "unknown")
    decision = state.get("system_decision")

    logger.info("Compiler starting | dispute_id=%s | decision=%s", dispute_id, decision)

    # Guard — only compile for CONTEST; never hallucinate for ACCEPT/HUMAN_REVIEW
    if decision != "CONTEST":
        reason = f"Skipped compilation — system_decision is {decision}, not CONTEST"
        logger.info("Compiler skipped | dispute_id=%s | reason=%s", dispute_id, reason)
        state["audit_events"].append({
            "stage": "COMPILATION",
            "agent": "CompilerAgent",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "skipped": True,
            "reason": reason,
            "decision": decision,
        })
        # Ensure fields exist but are None
        state["rebuttal_pdf_path"] = None
        state["evidence_packet"] = None
        return state

    evidence = state.get("evidence_collected", {})
    if not evidence:
        logger.warning("Compiler | no evidence_collected for dispute_id=%s", dispute_id)
        state["audit_events"].append({
            "stage": "COMPILATION",
            "agent": "CompilerAgent",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "skipped": True,
            "reason": "No evidence_collected — cannot compile",
            "decision": decision,
        })
        state["rebuttal_pdf_path"] = None
        state["evidence_packet"] = None
        return state

    # 1. Build sanitised packet (anti-hallucination)
    packet = build_evidence_packet(evidence)
    state["evidence_packet"] = packet

    # 2. Generate PDF via service
    try:
        result = await generate_rebuttal_pdf(
            dispute_id=state["dispute_id"],
            payment_id=state["payment_id"],
            merchant_id=state["merchant_id"],
            reason_code=state["reason_code"],
            amount_paise=state.get("amount", 0),
            evidence_packet=packet,
        )
        pdf_path = result["pdf_path"]
        word_count = result["word_count"]
        state["rebuttal_pdf_path"] = pdf_path

        # 3. Audit success
        state["audit_events"].append({
            "stage": "COMPILATION",
            "agent": "CompilerAgent",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "skipped": False,
            "pdf_path": pdf_path,
            "html_path": result["html_path"],
            "word_count": word_count,
            "evidence_keys": list(packet.keys()),
            "reason_code": state["reason_code"],
        })
        logger.info("Compiler done | dispute_id=%s | pdf=%s | words=%d", dispute_id, pdf_path, word_count)

    except Exception as exc:
        logger.exception("Compiler PDF generation failed | dispute_id=%s", dispute_id)
        state["error_log"].append(f"Compiler PDF error: {exc}")
        state["audit_events"].append({
            "stage": "COMPILATION",
            "agent": "CompilerAgent",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "skipped": True,
            "error": str(exc),
            "reason": "PDF generation exception",
        })
        state["rebuttal_pdf_path"] = None

    return state
