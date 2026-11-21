"""HTTP API for the Samsung Frame TV Art Changer integration.

Re-implements the original add-on's FastAPI endpoints as Home Assistant
aiohttp views, keeping the same JSON envelope ({"data": ..., "meta": ...})
so the bundled web UI only needs a different URL prefix.
"""

from __future__ import annotations

import logging
import os
import secrets
import uuid
from typing import Any, Dict, Optional

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .config import parse_tv_ips
from .const import (
    DOMAIN,
    SLIDESHOW_MAX_INTERVAL_SECONDS,
    SLIDESHOW_MIN_INTERVAL_SECONDS,
    SUPPORTED_UPLOAD_EXTENSIONS,
)
from .errors import AppError, InvalidInputError, UnauthorizedError, error_payload
from .schemas import (
    ActivateRequest,
    DeleteRequest,
    RandomRequest,
    parse_crop,
    parse_settings_update,
    parse_slideshow_start,
)

_LOGGER = logging.getLogger(__name__)

BASE_URL = "/api/samsung_frame_art"


def _service(request: web.Request):
    hass: HomeAssistant = request.app["hass"]
    entries = hass.data[DOMAIN]
    # Single-config-entry integration: use the first entry.
    entry_id = next(iter(entries))
    return entries[entry_id]["service"], hass


def _run_in_executor(hass: HomeAssistant, func):
    return hass.async_add_executor_job(func)


def _json_error(
    status: int,
    code: str,
    message: str,
    retryable: bool,
    request_id: str,
) -> web.Response:
    return web.json_response(
        error_payload(code=code, message=message, retryable=retryable, request_id=request_id),
        status=status,
        headers={"X-Request-ID": request_id},
    )


