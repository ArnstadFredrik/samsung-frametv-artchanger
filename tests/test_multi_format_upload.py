"""Multi-format upload tests: non-JPG/PNG inputs are converted to TV-format JPEG."""

import io
import os
import types

import aiohttp
import pytest
from PIL import Image
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.samsung_frame_art.const import DOMAIN
from custom_components.samsung_frame_art.media import TARGET_HEIGHT, TARGET_WIDTH, MediaService


TV_IP = "192.168.10.170"


class _OfflineTVClient:
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


@pytest.fixture(autouse=True)
def patch_tv_client(monkeypatch):
    monkeypatch.setattr("custom_components.samsung_frame_art.TVClient", _OfflineTVClient)


@pytest.fixture
def mock_entry():
    return MockConfigEntry(
        domain=DOMAIN,
        title="Samsung Frame TV Art Changer",
        data={"tv": TV_IP, "automation_token": "secret-token", "media_dir": ""},
    )


def _image_bytes(fmt: str, size=(640, 360), color=None) -> bytes:
    # Distinct pixel data per format: uploads are deduplicated by content hash.
    if color is None:
        palette = {
            "PNG": (10, 120, 200),
            "WEBP": (20, 130, 210),
            "GIF": (30, 140, 220),
            "BMP": (40, 150, 230),
            "TIFF": (50, 160, 240),
            "AVIF": (60, 170, 250),
            "JPEG": (70, 180, 255),
        }
        color = palette.get(fmt, (10, 120, 200))
    image = Image.new("RGB", size, color)
    buffer = io.BytesIO()
    image.save(buffer, format=fmt)
    return buffer.getvalue()


def test_prepare_image_converts_all_formats():
    service = MediaService()

    formats = ["PNG", "WEBP", "GIF", "BMP", "TIFF", "AVIF", "JPEG"]
    for fmt in formats:
        payload, digest = service.prepare_image(_image_bytes(fmt))
        assert len(payload) > 0, fmt
        image = Image.open(io.BytesIO(payload))
        assert image.format == "JPEG", fmt
        assert image.size == (TARGET_WIDTH, TARGET_HEIGHT), fmt
        assert len(digest) == 64, fmt


@pytest.mark.skipif(
    not __import__("custom_components.samsung_frame_art.media", fromlist=["HEIF_SUPPORTED"]).HEIF_SUPPORTED,
    reason="pillow-heif not available",
)
def test_prepare_image_converts_heic():
    import pillow_heif

    service = MediaService()
    image = Image.new("RGB", (640, 360), (200, 10, 10))
    buffer = io.BytesIO()
    pillow_heif.from_pillow(image).save(buffer, format="HEIF")
    payload, _ = service.prepare_image(buffer.getvalue())
    out = Image.open(io.BytesIO(payload))
    assert out.format == "JPEG"
    assert out.size == (TARGET_WIDTH, TARGET_HEIGHT)


@pytest.mark.asyncio
async def test_upload_endpoint_accepts_new_formats(hass, hass_client, enable_custom_integrations):
    entry = MockConfigEntry(
        domain=DOMAIN, data={"tv": TV_IP, "automation_token": "t", "media_dir": ""}
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    client = await hass_client()
    service = hass.data[DOMAIN][entry.entry_id]["service"]

    for fmt in ["WEBP", "GIF", "BMP", "TIFF", "AVIF"]:
        form = aiohttp.FormData()
        form.add_field(
            "file", _image_bytes(fmt), filename=f"photo.{fmt.lower()}", content_type="image/jpeg"
        )
        resp = await client.post("/api/samsung_frame_art/upload", data=form)
        assert resp.status == 200, fmt
        body = await resp.json()
        assert body["data"]["duplicate"] is False, fmt
        # Stored file is the converted TV-format JPEG.
        stored = os.path.join(service.settings.media_dir, body["data"]["asset"]["filename"])
        assert stored.endswith(".jpg"), fmt
        assert os.path.exists(stored), fmt
        with open(stored, "rb") as handle:
            img = Image.open(handle)
            assert img.format == "JPEG", fmt
            assert img.size == (TARGET_WIDTH, TARGET_HEIGHT), fmt


@pytest.mark.asyncio
async def test_preview_endpoint_converts_unrenderable_formats(hass, hass_client, enable_custom_integrations):
    import pillow_heif

    entry = MockConfigEntry(
        domain=DOMAIN, data={"tv": TV_IP, "automation_token": "t", "media_dir": ""}
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    client = await hass_client()

    async def preview(fmt: str, filename: str, payload: bytes):
        form = aiohttp.FormData()
        form.add_field("file", payload, filename=filename, content_type="application/octet-stream")
        resp = await client.post("/api/samsung_frame_art/preview", data=form)
        return resp

    # TIFF: browsers do not render it in <img>.
    resp = await preview("TIFF", "photo.tiff", _image_bytes("TIFF"))
    assert resp.status == 200
    assert resp.headers["Content-Type"].startswith("image/jpeg")
    out = Image.open(io.BytesIO(await resp.read()))
    assert out.format == "JPEG"
    assert out.size == (640, 360)  # full resolution kept for crop coordinates

    # HEIC: browsers (except Safari) do not render it in <img>.
    heif_image = Image.new("RGB", (640, 360), (200, 10, 10))
    heif_buffer = io.BytesIO()
    pillow_heif.from_pillow(heif_image).save(heif_buffer, format="HEIF")
    resp = await preview("HEIC", "photo.heic", heif_buffer.getvalue())
    assert resp.status == 200
    out = Image.open(io.BytesIO(await resp.read()))
    assert out.format == "JPEG"
    assert out.size == (640, 360)


@pytest.mark.asyncio
async def test_upload_endpoint_rejects_unsupported_format(hass, hass_client, enable_custom_integrations):
    entry = MockConfigEntry(
        domain=DOMAIN, data={"tv": TV_IP, "automation_token": "t", "media_dir": ""}
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    client = await hass_client()

    form = aiohttp.FormData()
    form.add_field("file", b"not-an-image", filename="photo.svg", content_type="image/svg+xml")
    resp = await client.post("/api/samsung_frame_art/upload", data=form)
    assert resp.status == 400
    body = await resp.json()
    assert body["error"]["code"] == "INVALID_INPUT"
    assert "svg" in body["error"]["message"]
