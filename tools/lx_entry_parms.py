#!/usr/bin/env python3
"""
lx_entry_parms.py - dump per-ordinal parameter word counts from an LX DLL's
entry table.

Why this exists: 16-bit OS/2 entry points use callee stack cleanup (RETF N), so
anything dispatching to them needs N per ordinal. Community-derived tables
(e.g. osFree's) have a known error class here - a wrong N silently leaks or
over-pops the caller's 16-bit stack on every call, and the symptom appears far
from the cause. The byte-authoritative source for N is IBM's own binary: LX
16-bit entry-table entries carry a "parameter word count" in their flags byte
(bits 3-7) -- the same
field EXEHDR prints as "N parm wds", but present for EVERY entry, named or
not (DOSCALL1.DLL exports almost everything by ordinal only; its non-resident
name table is empty, so EXEHDR's Exports section names only 32 of them).

Source (documented): LX format spec, entry table bundle encoding --
  bundle: u8 count, u8 type[, u16 object if type != 0]
  type 0 = unused (count ordinals skipped, no object field)
  type 1 = 16-bit entry:      u8 flags, u16 offset            (3 bytes/entry)
  type 2 = 286 call gate:     u8 flags, u16 offset, u16 gate  (5 bytes/entry)
  type 3 = 32-bit entry:      u8 flags, u32 offset            (5 bytes/entry)
  type 4 = forwarder:         u8 flags, u16 modord, u32 val   (7 bytes/entry)
  flags: bit 0 = exported, bits 3-7 = parameter word count (types 1-3).
Cross-checkable against an EXEHDR dump of the same DLL: every named export's
"N parm wds" matches this field.

Usage:
  tools/lx_entry_parms.py /path/to/OS2/DLL/DOSCALL1.DLL [--from N] [--to N]
"""
import argparse
import struct
import sys

TYPE_NAMES = {0: "unused", 1: "entry16", 2: "gate286", 3: "entry32", 4: "forwarder"}
ENTRY_SIZES = {1: 3, 2: 5, 3: 5, 4: 7}


def parse(path):
    data = open(path, "rb").read()
    # The DOS stub is OPTIONAL. A bare LX carries its magic at offset 0 with no
    # MZ header at all -- netlabs ships several (the ncurses tinfo6.dll and the
    # gcc runtime gcc1.dll among them). Demanding MZ first rejects those as a
    # corrupt file rather than as the second valid layout they are.
    # See os2ref/executable-formats.md section 1.1.
    if data[:2] == b"LX":
        lx_off = 0
    elif data[:2] == b"MZ":
        lx_off = struct.unpack_from("<I", data, 0x3C)[0]
    else:
        sys.exit(f"{path}: not an LX image (no LX magic at 0, no MZ stub)")
    if data[lx_off:lx_off + 2] != b"LX":
        sys.exit(f"{path}: no LX header at 0x{lx_off:x} (got {data[lx_off:lx_off+2]!r})")
    # LX header: entry table offset (relative to LX header) at LX+0x5C
    ent_off = lx_off + struct.unpack_from("<I", data, lx_off + 0x5C)[0]

    entries = {}  # ordinal -> (type, flags, parm_words)
    ordinal = 1
    pos = ent_off
    while True:
        cnt = data[pos]
        pos += 1
        if cnt == 0:
            break  # end of entry table
        btype = data[pos] & 0x7F
        pos += 1
        if btype == 0:
            ordinal += cnt
            continue
        pos += 2  # object number
        if btype not in ENTRY_SIZES:
            sys.exit(f"unknown bundle type {btype} at file 0x{pos:x}")
        for _ in range(cnt):
            flags = data[pos]
            entries[ordinal] = (btype, flags, (flags >> 3) & 0x1F)
            pos += ENTRY_SIZES[btype]
            ordinal += 1
    return entries


def main():
    # argparse, not hand-rolled "--k=v" splitting: the old parser silently
    # dropped the spaced form ("--from 100" left --from == True -> int(True) == 1)
    # and printed every ordinal as though the filter had been applied.
    ap = argparse.ArgumentParser(
        description="Dump per-ordinal parameter word counts from an LX DLL's "
                    "entry table.")
    ap.add_argument("lximage")
    ap.add_argument("--from", dest="lo", type=int, default=1,
                    metavar="N", help="first ordinal to print (default 1)")
    ap.add_argument("--to", dest="hi", type=int, default=None,
                    metavar="N", help="last ordinal to print (default: highest)")
    args = ap.parse_args()

    try:
        entries = parse(args.lximage)
    except (OSError, ValueError) as e:
        sys.exit("%s: %s" % (args.lximage, e))
    if not entries:
        sys.exit("%s: entry table is empty (module exports nothing by ordinal)"
                 % args.lximage)
    lo = args.lo
    hi = args.hi if args.hi is not None else max(entries)
    for ordn in sorted(entries):
        if not (lo <= ordn <= hi):
            continue
        btype, flags, pw = entries[ordn]
        exported = "exp" if flags & 1 else "   "
        print(f"{ordn:5d}  {TYPE_NAMES[btype]:9s} {exported}  flags=0x{flags:02x}  "
              f"parm_wds={pw:2d}  arg_bytes={pw * 2:2d}")


if __name__ == "__main__":
    main()
