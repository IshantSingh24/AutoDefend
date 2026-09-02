"""
train_with_mlflow.py
────────────────────
Senior ML: MLflow Tracking + Registry — not pickle.dump.
Logs params, metrics, artifacts, dataset fingerprint, git commit.
"""
import csv, json, hashlib, subprocess
from pathlib import Path
from collections import Counter
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.metrics import precision_score, recall_score, f1_score
from sklearn.linear_model import LogisticRegression
import lightgbm as lgb
import xgboost as xgb
import catboost as cb
from sklearn.ensemble import StackingClassifier

try:
    import mlflow
    import mlflow.sklearn
    HAS_MLFLOW = True
except ImportError:
    HAS_MLFLOW = False
    print("MLflow not installed — run with --no-mlflow for metrics only")

def dataset_fingerprint(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()[:12]

def git_commit() -> str:
    try:
        return subprocess.check_output(["git","rev-parse","--short","HEAD"], text=True).strip()
    except: return "no-git"

csv_path = Path(__file__).parent / "data" / "synthetic_mixed_realistic_700.csv"
rows = list(csv.DictReader(open(csv_path, encoding="utf-8")))
REASON_CODES = sorted(set(r["reason_code"] for r in rows))
LOGI = ["DELIVERED","IN_TRANSIT","TIMEOUT"]
AVS = {"Y":1,"N":0,"U":0.5,"":0.5, None:0.5}
def enc(r):
    return [int(r["amount_paise"])/100000, LOGI.index(r["logistics_status"]) if r["logistics_status"] in LOGI else 0,
            1 if r["signature"]=="True" else 0, 1 if r["three_ds"]=="True" else 0,
            1 if r["ip_match"]=="True" else 0, 1 if r["cvv_match"]=="True" else 0,
            AVS.get(r["avs"],0.5), int(float(r["order_count"] or 0))/10,
            int(float(r["prior_disputes"] or 0)), int(float(r["days_since"] or 100))/365,
            REASON_CODES.index(r["reason_code"])/len(REASON_CODES)]

X = np.array([enc(r) for r in rows], dtype=float)
y = np.array([1 if r["ground_truth"]=="CONTEST" else 0 for r in rows])
X_train, X_test, y_train, y_test, rtrain, rtest = train_test_split(X,y,rows,test_size=0.20, random_state=42, stratify=y)

fingerprint = dataset_fingerprint(csv_path)
commit = git_commit()
print(f"Dataset {csv_path} fingerprint={fingerprint} commit={commit} rows={len(rows)} {Counter(r['ground_truth'] for r in rows)}")

if HAS_MLFLOW:
    mlflow.set_experiment("autodefend-lightgbm")
    mlflow.set_tracking_uri("file:./mlruns")

# ── LightGBM ────────────────────────────────────────────────────────────────
lgb_clf = lgb.LGBMClassifier(n_estimators=150, max_depth=6, learning_rate=0.08, class_weight="balanced", random_state=42, verbose=-1)
if HAS_MLFLOW:
    with mlflow.start_run(run_name="lightgbm_baseline"):
        mlflow.log_params({"n_estimators":150,"max_depth":6,"lr":0.08,"dataset_fingerprint":fingerprint,"commit":commit,"rows":len(rows)})
        mlflow.log_input(mlflow.data.from_pandas(None) if False else mlflow.data.from_pandas)  # placeholder for dataset tracking
        lgb_clf.fit(X_train, y_train)
        yp = lgb_clf.predict(X_test)
        prec = precision_score(y_test, yp, zero_division=0); rec = recall_score(y_test, yp, zero_division=0); f1 = f1_score(y_test, yp, zero_division=0)
        fp_cost = sum(int(r["amount_paise"]) for r,yt,yp_ in zip(rtest,y_test,yp) if yt==0 and yp_==1)/100
        mlflow.log_metrics({"precision":prec,"recall":rec,"f1":f1,"fp_cost_rs":fp_cost})
        mlflow.sklearn.log_model(lgb_clf, "model", registered_model_name="autodefend-lightgbm")
        print(f"[MLflow] LightGBM logged run {mlflow.active_run().info.run_id} f1={f1:.3f} fp={fp_cost:.0f}")
else:
    lgb_clf.fit(X_train, y_train)
    yp = lgb_clf.predict(X_test)
    prec = precision_score(y_test, yp, zero_division=0); rec = recall_score(y_test, yp, zero_division=0); f1 = f1_score(y_test, yp, zero_division=0)
    fp_cost = sum(int(r["amount_paise"]) for r,yt,yp_ in zip(rtest,y_test,yp) if yt==0 and yp_==1)/100
    print(f"LightGBM (no mlflow) F1={f1:.3f} FP={fp_cost:.0f}")

# ── Stacking ───────────────────────────────────────────────────────────────
if HAS_MLFLOW:
    with mlflow.start_run(run_name="stacking_ensemble"):
        mlflow.log_params({"base":"xgb+lgb+cat","meta":"logistic","cv":5,"dataset_fingerprint":fingerprint,"commit":commit})
        xgb_clf = xgb.XGBClassifier(n_estimators=120, max_depth=5, learning_rate=0.08, scale_pos_weight=(len(y_train)-sum(y_train))/sum(y_train), random_state=42, verbosity=0, eval_metric="logloss")
        lgb2 = lgb.LGBMClassifier(n_estimators=120, max_depth=6, learning_rate=0.08, class_weight="balanced", random_state=42, verbose=-1)
        cat = cb.CatBoostClassifier(iterations=150, depth=6, learning_rate=0.08, auto_class_weights="Balanced", random_seed=42, verbose=False)
        stack = StackingClassifier(estimators=[("xgb",xgb_clf),("lgb",lgb2),("cat",cat)], final_estimator=LogisticRegression(max_iter=1000, class_weight="balanced"), cv=5, stack_method="predict_proba", n_jobs=1)
        stack.fit(X_train, y_train)
        yp2 = stack.predict(X_test)
        prec2 = precision_score(y_test, yp2, zero_division=0); rec2 = recall_score(y_test, yp2, zero_division=0); f2 = f1_score(y_test, yp2, zero_division=0)
        fp2 = sum(int(r["amount_paise"]) for r,yt,yp_ in zip(rtest,y_test,yp2) if yt==0 and yp_==1)/100
        mlflow.log_metrics({"precision":prec2,"recall":rec2,"f1":f2,"fp_cost_rs":fp2})
        mlflow.sklearn.log_model(stack, "model", registered_model_name="autodefend-stacking")
        print(f"[MLflow] Stacking logged f1={f2:.3f} fp={fp2:.0f}")
else:
    print("Stacking skipped — no mlflow")

print("Done. View: mlflow ui --port 5000  (then http://localhost:5000)  Registry: autodefend-lightgbm / autodefend-stacking")
