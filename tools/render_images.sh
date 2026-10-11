#!/bin/bash
# Screenshots of the schematic, the copper and the 3D model, and the README images.
#
#   tools/render_images.sh            # screenshots -> production/images/ (README images -> production/images/readme/)
#   tools/render_images.sh --readme   # also copy the README images whose content changed into docs/
#
# Needs KiCad 9 (kicad-cli), rsvg-convert, ImageMagick 7 (magick) and pdftoppm (poppler).
# The oblique 3D views are tilted 30 degrees from the top so that the silkscreen reads naturally.
set -eu
cd "$(dirname "$0")/.."
[ -d /opt/homebrew/bin ] && PATH=/opt/homebrew/bin:$PATH
ROOT=$PWD
N=m5stack_board_unitree_brushless_digital_servo
KC=${KICAD_CLI:-/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli}
FONT=${FONT:-/System/Library/Fonts/Helvetica.ttc}
OUT=$ROOT/production/images
mkdir -p "$OUT/readme"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
cd "$OUT"

svg() { $KC pcb export svg --mode-single --page-size-mode 2 --exclude-drawing-sheet --drill-shape-opt 2 "$@" "$ROOT/$N.kicad_pcb" >/dev/null 2>&1; }
render() { $KC pcb render --width 2000 --height 1400 --quality high --background opaque --floor "$@" "$ROOT/$N.kicad_pcb" >/dev/null 2>&1; }

# schematic
$KC sch export pdf -o "$TMP/sch.pdf" "$ROOT/$N.kicad_sch" >/dev/null 2>&1
pdftoppm -r 200 -png -singlefile "$TMP/sch.pdf" 1_schematic
# copper: front with silkscreen; back seen through the board, with the 3.5 mm screw circles of the mounting holes
svg -l F.Cu,F.Silkscreen,Edge.Cuts -o "$TMP/f.svg"
svg -l B.Cu,Edge.Cuts -o "$TMP/b.svg"
rsvg-convert -w 2000 -b '#001023' "$TMP/f.svg" -o 2_pcb_front.png
rsvg-convert -w 2000 -b '#001023' "$TMP/b.svg" -o "$TMP/b.png"
circles=()
for c in "200,200" "1800,200" "200,1200" "1800,1200"; do   # hole centres at 40 px/mm (5 mm from the edges)
    x=${c%,*}; y=${c#*,}
    circles+=(-draw "stroke-dasharray 14 10 circle $x,$y $((x + 140)),$y")
done
magick "$TMP/b.png" -fill none -stroke '#ffd400' -strokewidth 5 "${circles[@]}" 3_pcb_back_through.png
# 3D: top, oblique from four sides (tilt 30 degrees), bottom
render --side top -o 4_3d_top.png
render --side top --rotate 330,0,345 --zoom 0.9 -o 5_3d_iso_front.png
render --side top --rotate 330,0,60 --zoom 0.9 -o 6_3d_iso_left.png
render --side top --rotate 330,0,300 --zoom 0.9 -o 7_3d_iso_right.png
render --side top --rotate 330,0,160 --zoom 0.9 -o 8_3d_iso_back.png
render --side bottom -o 9_3d_bottom.png

# README images (docs/). The 3D renders vary slightly from run to run, so --readme copies an image only when
# some pixel differs by more than 20 %.
cd readme
magick ../5_3d_iso_front.png -crop 1540x1140+200+120 +repage -resize 1200x unitree_3d.png
magick ../4_3d_top.png -crop 1430x1025+280+175 +repage -resize 1100x unitree_3d_top.png
pdftoppm -r 150 -png -singlefile "$TMP/sch.pdf" unitree_schematic
svg --black-and-white -l F.Silkscreen,Edge.Cuts -o "$TMP/o.svg"
rsvg-convert -w 2000 -b white "$TMP/o.svg" -o "$TMP/o.png"
magick "$TMP/o.png" -bordercolor white -border 170x170 -background white -gravity north -extent 2340x1840 -gravity northwest \
    -font "$FONT" -fill black -stroke black -strokewidth 3 \
    -draw "line 170,80 2170,80" -draw "line 170,60 170,100" -draw "line 2170,60 2170,100" \
    -draw "line 70,170 70,1571" -draw "line 50,170 90,170" -draw "line 50,1571 90,1571" \
    -draw "line 370,1660 1970,1660" -draw "line 370,1640 370,1680" -draw "line 1970,1640 1970,1680" \
    -draw "line 2260,370 2260,1370" -draw "line 2240,370 2280,370" -draw "line 2240,1370 2280,1370" \
    -stroke none -pointsize 40 -annotate +1080+60 "50.0" -annotate +1100+1720 "40.0" \
    -annotate 270x270+50+940 "35.0" -annotate 270x270+2320+920 "25.0" \
    -pointsize 34 -annotate +190+1810 "unit: mm    M3 mounting holes (3.2 mm) x 4, 5.0 mm from the board edges" \
    unitree_layout.png

echo "screenshots: $OUT"
if [ "${1:-}" = "--readme" ]; then
    for f in unitree_3d unitree_3d_top unitree_schematic unitree_layout; do
        old=$ROOT/docs/$f.png
        if [ -f "$old" ] && [ "$(magick identify -format %wx%h "$old")" = "$(magick identify -format %wx%h $f.png)" ] &&
           [ "$(magick compare -metric AE -fuzz 20% "$old" $f.png null: 2>&1 | cut -d' ' -f1)" = "0" ]; then
            echo "docs/$f.png: unchanged"
        else
            cp $f.png "$old"; echo "docs/$f.png: updated"
        fi
    done
fi
