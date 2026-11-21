"""The Samsung Frame TV Art Changer integration.

Brings the Frame TV Art Changer gallery panel and services into Home Assistant
as a custom integration (converted from the original Supervisor add-on).
"""

from __future__ import annotations

import logging
from pathlib import Path

import voluptuous as vol
from homeassistant.components import frontend as frontend_component
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
import homeassistant.helpers.config_validation as cv

from . import http as frame_art_http
from .config import build_settings, parse_tv_ips
from .const import (
    CONF_AUTOMATION_TOKEN,
    CONF_MEDIA_DIR,
    CONF_TV_IPS,
    DEFAULT_MEDIA_SUBDIR,
    DOMAIN,
    PANEL_ICON,
    PANEL_TITLE,
    PANEL_URL_PATH,
)
from .errors import AppError
from .media import MediaService
from .runtime import RuntimeState
from .service import GalleryService
from .store import StateStore
from .tv_client import TVClient

_LOGGER = logging.getLogger(__name__)

SERVICE_RANDOM = "random"
SERVICE_REFRESH = "refresh"
SERVICE_ACTIVATE = "activate"

RANDOM_SCHEMA = vol.Schema(
    {
        vol.Optional("tv_ips"): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional("ensure_upload", default=True): cv.boolean,
        vol.Optional("activate", default=True): cv.boolean,
    }
)

REFRESH_SCHEMA = vol.Schema({vol.Optional("force", default=False): cv.boolean})

ACTIVATE_SCHEMA = vol.Schema(
    {
        vol.Required("asset_id"): cv.string,
        vol.Optional("tv_ips"): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional("ensure_upload", default=True): cv.boolean,
    }
)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up via YAML is not supported; config entry only."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Samsung Frame TV Art Changer from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    data_dir = hass.config.path(DOMAIN)
    media_dir = str(entry.data.get(CONF_MEDIA_DIR) or hass.config.path(DEFAULT_MEDIA_SUBDIR))
    tv_ips = parse_tv_ips(entry.data.get(CONF_TV_IPS))
    automation_token = str(entry.data.get(CONF_AUTOMATION_TOKEN) or "")

    settings = build_settings(
        data_dir=data_dir,
        media_dir=media_dir,
        tv_ips=tv_ips,
        automation_token=automation_token,
    )

    store = StateStore(settings.state_path)
    runtime = RuntimeState(snapshot_ttl_seconds=settings.snapshot_ttl_seconds)
    service = GalleryService(
        settings=settings,
        store=store,
        media_service=MediaService(),
        tv_client=TVClient(),
        runtime=runtime,
    )

    await hass.async_add_executor_job(service.bootstrap)
    await hass.async_add_executor_job(service.trigger_refresh, True, False)

    hass.data[DOMAIN][entry.entry_id] = {"settings": settings, "service": service}

    # Static web assets + panel (registered once, with the first entry).
    if "panel_registered" not in hass.data[DOMAIN]:
        www_dir = Path(__file__).parent / "www"
        await hass.http.async_register_static_paths(
            [StaticPathConfig(f"/{PANEL_URL_PATH}/www", str(www_dir), cache_headers=False)]
        )
        frontend_component.async_register_built_in_panel(
            hass,
            component_name="custom",
            frontend_url_path=PANEL_URL_PATH,
            sidebar_title=PANEL_TITLE,
            sidebar_icon=PANEL_ICON,
            config={
                "_panel_custom": {
                    "name": "samsung-frame-art",
                    "embed_iframe": True,
                    "url_path": f"/{PANEL_URL_PATH}/www/index.html",
                    "sidebar_title": PANEL_TITLE,
                    "sidebar_icon": PANEL_ICON,
                    "trusted": True,
                }
            },
        )
        frame_art_http.async_register_http_views(hass)
        hass.data[DOMAIN]["panel_registered"] = entry.entry_id

    async def handle_random(call: ServiceCall) -> None:
        try:
            await hass.async_add_executor_job(
                lambda: service.random_activate(
                    tv_ips=call.data.get("tv_ips"),
                    ensure_upload=call.data.get("ensure_upload", True),
                    activate=call.data.get("activate", True),
                )
            )
        except AppError as exc:
            raise HomeAssistantError(exc.message) from exc

    async def handle_refresh(call: ServiceCall) -> None:
        await hass.async_add_executor_job(
            lambda: service.refresh(force=call.data.get("force", False), wait=True)
        )

    async def handle_activate(call: ServiceCall) -> None:
        try:
            await hass.async_add_executor_job(
                lambda: service.activate_asset(
                    call.data["asset_id"],
                    tv_ips=call.data.get("tv_ips"),
                    ensure_upload=call.data.get("ensure_upload", True),
                    activate=True,
                )
            )
        except AppError as exc:
            raise HomeAssistantError(exc.message) from exc

    hass.services.async_register(DOMAIN, SERVICE_RANDOM, handle_random, schema=RANDOM_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_REFRESH, handle_refresh, schema=REFRESH_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_ACTIVATE, handle_activate, schema=ACTIVATE_SCHEMA)

    _LOGGER.info("Samsung Frame TV Art Changer set up (TVs: %s)", ", ".join(tv_ips) or "none")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    service = None
    stored = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if isinstance(stored, dict):
        service = stored.get("service")
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)

    if hass.data.get(DOMAIN, {}).get("panel_registered") == entry.entry_id:
        frontend_component.async_remove_panel(hass, PANEL_URL_PATH, warn_if_unknown=False)
        hass.data[DOMAIN].pop("panel_registered", None)
        for service_name in (SERVICE_RANDOM, SERVICE_REFRESH, SERVICE_ACTIVATE):
            hass.services.async_remove(DOMAIN, service_name)

    if service is not None:
        await hass.async_add_executor_job(service.stop)

    return True
