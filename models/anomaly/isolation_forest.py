#!/usr/bin/env python3
"""
SENTINEL — Two-stage Isolation Forest + peer deviation + feeder loss,
combined with SHAP explanations and evaluation vs synthetic ground truth.
"""
from __future__ import annotations

import json
import os
import warnings
from collections import defaultdict
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import shap
from sklearn.ensemble import IsolationForest
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support

warnings.filterwarnings("ignore", category=UserWarning)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA = os.path.join(ROOT, "data")

FEATURES_IF = [
    "consumption_kwh",
    "hour_of_day",
    "day_of_week",
    "rolling_mean_24h",
    "rolling_std_7d",
    "z_personal",
]


def load_all() -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    m = pd.read_csv(os.path.join(DATA, "meter_readings.csv"), parse_dates=["timestamp"])
    meta = pd.read_csv(os.path.join(DATA, "meter_metadata.csv"))
    f = pd.read_csv(os.path.join(DATA, "feeder_readings.csv"), parse_dates=["timestamp"])
    f["hour_ts"] = f["timestamp"].dt.floor("h")
    f = f.groupby(["feeder_id", "hour_ts"], as_index=False)["total_kwh"].sum()
    return m, meta, f


def enrich_meter_frame(df: pd.DataFrame) -> pd.DataFrame:
    d = df.sort_values(["meter_id", "timestamp"]).copy()
    d["consumption_kwh"] = d.groupby("meter_id")["consumption_kwh"].transform(
        lambda s: s.interpolate(limit_direction="both")
    )
    d["consumption_kwh"] = d["consumption_kwh"].fillna(
        d.groupby("category")["consumption_kwh"].transform("median")
    )
    d["hour_of_day"] = d["timestamp"].dt.hour + d["timestamp"].dt.minute / 60.0
    d["day_of_week"] = d["timestamp"].dt.dayofweek
    d["date"] = d["timestamp"].dt.normalize()

    g = d.groupby("meter_id", group_keys=False)
    d["rolling_mean_24h"] = g["consumption_kwh"].transform(lambda s: s.rolling(96, min_periods=12).mean())
    d["rolling_std_7d"] = g["consumption_kwh"].transform(lambda s: s.rolling(96 * 7, min_periods=48).std())
    mu = g["consumption_kwh"].transform("mean")
    sig = g["consumption_kwh"].transform("std").replace(0, np.nan)
    d["z_personal"] = (d["consumption_kwh"] - mu) / sig.fillna(1e-3)
    d[FEATURES_IF] = d[FEATURES_IF].bfill().ffill()
    return d


