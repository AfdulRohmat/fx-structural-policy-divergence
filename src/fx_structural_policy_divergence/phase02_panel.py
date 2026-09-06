"""Build the point-in-time macro/policy panel without any FX input."""

from __future__ import annotations

import csv
import json
import shutil
import statistics
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .alfred import (
    AlfredError,
    VintageTable,
    build_request,
    fetch_package,
    fetch_profile,
    parse_package,
    parse_profile,
    save_package,
)
from .io_utils import (
    sha256_file,
    write_csv,
    write_json,
    write_jsonl,
    write_manifest,
)
from .time_utils import add_months, month_end, month_ends

FEATURES = (
    "inflation_gap",
    "inflation_momentum",
    "labour_tightness",
    "labour_momentum",
)


def _chunks(values: tuple[date, ...], size: int = 30) -> tuple[tuple[date, ...], ...]:
    """Chunk dates without mixing non-contiguous vintage ranges."""
    groups: list[list[date]] = []
    for value in values:
        if not groups or add_months(groups[-1][-1], 1) != value:
            groups.append([value])
        else:
            groups[-1].append(value)
    return tuple(
        tuple(group[index : index + size])
        for group in groups
        for index in range(0, len(group), size)
    )


def _seed_public_cache(source: Path, target: Path) -> int:
    if not source.is_dir():
        return 0
    copied = 0
    for path in source.rglob("*"):
        if not path.is_file() or path.suffix not in {".zip", ".json"}:
            continue
        relative = path.relative_to(source)
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            continue
        shutil.copy2(path, destination)
        copied += 1
    return copied


def _load_tables(directory: Path) -> tuple[VintageTable, ...]:
    return tuple(
        parse_package(path.read_bytes()) for path in sorted(directory.glob("*.zip"))
    )


def _merge_tables(tables: tuple[VintageTable, ...]) -> VintageTable:
    if not tables:
        raise AlfredError("no ALFRED packages available")
    series_ids = {table.series_id for table in tables}
    if len(series_ids) != 1:
        raise AlfredError("cannot merge different ALFRED series")
    values: dict[tuple[date, date], float] = {}
    vintages: set[date] = set()
    hashes: list[str] = []
    for table in tables:
        hashes.append(table.raw_sha256)
        vintages.update(table.vintages)
        for key, value in table.values.items():
            if key in values and values[key] != value:
                raise AlfredError(f"conflicting ALFRED value: {key}")
            values[key] = value
    return VintageTable(
        series_id=next(iter(series_ids)),
        vintages=tuple(sorted(vintages)),
        values=values,
        raw_sha256="+".join(sorted(hashes)),
    )


def _ensure_series(
    series_id: str,
    desired_vintages: tuple[date, ...],
    raw_root: Path,
    phase01_root: Path,
    attempt_fetch: bool,
) -> dict[str, object]:
    directory = raw_root / series_id
    existing = _load_tables(directory) if directory.exists() else ()
    have = {vintage for table in existing for vintage in table.vintages}
    missing = tuple(item for item in desired_vintages if item not in have)
    fetched = 0
    errors: list[str] = []
    if missing and attempt_fetch:
        form_path = phase01_root / series_id / "form.html"
        try:
            if form_path.exists():
                profile = parse_profile(series_id, form_path.read_bytes())
            else:
                profile, _ = fetch_profile(series_id)
            for chunk in _chunks(missing):
                request = build_request(
                    observation_start=date(2000, 1, 1),
                    observation_end=profile.observation_end,
                    vintages=chunk,
                )
                try:
                    payload = fetch_package(series_id, request)
                    save_package(directory.parent, series_id, chunk, payload)
                    fetched += 1
                except AlfredError as exc:
                    errors.append(f"{chunk[0]}/{chunk[-1]}: {exc}")
        except AlfredError as exc:
            errors.append(str(exc))
    tables = _load_tables(directory) if directory.exists() else ()
    if not tables:
        return {
            "series_id": series_id,
            "status": "FAIL",
            "package_count": 0,
            "vintage_count": 0,
            "fetched_packages": fetched,
            "errors": errors,
        }
    merged = _merge_tables(tables)
    missing_after = sorted(set(desired_vintages) - set(merged.vintages))
    return {
        "series_id": series_id,
        "status": "PASS" if not errors and not missing_after else "PARTIAL",
        "package_count": len(tables),
        "vintage_count": len(merged.vintages),
        "first_vintage": min(merged.vintages).isoformat(),
        "last_vintage": max(merged.vintages).isoformat(),
        "fetched_packages": fetched,
        "missing_vintage_count": len(missing_after),
        "errors": errors,
    }


