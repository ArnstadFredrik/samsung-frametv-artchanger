# Samsung Frame TV Art Changer

A Home Assistant custom integration that manages Samsung The Frame TV artwork with a gallery UI, interactive crop upload, and automation triggers.

> **Origin:** This integration is a port of the **Samsung Frame TV Art Changer add-on** from
> [Timminater/timminaters-addons](https://github.com/Timminater/timminaters-addons), converted from a
> Supervisor add-on (FastAPI app behind ingress) into a native custom integration for the
> Home Assistant Marketplace (HACS). Full credit for the original implementation goes to
> [Timminater](https://github.com/Timminater).

## Features

- Gallery with art from Home Assistant (`frame_art` media folder) and from the TV.
- Sync status per item (`HA`, `TV`, `SYNC`, `ACTIVE`).
- Two-way visibility in the gallery:
  - HA items become visible and can be activated on the TV.
  - TV items become visible, including background thumbnail fetch via a queue.
- Upload with interactive crop to fixed output `3840x2160` (JPEG quality 90).
- Supported input formats: JPEG, PNG, WebP, GIF, BMP, TIFF, HEIC/HEIF (iPhone photos) and AVIF. Everything is automatically converted to the TV's required 3840x2160 JPEG before upload; HEIC/HEIF support is provided by pillow-heif.
- Crop tools: zoom, rotation slider (`-45..45`), extra 90-degree rotation, horizontal flip.
- Actions per item: activate on selected TVs, delete from `tv`, `ha` or `both`.
- Non-blocking refresh with metadata (`stale`, `refresh_in_progress`, `last_refresh`).
- Caching: TV snapshot cache in memory (TTL), thumbnail cache on disk.
- Settings page in the UI: manage TV IPs, refresh interval, snapshot TTL, network scan for supported Samsung TVs.

## Installation

### Home Assistant Marketplace (HACS)

1. Make sure the Marketplace / HACS is installed.
2. Add this repository as a custom repository with category **Integration**:
   `https://github.com/ArnstadFredrik/samsung-frametv-artchanger`
3. Click **Download** in HACS.
4. Restart Home Assistant.

### Manual

Copy `custom_components/samsung_frame_art/` into the `custom_components/` directory of your Home Assistant configuration, then restart Home Assistant.

## Configuration

After the restart, go to **Settings → Devices & Services → Add Integration** and search for **Samsung Frame TV Art Changer**.

| Option | Description |
| --- | --- |
| TV IP address(es) | Comma-separated list of Samsung The Frame TV IP addresses. |
| Automation token | Optional bearer token used to protect `/api/samsung_frame_art/automation/random`. |
| Media folder | Folder containing your local art (`.jpg`/`.png`). Leave empty to use `<config>/frame_art`. |

The panel appears in the sidebar as **Frame Art**.

The settings page inside the panel can also manage TV IPs, refresh interval, snapshot TTL, and network discovery at runtime — runtime changes are persisted independently of the config entry, exactly like in the original add-on.

## Usage

### Panel

Open **Frame Art** in the sidebar to browse, upload (with crop), activate, and delete art on your Frame TV(s).

### Automations

A random art changer can be driven in two ways:

1. **Home Assistant service** (recommended):

   ```yaml
   action:
     - service: samsung_frame_art.random
       data:
         ensure_upload: true
         activate: true
   ```

2. **HTTP endpoint** (compatible with the original add-on's automation URL). Set an *automation token* in the integration options, then call:

   ```yaml
   action:
     - service: rest_command.frame_random
   ```

   with a `rest_command` configured as:

   ```yaml
   rest_command:
     frame_random:
       url: http://<ha-ip>:8123/api/samsung_frame_art/automation/random
       method: POST
       headers:
         Authorization: "Bearer <your-automation-token>"
       payload: '{"tv_ips": ["192.168.1.199"], "ensure_upload": true, "activate": true}'
   ```

Other services:

| Service | Description |
| --- | --- |
| `samsung_frame_art.refresh` | Re-scan the media folder and refresh TV art state (`force: true` bypasses the snapshot cache). |
| `samsung_frame_art.activate` | Upload (if needed) and show a specific asset: `asset_id`, optional `tv_ips`. |
| `samsung_frame_art.random` | Pick a random local gallery image and show it. |

## Architecture notes (compared to the add-on)

| Original add-on | This integration |
| --- | --- |
| FastAPI app behind Supervisor ingress | aiohttp views registered on `hass.http` under `/api/samsung_frame_art/` |
| `/data/options.json` + `/data` state | Config entry + `<config>/samsung_frame_art/` data directory |
| Ingress panel with `/static` mount | Static assets at `/samsung_frame_art/www` + custom sidebar panel |
| Stdin commands / Docker | Not needed — runs inside the Home Assistant process |

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install homeassistant pytest pillow samsungtvws
.venv/bin/python -m pytest tests/ -v
```

## License

Upstream (Timminater/timminaters-addons) does not specify a license; this repository follows the same terms. See the attribution note above.
