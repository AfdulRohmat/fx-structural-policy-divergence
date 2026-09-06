"""Phase 04: verify frozen signals, then open confirmatory ECB FX marks."""

from __future__ import annotations

import csv
import io
import json
import math
import random
import statistics
import time
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .io_utils import (
    sha256_bytes,
    sha256_file,
    write_csv,
    write_json,
    write_jsonl,
    write_manifest,
)
from .phase03_model import MACRO_FEATURES, verify_prediction_freeze
from .time_utils import add_months, month_ends

ECB_URL = (
    "https://data-api.ecb.europa.eu/service/data/EXR/"
    "D.AUD+CAD+CHF+GBP+JPY+NOK+NZD+SEK+USD.EUR.SP00.A?"
    "startPeriod=2022-12-01&endPeriod=2025-12-31&format=csvdata"
)


def _download(url: str, retries: int = 4) -> bytes:
    request = Request(
        url,
        headers={"Accept": "text/csv", "User-Agent": "fx-spd/0.1"},
    )
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            with urlopen(request, timeout=180) as response:
                payload = bytes(response.read())
                if response.status != 200 or not payload:
                    raise ValueError(f"ECB HTTP {response.status}")
                return payload
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            last_error = exc
            if attempt + 1 < retries:
                time.sleep(2**attempt)
    raise RuntimeError(f"ECB download failed: {last_error}")


def parse_ecb_monthly_marks(
    payload: bytes, currencies: tuple[str, ...]
) -> tuple[dict[tuple[date, str], float], dict[date, date]]:
    rows = csv.DictReader(io.StringIO(payload.decode("utf-8-sig"), newline=""))
    required = set(currencies) - {"EUR"}
    daily: dict[date, dict[str, float]] = {}
    for row in rows:
        observed = date.fromisoformat(str(row["TIME_PERIOD"]))
        if observed >= date(2026, 1, 1):
            raise ValueError("ECB payload reaches sealed 2026 FX outcomes")
        currency = str(row["CURRENCY"])
        if currency not in required:
            raise ValueError(f"unexpected ECB currency: {currency}")
        if row["CURRENCY_DENOM"] != "EUR":
            raise ValueError("ECB source is not currency units per EUR")
        value = float(str(row["OBS_VALUE"]))
        if not math.isfinite(value) or value <= 0:
            raise ValueError("ECB mark must be finite and positive")
        if currency in daily.setdefault(observed, {}):
            raise ValueError(f"duplicate ECB observation: {observed}/{currency}")
        daily[observed][currency] = value
    common = sorted(day for day, values in daily.items() if set(values) == required)
    marks: dict[tuple[date, str], float] = {}
    source_dates: dict[date, date] = {}
    for snapshot in month_ends(date(2022, 12, 1), date(2025, 12, 31)):
        candidates = [
            day
            for day in common
            if day.year == snapshot.year and day.month == snapshot.month
        ]
        if not candidates:
            continue
        source_date = max(candidates)
        source_dates[snapshot] = source_date
        marks[(snapshot, "EUR")] = 1.0
        for currency, value in daily[source_date].items():
            marks[(snapshot, currency)] = value
    return marks, source_dates


def _currency_returns(
    marks: dict[tuple[date, str], float],
    currencies: tuple[str, ...],
    horizon: int,
) -> dict[tuple[date, str], float]:
    output: dict[tuple[date, str], float] = {}
    for origin in month_ends(date(2023, 1, 1), date(2025, 11, 30)):
        destination = add_months(origin, horizon)
        if not all(
            (origin, currency) in marks and (destination, currency) in marks
            for currency in currencies
        ):
            continue
        versus_eur = {
            currency: -100.0
            * math.log(marks[(destination, currency)] / marks[(origin, currency)])
            for currency in currencies
        }
        center = statistics.mean(versus_eur.values())
        for currency, value in versus_eur.items():
            output[(origin, currency)] = value - center
    return output


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _average_ranks(values: dict[str, float]) -> dict[str, float]:
    ordered = sorted(values.items(), key=lambda item: item[1])
    output: dict[str, float] = {}
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and ordered[end][1] == ordered[index][1]:
            end += 1
        rank = (index + 1 + end) / 2.0
        for currency, _ in ordered[index:end]:
            output[currency] = rank
        index = end
    return output


