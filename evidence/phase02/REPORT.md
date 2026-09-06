# Phase 02 - Canonical macro-policy panel

Status: `NOT_TESTED_PRIMARY_DIAGNOSTIC_PANEL_BUILT`.

Built 1550 currency-month rows. The confirmation slice has 246/350 complete rows and 0 months with all ten currencies complete.

Each row uses the latest ALFRED vintage no later than the month-end snapshot. Expanding z-scores exclude the current observation. Stale features fail closed and are never carried or imputed. BIS six-month labels are purged until their horizon has elapsed.

Because Phase 01 failed full-window source coverage, this artifact is diagnostic only. No FX outcome was read.
