#!/usr/bin/env python3
"""
Proves the rewritten freeze scan agrees with the original OpenCV one.

The merged app feeds the same "% of pixels that moved by more than the
tolerance" maths from ffmpeg (VideoToolbox on Apple Silicon) instead of cv2, so
the original's tuned settings must keep meaning the same thing. This runs both
implementations over the same clips with the same settings and compares the
moment each one calls "last motion".
"""
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import fan_cave_studio as fc            # noqa: E402
try:
    # copy the original freeze_trimmer.py in here as orig_freeze_trimmer.py to run this
    import orig_freeze_trimmer as orig   # noqa: E402
except ImportError:
    print("skipped: put the original freeze_trimmer.py in this folder as "
          "orig_freeze_trimmer.py to run the comparison")
    raise SystemExit(0)
except SystemExit:
    print("skipped: the original needs opencv-python installed "
          "(pip install opencv-python-headless)")
    raise SystemExit(0)

PASS, FAIL = [], []
NOSTOP = threading.Event()

CASES = [
    ("defaults", {}),
    ("strict unchanged %", {"unchanged_pct": 99.95}),
    ("high pixel tolerance", {"unchanged_pct": 99.95, "pixel_tol": 60}),
    ("coarser sampling", {"sample_interval": 0.25}),
    ("fast tail scan", {"fast_tail": True, "tail_window": 8.0}),
    ("narrow sample width", {"sample_width": 96}),
]


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(("  ok   " if cond else "  FAIL ") + name + (f"  {extra}" if extra else ""),
          flush=True)


def main():
    ffmpeg, ffprobe = fc.find_exe("ffmpeg"), fc.find_exe("ffprobe")
    tmp = Path(tempfile.mkdtemp(prefix="fzeq_"))
    clips = tmp / "clips"
    subprocess.run(["bash", str(HERE / "make_freeze_clips.sh"), str(clips)],
                   check=True, stdout=subprocess.DEVNULL)
    videos = fc.list_input(clips)

    for label, over in CASES:
        cfg = dict(fc.FZ_DEFAULTS)
        cfg.update(over)
        s = SimpleNamespace(**{k: v for k, v in cfg.items()
                               if k in orig.DEFAULTS or k in ("fast_tail", "tail_window")})
        worst = 0.0
        detail = ""
        agree = True
        for v in videos:
            old_t, old_total, _fps, old_wide = orig.detect_last_motion(v, s, ffprobe)
            new_t, new_total, new_wide = fc.detect_last_motion(v, cfg, ffmpeg, ffprobe, NOSTOP)
            gap = abs(old_t - new_t)
            if gap > worst:
                worst, detail = gap, f"{v.name}: cv2 {old_t:.2f}s vs ffmpeg {new_t:.2f}s"
            if old_wide != new_wide:
                agree = False
                detail = f"{v.name}: widened {old_wide} vs {new_wide}"
            if abs(old_total - new_total) > 0.05:
                agree = False
                detail = f"{v.name}: duration {old_total:.2f} vs {new_total:.2f}"
        tol = max(0.12, float(cfg["sample_interval"]) * 1.5)
        check(f"{label}: same last-motion moment (within {tol:.2f}s)",
              agree and worst <= tol, detail or f"max gap {worst:.3f}s")
        if agree and worst <= tol:
            print(f"         max gap across {len(videos)} clips: {worst:.3f}s", flush=True)

    # the classification each implementation would produce must match exactly
    for label, over in CASES[:3]:
        cfg = dict(fc.FZ_DEFAULTS)
        cfg.update(over)
        s = SimpleNamespace(**{k: v for k, v in cfg.items()
                               if k in orig.DEFAULTS or k in ("fast_tail", "tail_window")})
        same = True
        detail = ""
        for v in videos:
            old = orig.plan_for(v, tmp / "o", s, ffprobe)["status"]
            new = fc.plan_for(v, tmp / "n", cfg, ffmpeg, ffprobe, NOSTOP)["status"]
            if old != new:
                same = False
                detail = f"{v.name}: {old} vs {new}"
        check(f"{label}: identical trim/copy/anomaly decisions", same, detail)

    shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED: " + ", ".join(FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
