"""
agents/classifier.py
─────────────────────
Classifier Agent — Step 1 of the LangGraph FSM.

Responsibility:
  - Map a reason code to an evidence strategy (deterministic KB lookup)
  - LLM fallback for unknown/future reason codes
  - Populate DisputeState with: dispute_class, evidence_strategy, initial_confidence
  - Append CLASSIFICATION event to audit trail

Design rule: deterministic lookup ALWAYS preferred over LLM.
LLM is a safety net only — keeps costs low and behaviour predictable.
"""

import logging
from datetime import datetime, timezone

from app.graph.state import DisputeState
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


# ── Reason Code Knowledge Base ────────────────────────────────────────────────
# Each entry defines:
#   dispute_class     : fraud | non_receipt | service | policy
#   required_evidence : must be present for Evaluator to approve filing
#   optional_evidence : boosts confidence if present, but not blocking
#   base_confidence   : starting confidence score before evidence is checked
#   executors         : which executor agents to call (logistics/security/crm)
#   description       : human-readable label for audit trail

REASON_CODE_KB: dict[str, dict] = {

    # ── Visa ──────────────────────────────────────────────────────────────────
    "VISA_10_4": {
        "dispute_class":     "fraud",
        "description":       "Fraud – Card Absent Environment",
        "required_evidence": ["security"],
        "optional_evidence": ["crm"],
        "executors":         ["security", "crm"],
        "base_confidence":   0.75,
    },
    "VISA_13_1": {
        "dispute_class":     "non_receipt",
        "description":       "Merchandise / Services Not Received",
        "required_evidence": ["logistics"],
        "optional_evidence": ["security"],
        "executors":         ["logistics", "security"],
        "base_confidence":   0.60,
    },
    "VISA_13_3": {
        "dispute_class":     "service",
        "description":       "Not as Described or Defective Merchandise",
        "required_evidence": ["logistics"],
        "optional_evidence": ["crm"],
        "executors":         ["logistics", "crm"],
        "base_confidence":   0.55,
    },
    "VISA_13_7": {
        "dispute_class":     "policy",
        "description":       "Cancelled Merchandise / Services",
        "required_evidence": ["crm"],
        "optional_evidence": ["logistics"],
        "executors":         ["crm", "logistics"],
        "base_confidence":   0.50,
    },

    # ── Mastercard ────────────────────────────────────────────────────────────
    "MC_4853": {
        "dispute_class":     "service",
        "description":       "Cardholder Dispute – Not as Described",
        "required_evidence": ["logistics", "crm"],
        "optional_evidence": ["security"],
        "executors":         ["logistics", "crm", "security"],
        "base_confidence":   0.60,
    },
    "MC_4855": {
        "dispute_class":     "non_receipt",
        "description":       "Goods or Services Not Provided",
        "required_evidence": ["logistics"],
        "optional_evidence": ["crm"],
        "executors":         ["logistics", "crm"],
        "base_confidence":   0.55,
    },
    "MC_4863": {
        "dispute_class":     "fraud",
        "description":       "Cardholder Does Not Recognize Transaction",
        "required_evidence": ["security"],
        "optional_evidence": ["crm", "logistics"],
        "executors":         ["security", "crm"],
        "base_confidence":   0.70,
    },

    # ── UPI / NPCI ────────────────────────────────────────────────────────────
    "UPI_RC1": {
        "dispute_class":     "fraud",
        "description":       "UPI – Unauthorized Transaction",
        "required_evidence": ["security"],
        "optional_evidence": ["crm"],
        "executors":         ["security", "crm"],
        "base_confidence":   0.65,
    },
    "UPI_RC2": {
        "dispute_class":     "non_receipt",
        "description":       "UPI – Goods / Services Not Provided",
        "required_evidence": ["logistics"],
        "optional_evidence": [],
        "executors":         ["logistics"],
        "base_confidence":   0.55,
    },
}

# Codes that are always fraud-class (used to route security executor first)
FRAUD_CLASS_CODES = {"VISA_10_4", "MC_4863", "UPI_RC1"}


# ── LLM Fallback ──────────────────────────────────────────────────────────────

