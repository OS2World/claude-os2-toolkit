#!/usr/bin/env python3
"""msgdump.py - print messages from an OS/2 MKMSGF .MSG file.

Usage: msgdump.py <file.MSG> [number ...]
Format (read from DOSCALL1's message code): 31-byte header, index table at
file offset 0x1f with numbermsg entries (u16 if offset16bit==1 else u32); a
message runs to the next entry, or to the country-info block / extended block
/ end of file for the last one.  Each message text starts with a one-char
class (E/W/I/P/H/?) that OS/2 strips before display.
"""
import signal, struct, sys


def load(path):
    d = open(path, "rb").read()
    if d[:8] != b"\xffMKMSGF\x00":
        raise ValueError("not an MKMSGF file")
    comp = d[8:11].decode("ascii", "replace")
    n, first = struct.unpack_from("<HH", d, 0x0b)
    o16 = d[0x0f] == 1
    cinfo = struct.unpack_from("<H", d, 0x14)[0]
    ext = struct.unpack_from("<I", d, 0x16)[0]
    w = 2 if o16 else 4
    offs = [struct.unpack_from("<H" if o16 else "<I", d, 0x1f + w * i)[0] for i in range(n)]
    tail = min(x for x in (cinfo, ext, len(d)) if x and x > offs[-1])
    msgs = {}
    for i, o in enumerate(offs):
        e = offs[i + 1] if i + 1 < n else tail
        msgs[first + i] = d[o:e]
    return comp, msgs


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0 if len(sys.argv) >= 2 else 2)
    try:
        comp, msgs = load(sys.argv[1])
    except (OSError, ValueError) as e:
        sys.exit("msgdump.py: %s: %s" % (sys.argv[1], e))
    want = [int(a, 0) for a in sys.argv[2:]] or sorted(msgs)
    for k in want:
        t = msgs.get(k)
        if t is None:
            print("%s%04d: <absent>" % (comp, k))
            continue
        print("%s%04d [%s] %s" % (comp, k, chr(t[0]),
                                  t[1:].decode("cp437").rstrip("\r\n").replace("\r\n", "\n    ")))


if __name__ == "__main__":
    # Exit quietly when a reader closes the pipe (`| head`).
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    main()
