-- Question 3: For each education level, which industry is most common among
-- working respondents?
--
-- Grain of the result: top 3 industries per education level (rank 1 flagged
-- as is_most_common).
-- "Working" = currently employed: WRKSTAT codes 1 (full time), 2 (part time)
-- or 3 (with a job but temporarily not at work). Respondents not working are
-- excluded from the ranking, as required.
-- Caveats: INDUS10 uses granular NAICS 2007 codes, so counts per industry are
-- small; ranks below 1 can be near-ties. Unweighted counts. Working
-- respondents whose industry is missing are excluded from the ranking but
-- countable via industry_missing_for_education.

with working_respondents as (

    select *
    from {{ ref('mart_respondent_survey') }}
    where wrkstat_response_class = 'valid'
      and wrkstat_code in ('1', '2', '3')

),

industry_counts as (

    select
        degree_label as education_level,
        min(degree_code) as degree_code,
        indus10_label as industry,
        count(*) as working_respondents
    from working_respondents
    where indus10_response_class = 'valid'
      and degree_response_class = 'valid'
    group by education_level, industry

),

ranked as (

    select
        *,
        row_number() over (
            partition by education_level
            order by working_respondents desc, industry
        ) as industry_rank
    from industry_counts

),

missing_industry as (

    select
        degree_label as education_level,
        count(*) as industry_missing_for_education
    from working_respondents
    where indus10_response_class <> 'valid'
      and degree_response_class = 'valid'
    group by education_level

)

select
    ranked.education_level,
    ranked.industry,
    ranked.working_respondents,
    ranked.industry_rank,
    ranked.industry_rank = 1 as is_most_common,
    coalesce(missing_industry.industry_missing_for_education, 0)
        as industry_missing_for_education
from ranked
left join missing_industry
    on missing_industry.education_level = ranked.education_level
where ranked.industry_rank <= 3
order by ranked.degree_code, ranked.industry_rank
