#!/usr/bin/env python3
"""
Freeze Tail engine: detection against clips with a known freeze point, the
planning rules, and the writing step.
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

# clip -> (total duration, last motion, expected plan)
TRUTH = {
    "freeze_tail.mp4": (18.0, 12.0, "trim"),
    "blink_tail.mp4": (18.0, 12.0, "trim"),     # blinking icon must not count as motion
    "busy_tail.mp4": (18.0, 18.0, "copy"),      # a moving block in the tail IS motion
    "short_freeze.mp4": (17.5, 16.0, "copy"),   # 1.5s freeze is under the 2s threshold
    "long_freeze.mp4": (16.0, 4.0, "trim"),
    "all_static.mp4": (10.0, 0.0, "anomaly"),
    "no_freeze.mp4": (18.0, 18.0, "copy"),
}


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(("  ok   " if cond else "  FAIL ") + name + (f"  {extra}" if extra else ""),
          flush=True)


def base_cfg(**over):
    cfg = dict(fc.FZ_DEFAULTS)
    cfg.update(over)
    return cfg


def main():
    ffmpeg, ffprobe = fc.find_exe("ffmpeg"), fc.find_exe("ffprobe")
    check("ffmpeg/ffprobe discovered", bool(ffmpeg and ffprobe))
    check("numpy is available", fc._numpy() is not None)

    tmp = Path(tempfile.mkdtemp(prefix="fztest_"))
    clips = tmp / "clips"
    subprocess.run(["bash", str(Path(__file__).parent / "make_freeze_clips.sh"), str(clips)],
                   check=True, stdout=subprocess.DEVNULL)
    out_dir = tmp / "out"

    check("list_input finds 7 clips", len(fc.list_input(clips)) == 7,
          str([p.name for p in fc.list_input(clips)]))
    check("list_input skips ._ resource forks",
          not any(p.name.startswith("._") for p in fc.list_input(clips)))
    check("list_input accepts a single file",
          [p.name for p in fc.list_input(clips / "freeze_tail.mp4")] == ["freeze_tail.mp4"])
    check("list_input rejects a non-video", fc.list_input(clips / "._freeze_tail.mp4") == [])

    # ---- frame sampling --------------------------------------------------
    frames = list(fc.sample_gray(clips / "freeze_tail.mp4", 0.0, 2.0, 0.1, 160,
                                 fc.probe_dims(clips / "freeze_tail.mp4", ffprobe),
                                 ffmpeg, NOSTOP))
    check("sampling a 2s span at 10 Hz yields ~20 frames", 18 <= len(frames) <= 22,
          str(len(frames)))
    if frames:
        t, arr = frames[0]
        check("sampled frames are 160px wide grayscale", arr.shape[1] == 160
              and arr.dtype.name == "uint8", str(arr.shape))
        check("sample height keeps the 16:9 aspect", abs(arr.shape[0] - 90) <= 1,
              str(arr.shape))
        check("sample timestamps step by the interval",
              abs(frames[1][0] - frames[0][0] - 0.1) < 1e-6)

    # ---- detection -------------------------------------------------------
    cfg = base_cfg()
    plans = {}
    for name, (total, last_motion, expect) in TRUTH.items():
        p = fc.plan_for(clips / name, out_dir, cfg, ffmpeg, ffprobe, NOSTOP)
        plans[name] = p
        print(f"    {name:<20} plan={p['status']:<8} last_motion="
              f"{p['last_motion']:.2f}  cut={p['cut'] if p['cut'] is None else round(p['cut'], 2)}",
              flush=True)
    for name, (total, last_motion, expect) in TRUTH.items():
        p = plans[name]
        check(f"{name}: planned as {expect}", p["status"] == expect,
              f"got {p['status']}")
        check(f"{name}: duration read correctly", abs(p["total"] - total) < 0.4,
              f"{p['total']:.2f}")
        check(f"{name}: last motion within 0.25s of the truth",
              abs(p["last_motion"] - last_motion) <= 0.25,
              f"truth {last_motion}s, found {p['last_motion']:.2f}s")
    check("a trim cuts exactly at the last motion by default",
          abs(plans["freeze_tail.mp4"]["cut"] - plans["freeze_tail.mp4"]["last_motion"]) < 1e-9)
    check("removed time is duration minus cut",
          abs(plans["freeze_tail.mp4"]["removed"] - 6.0) <= 0.3,
          f"{plans['freeze_tail.mp4']['removed']:.2f}s")
    check("the anomaly carries an explanation", "static" in plans["all_static.mp4"]["msg"])

    # ---- the tolerance knobs actually do something -----------------------
    strict = fc.plan_for(clips / "blink_tail.mp4", out_dir,
                         base_cfg(unchanged_pct=99.95), ffmpeg, ffprobe, NOSTOP)
    check("raising 'screen unchanged %' makes the blinking icon count as motion",
          strict["status"] == "copy", f"got {strict['status']}")
    loose = fc.plan_for(clips / "busy_tail.mp4", out_dir,
                        base_cfg(unchanged_pct=70.0), ffmpeg, ffprobe, NOSTOP)
    check("lowering it lets a big moving block count as frozen",
          loose["status"] == "trim", f"got {loose['status']}")
    # the icon is red on a dark slate background -- about 30 levels of grey apart,
    # so a pixel tolerance above that hides it even at a strict unchanged %
    tolerant = fc.plan_for(clips / "blink_tail.mp4", out_dir,
                           base_cfg(unchanged_pct=99.95, pixel_tol=60),
                           ffmpeg, ffprobe, NOSTOP)
    check("raising pixel tolerance hides the icon again, even at 99.95%",
          tolerant["status"] == "trim" and abs(tolerant["last_motion"] - 12.0) <= 0.25,
          f"got {tolerant['status']} at {tolerant['last_motion']:.2f}")
    blind = fc.plan_for(clips / "freeze_tail.mp4", out_dir, base_cfg(pixel_tol=254),
                        ffmpeg, ffprobe, NOSTOP)
    check("an impossible pixel tolerance makes everything look static (anomaly, not a bad cut)",
          blind["status"] == "anomaly", f"got {blind['status']}")

    # ---- keep_tail / extra_trim ------------------------------------------
    kept = fc.plan_for(clips / "freeze_tail.mp4", out_dir, base_cfg(keep_tail=1.0),
                       ffmpeg, ffprobe, NOSTOP)
    check("keep tail adds to the cut point",
          abs(kept["cut"] - (plans["freeze_tail.mp4"]["cut"] + 1.0)) < 0.05,
          f"{kept['cut']:.2f}")
    extra = fc.plan_for(clips / "freeze_tail.mp4", out_dir, base_cfg(extra_trim=2.0),
                        ffmpeg, ffprobe, NOSTOP)
    check("extra end trim subtracts from the cut point",
          abs(extra["cut"] - (plans["freeze_tail.mp4"]["cut"] - 2.0)) < 0.05,
          f"{extra['cut']:.2f}")
    check("the cut never runs past the clip",
          fc.plan_for(clips / "freeze_tail.mp4", out_dir, base_cfg(keep_tail=999.0),
                      ffmpeg, ffprobe, NOSTOP)["cut"] <= 18.05)

    # ---- fast tail scan --------------------------------------------------
    fast = fc.plan_for(clips / "freeze_tail.mp4", out_dir,
                       base_cfg(fast_tail=True, tail_window=8.0), ffmpeg, ffprobe, NOSTOP)
    check("fast tail scan finds a freeze inside the window",
          fast["status"] == "trim" and abs(fast["last_motion"] - 12.0) <= 0.25
          and not fast["widened"], f"{fast['last_motion']:.2f} widened={fast['widened']}")
    wide = fc.plan_for(clips / "long_freeze.mp4", out_dir,
                       base_cfg(fast_tail=True, tail_window=8.0), ffmpeg, ffprobe, NOSTOP)
    check("a freeze longer than the window forces a full rescan", wide["widened"])
    check("the widened rescan still finds the right moment",
          abs(wide["last_motion"] - 4.0) <= 0.25, f"{wide['last_motion']:.2f}")

    # ---- output naming ---------------------------------------------------
    a = {"video": Path("x/clip.mov"), "out": out_dir / "clip.mp4"}
    b = {"video": Path("x/clip.mp4"), "out": out_dir / "clip.mp4"}
    c = {"video": Path("x/other.mp4"), "out": out_dir / "other.mp4"}
    fc.resolve_out_names([a, b, c])
    check("two sources mapping to one output name are separated",
          a["out"].name == "clip.mp4" and b["out"].name == "clip (2).mp4"
          and c["out"].name == "other.mp4",
          f"{a['out'].name} / {b['out'].name} / {c['out'].name}")

    # ---- writing ---------------------------------------------------------
    src = clips / "freeze_tail.mp4"
    exact = out_dir / "exact.mp4"
    fc.do_trim(src, 12.0, exact, ffmpeg, base_cfg(exact_cut=True))
    d = fc.probe_duration(exact, ffprobe)
    check("exact cut re-encodes to the requested length", abs(d - 12.0) < 0.35, f"{d:.2f}s")
    fast_out = out_dir / "fast.mp4"
    fc.do_trim(src, 12.0, fast_out, ffmpeg, base_cfg(exact_cut=False))
    d2 = fc.probe_duration(fast_out, ffprobe)
    check("stream-copy cut lands close to the requested length",
          abs(d2 - 12.0) < 1.2, f"{d2:.2f}s")

    def codec(p):
        return subprocess.run(
            [ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=codec_name", "-of", "default=nokey=1:noprint_wrappers=1", str(p)],
            capture_output=True, text=True).stdout.strip()
    check("both cut modes produce a playable H.264 file",
          codec(exact) == "h264" and codec(fast_out) == "h264")

    plan = fc.plan_for(clips / "freeze_tail.mp4", out_dir / "exec", cfg,
                       ffmpeg, ffprobe, NOSTOP)
    fc.execute_plan(plan, ffmpeg, cfg, NOSTOP)
    check("execute_plan trims and reports it", plan["result"] == "trimmed"
          and Path(plan["out"]).exists())
    copyplan = fc.plan_for(clips / "no_freeze.mp4", out_dir / "exec", cfg,
                           ffmpeg, ffprobe, NOSTOP)
    fc.execute_plan(copyplan, ffmpeg, cfg, NOSTOP)
    check("clips with no freeze are copied through", copyplan["result"] == "copied"
          and Path(copyplan["out"]).exists())
    skipplan = fc.plan_for(clips / "no_freeze.mp4", out_dir / "skip", cfg,
                           ffmpeg, ffprobe, NOSTOP)
    fc.execute_plan(skipplan, ffmpeg, base_cfg(copy_unchanged=False), NOSTOP)
    check("turning off 'copy unchanged' skips them instead",
          skipplan["result"] == "skipped" and not (out_dir / "skip").exists())
    stopped = fc.plan_for(clips / "freeze_tail.mp4", out_dir / "nope", cfg,
                          ffmpeg, ffprobe, NOSTOP)
    ev = threading.Event(); ev.set()
    fc.execute_plan(stopped, ffmpeg, cfg, ev)
    check("a cancelled plan writes nothing", stopped["result"] == "cancelled"
          and not (out_dir / "nope").exists())

    # ---- summary + report ------------------------------------------------
    allplans = [plans[n] for n in TRUTH]
    trims, copies, anomalies, errors, widened, removed = fc.freeze_summary(allplans)
    check("summary counts 3 trims, 3 copies, 1 anomaly",
          (len(trims), len(copies), len(anomalies), len(errors)) == (3, 3, 1, 0),
          f"{len(trims)}/{len(copies)}/{len(anomalies)}/{len(errors)}")
    rep = fc.write_freeze_report(out_dir, allplans)
    body = rep.read_text(encoding="utf-8")
    check("freeze report lists every clip", all(n in body for n in TRUTH))
    check("freeze report has a header row", body.startswith("run,file,plan,result"))

    # ---- shared settings file keeps both tabs separate -------------------
    s = fc.load_settings()
    check("settings hold a section per tab", set(s) == {"best_play", "freeze", "maps"})
    check("best play section is complete", set(s["best_play"]) == set(fc.BP_DEFAULTS))
    check("freeze section is complete", set(s["freeze"]) == set(fc.FZ_DEFAULTS))

    shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED: " + ", ".join(FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
