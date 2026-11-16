"""Tests for taskbits.layout."""

import pytest

from taskbits.layout import Layout, Placement


def test_adding_fills_from_the_left() -> None:
    layout = Layout()
    assert layout.add("clock", 1) == Placement("clock", 0, 1)
    assert layout.add("calendar", 2) == Placement("calendar", 1, 2)
    assert layout.add("cpu", 1) == Placement("cpu", 3, 1)
    assert layout.free_cells() == 0


def test_no_room_returns_none() -> None:
    layout = Layout()
    layout.add("a", 2)
    layout.add("b", 1)
    assert layout.add("c", 2) is None  # only 1 cell left
    assert layout.add("d", 1) is not None
    assert layout.add("e", 1) is None


def test_removal_leaves_a_gap_that_is_filled_first() -> None:
    layout = Layout()
    for name in ("a", "b", "c", "d"):
        layout.add(name, 1)
    layout.remove(1)
    assert layout.add("new", 1) == Placement("new", 1, 1)


def test_two_wide_needs_two_adjacent_free_cells() -> None:
    layout = Layout()
    layout.add("a", 1, start=1)
    layout.add("b", 1, start=3)
    # Cells 0 and 2 are free but not next to each other.
    assert layout.free_cells() == 2
    assert layout.first_fit(2) is None
    assert layout.add("wide", 2) is None


def test_removing_by_any_covered_cell() -> None:
    layout = Layout()
    layout.add("wide", 2, start=1)
    assert layout.remove(2) == Placement("wide", 1, 2)
    assert layout.placements == []
    assert layout.remove(2) is None


def test_drop_on_right_half_of_a_gap_shifts_left() -> None:
    layout = Layout()
    layout.add("a", 1, start=0)
    layout.add("b", 1, start=3)
    assert layout.start_near(2, 2) == 1  # gap is cells 1–2
    assert layout.start_near(1, 2) == 1
    assert layout.start_near(3, 1) is None  # occupied


def test_cannot_go_past_the_last_cell() -> None:
    layout = Layout()
    assert not layout.fits(3, 2)
    assert layout.start_near(3, 2) == 2


def test_invalid_size_is_rejected() -> None:
    with pytest.raises(ValueError):
        Layout().add("huge", 3)


def test_json_round_trip() -> None:
    layout = Layout()
    layout.add("calendar", 2, start=1)
    layout.add("clock", 1, start=0)
    assert Layout.from_json(layout.to_json()).placements == layout.placements


def test_bad_json_entries_are_skipped() -> None:
    data = {
        "widgets": [
            {"id": "ok", "start": 0, "size": 1},
            {"id": "overlap", "start": 0, "size": 1},
            {"id": "too-big", "start": 1, "size": 3},
            {"id": "off-the-end", "start": 3, "size": 2},
            {"start": 2},
        ]
    }
    assert Layout.from_json(data).placements == [Placement("ok", 0, 1)]
    assert Layout.from_json("garbage").placements == []
