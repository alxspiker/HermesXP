# CI Test Discovery Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans task-by-task. Steps use checkbox syntax.

**Goal:** Make GitHub Actions run the entire unittest suite with its required module path.

**Architecture:** Adjust the workflow's test command to match the proven local invocation. Remove the hard-coded test-count echo, which becomes stale as tests change.

**Tech Stack:** GitHub Actions YAML, Python 3.11, unittest.

**Spec:** `docs/superpowers/specs/2026-11-10-ci-test-discovery-design.md`

## Global Constraints
- Python 3.11 in CI.
- Preserve unittest discovery under `tests`.
- Do not access or change the XP machine.
- Push source on `main` and verify the remote commit.

## Review Focus
- Missing local-server import path prevents vision API tests from importing: test locally with the exact CI command.
- Stale hard-coded test count misrepresents coverage: ensure workflow no longer emits that claim.

---

### Task 1: Align CI test discovery with verified local invocation

**Files:**
- Modify: `.github/workflows/tests.yml`
- Test: run the complete unittest suite with `PYTHONPATH=local-server`.

**Interfaces:** None.

- [ ] **Step 1: Confirm failing baseline**

Run: `python -m unittest discover -s tests -v`
Expected: test discovery fails importing `api_server` from `test_vision_api`.

- [ ] **Step 2: Update workflow command**

In `.github/workflows/tests.yml`, use `PYTHONPATH=local-server python -m unittest discover -s tests -v`; remove the echo claiming a fixed test count. The unittest process exit code remains the CI gate.

- [ ] **Step 3: Verify exact CI command**

Run: `PYTHONPATH=local-server python -m unittest discover -s tests -v`
Expected: complete suite passes with zero failures/errors.

- [ ] **Step 4: Commit and push**

Commit on `main`, push to `origin main`, then compare local `HEAD` with `git ls-remote origin refs/heads/main`.
