"""Phase 03 policy-only walk-forward model and immutable signal freeze."""

from __future__ import annotations

import csv
import inspect
import json
import random
import statistics
from collections import Counter
from dataclasses import dataclass
from datetime import date
from itertools import combinations
from pathlib import Path
from typing import Any

from .io_utils import (
    sha256_bytes,
    sha256_file,
    write_csv,
    write_json,
    write_jsonl,
    write_manifest,
)
from .ridge import predict, ridge_fit
from .time_utils import add_months, month_ends

MACRO_FEATURES = (
    "inflation_gap_z",
    "inflation_momentum_z",
    "labour_tightness_z",
    "labour_momentum_z",
)
POLICY_FEATURES = (*MACRO_FEATURES, "policy_rate_percent", "policy_change_3m_bp")
BASE_PRIORITY = ("EUR", "GBP", "AUD", "NZD", "USD", "CAD", "CHF", "JPY", "NOK", "SEK")


def canonical_text_sha256(path: Path) -> str:
    """Hash logical text consistently across Git LF/CRLF checkouts."""
    return sha256_bytes(path.read_bytes().replace(b"\r\n", b"\n"))


@dataclass(frozen=True)
class FittedModel:
    feature_names: tuple[str, ...]
    currencies: tuple[str, ...]
    means: tuple[float, ...]
    scales: tuple[float, ...]
    coefficients: tuple[float, ...]
    penalty: float
    residual_sd: float


def _read_panel(path: Path) -> list[dict[str, Any]]:
    numeric = (*POLICY_FEATURES, "policy_change_6m_bp")
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8", newline="") as handle:
        for source in csv.DictReader(handle):
            row: dict[str, Any] = dict(source)
            row["snapshot_date"] = date.fromisoformat(source["snapshot"])
            row["label_available_date"] = date.fromisoformat(
                source["label_available_at"]
            )
            for name in numeric:
                row[name] = None if source.get(name, "") == "" else float(source[name])
            row["panel_complete"] = source["panel_complete"] == "True"
            rows.append(row)
    return rows


def _has_values(row: dict[str, Any], names: tuple[str, ...]) -> bool:
    return all(row.get(name) is not None for name in names)


def eligible_training_rows(
    rows: list[dict[str, Any]], origin: date
) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if row["label_available_date"] <= origin
        and row["panel_complete"]
        and _has_values(row, (*POLICY_FEATURES, "policy_change_6m_bp"))
    ]


