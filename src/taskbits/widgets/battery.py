"""Battery widget: charge level and state, from GetSystemPowerStatus."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor

from taskbits.widgets.base import Widget

UPDATE_INTERVAL_MS = 30_000
LOW_PERCENT = 20
LOW_COLOR = QColor("#E8453C")
CHARGING_COLOR = QColor("#34A853")

NO_BATTERY_FLAG = 128
UNKNOWN = 255


@dataclass(frozen=True)
class PowerStatus:
    """The parts of SYSTEM_POWER_STATUS we use."""

    plugged_in: bool | None  # None = unknown
    has_battery: bool
    charging: bool
    percent: int | None  # None = unknown
    seconds_left: int | None  # None = unknown or plugged in


def format_duration(seconds: int) -> str:
    """'2 h 05 min' or '45 min'."""
    hours, minutes = divmod(seconds // 60, 60)
    return f"{hours} h {minutes:02d} min" if hours else f"{minutes} min"


def battery_lines(status: PowerStatus) -> tuple[str, str]:
    """The two lines the widget shows for ``status``."""
    if not status.has_battery:
        return "No battery", "Plugged in" if status.plugged_in else ""
    level = f"{status.percent}%" if status.percent is not None else "?%"
    if status.charging:
        return level, "Charging"
    if status.plugged_in:
        return level, "Plugged in"
    if status.seconds_left is not None:
        return level, f"{format_duration(status.seconds_left)} left"
    return level, "On battery"


# --- Win32 --------------------------------------------------------------------------


class _SystemPowerStatus(ctypes.Structure):
    _fields_ = [
        ("ACLineStatus", ctypes.c_ubyte),  # 0 offline, 1 online, 255 unknown
        ("BatteryFlag", ctypes.c_ubyte),  # bit flags; 8 = charging, 128 = no battery
        ("BatteryLifePercent", ctypes.c_ubyte),  # 0–100, 255 unknown
        ("SystemStatusFlag", ctypes.c_ubyte),
        ("BatteryLifeTime", wintypes.DWORD),  # seconds, 0xFFFFFFFF unknown
        ("BatteryFullLifeTime", wintypes.DWORD),
    ]


def read_power_status() -> PowerStatus | None:
    """The current power status, or None if Windows refuses."""
    raw = _SystemPowerStatus()
    if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(raw)):
        return None
    return PowerStatus(
        plugged_in=None if raw.ACLineStatus == UNKNOWN else raw.ACLineStatus == 1,
        has_battery=raw.BatteryFlag == UNKNOWN or not raw.BatteryFlag & NO_BATTERY_FLAG,
        charging=bool(raw.BatteryFlag != UNKNOWN and raw.BatteryFlag & 8),
        percent=None if raw.BatteryLifePercent == UNKNOWN else raw.BatteryLifePercent,
        seconds_left=None if raw.BatteryLifeTime == 0xFFFFFFFF else raw.BatteryLifeTime,
    )


# --- the widget -----------------------------------------------------------------------


class BatteryWidget(Widget):
    id = "battery"
    name = "Battery"
    description = "Charge level and time left."
    size = 1

    def __init__(self) -> None:
        super().__init__()
        self._status = read_power_status()
        self._timer = QTimer(self, interval=UPDATE_INTERVAL_MS)
        self._timer.timeout.connect(self._update)
        self._timer.start()

    def _update(self) -> None:
        self._status = read_power_status()
        self.changed.emit()

    def lines(self) -> tuple[str, str]:
        if self._status is None:
            return "Battery", "Unavailable"
        return battery_lines(self._status)

    def accent(self) -> QColor | None:
        status = self._status
        if status is None or not status.has_battery:
            return None
        if status.charging:
            return CHARGING_COLOR
        if status.percent is not None and status.percent <= LOW_PERCENT:
            return LOW_COLOR
        return None

    def stop(self) -> None:
        self._timer.stop()
