"""
realistic_base_40.py
────────────────────
40 hand-crafted realistic disputes — diverse verticals, amounts, networks,
mimicking how real merchants see disputes. This is the SEED dataset that
real companies bootstrap from when they have no historical labels.

Method: Domain-informed manual creation (how Chargeflow/Justt bootstrapped before having 1000s of outcomes).
Each case has ground_truth set BEFORE any ML training (defense-only, honest labels).
"""

# 40 cases — 16 CONTEST, 14 RECOMMEND_ACCEPT, 8 HUMAN_REVIEW, 2 BORDERLINE
# Verticals: fashion, electronics, travel, food, groceries, edtech, gaming, subscriptions, marketplace
REALISTIC_BASE_40 = [
    # ── CONTEST (merchant should fight — strong evidence) 16 cases ────────────
    {"id": "RB_01", "vertical": "fashion", "reason_code": "VISA_10_4", "amount_paise": 450000, "dispute_class": "fraud",
     "logistics": {"status": "DELIVERED", "signature_available": True}, "security": {"three_ds_passed": True, "ip_match": True, "cvv_match": True, "avs_match": "Y"}, "crm": {"order_count": 9, "prior_disputes": 0, "days_since": 540}, "ground_truth": "CONTEST"},
    {"id": "RB_02", "vertical": "electronics", "reason_code": "VISA_10_4", "amount_paise": 89900, "dispute_class": "fraud",
     "logistics": {"status": "DELIVERED", "signature_available": True}, "security": {"three_ds_passed": True, "ip_match": True, "cvv_match": True, "avs_match": "Y"}, "crm": {"order_count": 4, "prior_disputes": 0, "days_since": 120}, "ground_truth": "CONTEST"},
    {"id": "RB_03", "vertical": "travel", "reason_code": "MC_4863", "amount_paise": 1250000, "dispute_class": "fraud",
     "logistics": {"status": "DELIVERED", "signature_available": True}, "security": {"three_ds_passed": True, "ip_match": True, "cvv_match": True, "avs_match": "Y"}, "crm": {"order_count": 12, "prior_disputes": 0, "days_since": 900}, "ground_truth": "CONTEST"},
    {"id": "RB_04", "vertical": "edtech", "reason_code": "VISA_13_3", "amount_paise": 250000, "dispute_class": "service",
     "logistics": {"status": "DELIVERED", "signature_available": True}, "security": {"three_ds_passed": True, "ip_match": True, "cvv_match": True, "avs_match": "Y"}, "crm": {"order_count": 6, "prior_disputes": 0, "days_since": 300}, "ground_truth": "CONTEST"},
    {"id": "RB_05", "vertical": "groceries", "reason_code": "VISA_13_1", "amount_paise": 180000, "dispute_class": "non_receipt",
     "logistics": {"status": "DELIVERED", "signature_available": True}, "security": {"three_ds_passed": False, "ip_match": True, "cvv_match": True, "avs_match": "Y"}, "crm": {"order_count": 15, "prior_disputes": 0, "days_since": 400}, "ground_truth": "CONTEST"},
    {"id": "RB_06", "vertical": "marketplace", "reason_code": "MC_4853", "amount_paise": 320000, "dispute_class": "service",
     "logistics": {"status": "DELIVERED", "signature_available": True}, "security": {"three_ds_passed": True, "ip_match": True, "cvv_match": True, "avs_match": "Y"}, "crm": {"order_count": 7, "prior_disputes": 1, "days_since": 250}, "ground_truth": "CONTEST"},
    {"id": "RB_07", "vertical": "gaming", "reason_code": "UPI_RC1", "amount_paise": 50000, "dispute_class": "fraud",
     "logistics": {"status": "DELIVERED", "signature_available": False}, "security": {"three_ds_passed": True, "ip_match": True, "cvv_match": True, "avs_match": "Y"}, "crm": {"order_count": 20, "prior_disputes": 0, "days_since": 700}, "ground_truth": "CONTEST"},
    {"id": "RB_08", "vertical": "subscriptions", "reason_code": "VISA_13_7", "amount_paise": 99000, "dispute_class": "policy",
     "logistics": {"status": "DELIVERED", "signature_available": False}, "security": {"three_ds_passed": True, "ip_match": True, "cvv_match": True, "avs_match": "N"}, "crm": {"order_count": 11, "prior_disputes": 0, "days_since": 800}, "ground_truth": "CONTEST"},
    {"id": "RB_09", "vertical": "food", "reason_code": "MC_4855", "amount_paise": 75000, "dispute_class": "non_receipt",
     "logistics": {"status": "DELIVERED", "signature_available": True}, "security": {"three_ds_passed": True, "ip_match": True, "cvv_match": True, "avs_match": "Y"}, "crm": {"order_count": 25, "prior_disputes": 0, "days_since": 600}, "ground_truth": "CONTEST"},
    {"id": "RB_10", "vertical": "fashion", "reason_code": "VISA_10_4", "amount_paise": 199900, "dispute_class": "fraud",
     "logistics": {"status": "DELIVERED", "signature_available": True}, "security": {"three_ds_passed": True, "ip_match": False, "cvv_match": True, "avs_match": "Y"}, "crm": {"order_count": 10, "prior_disputes": 0, "days_since": 350}, "ground_truth": "CONTEST"},
    {"id": "RB_11", "vertical": "electronics", "reason_code": "MC_4863", "amount_paise": 650000, "dispute_class": "fraud",
     "logistics": {"status": "DELIVERED", "signature_available": True}, "security": {"three_ds_passed": True, "ip_match": True, "cvv_match": False, "avs_match": "Y"}, "crm": {"order_count": 5, "prior_disputes": 0, "days_since": 200}, "ground_truth": "CONTEST"},
    {"id": "RB_12", "vertical": "travel", "reason_code": "VISA_13_1", "amount_paise": 450000, "dispute_class": "non_receipt",
     "logistics": {"status": "DELIVERED", "signature_available": True}, "security": {"three_ds_passed": False, "ip_match": True, "cvv_match": True, "avs_match": "Y"}, "crm": {"order_count": 8, "prior_disputes": 0, "days_since": 500}, "ground_truth": "CONTEST"},
    {"id": "RB_13", "vertical": "marketplace", "reason_code": "UPI_RC2", "amount_paise": 120000, "dispute_class": "non_receipt",
     "logistics": {"status": "DELIVERED", "signature_available": True}, "security": {"three_ds_passed": False, "ip_match": True, "cvv_match": True, "avs_match": "Y"}, "crm": {"order_count": 4, "prior_disputes": 0, "days_since": 180}, "ground_truth": "CONTEST"},
    {"id": "RB_14", "vertical": "edtech", "reason_code": "VISA_10_4", "amount_paise": 150000, "dispute_class": "fraud",
     "logistics": {"status": "DELIVERED", "signature_available": False}, "security": {"three_ds_passed": True, "ip_match": True, "cvv_match": True, "avs_match": "Y"}, "crm": {"order_count": 6, "prior_disputes": 0, "days_since": 90}, "ground_truth": "CONTEST"},
    {"id": "RB_15", "vertical": "groceries", "reason_code": "MC_4853", "amount_paise": 85000, "dispute_class": "service",
     "logistics": {"status": "DELIVERED", "signature_available": True}, "security": {"three_ds_passed": True, "ip_match": True, "cvv_match": True, "avs_match": "Y"}, "crm": {"order_count": 18, "prior_disputes": 0, "days_since": 400}, "ground_truth": "CONTEST"},
    {"id": "RB_16", "vertical": "gaming", "reason_code": "VISA_13_3", "amount_paise": 300000, "dispute_class": "service",
     "logistics": {"status": "DELIVERED", "signature_available": True}, "security": {"three_ds_passed": False, "ip_match": True, "cvv_match": True, "avs_match": "Y"}, "crm": {"order_count": 7, "prior_disputes": 0, "days_since": 280}, "ground_truth": "CONTEST"},

    # ── RECOMMEND_ACCEPT (weak / in-transit / no evidence) 14 cases ──────────
    {"id": "RB_17", "vertical": "fashion", "reason_code": "VISA_13_1", "amount_paise": 200000, "dispute_class": "non_receipt",
     "logistics": {"status": "IN_TRANSIT", "signature_available": False}, "security": {"three_ds_passed": True, "ip_match": True, "cvv_match": True, "avs_match": "Y"}, "crm": {"order_count": 2, "prior_disputes": 0, "days_since": 60}, "ground_truth": "RECOMMEND_ACCEPT"},
    {"id": "RB_18", "vertical": "electronics", "reason_code": "MC_4855", "amount_paise": 80000, "dispute_class": "non_receipt",
     "logistics": {"status": "IN_TRANSIT", "signature_available": False}, "security": {"three_ds_passed": False, "ip_match": False, "cvv_match": True, "avs_match": "N"}, "crm": {"order_count": 1, "prior_disputes": 0, "days_since": 5}, "ground_truth": "RECOMMEND_ACCEPT"},
    {"id": "RB_19", "vertical": "food", "reason_code": "VISA_13_1", "amount_paise": 50000, "dispute_class": "non_receipt",
     "logistics": {"status": "IN_TRANSIT", "signature_available": False}, "security": {"three_ds_passed": False, "ip_match": False, "cvv_match": False, "avs_match": "N"}, "crm": {"order_count": 1, "prior_disputes": 1, "days_since": 10}, "ground_truth": "RECOMMEND_ACCEPT"},
    {"id": "RB_20", "vertical": "travel", "reason_code": "VISA_10_4", "amount_paise": 300000, "dispute_class": "fraud",
     "logistics": {"status": "DELIVERED", "signature_available": False}, "security": {"three_ds_passed": False, "ip_match": False, "cvv_match": False, "avs_match": "N"}, "crm": {"order_count": 1, "prior_disputes": 0, "days_since": 7}, "ground_truth": "RECOMMEND_ACCEPT"},
    {"id": "RB_21", "vertical": "marketplace", "reason_code": "MC_4853", "amount_paise": 400000, "dispute_class": "service",
     "logistics": {"status": "DELIVERED", "signature_available": False}, "security": {"three_ds_passed": False, "ip_match": False, "cvv_match": False, "avs_match": "N"}, "crm": {"order_count": 1, "prior_disputes": 2, "days_since": 20}, "ground_truth": "RECOMMEND_ACCEPT"},
    {"id": "RB_22", "vertical": "edtech", "reason_code": "VISA_13_7", "amount_paise": 120000, "dispute_class": "policy",
     "logistics": {"status": "DELIVERED", "signature_available": False}, "security": {"three_ds_passed": False, "ip_match": False, "cvv_match": True, "avs_match": "N"}, "crm": {"order_count": 1, "prior_disputes": 0, "days_since": 15}, "ground_truth": "RECOMMEND_ACCEPT"},
    {"id": "RB_23", "vertical": "groceries", "reason_code": "VISA_13_3", "amount_paise": 60000, "dispute_class": "service",
     "logistics": {"status": "DELIVERED", "signature_available": False}, "security": {"three_ds_passed": False, "ip_match": False, "cvv_match": False, "avs_match": "N"}, "crm": {"order_count": 2, "prior_disputes": 1, "days_since": 30}, "ground_truth": "RECOMMEND_ACCEPT"},
    {"id": "RB_24", "vertical": "gaming", "reason_code": "UPI_RC1", "amount_paise": 25000, "dispute_class": "fraud",
     "logistics": {"status": "DELIVERED", "signature_available": False}, "security": {"three_ds_passed": False, "ip_match": False, "cvv_match": False, "avs_match": "N"}, "crm": {"order_count": 1, "prior_disputes": 0, "days_since": 2}, "ground_truth": "RECOMMEND_ACCEPT"},
    {"id": "RB_25", "vertical": "subscriptions", "reason_code": "VISA_13_7", "amount_paise": 150000, "dispute_class": "policy",
     "logistics": {"status": "DELIVERED", "signature_available": False}, "security": {"three_ds_passed": False, "ip_match": True, "cvv_match": False, "avs_match": "N"}, "crm": {"order_count": 2, "prior_disputes": 0, "days_since": 40}, "ground_truth": "RECOMMEND_ACCEPT"},
    {"id": "RB_26", "vertical": "fashion", "reason_code": "MC_4855", "amount_paise": 95000, "dispute_class": "non_receipt",
     "logistics": {"status": "DELIVERED", "signature_available": False}, "security": {"three_ds_passed": False, "ip_match": False, "cvv_match": True, "avs_match": "N"}, "crm": {"order_count": 1, "prior_disputes": 0, "days_since": 8}, "ground_truth": "RECOMMEND_ACCEPT"},
    {"id": "RB_27", "vertical": "electronics", "reason_code": "VISA_13_1", "amount_paise": 180000, "dispute_class": "non_receipt",
     "logistics": {"status": "DELIVERED", "signature_available": False}, "security": {"three_ds_passed": False, "ip_match": False, "cvv_match": False, "avs_match": "N"}, "crm": {"order_count": 1, "prior_disputes": 0, "days_since": 12}, "ground_truth": "RECOMMEND_ACCEPT"},
    {"id": "RB_28", "vertical": "food", "reason_code": "MC_4863", "amount_paise": 40000, "dispute_class": "fraud",
     "logistics": {"status": "DELIVERED", "signature_available": False}, "security": {"three_ds_passed": False, "ip_match": False, "cvv_match": False, "avs_match": "N"}, "crm": {"order_count": 2, "prior_disputes": 1, "days_since": 25}, "ground_truth": "RECOMMEND_ACCEPT"},
    {"id": "RB_29", "vertical": "travel", "reason_code": "UPI_RC2", "amount_paise": 70000, "dispute_class": "non_receipt",
     "logistics": {"status": "IN_TRANSIT", "signature_available": False}, "security": {"three_ds_passed": False, "ip_match": False, "cvv_match": False, "avs_match": "N"}, "crm": {"order_count": 1, "prior_disputes": 0, "days_since": 15}, "ground_truth": "RECOMMEND_ACCEPT"},
    {"id": "RB_30", "vertical": "marketplace", "reason_code": "VISA_10_4", "amount_paise": 75000, "dispute_class": "fraud",
     "logistics": {"status": "DELIVERED", "signature_available": False}, "security": {"three_ds_passed": False, "ip_match": False, "cvv_match": True, "avs_match": "N"}, "crm": {"order_count": 1, "prior_disputes": 0, "days_since": 18}, "ground_truth": "RECOMMEND_ACCEPT"},

    # ── HUMAN_REVIEW (API failure / ambiguous) 8 cases ───────────────────────
    {"id": "RB_31", "vertical": "fashion", "reason_code": "MC_4855", "amount_paise": 450000, "dispute_class": "non_receipt",
     "logistics": {"status": "TIMEOUT", "signature_available": False}, "security": {"three_ds_passed": False, "ip_match": True, "cvv_match": True, "avs_match": "Y"}, "crm": {"order_count": 3, "prior_disputes": 0, "days_since": 100}, "ground_truth": "HUMAN_REVIEW"},
    {"id": "RB_32", "vertical": "electronics", "reason_code": "VISA_13_1", "amount_paise": 280000, "dispute_class": "non_receipt",
     "logistics": {"status": "TIMEOUT", "signature_available": False}, "security": {"three_ds_passed": True, "ip_match": True, "cvv_match": True, "avs_match": "Y"}, "crm": {"order_count": 4, "prior_disputes": 0, "days_since": 150}, "ground_truth": "HUMAN_REVIEW"},
    {"id": "RB_33", "vertical": "edtech", "reason_code": "MC_4853", "amount_paise": 190000, "dispute_class": "service",
     "logistics": {"status": "TIMEOUT", "signature_available": False}, "security": {"three_ds_passed": True, "ip_match": False, "cvv_match": True, "avs_match": "N"}, "crm": {"order_count": 2, "prior_disputes": 0, "days_since": 60}, "ground_truth": "HUMAN_REVIEW"},
    {"id": "RB_34", "vertical": "travel", "reason_code": "VISA_10_4", "amount_paise": 375000, "dispute_class": "fraud",
     "logistics": {"status": "TIMEOUT", "signature_available": False}, "security": {"three_ds_passed": True, "ip_match": True, "cvv_match": True, "avs_match": "Y"}, "crm": {"order_count": 6, "prior_disputes": 0, "days_since": 300}, "ground_truth": "HUMAN_REVIEW"},
    {"id": "RB_35", "vertical": "groceries", "reason_code": "UPI_RC1", "amount_paise": 90000, "dispute_class": "fraud",
     "logistics": {"status": "TIMEOUT", "signature_available": False}, "security": {"three_ds_passed": False, "ip_match": False, "cvv_match": True, "avs_match": "N"}, "crm": {"order_count": 1, "prior_disputes": 0, "days_since": 20}, "ground_truth": "HUMAN_REVIEW"},
    {"id": "RB_36", "vertical": "gaming", "reason_code": "VISA_13_3", "amount_paise": 220000, "dispute_class": "service",
     "logistics": {"status": "TIMEOUT", "signature_available": False}, "security": {"three_ds_passed": False, "ip_match": True, "cvv_match": False, "avs_match": "N"}, "crm": {"order_count": 3, "prior_disputes": 1, "days_since": 80}, "ground_truth": "HUMAN_REVIEW"},
    {"id": "RB_37", "vertical": "subscriptions", "reason_code": "VISA_13_7", "amount_paise": 150000, "dispute_class": "policy",
     "logistics": {"status": "TIMEOUT", "signature_available": False}, "security": {"three_ds_passed": False, "ip_match": False, "cvv_match": True, "avs_match": "N"}, "crm": {"order_count": 2, "prior_disputes": 0, "days_since": 50}, "ground_truth": "HUMAN_REVIEW"},
    {"id": "RB_38", "vertical": "food", "reason_code": "MC_4863", "amount_paise": 110000, "dispute_class": "fraud",
     "logistics": {"status": "TIMEOUT", "signature_available": False}, "security": {"three_ds_passed": False, "ip_match": True, "cvv_match": False, "avs_match": "N"}, "crm": {"order_count": 2, "prior_disputes": 0, "days_since": 30}, "ground_truth": "HUMAN_REVIEW"},

    # ── BORDERLINE (confidence 0.50-0.70) 2 cases ────────────────────────────
    {"id": "RB_39", "vertical": "fashion", "reason_code": "MC_4853", "amount_paise": 320000, "dispute_class": "service",
     "logistics": {"status": "DELIVERED", "signature_available": False}, "security": {"three_ds_passed": False, "ip_match": False, "cvv_match": True, "avs_match": "N"}, "crm": {"order_count": 3, "prior_disputes": 0, "days_since": 45}, "ground_truth": "RECOMMEND_ACCEPT"},
    {"id": "RB_40", "vertical": "electronics", "reason_code": "VISA_10_4", "amount_paise": 115000, "dispute_class": "fraud",
     "logistics": {"status": "DELIVERED", "signature_available": True}, "security": {"three_ds_passed": True, "ip_match": False, "cvv_match": False, "avs_match": "N"}, "crm": {"order_count": 2, "prior_disputes": 0, "days_since": 60}, "ground_truth": "CONTEST"},
]
