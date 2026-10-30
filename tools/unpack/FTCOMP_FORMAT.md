# PACK2 / FTCOMP - the format UNPACK2.EXE reads

Specification of IBM's PACK2 archive container (magic `A5 96 FD FF`) and its only
algorithm, **FTCOMP**, recovered from `UNPACK2.EXE` and written so that a
reimplementation can be built from this page alone. The reference implementation
beside it, `ftcomp.py` + `pack2.py`, follows it section by section. section 9 lists what it
was validated against.

All multi-byte integers are little-endian. "Word" means u16. Routine names and
`seg:offset` addresses are from `UNPACK2.EXE` 2003-10-14 (79 888 bytes, md5 `7167d6fe...`)
with its matching `unpack2.sym`; the 1995 build differs only in commuted operands
(section 10).

---

## 1. Container

```
archive := member+ trailer
member  := header data-stream [ea-stream]
trailer := u32 member count
```

### 1.1 Member header (0x29 bytes + name)

| Off | Size | Field | Notes |
|---|---|---|---|
| 0x00 | u16 | magic | `0x96A5` |
| 0x02 | u16 | version | `0xFFFD` for PACK2. `UNPACK.EXE` dispatches on this word (PACK_FORMAT.md section 1) |
| 0x04 | u16 | FDATE | OS/2 packed date: `day | month<<5 | (year-1980)<<9` |
| 0x06 | u16 | FTIME | `sec/2 | min<<5 | hour<<11` |
| 0x08 | u16 | attributes | `DosSetFileMode` value; `0x20` (archive) on every member seen |
| 0x0a | u16 | flags | bit 0: "this member's EAs are required" (section 6). 0 on every member seen |
| 0x0c | u32 | EA stream offset | absolute file offset, 0 = no EAs |
| 0x10 | u32 | file size | uncompressed length; 0 = no data stream |
| 0x14 | u32 | next header offset | absolute; 0 = last member |
| 0x18 | char[9] | algorithm | `"FTCOMP"`, NUL-padded. Bytes after the NUL are uninitialised garbage |
| 0x21 | u16 | algorithm version | must be 1 (`_AlgorithmOk`, `stricmp(name,"FTCOMP")==0 && ver==1`) |
| 0x23 | u32 | EA list size | size of the FEALIST (section 6); 4 when there are no EAs |
| 0x27 | u16 | name length | including the NUL |
| 0x29 | char[] | stored name | NUL-terminated, e.g. `\OS2\DLL\OREXX.DLL` or a bare `FDISK.COM` |

`UNPACK2` reads 0x29 bytes, then *name length* more bytes (`_ShowFileNames`,
`_FindSpecificFile`). Its in-memory copy is 0x133 bytes, so a name may be up to 0x10a bytes.

### 1.2 Stream extents

From `_CalcMaxBytesToRead` (`0001:4e58`) and `_EaXfer` (`0001:556f`):

```
data stream:  [header+0x29+namelen,  EA offset   if EA offset
                                     else next header if next header
                                     else EOF-4)
EA stream:    [EA offset,            next header if next header else EOF-4)
```

The `-4` skips the trailer. Each stream is one *member stream* (section 2), and the EA stream is
decoded exactly like file data.

### 1.3 Trailer

The trailer is a u32 member count (`30` in WSeB `disk_4/rexx`, `1` in `fdisk.co_`). UNPACK2
never reads it except to exclude it from the last stream.

---

## 2. Member stream

```
member-stream := u32 blocksize, block*
```

`blocksize` was `0x6080` (24 704) in all 2 701 member headers surveyed (every PACK2 file on
the WSeB ISO, duplicates included). `_Decompress`
(`0001:5dfd`) works like this:

1. Fill a buffer with up to `blocksize` bytes (fewer at the end of the stream).
2. Call `_ftcomp_exec` on it, which returns *(output bytes, bytes consumed)*.
3. Append the output, discard the consumed bytes, top the buffer up again, and repeat
   until the stream is exhausted.

The output buffer is 0x7000 bytes and `blocksize` must not exceed it. Blocks are
therefore variable length, and each one is self-delimiting through its consumed count.

Codec state is reset at the start of every member stream, by `_InitDecompress` ->
`_ftcomp_clearbuffs` (section 5.1). It is **not** reset between blocks: the LZ window carries
across them.

