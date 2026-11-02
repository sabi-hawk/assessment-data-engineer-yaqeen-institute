{#
    Grain: one row per (respondent_key, variable_name).

    The metadata-driven interpretation engine. Every response is classified into
    exactly one response_class so analysts can never mistake one missing state
    for another, or for a genuine answer:

      valid            genuine survey answer
      dont_know        respondent was asked, answered "don't know" (.d)
      no_answer        respondent was asked, gave no answer (.n)
      not_applicable   question's filter routed the respondent away (.i on an
                       asked ballot, e.g. EVWORK for someone currently working)
      not_asked_ballot variable not fielded on the respondent's ballot that year
                       (.i on a ballot the seed marks as not asked)
      not_asked_in_year  variable not fielded at all in that survey year
      system_missing   null in the source extract
      skipped_on_web / refused / other_missing   other GSS missing tags
      unknown_code / unknown_variable  metadata gaps - tested to be empty
#}

with responses as (

    select * from {{ ref('int_gss__responses_long') }}

),

variable_meta as (

    select * from {{ ref('variable_metadata') }}

),

code_meta as (

    select * from {{ ref('response_code_metadata') }}

),

ballot_meta as (

    select * from {{ ref('variable_ballot_availability') }}

),

classified as (

    select
        responses.respondent_key,
        responses.survey_year,
        responses.ballot,
        responses.variable_name,
        responses.raw_code,
        variable_meta.value_type,
        code_meta.label as code_label,
        case
            when variable_meta.variable_name is null
                then 'unknown_variable'
            when not list_contains(
                    string_split(variable_meta.years_available, '|'),
                    cast(responses.survey_year as varchar)
                 )
                then 'not_asked_in_year'
            when responses.raw_code is null
                then 'system_missing'
            when responses.raw_code = '.i' and not coalesce(ballot_meta.asked_on_ballot, true)
                then 'not_asked_ballot'
            when code_meta.code is not null
                then code_meta.response_class
            when variable_meta.value_type = 'numeric'
                 and try_cast(responses.raw_code as double)
                     between variable_meta.valid_min and variable_meta.valid_max
                then 'valid'
            else 'unknown_code'
        end as response_class
    from responses
    left join variable_meta
        on variable_meta.variable_name = responses.variable_name
    left join code_meta
        on code_meta.variable_name = responses.variable_name
       and code_meta.code = responses.raw_code
    left join ballot_meta
        on ballot_meta.variable_name = responses.variable_name
       and ballot_meta.year = responses.survey_year
       and ballot_meta.ballot = responses.ballot

)

select
    respondent_key,
    survey_year,
    ballot,
    variable_name,
    raw_code,
    response_class,
    case
        when response_class <> 'valid' then null
        when value_type = 'numeric' then raw_code  -- numeric answers label themselves
        else code_label
    end as response_label,
    response_class = 'valid' as is_genuine_response
from classified
