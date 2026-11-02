# Final Report — GSS Respondent Pipeline

## 1. Executive summary

Two GSS cuts (2014+2016 and 2016+2018, overlap = the full 2016 wave) are
committed as JSON, validated and idempotently loaded into DuckDB by a Python
pipeline, transformed by a four-layer dbt project whose missing-value semantics
are fully metadata-driven, and queried by seven analytical queries including
the mandatory overlap audit. Everything runs locally with one command
(`python -m pipeline.main all`, ~35 s), is covered by 22 pytest tests and 56
dbt tests (all passing), and is rebuilt from NORC sources by committed scripts.
All results in §7 are actual query outputs saved under `/report/evidence/`.

## 2. Extract selection and variable mapping

**Years.** 2014, 2016, 2018 are the three most recent consecutive in-person
waves in which *every* required variable is fielded — including INTTECH
(technology interest), POSTLIFE, RELITEN, NEWS, WWWHR and the WTSSPS weight.
2021/2022 were rejected: 2021 lacks POSTLIFE and RELITEN entirely and switched
to web mode (a comparability break); 2022 lacks INTTECH.

**Cut design.** Extract 1 = all of 2014 + 2016 (5,405 records); Extract 2 =
all of 2016 + 2018 (5,215). Whole years, no respondent sampling: the Data
Explorer exports whole year selections, so this is the only cut design
reproducible both by script and by hand, and it keeps all three ballots
represented. Each cut has an exclusive year (2014 / 2018); the shared 2016 wave
gives a 2,867-observation overlap (53.0% / 55.0% of each cut — well above the
5% floor); distinct observations total 7,753 ≤ 10,000.

**Identification.** NORC's `id` restarts at 1 each year (verified empirically),
so the natural key is **(year, id)**, exposed as `respondent_key` = 'YYYY-NNNN'.

**Acquisition.** The Data Explorer has no API and requires an interactive
account, so the extracts were built by a committed script from NORC's official
public single-year releases — the same NORC data, with Stata tagged missing
values (.d/.i/.n) preserved verbatim. Manual Data Explorer instructions and an
equivalence check are in `docs/gss_data_explorer_instructions.md`. No record
was synthesised or altered.

**Variable mapping** (full table: `docs/variable_mapping.md`): WRKSTAT (working
status), EVWORK (ever worked ≥ 1 year — asked only of WRKSTAT 5–8; the
unemployed are routed past it), DEGREE+EDUC (education), INDUS10 (industry),
SATJOB (job satisfaction), POSTLIFE, PRAY, RELIG16, NEWS, TVHOURS, INTTECH
(technology interest — the only interest item in all three years; USETECH and
NANOTECH were considered and rejected), plus RELIG, ATTEND, RELITEN, WWWHR,
AGE, SEX, REGION, BALLOT, WTSSPS.

## 3. Data profile

Generated reproducibly (`docs/data_profile.md`,
`report/evidence/data_profile_missingness.csv`). Key facts: 10,620 raw records;
7,753 distinct observations (2014: 2,538; 2016: 2,867; 2018: 2,348); zero
in-file duplicates; zero system-missing cells. Missing tags observed: `.i`
(20,146 cells), `.d` (975), `.n` (401). Ballot structure inferred from the
data: NEWS/TVHOURS not fielded on ballot 3 in any year; WWWHR adds a non-user
filter on ballots 1–2; INTTECH rotates differently each year (2014: absent
ballot 1, partial 3; 2016/2018: absent ballot 3, partial 2). EVWORK's IAP is a
population filter (asked only of retired/school/house/other), as is SATJOB's
(retirees IAP; plus a 2016 ballot-1 variant anomaly, visible in the profile).
These distinctions — not applicable vs not asked on ballot vs not asked in year
vs don't know vs no answer — are modelled, not footnoted (§5).

## 4. Database choice and schema

