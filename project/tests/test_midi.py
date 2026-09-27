import tempfile
import unittest
from pathlib import Path

import _path  # noqa: F401
import mido

from mviser.harmony.midi_source import import_midi, read_notes, segment_chords
from mviser.harmony.sources import SourceError
from mviser.project_data import ProjectError, compile_project, normalize

TPB = 480


def write_midi(path, notes, bpm=120, drums=()):
    """notes: (start_beat, end_beat, note[, channel]) in beats."""
    midi = mido.MidiFile(ticks_per_beat=TPB)
    meta = mido.MidiTrack([mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm), time=0)])
    midi.tracks.append(meta)
    events = []
    for item in list(notes) + [(s, e, n, 9) for s, e, n in drums]:
        s, e, n = item[:3]
        ch = item[3] if len(item) > 3 else 0
        events += [(round(s * TPB), 1, mido.Message("note_on", note=n, velocity=90, channel=ch)),
                   (round(e * TPB), 0, mido.Message("note_off", note=n, velocity=0, channel=ch))]
    track = mido.MidiTrack()
    last = 0
    for tick, _, msg in sorted(events, key=lambda x: (x[0], x[1])):
        track.append(msg.copy(time=tick - last))
        last = tick
    midi.tracks.append(track)
    midi.save(str(path))


class MidiSourceTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        # 120 bpm: beat = 0.5 s. Am (A C E) 0-4, strummed F (onsets 10 ms apart) 4-8,
        # single G 8-10, silence 10-12, G7 12-16. Drums must be ignored.
        write_midi(self.dir / "song.mid", [
            (0, 4, 57), (0, 4, 60), (0, 4, 64),
            (4, 8, 53), (4.02, 8, 57), (4.04, 8, 60),
            (8, 10, 55),
            (12, 16, 55), (12, 16, 59), (12, 16, 62), (12, 16, 65),
        ], drums=[(0, 1, 36)])

    def test_read_notes_uses_tempo_and_skips_drums(self):
        notes = read_notes(self.dir / "song.mid")
        self.assertEqual(notes[0], (0.0, 2.0, 57))
        self.assertNotIn(36, [n for _, _, n in notes])
        self.assertEqual(len(notes), 11)

    def test_chord_segmentation(self):
        segments = segment_chords(read_notes(self.dir / "song.mid"))
        summary = [(round(s, 3), round(e, 3), p) for s, e, p in segments]
        self.assertEqual(summary, [
            (0.0, 2.0, [57, 60, 64]),
            (2.0, 4.0, [53, 57, 60]),
            (4.0, 5.0, [55]),
            (6.0, 8.0, [55, 59, 62, 65]),
        ])

    def test_notes_mode(self):
        events = import_midi(self.dir / "song.mid", {"mode": "notes"}, 1.0)
        self.assertEqual(len(events), 11)
        self.assertEqual((events[0]["at"], events[0]["duration"]), (1.0, 2.0))

    def test_project_import_names_chords_and_single_notes(self):
        raw = {"project": {"bpm": 120, "fps": 30, "key": "C"},
               "imports": [{"format": "midi", "path": "song.mid", "at": "2:1"}]}
        project = compile_project(normalize(raw, self.dir), self.dir)
        events = project.tracks["chord"].events
        self.assertEqual([e.payload["display"] for e in events], ["Am", "F", "G", "G7"])
        self.assertEqual([e.start_frame for e in events], [60, 120, 180, 240])
        self.assertEqual(events[2].end_frame, 210)  # single note ends; silence has no chord
        self.assertIsNone(project.tracks["chord"].active(215))
        self.assertEqual(events[3].payload["chord"].analysis["roman"], "V")
        self.assertNotIn("roman", events[2].payload["chord"].analysis)

    def test_errors(self):
        (self.dir / "bad.mid").write_bytes(b"not midi")
        with self.assertRaises(SourceError):
            from mviser.harmony.sources import IMPORTERS
            IMPORTERS["midi"](self.dir / "bad.mid", {})
        with self.assertRaises(ProjectError):
            normalize({"imports": [{"format": "midi", "path": "song.mid", "mode": "x"}]}, self.dir)


if __name__ == "__main__":
    unittest.main()
