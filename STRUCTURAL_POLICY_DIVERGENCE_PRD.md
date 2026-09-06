# PRD - Structural Policy Divergence Engine

Version: 1.0
Status: Phase 00 frozen before source and confirmatory FX access
Product type: point-in-time G10 research engine, not a trading strategy

## 1. Purpose

Test whether a small, economically motivated inflation and labour state can
forecast each G10 central bank's six-month policy path, and whether relative
changes in those forecasts provide a useful slow-moving FX context.

The intended operational role is to select or filter opportunities before an
independently specified technical entry. The engine does not create entries,
stops, leverage, or position size.

## 2. Motivation from the two video frameworks

The first framework argues that inflation and labour trends, interpreted
relative to each bank's mandate, produce a hawkish-versus-dovish divergence.
The second argues that markets react to what comes next and to changes in
expectations, rather than mechanically reacting to an announced decision.

This project combines the testable overlap:

```text
point-in-time macro state
    -> model-implied future policy change
    -> revision in that forecast as new macro data arrive
    -> relative revision between two currencies
    -> candidate fundamental context
```

It cannot claim to measure what is already priced without a qualified market
expectations source. That missing layer remains explicit.

## 3. Prior result and separation

The prior `fx-fundamental-bias-engine` P1Y proxy specification ended with
`DO_NOT_PROCEED_WITH_P1Y_PROXY_SPECIFICATION`.

Its eligible structural-policy diagnostic reported model MAE of approximately
74.53 bp versus 107.09 bp for no change and 96.32 bp for an equal-weight macro
benchmark. This motivates a new question, but it is not preregistered evidence
and cannot satisfy any gate in this project.

The failed EIOPA proxy, its predictions, and its FX results are not model inputs
here.

## 4. Primary research questions

1. Does the structural macro model beat no-change and equal-weight benchmarks
   when forecasting the next six months of policy changes?
2. Does an upward relative revision in the predicted policy path precede
   appreciation of the corresponding base currency?
3. Does requiring policy-path level and revision to agree identify a cleaner
   context than either quantity alone?
4. Do the strongest and weakest G10 currencies separate out of sample?
5. Are the results stable across years and leave-one-currency-out checks?

## 5. Output semantics

The engine emits continuous basis-point quantities:

```text
policy_path_6m[c,t]
policy_revision_1m[c,t]
level_divergence[base/quote,t]
revision_divergence[base/quote,t]
```

It may also emit transparent categorical context:

- `STRONG_HAWKISH`: level and revision are positive;
- `HAWKISH_FADING`: level positive, revision negative;
- `STRONG_DOVISH`: level and revision are negative;
- `DOVISH_FADING`: level negative, revision positive;
- `INCOMPLETE`: any mandatory input is unavailable.

No arithmetic `+1/+2` score is allowed.

## 6. Universe and primary clock

The universe is:

```text
USD EUR JPY GBP CHF CAD AUD NZD NOK SEK
```

USDJPY is a required readable case study, but all model fitting and primary
selection remain G10 and pair-agnostic. The primary clock is one synchronized
month-end snapshot.

## 7. Proposed sample split

- Development and policy-model training: 2013-01 through 2022-12.
- Confirmatory forecast origins: 2023-01 through 2025-11.
- Policy-label support: through 2026-06, subject to source qualification.
- 2026 FX outcomes: sealed.

The final origin is November 2025 because its next-month FX endpoint remains in
2025; 2026 FX data stay sealed. If Phase 01 cannot prove point-in-time coverage,
the result is `NOT_TESTED` unless a versioned, pre-FX amendment is registered.

## 8. Explicit non-goals

- no EIOPA curve relabelled as market expectations;
- no claim that predicted policy changes are unpriced surprises;
- no fitting, threshold selection, or sign selection against FX returns;
- no LLM-generated historical data or discretionary historical labels;
- no intraday macro-event strategy;
- no technical entry or PnL study before the research gate;
- no inversion of a negative research result into a contrarian strategy;
- no access to sealed 2026 FX outcomes.

## 9. Success boundary

The strongest possible Phase 05 decision is
`PROCEED_TO_TECHNICAL_FILTER_RESEARCH_SPD_V1`. It means structural policy
divergence has enough out-of-sample evidence to be tested as a filter around an
unchanged technical setup. It does not mean the engine is independently
tradeable.
