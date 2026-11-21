# Changelog

## 0.0.7

- Fixed the slideshow panel UI never leaving "Stopped": the status poller passed the raw API envelope to the UI update, overwriting the running state every 2 seconds (the slideshow itself ran fine).
- Collection filter options are now also read from the gallery data payload (robustness).

## 0.0.6

- Tags per image with gallery filtering, plus automatic media-folder collections (subfolders).
- Built-in slideshow: filtered collection, interval 5 s – 24 h, shuffle, TV selection, skip/stop; runs server-side with the panel closed.
- Refresh now re-scans the media folder, so new and removed local files are picked up without a restart.

## 0.0.5

- Server-side JPEG crop preview for formats browsers cannot render (HEIC/HEIF/TIFF).

## 0.0.4

- More upload formats: webp, gif, bmp, tiff, heic, heif, avif — converted to TV-format 3840x2160 JPEG.
- Media-folder scan picks up the same extensions.

## 0.0.3

- Brand images shipped in the integration (`brand/` directory, HA 2026.3+), icon composed from MDI glyphs.

## 0.0.2

- Panel authentication: HA access token forwarded to the panel, Authorization header on all API calls (fixed 401 in the panel UI).

## 0.0.1

- Fixed the 500 error in the options flow and the blank custom panel.

## 0.0.0

- Initial release: port of the Samsung Frame TV Art Changer Supervisor add-on
  (Timminater/timminaters-addons) to a custom integration for the
  Home Assistant Marketplace (HACS), with English UI.

---

Historical note: releases 0.0.0–0.0.4 were originally published as
1.0.0–1.0.4; the version scheme was reset to 0.0.x before the first
stable 1.x release.
