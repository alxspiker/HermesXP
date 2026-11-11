# LFM3-VL screenshot analysis

The host API's `/api/analyze` route runs the local LFM3-VL 2B Q4 model through the bundled `llama-cli` runtime. It first obtains the screenshot through the authenticated paired-device registry; it does not contain a fixed XP address or expose device credentials to the browser.

The default runtime root is `/home/hermes/local-multimodal`. Override it with `HERMESXP_LFM3_ROOT` only when the replacement root contains the expected CLI, model, projector, and runtime libraries:

- `bin/llama-b12167/llama-cli`
- `models/LFM3-VL-2B-QAD-Q4_0.gguf`
- `models/mmproj-LFM3-VL-2B-F16.gguf`

The subprocess uses a fixed argument vector (no shell), offline mode, four CPU threads, a 180-second timeout, a 7 GiB address-space limit, a 64 KiB output cap, and screenshots up to 3840×2160. Reasoning is disabled for this structured extraction call so the model can return the requested JSON instead of consuming its generation budget on an incomplete reasoning trace.

Valid model detections contain a control type, visible text when readable, pixel-space bounding box, model-reported confidence, and `source: "LFM3-VL"`. Confidence is model-reported and has not been calibrated. Proportional heuristic suggestions remain a separate `suggestions` field and must not be described as detections. If model inference or parsing fails, the API returns `analysis_mode: "heuristic"`, an empty `detections` list, and the error type; it does not invent model detections. `/api/status` reports the model as unavailable until a valid local inference has succeeded in that process.

A local synthetic-dialog fixture has been passed through the actual LFM3-VL runtime and returned the visible dialog, OK button, and Cancel button with bounding boxes. This verifies host-side inference and coordinate conversion only; it does not prove live XP screenshot acquisition or UI accuracy on the physical XP device. No live XP request is needed for this test.
