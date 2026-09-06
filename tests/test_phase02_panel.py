from __future__ import annotations

from datetime import date

from fx_structural_policy_divergence.alfred import VintageTable
from fx_structural_policy_divergence.phase02_panel import (
    _chunks,
    _latest,
    _observations,
    _zscore,
)


def test_selector_never_reads_future_vintage() -> None:
    table = VintageTable(
        series_id="TEST",
        vintages=(date(2020, 1, 31), date(2020, 2, 29)),
        values={
            (date(2019, 12, 1), date(2020, 1, 31)): 1.0,
            (date(2019, 12, 1), date(2020, 2, 29)): 999.0,
        },
        raw_sha256="test",
    )
    assert _observations(table, date(2020, 1, 31)) == [(date(2019, 12, 1), 1.0)]


def test_post_origin_mutation_does_not_change_selection() -> None:
    base = VintageTable(
        "TEST",
        (date(2020, 1, 31),),
        {(date(2019, 12, 1), date(2020, 1, 31)): 1.0},
        "base",
    )
    mutated = VintageTable(
        "TEST",
        (date(2020, 1, 31), date(2020, 2, 29)),
        {
            **base.values,
            (date(2019, 12, 1), date(2020, 2, 29)): 50.0,
        },
        "mutated",
    )
    assert _observations(base, date(2020, 1, 31)) == _observations(
        mutated, date(2020, 1, 31)
    )


def test_stale_feature_fails_closed() -> None:
    sequence = [(date(2010, month, 1), float(month)) for month in range(1, 13)]
    assert _latest(sequence, date(2011, 12, 31), 75, 3)[0] is None


def test_expanding_zscore_excludes_current_value() -> None:
    sequence = [(date(2020, month, 1), float(month)) for month in range(1, 6)]
    expected = (5.0 - 2.5) / 1.2909944487358056
    assert _zscore(sequence, 4, 4) == expected


def test_vintage_chunks_do_not_mix_discontinuous_ranges() -> None:
    values = (
        date(2013, 1, 31),
        date(2013, 2, 28),
        date(2023, 1, 31),
        date(2023, 2, 28),
    )
    assert _chunks(values) == (values[:2], values[2:])
