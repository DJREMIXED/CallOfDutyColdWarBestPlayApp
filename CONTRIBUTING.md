# Contributing

Thanks for looking. This is a small tool built for a specific job — sorting and
trimming Cold War gameplay captures — and it's maintained by one person in his
spare time. That shapes everything below.

## Before you write code

**Open an issue first** for anything bigger than a typo. It's disappointing for
both of us if you spend an evening on a feature I'd rather not maintain. A short
"would you take a patch that does X?" saves that.

Things likely to be accepted:

- Bug fixes, especially with a test that fails before and passes after
- Support for map names, banners or scoreboard layouts from other Call of Duty titles
- Making detection more forgiving of real footage that currently slips through
- Documentation that clears up something that confused you

Things likely to be declined:

- New third-party dependencies (see below)
- Anything that reaches the network
- Large refactors that touch every file
- Windows or Linux ports — not because they're unwelcome in principle, but because
  I can't test or support them

## How the code is put together

One file, `fan_cave_studio.py`, in four parts:

| Part | What lives there |
|---|---|
| Shared helpers | file listing, ffprobe wrappers, settings, safe non-overwriting paths |
| Best Play engine | Vision OCR, banner matching, stream-copy trimming |
| Freeze Tail engine | frame sampling, motion comparison, trim planning |
| Map Sorter engine | scoreboard reading, map matching, snapshots, moves |
| `run_gui()` | all three tabs, built on one `ttk.Notebook` |

Two rules that the code follows throughout and that patches should keep:

1. **Never overwrite a user's file.** Every move, copy and trim goes through
   `unique_path()`, so a name collision becomes `name (2).mp4` instead of
   destroying something.
2. **Never touch Tk from a worker thread.** Background work posts messages onto a
   queue; the `drain()` pump on the main thread is the only thing that updates
   widgets. This is a real crash source in tkinter, not a style preference.

Style: plain standard-library Python, 4-space indent, lines under ~95 characters.
No formatter is enforced. Comments should explain *why*, not restate the code.

## Dependencies

The app deliberately runs on almost nothing: `numpy`, the Apple Vision bindings,
and `ffmpeg` on the PATH. There was an OpenCV/pytesseract era and removing it made
the app faster and about 90 MB smaller.

Every dependency is code that runs on someone else's machine, so a PR that adds one
needs to make a case for it. Versions are pinned in `requirements.txt` and
`requirements-build.txt`; if your change needs a version bump, say so in the PR
description.

## Tests

There's a headless suite that generates its own clips with ffmpeg — no sample
footage needed. Run it before opening a PR:

```bash
python3 tests/test_units_bp.py      # Best Play engine
python3 tests/test_units_fz.py      # Freeze Tail engine
python3 tests/test_units_mp.py      # Map Sorter engine
python3 tests/test_pipeline_bp.py   # Best Play, end to end
python3 tests/test_gui_tabs.py      # all three tabs, driven through the real window
```

The GUI tests open real windows. On Linux, run them under `xvfb-run`.

If you're changing detection behaviour, add a case to the relevant test rather than
adjusting an assertion so it passes. The tests are built around clips with known
ground truth (a banner burned in at exactly 20.0s, a freeze starting at exactly
12.0s) — the point is that a change either preserves that accuracy or doesn't.

## Opening a pull request

- One change per PR. A bug fix and a refactor in the same branch is hard to review.
- Say what problem it solves and how you tested it.
- Keep the diff readable — no reformatting of untouched lines.
- Note if you used an AI assistant. That's fine; it just changes how closely I read it.

## What review looks like

I read every line before merging, and I'll be blunt about why: a merged pull request
runs on other people's Macs, and I'm the one vouching for it. So expect questions
about anything that:

- changes `build_mac_studio.command` or the requirements files — that code runs on a
  contributor's machine during install, and it's the most sensitive thing in the repo
- adds a `subprocess` call to anything other than `ffmpeg`, `ffprobe`, `tesseract` or `open`
- imports `urllib`, `requests`, `socket`, or otherwise touches the network
- uses `eval`, `exec`, `base64` decoding, or long unreadable string literals
- writes files outside the folder the user picked

None of these are automatically rejections — there might be a good reason. But I'll
ask, and if the answer isn't clear I'll pass. Please don't take that personally; a
small project has to be conservative about what it ships.

Reviews may take a while. If a PR sits for weeks it's inertia, not disdain — a nudge
is welcome.

## Reporting a security problem

Don't open a public issue. See [SECURITY.md](SECURITY.md).

## Licence

By contributing you agree your work is released under the [MIT Licence](LICENSE),
the same terms as the rest of the project.
