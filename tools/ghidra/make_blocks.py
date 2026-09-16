#!/usr/bin/env python3
"""
make_blocks.py - from an exporter manifest.json (lx_obj_export.py or
ne_seg_export.py), build the block-spec file LoadAllObjects.java consumes for
one bitness, and name the object that should be Ghidra's primary -import.

One Ghidra program has exactly one Language, and an OS/2 module routinely
mixes 16-bit and 32-bit code objects.  So the pipeline builds one program per
bitness present: the first executable object of that bitness is the -import
primary (it sets the program's language), and every other object is merged in
as an extra memory block at its real base.

The one thing that must not be naive here: an OPPOSITE-bitness CODE object
must be merged NON-EXECUTABLE.  Ghidra's auto-analyzer walks any block flagged
executable and decodes it in the program's single language, so a real 32-bit
code object merged executable into a 16-bit program is actively misdecoded as
garbage 16-bit instructions, and the analyzer then "finds" thousands of
functions that do not exist.  Measured on a mixed-bitness PM DLL: the 16-bit
pass went from a few hundred functions to several thousand, with the entire
excess landing inside the 32-bit object's address range.

So: opposite-bitness code objects are still added - their bytes stay available
for cross-referencing and manual disassembly at the correct width - but with
the execute bit cleared.  Same-bitness code and ALL data objects keep their
real permissions; data was never at risk, since Ghidra does not auto-
disassemble non-executable memory.

That guard is necessary but not sufficient: Ghidra's analysis can still create
functions inside a non-executable block.  bitness_index.py finds those after
the fact, and DecompileAll.java refuses to emit a .c file for them.

Usage: make_blocks.py <manifest.json> <bits: 16|32> <out_blocks.txt>
Prints: PRIMARY <num> <base_hex> <file>   (the object to pass to -import)
Exits 1 with NO_PRIMARY on stderr if the module has no executable object of
that bitness - which is how the runners decide to skip a pass.
"""
import argparse
import json
import sys


def main():
    ap = argparse.ArgumentParser(
        description="Build a LoadAllObjects.java block spec for one bitness "
                    "and print the primary object to -import.")
    ap.add_argument("manifest", help="manifest.json from an exporter")
    ap.add_argument("bits", type=int, choices=(16, 32), help="bitness of this pass")
    ap.add_argument("out_blocks", help="block-spec file to write")
    args = ap.parse_args()

    with open(args.manifest) as f:
        objs = json.load(f)
    objs.sort(key=lambda o: o["num"])

    primary = None
    for o in objs:
        if o["bits"] == args.bits and o["exec"]:
            primary = o
            break
    if primary is None:
        print("NO_PRIMARY", file=sys.stderr)
        sys.exit(1)

    lines = []
    for o in objs:
        if o["num"] == primary["num"]:
            continue
        perm = o["perm"]
        if o["exec"] and o["bits"] != args.bits:
            # opposite-bitness code: keep R/W, force non-executable so the
            # analyzer never decodes it under this program's language
            perm = perm[0] + perm[1] + "-"
        lines.append("%d 0x%08x %d %s %s"
                     % (o["num"], o["base"], o["size"], perm, o["file"]))
    with open(args.out_blocks, "w") as f:
        f.write("\n".join(lines) + ("\n" if lines else ""))

    print("PRIMARY %d 0x%08x %s" % (primary["num"], primary["base"], primary["file"]))


if __name__ == "__main__":
    main()
