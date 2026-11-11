## HermesXP — first-time setup

This Git repository is the **entire** HermesXP plugin: the MSN platform adapter,
the host setup tools, the versioned XP binaries, and the LAN updater. You do
not need to clone another repository or install build tools on Windows XP.

1. Install and enable the separate **Hermes Talk** plugin on the Hermes host. HermesXP uses the Talk-selected provider for all voice calls. Then on the computer running Hermes, after installing/enabling HermesXP:
   `bash ~/.hermes/plugins/hermes-msn/local-server/install.sh`
   (A normal unprivileged Hermes user can run the local server; optional
   privileged TLS prerequisites are explained by that installer.)
2. On the XP laptop, install the locally generated
   `HermesXP-Setup.exe` from the Hermes host's LAN package server or a USB
   drive. No GitHub connection is used by XP. Setup installs an automatic
   **HermesXPService** running as low-privilege LocalService for background
   health monitoring, and registers the desktop companion to launch when a
   Windows user signs in. Only the logged-in user process handles screenshots,
   keyboard, and mouse controls. **MSN integration is selected by default**:
   if Windows Live Messenger is already installed, Setup installs the supplied
   Switcher, local certificate and connection settings and patches the
   Messenger executables (preserving original `.bak` copies). Deselect this
   component if you don't want the installer to modify Messenger. To use
   custom Messenger and Contacts paths, configure `MessengerDir` and
   `ContactsDir` in `hermesxp.ini` before running Setup.
3. Pair each XP device once by giving it a unique 64-hex token in
   `hermesxp.ini` under `[Remote]` as `Token=<token>`, with
   `AllowedHostIP=<Hermes LAN IPv4>`. Store that same token in a **private**
   file on Hermes (mode 0600), then run
   `python3 ~/.hermes/plugins/hermes-msn/tools/hermesxp_update.py pair XP-NAME XP-LAN-IP --token-file /private/token-file`.
   **Never** put the pairing token into GitHub or a public LAN installer.

The package contains **no MSN account password**. Windows Live Messenger
needs an existing server account and a one-time sign-in unless its credentials
were already saved. The XP installer does not generate an unrelated password
or change Windows IP/gateway settings. Windows Live Messenger itself must
already be installed: this project does not redistribute Microsoft's client.

After pairing, use `hermes plugins update hermes-msn`. Hermes selects,
reviews and installs the new Git commit; the update watcher builds or
downloads verified generic artifacts on Hermes and sends them over the LAN.
Offline XP devices retry on the one-minute host timer, or immediately when an
authenticated XP discovery packet is received. A separate Windows XP helper
verifies startup and can restore the previous executable. The XP has no
dependency on public internet access.

The desktop EXE and rollback helper update automatically through the paired
LAN channel. The separate low-privilege service EXE is installed by Setup;
future changes to that service binary require running an updated Setup again.
This prevents remotely replacing a running Windows service without a separate
tested rollback mechanism.
If XP is powered on but no user has signed in yet, the health service is
available but the desktop-control/update listener does not run. XP updates
are applied when the desktop companion starts in a signed-in user session.

**Important:** Updating GitHub alone does not authorize new host software.
Run `hermes plugins update hermes-msn` (and address any security-scan caution)
to select the new commit before it is deployed to XP. The host never bypasses
the plugin scanner or silently executes arbitrary new upstream commits.

If an update is intentionally rolled back in Hermes, the corresponding XP
binaries are selected by the older plugin version. The update timer retries
without trying to select newer Git commits itself.

Only configure router/firewall restrictions after validating the setup. This
installer does **not** block XP's outbound internet access.
