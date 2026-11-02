-- Question 5: Among respondents who are not currently working, what share have
-- ever worked for 12 months or more?
--
-- Grain of the result: one summary row.
-- Variable: EVWORK ("Did you ever work for as long as one year?") - the GSS's
-- operationalisation of "12 months or more".
-- Universe (verified empirically, see docs/data_profile.md): the GSS asks
-- EVWORK only of respondents who are retired, in school, keeping house or
-- "other" (WRKSTAT 5-8). The unemployed (WRKSTAT 4) are NOT asked - their
-- work history is established through the job questions instead - so they are
-- "not currently working" but ineligible for EVWORK. They are reported in
-- their own column, not silently mixed into the denominator.
-- pct_ever_worked uses genuine yes/no answers as the denominator.
-- Caveat: unweighted; "not working" excludes WRKSTAT 3 (has a job, temporarily
-- absent), who are employed.

with not_working as (

    select *
    from {{ ref('mart_respondent_survey') }}
    where wrkstat_response_class = 'valid'
      and wrkstat_code in ('4', '5', '6', '7', '8')

)

select
    count(*) as not_working_total,
    count(*) filter (wrkstat_code = '4') as unemployed_not_asked_evwork,
    count(*) filter (evwork_response_class = 'valid') as answered_evwork,
    count(*) filter (evwork_code = '1') as ever_worked_year_or_more,
    count(*) filter (evwork_code = '2') as never_worked_year_or_more,
    count(*) filter (evwork_response_class = 'dont_know') as dont_know,
    count(*) filter (evwork_response_class = 'no_answer') as no_answer,
    count(*) filter (
        evwork_response_class not in ('valid', 'dont_know', 'no_answer')
        and wrkstat_code <> '4'
    ) as other_missing,
    round(
        100.0 * count(*) filter (evwork_code = '1')
        / nullif(count(*) filter (evwork_response_class = 'valid'), 0),
        1
    ) as pct_ever_worked_among_answered
from not_working
