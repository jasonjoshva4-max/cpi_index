"""Runner for APIx job grid expansion, execution, and raw storage writing."""
import logging
import uuid
from datetime import datetime, timedelta, timezone

from playwright.async_api import async_playwright

from apix.config import RAW_DATA_DIR
from apix.models import Job, JobResult, Route, RunMetrics
from apix.rate_limiter import DomainRateLimiter
from apix.robots import RobotsChecker
from apix.scrapers.airindia import AirIndiaScraper
from apix.scrapers.airindiaexpress import AirIndiaExpressScraper
from apix.scrapers.akasa import AkasaAirScraper
from apix.scrapers.base import BaseScraper
from apix.scrapers.easemytrip import EaseMyTripScraper
from apix.scrapers.indigo import IndiGoScraper
from apix.scrapers.spicejet import SpiceJetScraper
from apix.scrapers.yatra import YatraScraper
from apix.storage import RawJSONLStore

logger = logging.getLogger(__name__)

# Registry of available scrapers
SCRAPER_REGISTRY: dict[str, type[BaseScraper]] = {
    "indigo": IndiGoScraper,
    "airindia": AirIndiaScraper,
    "airindiaexpress": AirIndiaExpressScraper,
    "akasa": AkasaAirScraper,
    "spicejet": SpiceJetScraper,
    "easemytrip": EaseMyTripScraper,
    "yatra": YatraScraper,
}



class ScraperRunner:
    """Manages full execution flow for APIx scraper grid."""

    def __init__(self, raw_store: RawJSONLStore = None):
        self.raw_store = raw_store or RawJSONLStore(RAW_DATA_DIR)
        self.rate_limiter = DomainRateLimiter()
        self.robots_checker = RobotsChecker()

    @staticmethod
    def generate_job_grid(
        routes: list[Route],
        sources: list[str],
        lead_windows: list[int],
        search_ts: datetime = None,
    ) -> list[Job]:
        """Expands (routes x sources x windows) into individual Job objects."""
        if search_ts is None:
            search_ts = datetime.now(timezone.utc)

        search_ts_iso = search_ts.isoformat()
        jobs: list[Job] = []

        for source in sources:
            for route in routes:
                for window in lead_windows:
                    travel_dt = search_ts + timedelta(days=window)
                    travel_date_str = travel_dt.strftime("%Y-%m-%d")
                    job = Job(
                        route=route,
                        source=source,
                        lead_days=window,
                        travel_date=travel_date_str,
                        search_ts=search_ts_iso,
                    )
                    jobs.append(job)

        return jobs

    async def run(
        self,
        routes: list[Route],
        sources: list[str],
        lead_windows: list[int],
        run_id: str = None,
    ) -> tuple[RunMetrics, list[JobResult]]:
        """Executes jobs grid sequentially or concurrently per domain rules."""
        if run_id is None:
            run_id = f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

        jobs = self.generate_job_grid(routes, sources, lead_windows)
        metrics = RunMetrics()

        logger.info(f"Starting APIx scraper run '{run_id}' with {len(jobs)} jobs across sources: {sources}")

        # Instantiate active scraper objects per source
        scrapers: dict[str, BaseScraper] = {}
        for s in sources:
            if s in SCRAPER_REGISTRY:
                scrapers[s] = SCRAPER_REGISTRY[s]()
            else:
                logger.error(f"Unknown scraper source '{s}'. Skipping.")

        results: list[JobResult] = []

        async with async_playwright() as p:
            # Launch headless chromium browser
            browser = await p.chromium.launch(headless=True)

            try:
                for job in jobs:
                    metrics.jobs_attempted += 1
                    scraper = scrapers.get(job.source)

                    if not scraper:
                        metrics.parse_errors += 1
                        results.append(
                            JobResult(
                                job=job,
                                status="failed",
                                reason_code="UNKNOWN_SOURCE",
                                error_message=f"No scraper registered for source {job.source}",
                            )
                        )
                        continue

                    # Execute single job
                    res = await scraper.run_job(
                        job, browser, self.rate_limiter, self.robots_checker
                    )
                    results.append(res)

                    if res.status == "success":
                        metrics.jobs_succeeded += 1
                        # Append raw records to raw store
                        if res.records:
                            self.raw_store.write_records(
                                source=job.source,
                                run_id=run_id,
                                records=res.records,
                            )
                    elif res.status == "captcha_blocked":
                        metrics.captcha_backoffs += 1
                    elif res.status in ("failed", "robots_disallowed"):
                        metrics.parse_errors += 1

            finally:
                try:
                    await browser.close()
                except Exception as e:
                    logger.warning(f"Error closing Playwright browser: {e}")

        # Emit mandatory per-run summary log line
        logger.info(metrics.summary_line())

        return metrics, results
