#!/bin/bash
# Build a throwaway folder of PS5-ish gameplay clips with a "BEST PLAY" banner
# burned in at known timestamps, so detection accuracy can be asserted.
#
# The background is a dark, noisy gradient rather than colour bars, because that
# is what console gameplay actually looks like behind an end-of-match banner.
set -e
OUT="$1"
FONT="${FONT:-/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf}"
rm -rf "$OUT"; mkdir -p "$OUT"

gameplay() {   # $1 out  $2 duration  $3 text ("" for none)  $4 from  $5 to
  local vf="noise=alls=6:allf=t"
  if [ -n "$3" ]; then
    vf="$vf,drawtext=fontfile=$FONT:text='$3':fontcolor=white:fontsize=64:box=1:\
boxcolor=black@0.55:boxborderw=24:x=(w-text_w)/2:y=(h*0.34):enable='between(t,$4,$5)'"
  fi
  ffmpeg -hide_banner -loglevel error -y \
    -f lavfi -i "gradients=size=1280x720:rate=30:c0=0x0d1b2a:c1=0x24405c:duration=$2" \
    -vf "$vf,format=yuv420p" \
    -c:v libx264 -preset ultrafast -g 30 -pix_fmt yuv420p "$1"
}

gameplay "$OUT/match_alpha.mp4"  30 "BEST PLAY"   20 26
gameplay "$OUT/match_early.mp4"  30 "BEST PLAY"    5 11
gameplay "$OUT/no_banner.mp4"    20 ""             0  0
gameplay "$OUT/decoy_text.mp4"   20 "TEST PLAYER" 10 16

# worst-case busy frame with no banner at all -- must not produce a false hit
ffmpeg -hide_banner -loglevel error -y \
  -f lavfi -i "testsrc=size=1280x720:rate=30:duration=15" \
  -c:v libx264 -preset ultrafast -g 30 -pix_fmt yuv420p "$OUT/busy_bars.mp4"

printf 'not a video' > "$OUT/._match_alpha.mp4"
ls -1 "$OUT"
