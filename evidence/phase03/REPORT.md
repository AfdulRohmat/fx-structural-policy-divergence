# Phase 03 - Policy model and signal freeze

Status: `FROZEN_DIAGNOSTIC_NOT_PRIMARY`; registered H1: `NOT_TESTED`.

Generated 255 currency predictions and 835 pair divergence rows without loading FX. The available-sample policy diagnostic estimable flag is True and its support flag is True.

All training labels satisfy the six-month availability purge. Model scalers, penalty selection, constraints, and intercepts are refit using past rows only. Signal hashes are frozen in `prediction_freeze.json` and must verify before Phase 04 can open ECB FX data.
