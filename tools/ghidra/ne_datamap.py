#!/usr/bin/env python3
"""
ne_datamap.py - annotate one exported data segment with its real symbol names,
each symbol's gap-derived size, and its initial bytes.

For understanding a 16-bit OS/2 component, the automatic data segment (DGROUP)
is as load-bearing as the code: it is the module's entire global state.  A .SYM
gives names and offsets but no sizes, so a symbol's size is taken as the gap to
the next symbol - an upper bound, exact for densely packed globals and wrong
wherever the linker left padding, which is why the size column is derived, not
declared.  Initial values come straight out of the exported segment image, so
a zero here means the image really holds zero.

Symbols sharing one offset (aliases, and linker markers) are collapsed onto a
single row with their names joined.

Usage:
    ne_datamap.py <symfile> <segnum> <segbin>

  symfile  the module's .SYM
  segnum   logical segment number to map (the NE segment, as the .SYM numbers it)
  segbin   that segment's exported image, from ne_seg_export.py
"""
import argparse
import os
import sys

TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOOLS_DIR)
try:
    from sym2map import SymFile
except ImportError as e:
    sys.exit("ne_datamap.py: cannot import sym2map.py (%s).\n"
             "  It is expected at %s/sym2map.py" % (e, TOOLS_DIR))


def main():
    ap = argparse.ArgumentParser(
        description="Map a data segment's symbols to sizes and initial values.")
    ap.add_argument("symfile", help="the module's .SYM file")
    ap.add_argument("segnum", type=int, help="logical segment number to map")
    ap.add_argument("segbin", help="that segment's .bin from ne_seg_export.py")
    args = ap.parse_args()

    try:
        sf = SymFile(args.symfile)
    except (OSError, ValueError) as e:
        sys.exit("%s: not a readable MAPSYM .SYM file: %s" % (args.symfile, e))

    syms = []
    for seg in sf.segments:
        if seg.number != args.segnum:
            continue
        for s in seg.symbols:
            syms.append((s.off, s.name))
    syms.sort()
    if not syms:
        sys.exit("%s: no symbols in segment %d" % (args.symfile, args.segnum))

    with open(args.segbin, "rb") as f:
        data = f.read()

    merged = []
    for off, name in syms:
        if merged and merged[-1][0] == off:
            merged[-1][1].append(name)
        else:
            merged.append([off, [name]])

    print('# segment %d (%s) - %d bytes, %d named symbols'
          % (args.segnum, os.path.basename(args.segbin), len(data), len(syms)))
    print('%-8s %-6s %-34s %s' % ('OFFSET', 'SIZE', 'NAME', 'INITIAL VALUE'))
    for i, (off, names) in enumerate(merged):
        end = merged[i + 1][0] if i + 1 < len(merged) else len(data)
        size = max(0, end - off)
        blob = data[off:off + min(size, 24)]
        if size == 2 and off + 2 <= len(data):
            val = '0x%04x' % int.from_bytes(data[off:off + 2], 'little')
        elif size == 4 and off + 4 <= len(data):
            val = '0x%08x' % int.from_bytes(data[off:off + 4], 'little')
        elif size == 1 and off < len(data):
            val = '0x%02x' % data[off]
        elif blob and blob.rstrip(b'\0') and all(32 <= c < 127 for c in blob.rstrip(b'\0')):
            val = repr(blob.rstrip(b'\0').decode('latin1'))
        elif not any(blob):
            val = '(zero)'
        else:
            val = blob.hex()
        print('%04x     %-6d %-34s %s' % (off, size, '/'.join(names), val))


if __name__ == '__main__':
    main()
