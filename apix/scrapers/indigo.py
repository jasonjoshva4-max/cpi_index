"""IndiGo airline scraper implementation for APIx."""
import logging
from typing import Any

from playwright.async_api import Page, Response
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from apix.config import SOURCE_DOMAINS
from apix.models import AirfareRecord, AvailabilityFlag, Job
from apix.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class IndiGoScraper(BaseScraper):
    """Scraper for IndiGo (6E) flights."""

    def __init__(self, **kwargs):
        base_url = kwargs.pop("base_url", SOURCE_DOMAINS.get("indigo", "https://www.goindigo.in"))
        super().__init__(source_id="indigo", base_url=base_url, **kwargs)

    def build_search_url(self, job: Job) -> str:
        """Constructs target URL for IndiGo flight search."""
        return (
            f"{self.base_url}/flight-search.html?"
            f"origin={job.route.origin}&destination={job.route.destination}"
            f"&depDate={job.travel_date}&adults=1"
        )

    @staticmethod
    def parse_indigo_json_data(
        data: dict[str, Any], job: Job
    ) -> list[AirfareRecord]:
        """Parses raw JSON fare response from IndiGo API into AirfareRecord list."""
        records: list[AirfareRecord] = []

        # Support common JSON structures for flight search results
        flights = data.get("flights") or data.get("outboundFlights") or data.get("results") or []
        if not flights and isinstance(data, dict):
            # Check for nested data structures
            if "data" in data and isinstance(data["data"], dict):
                flights = data["data"].get("flights") or data["data"].get("outboundFlights") or []
            elif "journeys" in data and isinstance(data["journeys"], list):
                flights = []
                for journey in data["journeys"]:
                    flights.extend(journey.get("flights", []))

        if not flights:
            # Check if sold out / no flights available flag present in JSON
            availability = "sold_out" if data.get("sold_out") or data.get("no_flights") else "not_shown"
            logger.info(f"No flights found in IndiGo JSON payload for job {job.job_id}")
            return records

        for item in flights:
            carrier = item.get("carrier") or item.get("airlineCode") or "6E"
            flight_no = str(item.get("flightNumber") or item.get("flight_no") or item.get("code") or "")
            if flight_no and not flight_no.startswith("6E"):
                flight_no = f"6E-{flight_no}"

            origin = item.get("origin") or job.route.origin
            destination = item.get("destination") or job.route.destination
            dep_time = str(item.get("departureTime") or item.get("dep_time") or "")
            arr_time = str(item.get("arrivalTime") or item.get("arr_time") or "")
            stops = int(item.get("stops", 0))
            fare_class = item.get("fareClass") or item.get("cabinClass") or item.get("class")

            # Fare components check
            fare_details = item.get("fareDetails") or item.get("fare") or {}
            base_fare = fare_details.get("baseFare") or fare_details.get("base_fare")
            taxes = fare_details.get("taxes")
            udf = fare_details.get("udf")
            convenience_fee = fare_details.get("convenienceFee") or fare_details.get("convenience_fee")
            total_fare_val = (
                fare_details.get("totalFare")
                or fare_details.get("total_fare")
                or item.get("price")
                or item.get("totalPrice")
            )

            # Convert numeric values safely
            total_fare = float(total_fare_val) if total_fare_val is not None else 0.0
            base_fare_float = float(base_fare) if base_fare is not None else None
            taxes_float = float(taxes) if taxes is not None else None
            udf_float = float(udf) if udf is not None else None
            conv_fee_float = float(convenience_fee) if convenience_fee is not None else None

            availability: AvailabilityFlag = "available"
            if item.get("isSoldOut") or item.get("availableSeats", 1) == 0:
                availability = "sold_out"
            elif item.get("isCancelled"):
                availability = "cancelled"

            record = AirfareRecord(
                carrier=carrier,
                flight_no=flight_no,
                origin=origin,
                destination=destination,
                dep_time=dep_time,
                arr_time=arr_time,
                stops=stops,
                fare_class=fare_class,
                base_fare=base_fare_float,
                taxes=taxes_float,
                udf=udf_float,
                convenience_fee=conv_fee_float,
                total_fare=total_fare,
                source=job.source,
                search_ts=job.search_ts,
                travel_date=job.travel_date,
                lead_days=job.lead_days,
                availability_flag=availability,
            )
            records.append(record)

        return records

    async def scrape_page(
        self, page: Page, job: Job
    ) -> tuple[list[AirfareRecord], str | None]:
        """Scrapes flight data via intercepted network response or Playwright DOM selection."""
        from pathlib import Path
        diag_dir = Path("data/raw/diagnostics")
        diag_dir.mkdir(parents=True, exist_ok=True)

        json_captured: list[dict[str, Any]] = []
        network_log: list[dict[str, Any]] = []

        # Handler to capture fare API responses and log all network traffic
        async def handle_response(response: Response):
            try:
                url = response.url
                status = response.status
                content_type = response.headers.get("content-type", "")
                
                log_entry = {
                    "url": url,
                    "status": status,
                    "content_type": content_type,
                }
                network_log.append(log_entry)

                url_lower = url.lower()
                if any(k in url_lower for k in ["flight", "search", "api", "fare", "availability", "booking"]):
                    if status == 200 and "json" in content_type:
                        try:
                            data = await response.json()
                            json_captured.append(data)
                            logger.info(f"[Interception] Captured JSON response from: {url}")
                        except Exception as json_err:
                            logger.debug(f"Failed parsing response JSON from {url}: {json_err}")
            except Exception as e:
                logger.debug(f"Error reading response: {e}")

        page.on("response", handle_response)

        target_url = self.build_search_url(job)
        logger.info(f"Navigating to {target_url} for job {job.job_id}")

        nav_status: int | None = None
        try:
            response = await page.goto(target_url, wait_until="domcontentloaded")
            nav_status = response.status if response else 200
            
            # Allow time for dynamic AJAX requests
            await page.wait_for_timeout(3000)

            final_url = page.url
            page_title = await page.title()
            html_content = await page.content()

            logger.info(f"Page Loaded - Final URL: {final_url} | Title: '{page_title}' | Status: {nav_status}")

            # Diagnostics: CAPTCHA / Consent / Challenge detection
            is_cap = self.is_captcha(nav_status or 200, html_content)
            has_consent = any(c in html_content.lower() for c in ["cookie", "consent", "privacy", "accept all"])
            has_interstitial = any(c in html_content.lower() for c in ["challenge", "access denied", "security check", "verify you are human", "pardon our interruption"])

            logger.info(f"State Check - CAPTCHA: {is_cap} | Consent Text: {has_consent} | Interstitial Text: {has_interstitial}")
            logger.info(f"Network Summary - Total Responses: {len(network_log)} | Captured JSON Payloads: {len(json_captured)}")
            for item in network_log:
                if any(k in item["url"].lower() for k in ["api", "flight", "search", "fare"]):
                    logger.info(f"  Network Item: [{item['status']}] {item['url']} ({item['content_type']})")

            # Save diagnostic screenshot and HTML dump
            screenshot_path = diag_dir / f"indigo_{job.job_id}.png"
            html_path = diag_dir / f"indigo_{job.job_id}.html"
            
            try:
                await page.screenshot(path=str(screenshot_path), full_page=True)
                html_path.write_text(html_content, encoding="utf-8")
                logger.info(f"Saved diagnostic screenshot to {screenshot_path} and HTML to {html_path}")
            except Exception as diag_err:
                logger.warning(f"Could not save diagnostic files: {diag_err}")

            # Check for CAPTCHA/challenge
            if is_cap:
                return [], "CAPTCHA_DETECTED"

            # Check network interception results first
            if json_captured:
                logger.info(f"Captured {len(json_captured)} API network responses for {job.job_id}")
                all_records: list[AirfareRecord] = []
                for data in json_captured:
                    recs = self.parse_indigo_json_data(data, job)
                    all_records.extend(recs)
                if all_records:
                    return all_records, None

            # Fallback: Explicit Playwright wait for DOM results-list element
            selectors = [
                ".flight-search-results",
                ".flight-card",
                ".flight-list-item",
                "div[id*='flight']",
                ".no-flights-found",
            ]
            
            dom_found = False
            for sel in selectors:
                try:
                    await page.wait_for_selector(sel, timeout=3000)
                    dom_found = True
                    break
                except PlaywrightTimeoutError:
                    continue

            if json_captured:
                all_records = []
                for data in json_captured:
                    recs = self.parse_indigo_json_data(data, job)
                    all_records.extend(recs)
                if all_records:
                    return all_records, None

            # Re-check HTML content after DOM wait
            final_html = await page.content()
            if self.is_captcha(200, final_html):
                return [], "CAPTCHA_DETECTED"

            # If no flights found DOM element is present
            if "no flights" in final_html.lower() or "sold out" in final_html.lower():
                logger.info(f"No flights found / sold out indicated on page for job {job.job_id}")
                return [], None

            if not dom_found:
                logger.warning(f"Timeout waiting for flight results selector for job {job.job_id}")
                return [], "DOM_SELECTOR_TIMEOUT"

            return [], None

        except PlaywrightTimeoutError:
            logger.error(f"PlaywrightTimeoutError during page load for job {job.job_id}")
            return [], "PAGE_TIMEOUT"
        except Exception as e:
            logger.error(f"Error scraping IndiGo page for job {job.job_id}: {e}")
            return [], "SCRAPE_EXCEPTION"
