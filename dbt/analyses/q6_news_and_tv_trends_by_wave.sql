-- Question 6: How have newspaper reading and TV viewing changed from one survey
-- wave to the next?
--
-- Grain of the result: one row per (metric, survey year, category), with the
-- share of genuine answers in that year and its change versus the previous wave.
-- Comparability: NEWS (ordinal frequency categories) and TVHOURS (hours/day,
-- grouped here) are different kinds of measures - they are reported side by
-- side as distributions, never compared against each other directly. Both are
-- fielded on ballots 1-2 only in 2014-2018, and the ballot design is the same
-- in each wave, so year-over-year comparisons within each metric are fair.
-- Caveats: unweighted; answered_in_year is the per-year denominator of genuine
-- answers; pct_point_change is in percentage points vs the previous wave.

with respondents as (

    select * from {{ ref('mart_respondent_survey') }}

),

distributions as (

    select
        'newspaper reading (NEWS)' as metric,
        survey_year,
        news_label as category,
        min(news_code) as category_order,
        count(*) as respondents
    from respondents
    where news_response_class = 'valid'
    group by survey_year, news_label

    union all

    select
        'tv viewing (TVHOURS, grouped)' as metric,
        survey_year,
        case
            when tvhours_value <= 1 then '0-1 hours/day'
            when tvhours_value <= 3 then '2-3 hours/day'
            else '4+ hours/day'
        end as category,
        min(case
            when tvhours_value <= 1 then '1'
            when tvhours_value <= 3 then '2'
            else '3'
        end) as category_order,
        count(*) as respondents
    from respondents
    where tvhours_response_class = 'valid'
    group by survey_year, category

),

with_shares as (

    select
        metric,
        survey_year,
        category,
        category_order,
        respondents,
        sum(respondents) over (partition by metric, survey_year) as answered_in_year,
        round(
            100.0 * respondents
            / sum(respondents) over (partition by metric, survey_year),
            1
        ) as pct_of_answered
    from distributions

)

select
    metric,
    survey_year,
    category,
    respondents,
    answered_in_year,
    pct_of_answered,
    round(
        pct_of_answered - lag(pct_of_answered) over (
            partition by metric, category order by survey_year
        ),
        1
    ) as pct_point_change_vs_previous_wave
from with_shares
order by metric, category_order, survey_year
