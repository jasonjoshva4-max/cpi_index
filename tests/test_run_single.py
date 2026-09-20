"""Unit tests for single-job scraper test CLI runner (scrapers.run_single)."""
from unittest.mock import AsyncMock, patch

import pytest

from apix.models import Job, Route
from scrapers.run_single import (
    build_single_job,
    execute_single_job,
    parse_lead_days,
)


def test_parse_lead_days_valid():
    """Asserts that lead window strings in T7, T+7, t15, and 7 formats parse to integer lead days."""
    assert parse_lead_days("T7") == 7
    assert parse_lead_days("T+7") == 7
    assert parse_lead_days("t15") == 15
    assert parse_lead_days("7") == 7
    assert parse_lead_days("T+45") == 45


def test_parse_lead_days_invalid():
    """Asserts that invalid lead window strings raise ValueError."""
    with pytest.raises(ValueError, match="Invalid lead window format"):
        parse_lead_days("invalid")

    with pytest.raises(ValueError, match="Lead window string cannot be empty"):
        parse_lead_days("")

    with pytest.raises(ValueError, match="Lead days must be > 0"):
        parse_lead_days("T0")


def test_build_single_job_valid():
    """Asserts that valid parameters construct a proper Job object."""
    job = build_single_job("airindia", "DEL", "BOM", "T7")
    assert isinstance(job, Job)
    assert job.source == "airindia"
    assert job.route == Route("DEL", "BOM")
    assert job.lead_days == 7
    assert job.job_id.startswith("airindia_DEL_BOM_T7_")


def test_build_single_job_invalid_source():
    """Asserts that an unregistered scraper source raises ValueError."""
    with pytest.raises(ValueError, match="Unknown source"):
        build_single_job("invalid_airline", "DEL", "BOM", "T7")


@pytest.mark.asyncio
async def test_execute_single_job_unverified_compliance_stops_cleanly():
    """Asserts that UNVERIFIED compliance stops execution cleanly without launching Playwright."""
    with patch("scrapers.run_single.RobotsChecker") as MockRobotsChecker:
        mock_checker = MockRobotsChecker.return_value
        mock_checker.check_compliance = AsyncMock(return_value="unverified")

        summary = await execute_single_job(
            source="airindia",
            origin="DEL",
            destination="BOM",
            lead_str="T7",
        )

        assert summary["source"] == "airindia"
        assert summary["route"] == "DEL-BOM"
        assert summary["compliance_state"] == "UNVERIFIED"
        assert summary["scraper_status"] == "robots_unverified"
        assert summary["reason_code"] == "ROBOTS_UNVERIFIED"
        assert summary["number_of_fares_extracted"] == 0
        assert summary["raw_output_path"] == "N/A"


@pytest.mark.asyncio
async def test_execute_single_job_disallowed_compliance_stops_cleanly():
    """Asserts that DISALLOWED compliance stops execution cleanly."""
    with patch("scrapers.run_single.RobotsChecker") as MockRobotsChecker:
        mock_checker = MockRobotsChecker.return_value
        mock_checker.check_compliance = AsyncMock(return_value="disallowed")

        summary = await execute_single_job(
            source="indigo",
            origin="DEL",
            destination="BLR",
            lead_str="T15",
        )

        assert summary["compliance_state"] == "DISALLOWED"
        assert summary["scraper_status"] == "robots_disallowed"
        assert summary["reason_code"] == "ROBOTS_DISALLOWED"
        assert summary["number_of_fares_extracted"] == 0
