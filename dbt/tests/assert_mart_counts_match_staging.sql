-- The mart must carry exactly one row per staged observation: the pivot may
-- neither drop respondents nor fan them out. Must be empty.

with counts as (

    select
        (select count(*) from {{ ref('stg_gss__respondents') }}) as staging_rows,
        (select count(*) from {{ ref('mart_respondent_survey') }}) as mart_rows,
        (select count(distinct respondent_key) from {{ ref('mart_respondent_survey') }}) as mart_keys

)

select *
from counts
where staging_rows <> mart_rows
   or mart_rows <> mart_keys
