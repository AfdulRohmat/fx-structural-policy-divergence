from __future__ import annotations

from datetime import date

import pytest

from fx_structural_policy_divergence.phase04_fx import (
    _currency_returns,
    parse_ecb_monthly_marks,
    validate_pair_signal_uniqueness,
)


def _payload(rows: list[str]) -> bytes:
    return (
        "CURRENCY,CURRENCY_DENOM,TIME_PERIOD,OBS_VALUE\n" + "\n".join(rows) + "\n"
    ).encode()


def test_ecb_cross_orientation_base_appreciation() -> None:
    currencies = ("EUR", "USD", "JPY")
    rows = [
        "USD,EUR,2023-01-31,1.0",
        "JPY,EUR,2023-01-31,100.0",
        "USD,EUR,2023-02-28,1.0",
        "JPY,EUR,2023-02-28,110.0",
    ]
    marks, _ = parse_ecb_monthly_marks(_payload(rows), currencies)
    returns = _currency_returns(marks, currencies, 1)
    usd_jpy = returns[(date(2023, 1, 31), "USD")] - returns[(date(2023, 1, 31), "JPY")]
    assert usd_jpy > 0


def test_ecb_parser_rejects_sealed_2026() -> None:
    rows = ["USD,EUR,2026-01-02,1.0"]
    with pytest.raises(ValueError, match="sealed 2026"):
        parse_ecb_monthly_marks(_payload(rows), ("EUR", "USD"))


def test_inverse_pair_duplicate_is_rejected() -> None:
    rows = [
        {"snapshot": "2023-01-31", "base": "USD", "quote": "JPY"},
        {"snapshot": "2023-01-31", "base": "JPY", "quote": "USD"},
    ]
    with pytest.raises(ValueError, match="inverse"):
        validate_pair_signal_uniqueness(rows)
