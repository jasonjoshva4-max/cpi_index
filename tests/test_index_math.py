"""Unit tests for APIx index mathematical formulas: Jevons cell index, route weighting, missing cell weight re-normalization, and National APIx calculation."""
import pytest

from apix.index.apix import (
    calculate_jevons_index,
    calculate_national_apix,
    calculate_route_index,
)


def test_jevons_index_hand_calculated():
    """Asserts Jevons geometric mean formula against a hand-calculated reference vector.

    Fares at t=0: [5000, 6000, 4000]
    Fares at t=1: [5500, 6600, 4400]
    Relatives: [1.1, 1.1, 1.1]
    Expected Jevons: 1.1000
    """
    relatives = [1.1, 1.1, 1.1]
    jevons = calculate_jevons_index(relatives)
    assert round(jevons, 4) == 1.1000

    # Test variable relatives
    # r1 = 1.0, r2 = 1.2, r3 = 0.9
    # ln(1.0) = 0, ln(1.2) = 0.18232155679, ln(0.9) = -0.10536051565
    # mean_log = 0.07696104114 / 3 = 0.02565368038
    # exp(mean_log) = 1.0259858... -> 1.0260
    relatives_var = [1.0, 1.2, 0.9]
    jevons_var = calculate_jevons_index(relatives_var)
    assert round(jevons_var, 4) == 1.0260


def test_route_index_and_weight_renormalization():
    """Asserts route index aggregation and explicit missing cell weight re-normalization.

    Initial cells & weights:
    - Cell 1: I1 = 1.1000, weight v1 = 0.5
    - Cell 2: I2 = 1.2000, weight v2 = 0.3
    - Cell 3: Missing (originally weight v3 = 0.2)

    Active cell weights sum = 0.8
    Renormalized weights:
    - v1' = 0.5 / 0.8 = 0.625
    - v2' = 0.3 / 0.8 = 0.375
    Total weight sum = 1.0

    Expected Route Index: 0.625 * 1.10 + 0.375 * 1.20 = 0.6875 + 0.4500 = 1.1375
    """
    cell_indices = {
        "cell_1": 1.1000,
        "cell_2": 1.2000,
    }
    cell_weights = {
        "cell_1": 0.5,
        "cell_2": 0.3,
        "cell_3": 0.2,  # Missing cell
    }

    route_level, renorm_weights = calculate_route_index(cell_indices, cell_weights)

    assert round(renorm_weights["cell_1"], 3) == 0.625
    assert round(renorm_weights["cell_2"], 3) == 0.375
    assert sum(renorm_weights.values()) == pytest.approx(1.0)
    assert round(route_level, 4) == 1.1375


def test_national_apix_calculation():
    """Asserts National APIx index formula using DGCA route weights.

    Routes:
    - Route 1 (DEL-BOM): Ir1 = 1.0704, weight w1 = 0.70
    - Route 2 (DEL-BLR): Ir2 = 1.0000, weight w2 = 0.30

    Expected APIx level = 100 * (0.70 * 1.0704 + 0.30 * 1.0000)
                        = 100 * (0.74928 + 0.3000) = 104.9280
    """
    route_indices = {
        "DEL-BOM": 1.0704,
        "DEL-BLR": 1.0000,
    }
    route_weights = {
        "DEL-BOM": 0.70,
        "DEL-BLR": 0.30,
    }

    apix_level = calculate_national_apix(route_indices, route_weights)
    assert round(apix_level, 4) == 104.9280