---

## 3. Block (`_ftcomp_exec`, `0001:a714`)

```
block := "fT19" huffman-payload        (encoded)
       | anything else                 (stored)
```

* **Stored**: if the block has fewer than 4 bytes, or does not begin with the signature
  `fT19` (DGROUP `SIGNATURE`), all of the available bytes are output unchanged and all are
  consumed. This also clears the codec's mode byte (`SAVENCODE`) for the **rest of the
  member**: every later block is copied raw too, until the next member resets it. No real
  archive surveyed used this path.
* **Encoded**: the 4 signature bytes are dropped, the Huffman layer (section 4) decodes the
  payload into an *LZ record stream*, and the records are expanded (section 5). Consumed =
  4 + the Huffman layer's consumed count (section 4.6).

The LZ record stream is a sequence of `u16 len, chunk[len]`, where `len <= 0x3008`
and the record must fit in the 0xFE00-byte buffer, else the block is corrupt. Each chunk
goes through `EXPLODE` (section 5.2); the block's output is the concatenation.

---

## 4. Huffman layer (`HUFFMANDECODE`, `0001:91aa`)

### 4.1 Payload header

| Off | Size | Field |
|---|---|---|
| 0 | u16 | `N`: number of LZ-record-stream bytes to produce; `0xFFFF` = stored |
| 2 | u8 | `CAA`: tree-A weight multiplier for ordinary symbols |
| 3 | u8 | `CAX`: tree-A multiplier for "repeat-class" symbols |
| 4 | u8 | `CXX`: tree-B multiplier, repeat-class |
| 5 | u8 | `CXA`: tree-B multiplier, ordinary |
| 6... | | bit stream |

**Stored payload** (`N == 0xFFFF`): bytes 2-3 are a u16 length `L`, and the record stream is
the next `L` bytes, so consumed = `L + 4`. 185 of 2 243 encoded blocks used it (counts in
this document come from decoding every third WSeB archive).

### 4.2 Bit reader

The reader keeps a 16-bit MSB-first buffer and a count of valid bits.

* **Refill**: `while bits <= 8: buf |= next_byte << (8 - bits); bits += 8`.
* **Fast lookup**: `idx = buf >> 7` (the top 9 bits); `node = fast[idx]`; consume
  `fastbits[idx]` bits.
* **Walk**: `while node is internal: take one bit; node = bit ? L[node] : R[node]`. **A 1
  bit selects the left child.** When the buffer is empty during a walk, the next byte is
  loaded into the high half and `bits` becomes 7.

A symbol decode is always: refill, fast lookup, then walk.

### 4.3 Trees

Every tree has **433 leaves** (symbols 0..0x1B0). Node ids are multiples of 4; ids
`< 0x6C4` are leaves, with `symbol = id >> 2`.

| Tree | Built from | Used for |
|---|---|---|
| T2 | seed weights `XCODES2` (DGROUP `0x1898`), once at init | the per-block weight table (section 4.4) |
| T3 | seed weights `XCODES3` (DGROUP `0x1C98`), once at init | LZ token operands (section 4.5) |
| A | this block's weights x (`CAA`/`CAX`) | main symbols |
| B | this block's weights x (`CXA`/`CXX`) | main symbols following a repeat-class symbol |

All four are built by `BUILDTREE` (section 7). The tie-breaking there is part of the format.

### 4.4 Per-block weights, and trees A and B (`BUILDTREES`, `0001:8fe2`)

Decode 433 values `v[0..432]` with T2. For each symbol `s`:

* `s == 0x100`: the next `min(16, 433 - i)` values are 0;
* otherwise `v[i] = s & 0xFF`.

`ISREPCODE` (DGROUP `0x16E6`, 434 bytes) marks the repeat-class symbols. For tree A, weight
`w[i] = v[i] * (ISREPCODE[i] ? CAX : CAA)` for each non-zero `v[i]` (16-bit product).

Then normalise: if `max(w) > 255`, set `s = 0xFFFF / max`, and replace every `w[i]` with
`((w[i]*s) & 0xFFFF) >> 8`. A non-zero weight that rounds to 0 becomes 1.

Build tree A from `w`.

