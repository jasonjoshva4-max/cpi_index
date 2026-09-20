"""Unit tests for event calendar and macro intelligence signal matching engine."""
import pytest
from fastapi.testclient import TestClient

from api.main import app
from apix.db.database import init_db
from apix.db.seed_events_macro import seed_all
from apix.novelty.events import EventSignalMatcher

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db_events():
    init_db()
    seed_all()


def test_event_matching_surfaces_known_festival():
    """Asserts that a fare movement on a known festival date surfaces the event signal."""
    matcher = EventSignalMatcher()
    signals = matcher.match_signals(route_id="DEL-BOM", target_date="2026-09-26", window_days=2)

    assert len(signals) > 0

    # Locate festival event signal
    diwali_signal = [s for s in signals if s.get("event_id") == "EVT_001"]
    assert len(diwali_signal) == 1
    assert diwali_signal[0]["region"] == "DEL"
    assert diwali_signal[0]["label"] == "signal"


def test_no_nearby_event_returns_empty_list():
    """Asserts that a fare movement on a date with no nearby events returns an empty signal list (never fabricates)."""
    matcher = EventSignalMatcher()
    # Query date with no events or macro entries
    signals = matcher.match_signals(route_id="BLR-HYD", target_date="2025-01-15", window_days=0)

    # Must be strictly empty
    assert len(signals) == 0


def test_get_events_api_endpoint():
    """Asserts GET /api/events endpoint returns status 200 and metadata with label='signal'."""
    response = client.get("/api/events?route=DEL-BOM&start=2026-09-26")
    assert response.status_code == 200
    data = response.json()

    assert "signals" in data
    assert "metadata" in data

    meta = data["metadata"]
    assert meta["label"] == "signal"

    signals = data["signals"]
    for s in signals:
        assert s["label"] == "signal"
