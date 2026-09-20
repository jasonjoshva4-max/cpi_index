"""Air India Express (IX) scraper for APIx."""
import logging
from typing import Any

from playwright.async_api import Page, Response

from apix.models import AirfareRecord, Job
from apix.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class AirIndiaExpressScraper(BaseScraper):
    """Scraper for Air India Express (IX)."""

    def __init__(self, **kwargs):
        base_url = kwargs.pop("base_url", "https://www.airindiaexpress.in")
        super().__init__(source_id="airindiaexpress", base_url=base_url, **kwargs)

    def build_search_url(self, job: Job) -> str:
        return f"{self.base_url}/search?from={job.route.origin}&to={job.route.destination}&date={job.travel_date}"

    @staticmethod
    def parse_airindiaexpress_json_data(data: dict[str, Any], job: Job) -> list[AirfareRecord]:
        records = []
        flights = data.get("flights") or data.get("availability", [])
        for item in flights:
            carrier = item.get("carrier") or "IX"
            flight_no = str(item.get("flightNumber") or "")
            if flight_no and not flight_no.startswith("IX"):
                flight_no = f"IX-{flight_no}"

            total_fare = float(item.get("price") or item.get("totalFare") or 0.0)
            rec = AirfareRecord(
                carrier=carrier,
                flight_no=flight_no,
                origin=job.route.origin,
                destination=job.route.destination,
                dep_time=str(item.get("depTime") or ""),
                arr_time=str(item.get("arrTime") or ""),
                stops=int(item.get("stops", 0)),
                fare_class=item.get("class", "Economy"),
                base_fare=None,
                taxes=None,
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

        async def handle_response(res: Response):
            try:
                if "search" in res.url.lower() and "json" in res.headers.get("content-type", ""):
                    data = await res.json()
                    json_captured.append(data)
            except Exception:
                pass

        page.on("response", handle_response)
        try:
            res = await page.goto(self.build_search_url(job), wait_until="domcontentloaded")
            if json_captured:
                recs = []
                for d in json_captured:
                    recs.extend(self.parse_airindiaexpress_json_data(d, job))
                return recs, None
            return [], None
        except Exception as e:
            return [], str(e)
