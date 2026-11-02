"""Record-level validation rules: every malformed shape is caught and quarantined."""

from pipeline.extract_loader import ExtractFile
from pipeline.validation import validate_extract
from tests.conftest import make_record


def validate(records, meta_overrides=None):
    meta = {"record_count": len(records)}
    meta.update(meta_overrides or {})
    extract = ExtractFile(
        name="test", path=None, sha256="0" * 64, meta=meta, records=records
    )
    return validate_extract(extract)


def test_valid_records_pass():
    result = validate([make_record(rid=1), make_record(rid=2)])
    assert result.ok
    assert result.valid_count == 2
    assert result.quarantined_count == 0


def test_missing_tag_values_are_valid():
    result = validate([make_record(pray=".d", news=".i", evwork=".n", tvhours=None)])
    assert result.ok


def test_invalid_id_is_quarantined():
    result = validate([make_record(rid=-5), make_record(id="abc", rid=2)])
    assert not result.ok
    assert result.quarantined_count == 2
    assert any("invalid respondent id" in i for q in result.quarantined for i in q.issues)


def test_unexpected_year_is_quarantined():
    result = validate([make_record(year=1999)])
    assert not result.ok
    assert "survey year" in result.quarantined[0].issues[0]


def test_missing_field_is_quarantined():
    record = make_record()
    del record["pray"]
    result = validate([record])
    assert not result.ok
    assert any("missing expected field: pray" in i for i in result.quarantined[0].issues)


def test_unknown_missing_tag_is_quarantined():
    result = validate([make_record(pray=".q")])
    assert not result.ok
    assert any("unknown missing-value tag" in i for i in result.quarantined[0].issues)


def test_unexpected_type_is_quarantined():
    result = validate([make_record(pray=[1, 2])])
    assert not result.ok


def test_non_positive_weight_is_quarantined():
    result = validate([make_record(wtssps=0)])
    assert not result.ok
    assert any("weight" in i for i in result.quarantined[0].issues)


def test_duplicate_natural_key_is_quarantined():
    result = validate([make_record(rid=7), make_record(rid=7)])
    assert not result.ok
    assert result.duplicate_keys == 1
    assert result.valid_count == 1  # first occurrence survives


def test_header_count_mismatch_warns_but_does_not_fail():
    result = validate([make_record()], meta_overrides={"record_count": 99})
    assert result.ok
    assert any("record_count" in w for w in result.warnings)


def test_unexpected_extra_field_is_quarantined():
    result = validate([make_record(surprise_column=1)])
    assert not result.ok
    assert any("unexpected fields" in i for i in result.quarantined[0].issues)
