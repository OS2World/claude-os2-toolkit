#!/usr/bin/env python3
"""
ne_impnames.py - rewrite ne_seg_export.py's imports.txt (MODULE_<ordinal>)
into real API names, so a decompiled NE corpus reads DosOpen() instead of an
unresolved far call into a synthetic block.

An NE module imports by ordinal: the binary records "module reference 3,
ordinal 487" and nothing more.  The ordinal-to-name mapping lives in the
import library's module-definition (.DEF) file for that module, so this script
takes those .DEF files as input rather than carrying a built-in table.  The
usual sources are the OS/2 Toolkit's own .DEF files and the .DEF files in
osFree's re-implementation of the 16-bit API libraries; the toolkit's OS/2
library (see PATHS.md) is where a local copy would be filed.

An ordinal that no supplied .DEF names is passed through unchanged, and listed
on stderr.  That is deliberate: a missing name is a gap to look up, never a
guess.  Some ordinals genuinely are absent from every published .DEF for their
module - report those as unresolved and leave them so.

.DEF lines are read in their EXPORTS form, "NAME @ordinal" (anything after the
ordinal, such as a residentname or a parameter count, is ignored).

Usage:
    ne_impnames.py <imports.txt> --def MODULE=PATH [--def ...] [--defdir DIR]

  --def MODULE=PATH  the .DEF file giving MODULE's ordinals, e.g.
                     --def DOSCALLS=/path/to/doscalls.def
  --defdir DIR       a directory of .DEF files; each <name>.def in it is
                     registered for module <NAME> (uppercased)

Output: the same "0xVA name" lines, renamed where possible, on stdout - the
form ApplySymbols.java consumes.
"""
import argparse
import os
import re
import sys

ENTRY = re.compile(r'^\s*(\S+)\s*@\s*(\d+)', re.M)


def load_def(path):
    if not os.path.exists(path):
        return None
    with open(path, 'r', errors='replace') as f:
        return {int(o): n for n, o in ENTRY.findall(f.read())}


def main():
    ap = argparse.ArgumentParser(
        description="Rename MODULE_<ordinal> import stubs to real API names "
                    "using module-definition (.DEF) files.")
    ap.add_argument("imports", help="imports.txt written by ne_seg_export.py")
    ap.add_argument("--def", dest="defs", action="append", default=[],
                    metavar="MODULE=PATH",
                    help="ordinal table for one module (repeatable)")
    ap.add_argument("--defdir", help="directory of <module>.def files")
    args = ap.parse_args()

    tables = {}
    if args.defdir:
        for fn in sorted(os.listdir(args.defdir)):
            if fn.lower().endswith(".def"):
                t = load_def(os.path.join(args.defdir, fn))
                if t:
                    tables[os.path.splitext(fn)[0].upper()] = t
    for spec in args.defs:
        if "=" not in spec:
            sys.exit("--def expects MODULE=PATH, got: %s" % spec)
        mod, path = spec.split("=", 1)
        t = load_def(path)
        if t is None:
            sys.exit("--def %s: no such file: %s" % (mod, path))
        tables[mod.upper()] = t

    if not tables:
        print("ne_impnames: no .DEF tables given - every stub passes through "
              "unrenamed (see --def / --defdir)", file=sys.stderr)

    unresolved = []
    with open(args.imports) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            addr, tag = line.split(None, 1)
            mod, _, what = tag.rpartition('_')
            name = None
            if what.isdigit() and mod.upper() in tables:
                name = tables[mod.upper()].get(int(what))
            if name is None:
                name = tag
                unresolved.append(tag)
            print('%s %s' % (addr, name))
    if unresolved:
        print('ne_impnames: UNRESOLVED %s' % ', '.join(unresolved), file=sys.stderr)


if __name__ == '__main__':
    main()
