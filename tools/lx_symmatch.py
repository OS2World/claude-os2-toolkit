#!/usr/bin/env python3
r"""lx_symmatch.py - does this .SYM actually belong to this LX image?

WHY THIS EXISTS.  sym2map.py resolves a symbol as `object_base +
symbol_offset`, with segment number == object number, and it NEVER FAILS: a
.SYM from a DIFFERENT BUILD of the same module resolves perfectly cleanly to
wrong addresses, and lx_disasm.py then prints a confident disassembly that
starts mid-instruction. Nothing in either tool can notice, because nothing in
the .SYM format says which build it came from.

Measured on one such mismatched pair: applying a module's SMP-build .SYM to
the UNI build of the same module put one exported routine 0xd00 bytes off, so
the disassembly decoded `enter 0x4,0x0` as `sbb [0x8966],ah` - and the delta
GROWS from 0x570 to 0x1ec0 across a single object, so no constant correction
exists and no spot-check of one symbol would have found it.

THE INSTRUMENT.  The LX ENTRY TABLE is ground truth and needs no symbols: for
every export that carries a name in the resident or non-resident name table,
the entry table gives (object, offset) straight out of the image. Compare that
against what the .SYM says the same name resolves to. A matching pair agrees on
all of them.

IT DISCRIMINATES RATHER THAN PASS/FAIL, which is the property that makes it
worth having. Against one module's installed binary: the matching build's .SYM
agreed 32/32, the wrong build's 1/32, and a .SYM from a NEIGHBOURING RELEASE
22/32 - a partial match reads as a partial match, not as a pass.

SCOPE, so a green run is not over-read.  It checks only symbols that are ALSO
NAMED EXPORTS. For the module above that was 32 of ~2200 symbols, because the
module has 550 entry-table slots and 33 resident names. That is ample to detect
a build mismatch - a wrong build disagrees on essentially all of them - and it
is NOT proof that every internal symbol is right.

A module with few or no named exports cannot be checked this way AT ALL, and
the tool says so by reporting UNDECIDABLE rather than a percentage. This is the
common case for DEVICE DRIVERS, which typically export nothing by name: a small
sample would agree 1/1 with a .SYM from any build that happens to place that
one export identically, which reads as reassuring and decides nothing.

    lx_symmatch.py LXIMAGE SYMFILE

exit status:  0 = MATCH   1 = MISMATCH or PARTIAL   2 = UNDECIDABLE
"""
import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sym2map import LXImage, SymFile

DEFAULT_MIN_SAMPLE = 8


def tables(path):
    """(entry table, named exports) read straight out of the LX image.

    entries: ordinal -> (object number, offset)
    names:   exported name -> ordinal
    """
    with open(path, "rb") as f:
        d = f.read()
    if len(d) < 0x40 or d[:2] not in (b"MZ", b"ZM"):
        raise SystemExit("%s: not an MZ executable" % path)
    lxoff = struct.unpack_from("<I", d, 0x3c)[0]
    if d[lxoff:lxoff + 2] != b"LX":
        raise SystemExit("%s: not an LX image" % path)
    h = lxoff

    def u32(o):
        return struct.unpack_from("<I", d, h + o)[0]

    restab = h + u32(0x58)
    enttab = h + u32(0x5C)
    nrestab, cbnres = u32(0x88), u32(0x8C)   # a FILE offset, unlike the rest

    ents, o, ordn = {}, enttab, 1
    while True:
        cnt = d[o]
        o += 1
        if cnt == 0:
            break
        typ = d[o]
        o += 1
        if typ == 0:                 # empty bundle: spends ordinals, has no object
            ordn += cnt
            continue
        objn = struct.unpack_from("<H", d, o)[0]
        o += 2
        for _ in range(cnt):
            if typ == 1:
                ents[ordn] = (objn, struct.unpack_from("<H", d, o + 1)[0])
                o += 3
            elif typ == 2:
                ents[ordn] = (objn, struct.unpack_from("<H", d, o + 1)[0])
                o += 5
            elif typ == 3:
                ents[ordn] = (objn, struct.unpack_from("<I", d, o + 1)[0])
                o += 5
            elif typ == 4:           # forwarder: no address in this module
                o += 7
            else:
                raise SystemExit("unknown entry-table bundle type %d" % typ)
            ordn += 1

    def walk(a, b):
        r, o = {}, a
        while o < b:
            ln = d[o]
            if ln == 0:
                break
            r[d[o + 1:o + 1 + ln].decode("latin1")] = \
                struct.unpack_from("<H", d, o + 1 + ln)[0]
            o += 1 + ln + 2
        return r

    names = walk(restab, enttab)
    if cbnres:
        names.update(walk(nrestab, nrestab + cbnres))
    return ents, names


