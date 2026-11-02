# Query plan evidence - Q1 (prayer frequency by religion raised)

DuckDB 2.0.0; 25 repeated executions each; times in ms.

| variant | median | mean | min | max |
|---|---|---|---|---|
| before_view | 374.7 | 397.4 | 192.6 | 758.0 |
| after_table | 11.5 | 12.2 | 10.2 | 22.9 |

Median speedup from materializing the mart as a table: **32.7x**.

Full EXPLAIN ANALYZE output: q1_plan_before_view.txt / q1_plan_after_table.txt.