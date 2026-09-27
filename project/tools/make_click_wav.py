"""Generate a metronome-click WAV for samples/tests: make_click_wav.py OUT BPM SECONDS"""

import math
import struct
import sys
import wave


def make_click_wav(path, bpm: float, seconds: float, rate: int = 44100) -> None:
    beat = 60.0 / bpm
    frames = bytearray()
    for n in range(int(seconds * rate)):
        t = n / rate
        local = t % beat
        accent = 1760.0 if int(t / beat) % 4 == 0 else 880.0
        amp = 0.5 * math.exp(-local * 60) if local < 0.08 else 0.0
        frames += struct.pack("<h", int(amp * 32767 * math.sin(2 * math.pi * accent * t)))
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(bytes(frames))


if __name__ == "__main__":
    make_click_wav(sys.argv[1], float(sys.argv[2]), float(sys.argv[3]))
