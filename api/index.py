"""
SENTINEL — FastAPI service reading precomputed CSV/JSON artifacts (no on-request model inference).
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA = os.path.join(ROOT, "data")

app = FastAPI(title="SENTINEL API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATE: Dict[str, Any] = {}


@app.on_event("startup")
def load_data() -> None:
    def get_path(filename: str) -> str:
        primary = os.path.join(DATA, filename)
        if os.path.exists(primary):
            return primary
        # Fallback for deployment environments where large CSVs are ignored
        sample = os.path.join(DATA, filename.replace(".csv", "_sample.csv"))
        if os.path.exists(sample):
            return sample
        return primary # Will likely raise error on read, but it's the best we can do

    STATE["meter_readings"] = pd.read_csv(get_path("meter_readings.csv"), parse_dates=["timestamp"])
    STATE["meter_metadata"] = pd.read_csv(os.path.join(DATA, "meter_metadata.csv"))
    STATE["feeder_readings"] = pd.read_csv(get_path("feeder_readings.csv"), parse_dates=["timestamp"])
    STATE["forecast_results"] = pd.read_csv(get_path("forecast_results.csv"), parse_dates=["timestamp"])
    STATE["forecast_next24h"] = pd.read_csv(os.path.join(DATA, "forecast_next24h.csv"))
    STATE["forecast_metrics"] = pd.read_csv(os.path.join(DATA, "forecast_metrics.csv"))
    STATE["anomaly_results"] = pd.read_csv(os.path.join(DATA, "anomaly_results.csv"))
    with open(os.path.join(DATA, "anomaly_summary.json"), "r", encoding="utf-8") as f:
        STATE["anomaly_summary"] = json.load(f)
    STATE["last_updated"] = datetime.now(timezone.utc).isoformat()


def _ts() -> str:
    return str(STATE.get("last_updated") or datetime.now(timezone.utc).isoformat())


@app.get("/api/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "sentinel": "active", "last_updated": _ts()}


@app.get("/api/anomalies")
def anomalies(
    locality: Optional[str] = None,
    type: Optional[str] = Query(None, alias="type"),
    min_confidence: float = 0,
    feeder_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    df = STATE["anomaly_results"].copy()
    df = df[df["flag_status"] == "FLAGGED"]
    if locality:
        df = df[df["locality"].str.lower() == locality.lower()]
    if type:
        df = df[df["anomaly_type"].str.upper() == type.upper()]
    if feeder_id:
        df = df[df["feeder_id"].str.upper() == feeder_id.upper()]
    if min_confidence:
        df = df[df["confidence_score"] >= float(min_confidence)]
    return df.to_dict(orient="records")


@app.get("/api/anomaly-summary")
def anomaly_summary() -> Dict[str, Any]:
    summ = dict(STATE["anomaly_summary"])
    top = (
        STATE["anomaly_results"]
        .query("flag_status == 'FLAGGED'")
        .sort_values("confidence_score", ascending=False)
        .head(5)
        .to_dict(orient="records")
    )
    summ["top_flagged_meters"] = top
    return summ


@app.get("/api/forecast/zones")
def forecast_zones() -> List[Dict[str, Any]]:
    df = STATE["forecast_next24h"].copy()
    risk_rank = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}

    def max_risk(series: pd.Series) -> str:
        return max(series, key=lambda x: risk_rank.get(x, 0))

    rows = []
    for loc, g in df.groupby("locality"):
        peak_hour = int(g.loc[g["predicted_kwh"].idxmax(), "hour"])
        mx = max_risk(g["risk_level"])
        rows.append(
            {
                "locality": loc,
                "peak_hour": peak_hour,
                "max_risk_level": mx,
                "avg_predicted_kwh": float(g["predicted_kwh"].mean()),
                "flagged_meter_count": int(
                    STATE["anomaly_results"][
                        (STATE["anomaly_results"]["locality"] == loc)
                        & (STATE["anomaly_results"]["flag_status"] == "FLAGGED")
                    ]["meter_id"].nunique()
                ),
            }
        )
    return rows


@app.get("/api/forecast/feeder/{feeder_id}")
def forecast_feeder(feeder_id: str) -> Dict[str, Any]:
    raw = feeder_id.strip().upper()
    if raw.startswith("F") and len(raw) == 3:
        fid = raw
    else:
        digits = "".join(ch for ch in raw if ch.isdigit()) or "1"
        fid = f"F{int(digits):02d}"
    d24 = STATE["forecast_next24h"][STATE["forecast_next24h"]["feeder_id"] == fid]
    if d24.empty:
        raise HTTPException(status_code=404, detail="Feeder not found")
    acc = STATE["forecast_metrics"][STATE["forecast_metrics"]["feeder_id"] == fid]
    return {
        "feeder_id": fid,
        "hourly": d24.sort_values("hour").to_dict(orient="records"),
        "accuracy": acc.to_dict(orient="records")[0] if len(acc) else {},
    }


@app.get("/api/forecast/accuracy")
def forecast_accuracy() -> List[Dict[str, Any]]:
    return STATE["forecast_metrics"].to_dict(orient="records")


@app.get("/api/forecast/heatmap")
def forecast_heatmap() -> List[Dict[str, Any]]:
    """Locality × hour risk cells for UI heatmap."""
    df = STATE["forecast_next24h"].copy()
    return df.to_dict(orient="records")


@app.get("/api/forecast/overview-24h")
def forecast_overview_24h() -> Dict[str, Any]:
    """Aggregated next-window forecast vs historical baseline for dashboard chart."""
    n24 = STATE["forecast_next24h"].copy()
    agg = n24.groupby("hour", as_index=False)["predicted_kwh"].sum().sort_values("hour")
    fr = STATE["forecast_results"].copy()
    fr["hour"] = pd.to_datetime(fr["timestamp"], utc=True, errors="coerce").dt.hour
    base_by_h = fr.groupby("hour")["baseline_kwh"].mean()
    baseline = [float(base_by_h.get(h, base_by_h.mean())) for h in agg["hour"]]
    cap_line = [float(agg["predicted_kwh"].max() * 1.05)] * len(agg)
    return {
        "hours": agg["hour"].astype(int).tolist(),
        "forecast_kwh": agg["predicted_kwh"].round(3).tolist(),
        "baseline_kwh": [round(x, 3) for x in baseline],
        "capacity_reference_kwh": [round(x, 3) for x in cap_line],
    }


@app.get("/api/meters/{meter_id}")
def meter_detail(meter_id: str) -> Dict[str, Any]:
    meta = STATE["meter_metadata"]
    row = meta[meta["meter_id"] == meter_id]
    if row.empty:
        raise HTTPException(status_code=404, detail="Unknown meter")
    an = STATE["anomaly_results"][STATE["anomaly_results"]["meter_id"] == meter_id]
    mr = STATE["meter_readings"][STATE["meter_readings"]["meter_id"] == meter_id].sort_values("timestamp")
    tmax = mr["timestamp"].max()
    last7 = mr[mr["timestamp"] >= (tmax - pd.Timedelta(days=7))]
    return {
        "metadata": row.iloc[0].to_dict(),
        "readings_last_7d": last7[["timestamp", "consumption_kwh", "is_anomaly", "anomaly_type"]].to_dict(
            orient="records"
        ),
        "anomaly": an.iloc[0].to_dict() if len(an) else {},
    }


@app.get("/api/inspection-report/{meter_id}")
def inspection_report(meter_id: str) -> Dict[str, Any]:
    detail = meter_detail(meter_id)
    an = detail.get("anomaly") or {}
    rid = f"RPT-{meter_id}-{datetime.now(timezone.utc).strftime('%Y%m%d')}"
    priority = "HIGH" if an.get("confidence_score", 0) >= 75 else "MEDIUM" if an.get("confidence_score", 0) >= 50 else "LOW"
    evidence: List[str] = []
    if an.get("deviation_pct"):
        evidence.append(f"Deviation vs peer baseline: {float(an['deviation_pct']):.1f}%")
    if an.get("days_anomalous"):
        evidence.append(f"Anomalous activity spread across ~{int(an['days_anomalous'])} distinct day(s)")
    evidence.append(f"Personal baseline (interval mean): {float(an.get('personal_baseline_kwh', 0)):.3f} kWh")
    evidence.append(f"Peer cluster baseline: {float(an.get('peer_baseline_kwh', 0)):.3f} kWh")
    return {
        "report_id": rid,
        "generated_at": _ts(),
        "meter": detail.get("metadata"),
        "anomaly_details": an,
        "shap_explanation": an.get("explanation_text", ""),
        "recommendation": "Dispatch field team for physical inspection and seal verification.",
        "priority": priority,
        "evidence": evidence,
    }


@app.get("/api/dashboard-summary")
def dashboard_summary() -> Dict[str, Any]:
    meta = STATE["meter_metadata"]
    an = STATE["anomaly_results"]
    flagged = an[an["flag_status"] == "FLAGGED"]
    zones = forecast_zones()
    critical_zones = [z for z in zones if z["max_risk_level"] in ("HIGH", "CRITICAL")]
    feeders = STATE["forecast_next24h"].groupby("feeder_id")["risk_level"].apply(lambda s: s.mode().iloc[0]).reset_index()
    risk_rank = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
    feeders["rk"] = feeders["risk_level"].map(risk_rank)
    high_feeders = feeders[feeders["rk"] >= 2].sort_values("rk", ascending=False)["feeder_id"].tolist()
    f1 = float(STATE["anomaly_summary"].get("overall_f1", 0))
    return {
        "total_meters": int(meta["meter_id"].nunique()),
        "flagged_count": int(len(flagged)),
        "critical_zones": critical_zones,
        "high_risk_feeders": high_feeders,
        "detection_accuracy": {
            "precision": STATE["anomaly_summary"].get("overall_precision"),
            "recall": STATE["anomaly_summary"].get("overall_recall"),
            "f1": f1,
            "false_positive_rate": STATE["anomaly_summary"].get("false_positive_rate"),
        },
        "last_updated": _ts(),
    }
