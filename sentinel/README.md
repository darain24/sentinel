# SENTINEL ⚡ Smart Energy Network Theft & Efficiency Intelligence Layer
**AI-first smart meter intelligence stack for BESCOM: demand forecasting, theft/loss detection, explainable alerts, and mission-control visualization.**

## Overview
SENTINEL is a production-style prototype built for the AI for Bharat hackathon (BESCOM track) to help utilities detect non-technical losses, reduce inspection waste, and improve demand planning reliability. The platform combines synthetic smart-meter telemetry generation, feeder-level forecasting, multi-stage anomaly fusion, SHAP-based reasoning, and an operations dashboard designed for field + command-center workflows.

The system is intentionally split into offline model pipelines and an online low-latency API/UI tier. Training and scoring are run ahead of time into CSV/JSON artifacts; FastAPI serves these artifacts instantly; Next.js visualizes live state with 30-second refresh. This architecture keeps the demo resilient, deterministic, and deployment-ready.

## Problem Statement
Power distribution utilities face:
- Hidden energy theft and tampering signals in massive interval meter streams.
- Feeder-level aggregate mismatch that often gets detected too late.
- Limited explainability for field officers deciding where to dispatch teams.
- Forecast uncertainty that complicates localized grid operations planning.

## Solution Architecture
```text
┌──────────────────────────────┐
│ Synthetic Data Generator     │
│ 500 meters, 90 days, 15-min  │
└──────────────┬───────────────┘
               │ CSV artifacts
┌──────────────▼───────────────┐      ┌────────────────────────────┐
│ Forecasting Pipeline          │      │ Anomaly Pipeline           │
│ XGBoost per feeder            │      │ IF + Peer + Feeder stages  │
│ + baseline + risk levels      │      │ + SHAP + eval metrics      │
└──────────────┬───────────────┘      └──────────────┬─────────────┘
               └──────────────┬──────────────────────┘
                              │ precomputed outputs
                     ┌────────▼────────┐
                     │ FastAPI Backend │
                     │ CSV/JSON in RAM │
                     └────────┬────────┘
                              │ REST
                   ┌──────────▼──────────┐
                   │ Next.js Dashboard   │
                   │ BESCOM Ops Console  │
                   └─────────────────────┘
```

## Key Features
- 500 smart meters across 10 Bangalore localities with realistic temporal usage behavior.
- Ground-truth anomaly injection: theft, tampering, peer deviation, feeder mismatch.
- Feeder-wise hourly demand forecasting (XGBoost) with baseline comparison.
- Multi-stage anomaly fusion with confidence scoring and type assignment.
- SHAP-backed top feature attribution for each flagged meter.
- FastAPI with query filters, inspection-report generation, and dashboard summary APIs.
- Dark-themed enterprise dashboard (map, risk heatmap, anomaly side panel, reports).

## Tech Stack
| Layer | Stack |
|---|---|
| Data & ML | Python, pandas, numpy, scikit-learn, XGBoost, SHAP |
| API | FastAPI, Uvicorn |
| Frontend | Next.js 14 (App Router), TypeScript, Tailwind CSS |
| Visuals | Recharts, React-Leaflet, Framer Motion, Lucide |
| Notebook / Analysis | Jupyter, matplotlib, seaborn |

## Quick Start
Follow `instructions.md` for full setup and run sequence.

## Project Structure
```text
sentinel/
├── data/
│   ├── generate_synthetic.py
│   ├── meter_readings.csv
│   ├── feeder_readings.csv
│   ├── meter_metadata.csv
│   ├── forecast_results.csv
│   ├── forecast_next24h.csv
│   ├── anomaly_results.csv
│   └── anomaly_summary.json
├── models/
│   ├── forecasting/xgboost_demand.py
│   └── anomaly/isolation_forest.py
├── api/main.py
├── dashboard/   # Next.js app
├── notebooks/eda_and_evaluation.ipynb
├── README.md
└── instructions.md
```

## How It Works
### Data Pipeline
- Generates 90 days of 15-minute interval data (4.32M rows) across 500 meters.
- Injects realistic noise, seasonality, and communication dropouts (2% NaN).
- Persists meter, feeder, and metadata artifacts for downstream training.

### Demand Forecasting
- Aggregates meter readings to hourly feeder loads.
- Engineers temporal, lag, rolling, Fourier, and locality features.
- Trains 10 feeder-specific XGBoost regressors and computes risk buckets.

### Anomaly Detection
- Stage 1: per-meter Isolation Forest soft alerts.
- Stage 2: peer-cluster deviation persistence check.
- Stage 3: feeder mismatch streak detection.
- Final flag requires multi-signal confirmation (2-of-3) with confidence scoring.

### Explainability
- SHAP computes top feature influence for flagged meters.
- Human-readable explanation text accompanies each alert and inspection report.

## API Reference
| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Service heartbeat + last update |
| `GET /api/anomalies` | Filterable flagged meter list |
| `GET /api/anomaly-summary` | Detection summary + top flags |
| `GET /api/forecast/zones` | Locality-level risk rollup |
| `GET /api/forecast/feeder/{feeder_id}` | 24h feeder forecast details |
| `GET /api/forecast/accuracy` | Per-feeder model metrics |
| `GET /api/forecast/heatmap` | Locality × hour risk cells |
| `GET /api/forecast/overview-24h` | Dashboard line/area chart dataset |
| `GET /api/meters/{meter_id}` | Meter metadata + last 7 days readings |
| `GET /api/inspection-report/{meter_id}` | Structured field-inspection JSON |
| `GET /api/dashboard-summary` | Home dashboard aggregate payload |

## Evaluation Results
| Metric Group | Value |
|---|---|
| Forecast Mean RMSE | 2.567 |
| Forecast Mean MAE | 2.054 |
| Forecast Mean MAPE | 1.763% |
| Mean Improvement vs Baseline | 79.56% |
| Detection Precision | 1.000 |
| Detection Recall | 0.506 |
| Detection F1 | 0.672 |
| False Positive Rate | 0.000 |

## Team
SENTINEL Hackathon Team — AI for Smart Meter Intelligence & Loss Detection.

## Hackathon: AI for Bharat — BESCOM Track
Built for AI for Bharat (co-presented by PAN IIT Bangalore and Government of Karnataka), focused on actionable utility intelligence for BESCOM operations.

