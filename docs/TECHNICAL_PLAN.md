# Technical Plan and Research Contract - SPD v1

Status: frozen before source qualification and confirmatory FX access
PRD: `STRUCTURAL_POLICY_DIVERGENCE_PRD.md` v1.0
Machine-readable contract: `config/research_contract_v0_1.json`

## 1. Research boundary

This project tests `STRUCTURAL_POLICY_CONTEXT`. It does not test or claim a
market-implied surprise because a qualified point-in-time OIS/futures source is
not available.

The causal scope is:

```text
point-in-time inflation and labour state
    -> predicted six-month policy-rate change
    -> one-month revision in that prediction
    -> base-minus-quote structural divergence
    -> subsequent FX association
    -> technical-filter research only after a successful gate
```

The prior P1Y proxy decision remains final in its repository. Its EIOPA inputs,
proxy coefficients, and FX outcomes cannot enter this project.

## 2. Holdout and access control

- 2013-2022 is development history.
- January 2023 through November 2025 is the confirmatory forecast-origin window.
- Policy data through June 2026 may be used solely to complete six-month labels
  for December 2025 forecast origins.
- FX observations from 2026 onward remain sealed.
- Phase 01 must audit whether anyone or any prior artifact evaluated the new SPD
  signal against the proposed holdout. Mere possession of raw prices is
  recorded but is not equivalent to outcome analysis.
- Normal Phase 00-03 commands must not accept an FX input path.
- Phase 04 must verify the immutable Phase 03 prediction hash before reading FX.

If Phase 01 cannot prove adequate point-in-time macro coverage through 2025,
the confirmatory test becomes `NOT_TESTED`; it must not silently use revised
current history.

## 3. Canonical entities

### 3.1 `central_bank_profile`

```text
currency
country_code
central_bank_code
effective_from
effective_to
target_measure_id
underlying_inflation_measure_id
labour_measure_id
inflation_target_lower
inflation_target_midpoint
inflation_target_upper
mandate_notes
source_url
source_published_at
retrieved_at
source_sha256
```

Intervals cannot overlap. Target and mandate changes create new records.

### 3.2 `macro_vintage_observation`

```text
currency
indicator_id
reference_period
value
unit
seasonal_adjustment
available_at
vintage_at
retrieved_at
provider
source_url
source_sha256
```

Uniqueness is `(currency, indicator_id, reference_period, vintage_at)`. Missing
availability or vintage timestamps fail closed.

### 3.3 `policy_rate_observation`

```text
currency
central_bank_code
effective_at
available_at
rate_percent
provider
source_url
source_sha256
```

### 3.4 `structural_policy_prediction`

```text
currency
snapshot_at
forecast_horizon_months
predicted_policy_change_bp
prediction_lower_bp
prediction_upper_bp
training_cutoff
training_row_count
selected_penalty
feature_order
model_artifact_sha256
```

### 3.5 `fx_reference_rate`

```text
currency
quote_currency
observation_at
available_at
rate
provider
source_url
source_sha256
research_mark_only
```

## 4. Point-in-time snapshot contract

The primary snapshot is 17:00 `Europe/Brussels` on the last date in each month
with a complete set of ECB G10 reference legs. At snapshot `t`, a macro record
is eligible only when:

```text
available_at <= t
vintage_at <= t
reference_period <= t
```

Selectors choose the latest eligible release. They never reach forward,
interpolate, or silently carry a stale observation. Recency limits are declared
per indicator frequency during Phase 01 and frozen before panel outcomes.

Observation period, release time, vintage time, retrieval time, and model
training cutoff remain separate fields.

## 5. Macro feature contract

Every feature is signed so positive means more hawkish pressure:

```text
inflation_gap_raw
    = policy-relevant inflation - target midpoint

inflation_momentum_raw
    = current underlying inflation trend - trend three months earlier

labour_tightness_raw
    = -unemployment rate

labour_momentum_raw
    = -(current unemployment - unemployment three releases earlier)
```

Index-based inflation uses point-in-time index levels. Rate-based alternatives
must be declared by currency and cannot change after FX access.

Each raw feature becomes a country-local expanding z-score using historical
reference-period observations visible in the selected vintage. The current
observation is excluded. Minimum history is 36 observations, standard deviation
uses `ddof=1`, and zero variance yields missing.

