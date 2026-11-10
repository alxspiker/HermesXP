# HermesXP Offline Message Queue Design

**Intent and why:** A text Hermes already accepted for the paired MSN owner must not disappear because the loopback bridge socket is down or the MSN bot is not signed in. Today `MSNPlatformAdapter.send` returns `MSN bridge is offline` and drops the body. The Node `/send` path returns 503 when `client.active !== true` and also drops the body. The bridge process exits on MSN close so the supervisor can restart it; an in-memory queue dies in the exact restart that performs reconnect. Cron and gateway replies sent during that window are lost. This change keeps those texts on the Hermes host and pushes them, in order, when that hop reconnects.

**Who it is for:** The paired owner, and any Hermes path that already sends owner-only text (gateway reply, `send_message`, CLI/cron standalone sender).

**Goals:**
- Persist owner-bound text when the gateway has no authenticated bridge socket, and write those JSON lines to the bridge as soon as the next hello succeeds.
- Persist owner-bound text when the MSN bot is not signed in, including across the bridge process exit/restart, and call `sendMessage` in order when the bot emits `connected`.
- Persist inbound owner texts that could not be written to the gateway, and replay them after the next authenticated hello, including across a bridge restart.
- Cap each lane at 64. Outbound overflow rejects the new text and keeps the earlier ones. Inbound overflow drops the oldest, matching the previous 16-item memory backlog, and logs the drop.
- Queue files are host-local, mode 0600, and contain no bridge token.
- Return success to Hermes only after the text is either handed to a live writer or fsynced into the queue. A successful offline accept must not be `retryable`, or Hermes will send a second copy.
- At-least-once from queue to the next hop. A crash after `sendMessage` returns and before the ack can duplicate. That is accepted. Exactly-once is a non-goal.

**Non-goals:**
- Any command, launch, or file change on 192.168.1.78. No XP client change. No plugin version bump (0.7.7 stays; a bump is what the updater treats as an XP client release).
- Media, file transfer, or non-owner recipients.
- Proving Windows Live Messenger displayed the text. `sendMessage` resolving only means the local library accepted it, same as today.
- A retry loop that calls `sendMessage` again before the next reconnect.

**Constraints:**
- Work on `main`. Push the source commit and verify the remote hash before any live test. This change has no live XP test.
- `SendResult` is a fixed dataclass. Offline state goes in `raw_response={"queued": true, "offline": true}`, not extra constructor fields.
- Root `adapter.py` and `hermes-plugin/hermes-msn/adapter.py` must stay byte-identical.
- Tests must not write `~/.hermes/hermesxp-*-queue.json`. They set `HERMES_MSN_OFFLINE_QUEUE` and `HERMES_MSN_BRIDGE_QUEUE`.
- Default gateway port stays 18764. Tests may set `HERMES_MSN_GATEWAY_PORT` so they do not attach to the live adapter.

**Approaches considered:**
1. In-memory adapter queue only. Lost on gateway restart, and blind to MSN-down while the socket is up. Rejected.
2. In-memory Node backlog only. The process exits on MSN close, so reconnect destroys the queue. The existing inbound backlog already has this limit. Rejected as the whole design.
3. One shared queue file for Python and Node. Two writers, no lock, easy to clobber a message the other process already acked. Rejected.
4. Two durable lanes. Adapter file for texts not yet handed to the bridge. Bridge file for texts not yet handed to MSN, plus inbound texts not yet handed to the gateway. Each lane flushes on its own reconnect. Chosen.

**Chosen behavior:**
- Adapter `send` to a non-owner still fails and writes nothing.
- Adapter `send` with no writable bridge truncates to 4000 characters, appends `{id,to,text,queued_at}`, fsyncs, returns success with that id.
- After `hello_ok`, the adapter holds the write lock and pushes pending items in file order, acking each only after `drain`. A write error stops the flush and leaves the remainder.
- A corrupt or unreadable queue file is not replaced. That send fails. The bytes on disk stay as they were.
- Node `/send` and gateway `send` packets for the owner go through one acceptor. If the bot is inactive, a flush is in progress, or older outbound items are still queued, the text is appended and later flushed. Otherwise it is passed to `sendMessage` as today.
- On `msg.type === 'connected'` (the library sets `active = true` before the event), flush outbound head-to-tail. A `sendMessage` throw stops the flush and leaves that item queued.
- Inbound owner messages that `write()` cannot deliver are appended to the bridge file. Gateway hello replays them, then deletes each acked item. Over 64, drop oldest.
- Standalone HTTP keeps 202 for an accepted send. Offline accept adds `"offline": true` and `message_id`. Queue full or unreadable queue is 503, not a fake 202.

**Calls made here, not by the requester:** host-only files under `~/.hermes`; cap 64; reject-new on outbound overflow; drop-oldest on inbound overflow; no version bump; no XP contact.

Approved by the dispatch that ordered this feature implemented, tested, committed, and pushed. No XP action is included.
