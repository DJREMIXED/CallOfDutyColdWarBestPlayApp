# Security

## Reporting a problem

**Please don't open a public issue for a security problem.** Report it privately so
there's a chance to fix it before it's public knowledge.

- Email: **`djremixed@icloud.com`**
- Or use the repository host's private reporting: on GitHub, *Security → Report a
  vulnerability*; on Bitbucket, message the repository admin directly.

Useful things to include: what you found, how to reproduce it, what an attacker could
actually do with it, and how you'd like to be credited.

You'll get an acknowledgement within about a week. This is a spare-time project, so a
fix may take longer than that — but you'll be told where it stands rather than left
guessing. If a fix ships, the release notes will credit you unless you'd rather stay
anonymous.

## What this app does on your machine

Worth stating plainly, because you're being asked to run an unsigned app that reads
your video files.

**It does:**

- read the video files in the folder you choose
- run `ffmpeg` and `ffprobe` to sample frames and cut clips
- ask macOS's built-in Vision framework to read text from those sampled frames
- write output files, and move clips, **only inside the folders you selected**
- store your settings at
  `~/Library/Application Support/Fan Cave Studio/clip_trimmer.json`
- write temporary snapshots into a system temp folder, deleted when the run ends,
  and (Map Sorter only) a `_mapsort_snaps_*` cache in your clips folder that you can
  purge from the app

**It does not:**

- make any network connection — there is no networking code in the app at all
- collect analytics, telemetry, or send crash reports
- require an account, a licence key, or any credentials
- ask for elevated privileges (`sudo` is never needed, for installing or running)
- read or write anything outside the folders you picked

You don't have to take that on faith. It's a single Python file — search it for
`urllib`, `requests`, `socket`, or `http` and you'll find nothing.

## Verifying what you downloaded

The app is built from source **on your own machine**, by a build script you can read
before you run it. That's deliberate: there's no prebuilt binary to tamper with in
transit.

Before running `build_mac_studio.command` for the first time, it's reasonable to open
it in a text editor. It's about a hundred lines. It should only:

1. check that `python3`, `tkinter` and `ffmpeg` are present
2. create a virtual environment in `.buildenv_studio/`
3. `pip install` the pinned packages in `requirements.txt` and `requirements-build.txt`
4. run PyInstaller

If you're reading a copy that does anything else — downloads from an unfamiliar URL,
asks for `sudo`, installs a package not listed in the requirements files — **you're
not looking at the official version. Don't run it.**

Dependency versions are pinned so that a compromised upstream release can't silently
reach a build. If you want to go further, `pip install --require-hashes` is compatible
with these files once hashes are added.

## Scope

In scope:

- anything that would let a malicious *video file* cause the app to run code, write
  outside the chosen folders, or delete data
- the build script installing something other than what the requirements files list
- the app losing or overwriting a user's original footage
- anything sending data off the machine

Out of scope:

- macOS Gatekeeper warnings on first launch. Expected — the app isn't notarised.
  See the README.
- vulnerabilities in `ffmpeg` itself. Report those to
  [the ffmpeg project](https://ffmpeg.org/security.html) and update via
  `brew upgrade ffmpeg`.
- detection accuracy. A missed banner or a wrongly sorted map is a bug, not a
  security issue — open a normal issue for those.

## For maintainers of forks

If you fork this and distribute your own build, please change the app name and bundle
identifier so users can tell your build from this one. And consider signing and
notarising it — a signed build lets macOS verify it hasn't been tampered with between
you and the person running it.
