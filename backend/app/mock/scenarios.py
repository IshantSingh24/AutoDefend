"""
mock/scenarios.py
─────────────────
Simulated API responses for the 4 demo scenarios (dev set)
and the 20 labeled disputes held-out for ML evaluation.

Usage:
    from app.mock.scenarios import get_mock_response, HELD_OUT_TEST_SET

IMPORTANT: HELD_OUT_TEST_SET labels were set BEFORE any agent development.
           Do not use these cases to tune agent logic.
"""

from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# HELPER
# ─────────────────────────────────────────────────────────────────────────────

def get_mock_response(payment_id: str, executor: str) -> dict:
    """
    Return a mock API response for a given payment_id and executor type.
    Falls back to a generic 'DELIVERED' response if payment_id not found.

    executor: 'logistics' | 'security' | 'crm'
    """
    scenario = _SCENARIO_REGISTRY.get(payment_id)
    if scenario is None:
        return _DEFAULT_RESPONSES[executor]
    return scenario.get(executor, _DEFAULT_RESPONSES[executor])


# ─────────────────────────────────────────────────────────────────────────────
# DEV SCENARIOS (4 core demo cases)
# ─────────────────────────────────────────────────────────────────────────────

_SCENARIO_REGISTRY = {

    # ── Scenario A: Strong evidence → should CONTEST and WIN ─────────────────
    "PAY_FIGHT_WIN": {
        "meta": {
            "reason_code":   "VISA_10_4",
            "amount_paise":  850_00,       # Rs.850
            "phase":         "CHARGEBACK",
            "merchant_id":   "merchant_demo_001",
            "ground_truth":  "CONTEST",
            "expected_win":  True,
            "description":   "Delivered, 3DS passed, IP match — friendly fraud pattern",
        },
        "logistics": {
            "status":              "DELIVERED",
            "delivery_date":       "2026-08-20",
            "delivery_time":       "14:32 IST",
            "provider":            "Delhivery",
            "tracking_id":         "DL1234567890",
            "recipient_name":      "K. Sharma",
            "signature_available": True,
            "evidence_strength":   "STRONG",
        },
        "security": {
            "checkout_ip":          "103.21.58.12",
            "billing_address_match": True,
            "three_ds_passed":      True,
            "three_ds_reference":   "3DS_REF_ABCD1234",
            "cvv_match":            True,
            "avs_result":           "Y",
            "device_fingerprint":   "fp_abc123def456",
            "evidence_strength":    "STRONG",
        },
        "crm": {
            "customer_order_count":        5,
            "customer_avg_order_paise":    72_000,
            "prior_disputes":              0,
            "prior_dispute_outcomes":      [],
            "customer_since_days":         420,
            "delivery_success_rate":       1.0,
            "evidence_strength":           "STRONG",
        },
    },

    # ── Scenario B: Item in transit → RECOMMEND_ACCEPT (SR_001) ──────────────
    "PAY_HALT_TRANSIT": {
        "meta": {
            "reason_code":   "VISA_13_1",
            "amount_paise":  234_000,      # Rs.2,340
            "phase":         "CHARGEBACK",
            "merchant_id":   "merchant_demo_002",
            "ground_truth":  "RECOMMEND_ACCEPT",
            "expected_win":  False,
            "description":   "Package still in transit — filing would fail evidence check",
        },
        "logistics": {
            "status":              "IN_TRANSIT",
            "estimated_delivery":  "2026-08-30",
            "provider":            "Blue Dart",
            "tracking_id":         "BD9876543210",
            "recipient_name":      None,
            "signature_available": False,
            "evidence_strength":   "MISSING",
        },
        "security": {
            "checkout_ip":          "49.36.100.45",
            "billing_address_match": True,
            "three_ds_passed":      True,
            "three_ds_reference":   "3DS_REF_WXYZ5678",
            "cvv_match":            True,
            "avs_result":           "Y",
            "device_fingerprint":   "fp_xyz789abc012",
            "evidence_strength":    "STRONG",
        },
        "crm": {
            "customer_order_count":        2,
            "customer_avg_order_paise":    200_000,
            "prior_disputes":              0,
            "prior_dispute_outcomes":      [],
            "customer_since_days":         90,
            "delivery_success_rate":       1.0,
            "evidence_strength":           "MODERATE",
        },
    },

    # ── Scenario C: Logistics API timeout → HUMAN_REVIEW (SR_002) ────────────
    "PAY_API_TIMEOUT": {
        "meta": {
            "reason_code":   "MC_4855",
            "amount_paise":  450_000,      # Rs.4,500
            "phase":         "CHARGEBACK",
            "merchant_id":   "merchant_demo_003",
            "ground_truth":  "HUMAN_REVIEW",
            "expected_win":  None,         # Unknown — evidence unavailable
            "description":   "Logistics API returns 500 after 2 retries — route to human",
        },
        "logistics": {
            "status":            "TIMEOUT",
            "error":             "503 Service Unavailable after 2 retries",
            "provider":          "Shiprocket",
            "tracking_id":       "SR0011223344",
            "evidence_strength": "MISSING",
        },
        "security": {
            "checkout_ip":          "122.160.45.78",
            "billing_address_match": True,
            "three_ds_passed":      False,
            "three_ds_reference":   None,
            "cvv_match":            True,
            "avs_result":           "U",
            "device_fingerprint":   "fp_timeout_case",
            "evidence_strength":    "WEAK",
        },
        "crm": {
            "customer_order_count":        1,
            "customer_avg_order_paise":    450_000,
            "prior_disputes":              0,
            "prior_dispute_outcomes":      [],
            "customer_since_days":         15,
            "delivery_success_rate":       0.0,
            "evidence_strength":           "WEAK",
        },
    },

    # ── Scenario D: Low confidence → RECOMMEND_ACCEPT (below threshold) ───────
    "PAY_WEAK_EVIDENCE": {
        "meta": {
            "reason_code":   "MC_4853",
            "amount_paise":  320_000,      # Rs.3,200
            "phase":         "CHARGEBACK",
            "merchant_id":   "merchant_demo_004",
            "ground_truth":  "RECOMMEND_ACCEPT",
            "expected_win":  False,
            "description":   "Delivered but no signature, no 3DS, first-time customer — confidence ~0.45",
        },
        "logistics": {
            "status":              "DELIVERED",
            "delivery_date":       "2026-08-18",
            "provider":            "FedEx",
            "tracking_id":         "FX5544332211",
            "recipient_name":      None,           # no signature captured
            "signature_available": False,
            "evidence_strength":   "MODERATE",
        },
        "security": {
            "checkout_ip":          "27.97.212.33",
            "billing_address_match": False,        # IP doesn't match billing region
            "three_ds_passed":      False,         # 3DS not used
            "three_ds_reference":   None,
            "cvv_match":            True,
            "avs_result":           "N",
            "device_fingerprint":   "fp_new_device",
            "evidence_strength":    "WEAK",
        },
        "crm": {
            "customer_order_count":        1,      # first-time buyer
            "customer_avg_order_paise":    320_000,
            "prior_disputes":              0,
            "prior_dispute_outcomes":      [],
            "customer_since_days":         3,
            "delivery_success_rate":       0.0,
            "evidence_strength":           "WEAK",
        },
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# DEFAULT FALLBACK RESPONSES
# ─────────────────────────────────────────────────────────────────────────────

_DEFAULT_RESPONSES = {
    "logistics": {
        "status": "DELIVERED",
        "delivery_date": "2026-08-19",
        "provider": "Delhivery",
        "tracking_id": "DL_DEFAULT_001",
        "recipient_name": "Customer",
        "signature_available": True,
        "evidence_strength": "STRONG",
    },
    "security": {
        "checkout_ip": "103.0.0.1",
        "billing_address_match": True,
        "three_ds_passed": True,
        "three_ds_reference": "3DS_DEFAULT_001",
        "cvv_match": True,
        "avs_result": "Y",
        "device_fingerprint": "fp_default",
        "evidence_strength": "STRONG",
    },
    "crm": {
        "customer_order_count": 3,
        "customer_avg_order_paise": 50_000,
        "prior_disputes": 0,
        "prior_dispute_outcomes": [],
        "customer_since_days": 180,
        "delivery_success_rate": 1.0,
        "evidence_strength": "MODERATE",
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# HELD-OUT TEST SET (20 labeled disputes)
# Labels set BEFORE any agent development — for honest ML evaluation only.
# DO NOT reference these during classifier/evaluator logic development.
# ─────────────────────────────────────────────────────────────────────────────

HELD_OUT_TEST_SET = [

    # ── 8 x CONTEST cases (strong evidence, system should fight) ─────────────
    {
        "id": "HO_001", "reason_code": "VISA_10_4", "amount_paise": 250_000,
        "logistics": {"status": "DELIVERED", "signature_available": True},
        "security": {"three_ds_passed": True, "ip_match": True, "cvv_match": True},
        "crm": {"order_count": 5, "prior_disputes": 0},
        "ground_truth": "CONTEST", "expected_win": True,
    },
    {
        "id": "HO_002", "reason_code": "VISA_10_4", "amount_paise": 180_000,
        "logistics": {"status": "DELIVERED", "signature_available": True},
        "security": {"three_ds_passed": True, "ip_match": True, "cvv_match": True},
        "crm": {"order_count": 12, "prior_disputes": 0},
        "ground_truth": "CONTEST", "expected_win": True,
    },
    {
        "id": "HO_003", "reason_code": "MC_4863", "amount_paise": 95_000,
        "logistics": {"status": "DELIVERED", "signature_available": False},
        "security": {"three_ds_passed": True, "ip_match": True, "cvv_match": True},
        "crm": {"order_count": 8, "prior_disputes": 0},
        "ground_truth": "CONTEST", "expected_win": True,
    },
    {
        "id": "HO_004", "reason_code": "VISA_13_1", "amount_paise": 340_000,
        "logistics": {"status": "DELIVERED", "signature_available": True},
        "security": {"three_ds_passed": False, "ip_match": True, "cvv_match": True},
        "crm": {"order_count": 3, "prior_disputes": 0},
        "ground_truth": "CONTEST", "expected_win": True,
    },
    {
        "id": "HO_005", "reason_code": "MC_4853", "amount_paise": 120_000,
        "logistics": {"status": "DELIVERED", "signature_available": True},
        "security": {"three_ds_passed": True, "ip_match": True, "cvv_match": True},
        "crm": {"order_count": 7, "prior_disputes": 0},
        "ground_truth": "CONTEST", "expected_win": True,
    },
    {
        "id": "HO_006", "reason_code": "VISA_10_4", "amount_paise": 78_000,
        "logistics": {"status": "DELIVERED", "signature_available": True},
        "security": {"three_ds_passed": True, "ip_match": False, "cvv_match": True},
        "crm": {"order_count": 9, "prior_disputes": 0},
        "ground_truth": "CONTEST", "expected_win": True,
    },
    {
        "id": "HO_007", "reason_code": "MC_4855", "amount_paise": 210_000,
        "logistics": {"status": "DELIVERED", "signature_available": True},
        "security": {"three_ds_passed": True, "ip_match": True, "cvv_match": False},
        "crm": {"order_count": 4, "prior_disputes": 0},
        "ground_truth": "CONTEST", "expected_win": True,
    },
    {
        "id": "HO_008", "reason_code": "VISA_13_3", "amount_paise": 155_000,
        "logistics": {"status": "DELIVERED", "signature_available": True},
        "security": {"three_ds_passed": True, "ip_match": True, "cvv_match": True},
        "crm": {"order_count": 6, "prior_disputes": 0},
        "ground_truth": "CONTEST", "expected_win": True,
    },

    # ── 6 x RECOMMEND_ACCEPT cases ────────────────────────────────────────────
    {
        "id": "HO_009", "reason_code": "VISA_13_1", "amount_paise": 180_000,
        "logistics": {"status": "IN_TRANSIT"},   # SR_001 triggers
        "security": {"three_ds_passed": True, "ip_match": True, "cvv_match": True},
        "crm": {"order_count": 2, "prior_disputes": 0},
        "ground_truth": "RECOMMEND_ACCEPT", "expected_win": False,
    },
    {
        "id": "HO_010", "reason_code": "VISA_13_1", "amount_paise": 95_000,
        "logistics": {"status": "IN_TRANSIT"},   # SR_001 triggers
        "security": {"three_ds_passed": False, "ip_match": False, "cvv_match": True},
        "crm": {"order_count": 1, "prior_disputes": 0},
        "ground_truth": "RECOMMEND_ACCEPT", "expected_win": False,
    },
    {
        "id": "HO_011", "reason_code": "MC_4853", "amount_paise": 320_000,
        "logistics": {"status": "DELIVERED", "signature_available": False},
        "security": {"three_ds_passed": False, "ip_match": False, "cvv_match": True},
        "crm": {"order_count": 1, "prior_disputes": 0},
        "ground_truth": "RECOMMEND_ACCEPT", "expected_win": False,  # confidence ~0.45
    },
    {
        "id": "HO_012", "reason_code": "MC_4855", "amount_paise": 60_000,
        "logistics": {"status": "DELIVERED", "signature_available": False},
        "security": {"three_ds_passed": False, "ip_match": False, "cvv_match": False},
        "crm": {"order_count": 1, "prior_disputes": 1},
        "ground_truth": "RECOMMEND_ACCEPT", "expected_win": False,  # confidence ~0.35
    },
    {
        "id": "HO_013", "reason_code": "VISA_13_7", "amount_paise": 140_000,
        "logistics": {"status": "DELIVERED", "signature_available": False},
        "security": {"three_ds_passed": False, "ip_match": False, "cvv_match": True},
        "crm": {"order_count": 2, "prior_disputes": 0},
        "ground_truth": "RECOMMEND_ACCEPT", "expected_win": False,
    },
    {
        "id": "HO_014", "reason_code": "VISA_10_4", "amount_paise": 500_000,
        "logistics": {"status": "DELIVERED", "signature_available": False},
        "security": {"three_ds_passed": False, "ip_match": False, "cvv_match": False},
        "crm": {"order_count": 1, "prior_disputes": 0},
        "ground_truth": "RECOMMEND_ACCEPT", "expected_win": False,  # confidence ~0.35
    },

    # ── 4 x HUMAN_REVIEW cases (API timeouts) ─────────────────────────────────
    {
        "id": "HO_015", "reason_code": "MC_4855", "amount_paise": 450_000,
        "logistics": {"status": "TIMEOUT"},   # SR_002 triggers
        "security": {"three_ds_passed": False, "ip_match": True, "cvv_match": True},
        "crm": {"order_count": 1, "prior_disputes": 0},
        "ground_truth": "HUMAN_REVIEW", "expected_win": None,
    },
    {
        "id": "HO_016", "reason_code": "VISA_13_1", "amount_paise": 280_000,
        "logistics": {"status": "TIMEOUT"},   # SR_002 triggers
        "security": {"three_ds_passed": True, "ip_match": True, "cvv_match": True},
        "crm": {"order_count": 4, "prior_disputes": 0},
        "ground_truth": "HUMAN_REVIEW", "expected_win": None,
    },
    {
        "id": "HO_017", "reason_code": "MC_4853", "amount_paise": 190_000,
        "logistics": {"status": "TIMEOUT"},   # SR_002 triggers
        "security": {"three_ds_passed": True, "ip_match": True, "cvv_match": True},
        "crm": {"order_count": 3, "prior_disputes": 0},
        "ground_truth": "HUMAN_REVIEW", "expected_win": None,
    },
    {
        "id": "HO_018", "reason_code": "VISA_10_4", "amount_paise": 375_000,
        "logistics": {"status": "TIMEOUT"},   # SR_002 triggers
        "security": {"three_ds_passed": True, "ip_match": True, "cvv_match": True},
        "crm": {"order_count": 6, "prior_disputes": 0},
        "ground_truth": "HUMAN_REVIEW", "expected_win": None,
    },

    # ── 2 x BORDERLINE cases (confidence 0.50–0.70, threshold sensitivity) ───
    {
        "id": "HO_019", "reason_code": "MC_4853", "amount_paise": 320_000,
        "logistics": {"status": "DELIVERED", "signature_available": False},
        "security": {"three_ds_passed": False, "ip_match": False, "cvv_match": True},
        "crm": {"order_count": 2, "prior_disputes": 0},
        "ground_truth": "RECOMMEND_ACCEPT",   # confidence ~0.55 — just below 0.70 threshold
        "expected_win": False,
        "note": "Borderline: delivery + CVV only. Should flip to CONTEST if threshold lowered to 0.50",
    },
    {
        "id": "HO_020", "reason_code": "VISA_10_4", "amount_paise": 115_000,
        "logistics": {"status": "DELIVERED", "signature_available": True},
        "security": {"three_ds_passed": True, "ip_match": False, "cvv_match": False},
        "crm": {"order_count": 2, "prior_disputes": 0},
        "ground_truth": "CONTEST",            # confidence ~0.72 — just above threshold
        "expected_win": True,
        "note": "Borderline: delivery + 3DS but no IP/CVV match. Should flip to ACCEPT if threshold raised to 0.75",
    },
]
