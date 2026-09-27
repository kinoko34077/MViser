import json
import tempfile
import unittest
from pathlib import Path

import _path  # noqa: F401
from mviser.harmony import ChordSpec, HarmonyContext, MappingError, Tone, default_registry, parse_interval, parse_pitch
from mviser.harmony.analyzers import identify
from mviser.harmony.sources import SourceError, import_mcb
from mviser.project_data import ProjectError, compile_project, normalize

C = HarmonyContext.from_key("C")
AM = HarmonyContext.from_key("Am")


def resolve(value, context=C, notation=None):
    return default_registry().resolve(value, context, notation)


class PitchModelTests(unittest.TestCase):
    def test_pitches(self):
        self.assertEqual(parse_pitch("Eb"), 300)
        self.assertEqual(parse_pitch("A4"), 900)
        self.assertEqual(parse_pitch(1250), 50)
        self.assertEqual(parse_pitch({"microStepInOctave": 90000}), 900)

    def test_intervals(self):
        self.assertAlmostEqual(parse_interval("3:2").cents, 701.955, places=3)
        self.assertAlmostEqual(parse_interval("edo31:18").cents, 1200 * 18 / 31)
        self.assertEqual(parse_interval("b3").cents, 300)
        self.assertEqual(parse_interval("#11").cents, 1800)
        self.assertEqual(parse_interval("P5").cents, 700)
        self.assertEqual(parse_interval(386.3).cents, 386.3)


class MapperTests(unittest.TestCase):
    def test_symbol(self):
        spec = resolve("Dm7/F")
        self.assertEqual((spec.root_name, spec.quality, spec.bass_cents), ("D", "m7", 500))
        self.assertEqual([t.cents for t in spec.tones], [0, 300, 700, 1000])
        self.assertEqual(spec.source["notation"], "symbol")
        self.assertEqual([t.cents for t in resolve("G7(b9)").tones], [0, 400, 700, 1000, 1300])

    def test_degree_major_and_minor_keys(self):
        self.assertEqual(resolve("vi").display, "Am")
        self.assertEqual(resolve("V7").display, "G7")
        self.assertEqual(resolve("bVII").display, "Bb")
        self.assertEqual(resolve("V/ii").root_name, "A")
        self.assertEqual(resolve("III", AM).display, "C")
        self.assertEqual(resolve("V/III", AM).root_name, "G")
        with self.assertRaises(MappingError):
            resolve("vi", HarmonyContext())

    def test_auto_detection_does_not_confuse_numerals_with_notes(self):
        self.assertEqual(resolve("bVII").source["notation"], "degree")
        self.assertEqual(resolve("Bb").source["notation"], "symbol")

    def test_tones_microtonal(self):
        spec = resolve({"root": "A", "tones": ["5:4", "3:2"]})
        self.assertEqual(spec.display, "A")  # named by identify analyzer
        self.assertEqual(spec.quality, "major")
        self.assertFalse(spec.is_12tet)
        self.assertTrue(spec.analysis["microtonal"])
        self.assertAlmostEqual(spec.analysis["identified"]["deviation_cents"], 5.21, places=1)

    def test_tones_unknown_fails_open(self):
        spec = resolve({"root": "C", "tones": [0, 50, 150]})
        self.assertIsNone(spec.quality)
        self.assertTrue(spec.display.startswith("?("))
        self.assertEqual(spec.analysis["identified"]["quality"], "UNKNOWN")
        self.assertNotIn("roman", spec.analysis)

    def test_pitch_set_mvp1_path(self):
        spec = resolve({"pitches": [52, 57, 60, 64]})  # E A C E -> Am/E
        self.assertEqual(spec.quality, "minor")
        self.assertEqual(spec.root_name, "A")
        self.assertEqual(spec.analysis["identified"]["symbol"], "Am/E")

    def test_explicit_notation_and_errors(self):
        self.assertEqual(resolve({"notation": "symbol", "value": "C"}).display, "C")
        for bad in ("H", "Cxyz", {"root": "C", "tones": []}):
            with self.subTest(bad=bad), self.assertRaises(MappingError):
                resolve(bad)
        with self.assertRaises(MappingError):
            resolve("C", notation="nope")

    def test_custom_mapper_and_analyzer_can_be_registered(self):
        class Fixed:
            name = "fixed"

            def accepts(self, value):
                return value == "POWER"

            def map(self, value, context):
                return ChordSpec("5", 0.0, (Tone(0.0), Tone(700.0)))

        class Tag:
            name = "tag"

            def analyze(self, spec, context):
                return spec.with_analysis(tag="ok")

        registry = default_registry()
        registry.register_mapper(Fixed())
        registry.register_analyzer(Tag())
        spec = registry.resolve("POWER", C, analyzers=["tag"])
        self.assertEqual((spec.display, spec.analysis), ("5", {"tag": "ok"}))


