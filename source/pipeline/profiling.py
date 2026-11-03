"""Data profiling: reproducible profile of the committed extracts.

Produces docs/data_profile.md (human-readable) and
report/evidence/data_profile_missingness.csv (machine-readable). The profile is
computed from the raw JSON extracts themselves, before any database load, so it
describes exactly what the pipeline receives.
"""

from __future__ import annotations

import csv
import logging
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .config import EXPECTED_VARIABLES, NATURAL_KEY
from .extract_loader import ExtractFile

logger = logging.getLogger(__name__)

PROFILE_VARIABLES = tuple(
    v for v in EXPECTED_VARIABLES if v not in ("id", "year", "ballot")
)

# A ballot on which >= 99.5% of a variable's values are IAP ('.i') is treated as
# "variable not fielded on this ballot" (ballot rotation) rather than a
# respondent-level filter. The 0.5% headroom absorbs stray codes.
BALLOT_NOT_ASKED_THRESHOLD = 0.995


def _key(record: dict) -> tuple:
    return tuple(record.get(k) for k in NATURAL_KEY)


def profile_extracts(extracts: list[ExtractFile]) -> dict:
    """Compute all profile metrics; returns a plain dict (also used by tests)."""
    per_extract = {}
    all_keys: dict[str, set] = {}
    for ext in extracts:
        years = Counter(r.get("year") for r in ext.records)
        keys = [_key(r) for r in ext.records]
        distinct = set(keys)
        per_extract[ext.name] = {
            "records": len(ext.records),
            "per_year": dict(sorted(years.items())),
            "distinct_respondents": len(distinct),
            "duplicate_rows_in_file": len(keys) - len(distinct),
        }
        all_keys[ext.name] = distinct

    names = list(all_keys)
    overlap = set.intersection(*all_keys.values()) if len(names) > 1 else set()
    union = set.union(*all_keys.values())
    cross = {
        "distinct_respondents_overall": len(union),
        "overlap_respondents": len(overlap),
        "overlap_pct_per_extract": {
            n: round(100 * len(overlap) / len(all_keys[n]), 1) for n in names
        },
        "exclusive_years": {
            n: sorted(
                set(per_extract[n]["per_year"])
                - set().union(*(per_extract[m]["per_year"] for m in names if m != n))
            )
            for n in names
        },
    }

    # missingness per variable per year, over the deduplicated union of records
    dedup: dict[tuple, dict] = {}
    for ext in extracts:
        for rec in ext.records:
            dedup.setdefault(_key(rec), rec)
    years = sorted({k[0] for k in dedup})

    missingness = []  # rows: variable, year, n, valid, iap, dont_know, no_answer, other_tag, system_missing
    for var in PROFILE_VARIABLES:
        for year in years:
            c: Counter = Counter()
            for (ryear, _), rec in dedup.items():
                if ryear != year:
                    continue
                value = rec.get(var)
                if value is None:
                    c["system_missing"] += 1
                elif isinstance(value, str):
                    c[{".i": "iap", ".d": "dont_know", ".n": "no_answer"}.get(value, "other_tag")] += 1
                else:
                    c["valid"] += 1
            total = sum(c.values())
            missingness.append(
                {"variable": var, "year": year, "n": total, **{
                    k: c.get(k, 0)
                    for k in ("valid", "iap", "dont_know", "no_answer", "other_tag", "system_missing")
                }}
            )

    # ballot availability: share of IAP per (variable, year, ballot)
    ballot_rows = []
    by_year_ballot: dict[tuple, list] = defaultdict(list)
    for (ryear, _), rec in dedup.items():
        by_year_ballot[(ryear, rec.get("ballot"))].append(rec)
    for var in PROFILE_VARIABLES:
        for (year, ballot), recs in sorted(by_year_ballot.items()):
            iap = sum(1 for r in recs if r.get(var) == ".i")
            share = iap / len(recs) if recs else 0.0
            ballot_rows.append(
                {
                    "variable": var, "year": year, "ballot": ballot,
                    "respondents": len(recs), "iap": iap,
                    "iap_share": round(share, 4),
                    "asked_on_ballot": share < BALLOT_NOT_ASKED_THRESHOLD,
                }
            )

    return {
        "per_extract": per_extract,
        "cross_extract": cross,
        "missingness": missingness,
        "ballot_availability": ballot_rows,
        "years": years,
    }


def write_profile(
    profile: dict, extracts: list[ExtractFile], docs_dir: Path, evidence_dir: Path
) -> Path:
    """Render the profile as Markdown (docs) and CSV (evidence)."""
    evidence_dir.mkdir(parents=True, exist_ok=True)
    docs_dir.mkdir(parents=True, exist_ok=True)

    csv_path = evidence_dir / "data_profile_missingness.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(profile["missingness"][0]))
        writer.writeheader()
        writer.writerows(profile["missingness"])

    md = _render_markdown(profile, extracts)
    md_path = docs_dir / "data_profile.md"
    md_path.write_text(md, encoding="utf-8")
    logger.info("data profile written to %s and %s", md_path, csv_path)
    return md_path


