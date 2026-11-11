# Paired XP screenshot routing

The local dashboard server reads the private `~/.hermes/hermesxp-devices.json` registry through the same validator used by HermesXP updates. The registry must retain its 0600 permissions. XP pairing tokens are used only by the server-side authenticated client and are never returned to browser routes.

- `GET /api/devices` returns paired device names only.
- `GET /api/screenshot?device=<name>` returns a validated BMP from the named paired device. Omitting `device` works only when exactly one device is paired; multiple devices require explicit selection.
- `GET /api/analyze?device=<name>` uses the same authenticated screenshot path and returns heuristic estimates, not model detections.

Requests have a five-second XP timeout. Offline/unavailable devices return 503, request timeouts return 504, unknown devices return 404, and malformed or oversized images return 502. Screenshots are limited to 32 MiB, 8192 pixels per dimension, and 40 million pixels, and are sent with `Cache-Control: no-store`.

Tests use paired-registry and XP-client fixtures; they verify routing, dimensions, errors and secret non-disclosure. They do not constitute a live Windows XP device test.
