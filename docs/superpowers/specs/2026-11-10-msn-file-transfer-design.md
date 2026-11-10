# HermesXP MSN file transfer (update 1)

**Intent and why:** The owner should be able to exchange files with Hermes inside an MSN chat, with every byte mediated by the Hermes host. A direct connection to an address inside an invite would let a chat message steer the host at internal services. File bytes must also never become the text Hermes treats as the owner's instructions.

**Who it is for:** The paired MSN owner, talking to the Hermes bot from Messenger. Not other contacts. Not the public internet.

**Goals:**

- Bidirectional transfer on the existing switchboard session (MSNP2P), so the file is already routed through the Hermes MSN server and bot.
- Inbound files stored only under a Hermes transfer inbox, mode `0644`, never executed.
- Outbound files read only from a Hermes transfer outbox, by basename.
- Hermes sees a short notice (name, size, sha256), never the bytes.
- The XP user sees a short plain-text status in the chat, never a host path.
- Host-side tests prove both directions, the refusals, and that an advertised address is not dialed.

**Non-goals:**

- Live proof on the XP machine. That waits for an explicit OK after this source is on `main`. A green host suite does not mean Windows Live Messenger completed a transfer.
- MSNFTP / direct TCP. Invites that ask the host to connect somewhere are declined.
- Sending to any address other than the configured owner.
- Executing, previewing, or indexing file contents.
- Raising the plugin version or touching the XP installer.

**Constraints:**

- Work on `main`. Push and verify the remote commit before any deploy, service restart, or XP action.
- Do not run commands on `192.168.1.78`.
- Control plane stays loopback HTTP with the existing bridge token (`X-Hermes-Token`, 32+ characters) and owner check.
- Hard cap `8388608` bytes (8 MiB). Empty files are rejected.
- Names are ASCII basenames, 1–80 characters, matching `^[A-Za-z0-9][A-Za-z0-9 ._()-]{0,79}$`. Reject path separators, `..`, leading dots, Windows device names (`CON`, `PRN`, `AUX`, `NUL`, `COM1`–`COM9`, `LPT1`–`LPT9`), and a blocked extension appearing anywhere in the name: `exe`, `bat`, `cmd`, `com`, `scr`, `pif`, `vbs`, `vbe`, `js`, `jse`, `wsf`, `wsh`, `msi`, `dll`, `lnk`, `ps1`, `hta`, `cpl`, `msc`, `jar`, `gadget`.
- Only EUF-GUID `{5D3E02AB-6190-11D3-BBBB-00C04F795683}` is a file offer. Other session types are declined.
- No new dependencies. Node stdlib and the existing Python adapter only.

**Approaches:**

1. **In-band MSNP2P on the switchboard (chosen).** File chunks are `application/x-msnmsgrp2p` payloads the bot already receives through the Hermes MSN server. Nothing dials an invite address. Host tests can assemble real bytes without XP. Cost: a Windows Live client that refuses switchboard data and insists on a direct socket will not finish until a later, still-mediated transport is designed. That failure is safer than dialing.
2. **Direct TCP / MSNFTP to the address in the invite.** This is how older Messenger completes a transfer, and it is rejected. The address is attacker-controlled even when the sender is the owner (a compromised or confused client, or a crafted payload the server relays).
3. **Chat commands that read an arbitrary host path.** Rejected. A message can ask Hermes to send `/etc/passwd`. The outbox basename is the only handle.

**Chosen how:**

- Codec and store live in `msn-bridge/file_transfer.js`. The switchboard framer already in `msnclient/frame.js` is reused so a split TCP chunk still yields one P2P body.
- 48-byte little-endian P2P header: session id, identifier, offset, total size, length, flags, ack id, ack unique id, ack size. File context is the captured layout: uint32 declared size, uint32 version (2 or 3), uint64 file size at offset 8, UTF-16LE filename at offset 20. Builder writes a 574-byte context, declared size 574, version 2.
- Accept an in-band offer from the owner, reply with an ACK (`flags = 0x02`) and `MSNSLP/1.0 200 OK` carrying the same `SessionID`, then append in-order chunks. Write the file only when the assembled length equals the declared size. A hole, an overlap, or a chunk past the end deletes the partial state and writes nothing.
- Outbound: authenticated loopback `POST /file/send` with `{"to","name"}`, or a gateway `send_file` packet. The bridge reads the outbox file (no symlink escape), sends the invite, and sends chunks only after `200 OK`. Completion means the host queued the bytes and saw the last ACK, not that Messenger displayed the file.
- Gateway event for a received file is exactly `[file received] <name> (<size> bytes, sha256 <hex>)`. Packets that also carry `contents`, `body`, `text`, or `path` are dropped.
- Legacy `text/x-msmsgsinvite` file invites and any session that carries an address are declined with a fixed notice. `dial` is never true.

**Left to the builder:** chunk size (1200 bytes of file data), on-disk name (`<16 hex>_<basename>`), and the exact decline wording, as long as the tests below still describe the observable behavior.

**Not claimed:** end-to-end delivery on the live XP client. The current live-verified remote endpoint remains screenshot-only.

Approved for implementation by the explicit implement / commit / push order for this update. Live XP verification remains unauthorized.
