# WLM custom content sync and hosting restoration

**Date:** 2026-11-10
**Status:** approved for inline execution (parent task: implement, test, commit, push to main; no XP machine)

## Intent

Windows Live Messenger on the XP client can set a display picture, custom emoticons, and a conversation background. Those objects are MSNObjects. The local Escargot server is supposed to host the bytes and remember the scene across sign-in. Today the usertile host picks the first file in a shared directory, so a neighbor's picture or a thumbnail can be served (or the request 500s). Scene and custom emoticons are not stored, and the Hermes bot never advertises a picture.

This change restores that hosting on the Hermes host and syncs an explicitly configured Hermes picture, background, and emoticon set. It does not touch the XP machine and does not invent a default image.

## Goals

- Store display pictures (MSNObject type 3), custom emoticons (type 2), and static backgrounds (type 5) per user UUID.
- Build MSNObject XML whose SHA1C matches the documented `Creator…SHA1D` checksum.
- Serve each object by an exact id. Never use `files[0]` from a shared directory. Reject path traversal.
- Write the display picture into Escargot's `storage/dp/{uuid[0]}/{uuid[0:2]}/{uuid}.{ext}` layout so the existing PreAuthURL can find it after the lookup fix.
- Persist a scene and restore it on the next sign-in once `install.sh` reapplies patches.
- If `HERMES_MSN_DP`, `HERMES_MSN_BACKGROUND`, or `HERMES_MSN_EMOTICONS_DIR` is set, sync those files and publish `MSN_BOT_MSNOBJ`, `MSN_BOT_SCENE`, and `MSN_BOT_EMOTICON_CATALOG` for the bridge. Missing config is a no-op.
- The bridge appends a URL-encoded MSNObject to `CHG` and sends a `UUX` scene when those variables are set. A matching emoticon shortcut is announced with `text/x-mms-emoticon` (`shortcut<TAB>msnobj`) before the text.

## Non-goals

- No XP commands, no `xp_cmd.py`, no live WLM sign-in proof.
- No restart of `msn-server` in this change. The running process keeps its old code until an operator re-runs `install.sh` / restarts the service.
- No default Hermes portrait. No image is generated when the path is unset.
- No dynamic display pictures (type 7), winks (type 8), or signature sounds (type 14).
- No arbitrary upload endpoint. Files are read from paths the operator already set.

## Constraints

- Work on `main`. Commit and push source before any host service restart or XP action.
- Host-side tests use the stdlib plus Node for the bridge helper. They must not import the broken interpreter `PYTHONPATH` site-packages.
- Image types: PNG, JPEG, GIF only. Caps: display picture 256 KiB, emoticon 64 KiB, background 512 KiB, at most 32 emoticons.
- UUID in a URL must be a canonical 8-4-4-4-12 hex UUID. Emoticon and background ids must be 40 hex characters (SHA-1). `..` is a 404, not a read outside the store.
- SHA1C vector (IMFreedom, the hash string uses `buddy1` even though the sample XML says `buddy`): `Creatorbuddy1@hotmail.comSize24539Type3LocationTFR2C.tmpFriendlyAAA=SHA1DtrC8SlFx2sWQxZMIBAWSEnXc8oQ=` → `U32o6bosZzluJq82eAtMpx5dIEI=`.
- Friendly `AAA=` is Base64(UTF-16LE of a single NUL). A named shortcut's Friendly is Base64(UTF-16LE of that shortcut).
- Attribute order: Creator, Size, Type, Location, Friendly, SHA1D, SHA1C.

## Approaches

1. **Patch only Escargot in place.** Fixes the live tree but is not in git, and the next clone loses it. Rejected.
2. **Stand-alone host that WLM is not pointed at.** Testable, but WLM still fetches display pictures from `STORAGE_HOST`. Rejected as the only fix.
3. **Chosen:** a HermesXP library owns store, MSNObject, and a stdlib host. `patch-server.py` applies the same lookup rules and the new emoticon/background routes to the pinned server on install. The bridge only advertises values the library wrote. Tests cover the library, the patch applied to a copy of the upstream text, and the Node presence helper.

## What is left to the operator

Re-run `local-server/install.sh` (or `patch-server.py` plus a `msn-server` restart) before expecting the XP client to fetch the restored URLs. This task does not do that restart.
