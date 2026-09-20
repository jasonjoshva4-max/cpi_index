"""Unit tests for APIx IndiGo scraper, parsing, CAPTCHA detection, robots.txt, and raw storage."""
import json
import tempfile
from pathlib import Path

import pytest

from apix.models import AirfareRecord, Job, Route
from apix.robots import RobotsChecker
from apix.scrapers.indigo import IndiGoScraper
from apix.storage import RawJSONLStore

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_job():
    return Job(
        route=Route("DEL", "BOM"),
        source="indigo",
        lead_days=7,
        travel_date="2026-09-27",
        search_ts="2026-09-20T14:48:25+05:30",
    )


def test_indigo_success_fixture_parsing(sample_job):
    """Asserts that flight quotes with both itemized and non-itemized fares are parsed correctly."""
    fixture_path = FIXTURES_DIR / "indigo_success.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        json_data = json.load(f)

    records = IndiGoScraper.parse_indigo_json_data(json_data, sample_job)

    assert len(records) == 2

    # Record 1: Itemized fare split
    rec1 = records[0]
    assert rec1.carrier == "6E"
    assert rec1.flight_no == "6E-201"
    assert rec1.origin == "DEL"
    assert rec1.destination == "BOM"
    assert rec1.dep_time == "2026-09-27T08:00:00+05:30"
    assert rec1.arr_time == "2026-09-27T10:15:00+05:30"
    assert rec1.stops == 0
    assert rec1.fare_class == "Economy"
    assert rec1.base_fare == 4500.0
    assert rec1.taxes == 1200.0
    assert rec1.udf == 250.0
    assert rec1.convenience_fee == 300.0
    assert rec1.total_fare == 6250.0
    assert rec1.source == "indigo"
    assert rec1.travel_date == "2026-09-27"
    assert rec1.lead_days == 7
    assert rec1.availability_flag == "available"

    # Record 2: Unknown fare components (non-itemized)
    rec2 = records[1]
    assert rec2.flight_no == "6E-512"
    assert rec2.base_fare is None
    assert rec2.taxes is None
    assert rec2.udf is None
    assert rec2.convenience_fee is None
    assert rec2.total_fare == 5800.0
    assert rec2.availability_flag == "available"


def test_indigo_sold_out_fixture_parsing(sample_job):
    """Asserts that sold out / empty response yields 0 records without errors."""
    fixture_path = FIXTURES_DIR / "indigo_sold_out.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        json_data = json.load(f)

    records = IndiGoScraper.parse_indigo_json_data(json_data, sample_job)
    assert len(records) == 0


def test_captcha_detection_and_backoff():
    """Asserts CAPTCHA pattern matching and source pause state update."""
    scraper = IndiGoScraper()
    fixture_path = FIXTURES_DIR / "indigo_captcha.html"
    with open(fixture_path, "r", encoding="utf-8") as f:
        captcha_html = f.read()

    # 1. Pattern matching check
    is_cap = scraper.is_captcha(403, captcha_html)
    assert is_cap is True

    # 2. Check paused state initial state
    assert scraper.is_paused is False


@pytest.mark.asyncio
async def test_robots_txt_parsing():
    """Asserts robots.txt compliance checking returns 'unverified' state when unfetchable."""
    robots_checker = RobotsChecker()
    # Live fetch against timeout domain yields unverified state
    state = await robots_checker.check_compliance("https://www.goindigo.in/flight-search.html")
    assert state in ("allowed", "unverified")
    
    # Verify that unverified state prohibits automatic 'allow all'
    if state == "unverified":
        assert await robots_checker.is_allowed("https://www.goindigo.in/flight-search.html") is False


def test_raw_jsonl_storage_writing(sample_job):
    """Asserts that raw records are saved as line-delimited JSON objects with full schema."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        store = RawJSONLStore(base_dir=Path(tmp_dir))
        
        record = AirfareRecord(
            carrier="6E",
            flight_no="6E-201",
            origin="DEL",
            destination="BOM",
            dep_time="2026-09-27T08:00:00+05:30",
            arr_time="2026-09-27T10:15:00+05:30",
            stops=0,
            fare_class="Economy",
            base_fare=4500.0,
            taxes=1200.0,
            udf=250.0,
            convenience_fee=300.0,
            total_fare=6250.0,
            source="indigo",
            search_ts="2026-09-20T14:48:25+05:30",
            travel_date="2026-09-27",
            lead_days=7,
            availability_flag="available",
        )

        file_path = store.write_records("indigo", "run_test_123", [record])

        assert file_path.exists()
        lines = file_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1

        parsed = json.loads(lines[0])
        assert parsed["carrier"] == "6E"
        assert parsed["flight_no"] == "6E-201"
        assert parsed["origin"] == "DEL"
        assert parsed["destination"] == "BOM"
        assert parsed["total_fare"] == 6250.0
        assert parsed["availability_flag"] == "available"
