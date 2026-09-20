"""Core index calculation logic for APIx: Jevons cell index, DGCA route weighting, weight re-normalization, and rollups."""
import logging
import math
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from apix.db.database import get_db, init_db
from apix.db.models import (
    ApixDaily,
    ApixMonthly,
    ApixWeekly,
    FareClean,
    RouteIndex,
    RouteModel,
)

logger = logging.getLogger(__name__)

# Base date setting (first collection date)
DEFAULT_BASE_DATE = "2026-09-20"


def calculate_jevons_index(relatives: list[float]) -> float:
    """Computes Jevons index (geometric mean) for a list of price relatives.

    Formula: J = exp( mean( ln(r_i) ) )
    """
    if not relatives:
        raise ValueError("Cannot compute Jevons index for an empty list of relatives.")

    log_sum = sum(math.log(r) for r in relatives)
    mean_log = log_sum / len(relatives)
    return math.exp(mean_log)


def calculate_route_index(
    cell_indices: dict[str, float], cell_weights: dict[str, float]
) -> tuple[float, dict[str, float]]:
    """Calculates route index as weighted sum of cell indices.

    Handles missing cell weight re-normalization:
    When a cell is missing, re-normalizes the remaining active cell weights so sum(v'_c) = 1.0.

    Returns:
        Tuple of (route_index_level, renormalized_cell_weights)
    """
    active_cells = [c for c in cell_weights if c in cell_indices]
    if not active_cells:
        raise ValueError("No active cells available to compute route index.")

    total_active_weight = sum(cell_weights[c] for c in active_cells)
    renormalized_weights = {c: cell_weights[c] / total_active_weight for c in active_cells}

    route_level = sum(renormalized_weights[c] * cell_indices[c] for c in active_cells)
    return route_level, renormalized_weights


def calculate_national_apix(
    route_indices: dict[str, float], route_weights: dict[str, float]
) -> float:
    """Calculates National APIx index level from route indices using DGCA route traffic weights.

    Formula: APIx_t = 100 * sum( w'_r * I_{r,t} )
    Where w'_r are route weights re-normalized across active routes.
    """
    active_routes = [r for r in route_weights if r in route_indices]
    if not active_routes:
        raise ValueError("No active routes available to compute national APIx.")

    total_active_weight = sum(route_weights[r] for r in active_routes)
    renormalized_weights = {r: route_weights[r] / total_active_weight for r in active_routes}

    weighted_sum = sum(renormalized_weights[r] * route_indices[r] for r in active_routes)
    return 100.0 * weighted_sum


