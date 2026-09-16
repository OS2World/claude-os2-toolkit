#!/usr/bin/env python3
"""driver_re.py - static dissection of OS/2 device drivers (LX and NE).

Reads a shipped driver binary and reports what is observably in it: the device
header it declares, its objects and page types, the decompressed DGROUP, an
IOCtl handler jump table, the modules and ordinals it imports, and a census of
its DevHlp call sites.

This is the FACT-GATHERING phase. It records what is there; it does not decide
what any of it means. Anything you intend to depend on should be byte-verified,
and the census in particular is a LEAD LIST, not a specification (see below).

GOTCHAS THIS TOOL EXISTS TO PREVENT - each one produces confident garbage:

  1. A driver may be LX or NE, and the extension does not tell you. Parsing an
     NE driver with LX offsets yields plausible nonsense. `info` says which it
     is; the LX-only subcommands refuse an NE image rather than guess.
  2. DGROUP is commonly an LX ITERDATA (compressed) page plus ZEROFILL pages.
     A raw-file read at ANY DGROUP offset is garbage - the object has to be
     materialised first. A device header often appears verbatim in the file
     anyway, because an iteration count of 1 stores its bytes literally, which
     makes the raw read look like it worked.
  3. An LX fixup record puts the source-offset LIST *after* the target data, so
     a parser that reads it in written order desyncs.
  4. The DevHlp function code is in DL, which may be loaded by `mov dl,0xNN`
     *or* by `mov dx,0xNNNN` (DL is the low byte). Miss the second form and the
     backtracker silently resolves a stale DL and mislabels the call.

WHAT IT NEEDS.  Python 3 only for everything except `devhlp`, which shells out
to `ndisasm` (NASM). DevHlp NUMBER->NAME resolution reads IBM's `devhlp.inc`,
found through the OS/2 library by role (`os2-lib role ddk-headers inc`); pass
--devhlp-inc to point at one directly. Without it the census still runs and
reports raw numbers.

ABI FACTS USED HERE, and where they are stated: the device header layout is
IBM's `SysDev` struct from the DDK header `devhdr.h`; the DevHlp numbers are
IBM's `devhlp.inc`; the object, page and fixup tables are the published LX
format, which the OS/2 Toolkit's executable-format reference documents.
"""
import argparse
import os
import re
import signal
import struct
import subprocess
import sys
from pathlib import Path

# --------------------------------------------------------------- devhdr.h ---
# struct SysDev (DDK devhdr.h):
#   +0x00 ULONG  SDevNext    +0x04 USHORT SDevAtt    +0x06 USHORT SDevStrat
#   +0x08 USHORT SDevInt     +0x0A UCHAR  SDevName[8]
SYSDEV_NAME_OFF = 0x0A
DEV_CHAR_DEV = 0x8000   # bit 15 - device is a character device
DEV_IOCTL    = 0x4000   # bit 14 - device accepts IOCtl requests
DEV_GIOCTL   = 0x0040   # bit  6 - device supports generic IOCtl
DEV_FCNLEV   = 0x0380   # bits 9-7 - device function level


def att_flags(att):
    f = []
    if att & DEV_CHAR_DEV:
        f.append("CHAR_DEV")
    if att & DEV_IOCTL:
        f.append("IOCTL")
    if att & DEV_GIOCTL:
        f.append("GIOCTL")
    f.append("FCNLEV=0x%04x" % (att & DEV_FCNLEV))
    return "|".join(f)


def parse_sysdev(buf, off):
    nxt, att, strat, intr = struct.unpack_from("<IHHH", buf, off)
    name = buf[off + SYSDEV_NAME_OFF: off + SYSDEV_NAME_OFF + 8]
    return nxt, att, strat, intr, name


def printable(b):
    """A device name as text, with non-ASCII bytes shown as escapes."""
    return "".join(chr(c) if 0x20 <= c < 0x7F else "\\x%02x" % c for c in b)


