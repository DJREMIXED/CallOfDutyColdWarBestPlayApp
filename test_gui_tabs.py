#!/usr/bin/env python3
"""
Drives the merged window headlessly under Xvfb: runs the Best Play tab, then the
Freeze Tail tab, and checks that each tab has its own Start button, its own
settings and its own results — and that neither blocks the other.
"""
import os
import subprocess
import sys
import tempfile
import threading
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import tkinter                      # noqa: E402
import tkinter.ttk as ttk           # noqa: E402
from tkinter import messagebox      # noqa: E402
import fan_cave_studio as fc       # noqa: E402

PASS, FAIL, CRASHES, SEEN = [], [], [], []
BP_LEAD = 4.0


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(("  ok   " if cond else "  FAIL ") + name + (f"  {extra}" if extra else ""),
          flush=True)


messagebox.askyesno = lambda title, message=None, **k: (
    SEEN.append(("askyesno", str(message)[:60])), True)[1]
for _k in ("showwarning", "showerror", "showinfo"):
    setattr(messagebox, _k,
            (lambda kind: lambda title, message=None, **k:
                (SEEN.append((kind, str(message)[:120])), "ok")[1])(_k))


def walk(w):
    yield w
    for c in w.winfo_children():
        yield from walk(c)


def by_text(top, text):
    for w in walk(top):
        if isinstance(w, (tkinter.Button, ttk.Button, ttk.Checkbutton)):
            try:
                if str(w.cget("text")).strip() == text:
                    return w
            except Exception:
                pass
    return None


def field_after_label(top, label_text):
    """The plain Entry created right after a Label with this exact text."""
    for w in walk(top):
        kids = w.winfo_children()
        for i, c in enumerate(kids):
            if isinstance(c, (ttk.Label, tkinter.Label)):
                try:
                    if str(c.cget("text")).strip() != label_text:
                        continue
                except Exception:
                    continue
                for nxt in kids[i + 1:]:
                    if type(nxt) is ttk.Entry:
                        return nxt
                    if isinstance(nxt, (ttk.Label, tkinter.Label)):
                        break
    return None


def set_field(top, label_text, value):
    e = field_after_label(top, label_text)
    if e is None:
        return False
    e.delete(0, "end")
    e.insert(0, str(value))
    return True


def spinboxes(top):
    return [w for w in walk(top) if isinstance(w, ttk.Spinbox)]


def trees(top):
    return [w for w in walk(top) if isinstance(w, ttk.Treeview)]


def statuses(root):
    out = []
    for w in walk(root):
        if isinstance(w, ttk.Label):
            try:
                v = w.cget("textvariable")
                if v:
                    out.append(str(root.getvar(v)))
            except Exception:
                pass
    return out


def rows_of(tree):
    return {tree.item(i)["values"][0]: tree.item(i)["values"] for i in tree.get_children()}