* If `(CXX, CXA) == (CAX, CAA)`, or `CXX == CXA == 0`, tree B **is** tree A.
* Otherwise derive tree B the same way with `CXX`/`CXA`. Of 2 058 blocks surveyed, 627
  shared one tree and 1 431 had two.

### 4.5 Symbol stream

The block is decoded into `out[]` until `len(out) >= N`. The state is:

* `mode` (operand bytes still owed by an LZ token), initially 0;
* `useB`, initially 0;
* five "last value" registers `last1`, `lastC0`, `lastC1`, `lastC2`, `lastHi`, all 0;
* two 48-entry move-to-front tables, `REPS` (positions in `out` of LZ code bytes) and
  `DUPS` (recent 2-byte values), each with a cursor initialised to 0x20. All of this is
  reset per block.

**`mode == 0`** - decode `s` with tree B if `useB`, else tree A; then
`useB = ISREPCODE[s]`.

| `s` | Meaning |
|---|---|
| `0x000-0x0FF` | literal byte `s` |
| `0x100-0x180` | LZ token: emit `9E`, `c = s-0x100`. `mode = EATTABLE[c]` (DGROUP `0x15E6`). If `mode != 0`, push the position of `c` in `out` onto `REPS` |
| `0x181-0x190` | repeat the 2-byte pair `d = s-0x17F` (2..17) bytes back; push that pair onto `DUPS` |
| `0x191-0x1A0` | emit `DUPS[cur + (s-0x191)]`, then move it to the front |
| `0x1A1-0x1B0` | re-emit the LZ token whose code byte sits at `REPS[cur + (s-0x1A1)]`: emit `9E`, then copy the code byte and its operands from there (`80` -> 3 more bytes, bit 6 set -> 2 more, otherwise 1 more); move it to the front, storing the new code byte's position |

*Push* is `if cur == 0: copy entries 0..15 (REPS) or 0..14 (DUPS) to 32..; cur = 31;
else cur -= 1`, followed by `table[cur] = value`. *Move to front* shifts
`table[cur .. cur+k)` up by one and stores the value at `cur`. The live window is
`table[cur .. cur+16)`.

`EATTABLE`: codes `0x00-0x3F` -> 1, `0x41-0x7F` -> 2, `0x80` -> 3, all others -> 0. That is
the operand count of each `DECODE` token form (section 5.3).

**`mode == 1`** (8-bit distance) - decode `s` with T3. `s == 0x100` means "same as last
time" (`last1`); otherwise `last1 = s`. Emit 1 byte; `mode = 0`.

**`mode == 2`** (16-bit distance) - refill, then read a class prefix and the low bits:

| Top bits | Low bits | Class | Bits consumed |
|---|---|---|---|
| `0` | 4: `(buf>>11)&0xF` | 0 | 5 |
| `10` | 6: `(buf>>8)&0x3F` | 1 | 8 |
| `11` | 7: `(buf&0x3F80)>>7` | 2 | 9 |

Then decode `s` with T3. `0x100` means that class's last value; otherwise store it. Emit
the u16 `((s+0x10)<<4)+low`, `((s+0x44)<<6)+low` or `((s+0xA2)<<7)+low` (16-bit); `mode = 0`.

**`mode >= 3`** (the `80` token: count, distance low, distance high) - decode `s` with T3 and
increment `mode`.

* If `mode` reaches 6: `mode = 0`, and `s == 0x100` means `lastHi` (otherwise store it).
* Otherwise emit `0` for `0x100`, else `s+1`.

Every branch emits exactly one byte.

### 4.6 End

The produced length is `len(out)`. **Consumed** = bytes taken by the bit reader minus
`bits >> 3`, which hands back unread whole bytes. Data passes through `9E` unescaped
here; escaping is the LZ layer's business.

---

## 5. LZ layer

### 5.1 The window (`_ftcomp_clearbuffs`, `0001:a69c`)

The window is one 0xFFE4-byte segment. The history occupies `[0, 0xCFDC)` (53 212
bytes), and each chunk's output is written at `0xCFDC` (up to 0x3008 bytes). At the start
of every member stream (decode mode, `FASTMODE` 0):

| Range | Content |
|---|---|
| `0xBC62..+0x140` | `0x20` |
| `0xBDA2..+0x140` | `0xFF` |
| `0xBEE2..+0x140` | `0x00` |
| `0xC022..+0xFBA` | `INIDATA` (DGROUP `0x062C`, 4 026 bytes) |