Raw components always remain visible. No `+1/+2` score is created.

## 6. Structural policy model

The target is:

```text
policy_change_6m[c,t]
    = 100 * (policy_rate[c,t+6m] - policy_rate[c,t])
```

Predictors are the four macro z-scores, current policy rate, and trailing
three-month policy change.

The primary estimator is pooled ridge regression with:

- one unpenalized intercept per central bank;
- common G10 macro slopes constrained non-negative;
- frozen policy-smoothing terms;
- deterministic penalty grid `0.01, 0.1, 1, 10, 100`;
- nested expanding-window penalty selection by policy-path MAE;
- an unconstrained diagnostic fit;
- minimum 60 training months per currency and 600 pooled rows.

Policy labels enter training only when the entire six-month horizon has elapsed.
Scaler, penalty, active constraints, and coefficients are refit inside each past
window. FX returns are not available to this phase.

## 7. Structural divergence signal

For currency `c`:

```text
level[c,t] = predicted_policy_change_6m[c,t]
revision[c,t] = level[c,t] - level[c,t-1m]
```

For pair `base/quote`:

```text
level_divergence = level[base,t] - level[quote,t]
revision_divergence = revision[base,t] - revision[quote,t]
```

Primary signal magnitude is `revision_divergence`. A primary directional
context is eligible only when level and revision have the same nonzero sign.
Conflicts are `TRANSITION`, not zero and not a forced trade direction.

The G10 cross-sectional implementation ranks currency revisions. Top-two and
bottom-two membership is deterministic; a tie at a portfolio boundary
invalidates that month's extreme-spread observation.

All Phase 03 predictions, feature order, coefficients, fold membership, input
hashes, and signal rows are frozen before Phase 04.

## 8. Baselines

### Policy forecast baselines

1. no policy change;
2. equal-weight macro composite with scale fitted only to policy outcomes;
3. unconstrained structural ridge as a diagnostic.

### FX-context baselines and diagnostics

1. level divergence without the revision filter;
2. transparent inflation/labour dominance ranking from the video framework;
3. revision signal without the level-agreement filter.

None may replace the primary result after holdout access.

## 9. Registered hypotheses

### `SPD_H1_POLICY_SKILL`

Supported only if the constrained policy model has lower confirmatory MAE than
both no change and equal weight, and both paired month-block 95% improvement
intervals are wholly positive.

### `SPD_H2_PAIR_REVISION`

Supported only if the pooled coefficient of next-month base appreciation on
eligible base-minus-quote revision divergence is positive and its 95% interval
is wholly positive. Only one orientation of each unordered pair is stored.

### `SPD_H3_RANK_IC`

Supported only if mean monthly Spearman correlation between G10 policy revision
and subsequent currency-basket return is positive with a wholly positive 95%
interval.

### `SPD_H4_EXTREME_SPREAD`

Supported only if next-month return of equal-weight top-two minus bottom-two
currencies is positive with a wholly positive 95% interval.

### `SPD_H5_STABILITY`

Supported only if H2, H3, and H4 point estimates retain the expected sign in
2023, 2024, and 2025 separately and in every leave-one-currency-out run.

Three- and six-month returns are secondary. Their overlapping labels use
purging and month-cluster inference and cannot rescue a failed primary horizon.

## 10. Statistical contract

- Primary unit: synchronized calendar month.
- Primary FX horizon: next non-overlapping month.
- Bootstrap: circular moving blocks over calendar-month clusters.
- Block length: 3 months.
- Resamples: 10,000.
- Seed: `20260906`.
- Currency and pair rows sharing a month remain in the same resampled cluster.
- All reported intervals are two-sided 95% percentile intervals.
- Pair observations do not inflate the effective time count; sample flow always
  reports both pair-row N and distinct-month N.

## 11. Phase plan

### Phase 00 - contract and scaffold

- create independent project and documentation;
- register causal scope, proposed sample, signals, hypotheses, and gates;
- record prior P1Y result only as motivation;
- access no new data or outcomes.

Exit: user accepts or amends the draft before source work.

### Phase 01 - source and holdout qualification

