-- Question 2: What share of respondents believe in life after death, by survey
-- year? Shown alongside how many respondents were not asked.
--
-- Grain of the result: one row per survey year.
-- Denominator: pct_believe is computed over genuine answers only (yes + no).
-- "Don't know" is a substantive and common response to POSTLIFE (~10%), so it
-- is reported in its own column rather than folded into either side.
-- POSTLIFE was fielded on all ballots in 2014/2016/2018, so not_asked is 0
-- here by construction; the column exists because in other GSS years (e.g.
-- 2021) the variable is absent and the class 'not_asked_in_year'/'not_asked_
-- ballot' would be populated.

select
    survey_year,
    count(*) as respondents_total,
    count(*) filter (postlife_code = '1') as believe_yes,
    count(*) filter (postlife_code = '2') as believe_no,
    count(*) filter (postlife_response_class = 'dont_know') as dont_know,
    count(*) filter (postlife_response_class = 'no_answer') as no_answer,
    count(*) filter (
        postlife_response_class in ('not_asked_ballot', 'not_asked_in_year')
    ) as not_asked,
    count(*) filter (
        postlife_response_class in ('not_applicable', 'system_missing')
    ) as other_missing,
    round(
        100.0 * count(*) filter (postlife_code = '1')
        / nullif(count(*) filter (postlife_response_class = 'valid'), 0),
        1
    ) as pct_believe_among_answered
from {{ ref('mart_respondent_survey') }}
group by survey_year
order by survey_year
