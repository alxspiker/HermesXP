# msnclient — local-server patch

Vendored copy of https://github.com/tutmonde/msnclient (GPLv3, sole dependency
axios 0.21.1), with three small changes so the client can talk to a local
msn-server instead of Escargot. Upstream is unmaintained for this use: the
NS host and the Passport login URL are hardcoded in `main.js` with no server
parameter. The patch is env-driven, so with the variables unset the client
behaves exactly as upstream (Escargot).

## Changes (vs upstream main.js)

1. Top of file: added `const https = require('https')` and three constants
   read from the environment:
   - `MSN_SERVER_HOST` (default `'msnmsgr.escargot.chat'`)
   - `MSN_LOGIN_URL` (default `'https://msnmsgr.escargot.chat/login'`)
   - `MSN_LOGIN_INSECURE` (default false; `=1` passes an axios httpsAgent
     with `rejectUnauthorized: false`, for a local HTTPS login URL with a
     self-signed/local-CA cert — never for Escargot)
2. `execute()`: `this.client.connect(1863, 'msnmsgr.escargot.chat', ...)`
   became `this.client.connect(1863, MSN_SERVER_HOST, ...)`.
3. Passport login: `axios.get("https://msnmsgr.escargot.chat/login", ...)`
   became `axios.get(MSN_LOGIN_URL, { ...(insecure agent if set), headers... })`.

4. RNG accept fix (bug in upstream): the invitee's `acceptRequest` was called
   as `acceptRequest(this.email, element[1], element[4])`, but the function
   signature is `acceptRequest(session, auth)` and it writes
   `ANS 1 <selfEmail> <auth> <session>`. That sent the RNG session ID in the
   token position and the bot's own email in the session position, so the
   server's `_m_ans` (`front/msn/msnp_sb.py`, `get_token('sb/cal', token)`)
   rejected it with 911 and closed the switchboard — the caller never got
   JOI and the message was never sent. Fixed to
   `acceptRequest(element[1], element[4])` (session ID, then CKI token),
   which produces the correct `ANS 1 <email> <token> <sessionID>`. Found by
   tracing a failed owner→bot round-trip on the live local server (bot log
   showed RNG accepted but no message ever arrived).
5. Switchboard receive logging: the `MSNSwitchBoard` data handler now logs
   every parsed message (`[DEBUG] [SWITCHBOARD] recv:`), matching the
   library's existing `console.log(parsed)` habit on the NS connection.
   Without it the switchboard is silent, which made a failed message
   exchange undiagnosable (the RNG accept showed, then nothing).
6. Stale switchboard sessions (bug in upstream): the RNG handler only created
   a switchboard `if (this.switchboard[inviter] == undefined)`, and the
   cleanup deleted it on `msg.type == 'bye'` — but `parseMessageSB` reports
   BYE as `'leftChat'`, so the delete never fired. The first session with a
   user worked; every later invite from the same user was silently ignored
   (log showed "Accepting request" and then nothing), and `sendMessage`
   kept writing to the dead socket. Fixed: a new invite always replaces any
   existing switchboard for that user (destroying its socket), the cleanup
   now fires on `'leftChat'` as well as `'bye'`, and `sendMessage` starts a
   new session when the existing switchboard's socket is destroyed. Found
   by tracing a second round-trip test on the live local server: the first
   ping arrived, the second test's invite was accepted but no switchboard
   was ever created.
7. Switchboard file frames: the switchboard data handler now uses
   `MSNPFrameDecoder` so a length-prefixed MSG split across TCP chunks is
   one body. `application/x-msnmsgrp2p` is emitted as `{type:'p2p'}` and a
   `text/x-msmsgsinvite` file invite as `{type:'file_invite'}`. `sendP2P`
   writes `MSG <trid> D`. Text MSG still goes through `parseMessageSB`.
   The bridge, not this client, decides whether a file is stored. This
   client never dials an address from an invite.

## Local defaults used by the HermesXP installer

- `MSN_SERVER_HOST=127.0.0.1` (bot runs on the same ZBook as the server)
- `MSN_LOGIN_URL=http://127.0.0.1:8081/login` (plain HTTP on loopback; the
  server's HTTP front — no TLS needed for the bot)

## Re-applying to a newer upstream

The patch is three edits; re-apply by hand against a fresh upstream copy and
keep the env-var names. Verify with `diff -u` against the upstream file.