def _correlation(left: list[float], right: list[float]) -> float:
    left_mean = statistics.mean(left)
    right_mean = statistics.mean(right)
    numerator = sum(
        (x - left_mean) * (y - right_mean) for x, y in zip(left, right, strict=True)
    )
    denominator = math.sqrt(
        sum((item - left_mean) ** 2 for item in left)
        * sum((item - right_mean) ** 2 for item in right)
    )
    return 0.0 if denominator == 0 else numerator / denominator


def _slope(rows: list[dict[str, Any]], x_name: str, y_name: str) -> float:
    if not rows:
        return 0.0
    x = [float(row[x_name]) for row in rows]
    y = [float(row[y_name]) for row in rows]
    x_mean = statistics.mean(x)
    y_mean = statistics.mean(y)
    denominator = sum((item - x_mean) ** 2 for item in x)
    if denominator == 0:
        return 0.0
    return (
        sum(
            (left - x_mean) * (right - y_mean) for left, right in zip(x, y, strict=True)
        )
        / denominator
    )


def _quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = probability * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _cluster_bootstrap(
    rows: list[dict[str, Any]],
    statistic: Callable[[list[dict[str, Any]]], float],
    *,
    block_length: int,
    resamples: int,
    seed: int,
) -> tuple[float, float]:
    by_month: dict[date, list[dict[str, Any]]] = {}
    for row in rows:
        by_month.setdefault(row["snapshot_date"], []).append(row)
    months = sorted(by_month)
    if not months:
        raise ValueError("cannot bootstrap empty rows")
    generator = random.Random(seed)
    estimates: list[float] = []
    for _ in range(resamples):
        sampled_months: list[date] = []
        while len(sampled_months) < len(months):
            start = generator.randrange(len(months))
            sampled_months.extend(
                months[(start + offset) % len(months)] for offset in range(block_length)
            )
        sample = [
            row for month in sampled_months[: len(months)] for row in by_month[month]
        ]
        estimates.append(statistic(sample))
    return _quantile(estimates, 0.025), _quantile(estimates, 0.975)


