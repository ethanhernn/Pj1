"""Config loading + env-override behavior."""

import pytest

from src.config import load_config


def test_loads_defaults_from_yaml():
    cfg = load_config()
    assert cfg.edgar.cik_padded == "0002045724"
    assert "@" in cfg.edgar.user_agent
    assert cfg.ntfy.topic
    assert cfg.account.buying_power > 0


def test_nonempty_env_overrides(monkeypatch):
    monkeypatch.setenv("NTFY_TOPIC", "private-topic-123")
    monkeypatch.setenv("EDGAR_UA", "Custom Bot custom@example.com")
    cfg = load_config()
    assert cfg.ntfy.topic == "private-topic-123"
    assert cfg.edgar.user_agent == "Custom Bot custom@example.com"


@pytest.mark.parametrize("blank", ["", "   "])
def test_empty_env_falls_back_to_yaml(monkeypatch, blank):
    """Regression: GitHub Actions injects unset secrets as empty strings, which
    must NOT clobber the config defaults (was crashing the poll job with an
    empty User-Agent)."""
    monkeypatch.setenv("NTFY_TOPIC", blank)
    monkeypatch.setenv("NTFY_SERVER", blank)
    monkeypatch.setenv("EDGAR_UA", blank)
    cfg = load_config()
    assert cfg.ntfy.topic == "edgar-saw-monitor"
    assert cfg.ntfy.server == "https://ntfy.sh"
    assert "@" in cfg.edgar.user_agent  # valid UA, EdgarClient won't reject it