# --------------------------------------------------------------- LX parsing --
class LX:
    def __init__(self, path):
        self.path = Path(path)
        self.d = self.path.read_bytes()
        if len(self.d) < 0x40 or self.d[:2] not in (b"MZ", b"ZM"):
            self.lx, self.sig = 0, self.d[:2]
            return
        self.lx = struct.unpack_from("<I", self.d, 0x3C)[0]
        self.sig = self.d[self.lx:self.lx + 2]

    def is_lx(self):
        return self.sig == b"LX"

    def u32(self, o):
        return struct.unpack_from("<I", self.d, self.lx + o)[0]

    def u16(self, o):
        return struct.unpack_from("<H", self.d, self.lx + o)[0]

    @property
    def modflags(self):
        return self.u32(0x10)

    @property
    def npages(self):
        return self.u32(0x14)

    def objects(self):
        tab, n = self.lx + self.u32(0x40), self.u32(0x44)
        out = []
        for i in range(n):
            vsize, base, fl, pmap, msize, _ = struct.unpack_from(
                "<IIIIII", self.d, tab + i * 24)
            out.append(dict(idx=i + 1, vsize=vsize, base=base, flags=fl,
                            pagemap=pmap, mapsize=msize))
        return out

    PAGEKIND = {0: "VALID (raw)", 1: "ITERDATA (compressed)", 2: "INVALID",
                3: "ZEROFILL", 4: "RANGE", 5: "ITERDATA2"}

    def pages(self, obj):
        tab = self.lx + self.u32(0x48)
        datapages, shift = self.u32(0x80), self.u32(0x2C)
        out = []
        for p in range(obj["mapsize"]):
            off, sz, flags = struct.unpack_from(
                "<IHH", self.d, tab + (obj["pagemap"] - 1 + p) * 8)
            out.append(dict(idx=p, fileoff=datapages + (off << shift), size=sz,
                            flags=flags, kind=self.PAGEKIND.get(flags, "?%d" % flags)))
        return out

    def object_image(self, obj):
        """Materialise an object's bytes: decompress ITERDATA, expand ZEROFILL.

        THIS is what DGROUP offsets must be read out of - gotcha 2.
        """
        img = bytearray()
        psize = self.u32(0x28)
        for pg in self.pages(obj):
            if pg["flags"] == 0:                        # VALID: raw bytes
                img += self.d[pg["fileoff"]:pg["fileoff"] + pg["size"]]
                img += b"\0" * (psize - pg["size"])
            elif pg["flags"] == 3:                      # ZEROFILL
                img += b"\0" * psize
            elif pg["flags"] == 1:                      # ITERDATA
                img += self._deiter(pg["fileoff"], pg["size"], psize)
            else:
                img += b"\0" * psize
        return bytes(img[:obj["vsize"]])

    def _deiter(self, off, size, psize):
        """LX iterated page: repeated { u16 nIter; u16 nBytes; u8 data[nBytes] }."""
        out, p, end = bytearray(), off, off + size
        while p + 4 <= end:
            it, nb = struct.unpack_from("<HH", self.d, p)
            p += 4
            if it == 0 and nb == 0:
                break
            out += self.d[p:p + nb] * it
            p += nb
        out += b"\0" * (psize - len(out))
        return out[:psize]

    def imports(self):
        """(module names, {ordinal: call count}) harvested from fixup records.

        NOTE the source-offset list lives AFTER the target data - gotcha 3.
        """
        mods, p, n = [], self.lx + self.u32(0x70), self.u32(0x74)
        for _ in range(n):
            ln = self.d[p]
            mods.append(self.d[p + 1:p + 1 + ln].decode("ascii", "replace"))
            p += 1 + ln

        fixpage, fixrec = self.lx + self.u32(0x68), self.lx + self.u32(0x6C)
        ords = {}
        for pg in range(self.npages):
            o1 = struct.unpack_from("<I", self.d, fixpage + pg * 4)[0]
            o2 = struct.unpack_from("<I", self.d, fixpage + (pg + 1) * 4)[0]
            p, end = fixrec + o1, fixrec + o2
            while p < end:
                stype, flags = self.d[p], self.d[p + 1]
                p += 2
                cnt = 0
                if stype & 0x20:
                    cnt = self.d[p]
                    p += 1
                else:
                    p += 2                                  # SRCOFF
                t = flags & 0x03
                if t == 0:                                  # internal
                    p += 2 if flags & 0x40 else 1
                    if (stype & 0x0F) != 2:
                        p += 4 if flags & 0x10 else 2
                elif t == 1:                                # import by ordinal
                    p += 2 if flags & 0x40 else 1
                    if flags & 0x80:                        # 8-bit ordinal
                        o = self.d[p]; p += 1
                    elif flags & 0x10:
                        o = struct.unpack_from("<I", self.d, p)[0]; p += 4
                    else:
                        o = struct.unpack_from("<H", self.d, p)[0]; p += 2
                    ords[o] = ords.get(o, 0) + 1
                elif t == 2:                                # import by name
                    p += 2 if flags & 0x40 else 1
                    p += 4 if flags & 0x10 else 2
                elif t == 3:                                # own entry table
                    p += 2 if flags & 0x40 else 1
                if flags & 0x04:                            # additive
                    p += 4 if flags & 0x20 else 2
                if stype & 0x20:
                    p += 2 * cnt                            # source list LAST
        return mods, ords


