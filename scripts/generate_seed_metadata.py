"""Generate the dbt metadata seeds from official NORC value labels.

Writes three machine-readable, version-controlled seeds under /dbt/seeds:

- variable_metadata.csv            one row per analysis variable
- response_code_metadata.csv       one row per (variable, code), labels taken
                                   verbatim from NORC's Stata value labels
- variable_ballot_availability.csv one row per (variable, year, ballot), with
                                   asked=false where >=99.5% of a ballot is IAP
                                   (ballot rotation inferred from the data)

Run after (re)building the extracts:
    python scripts/build_extracts.py
    python scripts/generate_seed_metadata.py
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pyreadstat

REPO_ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = REPO_ROOT / "source" / "data" / "external"
RAW_DIR = REPO_ROOT / "source" / "data" / "raw"
SEED_DIR = REPO_ROOT / "dbt" / "seeds"

YEARS = (2014, 2016, 2018)

CATEGORICAL = (
    "wrkstat", "evwork", "degree", "indus10", "satjob", "postlife", "pray",
    "relig16", "news", "inttech", "relig", "attend", "reliten", "sex", "region",
)
NUMERIC = ("educ", "tvhours", "wwwhr", "age")
ALL_VARS = CATEGORICAL + NUMERIC

TAG_CLASS = {
    "d": "dont_know",
    "i": "not_applicable",   # refined to not_asked_ballot downstream via ballot seed
    "n": "no_answer",
    "s": "skipped_on_web",
    "r": "refused",
    "u": "other_missing",
    "x": "other_missing",
    "y": "other_missing",
    "z": "other_missing",
}
TAG_LABEL = {
    "d": "Don't know",
    "i": "Inapplicable (question not asked of this respondent)",
    "n": "No answer",
    "s": "Skipped on web",
    "r": "Refused",
    "u": "Uncodeable",
    "x": "Not available in this release",
    "y": "Not available in this year",
    "z": "See codebook",
}

# Business-question mapping and universe notes (authoritative source: GSS
# codebook via gssdataexplorer.norc.org; universes verified empirically against
# the extracts - see docs/data_profile.md).
VARIABLE_NOTES = {
    "wrkstat":  ("What is the respondent's working status?", "All respondents", ""),
    "evwork":   ("If not currently working: have they ever worked for as long as one year?",
                 "Respondents not currently working (IAP for those working full/part time)",
                 "The GSS asks 'as long as one year', which operationalises the brief's '12 months or more'."),
    "educ":     ("What is the respondent's education level? (years of school)", "All respondents", ""),
    "degree":   ("What is the respondent's education level? (highest degree)", "All respondents", ""),
    "indus10":  ("What industry does the respondent work in?",
                 "Respondents who are working or have ever worked",
                 "NAICS 2007 industry codes (NORC variable label); very granular, so analyses group or rank rather than enumerate."),
    "satjob":   ("How satisfied are they with their line of work?",
                 "Respondents currently or previously working", ""),
    "postlife": ("Do they believe in life after death?", "All respondents in 2014/2016/2018",
                 "High share of genuine 'don't know' answers (~10%): a substantive response, kept distinct."),
    "pray":     ("How frequently does the respondent pray?", "All respondents", ""),
    "relig16":  ("Which religion was the respondent raised in?", "All respondents", ""),
    "news":     ("How often does the respondent read a newspaper?",
                 "Ballots 1-2 only (not fielded on ballot 3 in 2014-2018)", ""),
    "tvhours":  ("How often does the respondent watch TV? (hours per day)",
                 "Ballots 1-2 only (not fielded on ballot 3 in 2014-2018)", ""),
    "inttech":  ("Is the respondent interested in technology? (interest in new technologies)",
                 "Science-module subsample; ballot rotation differs per year", ""),
    "relig":    ("Respondent's current religious preference", "All respondents", ""),
    "attend":   ("How often the respondent attends religious services", "All respondents", ""),
    "reliten":  ("Strength of religious affiliation", "Respondents with a religious preference", ""),
    "wwwhr":    ("Hours per week using the web", "Internet users on ballots 1-2",
                 "IAP combines ballot rotation (ballot 3) and the non-user filter; the ballot seed separates them."),
    "age":      ("Respondent's age", "All respondents", "Top-coded at 89 ('89 or older')."),
    "sex":      ("Respondent's sex", "All respondents", ""),
    "region":   ("Census region of interview", "All respondents", ""),
}


def dta_path(year: int) -> Path:
    for candidate in CACHE_DIR.rglob(f"GSS{year}.dta"):
        return candidate
    raise SystemExit(
        f"GSS{year}.dta not found under {CACHE_DIR}; run scripts/build_extracts.py first"
    )


def load_labels() -> tuple[dict, dict]:
    """Merge value labels and column labels across years; verify consistency."""
    value_labels: dict[str, dict] = {v: {} for v in ALL_VARS}
    column_labels: dict[str, str] = {}
    for year in YEARS:
        _, meta = pyreadstat.read_dta(
            str(dta_path(year)), metadataonly=True, encoding="LATIN1"
        )
        names = {n.lower(): n for n in meta.column_names}
        col_label = dict(zip((n.lower() for n in meta.column_names), meta.column_labels))
        for var in ALL_VARS:
            labels = meta.variable_value_labels.get(names[var], {})
            for code, label in labels.items():
                if isinstance(code, float) and code.is_integer():
                    code = int(code)
                key = str(code)
                previous = value_labels[var].get(key)
                if previous is not None and previous != label:
                    print(f"note: {var} code {key}: label differs across years "
                          f"({previous!r} vs {label!r}); keeping first")
                    continue
                value_labels[var][key] = label
            column_labels.setdefault(var, col_label.get(var, var))
    return value_labels, column_labels


def observed_stats() -> tuple[dict, dict, dict]:
    """Observed missing tags, numeric ranges and ballot availability per variable."""
    records: dict[tuple, dict] = {}
    for f in sorted(RAW_DIR.glob("gss_extract_*.json")):
        payload = json.loads(f.read_text(encoding="utf-8"))
        for rec in payload["records"]:
            records.setdefault((rec["year"], rec["id"]), rec)

    tags: dict[str, set] = {v: set() for v in ALL_VARS}
    ranges: dict[str, list] = {v: [None, None] for v in NUMERIC}
    ballot: dict[tuple, list] = {}
    for rec in records.values():
        for var in ALL_VARS:
            value = rec.get(var)
            if isinstance(value, str):
                tags[var].add(value.lstrip("."))
            elif value is not None and var in ranges:
                low, high = ranges[var]
                ranges[var] = [
                    value if low is None else min(low, value),
                    value if high is None else max(high, value),
                ]
            key = (var, rec["year"], rec["ballot"])
            total_iap = ballot.setdefault(key, [0, 0])
            total_iap[0] += 1
            if value == ".i":
                total_iap[1] += 1
    return tags, ranges, ballot


def main() -> int:
    SEED_DIR.mkdir(parents=True, exist_ok=True)
    value_labels, column_labels = load_labels()
    tags, ranges, ballot = observed_stats()

    with open(SEED_DIR / "response_code_metadata.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(
            ["variable_name", "code", "label", "response_class", "is_genuine_response", "metadata_source"]
        )
        for var in ALL_VARS:
            is_numeric = var in NUMERIC
            for code, label in sorted(
                value_labels[var].items(),
                key=lambda kv: (len(kv[0]), kv[0]),
            ):
                if code.isdigit() or (code.startswith("-") and code[1:].isdigit()):
                    if is_numeric:
                        # numeric variables: labelled boundary values (e.g. '89 OR OLDER')
                        # are genuine values; the range check validates them
                        continue
                    writer.writerow(
                        [var, code, label.strip(), "valid", "true",
                         "NORC GSS single-year Stata release value labels"]
                    )
            for tag in sorted(tags[var]):
                writer.writerow(
                    [var, f".{tag}", TAG_LABEL[tag], TAG_CLASS[tag], "false",
                     "GSS tagged missing values (NORC Stata releases)"]
                )

    with open(SEED_DIR / "variable_metadata.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(
            ["variable_name", "business_question", "description", "value_type",
             "years_available", "valid_min", "valid_max", "universe", "limitations"]
        )
        for var in ALL_VARS:
            question, universe, limitation = VARIABLE_NOTES[var]
            vmin, vmax = ranges.get(var, (None, None)) if var in NUMERIC else ("", "")
            writer.writerow(
                [var, question, column_labels[var].strip(),
                 "numeric" if var in NUMERIC else "categorical",
                 "|".join(str(y) for y in YEARS),
                 vmin if vmin is not None else "", vmax if vmax is not None else "",
                 universe, limitation]
            )

    with open(SEED_DIR / "variable_ballot_availability.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(["variable_name", "year", "ballot", "asked_on_ballot"])
        for (var, year, b), (total, iap) in sorted(ballot.items()):
            asked = (iap / total) < 0.995 if total else True
            writer.writerow([var, year, b, "true" if asked else "false"])

    for name in ("response_code_metadata.csv", "variable_metadata.csv",
                 "variable_ballot_availability.csv"):
        n_rows = sum(1 for _ in open(SEED_DIR / name, encoding="utf-8")) - 1
        print(f"wrote dbt/seeds/{name}: {n_rows} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
