"""
make_voice.py - makes the spoken narration for an episode (Google Gemini text-to-speech).

What it does
------------
1. Reads the episode JSON and takes the text of every "caption" event.
   (The voice says exactly the same words as the captions.)
2. Asks Gemini to read each caption aloud and saves one WAV file per caption.
3. Checks that each clip fits before the next caption starts.
4. Joins all clips into ONE narration track (narration.wav) that is exactly as
   long as the video, with each clip placed at its caption's start time.

Then run  add_voice.py  to put that narration into the MP4 (no need to re-render).

Example
-------
    python make_voice.py episodes/ep03_radcliffe_line.json --env "E:/arts and stuff/TTS automation/.env"

The API key is read from that .env file (GEMINI_API_KEY) or from the
GEMINI_API_KEY environment variable. It is never printed.

Saving money / quota: a clip is only made again if its caption text changed,
because the file name includes a short fingerprint (hash) of the text.
"""

import argparse
import hashlib
import json
import os
import sys
import time
import wave
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
RATE = 24000  # Gemini TTS sends 24,000 samples per second, 16-bit, mono

# How the voice should read. The Shorts used "...with natural pauses", but that was too slow
# for our caption timing (about 1.5 words a second). Captions need about 2.4 words a second.
DEFAULT_STYLE = "Calm, serious historical documentary narration at a steady, natural pace, without long pauses"


# --------------------------------------------------------------------------
# 1.  SETTINGS: API key, model, voice
# --------------------------------------------------------------------------
def load_settings(env_file):
    """Read key / model / voice from a .env file (if given), else from environment variables."""
    values = {}
    if env_file:
        from dotenv import dotenv_values  # small helper library that reads .env files
        values = dotenv_values(env_file)
    key = values.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not key:
        sys.exit("No GEMINI_API_KEY found. Use --env path/to/.env or set the GEMINI_API_KEY variable.")
    model = values.get("GEMINI_TTS_MODEL") or os.getenv("GEMINI_TTS_MODEL") or "gemini-2.5-flash-preview-tts"
    voice = values.get("GEMINI_TTS_VOICE") or os.getenv("GEMINI_TTS_VOICE") or "Charon"
    return key.strip(), model, voice


# --------------------------------------------------------------------------
# 2.  ONE CLIP: text -> WAV file
# --------------------------------------------------------------------------
def speak(client, model, voice, style, text, out_path, tries=5):
    """Ask Gemini to read `text` aloud and save it as a WAV file.
    If Google says "too many requests" (error 429), wait and try again (one key only)."""
    from google.genai import types

    config = types.GenerateContentConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
            )
        ),
    )
    prompt = f"Read aloud in a {style} style:\n{text}"

    wait = 20  # seconds to wait after a rate-limit error (doubles each time)
    for attempt in range(1, tries + 1):
        try:
            resp = client.models.generate_content(model=model, contents=prompt, config=config)
            audio = None
            for part in resp.candidates[0].content.parts:
                if part.inline_data and part.inline_data.data:
                    audio = part.inline_data.data
                    break
            if not audio:
                raise RuntimeError("Gemini sent no audio back.")
            if audio.startswith(b"RIFF"):  # already a complete WAV file
                out_path.write_bytes(audio)
            else:  # raw sound samples: wrap them in a WAV container
                with wave.open(str(out_path), "wb") as w:
                    w.setnchannels(1)
                    w.setsampwidth(2)
                    w.setframerate(RATE)
                    w.writeframes(audio)
            return
        except Exception as e:  # noqa: BLE001  (we report every kind of error the same way)
            msg = str(e)
            # A DAILY limit will not clear in a few minutes, so stop now. Clips already made are
            # kept, and the next run only makes the missing ones.
            if "PerDay" in msg:
                sys.exit("\nStopped: the free daily limit for this API key is used up (Google allows only a few "
                         "TTS requests per day for free). Run this again after it resets - finished clips "
                         "are kept. Or turn on billing for this key in Google AI Studio.")
            # A per-MINUTE limit clears quickly: wait and try again.
            if ("429" in msg or "RESOURCE_EXHAUSTED" in msg) and attempt < tries:
                print(f"    rate limit - waiting {wait}s, then retry {attempt + 1}/{tries}")
                time.sleep(wait)
                wait *= 2
                continue
            raise


