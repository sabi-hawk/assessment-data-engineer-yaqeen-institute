"""Shared fixtures: a well-formed synthetic extract for unit tests.

Unit tests use small synthetic payloads (clearly not GSS data) so they are
fast and can exercise malformed input. Integration tests (test_idempotency)
run against the real committed extracts.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SOURCE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE_DIR))

from pipeline.config import EXPECTED_VARIABLES, load_config  # noqa: E402


def make_record(year: int = 2014, rid: int = 1, **overrides) -> dict:
    """A structurally valid record with every expected field."""
    record = {var: 1 for var in EXPECTED_VARIABLES}
    record.update({"id": rid, "year": year, "ballot": 1, "wtssps": 1.0})
    record.update(overrides)
    return record


@pytest.fixture
def config():
    return load_config()


@pytest.fixture
def write_extract_file(tmp_path):
    """Factory: writes an extract JSON file and returns its path."""

    def _write(records, name="test_extract", meta_overrides=None, raw_text=None):
        path = tmp_path / f"{name}.json"
        if raw_text is not None:
            path.write_text(raw_text, encoding="utf-8")
            return path
        meta = {
            "name": name,
            "variables": list(EXPECTED_VARIABLES),
            "record_count": len(records),
        }
        meta.update(meta_overrides or {})
        path.write_text(
            json.dumps({"extract": meta, "records": records}), encoding="utf-8"
        )
        return path

    return _write
