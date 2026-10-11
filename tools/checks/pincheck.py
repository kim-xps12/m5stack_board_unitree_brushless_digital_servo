"""Pin assignment of every part against the specification (docs/design.md and the datasheets).

Checks, for the schematic (netlist exported with kicad-cli) and for the board (pad nets):
- every pin of every part is on the expected net, and the named pins have the expected function
  (so a swapped symbol, footprint or pin numbering shows up), with no missing or extra pins;
- the LCSC part numbers;
- the silkscreen next to the connectors: "Rx Tx V G" over the J2 pins, "+" / "-" beside the J1 pins,
  "Sig / BAT / GND" beside the rows of the servo ports.
usage: pincheck.py <board.kicad_pcb> <schematic.kicad_sch>
Exit status 1 on any mismatch.
"""
import os
import re
import subprocess
import sys
import tempfile

import pcbnew

KICAD_CLI = os.environ.get('KICAD_CLI', '/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli')
NC = None   # a pin that must stay unconnected

# ref: (LCSC, {pin: (net, schematic pin function or '' when the symbol does not name it)})
PORT = {'1': ('GND', 'Pin_1'), '2': ('/BAT', 'Pin_2'), '3': ('/signal', 'Pin_3')}   # servo header: 1 GND, 2 VCC, 3 SIGNAL
SPEC = {
    # connectors
    'J1': ('C428721', {'1': ('GND', 'Pin_1'), '2': ('/BAT_IN', 'Pin_2')}),                   # XT30UPB-M: 1 = -, 2 = +
    'J2': ('C7429580', {'1': ('GND', 'Pin_1'), '2': ('+5V', 'Pin_2'),                        # Grove: black, red,
                        '3': ('/TX', 'Pin_3'), '4': ('/RX', 'Pin_4')}),                      # yellow = host TX, white = host RX
    'J3': ('C131339', PORT), 'J4': ('C131339', PORT), 'J5': ('C131339', PORT),
    'J6': ('C131339', PORT), 'J7': ('C131339', PORT),
    # ICs (TI DBV / Torex MR pinouts)
    'U1': ('C7835', {'1': (NC, 'NC'), '2': ('/RC', ''), '3': ('GND', 'GND'),                 # 74LVC1G14: 1 NC, 2 A, 4 Y
                     '4': ('/TXEN', ''), '5': ('+3.3V', 'VCC')}),
    'U2': ('C5446', {'1': ('GND', 'GND'), '2': ('+3.3V', 'VO'), '3': ('+5V', 'VI')}),        # XC6206P332MR: 1 VSS, 2 VOUT, 3 VIN
    'U3': ('C7834', {'1': ('/TXEN', ''), '2': ('/TX', ''), '3': ('GND', 'GND'),              # 74LVC1G126: 1 OE, 2 A, 4 Y
                     '4': ('/BUS', ''), '5': ('+3.3V', 'VCC')}),
    'U4': ('C23654', {'1': ('/TXEN', ''), '2': ('/BUS', ''), '3': ('GND', 'GND'),            # 74LVC1G125: 1 /OE, 2 A, 4 Y
                      '4': ('/RX', ''), '5': ('+3.3V', 'VCC')}),
    # fuse: J1 + -> F1 -> BAT (holder = two Keystone 3557 clips; the fuse itself is user supplied)
    'F1': ('C2680614', {'1': ('/BAT_IN', ''), '2': ('/BAT', '')}),
    # polarised parts
    'D1': ('C7502691', {'1': ('/TX', 'K'), '2': ('/RC', 'A')}),                              # cathode on TX: TX low pulls RC low
    'C7': ('C3445238', {'1': ('/BAT', ''), '2': ('GND', '')}),                               # pin 1 = +
    # passives (either way round)
    'R1': ('C23231', {'1': ('/TX', ''), '2': ('/RC', '')}),
    'R2': ('C23182', {'1': ('/BUS', ''), '2': ('/signal', '')}),
    'R3': ('C25804', {'1': ('+3.3V', ''), '2': ('/BUS', '')}),
    'R4': ('C4190', {'1': ('+3.3V', ''), '2': ('GND', '')}),
    'C1': ('C14663', {'1': ('+3.3V', ''), '2': ('GND', '')}),
    'C4': ('C14663', {'1': ('+3.3V', ''), '2': ('GND', '')}),
    'C5': ('C14663', {'1': ('+3.3V', ''), '2': ('GND', '')}),
    'C2': ('C15849', {'1': ('+5V', ''), '2': ('GND', '')}),
    'C3': ('C15849', {'1': ('+3.3V', ''), '2': ('GND', '')}),
    'C6': ('C14858', {'1': ('/RC', ''), '2': ('GND', '')}),
    'TP1': ('', {'1': ('/TXEN', '1')}),
}
SWAPPABLE = {'R1', 'R2', 'R3', 'R4', 'C1', 'C2', 'C3', 'C4', 'C5', 'C6'}   # non-polarised: pin order does not matter
# silkscreen labels: text -> (ref, pin) it must sit next to
LABELS = {'Rx': ('J2', '4'), 'Tx': ('J2', '3'), 'V': ('J2', '2'), 'G': ('J2', '1'),
          'Sig': ('J3', '3'), 'BAT': ('J3', '2'), 'GND': ('J3', '1')}
FP_LABELS = {('J1', '+'): '2', ('J1', '-'): '1'}

errors = []


