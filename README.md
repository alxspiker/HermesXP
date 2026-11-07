# Hermes XP / MSN Messenger Bridge — prototype v0.1

**Status: development prototype.** A native Windows XP x86 companion and Hermes gateway platform adapter have been built; the Escargot/MSN login path requires your own accounts and has **not** been tested end-to-end. Do not call this a working self-hosted MSN server.

The XP companion is **not an agent runtime or remote execution service**. It is a read-only TCP connectivity probe. The modern host has a Hermes platform adapter and a separate Node.js bridge for an experimental MSN bot library.

## Contents

| File | Runs on | Function |
|---|---|---|
| `dist/HermesXP.exe` | Windows XP SP3 x86 | Win32 graphical probe, no external DLLs / CRT / WMI |
| `hermes-plugin/hermes-msn/plugin.yaml` + `adapter.py` | Hermes host, Python | Registers platform `hermes_msn`; handles inbound/outbound messages |
| `msn-bridge/bridge.js` | Hermes host, Node 18+ | Connects MSN bot to Hermes via authenticated localhost JSON-lines |
| `tools/probe_server.py` | Hermes host, Python | Optional stand-alone probe test *without* Hermes |
| `xp-client/*` | Build machine | C source, import definitions, clang/lld build script |
| `tests/` | Build machine | Simulated adapter loopback protocol tests |

## Architecture

```text
Original MSN Messenger on XP  ---> Escargot revival service
                                           |
                                    MSN bot account
                                           |
                              msn-bridge/bridge.js (Node)
                                           | loopback 127.0.0.1:18764 + secret
                                 Hermes MSN platform plugin
                                           |
                                    Hermes gateway / agent

HermesXP.exe on XP --> LAN port 18765 --> read-only host probe
```

**There is no custom MSNP server in this release.** MSN Messenger must be patched/configured for the Escargot network, and the Hermes bot requires its own Escargot login. This plugin does not automatically rewrite the original client or store Hermes LLM API keys on XP.

## Step A: test the XP executable independently

1. On the modern host run `python3 tools/probe_server.py --bind YOUR_LAN_IP` (for example, `192.168.1.20`). Restrict the host firewall port 18765/TCP to the XP device's IP only. Run this **only on a trusted or isolated LAN**.
2. Copy `dist/HermesXP.exe` to Windows XP and launch it. Enter the modern host LAN IP and click **Test connection**.
3. It should report **Hermes host reached! Probe OK. Not yet paired.** No services are installed and no configuration is changed.
4. Stop `probe_server.py` after testing. Do not run this alongside the plugin probe listener on the same IP/port.

If it fails, check host IP, Windows/host firewall, routing, and that port 18765 is listening. Avoid the XP WMI paths that crashed Ruiter.

## Step B: install Hermes gateway adapter on the modern host

1. Copy `hermes-plugin/hermes-msn` to `~/.hermes/plugins/hermes-msn` on the **Hermes host**, not on XP.
2. Generate a secret locally on the host: `python3 -c 'import secrets; print(secrets.token_hex(32))'`
3. Set the following in your Hermes **profile's** `.env` (or service environment). The same token must be supplied to the Node bridge; keep it secret:

   ```ini
   HERMES_MSN_BRIDGE_TOKEN=<the_generated_secret>
   HERMES_MSN_OWNER_EMAIL=<your_escargot_email>
   HERMES_MSN_ALLOWED_USERS=<your_escargot_email>
   # Optional: your HOST's private LAN IP to enable the read-only XP probe
   HERMES_XP_PROBE_BIND=192.168.1.20
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

## Step C: make MSN Messenger reach Hermes

**Requires Escargot accounts.** See https://escargot.chat/connect/guides/ to patch an original MSN Messenger client and troubleshoot XP TLS/login issues. The specific steps depend on which MSN version Ruiter has (Help → About). These steps are *not* performed by HermesXP.exe.

1. Create two Escargot accounts: one for the original MSN Messenger client on Ruiter, another for the Hermes bot.
2. Patch/configure the original Messenger for Escargot using their instructions; do not get a random modified EXE from an untrusted source.
3. On the **modern host**, from `msn-bridge/`, install the experimental library:
   ```sh
   git clone https://github.com/tutmonde/msnclient msnclient
   cd msnclient && npm install && cd ..
   ```
   That library is GPLv3 and explicitly marked under development. It is **not bundled** in this archive; its old dependencies may need security review and updates.
4. Export environment variables to the modern Node process (do not put secrets in source code):
   ```sh
   export MSN_BOT_EMAIL='bot_account@example.com'
   export MSN_BOT_PASSWORD='bot_password'
   export HERMES_MSN_BRIDGE_TOKEN='same_secret_as_gateway'
   export HERMES_MSN_OWNER_EMAIL='your_account@example.com'
   node bridge.js
   ```
5. Sign in to the original Messenger on XP, add the bot's email to your contact list, and send it a message. Only the configured owner address is allowed through the bridge into Hermes. The Hermes gateway itself must be running.

**Not verified:** Escargot login, add-contact handshake, MSN version compatibility and actual message round-trip with the old XP client. They require a live test and valid test accounts. An outdated MSNP9 bot library might need fixes if the revival service has changed. We do not claim those steps already work.

## Security boundaries / known limitations

- XP is unmaintained. Isolate it in a VLAN or filtered LAN. Restrict its outbound access to the necessary revival service if using Escargot; this release does not configure that network isolation.
- The XP probe is **unencrypted and unauthenticated** by design, and only exchanges a machine name and OK/BAD result. It does not grant device control or prove identity. Never treat a positive response as pairing.
- The MSN bridge is plaintext **loopback-only** and protected with a long shared token. Do not expose port 18764 to the LAN or internet.
- User address filtering is applied in both Node and Python. Other Messenger contacts cannot submit agent messages through this code, but the public MSN service is a separate trust boundary.
- No remote code execution, auto-installation, service installation, file modification or Windows Registry edits in this prototype.
- Nothing here bypasses XP security support end-of-life or fixes its browser/TLS stack.
- XP executable is cross-compiled, PE32/Windows 5.01 verified, but not run/tested on a Windows XP installation.
- To uninstall the prototype, delete `HermesXP.exe`, disable/remove the Hermes plugin, stop Node and remove its environment secrets. No XP OS settings are modified.

## Build and test

`cd xp-client && ./build.sh` uses LLVM Clang + lld-link; it generates small import libraries from bundled `.def` files and fixes 32-bit stdcall name decoration for Windows DLL imports, needing no Microsoft SDK. On a Linux build machine with Clang and lld-link installed, verify with `llvm-objdump -p HermesXP.exe`. The EXE uses only KERNEL32, USER32 and WS2_32, targets Windows GUI subsystem 5.01 and x86.

`python3 -m unittest discover -s tests -v` tests the adapter protocol with API stubs. It **does not** assert compatibility with installed Hermes or public MSN.

## Next milestone

Test XP native GUI on Ruiter, identify Messenger version, verify Escargot login, then fix the experimental MSN bot library/adapter until a true MSN → Hermes → MSN conversation is observed. After that, add authenticated device pairing and limited XP tools (without opening a remote shell by default).
