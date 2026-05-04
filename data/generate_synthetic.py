#!/usr/bin/env python3
"""
SENTINEL — Synthetic smart meter dataset for BESCOM hackathon demo.
500 meters × 90 days × 96 intervals/day with injected ground-truth anomalies.
"""
from __future__ import annotations

import os
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

RNG = np.random.default_rng(42)
random.seed(42)
np.random.seed(42)

LOCALITIES = [
    "Jayanagar",
    "Indiranagar",
    "Whitefield",
    "Koramangala",
    "Hebbal",
    "Electronic City",
    "Yelahanka",
    "Marathahalli",
    "Rajajinagar",
    "BTM Layout",
]

LOCALITY_COORDS: Dict[str, Tuple[float, float]] = {
    "Jayanagar": (12.9250, 77.5938),
    "Indiranagar": (12.9784, 77.6408),
    "Whitefield": (12.9698, 77.7500),
    "Koramangala": (12.9352, 77.6245),
    "Hebbal": (13.0358, 77.5970),
    "Electronic City": (12.8456, 77.6603),
    "Yelahanka": (13.1007, 77.5963),
    "Marathahalli": (12.9591, 77.6974),
    "Rajajinagar": (12.9915, 77.5543),
    "BTM Layout": (12.9166, 77.6100),
}

CATEGORIES = ["Residential", "Commercial", "Industrial"]
FEEDER_IDS = [f"F{i:02d}" for i in range(1, 11)]

NUM_METERS = 500
NUM_DAYS = 90
INTERVALS_PER_DAY = 96
GAP_FRAC = 0.02

# Anomaly cohort sizes
N_THEFT = 15
N_TAMPER = 10
N_PEER = 8
N_FEEDER_LOSS_FEEDERS = 3  # feeders with aggregate mismatch


@dataclass
class MeterSpec:
    meter_id: str
    locality: str
    feeder_id: str
    category: str
    lat: float
    lon: float


def _meter_jitter(loc: str) -> Tuple[float, float]:
    lat0, lon0 = LOCALITY_COORDS[loc]
    return float(lat0 + RNG.normal(0, 0.004)), float(lon0 + RNG.normal(0, 0.004))


def build_meter_specs() -> List[MeterSpec]:
    specs: List[MeterSpec] = []
    for i in range(NUM_METERS):
        feeder_idx = i // 50
        feeder = FEEDER_IDS[feeder_idx]
        locality = LOCALITIES[feeder_idx]
        # skew category by feeder for variety
        if i % 7 == 0:
            cat = "Industrial"
        elif i % 3 == 0:
            cat = "Commercial"
        else:
            cat = "Residential"
        lat, lon = _meter_jitter(locality)
        specs.append(
            MeterSpec(
                meter_id=f"MET_{i+1:03d}",
                locality=locality,
                feeder_id=feeder,
                category=cat,
                lat=lat,
                lon=lon,
            )
        )
    return specs


def base_profile_kwh(
    category: str,
    hour: int,
    dow: int,
    day_idx: int,
) -> float:
    """Typical 15-min kWh before noise, peaks, seasonality."""
    if category == "Residential":
        base = 0.22
        morning = 0.35 * np.exp(-((hour - 8) ** 2) / 4)
        evening = 0.55 * np.exp(-((hour - 20) ** 2) / 18)
    elif category == "Commercial":
        base = 0.45
        morning = 0.25 * np.exp(-((hour - 10) ** 2) / 6)
        evening = 0.15 * np.exp(-((hour - 19) ** 2) / 10)
        if dow >= 5:  # weekend — higher relative daytime use
            base *= 1.15
            morning *= 1.2
    else:  # Industrial
        base = 1.4
        morning = 0.1 * np.exp(-((hour - 9) ** 2) / 8)
        evening = 0.08 * np.exp(-((hour - 18) ** 2) / 12)

    # weekday vs weekend for residential
    if category == "Residential" and dow >= 5:
        base *= 0.88
        morning *= 0.85
        evening *= 1.05

    # seasonal (temperature proxy over 90 days — Bangalore summer ramp)
    season = 1.0 + 0.12 * np.sin(2 * np.pi * (day_idx / 90.0))
    kwh = (base + morning + evening) * season
    return float(max(0.02, kwh))