def same(pins_got, pins_want, ref):
    if ref in SWAPPABLE:
        return sorted(n for n, _ in pins_got.values()) == sorted(n for n, _ in pins_want.values())
    return all(pins_got.get(p, (None,))[0] == n for p, (n, _) in pins_want.items())


def netlist(sch):
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, 'n.net')
        subprocess.run([KICAD_CLI, 'sch', 'export', 'netlist', '--format', 'kicadsexpr', '-o', out, sch],
                       check=True, capture_output=True)
        s = open(out).read()
    pins, lcsc = {}, {}
    comps = s[:s.find('(libparts')]
    for m in re.finditer(r'\(comp \(ref "([^"]+)"\)', comps):
        k = comps.find('(comp (ref "', m.end())
        f = re.search(r'\(field \(name "LCSC"\) "([^"]*)"\)', comps[m.end():k if k > 0 else None])
        lcsc[m.group(1)] = f.group(1) if f else ''
    nets = s[s.find('(nets'):]
    for m in re.finditer(r'\(net\s+\(code "?\d+"?\)\s+\(name "([^"]*)"\)', nets):
        k = nets.find('(net ', m.end())
        for ref, pin, fn in re.findall(r'\(node \(ref "([^"]+)"\) \(pin "([^"]+)"\)(?: \(pinfunction "([^"]*)"\))?',
                                       nets[m.end():k if k > 0 else None]):
            name = None if m.group(1).startswith('unconnected-') else m.group(1)
            pins.setdefault(ref, {})[pin] = (name, fn)
    return pins, lcsc


def check(where, pins, lcsc, functions):
    refs = {r for r in pins if not r.startswith('#')}
    for ref in sorted(set(SPEC) ^ refs):
        errors.append(f'{where}: {ref} is {"missing" if ref in SPEC else "not in the specification"}')
    for ref in sorted(set(SPEC) & refs):
        want_lcsc, want = SPEC[ref]
        got = pins[ref]
        if lcsc.get(ref, '') != want_lcsc:
            errors.append(f'{where}: {ref} LCSC {lcsc.get(ref)!r}, expected {want_lcsc!r}')
        if set(got) != set(want):
            errors.append(f'{where}: {ref} pins {sorted(got)}, expected {sorted(want)}')
            continue
        if not same(got, want, ref):
            errors.append(f'{where}: {ref} ' + ', '.join(f'{p}={got[p][0]}' for p in sorted(got)) +
                          '; expected ' + ', '.join(f'{p}={want[p][0]}' for p in sorted(want)))
        if functions:
            for p, (_, fn) in want.items():
                if fn and got[p][1] != fn:
                    errors.append(f'{where}: {ref} pin {p} function {got[p][1]!r}, expected {fn!r}')


board = pcbnew.LoadBoard(sys.argv[1])
T = pcbnew.ToMM
sch_pins, sch_lcsc = netlist(sys.argv[2])
check('schematic', sch_pins, sch_lcsc, True)
pcb_pins, pcb_lcsc = {}, {}
for fp in board.Footprints():
    ref = fp.GetReference()
    if ref.startswith('MH'):
        continue
    pcb_lcsc[ref] = fp.GetFieldText('LCSC') if fp.HasFieldByName('LCSC') else ''
    for pad in fp.Pads():
        net = pad.GetNetname()
        pcb_pins.setdefault(ref, {})[pad.GetNumber()] = (None if not net or net.startswith('unconnected-') else net, '')
check('board', pcb_pins, pcb_lcsc, False)


def pad_at(ref, pin):
    p = board.FindFootprintByReference(ref).FindPadByNumber(pin).GetPosition()
    return T(p.x), T(p.y)


def nearest(x, y, ref, horizontal):
    """The pin of ref whose pad lines up with (x, y): same column (horizontal = False) or same row."""
    fp = board.FindFootprintByReference(ref)
    return min(fp.Pads(), key=lambda p: abs((T(p.GetPosition().y) if horizontal else T(p.GetPosition().x)) -
                                            (y if horizontal else x))).GetNumber()


texts = [d for d in board.GetDrawings() if d.GetClass() == 'PCB_TEXT' and d.GetLayerName() == 'F.Silkscreen']
for text, (ref, pin) in LABELS.items():
    found = [d for d in texts if d.GetText() == text]
    if len(found) != 1:
        errors.append(f'silkscreen: {len(found)} labels "{text}"')
        continue
    x, y = T(found[0].GetPosition().x), T(found[0].GetPosition().y)
    got = nearest(x, y, ref, horizontal=(ref != 'J2'))
    if got != pin:
        errors.append(f'silkscreen: "{text}" sits by {ref} pin {got}, expected pin {pin}')
for (ref, text), pin in FP_LABELS.items():
    fp = board.FindFootprintByReference(ref)
    found = [i for i in fp.GraphicalItems() if i.GetClass() == 'PCB_TEXT' and i.GetText() == text]
    if len(found) != 1:
        errors.append(f'silkscreen: {len(found)} labels "{text}" in {ref}')
        continue
    x, y = T(found[0].GetPosition().x), T(found[0].GetPosition().y)
    got = nearest(x, y, ref, horizontal=True)
    if got != pin:
        errors.append(f'silkscreen: "{text}" sits by {ref} pin {got}, expected pin {pin}')

for e in errors:
    print('NG', e)
n = sum(len(p) for _, p in SPEC.values())
print(f'pincheck: NG ({len(errors)})' if errors else
      f'pincheck: OK ({len(SPEC)} parts, {n} pins in the schematic and on the board, LCSC, connector labels)')
sys.exit(1 if errors else 0)
