"""Rate limiter for domain-level request throttling."""
import asyncio
import logging
import random
import time

from apix.config import DEFAULT_MAX_JOB_GAP, DEFAULT_MIN_JOB_GAP

logger = logging.getLogger(__name__)


class DomainRateLimiter:
    """Ensures randomized delay between jobs targeting the same domain to prevent bursts."""

    def __init__(
        self,
        min_gap: float = DEFAULT_MIN_JOB_GAP,
        max_gap: float = DEFAULT_MAX_JOB_GAP,
    ):
        self.min_gap = min_gap
        self.max_gap = max_gap
        self._locks: dict[str, asyncio.Lock] = {}
        self._last_request_time: dict[str, float] = {}

    def _get_lock(self, domain: str) -> asyncio.Lock:
        if domain not in self._locks:
            self._locks[domain] = asyncio.Lock()
        return self._locks[domain]

    async def wait(self, domain: str):
        """Enforces rate limit gap before proceeding with job for domain."""
        lock = self._get_lock(domain)
        async with lock:
            last_time = self._last_request_time.get(domain, 0.0)
            now = time.time()
            gap = now - last_time

            target_gap = random.uniform(self.min_gap, self.max_gap)
            if gap < target_gap:
                sleep_duration = target_gap - gap
                logger.debug(f"Rate limiting domain '{domain}': sleeping for {sleep_duration:.2f}s")
                await asyncio.sleep(sleep_duration)

            self._last_request_time[domain] = time.time()
