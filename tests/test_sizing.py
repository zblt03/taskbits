"""Tests for taskbits.sizing."""

from taskbits.sizing import metrics_for


def test_default_taskbar() -> None:
    m = metrics_for(48)
    assert (m.unit, m.gap, m.margin) == (84, 4, 4)
    assert m.widget_width(1) == 84
    assert m.widget_width(2) == 84 * 2 + 4
    assert m.total_width == 84 * 4 + 4 * 3


def test_sizes_scale_with_the_taskbar_height() -> None:
    small, big = metrics_for(40), metrics_for(64)
    assert small.unit < 84 < big.unit
    assert big.scale > 1 > small.scale


def test_cell_at() -> None:
    m = metrics_for(48)
    assert m.cell_at(0) == 0
    assert m.cell_at(83) == 0
    assert m.cell_at(87) == 0  # the gap belongs to the cell on its left
    assert m.cell_at(88) == 1
    assert m.cell_at(m.cell_x(3) + 10) == 3
    assert m.cell_at(m.total_width + 50) is None
    assert m.cell_at(-1) is None
