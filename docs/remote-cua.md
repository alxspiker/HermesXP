# Authenticated Remote CUA

`POST /api/cua/execute` supports only the typed UI actions accepted by `CUACommand`; it has no shell or arbitrary-command operation.

Live execution is off by default. It requires all of the following:

- `HERMES_CUA_TOKEN` configured with at least 32 characters.
- `HERMES_CUA_ALLOWED_IP` set to the exact caller address.
- `HERMES_CUA_LIVE_ENABLED=1` on the host.
- A registered paired XP device, selected by the request's `device` field or `HERMES_CUA_DEVICE` (a sole paired device may be selected automatically).
- `confirm_live: true` on each request.

Without both server opt-in and per-request confirmation, the API only validates and reports a simulation. The host reads dimensions from the paired XP `/ui/inspect` endpoint before mouse actions, enforces screen bounds, and reports `executed: true` / `verified: true` only after receiving the exact expected acknowledgement. Paired-device tokens are never returned in API responses or logs.

Request examples (replace the token placeholder with the configured secret):

```json
{"action":"double_click","coords":[120,80],"token":"<configured-host-secret>","confirm_live":true}
{"action":"drag","coords":[40,50],"end_coords":[200,150],"token":"<configured-host-secret>","confirm_live":true}
{"action":"scroll","coords":[250,200],"delta":-2,"token":"<configured-host-secret>","confirm_live":true}
```

Coordinates must be integer screen pixels. Scroll is bounded to -5..-1 or 1..5. Text input is limited to 128 printable ASCII characters; key input uses the client's allowlist. The endpoint caps request bodies at 4096 bytes and allows at most 10 authenticated live requests per identity in a rolling 5-second window.

HermesXP control uses HTTP. Keep the host listener on loopback by default; if remote use is explicitly configured, restrict it to a trusted private LAN or an encrypted tunnel. Never expose the dashboard or XP control port to the public internet. Host-side loopback fixture tests verify authentication, routing, and acknowledgements; they do not prove deployment or runtime behavior on the physical XP machine. Do not perform live XP tests without explicit user authorization and a pushed source version.
