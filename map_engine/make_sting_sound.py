"""
make_sting_sound.py - makes the 2.5-second sting sound from scratch (no recordings, no licence needed).

    python make_sting_sound.py            -> out/audio/sting.wav

The brand (brand/production.md) asks for "a soft quill-on-paper scratch and a single low tone
as the territory hatches in". This builds both with simple maths:
  - the low tone: a deep note (D, 73 Hz) with a soft start and a long fade, plus a quiet overtone;
  - the quill: short bursts of filtered noise, timed with the hatch lines in the sting
    (the sting's territory hatches in from 1.0 s to 1.8 s).
"""
import wave
from pathlib import Path

import numpy as np

RATE = 48000
HERE = Path(__file__).resolve().parent


def low_tone(n, start, freq=73.4, length=2.2):
    t = np.arange(n) / RATE - start
    env = np.where(t < 0, 0, np.minimum(t / 0.25, 1) * np.exp(-np.clip(t, 0, None) / (length / 2.5)))
    return env * (np.sin(2 * np.pi * freq * t) + 0.25 * np.sin(2 * np.pi * freq * 2 * t))


def quill(n, start, end, rng):
    """Scratchy strokes: each stroke is a little burst of noise, filtered to sound like a nib on paper."""
    out = np.zeros(n)
    for s in np.arange(start, end, 0.09):           # one stroke every 90 ms (like the hatch lines)
        a, b = int((s + rng.uniform(0, 0.02)) * RATE), int((s + 0.06) * RATE)
        burst = rng.standard_normal(b - a)
        burst = np.diff(burst, prepend=0)            # removes the low rumble: brighter, papery sound
        k = np.ones(6) / 6
        burst = np.convolve(burst, k, mode="same")   # softens the very top: less hiss
        burst *= np.hanning(b - a) * rng.uniform(0.5, 1.0)
        out[a:b] += burst
    return out


def main():
    rng = np.random.default_rng(7)  # fixed seed: the sound is the same every time
    n = int(2.5 * RATE)
    mix = 0.55 * low_tone(n, start=1.0) + 0.35 * quill(n, 1.0, 1.8, rng)
    mix *= 0.7 / np.max(np.abs(mix))                 # leave headroom
    fade = np.ones(n)
    fade[-int(0.3 * RATE):] = np.linspace(1, 0, int(0.3 * RATE))  # match the sting's fade-out
    mix *= fade
    out = HERE / "out" / "audio" / "sting.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes((mix * 32767).astype(np.int16).tobytes())
    print("Saved", out)


if __name__ == "__main__":
    main()
