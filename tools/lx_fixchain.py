#!/usr/bin/env python3
"""lx_fixchain.py - apply LX *chained* internal fixups, which sym2map.py's
LXImage does not.

WHY THIS EXISTS. A fixup record whose target flags carry 0x08 is the head of a
per-page chain. Each 4-byte slot in the chain holds
    (next_page_offset << 20) | target_offset_20bit
and only the head has a fixup record. The kernel's loader (_ldrApply32Fixups,
read in the Warp 4.5 SMP debug kernel) does:
    v = *head; delta = resolved - (v & 0xFFFFF); nxt = v >> 20
    *head = resolved
    up to 1024 times, while nxt <= 0xFFA:
        v = *(page + nxt); *(page + nxt) = (v & 0xFFFFF) + delta; nxt = v >> 20
and only for a 4-byte source type with source offset < 0xFFC.

sym2map.py fills a fixup slot only when it is zero, and a chain head is never
zero, so in a chained module NO chained reference is relocated: every global
decompiles as  (garbage_high_12_bits << 20) | low_20_bits . Measured on
CHKDSK32.DLL: absolute operands landing inside an object went from 14 of 1198
to 1740 of 1740 once chains were applied. About 230 modules of an installed
Warp 4.5 system carry chain records; the kernel, DOSCALL1 and the PM DLLs carry
none.

As a library:  apply_chains(lx_path, images)  where images maps object number
-> bytearray (object-relative, as LXImage.object_bytes returns), patched in
place; returns (records, slots, notes).
               chain_slots(lx_path, images)  yields every chained slot without
patching: (objnum, object_offset, target_objnum, target_offset).
As a CLI:      lx_fixchain.py <lx> [...]   reports chain records per module.
"""
import struct, sys


def _u16(d, o):
    return struct.unpack_from("<H", d, o)[0]


def _u32(d, o):
    return struct.unpack_from("<I", d, o)[0]


class _Hdr:
    def __init__(self, path):
        d = self.data = open(path, "rb").read()
        if d[:2] == b"MZ":
            h = _u32(d, 0x3C)
        elif d[:2] == b"LX":
            h = 0
        else:
            raise ValueError("not an LX image")
        if d[h:h + 2] != b"LX":
            raise ValueError("LX signature not found")
        self.h = h
        self.mpages = _u32(d, h + 0x14)
        self.pagesize = _u32(d, h + 0x28)
        objtab, objcnt = _u32(d, h + 0x40), _u32(d, h + 0x44)
        self.fpage = h + _u32(d, h + 0x68) if _u32(d, h + 0x68) else 0
        self.frec = h + _u32(d, h + 0x6C) if _u32(d, h + 0x6C) else 0
        self.objs = []
        for i in range(objcnt):
            vsize, base, flags, mapidx, mapsize, _ = struct.unpack_from(
                "<6I", d, h + objtab + 24 * i)
            self.objs.append(dict(num=i + 1, vsize=vsize, base=base,
                                  mapidx=mapidx, mapsize=mapsize))

    def records(self):
        """Yield (objnum, page_off_in_obj, stype, tflags, ttype, target_or_None,
        [source offsets]) for every fixup record.  Raises on a framing desync."""
        d = self.data
        if not (self.fpage and self.frec):
            return
        for o in self.objs:
            for i in range(o["mapsize"]):
                g = o["mapidx"] - 1 + i
                if g + 1 > self.mpages:
                    break
                p = self.frec + _u32(d, self.fpage + 4 * g)
                pend = self.frec + _u32(d, self.fpage + 4 * (g + 1))
                while p < pend:
                    src, fl = d[p], d[p + 1]
                    p += 2
                    stype, ttype, srclist = src & 0x0F, fl & 3, bool(src & 0x20)
                    if srclist:
                        cnt = d[p]; p += 1
                    else:
                        single = struct.unpack_from("<h", d, p)[0]; p += 2
                    target = None
                    if ttype == 0:
                        if fl & 0x40:
                            on = _u16(d, p); p += 2
                        else:
                            on = d[p]; p += 1
                        if stype == 2:
                            toff = 0
                        elif fl & 0x10:
                            toff = _u32(d, p); p += 4
                        else:
                            toff = _u16(d, p); p += 2
                        target = (on, toff)
                    elif ttype in (1, 2):
                        p += 2 if fl & 0x40 else 1
                        if ttype == 1:
                            p += 1 if fl & 0x80 else (4 if fl & 0x10 else 2)
                        else:
                            p += 4 if fl & 0x10 else 2
                    else:
                        p += 2 if fl & 0x40 else 1
                    add = 0
                    if fl & 0x04:
                        if fl & 0x20:
                            add = _u32(d, p); p += 4
                        else:
                            add = _u16(d, p); p += 2
                    if srclist:
                        offs = [struct.unpack_from("<h", d, p + 2 * k)[0] for k in range(cnt)]
                        p += 2 * cnt
                    else:
                        offs = [single]
                    if target is not None:
                        target = (target[0], (target[1] + add) & 0xFFFFFFFF)
                    yield (o["num"], i * self.pagesize, stype, fl, ttype, target, offs)
                if p != pend:
                    raise ValueError("fixup framing desync on page %d" % (g + 1))


