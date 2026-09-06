# FX Structural Policy Divergence

A pair-agnostic G10 research project testing whether point-in-time inflation
and labour conditions can produce a useful central-bank policy context for FX.

The project implements the part of the earlier Fundamental Bias research that
was promising:

```text
inflation and labour state
    -> predicted six-month central-bank policy path
    -> policy-path level and monthly revision
    -> hawkish-versus-dovish currency divergence
    -> FX context research
    -> technical filtering only after a successful gate
```

It does not reuse the failed EIOPA one-year proxy as a market-expectations
series. Until a genuine OIS/futures layer is qualified, every output is labelled
`STRUCTURAL_POLICY_CONTEXT`, not market surprise or standalone trading alpha.

## Current status

Phase 00 is frozen before source qualification and confirmatory FX access. No
source has been downloaded, no 2023-2025 confirmatory FX return has been opened,
and 2026 remains sealed.

The previous P1Y result remains unchanged:
`DO_NOT_PROCEED_WITH_P1Y_PROXY_SPECIFICATION`. Its structural-policy diagnostic
is prior motivation, not confirmatory evidence for this project.

## Proposed phases

| Phase | Scope | Status |
|---|---|---|
| 00 | PRD, causal scope, technical contract, project scaffold | Complete - frozen |
| 01 | free-source qualification and holdout-contamination audit | Pending |
| 02 | point-in-time G10 macro and policy panel | Pending |
| 03 | policy model and frozen structural-divergence signals | Pending |
| 04 | open confirmatory FX outcomes and evaluate | Blocked until Phase 03 freeze |
| 05 | aggregate research gate | Pending |
| 06+ | frozen technical-strategy filter research | Only after Phase 05 proceeds |

## Documentation

- [Product requirements](STRUCTURAL_POLICY_DIVERGENCE_PRD.md)
- [Technical plan and draft contract](docs/TECHNICAL_PLAN.md)

## Planned package layout

```text
config/                 versioned research contracts
docs/                   technical and phase reports
evidence/               compact committed audit evidence
references/             research papers and source notes
src/fx_structural_policy_divergence/
tests/
```

Raw provider payloads and complete run artifacts stay ignored. Each completed
phase will commit compact evidence, a readable report, and deterministic
reproduction commands.
