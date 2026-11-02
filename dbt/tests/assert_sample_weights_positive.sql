-- WTSSPS must be a usable weight on every observation: present and > 0.
-- Must be empty.

select respondent_key, sample_weight
from {{ ref('mart_respondent_survey') }}
where sample_weight is null
   or sample_weight <= 0
