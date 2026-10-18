#!/usr/bin/env python3
"""
lx_export.py - Inspect an OS/2 LX binary's linkage surface, and/or export its
reconstructed object images for Ghidra.

Two jobs, because they answer the two questions you have about a built module:

  1. "What does it export / import?" (default) - the object table, the exports
     (entry table + resident/non-resident name tables, including forwarders),
     and the imports (import module table, plus the ordinals/names actually
     referenced by fixup records). This is what diagnoses SYS2070 (bad ordinal)
     and SYS1804 (module not found): compare the importing side's requested
     ordinal against the exporting side's entry table.

  2. "Give me the bytes" (--dump) - the LXImage reconstructor decompresses
     object memory correctly, so it feeds Ghidra those raw bytes at each
     object's base instead of relying on the (fixup-buggy) community LX loader
     extension.

Usage:
    lx_export.py LXIMAGE [--exports] [--imports] [--json]
    lx_export.py LXIMAGE --def | --wlink
    lx_export.py LXIMAGE --dump [--obj N] [--outdir DIR] [--all]

With neither --exports nor --imports, both are shown.
--dump writes outdir/objNN_BASE.bin per object plus a manifest.json
(num, base, size, bits, perm, exec, file) for the Ghidra loader script.

LX table layout used below (offsets within the LX header) is [DOC-IBM], from
the LX executable-format spec; see os2ref/executable-formats.md. Note nrestab
is an ABSOLUTE file offset while every other table offset is relative to the
LX header - a distinction that silently yields garbage if missed.
"""
import argparse
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sym2map import LXImage

# --- LX header field offsets (relative to the LX header start) -------------
H_RESTAB    = 0x58   # resident name table (rel)
H_ENTTAB    = 0x5C   # entry table (rel)
H_IMPMOD    = 0x70   # import module name table (rel)
H_IMPMODCNT = 0x74   # number of import modules
H_IMPPROC   = 0x78   # import procedure name table (rel)
H_NRESTAB   = 0x88   # non-resident name table (ABSOLUTE file offset)
H_CBNRESTAB = 0x8C   # non-resident name table length

# Entry-table bundle types
ENT_UNUSED, ENT_16BIT, ENT_GATE286, ENT_32BIT, ENT_FORWARD = 0, 1, 2, 3, 4
ENT_TYPE_NAME = {ENT_16BIT: "entry16", ENT_GATE286: "gate286",
                 ENT_32BIT: "entry32", ENT_FORWARD: "forwarder"}


def _u32(d, off):
    return struct.unpack_from("<I", d, off)[0]


def _pstr(d, pos):
    """Length-prefixed (u8) string -> (text, next_pos)."""
    n = d[pos]
    return d[pos + 1:pos + 1 + n].decode("latin1"), pos + 1 + n


def parse_name_table(d, off, end=None):
    """Resident/non-resident name table -> [(name, ordinal)].

    Entries are: u8 len, name[len], u16 ordinal; a zero length terminates.
    The module name (resident table) or description (non-resident table) is
    not an export: it is the entry with ordinal 0, which callers drop.
    """
    out = []
    if not off:
        return out
    limit = end if end is not None else len(d)
    while off < limit and d[off]:
        name, off = _pstr(d, off)
        if off + 2 > limit:
            break
        out.append((name, struct.unpack_from("<H", d, off)[0]))
        off += 2
    return out