def assign_anomaly_meters(specs: List[MeterSpec]) -> Dict[str, Dict]:
    """Pick non-overlapping meter indices for each anomaly type."""
    idx_all = list(range(NUM_METERS))
    RNG.shuffle(idx_all)
    theft = idx_all[:N_THEFT]
    tamper = idx_all[N_THEFT : N_THEFT + N_TAMPER]
    peer = idx_all[N_THEFT + N_TAMPER : N_THEFT + N_TAMPER + N_PEER]
    return {
        "theft": theft,
        "tamper": tamper,
        "peer": peer,
        "feeder_loss_feeders": FEEDER_IDS[:N_FEEDER_LOSS_FEEDERS],
    }


def generate() -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Dict]:
    os.makedirs(os.path.dirname(__file__), exist_ok=True)
    specs = build_meter_specs()
    cohorts = assign_anomaly_meters(specs)

    start = datetime(2025, 1, 1, 0, 0, 0)
    timestamps: List[datetime] = [
        start + timedelta(days=d, minutes=t * 15)
        for d in range(NUM_DAYS)
        for t in range(INTERVALS_PER_DAY)
    ]

    rows: List[dict] = []
    theft_set = set(cohorts["theft"])
    tamper_set = set(cohorts["tamper"])
    peer_set = set(cohorts["peer"])

    # Peer multiplier pre-computed per meter (3x locality norm later applied in loop using running locality mean — simpler: apply constant 3.0 to synthetic base for peer meters)
    peer_mult = 3.0

    for mi, s in enumerate(specs):
        theft_drop = float(RNG.uniform(0.60, 0.80)) if mi in theft_set else 0.0
        theft_start_day = int(RNG.integers(55, 72)) if mi in theft_set else 999
        tamper_phase = float(RNG.uniform(3, 4)) if mi in tamper_set else 0.0
        tamper_amp = float(RNG.uniform(1.8, 2.8)) if mi in tamper_set else 0.0

        for day in range(NUM_DAYS):
            for slot in range(INTERVALS_PER_DAY):
                ts = timestamps[day * INTERVALS_PER_DAY + slot]
                hour = ts.hour + ts.minute / 60.0
                dow = ts.weekday()

                kwh = base_profile_kwh(s.category, int(hour), dow, day)

                # THEFT: sustained large drop
                if mi in theft_set and day >= theft_start_day:
                    kwh *= 1.0 - theft_drop

                # TAMPERING: irregular spikes every ~3-4 days
                if mi in tamper_set and tamper_phase > 0:
                    if (day % int(round(tamper_phase))) == int(day % 3) and slot > 40:
                        kwh *= tamper_amp * (0.5 + RNG.random())

                # PEER: consistently high vs peers
                if mi in peer_set:
                    kwh *= peer_mult

                # noise ±5–10%
                noise = float(RNG.uniform(0.90, 1.10))
                kwh *= noise

                is_anomaly = 0
                anomaly_type = "NORMAL"
                if mi in theft_set and day >= theft_start_day:
                    is_anomaly = 1
                    anomaly_type = "THEFT"
                elif mi in tamper_set and (day % int(max(2, round(tamper_phase)))) == (day % 3) and slot > 40:
                    is_anomaly = 1
                    anomaly_type = "TAMPERING"
                elif mi in peer_set:
                    is_anomaly = 1
                    anomaly_type = "PEER_DEVIATION"

                rows.append(
                    {
                        "meter_id": s.meter_id,
                        "locality": s.locality,
                        "feeder_id": s.feeder_id,
                        "category": s.category,
                        "timestamp": ts,
                        "consumption_kwh": kwh,
                        "is_anomaly": is_anomaly,
                        "anomaly_type": anomaly_type,
                    }
                )

    df = pd.DataFrame(rows)

    # Data gaps: 2% NaN in consumption
    n_gap = int(len(df) * GAP_FRAC)
    gap_idx = RNG.choice(len(df), size=n_gap, replace=False)
    df.loc[gap_idx, "consumption_kwh"] = np.nan

    # Feeder totals: sum of meters per feeder/hour slot, then apply loss feeders
    df_valid = df.copy()
    df_valid["consumption_kwh_filled"] = df_valid["consumption_kwh"].fillna(
        df_valid.groupby("meter_id")["consumption_kwh"].transform("median")
    )

    feeder_rows: List[dict] = []
    loss_feeders = set(cohorts["feeder_loss_feeders"])
    for ts in sorted(df["timestamp"].unique()):
        sub = df_valid[df_valid["timestamp"] == ts]
        for fid in FEEDER_IDS:
            msum = sub.loc[sub["feeder_id"] == fid, "consumption_kwh_filled"].sum()
            if fid in loss_feeders:
                # aggregate loss: feeder under-reports vs sum of meters
                total_kwh = float(msum * float(RNG.uniform(0.80, 0.86)))
            else:
                total_kwh = float(msum * float(RNG.uniform(0.985, 1.005)))
            feeder_rows.append(
                {
                    "feeder_id": fid,
                    "timestamp": ts,
                    "total_kwh": total_kwh,
                }
            )

    feeder_df = pd.DataFrame(feeder_rows)

    meta_rows = [
        {
            "meter_id": s.meter_id,
            "locality": s.locality,
            "feeder_id": s.feeder_id,
            "category": s.category,
            "lat": s.lat,
            "lon": s.lon,
        }
        for s in specs
    ]
    meta_df = pd.DataFrame(meta_rows)

    # Mark FEEDER_LOSS on meters under loss feeders for ground truth (optional label)
    # User asked ground truth on meter_readings — we keep PEER/TAMPER/THEFT; feeder loss is feeder-level.
    # Add FEEDER_LOSS label rows: mark all meters on those feeders for hours where gap>15% as anomaly_type override would blur evaluation. Keep is_anomaly for meter-level types only; anomaly script uses feeder gap.

    return df, feeder_df, meta_df, cohorts


