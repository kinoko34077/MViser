import shutil
import tempfile
import unittest
from pathlib import Path

import numpy as np
import yaml

import _path  # noqa: F401
from make_click_wav import make_click_wav
from mviser.preview_controller import PreviewController
from mviser.timeline import Tempo
from mviser.waveform import beat_grid, waveform_peaks


class PeakTests(unittest.TestCase):
    def test_columns_and_bounds(self):
        pcm = np.sin(np.linspace(0, 40 * np.pi, 8000, dtype=np.float32)).reshape(-1, 1) * 2
        peaks = waveform_peaks(pcm, 100)
        self.assertEqual(peaks.shape, (100, 2))
        self.assertTrue((peaks[:, 0] <= peaks[:, 1]).all())
        self.assertLessEqual(peaks.max(), 1.0)
        self.assertGreaterEqual(peaks.min(), -1.0)

    def test_silence_and_edge_cases(self):
        self.assertFalse(waveform_peaks(np.zeros((500, 2), np.float32), 10).any())
        self.assertEqual(waveform_peaks(np.zeros((0, 1), np.float32), 5).shape, (5, 2))
        self.assertEqual(waveform_peaks(np.ones((3, 1), np.float32), 10).shape, (10, 2))  # more columns than samples
        self.assertEqual(waveform_peaks(np.ones((3, 1), np.float32), 0).shape, (0, 2))


class GridTests(unittest.TestCase):
    def test_beats_and_measures(self):
        grid = beat_grid(Tempo(120, 10), 40, 400)  # 4 s, beat 0.5 s
        self.assertEqual(len(grid), 9)             # beats at 0..4 s inclusive
        self.assertEqual(grid[0], (0.0, True, 1))
        self.assertEqual(grid[1][:2], (50.0, False))
        self.assertEqual(grid[4], (200.0, True, 2))

    def test_offset_shifts_grid(self):
        grid = beat_grid(Tempo(120, 10, offset=0.25), 40, 400)
        self.assertEqual(grid[0], (25.0, True, 1))
        self.assertEqual(beat_grid(Tempo(120, 10), 0, 400), [])


class ControllerWaveformTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        make_click_wav(self.dir / "c.wav", 120, 2.0)
        raw = {"project": {"bpm": 120, "fps": 10, "resolution": [64, 36], "duration": 4},
               "audio": {"path": "c.wav"}, "chords": [{"at": 0, "chord": "C"}]}
        (self.dir / "p.yaml").write_text(yaml.safe_dump(raw), encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_waveform_aligned_to_project_length(self):
        c = PreviewController(self.dir / "p.yaml")
        peaks = c.waveform(200)
        self.assertEqual(peaks.shape, (200, 2))
        self.assertGreater(np.abs(peaks[:100]).max(), 0.1)   # audio in the first 2 s
        self.assertFalse(peaks[110:].any())                   # padded silence afterwards
        self.assertIs(c.waveform(200), peaks)                 # cached
        self.assertEqual(len([g for g in c.grid(200) if g[1]]), 3)  # measures 1..3 (0 s, 2 s, 4 s)

    def test_no_audio(self):
        (self.dir / "c.wav").unlink()
        c = PreviewController(self.dir / "p.yaml")
        self.assertIsNone(c.waveform(200))


if __name__ == "__main__":
    unittest.main()
