# Reproducing the Extracts

## A. Scripted path (how the committed extracts were actually built)

The GSS Data Explorer requires an interactive, authenticated session (free
account, email verification) and offers no export API, so the committed
extracts were built from **NORC's official, publicly hosted single-year data
releases** — the same NORC data, downloaded over HTTPS from gss.norc.org — by a
committed, deterministic script:

```bash
pip install -r source/requirements.txt
python scripts/build_extracts.py          # downloads 2014/2016/2018, writes both JSONs
python scripts/generate_seed_metadata.py  # regenerates the dbt metadata seeds
```

What the script does (no sampling, no synthesis — fully reproducible):

1. Downloads `https://gss.norc.org/content/dam/gss/get-the-data/documents/stata/{year}_stata.zip`
   for 2014, 2016, 2018 into `/source/data/external/` (git-ignored cache).
2. Reads the 23 selected variables with Stata tagged missing values preserved
   (`.d`/`.i`/`.n`), never collapsing them into nulls.
3. Writes `gss_extract_1_2014_2016.json` (all of 2014 + all of 2016) and
   `gss_extract_2_2016_2018.json` (all of 2016 + all of 2018), sorted by
   (year, id), original codes verbatim.

Cut design: whole survey years, no respondent sampling. This is deliberate —
the Data Explorer also exports whole year selections, so a year-level cut is
the only design reproducible on both paths; it also keeps every ballot
represented. The shared 2016 wave provides the required ≥5% overlap (53%/55%),
each cut has an exclusive year (2014 / 2018), and distinct observations total
7,753 ≤ 10,000.

## B. Manual Data Explorer path (the brief's stated mechanism)

To produce equivalent extracts via https://gssdataexplorer.norc.org/:

1. Create a free account and sign in.
2. Search and add these variables to your cart (MyGSS → Search Variables):
   `id year ballot wrkstat evwork educ degree indus10 satjob postlife pray
   relig16 news tvhours inttech relig attend reliten wwwhr age sex region
   wtssps`.
3. Create **Extract 1**: "Create Extract" → add the carted variables → under
   *Case selection*, filter `year` to **2014, 2016** → choose output format
   **JSON** (choose Excel/CSV only if JSON is unavailable in your account tier)
   → name it `gss_extract_1_2014_2016` → submit and download when processed.
4. Create **Extract 2** the same way with `year` = **2016, 2018**, named
   `gss_extract_2_2016_2018`.
5. Place the downloaded files under `/source/data/raw/` using the names above.

Expected schema per record (what the pipeline validates): the 23 fields listed
in step 2, numeric codes for answers, and the Data Explorer's missing-value
representation. **Note:** the Explorer renders missing values as labels (e.g.
".i: Inapplicable") or negative codes depending on export tier; if your export
differs from the committed tag format (`".d"` / `".i"` / `".n"` strings), adapt
the small `normalise_value()` function in `scripts/build_extracts.py` or map
the labels before ingestion. The pipeline will quarantine anything it does not
recognise rather than load it.

## C. Verifying equivalence

After either path, run:

```bash
cd source && python -m pipeline.main validate profile
```

and compare `docs/data_profile.md`: record counts (5,405 / 5,215), per-year
counts (2014: 2,538; 2016: 2,867; 2018: 2,348), overlap 2,867 and the
missingness table should match.
