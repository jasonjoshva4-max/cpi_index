# APIx Operational Runbook (`docs/runbook.md`)

Operational guide for system administrators, data engineers, and operators managing APIx scrapers, pipelines, and dashboard deployments.

---

## 1. Starting the Daily Scheduler & Execution

### 1.1 Running via Cron / CLI
Execute the cron-ready entrypoint directly:
```bash
python scrapers/run_daily.py
```
This expands the target grid ($6 \text{ routes} \times 7 \text{ sources} \times 5 \text{ windows} = 210 \text{ jobs}$), enforces domain rate limiting, checks `robots.txt`, and persists raw quotes to `data/raw/{source}/{run_id}.jsonl`.

### 1.2 Running via Docker Compose
To launch PostgreSQL, FastAPI, Streamlit Dashboard, and the Scraper worker:
```bash
docker-compose up --build
```
- **FastAPI OpenAPI UI**: `http://localhost:8000/docs`
- **Streamlit Dashboard**: `http://localhost:8501`

---

## 2. Handling CAPTCHA / Bot Challenge Backoff Alerts

### 2.1 Automated Protection Policy
When a Cloudflare, Akamai, or PerimeterX challenge is detected:
1. The scraper logs the event (`status = "captcha_blocked"`, `reason_code = "CAPTCHA_DETECTED"`).
2. The source state is automatically marked as **PAUSED** (`is_paused = True`) for the current run.
3. Remaining jobs for that source in the run are safely skipped.
4. **No bypass or CAPTCHA solving is attempted.**

### 2.2 Operator Incident Resolution
If a source triggers repeated CAPTCHA backoffs:
1. Inspect run logs: `grep "CAPTCHA" data/logs/run.log`.
2. Verify if `robots.txt` rules have changed.
3. Update User-Agent contact header in `apix/config.py` if contact info has changed.
4. If the source remains blocked, switch to fallback dataset ingestion or GDS API fallback per [`docs/sources.md`](file:///c:/Users/User/Downloads/APIX/docs/sources.md).

---

## 3. Re-Running Cleaning Pipeline from Raw Storage

The raw JSON Lines store (`data/raw/{source}/{run_id}.jsonl`) is append-only and never edited in place.

To re-run validation, normalization, deduplication, MAD outlier detection, and DB loading for a past `run_id`:
```python
from apix.pipeline.clean import CleanerPipeline

cleaner = CleanerPipeline()
cleaner.run_pipeline_for_raw_run(run_id="run_20260920_092541_62f8b5", source="indigo")
```
Because the pipeline is **idempotent**, existing rows for `run_id` are cleared and re-inserted cleanly.

---

## 4. Rotating In a New Data Source

To add a new airline or OTA source `newsource`:
1. Check `https://www.newsource.com/robots.txt` for scraping permissions.
2. Create scraper class `NewSourceScraper` in `apix/scrapers/newsource.py` inheriting from `BaseScraper`.
3. Implement `build_search_url()` and static parser `parse_newsource_json_data()`.
4. Register the scraper in `SCRAPER_REGISTRY` inside [`apix/runner.py`](file:///c:/Users/User/Downloads/APIX/apix/runner.py).
5. Add sample response fixture to `tests/fixtures/newsource_success.json`.
6. Add parser unit test to [`tests/test_scrapers.py`](file:///c:/Users/User/Downloads/APIX/tests/test_scrapers.py).

---

## 5. Demo Hardening Mode (Offline Frozen Snapshot)

For reliable live demo presentations where live web scraping might experience network delays:
Set the environment variable `APIX_USE_CACHE=1`:
```bash
# Windows PowerShell
$env:APIX_USE_CACHE="1"
python scrapers/run_daily.py

# Linux / macOS
APIX_USE_CACHE=1 python scrapers/run_daily.py
```
This forces the API and dashboard to run against frozen reference snapshot data without requiring live network calls.