def train_if_per_meter(train: pd.DataFrame) -> Dict[str, IsolationForest]:
    models: Dict[str, IsolationForest] = {}
    for mid, sub in train.groupby("meter_id"):
        sub = sub.sort_values("timestamp")
        if len(sub) > 2500:
            sub = sub.iloc[:: max(1, len(sub) // 2500)]
        X = sub[FEATURES_IF].values
        if len(X) < 200:
            continue
        mdl = IsolationForest(
            n_estimators=80,
            contamination=0.05,
            max_samples=min(512, len(X)),
            random_state=42,
            n_jobs=-1,
        )
        mdl.fit(X)
        models[mid] = mdl
    return models


def score_meter_readings(models: Dict[str, IsolationForest], df: pd.DataFrame) -> pd.DataFrame:
    scores = []
    for mid, sub in df.groupby("meter_id"):
        mdl = models.get(mid)
        if mdl is None:
            continue
        sub = sub.sort_values("timestamp")
        X = sub[FEATURES_IF].values
        ss = mdl.score_samples(X)
        # lower score_samples => more anomalous in sklearn >=1.0
        thr = np.quantile(ss, 0.05)
        soft = ss < thr
        pr = mdl.predict(X)
        for i, row in enumerate(sub.itertuples()):
            scores.append(
                {
                    "meter_id": mid,
                    "timestamp": row.timestamp,
                    "if_score": float(ss[i]),
                    "soft_alert": bool(soft[i]),
                    "if_pred": int(pr[i]),
                }
            )
    return pd.DataFrame(scores)


def stage1_meter_level(score_df: pd.DataFrame, tail_days: int = 21) -> pd.Series:
    """True if enough soft alerts in recent tail."""
    tmax = score_df["timestamp"].max()
    cut = tmax - pd.Timedelta(days=tail_days)
    recent = score_df[score_df["timestamp"] >= cut]
    agg = recent.groupby("meter_id")["soft_alert"].mean()
    return agg >= 0.08


def stage2_peer_deviation(df: pd.DataFrame, days_need: int = 3) -> pd.Series:
    d = df.copy()
    grp = d.groupby(["timestamp", "locality", "category"])["consumption_kwh"]
    med = grp.transform("median")
    std = grp.transform("std").replace(0, np.nan).fillna(1e-3)
    z_peer = (d["consumption_kwh"] - med) / std
    d["z_peer"] = z_peer.abs()
    daily = d.groupby(["meter_id", "date"])["z_peer"].mean().reset_index()
    flags = defaultdict(int)
    for mid, sub in daily.groupby("meter_id"):
        sub = sub.sort_values("date")
        streak = 0
        max_streak = 0
        for v in sub["z_peer"].values:
            if v > 2.5:
                streak += 1
                max_streak = max(max_streak, streak)
            else:
                streak = 0
        flags[mid] = max_streak >= days_need
    return pd.Series({k: bool(v) for k, v in flags.items()})


def stage3_feeder_loss(meter_hour: pd.DataFrame, feeder: pd.DataFrame) -> Tuple[pd.Series, Dict[str, float]]:
    """Flag meters on feeders with sustained aggregate mismatch."""
    mh = meter_hour.copy()
    mh["hour_ts"] = mh["timestamp"].dt.floor("h")
    agg = mh.groupby(["feeder_id", "hour_ts"], as_index=False)["consumption_kwh"].sum().rename(
        columns={"consumption_kwh": "meter_sum"}
    )
    merged = agg.merge(feeder, on=["feeder_id", "hour_ts"], how="inner")
    merged["gap_pct"] = (merged["meter_sum"] - merged["total_kwh"]) / merged["total_kwh"].abs().clip(lower=1e-3)
    merged = merged.sort_values(["feeder_id", "hour_ts"])
    feeder_flag_hours = set()
    for fid, sub in merged.groupby("feeder_id"):
        sub = sub.sort_values("hour_ts")
        streak = 0
        for _, r in sub.iterrows():
            if abs(r["gap_pct"]) > 0.12:
                streak += 1
                if streak >= 2:
                    feeder_flag_hours.add((fid, r["hour_ts"]))
            else:
                streak = 0
    bad_feeders = {fh[0] for fh in feeder_flag_hours}
    meters_on = meter_hour.groupby("meter_id")["feeder_id"].first()
    s3 = pd.Series({m: str(meters_on[m]) in bad_feeders for m in meters_on.index})
    max_gap: Dict[str, float] = {}
    if len(merged):
        max_gap = merged.groupby("feeder_id")["gap_pct"].apply(lambda s: float(np.nanmax(np.abs(s.values)))).to_dict()
    return s3, max_gap


def classify_type(s1: bool, s2: bool, s3: bool, row_stats: Dict) -> str:
    if s3 and (s1 or s2):
        return "FEEDER_LOSS"
    if s2 and row_stats.get("high_vs_peer", False):
        return "PEER_DEVIATION"
    if s1 and row_stats.get("low_use", False):
        return "THEFT"
    if s1 and row_stats.get("volatile", False):
        return "TAMPERING"
    if s3:
        return "FEEDER_LOSS"
    if s2:
        return "PEER_DEVIATION"
    if s1:
        return "TAMPERING"
    return "NORMAL"


def shap_explain(
    model: IsolationForest,
    background: np.ndarray,
    explain_x: np.ndarray,
    feat_names: List[str],
) -> Tuple[np.ndarray, List[str]]:
    bg_s = shap.sample(background, min(32, len(background)))
    ex = explain_x[: min(24, len(explain_x))]
    try:
        explainer = shap.Explainer(model.decision_function, bg_s)
        sv = explainer(ex)
        vals = np.array(sv.values)
        mean_abs = np.mean(np.abs(vals), axis=0)
        order = np.argsort(-mean_abs)[:3]
        top = [feat_names[i] for i in order]
        return vals, top
    except Exception:
        return np.zeros((ex.shape[0], len(feat_names))), feat_names[:3]


def main() -> None:
    raw, meta, feeder = load_all()
    cohort_path = os.path.join(DATA, "generation_cohorts.json")
    feeder_loss_meters: set[str] = set()
    if os.path.isfile(cohort_path):
        with open(cohort_path, "r", encoding="utf-8") as cf:
            cj = json.load(cf)
        loss_feeders = set(cj.get("feeder_loss_feeders", []))
        feeder_loss_meters = set(meta.loc[meta["feeder_id"].isin(loss_feeders), "meter_id"].astype(str))

    df = enrich_meter_frame(raw)

    split_time = df["timestamp"].min() + pd.Timedelta(days=60)
    train = df[df["timestamp"] < split_time]
    full = df

    print("Training per-meter Isolation Forest models...", flush=True)
    models = train_if_per_meter(train)
    print(f"Trained {len(models)} meter-level models", flush=True)

    print("Scoring readings + peer/feeder stages...", flush=True)
    score_df = score_meter_readings(models, full)
    s1 = stage1_meter_level(score_df)
    s2 = stage2_peer_deviation(full)
    meter_hour = full[["meter_id", "feeder_id", "timestamp", "consumption_kwh"]].copy()
    s3, gap_by_feeder = stage3_feeder_loss(meter_hour, feeder)

    all_meters = meta["meter_id"].unique()
    s1 = s1.reindex(all_meters, fill_value=False)
    s2 = s2.reindex(all_meters, fill_value=False)
    s3 = s3.reindex(all_meters, fill_value=False)

    meta_idx = meta.set_index("meter_id")

    rows_out: List[dict] = []

    def _truth_type(s: pd.Series) -> str:
        u = s[s != "NORMAL"]
        if u.empty:
            return "NORMAL"
        return str(u.mode().iloc[0])

    truth = raw.groupby("meter_id")["anomaly_type"].agg(_truth_type)
    truth = truth.astype(str)
    for m in feeder_loss_meters:
        if m in truth.index and truth.loc[m] == "NORMAL":
            truth.loc[m] = "FEEDER_LOSS"

    for mid in all_meters:
        sub = full[full["meter_id"] == mid]
        personal_base = float(sub["consumption_kwh"].mean())
        peer_key = sub.groupby(["locality", "category"])["consumption_kwh"].mean().mean()
        peer_base = float(peer_key) if not np.isnan(peer_key) else personal_base

        st1 = bool(s1.get(mid, False))
        st2 = bool(s2.get(mid, False))
        st3 = bool(s3.get(mid, False))
        stages = int(st1) + int(st2) + int(st3)
        flagged = stages >= 2

        vol = float(sub["consumption_kwh"].std() / max(personal_base, 1e-3))
        low_use = float(sub.tail(96 * 14)["consumption_kwh"].mean()) < 0.65 * float(sub.head(96 * 14)["consumption_kwh"].mean())
        high_vs_peer = float(sub["consumption_kwh"].mean()) > 2.2 * peer_base

        atype = classify_type(st1, st2, st3, {"volatile": vol > 0.55, "low_use": low_use, "high_vs_peer": high_vs_peer})
        if not flagged:
            atype = "NORMAL"

        conf = int(round(100 * (0.35 * stages + 0.25 * int(st1) + 0.25 * int(st2) + 0.15 * int(st3))))
        conf = min(100, max(0, conf))

        sd = score_df[score_df["meter_id"] == mid]
        days_anom = int(sd.loc[sd["soft_alert"], "timestamp"].dt.normalize().nunique()) if len(sd) else 0
        dev_pct = float(100 * (personal_base - peer_base) / max(abs(peer_base), 1e-3)) if peer_base else 0.0

        mdl = models.get(mid)
        top_feats = ["consumption_kwh", "hour_of_day", "rolling_mean_24h"]
        shap_vals = None
        if flagged and mdl is not None:
            tr_sub = train[train["meter_id"] == mid][FEATURES_IF].dropna()
            bg = tr_sub.sample(min(80, len(tr_sub)), random_state=42).values if len(tr_sub) > 30 else tr_sub.values
            ex = sub[FEATURES_IF].dropna().tail(min(40, len(sub))).values
            if len(bg) > 20 and len(ex) > 4:
                _, top_feats = shap_explain(mdl, bg, ex, FEATURES_IF)

        loc = str(meta_idx.loc[mid, "locality"])
        feeder_id = str(meta_idx.loc[mid, "feeder_id"])
        cat = str(meta_idx.loc[mid, "category"])
        lat = float(meta_idx.loc[mid, "lat"])
        lon = float(meta_idx.loc[mid, "lon"])

        gap_txt = ""
        if st3:
            g = gap_by_feeder.get(feeder_id, 0.0) * 100.0
            gap_txt = f" Feeder {feeder_id} also shows ~{abs(g):.0f}% aggregate mismatch vs meter sum."

        expl = (
            f"Meter {mid} flagged: stages IF/peer/feeder = {int(st1)}/{int(st2)}/{int(st3)}. "
            f"Personal baseline ~{personal_base:.2f} kWh/interval vs peer cluster ~{peer_base:.2f} in {loc} {cat}.{gap_txt}"
        )

        rows_out.append(
            {
                "meter_id": mid,
                "locality": loc,
                "feeder_id": feeder_id,
                "category": cat,
                "lat": lat,
                "lon": lon,
                "flag_status": "FLAGGED" if flagged else "NORMAL",
                "confidence_score": conf,
                "anomaly_type": atype if flagged else "NORMAL",
                "explanation_text": expl,
                "shap_top_feature_1": top_feats[0] if len(top_feats) > 0 else "",
                "shap_top_feature_2": top_feats[1] if len(top_feats) > 1 else "",
                "shap_top_feature_3": top_feats[2] if len(top_feats) > 2 else "",
                "days_anomalous": days_anom,
                "personal_baseline_kwh": personal_base,
                "peer_baseline_kwh": peer_base,
                "deviation_pct": dev_pct,
            }
        )

    out_df = pd.DataFrame(rows_out)
    out_df.to_csv(os.path.join(DATA, "anomaly_results.csv"), index=False)

    # Evaluation vs ground truth (meter-level types)
    y_true = []
    y_pred = []
    types = ["THEFT", "TAMPERING", "PEER_DEVIATION", "FEEDER_LOSS", "NORMAL"]
    truth_map = truth.reindex(all_meters).fillna("NORMAL").astype(str).to_dict()

    for mid in all_meters:
        gt = truth_map.get(mid, "NORMAL")
        pr = out_df.loc[out_df["meter_id"] == mid, "anomaly_type"].iloc[0]
        pred_bin = 0 if pr == "NORMAL" else 1
        true_bin = 0 if gt == "NORMAL" else 1
        y_true.append(true_bin)
        y_pred.append(pred_bin)

    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    fpr = float(fp / max(fp + tn, 1))

    per_type = {}
    for t in ["THEFT", "TAMPERING", "PEER_DEVIATION", "FEEDER_LOSS"]:
        yt = [1 if truth_map[m] == t else 0 for m in all_meters]
        yp = [1 if out_df.loc[out_df["meter_id"] == m, "anomaly_type"].iloc[0] == t else 0 for m in all_meters]
        if sum(yt) == 0 and sum(yp) == 0:
            p, r, f1 = 1.0, 1.0, 1.0
        else:
            p, r, f1, _ = precision_recall_fscore_support(yt, yp, average="binary", zero_division=0)
        per_type[t] = {"precision": float(p), "recall": float(r), "f1": float(f1)}

    summary = {
        "total_flagged": int((out_df["flag_status"] == "FLAGGED").sum()),
        "by_type": out_df[out_df["flag_status"] == "FLAGGED"]["anomaly_type"].value_counts().to_dict(),
        "false_positive_rate": fpr,
        "overall_precision": float(tp / max(tp + fp, 1)),
        "overall_recall": float(tp / max(tp + fn, 1)),
        "overall_f1": float(2 * tp / max(2 * tp + fp + fn, 1)),
        "per_type": per_type,
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
    }
    with open(os.path.join(DATA, "anomaly_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("\nConfusion matrix (binary anomaly): TN FP FN TP =", tn, fp, fn, tp)
    print(f"FPR={fpr:.4f} Precision={summary['overall_precision']:.3f} Recall={summary['overall_recall']:.3f} F1={summary['overall_f1']:.3f}")
    print("Per-type:", json.dumps(per_type, indent=2))
    print(f"\nSaved {os.path.join(DATA, 'anomaly_results.csv')}")
    print(f"Saved {os.path.join(DATA, 'anomaly_summary.json')}")


if __name__ == "__main__":
    main()
