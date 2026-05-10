import importlib.util
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

PRODUCTION_GATE_PATH = SCRIPTS_DIR / "production_gate.py"
PRODUCTION_GATE_SPEC = importlib.util.spec_from_file_location("production_gate", PRODUCTION_GATE_PATH)
production_gate = importlib.util.module_from_spec(PRODUCTION_GATE_SPEC)
assert PRODUCTION_GATE_SPEC and PRODUCTION_GATE_SPEC.loader
sys.modules["production_gate"] = production_gate
PRODUCTION_GATE_SPEC.loader.exec_module(production_gate)

PROTOTYPE_TIMELINE_PATH = SCRIPTS_DIR / "build_prototype_timeline.py"
PROTOTYPE_TIMELINE_SPEC = importlib.util.spec_from_file_location("build_prototype_timeline", PROTOTYPE_TIMELINE_PATH)
build_prototype_timeline = importlib.util.module_from_spec(PROTOTYPE_TIMELINE_SPEC)
assert PROTOTYPE_TIMELINE_SPEC and PROTOTYPE_TIMELINE_SPEC.loader
sys.modules["build_prototype_timeline"] = build_prototype_timeline
PROTOTYPE_TIMELINE_SPEC.loader.exec_module(build_prototype_timeline)

PACKAGE_PROTOTYPE_PATH = SCRIPTS_DIR / "package_prototype_bundle.py"
PACKAGE_PROTOTYPE_SPEC = importlib.util.spec_from_file_location("package_prototype_bundle", PACKAGE_PROTOTYPE_PATH)
package_prototype_bundle = importlib.util.module_from_spec(PACKAGE_PROTOTYPE_SPEC)
assert PACKAGE_PROTOTYPE_SPEC and PACKAGE_PROTOTYPE_SPEC.loader
sys.modules["package_prototype_bundle"] = package_prototype_bundle
PACKAGE_PROTOTYPE_SPEC.loader.exec_module(package_prototype_bundle)


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