# ------------------------------------------------------------ DevHlp table ---
def _library_inc_dirs():
    """Directories that may hold devhlp.inc, resolved by ROLE, never by path."""
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    try:
        import os2lib
    except ImportError:
        return []
    out = []
    for rolename, part in (("ddk-headers", "inc"), ("ddk-source", "ddk"),
                           ("toolkit-headers", "inc")):
        try:
            p = os2lib.role(rolename, part)
        except Exception:
            continue
        out.extend(p if isinstance(p, (list, tuple)) else [p])
    return out


def find_devhlp_inc(explicit=None):
    """Paths to devhlp.inc, most authoritative first. May be empty."""
    if explicit:
        p = Path(explicit)
        if not p.exists():
            sys.exit("--devhlp-inc %s: no such file" % explicit)
        return [p]
    found = []
    for d in _library_inc_dirs():
        d = Path(d)
        direct = d / "devhlp.inc"
        if direct.is_file():
            found.append(direct)
        elif d.is_dir():
            # A tree root: take a bounded look rather than walking forever.
            for hit in sorted(d.rglob("devhlp.inc"))[:12]:
                found.append(hit)
    seen, out = set(), []
    for p in found:
        if str(p) not in seen:
            seen.add(str(p))
            out.append(p)
    return out


def devhlp_names(explicit=None):
    """DevHlp number -> name, merged over every devhlp.inc found.

    The first file wins for a number; later copies only supply numbers the
    earlier ones lack (different DDK components ship different vintages, and
    the later ones carry the higher-numbered helpers).
    """
    names, paths = {}, find_devhlp_inc(explicit)
    for path in paths:
        try:
            txt = path.read_text(errors="replace")
        except OSError:
            continue
        for m in re.finditer(r"DevHlp_(\w+)\s+EQU\s+(\d+)", txt, re.I):
            names.setdefault(int(m.group(2)), m.group(1))
    return names, paths


# -------------------------------------------------------------- subcommands --
def cmd_info(lx, args):
    print("=== %s: %d bytes, signature %s ==="
          % (lx.path.name, len(lx.d), lx.sig.decode("ascii", "replace")))
    if not lx.is_lx():
        print("  NOT LX - only the 'devhdr' subcommand applies to this image.")
        return
    mf = lx.modflags
    kind = ("PHYSICAL DEVICE DRIVER" if mf & 0x20000 else
            "VIRTUAL DEVICE DRIVER" if mf & 0x40000 else "program/DLL")
    print("  modflags=0x%08x -> %s\n  pages=%d pagesize=%d"
          % (mf, kind, lx.npages, lx.u32(0x28)))
    for o in lx.objects():
        print("\n  obj%d: base=0x%08x vsize=%d pages=%d flags=0x%05x"
              % (o["idx"], o["base"], o["vsize"], o["mapsize"], o["flags"]))
        for pg in lx.pages(o)[:4]:
            print("      page%2d: fileoff=0x%05x size=%5d -> %s"
                  % (pg["idx"], pg["fileoff"], pg["size"], pg["kind"]))
        if o["mapsize"] > 4:
            print("      ... (%d more)" % (o["mapsize"] - 4))
        if any(p["flags"] == 1 for p in lx.pages(o)):
            print("      *** COMPRESSED - raw-file reads of this object are GARBAGE ***")


