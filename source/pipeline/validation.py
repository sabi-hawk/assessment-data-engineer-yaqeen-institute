"""Record-level validation of extract contents.

Checks every record against the documented extract schema:
- the natural key (year, id) is present, well-typed and in the expected range
- every expected variable is present
- values are genuine codes (numbers), known missing-value tags, or null
- no duplicate (year, id) within one extract

Records that fail a fatal check are quarantined (excluded from the load and
written to /source/data/processed for inspection) rather than silently dropped
or allowed to corrupt the load. A validation failure of the file as a whole
stops the pipeline.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from .config import EXPECTED_VARIABLES, KNOWN_MISSING_TAGS, SURVEY_YEARS
from .extract_loader import ExtractFile

logger = logging.getLogger(__name__)


@dataclass
class QuarantinedRecord:
    index: int
    issues: list[str]
    record: dict


@dataclass
class ValidationResult:
    extract_name: str
    total_records: int = 0
    valid_records: list[dict] = field(default_factory=list)
    quarantined: list[QuarantinedRecord] = field(default_factory=list)
    duplicate_keys: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def valid_count(self) -> int:
        return len(self.valid_records)

    @property
    def quarantined_count(self) -> int:
        return len(self.quarantined)

    @property
    def ok(self) -> bool:
        """The load may proceed if nothing (or only a marginal share) failed."""
        if self.total_records == 0:
            return False
        return self.quarantined_count == 0


def _record_issues(record: dict) -> list[str]:
    issues: list[str] = []

    rid = record.get("id")
    year = record.get("year")
    if not isinstance(rid, int) or isinstance(rid, bool) or rid <= 0:
        issues.append(f"invalid respondent id: {rid!r}")
    if not isinstance(year, int) or year not in SURVEY_YEARS:
        issues.append(f"survey year outside expected set {SURVEY_YEARS}: {year!r}")

    for var in EXPECTED_VARIABLES:
        if var not in record:
            issues.append(f"missing expected field: {var}")
            continue
        value = record[var]
        if value is None:
            continue
        if isinstance(value, bool):
            issues.append(f"{var}: boolean is not a valid survey code")
        elif isinstance(value, str):
            if value not in KNOWN_MISSING_TAGS:
                issues.append(f"{var}: unknown missing-value tag {value!r}")
        elif isinstance(value, (int, float)):
            if var == "wtssps" and float(value) <= 0:
                issues.append(f"wtssps: sample weight must be positive, got {value!r}")
        else:
            issues.append(f"{var}: unexpected type {type(value).__name__}")

    unexpected = set(record) - set(EXPECTED_VARIABLES)
    if unexpected:
        issues.append(f"unexpected fields: {sorted(unexpected)}")
    return issues


def validate_extract(extract: ExtractFile) -> ValidationResult:
    result = ValidationResult(extract_name=extract.name)
    result.total_records = len(extract.records)

    declared = extract.meta.get("record_count")
    if isinstance(declared, int) and declared != result.total_records:
        result.warnings.append(
            f"header record_count={declared} but file contains {result.total_records}"
        )

    declared_vars = extract.meta.get("variables")
    if declared_vars is not None and list(declared_vars) != list(EXPECTED_VARIABLES):
        result.warnings.append("header variable list differs from the expected schema")

    seen_keys: set[tuple] = set()
    for index, record in enumerate(extract.records):
        issues = _record_issues(record)
        key = (record.get("year"), record.get("id"))
        if not issues and key in seen_keys:
            result.duplicate_keys += 1
            issues.append(f"duplicate natural key within extract: {key}")
        if issues:
            result.quarantined.append(QuarantinedRecord(index, issues, record))
        else:
            seen_keys.add(key)
            result.valid_records.append(record)

    for warning in result.warnings:
        logger.warning("%s: %s", extract.name, warning)
    if result.quarantined:
        logger.error(
            "%s: %d of %d records quarantined",
            extract.name, result.quarantined_count, result.total_records,
        )
        for q in result.quarantined[:10]:
            logger.error("  record %d: %s", q.index, "; ".join(q.issues))
    else:
        logger.info(
            "%s: %d records valid, 0 quarantined", extract.name, result.valid_count
        )
    return result


def write_quarantine(result: ValidationResult, processed_dir: Path) -> Path | None:
    """Persist quarantined records for inspection; returns the file path if any."""
    if not result.quarantined:
        return None
    processed_dir.mkdir(parents=True, exist_ok=True)
    path = processed_dir / f"quarantine_{result.extract_name}.json"
    payload = [
        {"index": q.index, "issues": q.issues, "record": q.record}
        for q in result.quarantined
    ]
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info("quarantined records written to %s", path)
    return path
