import io, os, time, types
import pytest
from PIL import Image
from pytest_homeassistant_custom_component.common import MockConfigEntry
from custom_components.samsung_frame_art.const import DOMAIN

class _C:
    def __init__(self, timeout=8): self.timeout = timeout
    def snapshot(self, tv_ip):
        return types.SimpleNamespace(online=False, supported=False, available_ids=set(), available_items={}, active_id=None, error="offline")

@pytest.fixture(autouse=True)
def patch_tv(monkeypatch):
    monkeypatch.setattr("custom_components.samsung_frame_art.TVClient", _C)

@pytest.fixture
def hass_config_dir(hass_tmp_config_dir):
    return hass_tmp_config_dir

@pytest.mark.asyncio
async def test_debug(hass, enable_custom_integrations):
    entry = MockConfigEntry(domain=DOMAIN, data={"tv": "1.2.3.4", "automation_token": "t", "media_dir": ""})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    service = hass.data[DOMAIN][entry.entry_id]["service"]
    print("MEDIA_DIR:", service.settings.media_dir)
    os.makedirs(service.settings.media_dir, exist_ok=True)
    for i in range(3):
        buf = io.BytesIO()
        Image.new("RGB", (640,360), (i*50, 100, 100)).save(buf, format="JPEG")
        with open(os.path.join(service.settings.media_dir, f"a{i}.jpg"), "wb") as f:
            f.write(buf.getvalue())
    print("files on disk:", os.listdir(service.settings.media_dir))
    for attempt in range(5):
        service.refresh(force=True, wait=True)
        state = service.store.load()
        ids = [k for k, v in state["assets"].items() if v.get("ha_rel_path")]
        print(f"attempt {attempt}: assets={len(ids)}", [v.get('ha_rel_path') for v in state['assets'].values()])
        if len(ids) >= 3:
            break
        await hass.async_add_executor_job(time.sleep, 0.3)
    assert len(ids) >= 3, "no assets imported"
