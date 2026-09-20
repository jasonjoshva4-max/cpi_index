#!/usr/bin/env python3
"""Single-job scraper test mode for APIx.

Usage:
    python -m scrapers.run_single --source airindia --origin DEL --destination BOM --lead T7
"""
import argparse
import asyncio
import logging
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

# Add project root to PYTHONPATH if needed
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from apix.config import RAW_DATA_DIR
from apix.models import Job, Route
from apix.rate_limiter import DomainRateLimiter
from apix.robots import RobotsChecker
from apix.runner import SCRAPER_REGISTRY
from apix.storage import RawJSONLStore

logger = logging.getLogger("apix.run_single")


def parse_lead_days(lead_str: str) -> int:
    """Parses lead window strings like 'T7', 'T+7', 't15', '7' into integer lead days."""
    if not lead_str:
        raise ValueError("Lead window string cannot be empty.")
    cleaned = re.sub(r"^[Tt]\+?", "", lead_str.strip())
    try:
        val = int(cleaned)
    except ValueError as e:
        raise ValueError(f"Invalid lead window format '{lead_str}'. Expected formats: 'T7', 'T+7', or '7'.") from e

    if val <= 0:
        raise ValueError(f"Lead days must be > 0, got {val}")
    return val


def build_single_job(source: str, origin: str, destination: str, lead_str: str) -> Job:
    """Constructs a single Job object from CLI arguments."""
    source_clean = source.strip().lower()
    if source_clean not in SCRAPER_REGISTRY:
        raise ValueError(
            f"Unknown source '{source}'. Available registered scrapers: {list(SCRAPER_REGISTRY.keys())}"
        )

    origin_clean = origin.strip().upper()
    dest_clean = destination.strip().upper()
    lead_days = parse_lead_days(lead_str)

    search_ts_dt = datetime.now(timezone.utc)
    search_ts_iso = search_ts_dt.isoformat()
    travel_date = (search_ts_dt + timedelta(days=lead_days)).strftime("%Y-%m-%d")

    route = Route(origin_clean, dest_clean)
    return Job(
        route=route,
        source=source_clean,
        lead_days=lead_days,
        travel_date=travel_date,
        search_ts=search_ts_iso,
    )


async def execute_single_job(
    source: str,
    origin: str,
    destination: str,
    lead_str: str,
    raw_store: RawJSONLStore | None = None,
) -> dict[str, Any]:
    """Executes a single test job adhering to robots.txt compliance and outputs a summary report."""
    if raw_store is None:
        raw_store = RawJSONLStore(RAW_DATA_DIR)

    job = build_single_job(source, origin, destination, lead_str)
    scraper_cls = SCRAPER_REGISTRY[job.source]
    scraper = scraper_cls()

    robots_checker = RobotsChecker()
    rate_limiter = DomainRateLimiter()

    target_url = scraper.build_search_url(job)
    logger.info(f"Checking compliance for target URL: {target_url}")

    # 1. Robots / Compliance Check
    compliance_state = await robots_checker.check_compliance(target_url)
    compliance_display = compliance_state.upper()

    summary: dict[str, Any] = {
        "source": job.source,
        "route": str(job.route),
        "travel_date": job.travel_date,
        "compliance_state": compliance_display,
        "scraper_status": "SKIPPED",
        "reason_code": f"ROBOTS_{compliance_display}",
        "number_of_fares_extracted": 0,
        "raw_output_path": "N/A",
    }

    if compliance_state != "allowed":
        logger.warning(f"Compliance state is {compliance_display}. Stopping single job execution cleanly.")
        summary["scraper_status"] = f"robots_{compliance_state}"
        return summary

    # 2. Execution if Compliance is ALLOWED
    logger.info(f"Compliance state ALLOWED. Launching browser for job {job.job_id}...")
    run_id = f"single_{job.job_id}"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            res = await scraper.run_job(job, browser, rate_limiter, robots_checker)
            summary["scraper_status"] = res.status
            summary["reason_code"] = res.reason_code or "NONE"
            summary["number_of_fares_extracted"] = len(res.records)

            if res.status == "success" and res.records:
                saved_path = raw_store.write_records(
                    source=job.source,
                    run_id=run_id,
                    records=res.records,
                )
                summary["raw_output_path"] = str(saved_path)
        finally:
            try:
                await browser.close()
            except Exception as e:
                logger.warning(f"Error closing Playwright browser: {e}")

    return summary


def print_summary_report(summary: dict[str, Any]):
    """Prints a concise final summary block to stdout."""
    print("\n================ Single Job Run Summary ================")
    print(f"Source                  : {summary['source']}")
    print(f"Route                   : {summary['route']}")
    print(f"Travel Date             : {summary['travel_date']}")
    print(f"Compliance State        : {summary['compliance_state']}")
    print(f"Scraper Status          : {summary['scraper_status']}")
    print(f"Reason Code             : {summary['reason_code']}")
    print(f"Number of Fares         : {summary['number_of_fares_extracted']}")
    print(f"Raw Output Path         : {summary['raw_output_path']}")
    print("========================================================\n")


def main():
    parser = argparse.ArgumentParser(
        description="APIx Single-Job Scraper Test CLI Mode",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--source", required=True, help="Airline or OTA source (e.g. airindia, indigo, spicejet)")
    parser.add_argument("--origin", required=True, help="Origin 3-letter IATA airport code (e.g. DEL)")
    parser.add_argument("--destination", required=True, help="Destination 3-letter IATA airport code (e.g. BOM)")
    parser.add_argument("--lead", required=True, help="Lead window string (e.g. T7, T+7, or 7)")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    try:
        summary = asyncio.run(
            execute_single_job(
                source=args.source,
                origin=args.origin,
                destination=args.destination,
                lead_str=args.lead,
            )
        )
        print_summary_report(summary)
    except Exception as e:
        logger.error(f"Single-job execution error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
