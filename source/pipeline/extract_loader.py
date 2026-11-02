"""Read and structurally validate the committed JSON extracts.

Raw files are opened read-only and never modified: all downstream work happens
in the database. A file that is not valid JSON, or that does not follow the
documented extract schema, raises ExtractFormatError before anything is loaded.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


class ExtractFormatError(Exception):
    """The extract file is malformed (bad JSON or unexpected structure)."""


@dataclass
class ExtractFile:
    name: str
    path: Path
    sha256: str
    meta: dict
    records: list[dict]


def load_extract(name: str, path: Path) -> ExtractFile:
    if not path.exists():
        raise ExtractFormatError(f"extract file not found: {path}")

    raw_bytes = path.read_bytes()
    sha256 = hashlib.sha256(raw_bytes).hexdigest()

    try:
        payload = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExtractFormatError(f"{path.name}: not valid JSON ({exc})") from exc

    if not isinstance(payload, dict):
        raise ExtractFormatError(f"{path.name}: top level must be an object")
    meta = payload.get("extract")
    records = payload.get("records")
    if not isinstance(meta, dict):
        raise ExtractFormatError(f"{path.name}: missing 'extract' metadata object")
    if not isinstance(records, list):
        raise ExtractFormatError(f"{path.name}: missing 'records' array")
    if not all(isinstance(r, dict) for r in records):
        raise ExtractFormatError(f"{path.name}: every record must be an object")

    logger.info(
        "read %s: %d records, sha256=%s", path.name, len(records), sha256[:12]
    )
    return ExtractFile(name=name, path=path, sha256=sha256, meta=meta, records=records)
