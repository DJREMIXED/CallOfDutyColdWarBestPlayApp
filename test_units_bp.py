#!/usr/bin/env python3
"""Headless checks for the non-GUI logic in best_play_trimmer.py."""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import fan_cave_studio as bp  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(("  ok   " if cond else "  FAIL ") + name + (f"  {extra}" if extra and not cond else ""))


def main():
    ffmpeg, ffprobe = bp.find_exe("ffmpeg"), bp.find_exe("ffprobe")
    check("ffmpeg/ffprobe discovered", bool(ffmpeg and ffprobe))

    # ---- text matching ---------------------------------------------------
    hits = [
        ("clean read", ["BEST PLAY"]),
        ("split across two observations", ["BEST", "PLAY"]),
        ("lowercase", ["Best Play"]),
        ("B misread as 8", ["8EST PLAY"]),
        ("Y misread as V", ["BEST PLAV"]),
        ("S misread as 5", ["BE5T PLAY"]),
        ("dropped letter", ["BEST PLA"]),
        ("surrounded by other HUD text", ["ROUND 12", "THE BEST PLAY OF THE MATCH", "X1"]),
        ("punctuation and spacing noise", ["- B E S T   P L A Y -"]),
    ]
    for label, strings in hits:
        check(f"matches: {label}", bp.looks_like_best_play(strings), str(strings))

    misses = [
        ("empty frame", []),
        ("blank strings", ["", "   "]),
        ("one letter off but wrong first letter", ["TEST PLAYER"]),
        ("different banner", ["PLAY OF THE GAME"]),
        ("unrelated word", ["BESTIARY"]),
        ("scoreboard noise", ["SCORE 4500", "ELIMS 21", "K/D 2.10"]),
        ("just the word play", ["PLAY"]),
        ("just the word best", ["BEST"]),
    ]
    for label, strings in misses:
        check(f"rejects: {label}", not bp.looks_like_best_play(strings), str(strings))

    # ---- run detection ---------------------------------------------------
    check("first_run_start needs two in a row",
          bp.first_run_start(None, [False, True, False, True, True, False], False) == 3)
    check("first_run_start ignores a lone mid-scan blip",
          bp.first_run_start(None, [False, True, False, False], False) is None)
    check("first_run_start accepts a lone hit on the final frame",
          bp.first_run_start(None, [False, False, True], True) == 2)
    check("first_run_start returns None on a clean scan",
          bp.first_run_start(None, [False] * 10, True) is None)

    # ---- crop filter -----------------------------------------------------
    check("full frame skips the crop", "crop" not in bp.crop_filter("Full frame"))
    check("center band crops and scales",
          "crop=" in bp.crop_filter(bp.DEFAULT_REGION)
          and f"scale={bp.SCAN_W}" in bp.crop_filter(bp.DEFAULT_REGION))
    check("unknown region falls back to the default",
          bp.crop_filter("nonsense") == bp.crop_filter(bp.DEFAULT_REGION))

    # ---- settings round trip --------------------------------------------
    check("settings load with a section per tab",
          set(bp.load_settings()) == {"best_play", "freeze", "maps"})
    check("best play section loads with every default key",
          set(bp.load_settings()["best_play"]) == set(bp.BP_DEFAULTS))

    # ---- file handling ---------------------------------------------------
    tmp = Path(tempfile.mkdtemp(prefix="bptest_"))
    clips = tmp / "clips"
    subprocess.run(["bash", str(Path(__file__).parent / "make_ps5_clips.sh"), str(clips)],
                   check=True, stdout=subprocess.DEVNULL)
    vids = bp.list_videos(clips)
    check("list_videos finds 5 clips", len(vids) == 5, str([v.name for v in vids]))
    check("list_videos skips ._ resource forks",
          not any(v.name.startswith("._") for v in vids))

    src = clips / "match_alpha.mp4"
    dur = bp.probe_duration(src, ffprobe)
    check("probe_duration reads 30s", abs(dur - 30.0) < 0.5, f"{dur:.2f}")
    check("probe_duration survives a non-video", bp.probe_duration(clips / "nope.mp4", ffprobe) == 0.0)

    # ---- trimming --------------------------------------------------------
    out = tmp / "out" / "trimmed.mp4"
    bp.trim_from(src, 10.0, out, ffmpeg)
    tdur = bp.probe_duration(out, ffprobe)
    check("trim from 10s leaves ~20s", abs(tdur - 20.0) < 1.2, f"{tdur:.2f}")
    check("trim never starts LATER than asked", tdur >= 19.9, f"{tdur:.2f}")

    def codec(p):
        return subprocess.run(
            [ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=codec_name", "-of", "default=nokey=1:noprint_wrappers=1", str(p)],
            capture_output=True, text=True).stdout.strip()
    check("trim is a stream copy (codec unchanged)", codec(out) == codec(src),
          f"{codec(src)} -> {codec(out)}")
    check("trim start of 0 keeps the whole clip",
          abs(bp.probe_duration(bp.trim_from(src, 0.0, tmp / "out" / "whole.mp4", ffmpeg),
                                ffprobe) - 30.0) < 0.5)

    # ---- moving ----------------------------------------------------------
    dest_dir = tmp / "moved"
    (dest_dir).mkdir()
    (dest_dir / "match_early.mp4").write_bytes(b"squatter")
    moved = bp.move_into(clips / "match_early.mp4", dest_dir)
    check("move_into does not overwrite a same-named file",
          moved.name != "match_early.mp4"
          and (dest_dir / "match_early.mp4").read_bytes() == b"squatter", moved.name)

    # ---- report ----------------------------------------------------------
    rows = [{"file": "a.mp4", "status": "hit", "banner": 20.0, "start": 15.0,
             "duration": 30.0, "output": "a_bestplay.mp4", "note": ""},
            {"file": "b.mp4", "status": "miss", "banner": None, "start": None,
             "duration": 20.0, "output": "", "note": "scanned in 2.0s"}]
    rep = bp.write_report(tmp, rows)
    text = rep.read_text(encoding="utf-8")
    check("report has a header and both rows",
          text.count("\n") == 3 and "banner_at_s" in text and "a_bestplay.mp4" in text)
    bp.write_report(tmp, rows)
    check("second run appends instead of clobbering",
          rep.read_text(encoding="utf-8").count("\n") == 5)

    shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED: " + ", ".join(FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
