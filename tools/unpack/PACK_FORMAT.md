# PACK (version 1) - the format UNPACK.EXE decodes itself

Specification of IBM's original PACK format (magic `A5 96`, version word `FFFE`, and the
older `FFFF` / `0A0A` / `0A14` / `0A1E` / `1400`) and its codec, a **12-bit LZW with an
LRU-recycled dictionary**. It was recovered from `UNPACK.EXE` 2003-10-14 (74 896 bytes,
md5 `08fe2912...`) with its matching `unpack.sym`. Reference implementation: `pack1.py`.

`UNPACK.EXE` does not decode version `FFFD` (PACK2). It re-executes `UNPACK2.EXE` for
that version (section 5); the format is in `FTCOMP_FORMAT.md`.

All integers are little-endian.

---

## 1. Version dispatch (`_Check_File_Header`, `0001:0515`)

`UNPACK` reads 10 bytes: `u16 magic, u16 version, u16 FDATE, u16 FTIME, u16 attributes`.

| magic / version | Meaning | Rest of header | Data starts at |
|---|---|---|---|
| not `0x96A5` | not packed: **plain copy** of the whole file | - | 0 |
| `FFFD` | PACK2: exec `UNPACK2.EXE` (section 5) | - | - |
| `FFFE` (the "ver = 2.0" debug label) | section 2 | 16 more bytes, then the name | `0x1A + namelen` |
| `FFFF` ("ver = 1.3") | single member, EAs out of line | 5 bytes: `u32 EA offset` @`0x0A`, `u8 flags` @`0x0E`; NUL-terminated name @`0x0F` | after the name's NUL |
| `0A0A` `0A14` `0A1E` `1400` ("ver = 1.1, 1.2") | single member, no EAs | 13-byte name field @`0x0A` | `0x18` |
| anything else | error `0x4C1` (1217): "cannot be decompressed with this version of UNPACK" | | |

The debug labels come from `UNPACK`'s own `/headerINFO` dump strings. Every version except
`FFFD` runs the same codec (section 3) through `_Unpack` -> `_expreal` (real mode) or the threaded
`_explode` (protected mode).

**Corpus**: every `A5 96` file on a Warp Server for e-business install image, a CID tree, the IBM
Developer Connection CDs and two archive collections is `FFFD` (5 927) or `FFFE`
(2 117 files, 2 080 distinct). No `FFFF` or 1.x file was found, so those two rows are
implemented from the code and untested.

---

## 2. Version FFFE container

```
file   := member+ [padding] [trailer]
member := header data-stream? pad ea-stream? pad
```

### 2.1 Header (0x1A bytes + name)

| Off | Size | Field |
|---|---|---|
| 0x00 | u16 | magic `0x96A5` |
| 0x02 | u16 | version `0xFFFE` |
| 0x04 | u16 | FDATE |
| 0x06 | u16 | FTIME |
| 0x08 | u16 | attributes |
| 0x0A | u16 | flags |
| 0x0C | u32 | EA stream offset (absolute; 0 = none) |
| 0x10 | u32 | file size. **0 means there is no data stream**, and `UNPACK` goes straight to the EA stream (`STRIP_HEADER`). 133 members, all from two products in a CID install tree, carry `1` with real data of any length. `UNPACK` never uses the field as a length |
| 0x14 | u32 | next member offset (absolute; 0 = last) |
| 0x18 | u16 | name length (the field's padded length; the name inside is NUL-terminated) |
| 0x1A | char[] | name, e.g. `audio.dl$`. Paths are allowed |

The name length is always `== 2 (mod 4)`, which makes the header a multiple of 4 bytes
(2 117/2 117).

### 2.2 Layout and alignment

After each stream's end code (section 3.2), `UNPACK` (`START_NEXT_FILE` / `EAT_ZEROS` /
`NEXT_HEADER`):

1. pads to a 4-byte boundary;
2. skips whole zero dwords;
3. expects either another `A5 96 FE FF` header or the member's EA stream.

`UNPACK` does **not** read the `+0x0C`/`+0x14` pointers for this. It uses them only as
"is anything more coming?" flags on a member: both 0 means stop.

**Correction (2026-10-22, recorded in place):** an earlier version of this doc said the
pointers and the streaming rule agree on all members, so either could be used, and
`pack1.py` followed the pointers. The eCS CD disproves that.
`CID\SERVER\FFST\EPW\EPWDRIVR.PAK` has three members whose EA-offset field was written
1-3 bytes out of place: `0x3c2d8` stored at `+0x0B`, `0x295d4` at `+0x09`. Following the
pointers lost two EAs and misread a third. **The stream is authoritative.** `pack1.py` now
implements UNPACK's rule (`members()` docstring), reports pointer disagreements as
diagnostics, and agrees with IBM's LZW code on all of that file's streams. Over 6 265
members the pointers disagree only in those 3.

The alignment is counted from the first member's data start in the read buffer. Because
that start is always 4-aligned (section 2.1), this is the same as file-absolute alignment.

### 2.3 Trailer