async def _llm_classify_unknown_code(reason_code: str) -> dict:
    """
    Called only when reason_code is NOT in REASON_CODE_KB.
    Uses OpenAI (preferred, if key set) or Gemini fallback.
    Returns a strategy dict in the same format as REASON_CODE_KB entries.
    """
    logger.warning("Unknown reason code '%s' — falling back to LLM classification", reason_code)

    prompt = f"""You are a payment dispute expert. Given the reason code "{reason_code}", 
determine the dispute classification.

Reply with ONLY valid JSON in this exact format:
{{
  "dispute_class": "<fraud|non_receipt|service|policy>",
  "description": "<short human-readable description>",
  "required_evidence": ["<logistics|security|crm>"],
  "optional_evidence": ["<logistics|security|crm>"],
  "executors": ["<logistics|security|crm>"],
  "base_confidence": <0.40 to 0.70 as a float>
}}

Be conservative with base_confidence for unknown codes."""

    try:
        import json

        # Prefer OpenAI if key is available
        if settings.openai_api_key:
            from langchain_openai import ChatOpenAI
            from langchain_core.messages import HumanMessage
            llm = ChatOpenAI(
                model="gpt-4o-mini",
                api_key=settings.openai_api_key,
                temperature=0,
            )
        elif settings.google_api_key:
            from langchain_google_genai import ChatGoogleGenerativeAI
            from langchain_core.messages import HumanMessage
            llm = ChatGoogleGenerativeAI(
                model="gemini-1.5-flash",
                google_api_key=settings.google_api_key,
                temperature=0,
            )
        else:
            raise ValueError("No LLM API key configured")

        from langchain_core.messages import HumanMessage
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        raw = response.content.strip().strip("```json").strip("```").strip()
        strategy = json.loads(raw)
        strategy["llm_classified"] = True
        logger.info("LLM classified '%s' as: %s", reason_code, strategy["dispute_class"])
        return strategy

    except Exception as exc:
        logger.error("LLM fallback failed for code '%s': %s — using safe default", reason_code, exc)
        return {
            "dispute_class":     "unknown",
            "description":       f"Unknown reason code: {reason_code}",
            "required_evidence": ["logistics", "security", "crm"],
            "optional_evidence": [],
            "executors":         ["logistics", "security", "crm"],
            "base_confidence":   0.40,
            "llm_classified":    False,
            "fallback":          True,
        }



# ── Classifier Agent (LangGraph node) ────────────────────────────────────────

async def classifier_agent(state: DisputeState) -> DisputeState:
    """
    LangGraph node: CLASSIFY
    Input:  state with reason_code
    Output: state + dispute_class, evidence_strategy, initial_confidence
    """
    reason_code = state["reason_code"]
    logger.info("Classifier | dispute_id=%s | reason_code=%s", state["dispute_id"], reason_code)

    # 1. Deterministic lookup (preferred)
    if reason_code in REASON_CODE_KB:
        strategy = REASON_CODE_KB[reason_code]
        source = "kb"
        logger.info("Classifier | KB hit | class=%s | confidence=%.2f",
                    strategy["dispute_class"], strategy["base_confidence"])
    else:
        # 2. LLM fallback for unknown codes
        strategy = await _llm_classify_unknown_code(reason_code)
        source = "llm" if not strategy.get("fallback") else "fallback_default"

    # 2. Update state
    state["dispute_class"]      = strategy["dispute_class"]
    state["evidence_strategy"]  = strategy["executors"]       # which executors to call
    state["initial_confidence"] = strategy["base_confidence"]

    # 3. Append to audit trail
    state["audit_events"].append({
        "stage":         "CLASSIFICATION",
        "agent":         "ClassifierAgent",
        "timestamp":     datetime.now(timezone.utc).isoformat(),
        "reason_code":   reason_code,
        "source":        source,                              # kb | llm | fallback_default
        "dispute_class": strategy["dispute_class"],
        "description":   strategy["description"],
        "executors":     strategy["executors"],
        "base_confidence": strategy["base_confidence"],
    })

    logger.info(
        "Classifier done | class=%s | executors=%s | confidence=%.2f | source=%s",
        strategy["dispute_class"],
        strategy["executors"],
        strategy["base_confidence"],
        source,
    )

    return state
