# HermesXP / MSN Messenger Bridge — prototype

### Native Windows Live Messenger calls (v0.5.1 — LAN preview)

This is a **native MSN voice-call path**. The original Windows Live Messenger
2009 window owns the microphone, speakers, and call UI. HermesXP.exe's legacy
five-second voice button is not involved. The Hermes host handles signaling,
RTP audio and local speech/agent inference.

**Verified on RUITER (Windows XP SP3), November 9, 2026:**

- The Hermes bot signs in over **MSNP18 with RST2/SSO** and receives/sends
  binary `UUN`/`UBN` messages.
- Sending `/nativecall` in the bot conversation makes **Messenger itself**
  display a native incoming-call Accept/Decline prompt.
- Clicking **Accept** completes SIP/SDP negotiation and confirms
  `PCMU/8000` RTP ports. Hermes sends synthesized greeting RTP, receives
  microphone RTP, transcribes a turn using local LFM3-Audio, gets an agent
  reply, synthesizes it and transmits a native RTP response. The server-side
  end-to-end path was observed in service logs; someone at the XP machine
  must verify actual audibility.

**How to use it now:** open the Messenger chat with Hermes, send `/nativecall`
(or `/call` when native mode is enabled), then click **Accept** inside
Messenger. `/hangup` or Messenger's **End call** ends the native call.

**The original Call toolbar has one remaining legacy limitation.** WLM 2009
still displays `0x80EE00C8` because the open MSN server does not implement
Microsoft's old *outgoing* VOIP service. Hermes now recognizes the
corresponding `UUN` type-11 rendezvous and sends a **reciprocal native SIP
call** back to Messenger. You can accept that call in Messenger, but the
original error message appears first. This workaround does *not* claim to
implement the missing original outgoing-call service. For a cleaner flow,
use `/nativecall`.

For another Hermes installation, enable this explicitly in the host's
**private** `~/.hermes/msn-bridge.env`:

```ini
MSN_BOT_PROTOCOL=18
HERMES_MSN_NATIVE_CALL=1
HERMES_MSN_NATIVE_IP=<Hermes host's private LAN IPv4>
```

Restart `hermes-msn-bridge.service` and `hermes-xp-voice.service`.
This mode advertises WLM-compatible voice capabilities, decodes the
`<sip e="base64" i="..."><msg>...</msg></sip>` tunneled SIP envelope, sends
SIP INVITE/ACK/BYE over `UUN`/`UBN` type 12, and uses **G.711 PCMU RTP
on UDP/19740**. The native Node bridge sends PCM turns to a separate
**loopback-only** audio worker on TCP/18771. That worker reuses the
Hermes Talk local LFM3 transcription/TTS endpoints and the local Hermes
agent route; Node and XP never receive the agent's API key.

Calls accept only the configured MSN owner, use the paired XP's private
IPv4 address for RTP, and run on trusted LAN only. Restrict UDP/19740 to
the XP device. No port forwarding or automatic firewall changes are made.
There is at most one call, with speech turns buffered for processing;
this is **not yet a full low-latency, full-duplex, barge-in-capable system**.
Audio playback deliberately suppresses microphone echo and only processes
bounded recordings. This is still experimental.

To return to proven MSNP9 text messaging, remove `HERMES_MSN_NATIVE_CALL`
and `MSN_BOT_PROTOCOL` from the private bridge environment and restart
`hermes-msn-bridge.service`. Do not leave `MSN_DEBUG` or
`MSN_NATIVE_TRACE` enabled during normal use.

### Legacy separate voice companion (v0.4.0; optional)

The XP executable also retains **Talk to Hermes (5s)**, a push-to-talk-style
microphone/speaker path to the local Hermes host. From your MSN chat with the
Hermes bot, send **`/call`** to display an incoming voice invitation in
HermesXP. Accept on XP before the microphone is activated. Send **`/hangup`**
to stop playback/polling, or press the Stop voice button.

This old component is **not** the native Messenger call path above. With
native mode enabled, `/call` and `/hangup` control the native call instead.
Without native mode, they retain their previous companion behavior.

How the prototype works:

1. XP uses built-in WinMM to record up to five seconds at 16-kHz mono PCM16.
2. XP submits the audio over authenticated LAN HTTP on host port **18770**.
3. The Hermes host uses the **same local LFM3-Audio endpoints and local
   Hermes api_server agent model route as the Hermes Talk Discord cascade**.
   Transcription, agent inference, and speech synthesis run only on Hermes.
