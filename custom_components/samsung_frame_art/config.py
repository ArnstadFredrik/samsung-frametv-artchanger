"""Runtime settings for the Samsung Frame TV Art Changer integration.

Settings start from the config entry and can be overridden at runtime by the
web UI settings page (persisted in a JSON file under the integration data dir),
mirroring the behaviour of the original add-on.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import List, Optional


DEFAULT_REFRESH_SECONDS = 30
DEFAULT_SNAPSHOT_TTL_SECONDS = 20

RUNTIME_SETTINGS_FILENAME = "runtime_settings.json"
STATE_FILENAME = "gallery_state.json"


def parse_tv_ips(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


@dataclass
class Settings:
    tv_ips: List[str]
    media_dir: str
    data_dir: str
    state_path: str
    automation_token: str
    refresh_interval_seconds: int
    snapshot_ttl_seconds: int
    runtime_settings_path: str


def _read_json_file(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
            return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def build_settings(
    data_dir: str,
    media_dir: str,
    tv_ips: List[str],
    automation_token: str,
    refresh_interval_seconds: int = DEFAULT_REFRESH_SECONDS,
    snapshot_ttl_seconds: int = DEFAULT_SNAPSHOT_TTL_SECONDS,
) -> Settings:
    """Build a Settings object rooted at an integration data directory."""

    runtime_settings_path = os.path.join(data_dir, RUNTIME_SETTINGS_FILENAME)

    # Runtime overrides (written by the web UI settings page) take precedence,
    # same as in the original add-on.
    runtime_overrides = _read_json_file(runtime_settings_path)

    if runtime_overrides.get("tv_ips"):
        tv_ips = [str(item) for item in runtime_overrides["tv_ips"]]

    if runtime_overrides.get("refresh_interval_seconds") is not None:
        try:
            refresh_interval_seconds = max(5, int(runtime_overrides["refresh_interval_seconds"]))
        except (TypeError, ValueError):
            pass

    if runtime_overrides.get("snapshot_ttl_seconds") is not None:
        try:
            snapshot_ttl_seconds = max(1, int(runtime_overrides["snapshot_ttl_seconds"]))
        except (TypeError, ValueError):
            pass

    return Settings(
        tv_ips=[ip for ip in tv_ips if ip],
        media_dir=media_dir,
        data_dir=data_dir,
        state_path=os.path.join(data_dir, STATE_FILENAME),
        automation_token=str(automation_token or ""),
        refresh_interval_seconds=max(5, int(refresh_interval_seconds)),
        snapshot_ttl_seconds=max(1, int(snapshot_ttl_seconds)),
        runtime_settings_path=runtime_settings_path,
    )
