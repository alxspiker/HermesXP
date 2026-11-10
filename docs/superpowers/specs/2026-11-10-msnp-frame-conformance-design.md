# MSNP Frame Conformance Design

## Intent
Advance upgrade #5 with deterministic host-side protocol emulation coverage for the MSNP framing layer used by the XP/MSN bridge. TCP fragmentation/coalescing and malformed length headers must not corrupt or hang the client.

## Goals
- Exercise every byte split of representative length-prefixed binary and text-payload frames, coalesced frames, empty payloads, and the UUN acknowledgement exception.
- Assert malformed, oversized, and incomplete frames fail closed with bounded buffering.
- Remain deterministic, offline, host-only, and compatible with the current Node test harness.

## Non-goals / anti-goals
No XP device access, VM provisioning, production protocol changes, fuzzing dependency, or claims of live Escargot interoperability. Tests must not use real accounts or networks.

## Constraints
Keep `MSNPFrameDecoder` behavior/API unchanged unless a failing test exposes a correctness defect. Reuse `tests/test_native_call.py` and Node built-ins. No new dependencies.

## Approaches considered
1. Boot a Windows XP VM and replay live server sessions: broadest fidelity, but impractical, stateful, and unnecessary for decoder boundary invariants.
2. Add deterministic byte-stream conformance tests around the existing decoder: fast, repeatable, directly isolates TCP framing and malformed-input behavior. **Selected** for this bounded upgrade; it improves emulator coverage without implying XP runtime validation.
3. Add randomized fuzzing: potentially broad, but harder to reproduce and not needed for exact split-boundary guarantees.

## Design
Extend the current Node harness in `tests/test_native_call.py` with exhaustive two-chunk split checks for representative frames, one-byte-at-a-time feeding, frame coalescing, UUN `OK` acknowledgement handling, and malformed/oversized/incomplete length input. Keep all validation local and deterministic. If tests reveal production defects, fix only the decoder path test-first.

## Approval
Autonomous scheduled run: the user explicitly directed this job to execute fully without waiting; this design is treated as approved for implementation. Host-only; no XP actions.
