#!/usr/bin/env python3
"""
lx_retf_argbytes.py - recover per-ordinal arg_bytes from a real LX DLL by
reading each 16-bit entry point's own `retf N`.

WHY THIS EXISTS. Anything that calls a 16-bit OS/2 export has to clean the
argument block off the stack the way the callee expects, so arg_bytes has to be
right. Two other sources look authoritative and are not:

  - the LX entry table's parameter word count (lx_entry_parms.py) is
    byte-authoritative but DOSCALL1.DLL fills it in for only **8 of its 552
    entries**, so it cannot answer for the rest;
  - decompiler output invents argument lists. Reading one is how ordinal 717
    came to be recorded as taking 1 word when it takes 2.

`retf N` is the callee's OWN cleanup count, present in every 16-bit export,
and it is what the caller's stack discipline actually depends on. Measured on a
real DOSCALL1.DLL: ordinal 717 DosSMSetSessionType is `retf 0x4`, where a
hand-maintained table had 2.

METHOD. Walk the LX entry table for ordinal -> (object, offset), then scan
forward from the entry point for the first RETF. Reported confidence:

  ok      a single unambiguous RETF was reached
  branch  more than one distinct RETF operand was seen (report, don't trust)
  none    no RETF within the scan window (entry is a jump/gate, or data)

Only 16-bit entries (bundle types 1 and 2) are meaningful; 32-bit entries
(type 3) use caller cleanup and are skipped.

RELIABILITY, MEASURED - READ THIS BEFORE ACTING ON OUTPUT. Cross-checked
against the 8 ordinals whose parameter count DOSCALL1's entry table publishes
independently: **7 of 8 agree; ord 148 (DosSubFree) does not** - the byte scan
hits a 0xCB inside an earlier instruction and reports 0 where IBM says 6. So
this tool GENERATES LEADS, it is not authority. Verify every hit with
lx_disasm.py before changing a row (that is how 692/705/706/717 were
confirmed at r4494). The 7 hand-verified session-manager ordinals
(684/687/692/705/706/707/717) all reproduce exactly.

Usage:
  lx_retf_argbytes.py DLL [--ord N] [--window N]
"""
import struct, sys, os, re

SZ = {1: 3, 2: 5, 3: 5, 4: 7}

def entry_table(data):
    lx = struct.unpack_from("<I", data, 0x3C)[0]
    if data[lx:lx+2] != b"LX":
        sys.exit("not an LX image")
    pos = lx + struct.unpack_from("<I", data, lx + 0x5C)[0]
    out, ordn = {}, 1
    while True:
        cnt = data[pos]; pos += 1
        if cnt == 0:
            break
        bt = data[pos] & 0x7F; pos += 1
        if bt == 0:
            ordn += cnt; continue
        obj = struct.unpack_from("<H", data, pos)[0]; pos += 2
        for _ in range(cnt):
            if bt in (1, 2):
                off = struct.unpack_from("<H", data, pos + 1)[0]
            elif bt == 3:
                off = struct.unpack_from("<I", data, pos + 1)[0]
            else:
                off = None
            out[ordn] = (bt, obj, off)
            pos += SZ[bt]; ordn += 1
    return out

def object_bytes(path, obj_num):
    """Decompressed image of one LX object, via the project's own loader logic
    in sym2map.py (LXImage) rather than re-deriving page handling."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from sym2map import LXImage
    img = LXImage(path)
    return img.object_bytes(obj_num)

def first_retf(buf, start, window):
    """First RETF at or after `start`: CA iw = RETF imm16, CB = RETF (0).

    Every exit of a Pascal-convention function must pop the same amount - that
    IS the ABI - so the first RETF is the function's cleanup count and there is
    no need to scan to the end (doing so just walks into the next function and
    reports spurious disagreement).

    HONEST LIMITATION: this is a linear BYTE scan, not a disassembly, so a 0xCA
    or 0xCB byte occurring inside an earlier instruction's operand would be
    misread as a RETF. That is why --selftest exists: it re-derives the 8
    ordinals whose parameter count DOSCALL1's entry table publishes
    independently, plus the 7 verified by hand against lx_disasm.py, and any
    disagreement means do not trust the rest."""
    i = start
    end = min(len(buf), start + window)
    while i < end:
        b = buf[i]
        if b == 0xCA and i + 2 < end:
            return struct.unpack_from("<H", buf, i + 1)[0], 'ok'
        if b == 0xCB:
            return 0, 'ok'
        i += 1
    return None, 'none' 

def main():
    # `--ord 717` and `--ord=717` both work. The earlier parser took only the
    # `=` form and set the flag to True otherwise, so `--ord 717` filtered for
    # ordinal int(True) == 1, matched nothing, and exited 0 printing nothing --
    # and `--window 64` silently became a 1-byte window, so every row came back
    # `retf=? none` while still reporting success. An unknown flag now stops.
    TAKES_VALUE = {'--ord', '--window'}
    args, opts, argv = [], {}, sys.argv[1:]
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ('-h', '--help'):
            print(__doc__)
            sys.exit(0)
        if a.startswith('--'):
            name, eq, val = a.partition('=')
            if name not in TAKES_VALUE:
                sys.exit("lx_retf_argbytes.py: unknown option %s\n%s" % (name, __doc__))
            if not eq:
                if i + 1 >= len(argv):
                    sys.exit("lx_retf_argbytes.py: %s needs a value" % name)
                val = argv[i + 1]
                i += 1
            opts[name] = val
        else:
            args.append(a)
        i += 1
    if not args:
        sys.exit(__doc__)
    path = args[0]
    window = int(opts.get('--window', 512))
    data = open(path, 'rb').read()
    ents = entry_table(data)

    want = int(opts['--ord']) if '--ord' in opts else None
    table = {}
    cache = {}
    rows = []
    for ordn in sorted(ents):
        bt, obj, off = ents[ordn]
        if bt not in (1, 2) or off is None:
            continue
        if want is not None and ordn != want:
            continue
        if obj not in cache:
            try:
                cache[obj] = object_bytes(path, obj)
            except Exception as e:
                cache[obj] = None
        buf = cache[obj]
        if not buf or off >= len(buf):
            continue
        n, conf = first_retf(buf, off, window)
        rows.append((ordn, obj, off, n, conf))

    if True:
        for ordn, obj, off, n, conf in rows:
            print(f"{ordn:5d}  obj{obj}+0x{off:04x}  retf={'?' if n is None else n:>4}  {conf}")
        return

    bad = same = skipped = 0
    print(f"{'ord':>5} {'name':26} {'table':>5} {'retf':>5}  note")
    for ordn, obj, off, n, conf in rows:
        if ordn not in table:
            continue
        name, typ, argb = table[ordn]
        if typ != 'ENTRY_16BIT' or conf != 'ok':
            skipped += 1
            continue
        if argb == n:
            same += 1
            continue
        bad += 1
        print(f"{ordn:5d} {name:26} {argb:5d} {n:5d}  obj{obj}+0x{off:04x}")
    print(f"\nagree: {same}   DISAGREE: {bad}   not-comparable: {skipped}")

if __name__ == '__main__':
    main()
