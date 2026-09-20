# APIx REST API Reference (`docs/api_reference.md`)

Complete specification of all REST API endpoints, query parameters, Pydantic response schemas, and metadata provenance labels.

---

## 1. Global Metadata Response Block

Every JSON response includes a standardized `metadata` block indicating observation counts, cell counts, base period, and claim provenance:

```json
{
  "metadata": {
    "n_obs": 150,
    "n_cells": 6,
    "base_period": "2026-09-20",
    "label": "estimated"
  }
}
```

### Claim Provenance Labels (`label`):
- `"observed"`: Direct raw quote measurements.
- `"estimated"`: Model-derived or aggregate index computations.
- `"signal"`: Coincident contextual events / fuel indicators (never causal claims).

---

## 2. API Endpoints Reference

### 2.1 `GET /api/index`
Returns the latest National APIx level, base-fare series, and percentage change vs previous period.
- **Query Params**: None
- **Response Model**: `IndexLevelResponse` (`label = "estimated"`)

### 2.2 `GET /api/index/daily`
Returns daily APIx index series with optional date range filters and CSV export variant.
- **Query Params**:
  - `start` (string, optional): Start date (YYYY-MM-DD)
  - `end` (string, optional): End date (YYYY-MM-DD)
  - `format` (string, optional): `'json'` or `'csv'`
- **Response Model**: `DailyIndexResponse` or downloadable `text/csv` stream.

### 2.3 `GET /api/routes`
Returns route list with weights, latest route-level index, and volatility tercile bands.
- **Query Params**: None
- **Response Model**: `RoutesResponse` (`label = "estimated"`)

### 2.4 `GET /api/quality`
Returns data quality stats: total quotes, active cells, missing cells, MAD outliers count, and per-carrier availability breakdown.
- **Query Params**: None
- **Response Model**: `QualityResponse` (`label = "estimated"`)

### 2.5 `GET /api/anomalies`
Returns list of flagged fare anomalies and price surges ($Z > 3.5$).
- **Query Params**:
  - `start` (string, optional): YYYY-MM-DD
  - `end` (string, optional): YYYY-MM-DD
- **Response Model**: `AnomaliesResponse` (`label = "estimated"`)

### 2.6 `GET /api/volatility`
Returns 14-day rolling route volatility scores and High/Medium/Low tercile bands.
- **Query Params**: None
- **Response Model**: `VolatilityResponse` (`label = "estimated"`)

### 2.7 `GET /api/events`
Returns list of coinciding events and fuel/macro signals ($\pm 2$ days window).
- **Query Params**:
  - `start` (string, optional): YYYY-MM-DD
  - `end` (string, optional): YYYY-MM-DD
  - `route` (string, optional): e.g. `DEL-BOM`
- **Response Model**: `EventsResponse` (`label = "signal"`)

### 2.8 `GET /api/attribution`
Returns 3-level price movement attribution with explicit un-fudged residual and sample-size gated causal regression ($N \ge 30$).
- **Query Params**:
  - `start` (string, optional): YYYY-MM-DD
  - `end` (string, optional): YYYY-MM-DD
- **Response Model**: `AttributionResponse` (`label = "estimated"`)

### 2.9 `GET /api/forecast`
Returns walk-forward forecast, 95% interval bounds, and side-by-side evaluation against naive baselines.
- **Query Params**:
  - `route` (string, optional): e.g. `DEL-BOM`
  - `horizon` (integer, default 7): Forecast horizon in days (1-30)
- **Response Model**: `ForecastResponse` (`label = "estimated"`)

### 2.10 `GET /api/backtest`
Returns DGCA monthly benchmark correlation, internal airline-vs-OTA quote consistency rate, and lead-time sensitivity analysis.
- **Query Params**: None
- **Response Model**: `BacktestResponse` (`label = "estimated"`)
