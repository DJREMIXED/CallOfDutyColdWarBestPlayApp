# Fan Cave Studio PRO — Clip Toolkit

**Batch-trim and organise *Call of Duty: Black Ops Cold War* gameplay captures on macOS.**

![Platform](https://img.shields.io/badge/platform-macOS-lightgrey)
![Apple Silicon](https://img.shields.io/badge/Apple%20Silicon-optimised-blue)
![Python](https://img.shields.io/badge/python-3.9%2B-green)
![License](https://img.shields.io/badge/license-MIT-brightgreen)

<img width="1244" height="860" alt="Screenshot 2026-08-30 at 8 41 07 PM" src="https://github.com/user-attachments/assets/6f37fb0a-4582-456f-95c4-043a6594bbc2" />

<img width="1236" height="857" alt="Screenshot 2026-08-30 at 8 41 35 PM" src="https://github.com/user-attachments/assets/af15bd0b-2c2a-4bd6-808d-0e1a2ed9bd56" />

<img width="1228" height="852" alt="Screenshot 2026-08-30 at 8 56 07 PM" src="https://github.com/user-attachments/assets/41bab4a2-6e56-43e3-81ea-83cf1f264aa6" />



If you record on a PlayStation 5, you end up with a folder of long captures where the
good part is thirty seconds buried in the middle, the tail is a frozen scoreboard, and
nothing tells you which map anything was on. This app does those three jobs for a whole
folder at a time, without you scrubbing a timeline.

It is one window with three tabs. **Each tab is a separate tool with its own folders,
its own settings and its own Start button** — use one, use all three, run two at once.
Nothing here uploads anything; every clip stays on your Mac.

| Tab | What it does |
|---|---|
| **Best Play** | Watches each clip for the on-screen words **BEST PLAY**, then cuts everything before that moment away. Clips where the banner never appears are moved aside instead. |
| **Freeze Tail** | Finds where the picture stops moving at the end of a clip and cuts the dead tail off, so a run of clips plays back with no pauses. |
| **Map Sorter** | Files clips into a folder per map — automatically for any clip where you opened the scoreboard, and with a five-thumbnail glance-and-press-a-number review for the rest. |

Built for Apple Silicon: text is read with **Apple's Vision framework** (the Neural Engine,
not a bundled OCR library) and video is decoded through **VideoToolbox**.

---

## Requirements

| | |
|---|---|
| **macOS** | Apple Silicon (M1 or newer) recommended. Intel Macs work but fall back to software decoding. |
| **ffmpeg** | `brew install ffmpeg` — required. The app will not scan without it. |
| **Python 3** | 3.9 or newer, with `tkinter`. Tested on 3.11 – 3.14. |

**About tkinter:** the installers from [python.org](https://www.python.org/downloads/macos/)
already include it — nothing extra to do. If you use Homebrew's Python instead, add it with
`brew install python-tk`.

Everything else — `numpy` and the Apple Vision bindings — is installed automatically by the
build script, into a throwaway virtual environment inside your project folder. Nothing is
installed system-wide.

> Don't have Homebrew? Install it from [brew.sh](https://brew.sh), then run `brew install ffmpeg`.

---

## Install

### 1. Get the two files

Download these into a folder of your own — Desktop, Documents, wherever:

- `build_mac_studio.command`
- `fan_cave_studio.py`

Either clone the repo, or use **Code → Download ZIP**, or open each file and hit the
**Download raw file** button. Keep both files **in the same folder** — the builder looks for
the Python file next to itself.

```bash
mkdir -p ~/Desktop/FCSP
# then move the two downloaded files into ~/Desktop/FCSP
```

### 2. Run the one-time builder

Open **Terminal** and `cd` into that folder. **No `sudo` — it is not needed and not wanted.**

```bash
cd ~/Desktop/FCSP
chmod +x build_mac_studio.command
./build_mac_studio.command
```

The `chmod` line is only needed once: files downloaded from a browser arrive without the
executable bit. After that you can just double-click `build_mac_studio.command` in Finder.

The builder checks your prerequisites, creates `.buildenv_studio/`, installs numpy and the
Vision bindings into it, and packages everything with PyInstaller. It takes a couple of
minutes. If anything goes wrong it stops, tells you which line failed, and leaves the
Terminal window open so you can actually read the error.

<details>
<summary><b>Example build output</b> (click to expand)</summary>

```
$ ./build_mac_studio.command
>> Checking prerequisites…
   python3: Python 3.14.5  (/Library/Frameworks/Python.framework/Versions/3.14/bin/python3)
   arch:    arm64
>> Creating build environment…
>> Installing numpy (Freeze Tail) and Apple Vision bindings (Best Play, Map Sorter)…
Collecting numpy
Collecting pyobjc-framework-Vision
Collecting pyobjc-framework-Quartz
...
Successfully installed numpy-2.5.2 pyobjc-core-12.2.2 pyobjc-framework-Cocoa-12.2.2
  pyobjc-framework-CoreML-12.2.2 pyobjc-framework-Quartz-12.2.2 pyobjc-framework-Vision-12.2.2
>> Installing PyInstaller…
Successfully installed pyinstaller-6.22.2 ...
   numpy and the Vision bindings import cleanly.
>> Cleaning previous build…
>> Building app…
40 INFO: PyInstaller: 6.22.2
40 INFO: Python: 3.14.5
52 INFO: Platform: macOS-26.6.1-arm64-arm-64bit-Mach-O
...
16661 INFO: Build complete! The results are available in: ~/Desktop/FCSP/dist

>> Done.  App is at:  ~/Desktop/FCSP/dist/FanCaveStudio.app
>> First launch: right-click the app > Open (unsigned-app Gatekeeper).
>> Reminder: ffmpeg must be installed (brew install ffmpeg).
Press any key to close.
```

`WARNING: Cache entry deserialization failed, entry ignored` lines from pip are harmless —
that is just pip discarding a stale download cache. Paths will show your own home folder.

</details>

### 3. Launch it

The finished app is one folder deeper, in `dist/`:

```
~/Desktop/FCSP/dist/FanCaveStudio.app
```

Drag it to your Applications folder if you like, or run it where it sits.

**First launch only:** the app is not code-signed or notarised, so macOS will refuse to open
it on a double-click. **Right-click the app → Open**, then confirm. If macOS still blocks it,
open **System Settings → Privacy & Security**, scroll down, and click **Open Anyway** next to
the message about FanCaveStudio. After that it opens normally forever.

To rebuild later — after pulling a new `fan_cave_studio.py`, say — just run
`./build_mac_studio.command` again. It cleans the old build itself.

---

## Using it

A pipeline that works well on a folder straight off the PS5, though the tabs are
independent and you can use any one alone:

> **1.** Best Play on the capture dump → **2.** Freeze Tail on the resulting `BEST_PLAYS/`
> folder → **3.** Map Sorter on the trimmed output.
>
> That way each stage runs once over a flat folder, and you finish with one tidy folder
> per map full of tight, front-and-back-trimmed highlights.

### Best Play

Point it at your clips folder, set **how many seconds before the banner** the clip should
start, and press **Start Best Play scan**.

Each clip is sampled a couple of frames a second, the sampled frames are read for the words
"BEST PLAY", and the first moment the banner appears is refined to about a twelfth of a
second. The clip is then cut from `banner − lead-in` to the end.

| Setting | What it's for |
|---|---|
| **Start the clip _N_ seconds before…** | Your lead-in. 4–6 seconds usually frames the play nicely. |
| **Look at** | Which part of the screen to read. `Center band` is the default and the fastest. Widen it if the banner sits somewhere else. |
| **Frames per second** | How often to sample. 2 is plenty; raise it only if a very short banner is being missed. |
| **OCR threads** | How many frames to read at once. Defaults to your core count minus two. |

Cuts are **stream copies** — no re-encode, no quality loss, a couple of seconds per clip.
The trade-off is that ffmpeg lands on the nearest keyframe *at or before* your cut point, so
a clip can start up to a second earlier than you asked, never later. That is the safe
direction for a lead-in.

**Where things go**, inside the folder you selected:

```
Your clips folder/
├── BEST_PLAYS/            ← the trimmed clips, plus _bestplay_report.csv
├── NO_BEST_PLAY/          ← clips where the banner never appeared, moved untouched
└── _PROCESSED/            ← the untrimmed originals of everything that was trimmed
```

Because everything leaves the top level, re-running never redoes work.

### Freeze Tail

Choose an input folder and a **separate** output folder, then **Start Freeze Tail scan**.

Frames are sampled a few times a second and compared with the one before. A sample counts as
"unchanged" when at least *X%* of the screen is within a small brightness tolerance of the
previous one — which is why a blinking mic icon or a small corner animation doesn't stop a
freeze from being detected. Only a **trailing** freeze is trimmed; a pause in the middle is
left alone.

| Setting | What it's for |
|---|---|
| **Freeze duration (s)** | How long the tail has to hold still before it counts. Default 2. |
| **Screen unchanged %** | 95–99 is the useful range. Higher = stricter, so small animations count as motion. |
| **Pixel sensitivity (0–255)** | How much a pixel has to change to count. Raise it to ignore compression noise. |
| **Keep tail (s)** | Leave a hair of freeze after the cut. 0 cuts exactly at the last motion. |
| **Extra end trim (s)** | Cut this much *more* off — handy for a map or transition card. |
| **Fast tail scan** | Only scan the last N seconds. If that whole window is static it automatically rescans the full clip. |
| **Preview first** | Show a summary and wait for your OK before anything is written. |
| **Also copy clips with no trailing freeze** | Keeps the output folder a complete set. |
| **Exact cut (re-encode)** | On = frame-exact end via VideoToolbox. Off = instant stream copy. |

Originals are **never modified** — output is written to the folder you chose, alongside
`_freeze_report.csv`. Clips that look static from the very first frame are flagged as
anomalies and skipped rather than mangled.

### Map Sorter

Point it at a folder of clips, check the map list is right, press **Start Map Sorter**.

**Stage 1 — automatic.** Cold War prints the map on the scoreboard header
("TEAM DEATHMATCH AMSTERDAM"). Any clip where you opened the scoreboard is read and filed
straight into that map's folder. No thumbnails, no prompt.

**Stage 2 — you decide.** Whatever is left gets a strip of snapshots. Glance at them and
press a key:

| Key | Action |
|---|---|
| `1`–`9` | File under that map |
| `0` | File under **Other** |
| `S` | Skip this clip, leave it where it is |
| `Z` | Undo the last move |

(Shortcuts only fire on this tab, and never while you're typing in a text field.)

The **map list is an editable field**, not baked into the app — change it for a different
playlist or a different game, press **Apply**, and the buttons and number keys rebuild to
match. It's remembered between launches.

Every clip is **moved** into `<your folder>/<MapName>/`, so quitting and reopening carries on
where you left off. A `_mapsort_report.csv` records what went where and whether stage 1 or you
decided it.

| Setting | What it's for |
|---|---|
| **Map list** | Comma separated. Duplicates and blanks are cleaned up; `/` and `:` are made folder-safe. |
| **Stage 1 checkbox** | Turn off to send every clip to manual review. |
| **Read** | Which part of the frame holds the scoreboard header. Widen it if map names are being missed. |
| **Snapshots** | How many review frames per clip (1–8). |
| **Spread mode** | `Across the whole clip` samples the full length; `First seconds` keeps the older 3-seconds-apart behaviour. |

Snapshots are cached in a `_mapsort_snaps_*` folder so a resumed session doesn't remake them.
**Purge snapshots** clears the cache, and you're offered the same at the end of a run.

---

## Good to know

- **Nothing is ever overwritten.** If a destination filename is taken, the new file becomes
  `name (2).mp4`. This applies to every move, copy and trim in all three tabs.
- **Cancel works.** Every tab has one, and it finishes the current clip cleanly rather than
  leaving a half-written file.
- **Each tab writes a CSV report** so you can see exactly what happened without opening
  every clip.
- **Two tabs can run at the same time.** Starting a Freeze Tail pass doesn't disturb a Best
  Play scan already in flight.
- **Everything is local.** No account, no network calls, no telemetry.

### Settings

Your settings for all three tabs are remembered in:

```
~/Library/Application Support/Fan Cave Studio/clip_trimmer.json
```

A couple of Map Sorter knobs live only in that file, to keep the window uncluttered:
`interval` (seconds between scoreboard samples, default `0.7`) and `min_hits` (how many
frames a map name must read on before it counts, default `2`). Quit the app before editing
it, or your changes will be written over on exit.

---

## Troubleshooting

**"ffmpeg not found"** — `brew install ffmpeg`, then restart the app. Both `ffmpeg` and
`ffprobe` come from that one package.

**The build fails with `no module named tkinter`** — your Python has no Tk. Either install
Python from [python.org](https://www.python.org/downloads/macos/) (includes it) or run
`brew install python-tk`.

**macOS won't open the app** — see [Launch it](#3-launch-it) above. Right-click → Open, or
System Settings → Privacy & Security → Open Anyway.

**"Reader: Tesseract" instead of Apple Vision** — the PyObjC bindings didn't install. Rerun
the builder; it verifies they import and stops if they don't. Tesseract still works, just
slower and less accurate.

**Best Play isn't finding the banner** — try `Look at → Full frame` first. If that finds it,
one of the narrower regions is cutting the banner off. Raising *Frames per second* to 3–4
helps if the banner is only up briefly. The matcher already tolerates ordinary OCR slips
(`8EST PLAY`, `BEST PLAV`, the two words read as separate lines).

**Map Sorter is sending everything to manual review** — the header region probably isn't
catching the map name. Switch **Read** to `Top strip (full width)` or `Full frame` and try
again. Also check the map list actually contains the map, spelled the way the scoreboard
spells it.

**Freeze Tail trims too much / too little** — *Screen unchanged %* is the dial you want.
Lower it (95) if real motion is being treated as a freeze; raise it (99) if small on-screen
animations are stopping freezes from being found. *Pixel sensitivity* is the second dial:
raise it to ignore compression noise.

**A clip is flagged as an anomaly** — it looked static from the first frame, so it was left
alone rather than cut down to nothing. Usually a recording that never really started.

---

## How it works

No bundled OCR engine and no OpenCV — both jobs go through frameworks already on your Mac:

- **Text recognition** — Apple's Vision framework (`VNRecognizeTextRequest`) at its fast
  recognition level, running on the Neural Engine. If PyObjC is missing, it falls back to a
  Tesseract CLI if you have one.
- **Video decoding** — ffmpeg with `-hwaccel videotoolbox`, with an automatic software retry
  for any file the hardware decoder refuses.
- **Sampling** — frames are cropped to the region of interest and downscaled *before* they're
  read, which is where most of the speed comes from.
- **Best Play** scans in 60-second windows and decodes the next window while it reads the
  current one, so ffmpeg and the reader overlap instead of taking turns. A hit ends the scan.
- **Freeze Tail** compares 160px-wide grayscale samples in numpy — the share of pixels that
  moved by more than your tolerance.
- **Cuts** are stream copies wherever an exact re-encode isn't required.

### Running from source

You don't have to build the `.app` at all:

```bash
pip3 install numpy pyobjc-framework-Vision pyobjc-framework-Quartz
python3 fan_cave_studio.py
```

### Tests

The repo includes a headless test suite — engine tests, plus GUI tests that drive the real
window and check what actually lands on disk. They generate their own test clips with ffmpeg,
so no sample footage is needed:

```bash
python3 tests/test_units_bp.py      # Best Play engine
python3 tests/test_units_fz.py      # Freeze Tail engine
python3 tests/test_units_mp.py      # Map Sorter engine
python3 tests/test_pipeline_bp.py   # Best Play, end to end
python3 tests/test_gui_tabs.py      # all three tabs, driven through the window
```

---

## Not tested on Windows

This is macOS-only in practice. The Vision text reader and VideoToolbox decoding are Apple
frameworks, and the builder is a `.command` shell script. The Python is portable enough that
it would probably start on Windows or Linux with Tesseract installed and software decoding,
but none of that is tested and there's no build script for it. Pull requests welcome.

---

## License

MIT — see [LICENSE](LICENSE). Use it, change it, ship it; just keep the copyright notice.

## Disclaimer

Not affiliated with, endorsed by, or connected to Activision, Treyarch or Sony. *Call of
Duty* and *Black Ops Cold War* are trademarks of their respective owners. This is a personal
tool for organising your own gameplay recordings.
