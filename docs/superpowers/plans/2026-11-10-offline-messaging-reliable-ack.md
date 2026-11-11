# Offline Messaging Reliability Implementation Plan

> **For agentic workers:** Follow the TDD cycle for each behavior and verify the full repository suite before integration.

**Goal:** Make offline MSN message handoffs durable, acknowledged, ordered, bounded, retryable, and honest about what “accepted” means.

**Architecture:** The host adapter persists outbound texts before reporting acceptance and assigns stable IDs. The authenticated Node bridge durably accepts/deduplicates those IDs before acknowledging the host; its own queue retries in FIFO order. Inbound messages use stable IDs and are acknowledged only after the gateway accepts them, with a bounded persistent dedupe ledger. No interface claims recipient delivery without a remote receipt.

**Tech Stack:** Python asyncio adapter, Node.js bridge, JSON queue files, unittest and Node fixtures.

**Spec:** Active user acceptance criteria, subgoal 7 (offline messaging), in the session request.

## Global Constraints

- Preserve the authenticated loopback-only bridge and the existing MSN adapter API.
- Persist queues on the modern Hermes host only; do not contact or modify Windows XP.
- Keep queues bounded at 64 pending messages and message bodies at 4,000 characters.
- Preserve legacy packets without IDs while enabling the new acknowledged protocol.
- Report durable queue acceptance as accepted/queued, never as confirmed recipient delivery.

## Review Focus

- Host queue file unreadable or unwritable: refuse acceptance; preserve the original file.
- Lost ACK after durable Node acceptance: retry the same ID without creating a duplicate.
- Lost ACK after inbound gateway acceptance: replay is deduplicated by a persistent bounded ID ledger.
- Bridge/MSN outage or restart: preserve FIFO order and retry without secret leakage.
- Pending queue limit reached: reject new outbound text explicitly; never silently evict it.

---

### Task 1: Durable outbound handoff

**Files:**
- Modify `hermes-plugin/hermes-msn/adapter.py`
- Modify `msn-bridge/offline_queue.js`
- Modify `msn-bridge/bridge.js`
- Test `tests/test_offline_message_queue.py`

**Interfaces:**
- Host packets carry a stable `id` and the existing `type`, `to`, and `text` fields.
- Node replies with `send_ack` only after the message is durably queued or its ID is already known.
- Node retains a bounded completed-ID ledger to deduplicate a retry whose earlier ACK was lost.

- [x] Add tests for durable Node acceptance ACKs, duplicate-ID retries, FIFO retry, queue overflow, and honest queued/accepted status.
- [x] Run the focused tests and confirm they fail for the current missing-ACK/dedup behavior.
- [x] Implement stable IDs, durable acceptance, bounded dedupe history, and retry semantics without changing legacy no-ID packets.
- [x] Run offline queue tests and the complete repository suite.

### Task 2: Acknowledged inbound replay

**Files:**
- Modify `msn-bridge/offline_queue.js`
- Modify `msn-bridge/bridge.js`
- Modify `hermes-plugin/hermes-msn/adapter.py`
- Test `tests/test_offline_message_queue.py`

**Interfaces:**
- Persisted inbound packets carry an ID.
- The adapter ACKs only after `handle_message` accepts the event and the ID has been durably recorded.
- The Node bridge removes inbound packets only after the authenticated ACK; duplicate replays are ignored by a bounded host-side ledger.

- [x] Add restart/replay, duplicate-ACK, and lost-ACK tests against real local queue files and sockets.
- [x] Run the focused tests and confirm they expose the current pre-ACK removal behavior.
- [x] Implement inbound acknowledgment and deduplication; keep old packets readable.
- [x] Run the full suite, native XP client compatibility build only if code touches it, then review the final diff and commit.
