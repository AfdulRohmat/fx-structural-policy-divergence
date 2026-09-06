from __future__ import annotations

import inspect
from datetime import date

from fx_structural_policy_divergence.phase03_model import (
    block_bootstrap_mean_ci,
    eligible_training_rows,
    run_phase03,
    verify_prediction_freeze,
)
from fx_structural_policy_divergence.ridge import ridge_fit


def test_nonnegative_constraint_removes_negative_slope() -> None:
    design = [[1.0, 0.0], [1.0, 1.0], [1.0, 2.0]]
    target = [2.0, 1.0, 0.0]
    result = ridge_fit(
        design,
        target,
        penalty=0.1,
        unpenalized=frozenset({0}),
        nonnegative=frozenset({1}),
    )
    assert result[1] == 0.0


def test_training_label_is_purged_until_available() -> None:
    rows = [
        {
            "label_available_date": date(2023, 7, 31),
            "panel_complete": True,
            **{
                name: 1.0
                for name in (
                    "inflation_gap_z",
                    "inflation_momentum_z",
                    "labour_tightness_z",
                    "labour_momentum_z",
                    "policy_rate_percent",
                    "policy_change_3m_bp",
                    "policy_change_6m_bp",
                )
            },
        }
    ]
    assert eligible_training_rows(rows, date(2023, 6, 30)) == []
    assert eligible_training_rows(rows, date(2023, 7, 31)) == rows


def test_bootstrap_is_deterministic() -> None:
    values = {
        date(2023, 1, 31): [1.0, 2.0],
        date(2023, 2, 28): [2.0, 3.0],
        date(2023, 3, 31): [3.0, 4.0],
    }
    first = block_bootstrap_mean_ci(values, block_length=2, resamples=100, seed=7)
    second = block_bootstrap_mean_ci(values, block_length=2, resamples=100, seed=7)
    assert first == second


def test_phase03_runner_cannot_accept_fx_path() -> None:
    assert tuple(inspect.signature(run_phase03).parameters) == ("root",)


def test_freeze_verifier_rejects_mutated_signal(tmp_path) -> None:
    evidence = tmp_path / "evidence" / "phase03"
    evidence.mkdir(parents=True)
    for name in ("currency_predictions.csv", "pair_signals.csv", "currency_ranks.csv"):
        (evidence / name).write_text("frozen\n", encoding="utf-8")
    from fx_structural_policy_divergence.io_utils import sha256_file, write_json

    digest = sha256_file(evidence / "currency_predictions.csv")
    write_json(
        evidence / "prediction_freeze.json",
        {
            "currency_predictions_sha256": digest,
            "pair_signals_sha256": digest,
            "currency_ranks_sha256": digest,
        },
    )
    assert verify_prediction_freeze(tmp_path)["status"] == "PASS"
    (evidence / "pair_signals.csv").write_text("mutated\n", encoding="utf-8")
    import pytest

    with pytest.raises(ValueError, match="freeze mismatch"):
        verify_prediction_freeze(tmp_path)
