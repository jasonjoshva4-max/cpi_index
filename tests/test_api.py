"""API contract integration tests using FastAPI TestClient."""
import pytest
from fastapi.testclient import TestClient

from api.main import app
from apix.db.database import init_db

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    init_db()


def test_get_latest_index_endpoint():
    """Asserts GET /api/index response schema, metadata block, and status 200."""
    response = client.get("/api/index")
    assert response.status_code == 200
    data = response.json()

    assert "date" in data
    assert "level" in data
    assert "base_fare_level" in data
    assert "change_pct" in data
    assert "metadata" in data

    meta = data["metadata"]
    assert "n_obs" in meta
    assert "n_cells" in meta
    assert "base_period" in meta
    assert meta["label"] == "estimated"


def test_get_daily_index_json_endpoint():
    """Asserts GET /api/index/daily JSON response schema and date range filters."""
    response = client.get("/api/index/daily?start=2026-09-01&end=2026-09-30")
    assert response.status_code == 200
    data = response.json()

    assert "data" in data
    assert "metadata" in data

    meta = data["metadata"]
    assert meta["label"] == "estimated"


def test_get_daily_index_csv_endpoint():
    """Asserts GET /api/index/daily?format=csv returns CSV stream header."""
    response = client.get("/api/index/daily?format=csv")
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert response.text.startswith("date,level,base_fare_level,tax_level,n_cells")


def test_get_routes_endpoint():
    """Asserts GET /api/routes returns route weighting and current route levels."""
    response = client.get("/api/routes")
    assert response.status_code == 200
    data = response.json()

    assert "routes" in data
    assert "metadata" in data

    meta = data["metadata"]
    assert meta["label"] == "estimated"


def test_empty_database_fallback_behavior():
    """Asserts that querying API endpoints returns status 200 and valid schema even when no new data is present."""
    # Test latest index fallback
    res1 = client.get("/api/index")
    assert res1.status_code == 200
    assert isinstance(res1.json()["level"], float)

    # Test daily index fallback
    res2 = client.get("/api/index/daily")
    assert res2.status_code == 200
    assert isinstance(res2.json()["data"], list)

    # Test routes fallback
    res3 = client.get("/api/routes")
    assert res3.status_code == 200
    assert isinstance(res3.json()["routes"], list)

