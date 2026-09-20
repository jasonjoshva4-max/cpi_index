"""Seed script for DGCA official monthly average fare benchmarks."""
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
from apix.db.models import DgcaReference

logger = logging.getLogger(__name__)

CSV_PATH = BASE_DIR / "data" / "reference" / "dgca_monthly_reference.csv"


def seed_dgca_reference(csv_path: Path = CSV_PATH):
    """Parses DGCA monthly fare CSV and populates dgca_reference database table."""
    if not csv_path.exists():
        logger.warning(f"DGCA reference CSV file not found at {csv_path}")
        return

    init_db()
    db = next(get_db())
    count = 0

    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                month = r["month"].strip()
                route_or_nat = r["route_or_national"].strip()
                fare = float(r["avg_fare"])

                ref_obj = (
                    db.query(DgcaReference)
                    .filter(
                        DgcaReference.month == month,
                        DgcaReference.route_or_national == route_or_nat,
                    )
                    .first()
                )

                if not ref_obj:
                    ref_obj = DgcaReference(
                        month=month,
                        route_or_national=route_or_nat,
                        avg_fare=fare,
                    )
                    db.add(ref_obj)
                else:
                    ref_obj.avg_fare = fare
                count += 1

        db.commit()
        logger.info(f"Seeded {count} DGCA reference benchmark rows into database.")
    except Exception as e:
        db.rollback()
        logger.error(f"Error seeding DGCA reference data: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    seed_dgca_reference()
