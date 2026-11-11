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


if __name__ == "__main__":
    unittest.main()