def cmd_devhdr(paths, args):
    """Scan for SysDev headers.

    Distinguishes a device's OWNER - which declares it in a header - from an
    AttachDD CLIENT, which merely contains the name as data.
    """
    print("=== SysDev device-header scan (layout: DDK devhdr.h, name at +0x0A) ===")
    for path in paths:
        d = Path(path).read_bytes()
        print("\n  %s:" % Path(path).name)
        found = False
        for off in range(len(d) - 0x1A):
            nxt, att, strat, intr, name = parse_sysdev(d, off)
            if not (att & DEV_CHAR_DEV):
                continue
            if not all(0x20 <= c < 0x7F for c in name):
                continue
            n = name.decode("ascii").rstrip()
            if not n or "$" not in n:
                continue
            if nxt != 0xFFFFFFFF and (nxt >> 16) > 0x200:
                continue
            print("    @0x%04x DECLARES %r  next=0x%08x att=0x%04x [%s] "
                  "strat=0x%04x idc=0x%04x"
                  % (off, n, nxt, att, att_flags(att), strat, intr))
            found = True
        if not found:
            print("    declares NO device (if it contains a device name, it is "
                  "an AttachDD client, not the owner)")


def cmd_dgroup(lx, args):
    obj = lx.objects()[args.obj - 1]
    img = lx.object_image(obj)
    print("=== %s obj%d decompressed: %d bytes ==="
          % (lx.path.name, args.obj, len(img)))
    if len(img) >= 0x1A:
        nxt, att, strat, intr, name = parse_sysdev(img, 0)
        print("\n  obj%d:0x00 read as SysDev: name=%r next=0x%08x att=0x%04x "
              "[%s] strat=0x%04x idc=0x%04x"
              % (args.obj, printable(name), nxt, att, att_flags(att), strat, intr))
        print("  (a device header sits at the start of DGROUP only if this "
              "driver puts it there - check the name before believing it)")
    n = min(args.bytes, len(img))
    print("\n  first 0x%x bytes:" % n)
    for r in range(0, n, 16):
        print("    %04x  %s" % (r, img[r:r + 16].hex(" ")))


