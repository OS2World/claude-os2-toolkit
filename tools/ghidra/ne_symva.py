#!/usr/bin/env python3
"""
ne_symva.py - turn an NE module's .SYM symbols into the "0xVA name" form
ApplySymbols.java consumes, using this pipeline's NE addressing convention
(logical segment N -> pseudo-flat base N << 16, which Ghidra's 16-bit
protected mode renders back as 000N:offset).

Unlike the LX path there is no resolve-against-the-binary step: an NE .SYM's
segment numbers ARE the module's logical segment numbers, so the mapping is
exact and needs no image to resolve against.  Worth confirming once per module
family before relying on it - cross-check one ordinal in the module's own NE
entry table against the .SYM line for the same routine.

Marker ordering: IBM's .SYM files place linker and segment markers at the SAME
address as a real function (a module can have several _END / _START markers
sharing an address with a genuine routine).  ApplySymbols.java calls
createLabel(..., makePrimary=true), so whichever name is applied LAST is the
one that names the decompiled file.  Markers are therefore emitted first and
real names last, so the real function name wins.  Nothing is dropped; the
markers are still applied as labels.

Usage: ne_symva.py <symfile>            (writes "0xVA name" lines to stdout)
"""
import argparse
import os
import re
import sys

TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOOLS_DIR)
try:
    from sym2map import SymFile
except ImportError as e:
    sys.exit("ne_symva.py: cannot import sym2map.py (%s).\n"
             "  It is expected at %s/sym2map.py" % (e, TOOLS_DIR))

MARKER = re.compile(
    r'^_?[A-Za-z0-9]*(?:TEXT|BTXT|DATA|GROUP|SWAP\d*|BGRP|CODE|BSS)_?'
    r'(?:START|END)$')


def main():
    ap = argparse.ArgumentParser(
        description="Map an NE module's .SYM symbols to pseudo-flat VAs "
                    "(segment N at N<<16) for ApplySymbols.java.")
    ap.add_argument("symfile", help="the module's .SYM file")
    args = ap.parse_args()

    try:
        sf = SymFile(args.symfile)
    except (OSError, ValueError) as e:
        sys.exit("%s: not a readable MAPSYM .SYM file: %s" % (args.symfile, e))

    rows, segs = [], {}
    for seg in sf.segments:
        # Segment 0 holds absolutes/constants, which have no address here.
        # An offset above 0xFFFF cannot belong to a 16-bit NE segment.
        if seg.number == 0:
            continue
        for s in seg.symbols:
            if s.off > 0xFFFF:
                continue
            rows.append(((seg.number << 16) | s.off, s.name))
            segs[seg.number] = segs.get(seg.number, 0) + 1

    markers = sum(1 for _, n in rows if MARKER.match(n))
    rows.sort(key=lambda r: 0 if MARKER.match(r[1]) else 1)
    for va, name in rows:
        print('0x%08x %s' % (va, name))
    print('ne_symva: %d symbols (%d segment markers emitted first) across '
          'segments %s' % (len(rows), markers, sorted(segs.items())),
          file=sys.stderr)


if __name__ == '__main__':
    main()
