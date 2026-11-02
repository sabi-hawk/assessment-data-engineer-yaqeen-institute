# Naming Conventions

Applied across the whole repository; reviewers and new analysts should be able
to predict a name before looking it up.

## Schemas (DuckDB)

| schema | owner | contents |
|---|---|---|
| `raw` | Python pipeline | data as received (`extract_records`, `load_audit`) |
| `main_staging` | dbt | staging views |
| `main_intermediate` | dbt | intermediate views |
| `main_marts` | dbt | analyst-facing tables |
| `main_metadata` | dbt | seeds |

(dbt's default schema suffixing is kept: custom schema `staging` renders as
`main_staging`, etc. — predictable and standard for dbt-duckdb.)

## dbt models

- `stg_<source>__<entity>` — staging, one per source entity: `stg_gss__respondents`.
- `int_<source>__<description>` — intermediate: `int_gss__responses_long`,
  `int_gss__responses_classified`.
- `mart_<entity>` — analyst-facing: `mart_respondent_survey`.
- Model docs live in `_<prefix>__models.yml` next to the models.

## Columns

- snake_case everywhere; GSS mnemonics kept lower-case (`pray`, `relig16`).
- `<var>_code` — original GSS code, verbatim text (audit trail).
- `<var>_label` — human-readable answer (categorical variables).
- `<var>_value` — typed numeric answer (numeric variables).
- `<var>_response_class` — missing-value semantics (valid / dont_know / ...).
- Keys end in `_key` (`respondent_key`); booleans read as predicates
  (`in_extract_1`, `is_genuine_response`, `asked_on_ballot`).
- `survey_year`, `respondent_id`, `sample_weight` name the typed identity and
  weight columns.

## Seeds

Plain nouns describing content: `variable_metadata`, `response_code_metadata`,
`variable_ballot_availability`. Documented in `seeds/_seeds.yml`.

## Tests

- Generic tests are declared in the YAML next to the model.
- Singular tests are `assert_<expectation>.sql` and return offending rows:
  `assert_raw_overlap_consistent`, `assert_no_unknown_response_codes`,
  `assert_extract_constraints`, `assert_mart_counts_match_staging`,
  `assert_sample_weights_positive`, `assert_seed_response_codes_unique`.

## Analyses

`q<N>_<question_in_snake_case>.sql` (q1–q7), each headed by a comment stating
the question, result grain, denominator and caveats. Results are saved as
`report/evidence/analysis_results/<same name>.csv`.

## Python

- Package `pipeline`, one module per responsibility: `config`, `logging_config`,
  `extract_loader`, `validation`, `database`, `profiling`, `main`.
- Tests `test_<module_or_property>.py`; test names state the expectation
  (`test_load_order_does_not_change_final_dataset`).

## Files and scripts

- Extracts: `gss_extract_<n>_<years>.json` under `/source/data/raw/`.
- Scripts: verb-first (`build_extracts.py`, `generate_seed_metadata.py`,
  `capture_query_plans.py`).
- Logs: `run_<timestamp>_<run_id>.log`, `summary_<run_id>.json`.
