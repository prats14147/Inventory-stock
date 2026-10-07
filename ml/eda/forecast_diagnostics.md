# Forecast diagnostic EDA

This report uses the chronological holdout (target dates from 2023-10-01 through the dataset end). Metrics are descriptive; the holdout is not used to retune the model.

## Data integrity

| Check                             | Value    |
| --------------------------------- | -------- |
| Rows                              | 73100.00 |
| Products                          | 20.00    |
| Stores                            | 5.00     |
| Distinct dates                    | 731.00   |
| Expected complete panel rows      | 73100.00 |
| Missing panel rows                | 0.00     |
| Duplicate date/store/product keys | 0.00     |
| Missing cells                     | 0.00     |
| Raw vs cleaned Units Sold changed | 0.00     |

## Demand shape and possible censoring

| Measure                       | Value  |
| ----------------------------- | ------ |
| Mean daily entity sales       | 136.46 |
| Median daily entity sales     | 107.00 |
| Standard deviation            | 108.92 |
| Coefficient of variation      | 0.80   |
| Zero-sales rows (%)           | 0.49   |
| Sales >= inventory rows (%)   | 0.50   |
| Sales >= 95% of inventory (%) | 5.13   |
| P95 daily sales               | 357.00 |
| P99 daily sales               | 434.00 |

Sales at or above recorded inventory can indicate censored demand (the dataset may record available sales rather than what customers wanted). This flag is a diagnostic only because the dataset does not confirm stockout semantics.

## Model and baseline scores

| Horizon | Method           | MAE    | RMSE   | sMAPE_pct |
| ------- | ---------------- | ------ | ------ | --------- |
| 7.00    | XGBoost          | 88.54  | 108.14 | 71.56     |
| 7.00    | 14-day mean      | 90.87  | 111.80 | 72.70     |
| 7.00    | 7-day mean       | 93.44  | 115.74 | 74.02     |
| 7.00    | same-weekday lag | 119.58 | 153.63 | 92.41     |
| 14.00   | XGBoost          | 88.54  | 108.16 | 71.56     |
| 14.00   | 14-day mean      | 90.78  | 111.81 | 72.59     |
| 14.00   | 7-day mean       | 92.84  | 115.19 | 73.76     |
| 14.00   | same-weekday lag | 120.14 | 153.91 | 92.80     |

## Scores by actual sales range

| Horizon | Actual sales band | Rows    | MAE    | RMSE   | sMAPE_pct |
| ------- | ----------------- | ------- | ------ | ------ | --------- |
| 7.00    | 0                 | 33.00   | 136.27 | 136.27 | 200.00    |
| 7.00    | 1-50              | 2340.00 | 111.03 | 111.95 | 140.07    |
| 7.00    | 51-100            | 1995.00 | 62.35  | 63.95  | 60.48     |
| 7.00    | 101-200           | 2542.00 | 25.30  | 30.28  | 17.50     |
| 7.00    | 201+              | 2390.00 | 154.98 | 169.09 | 69.48     |
| 14.00   | 0                 | 33.00   | 136.28 | 136.29 | 200.00    |
| 14.00   | 1-50              | 2340.00 | 111.05 | 111.98 | 140.08    |
| 14.00   | 51-100            | 1995.00 | 62.36  | 63.98  | 60.47     |
| 14.00   | 101-200           | 2542.00 | 25.30  | 30.29  | 17.50     |
| 14.00   | 201+              | 2390.00 | 154.95 | 169.09 | 69.46     |

## Test performance over time (XGBoost)

| Horizon | Test month | Rows    | MAE   | RMSE   | sMAPE_pct |
| ------- | ---------- | ------- | ----- | ------ | --------- |
| 7.00    | 2023-10    | 3100.00 | 88.15 | 108.80 | 70.78     |
| 7.00    | 2023-11    | 3000.00 | 90.19 | 110.00 | 72.08     |
| 7.00    | 2023-12    | 3100.00 | 87.24 | 105.64 | 71.64     |
| 7.00    | 2024-01    | 100.00  | 91.38 | 108.68 | 78.17     |
| 14.00   | 2023-10    | 3100.00 | 88.13 | 108.80 | 70.76     |
| 14.00   | 2023-11    | 3000.00 | 90.23 | 110.01 | 72.09     |
| 14.00   | 2023-12    | 3100.00 | 87.22 | 105.66 | 71.64     |
| 14.00   | 2024-01    | 100.00  | 91.36 | 108.73 | 78.15     |

## Product and store demand variation

Per-product demand statistics:

| Product | Mean   | Std dev | Min  | Max    | CV   |
| ------- | ------ | ------- | ---- | ------ | ---- |
| P0008   | 133.67 | 108.68  | 0.00 | 494.00 | 0.81 |
| P0007   | 136.61 | 110.51  | 0.00 | 491.00 | 0.81 |
| P0010   | 135.83 | 109.72  | 0.00 | 488.00 | 0.81 |
| P0004   | 135.57 | 109.26  | 0.00 | 489.00 | 0.81 |
| P0018   | 134.76 | 108.54  | 0.00 | 499.00 | 0.81 |
| P0009   | 137.37 | 110.56  | 0.00 | 491.00 | 0.80 |
| P0019   | 136.22 | 109.49  | 0.00 | 479.00 | 0.80 |
| P0003   | 134.96 | 108.38  | 0.00 | 485.00 | 0.80 |
| P0001   | 136.27 | 109.32  | 0.00 | 496.00 | 0.80 |
| P0012   | 134.52 | 107.75  | 0.00 | 496.00 | 0.80 |
| P0006   | 136.01 | 108.81  | 0.00 | 489.00 | 0.80 |
| P0002   | 133.47 | 106.42  | 0.00 | 486.00 | 0.80 |
| P0020   | 138.91 | 110.23  | 0.00 | 484.00 | 0.79 |
| P0014   | 138.88 | 110.20  | 0.00 | 485.00 | 0.79 |
| P0011   | 136.62 | 108.25  | 0.00 | 484.00 | 0.79 |
| P0015   | 138.79 | 109.91  | 0.00 | 482.00 | 0.79 |
| P0013   | 136.97 | 108.15  | 0.00 | 494.00 | 0.79 |
| P0017   | 136.94 | 107.89  | 0.00 | 495.00 | 0.79 |
| P0016   | 139.12 | 109.39  | 0.00 | 492.00 | 0.79 |
| P0005   | 137.80 | 106.85  | 0.00 | 488.00 | 0.78 |

