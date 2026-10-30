#!/usr/bin/env python3
"""pack1.py - reader for IBM's original PACK format (magic A5 96, version
word FFFE / FFFF / 0A0A / 0A14 / 0A1E / 1400), the format UNPACK.EXE decodes
itself.  (UNPACK.EXE hands version FFFD - PACK2 - to UNPACK2.EXE; see pack2.py.)
Format: PACK_FORMAT.md beside this script.

    pack1.py list    FILE...
    pack1.py extract FILE... -d DIR [--ea-dir DIR]

The codec is 12-bit LZW with a least-recently-used recycled dictionary, ported
from UNPACK.EXE's DECODE (0001:534f) / its threaded twin FUN_0001_48a8 and the
code-fetch loops in _expreal (0001:514d) / _explode (0001:44a8).  Only version
FFFE has been seen in the wild here; FFFF and 1.x are documented in
PACK_FORMAT.md but not implemented.
"""
import argparse, datetime, os, struct, sys

MAGIC = 0x96A5
MAXCODE = 0xFFF          # [0x1066] stops growing at 0x1ffe = 4095*2


class Lzw:
    """UNPACK's dictionary.  Codes: 0 = end of stream, 1..256 = byte c-1,
    257..4095 = learned strings.  Tables are indexed by code (the original
    indexes by code*2)."""

    def __init__(self):
        n = MAXCODE + 1
        self.chr = bytearray(n)
        self.prefix = [0] * n
        self.ref = [0] * n       # number of entries using this one as prefix
        self.nxt = [0] * n       # LRU list of leaves (ref==0), 0 = sentinel
        self.prv = [0] * n
        self.reset()

    def reset(self):
        for c in range(1, 257):
            self.chr[c] = c - 1
            self.ref[c] = 1      # literals are never leaves, never recycled
        self.free = 256          # last allocated code
        self.nxt[0] = self.prv[0] = 0
        self.prev = 0            # code allocated by the previous step

    def _lru_append(self, c):
        tail = self.prv[0]
        self.prv[0] = c
        self.nxt[c] = 0
        self.prv[c] = tail
        self.nxt[tail] = c

    def decode(self, code, out):
        """DECODE: allocate (or recycle) the next entry, emit code's string,
        then make the new entry = code's string + (first byte of the NEXT
        string, filled in on the next call)."""
        if self.free != MAXCODE:
            self.free += 1
            new = self.free
        else:                                   # recycle the oldest leaf
            new = self.nxt[0]
            nh = self.nxt[new]
            self.prv[nh] = 0
            self.nxt[0] = nh
            p = self.prefix[new]
            self.ref[p] -= 1
            if self.ref[p] == 0:
                self._lru_append(p)
        # walk the prefix chain (the original reverses it in place, then
        # restores it while emitting - same bytes)
        chain = []
        c = code
        while True:
            chain.append(c)
            if c <= 256:
                break
            c = self.prefix[c]
        root = c
        self.chr[self.prev] = self.chr[root]    # complete last step's entry
        for c in reversed(chain):
            out.append(self.chr[c])
        if self.ref[code] == 0:                 # code gains a child: not a leaf
            a, b = self.prv[code], self.nxt[code]
            self.nxt[a] = b
            self.prv[b] = a
        self.ref[code] += 1
        self._lru_append(new)
        self.prev = new
        self.prefix[new] = code
        self.ref[new] = 0


def lzw_stream(d, pos, lzw):
    """Decode one LZW stream starting at d[pos] (dictionary already reset).
    Codes are 12-bit, big-endian nibble packed, two per three bytes; a zero
    code ends the stream.  Returns (bytes, position just past the end code)."""
    out = bytearray()
    while True:
        if pos + 1 >= len(d):
            raise ValueError("LZW stream runs off the end of the file")
        c = (d[pos] << 4) | (d[pos + 1] >> 4)          # first of a pair
        if c == 0:
            return bytes(out), pos + 1
        lzw.decode(c, out)
        if pos + 2 >= len(d):
            raise ValueError("LZW stream runs off the end of the file")
        c = ((d[pos + 1] & 0x0F) << 8) | d[pos + 2]     # second of a pair
        pos += 3
        if c == 0:
            return bytes(out), pos
        lzw.decode(c, out)


class Header:
    """Version FFFE header: 0x1a fixed bytes + name (padded to even length)."""

    def __init__(self, d, off):
        (self.magic, self.ver, self.fdate, self.ftime, self.attr, self.flags,
         self.ea_off, self.size, self.next_off, nlen) = struct.unpack_from("<HHHHHHIIIH", d, off)
        self.nlen = nlen
        self.name = d[off + 0x1A:off + 0x1A + nlen].split(b"\0")[0].decode("cp850")
        self.off = off
        self.data_off = off + 0x1A + nlen
        self.ea_pos = None               # set by members() when an EA stream is found

    @property
    def mtime(self):
        try:
            return datetime.datetime(1980 + (self.fdate >> 9), (self.fdate >> 5) & 0xF, self.fdate & 0x1F,
                                     self.ftime >> 11, (self.ftime >> 5) & 0x3F, (self.ftime & 0x1F) * 2)
        except ValueError:
            return None


