import unittest

import _path  # noqa: F401
from mviser.chord_list import chord_rows, current_row
from mviser.project_data import compile_project, normalize


class ChordListTests(unittest.TestCase):
    def test_rows_and_current(self):
        project = compile_project(normalize({
            "project": {"bpm": 120, "fps": 10, "key": "C", "duration": "4:1"},
            "chords": [{"at": "1:1", "chord": "C"}, {"at": "2:1", "chord": "G7"}, {"at": "3:1", "chord": "Am"}]}))
        rows = chord_rows(project, "tempo")
        self.assertEqual([(r["frame"], r["time"], r["display"], r["roman"], r["function"]) for r in rows],
                         [(0, "1:1.00", "C", "I", "tonic"), (20, "2:1.00", "G7", "V", "dominant"),
                          (40, "3:1.00", "Am", "vi", "tonic")])
        self.assertEqual([current_row(rows, f) for f in (0, 19, 20, 59, 60)], [0, 0, 1, 2, None])
        self.assertEqual(chord_rows(project)[1]["time"], "00:02.00")


if __name__ == "__main__":
    unittest.main()
