#!/bin/bash
# ============================================================================
# build_mac_studio.command — Double-click on a Mac to build FanCaveStudio.app
# ----------------------------------------------------------------------------
# One app, three tabs: Best Play, Freeze Tail and Map Sorter.
# Prereqs (one time):  brew install ffmpeg python-tk
# Then double-click this file. Finished app: dist/FanCaveStudio.app
# ============================================================================
set -Eeo pipefail   # no -u: some venv activate scripts read unset vars
cd "$(dirname "$0")"

APP_NAME="FanCaveStudio"
BUNDLE_ID="com.fancavestudio.cliptoolkit"
VENV=".buildenv_studio"

pause() { echo ""; read -n 1 -s -r -p "Press any key to close."; echo ""; }

on_error() {
  local code=$?
  echo ""
  echo "!! BUILD FAILED (exit $code) at line ${BASH_LINENO[0]}: ${BASH_COMMAND}"
  echo "!! Nothing was installed outside ./$VENV — fix the problem above and run again."
  pause
  exit "$code"
}
trap on_error ERR

echo ">> Checking prerequisites…"

if ! command -v python3 >/dev/null 2>&1; then
  echo "!! python3 not found. Install it with:  brew install python"
  pause; exit 1
fi
echo "   python3: $(python3 --version 2>&1)  ($(command -v python3))"
echo "   arch:    $(python3 -c 'import platform;print(platform.machine())')"

if ! python3 -c "import tkinter" >/dev/null 2>&1; then
  echo "!! This python3 has no tkinter, so the app cannot build or run."
  echo "   Fix with:  brew install python-tk"
  pause; exit 1
fi

if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
  echo "!! WARNING: ffmpeg/ffprobe not on PATH. The app builds, but neither tab"
  echo "   can run until you do:  brew install ffmpeg"
fi

if [ ! -f "fan_cave_studio.py" ]; then
  echo "!! fan_cave_studio.py is not next to this script. Keep both files together."
  pause; exit 1
fi

echo ">> Creating build environment…"
python3 -m venv "$VENV"
# shellcheck disable=SC1091
source "$VENV/bin/activate"
python -m pip install --upgrade pip >/dev/null

echo ">> Installing numpy (Freeze Tail) and Apple Vision bindings (Best Play, Map Sorter)…"
python -m pip install --upgrade numpy pyobjc-framework-Vision pyobjc-framework-Quartz

echo ">> Installing PyInstaller…"
python -m pip install --upgrade pyinstaller

python - <<'PY'
import sys
missing = []
for mod in ("numpy", "Vision", "Foundation"):
    try:
        __import__(mod)
    except Exception as ex:
        missing.append(f"{mod}: {ex}")
if missing:
    print("!! These did not import:\n   " + "\n   ".join(missing))
    sys.exit(1)
print("   numpy and the Vision bindings import cleanly.")
PY

echo ">> Cleaning previous build…"
rm -rf build "dist/$APP_NAME.app" "$APP_NAME.spec"

echo ">> Building app…"
pyinstaller --noconfirm --clean --windowed \
  --name "$APP_NAME" \
  --osx-bundle-identifier "$BUNDLE_ID" \
  --hidden-import objc --hidden-import Vision --hidden-import Foundation \
  --collect-submodules Vision --collect-submodules Foundation \
  --exclude-module cv2 --exclude-module opencv-python --exclude-module pytesseract \
  fan_cave_studio.py

if [ ! -d "dist/$APP_NAME.app" ]; then
  echo "!! PyInstaller finished but dist/$APP_NAME.app is missing."
  pause; exit 1
fi

deactivate || true

echo ""
echo ">> Done.  App is at:  $(pwd)/dist/$APP_NAME.app"
echo ">> First launch: right-click the app > Open (unsigned-app Gatekeeper)."
echo ">> Reminder: ffmpeg must be installed (brew install ffmpeg)."
pause
