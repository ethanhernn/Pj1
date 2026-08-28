"""Configuration loading. Reads config.yaml, applies environment overrides."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = REPO_ROOT / "config.yaml"


def _env_or(key: str, default: str) -> str:
    """Return env var `key` if set to a non-empty value, else `default`.

    GitHub Actions injects *unset* secrets as empty strings, so the env var is
    present-but-empty rather than absent — meaning os.environ.get(key, default)
    returns "" instead of the default. Treat empty/whitespace as unset.
    """
    value = os.environ.get(key)
    if value is None or not value.strip():
        return default
    return value


@dataclass
class EdgarConfig:
    cik: str
    user_agent: str
    poll_sleep_seconds: float

    @property
    def cik_padded(self) -> str:
        """CIK zero-padded to 10 digits, as the submissions URL requires."""
        return self.cik.lstrip("0").zfill(10)

    @property
    def cik_int(self) -> int:
        """CIK with leading zeros stripped, as used in Archives paths."""
        return int(self.cik)


@dataclass
class NtfyConfig:
    server: str
    topic: str


@dataclass
class AccountConfig:
    buying_power: float
    max_position_pct: float
    max_total_exposure_pct: float
    max_names: int
    stop_loss_pct: float


@dataclass
class RulesConfig:
    min_avg_daily_volume: int
    longs_only: bool
    source_buckets: list[str]
    rank_by: str
    increase_threshold_pct: float


@dataclass
class Config:
    edgar: EdgarConfig
    ntfy: NtfyConfig
    account: AccountConfig
    rules: RulesConfig
    cusip_overrides: dict[str, str] = field(default_factory=dict)


def load_config(path: str | Path = DEFAULT_CONFIG_PATH) -> Config:
    """Load config.yaml and apply env overrides (NTFY_TOPIC, EDGAR_UA)."""
    raw: dict[str, Any] = yaml.safe_load(Path(path).read_text())

    edgar_raw = raw["edgar"]
    ua = _env_or("EDGAR_UA", edgar_raw["user_agent"])
    edgar = EdgarConfig(
        cik=str(edgar_raw["cik"]),
        user_agent=ua,
        poll_sleep_seconds=float(edgar_raw.get("poll_sleep_seconds", 0.2)),
    )

    ntfy_raw = raw["ntfy"]
    ntfy = NtfyConfig(
        server=_env_or("NTFY_SERVER", ntfy_raw["server"]).rstrip("/"),
        topic=_env_or("NTFY_TOPIC", ntfy_raw["topic"]),
    )

    acct_raw = raw["account"]
    account = AccountConfig(
        buying_power=float(acct_raw["buying_power"]),
        max_position_pct=float(acct_raw["max_position_pct"]),
        max_total_exposure_pct=float(acct_raw["max_total_exposure_pct"]),
        max_names=int(acct_raw["max_names"]),
        stop_loss_pct=float(acct_raw["stop_loss_pct"]),
    )

    rules_raw = raw["rules"]
    rules = RulesConfig(
        min_avg_daily_volume=int(rules_raw["min_avg_daily_volume"]),
        longs_only=bool(rules_raw["longs_only"]),
        source_buckets=list(rules_raw["source_buckets"]),
        rank_by=str(rules_raw["rank_by"]),
        increase_threshold_pct=float(rules_raw.get("increase_threshold_pct", 5)),
    )

    overrides = {str(k): str(v) for k, v in (raw.get("cusip_overrides") or {}).items()}

    return Config(edgar=edgar, ntfy=ntfy, account=account, rules=rules, cusip_overrides=overrides)
