"""The zone fills saved in the board match a fresh refill (the plotted Gerbers use the saved fills).

Refills a copy in memory with the project's rules (.kicad_dru next to the board) and compares the copper.
usage: fillcheck.py <board.kicad_pcb> [tolerance mm2 (default 0.01)]
Exit status 1 when the copper differs by more than the tolerance.
"""
import sys
import pcbnew

TOL = float(sys.argv[2]) if len(sys.argv) > 2 else 0.01
b = pcbnew.LoadBoard(sys.argv[1])


def copper(board):
    """Per layer: the union of every zone fill and every pad on that layer."""
    out = {}
    for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
        s = pcbnew.SHAPE_POLY_SET()
        for z in board.Zones():
            if z.IsOnLayer(layer):
                s.BooleanAdd(z.GetFilledPolysList(layer))
        for fp in board.Footprints():
            for pad in fp.Pads():
                if pad.IsOnLayer(layer):
                    pad.TransformShapeToPolygon(s, layer, 0, pcbnew.FromMM(0.005), pcbnew.ERROR_INSIDE)
        s.Simplify()
        out[layer] = s
    return out


saved = copper(b)
pcbnew.ZONE_FILLER(b).Fill(b.Zones())
fresh = copper(b)
bad = 0
for layer in saved:
    x = saved[layer].CloneDropTriangulation()
    x.BooleanXor(fresh[layer])
    area = x.Area() / 1e12
    bad += area > TOL
    print(f'{pcbnew.LayerName(layer)}: saved vs refilled copper differs by {area:.4f} mm2')
print('fillcheck: NG (refill the zones and save)' if bad else 'fillcheck: OK')
sys.exit(1 if bad else 0)