def main():
    ap = argparse.ArgumentParser(
        prog="lx_symmatch.py",
        description="Check whether a .SYM really belongs to an LX image, by "
                    "comparing named exports against the entry table.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
verdicts:
  MATCH        every checkable named export agrees
  MISMATCH     none agrees - a different build, or the wrong module entirely
  PARTIAL      some agree - typically a neighbouring release. NOT a pass
  UNDECIDABLE  too few named exports to decide (drivers usually export none)

exit status: 0 MATCH, 1 MISMATCH/PARTIAL, 2 UNDECIDABLE

run this BEFORE trusting sym2map.py or lx_disasm.py output: a wrong .SYM
resolves cleanly to wrong addresses and disassembles mid-instruction.
""")
    ap.add_argument("lximage", help="the LX image (.DLL, .EXE, .SYS ...)")
    ap.add_argument("symfile", help="the .SYM claimed to accompany it")
    ap.add_argument("--min-sample", type=int, default=DEFAULT_MIN_SAMPLE,
                    metavar="N",
                    help="fewer than N checkable exports is UNDECIDABLE "
                         "(default: %d)" % DEFAULT_MIN_SAMPLE)
    ap.add_argument("--verbose", action="store_true",
                    help="print each disagreement with both addresses")
    args = ap.parse_args()

    ents, names = tables(args.lximage)
    lx = LXImage(args.lximage)
    ob = {o.num: o.base for o in lx.objects}
    sf = SymFile(args.symfile)
    sf.resolve(lx)

    sv = {}
    for seg in sf.segments:
        for s in seg.symbols:
            if s.va is not None:
                sv.setdefault(s.name.upper(), s.va)

    agree = disagree = miss = 0
    details = []
    for nm, ordv in names.items():
        e = ents.get(ordv)
        if not e or e[0] not in ob:
            continue
        r = sv.get(nm.upper())
        if r is None:
            miss += 1
            continue
        expect = ob[e[0]] + e[1]
        if r == expect:
            agree += 1
        else:
            disagree += 1
            details.append((nm, expect, r))

    tot = agree + disagree
    if tot == 0:
        verdict, rc = "UNDECIDABLE (no named export has an entry-table slot)", 2
    elif tot < args.min_sample:
        verdict, rc = "UNDECIDABLE (sample %d < %d)" % (tot, args.min_sample), 2
    elif disagree == 0:
        verdict, rc = "MATCH", 0
    elif agree == 0:
        verdict, rc = "MISMATCH", 1
    else:
        verdict, rc = "PARTIAL - a neighbouring build, not this one", 1

    print("%-30s %-30s  agree %3d/%-3d  %-6s  %s"
          % (os.path.basename(args.lximage), os.path.basename(args.symfile),
             agree, tot, ("%.0f%%" % (100.0 * agree / tot)) if tot else "-",
             verdict))
    if miss:
        print("   note: %d named export(s) absent from the .SYM entirely" % miss)
    if args.verbose:
        for nm, expect, got in details:
            print("   %-28s entry table 0x%08x  .SYM 0x%08x  (delta 0x%x)"
                  % (nm, expect, got, abs(got - expect)))
    return rc


if __name__ == "__main__":
    sys.exit(main())