def _pair_outcomes(
    signal_rows: list[dict[str, str]],
    returns: dict[tuple[date, str], float],
    *,
    require_agreement: bool,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in signal_rows:
        if require_agreement and row["primary_eligible"] != "True":
            continue
        snapshot = date.fromisoformat(row["snapshot"])
        base = row["base"]
        quote = row["quote"]
        if (snapshot, base) not in returns or (snapshot, quote) not in returns:
            continue
        output.append(
            {
                **row,
                "snapshot_date": snapshot,
                "next_return_percent": returns[(snapshot, base)]
                - returns[(snapshot, quote)],
            }
        )
    return output


def _rank_months(
    rank_rows: list[dict[str, str]],
    returns: dict[tuple[date, str], float],
    excluded: frozenset[str] = frozenset(),
) -> list[dict[str, Any]]:
    by_month: dict[date, dict[str, float]] = {}
    for row in rank_rows:
        currency = row["currency"]
        if currency in excluded:
            continue
        snapshot = date.fromisoformat(row["snapshot"])
        if (snapshot, currency) in returns:
            by_month.setdefault(snapshot, {})[currency] = float(row["revision_1m_bp"])
    output: list[dict[str, Any]] = []
    for snapshot, revisions in sorted(by_month.items()):
        if len(revisions) < 4:
            continue
        ordered = sorted(revisions, key=lambda item: (revisions[item], item))
        if (
            revisions[ordered[1]] == revisions[ordered[2]]
            or revisions[ordered[-2]] == revisions[ordered[-3]]
        ):
            continue
        revision_ranks = _average_ranks(revisions)
        outcome_values = {
            currency: returns[(snapshot, currency)] for currency in revisions
        }
        outcome_ranks = _average_ranks(outcome_values)
        currencies = sorted(revisions)
        rank_ic = _correlation(
            [revision_ranks[item] for item in currencies],
            [outcome_ranks[item] for item in currencies],
        )
        bottom = ordered[:2]
        top = ordered[-2:]
        spread = statistics.mean(
            outcome_values[item] for item in top
        ) - statistics.mean(outcome_values[item] for item in bottom)
        output.append(
            {
                "snapshot": snapshot.isoformat(),
                "snapshot_date": snapshot,
                "universe_size": len(revisions),
                "rank_ic": rank_ic,
                "extreme_spread_percent": spread,
                "top_two": "+".join(sorted(top)),
                "bottom_two": "+".join(sorted(bottom)),
            }
        )
    return output


def validate_pair_signal_uniqueness(rows: list[dict[str, str]]) -> None:
    seen: set[tuple[str, frozenset[str]]] = set()
    for row in rows:
        key = (row["snapshot"], frozenset((row["base"], row["quote"])))
        if key in seen:
            raise ValueError(f"duplicate or inverse pair signal: {key}")
        seen.add(key)


def _mean_statistic(name: str) -> Callable[[list[dict[str, Any]]], float]:
    return lambda rows: statistics.mean(float(row[name]) for row in rows)


def _evaluate_primary_diagnostics(
    pair_rows: list[dict[str, Any]],
    monthly: list[dict[str, Any]],
    contract: dict[str, Any],
) -> dict[str, Any]:
    bootstrap = contract["bootstrap"]
    h2_slope = _slope(pair_rows, "revision_divergence_bp", "next_return_percent")
    h2_ci = _cluster_bootstrap(
        pair_rows,
        lambda rows: _slope(rows, "revision_divergence_bp", "next_return_percent"),
        block_length=int(bootstrap["block_length_months"]),
        resamples=int(bootstrap["resamples"]),
        seed=int(bootstrap["seed"]) + 100,
    )
    ic = statistics.mean(float(row["rank_ic"]) for row in monthly)
    ic_ci = _cluster_bootstrap(
        monthly,
        _mean_statistic("rank_ic"),
        block_length=int(bootstrap["block_length_months"]),
        resamples=int(bootstrap["resamples"]),
        seed=int(bootstrap["seed"]) + 200,
    )
    spread = statistics.mean(float(row["extreme_spread_percent"]) for row in monthly)
    spread_ci = _cluster_bootstrap(
        monthly,
        _mean_statistic("extreme_spread_percent"),
        block_length=int(bootstrap["block_length_months"]),
        resamples=int(bootstrap["resamples"]),
        seed=int(bootstrap["seed"]) + 300,
    )
    return {
        "H2_pair_revision": {
            "row_count": len(pair_rows),
            "month_count": len({row["snapshot"] for row in pair_rows}),
            "slope_percent_per_bp": h2_slope,
            "slope_95_ci": [*h2_ci],
            "diagnostic_supported": h2_slope > 0 and h2_ci[0] > 0,
        },
        "H3_rank_ic": {
            "month_count": len(monthly),
            "mean_spearman": ic,
            "mean_95_ci": [*ic_ci],
            "diagnostic_supported": ic > 0 and ic_ci[0] > 0,
        },
        "H4_extreme_spread": {
            "month_count": len(monthly),
            "mean_percent": spread,
            "mean_bp": spread * 100.0,
            "mean_95_ci_percent": [*spread_ci],
            "diagnostic_supported": spread > 0 and spread_ci[0] > 0,
        },
    }


def _stability(
    signal_rows: list[dict[str, str]],
    rank_rows: list[dict[str, str]],
    returns: dict[tuple[date, str], float],
    currencies: tuple[str, ...],
) -> dict[str, Any]:
    all_pairs = _pair_outcomes(signal_rows, returns, require_agreement=True)
    by_year: dict[str, dict[str, float | int]] = {}
    for year in (2023, 2024, 2025):
        pairs = [row for row in all_pairs if row["snapshot_date"].year == year]
        monthly = [
            row
            for row in _rank_months(rank_rows, returns)
            if row["snapshot_date"].year == year
        ]
        by_year[str(year)] = {
            "pair_slope": _slope(
                pairs, "revision_divergence_bp", "next_return_percent"
            ),
            "rank_ic": statistics.mean(float(row["rank_ic"]) for row in monthly)
            if monthly
            else 0.0,
            "spread_percent": (
                statistics.mean(float(row["extreme_spread_percent"]) for row in monthly)
                if monthly
                else 0.0
            ),
            "month_count": len(monthly),
        }
    leave_one_out: dict[str, dict[str, float | int]] = {}
    for currency in currencies:
        pairs = [
            row
            for row in all_pairs
            if row["base"] != currency and row["quote"] != currency
        ]
        monthly = _rank_months(rank_rows, returns, frozenset({currency}))
        leave_one_out[currency] = {
            "pair_slope": _slope(
                pairs, "revision_divergence_bp", "next_return_percent"
            ),
            "rank_ic": statistics.mean(float(row["rank_ic"]) for row in monthly)
            if monthly
            else 0.0,
            "spread_percent": (
                statistics.mean(float(row["extreme_spread_percent"]) for row in monthly)
                if monthly
                else 0.0
            ),
            "month_count": len(monthly),
        }
    stable = all(
        float(group[name]) > 0
        for group in (*by_year.values(), *leave_one_out.values())
        for name in ("pair_slope", "rank_ic", "spread_percent")
    )
    return {
        "by_year": by_year,
        "leave_one_currency_out": leave_one_out,
        "all_expected_signs_stable": stable,
    }


def _baseline_diagnostics(
    signal_rows: list[dict[str, str]],
    panel_path: Path,
    rank_rows: list[dict[str, str]],
    returns: dict[tuple[date, str], float],
) -> dict[str, Any]:
    all_pairs = _pair_outcomes(signal_rows, returns, require_agreement=False)
    eligible_pairs = _pair_outcomes(signal_rows, returns, require_agreement=True)
    panel_rows = _read_rows(panel_path)
    composites: list[dict[str, str]] = []
    for row in panel_rows:
        if row["sample"] != "CONFIRMATION" or any(
            row[name] == "" for name in MACRO_FEATURES
        ):
            continue
        composites.append(
            {
                "snapshot": row["snapshot"],
                "currency": row["currency"],
                "revision_1m_bp": str(
                    statistics.mean(float(row[name]) for name in MACRO_FEATURES)
                ),
            }
        )
    video_monthly = _rank_months(composites, returns)
    return {
        "level_divergence_all_pairs": {
            "slope_percent_per_bp": _slope(
                all_pairs, "level_divergence_bp", "next_return_percent"
            ),
            "row_count": len(all_pairs),
        },
        "revision_without_level_filter": {
            "slope_percent_per_bp": _slope(
                all_pairs, "revision_divergence_bp", "next_return_percent"
            ),
            "row_count": len(all_pairs),
        },
        "revision_with_level_filter": {
            "slope_percent_per_bp": _slope(
                eligible_pairs, "revision_divergence_bp", "next_return_percent"
            ),
            "row_count": len(eligible_pairs),
        },
        "video_equal_macro_composite": {
            "month_count": len(video_monthly),
            "mean_rank_ic": (
                statistics.mean(float(row["rank_ic"]) for row in video_monthly)
                if video_monthly
                else None
            ),
            "mean_extreme_spread_percent": (
                statistics.mean(
                    float(row["extreme_spread_percent"]) for row in video_monthly
                )
                if video_monthly
                else None
            ),
        },
    }


def run_phase04(root: Path) -> dict[str, Any]:
    # This verification must complete before the first FX read or download.
    freeze_verification = verify_prediction_freeze(root)
    contract = json.loads(
        (root / "config" / "research_contract_v0_1.json").read_text(encoding="utf-8")
    )
    currencies = tuple(contract["currency_universe"])
    raw_path = root / "data" / "raw" / "phase04" / "ecb_fx_2022_2025.csv"
    if raw_path.exists():
        payload = raw_path.read_bytes()
    else:
        payload = _download(ECB_URL)
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_bytes(payload)
    marks, source_dates = parse_ecb_monthly_marks(payload, currencies)
    returns_1m = _currency_returns(marks, currencies, 1)
    signal_path = root / "evidence" / "phase03" / "pair_signals.csv"
    rank_path = root / "evidence" / "phase03" / "currency_ranks.csv"
    signal_rows = _read_rows(signal_path)
    validate_pair_signal_uniqueness(signal_rows)
    rank_rows = _read_rows(rank_path)
    pair_rows = _pair_outcomes(signal_rows, returns_1m, require_agreement=True)
    monthly = _rank_months(rank_rows, returns_1m)
    diagnostics = _evaluate_primary_diagnostics(pair_rows, monthly, contract)
    stability = _stability(signal_rows, rank_rows, returns_1m, currencies)
    panel_path = root / "artifacts" / "phase02" / "panel.csv"
    if sha256_file(panel_path) != freeze_verification["freeze"]["panel_input_sha256"]:
        raise ValueError("Phase 02 panel hash changed after Phase 03 freeze")
    baselines = _baseline_diagnostics(signal_rows, panel_path, rank_rows, returns_1m)
    secondary: dict[str, object] = {}
    for horizon in (3, 6):
        returns = _currency_returns(marks, currencies, horizon)
        rows = _pair_outcomes(signal_rows, returns, require_agreement=True)
        months = sorted({row["snapshot_date"] for row in rows})
        allowed = {month for index, month in enumerate(months) if index % horizon == 0}
        purged = [row for row in rows if row["snapshot_date"] in allowed]
        secondary[f"{horizon}m"] = {
            "method": "fixed-calendar non-overlapping origin purge",
            "row_count": len(purged),
            "month_count": len({row["snapshot"] for row in purged}),
            "slope_percent_per_bp": _slope(
                purged, "revision_divergence_bp", "next_return_percent"
            ),
        }
    source_gate = json.loads(
        (root / "evidence" / "phase01" / "source_gate_summary.json").read_text(
            encoding="utf-8"
        )
    )
    summary = {
        "phase": "04-fx-evaluation",
        "status": "DIAGNOSTIC_COMPLETE_REGISTERED_NOT_TESTED",
        "SPD_H2_PAIR_REVISION": "NOT_TESTED",
        "SPD_H3_RANK_IC": "NOT_TESTED",
        "SPD_H4_EXTREME_SPREAD": "NOT_TESTED",
        "SPD_H5_STABILITY": "NOT_TESTED",
        "available_sample_diagnostics": diagnostics,
        "available_sample_stability": stability,
        "baselines": baselines,
        "secondary_horizons": secondary,
        "source_gate": source_gate["phase_decision"],
        "freeze_verification": freeze_verification,
        "fx_marks_non_executable": True,
        "profitability_claim": False,
        "sealed_2026_fx_accessed": False,
    }
    artifact = root / "artifacts" / "phase04"
    evidence = root / "evidence" / "phase04"
    artifact.mkdir(parents=True, exist_ok=True)
    for destination in (artifact, evidence):
        write_csv(destination / "pair_outcomes.csv", pair_rows)
        write_csv(destination / "monthly_rank_outcomes.csv", monthly)
        write_json(destination / "summary.json", summary)
        write_json(
            destination / "sample_flow.json",
            {
                "ecb_monthly_common_marks": len(source_dates),
                "pair_rows": len(pair_rows),
                "distinct_pair_months": len({row["snapshot"] for row in pair_rows}),
                "rank_months": len(monthly),
            },
        )
        write_json(
            destination / "source_manifest.json",
            {
                "ecb_source_url": ECB_URL,
                "ecb_raw_sha256": sha256_bytes(payload),
                "phase03_signal_sha256": sha256_file(signal_path),
                "phase03_rank_sha256": sha256_file(rank_path),
                "research_marks_only": True,
                "sealed_2026_fx_accessed": False,
            },
        )
        write_json(destination / "config_snapshot.yaml", contract)
        write_jsonl(
            destination / "issues.jsonl",
            [
                {
                    "severity": "BLOCKING_PRIMARY",
                    "code": "SOURCE_GATE_FAILED",
                    "effect": (
                        "H2-H5 remain NOT_TESTED despite available-sample diagnostics."
                    ),
                }
            ],
        )
        h2 = diagnostics["H2_pair_revision"]
        h3 = diagnostics["H3_rank_ic"]
        h4 = diagnostics["H4_extreme_spread"]
        report = (
            "# Phase 04 - Frozen FX evaluation\n\n"
            "Registered H2-H5: `NOT_TESTED` because full-G10 source provenance "
            "failed before outcomes were opened.\n\n"
            f"Available-sample H2 slope: {h2['slope_percent_per_bp']:.6f}% per bp "
            f"with 95% CI {h2['slope_95_ci']}. Mean rank IC: "
            f"{h3['mean_spearman']:.3f} with 95% CI {h3['mean_95_ci']}. "
            f"Top-two minus bottom-two mean: {h4['mean_bp']:.1f} bp with "
            f"95% CI in percent {h4['mean_95_ci_percent']}.\n\n"
            "ECB rates are synchronized month-end reference marks, not executable "
            "quotes. No transaction costs, position sizing, or PnL claim is made. "
            "No 2026 FX outcome was requested or parsed.\n"
        )
        (destination / "REPORT.md").write_text(report, encoding="utf-8", newline="\n")
        write_manifest(destination, phase="04-fx-evaluation")
    return summary


def main() -> None:
    print(json.dumps(run_phase04(Path.cwd()), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
