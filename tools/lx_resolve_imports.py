#!/usr/bin/env python3
"""lx_resolve_imports.py - name the target of every fixup in an LX object.

Static-RE starter kit. Companion to lx_disasm.py: an LX image's code does not
contain the addresses of the functions it calls. A call through an import is
assembled as `call far 0x0:0x0` (or a zeroed offset), and the real target is
supplied at load time from the module's FIXUP RECORD TABLE. So a static
disassembly shows an unresolved call, and this tool says what the loader would
have put there.

It complements sym2map.py, which deliberately resolves only INTERNAL fixup
targets (ttype 0x00). This resolves all four target types:

    ttype 0x00  internal      -> objN+0xOFFSET within this module
    ttype 0x01  import by ordinal -> MODULE.#ORDINAL
    ttype 0x02  import by name    -> MODULE.NAME
    ttype 0x03  own entry table   -> an ORDINAL OF THIS MODULE, resolved
                                     through its own entry table to
                                     objN:0xOFFSET (plus the exported name,
                                     when the module publishes one)

CHAINED FIXUPS. A record whose target flags carry 0x08 is only the HEAD of a
chain: the other slots in that page are linked through the object's own bytes
and have no record (lx_fixchain.py says how). Listing records alone undercounts
internal references badly - CHKDSK32.DLL has 63 chain records covering 2645
slots. Heads print as "(chain head)"; the slots after them are read from the
image and print as "(chained)".

THE WORKFLOW WITH lx_disasm.py.  Disassemble, find a call whose target is
zero, take the flat address of the fixup SOURCE - the byte right after the
call opcode, which is where the loader writes - and look that address up in
this tool's "(flat 0x...)" column:

    lx_disasm.py MODULE.DLL --sym-name SOME_ENTRY --count 40
    lx_resolve_imports.py MODULE.DLL --obj 1 | grep 0x0001a2b7

WHY ttype 0x03 IS WORTH HAVING, and the trap it hides.  A module calling its
own exported ordinal produces a fixup that names an ordinal in ITS OWN entry
table - nothing in the import tables can answer it, and a tool that skips the
ordinal prints a bare "<entrytab>" and leaves a real, resolvable call looking
like an unresolvable far call. Resolving it means walking the entry table, and
a type-0 bundle is EMPTY yet STILL CONSUMES `cnt` ordinals: skip that and every
later ordinal shifts, silently, producing confident wrong names. The width
selector for the ordinal in a ttype 0x03 record is the 16-bit-ordinal flag
0x40, the same flag as the object/module ordinal in the other branches - NOT
0x10, which is the 32-bit target-offset flag and is not used here.

Field offsets are the LX header layout (objtab +0x40, entry table +0x5C,
resident names +0x58, fixup page table +0x68, fixup record table +0x6C, import
module table +0x70, import procedure table +0x78, non-resident names +0x88).
Note that the non-resident name table pointer is a FILE offset, unlike every
other pointer in the header, which is header-relative.
"""
import argparse
import signal
import struct
import sys


