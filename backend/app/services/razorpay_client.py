"""
services/razorpay_client.py
───────────────────────────
Razorpay Disputes API client — mock-first, defense-only.

Works without real keys:
  - If USE_MOCK_APIS=True or keys are placeholder -> all calls return mock dicts
  - No real network calls during demo / tests
  - Defense-only: only contest() and accept() (gated), no escalation/contact-customer

When real rzp_test_ keys are configured and USE_MOCK_APIS=False, wraps razorpay SDK.
"""

import hashlib
import hmac
import logging
from datetime import datetime, timezone
from pathlib import Path

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_mock_mode() -> bool:
    """True if we should mock Razorpay calls (no real keys or mock flag)."""
    if settings.use_mock_apis:
        return True
    if not settings.razorpay_key_id or settings.razorpay_key_id == "rzp_test_placeholder":
        return True
    if not settings.razorpay_key_secret or settings.razorpay_key_secret == "placeholder":
        return True
    return False


def _mock_response(action: str, dispute_id: str, extra: dict | None = None) -> dict:
    base = {
        "status": f"mock_{action}",
        "mock": True,
        "dispute_id": dispute_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "note": "Mock mode — no real Razorpay API call (no keys / USE_MOCK_APIS=True)",
    }
    if extra:
        base.update(extra)
    return base


class RazorpayDisputeClient:
    """
    Defense-only client. Capabilities:
      - contest (submit evidence) — defense
      - accept (merchant approved only) — defense (consumer wins)
      - fetch dispute/payment — read-only
    No outbound customer contact, no counter-claims, no auto-escalation.
    """

    def __init__(self):
        self.is_mock = _is_mock_mode()
        self.client = None
        if not self.is_mock:
            try:
                import razorpay
                self.client = razorpay.Client(
                    auth=(settings.razorpay_key_id, settings.razorpay_key_secret)
                )
                logger.info("Razorpay client initialized (live mode)")
            except Exception as exc:
                logger.warning("Razorpay SDK init failed (%s) — falling back to mock", exc)
                self.is_mock = True

    # ── Read ────────────────────────────────────────────────────────────────

    async def get_dispute(self, dispute_id: str) -> dict:
        """Fetch dispute details. Mock if no keys."""
        if self.is_mock:
            return _mock_response("fetch_dispute", dispute_id, {"phase": "chargeback"})
        try:
            # razorpay SDK is sync — run as sync call
            return self.client.dispute.fetch(dispute_id)
        except Exception as exc:
            logger.error("get_dispute failed: %s", exc)
            return _mock_response("fetch_dispute_error", dispute_id, {"error": str(exc)})

    async def get_payment(self, payment_id: str) -> dict:
        """Fetch payment metadata for security executor."""
        if self.is_mock:
            return _mock_response("fetch_payment", payment_id, {"payment_id": payment_id})
        try:
            return self.client.payment.fetch(payment_id)
        except Exception as exc:
            logger.error("get_payment failed: %s", exc)
            return _mock_response("fetch_payment_error", payment_id, {"error": str(exc)})

    # ── Defense actions ────────────────────────────────────────────────────

    def _build_evidence_payload(self, evidence: dict, pdf_path: str | None = None) -> dict:
        """Map internal evidence_packet to Razorpay API evidence schema."""
        payload: dict = {"action": "contest"}

        logistics = evidence.get("logistics", {})
        if logistics.get("status") == "DELIVERED":
            # Razorpay expects shipping/delivery proof keys
            if logistics.get("tracking_id"):
                payload["shipping_proof"] = logistics.get("tracking_id")
            if logistics.get("provider"):
                payload["shipping_provider"] = logistics.get("provider")
            payload["delivery_proof"] = "delivered"
            if logistics.get("recipient_name"):
                payload["recipient_name"] = logistics.get("recipient_name")

        security = evidence.get("security", {})
        if security.get("three_ds_passed") is True:
            payload["payment_proof"] = "3ds_authenticated"
            if security.get("three_ds_reference"):
                payload["three_ds_reference"] = security.get("three_ds_reference")
        if security.get("cvv_match") is True:
            payload["cvv_verified"] = True
        if security.get("avs_result") == "Y":
            payload["avs_verified"] = True
        if security.get("checkout_ip"):
            payload["checkout_ip"] = security.get("checkout_ip")

        crm = evidence.get("crm", {})
        if crm.get("customer_order_count") is not None:
            payload["customer_order_count"] = crm.get("customer_order_count")
        if crm.get("prior_disputes") is not None:
            payload["prior_disputes"] = crm.get("prior_disputes")

        if pdf_path:
            # Store relative path; actual upload handled separately
            payload["rebuttal_pdf"] = str(Path(pdf_path).name)

        return payload

    async def submit_contest(self, dispute_id: str, evidence: dict, pdf_path: str | None = None) -> dict:
        """
        Submit evidence to contest a dispute. Defense-only.
        Only called after Evaluator says CONTEST.
        In mock mode returns deterministic mock success.
        """
        payload = self._build_evidence_payload(evidence, pdf_path)

        if self.is_mock:
            logger.info("Mock submit_contest | dispute_id=%s | evidence_keys=%s", dispute_id, list(evidence.keys()))
            return _mock_response(
                "contest_submitted",
                dispute_id,
                {
                    "evidence_payload": payload,
                    "pdf_path": pdf_path,
                    "evidence_keys": list(evidence.keys()),
                },
            )

        try:
            # Real SDK call — sync
            result = self.client.dispute.contest(dispute_id, payload)
            logger.info("Razorpay contest submitted | dispute_id=%s", dispute_id)
            return {"status": "submitted", "mock": False, "dispute_id": dispute_id, "razorpay_response": result}
        except Exception as exc:
            logger.error("submit_contest failed: %s", exc)
            # Fallback to mock on failure so demo doesn't break
            return _mock_response("contest_error_fallback_mock", dispute_id, {"error": str(exc), "evidence_payload": payload})

    async def accept_dispute(self, dispute_id: str, merchant_approved: bool = False) -> dict:
        """
        Accept a dispute (consumer wins). GATED — requires explicit merchant approval.
        Never called autonomously by AI agents (enforced via flag).
        Defense-only: accepting = consumer wins, no offense.
        """
        if not merchant_approved:
            logger.warning("accept_dispute blocked — merchant_approved=False | dispute_id=%s", dispute_id)
            return {
                "status": "blocked",
                "mock": self.is_mock,
                "dispute_id": dispute_id,
                "reason": "merchant_approved flag required — AI cannot autonomously accept disputes",
            }

        if self.is_mock:
            return _mock_response("accepted", dispute_id, {"merchant_approved": True})

        try:
            result = self.client.dispute.accept(dispute_id)
            return {"status": "accepted", "mock": False, "dispute_id": dispute_id, "razorpay_response": result}
        except Exception as exc:
            logger.error("accept_dispute failed: %s", exc)
            return _mock_response("accept_error", dispute_id, {"error": str(exc)})

    # ── Webhook verification ────────────────────────────────────────────────

    @staticmethod
    def verify_webhook_signature(body: bytes, signature: str) -> bool:
        """HMAC-SHA256 verification (same as webhooks.py). Mock mode skips if placeholder."""
        if not settings.razorpay_webhook_secret or settings.razorpay_webhook_secret == "placeholder":
            logger.warning("Webhook signature check skipped (no secret — mock mode)")
            return True
        expected = hmac.new(
            settings.razorpay_webhook_secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)