def _scaler(
    rows: list[dict[str, Any]], feature_names: tuple[str, ...]
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    means: list[float] = []
    scales: list[float] = []
    for name in feature_names:
        values = [float(row[name]) for row in rows]
        means.append(statistics.mean(values))
        deviation = statistics.stdev(values) if len(values) > 1 else 0.0
        scales.append(deviation if deviation > 0 else 1.0)
    return tuple(means), tuple(scales)


def _design_row(
    row: dict[str, Any],
    currencies: tuple[str, ...],
    feature_names: tuple[str, ...],
    means: tuple[float, ...],
    scales: tuple[float, ...],
) -> list[float]:
    return [float(row["currency"] == item) for item in currencies] + [
        (float(row[name]) - mean) / scale
        for name, mean, scale in zip(feature_names, means, scales, strict=True)
    ]


def _fit(
    rows: list[dict[str, Any]],
    *,
    currencies: tuple[str, ...],
    feature_names: tuple[str, ...],
    penalty: float,
    nonnegative_count: int,
) -> FittedModel:
    means, scales = _scaler(rows, feature_names)
    design = [
        _design_row(row, currencies, feature_names, means, scales) for row in rows
    ]
    targets = [float(row["policy_change_6m_bp"]) for row in rows]
    offset = len(currencies)
    coefficients = ridge_fit(
        design,
        targets,
        penalty=penalty,
        unpenalized=frozenset(range(offset)),
        nonnegative=frozenset(range(offset, offset + nonnegative_count)),
    )
    residuals = [
        target - predict(item, coefficients)
        for item, target in zip(design, targets, strict=True)
    ]
    residual_sd = statistics.stdev(residuals) if len(residuals) > 1 else 0.0
    return FittedModel(
        feature_names,
        currencies,
        means,
        scales,
        coefficients,
        penalty,
        residual_sd,
    )


def _predict(model: FittedModel, row: dict[str, Any]) -> float:
    design = _design_row(
        row,
        model.currencies,
        model.feature_names,
        model.means,
        model.scales,
    )
    return predict(design, model.coefficients)


def _validation_starts(rows: list[dict[str, Any]]) -> tuple[date, ...]:
    dates = sorted({row["snapshot_date"] for row in rows})
    if len(dates) < 24:
        return ()
    indices = sorted({max(12, len(dates) - offset) for offset in (18, 12, 6)})
    return tuple(dates[index] for index in indices if index < len(dates))


def select_penalty(
    rows: list[dict[str, Any]],
    *,
    currencies: tuple[str, ...],
    penalties: tuple[float, ...],
) -> tuple[float, list[dict[str, object]]]:
    starts = _validation_starts(rows)
    if not starts:
        return penalties[0], []
    results: list[tuple[float, float]] = []
    records: list[dict[str, object]] = []
    for penalty in penalties:
        errors: list[float] = []
        for start in starts:
            train = [row for row in rows if row["label_available_date"] <= start]
            validation_end = add_months(start, 5)
            validation = [
                row for row in rows if start <= row["snapshot_date"] <= validation_end
            ]
            counts = Counter(str(row["currency"]) for row in train)
            if not validation or any(counts[item] < 24 for item in currencies):
                continue
            model = _fit(
                train,
                currencies=currencies,
                feature_names=POLICY_FEATURES,
                penalty=penalty,
                nonnegative_count=len(MACRO_FEATURES),
            )
            fold_errors = [
                abs(float(row["policy_change_6m_bp"]) - _predict(model, row))
                for row in validation
            ]
            errors.extend(fold_errors)
            records.append(
                {
                    "penalty": penalty,
                    "validation_start": start.isoformat(),
                    "training_rows": len(train),
                    "validation_rows": len(validation),
                    "mae": statistics.mean(fold_errors),
                }
            )
        results.append((statistics.mean(errors) if errors else float("inf"), penalty))
    return min(results)[1], records


def _minimums_met(
    rows: list[dict[str, Any]],
    currencies: tuple[str, ...],
    per_currency: int,
    pooled: int,
) -> bool:
    counts = Counter(str(row["currency"]) for row in rows)
    return len(rows) >= pooled and all(
        counts[item] >= per_currency for item in currencies
    )


def _quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = probability * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def block_bootstrap_mean_ci(
    values_by_month: dict[date, list[float]],
    *,
    block_length: int,
    resamples: int,
    seed: int,
) -> tuple[float, float]:
    months = sorted(values_by_month)
    monthly = [statistics.mean(values_by_month[item]) for item in months]
    if not monthly:
        raise ValueError("cannot bootstrap an empty series")
    generator = random.Random(seed)
    estimates: list[float] = []
    for _ in range(resamples):
        sample: list[float] = []
        while len(sample) < len(monthly):
            start = generator.randrange(len(monthly))
            sample.extend(
                monthly[(start + offset) % len(monthly)]
                for offset in range(block_length)
            )
        estimates.append(statistics.mean(sample[: len(monthly)]))
    return _quantile(estimates, 0.025), _quantile(estimates, 0.975)


def _policy_diagnostic(
    predictions: list[dict[str, Any]], contract: dict[str, Any]
) -> dict[str, Any]:
    eligible = [
        row
        for row in predictions
        if row["sample"] == "CONFIRMATION"
        and row["prediction_primary_bp"] is not None
        and row["prediction_equal_weight_bp"] is not None
        and row["actual_policy_change_6m_bp"] is not None
    ]
    if not eligible:
        return {"estimable": False, "supported": False, "row_count": 0}
    losses: dict[str, float] = {}
    for model in (
        "prediction_primary_bp",
        "prediction_equal_weight_bp",
        "no_change_bp",
    ):
        losses[model] = statistics.mean(
            abs(float(row["actual_policy_change_6m_bp"]) - float(row[model]))
            for row in eligible
        )
    intervals: dict[str, list[float]] = {}
    for index, baseline in enumerate(("prediction_equal_weight_bp", "no_change_bp")):
        values: dict[date, list[float]] = {}
        for row in eligible:
            actual = float(row["actual_policy_change_6m_bp"])
            improvement = abs(actual - float(row[baseline])) - abs(
                actual - float(row["prediction_primary_bp"])
            )
            values.setdefault(date.fromisoformat(row["snapshot"]), []).append(
                improvement
            )
        interval = block_bootstrap_mean_ci(
            values,
            block_length=int(contract["bootstrap"]["block_length_months"]),
            resamples=int(contract["bootstrap"]["resamples"]),
            seed=int(contract["bootstrap"]["seed"]) + index,
        )
        intervals[baseline] = [*interval]
    supported = all(
        losses["prediction_primary_bp"] < losses[item]
        for item in ("prediction_equal_weight_bp", "no_change_bp")
    ) and all(item[0] > 0 for item in intervals.values())
    return {
        "estimable": True,
        "supported": supported,
        "row_count": len(eligible),
        "month_count": len({row["snapshot"] for row in eligible}),
        "currencies": sorted({row["currency"] for row in eligible}),
        "mae_bp": losses,
        "paired_mae_improvement_95_ci_bp": intervals,
    }


def _pair_orientation(left: str, right: str) -> tuple[str, str]:
    priority = {currency: index for index, currency in enumerate(BASE_PRIORITY)}
    return (left, right) if priority[left] < priority[right] else (right, left)


def _signals(
    predictions: list[dict[str, Any]], currencies: tuple[str, ...]
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    by_key = {(row["snapshot"], row["currency"]): row for row in predictions}
    pairs: list[dict[str, object]] = []
    ranks: list[dict[str, object]] = []
    months = sorted(
        {row["snapshot"] for row in predictions if row["sample"] == "CONFIRMATION"}
    )
    for snapshot in months:
        available = [
            row
            for row in predictions
            if row["snapshot"] == snapshot and row["revision_1m_bp"] is not None
        ]
        ordered = sorted(
            available,
            key=lambda row: (-float(row["revision_1m_bp"]), str(row["currency"])),
        )
        revisions = [float(row["revision_1m_bp"]) for row in ordered]
        boundary_tie = len(revisions) >= 4 and (
            revisions[1] == revisions[2] or revisions[-2] == revisions[-3]
        )
        for rank, row in enumerate(ordered, start=1):
            ranks.append(
                {
                    "snapshot": snapshot,
                    "currency": row["currency"],
                    "revision_1m_bp": row["revision_1m_bp"],
                    "rank": rank,
                    "universe_size": len(ordered),
                    "bucket": (
                        "INVALID_TIE"
                        if boundary_tie
                        else "TOP2"
                        if rank <= 2
                        else "BOTTOM2"
                        if rank > len(ordered) - 2
                        else "MIDDLE"
                    ),
                    "registered_full_g10": len(ordered) == len(currencies),
                }
            )
        for first, second in combinations(currencies, 2):
            base, quote = _pair_orientation(first, second)
            base_row = by_key.get((snapshot, base))
            quote_row = by_key.get((snapshot, quote))
            if base_row is None or quote_row is None:
                continue
            if (
                base_row["revision_1m_bp"] is None
                or quote_row["revision_1m_bp"] is None
            ):
                continue
            level = float(base_row["prediction_primary_bp"]) - float(
                quote_row["prediction_primary_bp"]
            )
            revision = float(base_row["revision_1m_bp"]) - float(
                quote_row["revision_1m_bp"]
            )
            agreement = level != 0 and revision != 0 and level * revision > 0
            pairs.append(
                {
                    "snapshot": snapshot,
                    "pair": f"{base}{quote}",
                    "base": base,
                    "quote": quote,
                    "level_divergence_bp": level,
                    "revision_divergence_bp": revision,
                    "context": (
                        "BASE_HAWKISH"
                        if agreement and revision > 0
                        else "BASE_DOVISH"
                        if agreement
                        else "TRANSITION"
                    ),
                    "primary_eligible": agreement,
                    "registered_full_g10": False,
                }
            )
    return pairs, ranks


def verify_prediction_freeze(root: Path) -> dict[str, Any]:
    evidence = root / "evidence" / "phase03"
    freeze = json.loads(
        (evidence / "prediction_freeze.json").read_text(encoding="utf-8")
    )
    checks = {
        "currency_predictions": (
            canonical_text_sha256(evidence / "currency_predictions.csv")
            == freeze["currency_predictions_sha256"]
        ),
        "pair_signals": (
            canonical_text_sha256(evidence / "pair_signals.csv")
            == freeze["pair_signals_sha256"]
        ),
        "currency_ranks": (
            canonical_text_sha256(evidence / "currency_ranks.csv")
            == freeze["currency_ranks_sha256"]
        ),
    }
    if not all(checks.values()):
        raise ValueError(f"Phase 03 prediction freeze mismatch: {checks}")
    return {"status": "PASS", "checks": checks, "freeze": freeze}


def run_phase03(root: Path) -> dict[str, Any]:
    contract = json.loads(
        (root / "config" / "research_contract_v0_1.json").read_text(encoding="utf-8")
    )
    source_summary = json.loads(
        (root / "evidence" / "phase01" / "source_gate_summary.json").read_text(
            encoding="utf-8"
        )
    )
    panel_path = root / "artifacts" / "phase02" / "panel.csv"
    rows = _read_panel(panel_path)
    currencies = tuple(contract["currency_universe"])
    penalties = tuple(float(item) for item in contract["ridge_penalties"])
    forecast_dates = month_ends(date(2022, 12, 31), date(2025, 11, 30))
    predictions: list[dict[str, Any]] = []
    coefficient_records: list[dict[str, Any]] = []
    fold_records: list[dict[str, object]] = []
    for origin in forecast_dates:
        training = eligible_training_rows(rows, origin)
        counts = Counter(str(row["currency"]) for row in training)
        diagnostic_ok = _minimums_met(training, currencies, 36, 360)
        primary_ok = _minimums_met(
            training,
            currencies,
            int(contract["minimum_training_months_per_currency"]),
            int(contract["minimum_pooled_training_rows"]),
        )
        if not diagnostic_ok:
            continue
        selected, folds = select_penalty(
            training, currencies=currencies, penalties=penalties
        )
        fold_records.extend(
            {"outer_origin": origin.isoformat(), **row} for row in folds
        )
        constrained = _fit(
            training,
            currencies=currencies,
            feature_names=POLICY_FEATURES,
            penalty=selected,
            nonnegative_count=len(MACRO_FEATURES),
        )
        unconstrained = _fit(
            training,
            currencies=currencies,
            feature_names=POLICY_FEATURES,
            penalty=selected,
            nonnegative_count=0,
        )
        equal_rows = []
        for row in training:
            candidate = dict(row)
            candidate["equal_macro"] = statistics.mean(
                float(row[item]) for item in MACRO_FEATURES
            )
            equal_rows.append(candidate)
        equal_model = _fit(
            equal_rows,
            currencies=currencies,
            feature_names=("equal_macro",),
            penalty=selected,
            nonnegative_count=1,
        )
        coefficient_records.append(
            {
                "origin": origin.isoformat(),
                "selected_penalty": selected,
                "training_rows": len(training),
                "training_counts": dict(sorted(counts.items())),
                "feature_order": list(POLICY_FEATURES),
                "means": list(constrained.means),
                "scales": list(constrained.scales),
                "constrained_coefficients": list(constrained.coefficients),
                "unconstrained_coefficients": list(unconstrained.coefficients),
                "active_zero_macro_constraints": [
                    feature
                    for feature, value in zip(
                        MACRO_FEATURES,
                        constrained.coefficients[len(currencies) : len(currencies) + 4],
                        strict=True,
                    )
                    if value == 0
                ],
                "primary_training_minimum_met": primary_ok,
            }
        )
        for row in rows:
            if row["snapshot_date"] != origin or not _has_values(row, POLICY_FEATURES):
                continue
            level = _predict(constrained, row)
            equal_row = dict(row)
            equal_row["equal_macro"] = statistics.mean(
                float(row[item]) for item in MACRO_FEATURES
            )
            predictions.append(
                {
                    "snapshot": origin.isoformat(),
                    "currency": row["currency"],
                    "sample": "DEVELOPMENT"
                    if origin <= date(2022, 12, 31)
                    else "CONFIRMATION",
                    "prediction_primary_bp": level,
                    "prediction_lower_bp": level - 1.96 * constrained.residual_sd,
                    "prediction_upper_bp": level + 1.96 * constrained.residual_sd,
                    "prediction_unconstrained_bp": _predict(unconstrained, row),
                    "prediction_equal_weight_bp": _predict(equal_model, equal_row),
                    "no_change_bp": 0.0,
                    "actual_policy_change_6m_bp": row["policy_change_6m_bp"],
                    "selected_penalty": selected,
                    "training_cutoff": origin.isoformat(),
                    "training_row_count": len(training),
                    "primary_training_minimum_met": primary_ok,
                    "source_primary_eligible": source_summary["phase_decision"]
                    == "PASS",
                    "revision_1m_bp": None,
                }
            )
    prediction_by_key = {(row["snapshot"], row["currency"]): row for row in predictions}
    for row in predictions:
        previous = add_months(date.fromisoformat(row["snapshot"]), -1).isoformat()
        prior = prediction_by_key.get((previous, row["currency"]))
        if prior is not None:
            row["revision_1m_bp"] = float(row["prediction_primary_bp"]) - float(
                prior["prediction_primary_bp"]
            )
    pairs, ranks = _signals(predictions, currencies)
    h1_diagnostic = _policy_diagnostic(predictions, contract)
    artifact = root / "artifacts" / "phase03"
    evidence = root / "evidence" / "phase03"
    artifact.mkdir(parents=True, exist_ok=True)
    evidence.mkdir(parents=True, exist_ok=True)
    for destination in (artifact, evidence):
        write_csv(destination / "currency_predictions.csv", predictions)
        write_csv(destination / "pair_signals.csv", pairs)
        write_csv(destination / "currency_ranks.csv", ranks)
    write_json(artifact / "coefficients.json", coefficient_records)
    write_json(artifact / "nested_fold_records.json", fold_records)
    freeze = {
        "phase": "03-policy-signal-freeze",
        "currency_predictions_sha256": canonical_text_sha256(
            evidence / "currency_predictions.csv"
        ),
        "pair_signals_sha256": canonical_text_sha256(evidence / "pair_signals.csv"),
        "currency_ranks_sha256": canonical_text_sha256(evidence / "currency_ranks.csv"),
        "panel_input_sha256": sha256_file(panel_path),
        "fx_input_read": False,
        "sealed_2026_fx_read": False,
        "runner_parameters": tuple(inspect.signature(run_phase03).parameters),
    }
    summary = {
        "phase": "03-policy-signal-freeze",
        "status": "FROZEN_DIAGNOSTIC_NOT_PRIMARY",
        "SPD_H1_POLICY_SKILL": "NOT_TESTED",
        "h1_available_sample_diagnostic": h1_diagnostic,
        "source_gate": source_summary["phase_decision"],
        "prediction_rows": len(predictions),
        "pair_signal_rows": len(pairs),
        "eligible_pair_signal_rows": sum(
            bool(row["primary_eligible"]) for row in pairs
        ),
        "rank_rows": len(ranks),
        "fx_outcomes_accessed": False,
        "primary_interpretation": (
            "H1 remains NOT_TESTED because the source gate failed even if the "
            "available-sample diagnostic has a positive or negative result."
        ),
    }
    penalties_used = Counter(
        str(row["selected_penalty"]) for row in coefficient_records
    )
    model_audit = {
        "feature_order": list(POLICY_FEATURES),
        "currency_intercept_order": list(currencies),
        "outer_fit_count": len(coefficient_records),
        "nested_fold_count": len(fold_records),
        "selected_penalty_counts": dict(sorted(penalties_used.items())),
        "first_outer_origin": (
            coefficient_records[0]["origin"] if coefficient_records else None
        ),
        "last_outer_origin": (
            coefficient_records[-1]["origin"] if coefficient_records else None
        ),
        "latest_fit": coefficient_records[-1] if coefficient_records else None,
        "constraint": "Four common macro slopes constrained non-negative",
        "fx_outcomes_accessed": False,
    }
    for destination in (artifact, evidence):
        write_json(destination / "summary.json", summary)
        write_json(
            destination / "sample_flow.json",
            {
                "panel_rows": len(rows),
                "prediction_rows": len(predictions),
                "pair_signal_rows": len(pairs),
                "rank_rows": len(ranks),
            },
        )
        write_json(
            destination / "source_manifest.json",
            {
                "panel_sha256": freeze["panel_input_sha256"],
                "fx_input_read": False,
            },
        )
        write_json(destination / "config_snapshot.yaml", contract)
        write_jsonl(
            destination / "issues.jsonl",
            [
                {
                    "severity": "BLOCKING_PRIMARY",
                    "code": "PHASE01_SOURCE_GATE_FAILED",
                    "effect": "All registered hypotheses remain NOT_TESTED.",
                }
            ],
        )
        write_json(destination / "prediction_freeze.json", freeze)
        write_json(destination / "model_audit.json", model_audit)
        report = (
            "# Phase 03 - Policy model and signal freeze\n\n"
            f"Status: `{summary['status']}`; registered H1: `NOT_TESTED`.\n\n"
            f"Generated {len(predictions)} currency predictions and {len(pairs)} "
            "pair divergence rows without loading FX. The available-sample policy "
            f"diagnostic estimable flag is {h1_diagnostic.get('estimable')} and its "
            f"support flag is {h1_diagnostic.get('supported')}.\n\n"
            "All training labels satisfy the six-month availability purge. Model "
            "scalers, penalty selection, constraints, and intercepts are refit using "
            "past rows only. Signal hashes are frozen in `prediction_freeze.json` "
            "and must verify before Phase 04 can open ECB FX data.\n"
        )
        (destination / "REPORT.md").write_text(report, encoding="utf-8", newline="\n")
        write_manifest(destination, phase="03-policy-signal-freeze")
    verify_prediction_freeze(root)
    return summary


def main() -> None:
    print(json.dumps(run_phase03(Path.cwd()), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
