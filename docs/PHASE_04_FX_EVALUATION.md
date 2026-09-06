# Phase 04 - Frozen FX Evaluation

Status: complete - registered H2-H5 `NOT_TESTED`, diagnostics not supported

The runner first verified the canonical SHA-256 hashes of all Phase 03 currency
predictions, pair signals, and ranks. Only after the checks passed did it
download official ECB reference rates from December 2022 through December 2025.
The request and parser exclude all 2026 observations.

## One-month available-sample results

| Test | Estimate | 95% month-block interval | Diagnostic result |
|---|---:|---:|---|
| H2 pair revision slope | -0.00580% per bp | [-0.02849, +0.01301] | not supported |
| H3 mean monthly rank IC | -0.022 | [-0.122, +0.084] | not supported |
| H4 top-two minus bottom-two | -9.5 bp/month | [-42.8, +22.0] bp | not supported |

H2 uses 450 eligible pair-month rows across 30 distinct calendar months. H3
and H4 use 31 partial-universe months. Pair rows sharing a month stay together
inside the 10,000-resample circular month-block bootstrap, so the 450 rows are
not treated as 450 independent time observations.

The expected signs are not stable. The H2 slope is negative in 2023, 2024, and
2025, and leave-one-currency-out estimates do not repair the result. Level
divergence, unfiltered revision divergence, and the transparent equal-weight
video-style macro composite are also negative on their respective diagnostics.

This cleanly separates the two claims:

- the macro model predicts subsequent central-bank policy changes in the
  available sample;
- those policy-forecast revisions do not predict next-month FX direction in
  this sample.

All registered H2-H5 statuses remain `NOT_TESTED` because source coverage was
not full G10. Even viewed only as exploratory evidence, none meets its positive
direction/interval requirement. USDJPY itself is not estimable because the
registered Japanese inflation vintages end before the confirmation window.

ECB rates are non-executable reference marks. This phase does not represent a
strategy, include costs, size positions, or make a profitability claim.
