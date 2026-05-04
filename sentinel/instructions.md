# SENTINEL Setup & Run Instructions

## Prerequisites
- Python 3.10+
- Node.js 18+
- `pip`
- `npm`

## Step 1 — Clone and Setup
```bash
git clone <your-repo-url>
cd sentinel
```

## Step 2 — Python Environment
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## Step 3 — Generate Synthetic Data
```bash
python data/generate_synthetic.py
```

## Step 4 — Train Forecasting Model
```bash
python models/forecasting/xgboost_demand.py
```

## Step 5 — Run Anomaly Detection
```bash
python models/anomaly/isolation_forest.py
```

## Step 6 — Start API
```bash
uvicorn api.main:app --reload --port 8000
```

## Step 7 — Install and Start Dashboard
In a new terminal:
```bash
cd dashboard
npm install
npm run dev
```

## Step 8 — Open the Dashboard
Go to:
- `http://localhost:3000/dashboard`

## Notes
- The dashboard consumes only real computed outputs from the Python pipelines via FastAPI.
- No frontend mock data is used for charts, map, anomaly lists, or reports.
- Re-run Steps 3–5 whenever you want fresh synthetic runs and updated metrics.
- If a wheel build issue occurs on your machine, retry with: `pip install -r requirements.txt --prefer-binary`.

