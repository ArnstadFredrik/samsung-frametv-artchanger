# Dev server (test before publishing)

Runs a throwaway Home Assistant instance in Docker with the integration
mounted **live** from this repo.

## Start

```bash
cd dev
docker compose up -d
```

Open http://localhost:8123 — first boot runs onboarding (create a throwaway
user, skip the remaining steps). Then:

**Settings → Devices & Services → Add Integration → Samsung Frame TV Art
Changer**, enter your TV's IP and test.

## Apply code changes

- Python changes: `docker compose restart` (integration is mounted from the
  repo, nothing to copy).
- Web UI changes (`www/`): hard-refresh the panel iframe (Cmd+Shift+R) or
  restart the container.

## Logs

```bash
docker logs -f frame-art-dev
```

Debug logging for the integration: add to `dev-config/configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.samsung_frame_art: debug
```

## Teardown

```bash
docker compose down          # keeps dev-config/
docker compose down -v       # and removes volumes
```

`dev-config/` is git-ignored — the dev instance is disposable.
