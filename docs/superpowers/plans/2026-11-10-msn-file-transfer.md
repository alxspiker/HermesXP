# MSN file transfer implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bidirectional MSN chat file transfer mediated by Hermes, with host-side proof and no direct connect.

**Architecture:** A Node codec/store accepts in-band MSNP2P file sessions and serves outbox basenames. The switchboard reuses `MSNPFrameDecoder` so binary MSG bodies survive fragmentation. The Python adapter forwards notices only and requests sends by basename. No listener dials an invite address.

**Tech Stack:** Node.js stdlib, existing HermesXP Python unittest suite, MSNP2P on the current switchboard.

**Spec:** `docs/superpowers/specs/2026-11-10-msn-file-transfer-design.md`

## Global Constraints

- Work on `main`; push and verify `origin/main` before any deploy or XP action.
- Do not contact `192.168.1.78` or restart host MSN services as part of this change.
- Max file size is exactly 8388608 bytes. Empty files are rejected.
- Owner check is case-insensitive against `HERMES_MSN_OWNER_EMAIL`.
- Token compare stays timing-safe. File HTTP is loopback-only, same token header as `/send`.
- File contents never enter the gateway text. `dial` is never true.
- Keep `adapter.py` identical to `hermes-plugin/hermes-msn/adapter.py`. Do not bump `0.7.7`.

## Review Focus

- An invite that names `127.0.0.1` and a port, plus a prompt-injection body, must open no connection and must not forward that body to Hermes. A person would expect "decline", not a callback and not an agent instruction.
- A basename of `../secret` or a symlink pointing outside the outbox must not be read. A person would expect the send to fail closed.
- File bytes that say `SENTINEL_DO_NOT_LEAK_9f3a` must not appear in the gateway notice. A person would expect a name and a hash, not the document.
- A chunk whose offset is not the bytes already accepted, or whose end passes the declared size, must leave no file on disk. A person would expect a rejected transfer, not a partial or smuggled extra.
- A missing token, a wrong token, or a non-owner peer must not store or enqueue a file. A person would expect the same refusal as a text send to a stranger.

---

### Task 1: Codec, policy, and store

**Files:**

- Create: `msn-bridge/file_transfer.js`
- Test: `tests/file_transfer_cases.js` (run from `tests/test_file_transfer.py`)

**Interfaces:**

- Consumes: nothing
- Produces:
  - `sanitizeFilename(name: string) -> string | null`
  - `parseContext(b64: string) -> {filename: string, size: number} | null`
  - `buildContext(filename: string, size: number) -> string`
  - `parseP2P(buffer: Buffer) -> header | null`
  - `buildP2P(fields) -> Buffer`
  - `p2pPayload(mimeBody: Buffer) -> Buffer | null`
  - `TransferStore({owner, root, maxBytes})`
  - `store.receive(peer, p2pBuffer) -> {packets, event, notice, reason, dial}`
  - `store.offer(peer, basename) -> {ok, packets, reason, dial, callId, name}`
  - `store.feed(peer, p2pBuffer) -> {packets, event, notice, reason, dial}`
  - `store.declineLegacy(peer, inviteText) -> {dial: false, notice, packets: []}`
  - `MAX_FILE_BYTES === 8388608`
  - `FILE_GUID === '{5D3E02AB-6190-11D3-BBBB-00C04F795683}'`

- [ ] **Step 1: Write the failing node cases**

Cover: hand-built context parses `note.txt` / size 5; `../note.txt`, `run.exe`, `run.exe.txt`, `NUL.txt` sanitize to null; stranger and wrong GUID decline with `dial === false` and no file; in-order chunks of `hello` write `0644` and sha256 `2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824`; a hole writes nothing; size 8388609 declines; sentinel bytes are absent from `event` and `notice`; outbox symlink escape does not read; offer then hand-built `200 OK` then ACK round-trips `hello`.

- [ ] **Step 2: Run the case file and confirm MODULE_NOT_FOUND**

Run: `node tests/file_transfer_cases.js`
Expected: non-zero, cannot find `msn-bridge/file_transfer.js`

- [ ] **Step 3: Implement the module**

In-band only. ACK flag `0x02`. Chunk size 1200. No `net` connect.

- [ ] **Step 4: Re-run the case file**

Expected: exit 0 and `FILE_TRANSFER_CASES_PASS`

### Task 2: Switchboard framing and bridge routing

**Files:**

- Modify: `msn-bridge/msnclient/main.js` (switchboard uses `MSNPFrameDecoder`, emits `p2p` / `file_invite`, `sendP2P`)
- Modify: `msn-bridge/msnclient/LOCAL-PATCH.md`
- Modify: `msn-bridge/bridge.js`
- Test: extend `tests/file_transfer_cases.js` and `tests/test_file_transfer.py`

**Interfaces:**

- Consumes: Task 1 `TransferStore`, `p2pPayload`
- Produces: switchboard `msg` events `{type:'p2p', user, payload}` and `{type:'file_invite', user, body}`; `sendP2P(dest, buffer)` writes `MSG <trid> D <len>`; bridge `POST /file/send` and gateway `send_file`

- [ ] **Step 1: Write the failing bridge and switchboard cases**

A split P2P MSG on the real `MSNSwitchBoard` (axios stubbed) emits one payload. A legacy invite aimed at a live `127.0.0.1` port produces zero accepts. Bridge stores an owner file, gateway JSON has no sentinel, stranger is ignored, `/file/send` without token is 401, with token enqueues P2P, `../secret` does not enqueue.

- [ ] **Step 2: Run and confirm failure before the bridge/switchboard edits**

- [ ] **Step 3: Implement framing, send, and bridge routes**

Do not log payloads. Do not open a client socket to an invite address.

- [ ] **Step 4: Re-run the new cases**

Expected: pass, and the canary listener accepted 0 connections.

### Task 3: Python adapter notices and basename sends

**Files:**

- Modify: `adapter.py` and `hermes-plugin/hermes-msn/adapter.py` (identical)
- Modify: `tests/test_adapter.py`
- Modify: `README.md` (what is implemented, what is not live-verified)

**Interfaces:**

- Consumes: gateway packets `incoming_file` and `send_file`
- Produces: `MSNPlatformAdapter.send(..., metadata={'file': basename})` writes `send_file`; `standalone_send(..., media_files=['note.txt'])` POSTs `/file/send` on `127.0.0.1` only; unsafe names do not open a connection.

- [ ] **Step 1: Write the failing adapter tests**

- [ ] **Step 2: Run `python -m unittest tests.test_adapter -v` and confirm the new tests fail**

- [ ] **Step 3: Implement both adapter copies**

- [ ] **Step 4: Run the full suite**

Run: `python -m unittest discover -s tests -v`
Expected: all tests OK, including the previous suite.

- [ ] **Step 5: Commit and push `main`, then verify `git rev-parse HEAD` equals `git rev-parse origin/main`**
