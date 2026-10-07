"""Diagnose forecast quality and demand patterns on the chronological test set.

Run from the repository root with:
    .venv/Scripts/python.exe ml/eda/forecast_diagnostics.py

Writes a Markdown summary and per-entity metric CSVs under ml/eda/.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml" / "features"))
from build_features import FEATURE_COLUMNS, build_supervised_frame  # noqa: E402

DATA_PATH = ROOT / "data" / "processed" / "cleaned_inventory.csv"
ARTIFACTS = ROOT / "ml" / "artifacts"
OUTPUT = ROOT / "ml" / "eda"
TRAIN_END = pd.Timestamp("2023-07-01")
VAL_END = pd.Timestamp("2023-10-01")


def score(y: pd.Series | np.ndarray, pred: np.ndarray) -> dict[str, float]:
    actual = np.asarray(y, dtype=float)
    predicted = np.clip(np.asarray(pred, dtype=float), 0, None)
    denom = np.abs(actual) + np.abs(predicted)
    smape = np.mean(2 * np.abs(predicted - actual)[denom > 1e-9] / denom[denom > 1e-9]) * 100
    return {
        "MAE": float(mean_absolute_error(actual, predicted)),
        "RMSE": float(np.sqrt(mean_squared_error(actual, predicted))),
        "sMAPE_pct": float(smape),
    }


def markdown_table(frame: pd.DataFrame, digits: int = 2) -> str:
    if frame.empty:
        return "_(no rows)_"
    view = frame.copy()
    for column in view.select_dtypes(include="number"):
        view[column] = view[column].map(lambda x: f"{x:.{digits}f}")
    headers = [str(column) for column in view.columns]
    rows = [[str(value) for value in row] for row in view.itertuples(index=False, name=None)]
    widths = [max(len(headers[i]), *(len(row[i]) for row in rows)) for i in range(len(headers))]
    line = lambda values: "| " + " | ".join(value.ljust(widths[i]) for i, value in enumerate(values)) + " |"
    return "\n".join([line(headers), "| " + " | ".join("-" * width for width in widths) + " |", *(line(row) for row in rows)])


def main() -> None:
    raw_path = ROOT / "data" / "raw" / "retail_store_inventory.csv"
    raw = pd.read_csv(raw_path, parse_dates=["Date"])
    df = pd.read_csv(DATA_PATH, parse_dates=["Date"])
    dates = pd.DatetimeIndex(sorted(df["Date"].unique()))
    pairs = df[["Store ID", "Product ID"]].drop_duplicates()
    expected_rows = len(dates) * len(pairs)
    duplicate_key_rows = int(df.duplicated(["Date", "Store ID", "Product ID"]).sum())
    sales = df["Units Sold"].astype(float)
    cap = df["Units Sold"] >= df["Inventory Level"]

    data_checks = pd.DataFrame([
        ("Rows", len(df)),
        ("Products", df["Product ID"].nunique()),
        ("Stores", df["Store ID"].nunique()),
        ("Distinct dates", len(dates)),
        ("Expected complete panel rows", expected_rows),
        ("Missing panel rows", expected_rows - len(df)),
        ("Duplicate date/store/product keys", duplicate_key_rows),
        ("Missing cells", int(df.isna().sum().sum())),
        ("Raw vs cleaned Units Sold changed", int((raw["Units Sold"] != df["Units Sold"]).sum())),
    ], columns=["Check", "Value"])

    demand_summary = pd.DataFrame([
        ("Mean daily entity sales", sales.mean()),
        ("Median daily entity sales", sales.median()),
        ("Standard deviation", sales.std()),
        ("Coefficient of variation", sales.std() / sales.mean()),
        ("Zero-sales rows (%)", (sales == 0).mean() * 100),
        ("Sales >= inventory rows (%)", cap.mean() * 100),
        ("Sales >= 95% of inventory (%)", (sales >= .95 * df["Inventory Level"]).mean() * 100),
        ("P95 daily sales", sales.quantile(.95)),
        ("P99 daily sales", sales.quantile(.99)),
    ], columns=["Measure", "Value"])

    # Examine whether the recorded demand has a stable calendar pattern.
    df["weekday"] = df["Date"].dt.day_name()
    df["month"] = df["Date"].dt.month
    weekday = df.groupby("weekday")["Units Sold"].agg(["mean", "std", "count"]).reindex(
        ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    ).reset_index()
    weekday.columns = ["Weekday", "Mean sales", "Std dev", "Rows"]
    month = df.groupby("month")["Units Sold"].agg(["mean", "std", "count"]).reset_index()
    month.columns = ["Month", "Mean sales", "Std dev", "Rows"]

    # Input signal and target relationships. These are descriptive, not causal.
    feature_corr = df[["Units Sold", "Inventory Level", "Price", "Discount", "Holiday/Promotion", "Competitor Pricing", "Demand Forecast"]].corr(numeric_only=True)["Units Sold"].drop("Units Sold").sort_values(key=lambda s: s.abs(), ascending=False)
    signal_table = feature_corr.rename_axis("Field").reset_index(name="Correlation with Units Sold")

    all_metrics = []
    entity_metrics = []
    level_metrics = []
    for horizon in (7, 14):
        supervised = build_supervised_frame(df, horizon)
        test = supervised[supervised["target_date"] >= VAL_END].copy()
        model = joblib.load(ARTIFACTS / f"forecast_model_h{horizon}.joblib")
        x = test[FEATURE_COLUMNS]
        test["xgboost"] = np.clip(model.predict(x), 0, None)
        baseline_features = {
            "7-day mean": "rolling_mean_7",
            "14-day mean": "rolling_mean_14",
            "same-weekday lag": f"lag_{horizon}",
        }
        preds = {"XGBoost": test["xgboost"].to_numpy()}
        preds.update({name: test[col].to_numpy() for name, col in baseline_features.items()})
        for name, pred in preds.items():
            all_metrics.append({"Horizon": horizon, "Method": name, **score(test["y"], pred)})

        for (product, store), group in test.groupby(["Product ID", "Store ID"]):
            for name, pred_col in [("XGBoost", "xgboost"), *[(key, value) for key, value in baseline_features.items()]]:
                pred = group[pred_col].to_numpy() if pred_col == "xgboost" else group[pred_col].to_numpy()
                entity_metrics.append({"Horizon": horizon, "Product": product, "Store": store, "Method": name, **score(group["y"], pred)})

        test["actual_band"] = pd.cut(test["y"], bins=[-0.01, 0, 50, 100, 200, 5000], labels=["0", "1-50", "51-100", "101-200", "201+"])
        for band, group in test.groupby("actual_band", observed=False):
            if len(group) == 0:
                continue
            level_metrics.append({"Horizon": horizon, "Actual sales band": str(band), "Rows": len(group), **score(group["y"], group["xgboost"])})

    metrics = pd.DataFrame(all_metrics)
    entity = pd.DataFrame(entity_metrics)
    levels = pd.DataFrame(level_metrics)
    entity.to_csv(OUTPUT / "forecast_entity_metrics.csv", index=False)
    levels.to_csv(OUTPUT / "forecast_sales_level_metrics.csv", index=False)

    # Stability across time: score the final 3 months separately, in addition to the complete test.
    temporal = []
    for horizon in (7, 14):
        supervised = build_supervised_frame(df, horizon)
        test = supervised[supervised["target_date"] >= VAL_END].copy()
        model = joblib.load(ARTIFACTS / f"forecast_model_h{horizon}.joblib")
        test["prediction"] = np.clip(model.predict(test[FEATURE_COLUMNS]), 0, None)
        test["target_month"] = test["target_date"].dt.to_period("M").astype(str)
        for period, group in test.groupby("target_month"):
            temporal.append({"Horizon": horizon, "Test month": period, "Rows": len(group), **score(group["y"], group["prediction"])})
    temporal = pd.DataFrame(temporal)

    product_stats = df.groupby("Product ID")["Units Sold"].agg(["mean", "std", "min", "max"]).reset_index()
    product_stats.columns = ["Product", "Mean", "Std dev", "Min", "Max"]
    product_stats["CV"] = product_stats["Std dev"] / product_stats["Mean"]
    store_stats = df.groupby("Store ID")["Units Sold"].agg(["mean", "std", "min", "max"]).reset_index()
    store_stats.columns = ["Store", "Mean", "Std dev", "Min", "Max"]
    store_stats["CV"] = store_stats["Std dev"] / store_stats["Mean"]

    top_entities = entity[entity["Method"] == "XGBoost"].sort_values(["Horizon", "MAE"], ascending=[True, False])
    worst = top_entities.groupby("Horizon").head(5)[["Horizon", "Product", "Store", "MAE", "RMSE", "sMAPE_pct"]]
    best = top_entities.groupby("Horizon").tail(5).sort_values(["Horizon", "MAE"])[["Horizon", "Product", "Store", "MAE", "RMSE", "sMAPE_pct"]]

    lines = [
        "# Forecast diagnostic EDA",
        "",
        "This report uses the chronological holdout (target dates from 2023-10-01 through the dataset end). Metrics are descriptive; the holdout is not used to retune the model.",
        "",
        "## Data integrity",
        "",
        markdown_table(data_checks),
        "",
        "## Demand shape and possible censoring",
        "",
        markdown_table(demand_summary),
        "",
        "Sales at or above recorded inventory can indicate censored demand (the dataset may record available sales rather than what customers wanted). This flag is a diagnostic only because the dataset does not confirm stockout semantics.",
        "",
        "## Model and baseline scores",
        "",
        markdown_table(metrics.sort_values(["Horizon", "MAE"])),
        "",
        "## Scores by actual sales range",
        "",
        markdown_table(levels),
        "",
        "## Test performance over time (XGBoost)",
        "",
        markdown_table(temporal),
        "",
        "## Product and store demand variation",
        "",
        "Per-product demand statistics:",
        "",
        markdown_table(product_stats.sort_values("CV", ascending=False)),
        "",
        "Per-store demand statistics:",
        "",
        markdown_table(store_stats.sort_values("CV", ascending=False)),
        "",
        "## Day of week and month patterns",
        "",
        "Weekday averages:",
        "",
        markdown_table(weekday),
        "",
        "Month-of-year averages (all years pooled):",
        "",
        markdown_table(month),
        "",
        "## Available feature relationships",
        "",
        markdown_table(signal_table),
        "",
        "Correlations do not establish causality. Product and store identifiers are included in the forecasting model, but this table isolates simple numeric correlations.",
        "",
        "## Entity-level forecast errors",
        "",
        "Five highest-MAE product/store pairs by horizon:",
        "",
        markdown_table(worst),
        "",
        "Five lowest-MAE product/store pairs by horizon:",
        "",
        markdown_table(best),
        "",
        "All pair-by-method metrics are saved in `forecast_entity_metrics.csv`; sales-range scores are saved in `forecast_sales_level_metrics.csv`.",
        "",
    ]
    report_path = OUTPUT / "forecast_diagnostics.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {report_path}")
    print(f"Wrote {OUTPUT / 'forecast_entity_metrics.csv'}")
    print(f"Wrote {OUTPUT / 'forecast_sales_level_metrics.csv'}")


if __name__ == "__main__":
    main()
