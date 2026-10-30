#!/usr/bin/env python3
"""ftcomp.py - reference decoder for IBM's FTCOMP codec (the PACK2 format,
UNPACK2.EXE).  See FTCOMP_FORMAT.md beside this script for the format specification this
code implements; every routine names the UNPACK2.EXE 14.x routine (unpack2.sym)
it ports.

Layers, outermost first:
  ftcomp block  = "fT19" + Huffman payload        (_ftcomp_exec,  0001:a714)
  Huffman layer = weights + two dynamic trees      (HUFFMANDECODE, 0001:91aa)
  LZ records    = u16 len + chunk                  (_ftcomp_exec loop)
  LZ chunk      = flag byte + 0x9E-escaped LZ77    (EXPLODE 0001:a622, DECODE 0001:75fe)

SORT and BUILDTREE are ported literally, index for index: the dynamic trees are
rebuilt from transmitted *weights*, so the decoder must reproduce IBM's exact
tie-breaking among equal weights or it decodes garbage.  Everything else is
written plainly; its behaviour, not its instruction sequence, is what matters.

The constant tables (two seed-weight tables, EATTABLE, ISREPCODE, INIDATA, the
signature) live in UNPACK2.EXE's DGROUP; load_tables() extracts them.
"""
import struct

# ---------------------------------------------------------------------------
# constants

NSYM = 433                  # alphabet size of every tree (0x1b1)
LEAF_LIMIT = NSYM * 4       # node ids are multiples of 4; ids >= 0x6c4 are internal
SIG = b"fT19"

WIN_SIZE = 0x10000 - 0x1C   # SOURCEBUFFER segment, 0xffe4 bytes
HIST = 0xCFDC               # history kept between chunks (53 212 bytes)
CHUNK_MAX = 0x3008          # largest LZ chunk / chunk output
HUGEIN_SIZE = 0xFE00

# DGROUP offsets in UNPACK2.EXE (unpack2.sym)
_DG = {
    "INIDATA": (0x062C, 0xFBA),
    "EATTABLE": (0x15E6, 0x100),
    "ISREPCODE": (0x16E6, 0x1B2),
    "XCODES2": (0x1898, 2 * NSYM),
    "XCODES3": (0x1C98, 2 * NSYM),
    "SIGNATURE": (0x2098, 4),
}


def ne_segment(exe, segnum):
    """Initial bytes of NE segment `segnum` (1-based) of an EXE."""
    ne = struct.unpack_from("<I", exe, 0x3C)[0]
    assert exe[ne:ne + 2] == b"NE", "not an NE executable"
    segtab = ne + struct.unpack_from("<H", exe, ne + 0x22)[0]
    shift = struct.unpack_from("<H", exe, ne + 0x32)[0]
    sector, length, flags, minalloc = struct.unpack_from("<HHHH", exe, segtab + 8 * (segnum - 1))
    off = sector << shift
    raw = exe[off:off + (length or 0x10000)]
    if not flags & 0x0008:
        return raw
    out, p = bytearray(), 0          # NSITER: {u16 count, u16 len, bytes} records
    while p + 4 <= len(raw):
        count, ln = struct.unpack_from("<HH", raw, p)
        out += raw[p + 4:p + 4 + ln] * count
        p += 4 + ln
    return bytes(out)


def load_tables(unpack2_exe_path):
    """Extract the codec's constant tables from UNPACK2.EXE's DGROUP (segment 4)."""
    exe = open(unpack2_exe_path, "rb").read()
    dg = ne_segment(exe, 4)
    t = {k: bytes(dg[o:o + n]) for k, (o, n) in _DG.items()}
    if t["SIGNATURE"] != SIG:
        raise ValueError("unexpected FTCOMP signature %r" % t["SIGNATURE"])
    return t


# ---------------------------------------------------------------------------
# SORT (0001:8a7c) and BUILDTREE (0001:8cbe), literal ports.
#
# Memory model: a node id x (a multiple of 4) owns four words in DGROUP,
# W at 0x6002+2x, P at +2, L at +4, R at +6.  Here they are four lists indexed
# by x//4.  A is the word array at 0x7b32, holding node ids.

