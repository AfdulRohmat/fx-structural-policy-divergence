from __future__ import annotations

import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config" / "research_contract_v0_1.json"
G10 = {"AUD", "CAD", "CHF", "EUR", "GBP", "JPY", "NOK", "NZD", "SEK", "USD"}


def _contract() -> dict[str, object]:
    value = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_contract_contains_exact_g10_universe() -> None:
    assert set(_contract()["currency_universe"]) == G10


def test_confirmation_precedes_sealed_fx_period() -> None:
    contract = _contract()
    confirmation_end = date.fromisoformat(str(contract["confirmation_end"]))
    sealed_start = date.fromisoformat(str(contract["sealed_fx_start"]))
    assert confirmation_end < sealed_start


def test_fx_access_is_forbidden_before_signal_freeze() -> None:
    contract = _contract()
    assert contract["confirmation_fx_access"] == "FORBIDDEN_UNTIL_PHASE_03_FREEZE"
    assert contract["status"] == "FROZEN_BEFORE_SOURCE_AND_FX_ACCESS"
