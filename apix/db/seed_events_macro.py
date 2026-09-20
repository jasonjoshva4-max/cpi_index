"""Seed script for events calendar and macroeconomic indicator series."""
import csv
import logging
import sys
from pathlib import Path

# Add project root to PYTHONPATH
PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from apix.config import BASE_DIR
from apix.db.database import get_db, init_db
from apix.db.models import EventModel, MacroSeries

logger = logging.getLogger(__name__)

REF_DIR = BASE_DIR / "data" / "reference"


def seed_events(csv_path: Path = REF_DIR / "events.csv"):
    if not csv_path.exists():
        logger.warning(f"Events reference CSV not found at {csv_path}")
        return

    init_db()
    db = next(get_db())

    try:
        count = 0
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                evt_id = r["event_id"].strip()
                evt_obj = db.query(EventModel).filter(EventModel.event_id == evt_id).first()
                if not evt_obj:
                    evt_obj = EventModel(
                        event_id=evt_id,
                        date_start=r["date_start"].strip(),
                        date_end=r["date_end"].strip(),
                        type=r["type"].strip(),
                        region=r["region"].strip(),
                        source=r["source"].strip(),
                        note=r.get("note", "").strip(),
                    )
                    db.add(evt_obj)
                else:
                    evt_obj.date_start = r["date_start"].strip()
                    evt_obj.date_end = r["date_end"].strip()
                    evt_obj.type = r["type"].strip()
                    evt_obj.region = r["region"].strip()
                    evt_obj.source = r["source"].strip()
                    evt_obj.note = r.get("note", "").strip()
                count += 1
        db.commit()
        logger.info(f"Seeded {count} events into database.")
    except Exception as e:
        db.rollback()
        logger.error(f"Error seeding events: {e}")
        raise
    finally:
        db.close()


def seed_macro_series():
    init_db()
    macro_files = [
        REF_DIR / "macro_atf.csv",
        REF_DIR / "macro_crude.csv",
        REF_DIR / "macro_usdinr.csv",
    ]

    db = next(get_db())
    total_count = 0

    try:
        for csv_path in macro_files:
            if not csv_path.exists():
                continue

            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for r in reader:
                    dt = r["date"].strip()
                    s_name = r["series"].strip()
                    val = float(r["value"])

                    m_obj = db.query(MacroSeries).filter(
                        MacroSeries.date == dt, MacroSeries.series == s_name
                    ).first()

                    if not m_obj:
                        m_obj = MacroSeries(date=dt, series=s_name, value=val)
                        db.add(m_obj)
                    else:
                        m_obj.value = val
                    total_count += 1
        db.commit()
        logger.info(f"Seeded {total_count} macro series data points into database.")
    except Exception as e:
        db.rollback()
        logger.error(f"Error seeding macro series: {e}")
        raise
    finally:
        db.close()


def seed_all():
    seed_events()
    seed_macro_series()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    seed_all()
