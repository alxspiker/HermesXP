# HermesXP / Windows Live Messenger — Hermes Talk audio bridge

### Automatic address recovery (v0.7.2)

Once paired, HermesXP automatically recovers from a Windows XP device
switching Ethernet/Wi-Fi or changing its DHCP-assigned local IP, **and**
from the Hermes host changing its private LAN IP. The XP companion sends
an 8-second-interval UDP discovery challenge on port **18773**. The
Hermes host verifies the packet using the existing per-device 256-bit
pairing key, returns an HMAC-SHA256 authenticated challenge containing
its current LAN IP, and accepts XP's new IP only after XP's signed ACK.
The pairing secret is never broadcast, and anonymous discovery messages
cannot update the device registry.

On successful discovery, the XP companion updates its [Hermes] ServerIP
and [Remote] AllowedHostIP configuration and, when the Hermes host address
actually changed, updates the two managed MSN hosts-file entries and
relaunches Messenger to reconnect to the new server. Existing unrelated
hosts entries are preserved. The modern MSN bridge reselects its IP-bound
RTP listener based on the paired device's active LAN subnet; the discovery
host also updates its managed MSN redirect/TLS binding configuration when
the server address changes. If the existing local MSN certificate has an
old IP SAN, the server reissues **only its TLS leaf** with the new IP under
the **same existing CA and server private key**, so XP's existing trusted
root remains valid. OpenSSL and the original CA/private key must still
be available on the Hermes host. This avoids hardcoded per-user IPs. It
does not require SSH, an internet API, VPN, fixed DHCP leases, or re-pairing.

The Hermes server's LAN firewall must allow **UDP 18773 from RFC1918
private networks**. The host updater will configure this scoped inbound
rule automatically when UFW and noninteractive administrator authorization
are available; otherwise it logs that the owner must authorize the LAN
firewall rule. The XP side uses outbound UDP and authenticated replies.
Neither the discovery protocol nor this port provides a remote shell.

The authenticated XP endpoint GET /network/status reports discovery state,
verified response count and a Winsock/CryptoAPI error code, without the
pairing key. No new settings are necessary on users' installed XP systems.
The host Python client also exposes
HermesXPClient(device["host"], device["token"]).network_status().

### Generic Windows XP service management (v0.7.0)

HermesXP now manages **any installed Windows service by its SCM service name**,
not a FreeSSHD-specific repair button. The paired Hermes host can query
status, start, stop or restart services through XP's Service Control Manager.
The authenticated endpoint is POST /system/service with a canonical body such
as action=status&name=AudioSrv or action=restart&name=Spooler. It does not
accept arbitrary shell commands, executable paths, service installations,
or configuration changes.

From a Hermes host with a paired device in the private registry:

    python3 -m tools.hermesxp_services --device XP-Lab --service AudioSrv status
    python3 -m tools.hermesxp_services --device XP-Lab --service Spooler restart

The client reads the pairing token from the protected device registry.
The XP endpoint uses the same exact trusted-source-IPv4 check and 64-digit
hex pairing token as the screenshot and remote UI routes, strictly parses
the service name and action, and uses the logged-in Windows account's
existing SCM permissions. Responses report the service state and Windows
error code (e.g., service missing, access denied or operation pending).
Service shutdown is bounded to ~2.4 seconds to avoid hanging the HermesXP
listener when a Windows service is stuck. Restarting services can disrupt
connected clients; Hermes must authorize the requested action.

As with the existing remote UI, service management uses **plaintext HTTP on
the trusted LAN**. Do not expose it to untrusted machines or the internet.

### Native Messenger calls (v0.7.6)

**Native Call toolbar integration (v0.7.4).** When the paired owner presses
the Call button in Windows Live Messenger, the MSN bridge receives WLM's
type-11 rendezvous metadata. It authenticates the sender, sends WLM's
capability reply and initiates a native, reciprocal SIP invitation through
the same G.711 RTP/Hermes Talk session used by /nativecall. The delay is
300 ms, not 650 ms; duplicate requests and post-hangup negotiation frames
are suppressed to prevent a new call starting after the End Call button.
Messenger's native End Call button is handled via the tunneled SIP BYE.
Unanswered reciprocal invitations now expire after 20 seconds rather than
blocking the next call attempt for the entire 30-minute maximum call duration.

