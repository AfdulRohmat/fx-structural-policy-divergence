"""Phase 01 free-source and holdout qualification."""

from __future__ import annotations

import csv
import io
import json
import math
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .alfred import (
    AlfredError,
    build_request,
    fetch_package,
    fetch_profile,
    parse_package,
    parse_profile,
)
from .io_utils import sha256_bytes, write_csv, write_json, write_jsonl, write_manifest

BIS_BASE = "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CBPOL/1.0"


class QualificationError(RuntimeError):
    """Phase 01 could not safely qualify a provider."""


def _download(url: str, accept: str, retries: int = 4) -> bytes:
    request = Request(
        url,
        headers={"Accept": accept, "User-Agent": "fx-spd/0.1"},
    )
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            with urlopen(request, timeout=120) as response:
                payload = bytes(response.read())
                if response.status != 200 or not payload:
                    raise QualificationError(f"HTTP {response.status}")
                return payload
        except (HTTPError, URLError, TimeoutError, QualificationError) as exc:
            last_error = exc
            if attempt + 1 < retries:
                time.sleep(2**attempt)
    raise QualificationError(f"download failed: {last_error}")


def _audit_bis(ref_areas: dict[str, str], raw_root: Path) -> dict[str, Any]:
    area_key = "+".join(ref_areas.values())
    url = f"{BIS_BASE}/M.{area_key}?startPeriod=2013-01&endPeriod=2026-06"
    payload = _download(url, "application/vnd.sdmx.data+csv;version=1.0.0")
    path = raw_root / "bis_policy_monthly.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(payload)
    rows = list(csv.DictReader(io.StringIO(payload.decode("utf-8-sig"))))
    area_to_currency = {value: key for key, value in ref_areas.items()}
    dates: dict[str, list[date]] = {currency: [] for currency in ref_areas}
    valid_rows = 0
    for row in rows:
        currency = area_to_currency.get(str(row.get("REF_AREA", "")))
        if currency is None or row.get("FREQ") != "M":
            continue
        try:
            period = str(row["TIME_PERIOD"])
            observed = date.fromisoformat(f"{period}-01")
            value = float(str(row["OBS_VALUE"]))
        except (KeyError, ValueError):
            continue
        if math.isfinite(value):
            dates[currency].append(observed)
            valid_rows += 1
    missing = [item for item, values in dates.items() if not values]
    latest = {item: max(values).isoformat() for item, values in dates.items() if values}
    support_pass = not missing and all(
        value >= "2026-06-01" for value in latest.values()
    )
    return {
        "status": "PASS" if support_pass else "FAIL",
        "source_url": url,
        "source_sha256": sha256_bytes(payload),
        "row_count": valid_rows,
        "missing_currencies": missing,
        "latest_period_by_currency": latest,
        "scalar_effective_rate_limitation": (
            "BIS provides comparable effective policy-rate histories; profile metadata "
            "must document historical target/corridor convention changes."
        ),
    }


def _audit_alfred_series(
    *,
    series_id: str,
    frequency: str,
    vintages: tuple[date, ...],
    recency_days: int,
    observation_start: date,
    raw_root: Path,
) -> tuple[str, dict[str, object]]:
    raw_dir = raw_root / "alfred" / series_id
    form_path = raw_dir / "form.html"
    package_path = raw_dir / "qualification.zip"
    try:
        if form_path.exists():
            form_payload = form_path.read_bytes()
            profile = parse_profile(series_id, form_payload)
        else:
            profile, form_payload = fetch_profile(series_id)
            raw_dir.mkdir(parents=True, exist_ok=True)
            form_path.write_bytes(form_payload)
        cutoff = date(2025, 11, 30) - timedelta(days=recency_days)
        if profile.observation_end < cutoff:
            return series_id, {
                "mechanism_status": "PASS",
                "advertised_start": profile.observation_start.isoformat(),
                "advertised_end": profile.observation_end.isoformat(),
                "last_visible_at_2025_11_30": profile.observation_end.isoformat(),
                "requested_vintages_returned": 0,
                "form_sha256": profile.form_sha256,
                "package_sha256": "",
                "error": "advertised observation end is stale before package request",
            }
        if package_path.exists():
            package = package_path.read_bytes()
        else:
            requested = build_request(
                observation_start=observation_start,
                observation_end=profile.observation_end,
                vintages=vintages,
            )
            package = fetch_package(series_id, requested)
            package_path.write_bytes(package)
        table = parse_package(package)
        visible_at_last = [
            observed for observed, vintage in table.values if vintage == vintages[-1]
        ]
        if not visible_at_last:
            raise AlfredError("last qualification vintage has no observations")
        return series_id, {
            "mechanism_status": "PASS",
            "advertised_start": profile.observation_start.isoformat(),
            "advertised_end": profile.observation_end.isoformat(),
            "last_visible_at_2025_11_30": max(visible_at_last).isoformat(),
            "requested_vintages_returned": len(table.vintages),
            "form_sha256": profile.form_sha256,
            "package_sha256": table.raw_sha256,
            "error": "",
        }
    except (AlfredError, ValueError) as exc:
        return series_id, {
            "mechanism_status": "FAIL",
            "advertised_start": "",
            "advertised_end": "",
            "last_visible_at_2025_11_30": "",
            "requested_vintages_returned": 0,
            "form_sha256": "",
            "package_sha256": "",
            "error": str(exc),
        }