**DuckDB**: dbt-supported, zero-infrastructure single file, columnar and fast
at analytical scans, supports primary keys, transactions and `EXPLAIN ANALYZE`.
Postgres (server to run) and SQLite (row store, weak analytics) were rejected
as disproportionate or underpowered. Schemas: `raw` (Python-owned),
`main_staging`, `main_intermediate`, `main_marts`, `main_metadata` (dbt-owned).

## 5. Data model and architecture

Grain everywhere: one row per respondent-year observation. Layers:

- **raw.extract_records** — files as received, one row per (extract, year, id),
  PK-enforced, values verbatim text; plus **raw.load_audit** (observability).
- **stg_gss__respondents** (view) — dedup to (year, id) with provenance flags
  `in_extract_1/2`; a singular test proves overlap rows are identical across
  extracts before they are collapsed.
- **int_gss__responses_long / _classified** (views) — variables unpivoted to
  long form and classified against three seeds generated from NORC's own value
  labels: `variable_metadata`, `response_code_metadata`,
  `variable_ballot_availability`. Every response gets exactly one
  `response_class` ∈ {valid, dont_know, no_answer, not_applicable,
  not_asked_ballot, not_asked_in_year, system_missing, …}; unknown codes fail a
  test rather than being guessed.
- **mart_respondent_survey** (table, 7,753 rows) — per variable:
  `<var>_code` (original, audit trail), `<var>_label` or `<var>_value`, and
  `<var>_response_class`; plus key, ballot, weight, provenance.

Extensibility: the variable list lives in `dbt_project.yml` vars and the
meanings in seeds — adding a GSS variable = extend the extract, append one list
entry, add seed rows. No model SQL changes. Naming conventions:
`docs/naming_conventions.md`.

## 6. Libraries and frameworks

duckdb 2.0.0, dbt-core 1.12.6 + dbt-duckdb 1.11.1, pytest 9.2.0, pyreadstat
1.3.7 (extract rebuild only); Python 3.12, stdlib elsewhere (json, csv,
argparse, logging). Considered and rejected: pandas in the pipeline (stdlib +
DuckDB suffice), Airflow/Dagster (two files, one target), Docker (a venv +
pinned requirements reproduce fully; one less moving part on Windows), dbt
packages like dbt_utils (multi-column uniqueness written as one singular test —
keeps CI offline-capable).

## 7. Analytical results and caveats

All unweighted; each query documents its denominator; full outputs in
`report/evidence/analysis_results/`.

1. **Prayer × religion raised**: among genuine answers, "once a day or more"
   is 65.2% for those raised Protestant, 57.1% raised Catholic, 36.4% raised
   with no religion (never: 10.8% / 14.1% / 37.5%). Missing states are listed
   per religion. Small denominations → tiny cells, read with caution.
2. **Life after death by year**: belief among those answering yes/no: 79.5%
   (2014) → 80.7% (2016) → 81.0% (2018). "Don't know" is ~10% every year and
   reported separately; not_asked = 0 for these waves (POSTLIFE on all
   ballots), the column exists and would populate for e.g. 2021.
3. **Industry × education** (working = WRKSTAT 1–3): construction leads for
   less-than-high-school (53) and high-school (186); hospitals for associate
   (41); elementary/secondary schools for bachelor's (109) and graduate (94).
   NAICS-granular cells are small; ranks ≥2 are near-ties in places.
4. **TV × job satisfaction** (both answered, n = 3,471): satisfaction score
   (1 best–4 worst) is 1.671 (0–1 h), 1.675 (2–3 h), 1.783 (4+ h); pct
   satisfied 86.8% / 87.2% / 82.3%. A modest association, descriptive only —
   observational data, no causal claim; exclusions quantified per reason
   (2,631 not asked TVHOURS on ballot 3; 1,581 SATJOB not applicable; …).
5. **Non-working ever worked ≥ 1 year**: of 3,034 not currently working,
   306 (unemployed) are not asked EVWORK by design; of the 2,726 who answered,
   **90.5%** (2,467) have worked a year or more.
