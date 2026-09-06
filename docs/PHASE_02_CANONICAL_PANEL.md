# Phase 02 - Canonical Macro-Policy Panel

Status: complete - primary `NOT_TESTED`, diagnostic panel built

The pipeline built 1,550 monthly currency rows from January 2013 through
November 2025 and policy labels through June 2026. Of these, 1,088 rows are
complete under the amended source-recency rules. The registered confirmation
slice contains 246 complete currency-months out of 350.

There are zero confirmation months with all ten G10 currencies complete. Japan
has no eligible confirmation row because both registered CPI series stop in
2022. Euro-area confirmation coverage stops in June 2023 because its registered
unemployment series is discontinued. Most other currencies remain usable until
May-August 2025, after which the OECD migration gap exceeds the frozen recency
limit.

The panel is still useful for a diagnostic mechanism test:

- no missing feature is imputed or carried beyond its recency limit;
- each snapshot selects only ALFRED vintages available by that month-end;
- country-local expanding z-scores exclude the current observation;
- six-month policy labels come from BIS and are unavailable to training until
  the entire horizon has elapsed;
- no FX outcome is present in the Phase 02 code path or artifact.

The recency amendment was frozen before modeling and FX access. It changed the
limits from 75/150 days to 190/285 days for monthly/quarterly indicators because
the source's reference-period dates can precede actual OECD dissemination by
several months. Discontinued series still fail closed; the Phase 01 source gate
remains `FAIL`.
