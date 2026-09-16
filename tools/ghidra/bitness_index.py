#!/usr/bin/env python3
"""
bitness_index.py - say, per decompiled routine, which decompile is
AUTHORITATIVE and which is known garbage.

Why this exists
---------------
The runners build one Ghidra program per bitness present in a module, and each
program has exactly one Language.  Objects of the other bitness are mapped as
memory blocks, and make_blocks.py forces opposite-bitness CODE objects
non-executable so the analyzer will not walk them.  Measured: that guard is
necessary but NOT sufficient - Ghidra's auto-analysis creates functions inside
those non-executable blocks anyway, most of them analyzer-invented FUN_* names
that no symbol seeded.  Where a decompiler writes one file per function, the
result is a corpus that carries 32-bit code decoded as 16-bit instructions.
Fewer than half of those files carry any Ghidra warning, so a reader cannot
tell from inside the file that it is nonsense.

DecompileAll.java now refuses to emit files for functions in non-executable
blocks, which stops the problem at the source.  This script is what identifies
the damage in output produced before that filter, and it remains the honest
cross-check afterwards.

Object bitness comes from the exporter's manifest.json (for LX, the object
table's own 32-bit flag) - never from a directory or file name.

Statuses, chosen to be greppable:
  OK      - the file sits in the directory matching its object's bitness.
  GARBAGE - wrong-bitness decode, and a correct decompile of the SAME entry
            point exists; it is named in the authoritative column.
  ORPHAN  - wrong-bitness decode and there is NO decompile of that entry point
            in the correct-bitness pass.  This is the dangerous row: a grep
            finds the only file there is, and it is garbage.  The authoritative
            column names the nearest preceding correct-bitness function, which
            usually CONTAINS this address.  lx_ghidra_reseed.sh exists to turn
            these rows into real decompiles.
  UNMAPPED - the filename's entry point could not be parsed, or lies in no
            object in the manifest.

Usage: bitness_index.py [--markers] <module-out-dir> [...]

Writes <dir>/DECOMPILE_INDEX.tsv per directory and prints a one-line summary.
With --markers it ALSO drops a sibling "<file>.c.WRONG-BITNESS" next to every
known-garbage .c, so the warning is where the file is read - both `ls` and
`grep -rl <routine>` surface it - rather than only in an index a reader has to
know exists.  Nothing is ever deleted or rewritten: the misdecoded .c files
stay exactly as Ghidra wrote them, because they are the evidence.
"""
import argparse
import bisect
import json
import os
import re
import sys


def entry_va(fname):
    """Recover the entry-point VA from a DecompileAll.java output filename.

    DecompileAll writes "<safeName>_<entryPoint>.c".  Under x86:LE:32 the entry
    point renders flat ("0019bbe8"); under x86:LE:16:Protected Mode it renders
    segmented ("0019:bbe8"), where Ghidra's segment is the high 16 bits of the
    same flat address.  Both spell the same VA.
    """
    stem = fname[:-2] if fname.endswith(".c") else fname
    tok = stem.rsplit("_", 1)[-1]
    if ":" in tok:
        seg, off = tok.split(":", 1)
        try:
            return (int(seg, 16) << 16) + int(off, 16)
        except ValueError:
            return None
    return int(tok, 16) if re.fullmatch(r"[0-9a-fA-F]{6,8}", tok) else None


def routine(fname):
    return (fname[:-2] if fname.endswith(".c") else fname).rsplit("_", 1)[0]


def load_objects(moddir):
    with open(os.path.join(moddir, "objs", "manifest.json")) as f:
        m = json.load(f)
    # NOTE: 'size' is the size of the EXPORTED bytes, which for a data object
    # can be less than the declared virtual size.  That is the right range
    # here: it is exactly what Ghidra mapped.
    return [(o["num"], o["base"], o["base"] + o["size"], o["bits"]) for o in m]


