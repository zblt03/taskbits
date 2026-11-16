# Taskbits — conventions for Claude

A Windows 11 app that hosts small widgets *inside* the taskbar (left side). Widgets are built in or
made by users (Python plugins). Owner: Nacho (GitHub `zblt03`), IB CS HL student. Code must be
readable and explainable by a strong student: clear module boundaries, type hints, docstrings, no
clever tricks. Started from scratch, reusing ideas and code from `zblt03/cal-widget`.

## Workflow
- Work phase by phase; at each ⏸ checkpoint stop and say exactly what to test. Wait for confirmation.
- Before marking a step done: run tests (`.venv\Scripts\python -m pytest`), run the app if relevant, check `git status`.

## Git rules
- Commit and push after every working step. Conventional Commits in English (feat:, fix:, test:, docs:, refactor:, chore:, ci:).
- One logical change per commit; explain the *why* when not obvious.
- Run `git status` before every commit. Secrets (credentials.json, token.json) must NEVER be committed.
- Never force-push, rewrite history, or delete files without asking first.

## Conventions
- Python 3.14 (the local interpreter). Type hints everywhere, docstrings on public functions.
- `logging`, never `print`. All code, comments, commits and docs in English.
- Runtime files (layout.json, logs, …) live in `%LOCALAPPDATA%\taskbits\`, never in the repo.

## Widget model
- Widgets are 1 or 2 units wide and 1 unit tall. At most 4 units on the taskbar at once.
- The unit size comes from the taskbar height (responsive to DPI and taskbar size).
- Slots are a row of 4 cells; a widget occupies `size` adjacent cells. Clicking a widget in the
  gallery puts it in the first free gap that fits; it can also be dragged onto a cell.
- While the main window is open the taskbar is in *edit mode*: each widget gets an outline and an ✕
  at its top-left corner to remove it.

## Taskbar embedding (learned in cal-widget)
- The host window is made a child of `Shell_TrayWnd` (SetParent) and painted opaquely on a colour
  key, because Qt's per-pixel alpha stops repainting there. Never resize/move it through Qt once
  embedded; place it with Win32. Colour-keyed pixels are click-through (and drop-through).
- Qt's global/drop positions are wrong for the embedded window (Qt doesn't know its parent); use the
  real cursor position from Win32 instead.
