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

FINAL_RENDER_QA_PATH = Path(__file__).resolve().parents[1] / "scripts" / "final_render_qa.py"
FINAL_RENDER_QA_SPEC = importlib.util.spec_from_file_location("final_render_qa", FINAL_RENDER_QA_PATH)
final_render_qa = importlib.util.module_from_spec(FINAL_RENDER_QA_SPEC)
assert FINAL_RENDER_QA_SPEC and FINAL_RENDER_QA_SPEC.loader
sys.modules["final_render_qa"] = final_render_qa
FINAL_RENDER_QA_SPEC.loader.exec_module(final_render_qa)


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

    def test_pipeline_check_allows_presenter_duration_fit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "synced" / "front").mkdir(parents=True)
            (root / "synced" / "front" / "A01.mp4").write_bytes(b"placeholder")
            timeline = [{"type": "A_ROLL", "clip_path": "synced/front/A01.mp4", "start_time": 0.0, "end_time": 3.0}]
            report = pipeline_check.Report()
            with patch.object(pipeline_check, "media_duration", return_value=2.4):
                pipeline_check.validate_timeline(timeline, root, report, None, "vertical")
            codes = {item.code for item in report.findings}
            self.assertNotIn("clip-too-short", codes)

    def test_pipeline_check_rejects_loop_unsafe_broll_past_hold_tail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "broll").mkdir()
            (root / "broll" / "site.webm").write_bytes(b"placeholder")
            timeline = [
                {
                    "type": "B_ROLL",
                    "layout": "fullscreen",
                    "panels": [{"kind": "broll", "source_type": "webpage", "path": "broll/site.webm"}],
                    "start_time": 0.0,
                    "end_time": 3.0,
                }
            ]
            report = pipeline_check.Report()
            with patch.object(pipeline_check, "media_duration", return_value=2.7):
                pipeline_check.validate_timeline(timeline, root, report, None, "vertical")
            self.assertIn("clip-too-short", {item.code for item in report.findings})

    def test_pipeline_check_rejects_legacy_broll_panel_source(self):
        timeline = [
            {
                "type": "B_ROLL",
                "layout": "fullscreen",
                "panels": [{"kind": "broll", "source": "manual", "path": "broll/manual/asset.png"}],
                "start_time": 0.0,
                "end_time": 2.0,
            }
        ]
        report = pipeline_check.Report()

        pipeline_check.validate_timeline(timeline, Path("."), report, None, "vertical")

        self.assertIn("broll-panel-source-legacy", {item.code for item in report.findings})

    def test_pipeline_check_rejects_presenter_panel_source_type(self):
        timeline = [
            {
                "type": "B_ROLL",
                "layout": "fullscreen",
                "panels": [
                    {"kind": "broll", "source_type": "manual", "path": "broll/manual/asset.png"},
                    {"kind": "presenter", "source_type": "manual", "path": "synced/profile/P01.mp4", "role": "overlay"},
                ],
                "start_time": 0.0,
                "end_time": 2.0,
            }
        ]
        report = pipeline_check.Report()

        pipeline_check.validate_timeline(timeline, Path("."), report, None, "vertical")

        self.assertIn("presenter-source", {item.code for item in report.findings})

    def test_final_render_qa_fails_non_final_audio_alignment_source(self):
        findings = final_render_qa.build_findings(
            metadata={"duration_seconds": 86.76, "width": 1080, "height": 1920},
            frame_entries=[],
            timeline_summary={"asset_categories_used": ["a", "b", "c", "d"], "distinct_media_reference_count": 4},
            prefix_audit={"prompt_prefix_absent": True},
            caption_audit={"alignment_source": "script-scaled"},
            generated_audit={"missing_plan_refs": [], "unreviewed_refs": [], "rejected_refs": []},
            timeline_selected_visuals=[],
            selected_visuals={"manifest_is_resolved": True, "duplicate_canonical_ids": []},
            format_name="vertical",
            min_duration=None,
            max_duration=None,
            agent_visual_review_pass=True,
            visual_review_notes="Concrete visual review notes long enough to satisfy final QA requirements for this regression test.",
        )
        self.assertIn("caption-alignment-source", {item["code"] for item in findings})

    def test_timeline_broll_path_must_be_in_resolved_selected_visuals(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            timeline = [
                {
                    "type": "B_ROLL",
                    "layout": "fullscreen",
                    "panels": [{"kind": "broll", "source_type": "manual", "path": "broll/manual/missing.png"}],
                    "start_time": 0.0,
                    "end_time": 2.0,
                }
            ]
            selected_visuals = {
                "resolver": {"name": "youtube-autopipeline-selected-visuals-resolver"},
                "items": [],
            }

            findings = pipeline_check.timeline_selected_visual_findings(timeline, selected_visuals, root)

            self.assertIn("timeline-selected-visual-mismatch", {item.code for item in findings})

    def test_timeline_broll_source_type_must_match_resolved_source_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            timeline = [
                {
                    "type": "B_ROLL",
                    "layout": "fullscreen",
                    "panels": [{"kind": "broll", "source_type": "generated-image", "path": "broll/generated/local.png"}],
                    "start_time": 0.0,
                    "end_time": 2.0,
                }
            ]
            selected_visuals = {
                "resolver": {"name": "youtube-autopipeline-selected-visuals-resolver"},
                "items": [
                    {
                        "accepted": True,
                        "source_type": "manual",
                        "segment_id": "S01",
                        "local_path": "broll/generated/local.png",
                        "provenance": {"kind": "local_file", "project_relative_path": "broll/generated/local.png"},
                    }
                ],
            }

            findings = pipeline_check.timeline_selected_visual_findings(timeline, selected_visuals, root)

            self.assertIn("timeline-selected-visual-source-mismatch", {item.code for item in findings})

    def test_timeline_selected_visuals_ignore_aroll_and_presenter_panels(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            timeline = [
                {"type": "A_ROLL", "clip_path": "synced/front/A01.mp4", "start_time": 0.0, "end_time": 2.0},
                {
                    "type": "B_ROLL",
                    "layout": "fullscreen",
                    "panels": [
                        {"kind": "broll", "source_type": "manual", "path": "broll/manual/asset.png"},
                        {"kind": "presenter", "path": "synced/profile/P01.mp4", "role": "overlay"},
                    ],
                    "start_time": 2.0,
                    "end_time": 4.0,
                },
            ]
            selected_visuals = {
                "resolver": {"name": "youtube-autopipeline-selected-visuals-resolver"},
                "items": [
                    {
                        "accepted": True,
                        "source_type": "manual",
                        "segment_id": "S01",
                        "local_path": "broll/manual/asset.png",
                        "provenance": {"kind": "local_file", "project_relative_path": "broll/manual/asset.png"},
                    }
                ],
            }

            findings = pipeline_check.timeline_selected_visual_findings(timeline, selected_visuals, root)

            self.assertEqual([], findings)

    def test_generated_folder_manual_source_type_does_not_trigger_z_image_audit(self):
        selected_visuals = {
            "resolver": {"name": "youtube-autopipeline-selected-visuals-resolver"},
            "items": [
                {
                    "accepted": True,
                    "source_type": "manual",
                    "local_path": "broll/generated/local.png",
                    "provenance": {"kind": "local_file", "project_relative_path": "broll/generated/local.png"},
                }
            ],
        }

        audit = final_render_qa.z_image_audit(Path("."), selected_visuals, {"items": []})

        self.assertEqual([], audit["generated_refs_in_timeline"])

    def test_timeline_generated_image_requires_resolved_selected_visuals_and_z_image_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            timeline = [
                {
                    "type": "B_ROLL",
                    "layout": "fullscreen",
                    "panels": [{"kind": "broll", "source_type": "generated-image", "path": "broll/generated/S01.png"}],
                    "start_time": 0.0,
                    "end_time": 2.0,
                }
            ]
            selected_visuals = {
                "resolver": {"name": "youtube-autopipeline-selected-visuals-resolver"},
                "items": [
                    {
                        "accepted": True,
                        "source_type": "generated-image",
                        "segment_id": "S01",
                        "local_path": "broll/generated/S01.png",
                        "provenance": {"kind": "local_file", "project_relative_path": "broll/generated/S01.png"},
                    }
                ],
            }

            timeline_findings = pipeline_check.timeline_selected_visual_findings(timeline, selected_visuals, root)
            generated_audit = final_render_qa.z_image_audit(root, selected_visuals, {"items": []})

            self.assertEqual([], timeline_findings)
            self.assertIn("broll\\generated\\S01.png", generated_audit["missing_plan_refs"])


if __name__ == "__main__":
    unittest.main()
