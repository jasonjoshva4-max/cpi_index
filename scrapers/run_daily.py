#!/usr/bin/env python3
"""Cron-ready daily entrypoint for APIx airfare price index scraper.

Expands full (routes x sources x windows) grid:
- 6 Directed Routes: DEL-BOM, DEL-BLR, BOM-BLR, DEL-CCU, BLR-HYD, MAA-DEL
- 7 Sources: indigo, airindia, airindiaexpress, akasa, spicejet, easemytrip, yatra
- 5 Lead Windows: T+1, T+7, T+15, T+30, T+45
Total Grid Size: 6 x 7 x 5 = 210 jobs (or 300 jobs with fallback OTA slots)
"""
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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger("apix.run_daily")


async def main():
    logger.info("Initializing APIx daily cron scraper job with full basket coverage...")

    # Ensure DGCA route weights are seeded
    seed_routes_and_weights()

    # Full Basket Target Grid
    sources = [
        "indigo",
        "airindia",
        "airindiaexpress",
        "akasa",
        "spicejet",
        "easemytrip",
        "yatra",
    ]
    routes = [
        Route("DEL", "BOM"),
        Route("DEL", "BLR"),
        Route("BOM", "BLR"),
        Route("DEL", "CCU"),
        Route("BLR", "HYD"),
        Route("MAA", "DEL"),
    ]
    lead_windows = [1, 7, 15, 30, 45]  # T+1, T+7, T+15, T+30, T+45

    runner = ScraperRunner()
    grid = runner.generate_job_grid(routes, sources, lead_windows)
    logger.info(f"Grid expanded to {len(grid)} jobs ({len(routes)} routes x {len(sources)} sources x {len(lead_windows)} windows)")

    metrics, results = await runner.run(
        routes=routes,
        sources=sources,
        lead_windows=lead_windows,
    )

    print("\n--- Daily Run Execution Summary ---")
    print(metrics.summary_line())
    print("------------------------------------\n")


if __name__ == "__main__":
    asyncio.run(main())
