"""
add_voice.py - puts the sound into a finished MP4 (no re-rendering needed).

    # voice only
    python add_voice.py out/ep03_lamplight_1080p.mp4 out/voice/ep03_radcliffe_line/narration.wav

    # voice + music bed + sting sound (sting time is read from the episode file)
    python add_voice.py out/ep03_lamplight_1080p.mp4 out/voice/ep03_radcliffe_line/narration.wav ^
        --music path/to/track.mp3 --sting-sfx out/audio/sting.wav --episode episodes/ep03_radcliffe_line.json

This makes a NEW file next to the video, ending in _voice.mp4. The original is not touched.

What happens to the sound:
- the voice is gently compressed and set to -14 LUFS, the level YouTube plays videos at;
- the music (optional) is set 19 dB under the voice, as the brand asks (18-20 dB), loops if it
  is too short, and fades in at the start and out at the end;
- the sting sound (optional) plays at the sting's time;
- a limiter keeps the peaks below about -1 dB so nothing crackles;
- the picture is copied as it is (fast, no quality loss).
Only use music you are allowed to use on a monetized channel (e.g. the YouTube Audio Library),
and log it in source_log.csv and in the episode's "music" list.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

VOICE_TARGET = -14.0  # LUFS: YouTube's playback level
# Gentle compressor (evens out loud and soft words) then a limiter (flattens the few sharp peaks),
# so the whole voice can be made louder safely.
COMP = ("acompressor=threshold=-24dB:ratio=4:attack=3:release=150:makeup=3,"
        "alimiter=limit=0.35:attack=2:release=50:level=false")


def measure(path, pre=""):
    """Ask ffmpeg how loud a sound file is (it prints the numbers as a { ... } block)."""
    chain = (pre + "," if pre else "") + f"loudnorm=I={VOICE_TARGET}:TP=-2:LRA=11:print_format=json"
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-af", chain, "-f", "null", "-"],
                       capture_output=True, text=True, check=True)
    log = r.stderr
    start = log.rindex("{")
    return json.loads(log[start:log.index("}", start) + 1])


def duration_of(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def main():
    ap = argparse.ArgumentParser(description="Add narration (and optional music and sting sound) to an MP4.")
    ap.add_argument("video", help="the MP4 made by map_engine.py")
    ap.add_argument("narration", help="narration.wav made by make_voice.py")
    ap.add_argument("--out", help="output file (default: <video name>_voice.mp4)")
    ap.add_argument("--music", help="music bed (mp3 / wav); loops if shorter than the video")
    ap.add_argument("--music-gap", type=float, default=19.0, help="how many dB the music sits under the voice")
    ap.add_argument("--sting-sfx", help="sting sound (e.g. out/audio/sting.wav from make_sting_sound.py)")
    ap.add_argument("--sting-t", type=float, help="when the sting starts (seconds)")
    ap.add_argument("--episode", help="episode JSON: used to find the sting time automatically")
    args = ap.parse_args()

    video, narration = Path(args.video), Path(args.narration)
    for f in [video, narration] + [Path(x) for x in (args.music, args.sting_sfx) if x]:
        if not f.exists():
            sys.exit(f"Not found: {f}")
    out = Path(args.out) if args.out else video.with_name(video.stem + "_voice.mp4")
    D = duration_of(video)

    # ---- 1. the voice: compress, measure, then set to -14 LUFS in one even step ("linear") ----
    m = measure(narration, COMP)
    voice = (f"{COMP},loudnorm=I={VOICE_TARGET}:TP=-2:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}"
             f":measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}"
             f":linear=true,aresample=48000,apad,atrim=0:{D:.3f}")
    inputs = ["-i", str(video), "-i", str(narration)]
    graph = [f"[1:a]{voice}[v]"]
    mix = ["[v]"]

    # ---- 2. the music bed, 19 dB under the voice ----
    if args.music:
        mm = measure(args.music)
        gain = (VOICE_TARGET - args.music_gap) - float(mm["input_i"])  # how much to turn it up or down
        inputs = inputs + ["-stream_loop", "-1", "-i", args.music]      # -stream_loop -1 = repeat forever
        k = len(mix) + 1
        graph.append(f"[{k}:a]aresample=48000,atrim=0:{D:.3f},volume={gain:.2f}dB,"
                     f"afade=t=in:d=3,afade=t=out:st={max(D - 4, 0):.3f}:d=4[m]")
        mix.append("[m]")
        print(f"Music set to {VOICE_TARGET - args.music_gap:.0f} LUFS ({gain:+.1f} dB)")

    # ---- 3. the sting sound at the sting's time ----
    if args.sting_sfx:
        t = args.sting_t
        if t is None and args.episode:
            ep = json.loads(Path(args.episode).read_text(encoding="utf-8"))
            stings = [e["t"] for e in ep["events"] if e["type"] == "sting"]
            t = stings[0] if stings else None
        if t is None:
            sys.exit("Give --sting-t seconds, or --episode with a sting event in it.")
        ms = measure(args.sting_sfx)
        gain = (VOICE_TARGET - 8) - float(ms["input_i"])  # a little under the voice level
        inputs = inputs + ["-i", args.sting_sfx]
        k = len(mix) + 1
        graph.append(f"[{k}:a]aresample=48000,volume={gain:.2f}dB,adelay={int(t * 1000)}:all=1[s]")
        mix.append("[s]")
        print(f"Sting sound at {t:.1f} s")

    # ---- 4. mix everything, keep peaks under about -1 dB, copy the picture ----
    limiter = "alimiter=limit=0.89:level=false"  # 0.89 = about -1 dB
    if len(mix) > 1:
        graph.append(f"{''.join(mix)}amix=inputs={len(mix)}:normalize=0:duration=first,{limiter}[a]")
    else:
        graph.append(f"[v]{limiter}[a]")
    cmd = ["ffmpeg", "-y", "-loglevel", "error"] + inputs + [
        "-filter_complex", ";".join(graph),
        "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-t", f"{D:.3f}", "-movflags", "+faststart", str(out)]
    subprocess.run(cmd, check=True)
    print("Saved", out)


if __name__ == "__main__":
    main()
