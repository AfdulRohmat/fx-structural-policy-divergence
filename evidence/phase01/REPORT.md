# Phase 01 - Free source qualification

Decision: `FAIL`. Primary downstream status: `NOT_TESTED`.

BIS policy rates passed for all 10 currencies through June 2026. The strict macro gate passed 0/30 required currency-feature legs through November 2025. The legacy OECD series hosted by ALFRED mostly stop between early 2022 and spring 2025, so they cannot support the complete registered holdout.

This is a source failure, not an alpha result. Phase 01 did not read ECB FX data. Phase 02 may build a fail-closed diagnostic panel over available dates, but every registered primary hypothesis remains `NOT_TESTED` unless full point-in-time coverage is restored.

The exact SPD signal was not previously tested on 2023-2025 FX. Adjacent repositories did contain raw prices or different signals, and that exposure is explicitly recorded in `holdout_contamination_audit.json`.
