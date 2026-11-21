"""Slideshow: periodically activate gallery assets on the Frame TV(s).

Runs in a daemon thread inside the integration (same threading model as the
gallery refresh), cycling through a filtered selection of local gallery
assets. The selection can be narrowed by tag and/or media-folder.
"""

from __future__ import annotations

import logging
import random
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from .const import (
    SLIDESHOW_DEFAULT_INTERVAL_SECONDS,
    SLIDESHOW_MAX_CONSECUTIVE_FAILURES,
    SLIDESHOW_MAX_INTERVAL_SECONDS,
    SLIDESHOW_MIN_INTERVAL_SECONDS,
)

_LOGGER = logging.getLogger(__name__)


class SlideshowManager:
    """Cycles gallery assets on the configured TVs until stopped."""

    def __init__(self, activate: Callable[..., Dict[str, Any]], list_assets: Callable[..., List[str]]) -> None:
        self._activate = activate
        self._list_assets = list_assets

        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._skip_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        self._config: Dict[str, Any] = {}
        self._order: List[str] = []
        self._index = 0
        self._current_asset_id: Optional[str] = None
        self._current_filename: Optional[str] = None
        self._last_error: Optional[str] = None
        self._shown_count = 0
        self._consecutive_failures = 0
        self._started_at: Optional[float] = None

    # ------------------------------------------------------------------ API

    def status(self) -> Dict[str, Any]:
        with self._lock:
            running = self._thread is not None and self._thread.is_alive()
            return {
                "running": running,
                "config": dict(self._config),
                "assets_in_rotation": len(self._order),
                "index": self._index,
                "current_asset_id": self._current_asset_id,
                "current_filename": self._current_filename,
                "shown_count": self._shown_count,
                "consecutive_failures": self._consecutive_failures,
                "last_error": self._last_error,
            }

    def start(
        self,
        tv_ips: Optional[List[str]],
        tag: Optional[str],
        folder: Optional[str],
        interval_seconds: int,
        shuffle: bool,
    ) -> Dict[str, Any]:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                # Restart with the new configuration.
                self._stop_event.set()

        interval = max(SLIDESHOW_MIN_INTERVAL_SECONDS, min(SLIDESHOW_MAX_INTERVAL_SECONDS, int(interval_seconds)))

        asset_ids = self._list_assets(tag=tag, folder=folder)
        if not asset_ids:
            from .errors import NoRandomAssetsError

            raise NoRandomAssetsError("No gallery images match the selected collection")

        if shuffle:
            random.shuffle(asset_ids)
        else:
            asset_ids.sort()

        with self._lock:
            self._config = {
                "tv_ips": list(tv_ips) if tv_ips else None,
                "tag": tag,
                "folder": folder,
                "interval_seconds": interval,
                "shuffle": bool(shuffle),
            }
            self._order = asset_ids
            self._index = 0
            self._current_asset_id = None
            self._current_filename = None
            self._last_error = None
            self._shown_count = 0
            self._consecutive_failures = 0
            self._started_at = time.time()

            self._stop_event = threading.Event()
            self._skip_event = threading.Event()
            thread = threading.Thread(
                target=self._run,
                daemon=True,
                name="frame-art-slideshow",
            )
            self._thread = thread

        thread.start()
        return self.status()

    def stop(self) -> Dict[str, Any]:
        with self._lock:
            if self._thread is not None:
                self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=15.0)
        return self.status()

    def skip(self) -> Dict[str, Any]:
        with self._lock:
            running = self._thread is not None and self._thread.is_alive()
            if not running:
                from .errors import InvalidInputError

                raise InvalidInputError("Slideshow is not running")
            self._skip_event.set()
            # Wake the wait loop early.
        return self.status()

    # ------------------------------------------------------------- internals

    def _run(self) -> None:
        _LOGGER.info("Slideshow started: %s", self._config)
        try:
            while not self._stop_event.is_set():
                self._show_next()
                if self._stop_event.is_set():
                    break

                interval = max(5, int(self._config.get("interval_seconds", SLIDESHOW_DEFAULT_INTERVAL_SECONDS)))
                # Back off on failures so a slow/overloaded TV gets room to
                # recover instead of being hammered at the configured interval.
                with self._lock:
                    failures = self._consecutive_failures
                effective = interval if failures == 0 else max(interval, min(interval * failures, 300))
                waited = 0.0
                while waited < effective and not self._stop_event.is_set() and not self._skip_event.is_set():
                    time.sleep(0.5)
                    waited += 0.5
                self._skip_event.clear()
        finally:
            _LOGGER.info("Slideshow stopped")
            with self._lock:
                if self._thread is threading.current_thread():
                    self._thread = None

    def _show_next(self) -> None:
        with self._lock:
            if not self._order:
                self._stop_event.set()
                return
            if self._index >= len(self._order):
                # Wrap around; reshuffle if configured.
                if self._config.get("shuffle"):
                    random.shuffle(self._order)
                self._index = 0
            asset_id = self._order[self._index]
            self._index += 1

        try:
            # Slideshow activations skip the trailing force-refresh: with short
            # intervals it would hammer the TV with constant full re-scans. The
            # next gallery refresh picks up the state anyway.
            result = self._activate(
                asset_id,
                tv_ips=self._config.get("tv_ips"),
                ensure_upload=True,
                activate=True,
                trigger_refresh=False,
            )
            all_ok = bool(result.get("results")) and all(
                entry.get("ok") for entry in result.get("results", {}).values()
            )
            with self._lock:
                self._current_asset_id = asset_id
                self._shown_count += 1
                if all_ok:
                    self._consecutive_failures = 0
                    self._last_error = None
                else:
                    self._consecutive_failures += 1
                    errors = [
                        entry.get("error") or entry.get("code") or "unknown error"
                        for entry in result.get("results", {}).values()
                        if not entry.get("ok")
                    ]
                    self._last_error = "; ".join(errors)[:200]
        except Exception as exc:  # noqa: BLE001 - keep the slideshow alive
            _LOGGER.warning("Slideshow activation failed for %s: %s", asset_id, exc)
            with self._lock:
                self._consecutive_failures += 1
                self._last_error = str(exc)[:200]

        with self._lock:
            if self._consecutive_failures >= SLIDESHOW_MAX_CONSECUTIVE_FAILURES:
                _LOGGER.error(
                    "Slideshow stopping after %s consecutive failures: %s",
                    self._consecutive_failures,
                    self._last_error,
                )
                self._stop_event.set()
