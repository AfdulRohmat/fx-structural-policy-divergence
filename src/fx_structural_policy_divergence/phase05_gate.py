"""Fail-closed Phase 05 research gate."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .io_utils import write_json, write_jsonl, write_manifest

PROCEED = "PROCEED_TO_TECHNICAL_FILTER_RESEARCH_SPD_V1"
STOP = "DO_NOT_PROCEED_WITH_SPD_V1"


def evaluate_gate(
    phase01: dict[str, Any],
    phase03: dict[str, Any],
    phase04: dict[str, Any],
) -> dict[str, Any]:
    fx_statuses = {
        name: phase04.get(name)
        for name in (
            "SPD_H2_PAIR_REVISION",
            "SPD_H3_RANK_IC",
            "SPD_H4_EXTREME_SPREAD",
        )
    }
    supported_fx = [
        name for name, status in fx_statuses.items() if status == "SUPPORTED"
    ]
    checks = {
        "full_g10_point_in_time_source_coverage": phase01.get("phase_decision")
        == "PASS",
        "SPD_H1_POLICY_SKILL_supported": phase03.get("SPD_H1_POLICY_SKILL")
        == "SUPPORTED",
        "at_least_two_H2_H3_H4_supported": len(supported_fx) >= 2,
        "H2_or_H3_supported": any(
            fx_statuses[name] == "SUPPORTED"
            for name in ("SPD_H2_PAIR_REVISION", "SPD_H3_RANK_IC")
        ),
        "SPD_H5_STABILITY_supported": phase04.get("SPD_H5_STABILITY") == "SUPPORTED",
        "fx_marks_declared_non_executable": phase04.get("fx_marks_non_executable")
        is True,
        "no_profitability_claim": phase04.get("profitability_claim") is False,
        "sealed_2026_fx_untouched": phase04.get("sealed_2026_fx_accessed") is False,
    }
    mandatory = all(checks.values())
    return {
        "decision": PROCEED if mandatory else STOP,
        "technical_filter_research_authorized": mandatory,
        "checks": checks,
        "registered_hypotheses": {
            "SPD_H1_POLICY_SKILL": phase03.get("SPD_H1_POLICY_SKILL"),
            **fx_statuses,
            "SPD_H5_STABILITY": phase04.get("SPD_H5_STABILITY"),
        },
        "supported_fx_hypotheses": supported_fx,
        "failed_check_count": sum(not value for value in checks.values()),
    }


def run_phase05(root: Path) -> dict[str, Any]:
    phase01 = json.loads(
        (root / "evidence" / "phase01" / "summary.json").read_text(encoding="utf-8")
    )
    phase03 = json.loads(
        (root / "evidence" / "phase03" / "summary.json").read_text(encoding="utf-8")
    )
    phase04 = json.loads(
        (root / "evidence" / "phase04" / "summary.json").read_text(encoding="utf-8")
    )
    gate = evaluate_gate(phase01, phase03, phase04)
    h1 = phase03["h1_available_sample_diagnostic"]
    h2 = phase04["available_sample_diagnostics"]["H2_pair_revision"]
    h3 = phase04["available_sample_diagnostics"]["H3_rank_ic"]
    h4 = phase04["available_sample_diagnostics"]["H4_extreme_spread"]
    summary = {
        "phase": "05-research-gate",
        **gate,
        "readable_conclusion": (
            "Available-sample macro inputs predict six-month policy changes, but "
            "frozen policy-revision divergence does not predict next-month FX. "
            "Full-G10 source coverage also failed, so technical-filter research "
            "is not authorized under SPD v1."
        ),
        "diagnostic_evidence": {
            "policy_model_mae_bp": h1["mae_bp"]["prediction_primary_bp"],
            "policy_no_change_mae_bp": h1["mae_bp"]["no_change_bp"],
            "policy_equal_weight_mae_bp": h1["mae_bp"]["prediction_equal_weight_bp"],
            "pair_revision_slope_percent_per_bp": h2["slope_percent_per_bp"],
            "pair_revision_slope_95_ci": h2["slope_95_ci"],
            "mean_rank_ic": h3["mean_spearman"],
            "mean_rank_ic_95_ci": h3["mean_95_ci"],
            "extreme_spread_bp": h4["mean_bp"],
            "extreme_spread_95_ci_percent": h4["mean_95_ci_percent"],
        },
        "interpretation_boundary": {
            "supported_as_primary": [],
            "encouraging_diagnostic": ["macro_to_six_month_policy_change"],
            "not_supported_diagnostic": [
                "policy_revision_to_next_month_pair_return",
                "policy_revision_cross_sectional_rank_ic",
                "policy_revision_extreme_currency_spread",
                "year_and_leave_one_currency_stability",
            ],
            "not_estimable": ["USDJPY_due_to_JPY_vintage_gap"],
        },
    }
    evidence = root / "evidence" / "phase05"
    evidence.mkdir(parents=True, exist_ok=True)
    write_json(evidence / "summary.json", summary)
    write_json(
        evidence / "sample_flow.json",
        {
            "phase01_macro_legs_passed": phase01["macro_pass"],
            "phase01_macro_legs_required": phase01["macro_rows"],
            "phase03_policy_diagnostic_rows": h1["row_count"],
            "phase04_pair_rows": h2["row_count"],
            "phase04_distinct_pair_months": h2["month_count"],
            "phase04_rank_months": h3["month_count"],
        },
    )
    write_json(
        evidence / "source_manifest.json",
        {
            "phase01_summary": "evidence/phase01/summary.json",
            "phase03_summary": "evidence/phase03/summary.json",
            "phase04_summary": "evidence/phase04/summary.json",
            "new_data_read": False,
        },
    )
    contract = json.loads(
        (root / "config" / "research_contract_v0_1.json").read_text(encoding="utf-8")
    )
    write_json(evidence / "config_snapshot.yaml", contract)
    write_jsonl(
        evidence / "issues.jsonl",
        (
            {
                "severity": "BLOCKING",
                "check": name,
                "passed": passed,
            }
            for name, passed in gate["checks"].items()
            if not passed
        ),
    )
    report = (
        "# Phase 05 - Research gate\n\n"
        f"Decision: `{gate['decision']}`.\n\n"
        "The result has two distinct layers. The available-sample macro model "
        "predicts six-month policy changes materially better than both registered "
        "baselines. The frozen monthly policy-revision signal does not transfer "
        "that skill into FX direction: H2, H3, H4, and stability diagnostics all "
        "miss their positive-sign and interval requirements.\n\n"
        "The registered hypotheses remain NOT_TESTED because full-G10 point-in-time "
        "source coverage failed before modeling. The negative FX diagnostics are "
        "additional evidence against promoting this specification, not a substitute "
        "for the missing primary sample.\n\n"
        "Phase 06 technical-filter research is not authorized. A later study must "
        "use a prospectively frozen specification and genuinely new outcomes; it "
        "must not flip signs or tune horizons on this opened holdout.\n"
    )
    (evidence / "REPORT.md").write_text(report, encoding="utf-8", newline="\n")
    write_manifest(evidence, phase="05-research-gate")
    return summary


def main() -> None:
    print(json.dumps(run_phase05(Path.cwd()), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