class PrototypeGateTests(unittest.TestCase):
    def setUp(self):
        self.media_duration_patcher = patch("production_gate.media_duration", return_value=10.0)
        self.mock_media_duration = self.media_duration_patcher.start()

    def tearDown(self):
        self.media_duration_patcher.stop()

    def write_creative_project(self, root: Path, *, generated_image: bool = False) -> None:
        (root / "manifests").mkdir(parents=True, exist_ok=True)
        segment_type = "B_ROLL" if generated_image else "A_ROLL"
        panels = [{"kind": "broll", "source": "generated-image"}] if generated_image else None
        script_segment = {
            "segment_id": "S01",
            "type": segment_type,
            "start_time": 0.0,
            "end_time": 3.0,
            "narration": "Test narration.",
        }
        if panels:
            script_segment["layout"] = "fullscreen"
            script_segment["panels"] = panels
        script = {
            "metadata": {"language": "en", "format": "vertical"},
            "segments": [script_segment],
            "tts_chunks": [{"chunk_id": "T01", "voice_text": "Test narration."}],
            "broll_queries": [],
            "assembly_notes": [],
        }
        scene = {
            "scene_id": "SC01",
            "segment_id": "S01",
            "type": segment_type,
            "purpose": "Test scene",
            "visual_idea": "A simple generated illustration prompt",
            "fallback_strategy": "Use a text placeholder",
            "acceptance_criteria": "Readable and timed",
        }
        if panels:
            scene["layout"] = "fullscreen"
            scene["panels"] = panels
        visual_plan = {"schema_version": 1, "metadata": {"format": "vertical"}, "scenes": [scene]}
        write_json(root / "script.json", script)
        write_json(root / "manifests" / "visual-plan.json", visual_plan)
        request = production_gate.create_review_request(root)
        write_json(root / production_gate.REVIEW_REQUEST_RELATIVE_PATH, request)
        approval = production_gate.create_approval(root)
        write_json(root / production_gate.APPROVAL_RELATIVE_PATH, approval)

    def write_prototype_bundle(self, root: Path, *, generated_image: bool = False) -> None:
        (root / "avatar").mkdir(exist_ok=True)
        (root / "avatar" / "front.png").write_bytes(b"presenter plate")
        write_json(root / "timeline.prototype.json", [{"type": "A_ROLL", "clip_path": "avatar/front.png", "loop_policy": "error", "start_time": 0, "end_time": 3}])
        (root / "outputs").mkdir(exist_ok=True)
        (root / "outputs" / "prototype.mp4").write_bytes(b"prototype video")
        (root / "tts" / "clean").mkdir(parents=True, exist_ok=True)
        chunk_path = root / "tts" / "clean" / "T01.wav"
        chunk_path.write_bytes(b"prototype tts chunk")
        (root / "final_audio.wav").write_bytes(b"approved final audio")
        final_audio_manifest = {
            "duration_seconds": 3.0,
            "tts_chunks": [
                {
                    "chunk": "T01",
                    "timeline_start_seconds": 0.0,
                    "duration_seconds": 3.0,
                }
            ]
        }
        write_json(root / "manifests" / "final-audio-manifest.json", final_audio_manifest)
        tts_manifest = {"chunks": [{"chunk_id": "T01", "voice_text": "Test narration."}]}
        write_json(root / "manifests" / "tts-prototype-manifest.json", tts_manifest)
        tts_qa_report = {
            "status": "pass",
            "backend": "whisperx",
            "thresholds": {"min_word_recall": 0.85, "min_sequence_ratio": 0.78},
            "chunks": [{"chunk_id": "T01", "passed": True}],
            "errors": [],
        }
        write_json(root / "manifests" / "tts-pronunciation-qa.json", tts_qa_report)
        placeholder_text = "A simple generated illustration prompt"
        placeholders = []
        if generated_image:
            placeholders.append(
                {
                    "segment_id": "S01",
                    "scene_id": "SC01",
                    "placeholder_text": placeholder_text,
                    "sha256": production_gate.text_sha256(placeholder_text),
                }
            )
        manifest = {
            "schema_version": 1,
            "artifacts": {
                "script": production_gate.artifact_record(root, production_gate.SCRIPT_RELATIVE_PATH),
                "visual_plan": production_gate.artifact_record(root, production_gate.VISUAL_PLAN_RELATIVE_PATH),
                "timeline_prototype": production_gate.artifact_record(root, production_gate.TIMELINE_PROTOTYPE_RELATIVE_PATH),
                "prototype_video": production_gate.artifact_record(root, production_gate.PROTOTYPE_OUTPUT_RELATIVE_PATH),
                "tts_prototype_manifest": production_gate.artifact_record(root, production_gate.TTS_PROTOTYPE_MANIFEST_RELATIVE_PATH),
                "tts_pronunciation_qa": production_gate.artifact_record(root, production_gate.TTS_PRONUNCIATION_QA_RELATIVE_PATH),
                "final_audio_manifest": production_gate.artifact_record(root, production_gate.FINAL_AUDIO_MANIFEST_RELATIVE_PATH),
                "final_audio": production_gate.artifact_record(root, production_gate.FINAL_AUDIO_RELATIVE_PATH),
            },
            "tts": {
                "engine": "voxcpm",
                "model_id": "openbmb/VoxCPM2",
                "prototype_inference_timesteps": 10,
                "production_inference_timesteps": 10,
                "cfg_value": 2.0,
                "normalize": False,
                "denoise": False,
                "prompt_audio": {"sha256": "a" * 64},
                "reference_audio": {"sha256": "b" * 64},
                "chunks": [
                    {
                        "chunk_id": "T01",
                        "voice_text": "Test narration.",
                        "audio_path": "tts/clean/T01.wav",
                        "sha256": production_gate.sha256_file(chunk_path),
                    }
                ],
            },
            "presenter": {
                "latentsync": "skipped",
                "presenter_mode": "raw_muted_video",
            },
            "generated_image_placeholders": placeholders,
        }
        write_json(root / production_gate.PROTOTYPE_MANIFEST_RELATIVE_PATH, manifest)

    def replace_tts_qa_report(self, root: Path, report: dict) -> None:
        report_path = root / production_gate.TTS_PRONUNCIATION_QA_RELATIVE_PATH
        write_json(report_path, report)
        manifest_path = root / production_gate.PROTOTYPE_MANIFEST_RELATIVE_PATH
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["artifacts"]["tts_pronunciation_qa"] = production_gate.artifact_record(root, production_gate.TTS_PRONUNCIATION_QA_RELATIVE_PATH)
        write_json(manifest_path, manifest)

    def replace_presenter_mode(self, root: Path, mode: str) -> None:
        manifest_path = root / production_gate.PROTOTYPE_MANIFEST_RELATIVE_PATH
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["presenter"]["presenter_mode"] = mode
        write_json(manifest_path, manifest)

    def replace_final_audio_manifest(self, root: Path, manifest_payload: dict) -> None:
        manifest_path = root / production_gate.FINAL_AUDIO_MANIFEST_RELATIVE_PATH
        write_json(manifest_path, manifest_payload)
        prototype_manifest_path = root / production_gate.PROTOTYPE_MANIFEST_RELATIVE_PATH
        prototype_manifest = json.loads(prototype_manifest_path.read_text(encoding="utf-8"))
        prototype_manifest["artifacts"]["final_audio_manifest"] = production_gate.artifact_record(root, production_gate.FINAL_AUDIO_MANIFEST_RELATIVE_PATH)
        write_json(prototype_manifest_path, prototype_manifest)

    def approve_prototype(self, root: Path) -> None:
        request = production_gate.create_prototype_review_request(root)
        write_json(root / production_gate.PROTOTYPE_REVIEW_REQUEST_RELATIVE_PATH, request)
        approval = production_gate.create_prototype_approval(root)
        write_json(root / production_gate.PROTOTYPE_APPROVAL_RELATIVE_PATH, approval)

    def test_prototype_approval_passes_when_hashes_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_creative_project(root)
            self.write_prototype_bundle(root)
            self.approve_prototype(root)
            findings = production_gate.run_prototype_gate(root, write_state=False)
            self.assertFalse([item for item in findings if item.severity == "ERROR"], [f"{item.code}: {item.message}" for item in findings])

    def test_prototype_gate_accepts_raw_muted_video_presenter_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_creative_project(root)
            self.write_prototype_bundle(root)
            self.replace_presenter_mode(root, "raw_muted_video")
            findings = production_gate.run_prototype_gate(root, write_state=False)
            self.assertNotIn("prototype-presenter-mode", {item.code for item in findings})

    def test_prototype_gate_rejects_unknown_presenter_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_creative_project(root)
            self.write_prototype_bundle(root)
            self.replace_presenter_mode(root, "raw_video")
            findings = production_gate.run_prototype_gate(root, write_state=False)
            self.assertIn("prototype-presenter-mode", {item.code for item in findings})

    def test_prototype_approval_fails_when_prototype_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_creative_project(root)
            self.write_prototype_bundle(root)
            self.approve_prototype(root)
            (root / "outputs" / "prototype.mp4").write_bytes(b"changed prototype video")
            findings = production_gate.run_prototype_gate(root, write_state=False)
            self.assertIn("prototype-artifact-stale", {item.code for item in findings})

    def test_prototype_approval_fails_when_chunk_audio_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_creative_project(root)
            self.write_prototype_bundle(root)
            self.approve_prototype(root)
            (root / "tts" / "clean" / "T01.wav").write_bytes(b"changed prototype tts chunk")
            findings = production_gate.run_prototype_gate(root, write_state=False)
            self.assertIn("prototype-tts-chunk-audio-stale", {item.code for item in findings})

    def test_prototype_gate_rejects_empty_final_audio_manifest_chunks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_creative_project(root)
            self.write_prototype_bundle(root)
            self.replace_final_audio_manifest(root, {"duration_seconds": 3.0, "tts_chunks": []})
            findings = production_gate.run_prototype_gate(root, write_state=False)
            self.assertIn("prototype-final-audio-manifest", {item.code for item in findings})

    def test_prototype_gate_rejects_final_audio_chunk_without_timeline_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_creative_project(root)
            self.write_prototype_bundle(root)
            self.replace_final_audio_manifest(root, {"duration_seconds": 3.0, "tts_chunks": [{"chunk": "T01", "duration_seconds": 3.0}]})
            findings = production_gate.run_prototype_gate(root, write_state=False)
            self.assertIn("prototype-final-audio-manifest", {item.code for item in findings})

    def test_prototype_gate_requires_tts_pronunciation_qa_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_creative_project(root)
            self.write_prototype_bundle(root)
            (root / production_gate.TTS_PRONUNCIATION_QA_RELATIVE_PATH).unlink()
            findings = production_gate.run_prototype_gate(root, write_state=False)
            self.assertIn("prototype-artifact-missing", {item.code for item in findings})

    def test_prototype_gate_fails_when_tts_pronunciation_qa_status_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_creative_project(root)
            self.write_prototype_bundle(root)
            write_json(root / production_gate.TTS_PRONUNCIATION_QA_RELATIVE_PATH, {"status": "fail", "chunks": [], "errors": ["bad TTS"]})
            findings = production_gate.run_prototype_gate(root, write_state=False)
            self.assertIn("prototype-tts-pronunciation-qa", {item.code for item in findings})

    def test_prototype_gate_rejects_empty_tts_pronunciation_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_creative_project(root)
            self.write_prototype_bundle(root)
            self.replace_tts_qa_report(root, {"status": "pass"})
            findings = production_gate.run_prototype_gate(root, write_state=False)
            self.assertIn("prototype-tts-pronunciation-qa", {item.code for item in findings})

    def test_prototype_gate_rejects_automatic_tts_pronunciation_pass_without_backend(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_creative_project(root)
            self.write_prototype_bundle(root)
            self.replace_tts_qa_report(
                root,
                {
                    "status": "pass",
                    "thresholds": {"min_word_recall": 0.85, "min_sequence_ratio": 0.78},
                    "chunks": [{"chunk_id": "T01", "passed": True}],
                    "errors": [],
                },
            )
            findings = production_gate.run_prototype_gate(root, write_state=False)
            self.assertIn("prototype-tts-pronunciation-qa", {item.code for item in findings})

    def test_prototype_gate_accepts_user_approved_tts_pronunciation_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_creative_project(root)
            self.write_prototype_bundle(root)
            self.replace_tts_qa_report(
                root,
                {
                    "status": "pass",
                    "qa_method": "asr_with_user_approved_override",
                    "asr_status": "fail",
                    "manual_review_status": "approved",
                    "accepted_by": "user",
                    "accepted_at": "2026-05-08T12:00:00+00:00",
                    "chunks": [
                        {
                            "chunk_id": "T01",
                            "expected": "erteiks cztery tysiące dziewięćdziesiąt",
                            "asr_transcript": "RTX 4090",
                            "passed": False,
                        }
                    ],
                    "overrides": [
                        {
                            "chunk_id": "T01",
                            "expected": "erteiks cztery tysiące dziewięćdziesiąt",
                            "asr_transcript": "RTX 4090",
                            "reason": "ASR normalized intentional phonetic spelling after user-approved listening review.",
                        }
                    ],
                    "errors": [],
                },
            )
            findings = production_gate.run_prototype_gate(root, write_state=False)
            self.assertNotIn("prototype-tts-pronunciation-qa", {item.code for item in findings})

    def test_prototype_gate_rejects_tts_pronunciation_override_without_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_creative_project(root)
            self.write_prototype_bundle(root)
            self.replace_tts_qa_report(
                root,
                {
                    "status": "pass",
                    "qa_method": "asr_with_user_approved_override",
                    "asr_status": "fail",
                    "manual_review_status": "approved",
                    "accepted_by": "user",
                    "accepted_at": "2026-05-08T12:00:00+00:00",
                    "chunks": [{"chunk_id": "T01", "passed": False}],
                    "overrides": [{"chunk_id": "T01", "expected": "erteiks", "asr_transcript": "RTX"}],
                    "errors": [],
                },
            )
            findings = production_gate.run_prototype_gate(root, write_state=False)
            self.assertIn("prototype-tts-pronunciation-qa", {item.code for item in findings})

    def test_prototype_gate_rejects_tts_pronunciation_override_without_accepted_at(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_creative_project(root)
            self.write_prototype_bundle(root)
            self.replace_tts_qa_report(
                root,
                {
                    "status": "pass",
                    "qa_method": "asr_with_user_approved_override",
                    "asr_status": "fail",
                    "manual_review_status": "approved",
                    "accepted_by": "user",
                    "chunks": [{"chunk_id": "T01", "passed": False}],
                    "overrides": [{"chunk_id": "T01", "expected": "erteiks", "asr_transcript": "RTX", "reason": "User approved after listening."}],
                    "errors": [],
                },
            )
            findings = production_gate.run_prototype_gate(root, write_state=False)
            self.assertIn("prototype-tts-pronunciation-qa", {item.code for item in findings})

    def test_prototype_approval_fails_when_tts_pronunciation_qa_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_creative_project(root)
            self.write_prototype_bundle(root)
            self.approve_prototype(root)
            write_json(root / production_gate.TTS_PRONUNCIATION_QA_RELATIVE_PATH, {"status": "pass", "chunks": [], "errors": [], "changed": True})
            findings = production_gate.run_prototype_gate(root, write_state=False)
            self.assertIn("prototype-artifact-stale", {item.code for item in findings})

    def test_prototype_bundle_zip_excludes_review_mp4(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_creative_project(root)
            self.write_prototype_bundle(root)
            request = production_gate.create_prototype_review_request(root)
            write_json(root / production_gate.PROTOTYPE_REVIEW_REQUEST_RELATIVE_PATH, request)
            zip_path = root / "outputs" / "prototype-bundle-no-mp4.zip"
            result = package_prototype_bundle.package_bundle(root, zip_path)

            self.assertEqual(result["bundle_zip"], "outputs/prototype-bundle-no-mp4.zip")
            self.assertEqual(result["bundle_zip_local_path"], str(zip_path.resolve()))
            self.assertEqual(result["excluded_review_mp4"], "outputs/prototype.mp4")
            with zipfile.ZipFile(zip_path) as archive:
                names = set(archive.namelist())
            self.assertIn("script.json", names)
            self.assertIn("manifests/visual-plan.json", names)
            self.assertIn("manifests/prototype-review-request.json", names)
            self.assertIn("manifests/prototype-manifest.json", names)
            self.assertIn("timeline.prototype.json", names)
            self.assertIn("final_audio.wav", names)
            self.assertIn("manifests/final-audio-manifest.json", names)
            self.assertIn("tts/clean/T01.wav", names)
            self.assertNotIn("outputs/prototype.mp4", names)

    def test_prototype_bundle_zip_must_be_inside_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "project"
            outside = Path(tmp) / "prototype-bundle-no-mp4.zip"
            root.mkdir()
            self.write_creative_project(root)
            self.write_prototype_bundle(root)
            request = production_gate.create_prototype_review_request(root)
            write_json(root / production_gate.PROTOTYPE_REVIEW_REQUEST_RELATIVE_PATH, request)

            with self.assertRaises(ValueError):
                package_prototype_bundle.package_bundle(root, outside)

    def test_absolute_path_in_prototype_manifest_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_creative_project(root)
            self.write_prototype_bundle(root)
            manifest_path = root / production_gate.PROTOTYPE_MANIFEST_RELATIVE_PATH
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["artifacts"]["prototype_video"]["path"] = str(root / "outputs" / "prototype.mp4")
            write_json(manifest_path, manifest)
            findings = production_gate.run_prototype_gate(root, write_state=False)
            self.assertIn("prototype-portable-path", {item.code for item in findings})

    def test_final_production_gate_blocks_without_prototype_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_creative_project(root)
            self.write_prototype_bundle(root)
            findings = production_gate.run_prototype_gate(root, write_state=False)
            self.assertIn("missing-file", {item.code for item in findings})

    def test_generated_image_panels_become_text_placeholders(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "manifests").mkdir(parents=True, exist_ok=True)
            write_json(
                root / "manifests" / "visual-plan.json",
                {
                    "schema_version": 1,
                    "metadata": {"format": "vertical"},
                    "scenes": [
                        {
                            "scene_id": "SC01",
                            "segment_id": "S01",
                            "type": "B_ROLL",
                            "purpose": "Test scene",
                            "visual_idea": "A simple generated illustration prompt",
                            "fallback_strategy": "Use a text placeholder",
                            "acceptance_criteria": "Readable and timed",
                            "layout": "fullscreen",
                            "panels": [{"kind": "broll", "source": "generated-image"}],
                        }
                    ],
                },
            )
            timeline = [
                {
                    "type": "B_ROLL",
                    "segment_id": "S01",
                    "layout": "fullscreen",
                    "start_time": 0,
                    "end_time": 3,
                    "panels": [{"kind": "broll", "source": "generated-image", "path": "pending.png"}],
                }
            ]
            visual_plan = json.loads((root / "manifests" / "visual-plan.json").read_text(encoding="utf-8"))

            def fake_render(path: Path, text: str, size: tuple[int, int]) -> None:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(text.encode("utf-8"))

            with patch.object(build_prototype_timeline, "render_placeholder_png", side_effect=fake_render):
                prototype, placeholders = build_prototype_timeline.replace_generated_image_panels(
                    timeline,
                    visual_plan,
                    root,
                    output_format="vertical",
                )

            panel = prototype[0]["panels"][0]
            self.assertEqual(panel["source"], "generated-image")
            self.assertTrue(panel["path"].startswith("prototype/placeholders/"))
            self.assertEqual(placeholders[0]["placeholder_text"], "A simple generated illustration prompt")
            self.assertTrue((root / panel["path"]).exists())


if __name__ == "__main__":
    unittest.main()