`INIDATA` is a preset dictionary: MS C runtime messages (`R6000 - stack overflow`...),
device names (`LPT1: COM1: NUL:`...), code fragments. **`[0, 0xBC62)` is not cleared**: it
keeps whatever the previous member left. No real stream references it (section 9 checks this),
but a bit-exact decoder should keep one window per process, not per member.

### 5.2 Chunk (`EXPLODE`, `0001:a622`)

```
chunk := 00 bytes*        stored: output = bytes
       | xx lz-tokens*    xx != 0: DECODE the rest
```

Output is written at `0xCFDC`. Afterwards the window slides: `win[0:0xCFDC] =
win[n:n+0xCFDC]`, where `n` is this chunk's output length. 54 of 3 911 chunks surveyed were
stored.

### 5.3 Tokens (`DECODE`, `0001:75fe`)

The escape byte is `0x9E`; any other byte is a literal.

| Bytes | Length | Distance `d` |
|---|---|---|
| `9E 40` | literal `9E` | - |
| `9E 80 n lo hi` | `n + 0x43` (67..322) | 16-bit |
| `9E c lo hi`, `c & 0x40` (`c != 0x40`) | `(c & 0x3F) + 3` (3..66) | 16-bit |
| `9E c d`, otherwise | `c + 3` (3..194 when `c` is 0x00-0x3F or 0x81-0xBF) | 8-bit |

`d` is an **absolute-from-the-current-position** offset: the copy source is
`win[di - d - 1]`, where `di` is the absolute output position in the window (starting at
`0xCFDC`). The copy is a forward byte copy, so overlap repeats. The chunk is corrupt
(`_ftcomp_exec` returns `-1`, member deleted) when:

* `di <= d`;
* `di + length >= 0xCFDC + 0x3008`, so a match may not end exactly at the limit;
* a literal arrives when `di >= 0xCFDC + 0x3008` (the `9E 40` literal is not checked);
* a token runs past the end of the chunk.

---

## 6. EAs

The EA stream decodes to a 16-bit **FEALIST**: `u32 cbList`, then FEA records
`{u8 fEA, u8 cbName, u16 cbValue, name, NUL, value}`. `_WriteEaBuf` (`0001:5222`)
overwrites `cbList` with the decoded length, then applies the buffer with
`DosSetFileInfo(handle, 2, EAOP{fpFEAList=buf})`. Header `+0x23` equals that length
(230/230 checked).

When the target file system has no EA support (`_TargetSupportsEa`), and the member has an
EA stream:

* if `/F` was given, or header flags bit 0 is set: error 282, `ERROR_EAS_NOT_SUPPORTED`
  (`0x11A`), and the member is skipped;
* otherwise: message 284 (`0x11C`), whose `bseerr.h` message is `MSG%EAS_DISCARDED`, and
  the file is unpacked without its EAs.

---

## 7. `BUILDTREE` (`0001:8cbe`) and `SORT` (`0001:8a7c`)

Both are ported literally in `ftcomp.py` (`build_tree`, `_sort`). The algorithm:

1. **Collect** non-zero leaves into array `A` in symbol order. Weight-1 leaves are moved
   to a growing prefix: the element at the prefix end moves to the end of `A`, and the
   weight-1 leaf takes its place. A single non-zero leaf is paired with the last
   zero-weight leaf seen, whose weight is forced to 1.
2. **Sort** `A[m..n-1]`, where `m` is the size of the weight-1 prefix, ascending by weight.
   This is a non-stable quicksort: middle-element pivot, Hoare partition, explicit stack
   kept in `A` past `hi`, smaller side first. Ranges with `hi-lo <= 16` use insertion sort,
   inserting before the first element `>=` the key.
3. **Merge** `n-2` times: take `a = A[f]`, `b = A[f+1]`; the new node gets
   `W = W[a]+W[b]` **as a 16-bit sum** (433 weights of 255 overflow it), `L = a`, `R = b`.
   It is inserted at the lower bound of its weight in `A[f+2..n)`, i.e. *before* equal
   weights, then `f += 1`. The last two are merged into the root. New node ids run from
   `0x6C4` in steps of 4.
