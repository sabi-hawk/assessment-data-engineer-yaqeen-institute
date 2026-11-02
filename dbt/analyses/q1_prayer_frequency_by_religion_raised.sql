-- Question 1: How is prayer frequency distributed among respondents, by the
-- religion they were raised in?
--
-- Grain of the result: one row per (religion raised in, prayer response).
-- Missing states are not discarded: non-genuine prayer responses appear as
-- their response_class in parentheses, so the distribution is auditable.
-- pct_within_religion uses genuine prayer answers of that religion as the
-- denominator and is null on missing-state rows.
-- Caveats: unweighted counts; PRAY and RELIG16 are asked on all ballots in
-- 2014-2018, so coverage is near-complete (see docs/data_profile.md).

with respondents as (

    select * from {{ ref('mart_respondent_survey') }}

),

grouped as (

    select
        coalesce(relig16_label, '(' || relig16_response_class || ')') as religion_raised_in,
        coalesce(pray_label, '(' || pray_response_class || ')') as prayer_frequency,
        min(pray_code) as prayer_code,          -- original code, for sort order and audit
        pray_response_class = 'valid' as is_genuine_answer,
        count(*) as respondents
    from respondents
    group by religion_raised_in, prayer_frequency, is_genuine_answer

)

select
    religion_raised_in,
    prayer_frequency,
    respondents,
    case
        when is_genuine_answer then round(
            100.0 * respondents
            / sum(case when is_genuine_answer then respondents end)
                over (partition by religion_raised_in),
            1
        )
    end as pct_within_religion
from grouped
order by religion_raised_in, is_genuine_answer desc, prayer_code
