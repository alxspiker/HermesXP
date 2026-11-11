# Configurable screenshot vision

HermesXP's native `xp_screen` Hermes tool can optionally analyze screenshots from authenticated paired XP devices. No browser dashboard or HTTP management server is needed. A screenshot is sent to a model only when the tool is invoked with `analyze=true`. The default backend is **local llama-cli**, with LFM3-VL as a compatibility default; other compatible vision models are selectable. The second backend is an explicitly configured **OpenAI-compatible chat completions endpoint** (including locally hosted Ollama or llama.cpp servers). Neither backend is required for MSN messaging, voice, remote control, or pairing.

Configure the following environment variables in the Hermes host/plugin environment; the vision module is imported on demand by the native `xp_screen` tool:

| Variable | Purpose |
| --- | --- |
| `HERMESXP_VISION_BACKEND` | `llama-cli` (default), `openai-compatible`, or `disabled` |
| `HERMESXP_VISION_ROOT` | Local runtime root (defaults to `~/local-multimodal`; legacy `HERMESXP_LFM3_ROOT` is supported) |
| `HERMESXP_VISION_MODEL` | Local GGUF filename (default `LFM3-VL-2B-QAD-Q4_0.gguf`) |
| `HERMESXP_VISION_MODEL_PATH` | Override model path (absolute or relative to the runtime's `models/` folder) |
| `HERMESXP_VISION_PROJECTOR_PATH` | Matching multimodal projector (absolute or relative to `models/`) |
| `HERMESXP_VISION_LLAMA_CLI` | Absolute llama-cli binary path, or path relative to runtime root |
| `HERMESXP_VISION_FFMPEG_DIR` | Directory containing an ffmpeg executable for runtimes that need it |
| `HERMESXP_VISION_LIBRARY_PATH` | Explicit native-library search paths for the selected CLI build |
| `HERMESXP_VISION_THREADS` | Local inference CPU threads (default 4; maximum 32) |
| `HERMESXP_VISION_API_URL` | Explicit full chat/completions URL, such as `http://127.0.0.1:11434/v1/chat/completions` |
| `HERMESXP_VISION_API_MODEL` | Model ID supported by the configured endpoint |
| `HERMESXP_VISION_API_KEY` | Optional Bearer token (do not copy into XP packages) |

Example: local OpenAI-compatible service (no API key required):

```bash
export HERMESXP_VISION_BACKEND=openai-compatible
export HERMESXP_VISION_API_URL=http://127.0.0.1:11434/v1/chat/completions
export HERMESXP_VISION_API_MODEL=your-installed-vision-model
# Restart the Hermes gateway to load the configured plugin environment.
# Invoke xp_screen with analyze=true; there is no web server to start.
```

For local llama-cli, provide a compatible GGUF and projector; model support depends on the particular llama.cpp build. A model switch does not imply every GGUF vision architecture will work. The legacy runtime layout (`bin/llama-b12167/llama-cli`, `models/LFM3-VL-2B-QAD-Q4_0.gguf`, `models/mmproj-LFM3-VL-2B-F16.gguf`) remains the default under the configured runtime root.

## Boundaries and honest status

The subprocess uses fixed arguments (no shell), offline mode, a 180-second timeout, up to four million-ish screenshot pixels (max 3840×2160), a 64 KiB output cap, and resource limits when `prlimit` is available. API mode uses an explicit URL and does not follow HTTP redirects. Plain HTTP is allowed only for explicitly configured private/loopback IPs or localhost; use HTTPS for external hosts.

**Privacy:** Selecting a remote API sends the XP screenshot, including any visible sensitive content, to that endpoint. The operator is responsible for the model provider's privacy and billing terms. Neither API keys nor model files are sent to XP. Use the local backend or `disabled` if the image must remain on the Hermes host.

The detector validates model output into at most 100 control boxes with pixel coordinates, text, and model-reported confidence; confidence is not calibrated. On inference failure, `xp_screen` reports vision as unavailable with **no invented detections**. Successful inference is not proof that the predicted coordinates are correct. Host-side tests do not substitute for physical XP testing.
