"""Air India (AI) scraper for APIx."""
import logging
from typing import Any

from playwright.async_api import Page, Response

from apix.models import AirfareRecord, Job
from apix.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class AirIndiaScraper(BaseScraper):
    """Scraper for Air India (AI)."""

    def __init__(self, **kwargs):
        base_url = kwargs.pop("base_url", "https://www.airindia.com")
        super().__init__(source_id="airindia", base_url=base_url, **kwargs)

    def build_search_url(self, job: Job) -> str:
        return f"{self.base_url}/flight-search?origin={job.route.origin}&destination={job.route.destination}&date={job.travel_date}"

    @staticmethod
    def parse_airindia_json_data(data: dict[str, Any], job: Job) -> list[AirfareRecord]:
        records = []
        flights = data.get("outboundFlights") or data.get("flights") or data.get("data", {}).get("flights", [])

        for item in flights:
            carrier = item.get("carrier") or "AI"
            flight_no = str(item.get("flightNumber") or item.get("flight_no") or "")
            if flight_no and not flight_no.startswith("AI"):
                flight_no = f"AI-{flight_no}"

            origin = item.get("origin") or job.route.origin
            destination = item.get("destination") or job.route.destination
            dep_time = str(item.get("departureTime") or "")
            arr_time = str(item.get("arrivalTime") or "")
            stops = int(item.get("stops", 0))
            fare_class = item.get("fareClass") or "Economy"

            base_fare = item.get("baseFare")
            taxes = item.get("taxes")
            total_fare = float(item.get("totalFare") or item.get("price") or 0.0)

            rec = AirfareRecord(
                carrier=carrier,
                flight_no=flight_no,
                origin=origin,
                destination=destination,
                dep_time=dep_time,
                arr_time=arr_time,
                stops=stops,
                fare_class=fare_class,
                base_fare=float(base_fare) if base_fare is not None else None,
                taxes=float(taxes) if taxes is not None else None,
                udf=None,
                convenience_fee=None,
                total_fare=total_fare,
                source=job.source,
                search_ts=job.search_ts,
                travel_date=job.travel_date,
                lead_days=job.lead_days,
                availability_flag="available" if total_fare > 0 else "sold_out",
            )
            records.append(rec)
        return records

    async def scrape_page(self, page: Page, job: Job) -> tuple[list[AirfareRecord], str | None]:
        json_captured = []

        async def handle_response(response: Response):
            try:
                url = response.url.lower()
                if "flight-search" in url or "api/flights" in url:
                    if response.status == 200 and "json" in response.headers.get("content-type", ""):
                        data = await response.json()
                        json_captured.append(data)
            except Exception:
                pass

        page.on("response", handle_response)
        target_url = self.build_search_url(job)

        try:
            res = await page.goto(target_url, wait_until="domcontentloaded")
            status = res.status if res else 200
            html = await page.content()

            if self.is_captcha(status, html):
                return [], "CAPTCHA_DETECTED"

            if json_captured:
                all_recs = []
                for d in json_captured:
                    all_recs.extend(self.parse_airindia_json_data(d, job))
                if all_recs:
                    return all_recs, None

            return [], None
        except Exception as e:
            return [], str(e)
