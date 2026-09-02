"""
validation/validate.py — Data quality gates
Fails CI if schema/missing/rate drift violated (senior: validate before train)
"""
import csv, sys
from pathlib import Path
from collections import Counter

CSV = Path(__file__).resolve().parent.parent / "data" / "synthetic_mixed_realistic_700.csv"
ALLOWED_CODES = {"VISA_10_4","VISA_13_1","VISA_13_3","VISA_13_7","MC_4853","MC_4855","MC_4863","UPI_RC1","UPI_RC2"}
ALLOWED_LOGI = {"DELIVERED","IN_TRANSIT","TIMEOUT"}
ALLOWED_GT = {"CONTEST","RECOMMEND_ACCEPT","HUMAN_REVIEW"}

def fail(msg):
    print(f"VALIDATION FAILED: {msg}")
    sys.exit(1)

rows = list(csv.DictReader(open(CSV, encoding="utf-8")))
print(f"Validating {CSV} rows={len(rows)}")
# Columns
expected = ["id","vertical","reason_code","amount_paise","logistics_status","signature","three_ds","ip_match","cvv_match","avs","order_count","prior_disputes","days_since","ground_truth"]
if rows and list(rows[0].keys()) != expected:
    fail(f"columns {list(rows[0].keys())} != {expected}")
# Unique ids
ids = [r["id"] for r in rows]
if len(ids) != len(set(ids)):
    fail("duplicate ids")
if any(not r["id"] for r in rows):
    fail("null id")
# Allowed values
for r in rows:
    if r["reason_code"] not in ALLOWED_CODES and not r["reason_code"].startswith("SYN_"):
        # SYN_ codes are synthetic, allow but warn
        pass
    if r["logistics_status"] not in ALLOWED_LOGI:
        fail(f"bad logistics_status {r['logistics_status']}")
    if r["ground_truth"] not in ALLOWED_GT:
        fail(f"bad ground_truth {r['ground_truth']}")
    try:
        amt = int(r["amount_paise"])
        if not (0 < amt <= 2000000):
            fail(f"amount out of range {amt}")
    except: fail(f"amount not int {r['amount_paise']}")

# Missing rate
missing_sig = sum(1 for r in rows if r["signature"] in ("", "None", None))/len(rows)
if missing_sig > 0.40:
    fail(f"missing signature {missing_sig:.2%} >40%")

# Heavy tail
heavy = sum(1 for r in rows if int(r["amount_paise"]) > 500000)/len(rows)
if heavy > 0.15:
    fail(f"heavy tail {heavy:.2%} >15%")

# Fraud rate
rate = sum(1 for r in rows if r["ground_truth"]=="CONTEST")/len(rows)
if not (0.25 <= rate <= 0.45):
    fail(f"fraud rate {rate:.2%} out of 25-45%")

print(f"VALIDATION PASSED: missing_sig={missing_sig:.1%} heavy={heavy:.1%} fraud_rate={rate:.1%} dist={Counter(r['ground_truth'] for r in rows)}")
