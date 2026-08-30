#!/usr/bin/env python3
"""
End-to-end pipeline test: real OCR over real video, then real trims.

Clips carry a "BEST PLAY" banner burned in at known timestamps, so detection can
be checked against ground truth rather than against itself.
"""
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import fan_cave_studio as bp  # noqa: E402

PASS, FAIL = [], []
TRUTH = {                     # clip -> (source duration, banner appears at)
    "match_alpha.mp4": (30.0, 20.0),
    "match_early.mp4": (30.0, 5.0),
    "no_banner.mp4": (20.0, None),
    "decoy_text.mp4": (20.0, None),
    "busy_bars.mp4": (15.0, None),
}
LEAD_IN = 5.0


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(("  ok   " if cond else "  FAIL ") + name + (f"  {extra}" if extra else ""),
          flush=True)


def main():
    ffmpeg, ffprobe = bp.find_exe("ffmpeg"), bp.find_exe("ffprobe")
    ocr, note = bp.pick_ocr()
    if ocr is None:
        print("no OCR engine available:", note)
        return 2
    print(f"OCR engine: {ocr.name}\n")

    tmp = Path(tempfile.mkdtemp(prefix="bppipe_"))
    clips = tmp / "PS5 Clips"
    subprocess.run(["bash", str(Path(__file__).parent / "make_ps5_clips.sh"), str(clips)],
                   check=True, stdout=subprocess.DEVNULL)

    cfg = {"lead_in": LEAD_IN, "scan_fps": 2.0, "region": bp.DEFAULT_REGION, "threads": 6}
    work = Path(tempfile.mkdtemp(prefix="bpwork_"))
    cancel = threading.Event()
    results = {}
    t_start = time.time()
    for v in bp.list_videos(clips):
        r = bp.process_one(v, clips, cfg, ocr, work, lambda a, b: None,
                           cancel, ffmpeg, ffprobe)
        results[v.name] = r
        print(f"    {v.name:<20} {r['status']:<6} banner={bp.hhmmss(r['banner'])} "
              f"start={bp.hhmmss(r['start'])}  {r['note']}", flush=True)
    elapsed = time.time() - t_start
    print(f"    ({elapsed:.1f}s of scanning for {sum(d for d, _ in TRUTH.values()):.0f}s "
          f"of footage)\n", flush=True)

    # ---- detection accuracy ---------------------------------------------
    for name, (src_dur, truth) in TRUTH.items():
        r = results.get(name)
        check(f"{name}: produced a result", r is not None)
        if r is None:
            continue
        if truth is None:
            check(f"{name}: correctly reports no BEST PLAY", r["status"] == "miss",
                  f"got {r['status']} banner={r['banner']}")
        else:
            check(f"{name}: found BEST PLAY", r["status"] == "hit", str(r))
            if r["banner"] is not None:
                off = r["banner"] - truth
                check(f"{name}: banner located within 0.4s of the truth",
                      abs(off) <= 0.4, f"truth {truth}s, found {r['banner']:.2f}s "
                                       f"({off:+.2f}s)")
                check(f"{name}: never reports the banner EARLY",
                      off >= -0.15, f"{off:+.2f}s")
                check(f"{name}: trim start is banner minus the lead-in",
                      abs(r["start"] - max(0.0, truth - LEAD_IN)) <= 0.4,
                      f"{r['start']:.2f}")

    # ---- what landed where ----------------------------------------------
    hits_dir, miss_dir, done_dir = (clips / bp.OUT_HITS, clips / bp.OUT_MISSES,
                                    clips / bp.OUT_DONE)
    hit_files = sorted(p.name for p in hits_dir.glob("*.mp4")) if hits_dir.exists() else []
    miss_files = sorted(p.name for p in miss_dir.glob("*.mp4")) if miss_dir.exists() else []
    done_files = sorted(p.name for p in done_dir.glob("*.mp4")) if done_dir.exists() else []

    check("both banner clips were trimmed into BEST_PLAYS/",
          hit_files == ["match_alpha_bestplay.mp4", "match_early_bestplay.mp4"],
          str(hit_files))
    check("all three non-banner clips moved to NO_BEST_PLAY/",
          miss_files == ["busy_bars.mp4", "decoy_text.mp4", "no_banner.mp4"],
          str(miss_files))
    check("originals of trimmed clips moved to _PROCESSED/",
          done_files == ["match_alpha.mp4", "match_early.mp4"], str(done_files))
    check("the source folder has no loose clips left",
          bp.list_videos(clips) == [], str([p.name for p in bp.list_videos(clips)]))

    # ---- the trims themselves -------------------------------------------
    a = bp.probe_duration(hits_dir / "match_alpha_bestplay.mp4", ffprobe)
    check("match_alpha trimmed to ~15s (30s source, cut at 15s)",
          abs(a - 15.0) <= 1.2, f"{a:.2f}s")
    e = bp.probe_duration(hits_dir / "match_early_bestplay.mp4", ffprobe)
    check("match_early keeps the full 30s (banner at 5s, 5s lead-in -> cut at 0)",
          abs(e - 30.0) <= 1.2, f"{e:.2f}s")

    def codec(p):
        return subprocess.run(
            [ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=codec_name", "-of", "default=nokey=1:noprint_wrappers=1", str(p)],
            capture_output=True, text=True).stdout.strip()
    check("trimmed output is still H.264 (stream copy, no re-encode)",
          codec(hits_dir / "match_alpha_bestplay.mp4") == "h264")

    # the banner must survive into the trimmed clip, LEAD_IN seconds in
    probe_png = work / "verify.jpg"
    subprocess.run([ffmpeg, "-hide_banner", "-v", "error", "-y", "-ss", f"{LEAD_IN + 0.5:.2f}",
                    "-i", str(hits_dir / "match_alpha_bestplay.mp4"), "-frames:v", "1",
                    "-vf", bp.crop_filter(bp.DEFAULT_REGION), "-q:v", "3", str(probe_png)],
                   check=True)
    check("the banner is still on screen just after the lead-in in the trimmed clip",
          bp.looks_like_best_play(ocr.recognize(probe_png)))

    # ---- report ----------------------------------------------------------
    rep = bp.write_report(clips, list(results.values()))
    check("a CSV report was written", rep.exists() and rep.parent == hits_dir, str(rep))
    if rep.exists():
        body = rep.read_text(encoding="utf-8")
        check("report lists every clip", all(n in body for n in TRUTH), "")

    # ---- cancelling stops the work --------------------------------------
    clips2 = tmp / "cancel"
    subprocess.run(["bash", str(Path(__file__).parent / "make_ps5_clips.sh"), str(clips2)],
                   check=True, stdout=subprocess.DEVNULL)
    stop = threading.Event(); stop.set()
    t0 = time.time()
    r = bp.process_one(clips2 / "match_alpha.mp4", clips2, cfg, ocr, work,
                       lambda a, b: None, stop, ffmpeg, ffprobe)
    check("a cancelled clip reports cancelled and is left alone",
          r["status"] == "cancelled" and (clips2 / "match_alpha.mp4").exists())
    check("cancelling returns quickly", time.time() - t0 < 10.0, f"{time.time() - t0:.1f}s")

    shutil.rmtree(tmp, ignore_errors=True)
    shutil.rmtree(work, ignore_errors=True)
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED: " + ", ".join(FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
