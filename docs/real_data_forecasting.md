# Using real sales for forecasts

## Goal

Make forecasts reflect the user's stores and products while keeping the existing sample-trained forecast available as a fallback. Real sales should only drive a forecast after the history is complete enough to build targets and the real-data candidate performs better on a chronological holdout than a simple baseline.

## Why day completion is needed

`Real · Manual` sales are recorded as per-day totals for a product/store when at least one sale is entered. A missing product row can mean either zero sales or that the day's sales were not entered. Those cases must not be treated as the same value. A store/day completion confirmation records that all sales for that store and date have been entered; only then can missing product rows safely be interpreted as zero for model training.

The confirmation is stored in `sales_day_closures`. It does not create fake sales transactions or modify inventory. Dates with sample dataset sales cannot be marked complete, preventing sample history from being presented as real history. The Sales page shows the number of complete days per store over the most recent year.

## Gradual adoption

1. Record real sales as they happen.
2. At the end of each business day, mark that store's sales complete, even if there were no sales.
3. Accumulate at least 180 complete days before evaluating a provisional real-data model; 365 or more days are preferable to cover annual seasonality. These are starting guardrails, not guarantees of forecast quality. The current UI displays this count per store.
4. Compare candidates using rolling chronological validation. Keep the sample-trained XGBoost forecast as fallback until a real-data model beats a simple baseline consistently and has enough complete coverage.
5. Clearly label the forecast source and history coverage in the UI.

The current implementation adds step 2 and captures the completeness record. It does not retrain or switch the forecast yet.