4. **Fast table**: for each 9-bit prefix, walk from the root (1 = left) for at most 9
   steps, and record the node reached and the steps taken.

Tie-breaking is fully determined by steps 1-3, and decoding is bit-exact only if they are
reproduced exactly. A fuzzer (not shipped) compared the port with IBM's machine code on
random tie-heavy and overflowing weight sets.

---

## 8. What a decoder must get right (checklist)

1. Consumed counts: Huffman bytes minus `bits>>3`, plus 4.
2. Signature miss / short block => raw, *and raw for the rest of the member*.
3. Tree B shortcut cases (section 4.4) and the 255-normalisation rounding.
4. The inverted branch sense (1 = left) in all four trees.
5. `0x100` as a zero-run in the weight table, but as "repeat last" (or `count 0`) in the
   operand modes.
6. `REPS`/`DUPS` push vs move-to-front, and their reset-per-block.
7. Absolute `di - d - 1` addressing over a window preset with `INIDATA` and the
   0x20/0xFF/0x00 runs.
8. The window slide after *every* chunk, stored ones included.
9. 16-bit wrap in `BUILDTREE` weight sums.
10. Stream extents: EA offset / next header / EOF-4.

---

## 9. Validation (2026-10-22)

The test oracles named below (an emulator harness around IBM's own codec, and a fuzzer) were
used to produce these results; they are not shipped with this kit.

| Check | Result |
|---|---|
| `fdisk.co_` (Warp 3 fixpak) vs `FDISK.COM` unpacked by IBM UNPACK on a real OS/2 VM | md5 `45b9c245...` identical |
| All 285 distinct PACK2 archives on a Warp Server for e-business install ISO | 2 685 members, 112 MB decoded, 0 errors, 0 size mismatches |
| ...against an installed Warp Server for e-business tree | 1 178 identical. 9 differ (`INI.RC`, `INISYS.RC`, `INSTALL.SCR`, `LSI.MSG`, ...), and all 9 are byte-identical to IBM's own codec output, i.e. they were modified by install, not decoded wrongly |
| IBM's own codec under unicorn (an emulator harness, not shipped) | 300 random members, 347 streams incl. EA, 18.4 MB: 0 diffs |
| Fresh window per member vs one shared window | identical output for every member: the stale `[0,0xBC62)` region is never referenced |
| T2/T3 fixed trees + fast tables vs IBM's after `_ftcomp_init` | all 866 nodes and both 512-entry tables identical |
| `BUILDTREE` fuzz vs IBM's (the fuzzer above) | 2 400 trials incl. 1/2-symbol and overflow cases: 0 mismatches |
| Regression after the fuzz-found fixes, every root (WSeB ISO, DevCon CDs, mounted 1996 tree) | 5 911 archives, 15 852 members, 855 MB: 0 errors |
| eCS 2.0 RC7 CD (all 900 PACK2 files) | 0 errors; same `UNPACK2.EXE` as WSeB |

**Coverage limits**:

* No archive surveyed had a non-zero header flags word, an attribute other than `0x20`,
  or a raw (signature-less) block. Those paths are implemented from the code, not
  exercised by data.
* The oracle validates the codec, not `UNPACK2`'s file-system behaviour (section CLI in
  `INDEX.md`).

## 10. Build stability

* `UNPACK2.EXE` 1995-12-04 (79 792 bytes, `disk_3` of the mounted ISO view) has every
  constant table at the same DGROUP offset, byte-identical, and a byte-identical `DECODE`.
* Its `BUILDTREE`/`BUILDTREES` differ from the 2003 build only in operand order (`a*b`
  vs `b*a`, `W[a]+W[b]` vs `W[b]+W[a]`), which is the same result mod 2^16.
* The rest are relocated selector chains. The format did not change between these builds.

## 11. Not covered

`UNPACK2.EXE` also contains the **encoder**: `ENCODE`, `HUFFMANCODE` (`0001:993e`),
`IMPLODE`, `FINDMATCH*`, plus the `FILENCODE==1` paths in `_ftcomp_exec`/`_ftcomp_init`
(seed tables `INITLIST*`, `FREEZONE`). It was not read. A PACK2 *writer* could be derived
from the same binary and validated by round-tripping through `ftcomp.py`.
