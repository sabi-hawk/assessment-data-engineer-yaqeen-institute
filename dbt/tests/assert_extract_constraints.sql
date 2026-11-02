-- Encodes the assignment's data-shape guarantees as a test:
--   1. no more than 10,000 distinct respondent-year observations overall
--   2. the overlap is at least 5% of each cut
--   3. each cut contains at least one survey year the other does not
-- Returns one row per violated constraint; must be empty.

with observations as (

    select * from {{ ref('stg_gss__respondents') }}

),

stats as (

    select
        count(*) as distinct_total,
        count(*) filter (in_extract_1) as in_cut_1,
        count(*) filter (in_extract_2) as in_cut_2,
        count(*) filter (in_extract_1 and in_extract_2) as overlap,
        count(distinct survey_year) filter (in_extract_1 and not in_extract_2)
            as years_exclusive_to_cut_1,
        count(distinct survey_year) filter (in_extract_2 and not in_extract_1)
            as years_exclusive_to_cut_2
    from observations

)

select 'distinct respondents exceed 10,000' as violated_constraint, distinct_total as value
from stats where distinct_total > 10000

union all

select 'overlap below 5% of cut 1', overlap
from stats where overlap < 0.05 * in_cut_1

union all

select 'overlap below 5% of cut 2', overlap
from stats where overlap < 0.05 * in_cut_2

union all

select 'cut 1 has no exclusive survey year', years_exclusive_to_cut_1
from stats where years_exclusive_to_cut_1 = 0

union all

select 'cut 2 has no exclusive survey year', years_exclusive_to_cut_2
from stats where years_exclusive_to_cut_2 = 0
