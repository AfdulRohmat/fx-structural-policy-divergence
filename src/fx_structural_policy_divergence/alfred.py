"""Credential-free ALFRED point-in-time packages."""

from __future__ import annotations

import csv
import io
import json
import math
import re
import time
import zipfile
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from .io_utils import sha256_bytes

ALFRED_BASE = "https://alfred.stlouisfed.org/series/downloaddata"
_SERIES = re.compile(r"^[A-Z0-9]+$")
_COLUMN = re.compile(r"^(.+)_([0-9]{8})$")
_OBS_START = re.compile(
    rb'id="form_obs_start_date"[^>]*value="([0-9]{4}-[0-9]{2}-[0-9]{2})"'
)
_OBS_END = re.compile(
    rb'id="form_obs_end_date"[^>]*value="([0-9]{4}-[0-9]{2}-[0-9]{2})"'
)


class AlfredError(ValueError):
    """An ALFRED response violates the local source contract."""


@dataclass(frozen=True)
class SeriesProfile:
    series_id: str
    observation_start: date
    observation_end: date
    form_sha256: str


@dataclass(frozen=True)
class VintageTable:
    series_id: str
    vintages: tuple[date, ...]
    values: dict[tuple[date, date], float]
    raw_sha256: str


def source_url(series_id: str) -> str:
    if not _SERIES.fullmatch(series_id):
        raise ValueError(f"invalid ALFRED series id: {series_id}")
    return f"{ALFRED_BASE}?seid={series_id}"


def _request(request: Request, *, retries: int = 4) -> tuple[bytes, str]:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            with urlopen(request, timeout=120) as response:
                payload = bytes(response.read())
                if response.status != 200 or not payload:
                    raise AlfredError(f"HTTP {response.status}")
                return payload, response.geturl()
        except (HTTPError, URLError, TimeoutError, AlfredError) as exc:
            last_error = exc
            if attempt + 1 < retries:
                time.sleep(2**attempt)
    raise AlfredError(f"ALFRED request failed: {last_error}")


def parse_profile(series_id: str, payload: bytes) -> SeriesProfile:
    start_match = _OBS_START.search(payload)
    end_match = _OBS_END.search(payload)
    if start_match is None or end_match is None:
        raise AlfredError("ALFRED form fields changed")
    return SeriesProfile(
        series_id=series_id,
        observation_start=date.fromisoformat(start_match.group(1).decode()),
        observation_end=date.fromisoformat(end_match.group(1).decode()),
        form_sha256=sha256_bytes(payload),
    )


def fetch_profile(series_id: str) -> tuple[SeriesProfile, bytes]:
    request = Request(
        source_url(series_id),
        headers={"Accept": "text/html", "User-Agent": "fx-spd/0.1"},
    )
    payload, _ = _request(request)
    profile = parse_profile(series_id, payload)
    return profile, payload


def build_request(
    *, observation_start: date, observation_end: date, vintages: tuple[date, ...]
) -> bytes:
    if observation_end < observation_start:
        raise ValueError("observation range is reversed")
    if not vintages or tuple(sorted(set(vintages))) != vintages:
        raise ValueError("vintages must be sorted and unique")
    fields = (
        ("form[units]", "lin"),
        ("form[obs_start_date]", observation_start.isoformat()),
        ("form[obs_end_date]", observation_end.isoformat()),
        ("form[entered_vintage_dates]", " ".join(map(str, vintages))),
        ("form[file_type]", "2"),
        ("form[file_format]", "csv"),
        ("form[download_data]", ""),
    )
    return urlencode(fields).encode("ascii")


def fetch_package(series_id: str, request_payload: bytes) -> bytes:
    request = Request(
        source_url(series_id),
        data=request_payload,
        headers={
            "Accept": "application/zip",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "fx-spd/0.1",
        },
        method="POST",
    )
    payload, final_url = _request(request)
    if urlparse(final_url).hostname != "alfred.stlouisfed.org":
        raise AlfredError(f"unexpected redirect: {final_url}")
    if not payload.startswith(b"PK"):
        raise AlfredError("ALFRED returned HTML instead of a vintage package")
    return payload


def parse_package(payload: bytes) -> VintageTable:
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            names = [name for name in archive.namelist() if name.endswith(".csv")]
            if len(names) != 1:
                raise AlfredError("package must contain exactly one CSV")
            text = archive.read(names[0]).decode("utf-8-sig")
    except (zipfile.BadZipFile, UnicodeDecodeError) as exc:
        raise AlfredError("invalid ALFRED package") from exc
    reader = csv.DictReader(io.StringIO(text, newline=""))
    fields = tuple(reader.fieldnames or ())
    if not fields or fields[0] != "observation_date":
        raise AlfredError("ALFRED CSV header changed")
    ids: set[str] = set()
    columns: dict[str, date] = {}
    for field in fields[1:]:
        match = _COLUMN.fullmatch(field)
        if match is None:
            raise AlfredError(f"invalid vintage column: {field}")
        ids.add(match.group(1))
        columns[field] = datetime.strptime(match.group(2), "%Y%m%d").date()
    if len(ids) != 1:
        raise AlfredError("package contains inconsistent series ids")
    values: dict[tuple[date, date], float] = {}
    for row in reader:
        observation = date.fromisoformat(str(row["observation_date"]))
        for field, vintage in columns.items():
            raw = str(row.get(field) or "").strip()
            if raw in {"", "."}:
                continue
            value = float(raw)
            if not math.isfinite(value):
                raise AlfredError("non-finite ALFRED value")
            values[(observation, vintage)] = value
    if not values:
        raise AlfredError("package has no values")
    return VintageTable(
        series_id=next(iter(ids)),
        vintages=tuple(columns.values()),
        values=values,
        raw_sha256=sha256_bytes(payload),
    )


def save_package(
    root: Path, series_id: str, vintages: tuple[date, ...], payload: bytes
) -> Path:
    digest = sha256_bytes(payload)
    directory = root / series_id
    directory.mkdir(parents=True, exist_ok=True)
    stem = f"{vintages[0]:%Y%m%d}_{vintages[-1]:%Y%m%d}_{digest[:12]}"
    path = directory / f"{stem}.zip"
    if path.exists() and path.read_bytes() != payload:
        raise AlfredError(f"refusing to overwrite raw package: {path}")
    if not path.exists():
        path.write_bytes(payload)
    metadata = {
        "series_id": series_id,
        "vintages": [item.isoformat() for item in vintages],
        "retrieved_at_utc": datetime.now(UTC).isoformat(),
        "source_url": source_url(series_id),
        "sha256": digest,
    }
    sidecar = path.with_suffix(".metadata.json")
    if not sidecar.exists():
        sidecar.write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    return path
