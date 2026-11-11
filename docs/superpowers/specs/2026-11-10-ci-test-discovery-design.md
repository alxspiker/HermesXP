# CI Test Discovery Design

## Intent
Make GitHub Actions execute the same complete Python unittest suite as the verified local command, preventing CI from silently omitting tests or failing module imports.

## Goals
- Set `PYTHONPATH=local-server` when discovering tests so `test_vision_api` imports `api_server`.
- Remove the inaccurate hard-coded “94+ tests” success message.

## Non-goals / anti-goals
- No application behavior or test changes.
- No XP machine interaction, deployment, or live endpoint access.
- Do not mask test failures or downgrade test coverage.

## Constraints
- Keep GitHub Actions on Python 3.11 and current unittest discovery.
- Work on `main`; run full suite locally, then commit/push and verify remote main.

## Approaches
1. Prefix the existing test command with `PYTHONPATH=local-server` and remove the stale count (chosen: smallest change, matches the locally verified full-suite command).
2. Add repository-wide test bootstrap/package configuration (more invasive than needed).
3. Replace unittest with another runner (unnecessary migration and risk).

## Design
Update only `.github/workflows/tests.yml`. Run `PYTHONPATH=local-server python -m unittest discover -s tests -v` and let its exit status determine CI success. Keep XP strictly untouched.

## Builder decisions
This is a small CI-only correction; no unresolved product decisions.
