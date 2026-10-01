"""
ml/features/build_features.py

Builds a supervised learning frame for forecasting `Units Sold` at a given
horizon (7 or 14 days ahead), per (Store ID, Product ID) time series.

LEAKAGE DESIGN (see docs/limitations.md "Forecasting feature design"):
  - Lag/rolling features use only data up to and including the origin date T.
  - Target-date (T+h) time features (day of week, month, etc.) are used --
    these are calendar facts, always knowable in advance.
  - Target-date Price / Discount / Holiday-Promotion / Competitor Pricing
    are used under the standard retail-forecasting assumption that pricing
    and promotion calendars are planned ahead of the forecast horizon.
    This is a documented assumption, not a data fact.
  - Inventory Level uses ONLY the origin-date (T) value -- future inventory
    depends on events between T and T+h that aren't knowable at forecast
    time, so using the target-date value would be leakage.
  - Category / Region / Weather Condition / Seasonality are NOT stable
    per-entity or per-date in this dataset (verified in Phase 3 / this
    phase -- every date has all 4 seasons and all weather types spread
    across rows). Target-date values are therefore not knowable in
    advance. Only origin-date (last known) values are used, and they are
    expected to carry little signal -- included to satisfy the spec's
    feature list, not because they're expected to help.
  - The existing `Demand Forecast` column is NEVER used as a feature.
"""

from __future__ import annotations

import pandas as pd

LAG_DAYS = (1, 7, 14)
ROLLING_WINDOWS = (7, 14)


def _add_time_features(dates: pd.Series, prefix: str) -> pd.DataFrame:
    dt = pd.to_datetime(dates)
    return pd.DataFrame(
        {
            f"{prefix}_year": dt.dt.year,
            f"{prefix}_month": dt.dt.month,
            f"{prefix}_day": dt.dt.day,
            f"{prefix}_day_of_week": dt.dt.dayofweek,
            f"{prefix}_week_of_year": dt.dt.isocalendar().week.astype(int),
            f"{prefix}_weekend": dt.dt.dayofweek.isin([5, 6]).astype(int),
        }
    )