def print_summary(df: pd.DataFrame, feeder_df: pd.DataFrame, cohorts: Dict) -> None:
    print("=" * 60)
    print("SENTINEL Synthetic Data — Generation Summary")
    print("=" * 60)
    print(f"Total meters: {df['meter_id'].nunique()}")
    print(f"Total readings: {len(df):,}")
    print(f"Date range: {df['timestamp'].min()} → {df['timestamp'].max()}")
    gap_count = int(df['consumption_kwh'].isna().sum())
    print(f"Data gap (NaN) readings: {gap_count:,} ({100*gap_count/len(df):.2f}%)")
    truth = df.groupby("meter_id").agg(
        is_anomaly=("is_anomaly", "max"),
        anomaly_type=("anomaly_type", lambda x: x[x != "NORMAL"].iloc[0] if (x != "NORMAL").any() else "NORMAL"),
    )
    print("\nAnomaly breakdown (meter-level ground truth):")
    print(truth["anomaly_type"].value_counts().to_string())
    print(f"\nFeeders with injected aggregate loss: {cohorts['feeder_loss_feeders']}")
    print("=" * 60)


def main() -> None:
    base = os.path.dirname(__file__)
    df, feeder_df, meta_df, cohorts = generate()
    df.to_csv(os.path.join(base, "meter_readings.csv"), index=False)
    feeder_df.to_csv(os.path.join(base, "feeder_readings.csv"), index=False)
    meta_df.to_csv(os.path.join(base, "meter_metadata.csv"), index=False)
    # Persist cohort config for debugging (optional)
    import json

    with open(os.path.join(base, "generation_cohorts.json"), "w", encoding="utf-8") as f:
        json.dump(
            {
                "theft_meters": [f"MET_{i+1:03d}" for i in cohorts["theft"]],
                "tamper_meters": [f"MET_{i+1:03d}" for i in cohorts["tamper"]],
                "peer_meters": [f"MET_{i+1:03d}" for i in cohorts["peer"]],
                "feeder_loss_feeders": cohorts["feeder_loss_feeders"],
            },
            f,
            indent=2,
        )
    print_summary(df, feeder_df, cohorts)
    print(f"\nSaved:\n  {os.path.join(base, 'meter_readings.csv')}\n  {os.path.join(base, 'feeder_readings.csv')}\n  {os.path.join(base, 'meter_metadata.csv')}")


if __name__ == "__main__":
    main()
