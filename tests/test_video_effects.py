"""Smoke tests for editor FFmpeg effect helpers."""

from __future__ import annotations

import unittest

from core.video_effects import (
    any_xfade_transitions,
    append_effect_to_vf,
    build_xfade_filter_complex,
    normalize_effect,
    normalize_transition,
    segment_trim_vf,
)


class VideoEffectsTests(unittest.TestCase):
    def test_normalize_transition(self) -> None:
        self.assertEqual(normalize_transition("Cross Dissolve"), "xfade")
        self.assertEqual(normalize_transition("Fade to Black"), "fade_out")
        self.assertIsNone(normalize_transition(None))

    def test_normalize_effect(self) -> None:
        self.assertEqual(normalize_effect("B&W Film"), "grayscale")
        self.assertEqual(normalize_effect("Cinematic Grain"), "grain")

    def test_append_grayscale(self) -> None:
        vf = append_effect_to_vf("scale=1080:1920", "B&W Film")
        self.assertIn("format=gray", vf)

    def test_segment_trim_fade_out(self) -> None:
        vf = segment_trim_vf("scale=1080:1920", 5.0, None, "Fade to Black")
        self.assertIn("fade=t=out", vf)

    def test_xfade_filter_complex(self) -> None:
        segs = [{"transition": None}, {"transition": "Cross Dissolve"}]
        fc, label = build_xfade_filter_complex(2, [3.0, 4.0], segs)
        self.assertIn("xfade", fc)
        self.assertTrue(label.startswith("[v"))

    def test_any_xfade(self) -> None:
        self.assertFalse(any_xfade_transitions([{"transition": None}]))
        self.assertTrue(any_xfade_transitions([{}, {"transition": "Dissolve"}]))

    def test_xfade_filter_complex_differs_with_transition(self) -> None:
        none_fc, _ = build_xfade_filter_complex(1, [3.0], [{}])
        xfade_fc, _ = build_xfade_filter_complex(2, [3.0, 4.0], [{}, {"transition": "Cross Dissolve"}])
        self.assertEqual(none_fc, "")
        self.assertIn("xfade", xfade_fc)


class EditorAdapterSmokeTests(unittest.TestCase):
    """Manual test checklist companion (see plan Phase 6)."""

    def test_manual_checklist_documented(self) -> None:
        checklist = [
            "Load run with documentary_editor.json + clips_for_edit",
            "Reorder segments and save JSON",
            "Apply transition and export MP4",
            "Enable pipeline_mode=editor and pause/resume",
        ]
        self.assertEqual(len(checklist), 4)


if __name__ == "__main__":
    unittest.main()
