# Vision Analysis Honesty and Testability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Make screenshot suggestions explicitly heuristic and test actual production analysis behavior without XP access.

**Architecture:** Keep the existing FastAPI endpoint and proportional coordinate strategy, but factor analysis into a deterministic helper and return an explicit `analysis_mode`. Use generated BMP data in tests and preserve structured failure responses.

**Tech Stack:** Python, FastAPI, requests, Pillow, unittest.

**Spec:** `docs/superpowers/specs/2026-11-10-vision-analysis-honesty-design.md`

## Global Constraints
- Host-side only; do not access 192.168.1.78.
- Do not claim LFM/local_multimodal inference; describe the output as heuristic.
- Preserve screenshot-only XP endpoint and existing CUA action schema.
- Add no dependencies.

## Review Focus
- Invalid or truncated image bytes must return a structured error rather than raise an unhandled exception; test in Task 1.
- Screenshot fetch failures must retain a structured error response; test in Task 1.
- Small valid image dimensions must produce in-bounds scaled coordinates; test in Task 1.
- Heuristic output must not claim semantic detections or model inference; assert mode and neutral labels in Task 1.
- Existing consumers must retain the action/coordinate schema; assert required fields in Task 1.

---

### Task 1: Honest, testable screenshot analysis

**Files:**
- Modify: `local-server/api_server.py`
- Modify: `local-server/dashboard.html`
- Test: `tests/test_vision_api.py`

**Interfaces:**
- Consumes: existing FastAPI `/api/analyze` endpoint.
- Produces: JSON with `analysis_mode: "heuristic"`, `screenshot_size`, `suggestions` retaining action/coords/confidence/reason fields, and structured error results.

- [x] **Step 1: Replace fabricated analysis tests with endpoint behavior tests**
  Generate a small valid BMP using Pillow; call the actual endpoint via `TestClient` with `requests.get` patched to return those bytes. Assert `analysis_mode == "heuristic"`, expected dimensions and proportional coordinates, action schema, and non-semantic detected labels. Separately assert network and invalid-BMP failures return status `error`.
- [x] **Step 2: Run focused tests to verify the new assertions fail**
  Run: `PYTHONPATH=local-server python -m unittest tests.test_vision_api -v`
  Expected: failure because current output lacks `analysis_mode` and still makes semantic/model claims.
- [x] **Step 3: Implement truthful heuristic response in `local-server/api_server.py`**
  Add `analysis_mode: "heuristic"`; replace semantic detections and model claims with neutral heuristic labeling; catch image decode errors as structured errors. Keep generation inline in the endpoint because the real endpoint is now exercised directly and no second public/helper interface is needed.
- [x] **Step 4: Update dashboard capability copy**
  In `local-server/dashboard.html`, label suggestions as heuristic and remove claims of real LFM integration or detected UI elements.
- [x] **Step 5: Run focused tests**
  Run: `PYTHONPATH=local-server python -m unittest tests.test_vision_api -v`
  Expected: all focused tests pass.
- [x] **Step 6: Run the full suite**
  Run: `PYTHONPATH=local-server python -m unittest discover -s tests -v`
  Expected: all tests pass.
- [x] **Step 7: Commit**
  Commit the spec, plan, API, dashboard, and test changes as `fix(vision): label heuristic screenshot suggestions honestly`.
