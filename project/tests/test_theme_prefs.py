import tempfile
import unittest
from pathlib import Path

import _path  # noqa: F401
from mviser.gui_state import PREF_DEFAULTS, load_prefs, save_prefs, validate_prefs
from mviser.theme import PALETTES, STATUS_KEYS, contrast, palette


class PrefsTests(unittest.TestCase):
    def test_round_trip_and_fallbacks(self):
        path = Path(tempfile.mkdtemp()) / "p" / "gui_prefs.json"
        self.assertEqual(load_prefs(path), PREF_DEFAULTS)
        save_prefs({"theme": "dark", "time_mode": "tempo", "guides": True, "chord_colors": False}, path)
        self.assertEqual(load_prefs(path), {**PREF_DEFAULTS, "theme": "dark", "time_mode": "tempo", "guides": True,
                                            "chord_colors": False})
        self.assertEqual(validate_prefs({"side_panel": False, "side_width": 400})["side_width"], 400)
        self.assertFalse(validate_prefs({"side_panel": False})["side_panel"])
        for bad in (5, 99999, True, "300"):
            self.assertEqual(validate_prefs({"side_width": bad})["side_width"], PREF_DEFAULTS["side_width"])
        bad = validate_prefs({"theme": "neon", "time_mode": 3, "guides": "yes", "extra": 1})
        self.assertEqual(bad, PREF_DEFAULTS)
        path.write_text("{broken", encoding="utf-8")
        self.assertEqual(load_prefs(path), PREF_DEFAULTS)


class PaletteTests(unittest.TestCase):
    def test_same_keys_and_contrast(self):
        keys = set(PALETTES["light"])
        for name, pal in PALETTES.items():
            self.assertEqual(set(pal), keys, name)
            for key in ("fg",) + STATUS_KEYS:
                with self.subTest(theme=name, key=key):
                    self.assertGreaterEqual(contrast(pal[key], pal["bg"]), 4.5)
            self.assertGreaterEqual(contrast(pal["fg"], pal["field"]), 4.5)
            self.assertGreaterEqual(contrast(pal["select_fg"], pal["select"]), 4.5)
        self.assertEqual(palette("unknown"), PALETTES["light"])
        self.assertAlmostEqual(contrast("#000000", "#ffffff"), 21.0, places=1)


if __name__ == "__main__":
    unittest.main()