class IndexCalculator:
    """Database-backed Index Calculator for APIx."""

    def __init__(self, db: Session | None = None, base_date: str = DEFAULT_BASE_DATE):
        init_db()
        self.db = db or next(get_db())
        self.base_date = base_date

    def get_base_prices(self, route_id: str = None) -> dict[str, tuple[float, float | None]]:
        """Fetches base period reference prices (total_fare, base_fare) per cell for base date."""
        query = self.db.query(FareClean).filter(
            FareClean.search_date == self.base_date,
            FareClean.status == "available",
            FareClean.outlier_flag == False,
        )
        if route_id:
            query = query.filter(FareClean.route_id == route_id)

        quotes = query.all()
        cell_fares: dict[str, list[tuple[float, float | None]]] = {}

        for q in quotes:
            cell_id = f"{q.route_id}_T{q.lead_days}_{q.carrier}_{q.fare_type}_{q.stops}_{q.dep_band}"
            base_f = q.base_fare if q.base_fare is not None else None
            cell_fares.setdefault(cell_id, []).append((q.total_fare, base_f))

        base_prices: dict[str, tuple[float, float | None]] = {}
        for cell_id, fares in cell_fares.items():
            avg_total = sum(f[0] for f in fares) / len(fares)
            valid_base_fares = [f[1] for f in fares if f[1] is not None]
            avg_base = sum(valid_base_fares) / len(valid_base_fares) if valid_base_fares else None
            base_prices[cell_id] = (avg_total, avg_base)

        return base_prices

    def compute_daily_index(self, date_str: str) -> dict[str, Any]:
        """Calculates price relatives, cell Jevons indices, route indices, and National APIx level for date_str."""
        # 1. Fetch available quotes for date_str
        quotes = (
            self.db.query(FareClean)
            .filter(
                FareClean.search_date == date_str,
                FareClean.status == "available",
                FareClean.outlier_flag == False,
            )
            .all()
        )

        base_prices = self.get_base_prices()

        # Group quotes by cell
        cell_quotes: dict[str, list[FareClean]] = {}
        for q in quotes:
            cell_id = f"{q.route_id}_T{q.lead_days}_{q.carrier}_{q.fare_type}_{q.stops}_{q.dep_band}"
            cell_quotes.setdefault(cell_id, []).append(q)

        # 2. Compute Cell Relatives and Cell Jevons Indices
        cell_total_indices: dict[str, float] = {}
        cell_base_indices: dict[str, float] = {}
        routes_cell_map: dict[str, dict[str, float]] = {}
        routes_base_cell_map: dict[str, dict[str, float]] = {}

        for cell_id, q_list in cell_quotes.items():
            route_id = q_list[0].route_id
            
            # Base price reference
            if cell_id in base_prices:
                p0_total, p0_base = base_prices[cell_id]
            else:
                # If cell wasn't present on exact base date, use current cell average as baseline (relative = 1.0)
                p0_total = sum(q.total_fare for q in q_list) / len(q_list)
                p0_base = None

            total_relatives = [q.total_fare / p0_total for q in q_list]
            j_total = calculate_jevons_index(total_relatives)
            cell_total_indices[cell_id] = j_total

            # Base fare series
            if p0_base and p0_base > 0:
                base_relatives = [
                    q.base_fare / p0_base
                    for q in q_list
                    if q.base_fare is not None and q.base_fare > 0
                ]
                if base_relatives:
                    cell_base_indices[cell_id] = calculate_jevons_index(base_relatives)

            # Store in route cell map (equal weight 1.0 per cell by default within route)
            routes_cell_map.setdefault(route_id, {})[cell_id] = j_total
            if cell_id in cell_base_indices:
                routes_base_cell_map.setdefault(route_id, {})[cell_id] = cell_base_indices[cell_id]

        # Handle missing cells carry-forward check (up to 2 days)
        # If a cell is missing on date_str, search past 2 days
        all_known_routes = self.db.query(RouteModel).filter(RouteModel.active == True).all()

        # 3. Compute Route Indices
        route_total_levels: dict[str, float] = {}
        route_base_levels: dict[str, float] = {}

        for r in all_known_routes:
            r_id = r.route_id
            if routes_cell_map.get(r_id):
                # Cell weights equal by default
                c_map = routes_cell_map[r_id]
                c_weights = {c: 1.0 for c in c_map}
                r_level, _ = calculate_route_index(c_map, c_weights)
                route_total_levels[r_id] = r_level

                # Save route index to DB
                r_idx_obj = self.db.query(RouteIndex).filter(
                    RouteIndex.route_id == r_id, RouteIndex.date == date_str
                ).first()
                if not r_idx_obj:
                    r_idx_obj = RouteIndex(route_id=r_id, date=date_str, level=r_level)
                    self.db.add(r_idx_obj)
                else:
                    r_idx_obj.level = r_level

            if routes_base_cell_map.get(r_id):
                cb_map = routes_base_cell_map[r_id]
                cb_weights = {c: 1.0 for c in cb_map}
                rb_level, _ = calculate_route_index(cb_map, cb_weights)
                route_base_levels[r_id] = rb_level

        # 4. Compute National APIx Level
        route_weights = {
            r.route_id: (r.weight if r.weight > 0 else r.dgca_pax)
            for r in all_known_routes
        }

        if not route_total_levels:
            # Fallback if no routes found
            national_total = 100.0
            national_base = 100.0
            n_cells = 0
        else:
            national_total = calculate_national_apix(route_total_levels, route_weights)
            national_base = (
                calculate_national_apix(route_base_levels, route_weights)
                if route_base_levels
                else national_total
            )
            n_cells = len(cell_total_indices)

        # 5. Persist to apix_daily
        daily_row = self.db.query(ApixDaily).filter(ApixDaily.date == date_str).first()
        if not daily_row:
            daily_row = ApixDaily(
                date=date_str,
                level=round(national_total, 4),
                base_fare_level=round(national_base, 4),
                tax_level=round(national_total - national_base, 4),
                n_cells=n_cells,
            )
            self.db.add(daily_row)
        else:
            daily_row.level = round(national_total, 4)
            daily_row.base_fare_level = round(national_base, 4)
            daily_row.tax_level = round(national_total - national_base, 4)
            daily_row.n_cells = n_cells

        self.db.commit()

        logger.info(
            f"Computed Daily APIx for {date_str}: Level = {national_total:.4f} "
            f"(Base = {national_base:.4f}, n_cells = {n_cells})"
        )

        return {
            "date": date_str,
            "level": round(national_total, 4),
            "base_fare_level": round(national_base, 4),
            "tax_level": round(national_total - national_base, 4),
            "n_cells": n_cells,
            "route_levels": route_total_levels,
        }

    def compute_weekly_rollup(self, end_date_str: str) -> dict[str, Any]:
        """Rolls up past 7 daily APIx levels into apix_weekly."""
        end_dt = datetime.strptime(end_date_str, "%Y-%m-%d")
        start_dt = end_dt - timedelta(days=6)
        start_date_str = start_dt.strftime("%Y-%m-%d")

        daily_rows = (
            self.db.query(ApixDaily)
            .filter(ApixDaily.date >= start_date_str, ApixDaily.date <= end_date_str)
            .all()
        )

        if not daily_rows:
            logger.warning(f"No daily rows available for weekly rollup ending {end_date_str}")
            return {}

        avg_level = sum(r.level for r in daily_rows) / len(daily_rows)
        avg_base = sum(r.base_fare_level for r in daily_rows if r.base_fare_level) / len(daily_rows)
        total_cells = sum(r.n_cells for r in daily_rows)

        weekly_row = self.db.query(ApixWeekly).filter(ApixWeekly.date == end_date_str).first()
        if not weekly_row:
            weekly_row = ApixWeekly(
                date=end_date_str,
                level=round(avg_level, 4),
                base_fare_level=round(avg_base, 4),
                tax_level=round(avg_level - avg_base, 4),
                n_cells=total_cells,
            )
            self.db.add(weekly_row)
        else:
            weekly_row.level = round(avg_level, 4)
            weekly_row.base_fare_level = round(avg_base, 4)
            weekly_row.tax_level = round(avg_level - avg_base, 4)
            weekly_row.n_cells = total_cells

        self.db.commit()
        return {
            "date": end_date_str,
            "level": round(avg_level, 4),
            "base_fare_level": round(avg_base, 4),
            "n_cells": total_cells,
        }

    def compute_monthly_rollup(self, month_str: str) -> dict[str, Any]:
        """Rolls up daily APIx levels for a calendar month (YYYY-MM) into apix_monthly."""
        daily_rows = (
            self.db.query(ApixDaily)
            .filter(ApixDaily.date.like(f"{month_str}-%"))
            .all()
        )

        if not daily_rows:
            logger.warning(f"No daily rows available for monthly rollup {month_str}")
            return {}

        avg_level = sum(r.level for r in daily_rows) / len(daily_rows)
        avg_base = sum(r.base_fare_level for r in daily_rows if r.base_fare_level) / len(daily_rows)
        total_cells = sum(r.n_cells for r in daily_rows)

        monthly_row = self.db.query(ApixMonthly).filter(ApixMonthly.date == month_str).first()
        if not monthly_row:
            monthly_row = ApixMonthly(
                date=month_str,
                level=round(avg_level, 4),
                base_fare_level=round(avg_base, 4),
                tax_level=round(avg_level - avg_base, 4),
                n_cells=total_cells,
            )
            self.db.add(monthly_row)
        else:
            monthly_row.level = round(avg_level, 4)
            monthly_row.base_fare_level = round(avg_base, 4)
            monthly_row.tax_level = round(avg_level - avg_base, 4)
            monthly_row.n_cells = total_cells

        self.db.commit()
        return {
            "date": month_str,
            "level": round(avg_level, 4),
            "base_fare_level": round(avg_base, 4),
            "n_cells": total_cells,
        }
