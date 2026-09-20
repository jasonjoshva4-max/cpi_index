"""Unit tests for novelty detection: robust Z-score anomaly detection and route volatility score."""
import math

import numpy as np
import pytest

from apix.novelty.anomaly import compute_robust_z_score
from apix.novelty.volatility import assign_tercile_bands, calculate_volatility_score


def test_anomaly_injected_surge_detection():
    """Asserts that an injected price surge produces robust_z > 3.5 and is flagged."""
    baseline = [4900.0, 5000.0, 5100.0, 4950.0, 5050.0, 5000.0, 4980.0, 5020.0, 5010.0, 4990.0]
    surge_price = 20000.0

    robust_z, median_val, pct_diff = compute_robust_z_score(surge_price, baseline)

    assert median_val == 5000.0
    assert robust_z > 3.5
    assert pct_diff == pytest.approx(300.0)  # (20000 - 5000) / 5000 * 100 = 300%


def test_anomaly_flat_series_no_flag():
    """Asserts that normal fares in a flat series result in robust_z near 0 and no false flags."""
    baseline = [5000.0, 5000.0, 5000.0, 5000.0, 5000.0]
    normal_price = 5000.0

    robust_z, median_val, pct_diff = compute_robust_z_score(normal_price, baseline)

    assert median_val == 5000.0
    assert robust_z == 0.0
    assert pct_diff == 0.0
    assert robust_z < 3.5


def test_volatility_score_calculation():
    """Asserts volatility score calculation matching standard deviation of log returns."""
    # Synthetic price series with alternating 10% movement
    prices = [100.0, 110.0, 100.0, 110.0, 100.0]

    vol = calculate_volatility_score(prices)

    log_returns = [
        math.log(110.0 / 100.0),
        math.log(100.0 / 110.0),
        math.log(110.0 / 100.0),
        math.log(100.0 / 110.0),
    ]
    expected_std = float(np.std(log_returns, ddof=1))

    assert round(vol, 6) == round(expected_std, 6)


def test_volatility_tercile_bands():
    """Asserts proper ranking and High/Medium/Low tercile band classification across routes."""
    route_vols = {
        "DEL-BLR": 0.02,  # Lowest
        "DEL-BOM": 0.05,  # Middle
        "BOM-BLR": 0.10,  # Highest
    }

    bands = assign_tercile_bands(route_vols)

    assert bands["DEL-BLR"] == "Low"
    assert bands["DEL-BOM"] == "Medium"
    assert bands["BOM-BLR"] == "High"
