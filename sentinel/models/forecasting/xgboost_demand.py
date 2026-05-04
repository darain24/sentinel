#!/usr/bin/env python3
"""
SENTINEL — Per-feeder hourly demand forecasting with XGBoost + zone risk.
"""
from __future__ import annotations

import json
import os
import pickle
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.preprocessing import LabelEncoder

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA = os.path.join(ROOT, "data")
MODEL_DIR = os.path.join(os.path.dirname(__file__), "saved_models")
FEEDER_IDS = [f"F{i:02d}" for i in range(1, 11)]


def load_frames() -> Tuple[pd.DataFrame, pd.DataFrame]:
    m = pd.read_csv(os.path.join(DATA, "meter_readings.csv"), parse_dates=["timestamp"])
    meta = pd.read_csv(os.path.join(DATA, "meter_metadata.csv"))
    return m, meta


def dominant_locality(meta: pd.DataFrame) -> Dict[str, str]:
    rows = (
        meta.groupby(["feeder_id", "locality"])
        .size()
        .reset_index(name="n")
        .sort_values(["feeder_id", "n"], ascending=[True, False])
        .drop_duplicates("feeder_id")
    )
    return dict(zip(rows["feeder_id"], rows["locality"]))


def hourly_feeder_consumption(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["consumption_kwh"] = d.groupby("meter_id")["consumption_kwh"].transform(
        lambda s: s.interpolate(limit_direction="both")
    )
    d["consumption_kwh"] = d["consumption_kwh"].fillna(
        d.groupby("category")["consumption_kwh"].transform("median")
    )
    d["hour_ts"] = d["timestamp"].dt.floor("h")
    h = (
        d.groupby(["feeder_id", "hour_ts"], as_index=False)["consumption_kwh"]
        .sum()
        .rename(columns={"consumption_kwh": "total_kwh"})
        .sort_values(["feeder_id", "hour_ts"])
    )
    return h


def add_features(h: pd.DataFrame, le_loc: LabelEncoder, loc_map: Dict[str, str]) -> pd.DataFrame:
    h = h.copy()
    h["hour_of_day"] = h["hour_ts"].dt.hour
    h["day_of_week"] = h["hour_ts"].dt.dayofweek
    h["is_weekend"] = (h["day_of_week"] >= 5).astype(int)
    h["month"] = h["hour_ts"].dt.month
    h["day_of_year"] = h["hour_ts"].dt.dayofyear
    h["locality"] = h["feeder_id"].map(loc_map)
    h["locality_enc"] = le_loc.transform(h["locality"].astype(str))

    h = h.sort_values(["feeder_id", "hour_ts"])
    g = h.groupby("feeder_id", group_keys=False)
    h["rolling_mean_24h"] = g["total_kwh"].transform(lambda s: s.rolling(24, min_periods=6).mean())
    h["rolling_mean_7d"] = g["total_kwh"].transform(lambda s: s.rolling(24 * 7, min_periods=48).mean())
    h["rolling_std_24h"] = g["total_kwh"].transform(lambda s: s.rolling(24, min_periods=6).std())

    h["lag_1h"] = g["total_kwh"].shift(1)
    h["lag_24h"] = g["total_kwh"].shift(24)
    h["lag_168h"] = g["total_kwh"].shift(168)

    h["fourier_hour_sin"] = np.sin(2 * np.pi * h["hour_of_day"] / 24.0)
    h["fourier_hour_cos"] = np.cos(2 * np.pi * h["hour_of_day"] / 24.0)
    h["fourier_dow_sin"] = np.sin(2 * np.pi * h["day_of_week"] / 7.0)
    h["fourier_dow_cos"] = np.cos(2 * np.pi * h["day_of_week"] / 7.0)

    feat_cols = [
        "hour_of_day",
        "day_of_week",
        "is_weekend",
        "month",
        "rolling_mean_24h",
        "rolling_mean_7d",
        "rolling_std_24h",
        "lag_1h",
        "lag_24h",
        "lag_168h",
        "fourier_hour_sin",
        "fourier_hour_cos",
        "fourier_dow_sin",
        "fourier_dow_cos",
        "locality_enc",
    ]
    h[feat_cols] = h[feat_cols].bfill().ffill()
    return h


def baseline_same_hour_dow(train: pd.DataFrame) -> pd.DataFrame:
    key = train.groupby(["feeder_id", "hour_of_day", "day_of_week"])["total_kwh"].mean().reset_index()
    key = key.rename(columns={"total_kwh": "baseline_kwh"})
    return key


def risk_level(pred: float, cap: float) -> str:
    pct = pred / max(cap, 1e-6)
    if pct < 0.70:
        return "LOW"
    if pct < 0.85:
        return "MEDIUM"
    if pct < 0.95:
        return "HIGH"
    return "CRITICAL"


def train_eval_forecast() -> None:
    os.makedirs(MODEL_DIR, exist_ok=True)
    raw, meta = load_frames()
    loc_map = dominant_locality(meta)
    all_localities = sorted(set(loc_map.values()))
    le_loc = LabelEncoder().fit(all_localities)

    hourly = hourly_feeder_consumption(raw)
    hourly = add_features(hourly, le_loc, loc_map)

    split_time = hourly["hour_ts"].min() + pd.Timedelta(days=75)
    train = hourly[hourly["hour_ts"] < split_time].copy()
    test = hourly[hourly["hour_ts"] >= split_time].copy()

    base_tbl = baseline_same_hour_dow(train)

    feat_cols = [c for c in hourly.columns if c not in ("feeder_id", "hour_ts", "total_kwh", "locality")]

    metrics_rows: List[dict] = []
    forecast_rows: List[dict] = []
    next24_rows: List[dict] = []

    # Feeder capacity from training peak (robust)
    cap_by: Dict[str, float] = {}
    for fid, sub in train.groupby("feeder_id"):
        cap_by[fid] = float(np.quantile(sub["total_kwh"].values, 0.98) * 1.25 + 50.0)

    with open(os.path.join(MODEL_DIR, "feeder_capacity.json"), "w", encoding="utf-8") as f:
        json.dump(cap_by, f, indent=2)

    for fid in FEEDER_IDS:
        tr = train[train["feeder_id"] == fid].dropna(subset=["total_kwh"])
        te = test[test["feeder_id"] == fid]
        tr = tr.dropna(subset=feat_cols)
        te = te.dropna(subset=feat_cols)
        if len(tr) < 200:
            continue

        X_tr, y_tr = tr[feat_cols], tr["total_kwh"]
        X_te, y_te = te[feat_cols], te["total_kwh"]

        model = xgb.XGBRegressor(
            n_estimators=400,
            max_depth=8,
            learning_rate=0.05,
            subsample=0.85,
            colsample_bytree=0.85,
            objective="reg:squarederror",
            random_state=42,
            n_jobs=-1,
        )
        model.fit(X_tr, y_tr)
        pred = model.predict(X_te)
        pred = np.clip(pred, 0, None)

        te2 = te.merge(base_tbl[base_tbl["feeder_id"] == fid], on=["feeder_id", "hour_of_day", "day_of_week"], how="left")
        baseline = te2["baseline_kwh"].fillna(te2["total_kwh"].mean()).values

        rmse = float(np.sqrt(mean_squared_error(y_te, pred)))
        mae = float(mean_absolute_error(y_te, pred))
        mape = float(np.mean(np.abs((y_te.values - pred) / np.maximum(y_te.values, 1e-3))) * 100.0)
        rmse_b = float(np.sqrt(mean_squared_error(y_te.values, baseline)))
        impr = float(100.0 * (1 - rmse / max(rmse_b, 1e-6)))

        metrics_rows.append(
            {
                "feeder_id": fid,
                "locality": loc_map[fid],
                "rmse": rmse,
                "mae": mae,
                "mape": mape,
                "rmse_baseline": rmse_b,
                "improvement_pct_vs_baseline": impr,
            }
        )

        cap = cap_by[fid]
        for ts, act, pr, bl in zip(te["hour_ts"], y_te, pred, baseline):
            forecast_rows.append(
                {
                    "feeder_id": fid,
                    "locality": loc_map[fid],
                    "timestamp": ts,
                    "predicted_kwh": float(pr),
                    "actual_kwh": float(act),
                    "risk_level": risk_level(float(pr), cap),
                    "baseline_kwh": float(bl),
                }
            )

        with open(os.path.join(MODEL_DIR, f"{fid}.pkl"), "wb") as f:
            pickle.dump({"model": model, "feat_cols": feat_cols, "feeder_id": fid}, f)

        print(f"[{fid}] RMSE={rmse:.2f} MAE={mae:.2f} MAPE={mape:.2f}% | Baseline RMSE={rmse_b:.2f} | Improvement={impr:.1f}%")

    # Next 24h operational window: model scores on the final 24 consecutive hourly buckets per feeder
    for fid in FEEDER_IDS:
        cap = cap_by[fid]
        with open(os.path.join(MODEL_DIR, f"{fid}.pkl"), "rb") as f:
            bundle = pickle.load(f)
        model: xgb.XGBRegressor = bundle["model"]
        fcols: List[str] = bundle["feat_cols"]
        last24 = hourly[hourly["feeder_id"] == fid].sort_values("hour_ts").dropna(subset=fcols).tail(24)
        if len(last24) < 24:
            last24 = (
                hourly[hourly["feeder_id"] == fid]
                .sort_values("hour_ts")
                .ffill()
                .bfill()
                .tail(24)
            )
        preds = np.clip(model.predict(last24[fcols]), 0, None)
        for hour_slot, (_, row, pr) in enumerate(zip(range(1, 25), last24.iterrows(), preds), start=1):
            next24_rows.append(
                {
                    "feeder_id": fid,
                    "locality": loc_map[fid],
                    "hour": hour_slot,
                    "predicted_kwh": float(pr),
                    "risk_level": risk_level(float(pr), cap),
                }
            )

    pd.DataFrame(forecast_rows).to_csv(os.path.join(DATA, "forecast_results.csv"), index=False)
    pd.DataFrame(next24_rows).to_csv(os.path.join(DATA, "forecast_next24h.csv"), index=False)
    pd.DataFrame(metrics_rows).to_csv(os.path.join(DATA, "forecast_metrics.csv"), index=False)
    print(f"\nSaved models under {MODEL_DIR}")
    print(f"Saved {os.path.join(DATA, 'forecast_results.csv')}")
    print(f"Saved {os.path.join(DATA, 'forecast_next24h.csv')}")


if __name__ == "__main__":
    train_eval_forecast()
