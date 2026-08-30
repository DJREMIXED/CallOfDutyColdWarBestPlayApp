#!/usr/bin/env python3
"""
fan_cave_studio.py  (macOS / Apple Silicon)
===========================================
Fan Cave Studio PRO — Clip Toolkit

Three independent tools in one window, one per tab. Each has its own folders,
its own settings and its own Start button, and any of them can run on its own.

  BEST PLAY tab
    Watches PlayStation 5 captures for the on-screen words "BEST PLAY", then
    cuts everything before that moment away.
      * frames are sampled and read with Apple's Vision text recogniser
        (Neural Engine on an M1/M2), decoding through VideoToolbox;
      * the first moment the banner appears is located, then refined to ~1/12 s;
      * the clip is cut from (banner time − lead-in) to the end with a stream
        copy — no re-encode, no quality loss;
      * trimmed clips land in  BEST_PLAYS/ , originals move to  _PROCESSED/ ,
        and clips with no banner move to  NO_BEST_PLAY/  untouched.

  FREEZE TAIL tab
    Trims the frozen tail off highlight clips. When the screen stops changing
    for a set amount of time at the end of a clip, the clip is cut back to the
    exact moment motion stopped, so a run of clips plays with no dead pauses.
      * frames are sampled a few times a second, shrunk to grayscale through
        VideoToolbox, and compared with the previous sample;
      * a sample counts as "unchanged" when at least X% of the screen is within
        a small brightness tolerance of the one before it — so a blinking mic
        icon or a small corner animation does NOT count as motion;
      * only a TRAILING freeze is trimmed; a freeze in the middle is left alone;
      * output goes to a separate folder. Originals are never modified.

  MAP SORTER tab
    Files clips into a folder per map, in two stages.
      * STAGE 1 (automatic): Cold War prints the map on the scoreboard header,
        e.g. "TEAM DEATHMATCH AMSTERDAM". Any clip where you opened the
        scoreboard is read and filed straight into that map's folder.
      * STAGE 2 (you decide): whatever is left gets a strip of snapshots. Glance
        at them and press a number key for the map, or click its button.
      * keys: 1-9 pick a map, 0 = Other, S = skip, Z = undo the last move.
      * every clip is MOVED into  <folder>/<MapName>/ , so quitting and
        reopening carries on where you left off.
      * the map list is editable and remembered — it is not baked into the app.

REQUIREMENTS
  brew install ffmpeg python-tk
  pip3 install numpy pyobjc-framework-Vision pyobjc-framework-Quartz
     (Vision is the fast text reader for the Best Play and Map Sorter tabs.
      Without PyObjC they fall back to `brew install tesseract`, which is
      slower. numpy is required by the Freeze Tail tab.)
"""

import csv
import difflib
import hashlib
import json
import os
import platform
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

APP_NAME = "Fan Cave Studio PRO — Clip Toolkit"
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm", ".mts", ".m2ts",
              ".flv", ".wmv"}
IS_MAC = platform.system() == "Darwin"

# ---- Best Play tab --------------------------------------------------------
OUT_HITS = "BEST_PLAYS"
OUT_MISSES = "NO_BEST_PLAY"
OUT_DONE = "_PROCESSED"
REPORT_NAME = "_bestplay_report.csv"

TARGET = "BESTPLAY"
FUZZ = 0.86                 # how close an OCR read has to be to count
MIN_RUN = 2                 # consecutive sampled frames needed (kills false hits)
WINDOW_S = 60.0             # seconds of video scanned per batch
REFINE_FPS = 12.0           # second pass, to pin the exact moment the banner appears
SCAN_W = 1280               # frames are downscaled to this width before OCR

REGIONS = {
    "Center band (fastest)": (0.0, 0.26, 1.0, 0.44),   # x, y, w, h as fractions
    "Upper half": (0.0, 0.0, 1.0, 0.55),
    "Lower half": (0.0, 0.45, 1.0, 0.55),
    "Full frame": (0.0, 0.0, 1.0, 1.0),
}
DEFAULT_REGION = "Center band (fastest)"

BP_DEFAULTS = {
    "lead_in": 5.0,
    "scan_fps": 2.0,
    "region": DEFAULT_REGION,
    "threads": 0,            # 0 = auto
    "folder": "",
}

# ---- Freeze Tail tab ------------------------------------------------------
FZ_DEFAULTS = {
    "freeze_duration": 2.0,   # seconds the tail must stay still to count as a freeze
    "unchanged_pct": 98.0,    # % of screen that must hold still
    "pixel_tol": 12,          # per-pixel brightness diff (0-255) that counts as changed
    "sample_interval": 0.10,  # seconds between compared samples
    "keep_tail": 0.0,         # optional hair of freeze to keep after the cut
    "extra_trim": 0.0,        # trim this many extra seconds off the end
    "min_keep": 0.5,          # if the cut would be before this, treat as an anomaly
    "sample_width": 160,      # downscale width for comparison
    "copy_unchanged": True,   # copy clips with no trailing freeze into the output too
    "fast_tail": False,       # only scan the last N seconds
    "tail_window": 8.0,       # seconds from the end to scan when fast_tail is on
    "exact_cut": True,        # re-encode for a frame-exact end (off = instant copy)
    "vbitrate": "16M",
    "workers": 0,             # 0 = auto
    "preview": True,          # summary popup before anything is written
    "in_folder": "",
    "out_folder": "",
}

# ---- Map Sorter tab -------------------------------------------------------
OTHER_MAP = "Other"
SNAP_PREFIX = "_mapsort_snaps_"
MAP_REPORT = "_mapsort_report.csv"
MAP_FUZZ = 0.85           # fuzzy threshold, longer map names only

# x1, y1, x2, y2 as fractions of the frame.
# The default is deliberately wider than strictly necessary: cropping is only a
# speed trick, and a region that clips the last letters off a long map name
# ("AMSTERDAM" read as "AMSTERI") is the one failure mode that silently costs
# you auto-sorted clips.
MAP_REGIONS = {
    "Scoreboard header": (0.04, 0.08, 0.62, 0.20),
    "Scoreboard header (narrow)": (0.06, 0.10, 0.45, 0.18),
    "Top-left quarter": (0.00, 0.00, 0.50, 0.30),
    "Top strip (full width)": (0.00, 0.05, 1.00, 0.25),
    "Full frame": (0.00, 0.00, 1.00, 1.00),
}
DEFAULT_MAP_REGION = "Scoreboard header"
SPREAD_MODES = ("Across the whole clip", "First seconds (evenly spaced)")

MAP_DEFAULTS = {
    "folder": "",
    "maps": "Amsterdam, Game Show, Gluboko, ICBM, KGB, Mansion, Showroom, U-Bahn",
    "auto": True,             # run the scoreboard-reading stage first
    "region": DEFAULT_MAP_REGION,
    "interval": 0.7,          # seconds between OCR samples in stage 1
    "min_hits": 2,            # frames a map name must read on before it counts
    "snaps": 5,               # snapshots per clip for manual review
    "spread": SPREAD_MODES[0],
    "snap_interval": 3.0,     # gap between snapshots in "First seconds" mode
    "snap_width": 230,
    "threads": 0,             # 0 = auto
}


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #
def find_exe(name):
    exe = shutil.which(name)
    if exe:
        return exe
    for base in ("/opt/homebrew/bin/", "/usr/local/bin/", "/usr/bin/"):
        p = Path(base + name)
        if p.exists():
            return str(p)
    return None


def auto_threads():
    n = os.cpu_count() or 4
    return max(2, min(6, n - 2))


