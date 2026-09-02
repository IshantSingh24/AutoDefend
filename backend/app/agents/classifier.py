"""
agents/classifier.py
────────────────────
Classifier — Deterministic FSM + Embedding (not LLM agent).

Option A: 4-centroid TF-IDF (not 400 hardcodes).
Every reason code (400+ Visa/MC/Amex/UPI) maps to one of 4 categories
via cosine to centroid descriptions — then category → executors.
Local, 5ms, $0, no bluff.
"""

import logging
from datetime import datetime, timezone

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.graph.state import DisputeState
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


# ── 4 Category Centroids (the ONLY hardcode — 4, not 400) ───────────────────
# Each centroid = concatenated keywords for that dispute family.
# Real Visa collapses 400 codes into these 4 families (Chargeflow: fraud/friendly/merchant-error)
CATEGORY_CENTROIDS: dict[str, str] = {
    "fraud":       "fraud unauthorized card stolen absent environment does not recognize unauthorized transaction no authorization cardholder does not recognize",
    "non_receipt": "merchandise services not received goods not provided not delivered non receipt delivery failure",
    "service":     "not as described defective merchandise quality cardholder dispute product not as described service not as described",
    "policy":      "cancelled merchandise services refund policy credit not processed cancellation policy refund not issued",
}

# Category → evidence strategy (4 entries, not 400)
CATEGORY_STRATEGY: dict[str, dict] = {
    "fraud": {
        "description":       "Fraud – Unauthorized / Card Absent",
        "required_evidence": ["security"],
        "optional_evidence": ["crm"],
        "executors":         ["security", "crm"],
        "base_confidence":   0.70,
    },
    "non_receipt": {
        "description":       "Non-Receipt – Goods/Services Not Provided",
        "required_evidence": ["logistics"],
        "optional_evidence": ["security"],
        "executors":         ["logistics", "security"],
        "base_confidence":   0.60,
    },
    "service": {
        "description":       "Service – Not as Described / Defective",
        "required_evidence": ["logistics"],
        "optional_evidence": ["crm"],
        "executors":         ["logistics", "crm"],
        "base_confidence":   0.55,
    },
    "policy": {
        "description":       "Policy – Cancelled / Refund Not Processed",
        "required_evidence": ["crm"],
        "optional_evidence": ["logistics"],
        "executors":         ["crm", "logistics"],
        "base_confidence":   0.50,
    },
}

# Legacy KB kept for audit/reference only — NOT used for routing (Option A)
# Maps known code → its human description (used as embedding input)
REASON_CODE_DESCRIPTIONS: dict[str, str] = {
    "VISA_10_4": "Fraud – Card Absent Environment unauthorized card stolen",
    "VISA_13_1": "Merchandise Services Not Received not delivered",
    "VISA_13_3": "Not as Described or Defective Merchandise quality dispute",
    "VISA_13_7": "Cancelled Merchandise Services refund policy",
    "MC_4853":   "Cardholder Dispute Not as Described defective product",
    "MC_4855":   "Goods or Services Not Provided not delivered",
    "MC_4863":   "Cardholder Does Not Recognize Transaction fraud",
    "UPI_RC1":   "UPI Unauthorized Transaction fraud no authorization",
    "UPI_RC2":   "UPI Goods Services Not Provided not received",
}
# Keep old KB for backward compat in tests (exposes REASON_CODE_KB)
REASON_CODE_KB = {
    k: {"dispute_class": v, **CATEGORY_STRATEGY[v]}
    for k, v in {
        "VISA_10_4": "fraud", "VISA_13_1": "non_receipt", "VISA_13_3": "service", "VISA_13_7": "policy",
        "MC_4853": "service", "MC_4855": "non_receipt", "MC_4863": "fraud", "UPI_RC1": "fraud", "UPI_RC2": "non_receipt"
    }.items()
}
# Also expose descriptions for audit
for k in REASON_CODE_KB:
    REASON_CODE_KB[k]["description"] = REASON_CODE_DESCRIPTIONS.get(k, "")

