# MSNP Frame Conformance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Strengthen host-side emulator tests for MSNP stream framing under every TCP split and malformed lengths.

**Architecture:** Extend the existing Node subprocess harness in `tests/test_native_call.py`; exercise the real `MSNPFrameDecoder` without external services or XP. Preserve production behavior unless the tests demonstrate a defect.

**Tech Stack:** Python unittest, Node.js built-ins, existing `MSNPFrameDecoder`.

**Spec:** `docs/superpowers/specs/2026-11-10-msnp-frame-conformance-design.md`

## Global Constraints
- Do not access Windows XP or any live MSN/Escargot server.
- Add no dependencies; tests must be deterministic and offline.
- Keep the decoder API unchanged unless tests expose a defect.

## Review Focus
- Any two-chunk TCP split, including CRLF and payload boundaries, must yield exact frames once and preserve binary bytes.
- One-byte chunking and multiple frames in one chunk must neither lose nor duplicate frames.
- A UUN `OK` acknowledgement must remain bodyless while UUN payload frames honor declared lengths.
- Invalid/non-numeric/over-limit length headers must throw instead of growing the buffer unboundedly.
- Incomplete frame data may remain buffered but must stay within configured bounds.

---

### Task 1: Deterministic MSNP stream boundary conformance

**Files:**
- Modify: `tests/test_native_call.py`
- Test: `tests/test_native_call.py`

**Interfaces:**
- Consumes: `MSNPFrameDecoder(maxFrame=65536)` and `feed(Buffer) -> [{command, words, body}]`.
- Produces: One Node harness test proving split/coalesced/malformed frame behavior; no production interface changes anticipated.

- [ ] **Step 1: Add the failing conformance assertions** for every two-chunk split of UBN, UBX, and UUN payload frames; assert no premature frame before complete data, then exact command/body. Add one-byte feeding, coalesced frames, and UUN `OK` ack cases.
- [ ] **Step 2: Run the focused test** with `PYTHONPATH=local-server python -m unittest tests.test_native_call.NativeCallTests.test_msnp_stream_boundary_conformance -v`; confirm failures only if decoder behavior is incorrect (otherwise revise test harness until it proves each property).
- [ ] **Step 3: Add malformed-input assertions** for nonnumeric payload length, oversized declared length, and incomplete input exceeding the configured bound; each must throw a bounded error.
- [ ] **Step 4: Run focused test** and ensure all frame assertions pass. If implementation changes are needed, add the corresponding failing assertion first and make only the minimal decoder fix in `msn-bridge/msnclient/frame.js`.
- [ ] **Step 5: Run the full suite** with `PYTHONPATH=local-server python -m unittest discover -s tests -v`; expected: all tests pass and no XP/network access.
- [ ] **Step 6: Commit** tests and any necessary narrowly-scoped decoder fix as `test(msn): cover MSNP stream framing boundaries`.
