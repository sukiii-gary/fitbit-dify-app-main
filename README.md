# Fitbit Dify App

Minimal scaffold for a Fitbit segment analysis service:

- ingest Fitbit-like segment data
- store raw segments, features, predictions, and user memory
- compute simple feature vectors
- generate class probabilities through a replaceable predictor
- pass personalized context to Dify for explanation

## Quick start

1. Create a virtual environment and install dependencies:

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2. Copy the environment template:

```powershell
Copy-Item ..\.env.example .env
```

3. Run the API:

```powershell
uvicorn app.main:app --reload
```

4. Open the docs:

`http://127.0.0.1:8000/docs`

5. Open the dashboard:

`http://127.0.0.1:8000/dashboard`

## Import Fitbit export data

1. Export your Fitbit data from the Fitbit app and unzip it into `data/raw/fitbit-export/`.
2. Run the importer:

```powershell
.\backend\.venv\Scripts\python.exe .\backend\scripts\import_fitbit_export.py `
  --external-user-id fitbit_u001 `
  --name Alice `
  --timezone Asia/Shanghai
```

Use `--dry-run` first if you want to preview the generated hourly payloads without writing to the database.

If the directory contains Fitabase-style merged CSV files, the script auto-detects multi-user mode and creates one backend user per source `Id`.

More details: [docs/fitbit-import.md](docs/fitbit-import.md)

Project handover guide: [docs/project-handover-guide.md](docs/project-handover-guide.md)

## Backfill features and predictions

Once you have imported many raw segments, you can materialize missing feature vectors and model predictions in bulk:

```powershell
.\backend\.venv\Scripts\python.exe .\backend\scripts\backfill_features_predictions.py `
  --external-user-id fitabase_1503960366 `
  --limit 500
```

Run without `--external-user-id` to process every matching segment that is still missing features or predictions.

## Current scope

- The database defaults to SQLite for local setup. Switch `DATABASE_URL` to PostgreSQL for real usage.
- The predictor falls back to a deterministic heuristic when no trained XGBoost model artifact is present.
- Dify calls are skipped when `DIFY_API_KEY` is empty. The API still returns the assembled payload so you can inspect it.

## Suggested next steps

- Replace the heuristic predictor with a trained XGBoost artifact.
- Add Alembic migrations.
- Add a frontend timeline page.
- Add async jobs for batch feature extraction and prediction.
