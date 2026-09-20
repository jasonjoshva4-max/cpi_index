"""Event calendar and fuel/macro intelligence signal matching engine for APIx."""
import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from apix.db.database import get_db, init_db
from apix.db.models import EventModel, MacroSeries

logger = logging.getLogger(__name__)


def is_date_within_window(start_str: str, end_str: str, target_dt: datetime, window_days: int) -> bool:
    """Checks if target_dt falls within [date_start - window_days, date_end + window_days]."""
    dt_start = datetime.strptime(start_str, "%Y-%m-%d")
    dt_end = datetime.strptime(end_str, "%Y-%m-%d")

    w_start = dt_start - timedelta(days=window_days)
    w_end = dt_end + timedelta(days=window_days)

    return w_start <= target_dt <= w_end


class EventSignalMatcher:
    """Coincidence signal matcher connecting fare movements to events and macro shifts."""

    def __init__(self, db: Session | None = None):
        init_db()
        self.db = db or next(get_db())

    def match_signals(
        self,
        route_id: str | None = None,
        target_date: str | None = None,
        window_days: int = 2,
    ) -> list[dict[str, Any]]:
        """Finds events and macro changes coinciding with route_id and target_date within window_days."""
        signals: list[dict[str, Any]] = []

        if not target_date:
            target_date = datetime.now().strftime("%Y-%m-%d")

        target_dt = datetime.strptime(target_date, "%Y-%m-%d")
        win_start_str = (target_dt - timedelta(days=window_days)).strftime("%Y-%m-%d")
        win_end_str = (target_dt + timedelta(days=window_days)).strftime("%Y-%m-%d")

        # Determine origin and destination cities if route_id provided
        regions_to_match = ["National", "ALL"]
        if route_id and "-" in route_id:
            origin, dest = route_id.split("-")
            regions_to_match.extend([origin.upper(), dest.upper()])

        # 1. Query Event Calendar
        all_events = self.db.query(EventModel).all()
        for evt in all_events:
            # Region match check
            if evt.region.upper() in regions_to_match or not route_id:
                # Coincidence window check
                if is_date_within_window(evt.date_start, evt.date_end, target_dt, window_days):
                    signals.append({
                        "signal_type": "event",
                        "event_id": evt.event_id,
                        "title": f"{evt.type.capitalize()}: {evt.note or evt.event_id}",
                        "date_range": f"{evt.date_start} to {evt.date_end}",
                        "region": evt.region,
                        "source": evt.source,
                        "note": evt.note,
                        "label": "signal",
                    })

        # 2. Query Macro Series Changes within window
        macro_rows = (
            self.db.query(MacroSeries)
            .filter(MacroSeries.date >= win_start_str, MacroSeries.date <= win_end_str)
            .all()
        )

        for m in macro_rows:
            series_name_clean = m.series.replace("_", " ").title()
            signals.append({
                "signal_type": "macro",
                "event_id": f"MACRO_{m.series}_{m.date}",
                "title": f"Macro Shift: {series_name_clean}",
                "date_range": m.date,
                "region": "National",
                "source": "macro_series",
                "note": f"{series_name_clean} level recorded at {m.value:,.2f}",
                "label": "signal",
            })

        logger.info(f"Signal matching for route '{route_id}', date '{target_date}' returned {len(signals)} signals.")
        return signals
