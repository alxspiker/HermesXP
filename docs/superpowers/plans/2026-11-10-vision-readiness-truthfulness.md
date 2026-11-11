# Vision Readiness Truthfulness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure API and dashboard report heuristic-only screenshot suggestions honestly and never imply real LFM detections are running.

**Architecture:** Retain existing heuristic suggestion generation and simulated-only CUA endpoint. Correct the analysis/status response and UI copy, then pin behavior through API tests.

**Tech Stack:** Python, FastAPI, unittest, static HTML/JavaScript.

**Spec:** `docs/superpowers/specs/2026-11-10-vision-readiness-truthfulness-design.md`

## Global Constraints

- Host-side only; no XP deployment or live machine access.
- No new model/runtime/dependency integration in this pass.
- Do not imply CUA actions execute on XP.

## Review Focus

- Screenshot succeeds but model is unavailable: return heuristic-only mode with no fabricated detections or model rationale; test in Task 1.
- Screenshot fetch or image decoding fails: preserve error response and never claim successful/model analysis; existing tests cover in Task 1.
- Status is queried independently of analysis: report model unavailable and simulated-only CUA; test in Task 1.
- Heuristic coordinates on small resolutions: ensure bounds through existing helper test.
- CUA auth is valid: endpoint remains explicitly non-executing; existing test asserts `executed` false.

---

### Task 1: Truthful analysis and readiness reporting

**Files:**
- Modify: `local-server/api_server.py`
- Modify: `local-server/dashboard.html`
- Test: `tests/test_vision_api.py`

**Interfaces:**
- Consumes: existing `generate_heuristic_suggestions(width: int, height: int) -> list` and `/api/status`, `/api/analyze` routes.
- Produces: `/api/status` identifies heuristic-only and model unavailable; `/api/analyze` uses `analysis_mode="heuristic"`, has no `detected` claim or `lmf_reason`, and describes estimates/model unavailability honestly.

- [ ] **Step 1: Write failing tests**

Update the analysis test to assert heuristic mode, no `detected` field, no `lmf_reason`, and an explicit heuristic estimate note. Add a status test asserting model unavailable and simulated-only CUA.

- [ ] **Step 2: Run tests to verify failure**

Run: `PYTHONPATH=local-server python -m unittest tests.test_vision_api.TestVisionAPI.test_analyze_endpoint_returns_lfm_or_heuristic_suggestions tests.test_vision_api.TestVisionAPI.test_status_reports_model_unavailable -v`
Expected: FAIL because current endpoint reports a fabricated local-multimodal mode/detections and active model status.

- [ ] **Step 3: Implement minimal truthful responses**

Remove placeholder model branch and invented detection fields. Keep heuristic suggestions, explicitly state model integration is unavailable, and update status/dashboard copy to match. Preserve existing CUA validation and simulated-only behavior.

- [ ] **Step 4: Run focused and full tests**

Run: `PYTHONPATH=local-server python -m unittest tests.test_vision_api -v`
Expected: PASS.

Run: `PYTHONPATH=local-server python -m unittest discover -s tests -v`
Expected: complete suite passes with zero failures.

- [ ] **Step 5: Commit**

```bash
git add local-server/api_server.py local-server/dashboard.html tests/test_vision_api.py docs/superpowers/specs/2026-11-10-vision-readiness-truthfulness-design.md docs/superpowers/plans/2026-11-10-vision-readiness-truthfulness.md
git commit -m "fix(vision): report model readiness truthfully"
```