def read_wav(path):
    """WAV file -> numpy array of samples between -1 and 1 (mono, 24 kHz)."""
    with wave.open(str(path), "rb") as w:
        if w.getframerate() != RATE or w.getnchannels() != 1 or w.getsampwidth() != 2:
            sys.exit(f"{path.name}: expected 24 kHz mono 16-bit audio")
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    return data.astype(np.float32) / 32768.0


# --------------------------------------------------------------------------
# 3.  MAIN: all captions -> clips -> one narration track
# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Make Gemini narration for an episode's captions.")
    ap.add_argument("episode", help="episode JSON file")
    ap.add_argument("--env", help=".env file holding GEMINI_API_KEY (and optional model / voice)")
    ap.add_argument("--voice", help="Gemini voice name, e.g. Charon (overrides the .env)")
    ap.add_argument("--style", default=DEFAULT_STYLE, help="how the voice should read")
    ap.add_argument("--lead", type=float, default=0.3, help="seconds after a caption appears before the voice starts")
    ap.add_argument("--out", help="folder for the clips (default: out/voice/<episode name>)")
    args = ap.parse_args()

    ep_path = Path(args.episode)
    episode = json.loads(ep_path.read_text(encoding="utf-8"))
    out_dir = Path(args.out) if args.out else HERE / "out" / "voice" / ep_path.stem
    out_dir.mkdir(parents=True, exist_ok=True)

    # Captions in time order. Each one becomes one spoken line.
    captions = sorted([e for e in episode["events"] if e["type"] == "caption"], key=lambda e: e["t"])
    if not captions:
        sys.exit("This episode has no caption events, so there is nothing to say.")

    key, model, voice = load_settings(args.env)
    voice = args.voice or voice
    print(f"Voice: {voice}   Model: {model}   Lines: {len(captions)}")

    client = None  # only connect to Google if at least one clip is missing
    clips = []
    for n, cap in enumerate(captions, start=1):
        text = cap["text"]
        # Fingerprint of everything that changes the sound. New text/voice/style = new file.
        tag = hashlib.sha1(f"{voice}|{model}|{args.style}|{text}".encode("utf-8")).hexdigest()[:8]
        path = out_dir / f"{n:02d}_{tag}.wav"
        if path.exists():
            print(f"  [{n:02d}] already made  {path.name}")
        else:
            if client is None:
                from google import genai
                client = genai.Client(api_key=key)
            print(f"  [{n:02d}] speaking: {text[:60]}...")
            speak(client, model, voice, args.style, text, path)
        clips.append({"n": n, "t": cap["t"] + args.lead, "file": path.name, "text": text})

    # ---- check timing: each clip must end before the next line starts ----
    duration = float(episode["duration"])
    print("\nTiming check (voice length vs. time until the next line):")
    problems = 0
    for i, c in enumerate(clips):
        c["seconds"] = round(len(read_wav(out_dir / c["file"])) / RATE, 2)
        next_t = clips[i + 1]["t"] if i + 1 < len(clips) else duration
        room = next_t - c["t"]
        ok = c["seconds"] <= room
        problems += not ok
        print(f"  [{c['n']:02d}] {c['seconds']:5.1f}s of {room:5.1f}s  {'OK' if ok else 'TOO LONG - would overlap'}")

    # ---- build ONE narration track as long as the video ----
    track = np.zeros(int(duration * RATE) + RATE, dtype=np.float32)  # silence, plus 1 s spare
    for c in clips:
        sound = read_wav(out_dir / c["file"])
        start = int(c["t"] * RATE)
        end = min(start + len(sound), len(track))
        track[start:end] += sound[: end - start]  # "+=" so an overlap is audible, never silently cut
    track = np.clip(track[: int(duration * RATE)], -1.0, 1.0)
    narration = out_dir / "narration.wav"
    with wave.open(str(narration), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes((track * 32767).astype(np.int16).tobytes())

    # A small record of what was said and when (handy for checking and for subtitles later).
    (out_dir / "voice_manifest.json").write_text(
        json.dumps({"voice": voice, "model": model, "style": args.style, "clips": clips}, indent=2),
        encoding="utf-8")
    print(f"\nSaved {narration}")
    if problems:
        print(f"WARNING: {problems} line(s) are too long for their slot. Give those captions more time "
              f"in the episode JSON (or shorten the text), then run this again.")


if __name__ == "__main__":
    main()
