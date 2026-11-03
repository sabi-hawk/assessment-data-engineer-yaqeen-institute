# GSS Respondent Pipeline — Yaqeen Institute Data Engineering Assignment

A small, production-minded pipeline over General Social Survey (GSS) data:
two committed JSON extracts → Python validation and idempotent ingestion into
DuckDB → dbt transformation layers with metadata-driven missing-value semantics
→ analytical SQL → documentation, all orchestrated by one CLI and verifiable by
tests at every layer.

## Business objective

Model respondent-level GSS data on religiosity and media consumption so that an
analyst can answer questions such as prayer frequency by religion raised,
belief in life after death by year, or industry by education — without opening
the codebook, without double-counting the overlap between extracts, and without
ever mistaking "don't know", "no answer", "not applicable" or "not asked that
year" for a genuine answer or for each other.

## Architecture

```
NORC GSS (official single-year releases)
   │  scripts/build_extracts.py (reproducible; see docs/gss_data_explorer_instructions.md)
   ▼
/source/data/raw/*.json      two committed cuts: 2014+2016 and 2016+2018 (overlap = 2016)
   │  python -m pipeline.main   validate → profile → init-db → ingest   (quarantine, audit, logs)
   ▼
DuckDB  raw.extract_records  one row per (extract, year, id), values verbatim
   │  dbt seed + run + test
   ▼
staging   stg_gss__respondents          dedup to (year, id), provenance flags
intermediate  int_gss__responses_long / _classified   metadata-driven decoding
marts     mart_respondent_survey        code + label/value + response_class per variable
   │  dbt analyses (q1–q7) → report/evidence/analysis_results/*.csv
   ▼
dbt docs, query plans, final report
```

## Technology stack

| concern | choice | why |
|---|---|---|
| language | Python 3.11+ (3.12 verified) | stdlib-centred pipeline; one dep for DB |
| database | DuckDB 2.0 | dbt-supported, zero-infra local file, columnar, `EXPLAIN ANALYZE` |
| transformation | dbt-core 1.12 + dbt-duckdb 1.11 | layered models, tests, docs, seeds |
| testing | pytest 9 | unit + integration (idempotency proofs on real data) |
| orchestration | Python CLI (`pipeline.main`) | proportionate to 2 files / 1 target; fail-fast stages |
| CI | GitHub Actions | full pipeline + tests on every push |

## Repository structure

```
README.md                  this file
.env.example               optional configuration (no secrets anywhere)
source/
  data/raw/                the two committed GSS JSON extracts
  data/processed/          DuckDB file, quarantine output (git-ignored)
  data/external/           cached NORC downloads (git-ignored)
  pipeline/                config, loader, validation, database, profiling, CLI
  tests/                   pytest suite (22 tests)
  requirements.txt         pinned dependencies
dbt/
  dbt_project.yml          layers, materializations, variable lists
  profiles.yml.example     DuckDB profile (auto-copied to profiles.yml)
  models/ sources|staging|intermediate|marts
  seeds/                   variable_metadata, response_code_metadata, variable_ballot_availability
  analyses/                q1–q7 analytical SQL
  tests/                   singular data-expectation tests
docs/                      design_note, naming_conventions, variable_mapping,
                           data_profile (generated), gss_data_explorer_instructions
report/                    final_report.md + evidence/ (results, plans, profile CSV)
scripts/                   build_extracts, generate_seed_metadata, capture_query_plans
logs/                      run logs + JSON run summaries (git-ignored)
```

## Prerequisites

- Python 3.11+ with pip
- Git
- ~500 MB disk, no cloud resources, no credentials of any kind

## Installation

```bash
git clone <this-repository>
cd data-engineer-yaqeen-institute
python -m venv .venv
.venv\Scripts\Activate.ps1      # Windows PowerShell (cmd.exe: .venv\Scripts\activate.bat)
python -m pip install -r source/requirements.txt
```

`source/requirements.txt` pins the direct dependencies;
`source/requirements.lock.txt` is a full transitive freeze captured from a
clean-environment verification run — install from it instead
(`python -m pip install -r source/requirements.lock.txt`) for bit-for-bit
reproducibility months from now.

## Configuration

Everything works with defaults. To override, copy `.env.example` to `.env`
(e.g. `GSS_DB_PATH` for the database location). No secrets are used or
committed; `dbt/profiles.yml` is generated from the committed example and
git-ignored.

## Obtaining / reproducing the GSS extracts

The two extracts are **committed** under `/source/data/raw/`, so nothing needs
downloading to run the pipeline. To rebuild them from NORC sources, or to build
them manually in the GSS Data Explorer, follow
[docs/gss_data_explorer_instructions.md](docs/gss_data_explorer_instructions.md):

