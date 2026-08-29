"""
graph/state.py
──────────────
DisputeState — the single shared dict that flows through every node
in the LangGraph FSM. All agents read from and write to this object.

Design rule: never mutate a field from a previous stage; only add new fields.
"""

from typing import Any, Optional
from typing_extensions import TypedDict


class DisputeState(TypedDict, total=False):
    """
    total=False means all keys are optional at construction time.
    Each agent adds its own fields; earlier fields remain unchanged.
    """

    # ── Input (from webhook) ──────────────────────────────────────────────────
    dispute_id:   str         # Razorpay dispute ID  e.g. "disp_ABC123"
    payment_id:   str         # Razorpay payment ID  e.g. "pay_XYZ789"
    merchant_id:  str         # Razorpay merchant ID
    reason_code:  str         # e.g. "VISA_10_4", "MC_4853", "UPI_RC1"
    amount:       int         # disputed amount in paise (₹1 = 100 paise)
    phase:        str         # CHARGEBACK | PRE_ARB | ARBITRATION
    raw_webhook:  dict        # full raw webhook payload (for audit)

    # ── Classification output (Classifier Agent) ──────────────────────────────
    dispute_class:      str         # fraud | non_receipt | service | policy
    evidence_strategy:  list[str]   # ordered list of required evidence keys
    initial_confidence: float       # base confidence from reason-code KB

    # ── Evidence gathered (Parallel Executors) ────────────────────────────────
    evidence_collected: dict[str, Any]   # keyed by executor: logistics/security/crm

    # ── Evaluation output (Evaluator Agent) ───────────────────────────────────
    fight_confidence:       Optional[float]   # weighted 0.0–1.0
    stopping_rule:          Optional[str]     # SR_001 … SR_004 if triggered
    system_decision:        Optional[str]     # CONTEST | RECOMMEND_ACCEPT | HUMAN_REVIEW
    evaluator_reasoning:    Optional[str]     # plain-English explanation (RBI FREE-AI)

    # ── Compiler output (Compiler Agent) ──────────────────────────────────────
    rebuttal_pdf_path:  Optional[str]   # local path to generated PDF
    evidence_packet:    Optional[dict]  # sanitised evidence used in letter (no None fields)

    # ── Submission result (Submit Node) ───────────────────────────────────────
    submission_response: Optional[dict]  # Razorpay API response
    submitted_at:        Optional[str]   # ISO timestamp

    # ── Meta / audit ──────────────────────────────────────────────────────────
    audit_events: list[dict]   # append-only in-memory log (persisted to DB separately)
    error_log:    list[str]    # non-fatal warnings / API errors captured per step