def parse_entry_table(d, off):
    """Entry table -> {ordinal: info}. Bundle format is [DOC-IBM]:

        bundle: u8 count, u8 type [, u16 object if type != 0]
        type 0 = unused: skips `count` ordinals, no object field
        type 1 = 16-bit entry:  u8 flags, u16 offset          (3 bytes)
        type 2 = 286 call gate: u8 flags, u16 offset, u16 sel (5 bytes)
        type 3 = 32-bit entry:  u8 flags, u32 offset          (5 bytes)
        type 4 = forwarder:     u8 flags, u16 modord, u32 val (7 bytes)
        flags: bit 0 = exported, bits 3-7 = parameter word count

    A zero count terminates the table.
    """
    out = {}
    if not off:
        return out
    ordn = 1
    while off < len(d):
        cnt = d[off]
        if cnt == 0:
            break
        btype = d[off + 1]
        off += 2
        if btype == ENT_UNUSED:
            ordn += cnt
            continue
        objnum = struct.unpack_from("<H", d, off)[0]
        off += 2
        for _ in range(cnt):
            if off >= len(d):
                return out
            flags = d[off]
            info = {"type": ENT_TYPE_NAME.get(btype, "type%d" % btype),
                    "obj": objnum,
                    "exported": bool(flags & 0x01),
                    "parm_words": (flags >> 3) & 0x1F}
            if btype == ENT_16BIT:
                info["offset"] = struct.unpack_from("<H", d, off + 1)[0]
                off += 3
            elif btype == ENT_GATE286:
                info["offset"] = struct.unpack_from("<H", d, off + 1)[0]
                off += 5
            elif btype == ENT_32BIT:
                info["offset"] = _u32(d, off + 1)
                off += 5
            elif btype == ENT_FORWARD:
                # For forwarders the object field is the import-module ordinal.
                info["fwd_modord"] = struct.unpack_from("<H", d, off + 1)[0]
                info["fwd_value"] = _u32(d, off + 3)
                info["fwd_by_ordinal"] = bool(flags & 0x01)
                info.pop("exported", None)
                off += 7
            else:
                # Unknown bundle type: stop rather than desync and invent data.
                return out
            out[ordn] = info
            ordn += 1
    return out


def parse_import_modules(d, off, count):
    """Import module name table -> [name]; index 1 == first module."""
    out = []
    for _ in range(count):
        if off >= len(d):
            break
        name, off = _pstr(d, off)
        out.append(name)
    return out


def import_proc_name(d, impproc_off, index):
    """Name at `index` bytes into the import procedure name table."""
    if not impproc_off:
        return None
    pos = impproc_off + index
    if pos >= len(d):
        return None
    name, _ = _pstr(d, pos)
    return name


def collect_import_refs(lx):
    """Walk fixup records for imported targets -> {module_name: set(ref)}.

    ref is "#<ordinal>" for import-by-ordinal or the procedure name for
    import-by-name. Record layout mirrors LXImage._parse_page_fixups; only
    import targets (target type 1 and 2) are decoded here.

    Parsing is fail-safe per page: a desync abandons that page rather than
    emitting invented references.
    """
    d = lx.data
    refs = {}
    if not (lx.fpage_off and lx.frec_off):
        return refs
    h = lx.lx_off
    modules = parse_import_modules(d, h + _u32(d, h + H_IMPMOD),
                                   _u32(d, h + H_IMPMODCNT))
    impproc = _u32(d, h + H_IMPPROC)
    impproc_off = (h + impproc) if impproc else 0

    for gpage in range(lx.mpages):
        try:
            fstart = _u32(d, lx.fpage_off + gpage * 4)
            fend = _u32(d, lx.fpage_off + (gpage + 1) * 4)
        except struct.error:
            break
        p, pend = lx.frec_off + fstart, lx.frec_off + fend
        while p < pend:
            if p + 2 > pend:
                break
            source, flags = d[p], d[p + 1]
            p += 2
            if source == 0 and flags == 0:
                break
            stype = source & 0x0F
            ttype = flags & 0x03
            srclist = (source & 0x20) != 0
            nsrc = 0
            if srclist:
                if p + 1 > pend:
                    break
                nsrc = d[p]
                p += 1
                if nsrc == 0 or nsrc > 500:
                    break
            else:
                p += 2                                    # single source offset
            if ttype == 0x00:                             # internal
                p += 2 if (flags & 0x40) else 1
                if stype != 0x02:
                    p += 4 if (flags & 0x10) else 2
            elif ttype in (0x01, 0x02):                   # imported ordinal/name
                if flags & 0x40:
                    modord = struct.unpack_from("<H", d, p)[0]
                    p += 2
                else:
                    modord = d[p]
                    p += 1
                if ttype == 0x01:                         # by ordinal
                    if flags & 0x80:
                        val = d[p]; p += 1
                    elif flags & 0x10:
                        val = _u32(d, p); p += 4
                    else:
                        val = struct.unpack_from("<H", d, p)[0]; p += 2
                    ref = "#%d" % val
                else:                                     # by name
                    if flags & 0x10:
                        val = _u32(d, p); p += 4
                    else:
                        val = struct.unpack_from("<H", d, p)[0]; p += 2
                    ref = import_proc_name(d, impproc_off, val) or "@0x%x" % val
                mod = modules[modord - 1] if 1 <= modord <= len(modules) \
                    else "?mod%d" % modord
                refs.setdefault(mod, set()).add(ref)
            else:                                         # 0x03 entry-table
                p += 2
            if flags & 0x04:                              # additive fixup
                p += 4 if (flags & 0x20) else 2
            if srclist:
                p += 2 * nsrc
    return refs


