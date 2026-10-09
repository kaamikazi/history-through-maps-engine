"""
make_description.py - writes the YouTube description for an episode.

    python make_description.py episodes/ep03_radcliffe_line.json

It follows the brand's per-upload checklist (brand/production.md in the History-C repo):
  1. the one-line hook
  2. chapters with timestamps (YouTube turns these into chapter marks)
  3. sources (rows of source_log.csv for this video, plus the brand-wide rows)
  4. music credits (from the episode's "music" list, if any)
  5. the channel's About text

The result is saved as out/<episode>_description.txt. Read it before pasting:
it warns about anything still marked "to verify".
"""
import argparse
import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

# From brand/strategy.md ("About text") in the History-C repo.
ABOUT = ("History Through Maps tells the past by redrawing it, one animated map at a time. Each video "
         "follows a border, a route or an empire as it changes, with dates on screen and sources in the "
         "description. Every border has a story.")


def clock(seconds):
    """75 -> '1:15', 3725 -> '1:02:05' (the format YouTube reads as a chapter time)."""
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def main():
    ap = argparse.ArgumentParser(description="Write the YouTube description for an episode.")
    ap.add_argument("episode")
    ap.add_argument("--log", default=str(HERE.parent / "source_log.csv"), help="the source log CSV")
    ap.add_argument("--out", help="output text file (default: out/<episode>_description.txt)")
    args = ap.parse_args()

    ep_path = Path(args.episode)
    ep = json.loads(ep_path.read_text(encoding="utf-8"))
    warnings = []

    # ---- 1. hook ----
    hook = ep.get("hook") or ep.get("subtitle", "")
    if not ep.get("hook"):
        warnings.append('No "hook" in the episode file; used the subtitle instead.')

    # ---- 2. chapters: the opening, each chapter card, and any extra marks ----
    marks = [{"t": 0, "title": ep.get("opening_title", "Introduction")}]
    marks += [{"t": e["t"], "title": f"{e['number']}: {e['title'].replace(chr(10), ' ')}"}
              for e in ep["events"] if e["type"] == "chapter"]
    marks += [m for m in ep.get("chapters_extra", []) if m["t"] > 0]
    for e in ep["events"]:
        if e["type"] == "endscreen":
            marks.append({"t": e["t"], "title": "Next map"})
    if any(m["t"] == 0 for m in ep.get("chapters_extra", [])):  # a custom title for 0:00
        marks[0]["title"] = [m for m in ep["chapters_extra"] if m["t"] == 0][0]["title"]
    marks.sort(key=lambda m: m["t"])
    # YouTube's rules for chapters: start at 0:00, at least 3, each at least 10 seconds long.
    if len(marks) < 3:
        warnings.append("YouTube needs at least 3 chapters to show chapter marks.")
    for a, b in zip(marks, marks[1:]):
        if b["t"] - a["t"] < 10:
            warnings.append(f"Chapter '{a['title']}' is shorter than 10 s; YouTube may ignore the chapters.")

    # ---- 3. sources from the log ----
    video = ep.get("source_video")
    if not video:
        warnings.append('No "source_video" in the episode file, so no sources could be matched in the log.')
    sources = []
    with open(args.log, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            v = row["video"]
            used = (video and v == video) or v == "ALL VIDEOS (brand)"
            if not used:
                continue  # CANDIDATE / REJECTED rows and other videos are left out
            line = f"- {row['map_or_image']}. {row['source_url']}"
            if row["credit_line_shown"] and not row["credit_line_shown"].lower().startswith("not required"):
                line += f" ({row['credit_line_shown']})"
            sources.append(line)
            if "to verify" in (row["license_or_rights_statement"] + row["map_or_image"]).lower():
                warnings.append(f"Source still marked TO VERIFY: {row['map_or_image'][:70]}")

    # ---- 4. music ----
    music = [f"- \"{m['title']}\" by {m['artist']} ({m.get('licence', 'licence?')})"
             + (f". {m['credit']}" if m.get("credit") else "") for m in ep.get("music", [])]

    # Anything on screen or spoken that is still marked "to verify"?
    for e in ep["events"]:
        txt = " ".join(str(e.get(k, "")) for k in ("text", "headline", "kicker", "title"))
        if "to verify" in txt.lower():
            warnings.append(f"On-screen/spoken text marked 'to verify' at {clock(e['t'])}: {txt.strip()[:60]}")
    if ep.get("draft_tag"):
        warnings.append("draft_tag is on: the video still says 'Draft preview'. Turn it off before uploading.")

    # ---- put it together ----
    parts = [hook, "", "Chapters"] + [f"{clock(m['t'])} {m['title']}" for m in marks]
    parts += ["", "Sources and licences"] + (sources or ["- (none found in the log)"])
    if music:
        parts += ["", "Music"] + music
    parts += ["", "About the channel", ABOUT]
    text = "\n".join(parts) + "\n"

    out = Path(args.out) if args.out else HERE / "out" / f"{ep_path.stem}_description.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(text)
    print(f"Saved {out}")
    if warnings:
        print("\nCHECK BEFORE UPLOADING:")
        for w in warnings:
            print("  -", w)


if __name__ == "__main__":
    main()