class LXFixups:
    """LX header tables needed to name a fixup target."""

    def __init__(self, path):
        self.path = path
        self.has_chains = False
        self._followers = None
        with open(path, "rb") as f:
            self.data = f.read()
        d = self.data
        # The DOS stub is OPTIONAL. A bare LX carries its magic at offset 0 with no MZ
        # header at all -- netlabs ships several (the ncurses tinfo6.dll and the gcc
        # runtime gcc1.dll among them). Demanding MZ first rejects those as a corrupt
        # file rather than as the second valid layout they are.
        # See os2ref/executable-formats.md section 1.1.
        if d[:2] == b"LX":
            self.h = 0
        elif len(d) >= 0x40 and d[:2] in (b"MZ", b"ZM"):
            self.h = struct.unpack_from("<I", d, 0x3C)[0]
        else:
            raise SystemExit(
                "%s: not an LX image (no LX magic at 0, no MZ stub)" % path)
        if d[self.h:self.h + 2] != b"LX":
            raise SystemExit("%s: not an LX image (signature %r)"
                             % (path, d[self.h:self.h + 2]))
        self.pagesize = self.u32(0x28)
        self.mpages = self.u32(0x14)
        self.objtab, self.objcnt = self.u32(0x40), self.u32(0x44)
        self.fpagetab, self.frectab = self.u32(0x68), self.u32(0x6C)
        self.impmod, self.impmodcnt = self.u32(0x70), self.u32(0x74)
        self.impproc = self.u32(0x78)
        self.objects = self._objects()
        self.mod_names = self._mod_names()
        self.entries = self._entry_table()
        self.own_names = self._own_names()

    def u32(self, off):
        return struct.unpack_from("<I", self.data, self.h + off)[0]

    def _objects(self):
        """(vsize, base, flags, mapidx, mapsize) per object; 24 bytes each."""
        out = []
        for i in range(self.objcnt):
            vsize, base, flags, mapidx, mapsize, _res = struct.unpack_from(
                "<IIIIII", self.data, self.h + self.objtab + i * 24)
            out.append((vsize, base, flags, mapidx, mapsize))
        return out

    def _mod_names(self):
        """Import module name table: impmodcnt consecutive Pascal strings."""
        names, p = [], self.h + self.impmod
        for _ in range(self.impmodcnt):
            ln = self.data[p]
            names.append(self.data[p + 1:p + 1 + ln].decode("latin1"))
            p += 1 + ln
        return names

    def proc_name_at(self, rel_off):
        """A Pascal string at rel_off into the import procedure name table."""
        p = self.h + self.impproc + rel_off
        ln = self.data[p]
        return self.data[p + 1:p + 1 + ln].decode("latin1")

    def _entry_table(self):
        """ordinal -> ("obj", objnum, offset) | ("fwd", modord, ord_or_nameoff).

        Bundles are {cnt, type, [objnum|reserved], cnt * entry}. A type-0
        bundle is EMPTY - it carries no object number but still spends `cnt`
        ordinals, so it must advance the counter or every later ordinal is
        wrong. An unknown bundle type stops the walk rather than letting it
        march through unrelated bytes inventing ordinals.
        """
        entries = {}
        enttab = self.u32(0x5C)
        if not enttab:
            return entries
        d = self.data
        p, entn = self.h + enttab, 1
        while p < len(d):
            cnt = d[p]
            if cnt == 0:                      # end of entry table
                break
            etype = d[p + 1]
            p += 2
            if etype == 0x00:                 # empty bundle: ordinals still spent
                entn += cnt
                continue
            if etype == 0x04:                 # forwarder: reserved word, 7 per entry
                p += 2
                for _ in range(cnt):
                    modord = struct.unpack_from("<H", d, p + 1)[0]
                    tgt = struct.unpack_from("<I", d, p + 3)[0]
                    entries[entn] = ("fwd", modord, tgt)
                    p += 7
                    entn += 1
                continue
            if etype not in (0x01, 0x02, 0x03):
                break
            objnum = struct.unpack_from("<H", d, p)[0]
            p += 2
            for _ in range(cnt):
                if etype == 0x03:             # 32-bit entry: flags + dword offset
                    off = struct.unpack_from("<I", d, p + 1)[0]
                    p += 5
                else:                         # 16-bit (0x01) / 286 call gate (0x02)
                    off = struct.unpack_from("<H", d, p + 1)[0]
                    p += 3 if etype == 0x01 else 5
                entries[entn] = ("obj", objnum, off)
                entn += 1
        return entries

    def _own_names(self):
        """ordinal -> exported name, from the resident and non-resident tables.

        Most ordinals are exported by number only, so a miss here is normal and
        not a defect. The non-resident table pointer is a FILE offset.
        """
        names = {}
        d = self.data

        def walk(q, end):
            while q < end and d[q]:
                ln = d[q]
                nm = d[q + 1:q + 1 + ln].decode("latin1")
                o = struct.unpack_from("<H", d, q + 1 + ln)[0]
                q += 1 + ln + 2
                if o:
                    names.setdefault(o, nm)

        restab = self.u32(0x58)
        if restab:
            walk(self.h + restab, len(d))
        nrestab, cbnrestab = self.u32(0x88), self.u32(0x8C)
        if nrestab and cbnrestab:
            walk(nrestab, min(nrestab + cbnrestab, len(d)))
        return names

    def describe_own_ordinal(self, entord):
        ent = self.entries.get(entord)
        nm = self.own_names.get(entord)
        if ent is None:
            where = "<not in entry table>"
        elif ent[0] == "fwd":
            fwdmod = (self.mod_names[ent[1] - 1]
                      if 1 <= ent[1] <= len(self.mod_names) else "?")
            where = "forwarder -> %s #%d" % (fwdmod, ent[2])
        else:
            where = "obj%d:0x%03X" % (ent[1], ent[2])
        return "OWN ORDINAL #%d -> %s%s" % (entord, where, (" " + nm) if nm else "")

    def fixups(self, target_obj):
        """Yield (obj_offset, flat_va, stype, ttype, description) for one object.

        The fixup page table is indexed by the module's global page number
        (1-based, spanning all objects in page order); each object covers the
        page range given by its own mapidx/mapsize.
        """
        d = self.data
        if not 1 <= target_obj <= len(self.objects):
            raise SystemExit("object %d out of range (image has %d)"
                             % (target_obj, len(self.objects)))
        _vsize, base, _flags, mapidx, mapsize = self.objects[target_obj - 1]
        fpage_off, frec_off = self.h + self.fpagetab, self.h + self.frectab

        for pagerel in range(mapsize):
            pagenum = mapidx + pagerel
            if pagenum < 1 or pagenum > self.mpages:
                continue
            fstart, fend = struct.unpack_from("<II", d, fpage_off + (pagenum - 1) * 4)
            p, pend = frec_off + fstart, frec_off + fend
            page_off = pagerel * self.pagesize
            while p < pend:
                if p + 2 > pend:
                    break
                source, flagsb = d[p], d[p + 1]
                p += 2
                if source == 0 and flagsb == 0:
                    break
                stype = source & 0x0F
                ttype = flagsb & 0x03
                srclist = (source & 0x20) != 0
                if srclist:
                    cnt = d[p]
                    p += 1
                else:
                    single = struct.unpack_from("<h", d, p)[0]
                    p += 2

                if ttype == 0x00:
                    if flagsb & 0x40:
                        objnum = struct.unpack_from("<H", d, p)[0]
                        p += 2
                    else:
                        objnum = d[p]
                        p += 1
                    if stype == 0x02:
                        toff = 0
                    elif flagsb & 0x10:
                        toff = struct.unpack_from("<I", d, p)[0]
                        p += 4
                    else:
                        toff = struct.unpack_from("<H", d, p)[0]
                        p += 2
                    desc = "internal obj%d+0x%x" % (objnum, toff)
                elif ttype in (0x01, 0x02):
                    if flagsb & 0x40:
                        modord = struct.unpack_from("<H", d, p)[0]
                        p += 2
                    else:
                        modord = d[p]
                        p += 1
                    modname = (self.mod_names[modord - 1]
                               if 1 <= modord <= len(self.mod_names) else "?")
                    if ttype == 0x01:                       # by ordinal
                        if flagsb & 0x80:
                            ordv = d[p]
                            p += 1
                        elif flagsb & 0x10:
                            ordv = struct.unpack_from("<I", d, p)[0]
                            p += 4
                        else:
                            ordv = struct.unpack_from("<H", d, p)[0]
                            p += 2
                        desc = "%s.#%d" % (modname, ordv)
                    else:                                   # by name
                        if flagsb & 0x10:
                            nameoff = struct.unpack_from("<I", d, p)[0]
                            p += 4
                        else:
                            nameoff = struct.unpack_from("<H", d, p)[0]
                            p += 2
                        try:
                            desc = "%s.%s" % (modname, self.proc_name_at(nameoff))
                        except Exception:
                            desc = "%s.<nameoff 0x%x>" % (modname, nameoff)
                else:                                       # ttype 0x03
                    if flagsb & 0x40:                       # NOT 0x10 - see module docstring
                        entord = struct.unpack_from("<H", d, p)[0]
                        p += 2
                    else:
                        entord = d[p]
                        p += 1
                    desc = self.describe_own_ordinal(entord)

                if flagsb & 0x04:                           # additive fixup
                    p += 4 if flagsb & 0x20 else 2
                if flagsb & 0x08 and ttype == 0x00:
                    desc += " (chain head)"
                    self.has_chains = True

                if srclist:
                    for _ in range(cnt):
                        off = struct.unpack_from("<H", d, p)[0]
                        p += 2
                        yield (page_off + off, base + page_off + off,
                               stype, ttype, desc)
                else:
                    off = single & 0xFFFF
                    yield (page_off + off, base + page_off + off, stype, ttype, desc)

        if self.has_chains:
            for objnum, off, tobj, toff in self.chain_followers().get(target_obj, []):
                yield (off, base + off, 0x07, 0x00,
                       "internal obj%d+0x%x (chained)" % (tobj, toff))

    def chain_followers(self):
        """objnum -> [(objnum, obj_off, target_obj, target_off)] for every chained
        slot after a head. Reads the object images, so it runs only for a module
        that has chain records."""
        if self._followers is None:
            from sym2map import LXImage
            from lx_fixchain import chain_slots
            img = LXImage(self.path)
            images = {o.num: bytearray(img.object_bytes(o.num)) for o in img.objects}
            self._followers = {}
            for slot in chain_slots(self.path, images, heads=False):
                self._followers.setdefault(slot[0], []).append(slot)
        return self._followers


