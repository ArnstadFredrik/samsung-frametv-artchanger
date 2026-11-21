"""Tests for tags, folder filtering and the slideshow."""

import io
import time
import types

import pytest
from PIL import Image
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.samsung_frame_art.const import DOMAIN


TV_IP = "192.168.10.170"


class _FakeTVClient:
    """Records activate calls; snapshots report uploaded content ids."""

    def __init__(self) -> None:
        self.select_calls = []
        self.upload_calls = []

    def snapshot(self, tv_ip: str):
        return types.SimpleNamespace(
            online=True,
            supported=True,
            available_ids={cid for _, cid in self.select_calls} | {cid for _, cid in self.upload_calls},
            available_items={},
            active_id=self.select_calls[-1][1] if self.select_calls else None,
            error=None,
        )

    def upload(self, tv_ip: str, image_bytes: bytes, file_type: str = "JPEG") -> str:
        cid = f"cid-{len(self.upload_calls) + 1}"
        self.upload_calls.append((tv_ip, cid))
        return cid

    def select_image(self, tv_ip: str, content_id: str) -> None:
        self.select_calls.append((tv_ip, content_id))

    def delete_image(self, tv_ip: str, content_id: str) -> bool:
        return True

    def get_thumbnail(self, tv_ip: str, content_id: str) -> bytes:
        buffer = io.BytesIO()
        Image.new("RGB", (64, 36), (1, 2, 3)).save(buffer, format="JPEG")
        return buffer.getvalue()


@pytest.fixture
def hass_config_dir(hass_tmp_config_dir) -> str:
    return hass_tmp_config_dir


@pytest.fixture
def fake_tv(monkeypatch):
    client = _FakeTVClient()
    monkeypatch.setattr("custom_components.samsung_frame_art.TVClient", lambda timeout=8: client)
    return client


def _sample_jpeg(color=(90, 140, 220)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (640, 360), color).save(buffer, format="JPEG")
    return buffer.getvalue()


@pytest.fixture
def mock_entry():
    return MockConfigEntry(
        domain=DOMAIN,
        data={"tv": TV_IP, "automation_token": "t", "media_dir": ""},
    )


def _seed_local_assets(service, count=3, folders=None):
    """Write local files and refresh until the gallery has imported them."""
    import os

    folders = folders or [""] * count
    colors = [(90, 0, 0), (0, 90, 0), (0, 0, 90), (90, 90, 0), (0, 90, 90)]
    for index in range(count):
        folder = folders[index] if index < len(folders) else ""
        directory = os.path.join(service.settings.media_dir, folder) if folder else service.settings.media_dir
        os.makedirs(directory, exist_ok=True)
        with open(os.path.join(directory, f"art_{index}.jpg"), "wb") as handle:
            handle.write(_sample_jpeg(colors[index % len(colors)]))

    # The initial refresh may still be in flight from setup; keep forcing
    # refreshes until the new files are imported.
    deadline = time.time() + 10
    while True:
        service.refresh(force=True, wait=True)
        state = service.store.load()
        asset_ids = [
            asset_id for asset_id, asset in state["assets"].items() if asset.get("ha_rel_path")
        ]
        if len(asset_ids) >= count or time.time() > deadline:
            return asset_ids
        time.sleep(0.2)


@pytest.mark.asyncio
async def test_tags_set_list_and_filter(fake_tv, mock_entry, hass, enable_custom_integrations):
    mock_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()

    service = hass.data[DOMAIN][mock_entry.entry_id]["service"]
    asset_ids = _seed_local_assets(service, count=3)

    def run():
        service.set_asset_tags(asset_ids[0], ["winter", "favorite"])
        service.set_asset_tags(asset_ids[1], ["winter"])
        return (
            service.list_tags(),
            service.list_gallery(tag="winter")["items"],
            service.list_gallery(tag="favorite")["items"],
            service.list_gallery()["items"],
        )

    tags, winter_items, favorite_items, gallery_items = await hass.async_add_executor_job(run)

    assert {entry["tag"]: entry["count"] for entry in tags} == {"winter": 2, "favorite": 1}
    assert len(winter_items) == 2
    assert len(favorite_items) == 1
    assert any("favorite" in item["tags"] for item in gallery_items)

    # Tag replacement (PUT semantics) and validation.
    def run2():
        service.set_asset_tags(asset_ids[0], ["solo"])
        return service.list_tags()

    tags2 = await hass.async_add_executor_job(run2)
    assert {entry["tag"]: entry["count"] for entry in tags2} == {"solo": 1, "winter": 1}


