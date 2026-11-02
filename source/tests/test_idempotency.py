"""Integration tests against the real committed extracts.

Prove the assignment's idempotency requirements on actual data:
- loading twice does not duplicate or alter anything
- load order (1 then 2, vs 2 then 1) yields byte-identical final content
- the overlap (shared 2016 wave) is keyed correctly in raw
- an unchanged extract is skipped, --force reload still ends identical
"""

from __future__ import annotations

import hashlib

import pytest

from pipeline.config import load_config
from pipeline.database import GssDatabase
from pipeline.extract_loader import load_extract
from pipeline.validation import validate_extract

CONFIG = load_config()


@pytest.fixture(scope="module")
def extracts():
    loaded = []
    for name, path in CONFIG.extract_paths().items():
        extract = load_extract(name, path)
        validation = validate_extract(extract)
        assert validation.ok, f"{name} failed validation"
        loaded.append((extract, validation))
    return loaded


def fresh_db(tmp_path, filename="test.duckdb"):
    db = GssDatabase(tmp_path / filename)
    db.init_schema()
    return db


def content_fingerprint(db: GssDatabase) -> str:
    """Order-independent hash of the deduplicated final dataset (run metadata excluded)."""
    rows = db.conn.execute(
        """
        SELECT * EXCLUDE (extract_name, run_id, loaded_at)
        FROM raw.extract_records
        GROUP BY ALL
        ORDER BY year, id
        """
    ).fetchall()
    return hashlib.sha256(repr(rows).encode()).hexdigest()


def row_count(db, extract_name=None):
    if extract_name:
        return db.conn.execute(
            "SELECT count(*) FROM raw.extract_records WHERE extract_name = ?",
            [extract_name],
        ).fetchone()[0]
    return db.conn.execute("SELECT count(*) FROM raw.extract_records").fetchone()[0]


def test_double_run_does_not_duplicate(tmp_path, extracts):
    db = fresh_db(tmp_path)
    for extract, validation in extracts:
        db.load_extract(extract, validation, run_id="run1")
    first_total = row_count(db)
    first_print = content_fingerprint(db)

    statuses = [
        db.load_extract(extract, validation, run_id="run2").status
        for extract, validation in extracts
    ]
    assert statuses == ["skipped_unchanged", "skipped_unchanged"]
    assert row_count(db) == first_total
    assert content_fingerprint(db) == first_print
    db.close()


def test_force_reload_is_still_idempotent(tmp_path, extracts):
    db = fresh_db(tmp_path)
    for extract, validation in extracts:
        db.load_extract(extract, validation, run_id="run1")
    before = content_fingerprint(db)
    for extract, validation in extracts:
        stats = db.load_extract(extract, validation, run_id="run2", force=True)
        assert stats.status == "loaded"
        assert stats.records_replaced == stats.records_inserted
    assert content_fingerprint(db) == before
    db.close()


def test_load_order_does_not_change_final_dataset(tmp_path, extracts):
    db_forward = fresh_db(tmp_path, "forward.duckdb")
    for extract, validation in extracts:
        db_forward.load_extract(extract, validation, run_id="run_f")

    db_reverse = fresh_db(tmp_path, "reverse.duckdb")
    for extract, validation in reversed(extracts):
        db_reverse.load_extract(extract, validation, run_id="run_r")

    assert content_fingerprint(db_forward) == content_fingerprint(db_reverse)
    db_forward.close()
    db_reverse.close()


def test_overlap_is_detected_and_keys_hold(tmp_path, extracts):
    db = fresh_db(tmp_path)
    stats = [
        db.load_extract(extract, validation, run_id="run1")
        for extract, validation in extracts
    ]
    # the shared 2016 wave: 2,867 observations present in both cuts
    assert stats[1].overlap_rows_with_other_extracts == 2867

    distinct = db.conn.execute(
        "SELECT count(DISTINCT (year, id)) FROM raw.extract_records"
    ).fetchone()[0]
    total = row_count(db)
    assert total == sum(s.records_inserted for s in stats)
    assert distinct == total - 2867  # overlap keyed per extract, nothing lost
    db.close()


def test_audit_trail_is_written(tmp_path, extracts):
    db = fresh_db(tmp_path)
    extract, validation = extracts[0]
    db.load_extract(extract, validation, run_id="runA")
    db.load_extract(extract, validation, run_id="runB")
    audit = db.conn.execute(
        "SELECT run_id, status FROM raw.load_audit ORDER BY started_at"
    ).fetchall()
    assert [status for _, status in audit] == ["loaded", "skipped_unchanged"]
    db.close()
