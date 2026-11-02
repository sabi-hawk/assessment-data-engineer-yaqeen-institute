{#
    Grain: one row per respondent-year observation (respondent_key), i.e. the
    deduplicated union of both extracts. 7,753 rows for the committed cuts.

    The analyst-facing model. For every survey variable it carries:
      <var>_code            original GSS code, verbatim (audit trail)
      <var>_label           readable answer (categorical variables)
      <var>_value           typed numeric answer (numeric variables)
      <var>_response_class  valid / dont_know / no_answer / not_applicable /
                            not_asked_ballot / not_asked_in_year / ...

    Materialized as a table: it is read repeatedly by the analyses while its
    inputs (view-layer unpivot + metadata joins) are only computed once here.
#}

{% set categorical_variables = var('gss_categorical_variables') %}
{% set numeric_variables = var('gss_numeric_variables') %}

with respondents as (

    select * from {{ ref('stg_gss__respondents') }}

),

classified as (

    select * from {{ ref('int_gss__responses_classified') }}

),

pivoted as (

    select
        respondent_key,
        {% for variable in categorical_variables %}
        max(case when variable_name = '{{ variable }}' then raw_code end)
            as {{ variable }}_code,
        max(case when variable_name = '{{ variable }}' then response_label end)
            as {{ variable }}_label,
        max(case when variable_name = '{{ variable }}' then response_class end)
            as {{ variable }}_response_class,
        {% endfor %}
        {% for variable in numeric_variables %}
        max(case when variable_name = '{{ variable }}' then raw_code end)
            as {{ variable }}_code,
        max(case when variable_name = '{{ variable }}' and response_class = 'valid'
                 then try_cast(raw_code as double) end)
            as {{ variable }}_value,
        max(case when variable_name = '{{ variable }}' then response_class end)
            as {{ variable }}_response_class{{ "," if not loop.last }}
        {% endfor %}
    from classified
    group by respondent_key

)

select
    respondents.respondent_key,
    respondents.survey_year,
    respondents.respondent_id,
    respondents.ballot,
    respondents.sample_weight,
    respondents.source_extract_count,
    respondents.in_extract_1,
    respondents.in_extract_2,
    pivoted.* exclude (respondent_key)
from respondents
inner join pivoted
    on pivoted.respondent_key = respondents.respondent_key
