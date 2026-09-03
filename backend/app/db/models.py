import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey,
    Integer, String, Text, JSON,
)
from sqlalchemy.orm import relationship

from app.db.connection import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── Users / Multi-tenancy ─────────────────────────────────────────────────────

class User(Base):
    """
    A merchant user who logs into the dashboard.
    `merchant_id` scopes them to their own disputes — the core of multi-tenancy.
    """
    __tablename__ = "users"

    id           = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email        = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)   # bcrypt hash, never plaintext
    full_name    = Column(String(128))
    merchant_id  = Column(String(64), nullable=False, index=True)
    is_admin     = Column(Boolean, default=False)
    created_at   = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    def __repr__(self) -> str:
        return f"<User {self.email} | {self.merchant_id}>"


# ── Disputes ──────────────────────────────────────────────────────────────────

class Dispute(Base):
    """Core FSM state for each incoming chargeback."""
    __tablename__ = "disputes"

    id                  = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    razorpay_dispute_id = Column(String(64), unique=True, nullable=False, index=True)
    payment_id          = Column(String(64), nullable=False, index=True)
    merchant_id         = Column(String(64), nullable=False)
    reason_code         = Column(String(32), nullable=False)
    amount              = Column(Integer, nullable=False)   # paise
    phase               = Column(String(32), nullable=False)  # CHARGEBACK | PRE_ARB | ARBITRATION
    fsm_state           = Column(String(32), nullable=False, default="INGESTED")

    # Classification output
    dispute_class       = Column(String(32))               # fraud | non_receipt | service | policy
    initial_confidence  = Column(Float)

    # Evaluation output
    fight_confidence    = Column(Float)
    stopping_rule       = Column(String(16))               # SR_001 … SR_004
    system_decision     = Column(String(32))               # CONTEST | RECOMMEND_ACCEPT | HUMAN_REVIEW

    # Compiler output
    rebuttal_pdf_path   = Column(String(255))
    submitted_at        = Column(DateTime(timezone=True))

    # Actual outcome (filled after bank responds - used for ML metrics)
    actual_outcome      = Column(String(16))               # WON | LOST | ACCEPTED | PENDING

    created_at          = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at          = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    # Relationships
    audit_events        = relationship("AuditEvent",   back_populates="dispute", cascade="all, delete-orphan")
    evidence_items      = relationship("EvidenceItem", back_populates="dispute", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Dispute {self.razorpay_dispute_id} | {self.reason_code} | {self.fsm_state}>"


# ── Audit Events ──────────────────────────────────────────────────────────────

class AuditEvent(Base):
    """
    Immutable, hash-chained audit log.
    NEVER update or delete rows in this table.
    Each row links to the previous via previous_hash (SHA-256 chain).
    """
    __tablename__ = "audit_events"

    id             = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    dispute_id     = Column(String(36), ForeignKey("disputes.id"), nullable=False, index=True)
    stage          = Column(String(64), nullable=False)    # CLASSIFICATION | EVALUATION | etc.
    agent_name     = Column(String(128))
    event_data     = Column(JSON, nullable=False)          # full agent output snapshot
    previous_hash  = Column(String(64), nullable=False)    # SHA-256 of previous event ("GENESIS" for first)
    event_hash     = Column(String(64), nullable=False, unique=True)  # SHA-256 of this event
    created_at     = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    dispute        = relationship("Dispute", back_populates="audit_events")

    def __repr__(self) -> str:
        return f"<AuditEvent {self.stage} @ {self.created_at}>"


# ── Evidence Items ────────────────────────────────────────────────────────────

class EvidenceItem(Base):
    """Raw evidence collected by each executor agent."""
    __tablename__ = "evidence_items"

    id             = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    dispute_id     = Column(String(36), ForeignKey("disputes.id"), nullable=False, index=True)
    evidence_type  = Column(String(64), nullable=False)    # logistics | security | crm
    source_api     = Column(String(128))                   # delhivery | razorpay_payment | shopify
    raw_data       = Column(JSON, nullable=False)          # full API response
    strength       = Column(String(16), nullable=False)    # STRONG | MODERATE | WEAK | MISSING | TIMEOUT
    fetched_at     = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    dispute        = relationship("Dispute", back_populates="evidence_items")

    def __repr__(self) -> str:
        return f"<EvidenceItem {self.evidence_type} | {self.strength}>"
