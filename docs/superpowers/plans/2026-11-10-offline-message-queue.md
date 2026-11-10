# Offline Message Queue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist owner-bound HermesXP text while the bridge socket or MSN session is down, and push it in order when that hop reconnects.

**Architecture:** Two host-local JSON files. The Python adapter queues outbound text until the Node bridge authenticates, then writes the same `send` lines it would have written live. The Node bridge queues outbound text until `client.active` and inbound text until the gateway hello, and both lanes survive the process exit the supervisor uses to reconnect. Neither file is shared. Accepting a queue write returns success so Hermes does not retry a second copy.

**Tech Stack:** Python 3.13 unittest, Node 22, existing JSON-lines bridge on 127.0.0.1:18764, standalone HTTP on 127.0.0.1:18769.

**Spec:** `docs/superpowers/specs/2026-11-10-offline-message-queue-design.md`

## Global Constraints

- Work on `main`. Do not run anything against 192.168.1.78. Do not bump plugin version `0.7.7`.
- Root `adapter.py` and `hermes-plugin/hermes-msn/adapter.py` stay byte-identical. Same for both `plugin.yaml` files.
- `SendResult` fields are fixed. Offline success uses `raw_response={"queued": True, "offline": True}` and `retryable=False`.
- Outbound cap 64, reject the new item. Inbound cap 64, drop oldest. Text cap 4000. Owner only.
- Queue files mode `0600`. Corrupt files are not rewritten.
- Tests set `HERMES_MSN_OFFLINE_QUEUE` and `HERMES_MSN_BRIDGE_QUEUE` to temp paths. Default gateway port remains 18764.
- A 202 from `/send` still does not mean Messenger displayed the text.

## Review Focus

- A successful offline accept must not be retryable, or Hermes sends a duplicate when the bridge returns.
- Flush must ack only after the next hop accepts the write; a mid-flush error must leave the failed item and the tail on disk.
- A corrupt queue file must survive a later send attempt unchanged.
- Unauthorized recipients must not create a queue file.
- An online send must not also remain queued, or reconnect duplicates it.
- Outbound item 65 must fail while item 1 is still delivered first.
- Node must not flush outbound before `active === true`, and must not ack a `sendMessage` that threw.
- Inbound texts must still be delivered after the bridge process is killed and started again.
- Tests must not create `~/.hermes/hermesxp-gateway-offline-queue.json` or `hermesxp-bridge-queue.json`.

---

### Task 1: Adapter persists offline sends and pushes them on hello

**Files:**
- Modify: `hermes-plugin/hermes-msn/adapter.py` (then copy bytes onto `adapter.py`)
- Test: `tests/test_offline_message_queue.py`

**Interfaces:**
- Consumes: `MSNPlatformAdapter.send(chat_id, content) -> SendResult`
- Produces: `OfflineOutboundQueue(path).enqueue(to, text) -> {"ok": bool, "id": str, "error": str}`; `pending() -> list`; `ack(message_id) -> None`. File shape `{"items":[{"id","to","text","queued_at"}]}`.

- [ ] **Step 1: Write the failing test** `test_offline_sends_persist_and_push_in_order_on_reconnect` and `test_online_send_is_not_left_in_the_offline_queue`.

- [ ] **Step 2: Run** `python -m unittest tests.test_offline_message_queue.TestAdapterOfflineQueue -v` and confirm the offline send is not persisted.

- [ ] **Step 3: Implement** `OfflineOutboundQueue` and call it from `send` / post-hello flush in the plugin adapter. Copy the file onto the root adapter.

- [ ] **Step 4: Re-run the same test.** Expected: PASS.

- [ ] **Step 5: Commit** after the later tasks are green. Do not push a red tree.

### Task 2: Overflow, stranger, and corrupt file

**Files:**
- Modify: `hermes-plugin/hermes-msn/adapter.py` and root `adapter.py`
- Test: `tests/test_offline_message_queue.py`

**Interfaces:**
- Consumes: Task 1 queue.
- Produces: 65th `send` fails with `offline queue full`; stranger send leaves no file; corrupt bytes are unchanged and that send fails.

- [ ] **Step 1: Write** `test_full_offline_queue_rejects_new_text_and_keeps_earlier_order`, `test_unauthorized_recipient_is_not_queued`, `test_corrupt_queue_file_is_not_replaced`.

- [ ] **Step 2: Run them and confirm each fails because the guard is missing, not because the test errors.**

- [ ] **Step 3: Implement the three guards.**

- [ ] **Step 4: Re-run Task 2 tests.** Expected: PASS.

### Task 3: Node durable lanes and auto-push

**Files:**
- Create: `msn-bridge/offline_queue.js`
- Modify: `msn-bridge/bridge.js`
- Test: `tests/test_offline_message_queue.py`

**Interfaces:**
- Consumes: `client.sendMessage(email, text)`, `client.active`, gateway hello.
- Produces: `offline_queue.js` exports `MAX_ITEMS`, `load(path)`, `save(path, state)`, `enqueueOutbound(state, {to,text})`, `enqueueInbound(state, {sender,body})`, `ack(state, lane, id)`. State shape `{outbound:[], inbound:[]}`. Bridge env `HERMES_MSN_BRIDGE_QUEUE`, `HERMES_MSN_GATEWAY_PORT` (default 18764).

- [ ] **Step 1: Write failing Node tests:** module round-trip and mode 0600; bridge `/send` while inactive returns 202 offline and `sendMessage` sees that text only after `connected`; inbound body survives process restart and is written after hello.

- [ ] **Step 2: Run those tests and confirm FAIL.**

- [ ] **Step 3: Implement the module and bridge acceptor/flush.** Do not change the live default port.

- [ ] **Step 4: Re-run.** Expected: PASS. Existing `tests/test_bridge_reconnect.py` still passes.

### Task 4: Docs, full suite, push

**Files:**
- Modify: `README.md` messaging section, both `plugin.yaml` optional env entries, skill lesson after push.

- [ ] **Step 1: Document** the 202-offline contract and the two default files.

- [ ] **Step 2: Run** `python -m unittest discover -s tests -v` from the repo. Expected: all green, including the byte-identity test.

- [ ] **Step 3: Commit on main, push to origin, verify `git ls-remote` matches `git rev-parse HEAD`.**

- [ ] **Step 4: Do not start the updater and do not contact the XP machine.**
