"""Capture query-plan evidence for the materialization optimisation.

The most expensive analytical query is Q1 (prayer x religion raised: a full
mart scan plus window aggregation). This script runs its compiled SQL twice:

  BEFORE  against the mart's *view definition* (the compiled mart SQL inlined),
          i.e. what every analysis would pay if marts were materialized as
          views: the unpivot -> metadata joins -> re-pivot recomputed per query
  AFTER   against the materialized mart table (the project's actual config)

and saves EXPLAIN ANALYZE plans plus repeated-run timings under
/report/evidence/query_plans/.

Run after `python -m pipeline.main all`:
    python scripts/capture_query_plans.py
"""

from __future__ import annotations

import re
import statistics
import sys
import time
from pathlib import Path

import duckdb

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPILED = REPO_ROOT / "dbt" / "target" / "compiled" / "gss_pipeline"
OUT_DIR = REPO_ROOT / "report" / "evidence" / "query_plans"
DB_PATH = REPO_ROOT / "source" / "data" / "processed" / "gss.duckdb"

QUERY = COMPILED / "analyses" / "q1_prayer_frequency_by_religion_raised.sql"
MART = COMPILED / "models" / "marts" / "mart_respondent_survey.sql"

MART_RELATION = re.compile(r'"\w+"\."main_marts"\."mart_respondent_survey"')
REPEATS = 25


def timed(conn, sql: str) -> list[float]:
    timings = []
    for _ in range(REPEATS):
        start = time.perf_counter()
        conn.execute(sql).fetchall()
        timings.append((time.perf_counter() - start) * 1000)
    return timings


def main() -> int:
    if not QUERY.exists():
        raise SystemExit("compiled SQL not found - run `python -m pipeline.main all` first")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    query_sql = QUERY.read_text(encoding="utf-8")
    mart_sql = MART.read_text(encoding="utf-8")

    conn = duckdb.connect(str(DB_PATH), read_only=True)
    conn.execute(f"CREATE TEMP VIEW mart_as_view AS {mart_sql}")
    view_query = MART_RELATION.sub("mart_as_view", query_sql)
    assert view_query != query_sql, "mart relation not found in compiled query"

    results = {}
    for label, sql in (("before_view", view_query), ("after_table", query_sql)):
        plan = conn.execute(f"EXPLAIN ANALYZE {sql}").fetchall()
        plan_text = "\n".join(row[1] for row in plan)
        (OUT_DIR / f"q1_plan_{label}.txt").write_text(plan_text, encoding="utf-8")
        results[label] = timed(conn, sql)
    conn.close()

    lines = [
        "# Query plan evidence - Q1 (prayer frequency by religion raised)",
        "",
        f"DuckDB {duckdb.__version__}; {REPEATS} repeated executions each; times in ms.",
        "",
        "| variant | median | mean | min | max |",
        "|---|---|---|---|---|",
    ]
    for label, timings in results.items():
        lines.append(
            f"| {label} | {statistics.median(timings):.1f} | "
            f"{statistics.mean(timings):.1f} | {min(timings):.1f} | {max(timings):.1f} |"
        )
    speedup = statistics.median(results["before_view"]) / statistics.median(results["after_table"])
    lines += [
        "",
        f"Median speedup from materializing the mart as a table: **{speedup:.1f}x**.",
        "",
        "Full EXPLAIN ANALYZE output: q1_plan_before_view.txt / q1_plan_after_table.txt.",
    ]
    summary = OUT_DIR / "comparison.md"
    summary.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nwritten to {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
