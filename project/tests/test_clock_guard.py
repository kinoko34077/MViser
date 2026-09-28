import os
import tempfile
import time
import unittest
from pathlib import Path

import _path  # noqa: F401
from mviser.audio_player import AudioPlayer


class LeadingBackend:
    """Reports far more samples than real time (the Windows fault seen in MViser#41)."""

    def start(self, pcm, rate, offset):
        self.t0 = time.perf_counter()

    def stop(self):
        pass

    def position(self):
        return int((time.perf_counter() - self.t0 + 5.0) * 48000)


class ClockGuardTests(unittest.TestCase):
    def test_leading_audio_clock_falls_back_to_wall_clock(self):
        try:
            import tkinter as tk

            root = tk.Tk()
        except Exception as exc:
            self.skipTest(f"no display: {exc}")
        from mviser.audit.core import AuditContext
        from mviser.gui import PreviewApp
        from mviser.preview_controller import PreviewController

        ctx = AuditContext(Path(tempfile.mkdtemp()), gui="on")
        os.environ["MVISER_GLOBAL"] = str(ctx.work / "g.yaml")
        try:
            app = PreviewApp(root, PreviewController(ctx.sample()))
            app.audio.backend = LeadingBackend()
            app.c.seek(100)
            app.toggle_play()
            t0 = time.perf_counter()
            while time.perf_counter() - t0 < 0.5:
                root.update()
                time.sleep(0.02)
            self.assertTrue(app.clock_faults)
            self.assertLess(app.c.frame, 100 + 30)
            self.assertTrue(app.playing)
            app.toggle_play()
        finally:
            os.environ.pop("MVISER_GLOBAL", None)
            for after_id in root.tk.splitlist(root.tk.call("after", "info")):
                root.after_cancel(after_id)
            root.destroy()


if __name__ == "__main__":
    unittest.main()
