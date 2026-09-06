# Phase 03 - Policy Model and Signal Freeze

Status: complete - signals frozen, primary H1 `NOT_TESTED`

The policy-only walk-forward model generated 255 currency predictions, 835
fixed-orientation pair rows, and 242 cross-sectional rank rows. No FX input is
accepted by the Phase 03 runner and no FX outcome was read.

## Available-sample diagnostic

The diagnostic confirmation sample contains 246 currency-months across nine
currencies and 32 calendar months. Japan is absent because its registered
inflation series is stale before the confirmation window.

| Forecast | MAE (bp) |
|---|---:|
| constrained structural policy model | 33.72 |
| equal-weight macro baseline | 48.68 |
| no policy change | 48.88 |

The paired MAE improvement 95% month-block intervals are:

- versus equal weight: `[4.89, 26.85]` bp;
- versus no change: `[1.78, 28.16]` bp.

This is encouraging evidence for the video/research-paper mechanism: inflation
and labour state help forecast the direction and magnitude of the next six
months of central-bank policy better than arbitrary `+1/+2` scoring. The
weights are fitted inside past-only folds against realized policy changes,
rather than chosen by opinion.

It is not a registered positive H1 result. The source gate failed before the
model was fit, and the diagnostic sample is incomplete and unbalanced. H1 is
therefore retained as `NOT_TESTED` regardless of its favorable point estimate.

## Freeze boundary

`evidence/phase03/prediction_freeze.json` stores SHA-256 hashes for currency
predictions, pair signals, ranks, and the Phase 02 panel. Phase 04 must verify
all three signal hashes before downloading or parsing ECB FX marks. Any mutation
fails closed.