def _align_skip(d, pos, base):
    """START_NEXT_FILE / EAT_ZEROS: pad to a 4-byte boundary (counted from
    the start of the first member's data, as _expreal's buffer is), then
    skip whole zero dwords."""
    pos += (-(pos - base)) & 3
    while pos + 4 <= len(d) and d[pos:pos + 4] == b"\0\0\0\0":
        pos += 4
    return pos


HDR_MAGIC = b"\xa5\x96\xfe\xff"


def members(d, check=None):
    """Yield (Header, data bytes, FEALIST bytes or None) for a FFFE file.

    Follows UNPACK's own streaming rule (_expreal / START_NEXT_FILE /
    STRIP_HEADER; threaded twin FLUSH_LAST_BUFF / EAT_ZEROS / NEXT_HEADER):
      data stream (absent if size==0), end code;
      if this header's next-offset and EA-offset are both 0: stop (the
        trailer is never read);
      pad to 4, skip zero dwords; an A5 96 FE FF header there starts the next
        member, anything else is this member's EA stream; after an EA stream,
        pad/skip again, then a header or the end.
    The header pointers (+0x0c EA, +0x14 next) are NOT used for positions:
    real files have them misplaced (eCS CID/SERVER/FFST/EPW/EPWDRIVR.PAK),
    and IBM UNPACK ignores them except as the "anything more?" test above.
    If `check` is a list, every place the pointers disagree is appended."""
    magic, ver = struct.unpack_from("<HH", d, 0)
    if magic != MAGIC:
        raise ValueError("not a PACK file")
    if ver == 0xFFFD:
        raise ValueError("PACK2 (FFFD) archive: use pack2.py")
    if ver != 0xFFFE:
        raise ValueError("PACK version %04x not supported yet" % ver)
    lzw = Lzw()
    off = 0
    base = None
    nmem = 0
    while True:
        nmem += 1
        h = Header(d, off)
        if base is None:
            base = h.data_off
        data, pos = b"", h.data_off
        if h.size:                       # STRIP_HEADER: size 0 = no data stream
            lzw.reset()
            data, pos = lzw_stream(d, h.data_off, lzw)
        ea = None
        nxt = None
        if h.next_off or h.ea_off:
            q = _align_skip(d, pos, base)
            if q + 4 <= len(d) and d[q:q + 4] == HDR_MAGIC:
                nxt = q
            elif q < len(d) - 4:
                if check is not None and h.ea_off != q:
                    check.append("%s: EA stream at %#x, header says %#x" % (h.name, q, h.ea_off))
                lzw.reset()
                h.ea_pos = q                 # where the EA stream really starts
                ea, pos = lzw_stream(d, q, lzw)
                q = _align_skip(d, pos, base)
                if q + 4 <= len(d) and d[q:q + 4] == HDR_MAGIC:
                    nxt = q
        if check is not None:
            if nxt is not None and h.next_off != nxt:
                check.append("%s: next member at %#x, header says %#x" % (h.name, nxt, h.next_off))
            if ea is None and h.ea_off:
                check.append("%s: header says EA at %#x, none found" % (h.name, h.ea_off))
        yield h, data, ea
        if nxt is None:
            if check is not None:
                # trailer (never read by UNPACK): 0-3 zero bytes, then usually
                # a u32 member count; NOT 4-aligned
                tail = d[pos:]
                ok = (not tail.strip(b"\0")) or (
                    len(tail) >= 4 and not tail[:-4].strip(b"\0")
                    and struct.unpack_from("<I", tail, len(tail) - 4)[0] == nmem)
                if not ok:
                    check.append("%s: trailer %r" % (h.name, tail.hex()[:40]))
            return
        off = nxt


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["list", "extract", "test"])
    ap.add_argument("files", nargs="+")
    ap.add_argument("-d", "--dir", default=".")
    ap.add_argument("--ea-dir")
    a = ap.parse_args(argv)
    rc = 0
    for path in a.files:
        d = open(path, "rb").read()
        print(path)
        try:
            for h, data, ea in members(d):
                ok = len(data) == h.size or h.size == 1
                if not ok:
                    rc = 1
                t = h.mtime
                if a.cmd in ("list", "test"):
                    print("  %-30s %9d %s attr=%02x%s%s" % (
                        h.name, len(data), t.strftime("%Y-%m-%d %H:%M") if t else "?", h.attr,
                        " EA" if ea is not None else "", "" if ok else "  SIZE MISMATCH hdr=%d" % h.size))
                    continue
                dst = os.path.join(a.dir, h.name.replace("\\", "/").lstrip("/"))
                os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
                open(dst, "wb").write(data)
                if t:
                    os.utime(dst, (t.timestamp(), t.timestamp()))
                if ea is not None and a.ea_dir:
                    ed = os.path.join(a.ea_dir, h.name + ".fealist")
                    os.makedirs(os.path.dirname(ed) or ".", exist_ok=True)
                    open(ed, "wb").write(ea)
                print("  %s -> %s" % (h.name, dst))
        except (ValueError, IndexError) as e:
            print("  ERROR %s" % e, file=sys.stderr)
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
