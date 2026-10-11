"""Vias whose copper reaches into another net's track clearance on a layer where the via's net has a pour.

There the pour merges with the via, so the via shows as a bulge in the pour edge beside the track.
usage: viacheck.py <board.kicad_pcb> [tolerance mm (default 0.05)]
Exit status 1 when a bulge exceeds the tolerance.
"""
import math, sys
import pcbnew

T = pcbnew.ToMM
b = pcbnew.LoadBoard(sys.argv[1])
TOL = float(sys.argv[2]) if len(sys.argv) > 2 else 0.05


def segdist(p, a, c):
    dx, dy = c[0] - a[0], c[1] - a[1]
    L = dx * dx + dy * dy
    t = 0 if L == 0 else max(0, min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def xy(v): return (T(v.x), T(v.y))


# pour clearance of each (net, layer)
pour = {}
for z in b.Zones():
    for layer in z.GetLayerSet().Seq():
        pour[(z.GetNetname(), layer)] = T(z.GetLocalClearance() or 0)
tracks = [t for t in b.GetTracks() if t.GetClass() == 'PCB_TRACK']
bad = 0
rows = []
for v in b.GetTracks():
    if v.GetClass() != 'PCB_VIA':
        continue
    p, r = xy(v.GetPosition()), T(v.GetWidth(pcbnew.F_Cu)) / 2
    for t in tracks:
        clr = pour.get((v.GetNetname(), t.GetLayer()))
        if clr is None or t.GetNetname() == v.GetNetname():
            continue
        gap = segdist(p, xy(t.GetStart()), xy(t.GetEnd())) - r - T(t.GetWidth()) / 2
        if gap < clr:
            ng = clr - gap > TOL
            bad += ng
            rows.append(f'{"NG" if ng else "ok"}  {v.GetNetname()} via ({p[0]:.2f}, {p[1]:.2f})  {t.GetLayerName()} '
                        f'{t.GetNetname()}  gap {gap:.3f} mm  bulge {clr - gap:.3f} mm')
for row in sorted(set(rows)):
    print(row)
print(f'viacheck: {bad} via bulge(s) over {TOL} mm' if bad else f'viacheck: OK (no via bulge over {TOL} mm)')
sys.exit(1 if bad else 0)
