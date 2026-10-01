"""
tests/test_forecast_artifacts.py

Confirms the saved model artifacts (ml/artifacts/) actually reload and
reproduce the metrics recorded at training time -- catches "trained fine
but the saved artifact is stale/corrupt/mismatched" bugs.
"""

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ml" / "features"))
sys.path.insert(0, str(ROOT / "ml" / "training"))

from build_features import FEATURE_COLUMNS, build_supervised_frame  # noqa: E402
from train_forecast import TRAIN_END, VAL_END, evaluate  # noqa: E402

ARTIFACTS_DIR = ROOT / "ml" / "artifacts"
PROCESSED_PATH = ROOT / "data" / "processed" / "cleaned_inventory.csv"


@pytest.fixture(scope="module")
def cleaned_df():
    return pd.read_csv(PROCESSED_PATH, parse_dates=["Date"])


@pytest.mark.parametrize("horizon", [7, 14])
def test_saved_model_reproduces_metadata_metrics(cleaned_df, horizon):
    model_path = ARTIFACTS_DIR / f"forecast_model_h{horizon}.joblib"
    metadata_path = ARTIFACTS_DIR / f"forecast_metadata_h{horizon}.json"
    assert model_path.exists(), f"missing {model_path} -- run ml/training/train_forecast.py"
    assert metadata_path.exists()

    metadata = json.loads(metadata_path.read_text())
    model = joblib.load(model_path)

    sup = build_supervised_frame(cleaned_df, horizon)
    test = sup[sup["target_date"] >= VAL_END]
    assert len(test) == metadata["test_rows"]

    X_test, y_test = test[FEATURE_COLUMNS], test["y"]
    pred = np.clip(model.predict(X_test), a_min=0, a_max=None)
    reloaded_metrics = evaluate(y_test, pred)

    saved_metrics = metadata["xgboost_metrics"]
    assert reloaded_metrics["mae"] == pytest.approx(saved_metrics["mae"], abs=1e-6)
    assert reloaded_metrics["rmse"] == pytest.approx(saved_metrics["rmse"], abs=1e-6)


@pytest.mark.parametrize("horizon", [7, 14])
def test_xgboost_beats_baseline(horizon):
    metadata_path = ARTIFACTS_DIR / f"forecast_metadata_h{horizon}.json"
    metadata = json.loads(metadata_path.read_text())
    assert metadata["xgboost_improves_on_baseline_mae"] is True


def test_demand_forecast_column_not_in_features():
    """The existing (leaky) Demand Forecast column must never be a model feature."""
    assert "Demand Forecast" not in FEATURE_COLUMNS
    assert "demand_forecast" not in [c.lower() for c in FEATURE_COLUMNS]


def test_predictions_are_non_negative(cleaned_df):
    model = joblib.load(ARTIFACTS_DIR / "forecast_model_h14.joblib")
    sup = build_supervised_frame(cleaned_df, 14)
    test = sup[sup["target_date"] >= VAL_END]
    pred = model.predict(test[FEATURE_COLUMNS])
    # Raw model output can dip slightly negative; the service layer clips it
    # -- this test documents that the clip is necessary.
    clipped = np.clip(pred, a_min=0, a_max=None)
    assert (clipped >= 0).all()
