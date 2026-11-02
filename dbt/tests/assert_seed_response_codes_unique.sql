-- Referential soundness of the decode metadata: one meaning per
-- (variable, code). A duplicate would silently fan out every decode join.
-- Must be empty.

select
    variable_name,
    code,
    count(*) as duplicate_rows
from {{ ref('response_code_metadata') }}
group by variable_name, code
having count(*) > 1
