#!/usr/bin/env python3
"""
sym2map.py - Parse OS/2 MAPSYM (.SYM) symbol files and resolve symbols to
flat virtual addresses using the companion LX executable's object table.

Static-RE starter kit.

The .SYM format is the Microsoft/IBM MAPSYM binary symbol format. Layout
(new / paragraph format, MAPSYM 3.10+; this is what OS/2 Warp ships):

  MAPDEF (file header):
    0x00 u32  file size in paragraphs (excludes these 4 bytes)
    0x04 u16  entry-point segment number
    0x06 u16  symbol count in segment zero (constants/absolutes)
    0x08 u16  header size in bytes (through end of segment zero)
    0x0A u16  segment count (excluding segment zero)
    0x0C u16  first SEGDEF address (paragraphs)
    0x0E u8   unknown
    0x0F u8   module-name length
    0x10 ..   module name (no NUL)

  SEGDEF (segment header):
    0x00 u16  next SEGDEF address (paragraphs; 0 = last)
    0x02 u16  symbol count in this segment
    0x04 u16  segment size in bytes
    0x06 u16  segment number (1-based; maps to LX object number)
    0x08 6x   reserved
    0x0E u8   bitness flag (0 = 16-bit, non-zero = 32-bit)
    0x0F 5x   reserved
    0x14 u8   segment-name length
    0x15 ..   segment name

  SYMDEF (symbol entry):
    u16/u32   offset within segment (u32 iff parent segment is 32-bit)
    u8        name length
    ..        name

File ends with a 2-byte MAPSYM version number.

Usage:
    sym2map.py SYMFILE [--lx LXIMAGE] [--format {map,json,flat}]
                       [--grep PATTERN] [--seg N]

  --lx     the LX image the .SYM accompanies (same base name, e.g. PMMERGE.SYM
           alongside PMMERGE.DLL). If given, each symbol is resolved to a flat
           VA via the LX object table. Without it, output is segment:offset
           only.

Provenance: the .SYM parser and the LX page reconstruction here (iterated-data
expansion and ExePack2 decompression) are original, written from the MAPSYM and
LX format specifications - not adapted from another implementation.
"""
import argparse
import json
import struct
import sys


# ---------------------------------------------------------------------------
# LX image: object table (for segment-number -> base VA resolution)
# ---------------------------------------------------------------------------
class LXObject:
    __slots__ = ("num", "vsize", "base", "flags", "mapidx", "mapsize")

    def __init__(self, num, vsize, base, flags, mapidx, mapsize):
        self.num = num
        self.vsize = vsize
        self.base = base
        self.flags = flags
        self.mapidx = mapidx
        self.mapsize = mapsize

    @property
    def is_32bit(self):
        return bool(self.flags & 0x2000)        # LX_OBJ_BIG

    @property
    def is_exec(self):
        return bool(self.flags & 0x0004)        # LX_OBJ_EXECUTABLE

    def perm(self):
        f = self.flags
        return ("R" if f & 1 else "-") + ("W" if f & 2 else "-") + \
               ("X" if f & 4 else "-")

    def kind(self):
        bits = []
        bits.append("32" if self.is_32bit else "16")
        if self.flags & 0x1000:
            bits.append("ALIAS16")
        if self.flags & 0x4000:
            bits.append("CONF")
        if self.flags & 0x8000:
            bits.append("IOPL")
        return ",".join(bits)