6. **News & TV trends**: daily newspaper reading falls 24.9% → 21.1% → 20.0%
   (2014→2018) while "never" rises 28.7% → 36.5% → 43.5%; TV shifts mildly
   lighter (0–1 h/day 25.8% → 31.8%, 4+ h 30.5% → 28.6%). NEWS (frequency
   scale) and TVHOURS (hours, grouped) are reported side by side, never merged.
7. **Overlap audit**: 5,405 / 5,215 per cut, 2,867 in both, 7,753 distinct;
   overlap 53.0% / 55.0%; 10,620 raw rows → 2,867 duplicates collapsed in
   staging; mart rows = distinct keys = 7,753, proving each observation is
   counted once in every result above.

## 8. Performance and query optimisation

**Materializations**: staging/intermediate as views (cheap projections read
once per build), mart as table (read repeatedly by analyses), seeds as tables.
**Evidence** (`report/evidence/query_plans/`): the most expensive query (Q1 —
full mart scan + window aggregation) was run against the mart's view definition
vs the materialized table: median **374.7 ms → 11.5 ms (32.7×)** over 25 runs;
the before-plan shows the unpivot (19-way union), metadata hash joins and
re-pivot recomputed inside the query, the after-plan a single table scan.
**New extract**: only the new file is loaded (unchanged ones sha-skip); views
are free; the mart rebuilds in seconds. **At full GSS scale** (75,700 × ~7,000
variables ≈ 5×10⁸ long rows): the long/classified layer becomes the bottleneck
and would move from view to table or incremental-by-year; the mart would
partition by wave; ingestion would switch from executemany to DuckDB's native
JSON reader. **Deliberately not built**: incremental models, Airflow, Docker,
a metadata UI — disproportionate at 10⁴ rows (validating the optimisation at
scale = replay the same EXPLAIN ANALYZE harness against the cumulative file).

## 9. Limitations and mitigations

- NEWS/TVHOURS cover ballots 1–2 (~2/3 of each wave); INTTECH ~47–53%. The
  ballot-availability seed distinguishes these from respondent filters, and
  analyses report not-asked counts rather than hiding them. Unsolved: nothing
  recovers the missing ballot — estimates are valid for the fielded subsample.
- EVWORK excludes the unemployed by questionnaire routing; Q5 reports them in
  their own column. SATJOB's 2016 ballot-1 anomaly is profiled and documented.
- Unweighted results describe the sample, not the US population; weights are
  carried (§12-bonus) but deliberately not auto-applied.
- `.i` on a partially-fielded ballot-year cannot always be split between
  rotation and filter with certainty; the ≥99.5%-IAP inference rule is
  documented in the profile and seed generator.

## 10. Risk and complexity analysis

