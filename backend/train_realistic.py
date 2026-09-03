import csv, json
from pathlib import Path
from collections import Counter
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.metrics import precision_score, recall_score, f1_score, confusion_matrix, classification_report
from sklearn.linear_model import LogisticRegression
import lightgbm as lgb
import xgboost as xgb
import catboost as cb
from sklearn.ensemble import StackingClassifier

csv_path = Path("data/synthetic_mixed_realistic_700.csv")
rows = list(csv.DictReader(open(csv_path, encoding="utf-8")))
print(f"Loaded {len(rows)} realistic mixed rows")
print(Counter(r['ground_truth'] for r in rows))

REASON_CODES = sorted(set(r["reason_code"] for r in rows))
LOGI = ["DELIVERED","IN_TRANSIT","TIMEOUT"]
AVS = {"Y":1,"N":0,"U":0.5,"":0.5, None:0.5}
def enc(r):
    return [int(r["amount_paise"])/100000,
            LOGI.index(r["logistics_status"]) if r["logistics_status"] in LOGI else 0,
            1 if r["signature"]=="True" else 0,
            1 if r["three_ds"]=="True" else 0,
            1 if r["ip_match"]=="True" else 0,
            1 if r["cvv_match"]=="True" else 0,
            AVS.get(r["avs"],0.5),
            int(float(r["order_count"] or 0))/10,
            int(float(r["prior_disputes"] or 0)),
            int(float(r["days_since"] or 100))/365,
            REASON_CODES.index(r["reason_code"])/len(REASON_CODES)]

X = np.array([enc(r) for r in rows], dtype=float)
y = np.array([1 if r["ground_truth"]=="CONTEST" else 0 for r in rows])

X_train,X_test,y_train,y_test,rtrain,rtest = train_test_split(X,y,rows,test_size=0.20,random_state=42,stratify=y)
print(f"Train {len(y_train)} Test {len(y_test)}")

# LightGBM baseline
lgb_clf = lgb.LGBMClassifier(n_estimators=150, max_depth=6, learning_rate=0.08, class_weight="balanced", random_state=42, verbose=-1)
lgb_clf.fit(X_train, y_train)
yp = lgb_clf.predict(X_test)
prec = precision_score(y_test, yp, zero_division=0)
rec = recall_score(y_test, yp, zero_division=0)
f1 = f1_score(y_test, yp, zero_division=0)
fp_cost = sum(int(r["amount_paise"]) for r,yt,yp_ in zip(rtest,y_test,yp) if yt==0 and yp_==1)/100
print(f"\nLightGBM: Prec {prec:.3f} Rec {rec:.3f} F1 {f1:.3f} CM {confusion_matrix(y_test,yp).tolist()} FP Rs.{fp_cost:.0f}")
print(classification_report(y_test,yp, target_names=["NOT","CONTEST"], zero_division=0))

# Stacking
xgb_clf = xgb.XGBClassifier(n_estimators=120, max_depth=5, learning_rate=0.08, scale_pos_weight=(len(y_train)-sum(y_train))/sum(y_train), random_state=42, verbosity=0, eval_metric="logloss")
lgb2 = lgb.LGBMClassifier(n_estimators=120, max_depth=6, learning_rate=0.08, class_weight="balanced", random_state=42, verbose=-1)
cat = cb.CatBoostClassifier(iterations=150, depth=6, learning_rate=0.08, auto_class_weights="Balanced", random_seed=42, verbose=False)
stack = StackingClassifier(estimators=[("xgb",xgb_clf),("lgb",lgb2),("cat",cat)], final_estimator=LogisticRegression(max_iter=1000, class_weight="balanced"), cv=5, stack_method="predict_proba", n_jobs=1)
stack.fit(X_train, y_train)
yp2 = stack.predict(X_test)
prec2 = precision_score(y_test, yp2, zero_division=0)
rec2 = recall_score(y_test, yp2, zero_division=0)
f2 = f1_score(y_test, yp2, zero_division=0)
fp2 = sum(int(r["amount_paise"]) for r,yt,yp_ in zip(rtest,y_test,yp2) if yt==0 and yp_==1)/100
print(f"\nStacking: Prec {prec2:.3f} Rec {rec2:.3f} F1 {f2:.3f} CM {confusion_matrix(y_test,yp2).tolist()} FP Rs.{fp2:.0f}")
print(classification_report(y_test,yp2, target_names=["NOT","CONTEST"], zero_division=0))
print(f"\nWinner F1: LightGBM {f1:.3f} vs Stacking {f2:.3f} -> {'Stacking' if f2>f1 else 'LightGBM' if f1>f2 else 'Tie'}")
