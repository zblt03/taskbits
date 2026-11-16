"""Where widgets sit on the taskbar: a row of cells. Pure logic, no Qt, no I/O.

The taskbar area is a row of ``capacity`` cells (4 by default). A widget is 1
or 2 cells wide and occupies that many *adjacent* cells. Removing a widget
leaves a gap, which the next added widget can fill.

Example with capacity 4::

    cells:   0       1       2       3
           [clock] [   calendar    ] [ ]      <- cell 3 is free
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)

MAX_UNITS = 4
WIDGET_SIZES = (1, 2)


@dataclass(frozen=True)
class Placement:
    """One widget on the taskbar: which widget, first cell, and width in cells."""

    widget_id: str
    start: int
    size: int

    @property
    def end(self) -> int:
        """One past the last occupied cell."""
        return self.start + self.size

    def covers(self, cell: int) -> bool:
        """True if this widget occupies ``cell``."""
        return self.start <= cell < self.end


class Layout:
    """The widgets placed on the taskbar, with rules for adding and removing."""

    def __init__(self, capacity: int = MAX_UNITS) -> None:
        self.capacity = capacity
        self._placements: list[Placement] = []

    @property
    def placements(self) -> list[Placement]:
        """Placed widgets, left to right (a copy: change them with add/remove)."""
        return sorted(self._placements, key=lambda p: p.start)

    def widget_at(self, cell: int) -> Placement | None:
        """The widget covering ``cell``, or None if the cell is free."""
        for placement in self._placements:
            if placement.covers(cell):
                return placement
        return None

    def free_cells(self) -> int:
        """How many cells are still empty."""
        return self.capacity - sum(p.size for p in self._placements)

    def fits(self, start: int, size: int) -> bool:
        """True if cells ``start`` … ``start + size - 1`` exist and are all free."""
        if start < 0 or start + size > self.capacity:
            return False
        return all(self.widget_at(cell) is None for cell in range(start, start + size))

    def first_fit(self, size: int) -> int | None:
        """Leftmost start cell where a widget of ``size`` fits, or None if none."""
        for start in range(self.capacity):
            if self.fits(start, size):
                return start
        return None

    def start_near(self, cell: int, size: int) -> int | None:
        """Where to put a widget dropped on ``cell``, or None if it can't go there.

        A 2-wide widget dropped on the right half of a gap is shifted one cell
        left, so dropping it anywhere on a 2-cell gap works.
        """
        for start in (cell, cell - 1) if size == 2 else (cell,):
            if self.fits(start, size):
                return start
        return None

    def add(self, widget_id: str, size: int, start: int | None = None) -> Placement | None:
        """Place a widget at ``start`` (or the first gap that fits). None if it doesn't fit."""
        if size not in WIDGET_SIZES:
            raise ValueError(f"widget size must be 1 or 2, not {size}")
        if start is None:
            start = self.first_fit(size)
        if start is None or not self.fits(start, size):
            return None
        placement = Placement(widget_id, start, size)
        self._placements.append(placement)
        return placement

    def remove(self, cell: int) -> Placement | None:
        """Remove the widget covering ``cell`` and return it (None if the cell was free)."""
        placement = self.widget_at(cell)
        if placement is not None:
            self._placements.remove(placement)
        return placement

    # --- saving -----------------------------------------------------------------

    def to_json(self) -> dict[str, Any]:
        """Data for layout.json."""
        return {
            "widgets": [
                {"id": p.widget_id, "start": p.start, "size": p.size} for p in self.placements
            ]
        }

    @classmethod
    def from_json(cls, data: Any, capacity: int = MAX_UNITS) -> Layout:
        """Rebuild a layout from layout.json data, skipping any invalid entries."""
        layout = cls(capacity)
        entries = data.get("widgets", []) if isinstance(data, dict) else []
        for entry in entries:
            try:
                widget_id, start, size = str(entry["id"]), int(entry["start"]), int(entry["size"])
            except (KeyError, TypeError, ValueError):
                log.warning("layout: ignoring malformed entry %r", entry)
                continue
            if size not in WIDGET_SIZES or layout.add(widget_id, size, start) is None:
                log.warning("layout: %s does not fit at cell %s; ignored", widget_id, start)
        return layout