What breaks first as data/sources grow: (1) the Python executemany insert —
~9 s per 5k-row extract today, linear in rows; replace with DuckDB's native
`read_json` + `INSERT ... SELECT` (one order of magnitude). (2) The long-form
classified view — 147k rows now, ~5×10⁸ at full width; materialize and
partition it (fastest-growing object, ~#respondents × #variables). (3) Seed
curation — 386 code rows now, thousands at full width; generation from NORC
labels already automates it, but review becomes the bottleneck → add
drift-detection tests against new releases. Single-writer DuckDB becomes a
constraint only with concurrent writers; MotherDuck/Postgres is the escape
hatch. Quantified: today's end-to-end run is ~35 s; at 75,700 respondents the
same design projects to low minutes, dominated by ingestion.

## 11. Assumptions and deviations from design

Assumptions: overlap rows are value-identical across cuts (tested, holds);
WTSSPS is the appropriate weight in all three years (NORC back-computed it onto
pre-2021 files); the ≥99.5%-IAP ballot rule. Deviation from the design note:
one addition — the `variable_ballot_availability` seed, introduced after
profiling showed `.i` conflates rotation with filters. Everything else was
built as designed.

## 12. AI usage and human oversight

**Tools**: Claude Code (Anthropic, Claude Fable 5 model) was used throughout as
the implementation engine; no other AI tools. **What AI contributed**: the
large majority of the written artefacts — Python pipeline, dbt models/tests,
analytical SQL, scripts and documentation drafts — plus the empirical
legwork (downloading NORC files, scanning variable availability and ballot
patterns). **What is independently verified rather than taken on trust**: every
factual claim in this report traces to an executed artefact committed in the
repo — pipeline logs, pytest output (22 passed), dbt results (56 passed),
saved query CSVs and EXPLAIN ANALYZE plans; the NORC citation was taken
verbatim from the GSS terms page, and variable semantics from NORC's own value
labels, not from the model's memory. **Human in the loop**: direction of the
overall approach, review of the year/cut selection, the EVWORK/SATJOB universe
findings, the decision to source extracts from NORC's public releases with a
documented Data Explorer path, and final review of code, results and this
report before submission. **Corrected/rejected during the build**: an initial
draft NORC citation was replaced after verification against the live terms
page; an early plan to sample respondents within years was rejected as
non-reproducible in the Data Explorer.

## 13. Time spent and remaining improvements

Elapsed working time for the build was approximately **3 hours** of an
AI-assisted session (inspection → extracts → profiling → pipeline → dbt →
analyses → evidence → docs), plus human review time on top. With more time:
weighted versions of q1–q6 behind a dbt macro, a drift test comparing seeds
against a freshly downloaded NORC release, DuckDB-native JSON ingestion, a
small Evidence/Streamlit readout of the seven analyses, and Terraform for the
AWS sketch below.

---

## Appendix A (bonus): sample weights

**Choice: WTSSPS** (post-stratified weight) — it is present and positive on all
rows in all three year files (NORC recomputed it back onto pre-2021 waves when
introducing the post-stratified series), so one weight column works across the
whole mart; WTSS/WTSSALL exist only pre-2021 and would fork the logic the
moment a 2021+ wave is added. Analysts multiply counts by `sample_weight`
(e.g. `sum(sample_weight) filter (...) / sum(sample_weight)`) for
population-representative shares. Limitations: weighted estimates from our
subsample ballots (NEWS/TVHOURS) represent the fielded ballots only; no
design-effect/variance estimation is provided (would need VSTRAT/VPSU and a
survey library), so weighted results are point estimates without corrected
standard errors. Unweighted results (the default here) describe the sample and
are the honest baseline for cross-tabulations of this size.

## Appendix B (bonus): AWS production sketch

S3 (raw zone: versioned, immutable extracts; curated zone: Parquet) → ingestion
by a scheduled Lambda (file-sized loads) or ECS Fargate task running this same
Python package, writing Parquet + a Glue catalog → transformation: dbt on
Athena (or Redshift Serverless if concurrency grows) executed by ECS tasks →
orchestration: Step Functions (stage graph mirrors `pipeline.main`; EventBridge
schedule + S3 event trigger on new extracts) → IAM: task roles scoped
read-raw/write-curated per stage, no human write access to raw → observability:
CloudWatch logs + metrics, run summaries to S3, dbt artifacts published; alerts
on failed states. Cost drivers: Athena scan bytes (mitigated by Parquet +
partitioning by year), Fargate minutes, S3 storage (trivial). Scaling: GSS-full
is still small for Athena; the design's headroom is other-survey ingestion, not
volume.

## Appendix C (bonus): external data sources

Candidates: **Pew Religious Landscape Study** (religiosity depth, different
sampling), **American Time Use Survey** (actual media minutes vs self-report),
**World Values Survey** (cross-national religiosity). Ingestion: one raw schema
per source (`raw_pew.*`, …), source-specific loaders writing the same
(source, respondent_key, variable, code) long form; harmonisation happens in
intermediate models via a `source_variable_map` seed (GSS PRAY ↔ Pew prayer
frequency, with explicit category crosswalks), never by overwriting source
codes — each source keeps its own response_code_metadata rows and citation
metadata. Incompatible scales (e.g. ATUS minutes vs TVHOURS) are exposed as
separate conformed columns, with documentation, not merged. Assumptions:
annual refresh, public microdata files, <100 MB per source.