TTYPE_KIND = {0: "internal", 1: "import", 2: "import", 3: "own"}


def main():
    ap = argparse.ArgumentParser(
        prog="lx_resolve_imports.py",
        description="Resolve an LX object's fixups to module+ordinal/name, so "
                    "an unresolved call in lx_disasm.py output can be named.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
workflow with lx_disasm.py:
  1. lx_disasm.py MODULE.DLL --sym-name ENTRY --count 40
  2. find a call whose target is zero - the loader fills it in
  3. take the flat address of the byte AFTER the opcode (the fixup source)
  4. lx_resolve_imports.py MODULE.DLL --obj 1 | grep <that address>

output columns:
  objN+0xOFFSET   the fixup source, as an offset within the object
  (flat 0x...)    the same address as a flat VA - what lx_disasm.py prints
  stype/ttype     LX source type / target type (0 internal, 1 ordinal import,
                  2 name import, 3 this module's own entry-table ordinal)
  -> target       the resolved name

examples:
  lx_resolve_imports.py MODULE.DLL                  # object 1 (the default)
  lx_resolve_imports.py MODULE.DLL --obj 3
  lx_resolve_imports.py MODULE.DLL --all-objects
  lx_resolve_imports.py MODULE.DLL --kind import    # imports only
  lx_resolve_imports.py DRIVER.SYS --summary        # which modules, which ordinals
""")
    ap.add_argument("lximage", help="the LX image (.DLL, .EXE, .SYS ...)")
    ap.add_argument("--obj", type=int, default=1, metavar="N",
                    help="object number to resolve (default: 1)")
    ap.add_argument("--all-objects", action="store_true",
                    help="resolve every object in the image")
    ap.add_argument("--kind", choices=["all", "internal", "import", "own"],
                    default="all",
                    help="show only fixups of this kind (default: all)")
    ap.add_argument("--summary", action="store_true",
                    help="count targets instead of listing every fixup site")
    args = ap.parse_args()

    lx = LXFixups(args.lximage)
    objs = range(1, len(lx.objects) + 1) if args.all_objects else [args.obj]

    counts, total = {}, 0
    for objnum in objs:
        for off, flat, stype, ttype, desc in lx.fixups(objnum):
            if args.kind != "all" and TTYPE_KIND.get(ttype) != args.kind:
                continue
            total += 1
            if args.summary:
                counts[desc] = counts.get(desc, 0) + 1
            else:
                print("obj%d+0x%06x (flat 0x%08x) stype=%d ttype=%d -> %s"
                      % (objnum, off, flat, stype, ttype, desc))

    if args.summary:
        for desc, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
            print("%6d  %s" % (n, desc))
        print("\n%d distinct target(s), %d fixup site(s)" % (len(counts), total))
    elif total == 0:
        # Not an error: an object can legitimately have no fixups of this kind.
        print("no %s fixups in object(s) %s"
              % ("" if args.kind == "all" else args.kind,
                 ",".join(str(o) for o in objs)), file=sys.stderr)


if __name__ == "__main__":
    # Exit quietly when a reader closes the pipe (`| head`), the way a
    # normal filter does, instead of tracebacking on BrokenPipeError.
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    main()
