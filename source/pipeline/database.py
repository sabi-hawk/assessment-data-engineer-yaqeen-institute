"""DuckDB persistence: schema initialisation and idempotent extract loading.

Loading strategy (see docs/design_note.md):
- the raw layer stores records exactly as received, one row per
  (extract_name, year, id), enforced by a primary key. Overlapping respondents
  therefore appear once per extract in raw and are deduplicated downstream in
  the dbt staging layer, which keeps raw a faithful copy of the source files.
- each extract is loaded with delete-then-insert inside a single transaction,
  so a re-run (or a crashed run) can never duplicate or half-load an extract.
- an unchanged file (same sha256, same loaded row count) is skipped entirely,
  making repeated runs cheap no-ops. --force overrides the skip.
- every load writes an audit row (raw.load_audit) recording what ran, what it
  processed and how it ended.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from .config import EXPECTED_VARIABLES
from .extract_loader import ExtractFile
from .validation import ValidationResult

logger = logging.getLogger(__name__)

# Variables stored as raw text codes; year and id are typed since they form the key.
VALUE_COLUMNS = tuple(v for v in EXPECTED_VARIABLES if v not in ("year", "id"))


class DatabaseError(Exception):
    """Raised when the database cannot be opened or a load fails."""


@dataclass
class LoadStats:
    extract_name: str
    status: str                 # loaded | skipped_unchanged | failed
    records_in_file: int
    records_valid: int
    records_quarantined: int
    records_inserted: int
    records_replaced: int
    overlap_rows_with_other_extracts: int


class GssDatabase:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.conn = duckdb.connect(str(db_path))
        except duckdb.Error as exc:  # e.g. file locked or unwritable path
            raise DatabaseError(f"cannot open database at {db_path}: {exc}") from exc
        self.db_path = db_path

    def close(self) -> None:
        self.conn.close()

    def init_schema(self) -> None:
        value_cols = ",\n            ".join(f"{col} VARCHAR" for col in VALUE_COLUMNS)
        self.conn.execute("CREATE SCHEMA IF NOT EXISTS raw")
        self.conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS raw.extract_records (
                extract_name VARCHAR NOT NULL,
                year         INTEGER NOT NULL,
                id           INTEGER NOT NULL,
                {value_cols},
                run_id       VARCHAR NOT NULL,
                loaded_at    TIMESTAMP NOT NULL,
                PRIMARY KEY (extract_name, year, id)
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS raw.load_audit (
                run_id             VARCHAR NOT NULL,
                extract_name       VARCHAR NOT NULL,
                file_sha256        VARCHAR NOT NULL,
                started_at         TIMESTAMP NOT NULL,
                finished_at        TIMESTAMP,
                records_in_file    INTEGER,
                records_valid      INTEGER,
                records_quarantined INTEGER,
                records_inserted   INTEGER,
                records_replaced   INTEGER,
                overlap_rows_with_other_extracts INTEGER,
                status             VARCHAR NOT NULL
            )
            """
        )
        logger.info("database schema initialised at %s", self.db_path)

    # -- loading ------------------------------------------------------------

    def _last_successful_sha(self, extract_name: str) -> str | None:
        row = self.conn.execute(
            """
            SELECT file_sha256
            FROM raw.load_audit
            WHERE extract_name = ? AND status IN ('loaded', 'skipped_unchanged')
            ORDER BY started_at DESC
            LIMIT 1
            """,
            [extract_name],
        ).fetchone()
        return row[0] if row else None

    def _current_row_count(self, extract_name: str) -> int:
        return self.conn.execute(
            "SELECT count(*) FROM raw.extract_records WHERE extract_name = ?",
            [extract_name],
        ).fetchone()[0]

    def load_extract(
        self,
        extract: ExtractFile,
        validation: ValidationResult,
        run_id: str,
        force: bool = False,
    ) -> LoadStats:
        started_at = datetime.now(timezone.utc)
        existing_rows = self._current_row_count(extract.name)

        if (
            not force
            and self._last_successful_sha(extract.name) == extract.sha256
            and existing_rows == validation.valid_count
        ):
            logger.info(
                "%s unchanged (sha256 match, %d rows already loaded) - skipping",
                extract.name, existing_rows,
            )
            stats = LoadStats(
                extract.name, "skipped_unchanged",
                validation.total_records, validation.valid_count,
                validation.quarantined_count, 0, 0,
                self._overlap_rows(extract.name),
            )
            self._write_audit(run_id, extract, validation, stats, started_at)
            return stats

        rows = [
            [extract.name, rec["year"], rec["id"]]
            + [_as_text(rec.get(col)) for col in VALUE_COLUMNS]
            + [run_id, started_at]
            for rec in validation.valid_records
        ]
        placeholders = ", ".join("?" for _ in range(len(VALUE_COLUMNS) + 5))

        try:
            self.conn.execute("BEGIN TRANSACTION")
            self.conn.execute(
                "DELETE FROM raw.extract_records WHERE extract_name = ?",
                [extract.name],
            )
            self.conn.executemany(
                f"INSERT INTO raw.extract_records VALUES ({placeholders})", rows
            )
            self.conn.execute("COMMIT")
        except duckdb.Error as exc:
            self.conn.execute("ROLLBACK")
            stats = LoadStats(
                extract.name, "failed",
                validation.total_records, validation.valid_count,
                validation.quarantined_count, 0, 0, 0,
            )
            self._write_audit(run_id, extract, validation, stats, started_at)
            raise DatabaseError(f"load of {extract.name} failed: {exc}") from exc

        stats = LoadStats(
            extract.name, "loaded",
            validation.total_records, validation.valid_count,
            validation.quarantined_count,
            records_inserted=len(rows),
            records_replaced=existing_rows,
            overlap_rows_with_other_extracts=self._overlap_rows(extract.name),
        )
        self._write_audit(run_id, extract, validation, stats, started_at)
        logger.info(
            "%s loaded: %d inserted (%d replaced), %d overlap rows shared with other extracts",
            extract.name, stats.records_inserted, stats.records_replaced,
            stats.overlap_rows_with_other_extracts,
        )
        return stats

    def _overlap_rows(self, extract_name: str) -> int:
        """Rows of this extract whose (year, id) also arrived via another extract."""
        return self.conn.execute(
            """
            SELECT count(*)
            FROM raw.extract_records a
            WHERE a.extract_name = ?
              AND EXISTS (
                  SELECT 1 FROM raw.extract_records b
                  WHERE b.extract_name <> a.extract_name
                    AND b.year = a.year AND b.id = a.id
              )
            """,
            [extract_name],
        ).fetchone()[0]

    def _write_audit(
        self,
        run_id: str,
        extract: ExtractFile,
        validation: ValidationResult,
        stats: LoadStats,
        started_at: datetime,
    ) -> None:
        self.conn.execute(
            "INSERT INTO raw.load_audit VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                run_id, extract.name, extract.sha256,
                started_at, datetime.now(timezone.utc),
                stats.records_in_file, stats.records_valid,
                stats.records_quarantined, stats.records_inserted,
                stats.records_replaced, stats.overlap_rows_with_other_extracts,
                stats.status,
            ],
        )


def _as_text(value) -> str | None:
    """Raw layer stores original codes verbatim as text ('.d' tags included)."""
    if value is None:
        return None
    return str(value)
