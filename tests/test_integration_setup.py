"""End-to-end setup tests: config entry setup, panel, services and HTTP API."""

import os
import types

import aiohttp
import pytest

from homeassistant.components.frontend import async_panel_exists
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.samsung_frame_art.const import DOMAIN


TV_IP = "192.168.10.170"


class _OfflineTVClient:
    """Deterministic TV client stub: every TV is offline, no sockets are opened."""

    def __init__(self, timeout: int = 8) -> None:
        self.timeout = timeout

    def snapshot(self, tv_ip: str):
        return types.SimpleNamespace(
            online=False,
            supported=False,
            available_ids=set(),
            available_items={},
            active_id=None,
            error="offline (test stub)",
        )

    def upload(self, tv_ip: str, image_bytes: bytes, file_type: str = "JPEG") -> str:
        raise RuntimeError("offline (test stub)")

    def select_image(self, tv_ip: str, content_id: str) -> None:
        raise RuntimeError("offline (test stub)")

    def delete_image(self, tv_ip: str, content_id: str) -> bool:
        raise RuntimeError("offline (test stub)")

    def get_thumbnail(self, tv_ip: str, content_id: str) -> bytes:
        raise RuntimeError("offline (test stub)")


@pytest.fixture(autouse=True)
def patch_tv_client(monkeypatch):
    monkeypatch.setattr("custom_components.samsung_frame_art.TVClient", _OfflineTVClient)


@pytest.fixture
def hass_config_dir(hass_tmp_config_dir) -> str:
    """Give every test its own config directory so state never leaks between tests."""
    return hass_tmp_config_dir


@pytest.fixture
def mock_entry():
    return MockConfigEntry(
        domain=DOMAIN,
        title="Samsung Frame TV Art Changer",
        data={
            "tv": TV_IP,
            "automation_token": "secret-token",
            "media_dir": "",
        },
    )


@pytest.mark.asyncio
async def test_setup_entry_registers_panel_services_and_views(hass, hass_client, mock_entry, enable_custom_integrations):
    mock_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()

    # Panel registered in the sidebar
    try:
        panel_exists = async_panel_exists(hass, DOMAIN)
    except ImportError:  # older HA versions
        panel_exists = DOMAIN in hass.data.get("frontend_panels", {})
    assert panel_exists

    # Services registered
    services = hass.services.async_services().get(DOMAIN, {})
    assert {"random", "refresh", "activate"} <= set(services)

    # Static path served
    client = await hass_client()
    resp = await client.get("/samsung_frame_art/www/index.html")
    assert resp.status == 200
    assert b"Frame Art Gallery" in await resp.read()

    resp = await client.get("/samsung_frame_art/www/app.js")
    assert resp.status == 200

    # HTTP views registered: health endpoint responds
    resp = await client.get("/api/samsung_frame_art/health")
    assert resp.status == 200
    body = await resp.json()
    assert body["data"]["ok"] is True
    assert body["data"]["tv_count"] == 1
    assert "meta" in body


@pytest.mark.asyncio
async def test_gallery_and_tvs_endpoints(hass, hass_client, mock_entry, enable_custom_integrations):
    mock_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()

    client = await hass_client()

    resp = await client.get("/api/samsung_frame_art/gallery?filter=all")
    assert resp.status == 200
    body = await resp.json()
    assert body["data"]["items"] == []
    assert body["data"]["tv_status"][TV_IP]["online"] is False

    resp = await client.get("/api/samsung_frame_art/tvs")
    assert resp.status == 200
    body = await resp.json()
    assert body["data"]["tvs"][0]["ip"] == TV_IP

    resp = await client.get("/api/samsung_frame_art/settings")
    assert resp.status == 200
    body = await resp.json()
    assert body["data"]["tv_ips"] == [TV_IP]


@pytest.mark.asyncio
async def test_settings_update_endpoint(hass, hass_client, mock_entry, enable_custom_integrations):
    mock_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()

    client = await hass_client()

    resp = await client.put(
        "/api/samsung_frame_art/settings",
        json={"tv_ips": [TV_IP, "192.168.10.171"], "refresh_interval_seconds": 60, "snapshot_ttl_seconds": 10},
    )
    assert resp.status == 200
    body = await resp.json()
    assert body["data"]["tv_ips"] == [TV_IP, "192.168.10.171"]
    assert body["data"]["refresh_interval_seconds"] == 60

    resp = await client.get("/api/samsung_frame_art/settings")
    body = await resp.json()
    assert body["data"]["refresh_interval_seconds"] == 60


@pytest.mark.asyncio
async def test_automation_random_requires_bearer_token(hass, hass_client, mock_entry, enable_custom_integrations):
    mock_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()

    client = await hass_client()

    resp = await client.post("/api/samsung_frame_art/automation/random", json={})
    assert resp.status == 401
    body = await resp.json()
    assert body["error"]["code"] == "UNAUTHORIZED"

    resp = await client.post(
        "/api/samsung_frame_art/automation/random",
        json={},
        headers={"Authorization": "Bearer wrong"},
    )
    assert resp.status == 401

    resp = await client.post(
        "/api/samsung_frame_art/automation/random",
        json={"tv_ips": [TV_IP]},
        headers={"Authorization": "Bearer secret-token"},
    )
    # No local assets -> NO_RANDOM_ASSETS (409), proving token check passed.
    assert resp.status == 409
    body = await resp.json()
    assert body["error"]["code"] == "NO_RANDOM_ASSETS"


@pytest.mark.asyncio
async def test_upload_endpoint(hass, hass_client, mock_entry, enable_custom_integrations):
    import io

    from PIL import Image

    mock_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()

    client = await hass_client()

    image = Image.new("RGB", (320, 180), (10, 120, 200))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    payload = buffer.getvalue()

    form = aiohttp.FormData()
    form.add_field("file", payload, filename="photo.jpg", content_type="image/jpeg")
    resp = await client.post("/api/samsung_frame_art/upload", data=form)
    assert resp.status == 200
    body = await resp.json()
    assert body["data"]["duplicate"] is False
    asset = body["data"]["asset"]
    assert asset["source"] == "upload"
    assert asset["ha_rel_path"].endswith(".jpg")

    # The prepared image must exist on disk in the media folder.
    media_dir = hass.config.path(DOMAIN.split("_")[0] + "_art")  # not used; read from service
    service = hass.data[DOMAIN][mock_entry.entry_id]["service"]
    path = os.path.join(service.settings.media_dir, asset["filename"])
    assert os.path.exists(path)

    # Uploading the same bytes again is detected as a duplicate.
    form = aiohttp.FormData()
    form.add_field("file", payload, filename="photo.jpg", content_type="image/jpeg")
    resp = await client.post("/api/samsung_frame_art/upload", data=form)
    body = await resp.json()
    assert body["data"]["duplicate"] is True

    # Thumbnail endpoint serves the stored image.
    resp = await client.get(f"/api/samsung_frame_art/thumb/{asset['asset_id']}")
    assert resp.status == 200
    assert resp.headers["Content-Type"].startswith("image/jpeg")


@pytest.mark.asyncio
async def test_unload_removes_panel_and_services(hass, mock_entry, enable_custom_integrations):
    mock_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()
    assert async_panel_exists(hass, DOMAIN)

    assert await hass.config_entries.async_unload(mock_entry.entry_id)
    await hass.async_block_till_done()

    assert not async_panel_exists(hass, DOMAIN)
    services = hass.services.async_services().get(DOMAIN, {})
    assert "random" not in services
