-- Every response must resolve against the metadata seeds. A row here means a
-- code appeared in the data that the metadata does not describe (or a variable
-- was modelled without metadata) - the pipeline must not guess what it means.
-- Must be empty.

select
    variable_name,
    raw_code,
    response_class,
    count(*) as occurrences
from {{ ref('int_gss__responses_classified') }}
where response_class in ('unknown_code', 'unknown_variable')
group by variable_name, raw_code, response_class