def auto_workers():
    n = os.cpu_count() or 4
    return max(2, min(8, n // 2 + 1))


def settings_path():
    if IS_MAC:
        base = Path.home() / "Library" / "Application Support" / "Fan Cave Studio"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "fancave"
    return base / "clip_trimmer.json"


def load_settings():
    """Returns a section per tab, with defaults filled in."""
    raw = {}
    try:
        raw = json.loads(settings_path().read_text(encoding="utf-8"))
    except Exception:
        pass
    out = {}
    for key, defaults in (("best_play", BP_DEFAULTS), ("freeze", FZ_DEFAULTS),
                          ("maps", MAP_DEFAULTS)):
        section = dict(defaults)
        got = raw.get(key)
        if isinstance(got, dict):
            section.update({k: v for k, v in got.items() if k in defaults})
        out[key] = section
    return out


def save_settings(cfg):
    try:
        p = settings_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    except Exception:
        pass


def unique_path(path):
    path = Path(path)
    if not path.exists():
        return path
    n = 2
    while True:
        cand = path.parent / f"{path.stem} ({n}){path.suffix}"
        if not cand.exists():
            return cand
        n += 1


def hhmmss(t):
    if t is None:
        return "—"
    t = max(0.0, float(t))
    return f"{int(t // 3600):d}:{int(t // 60) % 60:02d}:{t % 60:05.2f}"


def is_clip(p):
    """A real video file, not a dotfile or a macOS ._ resource fork."""
    return (p.is_file() and not p.name.startswith(".")
            and p.suffix.lower() in VIDEO_EXTS)


def list_videos(folder):
    return sorted(p for p in Path(folder).iterdir() if is_clip(p))


def list_input(inp):
    """A folder of clips, or a single clip."""
    inp = Path(inp).expanduser()
    if inp.is_dir():
        return list_videos(inp)
    return [inp] if is_clip(inp) else []


def probe_duration(video, ffprobe):
    if not ffprobe:
        return 0.0
    try:
        out = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nokey=1:noprint_wrappers=1", str(video)],
            capture_output=True, text=True, check=True).stdout.strip()
        return float(out)
    except Exception:
        return 0.0


def probe_dims(video, ffprobe):
    """(width, height) of the first video stream, or (0, 0)."""
    if not ffprobe:
        return (0, 0)
    try:
        out = subprocess.run(
            [ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=width,height", "-of", "csv=s=x:p=0", str(video)],
            capture_output=True, text=True, check=True).stdout.strip()
        w, h = out.split("x")[:2]
        return (int(w), int(h))
    except Exception:
        return (0, 0)


def hwaccel_args():
    return ["-hwaccel", "videotoolbox"] if IS_MAC else []


def strip_hwaccel(cmd):
    out, skip = [], False
    for c in cmd:
        if skip:
            skip = False
            continue
        if c == "-hwaccel":
            skip = True
            continue
        out.append(c)
    return out


def open_in_finder(path):
    try:
        subprocess.run((["open"] if IS_MAC else ["xdg-open"]) + [str(path)])
        return True
    except Exception:
        return False


# =========================================================================== #
#                            BEST PLAY  engine
# =========================================================================== #
class VisionOCR:
    """Apple's Vision framework. Runs on the Neural Engine — the fast path on M1."""
    name = "Apple Vision (Neural Engine)"

    @staticmethod
    def available():
        if not IS_MAC:
            return False
        try:
            import Vision        # noqa: F401
            import Foundation    # noqa: F401
            return True
        except Exception:
            return False

    def __init__(self):
        import Vision
        import Foundation
        self._V = Vision
        self._NSURL = Foundation.NSURL
        self._level = getattr(Vision, "VNRequestTextRecognitionLevelFast", 1)

    def recognize(self, image_path):
        url = self._NSURL.fileURLWithPath_(str(image_path))
        handler = self._V.VNImageRequestHandler.alloc().initWithURL_options_(url, {})
        req = self._V.VNRecognizeTextRequest.alloc().init()
        req.setRecognitionLevel_(self._level)
        req.setUsesLanguageCorrection_(False)
        for setter, value in (("setRecognitionLanguages_", ["en-US"]),
                              ("setMinimumTextHeight_", 0.03)):
            try:
                getattr(req, setter)(value)
            except Exception:
                pass
        try:
            ok, _err = handler.performRequests_error_([req], None)
        except Exception:
            return []
        if not ok:
            return []
        out = []
        for obs in (req.results() or []):
            try:
                cands = obs.topCandidates_(1)
                if cands and len(cands):
                    out.append(str(cands[0].string()))
            except Exception:
                pass
        return out


class TesseractOCR:
    """Fallback for machines without PyObjC. Slower, but keeps the tab usable."""
    name = "Tesseract"

    @staticmethod
    def available():
        return find_exe("tesseract") is not None

    def __init__(self):
        self.exe = find_exe("tesseract")

    def recognize(self, image_path):
        try:
            r = subprocess.run(
                [self.exe, str(image_path), "stdout", "--psm", "11", "-l", "eng"],
                capture_output=True, text=True, timeout=30)
            return [ln for ln in r.stdout.splitlines() if ln.strip()]
        except Exception:
            return []


def pick_ocr(prefer_vision=True):
    """Return (engine, note). engine is None when nothing usable is installed."""
    if prefer_vision and VisionOCR.available():
        return VisionOCR(), ""
    if TesseractOCR.available():
        note = ("Apple Vision is unavailable, using Tesseract (slower).\n"
                "For the fast path:  pip3 install pyobjc-framework-Vision") if IS_MAC else ""
        return TesseractOCR(), note
    if IS_MAC:
        return None, ("No text recogniser found.\n\nInstall the fast one with:\n"
                      "    pip3 install pyobjc-framework-Vision pyobjc-framework-Quartz\n\n"
                      "or the fallback with:\n    brew install tesseract")
    return None, "No text recogniser found. Install tesseract."


CONFUSABLE = str.maketrans({"0": "O", "1": "I", "|": "I", "!": "I", "5": "S",
                            "8": "B", "$": "S", "6": "G", "@": "A"})


def normalize(text):
    return re.sub(r"[^A-Z]", "", text.upper().translate(CONFUSABLE))


def looks_like_best_play(strings):
    """True when this frame's OCR output plausibly contains BEST PLAY.

    Vision often returns the two words as separate observations, so the joined
    blob is tested as well as each line, and near-misses ('BEST PLAV') pass.
    """
    lines = [normalize(s) for s in strings]
    blob = "".join(lines)
    n = len(TARGET)
    for hay in (blob, *lines):
        if not hay:
            continue
        if TARGET in hay:
            return True
        # Near-misses only count when they still start with B, so ordinary words
        # one letter away from the target ("TEST PLAY") don't trip the scanner.
        for i, ch in enumerate(hay):
            if ch != "B":
                continue
            for w in (n - 1, n, n + 1, n + 2):
                chunk = hay[i:i + w]
                if len(chunk) < n - 1:
                    continue
                if difflib.SequenceMatcher(None, TARGET, chunk).ratio() >= FUZZ:
                    return True
    return False


def crop_filter(region):
    x, y, w, h = REGIONS.get(region, REGIONS[DEFAULT_REGION])
    if (x, y, w, h) == (0.0, 0.0, 1.0, 1.0):
        return f"scale={SCAN_W}:-2"
    return (f"crop=w=iw*{w:.4f}:h=ih*{h:.4f}:x=iw*{x:.4f}:y=ih*{y:.4f},"
            f"scale={SCAN_W}:-2")


def extract_frames(video, start, duration, fps, vf, out_dir, ffmpeg):
    """Write sampled JPEGs for [start, start+duration). Returns [(time, path)].

    Decoding runs through VideoToolbox on Apple Silicon, with a one-shot
    software retry for files the hardware decoder refuses.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("f_*.jpg"):
        old.unlink()
    cmd = ([ffmpeg, "-hide_banner", "-v", "error", "-nostdin"] + hwaccel_args()
           + ["-ss", f"{start:.3f}", "-i", str(video), "-t", f"{duration:.3f}",
              "-vf", f"fps={fps},{vf}",
              "-q:v", "4", "-an", "-sn", "-threads", "0",
              str(out_dir / "f_%06d.jpg")])
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        if not IS_MAC:
            return []
        try:                                      # retry once without hwaccel
            subprocess.run(strip_hwaccel(cmd), check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            return []
    frames = sorted(out_dir.glob("f_*.jpg"))
    return [(start + i / fps, p) for i, p in enumerate(frames)]


def extract_window(video, start, duration, fps, region, out_dir, ffmpeg):
    """Best Play sampling: the banner region, scaled for the text recogniser."""
    return extract_frames(video, start, duration, fps, crop_filter(region),
                          out_dir, ffmpeg)


def scan_frames(frames, ocr, threads, cancel):
    """OCR a batch of frames in parallel; returns a list of booleans."""
    if not frames:
        return []
    if threads <= 1:
        return [False if cancel.is_set() else looks_like_best_play(ocr.recognize(p))
                for _t, p in frames]

    def one(item):
        if cancel.is_set():
            return False
        return looks_like_best_play(ocr.recognize(item[1]))

    with ThreadPoolExecutor(max_workers=threads) as ex:
        return list(ex.map(one, frames))


def first_run_start(times, hits, at_end):
    """Index of the first hit that is backed by MIN_RUN consecutive hits.

    A lone hit is accepted only when it is the final sample, so a banner that
    starts on the very last frame of the scan still counts.
    """
    n = len(hits)
    for i, h in enumerate(hits):
        if not h:
            continue
        run = 1
        j = i + 1
        while j < n and hits[j]:
            run += 1
            j += 1
        if run >= MIN_RUN or (at_end and i == n - 1):
            return i
    return None


def find_banner(video, duration, cfg, ocr, tmp_dir, progress, cancel, ffmpeg):
    """Seconds at which BEST PLAY first appears, or None.

    Scans in windows so a hit ends the work early, and decodes the next window
    while the current one is being read.
    """
    fps = float(cfg["scan_fps"])
    region = cfg["region"]
    threads = int(cfg["threads"]) or auto_threads()
    duration = max(0.0, duration)
    starts = []
    t = 0.0
    while t < duration:
        starts.append(t)
        t += WINDOW_S

    pending = {}

    def prefetch(idx, slot):
        s = starts[idx]
        pending[idx] = extract_window(video, s, min(WINDOW_S, duration - s), fps,
                                      region, tmp_dir / slot, ffmpeg)

    coarse = None
    worker = None
    for i, s in enumerate(starts):
        if cancel.is_set():
            return None
        slot = f"w{i % 2}"
        if i not in pending:
            prefetch(i, slot)
        frames = pending.pop(i)
        if worker is not None:
            worker.join()
            worker = None
        if i + 1 < len(starts):                   # decode ahead while we read
            nxt = i + 1
            worker = threading.Thread(target=prefetch, args=(nxt, f"w{nxt % 2}"),
                                      daemon=True)
            worker.start()
        hits = scan_frames(frames, ocr, threads, cancel)
        idx = first_run_start([f[0] for f in frames], hits,
                              at_end=(i == len(starts) - 1))
        progress(min(duration, s + WINDOW_S), duration)
        if idx is not None:
            coarse = frames[idx][0]
            break
    if worker is not None:
        worker.join()
    if coarse is None:
        return None

    # Second pass: pin down the moment the banner actually appears.
    back = max(0.0, coarse - (1.0 / fps) - 0.05)
    span = coarse - back + 0.30
    fine = extract_window(video, back, span, REFINE_FPS, region,
                          tmp_dir / "refine", ffmpeg)
    if fine:
        hits = scan_frames(fine, ocr, threads, cancel)
        for (tm, _p), h in zip(fine, hits):
            if h:
                return tm
    return coarse


def trim_from(video, start, dest, ffmpeg):
    """Stream-copy everything from `start` onward. No re-encode, no quality loss."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [ffmpeg, "-hide_banner", "-v", "error", "-nostdin", "-y",
           "-ss", f"{max(0.0, start):.3f}", "-i", str(video),
           "-map", "0:v:0", "-map", "0:a:0?", "-c", "copy",
           "-avoid_negative_ts", "make_zero"]
    if dest.suffix.lower() in (".mp4", ".mov", ".m4v"):
        cmd += ["-movflags", "+faststart"]   # mp4-family only; other muxers reject it
    cmd += [str(dest)]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return dest


def move_into(video, folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    dest = unique_path(folder / Path(video).name)
    shutil.move(str(video), str(dest))
    return dest


def process_one(video, folder, cfg, ocr, tmp_dir, progress, cancel, ffmpeg, ffprobe):
    """One Best Play clip. Returns a dict with status in {hit, miss, error, cancelled}."""
    res = {"file": video.name, "status": "error", "banner": None,
           "start": None, "duration": None, "output": "", "note": ""}
    dur = probe_duration(video, ffprobe)
    res["duration"] = dur
    if dur <= 0:
        res["note"] = "unreadable or zero-length"
        return res

    t0 = time.time()
    banner = find_banner(video, dur, cfg, ocr, tmp_dir, progress, cancel, ffmpeg)
    res["note"] = f"scanned in {time.time() - t0:.1f}s"
    if cancel.is_set():
        res["status"] = "cancelled"
        return res

    if banner is None:
        try:
            move_into(video, folder / OUT_MISSES)
            res["status"] = "miss"
        except Exception as ex:
            res["note"] = f"could not move: {ex}"
        return res

    start = max(0.0, banner - float(cfg["lead_in"]))
    res["banner"], res["start"] = banner, start
    dest = unique_path(folder / OUT_HITS / f"{video.stem}_bestplay{video.suffix}")
    try:
        trim_from(video, start, dest, ffmpeg)
    except subprocess.CalledProcessError as ex:
        res["note"] = f"trim failed ({ex.returncode}); original left in place"
        return res
    if not dest.exists() or dest.stat().st_size == 0:
        res["note"] = "trim produced an empty file; original left in place"
        if dest.exists():
            dest.unlink()
        return res
    res["output"] = dest.name
    try:
        move_into(video, folder / OUT_DONE)
    except Exception as ex:
        res["note"] = f"trimmed, but original not moved: {ex}"
    res["status"] = "hit"
    return res


def write_report(folder, rows):
    out = Path(folder) / OUT_HITS / REPORT_NAME
    out.parent.mkdir(parents=True, exist_ok=True)
    new = not out.exists()
    with out.open("a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["run", "file", "status", "banner_at_s", "trim_start_s",
                        "source_duration_s", "output", "note"])
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        for r in rows:
            w.writerow([stamp, r["file"], r["status"],
                        f"{r['banner']:.2f}" if r["banner"] is not None else "",
                        f"{r['start']:.2f}" if r["start"] is not None else "",
                        f"{r['duration']:.2f}" if r["duration"] else "",
                        r["output"], r["note"]])
    return out


# =========================================================================== #
#                           FREEZE TAIL  engine
# =========================================================================== #
def _numpy():
    try:
        import numpy as np
        return np
    except ImportError:
        return None


def sample_gray(video, start, duration, interval, width, dims, ffmpeg, cancel):
    """Yield (time, HxW uint8 array) sampled every `interval` seconds.

    Frames come straight out of ffmpeg as raw grayscale, decoded through
    VideoToolbox on Apple Silicon, so nothing is written to disk and no image
    library is needed. `flags=area` matches the area-average downscale the
    original OpenCV version used, so the same tolerance settings mean the
    same thing.
    """
    np = _numpy()
    if np is None:
        return
    sw, sh = dims
    if sw <= 0 or sh <= 0:
        return
    w = int(width)
    h = max(1, int(round(sh * w / sw)))
    rate = 1.0 / max(0.001, interval)
    cmd = ([ffmpeg, "-hide_banner", "-v", "error", "-nostdin"] + hwaccel_args()
           + ["-ss", f"{max(0.0, start):.3f}", "-i", str(video)])
    if duration is not None:
        cmd += ["-t", f"{duration:.3f}"]
    cmd += ["-vf", f"fps={rate:.6f},scale={w}:{h}:flags=area,format=gray",
            "-an", "-sn", "-f", "rawvideo", "-pix_fmt", "gray", "-threads", "0", "-"]

    def spawn(c):
        return subprocess.Popen(c, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    proc = spawn(cmd)
    n = w * h
    i = 0
    got_any = False
    try:
        while True:
            if cancel is not None and cancel.is_set():
                break
            buf = proc.stdout.read(n)
            if not buf or len(buf) < n:
                break
            got_any = True
            yield (start + i / rate, np.frombuffer(buf, dtype=np.uint8).reshape(h, w))
            i += 1
    finally:
        try:
            proc.stdout.close()
        except Exception:
            pass
        proc.wait()

    if not got_any and IS_MAC and proc.returncode not in (0, None):
        # hardware decode refused this file — fall back to software once
        proc = spawn(strip_hwaccel(cmd))
        i = 0
        try:
            while True:
                if cancel is not None and cancel.is_set():
                    break
                buf = proc.stdout.read(n)
                if not buf or len(buf) < n:
                    break
                yield (start + i / rate, np.frombuffer(buf, dtype=np.uint8).reshape(h, w))
                i += 1
        finally:
            try:
                proc.stdout.close()
            except Exception:
                pass
            proc.wait()


def scan_range(video, start, duration, s, dims, ffmpeg, cancel):
    """Return (time of the last sample that differed from its predecessor, last time)."""
    np = _numpy()
    max_frac = 1.0 - float(s["unchanged_pct"]) / 100.0
    tol = int(s["pixel_tol"])
    prev = None
    last_change = None
    last_t = start
    for t, cur in sample_gray(video, start, duration, float(s["sample_interval"]),
                              int(s["sample_width"]), dims, ffmpeg, cancel):
        last_t = t
        if prev is not None:
            # same maths as the original: share of pixels that moved by more
            # than the tolerance. uint8-safe absolute difference.
            diff = np.maximum(cur, prev) - np.minimum(cur, prev)
            if np.count_nonzero(diff > tol) / cur.size > max_frac:
                last_change = t
        prev = cur
    return last_change, last_t


def detect_last_motion(video, s, ffmpeg, ffprobe, cancel):
    """(last motion time, total duration, widened?).

    fast_tail scans only the last `tail_window` seconds. If that whole window is
    static the freeze began earlier, so it falls back to a full scan.
    """
    total = probe_duration(video, ffprobe)
    dims = probe_dims(video, ffprobe)
    widened = False
    use_window = bool(s.get("fast_tail")) and s.get("tail_window") and total > float(s["tail_window"])

    if use_window:
        start_t = max(0.0, total - float(s["tail_window"]))
        change_t, last_seen = scan_range(video, start_t, None, s, dims, ffmpeg, cancel)
        if change_t is None and start_t > 0:
            widened = True
            change_t, last_seen = scan_range(video, 0.0, None, s, dims, ffmpeg, cancel)
    else:
        change_t, last_seen = scan_range(video, 0.0, None, s, dims, ffmpeg, cancel)

    if total <= 0:
        total = last_seen
    return (change_t if change_t is not None else 0.0), total, widened


def plan_for(video, out_dir, s, ffmpeg, ffprobe, cancel):
    last_t, total, widened = detect_last_motion(video, s, ffmpeg, ffprobe, cancel)
    base = {"video": video, "total": total, "widened": widened,
            "last_motion": last_t, "cut": None, "removed": 0.0, "out": None,
            "msg": "", "result": ""}
    if total <= 0:
        return {**base, "status": "error", "msg": "unreadable or zero-length"}
    frozen_len = total - last_t
    if frozen_len >= float(s["freeze_duration"]):
        if last_t < float(s["min_keep"]):
            return {**base, "status": "anomaly",
                    "msg": f"almost entirely static ({total:.1f}s)"}
        cut = last_t + float(s["keep_tail"]) - float(s["extra_trim"])
        cut = max(0.1, min(total, cut))
        return {**base, "status": "trim", "cut": cut, "removed": total - cut,
                "out": Path(out_dir) / (video.stem + ".mp4")}
    return {**base, "status": "copy", "out": Path(out_dir) / video.name}


def resolve_out_names(plans):
    """Two sources can map to the same output name (clip.mov and clip.mp4 both
    become clip.mp4). Give the later ones a suffix instead of silently
    overwriting the earlier one."""
    seen = {}
    for p in plans:
        out = p.get("out")
        if out is None:
            continue
        key = str(out).lower()
        if key in seen:
            seen[key] += 1
            p["out"] = out.with_name(f"{out.stem} ({seen[key]}){out.suffix}")
        else:
            seen[key] = 1
    return plans


def do_trim(video, cut, out, ffmpeg, s):
    """Cut the tail at `cut` seconds. Exact mode re-encodes; otherwise stream copy."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if not s.get("exact_cut", True):
        cmd = [ffmpeg, "-hide_banner", "-v", "error", "-nostdin", "-y",
               "-i", str(video), "-t", f"{cut:.3f}",
               "-map", "0:v:0", "-map", "0:a:0?", "-c", "copy"]
        if out.suffix.lower() in (".mp4", ".mov", ".m4v"):
            cmd += ["-movflags", "+faststart"]
        subprocess.run(cmd + [str(out)], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return out

    encoders = ["h264_videotoolbox", "libx264"] if IS_MAC else ["libx264"]
    last = None
    for enc in encoders:
        cmd = ([ffmpeg, "-hide_banner", "-v", "error", "-nostdin", "-y"]
               + hwaccel_args() + ["-i", str(video), "-t", f"{cut:.3f}",
                                   "-map", "0:v:0", "-map", "0:a:0?"])
        if enc == "h264_videotoolbox":
            cmd += ["-c:v", "h264_videotoolbox", "-b:v", str(s.get("vbitrate", "16M")),
                    "-pix_fmt", "yuv420p"]
        else:
            cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                    "-pix_fmt", "yuv420p"]
        cmd += ["-c:a", "aac", "-b:a", "192k", str(out)]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
            return out
        except subprocess.CalledProcessError as ex:
            last = ex
            if out.exists():
                out.unlink()
    raise last


def execute_plan(plan, ffmpeg, s, cancel):
    """Carry out one planned action. Returns the plan with 'result' filled in."""
    if cancel.is_set():
        plan["result"] = "cancelled"
        return plan
    video = plan["video"]
    try:
        if plan["status"] == "trim":
            do_trim(video, plan["cut"], plan["out"], ffmpeg, s)
            plan["result"] = "trimmed"
        elif plan["status"] == "copy":
            if not s.get("copy_unchanged", True):
                plan["result"] = "skipped"
            else:
                Path(plan["out"]).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(video, plan["out"])
                plan["result"] = "copied"
        else:
            plan["result"] = plan["status"]
    except subprocess.CalledProcessError:
        plan["result"] = "error"
        plan["msg"] = plan["msg"] or "ffmpeg failed"
    except Exception as ex:
        plan["result"] = "error"
        plan["msg"] = str(ex)
    return plan


def freeze_summary(plans):
    trims = [p for p in plans if p["status"] == "trim"]
    copies = [p for p in plans if p["status"] == "copy"]
    anomalies = [p for p in plans if p["status"] == "anomaly"]
    errors = [p for p in plans if p["status"] == "error"]
    widened = [p for p in plans if p.get("widened")]
    removed = sum(p["removed"] for p in trims)
    return trims, copies, anomalies, errors, widened, removed


def write_freeze_report(out_dir, plans):
    out = Path(out_dir) / "_freeze_report.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    new = not out.exists()
    with out.open("a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["run", "file", "plan", "result", "source_duration_s",
                        "last_motion_s", "cut_at_s", "removed_s", "widened_scan",
                        "output", "note"])
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        for p in plans:
            w.writerow([stamp, p["video"].name, p["status"], p.get("result", ""),
                        f"{p['total']:.2f}" if p.get("total") else "",
                        f"{p['last_motion']:.2f}" if p.get("last_motion") is not None else "",
                        f"{p['cut']:.2f}" if p.get("cut") is not None else "",
                        f"{p['removed']:.2f}" if p.get("removed") else "",
                        "yes" if p.get("widened") else "",
                        Path(p["out"]).name if p.get("out") else "", p.get("msg", "")])
    return out


# =========================================================================== #
#                            MAP SORTER  engine
# =========================================================================== #
def parse_map_list(text):
    """The editable map list -> a clean, de-duplicated list of names."""
    out, seen = [], set()
    for part in re.split(r"[,\n]", str(text or "")):
        name = " ".join(part.split())
        if not name:
            continue
        # a map folder name has to be safe to create on disk
        name = re.sub(r"[/\\:]+", "-", name).strip(". ")
        if name and name.lower() != OTHER_MAP.lower() and name.lower() not in seen:
            seen.add(name.lower())
            out.append(name)
    return out


def _squash(text):
    return re.sub(r"[^a-z0-9]", "", str(text).lower())


def match_map(text, maps):
    """Which map name (if any) this scoreboard text is naming."""
    n = _squash(text)
    if len(n) < 3:
        return None
    for m in maps:                        # exact substring first (covers short names)
        if _squash(m) and _squash(m) in n:
            return m
    for m in maps:                        # fuzzy only for names long enough to be safe
        mn = _squash(m)
        if len(mn) < 5:
            continue
        for i in range(0, max(1, len(n) - len(mn) + 1)):
            if difflib.SequenceMatcher(None, mn, n[i:i + len(mn)]).ratio() >= MAP_FUZZ:
                return m
    return None


def roi_filter(region, out_w=1200):
    x1, y1, x2, y2 = MAP_REGIONS.get(region, MAP_REGIONS[DEFAULT_MAP_REGION])
    w, h = max(0.01, x2 - x1), max(0.01, y2 - y1)
    if (x1, y1, x2, y2) == (0.0, 0.0, 1.0, 1.0):
        return f"scale={out_w}:-2"
    return (f"crop=w=iw*{w:.4f}:h=ih*{h:.4f}:x=iw*{x1:.4f}:y=ih*{y1:.4f},"
            f"scale={out_w}:-2")


def read_texts(frames, ocr, threads, cancel):
    """OCR a batch of frames in parallel; returns one joined string per frame."""
    if not frames:
        return []
    if threads <= 1:
        return ["" if cancel.is_set() else " ".join(ocr.recognize(p)) for _t, p in frames]

    def one(item):
        if cancel.is_set():
            return ""
        return " ".join(ocr.recognize(item[1]))

    with ThreadPoolExecutor(max_workers=threads) as ex:
        return list(ex.map(one, frames))


def detect_map(video, duration, cfg, ocr, tmp_dir, cancel, ffmpeg, threads=1):
    """The map named on the scoreboard, or None. Stops as soon as it is sure."""
    maps = cfg["map_list"]
    if not maps:
        return None
    interval = max(0.1, float(cfg["interval"]))
    min_hits = max(1, int(cfg["min_hits"]))
    vf = roi_filter(cfg["region"])
    tally = Counter()
    t = 0.0
    duration = max(0.0, duration)
    while t < duration:
        if cancel.is_set():
            return None
        frames = extract_frames(video, t, min(WINDOW_S, duration - t),
                                1.0 / interval, vf, tmp_dir, ffmpeg)
        for text in read_texts(frames, ocr, threads, cancel):
            m = match_map(text, maps)
            if m:
                tally[m] += 1
                if tally[m] >= min_hits:
                    return m
        t += WINDOW_S
    return None


def snapshot_times(duration, n, mode, interval):
    """When to grab the review snapshots."""
    n = max(1, int(n))
    if duration <= 0:
        return [0.0] * n
    if n == 1:
        return [duration * 0.5]
    if mode == SPREAD_MODES[0]:           # across the whole clip
        return [max(0.0, min(duration - 0.1, duration * (i + 0.5) / n))
                for i in range(n)]
    if duration <= (n - 1) * interval + 0.5:      # too short for the full spacing
        span = max(0.0, duration - 0.2)
        return [span * i / (n - 1) for i in range(n)]
    return [i * interval for i in range(n)]


def snap_prefix(video):
    safe = re.sub(r"[^A-Za-z0-9]+", "_", Path(video).stem)[:40]
    h = hashlib.md5(Path(video).name.encode("utf-8")).hexdigest()[:6]
    return f"{safe}_{h}"


def snap_paths_for(video, snap_dir, n):
    p = snap_prefix(video)
    return [Path(snap_dir) / f"{p}__{i}.png" for i in range(int(n))]


def find_or_make_snap_dir(folder, make=True):
    folder = Path(folder)
    existing = sorted(d for d in folder.glob(SNAP_PREFIX + "*") if d.is_dir())
    if existing:
        return existing[0]
    if not make:
        return None
    d = folder / (SNAP_PREFIX + uuid.uuid4().hex[:8])
    d.mkdir(parents=True, exist_ok=True)
    return d


def purge_snaps(folder, log=print):
    folder = Path(folder)
    removed = 0
    for d in folder.glob(SNAP_PREFIX + "*"):
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)
            removed += 1
    log(f"Purged {removed} snapshot cache folder(s).")
    return removed


def extract_snapshots(video, snap_dir, cfg, ffmpeg, ffprobe):
    """Make (or reuse) the review snapshots for one clip. Returns the paths made."""
    n = int(cfg["snaps"])
    outs = snap_paths_for(video, snap_dir, n)
    if all(o.exists() for o in outs):
        return outs
    dur = probe_duration(video, ffprobe)
    times = snapshot_times(dur, n, cfg["spread"], float(cfg["snap_interval"]))
    width = int(cfg["snap_width"])
    for out, t in zip(outs, times):
        if out.exists():
            continue
        cmd = ([ffmpeg, "-hide_banner", "-v", "error", "-nostdin", "-y"] + hwaccel_args()
               + ["-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1",
                  "-vf", f"scale={width}:-2", "-an", "-sn", str(out)])
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            if IS_MAC:
                try:
                    subprocess.run(strip_hwaccel(cmd), check=True,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except subprocess.CalledProcessError:
                    pass
    return [o for o in outs if o.exists()]


def move_to_map(video, folder, map_name):
    """Move a clip into <folder>/<map>/ without ever overwriting what is there."""
    dest_dir = Path(folder) / map_name
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = unique_path(dest_dir / Path(video).name)
    shutil.move(str(video), str(dest))
    return dest


def write_map_report(folder, rows):
    out = Path(folder) / MAP_REPORT
    new = not out.exists()
    with out.open("a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["run", "file", "map", "how", "moved_to"])
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        for r in rows:
            w.writerow([stamp, r["file"], r["map"], r["how"], r.get("dest", "")])
    return out


# =========================================================================== #
#                                   GUI
# =========================================================================== #
def run_gui(preset_folder=None):
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox

    ffmpeg = find_exe("ffmpeg")
    ffprobe = find_exe("ffprobe")
    settings = load_settings()
    bp_cfg, fz_cfg, mp_cfg = settings["best_play"], settings["freeze"], settings["maps"]
    if preset_folder:
        bp_cfg["folder"] = str(preset_folder)

    root = tk.Tk()
    root.title(APP_NAME)
    root.geometry("1240x820")

    msg_q = queue.Queue()

    def post(kind, payload):
        msg_q.put((kind, payload))

    book = ttk.Notebook(root)
    book.pack(fill="both", expand=True, padx=10, pady=10)
    bp_tab = ttk.Frame(book)
    fz_tab = ttk.Frame(book)
    mp_tab = ttk.Frame(book)
    book.add(bp_tab, text="  Best Play  ")
    book.add(fz_tab, text="  Freeze Tail  ")
    book.add(mp_tab, text="  Map Sorter  ")

    # ===================================================================== #
    #                            BEST PLAY tab
    # ===================================================================== #
    bp = {"cancel": threading.Event(), "running": False}

    top = ttk.Frame(bp_tab); top.pack(fill="x", padx=10, pady=(10, 4))
    ttk.Label(top, text="PS5 clips folder:").pack(side="left")
    bp_folder = tk.StringVar(value=bp_cfg["folder"])
    ttk.Entry(top, textvariable=bp_folder).pack(side="left", fill="x", expand=True, padx=6)
    ttk.Button(top, text="Choose…",
               command=lambda: pick_dir(bp_folder, "Choose the folder with your PS5 clips")
               ).pack(side="left")

    lead = ttk.LabelFrame(bp_tab, text="Trim"); lead.pack(fill="x", padx=10, pady=6)
    inner = ttk.Frame(lead); inner.pack(fill="x", padx=10, pady=8)
    ttk.Label(inner, text="Start the clip", font=("", 12)).pack(side="left")
    bp_lead = tk.DoubleVar(value=float(bp_cfg["lead_in"]))
    ttk.Spinbox(inner, from_=0.0, to=120.0, increment=0.5, width=7,
                textvariable=bp_lead, format="%.1f").pack(side="left", padx=6)
    ttk.Label(inner, text="seconds BEFORE the “BEST PLAY” banner appears.",
              font=("", 12)).pack(side="left")
    ttk.Label(lead, foreground="#888",
              text="Cuts are stream copies (no re-encode), so the cut lands on the "
                   "nearest keyframe at or before that point — never later.").pack(
        anchor="w", padx=10, pady=(0, 8))

    opts = ttk.LabelFrame(bp_tab, text="Scan"); opts.pack(fill="x", padx=10, pady=(0, 6))
    orow = ttk.Frame(opts); orow.pack(fill="x", padx=10, pady=8)
    ttk.Label(orow, text="Look at").pack(side="left")
    bp_region = tk.StringVar(value=bp_cfg["region"] if bp_cfg["region"] in REGIONS
                             else DEFAULT_REGION)
    ttk.Combobox(orow, textvariable=bp_region, values=list(REGIONS), width=22,
                 state="readonly").pack(side="left", padx=6)
    ttk.Label(orow, text="   Frames per second").pack(side="left")
    bp_fps = tk.DoubleVar(value=float(bp_cfg["scan_fps"]))
    ttk.Spinbox(orow, from_=0.5, to=10.0, increment=0.5, width=6,
                textvariable=bp_fps, format="%.1f").pack(side="left", padx=6)
    ttk.Label(orow, text="   OCR threads").pack(side="left")
    bp_threads = tk.IntVar(value=int(bp_cfg["threads"]) or auto_threads())
    ttk.Spinbox(orow, from_=1, to=16, width=5, textvariable=bp_threads).pack(side="left", padx=6)
    bp_engine = tk.StringVar(value="")
    ttk.Label(orow, textvariable=bp_engine, foreground="#888").pack(side="left", padx=12)

    bp_act = ttk.Frame(bp_tab); bp_act.pack(fill="x", padx=10)
    bp_start = ttk.Button(bp_act, text="Start Best Play scan", command=lambda: bp_go())
    bp_start.pack(side="left")
    bp_cancel_btn = ttk.Button(bp_act, text="Cancel", state="disabled",
                               command=lambda: bp_stop())
    bp_cancel_btn.pack(side="left", padx=6)
    ttk.Button(bp_act, text="Open results folder",
               command=lambda: reveal(Path(bp_folder.get().strip() or ".") / OUT_HITS,
                                      bp_folder.get().strip())).pack(side="left", padx=6)

    bp_status = tk.StringVar(value="Choose the folder your PS5 clips are in, then press Start.")
    ttk.Label(bp_tab, textvariable=bp_status, font=("", 12, "bold")).pack(
        anchor="w", padx=10, pady=(8, 2))
    bp_bar = ttk.Progressbar(bp_tab, mode="determinate", maximum=1000)
    bp_bar.pack(fill="x", padx=10, pady=(0, 6))

    bp_wrap = ttk.Frame(bp_tab); bp_wrap.pack(fill="both", expand=True, padx=10, pady=(0, 10))
    bp_cols = ("file", "result", "banner", "start", "output", "note")
    bp_tree = ttk.Treeview(bp_wrap, columns=bp_cols, show="headings", height=10)
    for c, w, t in (("file", 280, "Clip"), ("result", 80, "Result"),
                    ("banner", 95, "Banner at"), ("start", 95, "Trim from"),
                    ("output", 220, "Saved as"), ("note", 170, "Note")):
        bp_tree.heading(c, text=t)
        bp_tree.column(c, width=w, anchor="w")
    bp_sb = ttk.Scrollbar(bp_wrap, orient="vertical", command=bp_tree.yview)
    bp_tree.configure(yscrollcommand=bp_sb.set)
    bp_tree.pack(side="left", fill="both", expand=True)
    bp_sb.pack(side="right", fill="y")
    for tag, col in (("hit", "#1a7f37"), ("miss", "#8a6d00"), ("error", "#b3261e")):
        bp_tree.tag_configure(tag, foreground=col)

    # ===================================================================== #
    #                           FREEZE TAIL tab
    # ===================================================================== #
    fz = {"cancel": threading.Event(), "running": False, "plans": [],
          "confirm": {"answer": None, "event": threading.Event()}}

    fz_top = ttk.Frame(fz_tab); fz_top.pack(fill="x", padx=10, pady=(10, 2))
    ttk.Label(fz_top, text="Input folder of clips:", width=22).pack(side="left")
    fz_in = tk.StringVar(value=fz_cfg["in_folder"])
    ttk.Entry(fz_top, textvariable=fz_in).pack(side="left", fill="x", expand=True, padx=6)
    ttk.Button(fz_top, text="Choose…", command=lambda: pick_input()).pack(side="left")

    fz_top2 = ttk.Frame(fz_tab); fz_top2.pack(fill="x", padx=10, pady=2)
    ttk.Label(fz_top2, text="Output folder (separate):", width=22).pack(side="left")
    fz_out = tk.StringVar(value=fz_cfg["out_folder"])
    ttk.Entry(fz_top2, textvariable=fz_out).pack(side="left", fill="x", expand=True, padx=6)
    ttk.Button(fz_top2, text="Choose…",
               command=lambda: pick_dir(fz_out, "Choose the OUTPUT folder (separate)")
               ).pack(side="left")

    det = ttk.LabelFrame(fz_tab, text="What counts as frozen")
    det.pack(fill="x", padx=10, pady=6)
    grid = ttk.Frame(det); grid.pack(fill="x", padx=10, pady=8)

    def num_field(parent, label, var, row, col, width=7, hint=""):
        ttk.Label(parent, text=label).grid(row=row, column=col * 3, sticky="w", pady=2)
        ttk.Entry(parent, textvariable=var, width=width).grid(
            row=row, column=col * 3 + 1, sticky="w", padx=(6, 14))
        if hint:
            ttk.Label(parent, text=hint, foreground="#888").grid(
                row=row, column=col * 3 + 2, sticky="w", padx=(0, 16))

    fz_dur = tk.StringVar(value=str(fz_cfg["freeze_duration"]))
    fz_pct = tk.StringVar(value=str(fz_cfg["unchanged_pct"]))
    fz_tol = tk.StringVar(value=str(fz_cfg["pixel_tol"]))
    fz_keep = tk.StringVar(value=str(fz_cfg["keep_tail"]))
    fz_extra = tk.StringVar(value=str(fz_cfg["extra_trim"]))
    fz_window = tk.StringVar(value=str(fz_cfg["tail_window"]))
    fz_workers = tk.StringVar(value=str(int(fz_cfg["workers"]) or auto_workers()))
    num_field(grid, "Freeze duration (s):", fz_dur, 0, 0, hint="how long the tail must hold still")
    num_field(grid, "Screen unchanged %:", fz_pct, 0, 1, hint="95–99 ignores small animations")
    num_field(grid, "Pixel sensitivity (0–255):", fz_tol, 1, 0, hint="brightness change that counts")
    num_field(grid, "Keep tail (s):", fz_keep, 1, 1, hint="0 = cut exactly at last motion")
    num_field(grid, "Extra end trim (s):", fz_extra, 2, 0, hint="removes a map/transition card")
    num_field(grid, "Tail scan window (s):", fz_window, 2, 1, hint="used by fast tail scan")
    num_field(grid, "Parallel clips:", fz_workers, 3, 0)

    fz_boxes = ttk.Frame(det); fz_boxes.pack(fill="x", padx=10, pady=(0, 8))
    fz_fast = tk.BooleanVar(value=bool(fz_cfg["fast_tail"]))
    fz_preview = tk.BooleanVar(value=bool(fz_cfg["preview"]))
    fz_copy = tk.BooleanVar(value=bool(fz_cfg["copy_unchanged"]))
    fz_exact = tk.BooleanVar(value=bool(fz_cfg["exact_cut"]))
    ttk.Checkbutton(fz_boxes, text="Fast tail scan — only scan the last N seconds",
                    variable=fz_fast).grid(row=0, column=0, sticky="w")
    ttk.Checkbutton(fz_boxes, text="Preview first (summary before anything is written)",
                    variable=fz_preview).grid(row=0, column=1, sticky="w", padx=20)
    ttk.Checkbutton(fz_boxes, text="Also copy clips with no trailing freeze",
                    variable=fz_copy).grid(row=1, column=0, sticky="w")
    ttk.Checkbutton(fz_boxes, text="Exact cut (re-encode). Off = instant stream copy",
                    variable=fz_exact).grid(row=1, column=1, sticky="w", padx=20)

    fz_act = ttk.Frame(fz_tab); fz_act.pack(fill="x", padx=10)
    fz_start = ttk.Button(fz_act, text="Start Freeze Tail scan", command=lambda: fz_go())
    fz_start.pack(side="left")
    fz_cancel_btn = ttk.Button(fz_act, text="Cancel", state="disabled",
                               command=lambda: fz_stop())
    fz_cancel_btn.pack(side="left", padx=6)
    ttk.Button(fz_act, text="Open output folder",
               command=lambda: reveal(fz_out.get().strip(), fz_out.get().strip())
               ).pack(side="left", padx=6)

    fz_status = tk.StringVar(value="Choose an input folder and a separate output folder, "
                                   "then press Start.")
    ttk.Label(fz_tab, textvariable=fz_status, font=("", 12, "bold")).pack(
        anchor="w", padx=10, pady=(8, 2))
    fz_bar = ttk.Progressbar(fz_tab, mode="determinate", maximum=1000)
    fz_bar.pack(fill="x", padx=10, pady=(0, 6))

    fz_wrap = ttk.Frame(fz_tab); fz_wrap.pack(fill="both", expand=True, padx=10, pady=(0, 10))
    fz_cols = ("file", "plan", "cut", "removed", "result", "note")
    fz_tree = ttk.Treeview(fz_wrap, columns=fz_cols, show="headings", height=10)
    for c, w, t in (("file", 280, "Clip"), ("plan", 90, "Plan"),
                    ("cut", 95, "Cut at"), ("removed", 95, "Removed"),
                    ("result", 100, "Result"), ("note", 180, "Note")):
        fz_tree.heading(c, text=t)
        fz_tree.column(c, width=w, anchor="w")
    fz_sb = ttk.Scrollbar(fz_wrap, orient="vertical", command=fz_tree.yview)
    fz_tree.configure(yscrollcommand=fz_sb.set)
    fz_tree.pack(side="left", fill="both", expand=True)
    fz_sb.pack(side="right", fill="y")
    for tag, col in (("trim", "#1a7f37"), ("copy", "#555555"),
                     ("anomaly", "#8a6d00"), ("error", "#b3261e")):
        fz_tree.tag_configure(tag, foreground=col)

    # ===================================================================== #
    #                            MAP SORTER tab
    # ===================================================================== #
    mp = {"cancel": threading.Event(), "running": False, "folder": None,
          "snap_dir": None, "queue": [], "idx": 0, "undo": [], "rows": [],
          "photos": [], "maps": parse_map_list(mp_cfg["maps"]), "reviewing": False}

    mp_top = ttk.Frame(mp_tab); mp_top.pack(fill="x", padx=10, pady=(10, 4))
    ttk.Label(mp_top, text="Clips folder:").pack(side="left")
    mp_folder = tk.StringVar(value=mp_cfg["folder"])
    ttk.Entry(mp_top, textvariable=mp_folder).pack(side="left", fill="x", expand=True, padx=6)
    ttk.Button(mp_top, text="Choose…",
               command=lambda: pick_dir(mp_folder, "Choose the folder of clips")
               ).pack(side="left")
    ttk.Button(mp_top, text="Purge snapshots", command=lambda: mp_purge()).pack(side="left", padx=6)

    mp_set = ttk.LabelFrame(mp_tab, text="Maps and scan")
    mp_set.pack(fill="x", padx=10, pady=6)
    mrow1 = ttk.Frame(mp_set); mrow1.pack(fill="x", padx=10, pady=(8, 2))
    ttk.Label(mrow1, text="Map list (comma separated):").pack(side="left")
    mp_maps = tk.StringVar(value=mp_cfg["maps"])
    mp_maps_entry = ttk.Entry(mrow1, textvariable=mp_maps)
    mp_maps_entry.pack(side="left", fill="x", expand=True, padx=6)
    ttk.Button(mrow1, text="Apply", command=lambda: mp_apply_maps()).pack(side="left")

    mrow2 = ttk.Frame(mp_set); mrow2.pack(fill="x", padx=10, pady=(2, 8))
    mp_auto = tk.BooleanVar(value=bool(mp_cfg["auto"]))
    ttk.Checkbutton(mrow2, text="Stage 1: read the scoreboard and file those clips "
                                "automatically", variable=mp_auto).pack(side="left")
    ttk.Label(mrow2, text="   Read").pack(side="left")
    mp_region = tk.StringVar(value=mp_cfg["region"] if mp_cfg["region"] in MAP_REGIONS
                             else DEFAULT_MAP_REGION)
    ttk.Combobox(mrow2, textvariable=mp_region, values=list(MAP_REGIONS), width=20,
                 state="readonly").pack(side="left", padx=6)
    ttk.Label(mrow2, text="   Snapshots").pack(side="left")
    mp_snaps = tk.IntVar(value=int(mp_cfg["snaps"]))
    ttk.Spinbox(mrow2, from_=1, to=8, width=4, textvariable=mp_snaps).pack(side="left", padx=4)
    mp_spread = tk.StringVar(value=mp_cfg["spread"] if mp_cfg["spread"] in SPREAD_MODES
                             else SPREAD_MODES[0])
    ttk.Combobox(mrow2, textvariable=mp_spread, values=list(SPREAD_MODES), width=26,
                 state="readonly").pack(side="left", padx=6)
    mp_engine = tk.StringVar(value="")
    ttk.Label(mrow2, textvariable=mp_engine, foreground="#888").pack(side="left", padx=10)

    mp_act = ttk.Frame(mp_tab); mp_act.pack(fill="x", padx=10)
    mp_start = ttk.Button(mp_act, text="Start Map Sorter", command=lambda: mp_go())
    mp_start.pack(side="left")
    mp_cancel_btn = ttk.Button(mp_act, text="Cancel", state="disabled",
                               command=lambda: mp_stop())
    mp_cancel_btn.pack(side="left", padx=6)
    ttk.Button(mp_act, text="Open folder",
               command=lambda: reveal(mp_folder.get().strip(), mp_folder.get().strip())
               ).pack(side="left", padx=6)

    mp_status = tk.StringVar(value="Choose the folder of clips, then press Start.")
    ttk.Label(mp_tab, textvariable=mp_status, font=("", 12, "bold")).pack(
        anchor="w", padx=10, pady=(8, 2))
    mp_bar = ttk.Progressbar(mp_tab, mode="determinate", maximum=1000)
    mp_bar.pack(fill="x", padx=10, pady=(0, 4))

    # --- snapshot strip (scrolls sideways if the thumbnails are wide) ------
    strip_wrap = ttk.Frame(mp_tab); strip_wrap.pack(fill="x", padx=10)
    strip_canvas = tk.Canvas(strip_wrap, height=int(mp_cfg["snap_width"]) * 9 // 16 + 8,
                             highlightthickness=0)
    strip_bar = ttk.Scrollbar(strip_wrap, orient="horizontal", command=strip_canvas.xview)
    strip = ttk.Frame(strip_canvas)
    strip_canvas.create_window((0, 0), window=strip, anchor="nw")
    strip.bind("<Configure>",
               lambda e: strip_canvas.configure(scrollregion=strip_canvas.bbox("all")))
    strip_canvas.configure(xscrollcommand=strip_bar.set)
    strip_canvas.pack(fill="x")
    strip_bar.pack(fill="x")
    mp_img_labels = []

    # --- map buttons ------------------------------------------------------
    mp_btns = ttk.Frame(mp_tab); mp_btns.pack(fill="x", padx=10, pady=6)

    mp_wrap = ttk.Frame(mp_tab); mp_wrap.pack(fill="both", expand=True, padx=10, pady=(0, 10))
    mp_cols = ("file", "map", "how", "dest")
    mp_tree = ttk.Treeview(mp_wrap, columns=mp_cols, show="headings", height=7)
    for c, w, t in (("file", 320, "Clip"), ("map", 140, "Map"),
                    ("how", 90, "Decided by"), ("dest", 320, "Moved to")):
        mp_tree.heading(c, text=t)
        mp_tree.column(c, width=w, anchor="w")
    mp_sb = ttk.Scrollbar(mp_wrap, orient="vertical", command=mp_tree.yview)
    mp_tree.configure(yscrollcommand=mp_sb.set)
    mp_tree.pack(side="left", fill="both", expand=True)
    mp_sb.pack(side="right", fill="y")
    mp_tree.tag_configure("auto", foreground="#1a7f37")
    mp_tree.tag_configure("manual", foreground="#333333")
    mp_tree.tag_configure("skipped", foreground="#8a6d00")

    def mp_build_buttons():
        for w in mp_btns.winfo_children():
            w.destroy()
        maps = mp["maps"]
        per_row = 5
        for i, m in enumerate(maps):
            key = f"{i + 1}  " if i < 9 else "   "
            ttk.Button(mp_btns, text=f"{key}{m}", width=18,
                       command=(lambda name=m: mp_choose(name))).grid(
                row=i // per_row, column=i % per_row, padx=4, pady=3)
        base = len(maps)
        row, col = base // per_row, base % per_row
        for label, cmd in ((f"0  {OTHER_MAP}", lambda: mp_choose(OTHER_MAP)),
                           ("S  Skip", lambda: mp_skip()),
                           ("Z  Undo", lambda: mp_undo())):
            ttk.Button(mp_btns, text=label, width=18, command=cmd).grid(
                row=row, column=col, padx=4, pady=3)
            col += 1
            if col >= per_row:
                col = 0
                row += 1

    def mp_apply_maps():
        maps = parse_map_list(mp_maps.get())
        if not maps:
            messagebox.showwarning(APP_NAME, "The map list is empty.")
            return
        mp["maps"] = maps
        mp_build_buttons()
        mp_status.set(f"{len(maps)} map(s) loaded: " + ", ".join(maps))
        save_settings(current_settings())

    mp_build_buttons()

    def mp_current_cfg():
        c = dict(MAP_DEFAULTS)
        c.update({
            "folder": mp_folder.get().strip(),
            "maps": mp_maps.get(),
            "auto": bool(mp_auto.get()),
            "region": mp_region.get(),
            "snaps": max(1, int(mp_snaps.get() or 5)),
            "spread": mp_spread.get(),
            "snap_width": int(mp_cfg["snap_width"]),
            "threads": max(1, int(mp_cfg["threads"]) or auto_threads()),
        })
        c["map_list"] = mp["maps"]
        return c

    def mp_purge():
        folder = mp_folder.get().strip()
        if folder and messagebox.askyesno(APP_NAME, "Delete all snapshot cache folders here?"):
            purge_snaps(folder, lambda m: post("mp_status", m))

    def mp_stop():
        mp["cancel"].set()
        if mp["reviewing"]:
            mp["idx"] = len(mp["queue"])       # end review, keep what is already filed
            mp_finish_review()
            return
        mp_status.set("Stopping…")
        mp_cancel_btn.configure(state="disabled")

    def mp_go():
        folder = mp_folder.get().strip()
        if not folder or not Path(folder).is_dir():
            messagebox.showwarning(APP_NAME, "Choose a valid folder of clips."); return
        if not preflight():
            return
        mp_apply_maps()
        ocr, note = pick_ocr()
        if ocr is None and mp_auto.get():
            messagebox.showerror(APP_NAME, note); return
        if ocr is not None:
            mp_engine.set(f"Reader: {ocr.name}")
        videos = list_videos(folder)
        if not videos:
            messagebox.showinfo(APP_NAME, "No clips in that folder."); return
        for i in mp_tree.get_children():
            mp_tree.delete(i)
        mp.update({"cancel": threading.Event(), "running": True, "folder": Path(folder),
                   "queue": [], "idx": 0, "undo": [], "rows": [], "reviewing": False})
        mp_start.configure(state="disabled")
        mp_cancel_btn.configure(state="normal")
        save_settings(current_settings())
        threading.Thread(target=mp_work, args=(Path(folder), videos, mp_current_cfg(), ocr),
                         daemon=True).start()

    def mp_work(folder, videos, conf, ocr):
        try:
            remaining = list(videos)
            total = len(videos)
            if conf["auto"] and ocr is not None:
                post("mp_status", f"Stage 1 — reading scoreboards on {total} clip(s)…")
                tmp_root = Path(tempfile.mkdtemp(prefix="mapsort_"))
                remaining = []
                done = [0]
                lock = threading.Lock()
                workers = int(conf["threads"])

                def one(v):
                    if mp["cancel"].is_set():
                        return (v, None)
                    slot = tmp_root / re.sub(r"[^A-Za-z0-9]+", "_", v.stem)[:40]
                    dur = probe_duration(v, ffprobe)
                    try:
                        m = detect_map(v, dur, conf, ocr, slot, mp["cancel"], ffmpeg, 1)
                    except Exception:
                        m = None
                    finally:
                        shutil.rmtree(slot, ignore_errors=True)
                    with lock:
                        done[0] += 1
                        post("mp_bar", 0.6 * done[0] / total)
                        post("mp_status", f"Stage 1 — read {done[0]}/{total}…")
                    return (v, m)

                with ThreadPoolExecutor(max_workers=workers) as ex:
                    found = list(ex.map(one, videos))
                shutil.rmtree(tmp_root, ignore_errors=True)
                for v, m in found:
                    if m and not mp["cancel"].is_set():
                        try:
                            dest = move_to_map(v, folder, m)
                            post("mp_row", {"file": v.name, "map": m, "how": "auto",
                                            "dest": str(dest.parent.name + "/" + dest.name)})
                        except Exception as ex:
                            post("mp_status", f"Could not move {v.name}: {ex}")
                            remaining.append(v)
                    else:
                        remaining.append(v)
            else:
                post("mp_status", "Stage 1 skipped — every clip goes to manual review.")

            if mp["cancel"].is_set():
                post("mp_done", []); return

            if not remaining:
                post("mp_status", "Every clip was sorted from its scoreboard.")
                post("mp_done", []); return

            post("mp_status", f"Stage 2 — making snapshots for {len(remaining)} clip(s)…")
            snap_dir = find_or_make_snap_dir(folder)
            mp["snap_dir"] = snap_dir
            review = []
            for i, v in enumerate(remaining, 1):
                if mp["cancel"].is_set():
                    break
                snaps = extract_snapshots(v, snap_dir, conf, ffmpeg, ffprobe)
                review.append((v, snaps))
                post("mp_bar", 0.6 + 0.4 * i / len(remaining))
            post("mp_review", review)
        except Exception as ex:
            post("fail", str(ex))
            post("mp_done", [])

    def mp_clear_strip():
        for lbl in mp_img_labels:
            lbl.destroy()
        mp_img_labels.clear()
        mp["photos"] = []

    def mp_show_current():
        idx, q = mp["idx"], mp["queue"]
        if idx >= len(q):
            mp_finish_review(); return
        video, snaps = q[idx]
        mp_status.set(f"Manual review — clip {idx + 1} of {len(q)}:  {video.name}")
        mp_clear_strip()
        for i, png in enumerate(snaps):
            try:
                ph = tk.PhotoImage(file=str(png))
                mp["photos"].append(ph)
                lbl = ttk.Label(strip, image=ph)
            except Exception:
                lbl = ttk.Label(strip, text="(snapshot\nunreadable)", width=18)
            lbl.grid(row=0, column=i, padx=3)
            mp_img_labels.append(lbl)
        if not snaps:
            lbl = ttk.Label(strip, text="(no frames could be read from this clip)")
            lbl.grid(row=0, column=0, padx=3)
            mp_img_labels.append(lbl)
        strip.update_idletasks()
        strip_canvas.configure(scrollregion=strip_canvas.bbox("all"))

    def mp_record(video, name, how, dest):
        row = {"file": video.name, "map": name, "how": how,
               "dest": f"{Path(dest).parent.name}/{Path(dest).name}" if dest else ""}
        mp["rows"].append(row)
        mp_tree.insert("", "end", tags=(how,),
                       values=(row["file"], row["map"], row["how"], row["dest"]))
        mp_tree.see(mp_tree.get_children()[-1])

    def mp_choose(name):
        if not mp["reviewing"]:
            return
        idx, q = mp["idx"], mp["queue"]
        if idx >= len(q):
            return
        video, _snaps = q[idx]
        try:
            dest = move_to_map(video, mp["folder"], name)
        except Exception as ex:
            messagebox.showerror(APP_NAME, f"Could not move {video.name}:\n{ex}")
            return
        mp["undo"].append((dest, video, idx, name))
        mp_record(video, name, "manual", dest)
        mp["idx"] += 1
        mp_show_current()

    def mp_skip(self=None):
        if not mp["reviewing"] or mp["idx"] >= len(mp["queue"]):
            return
        video, _ = mp["queue"][mp["idx"]]
        mp_record(video, "—", "skipped", "")
        mp["idx"] += 1
        mp_show_current()

    def mp_undo():
        if not mp["reviewing"]:
            return
        if not mp["undo"]:
            mp_status.set("Nothing to undo."); return
        dest, orig, idx, name = mp["undo"].pop()
        try:
            shutil.move(str(dest), str(orig))
        except Exception as ex:
            messagebox.showerror(APP_NAME, f"Could not undo:\n{ex}")
            return
        for iid in reversed(mp_tree.get_children()):
            v = mp_tree.item(iid)["values"]
            if v[0] == orig.name and v[1] == name:
                mp_tree.delete(iid)
                break
        mp["rows"] = [r for r in mp["rows"]
                      if not (r["file"] == orig.name and r["map"] == name)]
        mp["idx"] = idx
        mp_show_current()

    def mp_finish_review():
        mp["reviewing"] = False
        mp_clear_strip()
        tally = Counter(r["map"] for r in mp["rows"] if r["map"] != "—")
        skipped = sum(1 for r in mp["rows"] if r["how"] == "skipped")
        parts = ", ".join(f"{k}: {v}" for k, v in sorted(tally.items()))
        mp_status.set(f"Done. {sum(tally.values())} clip(s) filed"
                      + (f" ({parts})" if parts else "")
                      + (f", {skipped} skipped" if skipped else "") + ".")
        mp_bar["value"] = 1000
        if mp["rows"] and mp["folder"]:
            try:
                write_map_report(mp["folder"], mp["rows"])
            except Exception:
                pass
        if mp["snap_dir"] and Path(mp["snap_dir"]).exists():
            if messagebox.askyesno(APP_NAME, "All clips sorted.\n\n"
                                             "Delete the snapshot cache now?"):
                purge_snaps(mp["folder"], lambda m: post("mp_status", m))
        mp_end()

    def mp_end():
        mp["running"] = False
        mp["reviewing"] = False
        mp_start.configure(state="normal")
        mp_cancel_btn.configure(state="disabled")

    def mp_key(action):
        """Number/letter shortcuts, but only on this tab and not while typing."""
        def handler(event):
            try:
                if book.index(book.select()) != 2:
                    return
                focused = root.focus_get()
            except Exception:
                return
            if isinstance(focused, (ttk.Entry, tk.Entry, ttk.Combobox, ttk.Spinbox)):
                return
            action()
            return "break"
        return handler

    for _i in range(9):
        root.bind(str(_i + 1), mp_key(lambda i=_i: (
            mp_choose(mp["maps"][i]) if i < len(mp["maps"]) else None)))
    root.bind("0", mp_key(lambda: mp_choose(OTHER_MAP)))
    for _k in ("s", "S"):
        root.bind(_k, mp_key(mp_skip))
    for _k in ("z", "Z"):
        root.bind(_k, mp_key(mp_undo))

    # ===================================================================== #
    #                          shared plumbing
    # ===================================================================== #
    def pick_dir(var, title):
        p = filedialog.askdirectory(title=title)
        if p:
            var.set(p)

    def pick_input():
        p = filedialog.askdirectory(title="Choose the folder of clips")
        if not p:
            return
        fz_in.set(p)
        if not fz_out.get().strip():          # sensible default the user can change
            fz_out.set(str(Path(p).parent / f"{Path(p).name}_trimmed"))

    def reveal(target, fallback):
        target = Path(target) if target else None
        if target is None or not target.exists():
            target = Path(fallback) if fallback else None
        if target is None or not target.exists():
            messagebox.showinfo(APP_NAME, "Nothing to open yet."); return
        if not open_in_finder(target):
            messagebox.showerror(APP_NAME, f"Could not open {target}")

    def preflight():
        if not ffmpeg or not ffprobe:
            messagebox.showerror(
                APP_NAME, "ffmpeg was not found.\n\nInstall it with:\n    brew install ffmpeg")
            return False
        return True

    def current_settings():
        return {
            "best_play": {
                "lead_in": safe_float(bp_lead.get(), BP_DEFAULTS["lead_in"]),
                "scan_fps": max(0.5, safe_float(bp_fps.get(), BP_DEFAULTS["scan_fps"])),
                "region": bp_region.get(),
                "threads": max(1, int(bp_threads.get() or auto_threads())),
                "folder": bp_folder.get().strip(),
            },
            "freeze": {
                **FZ_DEFAULTS,
                "freeze_duration": safe_float(fz_dur.get(), FZ_DEFAULTS["freeze_duration"]),
                "unchanged_pct": safe_float(fz_pct.get(), FZ_DEFAULTS["unchanged_pct"]),
                "pixel_tol": int(safe_float(fz_tol.get(), FZ_DEFAULTS["pixel_tol"])),
                "keep_tail": safe_float(fz_keep.get(), FZ_DEFAULTS["keep_tail"]),
                "extra_trim": safe_float(fz_extra.get(), FZ_DEFAULTS["extra_trim"]),
                "tail_window": safe_float(fz_window.get(), FZ_DEFAULTS["tail_window"]),
                "workers": max(1, int(safe_float(fz_workers.get(), auto_workers()))),
                "fast_tail": bool(fz_fast.get()),
                "preview": bool(fz_preview.get()),
                "copy_unchanged": bool(fz_copy.get()),
                "exact_cut": bool(fz_exact.get()),
                "in_folder": fz_in.get().strip(),
                "out_folder": fz_out.get().strip(),
            },
            "maps": {
                **MAP_DEFAULTS,
                "folder": mp_folder.get().strip(),
                "maps": mp_maps.get(),
                "auto": bool(mp_auto.get()),
                "region": mp_region.get(),
                "snaps": max(1, int(safe_float(mp_snaps.get(), MAP_DEFAULTS["snaps"]))),
                "spread": mp_spread.get(),
                "snap_width": int(mp_cfg["snap_width"]),
                "threads": int(mp_cfg["threads"]),
                "interval": float(mp_cfg["interval"]),
                "min_hits": int(mp_cfg["min_hits"]),
                "snap_interval": float(mp_cfg["snap_interval"]),
            },
        }

    def safe_float(v, fallback):
        try:
            return float(v)
        except (TypeError, ValueError):
            return float(fallback)

    # ---------------------------- Best Play run ---------------------------
    def bp_stop():
        bp["cancel"].set()
        bp_status.set("Finishing the current clip, then stopping…")
        bp_cancel_btn.configure(state="disabled")

    def bp_go():
        folder = bp_folder.get().strip()
        if not folder or not Path(folder).is_dir():
            messagebox.showwarning(APP_NAME, "Choose a valid folder of clips."); return
        if not preflight():
            return
        ocr, note = pick_ocr()
        if ocr is None:
            messagebox.showerror(APP_NAME, note); return
        if note:
            messagebox.showwarning(APP_NAME, note)
        bp_engine.set(f"Reader: {ocr.name}")
        videos = list_videos(folder)
        if not videos:
            messagebox.showinfo(APP_NAME, "No video files in that folder."); return
        for i in bp_tree.get_children():
            bp_tree.delete(i)
        bp["cancel"] = threading.Event()
        bp["running"] = True
        bp_start.configure(state="disabled")
        bp_cancel_btn.configure(state="normal")
        save_settings(current_settings())
        conf = current_settings()["best_play"]
        threading.Thread(target=bp_work, args=(Path(folder), videos, conf, ocr),
                         daemon=True).start()

    def bp_work(folder, videos, conf, ocr):
        rows = []
        total = len(videos)
        tmp_root = Path(tempfile.mkdtemp(prefix="bestplay_"))
        try:
            for n, v in enumerate(videos, 1):
                if bp["cancel"].is_set():
                    break
                post("bp_status", f"[{n}/{total}]  {v.name}  — scanning for BEST PLAY…")

                def progress(done, dur, _n=n):
                    frac = (_n - 1 + (done / dur if dur else 1)) / total
                    post("bp_bar", max(0.0, min(1.0, frac)))

                r = process_one(v, folder, conf, ocr, tmp_root, progress,
                                bp["cancel"], ffmpeg, ffprobe)
                if r["status"] != "cancelled":
                    rows.append(r)
                    post("bp_row", r)
                post("bp_bar", n / total)
            if rows:
                try:
                    write_report(folder, rows)
                except Exception as ex:
                    post("bp_status", f"Could not write the report: {ex}")
        except Exception as ex:
            post("fail", str(ex))
        finally:
            shutil.rmtree(tmp_root, ignore_errors=True)
            post("bp_done", rows)

    def bp_finish(rows):
        bp["running"] = False
        bp_start.configure(state="normal")
        bp_cancel_btn.configure(state="disabled")
        hits = sum(1 for r in rows if r["status"] == "hit")
        miss = sum(1 for r in rows if r["status"] == "miss")
        errs = sum(1 for r in rows if r["status"] == "error")
        stopped = " (stopped early)" if bp["cancel"].is_set() else ""
        bp_status.set(f"Done{stopped}. {hits} trimmed into {OUT_HITS}/, {miss} moved to "
                      f"{OUT_MISSES}/, {errs} error(s).")
        if not stopped:
            bp_bar["value"] = 1000

    # --------------------------- Freeze Tail run --------------------------
    def fz_stop():
        fz["cancel"].set()
        fz["confirm"]["answer"] = False
        fz["confirm"]["event"].set()
        fz_status.set("Stopping…")
        fz_cancel_btn.configure(state="disabled")

    def fz_go():
        inp, outp = fz_in.get().strip(), fz_out.get().strip()
        if not inp or not Path(inp).expanduser().exists():
            messagebox.showwarning(APP_NAME, "Choose a valid input folder."); return
        if not outp:
            messagebox.showwarning(APP_NAME, "Choose an output folder, separate from the input.")
            return
        in_res = Path(inp).expanduser().resolve()
        out_res = Path(outp).expanduser().resolve()
        if in_res == out_res:
            messagebox.showwarning(APP_NAME,
                                   "The output folder must be DIFFERENT from the input folder.")
            return
        if out_res in in_res.parents or in_res in out_res.parents:
            if not messagebox.askyesno(
                    APP_NAME,
                    "The output folder is inside the input folder (or the other way round).\n\n"
                    "That works, but a later run will pick up the output clips as input.\n\n"
                    "Continue?"):
                return
        if not preflight():
            return
        if _numpy() is None:
            messagebox.showerror(APP_NAME,
                                 "The Freeze Tail tab needs numpy.\n\nInstall it with:\n"
                                 "    pip3 install numpy")
            return
        videos = list_input(inp)
        if not videos:
            messagebox.showinfo(APP_NAME, "No video files found there."); return
        for i in fz_tree.get_children():
            fz_tree.delete(i)
        fz["cancel"] = threading.Event()
        fz["running"] = True
        fz["plans"] = []
        fz_start.configure(state="disabled")
        fz_cancel_btn.configure(state="normal")
        save_settings(current_settings())
        conf = current_settings()["freeze"]
        threading.Thread(target=fz_work, args=(videos, Path(outp).expanduser(), conf),
                         daemon=True).start()

    def fz_confirm(trims, removed, copies, anomalies, errors, widened):
        """Ask on the main thread, wait on the worker thread."""
        box = fz["confirm"]
        box["answer"] = None
        box["event"].clear()

        def ask():
            lines = [f"{trims} clip(s) have a trailing freeze to trim.",
                     f"About {removed:.1f}s ({removed / 60:.1f} min) of frozen tail "
                     f"will be removed.",
                     f"{copies} clip(s) have no freeze."]
            if widened:
                lines.append(f"{widened} clip(s) needed a wider scan — check those cuts.")
            if anomalies:
                lines.append(f"{anomalies} clip(s) look almost entirely static and "
                             f"will be skipped.")
            if errors:
                lines.append(f"{errors} clip(s) could not be scanned.")
            lines.append("\nWrite the output now?")
            box["answer"] = messagebox.askyesno(APP_NAME, "\n".join(lines))
            box["event"].set()

        root.after(0, ask)
        box["event"].wait()
        return bool(box["answer"])

    def fz_work(videos, out_dir, conf):
        total = len(videos)
        workers = max(1, min(int(conf["workers"]), total))
        plans = []
        try:
            post("fz_status", f"Scanning {total} clip(s) for trailing freezes "
                              f"({workers} at a time)…")
            done = [0]
            lock = threading.Lock()

            def scan(v):
                try:
                    p = plan_for(v, out_dir, conf, ffmpeg, ffprobe, fz["cancel"])
                except Exception as ex:
                    p = {"video": v, "status": "error", "msg": str(ex), "total": 0,
                         "widened": False, "last_motion": None, "cut": None,
                         "removed": 0.0, "out": None, "result": ""}
                with lock:
                    done[0] += 1
                    post("fz_bar", 0.5 * done[0] / total)
                    post("fz_scanned", p)
                return p

            with ThreadPoolExecutor(max_workers=workers) as ex:
                plans = list(ex.map(scan, videos))
            if fz["cancel"].is_set():
                post("fz_done", plans); return

            plans.sort(key=lambda p: p["video"].name.lower())
            resolve_out_names(plans)
            trims, copies, anomalies, errors, widened, removed = freeze_summary(plans)
            post("fz_status",
                 f"{len(trims)} to trim (~{removed:.1f}s of freeze), {len(copies)} unchanged, "
                 f"{len(anomalies)} anomalies, {len(errors)} errors.")

            if conf.get("preview", True):
                if not fz_confirm(len(trims), removed, len(copies), len(anomalies),
                                  len(errors), len(widened)):
                    post("fz_status", "Cancelled after the preview. Nothing was written.")
                    post("fz_done", plans)
                    return

            todo = [p for p in plans if p["status"] in ("trim", "copy")]
            if not todo:
                post("fz_done", plans); return
            post("fz_status", f"Writing {len(todo)} clip(s) to {out_dir}…")
            done[0] = 0

            def run(p):
                r = execute_plan(p, ffmpeg, conf, fz["cancel"])
                with lock:
                    done[0] += 1
                    post("fz_bar", 0.5 + 0.5 * done[0] / len(todo))
                    post("fz_written", r)
                return r

            with ThreadPoolExecutor(max_workers=workers) as ex:
                list(ex.map(run, todo))
            try:
                write_freeze_report(out_dir, plans)
            except Exception as ex:
                post("fz_status", f"Could not write the report: {ex}")
        except Exception as ex:
            post("fail", str(ex))
        finally:
            post("fz_done", plans)

    def fz_row_values(p):
        return (p["video"].name, p["status"],
                hhmmss(p.get("cut")),
                f"{p['removed']:.1f}s" if p.get("removed") else "—",
                p.get("result", "") or ("waiting" if p["status"] in ("trim", "copy") else "—"),
                ("wider scan; " if p.get("widened") else "") + (p.get("msg") or ""))

    def fz_upsert(p):
        key = p["video"].name
        for iid in fz_tree.get_children():
            if fz_tree.item(iid)["values"][0] == key:
                fz_tree.item(iid, values=fz_row_values(p), tags=(p["status"],))
                return
        fz_tree.insert("", "end", values=fz_row_values(p), tags=(p["status"],))
        fz_tree.see(fz_tree.get_children()[-1])

    def fz_finish(plans):
        fz["running"] = False
        fz_start.configure(state="normal")
        fz_cancel_btn.configure(state="disabled")
        trimmed = sum(1 for p in plans if p.get("result") == "trimmed")
        copied = sum(1 for p in plans if p.get("result") == "copied")
        skipped = sum(1 for p in plans if p.get("result") == "skipped")
        anomalies = sum(1 for p in plans if p["status"] == "anomaly")
        errors = sum(1 for p in plans if p["status"] == "error" or p.get("result") == "error")
        removed = sum(p["removed"] for p in plans if p.get("result") == "trimmed")
        stopped = " (stopped early)" if fz["cancel"].is_set() else ""
        if trimmed or copied or skipped:
            fz_status.set(
                f"Done{stopped}. {trimmed} trimmed ({removed:.1f}s of freeze removed), "
                f"{copied} copied unchanged, {skipped} skipped, {anomalies} anomalies, "
                f"{errors} error(s).")
            if not stopped:
                fz_bar["value"] = 1000
        elif not fz_status.get().startswith("Cancelled"):
            fz_status.set(f"Nothing written{stopped}. {anomalies} anomalies, {errors} error(s).")

    # ------------------------------ pump ----------------------------------
    def drain():
        try:
            while True:
                kind, payload = msg_q.get_nowait()
                if kind == "bp_status":
                    bp_status.set(payload)
                elif kind == "bp_bar":
                    bp_bar["value"] = payload * 1000
                elif kind == "bp_row":
                    r = payload
                    bp_tree.insert("", "end", tags=(r["status"],), values=(
                        r["file"],
                        {"hit": "BEST PLAY", "miss": "not found"}.get(r["status"], "error"),
                        hhmmss(r["banner"]), hhmmss(r["start"]),
                        r["output"] or "—", r["note"]))
                    bp_tree.see(bp_tree.get_children()[-1])
                elif kind == "bp_done":
                    bp_finish(payload)
                elif kind == "fz_status":
                    fz_status.set(payload)
                elif kind == "fz_bar":
                    fz_bar["value"] = payload * 1000
                elif kind in ("fz_scanned", "fz_written"):
                    fz_upsert(payload)
                elif kind == "fz_done":
                    fz_finish(payload)
                elif kind == "mp_status":
                    mp_status.set(payload)
                elif kind == "mp_bar":
                    mp_bar["value"] = payload * 1000
                elif kind == "mp_row":
                    r = payload
                    mp["rows"].append(r)
                    mp_tree.insert("", "end", tags=(r["how"],),
                                   values=(r["file"], r["map"], r["how"], r["dest"]))
                    mp_tree.see(mp_tree.get_children()[-1])
                elif kind == "mp_review":
                    mp["queue"] = payload
                    mp["idx"] = 0
                    mp["reviewing"] = True
                    mp["cancel"] = threading.Event()   # review is its own phase
                    mp_show_current()
                elif kind == "mp_done":
                    mp_end()
                    if mp["rows"] and mp["folder"]:
                        try:
                            write_map_report(mp["folder"], mp["rows"])
                        except Exception:
                            pass
                    if not mp_status.get().startswith(("Done", "Stopping")):
                        mp_status.set(mp_status.get())
                elif kind == "fail":
                    messagebox.showerror(APP_NAME, payload)
        except queue.Empty:
            pass
        root.after(120, drain)

    def on_close():
        busy = [n for n, st in (("Best Play", bp), ("Freeze Tail", fz),
                                ("Map Sorter", mp)) if st["running"]]
        if busy:
            if not messagebox.askyesno(
                    APP_NAME, f"{', '.join(busy)} still running. Quit anyway?"):
                return
            for st in (bp, fz, mp):
                st["cancel"].set()
            fz["confirm"]["event"].set()
        save_settings(current_settings())
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.after(120, drain)

    probe, _note = pick_ocr()
    label = f"Reader: {probe.name}" if probe else "No text reader installed"
    bp_engine.set(label)
    mp_engine.set(label)
    if not ffmpeg:
        for var in (bp_status, fz_status, mp_status):
            var.set("ffmpeg not found — run:  brew install ffmpeg")
    elif _numpy() is None:
        fz_status.set("numpy not found — run:  pip3 install numpy")
    root.mainloop()


def main():
    folder = None
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if args:
        folder = args[0]
        if not Path(folder).is_dir():
            sys.exit(f"Not a folder: {folder}")
    run_gui(preset_folder=folder)


if __name__ == "__main__":
    main()
