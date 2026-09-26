#!/usr/bin/env python3
"""
lx_entry_table.py - resolve an LX module's own export ordinals to flat
addresses, and to names where the name tables give one.

Why: an import fixup in some other module resolves to "MODULE.#ordinal", which
stays opaque until you read the exporting module's Entry Table.  Most
high-numbered internal ordinals are exported by ordinal only (no name), so the
ordinal is the only handle there is - and that is exactly the case where you
need the flat address to look the routine up in a decompiled corpus.

Entry Table format [DOC-IBM], from the LX executable-format specification: a
sequence of bundles, each "count(u8) type(u8) [object(u16) if type != 0]"
followed by `count` entries of a type-dependent size:

    type 0 (EMPTY)     - no entries follow; `count` ordinals are simply unused
    type 1 (16BIT)     - each entry: flags(u8) offset(u16)   [object in header]
    type 3 (32BIT)     - each entry: flags(u8) offset(u32)   [object in header]
    type 0x80|1, 0x80|3 - the "parameter typing present" variants seen in some
                          builds; the flags+offset shape is unaffected, so they
                          are decoded as 1 and 3
    type 2 (CALLGATE)  - flags(u8) offset(u16) callgate_selector(u16).  Legacy
                          16->32 ring-transition entries; the selector is not
                          needed here, the offset is recorded as for type 1.
    type 4 (FORWARDER) - flags(u8) module_ordinal(u16) offset_or_ordinal(u32),
                          and the bundle header field is RESERVED, not an
                          object number.  The target is in ANOTHER module, so
                          there is no local flat address: the address is
                          reported as None, and callers must check for that
                          rather than assume every ordinal has one.
Any other type raises rather than silently miscounting the byte stream.
The table ends at a bundle with count == 0.

Two decoding traps, kept as comments because both are easy to repeat:

  - The bundle header's OBJECT field is a u16, not a u8.  Reading it as one
    byte desyncs every subsequent entry in the bundle by one; the tell is a
    suspicious "all offsets share the same low byte" pattern in the output.
  - The header table offsets below were hand-counted from the LX header
    layout and then cross-checked against an independently validated anchor
    (the fixup page table at 0x68).  restab/enttab/nrestab are easy to confuse
    with dircnt/fpagetab/preload, and a wrong one yields confident garbage.

Name table format (resident and non-resident alike): a sequence of
{len(u8), name[len], ordinal(u16)}, terminated by len == 0.

Usage:
    lx_entry_table.py <lximage> [ordinal ...]
With no ordinals, dumps the whole ordinal -> (address, name) table.
"""
import argparse
import struct
import sys


def load(path):
    with open(path, "rb") as f:
        data = f.read()
    # The DOS stub is OPTIONAL. A bare LX carries its magic at offset 0 with no MZ
    # header at all -- netlabs ships several (the ncurses tinfo6.dll and the gcc
    # runtime gcc1.dll among them). Demanding MZ first rejects those as a corrupt
    # file rather than as the second valid layout they are.
    # See os2ref/executable-formats.md section 1.1.
    # (Duplicated rather than imported: this module runs headless under Ghidra,
    # where the rest of tools/ is not on sys.path.)
    if data[:2] == b"LX":
        e_lfanew = 0
    elif len(data) >= 0x40 and data[:2] in (b"MZ", b"ZM"):
        e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
    else:
        raise ValueError("not an LX image (no LX magic at 0, no MZ stub)")
    h = e_lfanew
    if data[h:h + 2] != b"LX":
        raise ValueError("not an LX image (no LX signature at e_lfanew)")

    def u32(off):
        return struct.unpack_from("<I", data, h + off)[0]

    objtab = u32(0x40)
    objcnt = u32(0x44)
    restab = u32(0x58)
    enttab = u32(0x5C)
    nrestab = u32(0x88)   # absolute file offset, unlike the others

    # object table: 24 bytes/entry (vsize, base, flags, pagemap idx, cnt, resv)
    obj_base = {}
    for i in range(objcnt):
        off = h + objtab + i * 24
        size, base = struct.unpack_from("<II", data, off)
        obj_base[i + 1] = base

    return data, h, enttab, restab, nrestab, obj_base


def parse_names(data, off):
    names = {}
    p = off
    while p < len(data):
        ln = data[p]
        if ln == 0:
            break
        name = data[p + 1:p + 1 + ln].decode("latin1")
        ordv = struct.unpack_from("<H", data, p + 1 + ln)[0]
        names[ordv] = name
        p += 1 + ln + 2
    return names


def parse_entries(data, off, obj_base):
    entries = {}          # ordinal -> (objnum, flat_addr or None, flags)
    p = off
    ordinal = 1
    while True:
        count = data[p]
        if count == 0:
            break
        etype = data[p + 1]
        p += 2
        real_type = etype & 0x7F
        if real_type == 0:
            ordinal += count
            continue
        objnum = struct.unpack_from("<H", data, p)[0]
        p += 2
        for _ in range(count):
            flags = data[p]
            if real_type == 1:
                offset = struct.unpack_from("<H", data, p + 1)[0]
                p += 3
            elif real_type == 3:
                offset = struct.unpack_from("<I", data, p + 1)[0]
                p += 5
            elif real_type == 2:
                offset = struct.unpack_from("<H", data, p + 1)[0]
                p += 5
            elif real_type == 4:
                p += 7
                entries[ordinal] = (objnum, None, flags)
                ordinal += 1
                continue
            else:
                raise NotImplementedError(
                    "entry type 0x%02x not implemented (ordinal %d)"
                    % (etype, ordinal))
            base = obj_base.get(objnum)
            addr = (base + offset) if base is not None else None
            entries[ordinal] = (objnum, addr, flags)
            ordinal += 1
    return entries


def main():
    ap = argparse.ArgumentParser(
        description="Resolve an LX module's export ordinals to flat addresses "
                    "and names.")
    ap.add_argument("lximage", help="the LX module to read")
    ap.add_argument("ordinal", nargs="*", type=int,
                    help="ordinals to resolve (default: dump the whole table)")
    args = ap.parse_args()

    try:
        data, h, enttab, restab, nrestab, obj_base = load(args.lximage)
    except (OSError, ValueError, struct.error) as e:
        sys.exit("%s: %s" % (args.lximage, e))

    entries = parse_entries(data, h + enttab, obj_base)
    names = {}
    names.update(parse_names(data, h + restab))
    names.update(parse_names(data, nrestab))

    for o in (args.ordinal or sorted(entries)):
        e = entries.get(o)
        if e is None:
            print("#%d  NOT IN ENTRY TABLE" % o)
            continue
        objnum, addr, flags = e
        addrs = ("obj%d+? (forwarder)" % objnum) if addr is None else ("0x%08x" % addr)
        print("#%-5d %-22s %s" % (o, addrs, names.get(o, "")))


if __name__ == "__main__":
    main()
