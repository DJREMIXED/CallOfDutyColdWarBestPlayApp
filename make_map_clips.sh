#!/bin/bash
# Build a throwaway folder of Faceoff-ish clips, some with a scoreboard header
# naming the map inside the header region the sorter reads.
set -e
OUT="$1"
FONT="${FONT:-/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf}"
rm -rf "$OUT"; mkdir -p "$OUT"
SIZE="1280x720"

# $1 out  $2 duration  $3 header text ("" = none)  $4 from  $5 to  $6 y position
clip() {
  local vf="noise=alls=6:allf=t"
  if [ -n "$3" ]; then
    vf="$vf,drawtext=fontfile=$FONT:text='$3':fontcolor=white:fontsize=30:\
box=1:boxcolor=black@0.5:boxborderw=8:x=80:y=$6:enable='between(t,$4,$5)'"
  fi
  ffmpeg -hide_banner -loglevel error -y \
    -f lavfi -i "gradients=size=$SIZE:rate=30:c0=0x0d1b2a:c1=0x24405c:duration=$2" \
    -vf "$vf,format=yuv420p" \
    -c:v libx264 -preset ultrafast -g 30 -pix_fmt yuv420p "$1"
}

# y=80 sits inside the default "Scoreboard header" region (10%-18% of 720 = 72-129)
clip "$OUT/match_amsterdam.mp4" 12 "TEAM DEATHMATCH AMSTERDAM" 4 8 80
clip "$OUT/match_ubahn.mp4"     12 "KILL CONFIRMED U-BAHN"     2 6 80
clip "$OUT/match_kgb.mp4"       12 "DOMINATION KGB"            5 9 80
clip "$OUT/no_scoreboard.mp4"   10 ""                          0 0 80
# same header, but drawn low on the screen: invisible to the default region
clip "$OUT/header_low.mp4"      12 "TEAM DEATHMATCH GLUBOKO"   3 7 560

printf 'not a video' > "$OUT/._match_kgb.mp4"
ls -1 "$OUT"
