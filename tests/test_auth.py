"""Tests for taskbits.google.auth that need no network."""

from pathlib import Path

import pytest

from taskbits import paths
from taskbits.google import auth


@pytest.fixture
def empty_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point both the data dir and the app dir at empty temp folders."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setattr(paths, "app_dir", lambda: tmp_path / "app")
    return tmp_path


def test_no_token_without_login_requires_reauth(empty_dirs: Path) -> None:
    with pytest.raises(auth.ReauthRequiredError):
        auth.get_credentials(allow_login=False)


def test_missing_credentials_gives_helpful_message(empty_dirs: Path) -> None:
    with pytest.raises(auth.CredentialsMissingError) as info:
        auth.get_credentials(allow_login=True)
    assert "README" in str(info.value)
    assert "credentials.json" in str(info.value)


def test_corrupt_token_is_treated_as_missing(empty_dirs: Path) -> None:
    paths.token_path().write_text("not json", encoding="utf-8")
    with pytest.raises(auth.ReauthRequiredError):
        auth.get_credentials(allow_login=False)
