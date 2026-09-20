# APIx Data Dictionary (`docs/data_dictionary.md`)

Complete data schema reference for all database tables and columns across APIx (Phases 1 through 8).

---

## 1. `raw_quotes`
Stores raw, unmodified scraped JSON payloads as append-only records.

| Column Name | Data Type | Nullable | Description |
| :--- | :--- | :--- | :--- |
| `id` | Integer (PK) | No | Auto-incrementing primary key |
| `run_id` | String | No | Unique scraper execution run identifier |
| `source` | String | No | Source identifier (e.g. `indigo`, `airindia`, `easemytrip`) |
| `payload` | JSON / JSONB | No | Full raw JSON response dict |
| `scraped_at` | String (ISO 8601) | No | UTC timestamp when scraped |

---

## 2. `fares_clean`
Cleaned, validated, normalized, and deduplicated airfare quotes.

| Column Name | Data Type | Nullable | Description |
| :--- | :--- | :--- | :--- |
| `quote_id` | String (PK) | No | SHA-256 deterministic unique quote hash |
| `route_id` | String | No | Directed sector IATA code pair (e.g. `DEL-BOM`) |
| `carrier` | String | No | Standardized airline IATA code (`6E`, `AI`, `QP`, `SG`) |
| `flight_no` | String | No | Flight number string (e.g. `6E-201`) |
| `lead_days` | Integer | No | Advance purchase window ($1, 7, 15, 30, 45$) |
| `fare_type` | String | No | Cabin class (default `economy`) |
| `base_fare` | Float | Yes | Itemized base fare (NULL if source un-itemized) |
| `taxes` | Float | Yes | Itemized taxes (NULL if source un-itemized) |
| `udf` | Float | Yes | User Development Fee |
| `conv_fee` | Float | Yes | Convenience fee |
| `total_fare` | Float | No | Total ticket fare |
| `search_date` | String (YYYY-MM-DD)| No | Date search was executed |
| `travel_date` | String (YYYY-MM-DD)| No | Target date of flight departure |
| `stops` | Integer | No | Number of intermediate stops ($0$ for non-stop) |
| `dep_band` | String | No | Time band (`early_morning`, `morning`, `afternoon`, `evening`, `night`) |
| `status` | String | No | Availability flag (`available`, `sold_out`, `cancelled`) |
| `outlier_flag` | Boolean | No | Robust MAD outlier flag ($M_i > 3.5$) |
| `run_id` | String | No | Scraper run ID |

---

## 3. `routes`
Air route metadata and DGCA passenger traffic volume weights.

| Column Name | Data Type | Nullable | Description |
| :--- | :--- | :--- | :--- |
| `route_id` | String (PK) | No | Sector ID (e.g. `DEL-BOM`) |
| `origin` | String | No | Origin IATA code |
| `destination` | String | No | Destination IATA code |
| `dgca_pax` | Float | No | DGCA monthly passenger volume |
| `weight` | Float | No | Normalized route weight $w_r$ ($\sum w_r = 1.0$) |
| `active` | Boolean | No | Active status flag |

---

## 4. `apix_daily` / `apix_weekly` / `apix_monthly`
National APIx price index series.

| Column Name | Data Type | Nullable | Description |
| :--- | :--- | :--- | :--- |
| `date` | String (PK) | No | Date string (YYYY-MM-DD or YYYY-MM) |
| `level` | Float | No | Total fare APIx index level (Base = 100.0) |
| `base_fare_level` | Float | Yes | Base fare APIx index level |
| `tax_level` | Float | Yes | Taxes & fees component index level |
| `n_cells` | Integer | No | Count of active elementary cells |

---

## 5. `anomalies`
Flagged fare surges and price drops per route and lead window.

| Column Name | Data Type | Nullable | Description |
| :--- | :--- | :--- | :--- |
| `id` | Integer (PK) | No | Primary key |
| `route_id` | String | No | Route sector ID |
| `date` | String (YYYY-MM-DD) | No | Search date |
| `lead_days` | Integer | No | Lead time window |
| `score` | Float | No | Robust Z-score |
| `pct_from_expected` | Float | No | % deviation from rolling median |
| `direction` | String | No | `surge` or `drop` |
| `flag` | Boolean | No | Active anomaly flag |

---

## 6. `volatility`
Route volatility scores and High/Medium/Low tercile bands.

| Column Name | Data Type | Nullable | Description |
| :--- | :--- | :--- | :--- |
| `id` | Integer (PK) | No | Primary key |
| `route_id` | String | No | Route sector ID |
| `window_end` | String (YYYY-MM-DD) | No | End date of 14-day rolling window |
| `value` | Float | No | Standard deviation of log returns $\text{std}(\ln(p_t / p_{t-1}))$ |
| `band` | String | No | `High`, `Medium`, or `Low` tercile ranking |

---

## 7. `events`
Curated events calendar dataset.

| Column Name | Data Type | Nullable | Description |
| :--- | :--- | :--- | :--- |
| `event_id` | String (PK) | No | Event identifier (e.g. `EVT_001`) |
| `date_start` | String (YYYY-MM-DD) | No | Start date |
| `date_end` | String (YYYY-MM-DD) | No | End date |
| `type` | String | No | `festival`, `holiday`, `disruption`, `weather` |
| `region` | String | No | Origin/destination airport or `National` |
| `source` | String | No | Source calendar registry |
| `note` | String | Yes | Event description |

---

## 8. `macro_series`
Macroeconomic indicator series.

| Column Name | Data Type | Nullable | Description |
| :--- | :--- | :--- | :--- |
| `id` | Integer (PK) | No | Primary key |
| `date` | String (YYYY-MM-DD) | No | Date |
| `series` | String | No | `atf_price_kl`, `brent_crude_bbl`, `usdinr_rate` |
| `value` | Float | No | Metric value |

---

## 9. `forecasts`
Walk-forward forecast runs, interval spreads, and accuracy metrics.

| Column Name | Data Type | Nullable | Description |
| :--- | :--- | :--- | :--- |
| `id` | Integer (PK) | No | Primary key |
| `run_date` | String (YYYY-MM-DD) | No | Execution date |
| `target_date` | String (YYYY-MM-DD) | No | Forecast target date |
| `route_id` | String | Yes | Route ID or NULL for National |
| `level` | Float | No | Point forecast |
| `lower` | Float | No | Lower 95% interval bound |
| `upper` | Float | No | Upper 95% interval bound |
| `model` | String | No | Model name or `seasonal_naive` |
| `beats_baselines` | Boolean | No | Flag indicating if model beat baselines |
| `mae` | Float | Yes | Mean Absolute Error |
| `mape` | Float | Yes | Mean Absolute Percentage Error |