def _policy_table(
    path: Path, area_map: dict[str, str]
) -> dict[tuple[str, date], float]:
    reverse = {area: currency for currency, area in area_map.items()}
    output: dict[tuple[str, date], float] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            currency = reverse.get(str(row.get("REF_AREA", "")))
            if currency is None or row.get("FREQ") != "M":
                continue
            raw_period = str(row["TIME_PERIOD"])
            period = date.fromisoformat(f"{raw_period}-01")
            key = (currency, month_end(period.year, period.month))
            value = float(str(row["OBS_VALUE"]))
            if key in output and output[key] != value:
                raise ValueError(f"conflicting BIS policy value: {key}")
            output[key] = value
    return output


def _observations(table: VintageTable, snapshot: date) -> list[tuple[date, float]]:
    eligible_vintages = [item for item in table.vintages if item <= snapshot]
    if not eligible_vintages:
        return []
    vintage = max(eligible_vintages)
    return sorted(
        (observed, value)
        for (observed, item_vintage), value in table.values.items()
        if item_vintage == vintage and observed <= snapshot
    )


def _yoy(
    observations: list[tuple[date, float]], value_kind: str
) -> list[tuple[date, float]]:
    if value_kind == "yoy_percent":
        return observations
    levels = {item: value for item, value in observations}
    output: list[tuple[date, float]] = []
    for observed, value in observations:
        prior_month = add_months(observed, -12)
        prior = levels.get(date(prior_month.year, prior_month.month, 1))
        if prior is not None and prior > 0:
            output.append((observed, 100.0 * (value / prior - 1.0)))
    return output


def _zscore(
    sequence: list[tuple[date, float]], index: int, minimum: int
) -> float | None:
    history = [value for _, value in sequence[:index]]
    if len(history) < minimum:
        return None
    deviation = statistics.stdev(history)
    if deviation == 0:
        return None
    return (sequence[index][1] - statistics.mean(history)) / deviation


def _latest(
    sequence: list[tuple[date, float]],
    snapshot: date,
    recency_days: int,
    minimum: int,
) -> tuple[float | None, float | None, date | None]:
    eligible = [index for index, item in enumerate(sequence) if item[0] <= snapshot]
    if not eligible:
        return None, None, None
    index = eligible[-1]
    observed, raw = sequence[index]
    if observed < snapshot - timedelta(days=recency_days):
        return None, None, observed
    return raw, _zscore(sequence, index, minimum), observed


def _target_midpoint(currency: str, snapshot: date, default: float) -> float:
    if currency == "NOK" and snapshot < date(2018, 3, 2):
        return 2.5
    return default


def _feature_sequences(
    *,
    snapshot: date,
    currency: str,
    currency_spec: dict[str, Any],
    tables: dict[str, VintageTable],
) -> dict[str, list[tuple[date, float]]]:
    headline_spec = currency_spec["headline"]
    underlying_spec = currency_spec["underlying"]
    labour_spec = currency_spec["unemployment"]
    headline = _yoy(
        _observations(tables[headline_spec["series_id"]], snapshot),
        headline_spec["value_kind"],
    )
    underlying = _yoy(
        _observations(tables[underlying_spec["series_id"]], snapshot),
        underlying_spec["value_kind"],
    )
    labour = _observations(tables[labour_spec["series_id"]], snapshot)
    midpoint = _target_midpoint(
        currency, snapshot, float(currency_spec["target_midpoint"])
    )
    inflation_gap = [(item, value - midpoint) for item, value in headline]
    underlying_by_date = {item: value for item, value in underlying}
    inflation_momentum: list[tuple[date, float]] = []
    for item, value in underlying:
        previous = add_months(item, -3)
        previous_value = underlying_by_date.get(date(previous.year, previous.month, 1))
        if previous_value is not None:
            inflation_momentum.append((item, value - previous_value))
    labour_tightness = [(item, -value) for item, value in labour]
    labour_momentum = [
        (item, -(value - labour[index - 3][1]))
        for index, (item, value) in enumerate(labour)
        if index >= 3
    ]
    return {
        "inflation_gap": inflation_gap,
        "inflation_momentum": inflation_momentum,
        "labour_tightness": labour_tightness,
        "labour_momentum": labour_momentum,
    }