```bash
python scripts/build_extracts.py
python scripts/generate_seed_metadata.py
```

## Running the pipeline

```bash
cd source
python -m pipeline.main all        # full workflow, fail-fast
```

Individual stages (same order the orchestrator enforces):

```bash
python -m pipeline.main validate          # raw extract validation (+ quarantine)
python -m pipeline.main profile           # regenerates docs/data_profile.md
python -m pipeline.main init-db ingest    # idempotent load (--force to reload unchanged files)
python -m pipeline.main dbt-run dbt-test  # models + tests
python -m pipeline.main analyses          # executes q1–q7, saves CSVs
```

Re-running `all` is safe: unchanged extracts are skipped via sha256, loads are
transactional delete-and-insert per extract, and load order does not affect the
final dataset (proven by tests).

## Running dbt directly

Requires the venv activated, so that `dbt` is on PATH.

```bash
# from the repository root (the profile's default DB path is root-relative)
dbt build --project-dir dbt --profiles-dir dbt     # seeds + models + tests
dbt test  --project-dir dbt --profiles-dir dbt
```

## Running the tests

```bash
cd source && python -m pytest tests -q        # 22 tests: validation, loader, idempotency
```

dbt data tests (56) run via `python -m pipeline.main dbt-test` or `dbt test` as
above.

## Running the analytical SQL

The seven queries live in `dbt/analyses/` (q1–q7, incl. the mandatory overlap
audit). `python -m pipeline.main analyses` compiles and executes them against
DuckDB and saves results to `report/evidence/analysis_results/*.csv`.

## Generating documentation

```bash
cd source && python -m pipeline.main dbt-docs
dbt docs serve --project-dir ../dbt --profiles-dir ../dbt   # browse at localhost:8080
```

## Query-plan evidence

```bash
python scripts/capture_query_plans.py   # writes report/evidence/query_plans/
```

## Troubleshooting

| symptom | cause / fix |
|---|---|
| `dbt executable not found on PATH` | activate the venv first — the orchestrator resolves `dbt` via `shutil.which`, so invoking the interpreter by full path (e.g. `.venv\Scripts\python.exe -m pipeline.main`) leaves `.venv\Scripts` off PATH and this stage fails |
| `python -m pip install` fails with `No such file or directory: ...numpy\f2py\...` (Windows) | path too long for the venv location — enable Windows long-path support or create the venv at a shorter path (e.g. `C:\venvs\gss`) |
| `pip.exe`/`pytest.exe` fail with *"An Application Control policy has blocked this file"* (Windows) | Smart App Control / WDAC rejects the unsigned console-script stubs that pip generates in the venv's `Scripts` directory. `python.exe` itself is signed, so call the module instead: `python -m pip`, `python -m pytest`. Do not disable Smart App Control to work around this — it cannot be re-enabled without a Windows reset |
| `database ... is locked` | close other DuckDB connections (e.g. an open `dbt docs serve` or IDE session) |
| `Catalog Error: Table ... does not exist` in dbt | run ingestion first: `python -m pipeline.main init-db ingest` |
| records quarantined on validate | inspect `source/data/processed/quarantine_*.json`; the pipeline refuses to load malformed extracts by design |
| relative-path errors running dbt manually | run dbt from the repository root, or set `GSS_DB_PATH` to an absolute path |

## Known limitations

- NEWS/TVHOURS are fielded on ballots 1–2 only, INTTECH on a science-module
  subsample; EVWORK is not asked of the unemployed. Analyses state their
  denominators and report the not-asked counts (see report §Results).
- Results are unweighted by default; `sample_weight` (WTSSPS) is carried on
  every row for weighted analysis.
- The extracts were built from NORC's official public year files rather than
  interactively in the Data Explorer (which has no API); both paths and the
  verification procedure are documented.

## Data citation

Data are from the General Social Survey, NORC at the University of Chicago,
obtained via https://gss.norc.org / the GSS Data Explorer
(https://gssdataexplorer.norc.org). Citation as required by the GSS terms and
conditions:

> Davern, Michael; Bautista, Rene; Freese, Jeremy; Herd, Pamela; and Morgan,
> Stephen L. General Social Survey 1972-2024. [Machine-readable data file].
> Principal Investigator, Michael Davern; Co-Principal Investigators, Rene
> Bautista, Jeremy Freese, Pamela Herd, and Stephen L. Morgan. NORC ed.
> Chicago, 2026. 1 datafile and 1 codebook (2024 Release 3a).