4. XP polls for the completed audio and plays the answer through WinMM.
   This preview is **half-duplex**, not a continuous low-latency call:
   each spoken turn requires another click, and long CPU model inference may
   cause a significant delay.

The voice service is provisioned automatically by
`local-server/install.sh` or the plugin's host-side update service. It
uses `~/.hermes/.env` for the same `API_SERVER_KEY` as Hermes Talk, and
`~/.hermes/hermesxp-devices.json` for the existing paired-device token/IP.
There is **no new XP pairing secret**, paid voice API, or direct XP internet
dependency. The existing XP companion update mechanism replaces the EXE,
retaining `hermesxp.ini`. Until that update arrives, MSN text chat continues
to work; older XP binaries simply do not recognize incoming invitations.

For a manually installed host, or to troubleshoot:

```bash
systemctl --user status hermes-xp-voice.service
journalctl --user -u hermes-xp-voice.service -n 40 --no-pager
```

Only the paired XP computer should be permitted to reach TCP/18770 on your
firewall. The voice service validates both the source IPv4 and the existing
per-device 256-bit token; it binds a **specific private host LAN address**.
No public listener, UPnP, or automatic firewall change is introduced.
An untrusted network must **not** be used for this plain-HTTP audio path.

If the speech service fails, first confirm
`lfm3-audio-server.service` and the Hermes `api_server` are running on the
host (default loopback ports 8899 and 8642 respectively). The Windows XP
machine itself never needs LFM3 or Python.

### Plugin-managed updates (v0.3)

Install the entire Git repository as a Hermes plugin:

```bash
hermes plugins install https://github.com/alxspiker/HermesXP.git --enable
```

The plugin contains the host-side MSN platform/server setup, both XP
executables, an authenticated updater, and a versioned release fetcher. Follow
the plugin's `after-install.md` **once** to provision the host services,
install XP, and pair the laptop (the XP installer can be copied over USB).
Subsequently, a normal `hermes plugins update hermes-msn` triggers an XP
client update automatically. The update timer retries offline machines.

### MSN as a Hermes messaging channel

MSN registers as the `hermes_msn` platform. Incoming Messenger conversations
reach the Hermes gateway; outbound messages can be sent through the normal
Hermes `send_message` tool or from a separate CLI/cron process:

```bash
hermes send --to hermes_msn:user@hermes.local "test"
```

Replace the recipient with your configured `HERMES_MSN_OWNER_EMAIL` if needed.
The standalone sender uses a token-authenticated local HTTP endpoint on
`127.0.0.1:18769` on the Hermes host. It can send only to the configured
owner, and never exposes that endpoint to XP or the public internet. A
successful response means the MSN bot accepted the message for sending,
not that Windows Live Messenger acknowledged its delivery.

**No XP-to-GitHub connection is required.** The Hermes computer downloads
prebuilt, checksum-verified release binaries when the release matches its
installed plugin revision. If no matching release exists, it builds with
Clang/LLVM on the Hermes computer. The XP receives a SHA-256-checked image
via its authenticated, IP-restricted LAN listener; a separate small rollback
helper replaces the EXE, starts it and restores the prior version if the
replacement fails its local startup health check.

Pairing secrets are stored in `~/.hermes/hermesxp-devices.json` on the Hermes
host (0600), outside the Git checkout. A separate token is required for each
XP laptop. Tokens are never embedded in public release assets or the public
LAN installer. Existing XP users must install v0.3 once to acquire the new
updater helper.

The update watcher and 15-minute retry timer are systemd user units on
the Hermes host. Neither the updater nor this change configures any outbound
XP firewall restriction; that is a separate decision.

**Release publishing without paid GitHub Actions:** The maintainer runs
`bash local-server/publish-release.sh --dry-run` on Linux to compile/test,
then `bash local-server/publish-release.sh --draft` to create a private
GitHub release draft with generic XP binaries. After validating startup and
rollback on an actual XP laptop, run `bash local-server/publish-release.sh
--publish`. No private certificates or tokens are uploaded; the XP device
does not connect to GitHub.

## Installing HermesXP on Windows XP

