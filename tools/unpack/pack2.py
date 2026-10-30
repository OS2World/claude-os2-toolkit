#!/usr/bin/env python3
"""pack2.py - read IBM PACK2 archives (magic A5 96 FD FF), the format
UNPACK2.EXE handles.  Format: FTCOMP_FORMAT.md beside this script.  Codec: ftcomp.py.

    pack2.py list    ARCHIVE...              (like UNPACK2 /SHOW /SIZES)
    pack2.py extract ARCHIVE... -d DIR [-n NAME] [--flat] [--ea-dir DIR]

Needs IBM's UNPACK2.EXE for the codec's constant tables: --unpack2 PATH, or
$OS2_UNPACK2. It is \\OS2\\UNPACK2.EXE on any installed OS/2; copy it off the
system (this kit ships no IBM binaries). `list` works without it.

extract writes each member under DIR at its stored path (UNPACK2's /P
behaviour); --flat writes the file name only (UNPACK2's default when a target
is given).  Timestamps come from the header's FDATE/FTIME.  EAs can't be
represented on a Linux file system, so each member's decoded FEALIST is written
to --ea-dir as <member path>.fealist when that option is given.
"""
import argparse, datetime, os, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ftcomp

MAGIC = 0x96A5
VER_PACK2 = 0xFFFD
HDR_FIXED = 0x29


class Member:
    """One PACK2 file header (the 0x29-byte fixed part + name)."""

    def __init__(self, d, off):
        (self.magic, self.ver, self.fdate, self.ftime, self.attr, self.flags,
         self.ea_off, self.size, self.next_off) = struct.unpack_from("<HHHHHHIII", d, off)
        self.alg = d[off + 0x18:off + 0x21].split(b"\0")[0].decode("latin-1")
        self.alg_ver = struct.unpack_from("<H", d, off + 0x21)[0]
        self.field23 = struct.unpack_from("<I", d, off + 0x23)[0]
        nlen = struct.unpack_from("<H", d, off + 0x27)[0]
        self.name = d[off + HDR_FIXED:off + HDR_FIXED + nlen].split(b"\0")[0].decode("cp850")
        self.off = off
        self.data_off = off + HDR_FIXED + nlen
        # _CalcMaxBytesToRead: data runs to the EA stream, else the next
        # header, else the 4-byte trailer at EOF
        if self.ea_off:
            self.data_end = self.ea_off
        elif self.next_off:
            self.data_end = self.next_off
        else:
            self.data_end = len(d) - 4
        # _EaXfer: the EA stream runs to the next header, else the trailer
        self.ea_end = (self.next_off or len(d) - 4) if self.ea_off else None

    @property
    def mtime(self):
        """FDATE/FTIME (OS/2 packed date/time) as a datetime, or None."""
        y = 1980 + (self.fdate >> 9)
        mo = (self.fdate >> 5) & 0xF
        da = self.fdate & 0x1F
        h, mi, s = self.ftime >> 11, (self.ftime >> 5) & 0x3F, (self.ftime & 0x1F) * 2
        try:
            return datetime.datetime(y, mo, da, h, mi, s)
        except ValueError:
            return None


def members(d):
    """Walk the header chain of a PACK2 archive.  Raises on a non-PACK2 file."""
    m0 = struct.unpack_from("<HH", d, 0)
    if m0 != (MAGIC, VER_PACK2):
        raise ValueError("not a PACK2 archive (magic %04x %04x)" % m0)
    out = []
    off = 0
    while True:
        m = Member(d, off)
        if m.magic != MAGIC:
            raise ValueError("bad header magic at %#x" % off)
        out.append(m)
        if not m.next_off:
            break
        if m.next_off <= off:
            raise ValueError("header chain loops at %#x" % off)
        off = m.next_off
    count = struct.unpack_from("<I", d, len(d) - 4)[0]
    if count != len(out):
        print("warning: trailer says %d members, chain has %d" % (count, len(out)), file=sys.stderr)
    return out


def decode(dec, d, m):
    """Returns (file bytes, FEALIST bytes or None) for member m."""
    if m.alg.upper() != "FTCOMP" or m.alg_ver != 1:     # _AlgorithmOk
        raise ValueError("unsupported algorithm %s v%d" % (m.alg, m.alg_ver))
    data = ftcomp.decode_member(dec, d[m.data_off:m.data_end]) if m.size else b""
    ea = None
    if m.ea_off:
        ea = bytearray(ftcomp.decode_member(dec, d[m.ea_off:m.ea_end]))
        struct.pack_into("<I", ea, 0, len(ea))          # _WriteEaBuf patches cbList
        ea = bytes(ea)
    return data, ea


def default_tables():
    return os.environ.get("OS2_UNPACK2")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["list", "extract", "test"])
    ap.add_argument("archives", nargs="+")
    ap.add_argument("-d", "--dir", default=".")
    ap.add_argument("-n", "--name", help="only the member whose file name matches (like /N:)")
    ap.add_argument("--flat", action="store_true", help="drop stored directories")
    ap.add_argument("--ea-dir")
    ap.add_argument("--unpack2", default=default_tables())
    a = ap.parse_args(argv)

    dec = None
    if a.cmd != "list":
        if not a.unpack2 or not os.path.isfile(a.unpack2):
            sys.exit("pack2.py: %s needs IBM's UNPACK2.EXE for the codec's tables: pass\n"
                     "  --unpack2 PATH or set OS2_UNPACK2 (it is \\OS2\\UNPACK2.EXE on any OS/2)"
                     % a.cmd)
        dec = ftcomp.FtcompDecoder(ftcomp.load_tables(a.unpack2))
    rc = 0
    for path in a.archives:
        d = open(path, "rb").read()
        try:
            ms = members(d)
        except ValueError as e:
            print("%s: %s" % (path, e), file=sys.stderr)
            rc = 1
            continue
        print(path)
        for m in ms:
            leaf = m.name.replace("\\", "/").rsplit("/", 1)[-1]
            if a.name and leaf.lower() != a.name.lower():
                continue
            if a.cmd == "list":
                packed = (m.next_off or len(d) - 4) - m.off
                t = m.mtime
                print("->%-40s %9d %9d %s attr=%02x%s" % (
                    m.name, m.size, packed, t.strftime("%Y-%m-%d %H:%M") if t else "?",
                    m.attr, " EA" if m.ea_off else ""))
                continue
            try:
                data, ea = decode(dec, d, m)
            except (ValueError, IndexError) as e:
                print("  %s: DECODE ERROR %s" % (m.name, e), file=sys.stderr)
                rc = 1
                continue
            if len(data) != m.size:
                print("  %s: size %d != header %d" % (m.name, len(data), m.size), file=sys.stderr)
                rc = 1
            if a.cmd == "test":
                print("  ok %s" % m.name)
                continue
            rel = leaf if a.flat else m.name.replace("\\", "/").lstrip("/")
            if len(rel) > 1 and rel[1] == ":":
                rel = rel[2:].lstrip("/")
            dst = os.path.join(a.dir, rel)
            os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
            with open(dst, "wb") as f:
                f.write(data)
            t = m.mtime
            if t:
                ts = t.timestamp()
                os.utime(dst, (ts, ts))
            if ea is not None and a.ea_dir:
                ed = os.path.join(a.ea_dir, rel + ".fealist")
                os.makedirs(os.path.dirname(ed) or ".", exist_ok=True)
                open(ed, "wb").write(ea)
            print("  %s -> %s" % (m.name, dst))
    return rc


if __name__ == "__main__":
    sys.exit(main())
