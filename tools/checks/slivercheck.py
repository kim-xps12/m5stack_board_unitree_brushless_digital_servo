"""Thin strips of pour between a zone's outline and the pads, vias and tracks of other nets inside it.

The fill keeps the zone clearance from each item; when what is left between that and the zone outline is
narrower than the zone's minimum width, the fill drops it there and the pour edge gets a notch (and the
neighbouring pour a bump). Reports every strip narrower than the limit.
usage: slivercheck.py <board.kicad_pcb> [limit mm (default 0.5)]
Exit status 1 when a strip is narrower than the limit.
"""
import math
import sys

import pcbnew

T, MM = pcbnew.ToMM, pcbnew.FromMM
b = pcbnew.LoadBoard(sys.argv[1])
LIMIT = float(sys.argv[2]) if len(sys.argv) > 2 else 0.5


def segdist(p, a, c):
    dx, dy = c[0] - a[0], c[1] - a[1]
    L = dx * dx + dy * dy
    t = 0 if L == 0 else max(0, min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def chains(polyset):
    out = []
    for i in range(polyset.OutlineCount()):
        for c in [polyset.Outline(i)] + [polyset.Hole(i, h) for h in range(polyset.HoleCount(i))]:
            pts = [(T(c.CPoint(k).x), T(c.CPoint(k).y)) for k in range(c.PointCount())]
            out.append(list(zip(pts, pts[1:] + pts[:1])))
    return out


def items(layer):
    for fp in b.Footprints():
        for pad in fp.Pads():
            if pad.IsOnLayer(layer):
                yield f'{fp.GetReference()} pad {pad.GetNumber()}', pad
    for t in b.GetTracks():
        if t.IsOnLayer(layer):
            yield ('via' if t.GetClass() == 'PCB_VIA' else 'track'), t


bad = 0
rows = []
for z in b.Zones():
    clr, minw = T(z.GetLocalClearance() or 0), T(z.GetMinThickness())
    for layer in z.GetLayerSet().Seq():
        edges = [e for c in chains(z.Outline()) for e in c]
        for name, it in items(layer):
            if it.GetNetname() == z.GetNetname() or not z.Outline().Contains(it.GetPosition()):
                continue
            shape = pcbnew.SHAPE_POLY_SET()
            it.TransformShapeToPolygon(shape, layer, 0, MM(0.005), pcbnew.ERROR_INSIDE)
            verts = [p for c in chains(shape) for p, _ in c]
            d = min(segdist(v, a, c) for v in verts for a, c in edges)
            strip = d - clr
            if strip < LIMIT:
                bad += 1
                p = it.GetPosition()
                rows.append(f'NG  {z.GetNetname()} zone on {pcbnew.LayerName(layer)}: {name} [{it.GetNetname()}] at '
                            f'({T(p.x):.2f}, {T(p.y):.2f}): strip {strip:.3f} mm (min width {minw} mm)')
for r in sorted(set(rows)):
    print(r)
print(f'slivercheck: NG ({bad} strip(s) under {LIMIT} mm)' if bad else f'slivercheck: OK (no pour strip under {LIMIT} mm)')
sys.exit(1 if bad else 0)