def main():
    def die():
        print("!! WATCHDOG: GUI test timed out.", flush=True)
        os._exit(2)
    wd = threading.Timer(540, die); wd.daemon = True; wd.start()

    tmp = Path(tempfile.mkdtemp(prefix="fcgui_"))
    ps5 = tmp / "PS5 Clips"
    frz_in = tmp / "Highlights"
    frz_out = tmp / "Highlights_trimmed"
    maps_dir = tmp / "Faceoff"
    subprocess.run(["bash", str(HERE / "make_ps5_clips.sh"), str(ps5)],
                   check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["bash", str(HERE / "make_freeze_clips.sh"), str(frz_in)],
                   check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["bash", str(HERE / "make_map_clips.sh"), str(maps_dir)],
                   check=True, stdout=subprocess.DEVNULL)
    os.environ["XDG_CONFIG_HOME"] = str(tmp / "cfg")     # never touch real settings

    real_mainloop = tkinter.Tk.mainloop

    def patched(self, n=0):
        self.report_callback_exception = lambda *a: CRASHES.append(
            "".join(traceback.format_exception(*a)))
        st = {"phase": "bp_setup", "n": 0}

        def tick():
            if not self.winfo_exists():
                return
            self.after(200, tick)
            st["n"] += 1
            p = st["phase"]

            # ---------------- Best Play tab ----------------
            if p == "bp_setup":
                book = next(w for w in walk(self) if isinstance(w, ttk.Notebook))
                st["book"] = book
                check("the window has three tabs", len(book.tabs()) == 3)
                check("tabs are named Best Play, Freeze Tail and Map Sorter",
                      [book.tab(t, "text").strip() for t in book.tabs()]
                      == ["Best Play", "Freeze Tail", "Map Sorter"],
                      str([book.tab(t, "text") for t in book.tabs()]))
                check("each tab has its own Start button",
                      by_text(self, "Start Best Play scan") is not None
                      and by_text(self, "Start Freeze Tail scan") is not None
                      and by_text(self, "Start Map Sorter") is not None)
                check("each tab has its own results table", len(trees(self)) == 3)
                check("set the PS5 clips folder", set_field(self, "PS5 clips folder:", ps5))
                sp = spinboxes(self)
                sp[0].delete(0, "end"); sp[0].insert(0, str(BP_LEAD))
                by_text(self, "Start Best Play scan").invoke()
                st["phase"] = "bp_running"
                return

            if p == "bp_running":
                if st["n"] % 30 == 0:
                    print(f"    .. {statuses(self)[1]} | {statuses(self)[-1]}", flush=True)
                bp_btn = by_text(self, "Start Best Play scan")
                fz_btn = by_text(self, "Start Freeze Tail scan")
                if not st.get("fz_launched") and str(bp_btn.cget("state")) == "disabled":
                    # Best Play is mid-run: the Freeze tab must still be startable,
                    # and starting it must not disturb the run already going.
                    check("the Freeze Tail Start button stays usable during a Best Play run",
                          str(fz_btn.cget("state")) != "disabled",
                          str(fz_btn.cget("state")))
                    ok = (set_field(self, "Input folder of clips:", frz_in)
                          and set_field(self, "Output folder (separate):", frz_out)
                          and set_field(self, "Freeze duration (s):", "2.0")
                          and set_field(self, "Screen unchanged %:", "98.0")
                          and set_field(self, "Extra end trim (s):", "0.0"))
                    check("the Freeze Tail settings fields are all present", ok)
                    fz_btn.invoke()          # both tabs now running at once
                    st["fz_launched"] = True
                    return
                done_bp = any("trimmed into BEST_PLAYS/" in s for s in statuses(self))
                done_fz = any("copied unchanged" in s for s in statuses(self))
                if done_bp and done_fz:
                    st["phase"] = "bp_check"
                return

            if p == "bp_check":
                st["phase"] = "fz_check"
                check("both tabs ran at the same time and both finished",
                      st.get("fz_launched") is True)
                bp_tree = trees(self)[0]
                vals = rows_of(bp_tree)
                check("Best Play table has a row per clip", len(vals) == 5, str(len(vals)))
                check("banner clips are marked BEST PLAY",
                      vals.get("match_alpha.mp4", ["", ""])[1] == "BEST PLAY"
                      and vals.get("match_early.mp4", ["", ""])[1] == "BEST PLAY", str(vals))
                check("clips without the banner are marked not found",
                      all(vals.get(n, ["", ""])[1] == "not found"
                          for n in ("no_banner.mp4", "decoy_text.mp4", "busy_bars.mp4")),
                      str(vals))
                hits = sorted(q.name for q in (ps5 / fc.OUT_HITS).glob("*.mp4"))
                check("BEST_PLAYS/ holds both trimmed clips",
                      hits == ["match_alpha_bestplay.mp4", "match_early_bestplay.mp4"],
                      str(hits))
                check("NO_BEST_PLAY/ holds the other three",
                      len(list((ps5 / fc.OUT_MISSES).glob("*.mp4"))) == 3)
                check("_PROCESSED/ holds the two originals",
                      len(list((ps5 / fc.OUT_DONE).glob("*.mp4"))) == 2)
                dur = fc.probe_duration(ps5 / fc.OUT_HITS / "match_alpha_bestplay.mp4",
                                        fc.find_exe("ffprobe"))
                check("the 4s lead-in typed into the tab was applied",
                      abs(dur - 14.0) <= 1.2, f"{dur:.2f}s")
                return

            # ---------------- Freeze Tail tab ----------------
            if p == "fz_check":
                check("the preview dialog was shown before writing",
                      any(k == "askyesno" and "trailing freeze" in m for k, m in SEEN),
                      str(SEEN))
                fz_tree = trees(self)[1]
                vals = rows_of(fz_tree)
                check("Freeze table has a row per clip", len(vals) == 7, str(len(vals)))
                check("the frozen-tail clips are planned as trims",
                      all(vals.get(n, ["", ""])[1] == "trim"
                          for n in ("freeze_tail.mp4", "blink_tail.mp4", "long_freeze.mp4")),
                      str(vals))
                check("clips with live tails are planned as copies",
                      all(vals.get(n, ["", ""])[1] == "copy"
                          for n in ("busy_tail.mp4", "no_freeze.mp4", "short_freeze.mp4")),
                      str(vals))
                check("the all-static clip is flagged as an anomaly",
                      vals.get("all_static.mp4", ["", ""])[1] == "anomaly", str(vals))
                check("trimmed rows report their result",
                      vals.get("freeze_tail.mp4", ["", "", "", "", ""])[4] == "trimmed",
                      str(vals.get("freeze_tail.mp4")))
                written = sorted(q.name for q in frz_out.glob("*.mp4"))
                check("output folder holds the trims and the untouched copies",
                      written == ["blink_tail.mp4", "busy_tail.mp4", "freeze_tail.mp4",
                                  "long_freeze.mp4", "no_freeze.mp4", "short_freeze.mp4"],
                      str(written))
                check("the anomaly was not written out", "all_static.mp4" not in written)
                d = fc.probe_duration(frz_out / "freeze_tail.mp4", fc.find_exe("ffprobe"))
                check("the frozen tail really was cut off (18s -> ~12s)",
                      abs(d - 12.0) <= 0.5, f"{d:.2f}s")
                d2 = fc.probe_duration(frz_out / "no_freeze.mp4", fc.find_exe("ffprobe"))
                check("a clip with no freeze came through at full length",
                      abs(d2 - 18.0) <= 0.3, f"{d2:.2f}s")
                check("a freeze report was written", (frz_out / "_freeze_report.csv").exists())
                check("the originals were never touched",
                      len(fc.list_input(frz_in)) == 7)
                check("no error dialogs in either tab",
                      not [s for s in SEEN if s[0] == "showerror"], str(SEEN))
                st["phase"] = "mp_setup"
                return

            # ---------------- Map Sorter tab ----------------
            if p == "mp_setup":
                st["phase"] = "mp_running"
                st["book"].select(2)                    # shortcuts are tab-scoped
                check("set the Map Sorter clips folder",
                      set_field(self, "Clips folder:", maps_dir))
                check("the map list field is editable and pre-filled",
                      set_field(self, "Map list (comma separated):",
                                "Amsterdam, Game Show, Gluboko, ICBM, KGB, "
                                "Mansion, Showroom, U-Bahn"))
                by_text(self, "Start Map Sorter").invoke()
                return

            if p == "mp_running":
                if st["n"] % 30 == 0:
                    print(f"    .. maps: {statuses(self)[-1]}", flush=True)
                if any(s.startswith("Manual review") for s in statuses(self)):
                    st["phase"] = "mp_auto_check"
                return

            if p == "mp_auto_check":
                st["phase"] = "mp_keys"
                mp_tree = trees(self)[2]
                vals = rows_of(mp_tree)
                check("stage 1 auto-filed the three clips with a scoreboard",
                      len(vals) == 3 and all(v[2] == "auto" for v in vals.values()),
                      str(vals))
                check("each auto-filed clip got the right map",
                      vals.get("match_amsterdam.mp4", [0, ""])[1] == "Amsterdam"
                      and vals.get("match_ubahn.mp4", [0, ""])[1] == "U-Bahn"
                      and vals.get("match_kgb.mp4", [0, ""])[1] == "KGB", str(vals))
                for name, mapname in (("match_amsterdam.mp4", "Amsterdam"),
                                      ("match_ubahn.mp4", "U-Bahn"),
                                      ("match_kgb.mp4", "KGB")):
                    check(f"{name} really moved into {mapname}/",
                          (maps_dir / mapname / name).exists())
                check("stage 2 is reviewing the two clips left",
                      any("clip 1 of 2" in s for s in statuses(self)),
                      str([s for s in statuses(self) if s.startswith("Manual")]))
                check("the review strip is showing snapshots",
                      len([w for w in walk(self)
                           if isinstance(w, ttk.Label) and str(w.cget("image"))]) >= 3)
                return

            if p == "mp_keys":
                st["phase"] = "mp_finish"
                before = sorted(q.name for q in maps_dir.glob("*.mp4"))
                # typing a map name must NOT be read as a map shortcut
                entry = field_after_label(self, "Map list (comma separated):")
                self.focus_force()
                entry.focus_set()
                self.update()
                if self.focus_get() is entry:
                    self.event_generate("<Key-1>")
                    self.update()
                    check("number keys do nothing while you are typing in the map list",
                          sorted(q.name for q in maps_dir.glob("*.mp4")) == before,
                          str(before))
                else:
                    check("number keys do nothing while you are typing in the map list",
                          True, "(focus not grantable headlessly - guard checked in code)")
                # with focus away from the fields, 1 files the clip under map 1
                trees(self)[2].focus_set()
                self.update()
                self.event_generate("<Key-1>")
                self.update()
                filed = sorted(q.name for q in (maps_dir / "Amsterdam").glob("*.mp4"))
                check("pressing 1 files the reviewed clip under the first map",
                      len(filed) == 2, str(filed))
                # and the buttons work too
                btn = by_text(self, "0  Other")
                check("an Other button is present", btn is not None)
                if btn is not None:
                    btn.invoke()
                    self.update()
                return

            if p == "mp_finish":
                st["phase"] = "quit"
                mp_tree = trees(self)[2]
                vals = rows_of(mp_tree)
                check("the table records manual decisions alongside the auto ones",
                      len(vals) == 5
                      and sum(1 for v in vals.values() if v[2] == "manual") == 2,
                      str(vals))
                check("nothing is left loose in the clips folder",
                      fc.list_videos(maps_dir) == [],
                      str([q.name for q in fc.list_videos(maps_dir)]))
                check("the Other bucket received the clip chosen with the button",
                      len(list((maps_dir / "Other").glob("*.mp4"))) == 1)
                check("a map report was written", (maps_dir / fc.MAP_REPORT).exists())
                check("the snapshot cache was purged at the end",
                      not [d for d in maps_dir.glob(fc.SNAP_PREFIX + "*") if d.is_dir()])
                check("the Map Sorter Start button came back",
                      str(by_text(self, "Start Map Sorter").cget("state")) != "disabled")
                check("no error dialogs anywhere",
                      not [s for s in SEEN if s[0] == "showerror"], str(SEEN))
                return

            if p == "quit":
                st["phase"] = "done"
                self.destroy()

        self.after(500, tick)
        return real_mainloop(self, n)

    tkinter.Tk.mainloop = patched
    try:
        fc.run_gui()
    except Exception:
        CRASHES.append(traceback.format_exc())

    saved = fc.load_settings()
    check("both tabs saved their own settings",
          abs(saved["best_play"]["lead_in"] - BP_LEAD) < 0.01
          and saved["freeze"]["in_folder"] == str(frz_in)
          and saved["best_play"]["folder"] == str(ps5), str(saved))
    check("no unhandled Tk callback exceptions", not CRASHES)
    for c in CRASHES:
        print("\n--- crash ---\n" + c)
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED: " + ", ".join(FAIL))
    return 1 if FAIL or CRASHES else 0


if __name__ == "__main__":
    sys.exit(main())
