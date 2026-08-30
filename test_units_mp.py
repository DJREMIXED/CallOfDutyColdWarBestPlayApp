#!/usr/bin/env python3
"""
Map Sorter engine: the map list, scoreboard matching, snapshot timing, the
scoreboard read against clips with a known map burned into the header, and the
file moves.
"""
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import fan_cave_studio as fc  # noqa: E402

PASS, FAIL = [], []
NOSTOP = threading.Event()
MAPS = fc.parse_map_list(fc.MAP_DEFAULTS["maps"])

# clip -> the map its scoreboard names, as the default region sees it
TRUTH = {
    "match_amsterdam.mp4": "Amsterdam",
    "match_ubahn.mp4": "U-Bahn",
    "match_kgb.mp4": "KGB",
    "no_scoreboard.mp4": None,
    "header_low.mp4": None,      # header is drawn outside the default region
}


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(("  ok   " if cond else "  FAIL ") + name + (f"  {extra}" if extra else ""),
          flush=True)


def cfg(**over):
    c = dict(fc.MAP_DEFAULTS)
    c.update(over)
    c["map_list"] = c.pop("map_list", MAPS)
    return c


def main():
    ffmpeg, ffprobe = fc.find_exe("ffmpeg"), fc.find_exe("ffprobe")
    ocr, note = fc.pick_ocr()
    check("ffmpeg/ffprobe discovered", bool(ffmpeg and ffprobe))
    if ocr is None:
        print("no OCR engine available:", note)
        return 2
    print(f"OCR engine: {ocr.name}\n")

    # ---- the map list ----------------------------------------------------
    check("map list splits on commas", fc.parse_map_list("A, B,C") == ["A", "B", "C"])
    check("map list trims and collapses spaces",
          fc.parse_map_list("  Game   Show ,  KGB ") == ["Game Show", "KGB"])
    check("map list drops duplicates case-insensitively",
          fc.parse_map_list("KGB, kgb, Kgb") == ["KGB"])
    check("map list drops empties", fc.parse_map_list("A,,  ,B") == ["A", "B"])
    check("map list splits on newlines too", fc.parse_map_list("A\nB") == ["A", "B"])
    check("map list refuses to shadow the Other bucket",
          fc.parse_map_list("Amsterdam, Other, other") == ["Amsterdam"])
    check("map list makes names safe as folder names",
          fc.parse_map_list("Nuke/Town, A:B") == ["Nuke-Town", "A-B"])
    check("an empty map list is empty", fc.parse_map_list("  ,  ") == [])

    # ---- matching --------------------------------------------------------
    hits = [
        ("plain header", "TEAM DEATHMATCH AMSTERDAM", "Amsterdam"),
        ("lowercase", "team deathmatch amsterdam", "Amsterdam"),
        ("hyphenated name", "KILL CONFIRMED U-BAHN", "U-Bahn"),
        ("name without the hyphen", "KILL CONFIRMED UBAHN", "U-Bahn"),
        ("short name, exact", "DOMINATION KGB", "KGB"),
        ("two-word name", "HARDPOINT GAME SHOW", "Game Show"),
        ("one letter misread", "TEAM DEATHMATCH AMSTEROAM", "Amsterdam"),
        ("noise around the name", "|| TDM  SHOWROOM  12:00", "Showroom"),
    ]
    for label, text, expect in hits:
        check(f"matches: {label}", fc.match_map(text, MAPS) == expect,
              f"{text!r} -> {fc.match_map(text, MAPS)}")
    misses = [
        ("empty", ""),
        ("too short", "KG"),
        ("unrelated words", "ROUND 3 SCORE 45 ELIMS 12"),
        ("a map not in the list", "HARDPOINT NUKETOWN"),
        ("OCR garbage", "a le ees . el ce ae a te a gis ree"),
    ]
    for label, text in misses:
        check(f"rejects: {label}", fc.match_map(text, MAPS) is None,
              f"{text!r} -> {fc.match_map(text, MAPS)}")
    check("short names are never fuzzy-matched", fc.match_map("KGA GAME", ["KGB"]) is None)
    check("matching an empty map list is safe", fc.match_map("AMSTERDAM", []) is None)

    # ---- regions ---------------------------------------------------------
    check("full frame skips the crop", "crop" not in fc.roi_filter("Full frame"))
    check("the header region crops and scales", "crop=" in fc.roi_filter("Scoreboard header"))
    check("an unknown region falls back to the default",
          fc.roi_filter("nonsense") == fc.roi_filter(fc.DEFAULT_MAP_REGION))
    check("the original narrow region is still selectable",
          fc.MAP_REGIONS["Scoreboard header (narrow)"] == (0.06, 0.10, 0.45, 0.18))

    # ---- snapshot timing -------------------------------------------------
    spread = fc.snapshot_times(100.0, 5, fc.SPREAD_MODES[0], 3.0)
    check("spread mode covers the whole clip",
          spread == [10.0, 30.0, 50.0, 70.0, 90.0], str(spread))
    early = fc.snapshot_times(100.0, 5, fc.SPREAD_MODES[1], 3.0)
    check("first-seconds mode keeps the original 3s spacing",
          early == [0.0, 3.0, 6.0, 9.0, 12.0], str(early))
    tiny = fc.snapshot_times(2.0, 5, fc.SPREAD_MODES[1], 3.0)
    check("a clip shorter than the spacing still gets 5 distinct times",
          len(tiny) == 5 and tiny == sorted(tiny) and tiny[-1] <= 2.0, str(tiny))
    check("spread mode never lands past the end",
          all(0 <= t <= 4.0 for t in fc.snapshot_times(4.0, 5, fc.SPREAD_MODES[0], 3.0)))
    check("a zero-length clip does not crash",
          fc.snapshot_times(0.0, 5, fc.SPREAD_MODES[0], 3.0) == [0.0] * 5)
    check("one snapshot lands mid-clip",
          fc.snapshot_times(10.0, 1, fc.SPREAD_MODES[0], 3.0) == [5.0])

    # ---- clips -----------------------------------------------------------
    tmp = Path(tempfile.mkdtemp(prefix="mptest_"))
    clips = tmp / "import"
    subprocess.run(["bash", str(Path(__file__).parent / "make_map_clips.sh"), str(clips)],
                   check=True, stdout=subprocess.DEVNULL)
    vids = fc.list_videos(clips)
    check("list_videos finds 5 clips", len(vids) == 5, str([v.name for v in vids]))
    check("list_videos skips ._ resource forks",
          not any(v.name.startswith("._") for v in vids))

    # ---- snapshot cache --------------------------------------------------
    snap_dir = fc.find_or_make_snap_dir(clips)
    check("a snapshot cache folder is created", snap_dir.is_dir()
          and snap_dir.name.startswith(fc.SNAP_PREFIX))
    check("the same cache folder is reused", fc.find_or_make_snap_dir(clips) == snap_dir)
    (clips / (fc.SNAP_PREFIX + "decoy_file")).write_text("not a folder")
    check("a file that looks like a cache folder is ignored",
          fc.find_or_make_snap_dir(clips) == snap_dir)

    conf = cfg(snaps=5, snap_width=200)
    made = fc.extract_snapshots(clips / "no_scoreboard.mp4", snap_dir, conf, ffmpeg, ffprobe)
    check("five review snapshots are made", len(made) == 5, str(len(made)))
    check("snapshots use the configured width",
          subprocess.run([ffprobe, "-v", "error", "-select_streams", "v:0",
                          "-show_entries", "stream=width", "-of",
                          "default=nokey=1:noprint_wrappers=1", str(made[0])],
                         capture_output=True, text=True).stdout.strip() == "200")
    stamp = made[0].stat().st_mtime_ns
    again = fc.extract_snapshots(clips / "no_scoreboard.mp4", snap_dir, conf, ffmpeg, ffprobe)
    check("a second pass reuses the cached snapshots",
          len(again) == 5 and again[0].stat().st_mtime_ns == stamp)
    check("two clips get different snapshot names",
          fc.snap_prefix(Path("a/clip.mp4")) != fc.snap_prefix(Path("a/clip.mov")))

    # ---- the scoreboard read ---------------------------------------------
    work = Path(tempfile.mkdtemp(prefix="mpwork_"))
    for name, expect in TRUTH.items():
        dur = fc.probe_duration(clips / name, ffprobe)
        got = fc.detect_map(clips / name, dur, cfg(), ocr, work / name, NOSTOP, ffmpeg, 4)
        check(f"{name}: scoreboard read -> {expect}", got == expect, f"got {got}")

    low = clips / "header_low.mp4"
    got = fc.detect_map(low, fc.probe_duration(low, ffprobe),
                        cfg(region="Full frame"), ocr, work / "low", NOSTOP, ffmpeg, 4)
    check("widening the region finds a header the default misses",
          got == "Gluboko", f"got {got}")
    got = fc.detect_map(clips / "match_kgb.mp4", 12.0, cfg(min_hits=99), ocr,
                        work / "hits", NOSTOP, ffmpeg, 4)
    check("demanding more confirmations than exist reports nothing", got is None, str(got))
    stop = threading.Event(); stop.set()
    check("a cancelled read returns nothing",
          fc.detect_map(clips / "match_kgb.mp4", 12.0, cfg(), ocr, work / "c",
                        stop, ffmpeg, 4) is None)
    check("an empty map list matches nothing",
          fc.detect_map(clips / "match_kgb.mp4", 12.0, cfg(map_list=[]), ocr,
                        work / "e", NOSTOP, ffmpeg, 4) is None)

    # ---- moving ----------------------------------------------------------
    dest = fc.move_to_map(clips / "match_kgb.mp4", clips, "KGB")
    check("a clip moves into its map folder",
          dest == clips / "KGB" / "match_kgb.mp4" and dest.exists()
          and not (clips / "match_kgb.mp4").exists(), str(dest))
    (clips / "match_kgb.mp4").write_bytes(b"a different clip, same name")
    dest2 = fc.move_to_map(clips / "match_kgb.mp4", clips, "KGB")
    check("a same-named clip never overwrites the one already filed",
          dest2 != dest and dest2.exists() and dest.stat().st_size > 100, str(dest2))
    fc.move_to_map(clips / "match_ubahn.mp4", clips, "Other")
    check("the Other bucket works like any map", (clips / "Other" / "match_ubahn.mp4").exists())

    # ---- report ----------------------------------------------------------
    rows = [{"file": "a.mp4", "map": "KGB", "how": "auto", "dest": "KGB/a.mp4"},
            {"file": "b.mp4", "map": "Other", "how": "manual", "dest": "Other/b.mp4"}]
    rep = fc.write_map_report(clips, rows)
    body = rep.read_text(encoding="utf-8")
    check("the report has a header and both rows",
          body.startswith("run,file,map,how,moved_to") and body.count("\n") == 3, repr(body[:80]))
    fc.write_map_report(clips, rows)
    check("a second run appends", rep.read_text(encoding="utf-8").count("\n") == 5)

    # ---- purge -----------------------------------------------------------
    fc.purge_snaps(clips, lambda m: None)
    check("purge removes the snapshot cache folders",
          not [d for d in clips.glob(fc.SNAP_PREFIX + "*") if d.is_dir()])
    check("purge leaves ordinary files alone",
          (clips / (fc.SNAP_PREFIX + "decoy_file")).exists())

    # ---- settings --------------------------------------------------------
    s = fc.load_settings()
    check("settings hold a section per tab",
          set(s) == {"best_play", "freeze", "maps"}, str(set(s)))
    check("the maps section is complete", set(s["maps"]) == set(fc.MAP_DEFAULTS))

    shutil.rmtree(tmp, ignore_errors=True)
    shutil.rmtree(work, ignore_errors=True)
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED: " + ", ".join(FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
