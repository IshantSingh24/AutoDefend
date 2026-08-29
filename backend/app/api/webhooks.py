"""
api/webhooks.py
───────────────
Receives Razorpay dispute webhook events.

Flow:
  1. Validate HMAC-SHA256 signature (reject if invalid)
  2. Parse payload → extract dispute fields
  3. Persist a new Dispute row (state = INGESTED)
  4. Launch LangGraph FSM in background (non-blocking)
  5. Return HTTP 200 immediately (Razorpay requires < 5s response)
"""

import hashlib
import hmac
import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.connection import get_db
from app.db.models import Dispute
from app.graph.state import DisputeState

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter()


# ── Signature validation ──────────────────────────────────────────────────────

def _verify_razorpay_signature(body: bytes, signature: str) -> bool:
    """
    Validate the X-Razorpay-Signature header.
    Razorpay signs the raw request body with HMAC-SHA256 using the webhook secret.
    Returns True if valid, False otherwise.
    """
    if not settings.razorpay_webhook_secret or settings.razorpay_webhook_secret == "placeholder":
        # In dev/mock mode, skip validation
        logger.warning("Webhook signature validation skipped (no secret configured)")
        return True

    expected = hmac.new(
        settings.razorpay_webhook_secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


# ── Payload parsing ───────────────────────────────────────────────────────────

def _parse_dispute_payload(payload: dict) -> dict:
    """
    Extract dispute fields from Razorpay webhook payload.
    Handles both payment.dispute.created and payment.dispute.updated events.
    """
    entity = payload.get("payload", {}).get("dispute", {}).get("entity", {})
    payment = payload.get("payload", {}).get("payment", {}).get("entity", {})

    return {
        "razorpay_dispute_id": entity.get("id", f"disp_mock_{uuid.uuid4().hex[:8]}"),
        "payment_id":          entity.get("payment_id") or payment.get("id", "pay_unknown"),
        "merchant_id":         entity.get("merchant_id", "merchant_unknown"),
        "reason_code":         _normalize_reason_code(entity.get("reason_code", "UNKNOWN")),
        "amount":              entity.get("amount", 0),
        "phase":               _normalize_phase(entity.get("phase", "chargeback")),
        "raw_webhook":         payload,
    }


def _normalize_reason_code(code: str) -> str:
    """Map Razorpay's raw reason codes to our internal format."""
    mapping = {
        "chargeback":         "VISA_10_4",   # generic fallback
        "not_received":       "VISA_13_1",
        "not_as_described":   "VISA_13_3",
        "cancelled":          "VISA_13_7",
        "unauthorized":       "VISA_10_4",
    }
    return mapping.get(code.lower(), code.upper().replace("-", "_"))


def _normalize_phase(phase: str) -> str:
    mapping = {
        "chargeback":       "CHARGEBACK",
        "pre_arbitration":  "PRE_ARB",
        "arbitration":      "ARBITRATION",
    }
    return mapping.get(phase.lower(), "CHARGEBACK")


# ── Background task: run the FSM ──────────────────────────────────────────────

async def _run_fsm_pipeline(state: DisputeState, dispute_db_id: str) -> None:
    """
    Launched as a background task after webhook is acknowledged.
    Imports graph lazily to avoid circular imports at startup.
    """
    try:
        # Lazy import — graph module is built in Step 8
        from app.graph.fsm import dispute_graph  # noqa: F401
        logger.info("FSM pipeline started | dispute_id=%s", state["dispute_id"])
        await dispute_graph.ainvoke(state)
        logger.info("FSM pipeline complete | dispute_id=%s", state["dispute_id"])
    except ImportError:
        # Step 8 not built yet — log and continue (expected during Steps 3–7)
        logger.warning(
            "FSM graph not yet available (Step 8 pending) | dispute_id=%s",
            state["dispute_id"],
        )
    except Exception as exc:
        logger.exception("FSM pipeline error | dispute_id=%s | error=%s", state["dispute_id"], exc)


# ── Webhook endpoint ──────────────────────────────────────────────────────────

@router.post("/dispute", status_code=200)
async def receive_dispute_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict:
    """
    POST /webhook/dispute
    Razorpay calls this when a dispute is created or updated.
    Must return 200 within 5 seconds — FSM runs in background.
    """
    body = await request.body()

    # 1. Signature validation
    signature = request.headers.get("X-Razorpay-Signature", "")
    if not _verify_razorpay_signature(body, signature):
        logger.warning("Invalid webhook signature received")
        raise HTTPException(status_code=400, detail="Invalid signature")

    # 2. Parse payload
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    event = payload.get("event", "")
    if event not in ("payment.dispute.created", "payment.dispute.updated", ""):
        # Acknowledge unknown events but do nothing
        return {"status": "ignored", "event": event}

    fields = _parse_dispute_payload(payload)
    logger.info(
        "Webhook received | event=%s | dispute_id=%s | reason=%s | amount=%s paise",
        event, fields["razorpay_dispute_id"], fields["reason_code"], fields["amount"],
    )

    # 3. Persist Dispute row (INGESTED state)
    dispute = Dispute(
        id=str(uuid.uuid4()),
        razorpay_dispute_id=fields["razorpay_dispute_id"],
        payment_id=fields["payment_id"],
        merchant_id=fields["merchant_id"],
        reason_code=fields["reason_code"],
        amount=fields["amount"],
        phase=fields["phase"],
        fsm_state="INGESTED",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(dispute)
    db.commit()
    db.refresh(dispute)

    # 4. Build initial DisputeState and launch FSM in background
    state: DisputeState = {
        "dispute_id":        fields["razorpay_dispute_id"],
        "payment_id":        fields["payment_id"],
        "merchant_id":       fields["merchant_id"],
        "reason_code":       fields["reason_code"],
        "amount":            fields["amount"],
        "phase":             fields["phase"],
        "raw_webhook":       payload,
        "evidence_collected": {},
        "audit_events":      [],
        "error_log":         [],
    }

    background_tasks.add_task(_run_fsm_pipeline, state, dispute.id)

    # 5. Return 200 immediately
    return {
        "status":     "accepted",
        "dispute_id": fields["razorpay_dispute_id"],
        "db_id":      dispute.id,
    }


# ── Demo trigger endpoint (for hackathon demo only) ───────────────────────────

@router.post("/demo/{scenario_id}", status_code=200)
async def trigger_demo_scenario(
    scenario_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict:
    """
    POST /webhook/demo/{scenario_id}
    Triggers a mock scenario directly (no real Razorpay webhook needed).
    scenario_id: PAY_FIGHT_WIN | PAY_HALT_TRANSIT | PAY_API_TIMEOUT | PAY_WEAK_EVIDENCE
    """
    from app.mock.scenarios import _SCENARIO_REGISTRY

    scenario = _SCENARIO_REGISTRY.get(scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail=f"Unknown scenario: {scenario_id}")

    meta = scenario["meta"]
    dispute_db_id = str(uuid.uuid4())

    dispute = Dispute(
        id=dispute_db_id,
        razorpay_dispute_id=f"disp_demo_{scenario_id.lower()}",
        payment_id=scenario_id,
        merchant_id=meta["merchant_id"],
        reason_code=meta["reason_code"],
        amount=meta["amount_paise"],
        phase=meta["phase"],
        fsm_state="INGESTED",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(dispute)
    db.commit()

    state: DisputeState = {
        "dispute_id":         f"disp_demo_{scenario_id.lower()}",
        "payment_id":         scenario_id,
        "merchant_id":        meta["merchant_id"],
        "reason_code":        meta["reason_code"],
        "amount":             meta["amount_paise"],
        "phase":              meta["phase"],
        "raw_webhook":        {"demo": True, "scenario_id": scenario_id},
        "evidence_collected": {},
        "audit_events":       [],
        "error_log":          [],
    }

    background_tasks.add_task(_run_fsm_pipeline, state, dispute_db_id)

    logger.info("Demo scenario triggered | scenario=%s | reason=%s", scenario_id, meta["reason_code"])
    return {
        "status":      "demo_started",
        "scenario_id": scenario_id,
        "dispute_id":  f"disp_demo_{scenario_id.lower()}",
        "description": meta["description"],
    }
