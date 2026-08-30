#!/bin/bash
# Build a throwaway folder of clips with trailing freezes at known timestamps.
set -e
OUT="$1"
rm -rf "$OUT"; mkdir -p "$OUT"
SIZE="640x360"
ENC=(-c:v libx264 -preset ultrafast -g 30 -pix_fmt yuv420p)

# motion then a dead-still tail:  $1 out  $2 seconds moving  $3 seconds frozen
plain() {
  ffmpeg -hide_banner -loglevel error -y \
    -f lavfi -i "testsrc2=size=$SIZE:rate=30:duration=$2" \
    -f lavfi -i "color=c=0x203040:size=$SIZE:rate=30:duration=$3" \
    -filter_complex "[0:v][1:v]concat=n=2:v=1:a=0,format=yuv420p[v]" \
    -map "[v]" "${ENC[@]}" "$1"
}

plain "$OUT/freeze_tail.mp4"  12 6
plain "$OUT/short_freeze.mp4" 16 1.5    # freeze under the 2s threshold
plain "$OUT/long_freeze.mp4"   4 12     # freeze longer than an 8s tail window

# frozen tail with a small icon blinking on and off (~0.7% of the screen).
# With "screen unchanged" at 98% this must STILL count as frozen.
ffmpeg -hide_banner -loglevel error -y \
  -f lavfi -i "testsrc2=size=$SIZE:rate=30:duration=12" \
  -f lavfi -i "color=c=0x203040:size=$SIZE:rate=30:duration=6" \
  -filter_complex "[1:v]drawbox=x=580:y=20:w=40:h=40:color=red:t=fill:\
enable='lt(mod(t,1),0.5)'[tail];[0:v][tail]concat=n=2:v=1:a=0,format=yuv420p[v]" \
  -map "[v]" "${ENC[@]}" "$OUT/blink_tail.mp4"

# a big block slides across the tail -- that IS motion, so there is no freeze
ffmpeg -hide_banner -loglevel error -y \
  -f lavfi -i "testsrc2=size=$SIZE:rate=30:duration=12" \
  -f lavfi -i "color=c=0x203040:size=$SIZE:rate=30:duration=6" \
  -f lavfi -i "color=c=white:size=160x160:rate=30:duration=6" \
  -filter_complex "[1:v][2:v]overlay=x='100+300*abs(sin(t*2))':y=100:eval=frame[tail];\
[0:v][tail]concat=n=2:v=1:a=0,format=yuv420p[v]" \
  -map "[v]" "${ENC[@]}" "$OUT/busy_tail.mp4"

# nothing but a static colour from the first frame -> anomaly
ffmpeg -hide_banner -loglevel error -y \
  -f lavfi -i "color=c=0x203040:size=$SIZE:rate=30:duration=10" \
  "${ENC[@]}" "$OUT/all_static.mp4"

# no freeze at all
ffmpeg -hide_banner -loglevel error -y \
  -f lavfi -i "testsrc2=size=$SIZE:rate=30:duration=18" \
  "${ENC[@]}" "$OUT/no_freeze.mp4"

printf 'not a video' > "$OUT/._freeze_tail.mp4"
ls -1 "$OUT"
