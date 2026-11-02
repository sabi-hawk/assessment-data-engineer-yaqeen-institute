"""Build the two committed GSS JSON extracts from official NORC single-year data releases.

The assignment asks for two extracts ("cuts") built in the GSS Data Explorer and
exported as JSON. The Data Explorer requires an interactive, authenticated session
and offers no API, so this script reproduces the same cuts from NORC's official,
publicly hosted single-year GSS data releases (https://gss.norc.org/us/en/gss/get-the-data.html).
See docs/gss_data_explorer_instructions.md for the manual Data Explorer path and
the report for the documented deviation.

No survey values are altered: original response codes are preserved, and Stata
tagged missing values (.d = don't know, .i = inapplicable, .n = no answer, ...)
are carried through as explicit string tags.

Usage:
    python scripts/build_extracts.py
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pyreadstat

REPO_ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = REPO_ROOT / "source" / "data" / "external"
RAW_DIR = REPO_ROOT / "source" / "data" / "raw"

NORC_URL = "https://gss.norc.org/content/dam/gss/get-the-data/documents/stata/{year}_stata.zip"

# Deliberate year choice (see docs/design_note.md and report section 2):
# 2014/2016/2018 are the three most recent consecutive in-person waves in which
# every required variable (incl. INTTECH, POSTLIFE, RELITEN, NEWS, WWWHR and the
# WTSSPS weight) was fielded. 2021 is excluded: web mode, no POSTLIFE/RELITEN.
EXTRACTS = {
    "gss_extract_1_2014_2016": [2014, 2016],
    "gss_extract_2_2016_2018": [2016, 2018],
}

# Respondent-level variables included in both cuts (lower-case GSS mnemonics).
VARIABLES = [
    "id", "year", "ballot",
    # business questions
    "wrkstat", "evwork", "educ", "degree", "indus10", "satjob",
    "postlife", "pray", "relig16", "news", "tvhours", "inttech",
    # required religiosity / media scope
    "relig", "attend", "reliten", "wwwhr",
    # demographics and weight
    "age", "sex", "region", "wtssps",
]

# Verbatim citation required by the GSS terms and conditions
# (https://gss.norc.org/terms-and-conditions, retrieved 2026-11-02).
CITATION = (
    "Davern, Michael; Bautista, Rene; Freese, Jeremy; Herd, Pamela; and Morgan, "
    "Stephen L. General Social Survey 1972-2024. [Machine-readable data file]. "
    "Principal Investigator, Michael Davern; Co-Principal Investigators, Rene "
    "Bautista, Jeremy Freese, Pamela Herd, and Stephen L. Morgan. NORC ed. "
    "Chicago, 2026. 1 datafile and 1 codebook (2024 Release 3a)."
)


def download_year(year: int) -> Path:
    """Download (or reuse a cached copy of) NORC's single-year Stata release."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = CACHE_DIR / f"{year}_stata.zip"
    if not zip_path.exists():
        url = NORC_URL.format(year=year)
        print(f"downloading {url}")
        urllib.request.urlretrieve(url, zip_path)  # noqa: S310 - fixed https host
    return zip_path


def extract_dta(zip_path: Path, year: int) -> Path:
    """Unpack the GSS<year>.dta member (location inside the zip varies by year)."""
    out_dir = CACHE_DIR / f"{year}_stata"
    with zipfile.ZipFile(zip_path) as zf:
        member = next(m for m in zf.namelist() if m.lower().endswith(".dta"))
        zf.extract(member, out_dir)
    return out_dir / member


def load_year(year: int) -> list[dict]:
    """Read one survey year, preserving original codes and tagged missing values."""
    dta_path = extract_dta(download_year(year), year)
    df, _ = pyreadstat.read_dta(
        str(dta_path),
        usecols=VARIABLES,
        encoding="LATIN1",
        user_missing=True,  # keep .d/.i/.n distinctions instead of collapsing to NaN
    )
    records = []
    for row in df.to_dict(orient="records"):
        rec = {}
        for var in VARIABLES:
            rec[var] = normalise_value(row.get(var))
        records.append(rec)
    records.sort(key=lambda r: (r["year"], r["id"]))
    return records


def normalise_value(value):
    """Map a raw cell to its JSON representation.

    - genuine numeric codes/values -> int (or float for non-integral values)
    - Stata tagged missing ('d', 'i', 'n', ...) -> '.d', '.i', '.n', ...
    - system missing (NaN/None) -> None
    """
    if value is None:
        return None
    if isinstance(value, str):
        return f".{value}"
    if isinstance(value, float):
        if math.isnan(value):
            return None
        if value.is_integer():
            return int(value)
        return round(value, 6)
    return int(value)


def write_extract(name: str, years: list[int], year_records: dict[int, list[dict]]) -> None:
    records = [rec for year in years for rec in year_records[year]]
    payload = {
        "extract": {
            "name": name,
            "source": (
                "NORC General Social Survey, official single-year data releases "
                "(https://gss.norc.org/us/en/gss/get-the-data.html)"
            ),
            "built_by": "scripts/build_extracts.py",
            "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "years": years,
            "variables": VARIABLES,
            "record_count": len(records),
            "grain": "one record per respondent per survey year; natural key (year, id)",
            "missing_value_tags": {
                ".d": "don't know",
                ".i": "inapplicable (not asked of this respondent / ballot)",
                ".n": "no answer",
                ".s": "skipped on web",
                ".r": "refused",
                ".u": "uncodeable",
                ".x": "not available in this release",
                ".y": "not available in this year",
                ".z": "see codebook",
            },
            "citation": CITATION,
        },
        "records": records,
    }
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RAW_DIR / f"{name}.json"
    # one record per line keeps git diffs and code review readable
    lines = [json.dumps(rec, separators=(",", ":")) for rec in records]
    header = json.dumps(payload["extract"], indent=2)
    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write('{\n"extract": ' + header + ',\n"records": [\n')
        fh.write(",\n".join(lines))
        fh.write("\n]\n}\n")
    digest = hashlib.sha256(out_path.read_bytes()).hexdigest()
    print(f"wrote {out_path.relative_to(REPO_ROOT)}  records={len(records)}  sha256={digest}")


def main() -> int:
    needed_years = sorted({y for years in EXTRACTS.values() for y in years})
    year_records = {year: load_year(year) for year in needed_years}
    for year in needed_years:
        print(f"year {year}: {len(year_records[year])} respondents")
    for name, years in EXTRACTS.items():
        write_extract(name, years, year_records)
    return 0


if __name__ == "__main__":
    sys.exit(main())