Per-store demand statistics:

| Store | Mean   | Std dev | Min  | Max    | CV   |
| ----- | ------ | ------- | ---- | ------ | ---- |
| S001  | 135.14 | 108.71  | 0.00 | 496.00 | 0.80 |
| S002  | 135.96 | 108.93  | 0.00 | 492.00 | 0.80 |
| S005  | 137.49 | 109.51  | 0.00 | 494.00 | 0.80 |
| S004  | 135.38 | 107.64  | 0.00 | 496.00 | 0.80 |
| S003  | 138.35 | 109.78  | 0.00 | 499.00 | 0.79 |

## Day of week and month patterns

Weekday averages:

| Weekday   | Mean sales | Std dev | Rows     |
| --------- | ---------- | ------- | -------- |
| Monday    | 135.09     | 107.57  | 10500.00 |
| Tuesday   | 137.31     | 109.46  | 10400.00 |
| Wednesday | 136.62     | 109.00  | 10400.00 |
| Thursday  | 137.28     | 108.71  | 10400.00 |
| Friday    | 136.85     | 109.33  | 10400.00 |
| Saturday  | 135.31     | 109.01  | 10500.00 |
| Sunday    | 136.81     | 109.36  | 10500.00 |

Month-of-year averages (all years pooled):

| Month | Mean sales | Std dev | Rows    |
| ----- | ---------- | ------- | ------- |
| 1.00  | 135.97     | 107.05  | 6300.00 |
| 2.00  | 138.61     | 110.29  | 5600.00 |
| 3.00  | 135.90     | 108.46  | 6200.00 |
| 4.00  | 134.74     | 109.61  | 6000.00 |
| 5.00  | 134.43     | 108.45  | 6200.00 |
| 6.00  | 136.86     | 110.06  | 6000.00 |
| 7.00  | 139.44     | 109.01  | 6200.00 |
| 8.00  | 135.71     | 108.68  | 6200.00 |
| 9.00  | 136.16     | 109.20  | 6000.00 |
| 10.00 | 137.50     | 109.61  | 6200.00 |
| 11.00 | 138.44     | 109.71  | 6000.00 |
| 12.00 | 134.03     | 107.04  | 6200.00 |

## Available feature relationships

| Field              | Correlation with Units Sold |
| ------------------ | --------------------------- |
| Demand Forecast    | 1.00                        |
| Inventory Level    | 0.59                        |
| Discount           | 0.00                        |
| Competitor Pricing | 0.00                        |
| Price              | 0.00                        |
| Holiday/Promotion  | -0.00                       |

Correlations do not establish causality. Product and store identifiers are included in the forecasting model, but this table isolates simple numeric correlations.

## Entity-level forecast errors

Five highest-MAE product/store pairs by horizon:

| Horizon | Product | Store | MAE    | RMSE   | sMAPE_pct |
| ------- | ------- | ----- | ------ | ------ | --------- |
| 7.00    | P0020   | S005  | 100.35 | 124.49 | 79.07     |
| 7.00    | P0004   | S005  | 99.93  | 122.83 | 77.05     |
| 7.00    | P0017   | S004  | 99.64  | 119.02 | 74.27     |
| 7.00    | P0012   | S002  | 99.62  | 120.78 | 76.99     |
| 7.00    | P0011   | S001  | 99.31  | 121.94 | 77.15     |
| 14.00   | P0020   | S005  | 100.48 | 124.50 | 79.13     |
| 14.00   | P0004   | S005  | 99.82  | 122.63 | 76.96     |
| 14.00   | P0017   | S004  | 99.56  | 118.98 | 74.23     |
| 14.00   | P0012   | S002  | 99.53  | 120.74 | 76.94     |
| 14.00   | P0014   | S001  | 99.30  | 120.48 | 75.16     |

Five lowest-MAE product/store pairs by horizon:

| Horizon | Product | Store | MAE   | RMSE   | sMAPE_pct |
| ------- | ------- | ----- | ----- | ------ | --------- |
| 7.00    | P0007   | S003  | 75.18 | 100.30 | 55.34     |
| 7.00    | P0013   | S001  | 76.87 | 98.31  | 65.38     |
| 7.00    | P0002   | S005  | 76.93 | 98.49  | 61.09     |
| 7.00    | P0012   | S004  | 78.33 | 94.64  | 64.75     |
| 7.00    | P0005   | S004  | 78.60 | 94.09  | 66.03     |
| 14.00   | P0007   | S003  | 75.13 | 100.26 | 55.32     |
| 14.00   | P0002   | S005  | 76.83 | 98.52  | 61.04     |
| 14.00   | P0013   | S001  | 76.86 | 98.24  | 65.42     |
| 14.00   | P0012   | S004  | 78.30 | 94.68  | 64.73     |
| 14.00   | P0005   | S004  | 78.71 | 94.08  | 66.08     |

All pair-by-method metrics are saved in `forecast_entity_metrics.csv`; sales-range scores are saved in `forecast_sales_level_metrics.csv`.
