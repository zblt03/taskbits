"""The list of widgets the user can add. Later this will include imported user widgets."""

from __future__ import annotations

import logging

from taskbits.widgets.base import Widget
from taskbits.widgets.builtin import BUILTIN_WIDGETS

log = logging.getLogger(__name__)


def available() -> list[type[Widget]]:
    """All widget classes the gallery offers, in display order."""
    return list(BUILTIN_WIDGETS)


def find(widget_id: str) -> type[Widget] | None:
    """The widget class with this id, or None if it is unknown."""
    for widget_class in available():
        if widget_class.id == widget_id:
            return widget_class
    return None


def create(widget_id: str) -> Widget | None:
    """A new instance of the widget with this id, or None if it is unknown."""
    widget_class = find(widget_id)
    if widget_class is None:
        log.warning("Unknown widget %r", widget_id)
        return None
    return widget_class()
