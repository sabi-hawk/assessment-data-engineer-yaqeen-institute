"""Structural validation of extract files (malformed JSON and schema surprises)."""

import pytest

from pipeline.extract_loader import ExtractFormatError, load_extract
from tests.conftest import make_record


def test_loads_well_formed_extract(write_extract_file):
    path = write_extract_file([make_record()])
    extract = load_extract("test_extract", path)
    assert extract.name == "test_extract"
    assert len(extract.records) == 1
    assert len(extract.sha256) == 64


def test_missing_file_raises():
    with pytest.raises(ExtractFormatError, match="not found"):
        load_extract("missing", __import__("pathlib").Path("does/not/exist.json"))


def test_malformed_json_raises(write_extract_file):
    path = write_extract_file(None, raw_text='{"extract": {, truncated')
    with pytest.raises(ExtractFormatError, match="not valid JSON"):
        load_extract("bad", path)


def test_missing_records_array_raises(write_extract_file):
    path = write_extract_file(None, raw_text='{"extract": {"name": "x"}}')
    with pytest.raises(ExtractFormatError, match="records"):
        load_extract("bad", path)


def test_missing_metadata_raises(write_extract_file):
    path = write_extract_file(None, raw_text='{"records": []}')
    with pytest.raises(ExtractFormatError, match="metadata"):
        load_extract("bad", path)


def test_non_object_record_raises(write_extract_file):
    path = write_extract_file(
        None, raw_text='{"extract": {"name": "x"}, "records": [1, 2]}'
    )
    with pytest.raises(ExtractFormatError, match="must be an object"):
        load_extract("bad", path)
