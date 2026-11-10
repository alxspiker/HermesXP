# CUA Request Hardening Design

## Intent
Harden the host-only CUA simulation endpoint against oversized requests and weak server configuration without enabling XP actions. This is a focused security improvement in upgrade #7.

## Goals
- Require a server secret of at least 32 characters and an exact configured peer IP before accepting CUA calls.
- Bound raw request bodies before JSON/Pydantic parsing, including chunked requests without Content-Length.
- Preserve current action validation and the explicit `executed: false` simulation contract.

## Non-goals / anti-goals
- No live XP input, arbitrary shell, XP machine access, TLS termination, or dashboard redesign.
- Do not reflect the configured secret or request token in logs/responses.

## Constraints
- Host-side FastAPI implementation; no new dependencies.
- Preserve current API route and accepted action schema.
- No XP machine or live server testing.

## Approaches
1. Validate only the environment secret: least change, but leaves unbounded body parsing exposed.
2. Add a bounded ASGI body guard plus fail-closed auth configuration: recommended and selected by the autonomous run instruction; protects both request parsing and weak configuration while keeping the endpoint simulation-only.
3. Replace the endpoint with an authenticated proxy to XP: rejected because it introduces live execution and violates current safety limits.

## Design
Add an ASGI middleware scoped to `/api/cua/execute` that caps request bodies at 4096 bytes, responds 413 on overflow, and safely handles both Content-Length and streamed bodies. Reject missing or shorter-than-32-character configured secrets as unconfigured (503); keep exact-peer and constant-time token checks. Existing payload-level validations remain authoritative. Add host-only tests for oversized declared and streamed request bodies, short server secrets, and normal authenticated simulation.

## Builder choices
Use a small pure-ASGI middleware in `local-server/api_server.py` to avoid dependency changes and keep the guard before FastAPI model parsing. Treat malformed or conflicting lengths as invalid requests rather than allowing parsing to proceed. Existing tests use FastAPI TestClient; test real ASGI request messages where needed.