**Use `HermesXP-Setup.exe`, not a loose copy of `HermesXP.exe`.** The NSIS
setup wizard supports XP SP3 x86, installs the companion and its MSN support
files, creates Start menu and optional desktop shortcuts, and registers
`HermesXP` under **Control Panel → Add or Remove Programs**.

- On the Hermes host, run `bash local-server/build-xp-package.sh`. The
  package directory `~/.hermes/msn-server/xp-package` contains
  `HermesXP-Setup.exe` as well as a portable `HermesXP.zip` fallback.
- Transfer the installer over a trusted LAN or USB. When the local package
  server is enabled, the LAN address is
  `http://<Hermes-host-LAN-IP>:18767/HermesXP-Setup.exe`.
- Run setup as an XP administrator and choose the installation directory.
  A fresh installation defaults to `Program Files\HermesXP`; an existing
  `C:\HermesXP` installation is upgraded **in place** to retain its settings.
  The installer never overwrites an existing `hermesxp.ini`.
- Launch **Start → Programs → HermesXP → HermesXP**. The app displays the
  IPv4 address assigned by Windows (updated automatically), with a
  **Network Connections** button that opens XP's own networking control panel.
  Connect to Wi-Fi or Ethernet using Windows XP before pairing. HermesXP does
  not ask for, store, or manage Wi-Fi passwords. **Install for MSN** is a
  separate button that configures Messenger and its local certificate.
- Uninstall with **Add or Remove Programs**. This removes the companion and
  its shortcuts; it deliberately preserves `hermesxp.ini` and other user
  data. It does not undo the independent Messenger patch/CA installation.

The installer must be built from a package containing the local CA, switcher,
and host settings. Do **not** publish a host-specific installer on the public
GitHub repository. `makensis` (from the free NSIS compiler package) is
required on the build host, **not** on Windows XP.

**Status: local server build in progress.** The XP probe (Step A) passed and the Hermes plugin (Step B) is installed. The local MSN server (Step C) is now built in: `local-server/install.sh` installs Escargot's open server code on the Hermes host, so **no Escargot website signup is needed** — WLM on the XP talks to a server running on the ZBook, and the Hermes bot logs in to the same server. The XP sign-in test (TLS 1.0 + local CA) is the remaining unverified step.

The XP companion is **not an agent runtime or remote execution service**. It is a read-only TCP connectivity probe. The modern host has a Hermes platform adapter and a separate Node.js bridge for an experimental MSN bot library.

## Contents

| File | Runs on | Function |
|---|---|---|
| `dist/HermesXP.exe` | Windows XP SP3 x86 | Win32 graphical probe, no external DLLs / CRT / WMI |
| Root `plugin.yaml`, `adapter.py` and `__init__.py` | Hermes host, Python | Full Git-backed Hermes plugin; updates through `hermes plugins update hermes-msn` |
| `tools/update_manager.py`, `tools/hermesxp_update.py` | Hermes host, Python | Verifies releases or builds locally and distributes authenticated updates to paired XP machines |
| `dist/HermesXP-Updater.exe` | Windows XP SP3 x86 | Separate restart-and-rollback helper |
| `msn-bridge/bridge.js` | Hermes host, Node 18+ | Connects MSN bot to Hermes via authenticated localhost JSON-lines |
| `msn-bridge/msnclient/` | Hermes host, Node | Patched copy of tutmonde/msnclient (GPLv3) — server host/login URL come from env, see `LOCAL-PATCH.md` |
| `local-server/install.sh` | Hermes host (ZBook), bash | One-time installer: downloads msn-server, creates accounts, starts services, sets up TLS |
| `tools/probe_server.py` | Hermes host, Python | Optional stand-alone probe test *without* Hermes |
| `xp-client/*` | Build machine | C source, import definitions, clang/lld build script |
| `tests/` | Build machine | Simulated adapter loopback protocol tests |

## Architecture

```text
WLM 2009 on XP  ---> local MSN server on the ZBook (msn-server, :1863/:1864)
  (Switcher patch   + stunnel TLS terminator on :443 for the HTTPS sign-in)
  redirects
  login.live.com     |
  to <ZBook LAN IP>  |  MSN bot account (hermes-bot@hermes.local)
                     |       |
                     |  msn-bridge/bridge.js (Node)
                     |       | loopback 127.0.0.1:18764 + secret
                     |  Hermes MSN platform plugin
                     |       |
                     |  Hermes gateway / agent

HermesXP.exe on XP --> LAN port 18765 --> read-only host probe
```

