import unittest

import _path  # noqa: F401
from mviser.harmony import HarmonyContext, default_registry
from mviser.project_data import ProjectError, _check_color, compile_project, normalize
from mviser.scene import resolve_scene_state
from mviser.styling import StyleRuleError, chord_facts, match_rules, validate_rules

RULES = validate_rules([
    {"when": {"microtonal": True}, "set": {"background_color": "#AA00AA"}},
    {"when": {"function": "dominant"}, "set": {"background_color": "#AA0000", "pulse": 0.2, "motion": "slide"}},
    {"when": {"function": ["tonic", "subdominant"], "quality": "minor"}, "set": {"text_color": "#DDDDFF"}},
], _check_color)


def spec(value, key="C"):
    return default_registry().resolve(value, HarmonyContext.from_key(key))


class RuleMatchingTests(unittest.TestCase):
    def test_facts(self):
        facts = chord_facts(spec("G7"))
        self.assertEqual((facts["quality"], facts["function"], facts["roman"], facts["notation"]),
                         ("7", "dominant", "V", "symbol"))

    def test_first_match_wins_and_lists(self):
        self.assertEqual(match_rules(spec("G7"), RULES)["background_color"], "#AA0000")
        self.assertEqual(match_rules(spec("Am"), RULES), {"text_color": "#DDDDFF"})
        self.assertEqual(match_rules(spec("C"), RULES), {})
        self.assertEqual(match_rules(spec({"root": "G", "tones": [0, "5:4", "3:2", "7:4"]}), RULES)["background_color"],
                         "#AA00AA")

    def test_validation(self):
        bad = [
            "x",
            [{"when": {}}],
            [{"when": {"colour": 1}, "set": {}}],
            [{"when": {}, "set": {"size": 1}}],
            [{"when": {}, "set": {"background_color": "red"}}],
            [{"when": {}, "set": {"motion": "spin"}}],
            [{"when": {}, "set": {"pulse": -1}}],
        ]
        for rules in bad:
            with self.subTest(rules=rules), self.assertRaises((StyleRuleError, ProjectError)):
                validate_rules(rules, _check_color)


class PriorityTests(unittest.TestCase):
    def project(self, **chord_overrides):
        g = {"at": "2:1", "chord": "G7", **chord_overrides}
        raw = {"project": {"bpm": 120, "fps": 30, "key": "C"},
               "style": {"rules": [{"when": {"function": "dominant"},
                                    "set": {"background_color": "#AA0000", "text_color": "#FFFF00",
                                            "motion": "cut", "pulse": 0.3}}]},
               "motion": {"enter": "fade", "pulse": 0.0},
               "chords": [{"at": "1:1", "chord": "C"}, g]}
        return compile_project(normalize(raw))

    def state(self, project):
        return resolve_scene_state(project, project.tracks["chord"].events[1].start_frame)

    def test_rule_applies(self):
        s = self.state(self.project())
        self.assertEqual((s.background_color, s.text_color, s.chord_motion.opacity), ("#AA0000", "#FFFF00", 1.0))
        self.assertAlmostEqual(s.chord_scale, 1.3)

    def test_event_level_wins(self):
        s = self.state(self.project(color="#000011", motion="fade", pulse=0))
        self.assertEqual((s.background_color, s.chord_motion.opacity, s.chord_scale), ("#000011", 0.0, 1.0))

    def test_chord_colors_beat_rules_and_rules_beat_auto(self):
        project = self.project()
        project.doc["style"]["chord_colors"] = {"G7": "#123456"}
        self.assertEqual(self.state(project).background_color, "#123456")
        first = resolve_scene_state(project, 0)
        self.assertNotEqual(first.background_color, "#AA0000")  # C is tonic: auto colour

    def test_invalid_rule_in_project(self):
        with self.assertRaises(ProjectError):
            normalize({"style": {"rules": [{"when": {"x": 1}, "set": {}}]}})
        with self.assertRaises(ProjectError):
            normalize({"chords": [{"at": 0, "chord": "C", "pulse": "big"}]})


if __name__ == "__main__":
    unittest.main()
