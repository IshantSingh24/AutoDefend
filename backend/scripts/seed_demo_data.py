"""
scripts/seed_demo_data.py
─────────────────────────
Seeds realistic demo data so the dashboard has something meaningful to show:

Users (multi-tenant demo):
  akhil@merchanta.com   / password   → merchant_a  (6 disputes: 4 WON + 2 FP)
  priya@merchantb.com   / password   → merchant_b  (3 disputes: 2 RECOMMEND_ACCEPT + 1 HUMAN_REVIEW)

Each dispute gets a hash-chained audit trail (Classification + Evaluation).
Disputes are scoped per merchant so logging in as each user shows a different,
isolated dashboard — proving multi-tenancy in the walkthrough.

Idempotent: wipes prior seed_* disputes and the two demo users before re-seeding.

Usage:  uv run python scripts/seed_demo_data.py
"""

import logging
from datetime import datetime, timedelta, timezone

from app.db.connection import SessionLocal
from app.db.models import Dispute, User
from app.services.audit_logger import audit_logger
from app.services.security import hash_password

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("seed")

DEMO_USERS = [
    {"email": "akhil@merchanta.com", "password": "password", "full_name": "Akhil Sharma", "merchant_id": "merchant_a"},
    {"email": "priya@merchantb.com", "password": "password", "full_name": "Priya Menon", "merchant_id": "merchant_b"},
]

# (pid, merchant, reason, paise, decision, outcome, days_ago, fight_conf)
DISPUTES = [
    # merchant_a → strong win record + the two false positives
    ("w01", "merchant_a", "VISA_10_4", 1240000, "CONTEST", "WON", 12, 0.94),
    ("w02", "merchant_a", "VISA_13_1", 450000, "CONTEST", "WON", 9, 0.91),
    ("w03", "merchant_a", "MC_4853", 2200000, "CONTEST", "WON", 6, 0.88),
    ("w04", "merchant_a", "VISA_13_3", 780000, "CONTEST", "WON", 3, 0.90),
    ("fp01", "merchant_a", "VISA_10_4", 3100000, "CONTEST", "LOST", 14, 0.82),
    ("fp02", "merchant_a", "MC_4855", 950000, "CONTEST", "LOST", 8, 0.78),
    # merchant_b → smaller portfolio, incl. a human-review case
    ("a01", "merchant_b", "VISA_13_1", 300000, "RECOMMEND_ACCEPT", None, 5, None),
    ("a02", "merchant_b", "MC_4853", 520000, "RECOMMEND_ACCEPT", None, 2, None),
    ("r01", "merchant_b", "MC_4855", 4600000, "HUMAN_REVIEW", None, 1, 0.62),
]


def seed_dispute(db, pid, merchant, reason, paise, decision, outcome, days_ago, fight_conf):
    now = datetime.now(timezone.utc)
    created = now - timedelta(days=days_ago)
    state = (
        "SUBMITTED" if decision == "CONTEST"
        else "ACCEPTED" if decision == "RECOMMEND_ACCEPT"
        else "HUMAN_REVIEW"
    )
    d = Dispute(
        id=f"seed_{pid}",
        razorpay_dispute_id=f"disp_seed_{pid}",
        payment_id=f"seed_{pid}",
        merchant_id=merchant,
        reason_code=reason,
        amount=paise,
        phase="CHARGEBACK",
        fsm_state=state,
        dispute_class="fraud",
        initial_confidence=0.80,
        fight_confidence=fight_conf if fight_conf else (0.90 if decision == "CONTEST" else 0.55),
        system_decision=decision,
        actual_outcome=outcome,
        created_at=created,
        updated_at=created,
    )
    db.add(d)
    db.commit()
    audit_logger.log_event(d.id, "CLASSIFICATION", "ClassifierAgent",
                           {"dispute_class": "fraud", "confidence": 0.80}, db=db)
    audit_logger.log_event(d.id, "EVALUATION", "EvaluatorAgent",
                           {"decision": decision, "confidence": d.fight_confidence}, db=db)


def main():
    db = SessionLocal()
    try:
        # 1. Clean previous demo rows (disputes first, then users)
        for d in db.query(Dispute).filter(Dispute.payment_id.like("seed_%")).all():
            db.delete(d)
        db.commit()
        for u in db.query(User).filter(User.email.in_([u["email"] for u in DEMO_USERS])).all():
            db.delete(u)
        db.commit()

        # 2. Seed demo users
        for u in DEMO_USERS:
            db.add(User(
                email=u["email"],
                password_hash=hash_password(u["password"]),
                full_name=u["full_name"],
                merchant_id=u["merchant_id"],
            ))
        db.commit()
        print(f"Seeded {len(DEMO_USERS)} demo users.")

        # 3. Seed disputes
        for row in DISPUTES:
            seed_dispute(db, *row)
        print(f"Seeded {len(DISPUTES)} demo disputes across "
              f"{sorted({r[1] for r in DISPUTES})} merchants.")

        print("Login as akhil@merchanta.com / password  or  priya@merchantb.com / password")
    finally:
        db.close()


if __name__ == "__main__":
    main()