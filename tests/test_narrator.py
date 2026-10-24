"""Meaningful timing/layout guards; all input content is synthetic."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('narrator', Path(__file__).resolve().parents[1] / 'scripts/narrator.py')
n = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(n)


class TimingTests(unittest.TestCase):
    def test_exact_caption_partition(self):
        text = '先检查输入。修改参数后，重新计算；再比较结果，不应丢字或重复。'
        parts = n.caption_parts(text, 12)
        self.assertEqual(''.join(x[2] for x in parts), text)
        self.assertTrue(all(0 < len(x[2]) <= 12 for x in parts))

    def test_word_offsets_scale_with_tempo(self):
        text = '第一阶段，第二阶段。'
        boundaries = [{'type': 'WordBoundary', 'text': '第一阶段', 'offset': 1_000_000},
                      {'type': 'WordBoundary', 'text': '第二阶段', 'offset': 30_000_000}]
        cues, approximate = n.aligned_captions(text, boundaries, 10, 5, 1.2, 5)
        self.assertFalse(approximate)
        self.assertAlmostEqual(cues[1][0], 12.5)
        self.assertEqual(cues[-1][1], 15)

    def test_external_audio_without_boundaries_is_flagged(self):
        cues, approximate = n.aligned_captions('这是外部录音，需要复核同步。', [], 1, 6, 1, 8)
        self.assertTrue(approximate)
        self.assertEqual(cues[0][0], 1)
        self.assertEqual(cues[-1][1], 7)

    def test_bad_word_timing_is_not_silently_accepted(self):
        events = [{'type': 'WordBoundary', 'text': '第一阶段', 'offset': 50_000_000},
                  {'type': 'WordBoundary', 'text': '第二阶段', 'offset': 10_000_000}]
        # First cue starts at clip start, but a later cue beyond clip end still fails.
        events[1]['offset'] = 90_000_000
        with self.assertRaises(ValueError):
            n.aligned_captions('第一阶段，第二阶段。', events, 0, 5, 1, 5)

    def test_srt_overlap_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'test.srt'
            p.write_text('1\n00:00:01,000 --> 00:00:03,000\n甲\n\n2\n00:00:02,500 --> 00:00:04,000\n乙\n', encoding='utf-8')
            with self.assertRaises(ValueError):
                n.parse_srt(p, 5)

    def test_plan_rejects_overlaps_and_crop_outside_source(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'source.mp4').touch()
            p = root / 'plan.json'
            plan = {'version': 1, 'video': 'source.mp4', 'segments': [
                {'start': 0, 'end': 3, 'text': '第一段'}, {'start': 2, 'end': 4, 'text': '第二段'}]}
            meta = {'duration': 10, 'width': 1280, 'height': 720, 'has_audio': False}
            with patch.object(n, 'probe', return_value=meta):
                p.write_text(json.dumps(plan), encoding='utf-8')
                with self.assertRaises(ValueError): n.load_plan(p, 'unused')
                plan['segments'] = [{'start': 0, 'end': 3, 'text': '第一段'}]
                plan['crop'] = {'x': 0, 'y': 48, 'width': 1280, 'height': 720}
                p.write_text(json.dumps(plan), encoding='utf-8')
                with self.assertRaises(ValueError): n.load_plan(p, 'unused')


if __name__ == '__main__':
    unittest.main()