def index_module(moddir):
    objs = load_objects(moddir)

    def owner(va):
        for num, lo, hi, bits in objs:
            if lo <= va < hi:
                return num, bits
        return None, None

    files = {}
    for bits in (16, 32):
        d = os.path.join(moddir, "decompiled_%d" % bits)
        # .c only: the .WRONG-BITNESS markers this script writes live in the
        # same directory and are not decompiles.
        files[bits] = (sorted(f for f in os.listdir(d) if f.endswith(".c"))
                       if os.path.isdir(d) else [])
    va_of = {b: {f: entry_va(f) for f in files[b]} for b in (16, 32)}
    by_va = {b: {v: f for f, v in va_of[b].items() if v is not None} for b in (16, 32)}
    sorted_va = {b: sorted(by_va[b]) for b in (16, 32)}

    rows = []
    counts = {"OK": 0, "GARBAGE": 0, "ORPHAN": 0, "UNMAPPED": 0}
    for bits in (16, 32):
        other = 32 if bits == 16 else 16
        for f in files[bits]:
            va = va_of[bits][f]
            here = "decompiled_%d/%s" % (bits, f)
            if va is None:
                counts["UNMAPPED"] += 1
                rows.append(("UNMAPPED", "?", "?", "?", routine(f), "", here))
                continue
            num, obits = owner(va)
            if obits is None:
                counts["UNMAPPED"] += 1
                rows.append(("UNMAPPED", "%08x" % va, "?", "?", routine(f), "", here))
                continue
            if obits == bits:
                counts["OK"] += 1
                rows.append(("OK", "%08x" % va, "obj%d" % num, "USE%d" % obits,
                             routine(f), here, ""))
                continue
            # wrong-bitness decode
            if va in by_va[other]:
                counts["GARBAGE"] += 1
                auth = "decompiled_%d/%s" % (other, by_va[other][va])
                rows.append(("GARBAGE", "%08x" % va, "obj%d" % num, "USE%d" % obits,
                             routine(f), auth, here))
            else:
                counts["ORPHAN"] += 1
                lst = sorted_va[other]
                i = bisect.bisect_right(lst, va) - 1
                if i >= 0 and owner(lst[i])[0] == num:
                    auth = "decompiled_%d/%s  (CONTAINING fn, +0x%x)" % (
                        other, by_va[other][lst[i]], va - lst[i])
                else:
                    auth = "NONE - no USE%d decompile covers this address" % obits
                rows.append(("ORPHAN", "%08x" % va, "obj%d" % num, "USE%d" % obits,
                             routine(f), auth, here))

    rows.sort(key=lambda r: (r[0] != "ORPHAN", r[0] != "GARBAGE", r[1]))
    out = os.path.join(moddir, "DECOMPILE_INDEX.tsv")
    with open(out, "w") as f:
        f.write("# status\tva\tobject\tobj_bitness\troutine\tauthoritative\tknown_garbage\n")
        f.write("# ORPHAN = the ONLY decompile of this routine is a wrong-bitness one.\n")
        for r in rows:
            f.write("\t".join(r) + "\n")
    return counts, rows


MARKER = """\
WRONG BITNESS - DO NOT CITE THE .c FILE BESIDE THIS MARKER.

  routine      : %(routine)s
  entry point  : 0x%(va)s
  lives in     : %(object)s, which the module's object table flags %(obits)s
  decoded as   : %(dbits)s   <-- wrong instruction width, so the C is nonsense

  READ INSTEAD : %(auth)s

%(extra)sLess than half of these files carry any Ghidra warning, so the file itself
is not evidence either way.
Index for this module: ../DECOMPILE_INDEX.tsv (grep for ORPHAN)
"""

ORPHAN_EXTRA = """\
This routine is an ORPHAN: no decompile of this exact entry point exists in
the correct-bitness pass.  The file named above is the nearest preceding
correct-bitness function, which usually CONTAINS this address.  If it does
not, this address has no trustworthy decompile at all - disassemble it, or
re-run the correct-bitness pass with lx_ghidra_reseed.sh.

"""


def write_markers(moddir, rows):
    n = 0
    for status, va, obj, obits, rtn, auth, garbage in rows:
        if status not in ("GARBAGE", "ORPHAN"):
            continue
        path = os.path.join(moddir, garbage)
        dbits = "USE16" if garbage.startswith("decompiled_16/") else "USE32"
        with open(path + ".WRONG-BITNESS", "w") as f:
            f.write(MARKER % dict(routine=rtn, va=va, object=obj, obits=obits,
                                  dbits=dbits, auth=auth,
                                  extra=ORPHAN_EXTRA if status == "ORPHAN" else ""))
        n += 1
    return n


def main():
    ap = argparse.ArgumentParser(
        description="Index a decompiled module by bitness correctness and "
                    "write DECOMPILE_INDEX.tsv.")
    ap.add_argument("moddir", nargs="+",
                    help="module output directories written by a pipeline runner")
    ap.add_argument("--markers", action="store_true",
                    help="also write a .WRONG-BITNESS marker beside each known-garbage .c")
    args = ap.parse_args()

    total = {"OK": 0, "GARBAGE": 0, "ORPHAN": 0, "UNMAPPED": 0}
    for d in args.moddir:
        if not os.path.isfile(os.path.join(d, "objs", "manifest.json")):
            print("%s: no objs/manifest.json - not a pipeline output directory" % d,
                  file=sys.stderr)
            continue
        c, rows = index_module(d)
        m = write_markers(d, rows) if args.markers else 0
        for k in total:
            total[k] += c[k]
        print("%-24s OK=%-5d GARBAGE=%-5d ORPHAN=%-5d UNMAPPED=%d%s"
              % (os.path.basename(d.rstrip("/")), c["OK"], c["GARBAGE"],
                 c["ORPHAN"], c["UNMAPPED"], ("  markers=%d" % m) if args.markers else ""))
    print("%-24s OK=%-5d GARBAGE=%-5d ORPHAN=%-5d UNMAPPED=%d"
          % ("TOTAL", total["OK"], total["GARBAGE"], total["ORPHAN"], total["UNMAPPED"]))


if __name__ == "__main__":
    main()
