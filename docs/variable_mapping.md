# Variable Mapping

How each business question maps to GSS variables, with coverage and
limitations. Codes, labels and universes were verified against NORC's official
single-year data releases (the source of the extracts) and the GSS codebook via
the Data Explorer; empirical universes and ballot patterns are quantified in
`docs/data_profile.md`. The machine-readable form of this mapping lives in the
dbt seeds (`variable_metadata`, `response_code_metadata`,
`variable_ballot_availability`).

All variables below are fielded in all three extract years (2014, 2016, 2018).

| # | Business question | Variable(s) | Why this variable | Universe / ballot | Missing codes seen | Limitation & mitigation |
|---|---|---|---|---|---|---|
| 1 | Working status | `WRKSTAT` | The GSS labour-force status item (8 codes: full time … other) | All respondents | `.n` (rare) | Codes 1–3 are all "employed"; analyses state which codes they treat as working |
| 2 | Ever worked ≥ 12 months | `EVWORK` ("ever work as long as one year?") | Direct operationalisation of "12 months or more" | Asked only of WRKSTAT 5–8 (retired/school/house/other). The unemployed (4) are routed past it | `.i`, `.n` | Unemployed cannot answer; Q5 reports them in a dedicated column instead of polluting the denominator |
| 3 | Education level | `DEGREE` (categorical) + `EDUC` (years) | DEGREE for grouping, EDUC for numeric analysis | All respondents | `.d`, `.n` | None material |
| 4 | Industry | `INDUS10` | The industry coding available in all three years (NAICS 2007 per NORC label) | Working or ever worked | `.i`, `.n` | ~270 granular codes → small cells; Q3 ranks rather than enumerates |
| 5 | Job satisfaction | `SATJOB` | The core work-satisfaction item (1 very satisfied … 4 very dissatisfied) | Currently working or keeping house with work history; retirees are IAP; extra IAP on 2016 ballot 1 (module variant fielded there) | `.i`, `.d`, `.n` | Universe quirks are quantified in the profile; Q4 reports every exclusion reason with counts |
| 6 | Belief in life after death | `POSTLIFE` | The canonical item | All respondents, all ballots in 2014–2018 | `.d` (~10%!), `.n` | "Don't know" is substantive and frequent → kept as its own category, never folded into yes/no |
| 7 | Prayer frequency | `PRAY` | The canonical item (6 frequencies) | All respondents | `.d`, `.n` | None material |
| 8 | Religion raised in | `RELIG16` | "In what religion were you raised?" | All respondents | `.d`, `.n` | Small denominations have tiny cells; Q1 keeps them but percentages carry small-n caveats |
| 9 | Newspaper frequency | `NEWS` | The canonical item (5 frequencies) | **Ballots 1–2 only** (ballot 3 not fielded, all years) | `.i`, `.n` | ~1/3 of each wave not asked; same design each wave so trends are internally comparable; classified `not_asked_ballot` |
| 10 | TV viewing | `TVHOURS` (hours/day) | The canonical TV item in these years | **Ballots 1–2 only** | `.i`, `.d`, `.n` | Hours/day is not a frequency scale like NEWS → reported side by side, never merged (Q6) |
| 11 | Interest in technology | `INTTECH` ("interest in new technologies", science module) | The only technology-interest item fielded in all three years | Science-module subsample; rotation differs per year (2014: not ballot 1; 2016/2018: not ballot 3; partial on one other ballot) | `.i`, `.d`, `.n` | Smallest coverage of all items (~47–53% asked); the ballot seed separates rotation from filters |
| — | Religious preference | `RELIG` | Required scope | All respondents | `.d`, `.n` | |
| — | Service attendance | `ATTEND` | Required scope | All respondents | `.d` | |
| — | Strength of affiliation | `RELITEN` | Required scope | Respondents with a religion | `.i`, `.d`, `.n` | |
| — | Weekly web hours | `WWWHR` | Required scope | Internet users on ballots 1–2 | `.i`, `.d`, `.n` | IAP mixes ballot rotation (ballot 3) and the non-user filter; the ballot seed separates them |
| — | Demographics | `AGE`, `SEX`, `REGION`, `EDUC` | Required scope | All respondents | `.n` | AGE top-coded at 89 |
| — | Survey design | `YEAR`, `ID`, `BALLOT` | Identity and rotation | — | — | `ID` unique only within `YEAR` |
| — | Weight | `WTSSPS` | Post-stratification weight present in all three year files (NORC back-computed); successor of WTSS/WTSSALL | All respondents, always positive | — | See report §Weights for usage guidance |

## Notes on "interest in technology"

The GSS has no variable literally named "interested in technology" asked every
year. Candidates considered: `INTTECH` (science module: interest in "new
technologies" — chosen, fielded 2014/2016/2018), `USETECH` (share of work time
using technology — measures use, not interest; absent 2016), `NANOTECH`
(nanotech-specific, 2010 only). `INTTECH` is the only direct interest measure
covering all three years.

## Missing-code inventory (observed in the extracts)

`.i` inapplicable (20,146 cells), `.d` don't know (975), `.n` no answer (401);
no `.s`/`.r`/`.u`/`.x`/`.y`/`.z` occur in 2014–2018 in-person data, but the
pipeline recognises and classifies them if a future extract carries them.
