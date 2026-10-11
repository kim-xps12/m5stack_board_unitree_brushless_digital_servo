#!/usr/bin/env python3
"""Write the JLCPCB PCBA order files (Gerber zip, BOM, CPL) to production/.

Run with the Python bundled with KiCad 9 (it provides pcbnew), from the repository root:

    /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 \
        tools/jlcpcb_export.py

Parts are matched by the "LCSC" field of each symbol. The CPL is corrected for the JLCPCB land
patterns (EasyEDA footprints), which differ from the KiCad footprints in rotation and, for the JST
connectors, in origin (KiCad: pin 1, JLCPCB: body centre). The corrections were found by fitting
each JLCPCB land pattern to the KiCad pads by pin function (diode cathode, IC pin 1, connector body);
check the placement preview when ordering anyway.
"""
import csv
import math
import os
import re
import subprocess
import sys
import zipfile

import pcbnew

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOARD = os.path.join(ROOT, 'm5stack_board_unitree_brushless_digital_servo.kicad_pcb')
OUT = os.path.join(ROOT, 'production')
KICAD_CLI = os.environ.get('KICAD_CLI', '/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli')

# LCSC part -> (rotation to add [deg, CCW], JLCPCB origin in KiCad footprint coordinates [mm])
CORRECTION = {
    'C7502691': (0, (0, 0)),       # RB751V-40 (hongjiacheng) SOD-323; pin 1 = cathode on the left, as in KiCad
    'C7835': (180, (0, 0)),        # SN74LVC1G14DBVR   SOT-23-5
    'C7834': (180, (0, 0)),        # SN74LVC1G126DBVR  SOT-23-5
    'C23654': (270, (0, 0)),       # SN74LVC1G125DBVR  SOT-23-5, drawn pin 1 bottom-left
    'C5446': (180, (0, 0)),        # XC6206P332MR-G    SOT-23
    'C131339': (180, (2.0, 0)),    # JST B3B-PH-K-S: pin 1 on the other side, origin at the body centre
    'C428721': (0, (2.5, 0)),      # Amass XT30UPB-M (pin 1 = -)
}
# Footprints that JLCPCB assembles as several parts: LCSC -> (comment, [(designator suffix, pad number, rotation to add)]).
# F1, the MINI blade fuse holder, is two Keystone 3557 clips; each sits at the middle of its two tails. Clip A
# (pads 1) faces +x in the footprint, i.e. the JLCPCB (EasyEDA) land pattern turned by 180 degrees.
SPLIT = {
    'C2680614': ('Keystone 3557 fuse clip', [('A', '1', 180), ('B', '2', 0)]),
}
GERBER_LAYERS = ['F.Cu', 'B.Cu', 'F.Paste', 'B.Paste', 'F.Silkscreen', 'B.Silkscreen', 'F.Mask', 'B.Mask',
                 'Edge.Cuts']


def lcsc(fp):
    return fp.GetFieldText('LCSC') if fp.HasFieldByName('LCSC') else ''


def cpl_row(fp):
    rot, (dx, dy) = CORRECTION.get(lcsc(fp), (0, (0, 0)))
    a = math.radians(fp.GetOrientationDegrees())
    x = pcbnew.ToMM(fp.GetPosition().x) + dx * math.cos(a) + dy * math.sin(a)
    y = pcbnew.ToMM(fp.GetPosition().y) - dx * math.sin(a) + dy * math.cos(a)
    side = 'Bottom' if fp.IsFlipped() else 'Top'
    angle = (fp.GetOrientationDegrees() + rot) % 360
    # Gerber coordinates: KiCad page coordinates with Y up
    return [fp.GetReference(), '%.4fmm' % x, '%.4fmm' % -y, side, '%g' % angle]


def split_rows(fp):
    """(designator, CPL row) of every JLCPCB part in a SPLIT footprint."""
    rows = []
    for suffix, number, rot in SPLIT[lcsc(fp)][1]:
        pads = [p for p in fp.Pads() if p.GetNumber() == number]
        x = sum(pcbnew.ToMM(p.GetPosition().x) for p in pads) / len(pads)
        y = sum(pcbnew.ToMM(p.GetPosition().y) for p in pads) / len(pads)
        ref = fp.GetReference() + suffix
        side = 'Bottom' if fp.IsFlipped() else 'Top'
        rows.append((ref, [ref, '%.4fmm' % x, '%.4fmm' % -y, side, '%g' % ((fp.GetOrientationDegrees() + rot) % 360)]))
    return rows


def main():
    board = pcbnew.LoadBoard(BOARD)
    os.makedirs(OUT, exist_ok=True)
    fps = sorted(board.GetFootprints(),
                 key=lambda f: [int(t) if t.isdigit() else t for t in re.split(r'(\d+)', f.GetReference())])

    bom, cpl, missing = {}, [], []
    for fp in fps:
        attr = fp.GetAttributes()
        if attr & (pcbnew.FP_EXCLUDE_FROM_BOM | pcbnew.FP_BOARD_ONLY | pcbnew.FP_DNP):
            continue
        part = lcsc(fp)
        if not part:
            missing.append(fp.GetReference())
            continue
        if part in SPLIT:
            key = (SPLIT[part][0], str(fp.GetFPID().GetLibItemName()), part)
            for ref, row in split_rows(fp):
                bom.setdefault(key, []).append(ref)
                cpl.append(row)
            continue
        key = (fp.GetValue(), str(fp.GetFPID().GetLibItemName()), part)
        bom.setdefault(key, []).append(fp.GetReference())
        if not attr & pcbnew.FP_EXCLUDE_FROM_POS_FILES:
            cpl.append(cpl_row(fp))
    if missing:
        sys.exit('no LCSC field: ' + ', '.join(missing))

    with open(os.path.join(OUT, 'bom_jlcpcb.csv'), 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['Comment', 'Designator', 'Footprint', 'LCSC Part #'])
        for (value, footprint, part), refs in bom.items():
            w.writerow([value, ','.join(refs), footprint, part])
    with open(os.path.join(OUT, 'cpl_jlcpcb.csv'), 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['Designator', 'Mid X', 'Mid Y', 'Layer', 'Rotation'])
        w.writerows(cpl)

    gerber_dir = os.path.join(OUT, 'gerber')
    os.makedirs(gerber_dir, exist_ok=True)
    for name in os.listdir(gerber_dir):
        os.remove(os.path.join(gerber_dir, name))
    subprocess.run([KICAD_CLI, 'pcb', 'export', 'gerbers', '--layers', ','.join(GERBER_LAYERS),
                    '--subtract-soldermask', '-o', gerber_dir, BOARD], check=True, stdout=subprocess.DEVNULL)
    subprocess.run([KICAD_CLI, 'pcb', 'export', 'drill', '--format', 'excellon', '--excellon-units', 'mm',
                    '--excellon-separate-th', '-o', gerber_dir + os.sep, BOARD], check=True, stdout=subprocess.DEVNULL)
    with zipfile.ZipFile(os.path.join(OUT, 'gerber_jlcpcb.zip'), 'w', zipfile.ZIP_DEFLATED) as z:
        for name in sorted(os.listdir(gerber_dir)):
            z.write(os.path.join(gerber_dir, name), name)

    print('BOM %d lines, CPL %d parts -> %s' % (len(bom), len(cpl), os.path.relpath(OUT, ROOT)))


if __name__ == '__main__':
    main()
