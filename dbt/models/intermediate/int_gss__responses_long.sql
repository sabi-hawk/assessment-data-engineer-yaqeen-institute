{#
    Grain: one row per (respondent_key, variable_name).

    Unpivots the modelled survey variables to long form so response codes can
    be interpreted by joining the metadata seeds once, instead of duplicating
    decode logic per column. The variable list lives in dbt_project.yml vars;
    adding a GSS variable means appending it there plus seed rows - no SQL edits.
#}

{% set gss_variables = var('gss_categorical_variables') + var('gss_numeric_variables') %}

{% for variable in gss_variables %}
select
    respondent_key,
    survey_year,
    ballot,
    '{{ variable }}' as variable_name,
    {{ variable }}_code as raw_code
from {{ ref('stg_gss__respondents') }}
{% if not loop.last %}union all{% endif %}
{% endfor %}
