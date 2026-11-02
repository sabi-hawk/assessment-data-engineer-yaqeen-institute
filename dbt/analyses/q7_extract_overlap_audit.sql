-- Question 7 (mandatory audit): the overlap between the two cuts, and proof
-- that every other result counts each respondent-survey observation once.
--
-- Grain of the result: one audit row.
-- raw_rows_loaded counts physical rows in the raw layer (overlap rows appear
-- once per extract there by design - raw preserves the files as received).
-- duplicate_rows_collapsed_downstream = raw rows - distinct observations: the
-- duplicates the staging layer removes before any analysis runs.
-- mart_rows = mart_distinct_keys = distinct observations proves the mart (the
-- basis of queries 1-6) carries each observation exactly once.

with observations as (

    select * from {{ ref('stg_gss__respondents') }}

),

mart as (

    select * from {{ ref('mart_respondent_survey') }}

),

raw_rows as (

    select count(*) as raw_rows_loaded
    from {{ source('gss_raw', 'extract_records') }}

)

select
    count(*) filter (in_extract_1) as respondents_in_extract_1,
    count(*) filter (in_extract_2) as respondents_in_extract_2,
    count(*) filter (in_extract_1 and in_extract_2) as respondents_in_both,
    count(*) as distinct_respondents_overall,
    round(
        100.0 * count(*) filter (in_extract_1 and in_extract_2)
        / count(*) filter (in_extract_1), 1
    ) as overlap_pct_of_extract_1,
    round(
        100.0 * count(*) filter (in_extract_1 and in_extract_2)
        / count(*) filter (in_extract_2), 1
    ) as overlap_pct_of_extract_2,
    (select raw_rows_loaded from raw_rows) as raw_rows_loaded,
    (select raw_rows_loaded from raw_rows) - count(*) as duplicate_rows_collapsed_downstream,
    (select count(*) from mart) as mart_rows,
    (select count(distinct respondent_key) from mart) as mart_distinct_keys
from observations
