# HermesXP / MSN Messenger Bridge — prototype

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
| `hermes-plugin/hermes-msn/plugin.yaml` + `adapter.py` | Hermes host, Python | Registers platform `hermes_msn`; handles inbound/outbound messages |
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

1. Copy `hermes-plugin/hermes-msn` to `~/.hermes/plugins/hermes-msn` on the **Hermes host**, not on XP.
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
