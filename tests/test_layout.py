"""Tests for taskbits.layout."""

import pytest

from taskbits.layout import Layout


def starts(layout: Layout) -> list[tuple[str, int]]:
    """(widget id, start cell) for each item, left to right."""
    return [(p.item.widget_id, p.start) for p in layout.placements]


def test_adding_appends_on_the_right() -> None:
    layout = Layout()
    layout.add("clock", 1)
    layout.add("calendar", 2)
    layout.add("cpu", 1)
    assert starts(layout) == [("clock", 0), ("calendar", 1), ("cpu", 3)]
    assert layout.free_cells() == 0


def test_no_room_returns_none() -> None:
    layout = Layout()
    layout.add("a", 2)
    layout.add("b", 1)
    assert layout.add("c", 2) is None  # only 1 cell left
    assert layout.add("d", 1) is not None
    assert layout.add("e", 1) is None


def test_removing_slides_the_rest_left() -> None:
    layout = Layout()
    a = layout.add("a", 1)
    layout.add("wide", 2)
    layout.add("b", 1)
    assert layout.remove(a)
    assert starts(layout) == [("wide", 0), ("b", 2)]
    assert not layout.remove(a)  # already gone


def test_two_free_cells_always_fit_a_two_wide_widget() -> None:
    # Packing to the left means free cells are never split into separate gaps.
    layout = Layout()
    a = layout.add("a", 1)
    layout.add("b", 1)
    layout.add("c", 1)
    layout.remove(a)
    assert layout.can_add(2)
    assert starts(layout)[-1] == ("c", 1)


def test_insert_at_index() -> None:
    layout = Layout()
    layout.add("a", 1)
    layout.add("b", 1)
    layout.add("wide", 2, index=1)
    assert starts(layout) == [("a", 0), ("wide", 1), ("b", 3)]


def test_move_reorders() -> None:
    layout = Layout()
    a = layout.add("a", 1)
    layout.add("wide", 2)
    layout.add("b", 1)
    assert layout.move(a, 2)
    assert starts(layout) == [("wide", 0), ("b", 2), ("a", 3)]
    assert layout.move(a, 99)  # clamped to the end
    assert starts(layout)[-1] == ("a", 3)


def test_item_at() -> None:
    layout = Layout()
    layout.add("a", 1)
    wide = layout.add("wide", 2)
    assert layout.item_at(2) is wide
    assert layout.item_at(3) is None


def test_insertion_index_uses_item_centres() -> None:
    layout = Layout()
    layout.add("a", 1)  # centre 0.5
    layout.add("wide", 2)  # centre 2.0
    assert layout.insertion_index(0.2) == 0
    assert layout.insertion_index(0.6) == 1
    assert layout.insertion_index(1.9) == 1
    assert layout.insertion_index(3.5) == 2


def test_copy_is_independent() -> None:
    layout = Layout()
    a = layout.add("a", 1)
    preview = layout.copy()
    preview.remove(a)
    assert starts(layout) == [("a", 0)]


def test_invalid_size_is_rejected() -> None:
    with pytest.raises(ValueError):
        Layout().add("huge", 3)


def test_json_round_trip() -> None:
    layout = Layout()
    layout.add("calendar", 2)
    layout.add("clock", 1)
    assert starts(Layout.from_json(layout.to_json())) == starts(layout)


def test_bad_json_entries_are_skipped() -> None:
    data = {
        "widgets": [
            {"id": "ok", "size": 2},
            {"id": "too-big", "size": 3},
            {"id": "fits", "size": 2},
            {"id": "no-room", "size": 1},
            {"size": 1},
        ]
    }
    assert starts(Layout.from_json(data)) == [("ok", 0), ("fits", 2)]
    assert Layout.from_json("garbage").items == []
