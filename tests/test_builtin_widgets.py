"""Tests for the pure logic inside the built-in widgets."""

from taskbits.widgets.battery import PowerStatus, battery_lines, format_duration
from taskbits.widgets.focus import Phase, Pomodoro, format_mm_ss
from taskbits.widgets.system import CpuTimes, cpu_percent

# --- system -------------------------------------------------------------------------


def test_cpu_percent() -> None:
    before = CpuTimes(idle=100, kernel=200, user=100)
    # 100 units passed in total (kernel 60 + user 40), 25 of them idle.
    after = CpuTimes(idle=125, kernel=260, user=140)
    assert cpu_percent(before, after) == 75


def test_cpu_percent_with_no_time_passed() -> None:
    same = CpuTimes(1, 2, 3)
    assert cpu_percent(same, same) == 0


# --- battery ------------------------------------------------------------------------


def status(**changes: object) -> PowerStatus:
    values = dict(plugged_in=False, has_battery=True, charging=False, percent=85, seconds_left=None)
    values.update(changes)
    return PowerStatus(**values)  # type: ignore[arg-type]


def test_battery_lines() -> None:
    assert battery_lines(status(charging=True, plugged_in=True)) == ("85%", "Charging")
    assert battery_lines(status(plugged_in=True)) == ("85%", "On AC")
    assert battery_lines(status(seconds_left=2 * 3600 + 5 * 60)) == ("85%", "2h 05m")
    assert battery_lines(status()) == ("85%", "On battery")
    assert battery_lines(status(percent=None)) == ("?%", "On battery")
    assert battery_lines(status(has_battery=False, plugged_in=True)) == ("No battery", "On AC")


def test_format_duration() -> None:
    assert format_duration(45 * 60 + 30) == "45 min"
    assert format_duration(3600) == "1h 00m"


# --- focus timer --------------------------------------------------------------------


def test_pomodoro_runs_pauses_and_resumes() -> None:
    timer = Pomodoro(focus_seconds=100, break_seconds=20)
    assert not timer.running
    timer.toggle(now=0)
    assert timer.remaining(now=30) == 70
    timer.toggle(now=30)  # pause
    assert timer.remaining(now=500) == 70  # time doesn't pass while paused
    timer.toggle(now=500)
    assert timer.remaining(now=510) == 60


def test_pomodoro_switches_to_break_and_back() -> None:
    timer = Pomodoro(focus_seconds=100, break_seconds=20)
    timer.toggle(now=0)
    assert not timer.tick(now=99)
    assert timer.tick(now=100)
    assert timer.phase is Phase.BREAK and timer.running
    assert timer.remaining(now=105) == 15
    assert timer.tick(now=120)
    assert timer.phase is Phase.FOCUS


def test_pomodoro_reset_and_skip() -> None:
    timer = Pomodoro(focus_seconds=100, break_seconds=20)
    timer.skip(now=0)
    assert timer.phase is Phase.BREAK and timer.running
    timer.reset()
    assert timer.phase is Phase.FOCUS and not timer.running
    assert timer.remaining(now=999) == 100


def test_format_mm_ss_rounds_up() -> None:
    assert format_mm_ss(1500) == "25:00"
    assert format_mm_ss(1499.2) == "25:00"
    assert format_mm_ss(59.01) == "01:00"
    assert format_mm_ss(0) == "00:00"


def test_battery_glyph() -> None:
    from taskbits.widgets.drawing import battery_glyph

    assert battery_glyph(0, charging=False) == ""
    assert battery_glyph(54, charging=False) == ""
    assert battery_glyph(100, charging=False) == ""
    assert battery_glyph(100, charging=True) == ""
    assert battery_glyph(150, charging=True) == ""  # clamped