class AnalyzerTests(unittest.TestCase):
    def test_identify_prefers_template_order_and_bass(self):
        self.assertEqual(identify([200, 500, 900, 0], 500, 200)["symbol"], "Dm7/F")
        self.assertEqual(identify([0, 400, 700, 900], 0)["symbol"], "C6")
        self.assertEqual(identify([0, 100, 200])["quality"], "UNKNOWN")

    def test_function_major(self):
        cases = {"C": ("I", "tonic"), "Dm7": ("ii", "subdominant"), "G7": ("V", "dominant"),
                 "Bdim": ("vii°", "dominant"), "Fm": ("iv", "borrowed/chromatic")}
        for symbol, expected in cases.items():
            a = resolve(symbol).analysis
            self.assertEqual((a["roman"], a["function"]), expected, symbol)

    def test_function_minor(self):
        cases = {"Am": ("i", "tonic"), "F": ("VI", "subdominant"), "E7": ("V", "dominant"),
                 "G": ("VII", "dominant"), "C": ("III", "tonic")}
        for symbol, expected in cases.items():
            a = resolve(symbol, AM).analysis
            self.assertEqual((a["roman"], a["function"]), expected, symbol)


class ProjectIntegrationTests(unittest.TestCase):
    def test_project_key_display_modes_and_colors(self):
        raw = {"project": {"bpm": 120, "fps": 30, "key": "C"},
               "harmony": {"display": "roman"},
               "style": {"chord_colors": {"V": "#445566"}},
               "chords": [{"at": "1:1", "chord": "vi"}, {"at": "2:1", "chord": "G7"},
                          {"at": "3:1", "chord": {"root": "D", "tones": [0, "6:5", "3:2"]}}]}
        project = compile_project(normalize(raw))
        events = project.tracks["chord"].events
        self.assertEqual([e.payload["display"] for e in events], ["vi", "V", "ii"])
        from mviser.scene import resolve_scene_state
        self.assertEqual(resolve_scene_state(project, events[1].start_frame).background_color, "#445566")

    def test_invalid_key_and_display(self):
        for raw in ({"project": {"key": "H"}}, {"harmony": {"display": "x"}},
                    {"chords": [{"at": 0, "chord": "vi"}]}):
            with self.subTest(raw=raw), self.assertRaises(ProjectError):
                compile_project(normalize(raw))


MCB = {
    "app": "muChordbot",
    "payload": {
        "pitchPresets": [{"id": "P5", "cent": 701.96}, {"id": "M3", "cent": 386.31}],
        "chordPresets": [{"id": "MAJ", "name": "M", "tones": [
            {"localCent": 0, "label": "R"}, {"pitchPresetId": "M3"}, {"pitchPresetId": "P5"}]}],
        "progression": {"parts": [
            {"chordId": "MAJ", "root": {"microStepInOctave": 90000}, "beats": 4},
            {"chordId": "MAJ", "root": {"microStepInOctave": 50000}, "beats": 2},
            {"chordId": "MAJ", "root": {"microStepInOctave": 70000}, "beats": 4}]},
    },
}


class McbImportTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        (self.dir / "p.mcb").write_text(json.dumps(MCB), encoding="utf-8")

    def test_import_positions_and_tones(self):
        events = import_mcb(self.dir / "p.mcb", {}, 2.0, 0.5)
        self.assertEqual([e["at"] for e in events], ["2:1", "3:1", "3:3"])
        self.assertEqual(events[0]["value"]["root"], {"cents": 900.0})
        self.assertEqual([t["cents"] for t in events[0]["value"]["tones"]], [0.0, 386.31, 701.96])

    def test_import_through_project(self):
        raw = {"project": {"bpm": 120, "fps": 30, "key": "C"},
               "imports": [{"format": "mcb", "path": "p.mcb", "at": "1:1"}]}
        project = compile_project(normalize(raw, self.dir), self.dir)
        displays = [e.payload["display"] for e in project.tracks["chord"].events]
        self.assertEqual(displays, ["A", "F", "G"])

    def test_bad_mcb(self):
        (self.dir / "bad.mcb").write_text("{}", encoding="utf-8")
        with self.assertRaises(SourceError):
            import_mcb(self.dir / "bad.mcb")
        with self.assertRaises(ProjectError):
            normalize({"imports": [{"format": "xml", "path": "p"}]}, self.dir)


if __name__ == "__main__":
    unittest.main()