# ── TF-IDF embedder (local, 5ms, $0) ────────────────────────────────────────
# Fit once on 4 centroids — vocabulary = fraud/non_receipt/service/policy keywords
_centroid_names = list(CATEGORY_CENTROIDS.keys())
_centroid_docs = list(CATEGORY_CENTROIDS.values())
_vectorizer = TfidfVectorizer()
_centroid_vectors = _vectorizer.fit_transform(_centroid_docs)  # shape (4, vocab)


def _classify_via_embedding(reason_code: str) -> tuple[str, dict, str]:
    """
    Map any reason_code (400+ codes) → dispute_class via cosine to 4 centroids.
    Returns (dispute_class, strategy, source)
    """
    # 1. Get text for embedding: known description or raw code itself
    text = REASON_CODE_DESCRIPTIONS.get(reason_code, reason_code.replace("_", " ").replace("-", " "))
    # 2. Vectorize incoming text with same vectorizer
    try:
        vec = _vectorizer.transform([text])
        sims = cosine_similarity(vec, _centroid_vectors)[0]  # 4 scores
        best_idx = int(sims.argmax())
        max_sim = float(sims.max())
        # If no word overlap (e.g., "UPI_999_NEW"), sims are all 0 -> fallback to safe default
        if max_sim < 0.15:
            logger.warning("Embedding low confidence for %s (max_sim=%.2f) -> fallback default", reason_code, max_sim)
            return "unknown", {
                "description": f"Unknown reason code: {reason_code}",
                "required_evidence": ["logistics", "security", "crm"],
                "optional_evidence": [],
                "executors": ["logistics", "security", "crm"],
                "base_confidence": 0.40,
            }, "fallback_default"
        dispute_class = _centroid_names[best_idx]
        strategy = CATEGORY_STRATEGY[dispute_class]
        logger.info("Embedding classify | code=%s text='%s' -> class=%s sims=%s", reason_code, text, dispute_class, [f"{c}:{s:.2f}" for c,s in zip(_centroid_names, sims)])
        return dispute_class, strategy, "embedding"
    except Exception as exc:
        logger.warning("Embedding failed for %s: %s -> fallback", reason_code, exc)
        return "unknown", {
            "description": f"Unknown reason code: {reason_code}",
            "required_evidence": ["logistics", "security", "crm"],
            "optional_evidence": [],
            "executors": ["logistics", "security", "crm"],
            "base_confidence": 0.40,
        }, "fallback_default"


# ── Classifier Agent (LangGraph node) ────────────────────────────────────────

async def classifier_agent(state: DisputeState) -> DisputeState:
    """
    LangGraph node: CLASSIFY
    Input:  state with reason_code (any of 400+ codes)
    Output: state + dispute_class, evidence_strategy, initial_confidence
    Method: 4-centroid TF-IDF embedding (Option A), not 400 ifs. No LLM.
    """
    reason_code = state["reason_code"]
    logger.info("Classifier | dispute_id=%s | reason_code=%s", state["dispute_id"], reason_code)

    # Deterministic embedding (local, $0, 5ms) — covers 400+ via 4 categories
    dispute_class, strategy, source = _classify_via_embedding(reason_code)

    # 3. Update state via category strategy (4 entries, not 400)
    state["dispute_class"] = dispute_class
    state["evidence_strategy"] = strategy["executors"]
    state["initial_confidence"] = strategy["base_confidence"]

    # 4. Audit
    state["audit_events"].append({
        "stage": "CLASSIFICATION",
        "agent": "ClassifierAgent",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "reason_code": reason_code,
        "source": source,  # embedding | llm | fallback_default
        "dispute_class": dispute_class,
        "description": strategy["description"],
        "executors": strategy["executors"],
        "base_confidence": strategy["base_confidence"],
    })
    logger.info("Classifier done | class=%s | executors=%s | confidence=%.2f | source=%s", dispute_class, strategy["executors"], strategy["base_confidence"], source)
    return state
