from __future__ import annotations

from fx_structural_policy_divergence.phase05_gate import PROCEED, STOP, evaluate_gate


def _phase04(status: str = "SUPPORTED") -> dict[str, object]:
    return {
        "SPD_H2_PAIR_REVISION": status,
        "SPD_H3_RANK_IC": status,
        "SPD_H4_EXTREME_SPREAD": status,
        "SPD_H5_STABILITY": status,
        "fx_marks_non_executable": True,
        "profitability_claim": False,
        "sealed_2026_fx_accessed": False,
    }


def test_gate_proceeds_only_when_every_mandatory_condition_passes() -> None:
    result = evaluate_gate(
        {"phase_decision": "PASS"},
        {"SPD_H1_POLICY_SKILL": "SUPPORTED"},
        _phase04(),
    )
    assert result["decision"] == PROCEED
    assert result["technical_filter_research_authorized"] is True


def test_gate_fails_closed_for_not_tested_source_and_hypotheses() -> None:
    result = evaluate_gate(
        {"phase_decision": "FAIL"},
        {"SPD_H1_POLICY_SKILL": "NOT_TESTED"},
        _phase04("NOT_TESTED"),
    )
    assert result["decision"] == STOP
    assert result["technical_filter_research_authorized"] is False


def test_gate_requires_stability_even_if_point_estimates_pass() -> None:
    phase04 = _phase04()
    phase04["SPD_H5_STABILITY"] = "NOT_SUPPORTED"
    result = evaluate_gate(
        {"phase_decision": "PASS"},
        {"SPD_H1_POLICY_SKILL": "SUPPORTED"},
        phase04,
    )
    assert result["decision"] == STOP
