"""Unit tests for multi-airline and OTA parser implementations."""
import json
from pathlib import Path

import pytest

from apix.models import Job, Route
from apix.scrapers.airindia import AirIndiaScraper
from apix.scrapers.akasa import AkasaAirScraper
from apix.scrapers.easemytrip import EaseMyTripScraper
from apix.scrapers.spicejet import SpiceJetScraper
from apix.scrapers.yatra import YatraScraper

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_job():
    return Job(
        route=Route("DEL", "BOM"),
        source="airindia",
        lead_days=7,
        travel_date="2026-09-27",
        search_ts="2026-09-20T14:48:25+05:30",
    )


def test_airindia_parser(sample_job):
    fixture_path = FIXTURES_DIR / "airindia_success.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    recs = AirIndiaScraper.parse_airindia_json_data(data, sample_job)
    assert len(recs) == 1
    assert recs[0].carrier == "AI"
    assert recs[0].flight_no == "AI-101"
    assert recs[0].total_fare == 6500.0


def test_akasa_parser(sample_job):
    fixture_path = FIXTURES_DIR / "akasa_success.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    recs = AkasaAirScraper.parse_akasa_json_data(data, sample_job)
    assert len(recs) == 1
    assert recs[0].carrier == "QP"
    assert recs[0].flight_no == "QP-1102"
    assert recs[0].total_fare == 5000.0


def test_spicejet_parser(sample_job):
    fixture_path = FIXTURES_DIR / "spicejet_success.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    recs = SpiceJetScraper.parse_spicejet_json_data(data, sample_job)
    assert len(recs) == 1
    assert recs[0].carrier == "SG"
    assert recs[0].flight_no == "SG-8169"
    assert recs[0].total_fare == 4900.0


def test_easemytrip_parser(sample_job):
    fixture_path = FIXTURES_DIR / "easemytrip_success.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    recs = EaseMyTripScraper.parse_easemytrip_json_data(data, sample_job)
    assert len(recs) == 1
    assert recs[0].carrier == "6E"
    assert recs[0].flight_no == "6E-454"
    assert recs[0].total_fare == 5200.0


def test_yatra_parser(sample_job):
    fixture_path = FIXTURES_DIR / "yatra_success.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    recs = YatraScraper.parse_yatra_json_data(data, sample_job)
    assert len(recs) == 1
    assert recs[0].carrier == "AI"
    assert recs[0].flight_no == "AI-505"
    assert recs[0].total_fare == 6300.0