def build_supervised_frame(df: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """
    df: cleaned dataset (one row per Date/Store ID/Product ID).
    horizon: number of days ahead to forecast (7 or 14).

    Returns one row per (Store ID, Product ID, origin_date) with all
    features plus the target `y` (Units Sold at origin_date + horizon).
    Rows without enough history for the longest lag, or without a known
    future actual (near the end of the dataset), are dropped.
    """
    df = df.sort_values(["Store ID", "Product ID", "Date"]).reset_index(drop=True)
    grouped = df.groupby(["Store ID", "Product ID"], group_keys=False)

    frames = []
    for (store_id, product_id), g in grouped:
        g = g.sort_values("Date").reset_index(drop=True)

        lag_feats = pd.DataFrame(index=g.index)
        for lag in LAG_DAYS:
            lag_feats[f"lag_{lag}"] = g["Units Sold"].shift(lag)
        for window in ROLLING_WINDOWS:
            lag_feats[f"rolling_mean_{window}"] = g["Units Sold"].rolling(window).mean()
            lag_feats[f"rolling_std_{window}"] = g["Units Sold"].rolling(window).std()

        origin = g[
            [
                "Date",
                "Price",
                "Discount",
                "Holiday/Promotion",
                "Competitor Pricing",
                "Inventory Level",
                "Category",
                "Region",
                "Weather Condition",
                "Seasonality",
            ]
        ].rename(
            columns={
                "Date": "origin_date",
                "Price": "origin_price",
                "Discount": "origin_discount",
                "Holiday/Promotion": "origin_promotion",
                "Competitor Pricing": "origin_competitor_pricing",
                "Inventory Level": "origin_inventory_level",
                "Category": "origin_category",
                "Region": "origin_region",
                "Weather Condition": "origin_weather",
                "Seasonality": "origin_seasonality",
            }
        )
        origin = pd.concat([origin, lag_feats], axis=1)

        # Target: shift Units Sold (and the "planned" business columns)
        # backward by `horizon` so row i holds the value `horizon` days
        # after row i's date.
        target_slice = g[
            ["Date", "Price", "Discount", "Holiday/Promotion", "Competitor Pricing", "Units Sold"]
        ].rename(
            columns={
                "Date": "target_date",
                "Price": "target_price",
                "Discount": "target_discount",
                "Holiday/Promotion": "target_promotion",
                "Competitor Pricing": "target_competitor_pricing",
                "Units Sold": "y",
            }
        )
        target_shifted = target_slice.shift(-horizon)

        combined = pd.concat([origin, target_shifted], axis=1)
        combined["Store ID"] = store_id
        combined["Product ID"] = product_id
        frames.append(combined)

    result = pd.concat(frames, ignore_index=True)

    required_cols = (
        [f"lag_{lag}" for lag in LAG_DAYS] + [f"rolling_mean_{w}" for w in ROLLING_WINDOWS] + ["y", "target_date"]
    )
    result = result.dropna(subset=required_cols).reset_index(drop=True)

    time_feats = _add_time_features(result["target_date"], prefix="target")
    result = pd.concat([result, time_feats], axis=1)

    for col in ["Store ID", "Product ID", "origin_category", "origin_region", "origin_weather", "origin_seasonality"]:
        result[col] = result[col].astype("category")

    result["horizon"] = horizon
    return result


def build_live_feature_row(df: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """
    Builds one feature row per (Store ID, Product ID) for forecasting
    `horizon` days beyond the LAST date present in `df` -- i.e. genuine
    forward-looking inference, not backtesting.

    Since the target date is beyond the data, there is no real future
    Price/Discount/Holiday-Promotion/Competitor Pricing to use. Under the
    same "planned in advance" assumption documented in
    build_supervised_frame, these are carried forward from the most
    recent known (origin) values -- i.e. we assume no planned change
    unless told otherwise. This is a documented simplification, not a
    verified fact -- see docs/limitations.md.
    """
    df = df.sort_values(["Store ID", "Product ID", "Date"]).reset_index(drop=True)
    last_date = df["Date"].max()
    target_date = last_date + pd.Timedelta(days=horizon)

    grouped = df.groupby(["Store ID", "Product ID"], group_keys=False)
    rows = []
    for (store_id, product_id), g in grouped:
        g = g.sort_values("Date").reset_index(drop=True)
        if len(g) < max(LAG_DAYS + ROLLING_WINDOWS):
            continue  # not enough history for this store/product combo

        last = g.iloc[-1]
        sales = g["Units Sold"]

        row = {
            "origin_date": last["Date"],
            "origin_price": last["Price"],
            "origin_discount": last["Discount"],
            "origin_promotion": last["Holiday/Promotion"],
            "origin_competitor_pricing": last["Competitor Pricing"],
            "origin_inventory_level": last["Inventory Level"],
            "origin_category": last["Category"],
            "origin_region": last["Region"],
            "origin_weather": last["Weather Condition"],
            "origin_seasonality": last["Seasonality"],
            # Carried forward -- documented assumption, see docstring above.
            "target_price": last["Price"],
            "target_discount": last["Discount"],
            "target_promotion": last["Holiday/Promotion"],
            "target_competitor_pricing": last["Competitor Pricing"],
            "target_date": target_date,
            "Store ID": store_id,
            "Product ID": product_id,
        }
        for lag in LAG_DAYS:
            row[f"lag_{lag}"] = sales.iloc[-lag]
        for window in ROLLING_WINDOWS:
            row[f"rolling_mean_{window}"] = sales.iloc[-window:].mean()
            row[f"rolling_std_{window}"] = sales.iloc[-window:].std()
        rows.append(row)

    result = pd.DataFrame(rows)
    time_feats = _add_time_features(result["target_date"], prefix="target")
    result = pd.concat([result, time_feats], axis=1)

    for col in ["Store ID", "Product ID", "origin_category", "origin_region", "origin_weather", "origin_seasonality"]:
        result[col] = result[col].astype("category")

    result["horizon"] = horizon
    return result


FEATURE_COLUMNS = (
    [f"lag_{lag}" for lag in LAG_DAYS]
    + [f"rolling_mean_{w}" for w in ROLLING_WINDOWS]
    + [f"rolling_std_{w}" for w in ROLLING_WINDOWS]
    + [
        "origin_price",
        "origin_discount",
        "origin_promotion",
        "origin_competitor_pricing",
        "origin_inventory_level",
        "origin_category",
        "origin_region",
        "origin_weather",
        "origin_seasonality",
        "target_price",
        "target_discount",
        "target_promotion",
        "target_competitor_pricing",
        "target_year",
        "target_month",
        "target_day",
        "target_day_of_week",
        "target_week_of_year",
        "target_weekend",
        "Store ID",
        "Product ID",
    ]
)
