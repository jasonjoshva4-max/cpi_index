"""Unit tests for cleaning pipeline validation, deduplication, MAD outlier detection, component splitting, and idempotency."""
import pytest

from apix.db.database import get_db, init_db
from apix.db.models import FareClean, RawQuote
from apix.pipeline.clean import CleanerPipeline


@pytest.fixture
def cleaner():
    init_db()
    return CleanerPipeline()


def test_duplicate_record_filtering(cleaner):
    """Asserts deduplication logic removes duplicate quotes matching identical key."""
    raw_recs = [
        {
            "carrier": "6E",
            "flight_no": "6E-201",
            "origin": "DEL",
            "destination": "BOM",
            "travel_date": "2026-09-27",
            "search_ts": "2026-09-20T14:48:25+05:30",
            "fare_class": "Economy",
            "total_fare": 6250.0,
            "source": "indigo",
            "availability_flag": "available",
        },
        {
            "carrier": "6E",
            "flight_no": "6E-201",
            "origin": "DEL",
            "destination": "BOM",
            "travel_date": "2026-09-27",
            "search_ts": "2026-09-20T14:48:25+05:30",
            "fare_class": "Economy",
            "total_fare": 6250.0,
            "source": "indigo",
            "availability_flag": "available",
        },
    ]

    cleaned, reject_count = cleaner.process_raw_records(raw_recs, "run_dedup_test")

    assert reject_count == 0
    assert len(cleaned) == 1
    assert cleaned[0]["flight_no"] == "6E-201"


def test_sold_out_record_flagging(cleaner):
    """Asserts sold-out flight is flagged correctly with status='sold_out' and zero total_fare handled."""
    raw_rec = {
        "carrier": "6E",
        "flight_no": "6E-305",
        "origin": "DEL",
        "destination": "BLR",
        "travel_date": "2026-09-27",
        "search_ts": "2026-09-20T14:48:25+05:30",
        "fare_class": "Economy",
        "total_fare": 0.0,
        "source": "indigo",
        "availability_flag": "sold_out",
    }

    is_valid, reason = cleaner.validate_record(raw_rec)
    assert is_valid is True

    norm = cleaner.normalize_record(raw_rec, "run_sold_out_test")
    assert norm["status"] == "sold_out"
    assert norm["total_fare"] == 0.0


def test_mad_outlier_record_detection(cleaner):
    """Asserts MAD robust outlier detection flags extreme fares without deleting them."""
    raw_recs = [
        {"carrier": "6E", "flight_no": f"6E-{100+i}", "origin": "DEL", "destination": "BOM", "travel_date": "2026-09-27", "search_ts": "2026-09-20T14:48:25+05:30", "fare_class": "economy", "total_fare": f, "source": "indigo", "availability_flag": "available", "lead_days": 7}
        for i, f in enumerate([5000.0, 5100.0, 5050.0, 5200.0, 25000.0])
    ]

    cleaned, _ = cleaner.process_raw_records(raw_recs, "run_outlier_test")

    assert len(cleaned) == 5
    # The 25000 fare must be flagged as an outlier
    outlier_rec = [r for r in cleaned if r["total_fare"] == 25000.0][0]
    assert outlier_rec["outlier_flag"] is True

    # Normal fares must not be flagged
    normal_recs = [r for r in cleaned if r["total_fare"] < 10000.0]
    for r in normal_recs:
        assert r["outlier_flag"] is False


def test_missing_component_record(cleaner):
    """Asserts un-itemized fares preserve total_fare while leaving base_fare and taxes as None."""
    raw_rec = {
        "carrier": "6E",
        "flight_no": "6E-512",
        "origin": "DEL",
        "destination": "BOM",
        "travel_date": "2026-09-27",
        "search_ts": "2026-09-20T14:48:25+05:30",
        "base_fare": None,
        "taxes": None,
        "total_fare": 5800.0,
        "source": "indigo",
        "availability_flag": "available",
    }

    norm = cleaner.normalize_record(raw_rec, "run_missing_comp_test")
    assert norm["base_fare"] is None
    assert norm["taxes"] is None
    assert norm["total_fare"] == 5800.0


def test_pipeline_idempotency(cleaner):
    """Asserts running the pipeline twice for the same run_id overwrites/clears existing rows cleanly."""
    raw_recs = [
        {
            "carrier": "6E",
            "flight_no": "6E-201",
            "origin": "DEL",
            "destination": "BOM",
            "travel_date": "2026-09-27",
            "search_ts": "2026-09-20T14:48:25+05:30",
            "fare_class": "Economy",
            "total_fare": 6250.0,
            "source": "indigo",
            "availability_flag": "available",
        }
    ]

    cleaned, _ = cleaner.process_raw_records(raw_recs, "run_idempotency_123")

    # Load 1st time
    cleaner.load_to_db(cleaned, raw_recs, "run_idempotency_123", "indigo")

    db = next(get_db())
    count1 = db.query(FareClean).filter(FareClean.run_id == "run_idempotency_123").count()
    raw_count1 = db.query(RawQuote).filter(RawQuote.run_id == "run_idempotency_123").count()
    assert count1 == 1
    assert raw_count1 == 1

    # Load 2nd time (re-run)
    cleaner.load_to_db(cleaned, raw_recs, "run_idempotency_123", "indigo")

    count2 = db.query(FareClean).filter(FareClean.run_id == "run_idempotency_123").count()
    raw_count2 = db.query(RawQuote).filter(RawQuote.run_id == "run_idempotency_123").count()

    assert count2 == 1
    assert raw_count2 == 1
    db.close()