**There is no Escargot account in this setup.** The MSN server is Escargot's open server code (valtron/msn-server, CC BY-NC 4.0), downloaded by the installer at setup time and run locally on the ZBook. It is not vendored in this repo (license). This plugin does not automatically rewrite the original client or store Hermes LLM API keys on XP — the Switcher patch and CA install on the XP are the two manual steps (Step C).

## Step A: test the XP executable independently

1. On the modern host run `python3 tools/probe_server.py --bind YOUR_LAN_IP` (for example, `192.168.1.20`). Restrict the host firewall port 18765/TCP to the XP device's IP only. Run this **only on a trusted or isolated LAN**.
2. Copy `dist/HermesXP.exe` to Windows XP and launch it. Enter the modern host LAN IP and click **Test connection**.
3. It should report **Hermes host reached! Probe OK. Not yet paired.** No services are installed and no configuration is changed.
4. Stop `probe_server.py` after testing. Do not run this alongside the plugin probe listener on the same IP/port.

If it fails, check host IP, Windows/host firewall, routing, and that port 18765 is listening. Avoid the XP WMI paths that crashed Ruiter.

## Step B: install Hermes gateway adapter on the modern host

1. Install the **whole repository** on the Hermes host with `hermes plugins install https://github.com/alxspiker/HermesXP.git --enable`. Do not copy just the legacy `hermes-plugin/hermes-msn` subfolder; an isolated subfolder cannot receive the build tools or native Git updates.
2. Generate a secret locally on the host: `python3 -c 'import secrets; print(secrets.token_hex(32))'`
3. Set the following in your Hermes **profile's** `.env` (or service environment). The same token must be supplied to the Node bridge; keep it secret. The owner/bot accounts are created by the Step C installer as `user@hermes.local` / `hermes-bot@hermes.local` (defaults — override with --owner-email / --bot-email, or set them in .env):

   ```ini
   HERMES_MSN_BRIDGE_TOKEN=<the_generated_secret>
   HERMES_MSN_OWNER_EMAIL=user@hermes.local
   HERMES_MSN_ALLOWED_USERS=user@hermes.local
   # Optional: your HOST's private LAN IP to enable the read-only XP probe
   HERMES_XP_PROBE_BIND=<ZBook LAN IP>
   ```

4. Enable the plugin: `hermes plugins enable hermes-msn`. Enable the platform in Hermes gateway configuration if it isn't enabled automatically:

   ```yaml
   gateway:
     platforms:
       hermes_msn:
         enabled: true
   ```

   Merge this into your *existing* YAML; do not overwrite it. Depending on Hermes version/profile, the platform setup menu may be preferable. Restart your Hermes gateway.
5. The adapter binds only `127.0.0.1:18764` for the MSN bot. Optional XP probe is on explicitly configured `HERMES_XP_PROBE_BIND:18765`.

## Step C: local MSN server (no Escargot signup)

Run the installer on the Hermes host (ZBook) as user `hermes`. It is idempotent — safe to re-run.

1. One-time system prerequisites (as a sudo user on the host):
   ```sh
   sudo apt-get install -y stunnel4
   echo 'net.ipv4.ip_unprivileged_port_start=0' | sudo tee /etc/sysctl.d/99-hermesxp.conf
   sudo sysctl -p /etc/sysctl.d/99-hermesxp.conf
   ```
   The sysctl lets a user service bind :443 (the TLS terminator). Without it the installer still finishes the server + bridge and warns.
