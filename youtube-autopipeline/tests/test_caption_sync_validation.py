import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


PIPELINE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "pipeline_check.py"
sys.path.insert(0, str(PIPELINE_PATH.parent))
PIPELINE_SPEC = importlib.util.spec_from_file_location("pipeline_check", PIPELINE_PATH)
pipeline_check = importlib.util.module_from_spec(PIPELINE_SPEC)
assert PIPELINE_SPEC and PIPELINE_SPEC.loader
sys.modules["pipeline_check"] = pipeline_check
PIPELINE_SPEC.loader.exec_module(pipeline_check)

VISUAL_QA_PATH = Path(__file__).resolve().parents[1] / "scripts" / "visual_qa.py"
VISUAL_QA_SPEC = importlib.util.spec_from_file_location("visual_qa", VISUAL_QA_PATH)
visual_qa = importlib.util.module_from_spec(VISUAL_QA_SPEC)
assert VISUAL_QA_SPEC and VISUAL_QA_SPEC.loader
sys.modules["visual_qa"] = visual_qa
VISUAL_QA_SPEC.loader.exec_module(visual_qa)


class CaptionSyncValidationTests(unittest.TestCase):
    def write_project(self, root: Path, s11_start: float) -> tuple[list[dict], Path]:
        (root / "manifests").mkdir()
        (root / "still.png").write_bytes(b"not a real png but enough for path validation")
        audio = root / "final_audio.wav"
        audio.write_bytes(b"placeholder")
        manifest = {
            "duration_seconds": 86.76,
            "tts_chunks": [
                {"chunk": "T01", "timeline_start_seconds": 0.0, "duration_seconds": 72.56},
                {"chunk": "T11", "timeline_start_seconds": s11_start, "duration_seconds": 14.2},
            ],
        }
        (root / "manifests" / "final-audio-manifest.json").write_text(
            json.dumps(manifest),
            encoding="utf-8",
        )
        timeline = [
            {"type": "A_ROLL", "clip_path": "still.png", "start_time": 0.0, "end_time": 72.56},
            {"type": "A_ROLL", "clip_path": "still.png", "start_time": 72.56, "end_time": 86.76},
        ]
        return timeline, audio

    def test_pipeline_check_accepts_manifest_matching_timeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            timeline, audio = self.write_project(root, 72.56)
            report = pipeline_check.Report()
            with patch.object(pipeline_check, "media_duration", return_value=86.76):
                pipeline_check.validate_timeline(timeline, root, report, audio, "vertical")
            self.assertFalse(report.has_errors, [f"{item.code}: {item.message}" for item in report.findings])

    def test_pipeline_check_fails_manifest_shifted_from_timeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            timeline, audio = self.write_project(root, 76.17)
            report = pipeline_check.Report()
            with patch.object(pipeline_check, "media_duration", return_value=86.76):
                pipeline_check.validate_timeline(timeline, root, report, audio, "vertical")
            self.assertIn("final-audio-timeline-start", {item.code for item in report.findings})

    def test_visual_qa_fails_non_final_audio_alignment_source(self):
        findings = visual_qa.build_findings(
            metadata={"duration_seconds": 86.76, "width": 1080, "height": 1920},
            frame_entries=[],
            timeline_summary={"asset_categories_used": ["a", "b", "c", "d"], "distinct_media_reference_count": 4},
            prefix_audit={"prompt_prefix_absent": True},
            caption_audit={"alignment_source": "script-scaled"},
            generated_audit={"missing_plan_refs": [], "unreviewed_refs": [], "rejected_refs": []},
            selected_visuals={"manifest_is_resolved": True, "duplicate_canonical_ids": []},
            format_name="vertical",
            min_duration=None,
            max_duration=None,
            agent_visual_review_pass=True,
            visual_review_notes="Concrete visual review notes long enough to satisfy final QA requirements for this regression test.",
        )
        self.assertIn("caption-alignment-source", {item["code"] for item in findings})


if __name__ == "__main__":
    unittest.main()