def _build_row(
    *,
    snapshot: date,
    currency: str,
    spec: dict[str, Any],
    tables: dict[str, VintageTable],
    policies: dict[tuple[str, date], float],
    recency: dict[str, int],
    minimum: int,
) -> dict[str, object]:
    sequences = _feature_sequences(
        snapshot=snapshot, currency=currency, currency_spec=spec, tables=tables
    )
    frequency = {
        "inflation_gap": spec["headline"]["frequency"],
        "inflation_momentum": spec["underlying"]["frequency"],
        "labour_tightness": spec["unemployment"]["frequency"],
        "labour_momentum": spec["unemployment"]["frequency"],
    }
    row: dict[str, object] = {
        "snapshot": snapshot.isoformat(),
        "currency": currency,
        "country": spec["country"],
        "macro_vintage_cutoff": snapshot.isoformat(),
    }
    for feature in FEATURES:
        raw, zscore, reference = _latest(
            sequences[feature],
            snapshot,
            recency[str(frequency[feature])],
            minimum,
        )
        row[f"{feature}_raw"] = raw
        row[f"{feature}_z"] = zscore
        row[f"{feature}_reference_period"] = (
            "" if reference is None else reference.isoformat()
        )
    policy = policies.get((currency, snapshot))
    policy_prior = policies.get((currency, add_months(snapshot, -3)))
    policy_future = policies.get((currency, add_months(snapshot, 6)))
    row["policy_rate_percent"] = policy
    row["policy_change_3m_bp"] = (
        None
        if policy is None or policy_prior is None
        else 100.0 * (policy - policy_prior)
    )
    row["policy_change_6m_bp"] = (
        None
        if policy is None or policy_future is None
        else 100.0 * (policy_future - policy)
    )
    row["label_available_at"] = add_months(snapshot, 6).isoformat()
    row["macro_complete"] = all(row[f"{item}_z"] is not None for item in FEATURES)
    row["policy_complete"] = all(
        row[item] is not None
        for item in (
            "policy_rate_percent",
            "policy_change_3m_bp",
            "policy_change_6m_bp",
        )
    )
    row["panel_complete"] = bool(row["macro_complete"] and row["policy_complete"])
    row["sample"] = "DEVELOPMENT" if snapshot <= date(2022, 12, 31) else "CONFIRMATION"
    return row


