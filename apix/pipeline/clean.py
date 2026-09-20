"""Data cleaning, validation, normalization, deduplication, and outlier detection pipeline for APIx."""
import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from apix.config import RAW_DATA_DIR
from apix.db.database import get_db, init_db
from apix.db.models import FareClean, RawQuote, RouteModel

logger = logging.getLogger(__name__)

CARRIER_LOOKUP = {
    "6E": "6E",
    "INDIGO": "6E",
    "GOINDIGO": "6E",
    "AI": "AI",
    "AIR INDIA": "AI",
    "AIRINDIA": "AI",
    "UK": "UK",
    "VISTARA": "UK",
    "QP": "QP",
    "AKASA": "QP",
    "AKASA AIR": "QP",
    "SG": "SG",
    "SPICEJET": "SG",
    "I5": "I5",
    "AIRASIA INDIA": "I5",
    "AIX": "I5",
}


def parse_currency(val: Any) -> float | None:
    """Normalizes currency values (strings/floats) to float."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        # Strip currency symbols, commas, and whitespace
        clean_str = val.replace("₹", "").replace("$", "").replace(",", "").strip()
        if not clean_str or clean_str.lower() in ("null", "none", "nan"):
            return None
        try:
            return float(clean_str)
        except ValueError:
            return None
    return None


def get_departure_band(dep_time_str: str) -> str:
    """Classifies departure time string into standardized time band."""
    if not dep_time_str:
        return "morning"

    time_part = dep_time_str
    if "T" in dep_time_str:
        time_part = dep_time_str.split("T")[1]

    try:
        hour = int(time_part.split(":")[0])
    except (ValueError, IndexError):
        return "morning"

    if 0 <= hour < 6:
        return "early_morning"
    elif 6 <= hour < 12:
        return "morning"
    elif 12 <= hour < 17:
        return "afternoon"
    elif 17 <= hour < 21:
        return "evening"
    else:
        return "night"


class CleanerPipeline:
    """End-to-end cleaning pipeline for raw scraped quotes."""

    def __init__(self, raw_data_dir: Path = RAW_DATA_DIR):
        self.raw_data_dir = raw_data_dir
        init_db()

    def validate_record(self, raw_rec: dict[str, Any]) -> tuple[bool, str | None]:
        """Validates record presence of mandatory fields: origin, destination, travel_date, search_ts, total_fare."""
        origin = raw_rec.get("origin")
        destination = raw_rec.get("destination")
        travel_date = raw_rec.get("travel_date")
        search_ts = raw_rec.get("search_ts")
        total_fare = parse_currency(raw_rec.get("total_fare"))
        availability = raw_rec.get("availability_flag", "available")

        if not origin or not destination:
            return False, "MISSING_ROUTE"
        if not travel_date or not search_ts:
            return False, "MISSING_DATE"
        
        # Total fare can be missing only if explicitly sold out or cancelled
        if availability not in ("sold_out", "cancelled"):
            if total_fare is None or total_fare <= 0:
                return False, "INVALID_TOTAL_FARE"

        return True, None

    def normalize_record(self, raw_rec: dict[str, Any], run_id: str) -> dict[str, Any]:
        """Parses and normalizes raw record fields."""
        raw_carrier = str(raw_rec.get("carrier", "6E")).upper().strip()
        carrier = CARRIER_LOOKUP.get(raw_carrier, raw_carrier)

        flight_no = str(raw_rec.get("flight_no", "")).strip().upper()
        if flight_no and not flight_no.startswith(carrier):
            flight_no = f"{carrier}-{flight_no}"

        origin = str(raw_rec.get("origin")).upper().strip()
        destination = str(raw_rec.get("destination")).upper().strip()
        route_id = f"{origin}-{destination}"

        dep_time = str(raw_rec.get("dep_time", ""))
        dep_band = get_departure_band(dep_time)

        # Dates (YYYY-MM-DD)
        search_ts_str = str(raw_rec.get("search_ts"))
        search_date = search_ts_str.split("T")[0]
        travel_date = str(raw_rec.get("travel_date")).split("T")[0]

        lead_days = int(raw_rec.get("lead_days", 7))
        fare_type = str(raw_rec.get("fare_class") or "economy").lower().strip()
        stops = int(raw_rec.get("stops", 0))

        # Fare Component Splitting Policy:
        # Preserve itemized base_fare, taxes, udf, conv_fee ONLY if present in source;
        # otherwise set to None (never estimate a split).
        base_fare = parse_currency(raw_rec.get("base_fare"))
        taxes = parse_currency(raw_rec.get("taxes"))
        udf = parse_currency(raw_rec.get("udf"))
        conv_fee = parse_currency(raw_rec.get("convenience_fee") or raw_rec.get("conv_fee"))
        total_fare = parse_currency(raw_rec.get("total_fare")) or 0.0

        status = str(raw_rec.get("availability_flag", "available")).lower().strip()
        source = str(raw_rec.get("source", "unknown")).lower().strip()

        # Deterministic unique quote ID
        hash_input = f"{source}_{carrier}_{flight_no}_{travel_date}_{search_date}_{fare_type}_{dep_time}"
        quote_id = f"q_{hashlib.sha256(hash_input.encode()).hexdigest()[:16]}"

        return {
            "quote_id": quote_id,
            "route_id": route_id,
            "carrier": carrier,
            "flight_no": flight_no,
            "lead_days": lead_days,
            "fare_type": fare_type,
            "base_fare": base_fare,
            "taxes": taxes,
            "udf": udf,
            "conv_fee": conv_fee,
            "total_fare": total_fare,
            "search_date": search_date,
            "travel_date": travel_date,
            "stops": stops,
            "dep_band": dep_band,
            "status": status,
            "outlier_flag": False,
            "run_id": run_id,
            "source": source,
        }

    def deduplicate(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Deduplicates records using key: (carrier, flight_no, travel_date, fare_type, search_date, source)."""
        seen = set()
        deduped = []
        for rec in records:
            key = (
                rec["carrier"],
                rec["flight_no"],
                rec["travel_date"],
                rec["fare_type"],
                rec["search_date"],
                rec["source"],
            )
            if key not in seen:
                seen.add(key)
                deduped.append(rec)
            else:
                logger.debug(f"Duplicate record ignored: {key}")
        return deduped

    def detect_outliers_mad(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Robust outlier detection using Median Absolute Deviation (MAD) within (route x lead_days x carrier).

        Flags outliers without deleting them.
        """
        # Group available records by cell
        groups: dict[tuple[str, int, str], list[int]] = {}
        for idx, rec in enumerate(records):
            if rec["status"] == "available" and rec["total_fare"] > 0:
                cell_key = (rec["route_id"], rec["lead_days"], rec["carrier"])
                groups.setdefault(cell_key, []).append(idx)

        for cell_key, indices in groups.items():
            if len(indices) < 3:
                # Need at least 3 points for meaningful MAD outlier calculation
                continue

            fares = np.array([records[i]["total_fare"] for i in indices])
            median = float(np.median(fares))
            abs_dev = np.abs(fares - median)
            mad = float(np.median(abs_dev))

            if mad == 0:
                continue

            # Modified Z-score: 0.6745 * |x - median| / MAD
            mod_z_scores = 0.6745 * abs_dev / mad

            for idx_pos, i in enumerate(indices):
                if mod_z_scores[idx_pos] > 3.5:
                    records[i]["outlier_flag"] = True
                    logger.info(
                        f"MAD Outlier detected: Fare {records[i]['total_fare']} for cell {cell_key} "
                        f"(Modified Z-Score = {mod_z_scores[idx_pos]:.2f})"
                    )

        return records

    def process_raw_records(
        self, raw_records: list[dict[str, Any]], run_id: str
    ) -> tuple[list[dict[str, Any]], int]:
        """Executes full cleaning pipeline: validate -> normalize -> dedup -> MAD outlier detection."""
        valid_records = []
        reject_count = 0

        for raw_rec in raw_records:
            is_valid, reason = self.validate_record(raw_rec)
            if is_valid:
                norm_rec = self.normalize_record(raw_rec, run_id)
                valid_records.append(norm_rec)
            else:
                reject_count += 1
                logger.warning(f"Record validation rejected ({reason}): {raw_rec}")

        logger.info(f"Validation summary for run '{run_id}': {len(valid_records)} valid, {reject_count} rejected.")

        # Deduplicate
        deduped_records = self.deduplicate(valid_records)
        logger.info(f"Deduplication summary for run '{run_id}': {len(valid_records) - len(deduped_records)} duplicates removed.")

        # Outlier detection (flag, don't delete)
        cleaned_records = self.detect_outliers_mad(deduped_records)

        return cleaned_records, reject_count

    def load_to_db(self, records: list[dict[str, Any]], raw_records: list[dict[str, Any]], run_id: str, source: str):
        """Idempotently loads raw and cleaned records into database."""
        db = next(get_db())
        try:
            # 1. Idempotency check: clear previous records for same run_id
            db.query(FareClean).filter(FareClean.run_id == run_id).delete()
            db.query(RawQuote).filter(RawQuote.run_id == run_id).delete()

            # 2. Insert raw quotes
            scraped_at_iso = datetime.now().isoformat()
            raw_objs = [
                RawQuote(
                    run_id=run_id,
                    source=source,
                    payload=raw_rec,
                    scraped_at=scraped_at_iso,
                )
                for raw_rec in raw_records
            ]
            db.bulk_save_objects(raw_objs)

            # 3. Ensure route entries exist in routes table
            for rec in records:
                route_id = rec["route_id"]
                existing_route = db.query(RouteModel).filter(RouteModel.route_id == route_id).first()
                if not existing_route:
                    origin, dest = route_id.split("-")
                    db.add(RouteModel(route_id=route_id, origin=origin, destination=dest, dgca_pax=1000.0, weight=1.0, active=True))

            # 4. Insert cleaned fare quotes
            fare_objs = [
                FareClean(
                    quote_id=rec["quote_id"],
                    route_id=rec["route_id"],
                    carrier=rec["carrier"],
                    flight_no=rec["flight_no"],
                    lead_days=rec["lead_days"],
                    fare_type=rec["fare_type"],
                    base_fare=rec["base_fare"],
                    taxes=rec["taxes"],
                    udf=rec["udf"],
                    conv_fee=rec["conv_fee"],
                    total_fare=rec["total_fare"],
                    search_date=rec["search_date"],
                    travel_date=rec["travel_date"],
                    stops=rec["stops"],
                    dep_band=rec["dep_band"],
                    status=rec["status"],
                    outlier_flag=rec["outlier_flag"],
                    run_id=rec["run_id"],
                )
                for rec in records
            ]
            db.bulk_save_objects(fare_objs)
            db.commit()

            logger.info(f"Successfully committed {len(raw_objs)} raw and {len(fare_objs)} clean records to DB for run '{run_id}'.")

        except Exception as e:
            db.rollback()
            logger.error(f"Error persisting pipeline results to DB: {e}")
            raise
        finally:
            db.close()

    def run_pipeline_for_raw_run(self, run_id: str, source: str) -> list[dict[str, Any]]:
        """Reads raw JSONL file for run_id and executes full cleaning and database load."""
        raw_file = self.raw_data_dir / source / f"{run_id}.jsonl"
        if not raw_file.exists():
            raise FileNotFoundError(f"Raw data file not found: {raw_file}")

        raw_records = []
        with open(raw_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    raw_records.append(json.loads(line))

        cleaned_records, reject_count = self.process_raw_records(raw_records, run_id)
        self.load_to_db(cleaned_records, raw_records, run_id, source)

        return cleaned_records
