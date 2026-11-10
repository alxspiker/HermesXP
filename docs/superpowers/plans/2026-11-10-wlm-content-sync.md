# WLM content sync implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore WLM display-picture hosting and sync configured display pictures, custom emoticons, and backgrounds for the Hermes bot without touching the XP machine.

**Architecture:** `local-server/wlm_content.py` is the store, MSNObject builder, and stdlib host. `patch-server.py` copies the same lookup into the pinned Escargot tree and persists scenes. The Node bridge only appends env values that the sync step wrote.

**Tech Stack:** Python 3 stdlib, Node (bridge helper), existing HermesXP unittest suite.

**Spec:** `docs/superpowers/specs/2026-11-10-wlm-content-sync-design.md`

## Global Constraints

- Push source to `main` before any XP action or `msn-server` restart. Do not restart services in this task.
- No default image. Unset `HERMES_MSN_DP` / background / emoticon dir is a skip.
- SHA1C vector and type numbers are copied from the spec. Do not invent a second checksum.
- URL ids: UUID or 40-hex SHA-1 only. Reject `..`.
- Image caps: DP 256 KiB, emoticon 64 KiB, background 512 KiB, 32 emoticons.

## Review Focus

- A shared `storage/dp/a/ab/` directory whose first file belongs to another user must not be served as this user's tile.
- A thumbnail saved as `{uuid}_thumb.png` must still be found when the full tile is JPEG.
- A missing thumbnail must not raise from profile size lookup.
- `GET /storage/emoticon/{uuid}/../../etc/passwd` and any non-hex id must 404 and must not read outside the store.
- A shortcut `(h)` must not fire inside `(hermes)`.
- `CHG` must not append an unencoded MSNObject (spaces would split the command).

---

### Task 1: Content store and hosting

**Files:**
- Create: `local-server/wlm_content.py`
- Test: `tests/test_wlm_content.py`

**Interfaces:**
- Produces: `sha1c`, `msn_object`, `ContentStore.store`, `resolve_usertile`, `profile_image_stats`, `serve`, `sync_configured`, `presence_for`

- [ ] Write failing tests for the documented SHA1C vector, per-uuid store, shared-directory lookup, traversal, and no-default sync.
- [ ] Run `python3 -m unittest tests.test_wlm_content -v` and confirm failure because the module is missing.
- [ ] Implement the library.
- [ ] Re-run the module tests and confirm they pass.

### Task 2: Escargot patch

**Files:**
- Modify: `local-server/patch-server.py`
- Create: `local-server/wlm_hosting.py`
- Test: `tests/test_wlm_content.py` (patch cases)

**Interfaces:**
- Consumes: `resolve_usertile` / `profile_image_stats` behavior
- Produces: patched `front/msn/http/other.py` without `files[0].suffix`; `front/msn/wlm_hosting.py`; scene save/load call sites

- [ ] Failing test applies the patcher to a copy of the upstream usertile text and expects the safe lookup.
- [ ] Implement the patch and scene module.
- [ ] Confirm the patched pure functions agree with `wlm_content` on a neighbor-file fixture.

### Task 3: Bot sync and bridge advertise

**Files:**
- Modify: `local-server/ensure-bot-user.py`
- Create: `msn-bridge/wlm_presence.js`
- Modify: `msn-bridge/msnclient/main.js`
- Modify: `README.md`

**Interfaces:**
- Consumes: `sync_configured`, `presence_for`
- Produces: env keys `MSN_BOT_MSNOBJ`, `MSN_BOT_SCENE`, `MSN_BOT_EMOTICON_CATALOG`; `chgLine`, `uuxCommand`, `emoticonAnnouncement`

- [ ] Failing Node/Python tests for URL-encoded CHG, XML-escaped UUX, and tab-separated emoticon announce.
- [ ] Wire ensure-bot-user and the three CHG sites.
- [ ] Full suite: `PYTHONPATH=local-server python3 -m unittest discover -s tests -v`

### Task 4: Commit and push

- [ ] Commit on `main` and push to `origin`.
- [ ] Verify `git rev-parse HEAD` equals `git rev-parse origin/main`.
