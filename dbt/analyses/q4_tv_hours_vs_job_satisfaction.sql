-- Question 4: Is time spent watching TV related to job satisfaction?
--
-- Grain of the result: one row per TV-viewing group, with the job-satisfaction
-- distribution, group sizes and an average score, plus accounting rows for
-- respondents excluded for each missing-data reason.
-- Universe: respondents with BOTH a genuine TVHOURS and a genuine SATJOB
-- answer. TVHOURS is fielded on ballots 1-2 only, and SATJOB only applies to
-- respondents who work or have worked, so this cross-section is a minority of
-- the sample - the exclusion rows quantify exactly who is left out.
-- satisfaction_score averages SATJOB codes (1 = very satisfied ... 4 = very
-- dissatisfied), so LOWER is MORE satisfied.
-- Caveat: this is a descriptive cross-tabulation of observational survey data;
-- any association between TV time and satisfaction is NOT evidence of
-- causation (confounders like employment type, age and health are untouched).

with respondents as (

    select * from {{ ref('mart_respondent_survey') }}

),

answered_both as (

    select
        case
            when tvhours_value <= 1 then '0-1 hours'
            when tvhours_value <= 3 then '2-3 hours'
            else '4+ hours'
        end as tv_hours_per_day,
        satjob_code,
        satjob_label
    from respondents
    where tvhours_response_class = 'valid'
      and satjob_response_class = 'valid'

),

by_group as (

    select
        tv_hours_per_day,
        count(*) as respondents,
        count(*) filter (satjob_code = '1') as very_satisfied,
        count(*) filter (satjob_code = '2') as moderately_satisfied,
        count(*) filter (satjob_code = '3') as a_little_dissatisfied,
        count(*) filter (satjob_code = '4') as very_dissatisfied,
        round(avg(cast(satjob_code as integer)), 3) as satisfaction_score_1_best_4_worst,
        round(
            100.0 * count(*) filter (satjob_code in ('1', '2')) / count(*),
            1
        ) as pct_satisfied
    from answered_both
    group by tv_hours_per_day

)

select * from by_group

union all

-- accounting: who is excluded from the cross-tabulation, and why
select
    '(excluded: ' || reason || ')' as tv_hours_per_day,
    count(*) as respondents,
    null, null, null, null, null, null
from (
    select
        case
            when tvhours_response_class in ('not_asked_ballot', 'not_asked_in_year')
                then 'TVHOURS not asked on ballot'
            when tvhours_response_class <> 'valid'
                then 'TVHOURS missing (' || tvhours_response_class || ')'
            when satjob_response_class = 'not_applicable'
                then 'SATJOB not applicable (no work history in scope)'
            else 'SATJOB missing (' || satjob_response_class || ')'
        end as reason
    from respondents
    where tvhours_response_class <> 'valid'
       or satjob_response_class <> 'valid'
)
group by reason
order by tv_hours_per_day