def describe(lx):
    """Collect the module's linkage surface as plain data."""
    d, h = lx.data, lx.lx_off
    restab = _u32(d, h + H_RESTAB)
    nrestab = _u32(d, h + H_NRESTAB)          # ABSOLUTE file offset
    cbnres = _u32(d, h + H_CBNRESTAB)

    res = parse_name_table(d, h + restab if restab else 0)
    nres = parse_name_table(d, nrestab, nrestab + cbnres if nrestab else None)

    # The module name / description is the first entry, with ordinal 0; a
    # linker given no description writes none, so only ordinal 0 is dropped.
    module_name = res[0][0] if res and res[0][1] == 0 else None
    description = nres[0][0] if nres and nres[0][1] == 0 else None
    res = [r for r in res if r[1] != 0]
    nres = [r for r in nres if r[1] != 0]
    named = {}
    for name, ordn in res + nres:
        named.setdefault(ordn, name)

    entries = parse_entry_table(d, h + _u32(d, h + H_ENTTAB)
                                if _u32(d, h + H_ENTTAB) else 0)
    exports = []
    for ordn in sorted(entries):
        e = dict(entries[ordn])
        e["ordinal"] = ordn
        e["name"] = named.get(ordn)
        exports.append(e)

    modules = parse_import_modules(d, h + _u32(d, h + H_IMPMOD),
                                   _u32(d, h + H_IMPMODCNT))
    return {"module": module_name, "description": description,
            "exports": exports, "import_modules": modules,
            "import_refs": collect_import_refs(lx)}


def print_objects(lx):
    print("OBJECTS")
    for o in lx.objects:
        print("  %2d  base=%08x  vsize=%8d  %s  %s  %s"
              % (o.num, o.base, o.vsize, "U32" if o.is_32bit else "U16",
                 o.perm(), o.kind()))


def print_exports(info):
    exports = info["exports"]
    print("EXPORTS  (%d entry-table slots)" % len(exports))
    if not exports:
        print("  (none - module exports nothing by ordinal)")
        return
    print("  %-6s %-9s %-24s %s" % ("ORD", "TYPE", "NAME", "TARGET"))
    for e in exports:
        if e["type"] == "forwarder":
            how = "#%d" % e["fwd_value"] if e["fwd_by_ordinal"] \
                else "name@0x%x" % e["fwd_value"]
            target = "-> module %d %s" % (e["fwd_modord"], how)
        else:
            target = "obj %d:%08x  %d parm wds" % (e["obj"], e.get("offset", 0),
                                                   e["parm_words"])
            if not e.get("exported", True):
                target += "  [not exported]"
        print("  %-6d %-9s %-24s %s"
              % (e["ordinal"], e["type"], e["name"] or "-", target))


