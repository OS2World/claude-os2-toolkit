#!/usr/bin/env python3
"""
lx_obj_export.py - export every object of an OS/2 LX module as a flat binary
at its real base address, for the Ghidra pipeline in this directory.

Why every object, and why at the real base: an LX module is not one image.
Its objects (code and data, 16-bit and 32-bit) are separate segments loaded at
separate, widely-spaced flat addresses recorded in the object table.  Import
one object alone and every cross-object call is a reference into nothing, so
the decompiler cannot follow it and Ghidra's analyzer never discovers the
functions on the far side.  Exporting all of them, with their true bases, lets
the runner merge the rest into one program (see make_blocks.py and
LoadAllObjects.java) so cross-object references resolve.

Data objects are exported too, even though nothing executes there: code that
dereferences a global decompiles as a named/inspectable memory access instead
of a bare numeric address once the bytes are actually mapped.

Fixups are applied (sym2map.py's LXImage.object_bytes(num, fixups=True)),
which fills genuinely-unapplied (zero) fixup slots non-destructively.  It is
worth knowing what this does NOT fix: thunk gates whose far-jump target is
populated at run time by the loader or by module initialisation carry no
static relocation at all, so they still decompile as a jump to 0:0 followed by
"bad instruction data".  That is a true statement about the binary, not a tool
failure - the real target, when it is knowable statically, is usually in the
instruction immediately before the jump.

Chained fixups (LX target flag 0x08) are applied first, by ../lx_fixchain.py:
sym2map.py fills only zero slots and a chain head is never zero, so without this
every chained reference exports with the next-link offset in its top 12 bits
(about 230 shipped modules; see lx_fixchain.py). Then sym2map's zero-slot fill
runs on top.

Each object is zero-filled to its full virtual size. Reading stops at the last
mapped page, and without the fill everything in the object's BSS gets no Ghidra
memory, so the symbols there are dropped (CHKDSK32.DLL: 417 of 507 placed
before, 506 after).

Usage:
    lx_obj_export.py <lximage> <outdir>

Writes outdir/objNN_BASE.bin per object plus outdir/manifest.json with one
record per object: num, base, size, bits, perm, exec, file.  That manifest is
the shape make_blocks.py and bitness_index.py consume.

Depends on sym2map.py from this toolkit's tools/ directory (the parent of this
one); it is imported read-only for its LX reader.
"""
import argparse
import json
import os
import sys

TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOOLS_DIR)
try:
    from sym2map import LXImage
    from lx_fixchain import apply_chains
except ImportError as e:
    sys.exit("lx_obj_export.py: cannot import sym2map.py (%s).\n"
             "  It is expected next to this script's parent directory, at\n"
             "  %s/sym2map.py" % (e, TOOLS_DIR))


def main():
    ap = argparse.ArgumentParser(
        description="Export every LX object to a flat binary at its real base, "
                    "with fixups applied, plus a manifest.json for the Ghidra "
                    "pipeline.")
    ap.add_argument("lximage", help="the LX module (.DLL, .EXE, driver)")
    ap.add_argument("outdir", help="directory to write objNN_BASE.bin and manifest.json into")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    try:
        lx = LXImage(args.lximage)
    except (OSError, ValueError) as e:
        sys.exit("%s: not a readable LX image: %s" % (args.lximage, e))

    manifest = []
    images = {o.num: bytearray(lx.object_bytes(o.num, fixups=False)) for o in lx.objects}
    nrec, nslot, notes = apply_chains(args.lximage, images)
    if nrec:
        print("chained fixups: %d records, %d slots relocated" % (nrec, nslot))
    for n in notes:
        print("chained fixups: " + n, file=sys.stderr)
    for o in lx.objects:
        data = images[o.num]
        lx._apply_fixups(o, data)          # sym2map's zero-slot fill, on top of the chains
        if len(data) < o.vsize:            # BSS: give it memory so its symbols get placed
            data += bytes(o.vsize - len(data))
        data = bytes(data)
        # An executable object that is almost all zero bytes is a page-read failure, not
        # code: Ghidra decodes it as `add [eax],al` over and over and reports every function
        # "ok". Seen on an LX given an MZ stub without shifting its file-relative
        # e32_datapage, so every ExePack2 page decompressed from the wrong offset (97.6% zero);
        # across 158 good executable objects the worst was 67%, on a 6-byte object.
        if o.is_exec and len(data) >= 4096 and data.count(0) > 0.9 * len(data):
            sys.exit("obj %d: executable object is %.1f%% zero bytes - its pages were not read. "
                     "If an MZ stub was prepended, were e32_datapage/e32_nrestab shifted by its "
                     "size?" % (o.num, 100.0 * data.count(0) / len(data)))
        name = "obj%02d_%08x.bin" % (o.num, o.base)
        path = os.path.join(args.outdir, name)
        with open(path, "wb") as f:
            f.write(data)
        manifest.append(dict(num=o.num, base=o.base, size=len(data),
                             bits=32 if o.is_32bit else 16, perm=o.perm(),
                             exec=bool(o.is_exec), file=os.path.abspath(path)))
        print("obj %2d  base=%08x  size=%7d  %s  %s  exec=%s"
              % (o.num, o.base, len(data), "U32" if o.is_32bit else "U16",
                 o.perm(), o.is_exec))

    mpath = os.path.join(args.outdir, "manifest.json")
    with open(mpath, "w") as f:
        json.dump(manifest, f, indent=2)
    print("manifest: %s" % mpath)


if __name__ == "__main__":
    main()