class Tree:
    """A built tree plus its 9-bit fast-lookup table (the FILENCODE==2 path)."""
    __slots__ = ("W", "P", "L", "R", "root", "fast_node", "fast_bits")


def _sort(A, W, lo, hi):
    """SORT: sort A[lo..hi] ascending by W[A[i]//4].  An explicit stack lives in
    A itself just past hi, as in the original; quicksort on ranges longer than
    17, insertion sort below that."""
    A[hi + 1] = lo
    A[hi + 2] = hi
    base = hi + 1
    sp = hi + 3
    while True:
        sp -= 2
        lo, hi = A[sp], A[sp + 1]
        while True:
            if hi - lo > 0x10:
                i, j = lo, hi
                pivot = W[A[(lo + hi) >> 1] // 4]
                while True:
                    while W[A[i] // 4] < pivot:
                        i += 1
                    while W[A[j] // 4] > pivot:
                        j -= 1
                    if j >= i:
                        A[i], A[j] = A[j], A[i]
                        i += 1
                        j -= 1
                    if j < i:
                        break
                if hi - i > j - lo:
                    if hi > i:
                        A[sp], A[sp + 1] = i, hi
                        sp += 2
                    hi = j
                else:
                    if lo < j:
                        A[sp], A[sp + 1] = lo, j
                        sp += 2
                    lo = i
                if hi <= lo:
                    break
            else:
                k = lo + 1
                while k <= hi:
                    v = A[k]
                    wv = W[v // 4]
                    pos = lo
                    if W[A[lo] // 4] < wv:
                        while pos < k:
                            pos += 1
                            if not (W[A[pos] // 4] < wv):
                                break
                    A[pos + 1:k + 1] = A[pos:k]
                    A[pos] = v
                    k += 1
                break
        if sp == base:
            return


def build_tree(weights):
    """BUILDTREE: Huffman tree over NSYM leaves with the given 16-bit weights,
    plus the decode fast table.  Returns a Tree."""
    n_nodes = 2 * NSYM
    W = [0] * n_nodes
    P = [0] * n_nodes
    L = [0] * n_nodes
    R = [0] * n_nodes
    W[:NSYM] = [w & 0xFFFF for w in weights]
    A = [0] * 1024           # 0x7b32: 512 words, then SORT's stack may run on

    n = 0                    # si
    m = 0                    # [bp-8]: weight-1 leaves gathered at the front
    last_zero = 0            # [bp-0x14]
    for i in range(NSYM):
        x = 4 * i
        P[i] = 0
        w = W[i]
        if w == 0:
            last_zero = x
        elif w == 1:
            A[n] = A[m]
            n += 1
            A[m] = x
            m += 1
        else:
            A[n] = x
            n += 1
    if n == 0:
        raise ValueError("BUILDTREE on an empty alphabet")
    lo = m
    if n == 1:
        A[n] = A[m]
        n += 1
        A[m] = last_zero
        lo = m + 1
        W[last_zero // 4] = 1
    _sort(A, W, lo, n - 1)

    nxt = LEAF_LIMIT         # [bp-0xa]
    f = 0                    # [bp-0x10]
    if n != 2:
        c = n
        while True:
            c -= 1
            a, b = A[f], A[f + 1]
            lo_ = f + 2
            f += 1
            w = (W[b // 4] + W[a // 4]) & 0xFFFF    # 16-bit add: sums wrap
            mid = (n + lo_) >> 1
            if n > lo_:
                hi_ = n
                bx = mid
                while True:
                    if W[A[bx] // 4] < w:
                        lo_ = bx + 1
                    else:
                        hi_ = bx
                    bx = (hi_ + lo_) >> 1
                    if not (hi_ > lo_):
                        break
                mid = bx
            A[f:mid - 1] = A[f + 1:mid]
            A[mid - 1] = nxt
            k = nxt // 4
            W[k] = w & 0xFFFF
            P[k] = 0
            L[k] = a
            R[k] = b
            P[a // 4] = nxt
            P[b // 4] = nxt
            nxt += 4
            if c == 2:
                break
    a, b = A[f], A[f + 1]
    k = nxt // 4
    W[k] = (W[b // 4] + W[a // 4]) & 0xFFFF
    P[k] = 0
    L[k] = a
    R[k] = b
    P[a // 4] = nxt
    P[b // 4] = nxt

    t = Tree()
    t.W, t.P, t.L, t.R, t.root = W, P, L, R, nxt
    # fast table: for each 9-bit prefix walk from the root, at most 9 steps.
    # NB the original's branch sense: a 1 bit takes L, a 0 bit takes R.
    t.fast_node = [0] * 512
    t.fast_bits = [0] * 512
    for i in range(512):
        code = i << 7
        x = t.root
        nb = 0
        while True:
            k = x // 4
            x = L[k] if code & 0x8000 else R[k]
            code = (code << 1) & 0xFFFF
            nb += 1
            if not (x >= LEAF_LIMIT and nb < 9):
                break
        t.fast_node[i] = x
        t.fast_bits[i] = nb
    return t


# ---------------------------------------------------------------------------
# HUFFMANDECODE (0001:91aa)

class BitReader:
    """The routine's 16-bit MSB-first bit buffer ([bp-0xe]) and fill count
    ([bp-8]); `pos` is CIN, counted from the start of the Huffman payload."""
    __slots__ = ("d", "pos", "buf", "bits")

    def __init__(self, d, pos):
        self.d, self.pos, self.buf, self.bits = d, pos, 0, 0

    def _byte(self):
        b = self.d[self.pos] if self.pos < len(self.d) else 0
        self.pos += 1
        return b

    def refill(self):
        while self.bits <= 8:
            self.buf |= self._byte() << (8 - self.bits)
            self.bits += 8

    def take(self, n):
        self.buf = (self.buf << n) & 0xFFFF
        self.bits -= n

    def walk_bit(self):
        """One step of a tree walk past the fast table: returns the top bit."""
        if self.bits == 0:
            self.buf = self._byte() << 8
            self.bits = 7
        else:
            self.bits -= 1
        bit = self.buf & 0x8000
        self.buf = (self.buf << 1) & 0xFFFF
        return bit

    def symbol(self, t):
        """Decode one symbol with tree t (fast table, then bitwise walk)."""
        self.refill()
        idx = self.buf >> 7
        x = t.fast_node[idx]
        self.take(t.fast_bits[idx])
        while x >= LEAF_LIMIT:
            k = x // 4
            x = t.L[k] if self.walk_bit() else t.R[k]
        return x >> 2


def _weights_for(vals, isrep, mult_rep, mult_other):
    """BUILDTREES' weight derivation: v * multiplier, then rescaled into 1..255
    when the largest exceeds 255."""
    w = [0] * NSYM
    mx = 0
    for i, v in enumerate(vals):
        if v:
            w[i] = (v * (mult_rep if isrep[i] else mult_other)) & 0xFFFF
            mx = max(mx, w[i])
    if mx > 0xFF:
        s = 0xFFFF // mx
        for i in range(NSYM):
            o = w[i]
            w[i] = ((o * s) & 0xFFFF) >> 8
            if o and not w[i]:
                w[i] = 1
    return w


class FtcompDecoder:
    """Decoder state for one PACK2 archive member.  Call reset() at the start
    of every file (that is _ftcomp_clearbuffs), then block() per block."""

    def __init__(self, tables):
        self.t = tables
        self.eat = tables["EATTABLE"]
        self.isrep = tables["ISREPCODE"]
        self.tree2 = build_tree(struct.unpack("<%dH" % NSYM, tables["XCODES2"]))
        self.tree3 = build_tree(struct.unpack("<%dH" % NSYM, tables["XCODES3"]))
        self.win = bytearray(WIN_SIZE)
        self.reset()

    def reset(self):
        """_ftcomp_clearbuffs, decode mode with FASTMODE=0.  Note what it does
        NOT clear: window bytes below 0xbc62 keep whatever the previous member
        left there."""
        w = self.win
        w[0xBC62:0xBC62 + 0x140] = b"\x20" * 0x140
        w[0xBDA2:0xBDA2 + 0x140] = b"\xff" * 0x140
        w[0xBEE2:0xBEE2 + 0x140] = b"\x00" * 0x140
        w[0xC022:0xC022 + 0xFBA] = self.t["INIDATA"]
        self.raw_mode = False     # SAVENCODE dropped to 0: rest of member is stored

    # ---- one _ftcomp_exec call ------------------------------------------
    def block(self, data):
        """Decode one block from the front of `data`.  Returns (output, used)."""
        if self.raw_mode or len(data) < 4 or data[:4] != SIG:
            self.raw_mode = True
            return bytes(data), len(data)
        payload = data[4:]
        recs, used = self._huffman(payload)
        out = bytearray()
        si = 0
        n = len(recs)
        while n:
            ln = recs[si] | (recs[si + 1] << 8)
            si += 2
            n -= 2
            if ln > CHUNK_MAX or HUGEIN_SIZE - si < ln:
                raise ValueError("bad LZ record length %d" % ln)
            out += self._explode(recs[si:si + ln])
            si += ln
            n -= ln
        return bytes(out), used + 4

    # ---- HUFFMANDECODE ------------------------------------------------------
    def _huffman(self, p):
        total = p[0] | (p[1] << 8)
        if total == 0xFFFF:                       # stored Huffman payload
            ln = p[2] | (p[3] << 8)
            return bytes(p[4:4 + ln]), ln + 4
        caa, cax, cxx, cxa = p[2], p[3], p[4], p[5]
        br = BitReader(p, 6)
        vals = [0] * NSYM
        si = 0
        while si < NSYM:
            s = br.symbol(self.tree2)
            if s == 0x100:                        # run of up to 16 zero weights
                si += min(16, NSYM - si)
            else:
                vals[si] = s & 0xFF
                si += 1
        isrep = self.isrep
        treeA = build_tree(_weights_for(vals, isrep, cax, caa))
        if (cxx == cax and cxa == caa) or (cxx == 0 and cxa == 0):
            treeB = treeA
        else:
            treeB = build_tree(_weights_for(vals, isrep, cxx, cxa))

        tree3 = self.tree3
        eat = self.eat
        out = bytearray()
        reps = [0] * 0x30          # LASTREPS: positions of LZ code bytes
        dups = [0] * 0x30          # LASTDUPS: recent 2-byte values
        rcur = dcur = 0x20
        last1 = last_c0 = last_c1 = last_c2 = last_hi = 0
        mode = 0                   # [bp-0xb]: operand bytes still owed
        useB = 0                   # [bp-3]:   ISREPCODE of the previous symbol
        cls = low = 0
        while len(out) < total:
            if mode == 0:
                s = br.symbol(treeB if useB else treeA)
                useB = isrep[s]
                if s <= 0xFF:
                    out.append(s)
                elif s < 0x181:                   # new LZ token: 9E <code>
                    code = s - 0x100
                    out += bytes((0x9E, code))
                    mode = eat[code]
                    if mode:
                        if rcur == 0:
                            reps[32:48] = reps[0:16]
                            rcur = 0x1F
                        else:
                            rcur -= 1
                        reps[rcur] = len(out) - 1
                elif s < 0x191:                   # repeat a 2-byte pair 2..17 back
                    o = len(out) - (s - 0x17F)
                    pair = out[o] | (out[o + 1] << 8)
                    out += bytes((out[o], out[o + 1]))
                    if dcur == 0:
                        dups[32:47] = dups[0:15]
                        dcur = 0x1F
                    else:
                        dcur -= 1
                    dups[dcur] = pair
                elif s < 0x1A1:                   # recent pair, move to front
                    k = s - 0x191
                    pair = dups[dcur + k]
                    out += bytes((pair & 0xFF, pair >> 8))
                    dups[dcur + 1:dcur + 1 + k] = dups[dcur:dcur + k]
                    dups[dcur] = pair
                else:                             # recent LZ token, move to front
                    k = s - 0x1A1
                    src = reps[rcur + k]
                    out.append(0x9E)
                    here = len(out)
                    out += bytes((out[src], out[src + 1]))
                    if out[here] == 0x80:
                        out += bytes((out[src + 2], out[src + 3]))
                    elif out[here] & 0x40:
                        out.append(out[src + 2])
                    reps[rcur + 1:rcur + 1 + k] = reps[rcur:rcur + k]
                    reps[rcur] = here
            elif mode < 3:
                low = 0
                if mode == 2:                     # distance low bits, 3 classes
                    br.refill()
                    b = br.buf
                    if not b & 0x8000:
                        low, cls = (b >> 11) & 0x0F, 0
                        br.take(5)
                    elif not b & 0x4000:
                        low, cls = (b >> 8) & 0x3F, 1
                        br.take(8)
                    else:
                        low, cls = (b & 0x3F80) >> 7, 2
                        br.take(9)
                s = br.symbol(tree3)
                if mode == 1:                     # 8-bit distance byte
                    if s == 0x100:
                        s = last1
                    else:
                        last1 = s
                    out.append(s & 0xFF)
                else:                             # 16-bit distance word
                    if cls == 0:
                        if s == 0x100:
                            s = last_c0
                        else:
                            last_c0 = s
                        v = ((s + 0x10) << 4) + low
                    elif cls == 1:
                        if s == 0x100:
                            s = last_c1
                        else:
                            last_c1 = s
                        v = ((s + 0x44) << 6) + low
                    else:
                        if s == 0x100:
                            s = last_c2
                        else:
                            last_c2 = s
                        v = ((s + 0xA2) << 7) + low
                    v &= 0xFFFF
                    out += bytes((v & 0xFF, v >> 8))
                mode = 0
            else:                                 # 0x80 token: count, dist lo, dist hi
                s = br.symbol(tree3)
                mode += 1
                if mode == 6:
                    mode = 0
                    if s == 0x100:
                        s = last_hi
                    else:
                        last_hi = s
                else:
                    s = 0 if s == 0x100 else s + 1
                out.append(s & 0xFF)
        used = br.pos - (br.bits >> 3)
        return bytes(out), used

    # ---- EXPLODE / DECODE ----------------------------------------------------
    def _explode(self, chunk):
        """One LZ record: flag byte 0 = stored, else 0x9E-escaped LZ77 into the
        window at HIST; then slide the window down by the output length."""
        w = self.win
        body = chunk[1:]
        if chunk[0] == 0:
            n = len(body)
            w[HIST:HIST + n] = body
        else:
            n = self._decode(body)
        res = bytes(w[HIST:HIST + n])
        w[0:HIST] = w[n:n + HIST]
        return res

    def _decode(self, src):
        w = self.win
        di = HIST
        end_out = HIST + CHUNK_MAX
        si = 0
        end_in = len(src)
        while si < end_in:
            c = src[si]
            if c != 0x9E:
                if di >= end_out:
                    raise ValueError("LZ output overflow")
                w[di] = c
                di += 1
                si += 1
                continue
            code = src[si + 1]
            if code == 0x40:                      # escaped literal 0x9E
                w[di] = 0x9E
                di += 1
                si += 2
                continue
            if code == 0x80:                      # long: count byte + 16-bit distance
                cnt = src[si + 2] + 0x43
                dist = src[si + 3] | (src[si + 4] << 8)
                step = 5
            elif code & 0x40:                     # 16-bit distance
                cnt = (code & 0x3F) + 3
                dist = src[si + 2] | (src[si + 3] << 8)
                step = 4
            else:                                 # 8-bit distance
                cnt = code + 3
                dist = src[si + 2]
                step = 3
            if di <= dist or di + cnt >= end_out:
                raise ValueError("bad LZ match at %d" % si)
            s = di - dist - 1
            for k in range(cnt):                  # rep movsb: overlap-forward copy
                w[di + k] = w[s + k]
            di += cnt
            si += step
        if si != end_in:
            raise ValueError("LZ token runs past chunk end")
        return di - HIST


def decode_member(dec, stream):
    """Decode one member's packed stream: a u32 block size, then blocks
    (mirrors _InitDecompress/_Decompress).  Returns the member's bytes."""
    if len(stream) < 4:
        raise ValueError("stream too short")
    bsize = struct.unpack_from("<I", stream, 0)[0]
    data = stream[4:]
    dec.reset()
    out = bytearray()
    pos = 0
    while pos < len(data):
        blk, used = dec.block(data[pos:pos + bsize])
        if not used:
            raise ValueError("no progress")
        out += blk
        pos += used
    return bytes(out)