def _with_meta(
    request: web.Request,
    service,
    data: Dict[str, Any],
    compatibility: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    meta = service.get_meta(request_id)
    payload: Dict[str, Any] = {"data": data, "meta": meta}
    if compatibility:
        payload.update(compatibility)
    return payload


def _sync_handler(func):
    """Run a blocking handler function in the executor and map AppError to JSON."""

    async def handler(self, request: web.Request, **kwargs) -> web.StreamResponse:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        try:
            hass: HomeAssistant = request.app["hass"]
            payload = await _run_in_executor(hass, lambda: func(self, request))
            if isinstance(payload, web.StreamResponse):
                return payload
            return web.json_response(payload, headers={"X-Request-ID": request_id})
        except AppError as exc:
            return _json_error(exc.status, exc.code, exc.message, exc.retryable, request_id)
        except web.HTTPException:
            raise
        except Exception as exc:  # pragma: no cover - defensive
            _LOGGER.exception("Unhandled API error: %s", exc)
            return _json_error(500, "INTERNAL_ERROR", "Internal server error", False, request_id)

    return handler


def _async_handler(func):
    """Wrap an async handler and map AppError to JSON error responses."""

    async def handler(self, request: web.Request, **kwargs) -> web.Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        try:
            return await func(self, request)
        except AppError as exc:
            return _json_error(exc.status, exc.code, exc.message, exc.retryable, request_id)
        except web.HTTPException:
            raise
        except Exception as exc:  # pragma: no cover - defensive
            _LOGGER.exception("Unhandled API error: %s", exc)
            return _json_error(500, "INTERNAL_ERROR", "Internal server error", False, request_id)

    return handler


async def _read_json_body(request: web.Request) -> Dict[str, Any]:
    try:
        body = await request.json()
    except Exception:
        body = None
    return body if isinstance(body, dict) else {}


class FrameArtHealthView(HomeAssistantView):
    url = f"{BASE_URL}/health"
    name = "api:samsung_frame_art:health"

    @_sync_handler
    def get(self, request: web.Request) -> Dict[str, Any]:
        service, _ = _service(request)
        settings = service.settings
        data = {
            "ok": True,
            "tv_count": len(settings.tv_ips),
            "media_dir": settings.media_dir,
        }
        return _with_meta(request, service, data, compatibility=data)


class FrameArtTvsView(HomeAssistantView):
    url = f"{BASE_URL}/tvs"
    name = "api:samsung_frame_art:tvs"

    @_sync_handler
    def get(self, request: web.Request) -> Dict[str, Any]:
        service, _ = _service(request)
        tvs = service.list_tvs(trigger_refresh=True)
        return _with_meta(request, service, {"tvs": tvs}, compatibility={"tvs": tvs})


class FrameArtSettingsView(HomeAssistantView):
    url = f"{BASE_URL}/settings"
    name = "api:samsung_frame_art:settings"

    @_sync_handler
    def get(self, request: web.Request) -> Dict[str, Any]:
        service, _ = _service(request)
        payload = service.get_runtime_settings()
        return _with_meta(request, service, payload, compatibility=payload)

    async def put(self, request: web.Request) -> web.Response:
        body = await _read_json_body(request)
        hass: HomeAssistant = request.app["hass"]
        service, _ = _service(request)
        payload = parse_settings_update(body)
        updated = await _run_in_executor(
            hass,
            lambda: service.update_runtime_settings(
                tv_ips=payload.tv_ips,
                refresh_interval_seconds=payload.refresh_interval_seconds,
                snapshot_ttl_seconds=payload.snapshot_ttl_seconds,
            ),
        )
        return web.json_response(_with_meta(request, service, updated, compatibility=updated))

    async def _wrapped_put(self, request: web.Request) -> web.Response:
        return await self.put(request)


class FrameArtDiscoverView(HomeAssistantView):
    url = f"{BASE_URL}/settings/discover"
    name = "api:samsung_frame_art:discover"

    @_async_handler
    async def post(self, request: web.Request) -> web.Response:
        body = await _read_json_body(request)
        subnet = body.get("subnet") if body else None
        service, hass = _service(request)
        result = await _run_in_executor(hass, lambda: service.discover_supported_tvs(subnet=subnet))
        return web.json_response(_with_meta(request, service, result, compatibility=result))


class FrameArtGalleryView(HomeAssistantView):
    url = f"{BASE_URL}/gallery"
    name = "api:samsung_frame_art:gallery"

    @_sync_handler
    def get(self, request: web.Request) -> Dict[str, Any]:
        service, _ = _service(request)
        filter_name = request.query.get("filter", "all")
        tv_ip = request.query.get("tv_ip") or None
        tag = request.query.get("tag") or None
        folder = request.query.get("folder")
        folder = None if folder in (None, "") else folder
        gallery = service.list_gallery(
            filter_name=filter_name, tv_ip=tv_ip, trigger_refresh=True, tag=tag, folder=folder
        )
        return _with_meta(request, service, gallery, compatibility=gallery)


class FrameArtRefreshView(HomeAssistantView):
    url = f"{BASE_URL}/refresh"
    name = "api:samsung_frame_art:refresh"

    @_sync_handler
    def post(self, request: web.Request) -> Dict[str, Any]:
        service, _ = _service(request)
        started = service.trigger_refresh(force=True, wait=False)
        gallery = service.list_gallery(filter_name="all", trigger_refresh=False)
        compatibility = dict(gallery)
        compatibility["refresh_triggered"] = started
        data = {"refresh_triggered": started, "gallery": gallery}
        return _with_meta(request, service, data, compatibility=compatibility)


class FrameArtThumbView(HomeAssistantView):
    url = f"{BASE_URL}/thumb/{'{asset_id}'}"
    name = "api:samsung_frame_art:thumb"

    @_sync_handler
    def get(self, request: web.Request) -> web.Response:
        service, _ = _service(request)
        asset_id = request.match_info["asset_id"]
        image = service.read_thumbnail(asset_id)
        return web.Response(body=image, content_type="image/jpeg")


class FrameArtUploadView(HomeAssistantView):
    url = f"{BASE_URL}/upload"
    name = "api:samsung_frame_art:upload"

    @_async_handler
    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        service, _ = _service(request)

        post = await request.post()
        upload = post.get("file")
        if not isinstance(upload, web.FileField):
            raise InvalidInputError("Missing file field")

        filename = upload.filename or ""
        ext = os.path.splitext(filename)[1].lower()
        if ext not in SUPPORTED_UPLOAD_EXTENSIONS:
            raise InvalidInputError(
                "Unsupported image format: "
                f"{ext or 'unknown'}. Supported: "
                + ", ".join(sorted(SUPPORTED_UPLOAD_EXTENSIONS))
            )

        payload = upload.file.read()
        if not payload:
            raise InvalidInputError("Uploaded file is empty")

        crop_data = parse_crop(post.get("crop"))
        selected_tvs = parse_tv_ips(post.get("tv_ips"))
        should_activate = str(post.get("activate", "")).strip().lower() in {"1", "true", "yes", "on"}

        result = await _run_in_executor(
            hass,
            lambda: service.upload_image(
                file_bytes=payload,
                crop=crop_data,
                activate=should_activate,
                tv_ips=selected_tvs,
            ),
        )

        response = {
            "asset": result.asset,
            "duplicate": result.duplicate,
            "activation": result.activation,
        }
        return web.json_response(_with_meta(request, service, response, compatibility=response))


class FrameArtActivateView(HomeAssistantView):
    url = f"{BASE_URL}/items/{'{asset_id}'}/activate"
    name = "api:samsung_frame_art:activate"

    @_async_handler
    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        service, _ = _service(request)
        asset_id = request.match_info["asset_id"]
        body = await _read_json_body(request)

        payload = ActivateRequest(
            tv_ips=body.get("tv_ips"),
            ensure_upload=bool(body.get("ensure_upload", True)),
            activate=bool(body.get("activate", True)),
        )

        result = await _run_in_executor(
            hass,
            lambda: service.activate_asset(
                asset_id,
                tv_ips=payload.tv_ips,
                ensure_upload=payload.ensure_upload,
                activate=payload.activate,
            ),
        )
        return web.json_response(_with_meta(request, service, result, compatibility=result))


class FrameArtDeleteView(HomeAssistantView):
    url = f"{BASE_URL}/items/{'{asset_id}'}"
    name = "api:samsung_frame_art:delete"

    @_async_handler
    async def delete(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        service, _ = _service(request)
        asset_id = request.match_info["asset_id"]
        body = await _read_json_body(request)

        payload = DeleteRequest(
            targets=str(body.get("targets", "both")),
            tv_ips=body.get("tv_ips"),
        )

        result = await _run_in_executor(
            hass,
            lambda: service.delete_asset(asset_id, targets=payload.targets, tv_ips=payload.tv_ips),
        )
        return web.json_response(_with_meta(request, service, result, compatibility=result))


class FrameArtPreviewView(HomeAssistantView):
    """Convert an uploaded image to a browser-renderable JPEG crop preview.

    Needed because browsers cannot decode HEIC/HEIF/TIFF in <img> elements.
    """

    url = f"{BASE_URL}/preview"
    name = "api:samsung_frame_art:preview"

    @_async_handler
    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        service, _ = _service(request)

        post = await request.post()
        upload = post.get("file")
        if not isinstance(upload, web.FileField):
            raise InvalidInputError("Missing file field")

        filename = upload.filename or ""
        ext = os.path.splitext(filename)[1].lower()
        if ext not in SUPPORTED_UPLOAD_EXTENSIONS:
            raise InvalidInputError(
                "Unsupported image format: "
                f"{ext or 'unknown'}. Supported: "
                + ", ".join(sorted(SUPPORTED_UPLOAD_EXTENSIONS))
            )

        payload = upload.file.read()
        if not payload:
            raise InvalidInputError("Uploaded file is empty")

        preview = await _run_in_executor(hass, lambda: service.media_service.build_preview(payload))
        return web.Response(body=preview, content_type="image/jpeg")


class FrameArtTagsView(HomeAssistantView):
    url = f"{BASE_URL}/tags"
    name = "api:samsung_frame_art:tags"

    @_sync_handler
    def get(self, request: web.Request) -> Dict[str, Any]:
        service, _ = _service(request)
        return {"tags": service.list_tags()}


class FrameArtItemTagsView(HomeAssistantView):
    url = f"{BASE_URL}/items/{'{asset_id}'}/tags"
    name = "api:samsung_frame_art:item_tags"

    @_async_handler
    async def put(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        service, _ = _service(request)
        asset_id = request.match_info["asset_id"]
        body = await _read_json_body(request)

        tags = body.get("tags")
        if not isinstance(tags, list) or not all(isinstance(item, str) for item in tags):
            raise InvalidInputError("tags must be a list of strings")

        result = await _run_in_executor(hass, lambda: service.set_asset_tags(asset_id, tags))
        return web.json_response(_with_meta(request, service, result, compatibility=result))


class FrameArtSlideshowView(HomeAssistantView):
    url = f"{BASE_URL}/slideshow"
    name = "api:samsung_frame_art:slideshow"

    @_sync_handler
    def get(self, request: web.Request) -> Dict[str, Any]:
        service, _ = _service(request)
        status = service.slideshow.status()
        return _with_meta(request, service, status, compatibility=status)


class FrameArtSlideshowStartView(HomeAssistantView):
    url = f"{BASE_URL}/slideshow/start"
    name = "api:samsung_frame_art:slideshow_start"

    @_async_handler
    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        service, _ = _service(request)
        body = await _read_json_body(request)

        config = parse_slideshow_start(body)
        result = await _run_in_executor(
            hass,
            lambda: service.slideshow.start(
                tv_ips=config.tv_ips,
                tag=config.tag,
                folder=config.folder,
                interval_seconds=config.interval_seconds,
                shuffle=config.shuffle,
            ),
        )
        return web.json_response(_with_meta(request, service, result, compatibility=result))


class FrameArtSlideshowStopView(HomeAssistantView):
    url = f"{BASE_URL}/slideshow/stop"
    name = "api:samsung_frame_art:slideshow_stop"

    @_sync_handler
    def post(self, request: web.Request) -> Dict[str, Any]:
        service, _ = _service(request)
        status = service.slideshow.stop()
        return _with_meta(request, service, status, compatibility=status)


class FrameArtSlideshowSkipView(HomeAssistantView):
    url = f"{BASE_URL}/slideshow/skip"
    name = "api:samsung_frame_art:slideshow_skip"

    @_sync_handler
    def post(self, request: web.Request) -> Dict[str, Any]:
        service, _ = _service(request)
        status = service.slideshow.skip()
        return _with_meta(request, service, status, compatibility=status)


class FrameArtAutomationRandomView(HomeAssistantView):
    """Bearer-token protected endpoint for HA automations (same as the add-on)."""

    url = f"{BASE_URL}/automation/random"
    name = "api:samsung_frame_art:automation_random"
    requires_auth = False

    @_async_handler
    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        service, _ = _service(request)

        configured_token = (service.settings.automation_token or "").strip()
        if not configured_token:
            raise UnauthorizedError("automation_token is not configured")

        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            raise UnauthorizedError("Missing bearer token")
        token = header[len("Bearer ") :].strip()
        if not secrets.compare_digest(token, configured_token):
            raise UnauthorizedError("Invalid bearer token")

        body = await _read_json_body(request)
        payload = RandomRequest(
            tv_ips=body.get("tv_ips"),
            ensure_upload=bool(body.get("ensure_upload", True)),
            activate=bool(body.get("activate", True)),
        )

        result = await _run_in_executor(
            hass,
            lambda: service.random_activate(
                tv_ips=payload.tv_ips,
                ensure_upload=payload.ensure_upload,
                activate=payload.activate,
            ),
        )
        return web.json_response(_with_meta(request, service, result, compatibility=result))


def async_register_http_views(hass: HomeAssistant) -> None:
    hass.http.register_view(FrameArtHealthView())
    hass.http.register_view(FrameArtTvsView())
    hass.http.register_view(FrameArtSettingsView())
    hass.http.register_view(FrameArtDiscoverView())
    hass.http.register_view(FrameArtGalleryView())
    hass.http.register_view(FrameArtRefreshView())
    hass.http.register_view(FrameArtThumbView())
    hass.http.register_view(FrameArtUploadView())
    hass.http.register_view(FrameArtPreviewView())
    hass.http.register_view(FrameArtActivateView())
    hass.http.register_view(FrameArtDeleteView())
    hass.http.register_view(FrameArtTagsView())
    hass.http.register_view(FrameArtItemTagsView())
    hass.http.register_view(FrameArtSlideshowView())
    hass.http.register_view(FrameArtSlideshowStartView())
    hass.http.register_view(FrameArtSlideshowStopView())
    hass.http.register_view(FrameArtSlideshowSkipView())
    hass.http.register_view(FrameArtAutomationRandomView())