def export_records(lx, info):
    """Per entry-table slot, what a module definition needs: ordinal, names
    (first resident ones flagged), kind, object:offset, parameter words, and
    for a forwarder its (module, target) with target an int ordinal or a name.
    """
    d, h = lx.data, lx.lx_off
    restab = _u32(d, h + H_RESTAB)
    nrestab = _u32(d, h + H_NRESTAB)
    cbnres = _u32(d, h + H_CBNRESTAB)
    res = [r for r in parse_name_table(d, h + restab if restab else 0) if r[1]]
    nres = [r for r in parse_name_table(d, nrestab, nrestab + cbnres if nrestab else None)
            if r[1]]
    names, resident = {}, set()
    for name, ordn in res:
        names.setdefault(ordn, []).append(name)
        resident.add((ordn, name))
    for name, ordn in nres:
        names.setdefault(ordn, []).append(name)
    impproc = _u32(d, h + H_IMPPROC)
    mods = info["import_modules"]
    for e in info["exports"]:
        ordn = e["ordinal"]
        nl = names.get(ordn, [])
        r = {"ordinal": ordn, "names": nl, "kind": e["type"],
             "resident": bool(nl) and (ordn, nl[0]) in resident,
             "pwords": 0, "fwd": None, "note": [e["type"]]}
        if e["type"] == "forwarder":
            mod = mods[e["fwd_modord"] - 1] if 0 < e["fwd_modord"] <= len(mods) \
                else "module%d" % e["fwd_modord"]
            tgt = e["fwd_value"] if e["fwd_by_ordinal"] else \
                import_proc_name(d, h + impproc if impproc else 0, e["fwd_value"])
            r["fwd"] = (mod, tgt)
        else:
            r["pwords"] = e["parm_words"]
            r["note"].append("obj %d:%08x" % (e["obj"], e.get("offset", 0)))
            if not e.get("exported", True):
                r["note"].append("not exported")
        if len(nl) > 1:
            r["note"].append("also named " + ", ".join(nl[1:]))
        yield r


def print_def(lx, info):
    """The export surface as an OS/2 module definition file (.def).

    One EXPORTS line per entry-table slot, in ordinal order, with the slot's
    first name (resident names marked RESIDENTNAME), NONAME and a placeholder
    name for unnamed slots, the parameter word count where it is nonzero, and
    forwarders as `= MODULE.target`. What a .def cannot say (the entry kind and
    object, a second name) goes in a trailing comment.
    """
    print("LIBRARY %s" % (info["module"] or "?"))
    if info["description"]:
        print("DESCRIPTION '%s'" % info["description"].replace("'", "''"))
    print("EXPORTS")
    for r in export_records(lx, info):
        name = r["names"][0] if r["names"] else "ORD_%d" % r["ordinal"]
        line = "    %s" % name
        if r["fwd"]:
            line += " = %s.%s" % r["fwd"]
        line += " @%d" % r["ordinal"]
        if not r["names"]:
            line += " NONAME"
        elif r["resident"]:
            line += " RESIDENTNAME"
        if r["pwords"]:
            line += " %d" % r["pwords"]
        print("%-56s ; %s" % (line, "; ".join(r["note"])))


def print_wlink(lx, info):
    """The export surface as OpenWatcom wlink directives (OS/2 LX).

    A named slot is `export NAME.ord [RESIDENT] [iopl_bytes]`, bound to the
    symbol NAME; an unnamed one is `anonymousexport ORD_n.n`, bound to ORD_n,
    which puts no name in either name table. iopl_bytes is twice the slot's
    parameter word count. A forwarder imports its target under FWD_n and
    exports that.
    """
    print("option modname=%s" % (info["module"] or "?"))
    if info["description"]:
        print("option description '%s'" % info["description"].replace("'", "''"))
    for r in export_records(lx, info):
        ordn = r["ordinal"]
        name = r["names"][0] if r["names"] else "ORD_%d" % ordn
        sym = ""
        if r["fwd"]:
            print("import FWD_%d %s.%s" % (ordn, r["fwd"][0], r["fwd"][1]))
            sym = "=FWD_%d" % ordn
        line = "%s %s.%d%s" % ("export" if r["names"] else "anonymousexport",
                               name, ordn, sym)
        if r["resident"]:
            line += " RESIDENT"
        if r["pwords"]:
            line += " %d" % (2 * r["pwords"])
        print("%-56s # %s" % (line, "; ".join(r["note"])))