**Limit:** The legacy MSN service does not implement WLM 2009's original
outgoing VOIP control plane (historically 0x80EE00C8). Therefore the Call
button is handled through a reciprocal SIP invitation, which may still
display Messenger's native Accept prompt and cannot guarantee the original
outgoing WLM window stays connected. This is not an OS-wide WLM patch or a
full replacement MSN VOIP service. Exact one-click calling requires a
real-device acceptance test; there is no claim of verified interoperability
until that passes.

**Hermes agent call controls.** The plugin registers a tool named msn_call
with action start, end or status. It calls the existing signed-in MSN bot's
authenticated loopback interface on 127.0.0.1:18769, using the same pairing
credentials and owner restriction as standalone send_message. /nativecall,
/call and /hangup remain available as MSN chat commands. No arbitrary
recipient, XP command execution, microphone capture or new voice provider
is introduced.

**Optional RTP packetization (v0.7.3).** Windows XP audio hardware and
Messenger's internal receiver can be sensitive to extremely short playback
queues. The bridge supports either standard 20 ms PCMU packets (default)
or an experimental 40 ms PCMU packet size without changing sample rate or
codec. Use the host-only environment setting:

    HERMES_MSN_RTP_PACKET_MS=40

Then restart the MSN bridge. The SDP advertises the chosen packetization,
and sender packet deadlines, sequence numbers, and RTP timestamps follow it.
Incomplete 20 ms speech tails are padded with PCMU silence rather than
discarded. Change this back to 20 if a Messenger client cannot play 40 ms
packets. This controls outbound Hermes-to-XP media only; Messenger may
continue sending 20 ms packets to Hermes.

**Evidence and limits:** A controlled six-second continuous PCM test passed
through Talk's Python output, Node's PCMU converter, and the 20 ms RTP
scheduler with all 300 speech packets continuous. On an MSI Wind U100 XP
machine, a separate 8 kHz/16-bit silent waveOut timing test completed 598
of approximately 600 20 ms frames with an 80–160 ms playback queue, but
only 431 with a 40 ms queue (repeated). That indicates a severe sensitivity
to short XP waveOut buffer queues; it does not establish how Messenger
internally buffers RTP or guarantee that 40 ms PCMU packetization helps.
The sound-card test is in xp-client/diagnostics/waveout-timing.c. It neither
records user audio nor changes XP settings.

Windows Live Messenger 2009 owns the native call UI, microphone and speakers.
HermesXP runs **no ASR, TTS, voice LLM, or voice provider logic**. A paired XP
machine sends PCMU/8000 RTP over the private LAN to Hermes, where an
**authenticated, loopback-only streaming audio adapter** invokes the installed
**Hermes Talk** plugin. Talk owns provider/model/voice selection, ChatGPT/Codex
sign-in, audio turn detection, conversations and Hermes tool delegation. Talk
updates are not copied into HermesXP.

**Prerequisites:** Hermes Talk must be installed and enabled on the Hermes host.
The HermesXP host update registers `hermes xpvoice`, which starts the native
Talk audio adapter on `127.0.0.1:18771`. The Windows XP executable no longer
has the old five-second voice button, and the old LAN `:18770` speech service
and `/voice/turn` API have been removed.

Configure the native MSN connection in the PRIVATE
`~/.hermes/msn-bridge.env` on the Hermes computer:

```ini
MSN_BOT_PROTOCOL=18
HERMES_MSN_NATIVE_CALL=1
# Optional: preferred local address (automatically ignored if no longer assigned)
# HERMES_MSN_NATIVE_IP=<Hermes host's preferred private LAN IPv4>
```

The bridge token and owner restriction are installed/preserved separately.
Restart `hermes-msn-bridge.service` and `hermes-xp-voice.service` when changing
host settings. In the Messenger chat with Hermes, send **`/nativecall`** or
**`/call`**, then accept the call in Messenger. Use `/hangup` or Messenger's
End Call button to finish. The built-in outgoing Call toolbar still has the
old MSN service limitation (`0x80EE00C8`); Hermes offers a reciprocal native
invitation when it receives the rendezvous request.

### Voice provider configuration — owned by Hermes Talk

Change provider/model/auth/voice in the **Hermes Talk plugin**, not HermesXP.
For example, Talk's OpenAI Realtime lane uses its Hermes/Codex sign-in when
available, while its GPT-Live subscription lane requires Talk's own Codex CLI
and task setup. Talk supports other providers subject to its own dependencies,
credentials and compatibility checks. HermesXP has no separate API-key field
or paid provider fallback.

