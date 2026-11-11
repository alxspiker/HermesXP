# Vision Readiness Truthfulness Design

## Intent
Make dashboard/API reporting match behavior so operators do not mistake heuristic coordinates for real visual detections or an integrated LFM3-VL runtime.

## Goals
- Report heuristic analysis honestly, with no fabricated detected elements or model rationale.
- Report live model integration as unavailable until the API actually invokes a supported backend.
- Preserve screenshot retrieval, heuristic suggestions, and safe simulated-only CUA validation.

## Non-goals / anti-goals
- No XP deployment or live machine access.
- No new model/runtime/dependency integration in this pass.
- Do not imply CUA actions execute on XP.

## Constraints
- Work on main; host-side only. Do not touch 192.168.1.78.
- Existing screenshot endpoint remains a live read, but this run will not call it.
- Keep response compatibility where practical; fields describing model detections must not contain fabricated values.

## Approaches
1. Keep current behavior and soften labels: rejected because the API still labels a placeholder as an active model and returns invented detections.
2. Replace placeholder with an actual model runtime now: rejected because the repo contains no callable model integration and external tool access is not a dependable API server backend.
3. Fail honestly to heuristic-only status and response, with explicit unavailable-model metadata: selected for safety and truthful operator expectations.

## Design
Update `/api/status` and `/api/analyze` so they say heuristic-only/model unavailable, label suggestions as estimates, and return no `detected` elements or fabricated `lmf_reason`. Preserve heuristic fallback on screenshot success and keep CUA endpoint simulation-only. Add endpoint tests for actual behavior and run the complete host suite.

## Approval simulation
The scheduled job explicitly requests autonomous execution and approval simulation when no user is present. Treat this document as approved for this bounded host-only change. No live XP actions are authorized.