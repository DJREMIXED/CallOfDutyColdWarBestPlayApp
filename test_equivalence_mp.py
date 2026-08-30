#!/usr/bin/env python3
"""
Proves the rewritten Map Sorter keeps the original's judgement.

The scoreboard reader moved from OpenCV + pytesseract to ffmpeg + Apple Vision,
but the decision layer — which map a piece of scoreboard text is naming, and
when the review snapshots are taken — must behave exactly as before. This runs
both implementations over the same inputs and compares every answer.
"""
import itertools
import random
import string
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import fan_cave_studio as fc          # noqa: E402
try:
    # copy the original map_sorter.py in here as orig_map_sorter.py to run this
    import orig_map_sorter as orig    # noqa: E402
except ImportError:
    print("skipped: put the original map_sorter.py in this folder as "
          "orig_map_sorter.py to run the comparison")
    raise SystemExit(0)
except SystemExit:
    print("skipped: the original needs opencv-python and pytesseract installed")
    raise SystemExit(0)

PASS, FAIL = [], []
MAPS = list(orig.MAPS)


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(("  ok   " if cond else "  FAIL ") + name + (f"  {extra}" if extra else ""),
          flush=True)


def sample_texts():
    """Realistic scoreboard lines, near-misses, and pure noise."""
    modes = ["TEAM DEATHMATCH", "DOMINATION", "KILL CONFIRMED", "HARDPOINT", "TDM", ""]
    texts = []
    for mode, m in itertools.product(modes, MAPS + ["Nuketown", "Raid", ""]):
        texts.append(f"{mode} {m}".strip())
        texts.append(f"{mode} {m}".strip().lower())
        texts.append(f"|| {mode}  {m}  12:00".strip())
    # single-character corruptions, the commonest OCR failure
    rng = random.Random(20260830)
    for m in MAPS:
        for _ in range(6):
            s = list(f"TEAM DEATHMATCH {m}".upper())
            i = rng.randrange(len(s))
            s[i] = rng.choice(string.ascii_uppercase)
            texts.append("".join(s))
        texts.append(f"TEAM DEATHMATCH {m}"[:-2])          # truncated by the crop
        texts.append(f"TEAM DEATHMATCH {m.replace('-', '')}")
    # noise
    for _ in range(200):
        n = rng.randrange(0, 40)
        texts.append("".join(rng.choice(string.ascii_letters + "  .,|-") for _ in range(n)))
    return texts


def main():
    texts = sample_texts()
    diffs = []
    for t in texts:
        if orig.match_map(t) != fc.match_map(t, MAPS):
            diffs.append((t, orig.match_map(t), fc.match_map(t, MAPS)))
    check(f"same map decision on all {len(texts)} scoreboard strings", not diffs,
          "; ".join(f"{t!r}: {a} vs {b}" for t, a, b in diffs[:4]))

    # the original's snapshot timing is still available as "First seconds" mode
    time_diffs = []
    for dur in (0.0, 0.5, 2.0, 5.0, 12.0, 13.5, 30.0, 600.0):
        for n in (1, 3, 5, 8):
            for interval in (1.0, 3.0, 5.0):
                a = orig.snapshot_times(dur, n, interval)
                b = fc.snapshot_times(dur, n, fc.SPREAD_MODES[1], interval)
                if n == 1:
                    continue        # the new mid-clip single frame is a deliberate change
                if [round(x, 6) for x in a] != [round(x, 6) for x in b]:
                    time_diffs.append((dur, n, interval, a, b))
    check("'First seconds' mode reproduces the original snapshot times exactly",
          not time_diffs, str(time_diffs[:2]))

    # and the default mode really does spread further across the clip
    spread = fc.snapshot_times(60.0, 5, fc.SPREAD_MODES[0], 3.0)
    early = orig.snapshot_times(60.0, 5, 3.0)
    check("the new default samples a wider slice of the clip",
          max(spread) > max(early) and len(spread) == len(early),
          f"{spread} vs {early}")

    check("the map list parses to the original's built-in list",
          fc.parse_map_list(fc.MAP_DEFAULTS["maps"]) == MAPS,
          str(fc.parse_map_list(fc.MAP_DEFAULTS["maps"])))
    check("the original's snapshot filenames are still produced",
          fc.snap_prefix(Path("x/My Clip 01.mp4")) == orig.snap_prefix(Path("x/My Clip 01.mp4")))
    check("the snapshot cache folder prefix is unchanged so old caches are reused",
          fc.SNAP_PREFIX == orig.SNAP_PREFIX)

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED: " + ", ".join(FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
