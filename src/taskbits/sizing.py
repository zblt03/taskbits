"""Pixel sizes of the taskbar area, derived from the taskbar height. Pure logic.

Everything scales with the taskbar height, so widgets keep the same shape on
any DPI or taskbar size. All values are Qt *logical* pixels.
"""

from __future__ import annotations

from dataclasses import dataclass

from taskbits.layout import MAX_UNITS

UNIT_ASPECT = 1.75  # a 1-wide widget is this many times wider than the taskbar is tall
GAP_RATIO = 1 / 12  # space between cells, as a fraction of the taskbar height
MARGIN_RATIO = 1 / 12  # space above and below widgets (Windows leaves a gap too)
REFERENCE_HEIGHT = 48  # the default Windows 11 taskbar height at 100 %


@dataclass(frozen=True)
class Metrics:
    """All sizes needed to lay out and draw the widget row."""

    height: int  # usable taskbar height
    unit: int  # width of one cell
    gap: int  # space between cells
    margin: int  # space above/below each widget
    capacity: int = MAX_UNITS

    @property
    def scale(self) -> float:
        """How much bigger than a default taskbar: used to scale fonts."""
        return self.height / REFERENCE_HEIGHT

    def cell_x(self, cell: int) -> int:
        """Left edge of ``cell``."""
        return cell * (self.unit + self.gap)

    def widget_width(self, size: int) -> int:
        """Width of a widget ``size`` cells wide (it also covers the gaps between them)."""
        return size * self.unit + (size - 1) * self.gap

    @property
    def total_width(self) -> int:
        """Width of the whole row of cells."""
        return self.widget_width(self.capacity)

    def cells_at(self, x: float) -> float:
        """Horizontal position ``x`` measured in cells (1.5 = middle of cell 1)."""
        return x / (self.unit + self.gap)

    def cell_at(self, x: float) -> int | None:
        """The cell under horizontal position ``x`` (gaps count as the cell to their left)."""
        if x < 0:
            return None
        cell = int(x // (self.unit + self.gap))
        return cell if cell < self.capacity else None


def metrics_for(taskbar_height: int, capacity: int = MAX_UNITS) -> Metrics:
    """Compute the layout sizes for a taskbar of ``taskbar_height`` logical pixels."""
    return Metrics(
        height=taskbar_height,
        unit=round(taskbar_height * UNIT_ASPECT),
        gap=max(2, round(taskbar_height * GAP_RATIO)),
        margin=max(2, round(taskbar_height * MARGIN_RATIO)),
        capacity=capacity,
    )
