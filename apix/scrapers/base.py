"""Abstract Base Scraper for APIx."""
import abc
import asyncio
import logging
import re

from playwright.async_api import Browser, BrowserContext, Page

from apix.config import (
    DEFAULT_INITIAL_BACKOFF,
    DEFAULT_MAX_RETRIES,
    DEFAULT_PAGE_TIMEOUT,
    DEFAULT_USER_AGENT,
)
from apix.models import AirfareRecord, Job, JobResult
from apix.rate_limiter import DomainRateLimiter
from apix.robots import RobotsChecker

logger = logging.getLogger(__name__)

CAPTCHA_PATTERNS = [
    r"cf-challenge",
    r"cloudflare",
    r"turnstile",
    r"perimeterx",
    r"px-captcha",
    r"px-block",
    r"akamai",
    r"akamfailoverpage",
    r"something went wrong",
    r"sec-cpt",
    r"incapsula",
    r"distil",
    r"captcha",
    r"robotcheck",
    r"security check",
    r"verify you are human",
    r"access denied",
    r"pardon our interruption",
]


class BaseScraper(abc.ABC):
    """Abstract Base Class for airline scrapers."""

    def __init__(
        self,
        source_id: str,
        base_url: str,
        user_agent: str = DEFAULT_USER_AGENT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        initial_backoff: float = DEFAULT_INITIAL_BACKOFF,
        page_timeout: int = DEFAULT_PAGE_TIMEOUT,
    ):
        self.source_id = source_id
        self.base_url = base_url.rstrip("/")
        self.user_agent = user_agent
        self.max_retries = max_retries
        self.initial_backoff = initial_backoff
        self.page_timeout = page_timeout
        self.is_paused: bool = False

    @abc.abstractmethod
    def build_search_url(self, job: Job) -> str:
        """Constructs target search URL for the given job."""

    @abc.abstractmethod
    async def scrape_page(
        self, page: Page, job: Job
    ) -> tuple[list[AirfareRecord], str | None]:
        """Scrapes flight data using Playwright page instance.

        Returns a tuple of (list_of_records, error_or_reason_code).
        """

    def is_captcha(self, status: int, text: str) -> bool:
        """Pattern matches response for CAPTCHA/challenge/bot failover signatures."""
        lower_text = text.lower()
        if status in (403, 429) or True:
            for pattern in CAPTCHA_PATTERNS:
                if re.search(pattern, lower_text):
                    return True

        return False

    async def run_job(
        self,
        job: Job,
        browser: Browser,
        rate_limiter: DomainRateLimiter,
        robots_checker: RobotsChecker,
    ) -> JobResult:
        """Executes a single job with rate limiting, robots check, context isolation, retries & CAPTCHA detection."""
        if self.is_paused:
            logger.warning(
                f"Source '{self.source_id}' is currently PAUSED due to prior CAPTCHA detection. "
                f"Skipping job {job.job_id}."
            )
            return JobResult(
                job=job,
                status="captcha_blocked",
                reason_code="SOURCE_PAUSED_CAPTCHA",
                error_message="Source paused due to earlier CAPTCHA detection.",
            )

        target_url = self.build_search_url(job)

        # 1. Robots.txt Compliance Check
        compliance_state = await robots_checker.check_compliance(target_url)

        if compliance_state == "disallowed":
            logger.warning(f"Robots.txt disallowed URL {target_url} for job {job.job_id}")
            return JobResult(
                job=job,
                status="robots_disallowed",
                reason_code="ROBOTS_DISALLOWED",
                error_message=f"Disallowed by robots.txt: {target_url}",
            )
        elif compliance_state == "unverified":
            self.is_paused = True
            logger.warning(
                f"Robots.txt could not be retrieved from {target_url}. Source '{self.source_id}' "
                f"marked as UNVERIFIED and PAUSED until compliance can be verified."
            )
            return JobResult(
                job=job,
                status="robots_unverified",
                reason_code="ROBOTS_UNVERIFIED",
                error_message=f"Unverified compliance state: robots.txt unfetchable from {target_url}",
            )

        # 2. Domain Rate Limiting
        domain = self.base_url
        await rate_limiter.wait(domain)

        attempt = 0
        last_error_code = "UNKNOWN_FAILURE"
        last_error_msg = ""

        while attempt <= self.max_retries:
            attempt += 1
            logger.info(f"Executing job {job.job_id} (Attempt {attempt}/{self.max_retries + 1})")

            context: BrowserContext | None = None
            try:
                # Fresh browser context per job; isolated cookies
                context = await browser.new_context(
                    user_agent=self.user_agent,
                    viewport={"width": 1280, "height": 800},
                    ignore_https_errors=True,
                )
                page = await context.new_page()
                page.set_default_timeout(self.page_timeout)

                records, reason = await self.scrape_page(page, job)

                if reason == "CAPTCHA_DETECTED":
                    self.is_paused = True
                    logger.error(
                        f"CAPTCHA detected for source '{self.source_id}' during job {job.job_id}. "
                        "Backing off and marking source as PAUSED for this run."
                    )
                    return JobResult(
                        job=job,
                        status="captcha_blocked",
                        reason_code="CAPTCHA_DETECTED",
                        error_message="CAPTCHA / Bot Challenge detected.",
                    )

                if reason is None:
                    # Successful job execution
                    return JobResult(
                        job=job,
                        status="success",
                        records=records,
                    )
                else:
                    last_error_code = reason
                    last_error_msg = f"Scrape failed with reason: {reason}"

            except Exception as e:
                err_str = str(e)
                logger.error(f"Error during job {job.job_id} execution attempt {attempt}: {err_str}")

                # Check if exception content indicates CAPTCHA/403/429
                if "403" in err_str or "429" in err_str or "captcha" in err_str.lower():
                    self.is_paused = True
                    return JobResult(
                        job=job,
                        status="captcha_blocked",
                        reason_code="CAPTCHA_DETECTED_IN_EXCEPTION",
                        error_message=f"CAPTCHA or blocking exception: {err_str}",
                    )

                last_error_code = "EXECUTION_EXCEPTION"
                last_error_msg = err_str

            finally:
                if context:
                    await context.close()

            # Bounded retry with exponential backoff if retries remain
            if attempt <= self.max_retries:
                backoff_time = self.initial_backoff * (2 ** (attempt - 1))
                logger.info(f"Retrying job {job.job_id} in {backoff_time:.2f}s...")
                await asyncio.sleep(backoff_time)

        # Retries exhausted
        return JobResult(
            job=job,
            status="failed",
            reason_code=last_error_code,
            error_message=last_error_msg,
        )
