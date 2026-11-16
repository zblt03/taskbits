"""Application controller: owns the layout and the widget instances, wires the windows.

* :class:`~taskbits.host.TaskbarHost` draws the placed widgets inside the taskbar.
* :class:`~taskbits.gallery.MainWindow` lists the widgets that can be added.
* A tray icon reopens the main window (there may be nothing on the taskbar to
  right-click) and quits the app.

While the main window is open, the taskbar host is in edit mode.
"""

from __future__ import annotations

import json
import logging
import math
import sys

from PySide6.QtCore import QObject, QRect, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from taskbits import paths, taskbar
from taskbits.gallery import MainWindow
from taskbits.host import TaskbarHost
from taskbits.icon import app_icon
from taskbits.layout import Layout
from taskbits.sizing import Metrics, metrics_for
from taskbits.widgets import catalog
from taskbits.widgets.base import Widget

log = logging.getLogger(__name__)

PLACEMENT_INTERVAL_MS = 2_000  # re-check taskbar size, theme and position
WATCH_INTERVAL_MS = 1_000  # Explorer restarts, hover, topmost (overlay)
LEFT_OFFSET = 8  # logical px between the taskbar's left edge and the first widget
DEFAULT_TASKBAR_HEIGHT = 48


class App(QObject):
    """Glue between the layout, the widgets, the taskbar host and the main window."""

    def __init__(self, embed: bool = True) -> None:
        super().__init__()
        self.embed = embed
        self.layout = self._load_layout()
        self.widgets: dict[int, Widget] = {}  # start cell -> running widget
        for placement in self.layout.placements:
            self._start_widget(placement.widget_id, placement.start)

        self.metrics = self._current_metrics()
        self.host = self._create_host()

        # The gallery gets its own preview instances, separate from the taskbar ones.
        self.window = MainWindow([widget_class() for widget_class in catalog.available()])
        self.window.setWindowIcon(app_icon())
        self.window.add_requested.connect(lambda widget_id: self.add_widget(widget_id))
        self.window.closed.connect(lambda: self.host.set_edit_mode(False))

        self.tray = self._create_tray()

        self._placement_timer = QTimer(self, interval=PLACEMENT_INTERVAL_MS)
        self._placement_timer.timeout.connect(self.reposition)
        self._watch_timer = QTimer(self, interval=WATCH_INTERVAL_MS)
        self._watch_timer.timeout.connect(self._watch)

    def start(self) -> None:
        """Show everything and start the timers."""
        self._placement_timer.start()
        self._watch_timer.start()
        self._watch()  # shows the host as soon as the taskbar exists
        self.open_main_window()

    # --- layout and widgets ----------------------------------------------------------

    @staticmethod
    def _load_layout() -> Layout:
        path = paths.layout_path()
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except FileNotFoundError:
            return Layout()
        except (OSError, ValueError):
            log.exception("Could not read %s; starting with an empty taskbar", path)
            return Layout()
        return Layout.from_json(data)

    def _save_layout(self) -> None:
        try:
            paths.layout_path().write_text(json.dumps(self.layout.to_json(), indent=2), encoding="utf-8")
        except OSError:
            log.exception("Could not save the layout")

    def _start_widget(self, widget_id: str, start: int) -> None:
        widget = catalog.create(widget_id)
        if widget is not None:
            self.widgets[start] = widget

    def add_widget(self, widget_id: str, start: int | None = None) -> None:
        """Put a widget on the taskbar: at ``start``, or in the first gap that fits."""
        widget_class = catalog.find(widget_id)
        if widget_class is None:
            return
        placement = self.layout.add(widget_id, widget_class.size, start)
        if placement is None:
            log.info("No room for %s (%d wide)", widget_id, widget_class.size)
            return
        log.info("Added %s at cell %d", widget_id, placement.start)
        self._start_widget(widget_id, placement.start)
        self._layout_changed()

    def remove_widget(self, cell: int) -> None:
        """Take the widget covering ``cell`` off the taskbar."""
        placement = self.layout.remove(cell)
        if placement is None:
            return
        log.info("Removed %s from cell %d", placement.widget_id, placement.start)
        widget = self.widgets.pop(placement.start, None)
        if widget is not None:
            widget.stop()
            widget.deleteLater()
        self._layout_changed()

    def _layout_changed(self) -> None:
        self._save_layout()
        self.host.set_items(self.layout, self.widgets)
        self.window.update_space(self.layout)

    def _on_widget_clicked(self, start: int) -> None:
        widget = self.widgets.get(start)
        if widget is not None:
            widget.clicked()

    # --- main window and tray ----------------------------------------------------------

    def open_main_window(self) -> None:
        """Show the gallery and put the taskbar in edit mode."""
        self.window.update_space(self.layout)
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()
        self.host.set_edit_mode(True)

    def _create_tray(self) -> QSystemTrayIcon:
        tray = QSystemTrayIcon(app_icon(), self)
        tray.setToolTip("Taskbits")
        menu = QMenu()
        menu.addAction("Open Taskbits", self.open_main_window)
        menu.addSeparator()
        menu.addAction("Quit", QApplication.quit)
        tray.setContextMenu(menu)
        self._tray_menu = menu  # keep a reference: the tray does not own the menu
        tray.activated.connect(
            lambda reason: self.open_main_window()
            if reason == QSystemTrayIcon.ActivationReason.Trigger
            else None
        )
        tray.show()
        return tray

    # --- the taskbar host window -------------------------------------------------------

    def _current_metrics(self) -> Metrics:
        """Sizes for the current taskbar (the usable height, below its top border line)."""
        info = taskbar.get_taskbar()
        scale = QGuiApplication.primaryScreen().devicePixelRatio()
        if info is None:
            return metrics_for(DEFAULT_TASKBAR_HEIGHT)
        usable_px = info.rect.height - math.ceil(scale)
        return metrics_for(round(usable_px / scale))

    def _create_host(self) -> TaskbarHost:
        host = TaskbarHost(self.metrics, embedded=self.embed)
        host.widget_clicked.connect(self._on_widget_clicked)
        host.remove_requested.connect(self.remove_widget)
        host.drop_requested.connect(self.add_widget)
        host.edit_requested.connect(self.open_main_window)
        host.quit_requested.connect(QApplication.quit)
        host.set_items(self.layout, self.widgets)
        host.set_edit_mode(self.window.isVisible() if hasattr(self, "window") else False)
        return host

    def _replace_host(self) -> None:
        """Throw the host window away and create a fresh (hidden) one.

        Needed after an Explorer restart and when the taskbar height changes,
        because an embedded window must not be resized through Qt.
        """
        self.host.hide()
        self.host.deleteLater()
        self.host = self._create_host()

    def _show_host(self) -> None:
        if not self.embed:
            self.reposition()  # place it before it first appears
        self.host.show()
        self.reposition()  # embedding needs the native window to exist

    def reposition(self) -> None:
        """Follow the taskbar's size, theme and position; cheap enough every 2 s."""
        metrics = self._current_metrics()
        if metrics != self.metrics:
            log.info("Taskbar height changed to %d px; resizing widgets", metrics.height)
            self.metrics = metrics
            self._replace_host()
            self._show_host()
            return
        self.host.set_light_theme(taskbar.uses_light_theme())
        if self.embed:
            self._reposition_embedded()
        else:
            self._reposition_overlay()

    def _reposition_embedded(self) -> None:
        """Keep the host a child of the taskbar, placed with Win32 (physical pixels)."""
        if not self.host.isVisible():
            return
        hwnd = int(self.host.winId())
        tray = taskbar.find_taskbar_window()
        info = taskbar.get_taskbar()
        if tray is None or info is None:
            return
        if not taskbar.is_child_of(hwnd, tray):
            log.info("Embedding the widget row into the taskbar")
            if not taskbar.embed_in_taskbar(hwnd, tray):
                log.warning("Could not embed into the taskbar; using overlay mode")
                self.embed = False
                self._replace_host()
                self._show_host()
                return
        key = self.host.key_color()  # re-applied every tick: follows theme changes
        taskbar.set_color_key(hwnd, key.red(), key.green(), key.blue())

        scale = QGuiApplication.primaryScreen().devicePixelRatio()
        border_px = math.ceil(scale)  # the taskbar's 1-logical-px top border line
        taskbar.place_child(
            hwnd,
            round(LEFT_OFFSET * scale),
            border_px,
            round(self.host.width() * scale),
            info.rect.height - border_px,
        )

    def _reposition_overlay(self) -> None:
        """Float the host over the left end of the taskbar."""
        info = taskbar.get_taskbar()
        scale = QGuiApplication.primaryScreen().devicePixelRatio()
        if info is None:
            return
        left = round(info.rect.left / scale) + LEFT_OFFSET
        top = round((info.rect.top + math.ceil(scale)) / scale)
        target = QRect(left, top, self.host.width(), self.host.height())
        if self.host.geometry() != target:
            self.host.setGeometry(target)

    def _watch(self) -> None:
        """Every second: survive Explorer restarts and keep the hover state honest."""
        if self.embed and not taskbar.window_exists(int(self.host.winId())):
            # Explorer restarted: Windows destroyed the taskbar *and* our child window.
            log.warning("Host window was destroyed (Explorer restart?); recreating it")
            self._replace_host()
        if not self.host.isVisible():
            if self.embed and taskbar.find_taskbar_window() is None:
                return  # Explorer not running yet; try again next tick
            self._show_host()

        hwnd = int(self.host.winId())
        if self.embed:
            cursor = taskbar.cursor_in_window(hwnd)
            self.host.sync_hover(cursor[0] / self.host.devicePixelRatioF() if cursor else None)
        else:
            taskbar.set_topmost(hwnd)


def run(embed: bool = True) -> int:
    """Create the Qt application, start Taskbits and run the event loop."""
    qt_app = QApplication(sys.argv)
    qt_app.setQuitOnLastWindowClosed(False)  # closing the gallery keeps the widgets running
    qt_app.setWindowIcon(app_icon())
    controller = App(embed=embed)
    controller.start()
    return qt_app.exec()
