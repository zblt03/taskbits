"""Tests for taskbits.sizing."""

from taskbits.sizing import metrics_for


def test_default_taskbar() -> None:
    m = metrics_for(48)
    assert (m.unit, m.gap, m.margin) == (84, 4, 6)
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


def test_cells_at() -> None:
    m = metrics_for(48)
    assert m.cells_at(0) == 0
    assert m.cells_at(m.cell_x(2)) == 2


def test_badge_fits_above_widget_and_right_of_last_one() -> None:
    for height in (32, 40, 44, 48, 64, 72):
        m = metrics_for(height)
        assert m.badge_size / 2 <= m.margin  # the top half fits above the widget
        assert m.window_width >= m.total_width + m.badge_size / 2
