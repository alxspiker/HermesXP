import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import vision_model
from vision_model import (
    _run_cli,
    infer_lfm3vl,
    model_status,
    parse_model_detections,
)


class VisionModelTests(unittest.TestCase):
    def test_parse_maps_normalized_boxes_to_pixels_and_labels_source(self):
        raw = '[{"type":"button","text":"OK","bbox":[529,608,659,690],"confidence":0.95}]'
        result = parse_model_detections(raw, width=640, height=360)
        self.assertEqual(result, [{
            "type": "button", "text": "OK", "bbox": [331, 214, 412, 243],
            "confidence": 0.95, "source": "LFM3-VL",
        }])

    def test_invalid_model_output_is_not_reported_as_a_detection(self):
        with self.assertRaises(ValueError):
            parse_model_detections("No controls found.", width=640, height=360)

    def test_cli_disables_reasoning_so_final_detection_fits_budget(self):
        class FakeProcess:
            returncode = 0
            def wait(self, timeout):
                return None

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bindir = root / "bin"
            models = root / "models"
            bindir.mkdir()
            models.mkdir()
            (bindir / "llama-cli").touch()
            (models / vision_model.MODEL_NAME).touch()
            (models / "mmproj-LFM3-VL-2B-F16.gguf").touch()
            image_path = root / "input.png"
            image_path.touch()
            prompt = "Return only an empty JSON array."
            output = f"\n> {prompt}\n[]\n[ Prompt: test ]\n"

            def fake_popen(command, **kwargs):
                kwargs["stdout"].write(output.encode())
                kwargs["stderr"].write(b"")
                return FakeProcess()

            with (
                patch.object(vision_model, "_BIN", bindir),
                patch.object(vision_model, "_MODELS", models),
                patch.object(vision_model, "_FFMPEG", root / "ffmpeg"),
                patch.object(vision_model, "MODEL_ROOT", root),
                patch("vision_model.subprocess.Popen", side_effect=fake_popen) as popen,
            ):
                self.assertEqual(_run_cli(image_path, prompt, timeout=5), "[]")

        command = popen.call_args.args[0]
        reasoning_index = command.index("--reasoning")
        self.assertEqual(command[reasoning_index + 1], "off")

    def test_inference_marks_verified_only_after_valid_model_output(self):
        state = {"state": "not-verified", "last_success": None, "error": None}
        raw = '[{"type":"button","text":"OK","bbox":[529,608,659,690],"confidence":0.95}]'
        with (
            patch.object(vision_model, "_STATE", state),
            patch("vision_model._run_cli", return_value=raw) as run,
        ):
            detections = infer_lfm3vl(Image.new("RGB", (640, 360), "white"))
            run.assert_called_once()
            self.assertEqual(model_status()["state"], "verified")
        self.assertEqual(detections[0]["bbox"], [331, 214, 412, 243])

    def test_out_of_bounds_box_and_invalid_confidence_are_rejected(self):
        for raw in (
            '[{"type":"button","bbox":[0,0,1200,10],"confidence":0.9}]',
            '[{"type":"button","bbox":[0,0,10,10],"confidence":1.5}]',
        ):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                parse_model_detections(raw, width=640, height=360)

    def test_custom_llama_model_and_runtime_paths(self):
        class FakeProcess:
            returncode = 0

            def wait(self, timeout):
                return None

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary = root / "my llama-cli"
            model = root / "custom model.gguf"
            projector = root / "custom projector.gguf"
            for file in (binary, model, projector):
                file.touch()
            image_path = root / "screen.png"
            image_path.touch()
            prompt = "Return only []"

            def fake_popen(command, **kwargs):
                kwargs["stdout"].write(("\n> " + prompt + "\n[]\n[ Prompt: test ]\n").encode())
                return FakeProcess()

            with (
                patch.dict(os.environ, {
                    "HERMESXP_VISION_BACKEND": "llama-cli",
                    "HERMESXP_VISION_MODEL": model.name,
                    "HERMESXP_VISION_MODEL_PATH": str(model),
                    "HERMESXP_VISION_PROJECTOR_PATH": str(projector),
                    "HERMESXP_VISION_LLAMA_CLI": str(binary),
                    "HERMESXP_VISION_THREADS": "2",
                }),
                patch("vision_model.subprocess.Popen", side_effect=fake_popen) as popen,
            ):
                self.assertEqual(_run_cli(image_path, prompt), "[]")
        command = popen.call_args.args[0]
        self.assertEqual(command[command.index("-m") + 1], str(model))
        self.assertEqual(command[command.index("--mmproj") + 1], str(projector))
        self.assertEqual(command[command.index("-t") + 1], "2")
        self.assertEqual(popen.call_args.kwargs["env"]["HOME"], str(Path.home()))
        self.assertNotIn("HERMESXP_VISION_API_KEY", popen.call_args.kwargs["env"])

    def test_openai_compatible_uses_configured_model_without_live_network(self):
        raw = '[{"type":"button","text":"OK","bbox":[100,100,300,200],"confidence":0.9}]'

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return None

            def read(self, limit):
                self.limit = limit
                return json.dumps({"choices": [{"message": {"content": raw}}]}).encode()

        response = FakeResponse()

        class FakeOpener:
            def open(self, request, timeout):
                self.request = request
                self.timeout = timeout
                return response

        opener = FakeOpener()
        with (
            patch.dict(os.environ, {
                "HERMESXP_VISION_BACKEND": "openai-compatible",
                "HERMESXP_VISION_API_URL": "http://127.0.0.1:11434/v1/chat/completions",
                "HERMESXP_VISION_API_MODEL": "other-vision",
                "HERMESXP_VISION_API_KEY": "sample-secret",
            }),
            patch.object(vision_model, "_STATE", {"state": "not-verified", "last_success": None, "error": None}),
            patch("vision_model.build_opener", return_value=opener) as build,
        ):
            detections = infer_lfm3vl(Image.new("RGB", (100, 80), "white"))
            self.assertEqual(model_status()["model"], "other-vision")
            self.assertEqual(model_status()["backend"], "openai-compatible")

        self.assertEqual(detections[0]["source"], "other-vision")
        self.assertEqual(detections[0]["bbox"], [10, 8, 29, 16])
        payload = json.loads(opener.request.data)
        self.assertEqual(payload["model"], "other-vision")
        self.assertTrue(payload["messages"][0]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,"))
        self.assertEqual(opener.request.get_header("Authorization"), "Bearer sample-secret")
        self.assertEqual(response.limit, vision_model._MAX_OUTPUT + 1)
        self.assertIs(build.call_args.args[0], vision_model._NoRedirect)

    def test_remote_plain_http_is_rejected_before_network(self):
        with (
            patch.dict(os.environ, {
                "HERMESXP_VISION_BACKEND": "openai-compatible",
                "HERMESXP_VISION_API_URL": "http://example.com/v1/chat/completions",
                "HERMESXP_VISION_API_MODEL": "vision",
            }),
            patch("vision_model.build_opener") as opener,
        ):
            with self.assertRaisesRegex(ValueError, "plain HTTP"):
                infer_lfm3vl(Image.new("RGB", (80, 60)))
            opener.assert_not_called()

    def test_disabling_vision_never_claims_success(self):
        with (
            patch.dict(os.environ, {"HERMESXP_VISION_BACKEND": "disabled"}),
            patch.object(vision_model, "_STATE", {
                "state": "verified", "last_success": 123.0, "error": None,
            }),
        ):
            self.assertEqual(model_status()["state"], "disabled")
            self.assertIsNone(model_status()["model"])
            with self.assertRaisesRegex(RuntimeError, "disabled"):
                infer_lfm3vl(Image.new("RGB", (80, 60)))

if __name__ == "__main__":
    unittest.main()
