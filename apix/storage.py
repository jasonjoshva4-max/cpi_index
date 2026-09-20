"""Append-only raw JSON Lines storage module for APIx."""
import json
import logging
from pathlib import Path
from typing import Any

from apix.config import RAW_DATA_DIR
from apix.models import AirfareRecord

logger = logging.getLogger(__name__)


class RawJSONLStore:
    """Manages append-only JSON Lines raw data store."""

    def __init__(self, base_dir: Path = RAW_DATA_DIR):
        self.base_dir = base_dir

    def get_file_path(self, source: str, run_id: str) -> Path:
        source_dir = self.base_dir / source
        source_dir.mkdir(parents=True, exist_ok=True)
        return source_dir / f"{run_id}.jsonl"

    def write_records(
        self,
        source: str,
        run_id: str,
        records: list[AirfareRecord | dict[str, Any]],
    ) -> Path:
        """Appends raw records as line-delimited JSON objects."""
        if not records:
            logger.info(f"No records to write for source '{source}', run '{run_id}'")
            return self.get_file_path(source, run_id)

        file_path = self.get_file_path(source, run_id)
        with open(file_path, "a", encoding="utf-8") as f:
            for record in records:
                if isinstance(record, AirfareRecord):
                    rec_dict = record.to_dict()
                else:
                    rec_dict = record
                line = json.dumps(rec_dict, ensure_ascii=False)
                f.write(line + "\n")

        logger.info(f"Appended {len(records)} records to {file_path}")
        return file_path
