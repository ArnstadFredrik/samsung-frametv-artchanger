"""Lightweight request payload parsing (replaces the pydantic schemas of the
original add-on so the integration only depends on samsungtvws and Pillow)."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any, Dict, List, Optional

from .const import SLIDESHOW_MAX_INTERVAL_SECONDS, SLIDESHOW_MIN_INTERVAL_SECONDS
from .errors import InvalidInputError


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _as_float(value: Any, name: str, default: Optional[float] = None) -> Optional[float]:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        raise InvalidInputError(f"Invalid value for {name}: {value!r}")


def _as_int(value: Any, name: str, default: int, minimum: Optional[int] = None, maximum: Optional[int] = None) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError):
        raise InvalidInputError(f"Invalid value for {name}: {value!r}")
    if minimum is not None:
        result = max(minimum, result)
    if maximum is not None:
        result = min(maximum, result)
    return result


def parse_crop(raw) -> Optional[Dict[str, Any]]:
    """Parse a crop payload from a JSON string or dict, as sent by the web UI."""

    if raw is None or raw == "":
        return None

    if isinstance(raw, str):
        try:
            loaded = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise InvalidInputError(f"Invalid crop payload: {exc}") from exc
    else:
        loaded = raw

    if not isinstance(loaded, dict):
        raise InvalidInputError("Invalid crop payload type")

    payload: Dict[str, Any] = {}
    x = _as_float(loaded.get("x"), "x")
    y = _as_float(loaded.get("y"), "y")
    width = _as_float(loaded.get("width"), "width")
    height = _as_float(loaded.get("height"), "height")
    if x is not None:
        payload["x"] = x
    if y is not None:
        payload["y"] = y
    if width is not None:
        payload["width"] = width
    if height is not None:
        payload["height"] = height

    payload["quarter_turns"] = _as_int(loaded.get("quarter_turns", 0), "quarter_turns", 0, minimum=0, maximum=3)
    payload["flip_horizontal"] = _as_bool(loaded.get("flip_horizontal"), False)
    return payload


@dataclass
class ActivateRequest:
    tv_ips: Optional[List[str]] = None
    ensure_upload: bool = True
    activate: bool = True


@dataclass
class DeleteRequest:
    targets: str = "both"
    tv_ips: Optional[List[str]] = None


@dataclass
class RandomRequest:
    tv_ips: Optional[List[str]] = None
    ensure_upload: bool = True
    activate: bool = True


@dataclass
class SettingsUpdateRequest:
    tv_ips: List[str] = field(default_factory=list)
    refresh_interval_seconds: int = 30
    snapshot_ttl_seconds: int = 20


@dataclass
class SlideshowStartRequest:
    tv_ips: Optional[List[str]] = None
    tag: Optional[str] = None
    folder: Optional[str] = None
    interval_seconds: int = 3600
    shuffle: bool = True


def parse_slideshow_start(payload: Dict[str, Any]) -> SlideshowStartRequest:
    tv_ips = payload.get("tv_ips")
    if tv_ips is not None and not (isinstance(tv_ips, list) and all(isinstance(item, str) for item in tv_ips)):
        raise InvalidInputError("tv_ips must be a list of strings")

    tag = payload.get("tag")
    if tag is not None and (not isinstance(tag, str) or not tag.strip()):
        tag = None
    folder = payload.get("folder")
    if folder is not None and not isinstance(folder, str):
        raise InvalidInputError("folder must be a string")

    return SlideshowStartRequest(
        tv_ips=tv_ips,
        tag=tag,
        folder=folder,
        interval_seconds=_as_int(
            payload.get("interval_seconds", 3600),
            "interval_seconds",
            3600,
            minimum=SLIDESHOW_MIN_INTERVAL_SECONDS,
            maximum=SLIDESHOW_MAX_INTERVAL_SECONDS,
        ),
        shuffle=_as_bool(payload.get("shuffle"), True),
    )


def parse_settings_update(payload: Dict[str, Any]) -> SettingsUpdateRequest:
    tv_ips = payload.get("tv_ips")
    if not isinstance(tv_ips, list):
        raise InvalidInputError("tv_ips must be a list")
    return SettingsUpdateRequest(
        tv_ips=[str(item) for item in tv_ips],
        refresh_interval_seconds=_as_int(
            payload.get("refresh_interval_seconds", 30), "refresh_interval_seconds", 30, minimum=5, maximum=3600
        ),
        snapshot_ttl_seconds=_as_int(
            payload.get("snapshot_ttl_seconds", 20), "snapshot_ttl_seconds", 20, minimum=1, maximum=600
        ),
    )
