"""Which widgets are on the taskbar, in what order. Pure logic, no Qt, no I/O.

The taskbar area is a row of ``capacity`` cells (4 by default). A widget is 1
or 2 cells wide. Widgets are always packed to the left with no gaps between
them, like icons on a phone: removing one slides the others left, and
dragging one changes the *order*.

Example with capacity 4::

    cells:   0       1       2       3
           [clock] [   calendar    ] [ ]      <- one cell still free
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)

MAX_UNITS = 4
WIDGET_SIZES = (1, 2)


@dataclass(eq=False)
class Item:
    """One widget on the taskbar.

    Compared by identity (``eq=False``): two clocks are two different items,
    so an item can be used as a dictionary key for its running widget.
    """

    widget_id: str
    size: int


@dataclass(frozen=True)
class Placement:
    """Where an item currently sits: its first cell."""

    item: Item
    start: int

    @property
    def size(self) -> int:
        return self.item.size

    @property
    def end(self) -> int:
        """One past the last occupied cell."""
        return self.start + self.item.size

    def covers(self, cell: int) -> bool:
        """True if this item occupies ``cell``."""
        return self.start <= cell < self.end


class Layout:
    """The ordered row of widgets on the taskbar."""

    def __init__(self, capacity: int = MAX_UNITS) -> None:
        self.capacity = capacity
        self.items: list[Item] = []  # left to right

    def copy(self) -> Layout:
        """A shallow copy (same items, independent order), for previews while dragging."""
        layout = Layout(self.capacity)
        layout.items = list(self.items)
        return layout

    @property
    def placements(self) -> list[Placement]:
        """Every item with its start cell, left to right, packed with no gaps."""
        result = []
        start = 0
        for item in self.items:
            result.append(Placement(item, start))
            start += item.size
        return result

    def placement_of(self, item: Item) -> Placement | None:
        """Where ``item`` sits, or None if it is not in this layout."""
        for placement in self.placements:
            if placement.item is item:
                return placement
        return None

    def item_at(self, cell: int) -> Item | None:
        """The item covering ``cell``, or None if the cell is free."""
        for placement in self.placements:
            if placement.covers(cell):
                return placement.item
        return None

    def used_cells(self) -> int:
        return sum(item.size for item in self.items)

    def free_cells(self) -> int:
        """How many cells are still empty (always at the right end)."""
        return self.capacity - self.used_cells()

    def can_add(self, size: int) -> bool:
        """True if a widget ``size`` cells wide still fits."""
        return size <= self.free_cells()

    def insertion_index(self, position: float) -> int:
        """Where in the order something dropped at ``position`` should go.

        ``position`` is measured in cells (1.5 = the middle of cell 1). The
        new widget goes after every item whose centre is left of it.
        """
        index = 0
        for placement in self.placements:
            if placement.start + placement.size / 2 <= position:
                index += 1
        return index

    def add(self, widget_id: str, size: int, index: int | None = None) -> Item | None:
        """Insert a widget at ``index`` in the order (default: at the end).

        Returns the new item, or None if there is not enough room.
        """
        if size not in WIDGET_SIZES:
            raise ValueError(f"widget size must be 1 or 2, not {size}")
        if not self.can_add(size):
            return None
        item = Item(widget_id, size)
        self.items.insert(len(self.items) if index is None else index, item)
        return item

    def remove(self, item: Item) -> bool:
        """Take ``item`` out; the items to its right slide left. False if not present."""
        if item not in self.items:
            return False
        self.items.remove(item)
        return True

    def move(self, item: Item, index: int) -> bool:
        """Move ``item`` to position ``index`` in the order (counted without the item)."""
        if not self.remove(item):
            return False
        self.items.insert(min(index, len(self.items)), item)
        return True

    # --- saving -----------------------------------------------------------------

    def to_json(self) -> dict[str, Any]:
        """Data for layout.json."""
        return {"widgets": [{"id": item.widget_id, "size": item.size} for item in self.items]}

    @classmethod
    def from_json(cls, data: Any, capacity: int = MAX_UNITS) -> Layout:
        """Rebuild a layout from layout.json data, skipping any invalid entries."""
        layout = cls(capacity)
        entries = data.get("widgets", []) if isinstance(data, dict) else []
        for entry in entries:
            try:
                widget_id, size = str(entry["id"]), int(entry["size"])
            except (KeyError, TypeError, ValueError):
                log.warning("layout: ignoring malformed entry %r", entry)
                continue
            if size not in WIDGET_SIZES or layout.add(widget_id, size) is None:
                log.warning("layout: %s (size %s) does not fit; ignored", widget_id, size)
        return layout
