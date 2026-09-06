from __future__ import annotations

from datetime import date

import pytest

from fx_structural_policy_divergence.alfred import build_request, source_url


def test_alfred_rejects_non_series_identifier() -> None:
    with pytest.raises(ValueError, match="invalid ALFRED"):
        source_url("../secret")


def test_vintage_request_rejects_unsorted_dates() -> None:
    with pytest.raises(ValueError, match="sorted"):
        build_request(
            observation_start=date(2010, 1, 1),
            observation_end=date(2020, 1, 1),
            vintages=(date(2020, 1, 31), date(2019, 1, 31)),
        )


def test_vintage_request_has_no_fx_argument() -> None:
    payload = build_request(
        observation_start=date(2010, 1, 1),
        observation_end=date(2020, 1, 1),
        vintages=(date(2020, 1, 31),),
    )
    assert b"fx" not in payload.lower()
