# CUA Request Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bound CUA request parsing and fail closed on weak server-side secrets without enabling XP execution.

**Architecture:** Add pure-ASGI middleware for the CUA endpoint that buffers no more than 4096 bytes and returns 413 above the limit. Tighten endpoint configuration validation to require a server secret of at least 32 characters; preserve exact-peer authentication and simulation-only responses.

**Tech Stack:** Python, FastAPI/Starlette ASGI, unittest/TestClient.

**Spec:** `docs/superpowers/specs/2026-11-10-cua-request-hardening-design.md`

## Global Constraints
- The CUA endpoint remains simulation-only and returns `executed: false`.
- No XP machine access, no arbitrary shell or live input, and no new dependencies.
- Preserve the `/api/cua/execute` route and current action schema.
- Maximum raw request body: 4096 bytes; minimum configured secret length: 32 characters.

## Review Focus
- Declared oversized body: reject with 413 before JSON parsing; test a Content-Length above 4096.
- Streamed oversized body with absent length: reject with 413; test ASGI chunks whose sum exceeds 4096.
- Short configured secret: return 503; test a 31-character configured secret.
- Valid authenticated action remains simulation-only; test 200 and `executed: false`.
- Exact source-IP and wrong-token protections remain in force; retain and run existing tests.

---

### Task 1: Bound CUA request bodies and strengthen configuration validation

**Files:**
- Modify: `local-server/api_server.py`
- Test: `tests/test_vision_api.py`

**Interfaces:**
- Consumes: Existing FastAPI app and `/api/cua/execute` request schema.
- Produces: ASGI middleware limiting that route's request body to 4096 bytes; endpoint auth configuration fails closed when `HERMES_CUA_TOKEN` is missing or shorter than 32 characters.

- [ ] **Step 1: Write failing tests** for declared body >4096, streamed body >4096 without Content-Length, short configured server secret, and an authenticated valid request that still reports `executed: false`.
- [ ] **Step 2: Run targeted tests** with `python -m unittest tests.test_vision_api -v`; confirm new expectations fail for the missing guards while existing tests behave as recorded.
- [ ] **Step 3: Implement the bounded pure-ASGI request guard** for `/api/cua/execute`, returning HTTP 413 without forwarding over-limit data to FastAPI.
- [ ] **Step 4: Require server secret length >=32** and retain exact-peer checking, `hmac.compare_digest`, action validation, and simulation-only behavior.
- [ ] **Step 5: Run targeted tests**, then the full suite with `PYTHONPATH=local-server python -m unittest discover -s tests -v`; expected all tests pass.
- [ ] **Step 6: Review diff and commit** as `fix(security): bound host CUA request parsing`.
