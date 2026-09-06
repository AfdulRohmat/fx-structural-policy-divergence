# Phase 05 - Final Research Review

Decision: `DO_NOT_PROCEED_WITH_SPD_V1`

## Executive answer

The research found a real and useful relationship from macro conditions to
subsequent central-bank policy changes, but it did not find evidence that the
monthly revision of that policy forecast creates a directional FX edge.

The result therefore does not justify using SPD v1 as a technical-entry filter.
This is stricter than saying “fundamentals do not matter.” It says the tested
transmission rule and horizon are not supported:

```text
inflation and labour -> six-month policy change       encouraging diagnostic
policy-forecast revision -> next-month FX direction  not supported diagnostic
```

## Evidence by phase

### Phase 01 - data qualification

BIS policy rates passed for all ten currencies through June 2026. The initial
conservative endpoint audit classified 0/30 registered macro legs as passing.
A pre-FX recency amendment recovered valid date-level rows, but still produced
zero confirmation months with all ten currencies complete. Japan CPI ends in
2022; euro-area unemployment ends in early 2023; most legacy OECD feeds end
during 2025. The primary research path was therefore marked `NOT_TESTED` before
any FX access.

### Phase 02 - canonical panel

The engine built 1,550 currency-month rows and 1,088 complete rows. Confirmation
has 246/350 complete currency-months but zero full-G10 months. Missing/stale
features were not imputed. Japan has no eligible confirmation row, so USDJPY is
not directly tested in this version.

### Phase 03 - macro to policy

On the available 246-row, nine-currency diagnostic sample:

| Model | Six-month policy MAE |
|---|---:|
| constrained structural model | 33.72 bp |
| equal-weight macro | 48.68 bp |
| no policy change | 48.88 bp |

The structural model's paired improvement intervals are wholly positive versus
both baselines. This validates the decision to learn weights from policy
outcomes rather than invent `+1/+2` scores. The latest fit gives the largest
macro coefficient to the inflation gap; labour tightness is constrained to
zero, while labour momentum contributes only slightly. The model is not simply
the two videos translated into equal weights.

Official H1 is still `NOT_TESTED` because the source qualification gate failed.

### Phase 04 - policy divergence to FX

| Diagnostic | Estimate | 95% interval |
|---|---:|---:|
| eligible pair revision slope | -0.00580% per bp | [-0.02849, +0.01301] |
| mean monthly rank IC | -0.022 | [-0.122, +0.084] |
| top-two minus bottom-two | -9.5 bp/month | [-42.8, +22.0] bp |

The three point estimates are negative and all intervals include zero. Pair
slope is negative in every individual year. Three- and six-month purged slopes
are also negative. Removing one currency at a time does not restore stability.

Level-only divergence, unfiltered revision divergence, and the equal-weight
video-style macro composite are also negative. There is no defensible positive
FX-context result hiding behind the primary filter.

## What the result means

The model can anticipate what central banks subsequently do without generating
unexpected FX information. Markets may already price the same macro state, and
exchange rates also respond to relative valuations, global risk, carry,
positioning, and the difference between realized policy and policy already
expected by traders. A good forecast of realized policy is not automatically a
good forecast of excess currency returns.

The videos remain directionally useful as an economic narrative, especially
for comparing inflation and labour regimes. Our evidence supports their
macro-to-policy layer. It does not support promoting their raw cross-country
ranking into a standalone or monthly directional FX signal.

## Allowed next research

Do not flip the signal or tune the same 2023-2025 outcomes. Sensible future work
requires a new preregistration and new information boundary:

1. collect official/national release vintages prospectively, especially for
   Japan and the euro area;
2. test policy forecast minus true market-implied OIS/futures expectations,
   rather than forecast level alone, when a qualified source is available;
3. add globally priced state variables such as risk regime, valuation, or carry
   only under a new contract and new holdout;
4. treat the current engine as a central-bank regime monitor, not a trading
   filter, until independent FX evidence exists.

ECB observations are non-executable reference marks. No PnL, costs, position
sizing, or standalone strategy was tested.
