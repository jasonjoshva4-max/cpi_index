"""Robust anomaly and surge detection engine for APIx."""
import logging
from typing import Any

import numpy as np
from sqlalchemy.orm import Session

from apix.db.database import get_db, init_db
from apix.db.models import Anomaly, FareClean

logger = logging.getLogger(__name__)


def compute_robust_z_score(
    value: float, window_values: list[float]
) -> tuple[float, float, float]:
    """Computes robust Z-score using Median and Median Absolute Deviation (MAD).

    Formula:
        robust_z = 0.6745 * (x_t - median_window) / MAD_window

    Returns:
        Tuple of (robust_z, median_window, pct_from_expected)
    """
    if not window_values:
        return 0.0, value, 0.0

    arr = np.array(window_values, dtype=float)
    median = float(np.median(arr))
    abs_dev = np.abs(arr - median)
    mad = float(np.median(abs_dev))

    pct_from_expected = ((value - median) / median * 100.0) if median > 0 else 0.0

    if mad == 0:
        # Fallback to standard deviation if MAD is zero
        std = float(np.std(arr))
        if std == 0:
            return 0.0, median, pct_from_expected
        robust_z = (value - median) / std
    else:
        robust_z = 0.6745 * (value - median) / mad

    return float(robust_z), median, float(pct_from_expected)


class AnomalyDetector:
    """Engine for detecting airfare price surges and drops per (route x lead-time) cell."""

    def __init__(self, db: Session | None = None, z_threshold: float = 3.5):
        init_db()
        self.db = db or next(get_db())
        self.z_threshold = z_threshold

    def detect_anomalies_for_date(self, target_date: str) -> list[dict[str, Any]]:
        """Evaluates fare quotes on target_date against cell rolling window for anomalies/surges."""
        # 1. Fetch available quotes for target_date
        current_quotes = (
            self.db.query(FareClean)
            .filter(
                FareClean.search_date == target_date,
                FareClean.status == "available",
                FareClean.outlier_flag == False,
            )
            .all()
        )

        if not current_quotes:
            logger.info(f"No available quotes found for anomaly detection on {target_date}")
            return []

        # 2. Group current quotes by (route_id, lead_days)
        cell_current: dict[tuple[str, int], list[float]] = {}
        for q in current_quotes:
            key = (q.route_id, q.lead_days)
            cell_current.setdefault(key, []).append(q.total_fare)

        detected_anomalies = []

        for (route_id, lead_days), current_fares in cell_current.items():
            # Fetch historical rolling window (past 14 days) strictly for same (route_id, lead_days)
            hist_quotes = (
                self.db.query(FareClean.total_fare)
                .filter(
                    FareClean.route_id == route_id,
                    FareClean.lead_days == lead_days,
                    FareClean.search_date <= target_date,
                    FareClean.status == "available",
                    FareClean.outlier_flag == False,
                )
                .all()
            )
            hist_fares = [f[0] for f in hist_quotes]

            avg_current_fare = float(np.mean(current_fares))
            robust_z, median_val, pct_diff = compute_robust_z_score(avg_current_fare, hist_fares)

            flag = False
            direction = "normal"

            if robust_z > self.z_threshold:
                flag = True
                direction = "surge"
            elif robust_z < -self.z_threshold:
                flag = True
                direction = "drop"

            if flag:
                anomaly_dict = {
                    "route_id": route_id,
                    "date": target_date,
                    "lead_days": lead_days,
                    "score": round(robust_z, 4),
                    "pct_from_expected": round(pct_diff, 2),
                    "direction": direction,
                    "flag": True,
                }
                detected_anomalies.append(anomaly_dict)

                # Persist to database anomalies table
                existing = (
                    self.db.query(Anomaly)
                    .filter(
                        Anomaly.route_id == route_id,
                        Anomaly.date == target_date,
                        Anomaly.lead_days == lead_days,
                    )
                    .first()
                )
                if not existing:
                    anom_obj = Anomaly(
                        route_id=route_id,
                        date=target_date,
                        lead_days=lead_days,
                        score=round(robust_z, 4),
                        pct_from_expected=round(pct_diff, 2),
                        direction=direction,
                        flag=True,
                    )
                    self.db.add(anom_obj)
                else:
                    existing.score = round(robust_z, 4)
                    existing.pct_from_expected = round(pct_diff, 2)
                    existing.direction = direction
                    existing.flag = True

        self.db.commit()
        logger.info(f"Anomaly detection complete for {target_date}: {len(detected_anomalies)} anomalies flagged.")
        return detected_anomalies