2. Run the installer from this repo:
   ```sh
   cd local-server && ./install.sh
   ```
   It clones Escargot's server code pinned to commit `9cddb9c` into `~/.hermes/msn-server` (downloaded at install time, not vendored — CC BY-NC 4.0), creates a venv + dependencies, writes `settings_local.py` (all redirects to the ZBook LAN IP), creates the SQLite databases, creates the two accounts (`user@hermes.local` owner, `hermes-bot@hermes.local` bot, unless overridden), writes their credentials into `~/.hermes/.env`, and starts three systemd user services: `msn-server` (:1863/:1864/:8081), `msn-tls` (stunnel :443 → 8081, TLS 1.0 + old ciphers for XP), `hermes-msn-bridge` (Node bridge → 127.0.0.1:18764).
   The optional UFW step asks for the XP device's **single IPv4 address**, shows the proposed inbound TCP ports (443, 1863 and 1864), and requires confirmation. It invokes only the trusted system UFW executable, using `sudo -n` first and requesting interactive sudo authorization if needed and a terminal is available. It never runs this user-writable Python helper as root for authorization. Without suitable sudo permission, ask an administrator to configure the firewall. It does not enable inactive UFW, open ports for an entire subnet, or configure other firewalls. Non-interactive installs leave the firewall unchanged; run `python3 local-server/setup-firewall.py` later to use the helper. Existing broader rules are not removed; rule verification does not establish effective connectivity or precedence over earlier rules. A failed operation can leave earlier successfully added rules in place. Port 18767 (package download) is not opened by the helper: transfer via USB or arrange a separate temporary, XP-IP-restricted rule with your administrator.

3. **The installer prints the owner password ONCE** (`OWNER_PASSWORD_FOR_WLM=...`). Give it to the person who will type it into WLM on the XP. It is never written to a file.
4. Restart the Hermes gateway so the `hermes_msn` platform connects (the adapter health-checks 127.0.0.1:1863 and logs a clear error if the server is down).
5. On XP: run `HermesXP-Setup.exe` from the trusted LAN package directory (or transfer it over USB), then launch HermesXP from the Start menu and click **Install for MSN**. The button places `escargot.dll` and both Switcher INIs next to Messenger, installs the local CA into Trusted Root, patches both Messenger exes to load the Switcher at startup (originals backed up as `.bak`), and launches Messenger. The portable ZIP is available for troubleshooting.
   - Sign in to WLM as `user@hermes.local` (or your configured owner address) with the printed password. The bot (`hermes-bot@hermes.local`) is already in your contacts — pick it and send it a message. Only the configured owner address is allowed through the bridge into Hermes. The Hermes gateway itself must be running.
6. Verify: `systemctl --user status msn-server.service msn-tls.service hermes-msn-bridge.service`, and check the gateway log shows the platform connected and the bridge logged in.

**Not verified yet:** the XP HTTPS sign-in against the local TLS terminator (the R1 gate — whether WLM 2009's SChannel accepts the local CA cert and TLS 1.0 + 3DES from Debian 13's OpenSSL). If sign-in fails on TLS, stop and investigate the Switcher/cert behaviour before building more code around it.

## Security boundaries / known limitations

- XP is unmaintained. Isolate it in a VLAN or filtered LAN. Restrict its outbound access to the necessary revival service if using Escargot; this release does not configure that network isolation.
- The XP probe is **unencrypted and unauthenticated** by design, and only exchanges a machine name and OK/BAD result. It does not grant device control or prove identity. Never treat a positive response as pairing.
- The MSN bridge is plaintext **loopback-only** and protected with a long shared token. Do not expose port 18764 to the LAN or internet.
- User address filtering is applied in both Node and Python. Other Messenger contacts cannot submit agent messages through this code, but the public MSN service is a separate trust boundary.
- No remote code execution, auto-installation, service installation, file modification or Windows Registry edits in this prototype.
- Nothing here bypasses XP security support end-of-life or fixes its browser/TLS stack.
- XP executable is cross-compiled, PE32/Windows 5.01 verified, but not run/tested on a Windows XP installation.
- To uninstall the Windows companion, use Control Panel → Add or Remove Programs → HermesXP. This does not remove the separate Hermes host plugin/services or automatically undo existing Messenger modifications.

## Build and test

`cd xp-client && ./build.sh` uses LLVM Clang + lld-link; it generates small import libraries from bundled `.def` files and fixes 32-bit stdcall name decoration for Windows DLL imports, needing no Microsoft SDK. On a Linux build machine with Clang and lld-link installed, verify with `llvm-objdump -p HermesXP.exe`. The EXE uses only KERNEL32, USER32 and WS2_32, targets Windows GUI subsystem 5.01 and x86.

`python3 -m unittest discover -s tests -v` tests the adapter protocol with API stubs. It **does not** assert compatibility with installed Hermes or public MSN.

## Next milestone

Test XP native GUI on Ruiter, identify Messenger version, verify Escargot login, then fix the experimental MSN bot library/adapter until a true MSN → Hermes → MSN conversation is observed. After that, add authenticated device pairing and limited XP tools (without opening a remote shell by default).