def cmd_ioctl(lx, args):
    """An IOCtl handler jump table held in a data object.

    A driver that dispatches generic IOCtl through a table typically indexes it
    by (function - base), bounded by a count or limit word stored nearby. The
    offsets below are NOT universal - they are where a particular driver's
    dispatcher was observed to read. Disassemble the Strategy/IOCtl path and
    pass --table/--bound/--func-base for the driver in front of you.
    """
    img = lx.object_image(lx.objects()[args.obj - 1])
    objs = lx.objects()
    code_size = objs[args.code_obj - 1]["vsize"] if args.code_obj <= len(objs) else 0
    if args.bound_addr + 2 > len(img):
        print("  bound word 0x%x is past the end of obj%d (%d bytes)"
              % (args.bound_addr, args.obj, len(img)))
        return
    bound = struct.unpack_from("<H", img, args.bound_addr)[0]
    print("=== IOCtl handler table @obj%d:0x%x  bound=[0x%x]=0x%04x -> %d entries ==="
          % (args.obj, args.table, args.bound_addr, bound, bound // 2))
    if not 0 < bound <= 0x100:
        print("  implausible bound - this driver probably builds its table at "
              "INIT rather than storing it statically, or the offsets are wrong "
              "for this driver (see --help).")
        return
    for i in range(bound // 2):
        off = struct.unpack_from("<H", img, args.table + i * 2)[0]
        tag = ("" if 0 < off < code_size else
               "  <- NULL/unsupported" if off == 0 else "  <- OUT OF RANGE")
        print("   func 0x%02x -> obj%d:0x%04x%s"
              % (args.func_base + i, args.code_obj, off, tag))


def cmd_imports(lx, args):
    mods, ords = lx.imports()
    print("=== %s imports ===\n  modules: %s"
          % (lx.path.name, ", ".join(mods) or "(none)"))
    print("  ordinals (%d distinct):" % len(ords))
    for k in sorted(ords):
        print("    ord %4d  x%d" % (k, ords[k]))
    if mods:
        print("\n  name an ordinal with:  extract_omf_lib_ordinals.py <lib> %s"
              % mods[0])


def devhlp_census(lx, obj_idx, devhlp_inc=None):
    """Census `call far [0x20]` sites and the DL value that reaches them.

    *** APPROXIMATE - a lead list, not a spec. ***
    ndisasm does a linear sweep: it desyncs on embedded data and invents
    instructions. Operand backtracking cannot see a DL set via a register, or
    set outside the window it looks back over. Byte-verify anything you depend
    on - `verify_byte` below is what that looks like.
    """
    obj = lx.objects()[obj_idx - 1]
    pg0 = lx.pages(obj)[0]
    try:
        asm = subprocess.run(
            ["ndisasm", "-b", "16", "-o", "0", "-e", str(pg0["fileoff"]),
             str(lx.path)], capture_output=True, text=True).stdout
    except FileNotFoundError:
        print("  ndisasm not found - install NASM (e.g. 'apt install nasm'). "
              "Every other subcommand works without it.")
        return {}, [], []

    parsed = []
    for l in asm.splitlines():
        m = re.match(r"^([0-9A-Fa-f]{8})\s+([0-9A-Fa-f]+)\s+(.*)$", l)
        if m:
            parsed.append((int(m.group(1), 16), m.group(3).strip()))

    names, incs = devhlp_names(devhlp_inc)
    hist, sites = {}, []
    for i, (addr, txt) in enumerate(parsed):
        if not re.search(r"call far \[(es:)?0x20\]", txt, re.I):
            continue
        dl = None
        for j in range(i - 1, max(-1, i - 14), -1):
            t = parsed[j][1]
            m = re.match(r"mov dx,0x([0-9a-f]+)$", t, re.I)   # gotcha 4: DL is the low byte
            if m:
                dl = int(m.group(1), 16) & 0xFF
                break
            m = re.match(r"mov dl,0x([0-9a-f]+)$", t, re.I)
            if m:
                dl = int(m.group(1), 16)
                break
            if re.match(r"(call|ret|jmp) ", t, re.I):
                break
        if dl is None:
            nm = "UNRESOLVED"
        elif dl in names:
            nm = names[dl]
        else:
            nm = "<no name for #%d>" % dl
        hist[nm] = hist.get(nm, 0) + 1
        sites.append((addr, dl, nm))
    return hist, sites, incs


def verify_byte(lx, needle, label):
    """Byte-level check - the only evidence class worth staking a claim on."""
    hits = [i for i in range(len(lx.d) - len(needle) + 1)
            if lx.d[i:i + len(needle)] == needle]
    print("  %s: pattern %s -> %d occurrence(s) in file%s"
          % (label, needle.hex(" "), len(hits),
             (" at " + ", ".join(hex(h) for h in hits)) if hits else ""))
    return hits


def cmd_devhlp(lx, args):
    hist, sites, incs = devhlp_census(lx, args.code_obj, args.devhlp_inc)
    print("=== DevHlp call-site census (obj%d) - APPROXIMATE, see --help ==="
          % args.code_obj)
    if incs:
        for p in incs[:3]:
            print("  names from: %s" % p)
    else:
        print("  no devhlp.inc found - numbers are reported unnamed.")
        print("  (os2-lib role ddk-headers inc, or pass --devhlp-inc PATH)")
    for a, dl, nm in sites:
        print("   obj%d:0x%04x  DL=%s  %s"
              % (args.code_obj, a, "??" if dl is None else "0x%02x" % dl, nm))
    if not sites:
        print("   no `call far [0x20]` sites found in this object.")
        return
    print("\n  distinct:")
    for k, v in sorted(hist.items(), key=lambda x: -x[1]):
        print("    %-28s x%d" % (k, v))

    print("\n  --- byte-verified checks (trustworthy) ---")
    seen = []
    for _a, dl, nm in sites:
        if dl is not None and dl not in seen:
            seen.append(dl)
    for dl in seen[:8]:
        nm = next((n for _a, d, n in sites if d == dl), "?")
        verify_byte(lx, b"\xb2" + bytes([dl]),
                    "%s (%d/0x%02x) via 'mov dl,0x%02x'" % (nm, dl, dl, dl))

    print("\n  presence of some common helpers (absent is a real finding too):")
    for n in ("SetIRQ", "EOI", "ProcBlock", "ProcRun", "SendEvent", "SemRequest"):
        print("    %-12s %s" % (n, "PRESENT" if n in hist else "absent"))


def main():
    ap = argparse.ArgumentParser(
        prog="driver_re.py",
        description="Static dissection of OS/2 LX/NE device drivers.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
subcommands:
  info     LX header, objects, page types, driver kind      (LX; NE reported)
  devhdr   scan for SysDev device headers                   (LX and NE)
  dgroup   materialise a data object and hexdump it         (LX)
  ioctl    read an IOCtl handler jump table                 (LX)
  imports  imported modules and ordinals, from fixups       (LX)
  devhlp   DevHlp call-site census                          (LX; needs ndisasm)
  all      info + devhdr + imports + ioctl + devhlp

requirements:
  Python 3 standard library for everything except `devhlp`, which needs
  ndisasm (NASM). DevHlp names come from IBM's devhlp.inc, found by role
  (os2-lib role ddk-headers inc) or named with --devhlp-inc.

examples:
  driver_re.py info    DRIVER.SYS
  driver_re.py devhdr  DRIVER.SYS OTHER.ADD      # several images at once
  driver_re.py dgroup  DRIVER.SYS --obj 7 --bytes 0x80
  driver_re.py devhlp  DRIVER.SYS --code-obj 3
  driver_re.py ioctl   DRIVER.SYS --obj 1 --table 0x8c --bound-addr 0xac

note on `ioctl`: the table/bound offsets are properties of the DRIVER, not of
OS/2. Disassemble its IOCtl dispatch path, see where it indexes, and pass the
offsets. The defaults are one observed convention and an implausible result is
reported as such rather than printed as a table.
""")
    ap.add_argument("cmd", choices=["info", "devhdr", "dgroup", "ioctl",
                                    "imports", "devhlp", "all"])
    ap.add_argument("driver", nargs="+", help="driver image(s)")
    ap.add_argument("--obj", type=int, default=1, metavar="N",
                    help="data object for dgroup/ioctl (default: 1)")
    ap.add_argument("--code-obj", type=int, default=2, metavar="N",
                    help="code object for devhlp/ioctl targets (default: 2)")
    ap.add_argument("--bytes", type=lambda s: int(s, 0), default=0x100,
                    metavar="N", help="dgroup hexdump length (default: 0x100)")
    ap.add_argument("--table", type=lambda s: int(s, 0), default=0x8C,
                    metavar="OFF", help="IOCtl table offset (default: 0x8c)")
    ap.add_argument("--bound-addr", type=lambda s: int(s, 0), default=0xAC,
                    metavar="OFF", help="word bounding the table (default: 0xac)")
    ap.add_argument("--func-base", type=lambda s: int(s, 0), default=0x70,
                    metavar="N", help="function code of entry 0 (default: 0x70)")
    ap.add_argument("--devhlp-inc", metavar="PATH",
                    help="IBM devhlp.inc to name DevHlp numbers from")
    args = ap.parse_args()

    if args.cmd == "devhdr":
        cmd_devhdr(args.driver, args)
        return

    lx = LX(args.driver[0])
    if not lx.is_lx():
        print("ERROR: %s is %r, not LX. Use the 'devhdr' subcommand, which "
              "works on NE drivers too." % (args.driver[0], lx.sig),
              file=sys.stderr)
        sys.exit(1)

    nobj = len(lx.objects())
    for which, n in (("--obj", args.obj), ("--code-obj", args.code_obj)):
        if not 1 <= n <= nobj:
            sys.exit("%s %d out of range (image has %d objects; run 'info')"
                     % (which, n, nobj))

    if args.cmd == "all":
        cmd_info(lx, args); print()
        cmd_devhdr(args.driver, args); print()
        cmd_imports(lx, args); print()
        cmd_ioctl(lx, args); print()
        cmd_devhlp(lx, args)
    else:
        {"info": cmd_info, "dgroup": cmd_dgroup, "ioctl": cmd_ioctl,
         "imports": cmd_imports, "devhlp": cmd_devhlp}[args.cmd](lx, args)


if __name__ == "__main__":
    # Exit quietly when a reader closes the pipe (`| head`), the way a
    # normal filter does, instead of tracebacking on BrokenPipeError.
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    main()