# 4-byte source types: 7 = 32-bit offset, 8 = 32-bit self-relative, 3 = 16:16 pointer
_DWORD_STYPES = (3, 7, 8)


def _walk(path, images, patch):
    """Walk every chain. Yields ('slot', objnum, obj_off, target_obj, target_off)
    for each slot and ('note', text) for anything not applied. With patch=True
    the images are relocated in place as the loader would."""
    hdr = _Hdr(path)
    bases = {o["num"]: o["base"] for o in hdr.objs}
    for objnum, poff, stype, fl, ttype, target, offs in hdr.records():
        if not (fl & 0x08) or stype not in _DWORD_STYPES:
            continue
        yield ("record",)
        if ttype != 0 or stype != 7:
            yield ("note", "chain record not applied: obj%d page+0x%x stype %d ttype %d"
                   % (objnum, poff, stype, ttype))
            continue
        img = images.get(objnum)
        if img is None:
            continue
        resolved = (bases[target[0]] + target[1]) & 0xFFFFFFFF
        for so in offs:
            if so < 0 or so >= 0xFFC or poff + so + 4 > len(img):
                yield ("note", "chain head out of range: obj%d page+0x%x off %d" % (objnum, poff, so))
                continue
            v = _u32(img, poff + so)
            delta = (resolved - (v & 0xFFFFF)) & 0xFFFFFFFF
            nxt = v >> 20
            if patch:
                struct.pack_into("<I", img, poff + so, resolved)
            yield ("slot", objnum, poff + so, target[0], target[1], True)
            for _ in range(1024):
                if nxt > 0xFFA or poff + nxt + 4 > len(img):
                    break
                v = _u32(img, poff + nxt)
                tgt = ((v & 0xFFFFF) + delta) & 0xFFFFFFFF
                if patch:
                    struct.pack_into("<I", img, poff + nxt, tgt)
                # the slot's own target, as an object-relative offset in the head's target object
                yield ("slot", objnum, poff + nxt, target[0], (tgt - bases[target[0]]) & 0xFFFFFFFF, False)
                nxt = v >> 20


def apply_chains(path, images):
    """Relocate every chained slot in place. Returns (records, slots, notes)."""
    nrec = nslot = 0
    notes = []
    for ev in _walk(path, images, True):
        if ev[0] == "record":
            nrec += 1
        elif ev[0] == "slot":
            nslot += 1
        else:
            notes.append(ev[1])
    return nrec, nslot, notes


def chain_slots(path, images, heads=True):
    """Yield (objnum, obj_off, target_obj, target_off) for every chained slot,
    reading the unpatched images; nothing is modified. heads=False leaves out
    each chain's head, which has a fixup record of its own."""
    for ev in _walk(path, images, False):
        if ev[0] == "slot" and (heads or not ev[5]):
            yield ev[1:5]


def main():
    for path in sys.argv[1:]:
        try:
            hdr = _Hdr(path)
            n = sum(1 for r in hdr.records() if r[3] & 0x08)
        except Exception as e:
            print("%s: ERROR %s" % (path, e))
            continue
        print("%-60s chain records: %d" % (path, n))


if __name__ == "__main__":
    main()
