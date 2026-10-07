import tomllib
from pathlib import Path

import pytest
from pydantic import ValidationError

from bot.config import SearchConfig, Settings, TomlConfigSettingsSource


@pytest.fixture
def toml_settings(monkeypatch):
    path = Path(__file__).resolve().parent.parent / "settings.example.toml"
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    monkeypatch.setattr(TomlConfigSettingsSource, "__call__", lambda self: data)
    monkeypatch.delenv("SEARCH", raising=False)
    monkeypatch.delenv("SEARCH__SEARCH_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("SEARCH__MAX_CONCURRENT_PER_PROVIDER", raising=False)
    return data


def test_search_defaults_for_existing_config(toml_settings):
    toml_settings.pop("search")
    settings = Settings()
    assert settings.search.search_timeout_seconds == 5.0
    assert settings.search.max_concurrent_per_provider == 3


def test_search_settings_from_toml(toml_settings):
    toml_settings["search"] = {
        "search_timeout_seconds": 2.5,
        "max_concurrent_per_provider": 7,
    }
    settings = Settings()
    assert settings.search.search_timeout_seconds == 2.5
    assert settings.search.max_concurrent_per_provider == 7


def test_search_environment_overrides_toml(toml_settings, monkeypatch):
    monkeypatch.setenv("SEARCH__SEARCH_TIMEOUT_SECONDS", "1.5")
    monkeypatch.setenv("SEARCH__MAX_CONCURRENT_PER_PROVIDER", "2")
    settings = Settings()
    assert settings.search.search_timeout_seconds == 1.5
    assert settings.search.max_concurrent_per_provider == 2


@pytest.mark.parametrize("value", [0, -1, float("inf"), float("nan")])
def test_invalid_search_timeout(value):
    with pytest.raises(ValidationError):
        SearchConfig(search_timeout_seconds=value)


@pytest.mark.parametrize("value", [0, -1, 1.5, True])
def test_invalid_search_concurrency(value):
    with pytest.raises(ValidationError):
        SearchConfig(max_concurrent_per_provider=value)