def print_imports(info):
    mods = info["import_modules"]
    refs = info["import_refs"]
    print("IMPORTS  (%d modules)" % len(mods))
    if not mods:
        print("  (none)")
        return
    for i, m in enumerate(mods, 1):
        # Ordinals sort numerically (#14 before #111); names alphabetically after.
        used = sorted(refs.get(m, ()),
                      key=lambda s: (0, int(s[1:]), "") if s.startswith('#')
                      and s[1:].isdigit() else (1, 0, s))
        print("  %2d  %-12s %s" % (i, m,
                                   ("%d refs: " % len(used)) + ", ".join(used[:12])
                                   + (" ..." if len(used) > 12 else "")
                                   if used else "(no fixup references found)"))


def main():
    ap = argparse.ArgumentParser(
        description="Inspect an OS/2 LX binary's exports/imports, or dump its "
                    "object images for Ghidra (--dump).")
    ap.add_argument("lximage")
    ap.add_argument("--exports", action="store_true", help="show exports only")
    ap.add_argument("--imports", action="store_true", help="show imports only")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--def", dest="deffile", action="store_true",
                    help="print the exports as an OS/2 module definition file")
    ap.add_argument("--wlink", action="store_true",
                    help="print the exports as OpenWatcom wlink directives")
    ap.add_argument("--dump", action="store_true",
                    help="write object images + manifest.json for Ghidra")
    ap.add_argument("--obj", type=int, help="--dump: only this object number")
    ap.add_argument("--outdir", default="/tmp/lx_objs", help="--dump: output dir")
    ap.add_argument("--all", action="store_true",
                    help="--dump: include non-exec objects")
    args = ap.parse_args()

    try:
        lx = LXImage(args.lximage)
    except (OSError, ValueError) as e:
        sys.exit("%s: %s" % (args.lximage, e))

    if not args.dump:
        info = describe(lx)
        if args.deffile:
            print_def(lx, info)
            return 0
        if args.wlink:
            print_wlink(lx, info)
            return 0
        if args.json:
            out = dict(info)
            out["import_refs"] = {k: sorted(v) for k, v in info["import_refs"].items()}
            json.dump(out, sys.stdout, indent=2)
            print()
            return 0
        print("module: %s   %s" % (info["module"] or "?",
                                   info["description"] or ""))
        want_e = args.exports or not args.imports
        want_i = args.imports or not args.exports
        if want_e and want_i:
            print_objects(lx)
            print()
        if want_e:
            print_exports(info)
            if want_i:
                print()
        if want_i:
            print_imports(info)
        return 0

    os.makedirs(args.outdir, exist_ok=True)
    manifest = []
    for o in lx.objects:
        if args.obj and o.num != args.obj:
            continue
        if not args.all and not o.is_exec and args.obj is None:
            continue
        data = lx.object_bytes(o.num)
        name = "obj%02d_%08x.bin" % (o.num, o.base)
        path = os.path.join(args.outdir, name)
        with open(path, "wb") as f:
            f.write(data)
        entry = dict(num=o.num, base=o.base, size=len(data),
                     bits=32 if o.is_32bit else 16, perm=o.perm(),
                     exec=bool(o.is_exec), file=path)
        manifest.append(entry)
        print("obj %2d  base=%08x  size=%7d  %s  %s  -> %s"
              % (o.num, o.base, len(data), "U32" if o.is_32bit else "U16",
                 o.perm(), path))
    with open(os.path.join(args.outdir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
    print("manifest: %s" % os.path.join(args.outdir, "manifest.json"))
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
