"""
add_voice.py - puts a narration track into a finished MP4 (no re-rendering needed).

    python add_voice.py out/ep03_cinematic_1080p.mp4 out/voice/ep03_radcliffe_line/narration.wav

This makes a NEW file next to the video, ending in _voice.mp4. The original is not touched.

What happens to the sound:
- loudness is evened out to -14 LUFS, the level YouTube plays videos at, so
  YouTube will not turn it down or up;
- the peaks are kept below about -1 dB so nothing crackles;
- the picture is copied as it is (fast, no quality loss).
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description="Add a narration WAV to an MP4.")
    ap.add_argument("video", help="the MP4 made by map_engine.py")
    ap.add_argument("narration", help="narration.wav made by make_voice.py")
    ap.add_argument("--out", help="output file (default: <video name>_voice.mp4)")
    args = ap.parse_args()

    video, narration = Path(args.video), Path(args.narration)
    for f in (video, narration):
        if not f.exists():
            sys.exit(f"Not found: {f}")
    out = Path(args.out) if args.out else video.with_name(video.stem + "_voice.mp4")

    # PASS 1: measure how loud the narration is now (ffmpeg prints the numbers as JSON).
    target = "I=-14:TP=-2:LRA=11"   # -2 dB (not -1.5) leaves room for the small overshoot AAC adds
    # Gentle compressor: evens out loud and soft words, the usual first step for narration.
    # Then a limiter flattens the few sharp peaks, so the whole voice can be made louder safely.
    comp = ("acompressor=threshold=-24dB:ratio=4:attack=3:release=150:makeup=3,"
            "alimiter=limit=0.35:attack=2:release=50:level=false")
    probe = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(narration), "-af", f"{comp},loudnorm={target}:print_format=json", "-f", "null", "-"],
        capture_output=True, text=True, check=True)
    log = probe.stderr
    start = log.rindex("{")              # the numbers are the last { ... } block in ffmpeg's log
    m = json.loads(log[start:log.index("}", start) + 1])

    # PASS 2: use those numbers so ffmpeg turns the WHOLE track up or down by one even amount
    # ("linear"), instead of guessing as it goes (which goes wrong with long silences).
    loudnorm = (f"loudnorm={target}:measured_I={m['input_i']}:measured_TP={m['input_tp']}"
                f":measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}"
                f":offset={m['target_offset']}:linear=true")

    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(video),        # input 0: the picture
        "-i", str(narration),    # input 1: the voice
        "-map", "0:v", "-map", "1:a",            # take picture from 0, sound from 1
        "-c:v", "copy",                           # do not re-encode the picture
        "-af", comp + "," + loudnorm + ",aresample=48000",  # compress, YouTube loudness, 48 kHz
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",                              # stop at the end of the shorter input
        "-movflags", "+faststart",
        str(out),
    ]
    subprocess.run(cmd, check=True)
    print("Saved", out)


if __name__ == "__main__":
    main()