Most files end in 0-3 zero bytes plus a **u32 member count**, as PACK2 does. The count is
**not** 4-aligned. Some files end in padding only (e.g. one product's files in a CID tree), and one ends
in `FF FF FF FF`. `UNPACK` never
reads past the last stream, so the trailer is advisory.

### 2.4 EAs

The EA stream decodes to a FEALIST, which `WRITETOEA` (`0001:3f3e`) passes **verbatim** to
`DosSetFileInfo(h, 2, EAOP)`. Unlike PACK2, `cbList` is not patched, so bytes past
`cbList` are ignored; one real member has 7 such bytes. 633 members carry EAs.

---

## 3. Codec

### 3.1 Code stream

Codes are **12-bit, packed big-endian two per three bytes**:

```
code1 = b0<<4 | b1>>4
code2 = (b1 & 0x0F)<<8 | b2
```

A zero code ends the stream. After `code1 == 0` only `b0` and the high half of `b1` are
consumed; the next stream's alignment counts from `b1`.

| Code | Meaning |
|---|---|
| 0 | end of stream |
| 1..256 | literal byte `code-1` |
| 257..4095 | dictionary string |

### 3.2 Dictionary (`DECODE`, `0001:534f`)

Per code `c`, the dictionary keeps `CHR[c]`, `PREFIX[c]`, `REF[c]` (how many entries use
`c` as their prefix), and an LRU doubly-linked list of *leaves* (`REF == 0`), with
sentinel 0. Reset per stream:

* `CHR[c] = c-1` and `REF[c] = 1` for `c` in 1..256 (literals never become leaves);
* `free = 256`, `prev = 0`, LRU empty.

For each code `c` (non-zero):

1. **Allocate** `new`: if `free < 4095`, then `new = ++free`. Otherwise **recycle**: unlink
   the oldest leaf `new` from the LRU head, then `REF[PREFIX[new]] -= 1`; if that reaches
   0, append `PREFIX[new]` to the LRU tail (it has just become a leaf).
2. **Emit** `c`'s string. Walk `PREFIX` from `c` down to its root literal `r`;
   `CHR[prev] = CHR[r]` completes the *previous* step's entry; then output the chain's
   `CHR` bytes root-first. The original reverses the chain in place and restores it while
   emitting; the output is the same.
3. **Link**: if `REF[c] == 0`, unlink `c` from the LRU (it is gaining a child);
   `REF[c] += 1`.
4. **Record** the new entry: append `new` to the LRU tail; `PREFIX[new] = c`;
   `REF[new] = 0`; `prev = new`. Its `CHR` is filled in by the next code (step 2): the
   new entry = `c`'s string + the first byte of the next string. That makes the
   KwKwK case (the next code naming `new` itself) work naturally.

Recycling therefore always evicts the least-recently-*created-or-orphaned* leaf. It never
evicts an entry that is still some other entry's prefix.

### 3.3 Reset points

The dictionary is reset at every member header and before every EA stream
(`STRIP_HEADER` tail, `0001:554d`; `NEXT_HEADER` in the threaded path).

---

## 4. Version FFFF and 1.x

These versions are single-member. For `FFFF`, `_Unpack` (`0001:0ae9`) decodes the data
stream, then (if the EA offset is non-zero and the target supports EAs) seeks to the EA
offset and runs the codec again in EA mode. For 1.x the EA offset is forced to 0.

**Untested: no sample exists in this tree.**

---

## 5. Hand-off to UNPACK2 (`_ExecuteNewUnpack`, `0001:407a`)

For `FFFD`, `UNPACK`:

1. builds `UNPACK2.EXE`'s path from `argv[0]`'s directory, using it if `DosQFileMode`
   finds it there and the bare name `UNPACK2.EXE` otherwise;
2. rebuilds the command line, with each argument from `argv[1]` on wrapped in `"`, and a
   trailing `\` doubled;
3. runs `DosExecPgm` synchronously and exits with the child's return code. If the exec
   fails it reports 1217 and exits 4.

So every `UNPACK` switch reaches `UNPACK2` unchanged, and a PACK2 archive behaves the
same under either command.

---

## 6. Validation (2026-10-22)

| Check | Result |
|---|---|
| All 2 098 distinct `FFFE` files in the corpus, both install CDs included | 6 265 members, 264 MB decoded, 0 decode errors; the header pointers disagree with the stream only in the 3 EPWDRIVR.PAK members above |
| Sizes | 6 085 members equal header `+0x10` exactly; the other 133 carry `1` (section 2.1) |
| FEALIST structure | 635/636 tile `cbList` exactly; the 1 exception has `cbList` 7 bytes short of the stream, which `UNPACK` ignores by design (section 2.4) |
| IBM's own `DECODE` under unicorn, code by code (an emulator harness, not shipped) | 42 files, 149 streams (72 long enough to recycle dictionary entries), 9.85 MB: 0 diffs |

**Known gap**: nothing on disk has an unpacked counterpart for a `FFFE` file, so there is
no independent ground-truth file comparison like PACK2's. The oracle run is the
ground-truth check. Content sanity: decoded EXEs and DLLs carry valid MZ/LX headers, and
text members are clean text.