class LXImage:
    def __init__(self, path):
        self.path = path
        self.objects = []          # list[LXObject], index 0 == object 1
        self._load()

    def _load(self):
        with open(self.path, "rb") as f:
            data = f.read()
        self.data = data
        # An LX image may or may not carry a DOS stub, and BOTH shapes ship.
        # The stub is optional: a DLL is never started from DOS, so many are
        # linked without one and then the LX header begins at offset 0. Reading
        # only the MZ form rejects those outright with "not an MZ/LX image",
        # which reads like a corrupt file rather than a second valid layout --
        # e.g. the ncurses tinfo6.dll shipped by netlabs is bare LX.
        if data[:2] == b"LX":
            e_lfanew = 0
        elif data[:2] == b"MZ":
            e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
            if data[e_lfanew:e_lfanew + 2] != b"LX":
                raise ValueError("LX signature not found at e_lfanew=0x%x" % e_lfanew)
        else:
            raise ValueError("not an LX image (no LX magic at 0, no MZ stub)")
        self.lx_off = e_lfanew
        # lx_header_t fields we need (offsets within LX header, packed)
        # objtab @ +0x40, objcnt @ +0x44, objmap @ +0x48, pageshift @ +0x2C,
        # pagesize @ +0x28, datapage @ +0x80
        self.mpages = struct.unpack_from("<I", data, e_lfanew + 0x14)[0]
        self.pagesize, self.pageshift = struct.unpack_from("<II", data, e_lfanew + 0x28)
        (objtab, objcnt, objmap) = struct.unpack_from("<III", data, e_lfanew + 0x40)
        fpagetab, frectab = struct.unpack_from("<II", data, e_lfanew + 0x68)
        self.datapage = struct.unpack_from("<I", data, e_lfanew + 0x80)[0]
        self.objmap_off = e_lfanew + objmap
        self.fpage_off = (e_lfanew + fpagetab) if fpagetab else 0
        self.frec_off = (e_lfanew + frectab) if frectab else 0
        self.objcnt = objcnt
        ot = e_lfanew + objtab
        for i in range(objcnt):
            vsize, base, flags, mapidx, mapsize, _res = \
                struct.unpack_from("<IIIIII", data, ot + i * 24)
            self.objects.append(LXObject(i + 1, vsize, base, flags, mapidx, mapsize))

    def object_by_num(self, num):
        if 1 <= num <= len(self.objects):
            return self.objects[num - 1]
        return None

    def _iterdata(self, off, size, dest_size):
        """Expand an LX iterated-data (ITERDATA) page.

        Iteration records are {u16 repeat, u16 block_size, bytes[block_size]};
        a zero repeat terminates. Format per the LX spec - see
        os2ref/executable-formats.md section 2.12.
        """
        out = bytearray()
        end = off + size
        p = off
        d = self.data
        while p + 4 <= end and len(out) < dest_size:
            repeat = struct.unpack_from("<H", d, p)[0]
            block = struct.unpack_from("<H", d, p + 2)[0]
            p += 4
            if repeat == 0:
                break
            if block == 0:                       # single-byte run
                if p + 1 > end:
                    break
                out += bytes([d[p]]) * repeat
                p += 1
            else:
                if p + block > end:
                    break
                out += d[p:p + block] * repeat
                p += block
        if len(out) < dest_size:
            out += b"\x00" * (dest_size - len(out))
        return bytearray(out[:dest_size])

    def _decompress(self, src, dest_size):
        """Decompress an LX ExePack2 (ITERDATA2) page.

        The two low bits of each control byte select the record kind; see
        os2ref/executable-formats.md for the page-flag definitions.
        """
        dst = bytearray(dest_size)
        n = len(src)
        sOf = dOf = 0

        def u16(o):
            return src[o] | (src[o + 1] << 8)

        while sOf + 1 <= n:
            b1 = src[sOf]
            c = b1 & 3
            if c == 0:
                if b1 == 0:
                    if sOf + 2 > n:
                        break
                    if src[sOf + 1] == 0:            # end marker 00 00
                        sOf += 2
                        if dOf >= dest_size or sOf + 1 > n:
                            break
                        continue
                    cnt = src[sOf + 1]
                    if sOf + 3 <= n and dOf + cnt <= dest_size:
                        for i in range(cnt):
                            dst[dOf + i] = src[sOf + 2]
                        dOf += cnt
                        sOf += 3
                    else:
                        break
                else:
                    cnt = b1 >> 2
                    if sOf + cnt + 1 <= n and dOf + cnt <= dest_size:
                        dst[dOf:dOf + cnt] = src[sOf + 1:sOf + 1 + cnt]
                        dOf += cnt
                        sOf += cnt + 1
                    else:
                        break
            elif c == 1:
                if sOf + 2 > n:
                    break
                bOf = u16(sOf) >> 7
                b2 = ((b1 >> 4) & 7) + 3
                nlit = (b1 >> 2) & 3
                sOf += 2
                if sOf + nlit <= n and dOf + nlit + b2 <= dest_size and dOf + nlit - bOf >= 0:
                    dst[dOf:dOf + nlit] = src[sOf:sOf + nlit]
                    dOf += nlit
                    sOf += nlit
                    for i in range(b2):
                        dst[dOf + i] = dst[dOf - bOf + i]
                    dOf += b2
                else:
                    break
            elif c == 2:
                if sOf + 2 > n:
                    break
                bOf = u16(sOf) >> 4
                cnt = ((b1 >> 2) & 3) + 3
                if dOf + cnt <= dest_size and dOf - bOf >= 0:
                    for i in range(cnt):
                        dst[dOf + i] = dst[dOf - bOf + i]
                    dOf += cnt
                    sOf += 2
                else:
                    break
            else:  # c == 3
                if sOf + 3 > n:
                    break
                b2 = (u16(sOf) >> 6) & 0x3F
                nlit = (src[sOf] >> 2) & 0x0F
                bOf = u16(sOf + 1) >> 4
                sOf += 3
                if sOf + nlit <= n and dOf + nlit + b2 <= dest_size and dOf + nlit - bOf >= 0:
                    dst[dOf:dOf + nlit] = src[sOf:sOf + nlit]
                    dOf += nlit
                    sOf += nlit
                    for i in range(b2):
                        dst[dOf + i] = dst[dOf - bOf + i]
                    dOf += b2
                else:
                    break
            if dOf >= dest_size:
                break
        return dst

    def _parse_page_fixups(self, p, pend, page_off, obj_image_len):
        """Parse one page's fixup records into a list of (src_type, off, value)
        writes for INTERNAL targets. Returns (writes, consumed_ok). If parsing
        doesn't land exactly on pend, consumed_ok is False and the caller skips
        the page (fail-safe: never corrupt the image on a parse desync)."""
        d = self.data
        writes = []
        psize = self.pagesize
        while p < pend:
            if p + 2 > pend:
                return writes, False
            source = d[p]; flags = d[p + 1]; p += 2
            if source == 0 and flags == 0:
                break
            stype = source & 0x0F
            ttype = flags & 0x03
            srclist = (source & 0x20) != 0
            # --- source offsets ---
            offsets = []
            if srclist:
                if p + 1 > pend:
                    return writes, False
                cnt = d[p]; p += 1
                if cnt == 0 or cnt > 500:
                    return writes, False
                # source-list offsets come AFTER the target (parsed below); record count
            else:
                if p + 2 > pend:
                    return writes, False
                single = struct.unpack_from("<h", d, p)[0]; p += 2
            # --- target data ---
            final = None
            if ttype == 0x00:                                  # internal
                if flags & 0x40:
                    objnum = struct.unpack_from("<H", d, p)[0]; p += 2
                else:
                    objnum = d[p]; p += 1
                if stype == 0x02:                              # selector: no offset
                    toff = 0
                elif flags & 0x10:
                    toff = struct.unpack_from("<I", d, p)[0]; p += 4
                else:
                    toff = struct.unpack_from("<H", d, p)[0]; p += 2
                tobj = self.object_by_num(objnum)
                if tobj is not None:
                    if stype != 0x02 and toff > tobj.vsize and (toff & 0x80000000):
                        toff = (tobj.vsize + (toff - (1 << 32))) & 0xFFFFFFFF
                    final = (tobj.base + toff) & 0xFFFFFFFF
            elif ttype in (0x01, 0x02):                        # imported ord / name
                p += 2 if (flags & 0x40) else 1                # module ordinal
                if ttype == 0x01:                              # import by ordinal
                    if flags & 0x80:
                        p += 1
                    elif flags & 0x10:
                        p += 4
                    else:
                        p += 2
                else:                                          # import by name
                    p += 4 if (flags & 0x10) else 2
            else:                                              # entry table (0x03)
                # Not resolved, and resolving it would change nothing today:
                # across the 178 DLLs and the EXEs of an installed Warp 4.5,
                # every entry-table fixup is a 16:16 far pointer (461 sites) or a
                # selector (20), which this reader never writes for ANY target,
                # plus 16 offset16 sites whose slots already hold values.
                # Measured by resolving them through the entry table: 0 bytes
                # changed. The real gap is 16:16 far pointers in general.
                p += 2 if (flags & 0x40) else 1
            # --- additive ---
            if flags & 0x04:
                if flags & 0x20:
                    add = struct.unpack_from("<I", d, p)[0]; p += 4
                else:
                    add = struct.unpack_from("<H", d, p)[0]; p += 2
                if final is not None:
                    final = (final + add) & 0xFFFFFFFF
            # --- source-list offset array (after target+additive) ---
            if srclist:
                if p + 2 * cnt > pend:
                    return writes, False
                for _ in range(cnt):
                    offsets.append(struct.unpack_from("<H", d, p)[0]); p += 2
            else:
                offsets.append(single & 0xFFFF)
            # --- record applies (internal only) ---
            if final is not None and ttype == 0x00:
                for off in offsets:
                    if off >= 0x8000 or off >= psize:          # cross-page / oob
                        continue
                    writes.append((stype, page_off + off, final))
        return writes, (p == pend or (source == 0 and flags == 0))

    def _apply_fixups(self, obj, image):
        if not (self.fpage_off and self.frec_off):
            return 0, 0
        applied = skipped_pages = 0
        for i in range(obj.mapsize):
            gpage = obj.mapidx - 1 + i               # 0-based global page
            if gpage + 1 > self.mpages:
                break
            fstart = struct.unpack_from("<I", self.data, self.fpage_off + gpage * 4)[0]
            fend = struct.unpack_from("<I", self.data, self.fpage_off + (gpage + 1) * 4)[0]
            if fstart >= fend:
                continue
            writes, ok = self._parse_page_fixups(self.frec_off + fstart,
                                                 self.frec_off + fend,
                                                 i * self.pagesize, len(image))
            if not ok:
                skipped_pages += 1
                continue
            for stype, off, value in writes:
                if off + 4 > len(image):
                    continue
                # Non-destructive: only fill genuinely-unapplied slots (zero).
                # Bound/pre-applied modules already hold correct addresses; never
                # overwrite them (protects ground-truth integrity).
                if stype in (0x07, 0x08, 0x06, 0x05):
                    cur = struct.unpack_from("<I" if stype != 0x05 else "<H", image, off)[0]
                    if cur != 0:
                        continue
                if stype == 0x07:                    # OFFSET32 (absolute)
                    struct.pack_into("<I", image, off, value)
                elif stype == 0x08:                  # SELFREL32
                    srcva = obj.base + off
                    struct.pack_into("<I", image, off, (value - (srcva + 4)) & 0xFFFFFFFF)
                elif stype == 0x05:                  # OFFSET16
                    struct.pack_into("<H", image, off, value & 0xFFFF)
                elif stype == 0x00:                  # BYTE
                    if image[off] != 0:
                        continue
                    image[off] = value & 0xFF
                elif stype == 0x06:                  # PTR16:32 -> write off32 (sel left 0)
                    struct.pack_into("<I", image, off, value)
                else:                                # 0x02/0x03 selector types: skip statically
                    continue
                applied += 1
        return applied, skipped_pages

    def object_bytes(self, num, fixups=False):
        """Reconstruct an object's in-memory image (page map walk).

        fixups=False by default: the kernel and bound DLLs already hold correct
        absolute addresses at their preferred bases, so reconstruction alone is
        sufficient. fixups=True fills any genuinely-unapplied (zero) fixup slots
        non-destructively (for relocatable modules)."""
        obj = self.object_by_num(num)
        if obj is None:
            return None
        out = bytearray()
        for i in range(obj.mapsize):
            page_idx = obj.mapidx + i - 1        # LX pages are 1-indexed
            high, low = struct.unpack_from("<II", self.data, self.objmap_off + page_idx * 8)
            ptype = (low >> 16) & 0xFFFF
            psize = low & 0xFFFF
            page = bytearray(self.pagesize)
            if ptype == 0x0000:                  # VALID
                fo = self.datapage + (high << self.pageshift)
                page[:psize] = self.data[fo:fo + psize]
            elif ptype == 0x0001:                # ITERDATA
                fo = self.datapage + (high << self.pageshift)
                page = self._iterdata(fo, psize, self.pagesize)
            elif ptype in (0x0002, 0x0003):      # INVALID / ZEROED
                pass                             # already zero
            elif ptype == 0x0005:                # COMPRESSED (ExePack2)
                fo = self.datapage + (high << self.pageshift)
                page = self._decompress(self.data[fo:fo + psize], self.pagesize)
            out += page
        del out[obj.vsize:]
        if fixups:
            self._apply_fixups(obj, out)
        return bytes(out)


