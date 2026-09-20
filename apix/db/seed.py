"""DGCA route weights and reference data seed script."""
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
from apix.db.models import RouteModel

logger = logging.getLogger(__name__)

DGCA_CSV_PATH = BASE_DIR / "data" / "reference" / "dgca_traffic.csv"


def seed_routes_and_weights(csv_path: Path = DGCA_CSV_PATH):
    """Loads DGCA traffic figures from CSV, calculates normalized route weights w_r = pax_r / sum(pax), and updates DB."""
    if not csv_path.exists():
        logger.error(f"DGCA reference file not found at {csv_path}")
        return

    init_db()

    rows = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append({
                "route_id": r["route_id"].strip(),
                "origin": r["origin"].strip(),
                "destination": r["destination"].strip(),
                "dgca_pax": float(r["dgca_pax"]),
            })

    total_pax = sum(r["dgca_pax"] for r in rows)
    if total_pax == 0:
        logger.error("Total DGCA passenger volume is 0. Cannot compute weights.")
        return

    db = next(get_db())
    try:
        for r in rows:
            weight = r["dgca_pax"] / total_pax
            route_obj = db.query(RouteModel).filter(RouteModel.route_id == r["route_id"]).first()
            if not route_obj:
                route_obj = RouteModel(
                    route_id=r["route_id"],
                    origin=r["origin"],
                    destination=r["destination"],
                    dgca_pax=r["dgca_pax"],
                    weight=round(weight, 6),
                    active=True,
                )
                db.add(route_obj)
            else:
                route_obj.origin = r["origin"]
                route_obj.destination = r["destination"]
                route_obj.dgca_pax = r["dgca_pax"]
                route_obj.weight = round(weight, 6)
                route_obj.active = True

        db.commit()
        logger.info(f"Successfully seeded/updated {len(rows)} routes with DGCA weights (total pax = {total_pax:,.0f}).")
    except Exception as e:
        db.rollback()
        logger.error(f"Error seeding DGCA routes: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    seed_routes_and_weights()