- audit free point-in-time macro sources for every feature and G10 currency;
- repair the known JPY inflation and CHF/NOK labour legacy gaps with documented
  official replacements or fail them closed;
- qualify BIS policy rates and central-bank profile histories;
- perform a 2023-2025 holdout-contamination audit;
- freeze indicator-specific recency limits and final feasible dates;
- do not download or parse confirmatory FX returns.

Exit: `PASS`, `REVIEW_REQUIRED`, or `FAIL` source matrix.

### Phase 02 - canonical macro and policy panel

- implement schemas and immutable adapters;
- build monthly point-in-time states and six-month policy labels;
- prove past-only selector and standardizer invariance;
- emit coverage and missingness by currency/month;
- keep FX outcomes inaccessible.

Exit: complete G10 panel or `NOT_TESTED`.

### Phase 03 - policy model and signal freeze

- run nested walk-forward constrained and unconstrained policy models;
- evaluate `SPD_H1_POLICY_SKILL` using policy outcomes only;
- generate level, revision, pair divergence, ranks, and context quadrants;
- freeze prediction artifact and SHA-256 manifest;
- record a machine-verifiable assertion that no FX input was read.

Exit: immutable Phase 03 signal artifact. A failed H1 blocks promotion but does
not authorize model changes after FX access.

### Phase 04 - confirmatory FX evaluation

- verify the frozen Phase 03 hash;
- only then obtain and parse 2023-2025 ECB reference rates;
- derive one orientation per pair and centered G10 currency returns;
- evaluate `SPD_H2` through `SPD_H5` without refit or sign flip;
- label ECB rates non-executable and make no PnL claim.

### Phase 05 - research gate

Phase 05 aggregates frozen results. It emits
`PROCEED_TO_TECHNICAL_FILTER_RESEARCH_SPD_V1` only when:

1. point-in-time provenance and full G10 coverage pass;
2. `SPD_H1_POLICY_SKILL` is `SUPPORTED`;
3. at least two of `SPD_H2`, `SPD_H3`, and `SPD_H4` are `SUPPORTED`, including
   at least one of H2 or H3;
4. `SPD_H5_STABILITY` is `SUPPORTED`;
5. FX marks are explicitly non-executable and no profitability claim is made;
6. 2026 FX outcomes remain sealed.

Any mandatory `FAIL`, `NOT_SUPPORTED`, or `NOT_TESTED` produces
`DO_NOT_PROCEED_WITH_SPD_V1`.

### Phase 06+ - technical filter research

Allowed only after Phase 05 proceeds. The technical setup, entry, exit, and
risk rules must be frozen independently. The primary comparison is the same
technical setup unfiltered versus aligned, transition, and opposed structural
policy contexts.

## 12. Artifact contract

Every phase writes a new immutable run directory containing:

```text
config_snapshot.yaml
source_manifest.json
sample_flow.json
issues.jsonl
summary.json
REPORT.md
manifest.json
```

Model phases additionally persist feature order, scalers, training membership,
label-availability cutoffs, selected penalties, coefficients, predictions,
benchmarks, residuals, bootstrap settings, software version, and input hashes.

Compact evidence and readable reports are committed. Raw source payloads and
full artifacts remain ignored but hash-addressed.

## 13. Test and quality gates

Required network-free tests include:

- schema uniqueness and interval-overlap rejection;
- exact-vintage selection and post-origin mutation invariance;
- stale/missing inputs fail closed;
- six-month label purge at every fold;
- non-negative macro-slope enforcement;
- deterministic penalty and bootstrap selection;
- Phase 00-03 CLI rejection of FX paths;
- Phase 03 prediction-hash verification before Phase 04;
- ECB orientation and synchronized G10 month-end marks;
- inverse-pair duplicate rejection;
- 2026 FX seal enforcement;
- Phase 05 fails closed for every non-supported mandatory gate.

Before merging any phase:

```powershell
python -m pytest -q
ruff check .
mypy src
git diff --check
```

## 14. Change control

After this contract is frozen, changes to data definitions,
features, signal transform, primary horizon, sample split, model family,
hypotheses, or gate require:

1. a versioned amendment;
2. a reason independent of confirmatory FX outcomes;
3. a new hypothesis identifier when the tested claim changes;
4. preservation of the original artifact and result;
5. no retroactive preregistration claim.
