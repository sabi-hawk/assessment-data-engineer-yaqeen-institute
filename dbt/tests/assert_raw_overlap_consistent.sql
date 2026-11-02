-- A respondent-year observation delivered by both extracts must be identical
-- in both (same codes, same ballot, same weight). If NORC revised a value
-- between cuts this surfaces it instead of silently picking one.
-- Returns the offending (year, id) pairs; must be empty.

{% set payload_columns =
    ['ballot', 'wtssps']
    + var('gss_categorical_variables')
    + var('gss_numeric_variables') %}

select
    year,
    id,
    count(distinct
        {% for column in payload_columns %}
        coalesce({{ column }}, '<null>') {{ "||'|'||" if not loop.last }}
        {% endfor %}
    ) as distinct_payloads
from {{ source('gss_raw', 'extract_records') }}
group by year, id
having distinct_payloads > 1
