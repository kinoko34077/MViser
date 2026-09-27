import tempfile
import unittest
from pathlib import Path

import numpy as np

import _path  # noqa: F401
from make_click_wav import make_click_wav
from mviser.audio_player import AudioPlayer, decode_pcm, default_backend


class FakeBackend:
    def __init__(self, fail=False):
        self.fail = fail
        self.started = None
        self.played = None

    def start(self, pcm, rate, offset):
        if self.fail:
            raise RuntimeError("device busy")
        self.started = (len(pcm), rate, offset)
        self.played = 0

    def stop(self):
        self.played = None

    def position(self):
        return self.played


class AudioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp())
        cls.wav = cls.dir / "click.wav"
        make_click_wav(cls.wav, 120, 3.0)

    def test_decode_length_and_offset(self):
        pcm = decode_pcm(self.wav, 0.0, 8000)
        self.assertEqual(pcm.shape[1], 2)
        self.assertAlmostEqual(len(pcm) / 8000, 3.0, delta=0.05)
        later = decode_pcm(self.wav, 1.0, 8000)
        self.assertAlmostEqual(len(later) / 8000, 2.0, delta=0.05)
        self.assertEqual(pcm.dtype, np.float32)

    def test_play_offset_and_clock(self):
        backend = FakeBackend()
        player = AudioPlayer(backend, rate=8000)
        self.assertIsNone(player.load(self.wav, 0.0, 30))
        self.assertTrue(player.play(45))  # 1.5 s
        self.assertEqual(backend.started[2], 12000)
        backend.played = 4000  # 0.5 s later
        self.assertEqual(player.current_frame(), 60)
        player.stop()
        self.assertIsNone(player.current_frame())
        self.assertFalse(player.play(10_000))  # beyond audio end

    def test_reload_is_cached(self):
        player = AudioPlayer(FakeBackend(), rate=8000)
        player.load(self.wav, 0.0, 30)
        first = player.pcm
        player.load(self.wav, 0.0, 30)
        self.assertIs(player.pcm, first)

    def test_silent_fallbacks(self):
        player = AudioPlayer(None, auto_backend=False)
        player.load(self.wav, 0.0, 30)
        self.assertFalse(player.play(0))
        self.assertIsNone(player.current_frame())
        failing = AudioPlayer(FakeBackend(fail=True), rate=8000)
        failing.load(self.wav, 0.0, 30)
        self.assertFalse(failing.play(0))
        self.assertIn("device busy", failing.message)
        muted = AudioPlayer(FakeBackend(), rate=8000)
        muted.load(self.wav, 0.0, 30)
        muted.muted = True
        self.assertFalse(muted.play(0))
        self.assertIsNotNone(AudioPlayer(FakeBackend()).load(self.dir / "missing.wav", 0.0, 30))
        self.assertIsNone(AudioPlayer(FakeBackend()).load(None, 0.0, 30))

    def test_default_backend_never_raises(self):
        backend, message = default_backend()
        self.assertTrue(backend is not None or message)


if __name__ == "__main__":
    unittest.main()
