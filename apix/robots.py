"""Robots.txt parser and checker for APIx."""
import logging
from typing import Literal
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from apix.config import DEFAULT_USER_AGENT

logger = logging.getLogger(__name__)

ComplianceStatus = Literal["allowed", "disallowed", "unverified"]


class RobotsChecker:
    """Fetches and parses robots.txt for target domains with explicit compliance states."""

    def __init__(self, user_agent: str = DEFAULT_USER_AGENT):
        self.user_agent = user_agent
        self._parsers: dict[str, RobotFileParser | None] = {}
        self._compliance_states: dict[str, ComplianceStatus] = {}

    async def fetch_and_parse(self, base_url: str) -> tuple[RobotFileParser | None, ComplianceStatus]:
        """Fetches robots.txt. Returns (parser, compliance_state)."""
        parsed_url = urlparse(base_url)
        domain = f"{parsed_url.scheme}://{parsed_url.netloc}"

        if domain in self._compliance_states:
            return self._parsers.get(domain), self._compliance_states[domain]

        robots_url = f"{domain}/robots.txt"
        rfp = RobotFileParser()
        rfp.set_url(robots_url)

        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                response = await client.get(robots_url, headers={"User-Agent": self.user_agent})
                if response.status_code == 200:
                    rfp.parse(response.text.splitlines())
                    logger.info(f"Successfully fetched and parsed robots.txt for {domain}")
                    self._parsers[domain] = rfp
                    self._compliance_states[domain] = "allowed"
                    return rfp, "allowed"
                elif response.status_code == 404:
                    logger.info(f"robots.txt returned 404 Not Found for {domain}. Standard web convention permits access.")
                    rfp.parse([])
                    self._parsers[domain] = rfp
                    self._compliance_states[domain] = "allowed"
                    return rfp, "allowed"
                else:
                    logger.warning(
                        f"robots.txt returned non-standard status {response.status_code} for {domain}. "
                        "Marking compliance state as UNVERIFIED."
                    )
                    self._parsers[domain] = None
                    self._compliance_states[domain] = "unverified"
                    return None, "unverified"
        except Exception as e:
            logger.error(
                f"Error fetching robots.txt from {robots_url}: {e}. "
                "Compliance state set to UNVERIFIED (cannot retrieve robots.txt)."
            )
            self._parsers[domain] = None
            self._compliance_states[domain] = "unverified"
            return None, "unverified"

    async def check_compliance(self, target_url: str) -> ComplianceStatus:
        """Returns explicit compliance state: 'allowed', 'disallowed', or 'unverified'."""
        rfp, base_state = await self.fetch_and_parse(target_url)
        if base_state == "unverified" or rfp is None:
            return "unverified"

        allowed = rfp.can_fetch(self.user_agent, target_url)
        if allowed:
            return "allowed"
        else:
            logger.warning(f"Robots.txt explicitly disallows path: {target_url}")
            return "disallowed"

    async def is_allowed(self, target_url: str) -> bool:
        """Strict check: returns True ONLY if compliance is explicitly verified as 'allowed'."""
        state = await self.check_compliance(target_url)
        return state == "allowed"
