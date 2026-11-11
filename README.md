# HermesXP

![HermesXP logo](assets/hermesxp-logo.jpg)

**A Windows XP companion and Windows Live Messenger integration for [Hermes](https://github.com/NousResearch/hermes-agent).**

HermesXP connects a legacy Windows XP computer to a modern Hermes host. It provides authenticated desktop access, Windows service management, Messenger text messaging, and optional native voice calls through Hermes Talk. Hermes runs the AI models and automation; the XP computer runs a small native companion and the existing Messenger client.

There is **no web dashboard**, separate XP inference runtime, or requirement for XP to reach GitHub.

## Capabilities

| Capability | Description |
| --- | --- |
| Desktop observation | Capture the XP desktop on demand and pass screenshots to Hermes' existing vision tools. |
| Desktop interaction | Authenticated mouse, keyboard, scrolling, dragging, and text input, with explicit write authorization. |
| Windows service management | Inspect, start, stop, or restart an installed service by its Service Control Manager name. |
| Messenger messaging | Exchange messages with Hermes through a locally hosted MSN server and a Hermes gateway adapter. |
| Native Messenger audio | Route supported Messenger SIP/RTP calls to the separate Hermes Talk plugin. |
| LAN discovery | Recover from DHCP and local network address changes using authenticated discovery. |
| Managed client updates | Deploy the paired desktop executable and rollback helper from the Hermes host, retrying when XP reconnects. |
| Background health service | Run a low-privilege Windows service before sign-in; launch desktop controls when a user signs in. |

**Scope:** Windows Live Messenger is an optional integration, not a prerequisite for desktop control. The project does not distribute Microsoft's Messenger application.

## Requirements

**Hermes host**

- A Linux machine running Hermes, Python, Node.js, and systemd user services.
- A private IPv4 LAN connecting the host to the XP computer.
- Host-side build tools when prebuilt release assets are unavailable: Clang, LLVM (including `lld-link` and `llvm-rc`), and NSIS (`makensis`) for the Windows installer.
- `stunnel` and appropriate local TLS/firewall configuration if using Windows Live Messenger sign-in.
- The **Hermes Talk** plugin, installed and configured separately, if using voice calls.

**Windows XP computer**

- Windows XP SP3, 32-bit (x86), with a working LAN connection.
- Administrator rights for the initial HermesXP installer.
- An existing Windows Live Messenger installation if MSN integration is selected.

XP does not need an internet connection to run or receive client updates. Downloads, builds, and model/provider connections happen on the Hermes host.

## Installation

### 1. Install the Hermes plugin

Install the **entire repository** on the machine running Hermes:

```bash
hermes plugins install https://github.com/alxspiker/HermesXP.git --enable
```

The plugin is named `hermes-msn`. Installing only the `hermes-plugin/hermes-msn` subdirectory omits the host setup scripts and updater.

### 2. Configure the Hermes host

Run the setup script as the user who runs Hermes:

```bash
bash ~/.hermes/plugins/hermes-msn/local-server/install.sh
```

The script provisions the local MSN server and bridge, creates host-side configuration, and installs the discovery, update, and voice service definitions. It also prepares a Windows XP installation package.

Some features require administrator-approved host configuration, particularly the TLS listener and LAN firewall. Review the script's output; do not expose these services to the public internet.

If Messenger is enabled, the installer creates local owner and bot accounts. **Record the owner password when it is displayed**; the installer does not write it into the XP package.

### 3. Install the Windows XP companion

Copy the generated installer to the XP machine from a trusted USB drive or the host's optional LAN package server.

- **Installer:** `~/.hermes/msn-server/xp-package/HermesXP-Setup.exe`
- **Portable fallback:** `~/.hermes/msn-server/xp-package/HermesXP.zip`
- **Optional LAN download:** `http://<host-LAN-IP>:18767/HermesXP-Setup.exe`

Run `HermesXP-Setup.exe` as an administrator. It installs:

- The **HermesXPService** low-privilege background health service.
- A desktop companion that starts automatically at Windows sign-in.
- The application, updater/rollback helper, shortcuts, and uninstaller.
- Optional integration with an **existing** Windows Live Messenger installation, including Switcher configuration, a local certificate, and backups of modified executables.

The Messenger component is selected by default but can be deselected. HermesXP never downloads the Windows Live Messenger client or bundles account passwords.

The compact application window shows pairing, network, and host status. Open **Settings** for host connection testing, **Repair Messenger**, and Windows **Network Connections**. Normal operation does not require keeping the window in the foreground.

### 4. Pair the device

Pairing is deliberately separate from installation. Each XP machine needs its own randomly generated 64-character hexadecimal token.

On XP, set the token and the allowed Hermes host LAN address in `hermesxp.ini`:

```ini
[Remote]
Token=<unique-64-character-hex-token>
AllowedHostIP=<Hermes-host-LAN-IP>
```

Store the same token in a **private file outside the Git checkout** on the Hermes host, readable only by the Hermes user. From the installed plugin directory, register the XP device:

```bash
cd ~/.hermes/plugins/hermes-msn
python3 tools/hermesxp_update.py pair <device-name> <XP-LAN-IP> --token-file /private/path/to/token
python3 tools/hermesxp_update.py status
```

Do not place pairing tokens in screenshots, Git commits, release assets, or the LAN installer. See [first-time setup](after-install.md) for the full pairing and provisioning procedure.

### 5. Verify the connection

Restart the Hermes gateway if the new `hermes_msn` platform is not yet active. Check the host services and plugin diagnostics:

```bash
systemctl --user status msn-server.service hermes-msn-bridge.service
systemctl --user status hermes-xp-discovery.service hermes-xp-update.timer
hermes plugins doctor hermes-msn
```

If using Messenger, sign in with the locally created owner account and send a message to the Hermes bot. A reachable XP desktop also needs a Windows user to be signed in; the background health service alone does **not** provide mouse, keyboard, or screenshot access.

## Hermes tools

HermesXP exposes native tools directly to the Hermes agent, rather than a separate management website.

| Tool | Function |
| --- | --- |
| `xp_status` | Read host service, update, and paired-device status; optionally probe reachable XP devices. |
| `xp_screen` | Capture a screenshot on demand and optionally save it to Hermes' private media cache. |
| `xp_control` | Perform bounded mouse and keyboard actions on the paired desktop. |
| `xp_service` | Read or change the state of an existing named Windows service. |
| `msn_call` | Start, end, or inspect an MSN voice call through the configured host bridge. |

Desktop **writes** (`xp_control` and service start/stop/restart) require **both** `HERMES_CUA_LIVE_ENABLED=1` on the Hermes host and `confirm_live=true` in the individual tool call. Reads are available without enabling live input.

Screenshots are captured only when requested. HermesXP does not select, host, or run a vision model: Hermes can inspect a returned `screenshot_path` using its existing `vision_analyze` tool and configured vision provider. Saved captures remain in the private Hermes media cache with bounded retention.

For input limits, permissions, and the exact trust model, see [authenticated desktop control](docs/remote-cua.md).

## Windows Live Messenger and voice

The optional MSN bridge registers the `hermes_msn` messaging platform with Hermes. The Windows Live Messenger client connects to a local MSN server on the Hermes host; the bot forwards owner-authorized conversations to the Hermes gateway.

A message can also be sent through the normal Hermes CLI:

```bash
hermes send --to hermes_msn:user@hermes.local "Hello from Hermes"
```

Replace the address with your configured owner account. A successful send indicates the bridge accepted the message; it does not prove delivery to Messenger.

Voice calls use Messenger's native microphone/speaker path and G.711 RTP over the private LAN. **Hermes Talk** owns voice-provider selection, authentication, turn detection, and any agent actions. HermesXP does not provide a second voice model or a fallback to paid APIs.

For the supported native-call path, configure the host's private `~/.hermes/msn-bridge.env` and restart the bridge:

```ini
MSN_BOT_PROTOCOL=18
HERMES_MSN_NATIVE_CALL=1
```

In a Messenger conversation with the bot, use `/call` (or `/nativecall`) to request a call and `/hangup` to end it. The original Messenger Call button can use a different negotiation path; reciprocal invitations may still require acceptance, and interoperability varies by Messenger version and audio hardware. **Native calls are experimental**, not a replacement for the complete historical MSN voice service.

Advanced Talk settings, provider credentials, and foreground voice-tool permissions belong on the Hermes host. Voice input is **not** a speaker-identity check: do not grant sensitive actions through voice on an unattended or physically untrusted XP computer.

## Updates and unattended operation

```bash
hermes plugins update hermes-msn
```

This command selects and updates the **Hermes plugin**. The installed host-side update watcher then prepares matching XP artifacts and attempts to deliver them over the authenticated LAN connection.

- The Hermes host uses verified release artifacts when they match the installed plugin revision, or builds them locally if necessary.
- The XP desktop executable and rollback helper are checked and replaced through the paired updater. A failed startup can restore the previous executable.
- If XP is offline, the host retains the update and retries periodically when it becomes reachable.
- The background health service starts independently of Windows sign-in; **desktop controls and automatic executable delivery require the signed-in companion**.
- The separate `HermesXP-Service.exe` is installed by the XP setup program. **Updates to the service binary require running a newer installer again**; it is not silently replaced by the remote executable updater.

**Updating a GitHub repository does not update installed Hermes plugins by itself.** The XP updater follows the revision deliberately installed through Hermes; it does not independently download or run arbitrary newer commits.

## Architecture

```text
Windows XP                                  Hermes host (Linux)
──────────                                  ───────────────────
Windows Live Messenger ───── MSN LAN ────► Local MSN server
                                           │
                                           └─► MSN bot / bridge ─► Hermes gateway
                                                        │
                                                 Hermes Talk (optional)

HermesXP desktop companion ◄─ paired LAN ─ Hermes native XP tools
  ├─ Screenshots and bounded input           ├─ Screen / control / service
  ├─ Client update listener                  └─ Update manager and registry
  └─ Authenticated LAN discovery ◄────────► Discovery service

HermesXPService (background health)         systemd host services
```

Selected network interfaces:

| Interface | Purpose |
| --- | --- |
| TCP 1863/1864, host | Local MSN messaging. |
| TCP 443, host | Optional legacy HTTPS/TLS sign-in for Messenger. |
| TCP 18768, XP | Authenticated device status, screen/input, service control, and updates. |
| UDP 18773, LAN | Authenticated host/device address discovery. |
| TCP 18767, host | Optional local installer download; restrict access. |
| Host loopback ports | Hermes gateway, bot control, and Talk adapter; not public LAN endpoints. |

The read-only host connection probe (`18765/TCP`) is optional and is **not** evidence that an XP device is paired. Discovery is authenticated with a per-device key and can recover from supported private-LAN IP changes without a fixed DHCP lease.

## Security and limitations

- **Windows XP is unsupported software.** Keep it on an isolated or tightly filtered private network. Do not forward its control or MSN ports from the router.
- Paired remote control uses token authentication and an allowed host IPv4 address, but the control connection is **plaintext HTTP over the trusted LAN**. Treat network access as sensitive.
- The XP companion has **no arbitrary shell-command endpoint**. Service operations are restricted to installed SCM service names and bounded actions, subject to the Windows account's permissions.
- The installation process can make privileged changes to XP, including Messenger executable patching and certificate trust. Inspect the generated package and use it only from a trusted host.
- Messenger authentication, media, and transfer protocols have their own limitations. Local protocol tests cannot establish compatibility with every Windows Live Messenger installation.
- Pairing secrets and Hermes provider credentials remain on the Hermes host or in the paired XP configuration as appropriate; never publish either. XP receives no Hermes provider API keys.
- Uninstalling the XP companion does not uninstall the separate Hermes host integration or automatically reverse Messenger certificate and executable changes.

## Building and testing

From the repository root on a compatible Linux build host:

```bash
bash local-server/build-exe.sh "$PWD"
bash local-server/build-xp-package.sh "$PWD"

python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-test.txt
PYTHONPATH=local-server python -m unittest discover -s tests -q
```

The build creates native PE32 executables targeting Windows XP. The package command requires host-specific local MSN configuration; NSIS is required to produce the normal `HermesXP-Setup.exe` installer.

Automated tests cover host logic and portions of the native client protocol. They **do not replace testing on actual Windows XP hardware**, especially for Messenger sign-in, desktop interaction, service permissions, and audio.

Releases can be prepared and published using [the host-side release script](local-server/publish-release.sh); no GitHub Actions workflow is required.

## Project layout

| Path | Responsibility |
| --- | --- |
| `plugin.yaml`, `adapter.py` | Hermes plugin registration, platform integration, and tools. |
| `xp-client/` | Native Windows XP companion, service, updater, installer, and resources. |
| `local-server/` | MSN server bootstrap, host services, packaging, and release scripts. |
| `msn-bridge/` | Messenger bot protocol, voice signaling, and local Hermes transport. |
| `tools/` | Authenticated XP client, pairing, LAN discovery, and update management. |
| `tests/` | Host-side and protocol regression tests. |
| `assets/` | HermesXP branding; the XP icon and banner are embedded into the executable. |

## Documentation

- [First-time setup and pairing](after-install.md)
- [Authenticated XP desktop controls](docs/remote-cua.md)
- [Messenger file-transfer test fixtures](docs/msn-file-transfer-fixtures.md)

**Third-party software:** The local MSN server is obtained from [valtron/msn-server](https://gitlab.com/valtron/msn-server) during setup; the Messenger bridge includes a patched [tutmonde/msnclient](https://github.com/tutmonde/msnclient). Their respective licenses and redistribution conditions apply. HermesXP does not include or redistribute Microsoft's Messenger client.
