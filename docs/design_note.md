# Design Note — GSS Respondent Pipeline

_Written before pipeline development (Section 2.1 of the brief). Divergences
between this note and the final build are listed at the end and in the report._

## 1. Core table grain

One row per **respondent-year observation**. The GSS is a repeated
cross-section: each survey year draws a fresh sample, so a "respondent" exists
only within one wave. Every layer from staging down holds exactly one row per
observation; the raw layer additionally keys by extract to preserve the files
as received.

## 2. Respondent identification

NORC's `id` restarts at 1 every survey year (verified against the official
year files: 2016 ids run 1–2867). It is therefore **not** globally unique, and
the natural key is **(year, id)**. The pipeline exposes it as
`respondent_key = 'YYYY-NNNN'` for readability. Overlap between the two cuts is
defined on this key.

## 3. Database choice: DuckDB

- dbt-supported (dbt-duckdb), zero infrastructure, a single local file —
  matches the brief's "runs locally without paid cloud resources".
- Columnar + vectorised: the full GSS (75,700 × ~7,000) would still fit
  comfortably on a laptop.
- Supports constraints (primary keys), transactions, `EXPLAIN ANALYZE`.
- Rejected alternatives: Postgres (needs a server — disproportionate),
  SQLite (row store, weaker analytics, weaker dbt support).

## 4. Layers

| layer | owner | schema | materialization | purpose |
|---|---|---|---|---|
| raw | Python | `raw` | table | files as received, one row per (extract, year, id), values verbatim as text |
| staging | dbt | `main_staging` | view | dedup to (year, id), typing of key/weight, provenance flags, codes preserved |
| intermediate | dbt | `main_intermediate` | view | unpivot to long form; metadata-driven classification of every response |
| marts | dbt | `main_marts` | table | analyst-facing wide model: code + label/value + response_class per variable |
| seeds | dbt | `main_metadata` | table | variable / response-code / ballot-availability metadata |

## 5. Ingestion strategy

Python reads the committed JSON extracts, validates structure (loader) and
every record (validator: key, fields, types, known missing tags, in-file
duplicates, positive weights), quarantines malformed records to
`/source/data/processed/`, and loads valid records into DuckDB.

## 6. Idempotency and deduplication

- **Within an extract**: delete-then-insert of that extract's partition inside
  one transaction. A re-run or crash can never duplicate or half-load.
- **Unchanged file**: the loader compares the file's sha256 with the last
  successful load's and skips (`skipped_unchanged`), so re-runs are no-ops.
- **Across extracts (the overlap)**: raw keeps one row per (extract, year, id)
  — a faithful copy of the files; staging groups by (year, id), collapsing the
  overlap once, with `in_extract_1`/`in_extract_2` provenance flags. A singular
  dbt test asserts overlap rows are identical across extracts before collapsing.
- Load order cannot matter because extract partitions are independent and the
  staging aggregation is commutative — proven by an integration test comparing
  content fingerprints of both load orders.

## 7. Missing-value handling

Source files carry Stata tagged missing values; extracts preserve them as
`.d` / `.i` / `.n` strings. The dbt layer classifies every response into one
`response_class`: `valid`, `dont_know`, `no_answer`, `not_applicable`
(filtered out by a prior question), `not_asked_ballot` (item rotation),
`not_asked_in_year`, `system_missing`. Classification is **metadata-driven**:
three seeds generated from NORC's own value labels and the observed ballot
design; models join the seeds and never hard-code meanings. Unknown codes fail
a test instead of being guessed.

## 8. Data quality and validation

Three lines of defence: Python validation before load (structure, types, keys,
duplicates); dbt source tests on the raw tables; dbt schema + singular tests on
models (unique keys, accepted classes, overlap consistency, assignment
constraints such as ≤10,000 distinct respondents and ≥5% overlap, no unknown
codes, mart/staging count reconciliation, positive weights).

## 9. Incremental processing

At this volume (10,620 raw rows) full rebuilds are the simplest correct
strategy: adding an extract reloads only that extract's partition (others are
sha-skipped), then dbt rebuilds views (free) and the mart table (~seconds).
Incremental dbt models are deliberately **not** used — documented in the
report's efficiency section with the full-scale design.

## 10. Orchestration

A Python CLI (`python -m pipeline.main all`) runs ordered, fail-fast stages:
check-env → validate → profile → init-db → ingest → dbt seed → dbt source
tests → dbt run → dbt test → analyses → dbt docs. A failed stage aborts the
rest; failing data tests block the analyses. Airflow/Dagster would be
disproportionate for two files and one target.

- **Triggers**: runs are manual (a reviewer invoking the CLI) and automatic in
  CI on every push. Adding a new extract = commit the file, register it in
  `config.EXTRACT_FILES`, run `all`: only the new file is loaded (existing ones
  sha-skip) and dbt rebuilds downstream.
- **Failure detection**: a failed run exits non-zero (fails CI), logs the
  failing stage with its error, writes `status: failed` into the JSON run
  summary, and records a `failed` row in `raw.load_audit` for load errors.
- **Safe re-run**: just re-invoke `all`. Loads are transactional per extract
  (a crashed load leaves the previous state intact) and unchanged inputs are
  skipped, so retries converge on the same final state.

## 11. Logging and observability

Every run gets a run id, a log file under `/logs`, a JSON run summary (stage
status/durations, record counts), and a `raw.load_audit` row per extract load
(sha256, counts inserted/replaced/quarantined, overlap rows, status).

## 12. Assumptions

- The GSS Data Explorer requires an interactive account; extracts are instead
  built reproducibly from NORC's official public single-year releases, with
  Data Explorer instructions documented (see
  `docs/gss_data_explorer_instructions.md`). Same NORC data, scripted path.
- 2014/2016/2018 were chosen because every required variable (incl. INTTECH,
  POSTLIFE, RELITEN, NEWS, WWWHR, WTSSPS) is fielded in all three; 2021 lacks
  POSTLIFE/RELITEN and switched mode.
- Overlap rows are expected to be value-identical across cuts (same NORC
  release) — enforced by test, not assumed silently.
- Analyses are unweighted by default; `sample_weight` (WTSSPS) is carried for
  weighted analysis (see report, weights bonus).

## 13. Divergence from this note in the final build

None material. One addition made during implementation: a third seed
(`variable_ballot_availability`) was introduced after profiling showed `.i`
conflates ballot rotation with respondent-level filters; the seed lets the
classifier separate `not_asked_ballot` from `not_applicable`.