def _render_markdown(profile: dict, extracts: list[ExtractFile]) -> str:
    lines: list[str] = []
    add = lines.append
    add("# Data Profile — GSS Extracts")
    add("")
    add(f"_Generated by `pipeline.profiling` on {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC. "
        "Regenerate with `python -m pipeline.main profile` from `/source`._")
    add("")
    add("## 1. Extracts")
    add("")
    add("| extract | records | per year | distinct (year, id) | duplicate rows in file |")
    add("|---|---|---|---|---|")
    for name, stats in profile["per_extract"].items():
        per_year = ", ".join(f"{y}: {n:,}" for y, n in stats["per_year"].items())
        add(f"| {name} | {stats['records']:,} | {per_year} | "
            f"{stats['distinct_respondents']:,} | {stats['duplicate_rows_in_file']} |")
    add("")
    cross = profile["cross_extract"]
    add("## 2. Overlap between the two cuts")
    add("")
    add(f"- Distinct respondent-year observations overall: **{cross['distinct_respondents_overall']:,}** "
        "(assignment ceiling: 10,000)")
    add(f"- Observations present in both cuts: **{cross['overlap_respondents']:,}**")
    for name, pct in cross["overlap_pct_per_extract"].items():
        add(f"- Overlap as share of `{name}`: **{pct}%** (assignment floor: 5%)")
    for name, years in cross["exclusive_years"].items():
        add(f"- Years exclusive to `{name}`: **{years}**")
    add("")
    add("A GSS respondent id restarts at 1 each survey year, so identity is the pair "
        "`(year, id)`. The overlap is the full 2016 wave, present in both cuts.")
    add("")
    add("## 3. Missingness per variable per year")
    add("")
    add("Counts over the deduplicated union of both cuts. `iap` is the survey's "
        "'inapplicable' code (`.i`): the respondent was not asked, either because of "
        "ballot rotation or because a filter question routed them away. "
        "`dont_know` (`.d`) and `no_answer` (`.n`) are refusals/unknowns from "
        "respondents who **were** asked. `system_missing` would be a null in the "
        "source file (none occur in these cuts).")
    add("")
    add("| variable | year | n | valid | iap | don't know | no answer | other | pct valid | pct missing |")
    add("|---|---|---|---|---|---|---|---|---|---|")
    for row in profile["missingness"]:
        pct = 100 * row["valid"] / row["n"] if row["n"] else 0
        add(f"| {row['variable']} | {row['year']} | {row['n']:,} | {row['valid']:,} | "
            f"{row['iap']:,} | {row['dont_know']:,} | {row['no_answer']:,} | "
            f"{row['other_tag'] + row['system_missing']:,} | {pct:.1f}% | {100 - pct:.1f}% |")
    add("")
    add("**Availability across years:** every profiled variable is fielded in all "
        "three extract years (2014, 2016, 2018) - no variable is year-restricted "
        "within these cuts. The year choice was made for exactly this reason; in "
        "other GSS years this does not hold (e.g. POSTLIFE and RELITEN are absent "
        "in 2021), and the pipeline's `not_asked_in_year` classification covers "
        "that case.")
    add("")
    add("## 4. Ballot rotation (inferred from the data)")
    add("")
    add("GSS rotates many items across three ballots. A variable is reported as "
        "*not fielded* on a ballot when ≥99.5% of that ballot's respondents are IAP.")
    add("")
    not_asked = [r for r in profile["ballot_availability"] if not r["asked_on_ballot"]]
    if not_asked:
        add("| variable | year | ballot | respondents | iap |")
        add("|---|---|---|---|---|")
        for r in not_asked:
            add(f"| {r['variable']} | {r['year']} | {r['ballot']} | "
                f"{r['respondents']:,} | {r['iap']:,} |")
    else:
        add("No ballot-level exclusions detected.")
    add("")
    add("Variables with substantial IAP that is **not** ballot-driven (evwork, satjob, "
        "indus10, and wwwhr within ballots 1–2) are population filters: the question "
        "applies only to a subset (e.g. EVWORK is asked only of respondents not "
        "currently working; WWWHR only of internet users). The dbt layer separates "
        "these states: `not_asked_ballot` vs `not_applicable`.")
    add("")
    add("**What this means for the questions the pipeline can honestly answer:** "
        "questions built on NEWS or TVHOURS (Q4 TV vs job satisfaction, Q6 "
        "newspaper/TV trends) can only describe the ~2/3 of each wave on ballots 1-2; "
        "INTTECH has the thinnest coverage (~47-53% asked) so technology-interest "
        "estimates carry the widest uncertainty; EVWORK-based results (Q5) exclude "
        "the unemployed by questionnaire design; everything else (PRAY, RELIG16, "
        "POSTLIFE, WRKSTAT, DEGREE, demographics) covers effectively the full "
        "sample. Every analysis states its denominator and reports not-asked "
        "counts alongside results rather than hiding them.")
    add("")
    add("## 5. Source files")
    add("")
    for ext in extracts:
        add(f"- `{ext.path.name}` — sha256 `{ext.sha256}`")
    add("")
    return "\n".join(lines)
