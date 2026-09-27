import unittest

import _path  # noqa: F401
from mviser.chord_engine import ChordParseError, parse_chord


class ChordParserTests(unittest.TestCase):
    def test_issue_examples(self):
        cases = {
            "C": ("C", 0, "major", None),
            "Cm": ("C", 0, "minor", None),
            "C#maj7": ("C#", 1, "maj7", None),
            "Bb7": ("Bb", 10, "7", None),
            "Dm7/F": ("D", 2, "m7", "F"),
            "Gsus4": ("G", 7, "sus4", None),
        }
        for symbol, (root, pc, quality, bass) in cases.items():
            with self.subTest(symbol=symbol):
                chord = parse_chord(symbol)
                self.assertEqual((chord.root, chord.root_pc, chord.quality, chord.bass), (root, pc, quality, bass))
                self.assertEqual(chord.raw_symbol, symbol)

    def test_mvp1_candidate_qualities(self):
        for symbol, quality in {"Cdim": "dim", "Caug": "aug", "Csus2": "sus2", "Em7": "m7", "Fmaj7": "maj7"}.items():
            self.assertEqual(parse_chord(symbol).quality, quality)

    def test_tension_is_preserved_not_dropped(self):
        chord = parse_chord("G7(b9)")
        self.assertEqual(chord.quality, "7")
        self.assertEqual(chord.extension, "b9")

    def test_slash_bass_pitch_class(self):
        self.assertEqual(parse_chord("Bm7/D").bass_pc, 2)
        self.assertEqual(parse_chord("C/Bb").bass_pc, 10)

    def test_invalid_symbol(self):
        for bad in ("", "H7", "7C", "xyz"):
            with self.subTest(bad=bad), self.assertRaises(ChordParseError):
                parse_chord(bad)


if __name__ == "__main__":
    unittest.main()
