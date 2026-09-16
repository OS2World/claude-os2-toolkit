#!/usr/bin/env python3
"""extract_omf_lib_ordinals.py - recover ordinal -> name maps from an OMF
import library.

An OMF COMENT record of class 0xA0, subtype 0x01 (IMPDEF) states "<NAME> is
exported by <MODULE>, ordinal N". An IBM import library is therefore an
IBM-AUTHORED ordinal->name map for every module it covers - and for many OS/2
modules it is the ONLY one, because the names are not in the DLL at all: a
module whose exports are by-ordinal-only has a short resident name table and an
empty non-resident name table, so the binary knows the numbers and not the
names.

This is what turns a by-ordinal import (seen as "MODULE.#257" in
lx_resolve_imports.py or lx_export.py output) into a function name.

IMPORTANT SCOPE LIMIT - do not overclaim this tool.  An import library only
ever carried the module's PUBLISHED API. Undocumented internal ordinals - the
ones only another system DLL calls - were never in any library or header, so
their absence here is expected and is not evidence that the ordinal is unused.

FINDING A LIBRARY.  The toolkit locates material by role, never by path:

    os2-lib role toolkit-import-libs libs

gives the directory holding os2386.lib (32-bit), os2286.lib (16-bit) and the
rest. Pass the file you want as the argument.
"""
import argparse
import json
import os
import signal
import struct
import sys

OMF_COMENT = 0x88
OMF_CLASS_EXT = 0xA0
OMF_SUBTYPE_IMPDEF = 0x01


def parse_omf_lib(path):
    """{module: {ordinal: [names...]}} for every by-ordinal IMPDEF record.

    Libraries page-align each module, so a linear record walk desyncs on the
    padding; scan for IMPDEF records directly instead. Several names commonly
    map to one ordinal (mixed-case and uppercase aliases ship side by side),
    hence a list rather than a single name.
    """
    with open(path, "rb") as f:
        d = f.read()
    out = {}
    for i in range(len(d) - 8):
        if d[i] != OMF_COMENT:
            continue
        rlen = struct.unpack_from("<H", d, i + 1)[0]
        if rlen < 6 or i + 3 + rlen > len(d):
            continue
        b = d[i + 3: i + 3 + rlen]
        if len(b) < 4 or b[1] != OMF_CLASS_EXT or b[2] != OMF_SUBTYPE_IMPDEF:
            continue
        try:
            p = 3
            by_ordinal = b[p]; p += 1
            ln = b[p]; p += 1
            name = b[p:p + ln].decode("latin1"); p += ln
            ln = b[p]; p += 1
            module = b[p:p + ln].decode("latin1"); p += ln
            if not by_ordinal:
                continue
            ordv = struct.unpack_from("<H", b, p)[0]
            out.setdefault(module, {}).setdefault(ordv, []).append(name)
        except (IndexError, struct.error, UnicodeDecodeError):
            continue
    return out


def main():
    ap = argparse.ArgumentParser(
        prog="extract_omf_lib_ordinals.py",
        description="Dump ordinal -> name maps from an OMF import library "
                    "(IMPDEF records).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
finding an import library (never hardcode a path):
  libs=$(os2-lib role toolkit-import-libs libs)
  extract_omf_lib_ordinals.py "$libs/os2386.lib"            # module summary
  extract_omf_lib_ordinals.py "$libs/os2386.lib" DOSCALLS   # one module's map
  extract_omf_lib_ordinals.py "$libs/os2386.lib" PMWIN --json pmwin.json

with no MODULE, prints one summary line per module in the library.
with a MODULE, prints its ordinal -> name map (all aliases per ordinal).

use it to name a by-ordinal import reported by lx_resolve_imports.py or
lx_export.py. An ordinal absent here is typically an undocumented internal,
not an error.
""")
    ap.add_argument("lib", help="the .lib file (an OMF import library)")
    ap.add_argument("module", nargs="?",
                    help="module name (e.g. DOSCALLS); omit for a summary")
    ap.add_argument("--json", metavar="PATH",
                    help="also write the module's map to PATH as JSON")
    ap.add_argument("--ordinal", type=int, metavar="N",
                    help="print only ordinal N of MODULE")
    args = ap.parse_args()

    if not os.path.exists(args.lib):
        sys.exit("%s: no such file. Find your import libraries with:\n"
                 "  os2-lib role toolkit-import-libs libs" % args.lib)

    mods = parse_omf_lib(args.lib)
    if not mods:
        sys.exit("%s: no by-ordinal IMPDEF records found. Is this an OMF "
                 "IMPORT library (not a static .lib)?" % args.lib)

    if not args.module:
        print("%s: modules = %s" % (os.path.basename(args.lib),
                                    ", ".join(sorted(mods))))
        for m, omap in sorted(mods.items()):
            names = sum(len(v) for v in omap.values())
            print("  %-10s %4d ordinals (%d..%d), %d names (%.1f aliases/ordinal)"
                  % (m, len(omap), min(omap), max(omap), names,
                     float(names) / len(omap)))
        return

    module = args.module.upper()
    omap = mods.get(module) or mods.get(args.module)
    if not omap:
        sys.exit("no by-ordinal IMPDEFs for module %s in %s (modules: %s)"
                 % (args.module, os.path.basename(args.lib),
                    ", ".join(sorted(mods))))

    if args.ordinal is not None:
        v = omap.get(args.ordinal)
        if not v:
            sys.exit("%s ordinal %d is not in this library (undocumented "
                     "internals never were)" % (module, args.ordinal))
        print("%s.#%d = %s" % (module, args.ordinal, ", ".join(sorted(v))))
        return

    for o in sorted(omap):
        print("%-6d %s" % (o, ", ".join(sorted(omap[o]))))
    print("\n%s: %d ordinals (%d..%d)" % (module, len(omap), min(omap), max(omap)),
          file=sys.stderr)

    if args.json:
        with open(args.json, "w") as f:
            json.dump({str(o): sorted(v) for o, v in sorted(omap.items())},
                      f, indent=1)
        print("wrote %s" % args.json, file=sys.stderr)


if __name__ == "__main__":
    # Exit quietly when a reader closes the pipe (`| head`), the way a
    # normal filter does, instead of tracebacking on BrokenPipeError.
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    main()