@pytest.mark.asyncio
async def test_folder_metadata_and_filter(fake_tv, mock_entry, hass, enable_custom_integrations):
    mock_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()

    service = hass.data[DOMAIN][mock_entry.entry_id]["service"]
    _seed_local_assets(service, count=3, folders=["", "vacation", "vacation"])

    def run():
        gallery = service.list_gallery()
        folders = gallery["folders"]
        vacation = service.list_gallery(folder="vacation")["items"]
        root = service.list_gallery(folder="")["items"]
        return folders, vacation, root

    folders, vacation, root = await hass.async_add_executor_job(run)

    assert folders == ["vacation"]
    assert len(vacation) == 2
    assert all(item["folder"] == "vacation" for item in vacation)
    assert len(root) == 1
    assert root[0]["folder"] in (None, "")


@pytest.mark.asyncio
async def test_tags_and_slideshow_endpoints(fake_tv, mock_entry, hass, hass_client, enable_custom_integrations):
    mock_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()
    client = await hass_client()

    service = hass.data[DOMAIN][mock_entry.entry_id]["service"]
    asset_ids = await hass.async_add_executor_job(_seed_local_assets, service, 3, None)

    # PUT tags
    resp = await client.put(
        f"/api/samsung_frame_art/items/{asset_ids[0]}/tags",
        json={"tags": ["family", "beach"]},
    )
    assert resp.status == 200
    body = await resp.json()
    assert body["data"]["tags"] == ["family", "beach"]

    # GET tags
    resp = await client.get("/api/samsung_frame_art/tags")
    body = await resp.json()
    assert {"tag": "beach", "count": 1} in body["tags"]

    # Gallery filter by tag over HTTP
    resp = await client.get("/api/samsung_frame_art/gallery?tag=family")
    body = await resp.json()
    assert len(body["data"]["items"]) == 1

    # Slideshow status before start
    resp = await client.get("/api/samsung_frame_art/slideshow")
    assert resp.status == 200
    body = await resp.json()
    assert body["data"]["running"] is False

    # Start (min interval clamps to 5s in the manager)
    resp = await client.post(
        "/api/samsung_frame_art/slideshow/start",
        json={"tag": "family", "interval_seconds": 1, "shuffle": False, "tv_ips": [TV_IP]},
    )
    assert resp.status == 200
    body = await resp.json()
    assert body["data"]["running"] is True
    assert body["data"]["assets_in_rotation"] == 1

    # Wait for the first activation cycle.
    deadline = time.time() + 10
    while time.time() < deadline and not fake_tv.select_calls:
        await hass.async_add_executor_job(time.sleep, 0.2)
    assert fake_tv.select_calls, "slideshow should have activated an image"

    # Skip triggers an immediate extra activation.
    before = len(fake_tv.select_calls)
    resp = await client.post("/api/samsung_frame_art/slideshow/skip")
    assert resp.status == 200
    deadline = time.time() + 10
    while time.time() < deadline and len(fake_tv.select_calls) <= before:
        await hass.async_add_executor_job(time.sleep, 0.2)
    assert len(fake_tv.select_calls) > before

    # Stop
    resp = await client.post("/api/samsung_frame_art/slideshow/stop")
    assert resp.status == 200
    body = await resp.json()
    assert body["data"]["running"] is False

    # Skip while stopped is an error.
    resp = await client.post("/api/samsung_frame_art/slideshow/skip")
    assert resp.status == 400


@pytest.mark.asyncio
async def test_slideshow_start_without_matching_assets(fake_tv, mock_entry, hass, hass_client, enable_custom_integrations):
    mock_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()
    client = await hass_client()

    resp = await client.post(
        "/api/samsung_frame_art/slideshow/start",
        json={"tag": "nope", "interval_seconds": 60},
    )
    assert resp.status == 409
    body = await resp.json()
    assert body["error"]["code"] == "NO_RANDOM_ASSETS"

    # Slideshow thread must not leak: stop is a no-op when not running.
    resp = await client.post("/api/samsung_frame_art/slideshow/stop")
    assert resp.status == 200
