#!/usr/bin/env python3
"""Run a single test job: DEL -> BOM, T+7, source=indigo."""
import asyncio
import logging
import sys
from pathlib import Path

# Add project root to PYTHONPATH
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from apix.models import Route
from apix.runner import ScraperRunner
from apix.db.seed import seed_routes_and_weights

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger("apix.run_single_job")


async def main():
    logger.info("Executing single test job: DEL -> BOM | T+7 | source=indigo...")
    seed_routes_and_weights()

    sources = ["indigo"]
    routes = [Route("DEL", "BOM")]
    lead_windows = [7]

    runner = ScraperRunner()
    metrics, results = await runner.run(
        routes=routes,
        sources=sources,
        lead_windows=lead_windows,
        run_id="run_indigo_test_single",
    )

    print("\n--- Single Job Run Execution Summary ---")
    print(metrics.summary_line())
    print("Results:")
    for res in results:
        print(f"  Job ID: {res.job.job_id} | Status: {res.status} | Reason: {res.reason_code} | Records: {len(res.records)}")
        if res.error_message:
            print(f"  Error: {res.error_message}")
    print("----------------------------------------\n")


if __name__ == "__main__":
    asyncio.run(main())
