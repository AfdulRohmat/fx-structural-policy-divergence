# Phase 01 - Source Qualification

Status: complete - `FAIL` for the registered full-G10 primary test

The official BIS monthly policy-rate API covers all ten registered currencies
through June 2026. The macro layer does not meet the stricter point-in-time
coverage requirement through November 2025.

All 30 currency-feature legs were checked against their ALFRED source forms and
the registered recency limits. None covers the entire confirmation endpoint.
The common legacy OECD CPI family was discontinued during the OECD data-system
transition in early 2025; Japan CPI ended much earlier, and the registered euro
area unemployment series ends in January 2023. A currently revised replacement
cannot silently be substituted after the research contract was frozen.

This means the registered SPD hypotheses are `NOT_TESTED`, not failed economic
hypotheses. We will still build a date-eligible diagnostic panel and freeze its
predictions before any FX access. That diagnostic can reveal whether the
engineering and mechanism deserve a later rerun with a qualified archive, but
it cannot pass the Phase 05 promotion gate.

No confirmatory FX input was downloaded or parsed in this phase. Detailed
series endpoints, raw hashes, and holdout-contamination disclosures are under
`evidence/phase01/`.