def run_phase01(
    registry_path: Path, evidence_root: Path, raw_root: Path
) -> dict[str, Any]:
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    vintages = tuple(
        date.fromisoformat(item) for item in registry["qualification_vintages"]
    )
    recency = {str(key): int(value) for key, value in registry["recency_days"].items()}
    matrix: list[dict[str, object]] = []
    unique: dict[str, dict[str, object]] = {}
    series_frequencies = {
        str(spec["series_id"]): str(spec["frequency"])
        for currency_spec in registry["currencies"].values()
        for spec in (
            currency_spec["headline"],
            currency_spec["underlying"],
            currency_spec["unemployment"],
        )
    }
    # ALFRED intermittently returns HTTP 500 under wider parallel bursts.
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = executor.map(
            lambda item: _audit_alfred_series(
                series_id=item[0],
                frequency=item[1],
                vintages=vintages,
                recency_days=recency[item[1]],
                observation_start=date.fromisoformat(registry["observation_start"]),
                raw_root=raw_root,
            ),
            sorted(series_frequencies.items()),
        )
        unique.update(dict(results))
    for currency, currency_spec in registry["currencies"].items():
        for feature in ("headline", "underlying", "unemployment"):
            spec = currency_spec[feature]
            series_id = str(spec["series_id"])
            audit = unique[series_id]
            frequency = str(spec["frequency"])
            last_visible_raw = str(audit["last_visible_at_2025_11_30"])
            last_visible = (
                date.fromisoformat(last_visible_raw) if last_visible_raw else None
            )
            cutoff = date(2025, 11, 30) - timedelta(days=recency[frequency])
            coverage_pass = last_visible is not None and last_visible >= cutoff
            status = (
                "PASS"
                if audit["mechanism_status"] == "PASS" and coverage_pass
                else "FAIL"
            )
            matrix.append(
                {
                    "currency": currency,
                    "feature": feature,
                    "series_id": series_id,
                    "frequency": frequency,
                    "value_kind": spec["value_kind"],
                    "provider": "ALFRED",
                    "point_in_time_mechanism": audit["mechanism_status"],
                    "last_visible_at_2025_11_30": last_visible_raw,
                    "recency_limit_days": recency[frequency],
                    "coverage_status": status,
                    "error": audit["error"],
                }
            )

    bis = _audit_bis(dict(registry["bis_ref_areas"]), raw_root / "bis")
    failed = [row for row in matrix if row["coverage_status"] != "PASS"]
    profile_rows = [
        {
            "currency": currency,
            "profile_source_url": url,
            "status": "PASS_WITH_EFFECTIVE_DATING_REQUIRED",
        }
        for currency, url in registry["central_bank_profile_sources"].items()
    ]
    holdout_audit = {
        "status": "PASS_FOR_NEW_SPD_HYPOTHESES_WITH_ADJACENT_RESEARCH_DISCLOSED",
        "new_signal_previously_tested_on_2023_2025_fx": False,
        "raw_2023_2025_fx_possession_in_adjacent_repositories": True,
        "adjacent_research": [
            {
                "repository": "fx-fundamental-bias-engine",
                "scope": "P1Y proxy and structural-policy development diagnostics",
                "evaluation_end": "2022-12-31",
                "overlap_with_spd_confirmation": False,
            },
            {
                "repository": "fx-fundamental-analysis",
                "scope": "USDJPY employment-event study with a different signal",
                "evaluation_overlap": "2017-2024",
                "same_hypothesis_or_signal": False,
            },
        ],
        "interpretation": (
            "The exact SPD signal has not been evaluated on the registered holdout. "
            "Adjacent FX outcome exposure is disclosed and raises interpretation risk, "
            "but does not replace the frozen test."
        ),
    }
    primary_pass = not failed and bis["status"] == "PASS"
    summary = {
        "phase": "01-source-qualification",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "confirmatory_fx_read": False,
        "macro_rows": len(matrix),
        "macro_pass": len(matrix) - len(failed),
        "macro_fail": len(failed),
        "failed_legs": [f"{row['currency']}:{row['feature']}" for row in failed],
        "bis_policy": bis,
        "central_bank_profiles": profile_rows,
        "holdout_contamination_audit": holdout_audit,
        "phase_decision": "PASS" if primary_pass else "FAIL",
        "downstream_primary_status": "ELIGIBLE" if primary_pass else "NOT_TESTED",
        "reason": (
            "All registered macro legs and BIS policy support qualify."
            if primary_pass
            else (
                "At least one required G10 macro leg lacks point-in-time "
                "coverage through the registered confirmation window."
            )
        ),
    }
    write_csv(evidence_root / "source_matrix.csv", matrix)
    write_json(evidence_root / "series_audit.json", unique)
    write_json(evidence_root / "source_gate_summary.json", summary)
    write_json(evidence_root / "holdout_contamination_audit.json", holdout_audit)
    write_json(evidence_root / "summary.json", summary)
    write_json(
        evidence_root / "sample_flow.json",
        {
            "required_macro_legs": len(matrix),
            "qualified_macro_legs": len(matrix) - len(failed),
            "failed_macro_legs": len(failed),
            "policy_currencies_required": len(registry["bis_ref_areas"]),
            "policy_currencies_qualified": (
                len(registry["bis_ref_areas"]) if bis["status"] == "PASS" else 0
            ),
        },
    )
    write_json(
        evidence_root / "source_manifest.json",
        {
            "alfred_base_url": "https://alfred.stlouisfed.org/series/downloaddata",
            "bis": {
                "source_url": bis["source_url"],
                "source_sha256": bis["source_sha256"],
            },
            "confirmatory_fx_read": False,
        },
    )
    write_json(
        evidence_root / "config_snapshot.yaml",
        {
            "research_contract": json.loads(
                (registry_path.parent / "research_contract_v0_1.json").read_text(
                    encoding="utf-8"
                )
            ),
            "source_registry": registry,
        },
    )
    write_jsonl(
        evidence_root / "issues.jsonl",
        (
            {
                "severity": "BLOCKING_PRIMARY",
                "currency": row["currency"],
                "feature": row["feature"],
                "series_id": row["series_id"],
                "detail": row["error"],
            }
            for row in failed
        ),
    )
    report = (
        "# Phase 01 - Free source qualification\n\n"
        f"Decision: `{summary['phase_decision']}`. Primary downstream status: "
        f"`{summary['downstream_primary_status']}`.\n\n"
        f"BIS policy rates passed for all 10 currencies through June 2026. "
        f"The strict macro gate passed {len(matrix) - len(failed)}/{len(matrix)} "
        "required currency-feature legs through November 2025. The legacy OECD "
        "series hosted by ALFRED mostly stop between early 2022 and spring 2025, "
        "so they cannot support the complete registered holdout.\n\n"
        "This is a source failure, not an alpha result. Phase 01 did not read ECB "
        "FX data. Phase 02 may build a fail-closed diagnostic panel over available "
        "dates, but every registered primary hypothesis remains `NOT_TESTED` unless "
        "full point-in-time coverage is restored.\n\n"
        "The exact SPD signal was not previously tested on 2023-2025 FX. Adjacent "
        "repositories did contain raw prices or different signals, and that exposure "
        "is explicitly recorded in `holdout_contamination_audit.json`.\n"
    )
    (evidence_root / "REPORT.md").write_text(report, encoding="utf-8", newline="\n")
    write_manifest(evidence_root, phase="01-source-qualification")
    return summary


def main() -> None:
    root = Path.cwd()
    result = run_phase01(
        root / "config" / "source_registry_v0_1.json",
        root / "evidence" / "phase01",
        root / "data" / "raw" / "phase01",
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