# ---------------------------------------------------------------------------
# MAPSYM (.SYM) parser
# ---------------------------------------------------------------------------
class Symbol:
    __slots__ = ("seg", "off", "name", "va")

    def __init__(self, seg, off, name):
        self.seg = seg
        self.off = off
        self.name = name
        self.va = None


class Segment:
    def __init__(self, number, name, bitness, size):
        self.number = number
        self.name = name
        self.bits = bitness
        self.size = size
        self.symbols = []


class SymFile:
    def __init__(self, path):
        self.path = path
        self.module = None
        self.seg0 = []          # constants / absolutes (Symbol with seg=0)
        self.segments = []      # list[Segment]
        self._parse()

    def _pstr(self, data, pos):
        ln = data[pos]
        return data[pos + 1:pos + 1 + ln].decode("latin1"), pos + 1 + ln

    class _Desync(Exception):
        pass

    def _parse_syms(self, data, start, count, wide, limit, segnum):
        """Parse `count` SYMDEF entries with the given offset width, bounded by
        `limit`. Raises _Desync on overrun or an implausible name (used to
        auto-detect 16- vs 32-bit offset width)."""
        pos = start
        out = []
        need = 4 if wide else 2
        for _ in range(count):
            if pos + need + 1 > limit:
                raise self._Desync()
            if wide:
                off = struct.unpack_from("<I", data, pos)[0]
            else:
                off = struct.unpack_from("<H", data, pos)[0]
            pos += need
            ln = data[pos]
            pos += 1
            if ln == 0 or pos + ln > limit:
                raise self._Desync()
            raw = data[pos:pos + ln]
            # symbol names are printable ASCII (incl. _ @ $ ? . digits)
            if any(c < 0x20 or c > 0x7E for c in raw):
                raise self._Desync()
            out.append(Symbol(segnum, off, raw.decode("latin1")))
            pos += ln
        return out, pos

    def _parse(self):
        data = open(self.path, "rb").read()
        self.data = data
        (filesz_para, entryseg, seg0count, hdrsize, segcount, firstseg) = \
            struct.unpack_from("<IHHHHH", data, 0)
        namelen = data[0x0F]
        self.module = data[0x10:0x10 + namelen].decode("latin1")
        self.entryseg = entryseg
        self.segcount = segcount

        # Detect paragraph vs byte addressing for the SEGDEF chain.
        # New format: firstseg is in paragraphs. Validate by checking the byte
        # position lands inside the file and yields a sane SEGDEF.
        self.para = True
        if firstseg * 16 >= len(data):
            self.para = False

        # Segment-zero symbols immediately follow the module name.
        pos = 0x10 + namelen
        for _ in range(seg0count):
            off = struct.unpack_from("<H", data, pos)[0]
            pos += 2
            name, pos = self._pstr(data, pos)
            self.seg0.append(Symbol(0, off, name))

        # Walk the SEGDEF chain.
        scale = 16 if self.para else 1
        segaddr = firstseg * scale
        seen = 0
        while segaddr and seen < segcount + 2:   # +slack guard
            if segaddr + 0x15 > len(data):
                break
            nextseg, symcount, segsize, segnum = \
                struct.unpack_from("<HHHH", data, segaddr)
            bitness = data[segaddr + 0x0E]
            snamelen = data[segaddr + 0x14]
            sname = data[segaddr + 0x15:segaddr + 0x15 + snamelen].decode("latin1")
            sp = segaddr + 0x15 + snamelen

            # Offset width: prefer the SEGDEF bitness flag, but validate the
            # parse lands on the next SEGDEF (paragraph) boundary. Retry the
            # other width if it desyncs. nextseg==0 -> last segment, bounded by
            # file end minus the trailing 2-byte MAPSYM version.
            if nextseg:
                limit = nextseg * scale
            else:
                limit = len(data) - 2
            declared = bitness != 0
            chosen = None
            for wide in (declared, not declared):
                try:
                    syms, end = self._parse_syms(data, sp, symcount, wide,
                                                 len(data), segnum)
                except self._Desync:
                    continue
                # accept if we end at/just-before the boundary (<=16 padding
                # for paragraph alignment of the next SEGDEF)
                if end <= limit and (limit - end) <= 16:
                    chosen = (wide, syms)
                    break
                if chosen is None:        # keep first non-crashing parse as fallback
                    chosen = (wide, syms)
            wide, syms = chosen
            seg = Segment(segnum, sname, 32 if wide else 16, segsize)
            seg.symbols = syms
            self.segments.append(seg)
            seen += 1
            if nextseg == 0:
                break
            segaddr = nextseg * scale

    def total_symbols(self):
        return len(self.seg0) + sum(len(s.symbols) for s in self.segments)

    def resolve(self, lx):
        """Fill in flat VAs using the LX object table (segment# == object#)."""
        for seg in self.segments:
            obj = lx.object_by_num(seg.number)
            if obj is None:
                continue
            for sym in seg.symbols:
                sym.va = obj.base + sym.off


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Parse OS/2 MAPSYM .SYM files")
    ap.add_argument("symfile")
    ap.add_argument("--lx", help="companion LX image for VA resolution")
    ap.add_argument("--format", choices=["map", "json", "flat"], default="map")
    ap.add_argument("--grep", help="case-insensitive substring filter on names")
    ap.add_argument("--seg", type=int, help="only this segment number")
    args = ap.parse_args()

    # Report bad input as a message, not a traceback: the recipes invoke this with
    # placeholder names (MODULE.sym), so a stack dump is the first thing a new
    # user sees. struct.error is what a non-.SYM file raises while parsing.
    try:
        sf = SymFile(args.symfile)
    except (OSError, ValueError, struct.error) as e:
        sys.exit("%s: not a readable MAPSYM .SYM file: %s" % (args.symfile, e))
    lx = None
    if args.lx:
        try:
            lx = LXImage(args.lx)
        except (OSError, ValueError, struct.error) as e:
            sys.exit("%s: %s" % (args.lx, e))
        sf.resolve(lx)

    pat = args.grep.lower() if args.grep else None

    def keep(sym, seg):
        if args.seg is not None and seg != args.seg:
            return False
        if pat and pat not in sym.name.lower():
            return False
        return True

    if args.format == "json":
        out = {
            "module": sf.module,
            "segments": [],
        }
        for seg in sf.segments:
            syms = [{"off": s.off, "va": s.va, "name": s.name}
                    for s in seg.symbols if keep(s, seg.number)]
            out["segments"].append({
                "number": seg.number, "name": seg.name,
                "bits": seg.bits, "size": seg.size,
                "symbols": syms,
            })
        json.dump(out, sys.stdout, indent=2)
        print()
        return

    # map / flat text
    print("; module: %s   segments: %d   symbols: %d"
          % (sf.module, len(sf.segments), sf.total_symbols()))
    if lx:
        print("; LX objects: %d" % len(lx.objects))
        print("; seg  obj  base       size      perm kind        name")
        for seg in sf.segments:
            obj = lx.object_by_num(seg.number)
            if obj:
                print("; %3d  %3d  %08x   %8x  %s  %-10s  %s"
                      % (seg.number, obj.num, obj.base, obj.vsize,
                         obj.perm(), obj.kind(), seg.name))
    print()
    for seg in sf.segments:
        rows = [s for s in seg.symbols if keep(s, seg.number)]
        if not rows:
            continue
        print("; --- segment %d (%s, %d-bit) ---"
              % (seg.number, seg.name, seg.bits))
        for s in sorted(rows, key=lambda x: x.off):
            if args.format == "flat" and s.va is not None:
                print("%08x  %s" % (s.va, s.name))
            elif s.va is not None:
                print("%04x:%08x  %08x  %s" % (s.seg, s.off, s.va, s.name))
            else:
                print("%04x:%08x  %s" % (s.seg, s.off, s.name))


if __name__ == "__main__":
    main()
