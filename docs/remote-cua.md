# Authenticated XP control through native Hermes tools

There is no XP management dashboard, host FastAPI service, or public control
API. Hermes tools call the authenticated paired XP client directly using the
private device registry (normally `~/.hermes/hermesxp-devices.json`). The
registry must not be included in any public package, log or tool result.

The `xp_status` and `xp_screen` tools are read-only with respect to XP
(screenshots can optionally be saved to a private host directory). The
`xp_service` tool supports read-only `status` by default. `xp_control`
and mutating service commands require **both**:

- The operator explicitly configures `HERMES_CUA_LIVE_ENABLED=1` on the
  Hermes host (defaults to disabled).
- The specific tool call includes `confirm_live=true`.

Input is bounded to authenticated clicks, double-click, drag, scroll,
printable ASCII text (128 characters), and allowlisted key presses. There is
**no arbitrary shell command**. The host reads the desktop dimensions before
acting, verifies coordinates, limits mutations to ten requests in five
seconds and only claims success after the XP companion returns its exact
expected acknowledgement.

`xp_screen` may save the most recent BMP per paired device, with private
directory/file permissions and atomic replacement. Set `save=false` to avoid
persisting the screenshot. `analyze=true` opts into model inference; external
vision providers receive the screenshot if so configured.

The Windows XP listener must remain protected by the LAN firewall and paired
authentication. Do not expose XP port 18768 to the public Internet. Messenger
uses a separate loopback sender port 18769 on the modern host, and remains
independent of these tools.
