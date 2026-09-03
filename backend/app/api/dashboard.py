"""
api/dashboard.py
────────────────
Merchant-facing REST API for the AutoDefend dashboard.

Routes:
  GET  /api/disputes                       List all disputes with status badge
  GET  /api/disputes/{db_id}               Dispute detail + audit trail + evidence
  GET  /api/disputes/{db_id}/pdf           Download rebuttal PDF
  POST /api/disputes/{db_id}/accept        Merchant accepts (explicit approval)
  POST /api/disputes/{db_id}/contest       Merchant overrides to contest
  GET  /api/metrics/summary                30-day performance panel
  GET  /api/metrics/false-positive-cost     FP cost breakdown (prominent per track)

All read paths expose the hash-chained audit trail. Chain integrity is computed
live so tampering is visible to the merchant/admin.
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.connection import get_db
from app.db.models import AuditEvent, Dispute, EvidenceItem, User
from app.services.audit_logger import audit_logger
from app.services.security import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()

STATUS_BADGE = {
    "SUBMITTED":      "AUTO_DEFENDED",
    "WON":            "WON",
    "LOST":           "LOST",
    "RECOMMEND_ACCEPT": "ACCEPTED",
    "HUMAN_REVIEW":   "PENDING_REVIEW",
    "CONTEST":        "AUTO_DEFENDED",
}


# ── Serializers ──────────────────────────────────────────────────────────────

def _serialize_dispute(d: Dispute) -> dict:
    return {
        "db_id":            d.id,
        "dispute_id":       d.razorpay_dispute_id,
        "payment_id":       d.payment_id,
        "merchant_id":      d.merchant_id,
        "reason_code":      d.reason_code,
        "amount_paise":     d.amount,
        "amount_rs":        d.amount / 100,
        "phase":            d.phase,
        "fsm_state":        d.fsm_state,
        "dispute_class":    d.dispute_class,
        "initial_confidence": d.initial_confidence,
        "fight_confidence": d.fight_confidence,
        "stopping_rule":    d.stopping_rule,
        "system_decision":  d.system_decision,
        "status_badge":     STATUS_BADGE.get(d.system_decision or d.fsm_state, d.fsm_state),
        "rebuttal_pdf_path": d.rebuttal_pdf_path,
        "submitted_at":     d.submitted_at.isoformat() if d.submitted_at else None,
        "actual_outcome":   d.actual_outcome,
        "created_at":       d.created_at.isoformat() if d.created_at else None,
        "updated_at":       d.updated_at.isoformat() if d.updated_at else None,
    }


def _serialize_audit_event(e: AuditEvent, chain: dict) -> dict:
    return {
        "id":             e.id,
        "stage":          e.stage,
        "agent_name":     e.agent_name,
        "event_data":     e.event_data,
        "previous_hash":  e.previous_hash[:12],
        "event_hash":     e.event_hash[:12],
        "created_at":     e.created_at.isoformat() if e.created_at else None,
        "chain_intact":   chain["valid"],
    }


def _serialize_evidence(ev: EvidenceItem) -> dict:
    return {
        "id":            ev.id,
        "evidence_type": ev.evidence_type,
        "source_api":    ev.source_api,
        "strength":      ev.strength,
        "raw_data":      ev.raw_data,
        "fetched_at":    ev.fetched_at.isoformat() if ev.fetched_at else None,
    }


# ── API ──────────────────────────────────────────────────────────────────────

@router.get("/disputes")
def list_disputes(
    status: Optional[str] = None,
    limit: int = 100,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List this merchant's disputes, newest first. Optional ?status= filter."""
    q = db.query(Dispute).filter(Dispute.merchant_id == current.merchant_id).order_by(Dispute.created_at.desc())
    if status:
        q = q.filter(Dispute.fsm_state == status)
    rows = q.limit(min(limit, 200)).all()
    return {"disputes": [_serialize_dispute(d) for d in rows], "count": len(rows)}


