#!/bin/bash
# Every check of the KiCad project; run from anywhere after each change. Reports go to production/checks/.
# Exit status 1 when a check fails.
#
#   tools/check_all.sh
#
# KICAD_CLI and KICAD_PYTHON override the KiCad 9 paths (default: the macOS application bundle).
set -u
cd "$(dirname "$0")/.."
N=m5stack_board_unitree_brushless_digital_servo
KC=${KICAD_CLI:-/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli}
PY=${KICAD_PYTHON:-/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3}
OUT=production/checks
mkdir -p "$OUT"
fail=0
quiet() { grep -v "wxApp\|memory leak\|assert\|Debug"; }
check() {   # check <name> <script> [args...]: run a pcbnew check, keep its report, fail on a nonzero exit
    local name=$1; shift
    "$PY" "$@" > "$OUT/$name.txt" 2>&1
    local st=$?
    quiet < "$OUT/$name.txt"
    [ $st = 0 ] || fail=1
}

echo "== DRC (with schematic parity)"
$KC pcb drc --schematic-parity --severity-all --exit-code-violations -o "$OUT/drc.rpt" $N.kicad_pcb >/dev/null 2>&1 || fail=1
grep "^\*\* Found" "$OUT/drc.rpt"

echo "== ERC"
$KC sch erc --severity-all --exit-code-violations -o "$OUT/erc.rpt" $N.kicad_sch >/dev/null 2>&1 || fail=1
grep "ERC" "$OUT/erc.rpt" | tail -1

echo "== pin assignment of every part (schematic and board), LCSC, connector labels"
check pincheck tools/checks/pincheck.py $N.kicad_pcb $N.kicad_sch

echo "== zone fills saved = fresh refill"
check fillcheck tools/checks/fillcheck.py $N.kicad_pcb

echo "== GND vias bulging into other nets' pour clearance"
check viacheck tools/checks/viacheck.py $N.kicad_pcb

echo "== copper other than GND within 3.5 mm of the mounting holes"
check holecheck tools/checks/holecheck.py $N.kicad_pcb

echo "== JLCPCB order files (production/)"
"$PY" tools/jlcpcb_export.py > "$OUT/export.txt" 2>&1 || fail=1
quiet < "$OUT/export.txt" | tail -1

# Optional: the JLCPCB (EasyEDA) land patterns are not in the repository (see work/README.md)
if [ -f work/jlc/verify_cpl.py ]; then
    # Land pattern differences (hand-soldering pads, a wider lead span) shift pads by up to 0.3 mm; a wrong
    # rotation or origin moves them by a pin pitch (0.9 mm or more)
    echo "== CPL: JLCPCB land patterns vs board pads (NG over 0.4 mm)"
    "$PY" work/jlc/verify_cpl.py "$PWD/work/jlc" $N.kicad_pcb production/bom_jlcpcb.csv production/cpl_jlcpcb.csv \
        > "$OUT/cpl_raw.txt" 2>&1 || { fail=1; quiet < "$OUT/cpl_raw.txt" | tail -3; }
    grep "max pad-centre error" "$OUT/cpl_raw.txt" > "$OUT/cpl.txt"
    awk '{ e = $(NF - 1); if (e > m) m = e; if (e > 0.4) { print "NG " $0; bad = 1 } }
         END { printf "%d parts, max pad-centre error %.3f mm\n", NR, m; exit bad }' "$OUT/cpl.txt" || fail=1
else
    echo "== CPL check skipped (work/jlc/ not present)"
fi

if [ $fail = 0 ]; then echo "== ALL OK"; else echo "== NG (reports in $OUT/)"; fi
exit $fail