def run_phase02(root: Path) -> dict[str, Any]:
    registry = json.loads(
        (root / "config" / "source_registry_v0_1.json").read_text(encoding="utf-8")
    )
    contract = json.loads(
        (root / "config" / "research_contract_v0_1.json").read_text(encoding="utf-8")
    )
    raw_root = root / "data" / "raw" / "phase02"
    alfred_root = raw_root / "alfred"
    seed_root = (
        root.parent
        / "fx-fundamental-bias-engine"
        / "data"
        / "raw"
        / "phase02"
        / "alfred"
    )
    seeded_files = _seed_public_cache(seed_root, alfred_root)
    desired_vintages = month_ends(date(2013, 1, 1), date(2025, 4, 30))
    series_ids = sorted(
        {
            str(spec[feature]["series_id"])
            for spec in registry["currencies"].values()
            for feature in ("headline", "underlying", "unemployment")
        }
    )
    attempt_fetch = not (
        root / "artifacts" / "phase02" / "source_manifest.json"
    ).exists()
    with ThreadPoolExecutor(max_workers=2) as executor:
        fetch_audit = list(
            executor.map(
                lambda series_id: _ensure_series(
                    series_id,
                    desired_vintages,
                    alfred_root,
                    root / "data" / "raw" / "phase01" / "alfred",
                    attempt_fetch,
                ),
                series_ids,
            )
        )
    tables: dict[str, VintageTable] = {}
    for series_id in series_ids:
        packages = _load_tables(alfred_root / series_id)
        if packages:
            tables[series_id] = _merge_tables(packages)
    missing_series = [item for item in series_ids if item not in tables]
    if missing_series:
        raise RuntimeError(f"no source packages for: {missing_series}")
    bis_source = root / "data" / "raw" / "phase01" / "bis" / "bis_policy_monthly.csv"
    policies = _policy_table(bis_source, dict(registry["bis_ref_areas"]))
    snapshots = month_ends(
        date.fromisoformat(contract["development_start"]),
        date.fromisoformat(contract["confirmation_end"]),
    )
    rows = [
        _build_row(
            snapshot=snapshot,
            currency=currency,
            spec=spec,
            tables=tables,
            policies=policies,
            recency={
                str(key): int(value) for key, value in registry["recency_days"].items()
            },
            minimum=int(contract["minimum_zscore_observations"]),
        )
        for snapshot in snapshots
        for currency, spec in registry["currencies"].items()
    ]
    artifact = root / "artifacts" / "phase02"
    evidence = root / "evidence" / "phase02"
    artifact.mkdir(parents=True, exist_ok=True)
    write_csv(artifact / "panel.csv", rows)
    confirmation = [row for row in rows if row["sample"] == "CONFIRMATION"]
    by_currency: dict[str, dict[str, Any]] = {}
    for currency in registry["currencies"]:
        selected = [row for row in confirmation if row["currency"] == currency]
        complete_dates = [
            str(row["snapshot"]) for row in selected if row["panel_complete"]
        ]
        by_currency[currency] = {
            "confirmation_rows": len(selected),
            "complete_rows": len(complete_dates),
            "first_complete": min(complete_dates) if complete_dates else None,
            "last_complete": max(complete_dates) if complete_dates else None,
        }
    complete_confirmation = sum(bool(row["panel_complete"]) for row in confirmation)
    full_g10_months = sum(
        all(
            row["panel_complete"]
            for row in confirmation
            if row["snapshot"] == snapshot.isoformat()
        )
        for snapshot in month_ends(date(2023, 1, 1), date(2025, 11, 30))
    )
    source_gate = json.loads(
        (root / "evidence" / "phase01" / "source_gate_summary.json").read_text(
            encoding="utf-8"
        )
    )
    summary = {
        "phase": "02-canonical-panel",
        "status": "NOT_TESTED_PRIMARY_DIAGNOSTIC_PANEL_BUILT",
        "source_gate": source_gate["phase_decision"],
        "primary_eligible": False,
        "row_count": len(rows),
        "complete_row_count": sum(bool(row["panel_complete"]) for row in rows),
        "confirmation_row_count": len(confirmation),
        "confirmation_complete_row_count": complete_confirmation,
        "full_g10_confirmation_months": full_g10_months,
        "coverage_by_currency": by_currency,
        "series_fetch_status_counts": dict(
            Counter(str(item["status"]) for item in fetch_audit)
        ),
        "fx_outcomes_accessed": False,
        "sealed_2026_fx_accessed": False,
        "diagnostic_scope": (
            "Only complete currency-months may enter diagnostics. Missing or stale "
            "macro observations are never imputed."
        ),
    }
    source_manifest = {
        "seeded_public_raw_files": seeded_files,
        "seed_source": str(seed_root),
        "seed_contents": (
            "ALFRED raw packages and metadata only; no model or FX artifacts"
        ),
        "bis_sha256": sha256_file(bis_source),
        "series_fetch_audit": fetch_audit,
        "fx_outcomes_accessed": False,
    }
    for destination in (artifact, evidence):
        write_json(destination / "summary.json", summary)
        write_json(destination / "sample_flow.json", summary)
        write_json(destination / "source_manifest.json", source_manifest)
        write_json(
            destination / "config_snapshot.yaml",
            {
                "contract": contract,
                "registry": registry,
                "amendment": json.loads(
                    (root / "config" / "amendment_v0_1_1.json").read_text(
                        encoding="utf-8"
                    )
                ),
            },
        )
        write_jsonl(
            destination / "issues.jsonl",
            (
                {
                    "severity": "BLOCKING_PRIMARY",
                    "currency": currency,
                    "complete_rows": item["complete_rows"],
                    "last_complete": item["last_complete"],
                }
                for currency, item in by_currency.items()
                if int(item["complete_rows"]) < len(confirmation)
            ),
        )
        report = (
            "# Phase 02 - Canonical macro-policy panel\n\n"
            f"Status: `{summary['status']}`.\n\n"
            f"Built {len(rows)} currency-month rows. The confirmation slice has "
            f"{complete_confirmation}/{len(confirmation)} complete rows and "
            f"{full_g10_months} months with all ten currencies complete.\n\n"
            "Each row uses the latest ALFRED vintage no later than the month-end "
            "snapshot. Expanding z-scores exclude the current observation. Stale "
            "features fail closed and are never carried or imputed. BIS six-month "
            "labels are purged until their horizon has elapsed.\n\n"
            "Because Phase 01 failed full-window source coverage, this artifact is "
            "diagnostic only. No FX outcome was read.\n"
        )
        (destination / "REPORT.md").write_text(report, encoding="utf-8", newline="\n")
        write_manifest(destination, phase="02-canonical-panel")
    write_csv(
        evidence / "coverage_by_currency.csv",
        [{"currency": currency, **values} for currency, values in by_currency.items()],
    )
    write_manifest(evidence, phase="02-canonical-panel")
    return summary


def main() -> None:
    print(json.dumps(run_phase02(Path.cwd()), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
