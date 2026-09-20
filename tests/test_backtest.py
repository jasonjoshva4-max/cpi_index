"""Unit tests for DGCA back-testing, internal airline vs OTA quote consistency, and lead-time sensitivity analysis."""
import pytest
from fastapi.testclient import TestClient

from api.main import app
from apix.db.database import init_db
from apix.db.seed_dgca_ref import seed_dgca_reference
from apix.index.backtest import BacktestEngine, compute_series_metrics

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db_backtest():
    init_db()
    seed_dgca_reference()


def test_dgca_backtest_metrics_calculation():
    """Asserts re-basing to 100.0, correlation, MAE, RMSE, and direction-of-change agreement calculation."""
    apix_series = [100.0, 102.5, 105.0]
    dgca_series = [5400.0, 5535.0, 5670.0]  # Exact 2.5% increase per month -> rebased 100.0, 102.5, 105.0

    metrics = compute_series_metrics(apix_series, dgca_series)

    assert metrics["correlation"] == 1.0
    assert metrics["mae"] == 0.0
    assert metrics["rmse"] == 0.0
    assert metrics["direction_agreement_rate"] == 100.0


def test_internal_consistency_check():
    """Asserts airline vs OTA quote agreement rate calculation."""
    engine = BacktestEngine()
    res = engine.run_internal_consistency_check()

    assert "quote_agreement_rate_pct" in res
    assert "mean_abs_price_diff" in res
    assert res["quote_agreement_rate_pct"] >= 90.0


def test_lead_time_sensitivity_analysis():
    """Asserts index sensitivity calculation across 3 lead-time weight mixtures."""
    engine = BacktestEngine()
    res = engine.run_lead_time_sensitivity_analysis()

    assert "mixtures" in res
    assert "max_sensitivity_delta" in res
    assert res["max_sensitivity_delta"] <= 3.5


def test_get_backtest_api_endpoint():
    """Asserts GET /api/backtest endpoint returns status 200 and structured report."""
    response = client.get("/api/backtest")
    assert response.status_code == 200
    data = response.json()

    assert "dgca_backtest" in data
    assert "internal_consistency" in data
    assert "index_sensitivity" in data
    assert "metadata" in data

    meta = data["metadata"]
    assert meta["label"] == "estimated"

    limitation_note = data["dgca_backtest"].get("limitation_warning")
    assert limitation_note is not None
    assert "Limitation Warning" in limitation_note
