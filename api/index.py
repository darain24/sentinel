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
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATE: Dict[str, Any] = {}


def _load_csv(filename: str, **kwargs) -> pd.DataFrame:
    """Load a CSV, trying the primary file first, then a _sample fallback."""
    primary = os.path.join(DATA, filename)
    if os.path.exists(primary):
        return pd.read_csv(primary, **kwargs)
    sample = os.path.join(DATA, filename.replace(".csv", "_sample.csv"))
    if os.path.exists(sample):
        return pd.read_csv(sample, **kwargs)
    # Last resort: return empty DataFrame so the app doesn't crash
    return pd.DataFrame()


@app.on_event("startup")
def load_data() -> None:
    STATE["meter_readings"] = _load_csv("meter_readings.csv", parse_dates=["timestamp"])
    STATE["meter_metadata"] = _load_csv("meter_metadata.csv")
    STATE["feeder_readings"] = _load_csv("feeder_readings.csv", parse_dates=["timestamp"])
    STATE["forecast_results"] = _load_csv("forecast_results.csv", parse_dates=["timestamp"])
    STATE["forecast_next24h"] = _load_csv("forecast_next24h.csv")
    STATE["forecast_metrics"] = _load_csv("forecast_metrics.csv")
    STATE["anomaly_results"] = _load_csv("anomaly_results.csv")
    summary_path = os.path.join(DATA, "anomaly_summary.json")
    if os.path.exists(summary_path):
        with open(summary_path, "r", encoding="utf-8") as f:
            STATE["anomaly_summary"] = json.load(f)
    else:
        STATE["anomaly_summary"] = {}
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
    if df.empty:
        return []
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
    ar = STATE["anomaly_results"]
    if not ar.empty:
        top = (
            ar
            .query("flag_status == 'FLAGGED'")
            .sort_values("confidence_score", ascending=False)
            .head(5)
            .to_dict(orient="records")
        )
        summ["top_flagged_meters"] = top
    else:
        summ["top_flagged_meters"] = []
    return summ


@app.get("/api/forecast/zones")
def forecast_zones() -> List[Dict[str, Any]]:
    df = STATE["forecast_next24h"].copy()
    if df.empty:
        return []
    risk_rank = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}

    def max_risk(series: pd.Series) -> str:
        return max(series, key=lambda x: risk_rank.get(x, 0))

    rows = []
    for loc, g in df.groupby("locality"):
        peak_hour = int(g.loc[g["predicted_kwh"].idxmax(), "hour"])
        mx = max_risk(g["risk_level"])
        ar = STATE["anomaly_results"]
        flagged_count = 0
        if not ar.empty:
            flagged_count = int(
                ar[
                    (ar["locality"] == loc)
                    & (ar["flag_status"] == "FLAGGED")
                ]["meter_id"].nunique()
            )
        rows.append(
            {
                "locality": loc,
                "peak_hour": peak_hour,
                "max_risk_level": mx,
                "avg_predicted_kwh": float(g["predicted_kwh"].mean()),
                "flagged_meter_count": flagged_count,
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
    if n24.empty:
        return {"hours": [], "forecast_kwh": [], "baseline_kwh": [], "capacity_reference_kwh": []}
    agg = n24.groupby("hour", as_index=False)["predicted_kwh"].sum().sort_values("hour")
    fr = STATE["forecast_results"].copy()
    if not fr.empty:
        fr["hour"] = pd.to_datetime(fr["timestamp"], utc=True, errors="coerce").dt.hour
        base_by_h = fr.groupby("hour")["baseline_kwh"].mean()
        baseline = [float(base_by_h.get(h, base_by_h.mean())) for h in agg["hour"]]
    else:
        baseline = [0.0] * len(agg)
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
    if meta.empty:
        raise HTTPException(status_code=404, detail="Unknown meter")
    row = meta[meta["meter_id"] == meter_id]
    if row.empty:
        raise HTTPException(status_code=404, detail="Unknown meter")
    an = STATE["anomaly_results"]
    an_row = an[an["meter_id"] == meter_id] if not an.empty else pd.DataFrame()
    mr = STATE["meter_readings"]
    if not mr.empty:
        mr = mr[mr["meter_id"] == meter_id].sort_values("timestamp")
        tmax = mr["timestamp"].max()
        last7 = mr[mr["timestamp"] >= (tmax - pd.Timedelta(days=7))]
        readings = last7[["timestamp", "consumption_kwh", "is_anomaly", "anomaly_type"]].to_dict(orient="records")
    else:
        readings = []
    return {
        "metadata": row.iloc[0].to_dict(),
        "readings_last_7d": readings,
        "anomaly": an_row.iloc[0].to_dict() if len(an_row) else {},
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
    if meta.empty:
        return {
            "total_meters": 0, "flagged_count": 0, "critical_zones": [],
            "high_risk_feeders": [], "detection_accuracy": {}, "last_updated": _ts(),
        }
    flagged = an[an["flag_status"] == "FLAGGED"] if not an.empty else pd.DataFrame()
    zones = forecast_zones()
    critical_zones = [z for z in zones if z["max_risk_level"] in ("HIGH", "CRITICAL")]
    n24 = STATE["forecast_next24h"]
    high_feeders = []
    if not n24.empty:
        feeders = n24.groupby("feeder_id")["risk_level"].apply(lambda s: s.mode().iloc[0]).reset_index()
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