For **GPT-Live** (`TALK_VOICE_MODE=live`), the Talk plugin requires an explicit
**authorized canonical Hermes task**. Select the task using Talk's own
`hermes talk --targets` command, then set the target on the Hermes host in
its private `~/.hermes/msn-bridge.env`:

```ini
HERMES_XP_TALK_TARGET=<authorized Talk target ID>
# Optional: HERMES_XP_TALK_PEER=local
# Optional: HERMES_XP_TALK_PROFILE=default
```

Talk's `TALK_TASK_API_URL` and session access must be configured as documented
by Hermes Talk for native task calls. If the configured Talk provider cannot
connect, HermesXP **fails closed**; it does not silently switch to LFM3,
another provider or a metered API. A Talk update may alter its own options,
requirements or support; inspect its diagnostics after upgrading.

### Audio routing and security

- The MSN bot accepts calls only from the configured owner, and SIP/SDP RTP
  only from the paired XP device's configured private IPv4. Never expose
  UDP/19740 to the public internet.
- MSN RTP PCMU/8000 is converted to/from Hermes Talk's PCM16/24000 stream
  on the Hermes host. Provider-native turn detection replaces HermesXP's
  legacy silence-record/transcribe/poll logic.
- The Talk adapter listens on **127.0.0.1:18771 only**, authenticates using
  the private bridge token, allows one call at a time and bounds audio buffers.
  Nothing on Windows XP receives Talk credentials or provider tokens.
- A 20ms monotonic-clock RTP sender provides continuous packets (silence when
  Talk has not produced audio), with a short initial playback buffer. Native
  Windows Live Messenger is still an experimental G.711 endpoint; its speaker
  quality, jitter handling and echo cancellation have not been proven across
  every XP sound card and provider.

**Audio pacing and echo fix (v0.6.1):** Hermes Talk can produce speech much
faster than real time. The host audio adapter now splits that output into
20ms PCM packets, sends at a monotonic clock rate with an initial 80ms
jitter-buffer preroll, and keeps up to 20 seconds of provider speech queued
without flooding the Messenger RTP bridge. The earlier unpaced forwarding
caused repeatedly logged two-second queue overflows and clipped speech.
During provider playback, the XP microphone path uses an acoustic level gate
to reduce speaker feedback into Talk and prevent repeated false turn starts.
Much louder deliberate speech can still interrupt; this is a simple gate,
not acoustic echo cancellation. Set Talk's `TALK_ECHO_GATE=off` only when
using headphones or testing microphone behavior. Talk remains the sole owner
of provider selection, conversation and tools.

**RTP smoothing (v0.6.2):** The Messenger RTP sender now requires an initial
160ms speech buffer and never emits a catch-up burst after an event-loop stall;
it advances timestamps over missed time instead. Duplicate/out-of-order
microphone RTP is ignored. At hangup the host logs input packet loss,
timer slips and output underflows as a concise, content-free diagnostic,
so a future real-call problem can be measured rather than guessed.
Provider behavior and response creation remain owned by Hermes Talk.

**Direct foreground Hermes tools (v0.6.3):** The previous Talk session
exposed only Talk's limited tool list, including background `delegate_task`.
To execute requested actions from the Messenger voice call without the
delegation conversation, opt in on the Hermes host in private
`~/.hermes/msn-bridge.env`:

```ini
HERMES_XP_TALK_DIRECT_TOOLS=1
```

This requires the matching `hermes-talk-custom` fork v0.22.3+, whose
explicitly scoped classification permits the authenticated HermesXP
`hermes_execute` foreground tool while refusing unknown voice tools on
every other surface. HermesXP advertises one voice tool: `hermes_execute`,
which runs the locally installed `hermes -z`
using the **CLI's existing tools/models and approval policy**, waits for
the reply and speaks it through Talk. This is a foreground **new Hermes CLI
turn**, not a background delegation, not the existing MSN text session,
and not an unbounded realtime direct gateway attachment. It can take longer
than ordinary conversation; one command has a 3-minute limit and hanging up
terminates a running command. Do not mistake a tool admission for successful
execution; Hermes' result must report what actually happened.

**Security:** Voice is not a speaker biometric. Only enable this on a
physically trusted paired XP computer with a private network, because
anyone who can speak into its microphone during your MSN call may request
actions carrying the CLI account's configured permissions. No CLI token
or Hermes provider credential is transferred to XP. The tool is never
advertised to Discord or other Talk surfaces.

