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
   drive. No GitHub connection is used by XP.
3. Pair each XP device once by giving it a unique 64-hex token in
   `hermesxp.ini` under `[Remote]` as `Token=<token>`, with
   `AllowedHostIP=<Hermes LAN IPv4>`. Store that same token in a **private**
   file on Hermes (mode 0600), then run
   `python3 ~/.hermes/plugins/hermes-msn/tools/hermesxp_update.py pair XP-NAME XP-LAN-IP --token-file /private/token-file`.
   **Never** put the pairing token into GitHub or a public LAN installer.

After pairing, use `hermes plugins update hermes-msn`. Hermes selects,
reviews and installs the new Git commit; the update watcher builds or
downloads verified generic artifacts on Hermes and sends them over the LAN.
Offline XP devices retry when available. A separate Windows XP helper
verifies startup and can restore the previous executable. The XP has no
dependency on public internet access.

If an update is intentionally rolled back in Hermes, the corresponding XP
binaries are selected by the older plugin version. The update timer retries
without trying to select newer Git commits itself.

Only configure router/firewall restrictions after validating the setup. This
installer does **not** block XP's outbound internet access.
