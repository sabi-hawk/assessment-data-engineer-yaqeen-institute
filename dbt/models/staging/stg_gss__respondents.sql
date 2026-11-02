{#
    Grain: one row per respondent-year observation (survey_year, respondent_id).

    Deduplicates the overlap between the two extracts: a respondent observed in
    both cuts has one row here, with provenance flags saying where it came from.
    Overlap rows are byte-identical across extracts (enforced by the singular
    test assert_raw_overlap_consistent), so max() simply collapses duplicates.
    Original response codes are preserved as *_code text columns.
#}

{% set gss_variables = var('gss_categorical_variables') + var('gss_numeric_variables') %}

with source_records as (

    select * from {{ source('gss_raw', 'extract_records') }}

),

deduplicated as (

    select
        year,
        id,
        {% for extract_name in var('extract_names') %}
        bool_or(extract_name = '{{ extract_name }}') as in_extract_{{ loop.index }},
        {% endfor %}
        count(*) as source_extract_count,
        max(ballot) as ballot,
        max(wtssps) as wtssps,
        {% for variable in gss_variables %}
        max({{ variable }}) as {{ variable }}{{ "," if not loop.last }}
        {% endfor %}
    from source_records
    group by year, id

)

select
    printf('%d-%04d', year, id) as respondent_key,
    year as survey_year,
    id as respondent_id,
    cast(ballot as integer) as ballot,
    cast(wtssps as double) as sample_weight,
    source_extract_count,
    {% for extract_name in var('extract_names') %}
    in_extract_{{ loop.index }},
    {% endfor %}
    {% for variable in gss_variables %}
    {{ variable }} as {{ variable }}_code{{ "," if not loop.last }}
    {% endfor %}
from deduplicated
