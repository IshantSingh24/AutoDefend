"""
agents/evaluator.py
───────────────────
Evaluator — Deterministic FSM + ML (LightGBM) — no LLM, no bluff.

1. Hard gates (2 lines): TIMEOUT and high-value → HUMAN_REVIEW (safety)
2. LightGBM: encode evidence → predict_proba → fight_confidence → CONTEST if >=0.70
   Model: data/models/lightgbm_baseline.pkl trained on 500 synthetic (200/180/120)
   <10ms, $0, no 429, explainable via feature vector.
"""

import logging
import pickle
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from app.config import get_settings
from app.graph.state import DisputeState

logger = logging.getLogger(__name__)
settings = get_settings()

# ── Stopping Rules (only 2 hard gates — rest learned by ML) ─────────────────

def apply_stopping_rules(state: DisputeState) -> str | None:
    evidence = state.get("evidence_collected", {})
    for executor, data in evidence.items():
        if data.get("status") == "TIMEOUT":
            logger.warning("Stopping Rule: SR_002 (API Timeout on %s)", executor)
            return "SR_002"
    if state.get("amount", 0) > settings.autonomous_max_paise:
        logger.warning("Stopping Rule: SR_003 (High Value %s)", state.get("amount"))
        return "SR_003"
    return None


# ── LightGBM loader (once, ~150 trees) ───────────────────────────────────────

_MODEL_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "models" / "lightgbm_baseline.pkl"
_model = None

def _get_model():
    global _model
    if _model is not None:
        return _model
    if not _MODEL_PATH.exists():
        logger.warning("LightGBM model not found at %s — using rule fallback", _MODEL_PATH)
        return None
    try:
        with open(_MODEL_PATH, "rb") as f:
            _model = pickle.load(f)
        logger.info("LightGBM loaded | %s | %d estimators", _MODEL_PATH, _model.n_estimators)
        return _model
    except Exception as exc:
        logger.error("Failed to load LightGBM model: %s", exc)
        return None


# ── Feature encoding (must match train_two_models.py: encode) ────────────────

_REASON_CODES = ["MC_4853", "MC_4855", "MC_4863", "UPI_RC1", "UPI_RC2", "VISA_10_4", "VISA_13_1", "VISA_13_3", "VISA_13_7"]
_LOGI_STATUS = ["DELIVERED", "IN_TRANSIT", "TIMEOUT"]
_AVS_MAP = {"Y": 1, "N": 0, "U": 0.5, "": 0.5, None: 0.5}

def _encode(state: DisputeState) -> np.ndarray:
    logistics = state.get("evidence_collected", {}).get("logistics", {})
    security = state.get("evidence_collected", {}).get("security", {})
    crm = state.get("evidence_collected", {}).get("crm", {})
    return np.array([[
        state.get("amount", 0) / 100000,
        _LOGI_STATUS.index(logistics.get("status", "DELIVERED")) if logistics.get("status") in _LOGI_STATUS else 0,
        1 if logistics.get("signature_available") else 0,
        1 if security.get("three_ds_passed") else 0,
        1 if security.get("ip_match") or security.get("billing_address_match") else 0,
        1 if security.get("cvv_match") else 0,
        _AVS_MAP.get(security.get("avs_result"), 0.5),
        crm.get("order_count", crm.get("customer_order_count", 0)) / 10 if isinstance(crm.get("order_count", crm.get("customer_order_count", 0)), (int, float)) else 0,
        crm.get("prior_disputes", 0) / 5 if isinstance(crm.get("prior_disputes"), (int, float)) else 0,
        crm.get("days_since", crm.get("customer_since_days", 100)) / 365 if isinstance(crm.get("days_since", crm.get("customer_since_days", 100)), (int, float)) else 0.27,
        _REASON_CODES.index(state.get("reason_code", "VISA_10_4")) / len(_REASON_CODES) if state.get("reason_code") in _REASON_CODES else 0.5,
    ]], dtype=float)


def _rule_fallback_confidence(state: DisputeState) -> tuple[float, str]:
    """Rule fallback if model missing — same weights as old heuristic, for safety."""
    logistics = state.get("evidence_collected", {}).get("logistics", {})
    security = state.get("evidence_collected", {}).get("security", {})
    crm = state.get("evidence_collected", {}).get("crm", {})
    score = 0
    if logistics.get("status") == "DELIVERED": score += 0.35
    if logistics.get("signature_available"): score += 0.05
    if security.get("three_ds_passed"): score += 0.25
    if security.get("ip_match") or security.get("billing_address_match"): score += 0.20
    if security.get("cvv_match"): score += 0.10
    oc = crm.get("order_count", crm.get("customer_order_count", 0))
    if isinstance(oc, (int, float)) and oc >= 5: score += 0.10
    if security.get("avs_result") == "Y": score += 0.05
    score = min(1.0, score)
    reason = f"Rule fallback score {score:.2f} (delivery+3DS+IP+CVV+CRM) — model not loaded"
    return score, reason


# ── Evaluator Agent (LangGraph Node) ─────────────────────────────────────────

async def evaluator_agent(state: DisputeState) -> DisputeState:
    logger.info("Evaluator (LightGBM) | dispute_id=%s", state["dispute_id"])
    stopping_rule = apply_stopping_rules(state)
    state["stopping_rule"] = stopping_rule

    if stopping_rule == "SR_002":
        decision = "HUMAN_REVIEW"
        confidence = 0.0
        reasoning = "API Timeout — evidence incomplete, routed to human review."
    elif stopping_rule == "SR_003":
        decision = "HUMAN_REVIEW"
        confidence = 0.5
        reasoning = f"Amount {state['amount']} paise exceeds autonomous limit {settings.autonomous_max_paise}."
    else:
        model = _get_model()
        if model is not None:
            try:
                X = _encode(state)
                proba = float(model.predict_proba(X)[0][1])
                confidence = max(0.0, min(1.0, proba))
                # Human-readable reasoning from top features (matches train_two_models.py importance)
                if confidence >= 0.85:
                    reasoning = f"LightGBM confidence {confidence:.2f} — strong signals (repeat customer, 3DS passed, delivered)."
                elif confidence >= 0.70:
                    reasoning = f"LightGBM confidence {confidence:.2f} — sufficient evidence to contest."
                else:
                    reasoning = f"LightGBM confidence {confidence:.2f} — weak signals (no signature, 3DS failed, new customer) below threshold {settings.auto_defend_confidence_threshold}."
            except Exception as exc:
                logger.error("LightGBM inference failed: %s — fallback to rule", exc)
                confidence, reasoning = _rule_fallback_confidence(state)
        else:
            confidence, reasoning = _rule_fallback_confidence(state)

        # Threshold gate
        if confidence >= settings.auto_defend_confidence_threshold:
            decision = "CONTEST"
        else:
            decision = "RECOMMEND_ACCEPT"

    state["fight_confidence"] = confidence
    state["system_decision"] = decision
    state["evaluator_reasoning"] = reasoning

    state["audit_events"].append({
        "stage": "EVALUATION",
        "agent": "EvaluatorAgent",
        "model": "lightgbm_baseline" if _get_model() is not None else "rule_fallback",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stopping_rule": stopping_rule,
        "fight_confidence": confidence,
        "decision": decision,
        "reasoning": reasoning,
    })
    logger.info("Evaluator done | decision=%s | confidence=%.2f | rule=%s", decision, confidence, stopping_rule)
    return state