**Persistent native MSN audio diagnostics (v0.6.3):** RTP waits for a
400ms startup speech buffer, but short underruns within a speech burst
do **not** restart that full wait. It logs content-free packet-loss,
audio-underflow, clock-skip and buffer statistics every 12 seconds while
an MSN call is active, including when Windows Live Messenger omits SIP BYE.
These measurements help distinguish network/scheduler gaps from the XP
decoder or sound card.

**Playback continuity (v0.6.4):** The last real Messenger call showed no
incoming RTP packet loss and no RTP timer skips, but 28 playback
underflow packets and three playback interruptions. The speech-start
queue is now 800ms instead of 400ms. During playback, echo suppression
keeps the Realtime provider's 20ms input clock continuous by **replacing**
suppressed microphone audio with PCM silence (instead of deleting frames),
and covers up to 1.1s of delayed XP speaker output. This is still a
heuristic acoustic gate rather than full acoustic echo cancellation.
For a physically trusted paired operator, one `hermes_execute` voice tool
now handles real Hermes tasks; the redundant `get_current_time` tool
has been removed from HermesXP and from the matching Talk fork 0.22.4+.
More buffering adds about 400ms to the start of long answers.

**Audio rollback (v0.6.6):** On RUITER, the v0.6.5 changes made playback
perceptibly worse despite low RTP underflow counts. Restored the
v0.6.4 native-call and PCM-adapter behavior: no forced half-duplex mode,
no faded replay of missing samples, and no 850ms wait before short replies.
The working foreground `hermes_execute` tool, the 800ms RTP buffer, echo
timing preservation, and periodic content-free RTP diagnostics remain.
The regression's low underflow count did not establish better perceived
audio, and these changes are not treated as a permanent choppiness fix.

**RTP sender clock correction (v0.6.7):** Replaced the 10ms polling
`setInterval` with a one-shot `setTimeout` aimed directly at the next
20ms monotonic RTP deadline. The old sender periodically emitted two
20ms packets less than 15ms apart despite reporting zero skipped packets.
On the Debian host, a 4.5-second synthetic stream measured 9 such short
intervals with the old polling schedule, versus 0 with deadline scheduling.
The changed sender additionally records the counts of intervals shorter
than 15ms and longer than 25ms, and its longest observed packet gap, in
the existing periodic `Messenger RTP` call statistics. The PCMU codec,
800ms audio preroll, and Hermes Talk/provider/tool routing are unchanged.
This does not establish whether XP's receiver jitter buffer eliminates
every remaining audible dropout; compare live call quality and statistics.

**Unexpected call-end recovery (v0.6.8):** A real long call ended after
Hermes Talk reported a session task cleanup timeout while its foreground
tool was beginning. HermesXP no longer treats every provider-session end
as an instruction to hang up the physical MSN call. It keeps the existing
authenticated TCP media leg and its one pair of audio threads, clears
orphaned playback and microphone frames, and starts a fresh Talk session.
Up to three reconnects are allowed per call with short backoff, so a
persistent configuration/provider failure cannot loop indefinitely.
Genuine MSN hangups still close the socket immediately. These reconnects
start a fresh model conversation, so context from the earlier voice segment
may need restating. Hermes Talk custom fork v0.22.5+ reports the primary
task-exit reason and cancels pending foreground work during cleanup rather
than masking it with a generic six-second timeout. Both changes preserve
the v0.6.7 RTP packet pacing and the existing Hermes execution tool.

**Audio and call diagnostics (v0.6.9):** On a real v0.6.8 call, Hermes'
20ms RTP sender stayed within 15–25ms timing throughout, with zero
incoming packet loss, but Talk sent 13 playback-clear events and the
sender experienced six brief output underflows. A playback-clear event
does not necessarily mean audible speech was cut off; it may reset an
empty buffer on a normal operator turn. The periodic and final statistics
now separately show resets during active/queued speech and milliseconds
of buffered output actually discarded by those resets. Audio encoding,
volume, buffering, echo gating and packet timing are intentionally
unchanged. The matching Talk custom fork v0.22.6+ fixes a real
host-tool-batch cleanup crash that otherwise closed MSN unexpectedly
when provider recovery was attempted.

To diagnose:

```bash
hermes talk doctor
hermes xpvoice --help
systemctl --user status hermes-xp-voice.service hermes-msn-bridge.service
journalctl --user -u hermes-xp-voice.service -n 50 --no-pager
```

To disable native calls while keeping MSN text messaging, remove
`HERMES_MSN_NATIVE_CALL` and `MSN_BOT_PROTOCOL` from the bridge environment
and restart `hermes-msn-bridge.service`.

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
