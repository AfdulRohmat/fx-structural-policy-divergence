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

Research complete through Phase 05. Final decision:

```text
DO_NOT_PROCEED_WITH_SPD_V1
```

The available-sample macro model materially improves six-month policy forecasts,
but its frozen monthly revisions do not show a positive next-month FX
association. Full-G10 point-in-time macro coverage also failed, mainly because
registered OECD/ALFRED series were discontinued. The project therefore does not
authorize technical-filter research.

The previous P1Y result remains unchanged:
`DO_NOT_PROCEED_WITH_P1Y_PROXY_SPECIFICATION`. Its structural-policy diagnostic
is prior motivation, not confirmatory evidence for this project.

## Research phases

| Phase | Scope | Status |
|---|---|---|
| 00 | PRD, causal scope, technical contract, project scaffold | Complete - frozen |
| 01 | free-source qualification and holdout-contamination audit | Complete - source gate failed |
| 02 | point-in-time G10 macro and policy panel | Complete - diagnostic panel |
| 03 | policy model and frozen structural-divergence signals | Complete - H1 diagnostic encouraging |
| 04 | frozen ECB FX evaluation | Complete - FX diagnostics not supported |
| 05 | aggregate research gate | Complete - do not proceed |
| 06+ | frozen technical-strategy filter research | Not authorized under SPD v1 |

## Result in one table

| Layer | Main diagnostic | Result |
|---|---:|---|
| macro -> six-month policy | model MAE 33.72 bp vs 48.88 bp no-change | encouraging |
| pair revision -> next-month FX | slope -0.00580%/bp, CI crosses zero | not supported |
| cross-sectional FX rank | mean IC -0.022, CI crosses zero | not supported |
| top-two minus bottom-two | -9.5 bp/month, CI crosses zero | not supported |

All registered hypotheses are formally `NOT_TESTED` because full-G10 source
qualification failed. The diagnostic FX results are nevertheless unfavorable
and do not justify promotion.

## Documentation

- [Product requirements](STRUCTURAL_POLICY_DIVERGENCE_PRD.md)
- [Frozen technical plan and contract](docs/TECHNICAL_PLAN.md)
- [Final research review](docs/PHASE_05_FINAL_RESEARCH_REVIEW.md)
- [Research backbone](references/RESEARCH_BACKBONE.md)

## Reproduce

The code uses the Python standard library only. From the repository root:

```powershell
$env:PYTHONPATH = (Resolve-Path src).Path
python -m fx_structural_policy_divergence.phase01_sources
python -m fx_structural_policy_divergence.phase02_panel
python -m fx_structural_policy_divergence.phase03_model
python -m fx_structural_policy_divergence.phase04_fx
python -m fx_structural_policy_divergence.phase05_gate
```

Phase 04 verifies the frozen Phase 03 hashes before it reads FX and rejects any
2026 observation. Raw downloads and full run artifacts remain ignored; compact
evidence and hashes are committed under `evidence/`.

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