@router.get("/disputes/{db_id}")
def dispute_detail(db_id: str, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Full detail: dispute + evidence items + hash-chained audit trail (scoped to merchant)."""
    d = db.query(Dispute).filter(Dispute.id == db_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Dispute not found")
    if d.merchant_id != current.merchant_id:
        raise HTTPException(status_code=403, detail="You do not have access to this dispute")

    evidence = db.query(EvidenceItem).filter_by(dispute_id=d.id).order_by(EvidenceItem.fetched_at.asc()).all()
    events = db.query(AuditEvent).filter_by(dispute_id=d.id).order_by(AuditEvent.created_at.asc()).all()
    chain = audit_logger.verify_chain_integrity(d.id, db=db)

    return {
        "dispute":   _serialize_dispute(d),
        "evidence":  [_serialize_evidence(ev) for ev in evidence],
        "audit_trail": {
            "chain_valid": chain["valid"],
            "total_events": chain["total"],
            "first_tampered_event": chain["first_tampered_event"],
            "events": [_serialize_audit_event(e, chain) for e in events],
        },
    }


@router.get("/disputes/{db_id}/pdf")
def download_rebuttal_pdf(db_id: str, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Download the compiled rebuttal PDF if one exists (scoped to merchant)."""
    d = db.query(Dispute).filter(Dispute.id == db_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Dispute not found")
    if d.merchant_id != current.merchant_id:
        raise HTTPException(status_code=403, detail="You do not have access to this dispute")
    if not d.rebuttal_pdf_path or not os.path.exists(d.rebuttal_pdf_path):
        raise HTTPException(status_code=404, detail="No rebuttal PDF generated for this dispute")
    return FileResponse(d.rebuttal_pdf_path, media_type="application/pdf",
                        filename=f"rebuttal_{d.razorpay_dispute_id}.pdf")


class MerchantAction(BaseModel):
    """Merchant's explicit decision. Never initiated by the AI."""
    note: Optional[str] = None


@router.post("/disputes/{db_id}/accept")
def merchant_accept(db_id: str, body: MerchantAction, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Merchant explicitly absorbs the dispute (accept the chargeback).
    This is a human-in-the-loop override — the system never accepts on its own.
    """
    d = db.query(Dispute).filter(Dispute.id == db_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Dispute not found")
    if d.merchant_id != current.merchant_id:
        raise HTTPException(status_code=403, detail="You do not have access to this dispute")
    d.system_decision = "RECOMMEND_ACCEPT"
    d.fsm_state = "ACCEPTED"
    d.actual_outcome = "ACCEPTED"
    db.commit()
    audit_logger.log_event(d.id, "MERCHANT_REVIEW", "Merchant", {
        "action": "accept",
        "note": body.note,
        "reason_code": d.reason_code,
    }, db=db)
    return {"status": "accepted", "dispute_id": d.razorpay_dispute_id}


@router.post("/disputes/{db_id}/contest")
def merchant_contest(db_id: str, body: MerchantAction, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Merchant overrides the recommendation to contest regardless (scoped to merchant)."""
    d = db.query(Dispute).filter(Dispute.id == db_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Dispute not found")
    if d.merchant_id != current.merchant_id:
        raise HTTPException(status_code=403, detail="You do not have access to this dispute")
    d.system_decision = "CONTEST"
    d.fsm_state = "SUBMITTED"
    db.commit()
    audit_logger.log_event(d.id, "MERCHANT_REVIEW", "Merchant", {
        "action": "contest_override",
        "note": body.note,
        "reason_code": d.reason_code,
    }, db=db)
    return {"status": "contested", "dispute_id": d.razorpay_dispute_id}


# ── Metrics ──────────────────────────────────────────────────────────────────

@router.get("/metrics/summary")
def metrics_summary(days: int = 30, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Performance panel (this merchant only): win rate, revenue, FP cost, time saved, TAT."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    m = current.merchant_id

    total = db.query(Dispute).filter(Dispute.merchant_id == m, Dispute.created_at >= since).count()
    won = db.query(Dispute).filter(Dispute.merchant_id == m, Dispute.created_at >= since, Dispute.actual_outcome == "WON").count()
    lost = db.query(Dispute).filter(Dispute.merchant_id == m, Dispute.created_at >= since, Dispute.actual_outcome == "LOST").count()
    contested = db.query(Dispute).filter(Dispute.merchant_id == m, Dispute.created_at >= since, Dispute.system_decision == "CONTEST").count()
    accepted = db.query(Dispute).filter(Dispute.merchant_id == m, Dispute.created_at >= since, Dispute.system_decision == "RECOMMEND_ACCEPT").count()
    pending_review = db.query(Dispute).filter(Dispute.merchant_id == m, Dispute.created_at >= since, Dispute.fsm_state == "HUMAN_REVIEW").count()

    revenue_won_paise = db.query(Dispute).filter(
        Dispute.merchant_id == m, Dispute.created_at >= since, Dispute.actual_outcome == "WON"
    ).with_entities(Dispute.amount).all()
    revenue_paise = sum(r[0] for r in revenue_won_paise)

    # Time saved: each auto-defended dispute saves the merchant ~4h of manual
    # evidence assembly (used as a conservative planning estimate, labelled as such).
    auto_defended = db.query(Dispute).filter(
        Dispute.merchant_id == m,
        Dispute.created_at >= since,
        Dispute.fsm_state.in_(["SUBMITTED", "WON", "LOST"]),
    ).count()

    win_rate = (won / contested * 100) if contested else 0.0

    return {
        "window_days":   days,
        "total":         total,
        "contested":     contested,
        "accepted":      accepted,
        "pending_review": pending_review,
        "won":           won,
        "lost":          lost,
        "win_rate_pct":  round(win_rate, 1),
        "revenue_recovered_rs": round(revenue_paise / 100, 2),
        "auto_defended": auto_defended,
        "time_saved_hours_est": auto_defended * 4,
        "unit": "rs",
        "merchant_id": m,
    }


@router.get("/metrics/false-positive-cost")
def false_positive_cost(days: int = 30, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    False-positive cost (this merchant only): disputes we contested but LOST.
    Shown prominently on the dashboard — the honest cost of over-filing.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)
    fps = db.query(Dispute).filter(
        Dispute.merchant_id == current.merchant_id,
        Dispute.created_at >= since,
        Dispute.system_decision == "CONTEST",
        Dispute.actual_outcome == "LOST",
    ).all()

    fp_paise = sum(d.amount for d in fps)
    return {
        "window_days":         days,
        "false_positive_count": len(fps),
        "false_positive_cost_rs": round(fp_paise / 100, 2),
        "avg_fp_cost_rs":       round((fp_paise / len(fps) / 100), 2) if fps else 0.0,
        "merchant_id":          current.merchant_id,
        "cases": [
            {
                "id": f.razorpay_dispute_id,
                "amount_rs": f.amount / 100,
                "reason_code": f.reason_code,
                "fight_confidence": f.fight_confidence,
            }
            for f in fps
        ],
    }
