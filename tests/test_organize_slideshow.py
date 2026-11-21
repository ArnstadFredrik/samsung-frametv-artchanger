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
def fake_tv(monkeypatch):
    client = _FakeTVClient()
    monkeypatch.setattr("custom_components.samsung_frame_art.TVClient", lambda timeout=8, token_dir=None: client)
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
        import os

        media_files = []
        for root, _, files in os.walk(service.settings.media_dir):
            for name in files:
                media_files.append(os.path.relpath(os.path.join(root, name), service.settings.media_dir))
        state = service.store.load()
        return (
            gallery["folders"],
            gallery["items"],
            sorted(media_files),
            [(a.get("filename"), a.get("ha_rel_path")) for a in state["assets"].values()],
            service.settings.media_dir,
        )

    folders, items, media_files, stored_assets, media_dir = await hass.async_add_executor_job(run)

    assert folders == ["vacation"], (
        f"media_dir={media_dir} media_files={media_files} stored_assets={stored_assets} items={items}"
    )
    vacation = service.list_gallery(folder="vacation")["items"]
    root = service.list_gallery(folder="")["items"]
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
async def test_sort_by_tag_and_name(hass, hass_client, enable_custom_integrations, fake_tv):
    mock_entry = MockConfigEntry(
        domain=DOMAIN, data={"tv": TV_IP, "automation_token": "t", "media_dir": ""}
    )
    mock_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()

    service = hass.data[DOMAIN][mock_entry.entry_id]["service"]
    asset_ids = await hass.async_add_executor_job(_seed_local_assets, service, 3, None)

    def run():
        service.set_asset_tags(asset_ids[1], ["zeta"])
        service.set_asset_tags(asset_ids[2], ["alpha", "zeta"])
        return (
            [item["asset_id"] for item in service.list_gallery(sort="tag")["items"]],
            [item["asset_id"] for item in service.list_gallery(sort="name")["items"]],
            [item["asset_id"] for item in service.list_gallery(sort="recent")["items"]],
        )

    tag_order, name_order, recent_order = await hass.async_add_executor_job(run)

    # Tag sort: untagged images (empty tag list) first, then alpha, then zeta.
    assert tag_order[0] not in (asset_ids[1], asset_ids[2])
    assert tag_order[-2:] == [asset_ids[2], asset_ids[1]]
    # Name sort: art_0 < art_1 < art_2.
    assert name_order == asset_ids
    # Recent sort: last updated first (asset_ids[2] got its tag last).
    assert recent_order[0] == asset_ids[2]


@pytest.mark.asyncio
async def test_upload_with_tags(hass, hass_client, enable_custom_integrations, fake_tv):
    import aiohttp

    mock_entry = MockConfigEntry(
        domain=DOMAIN, data={"tv": TV_IP, "automation_token": "t", "media_dir": ""}
    )
    mock_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()
    client = await hass_client()

    form = aiohttp.FormData()
    form.add_field("file", _sample_jpeg(), filename="photo.jpg", content_type="image/jpeg")
    form.add_field("tags", "sommer, favoritt")
    resp = await client.post("/api/samsung_frame_art/upload", data=form)
    assert resp.status == 200
    body = await resp.json()
    assert body["data"]["asset"]["tags"] == ["sommer", "favoritt"]

    # Tags land in the tag list immediately.
    resp = await client.get("/api/samsung_frame_art/tags")
    body = await resp.json()
    assert {entry["tag"] for entry in body["tags"]} == {"sommer", "favoritt"}


@pytest.mark.asyncio
async def test_slideshow_includes_tv_discovered_assets(fake_tv, mock_entry, hass, hass_client, enable_custom_integrations):
    """TV-discovered art (no local file) with a tag is slideshow-eligible."""
    mock_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()

    service = hass.data[DOMAIN][mock_entry.entry_id]["service"]

    def seed():
        state = service.store.load()
        state["assets"]["tv-asset-1"] = {
            "asset_id": "tv-asset-1",
            "filename": "TV art",
            "ha_rel_path": None,
            "source": "tv_discovery",
            "created_at": "2026-11-21T00:00:00+00:00",
            "updated_at": "2026-11-21T00:00:00+00:00",
            "tags": ["familie"],
            "tv_map": {TV_IP: {"content_id": "MY_F0009", "on_tv": True, "active": False, "error": None}},
        }
        service.store.save(state)

    await hass.async_add_executor_job(seed)

    # The TV reports the seeded content_id as available (it lives on the TV).
    fake_tv.snapshot = lambda tv_ip: types.SimpleNamespace(
        online=True,
        supported=True,
        available_ids={"MY_F0009"},
        available_items={"MY_F0009": {"content_id": "MY_F0009", "title": "TV art"}},
        active_id=None,
        error=None,
    )
    service.runtime.clear_snapshot_cache()

    resp = await client_post(hass, hass_client, "/api/samsung_frame_art/slideshow/start", {
        "tag": "familie",
        "interval_seconds": 5,
        "shuffle": False,
        "tv_ips": [TV_IP],
    })
    assert resp.status == 200
    body = await resp.json()
    assert body["data"]["assets_in_rotation"] == 1

    # The TV-present asset gets selected directly (no upload needed).
    deadline = time.time() + 10
    while time.time() < deadline and not fake_tv.select_calls:
        await hass.async_add_executor_job(time.sleep, 0.2)
    assert (TV_IP, "MY_F0009") in fake_tv.select_calls
    assert fake_tv.upload_calls == []

    resp = await client_post(hass, hass_client, "/api/samsung_frame_art/slideshow/stop", None)
    assert resp.status == 200


async def client_post(hass, hass_client, url, payload):
    client = await hass_client()
    if payload is None:
        return await client.post(url)
    return await client.post(url, json=payload)


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
