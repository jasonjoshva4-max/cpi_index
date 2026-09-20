"""Route volatility score calculation and tercile band ranking engine for APIx."""
import logging
import math
from datetime import datetime, timedelta
from typing import Any

import numpy as np
from sqlalchemy.orm import Session

from apix.db.database import get_db, init_db
from apix.db.models import RouteIndex, RouteModel, Volatility

logger = logging.getLogger(__name__)


def calculate_volatility_score(daily_prices: list[float]) -> float:
    """Computes route volatility score as standard deviation of log returns.

    Formula:
        volatility_r = std( ln( p_t / p_{t-1} ) )
    """
    if len(daily_prices) < 2:
        return 0.0

    log_returns = []
    for i in range(1, len(daily_prices)):
        p_prev = daily_prices[i - 1]
        p_curr = daily_prices[i]
        if p_prev > 0 and p_curr > 0:
            log_ret = math.log(p_curr / p_prev)
            log_returns.append(log_ret)

    if not log_returns:
        return 0.0

    return float(np.std(log_returns, ddof=1)) if len(log_returns) > 1 else float(np.std(log_returns))


def assign_tercile_bands(route_volatilities: dict[str, float]) -> dict[str, str]:
    """Ranks route volatility values and bands them High/Medium/Low by terciles."""
    if not route_volatilities:
        return {}

    sorted_routes = sorted(route_volatilities.items(), key=lambda x: x[1])
    n = len(sorted_routes)

    bands = {}
    if n == 1:
        bands[sorted_routes[0][0]] = "Low"
    elif n == 2:
        bands[sorted_routes[0][0]] = "Low"
        bands[sorted_routes[1][0]] = "High"
    elif n == 3:
        bands[sorted_routes[0][0]] = "Low"
        bands[sorted_routes[1][0]] = "Medium"
        bands[sorted_routes[2][0]] = "High"
    else:
        # Quantile thresholds (33rd and 66th percentiles)
        vals = [v for _, v in sorted_routes]
        t1 = float(np.percentile(vals, 33.33))
        t2 = float(np.percentile(vals, 66.66))

        for route_id, val in route_volatilities.items():
            if val <= t1:
                bands[route_id] = "Low"
            elif val <= t2:
                bands[route_id] = "Medium"
            else:
                bands[route_id] = "High"

    return bands


class VolatilityCalculator:
    """Engine for computing 14-day rolling route volatility scores and tercile bands."""

    def __init__(self, db: Session | None = None, window_days: int = 14):
        init_db()
        self.db = db or next(get_db())
        self.window_days = window_days

    def compute_volatility_for_date(self, window_end_date: str) -> dict[str, dict[str, Any]]:
        """Computes volatility scores and tercile bands across active routes for window_end_date."""
        end_dt = datetime.strptime(window_end_date, "%Y-%m-%d")
        start_dt = end_dt - timedelta(days=self.window_days)
        start_date_str = start_dt.strftime("%Y-%m-%d")

        all_routes = self.db.query(RouteModel).filter(RouteModel.active == True).all()
        route_vols: dict[str, float] = {}

        for r in all_routes:
            # Fetch daily route levels within window
            r_rows = (
                self.db.query(RouteIndex)
                .filter(
                    RouteIndex.route_id == r.route_id,
                    RouteIndex.date >= start_date_str,
                    RouteIndex.date <= window_end_date,
                )
                .order_by(RouteIndex.date.asc())
                .all()
            )
            prices = [row.level for row in r_rows]
            vol_score = calculate_volatility_score(prices)
            route_vols[r.route_id] = vol_score

        bands = assign_tercile_bands(route_vols)
        results = {}

        for r_id, vol_score in route_vols.items():
            band = bands.get(r_id, "Low")
            results[r_id] = {
                "route_id": r_id,
                "window_end": window_end_date,
                "value": round(vol_score, 6),
                "band": band,
            }

            # Persist to database volatility table
            existing = (
                self.db.query(Volatility)
                .filter(
                    Volatility.route_id == r_id,
                    Volatility.window_end == window_end_date,
                )
                .first()
            )
            if not existing:
                vol_obj = Volatility(
                    route_id=r_id,
                    window_end=window_end_date,
                    value=round(vol_score, 6),
                    band=band,
                )
                self.db.add(vol_obj)
            else:
                existing.value = round(vol_score, 6)
                existing.band = band

        self.db.commit()
        logger.info(f"Computed route volatility scores for {window_end_date}: {len(results)} routes processed.")
        return results
