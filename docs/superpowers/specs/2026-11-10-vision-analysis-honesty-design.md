# Vision Analysis Honesty and Testability

## Intent
Make the dashboard's screenshot analysis truthful and executable under tests. The current `/api/analyze` implementation derives fixed proportional coordinates from image dimensions, but describes synthetic UI elements as detected and the current tests assert a hand-built dictionary rather than calling production behavior.

## Goals
- Exercise the real analysis endpoint with a valid generated BMP, without contacting XP.
- Label output as heuristic rather than model-based detection.
- Keep deterministic coordinate scaling and existing CUA action schema.
- Return a clear error result for unreachable or invalid screenshot data.

## Non-goals / anti-goals
- Do not add live XP actions or alter the screenshot-only XP endpoint.
- Do not claim LFM/local_multimodal inference; the API has no runtime model integration.
- Do not add dependencies or change authentication behavior.

## Constraints
Work on main; host-only. No XP machine access. Preserve existing endpoint URL and JSON fields where practical; add an explicit analysis mode and avoid claiming semantic detections that are not performed.

## Approaches
1. Replace the heuristic with a real model runtime integration: rejected for this slice because no model runtime is wired into the API process.
2. Keep the proportional heuristic, label it honestly, and test the actual endpoint with generated BMP fixtures: selected because it is accurate about capabilities, deterministic, and requires no new dependency.
3. Remove the endpoint: rejected because the dashboard already depends on structured suggestions.

## Design
Refactor `/api/analyze` into a testable helper that accepts an image response payload or a screenshot fetcher, validates image decoding, and produces proportionally scaled suggestions marked `analysis_mode: heuristic`. Use generated in-memory BMP bytes in endpoint tests. Preserve graceful failure responses for network errors and malformed images. Update dashboard labels and status copy to state that suggestions are heuristic, not LFM-powered.

## Acceptance
Tests call the real endpoint and assert scaled coordinates for a generated BMP, the heuristic label, and error handling for invalid image data. Full repository unittest suite passes. No XP interaction occurs.