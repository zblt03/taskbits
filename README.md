# Taskbits

Small widgets for the Windows 11 taskbar. Work in progress.

## Run from source

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m pip install -e .
.venv\Scripts\python -m taskbits
```

## License

[MIT](LICENSE) © Nacho

## Calendar widget

The Calendar widget shows your current or next Google Calendar event (read-only access,
scope `calendar.readonly`). Click it once to sign in with Google in your browser.

Release builds include a shared Google OAuth client, so nothing else is needed. When running
from source, put a Google OAuth client of type *Desktop app* (`credentials.json`) in
`%LOCALAPPDATA%\taskbits\` or in the project root (it is git-ignored).

Optional settings in `%LOCALAPPDATA%\taskbits\settings.json`:

```json
{"widgets": {"calendar": {"show_tomorrow": true, "excluded_calendars": ["Birthdays"], "use_calendar_color": true}}}
```
