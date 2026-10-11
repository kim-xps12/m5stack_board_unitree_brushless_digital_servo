"""No copper other than GND within the screw circle of a mounting hole (MH1-MH4), on either side.

Screw heads, washers and metal spacers sit on both faces; only GND copper may lie under them.
Samples a 0.05 mm grid over the circle and reports the nets of the zone fills, tracks and vias found.
usage: holecheck.py <board.kicad_pcb> [radius mm (default 3.5)]
Exit status 1 when copper of another net is inside the circle.
"""
import math
import sys

import pcbnew

MM = pcbnew.FromMM
b = pcbnew.LoadBoard(sys.argv[1])
R = float(sys.argv[2]) if len(sys.argv) > 2 else 3.5
STEP = 0.05
bad = 0
for fp in sorted(b.GetFootprints(), key=lambda f: f.GetReference()):
    if not fp.GetReference().startswith('MH'):
        continue
    c = fp.GetPosition()
    nets = set()
    n = int(R / STEP)
    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            if math.hypot(i * STEP, j * STEP) > R:
                continue
            p = pcbnew.VECTOR2I(c.x + MM(i * STEP), c.y + MM(j * STEP))
            for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
                for z in b.Zones():
                    if z.IsOnLayer(layer) and z.HitTestFilledArea(layer, p):
                        nets.add((z.GetNetname(), pcbnew.LayerName(layer)))
                for t in b.GetTracks():
                    if t.IsOnLayer(layer) and t.HitTest(p):
                        nets.add((t.GetNetname(), pcbnew.LayerName(layer)))
    other = sorted(k for k in nets if k[0] != 'GND')
    bad += bool(other)
    print(f'{fp.GetReference()}: within r = {R} mm: ' + (f'NG {other}' if other else
          'GND only (' + ', '.join(sorted(l for _, l in nets)) + ')' if nets else 'no copper'))
print(f'holecheck: NG ({bad} hole(s))' if bad else 'holecheck: OK')
sys.exit(1 if bad else 0)
