"""Unit tests for Phase 7 attribution identity and walk-forward forecasting baseline evaluation."""
import pytest
from fastapi.testclient import TestClient

from api.main import app
from apix.db.database import init_db
from apix.novelty.attribution import compute_level1_decomposition
from apix.novelty.forecast import WalkForwardForecaster

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db_attr():
    init_db()


def test_attribution_level1_identity():
    """Asserts that Level 1 attribution components sum exactly to total change minus reported residual.

    Identity: Total Change = Route Mix + Carrier Mix + Lead Time Mix + Base/Tax + Residual
    """
    start_level = 100.0
    end_level = 105.5
    start_base = 100.0
    end_base = 104.0

    route_contribs = {"DEL-BOM": 2.0, "DEL-BLR": 1.5}
    carrier_contrib = 0.5
    lead_contrib = 0.3

    decomp = compute_level1_decomposition(
        start_level=start_level,
        end_level=end_level,
        start_base=start_base,
        end_base=end_base,
        route_contribs=route_contribs,
        carrier_contrib=carrier_contrib,
        lead_contrib=lead_contrib,
    )

    total = decomp["total_change"]
    sum_components = (
        decomp["route_mix_contribution"]
        + decomp["carrier_mix_contribution"]
        + decomp["lead_time_mix_contribution"]
        + decomp["base_vs_taxes_contribution"]
        + decomp["residual"]
    )

    # Assert exact identity
    assert round(total, 4) == round(sum_components, 4)


def test_forecast_walk_forward_evaluation_gating():
    """Asserts that walk-forward evaluator scores model against baselines and flags gating correctly."""
    forecaster = WalkForwardForecaster()
    res = forecaster.evaluate_and_forecast(horizon=7)

    assert "chosen_model" in res
    assert "beats_baselines" in res
    assert "evaluation_metrics" in res
    assert "forecast_points" in res

    metrics = res["evaluation_metrics"]
    assert "model" in metrics
    assert "last_value" in metrics
    assert "seasonal_naive" in metrics

    # Verify 7 forecast horizon points returned
    points = res["forecast_points"]
    assert len(points) == 7
    for p in points:
        assert p["lower"] <= p["level"] <= p["upper"]


def test_attribution_and_forecast_api_endpoints():
    """Asserts status 200 and schema for GET /api/attribution and GET /api/forecast."""
    res_attr = client.get("/api/attribution")
    assert res_attr.status_code == 200
    data_attr = res_attr.json()
    assert "level1_decomposition" in data_attr
    assert data_attr["metadata"]["label"] == "estimated"

    res_fc = client.get("/api/forecast?horizon=7")
    assert res_fc.status_code == 200
    data_fc = res_fc.json()
    assert "forecast_points" in data_fc
    assert data_fc["metadata"]["label"] == "estimated"
