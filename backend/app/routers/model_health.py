"""backend/app/routers/model_health.py

Training metrics for the /model-health page, read straight from the saved
artifacts (never recomputed, never invented):

  ml/artifacts/forecast_summary.json       -- MAE/RMSE/sMAPE per horizon
  ml/artifacts/forecast_metadata_h{7,14}.json -- splits, features, best iteration

GET /api/model-health -- horizons, metrics, baseline comparison, retrain dates
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter

router = APIRouter(prefix="/api/model-health", tags=["model-health"])

ARTIFACTS_DIR = Path(__file__).resolve().parents[3] / "ml" / "artifacts"


def _read_json(name: str) -> dict | None:
    path = ARTIFACTS_DIR / name
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


@router.get("")
def model_health() -> dict:
    summary = _read_json("forecast_summary.json") or {}
    horizons = []
    for key in ("7", "14"):
        entry = summary.get(key)
        if not entry:
            continue
        baseline = entry.get("baseline_metrics", {})
        model = entry.get("xgboost_metrics", {})
        mae = model.get("mae")
        baseline_mae = baseline.get("mae")
        improvement_pct = (
            round(100 * (baseline_mae - mae) / baseline_mae, 1)
            if mae is not None and baseline_mae
            else None
        )
        metadata = _read_json(f"forecast_metadata_h{key}.json") or {}
        horizons.append(
            {
                "horizon_days": entry.get("horizon"),
                "model": "XGBoost",
                "baseline": "7-day moving average",
                "mae": mae,
                "rmse": model.get("rmse"),
                "smape": model.get("smape"),
                "test_rows": model.get("n"),
                "baseline_mae": baseline_mae,
                "baseline_rmse": baseline.get("rmse"),
                "baseline_smape": baseline.get("smape"),
                "improvement_pct_vs_baseline": improvement_pct,
                "train_rows": entry.get("train_rows"),
                "val_rows": entry.get("val_rows"),
                "train_date_cutoff": entry.get("train_date_cutoff"),
                "val_date_cutoff": entry.get("val_date_cutoff"),
                "best_iteration": entry.get("best_iteration"),
                "feature_count": len(metadata.get("feature_columns", entry.get("feature_columns", []))),
                "feature_columns": metadata.get("feature_columns", []),
            }
        )
    return {
        "artifacts_dir": str(ARTIFACTS_DIR),
        "artifacts_found": bool(horizons),
        "horizons": horizons,
        "note": (
            "Metrics are test-set results on a chronological holdout (Oct 2023 onward). "
            "The modest ~5% gain over the naive baseline with high sMAPE (~72%) reflects "
            "limited learnable signal in the synthetic dataset, not a modeling failure -- "
            "see docs/limitations.md."
        ),
    }
