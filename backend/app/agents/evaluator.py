"""
agents/evaluator.py
───────────────────
Evaluator Agent — Step 3 of the LangGraph FSM.

This is the central intelligence of AutoDefend. It:
  1. Ingests all evidence gathered by the parallel executors.
  2. Applies strict rule-based "Stopping Rules" (e.g. SR_001, SR_002).
  3. Uses OpenAI to reason about evidence strength and calculate a final confidence score.
  4. Makes the final system decision: CONTEST | RECOMMEND_ACCEPT | HUMAN_REVIEW.
"""

import json
import logging
from datetime import datetime, timezone

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

from app.config import get_settings
from app.graph.state import DisputeState

logger = logging.getLogger(__name__)
settings = get_settings()


# ── Stopping Rules ────────────────────────────────────────────────────────────

def apply_stopping_rules(state: DisputeState) -> str | None:
    """
    Check strict business rules that override the LLM.
    Returns the stopping rule code if triggered, else None.
    """
    evidence = state.get("evidence_collected", {})
    
    # SR_001: Logistics says IN_TRANSIT -> guaranteed loss if we fight non-receipt
    logistics = evidence.get("logistics", {})
    if state.get("dispute_class") == "non_receipt" and logistics.get("status") == "IN_TRANSIT":
        logger.warning("Stopping Rule Triggered: SR_001 (In Transit)")
        return "SR_001"

    # SR_002: Critical API timeout -> requires human review
    for executor, data in evidence.items():
        if data.get("status") == "TIMEOUT":
            logger.warning("Stopping Rule Triggered: SR_002 (API Timeout on %s)", executor)
            return "SR_002"

    # SR_003: Over autonomous limit (e.g., > 5 Lakh INR)
    if state.get("amount", 0) > settings.autonomous_max_paise:
        logger.warning("Stopping Rule Triggered: SR_003 (High Value)")
        return "SR_003"

    return None


# ── LLM Confidence Evaluation ─────────────────────────────────────────────────

async def evaluate_evidence_strength(state: DisputeState) -> dict:
    """
    Uses OpenAI to evaluate the gathered evidence against the dispute reason.
    Outputs a confidence score (0.0 to 1.0) and human-readable reasoning.
    """
    if not settings.openai_api_key:
        raise ValueError("OpenAI API key required for Evaluator Agent")

    llm = ChatOpenAI(
        model="gpt-4o-mini",
        api_key=settings.openai_api_key,
        temperature=0,
    )

    prompt = f"""You are a payment dispute evaluator for Razorpay merchants.
Your job is to evaluate if the merchant has enough evidence to win this dispute.

DISPUTE DETAILS:
- Reason Code: {state['reason_code']}
- Dispute Class: {state['dispute_class']}
- Initial Base Confidence: {state['initial_confidence']}

EVIDENCE GATHERED:
{json.dumps(state.get('evidence_collected', {}), indent=2)}

INSTRUCTIONS:
1. Review the evidence strength for each gathered item.
2. If critical evidence (like delivery proof for non-receipt, or 3DS for fraud) is STRONG, adjust confidence UP.
3. If critical evidence is WEAK or MISSING, adjust confidence DOWN.
4. Output a final `fight_confidence` score between 0.00 and 1.00.
5. Provide a short 2-sentence reasoning for the score.

Respond ONLY with valid JSON in this exact format:
{{
  "fight_confidence": <float>,
  "reasoning": "<string>"
}}
"""

    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        raw = response.content.strip().strip("```json").strip("```").strip()
        result = json.loads(raw)
        
        # Enforce bounds
        conf = float(result.get("fight_confidence", state.get("initial_confidence", 0.5)))
        result["fight_confidence"] = max(0.0, min(1.0, conf))
        return result
        
    except Exception as exc:
        logger.error("LLM evaluation failed: %s", exc)
        # Safe fallback if LLM fails
        return {
            "fight_confidence": 0.40,  # Below threshold, will trigger RECOMMEND_ACCEPT
            "reasoning": f"LLM evaluation failed: {str(exc)}. Defaulting to safe score."
        }


# ── Evaluator Agent (LangGraph Node) ──────────────────────────────────────────

async def evaluator_agent(state: DisputeState) -> DisputeState:
    """
    LangGraph node: EVALUATE
    Input: state with evidence_collected
    Output: state with fight_confidence, system_decision, evaluator_reasoning
    """
    logger.info("Evaluator starting | dispute_id=%s", state["dispute_id"])

    # 1. Apply Deterministic Stopping Rules
    stopping_rule = apply_stopping_rules(state)
    state["stopping_rule"] = stopping_rule

    if stopping_rule == "SR_001":
        decision = "RECOMMEND_ACCEPT"
        confidence = 0.0
        reasoning = "Automatic accept: Item is still in transit."
    elif stopping_rule == "SR_002":
        decision = "HUMAN_REVIEW"
        confidence = 0.0
        reasoning = "API Timeout occurred during evidence gathering."
    elif stopping_rule == "SR_003":
        decision = "HUMAN_REVIEW"
        confidence = 0.5
        reasoning = f"Dispute amount ({state['amount']} paise) exceeds autonomous limit."
    else:
        # 2. No stopping rules -> Use LLM to calculate confidence
        eval_result = await evaluate_evidence_strength(state)
        confidence = eval_result["fight_confidence"]
        reasoning = eval_result["reasoning"]

        # 3. Apply Decision Threshold
        if confidence >= settings.auto_defend_confidence_threshold:
            decision = "CONTEST"
        else:
            decision = "RECOMMEND_ACCEPT"

    # Update state
    state["fight_confidence"] = confidence
    state["system_decision"] = decision
    state["evaluator_reasoning"] = reasoning

    # Audit trail
    state["audit_events"].append({
        "stage": "EVALUATION",
        "agent": "EvaluatorAgent",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stopping_rule": stopping_rule,
        "fight_confidence": confidence,
        "decision": decision,
        "reasoning": reasoning
    })

    logger.info("Evaluator done | decision=%s | confidence=%.2f | rule=%s", 
                decision, confidence, stopping_rule)

    return state
