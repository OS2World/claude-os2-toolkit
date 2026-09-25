# OS/2 Executable Formats - LX (32-bit) and NE (16-bit)

The two module formats an OS/2 loader and linker deal with: the **Linear eXecutable (LX)**
format used by 32-bit programs, dynamic-link libraries, and 32-bit device drivers, and the
**New Executable (NE)** format inherited from 16-bit OS/2 (and shared with 16-bit Windows) used
by 16-bit programs, DLLs, and drivers. Both are demand-paged/segmented images with a small
DOS-compatible stub at the front; the real module begins at a "new header" whose offset is
recorded in the DOS stub. This reference gives the header, the object/segment table, the
page/relocation tables, the name tables, and the entry table for each format, at field level,
distinguishing facts taken from the published LX/NE format specification from facts taken from
the IBM Toolkit headers.

Provenance: **[DOC-IBM]** the IBM OS/2 Toolkit headers `exe386.h` (LX) and `newexe.h` (NE),
which define the C structures, field names, and manifest constants; **[DOC-IBM]** IBM's *LX -
Linear eXecutable Module Format Description* (June 3, 1992), the format specification prose
(layout, field semantics, load-time behavior, fixup grammar); **[DOC]** the community-transcribed
*New Executable* format description (segment/relocation/entry-table grammar), cross-checked
against `newexe.h`. Field offsets and sizes are given as they fall out of the byte-packed
(`#pragma pack(1)`) C structures.

---

## 1. Overview and file layout

An OS/2 executable file begins with a **DOS 2-compatible `.EXE` header** (`struct exe_hdr`,
magic `MZ` = 0x5A4D) whose field at offset **0x3C** (`e_lfanew`) holds the file offset of the
"new" header that follows the DOS stub program. The loader reads the DOS header, follows
`e_lfanew`, and inspects the first two bytes there: `"LX"` (0x584C) selects the 32-bit Linear
eXecutable path; `"NE"` (0x454E) selects the 16-bit New Executable path. [DOC-IBM - `newexe.h`
`EMAGIC`/`ENEWHDR`, `exe386.h` `E32MAGIC`, `newexe.h` `NEMAGIC`]

```
struct exe_hdr {                    /* DOS 1/2/3 .EXE header - 64 bytes */
    unsigned short e_magic;         /* 0x00  Magic number 'MZ' (0x5A4D)               */
    ...                             /*       (DOS stub fields)                          */
    long           e_lfanew;        /* 0x3C  File offset of the new (LX or NE) header  */
};                                  /* 0x40                                              */
```
[DOC-IBM - `newexe.h` `struct exe_hdr`; `E_LFANEW`]

### 1.1 The DOS stub is OPTIONAL - an LX file may start at `LX` [DOC-IBM][OBS-RE]

**The trap.** The paragraph above describes the usual arrangement, and it is easy to read as the
only one: find `MZ`, follow `e_lfanew`, expect `LX` there. A loader written that way rejects a
large class of real, valid OS/2 binaries - and it rejects them with a message like "not an MZ/LX
image", which reads as *corrupt file* rather than *second valid layout*.

**The fact.** The DOS stub is something the linker ADDS, not something the format requires.
LINK386's `STUB` statement selects the DOS executable to place at the front, and IBM notes that
"By default, LINK386 adds its own standard stub for this purpose" - a default, which a build may
omit. When it is omitted the LX header IS the file, so the `LX` magic sits at **offset 0** and
there is no `e_lfanew` to follow. This is not exotic: a DLL is never started from DOS, so nothing
needs the stub, and shipped DLLs are found in both shapes.
[DOC-IBM - `toolinf2.txt` "LINK386 - STUB Statement"] [OBS-RE - two shipped `tinfo6.dll` builds of
the same library, one bare-LX and one MZ-stubbed]

**How to verify.** The first two bytes decide it, with no parsing:

```sh
head -c 2 SOMEFILE.DLL | od -c      # '  L  X'  -> header at offset 0
                                    # '  M  Z'  -> follow e_lfanew at 0x3C
```

**The tell.** A binary that `file` happily calls "LX executable for OS/2" while your own reader
calls malformed is this, every time. Read the magic at offset 0 first, and only fall back to the
`MZ` + `e_lfanew` path when it is not `LX`.

**LX file layout** (the order in which sections appear in the file) is: DOS section (discarded)
-> Linear EXE header -> *Loader section* (Object Table, Object Page Table, Resource Table, Resident
Name Table, Entry Table, Module Format Directives Table, Per-Page Checksum Table) -> *Fixup section*
(Fixup Page Table, Fixup Record Table, Import Module Name Table, Import Procedure Name Table) ->
data (Preload Pages, Demand Load Pages, Iterated Data Pages) -> Non-Resident Name Table -> Debug
Information. All table offsets in the header are relative to the **beginning of the LX header**,
except a few explicitly relative to the beginning of the **file** (see section 2.2). A table offset of
zero means the table is absent and its size is zero. [DOC-IBM - LX spec, "32-bit Linear EXE File
Layout"]

---

## 2. LX - Linear eXecutable (32-bit)

### 2.1 Signatures and enumerations [DOC-IBM]

| Symbol | Value | Meaning |
|---|---|---|
| `E32MAGIC` | 0x584C (`'L','X'`) | LX signature word; `'L'` low byte, `'X'` high byte |
| `E32LEBO` / `E32BEBO` | 0x00 / 0x01 | byte order: little / big endian |
| `E32LEWO` / `E32BEWO` | 0x00 / 0x01 | word order: little / big endian |
| `E32LEVEL` | 0 | format level (0 for the initial/only version) |
| `E32CPU286` / `E32CPU386` / `E32CPU486` | 0x01 / 0x02 / 0x03 | required CPU |
| `OBJPAGELEN` | 4096 | LX page size (bytes) |

OS type is shared with NE: `NE_UNKNOWN` 0, `NE_OS2` 1, `NE_WINDOWS` 2, `NE_DOS4` 3, `NE_DEV386`
4. [DOC-IBM - `exe386.h` defines; `newexe.h` OS-type defines]

### 2.2 The LX header (`struct e32_exe`) [DOC-IBM]

Byte-packed; padded with reserved bytes to **196 bytes**. Offsets are from the start of the LX
header.

| Off | Field | Size | Purpose |
|---|---|---|---|
| 0x00 | `e32_magic[2]` | 2 | `"LX"` |
| 0x02 | `e32_border` | 1 | byte ordering |
| 0x03 | `e32_worder` | 1 | word ordering |
| 0x04 | `e32_level` | 4 | EXE format level (0) |
| 0x08 | `e32_cpu` | 2 | CPU type |
| 0x0A | `e32_os` | 2 | OS type |
| 0x0C | `e32_ver` | 4 | module version (set at link time) |
| 0x10 | `e32_mflags` | 4 | module flags (section 2.3) |
| 0x14 | `e32_mpages` | 4 | number of pages physically in the module |
| 0x18 | `e32_startobj` | 4 | object number the entry EIP is relative to |
| 0x1C | `e32_eip` | 4 | entry address (offset within `e32_startobj`) |
| 0x20 | `e32_stackobj` | 4 | object number the initial ESP is relative to |
| 0x24 | `e32_esp` | 4 | initial ESP (0 = top of the stack object) |
| 0x28 | `e32_pagesize` | 4 | page size (4096) |
| 0x2C | `e32_pageshift` | 4 | page-offset shift for Object Page Table offsets (default 12) |
| 0x30 | `e32_fixupsize` | 4 | total size of the fixup section (4 tables) |
| 0x34 | `e32_fixupsum` | 4 | fixup-section checksum (0 if unused) |
| 0x38 | `e32_ldrsize` | 4 | size of the resident loader section (Object Table ... Per-Page Checksum) |
| 0x3C | `e32_ldrsum` | 4 | loader-section checksum (0 if unused) |
| 0x40 | `e32_objtab` | 4 | Object Table offset |
| 0x44 | `e32_objcnt` | 4 | number of objects in the module |
| 0x48 | `e32_objmap` | 4 | Object Page Table offset |
| 0x4C | `e32_itermap` | 4 | Object Iterated-Data Map offset (file-relative) |
| 0x50 | `e32_rsrctab` | 4 | Resource Table offset |
| 0x54 | `e32_rsrccnt` | 4 | number of Resource Table entries |
| 0x58 | `e32_restab` | 4 | Resident Name Table offset |
| 0x5C | `e32_enttab` | 4 | Entry Table offset |
| 0x60 | `e32_dirtab` | 4 | Module Format Directives Table offset |
| 0x64 | `e32_dircnt` | 4 | number of module directives |
| 0x68 | `e32_fpagetab` | 4 | Fixup Page Table offset |
| 0x6C | `e32_frectab` | 4 | Fixup Record Table offset |
| 0x70 | `e32_impmod` | 4 | Import Module Name Table offset |
| 0x74 | `e32_impmodcnt` | 4 | number of Import Module Name Table entries |
| 0x78 | `e32_impproc` | 4 | Import Procedure Name Table offset |
| 0x7C | `e32_pagesum` | 4 | Per-Page Checksum Table offset |
| 0x80 | `e32_datapage` | 4 | Data Pages (preload) offset (file-relative) |
| 0x84 | `e32_preload` | 4 | number of preload pages |
| 0x88 | `e32_nrestab` | 4 | Non-Resident Name Table offset (file-relative) |
| 0x8C | `e32_cbnrestab` | 4 | Non-Resident Name Table size (bytes) |
| 0x90 | `e32_nressum` | 4 | Non-Resident Name Table checksum |
| 0x94 | `e32_autodata` | 4 | Auto Data Segment object number (16-bit compatibility only) |
| 0x98 | `e32_debuginfo` | 4 | Debug Information offset |
| 0x9C | `e32_debuglen` | 4 | Debug Information length (bytes) |
| 0xA0 | `e32_instpreload` | 4 | number of instance pages in the preload section |
| 0xA4 | `e32_instdemand` | 4 | number of instance pages in the demand-load section |
| 0xA8 | `e32_heapsize` | 4 | heap size added to the auto-DS object (16-bit apps only) |
| 0xAC | `e32_stacksize` | 4 | stack size |
| 0xB0 | `e32_res3[20]` | 20 | reserved (pad to 196 bytes) |

[DOC-IBM - `exe386.h` `struct e32_exe`; field semantics from LX spec "32-bit Linear EXE
Header"]

Notes: `e32_itermap`, `e32_datapage`, and `e32_nrestab` offsets are relative to the **beginning
of the file**; the remaining table offsets are relative to the **beginning of the LX header**.
`e32_mpages` counts only pages physically present (enumerated, iterated, or relocated
zero-fill) - not pure zero-fill/invalid pages implied by an object's virtual size. [DOC-IBM - LX
spec]

### 2.3 Module flags (`e32_mflags`) [DOC-IBM]

| Symbol | Value | Meaning |
|---|---|---|
| `E32LIBINIT` | 0x00000004 | per-process library initialization (else global) |
| `E32NOINTFIX` | 0x00000010 | internal fixups have been applied/removed from the file |
| `E32NOEXTFIX` | 0x00000020 | external fixups have been applied |
| `E32NOPMW` | 0x00000100 | incompatible with PM windowing |
| `E32PMW` | 0x00000200 | compatible with PM windowing |
| `E32PMAPI` / `E32APPMASK` | 0x00000300 | uses the PM windowing API / application-type mask |
| `E32NOLOAD` | 0x00002000 | module not loadable (link errors or incremental link) |
| `E32MODMASK` | 0x00038000 | module-type mask |
| `E32MODEXE` | 0x00000000 | program (`.EXE`) module |
| `E32MODDLL` / `E32NOTP` | 0x00008000 | library (DLL) module |
| `E32MODPROTDLL` | 0x00018000 | protected-memory library module |
| `E32MODPDEV` | 0x00020000 | physical device driver |
| `E32MODVDEV` | 0x00028000 | virtual device driver |
| `E32LIBTERM` | 0x40000000 | per-process library termination |
| `E32NOTMPSAFE` | 0x00080000 | process is multiprocessor-unsafe (SMP builds) |

[DOC-IBM - `exe386.h` module-flag defines; LX spec "MODULE FLAGS"]

### 2.4 Object Table (`struct o32_obj`) [DOC-IBM]

Each entry is **24 bytes**. Objects are numbered from 1. The table has `e32_objcnt` entries;
entries are ordered by their page-table index.

| Off | Field | Size | Purpose |
|---|---|---|---|
| 0x00 | `o32_size` | 4 | object virtual size (bytes) |
| 0x04 | `o32_base` | 4 | preferred (relocation) base virtual address |
| 0x08 | `o32_flags` | 4 | object attribute flags (section 2.5) |
| 0x0C | `o32_pagemap` | 4 | index of this object's first Object Page Table entry |
| 0x10 | `o32_mapsize` | 4 | number of Object Page Table entries for this object |
| 0x14 | `o32_reserved` | 4 | reserved (0) |

[DOC-IBM - `exe386.h` `struct o32_obj`; LX spec "Object Table"]

### 2.5 Object flags (`o32_flags`) [DOC-IBM]

The published LX specification defines the low word as:

| Value | Meaning |
|---|---|
| 0x0001 | Readable object (`OBJREAD`) |
| 0x0002 | Writable object (`OBJWRITE`) |
| 0x0004 | Executable object |
| 0x0008 | Resource object (`OBJRSRC`) |
| 0x0010 | Discardable object |
| 0x0020 | Shared object |
| 0x0040 | Object has preload pages |
| 0x0080 | Object has invalid pages (`OBJINVALID`) |
| 0x0100 | Object is resident - valid for VDDs/PDDs only |
| 0x0200 | Reserved |
| 0x0300 | Object is resident & contiguous - VDDs/PDDs only |
| 0x0400 | Object is resident & 'long-lockable' - VDDs/PDDs only |
| 0x0800 | Object is marked as an IBM Microkernel extension |
| 0x1000 | 16:16 alias required (80x86-specific) |
| 0x2000 | Big/Default bit setting (80x86-specific) |
| 0x4000 | Conforming for code (80x86-specific) |
| 0x8000 | Object I/O privilege level (80x86-specific) |

[DOC-IBM - os2tk45 LX spec (`lxref`) section "OBJECT FLAGS"]. The Big/Default (0x2000)
bit sets the descriptor B-bit for data (ESP vs SP) and D-bit for code (default 32- vs 16-bit
operand/address size). [DOC-IBM - LX spec]

> **Note on constant naming.** `exe386.h` defines two parallel naming schemes for the low bits
> (0x0004/0x0010/0x0020/0x0040): the `OBJ*` names under `FOR_EXEHDR` and the `NS*` names
> otherwise. The bit **values** above are those of the published LX specification and match the
> `FOR_EXEHDR` set. [DOC-IBM - `exe386.h` `#if FOR_EXEHDR` block]

### 2.6 Object Page Table (`struct o32_map`) [DOC-IBM]

Each entry is **8 bytes** and describes one logical page. The Object Page Table is parallel to
(and indexed by the same logical page number as) the Fixup Page Table. Logical pages are
numbered from 1.

| Off | Field | Size | Purpose |
|---|---|---|---|
| 0x00 | `o32_pagedataoffset` | 4 | page-data offset (shifted left by `e32_pageshift`); 0 for a zero-fill page |
| 0x04 | `o32_pagesize` | 2 | number of bytes of page data actually present in the file |
| 0x06 | `o32_pageflags` | 2 | per-page type flags |

Per-page flag values: [DOC-IBM]

| Symbol | Value | Meaning |
|---|---|---|
| `VALID` | 0x0000 | legal physical page (offset from the preload-page section) |
| `ITERDATA` | 0x0001 | iterated-data page (offset from the iterated-data section) |
| `INVALID` | 0x0002 | invalid page |
| `ZEROED` | 0x0003 | zero-filled page |
| `RANGE` | 0x0004 | range of pages |
| `ITERDATA2` | 0x0005 | iterated-data page, type II |

[DOC-IBM - `exe386.h` `struct o32_map` and `VALID`/`ITERDATA`/... defines; LX spec "Object Page
Table". `ITERDATA2` is present in the header but the base iteration record described in section 2.11 is
the `ITERDATA` form.]

### 2.7 Resource Table (`struct rsrc32`) [DOC-IBM]

Each entry is **14 bytes**; the count is `e32_rsrccnt`. Entries are sorted ascending by Name ID
within Type ID (enabling a binary search of the 32-bit table).

| Off | Field | Size | Purpose |
|---|---|---|---|
| 0x00 | `type` | 2 | resource type ID |
| 0x02 | `name` | 2 | resource name ID |
| 0x04 | `cb` | 4 | resource size (bytes) |
| 0x08 | `obj` | 2 | object number containing the resource |
| 0x0A | `offset` | 4 | offset of the resource within that object |

[DOC-IBM - `exe386.h` `struct rsrc32`; LX spec "Resource Table"]

### 2.8 Resident and Non-Resident Name Tables [DOC-IBM]

Both tables map exported entry-point **names -> ordinal numbers** (the ordinal indexes the Entry
Table). The first entry of the **Resident** Name Table is the module's own name (its ordinal
field is ignored). Resident names stay in memory while the module is loaded; non-resident names
are read from the file only when a link-by-name reference is resolved. Strings are **case
sensitive** and **not** null-terminated. Each entry:

```
+-----+------------------------+-----------+
| LEN |   ASCII STRING (LEN)   | ORDINAL # |   LEN: 1 byte, STRING: LEN bytes, ORDINAL: 2 bytes
+-----+------------------------+-----------+
```

`LEN` = string length (1..127); a `LEN` of 0 terminates the table. Bit 7 of `LEN` is an
"overload" bit reserved for parameter type-checking information. [DOC-IBM - LX spec "Resident or
Non-resident Name Table Entry"]

### 2.9 Entry Table - bundles [DOC-IBM]

The Entry Table resolves fixup references to entry points inside the module; an ordinal indexes
it, numbered from 1. Entries are grouped into **bundles**; all entries in a bundle share a size
and type. A bundle begins with a header (`struct b32_bundle`, **4 bytes**):

| Off | Field | Size | Purpose |
|---|---|---|---|
| 0x00 | `b32_cnt` | 1 | number of entries in the bundle (0 = end of the Entry Table) |
| 0x01 | `b32_type` | 1 | bundle type (below) |
| 0x02 | `b32_obj` | 2 | object number for the entries in this bundle |

Bundle types: [DOC-IBM]

| Symbol | Value | Meaning | Per-entry size |
|---|---|---|---|
| `EMPTY` | 0x00 | unused entries (skip `b32_cnt` ordinals; no per-entry data) | - |
| `ENTRY16` | 0x01 | 16-bit offset entry point | 3 (`FIXENT16`) |
| `GATE16` | 0x02 | 286 call gate (16-bit IOPL) | 5 (`GATEENT16`) |
| `ENTRY32` | 0x03 | 32-bit offset entry point | 5 (`FIXENT32`) |
| `ENTRYFWD` | 0x04 | forwarder entry point | 7 (`FWDENT`) |
| `TYPEINFO` | 0x80 | flag OR'd into type: parameter typing info present | - |

The per-entry variant follows the bundle header (`struct e32_entry`): each starts with a 1-byte
`e32_flags` (`E32EXPORT` 0x01 = exported; `E32SHARED` 0x02 = uses shared data; `E32PARAMS` 0xF8
= parameter word/dword count) then:
- **16-bit** (`ENTRY16`): 2-byte offset in object.
- **286 call gate** (`GATE16`): 2-byte offset + 2-byte call-gate selector (a reserved field the
  loader fills with an LDT call-gate selector for ring-2 references).
- **32-bit** (`ENTRY32`): 4-byte offset in object.
- **Forwarder** (`ENTRYFWD`): flag byte (`FWD_ORDINAL` 0x01 = import by ordinal) + 2-byte module
  ordinal (`e32_fwd.modord`, index into the Import Module Name Table) + 4-byte value
  (`e32_fwd.value` = target ordinal, or an offset into the target module's procedure-name table).
  A forwarder's value *is* an imported reference; the loader follows the chain (max 1024 deep;
  circular chains are a load error) to a non-forwarded entry point.

[DOC-IBM - `exe386.h` `struct b32_bundle`/`struct e32_entry`, bundle-type and `E32*`/`FWD_ORDINAL`
defines; LX spec "Entry Table"]

### 2.10 Fixups - Fixup Page Table and Fixup Record Table [DOC-IBM]

**Fixup Page Table.** Parallel to the Object Page Table, indexed by logical page number, with
**one extra** trailing entry. Each entry is a 4-byte offset, from the start of the Fixup Record
Table, to the first fixup record for that page; the extra final entry gives the offset just past
the last fixup record. A page's fixup records thus run from its own entry up to the next entry.
[DOC-IBM - LX spec "Fixup Page Table"]

**Fixup Record Table.** Variable-length records, grouped and sorted by logical page. Each record
(`struct r32_rlc`) begins with two bytes:

| Field | Purpose |
|---|---|
| `nr_stype` (SRC) | source type + modifier bits (below) |
| `nr_flags` (FLAGS) | target flags (below) |

**Source type** (`nr_stype`, mask `NRSRCMASK` = 0x0F): [DOC-IBM]

| Symbol | Value | Source |
|---|---|---|
| `NRSBYT` | 0x00 | byte (8-bit) |
| `NRSSEG` | 0x02 | 16-bit selector |
| `NRSPTR` | 0x03 | 16:16 pointer (32-bit) |
| `NRSOFF` | 0x05 | 16-bit offset |
| `NRPTR48` | 0x06 | 16:32 pointer (48-bit) |
| `NROFF32` | 0x07 | 32-bit offset |
| `NRSOFF32` | 0x08 | 32-bit self-relative offset |
| `NRALIAS` | 0x10 | fixup refers to the object's 16:16 alias (valid for src 2/3/6) |
| `NRCHAIN` | 0x20 | source-list flag: `SRCOFF` becomes a 1-byte count; a list of source offsets trails the record |

**Target flags** (`nr_flags`): [DOC-IBM]

| Symbol | Value | Meaning |
|---|---|---|
| `NRRTYP` | 0x03 | target-type mask |
| `NRRINT` | 0x00 | internal reference |
| `NRRORD` | 0x01 | imported reference by ordinal |
| `NRRNAM` | 0x02 | imported reference by name |
| `NRRENT` | 0x03 | internal reference via the Entry Table |
| `NRADD` | 0x04 | additive fixup - an additive value trails the record |
| `NR32BITOFF` | 0x10 | target offset is 32-bit (else 16-bit) |
| `NR32BITADD` | 0x20 | additive value is 32-bit (else 16-bit) |
| `NR16OBJMOD` | 0x40 | object number / module ordinal is 16-bit (else 8-bit) |
| `NR8BITORD` | 0x80 | import ordinal is 8-bit |

The remaining fields are **variable size**, selected by the flags. `struct r32_rlc` models the
maximal record: `r32_soff` (source offset, or count when `NRCHAIN`), `r32_objmod` (target
object number or module ordinal), then a `r32_target` union whose shape depends on the target
type:

- **Internal reference** (`NRRINT`): target object (1 or 2 bytes) + target offset (2 or 4 bytes;
  the offset is *absent* for a 16-bit-selector source).
- **Import by name** (`NRRNAM`): module ordinal (1/2 B) + procedure-name offset into the Import
  Procedure Name Table (2/4 B) + optional additive.
- **Import by ordinal** (`NRRORD`): module ordinal (1/2 B) + import ordinal (1/2/4 B) + optional
  additive.
- **Internal via entry table** (`NRRENT`): entry-table ordinal (1/2 B) + optional additive.

When `NRCHAIN` is set, a `SRCOFF1..SRCOFFn` list of 2-byte source offsets follows the record
(after any additive). Source offsets are relative to the start of the fixup's page; a fixup that
crosses a page boundary appears as a separate record on each page (the second uses a negative
offset). [DOC-IBM - `exe386.h` `struct r32_rlc` and `R32_*`/`NR*` defines; LX spec "Fixup Record
Table"]

### 2.11 Import Module / Import Procedure Name Tables [DOC-IBM]

Both are sequences of length-prefixed strings - 1-byte length (1..127) then that many ASCII
bytes, **case sensitive**, **not** null-terminated, **no** terminator record between them. The
Import **Module** Name Table names the modules referenced by imported fixups; a fixup's module
ordinal is a 1-based index into it. The Import **Procedure** Name Table holds procedure-name
strings that import-by-name fixups point into by byte offset. In the Import Procedure table, bit
7 of the length byte is the parameter-typing overload bit. [DOC-IBM - LX spec "Import Module Name
Table"/"Import Procedure Name Table"]

### 2.12 Iterated (compressed) pages [DOC-IBM]

An iterated-data page (per-page flag `ITERDATA`) is stored as a run of iteration records
(`struct LX_Iter`) that the loader expands to reconstitute the 4 KB page:

| Off | Field | Size | Purpose |
|---|---|---|---|
| 0x00 | `LX_nIter` | 2 | number of iterations (times the pattern repeats) |
| 0x02 | `LX_nBytes` | 2 | length of the data pattern (bytes; <= half the page size) |
| 0x04 | `LX_Iterdata` | `LX_nBytes` | the data pattern to replicate |

The next iteration record immediately follows the pattern; records fill out the page. Iterated
pages must lie in the same file section as regular data pages (`e32_itermap` is 0 or equal to
`e32_datapage`). [DOC-IBM - `exe386.h` `struct LX_Iter`; LX spec "Iterated Data Pages"]

### 2.13 Per-Page Checksum, Module Directives, Debug Info [DOC-IBM]

- **Per-Page Checksum Table** - one 4-byte cryptographic checksum per physical page, ordered by
  logical page. Present only if the checksum feature is used (else the header sums are 0).
- **Module Format Directives Table** - optional extension mechanism; each entry is directive
  number (2 B) + data length (2 B) + data offset (4 B). Directive numbers include `0x8001` Verify
  Record (resident), `0x0002` Language Information, `0x0003` Co-Processor Required Support, `0x0004`
  Thread State Initialization; bit 0x8000 marks resident directive data.
- **Debug Information** - format is defined by the debugger, not the loader; the LX header records
  only its offset and length. The first four bytes are a signature `"NB0"` + a type digit
  (0 = 32-bit CodeView, 1 = AIX, 2 = 16-bit CodeView, 4 = 32-bit OS/2 PM debugger).

[DOC-IBM - LX spec "Per-Page Checksum"/"Module Format Directives Table"/"Debug Information"]

### 2.14 Program and library entry register state [DOC-IBM]

At transfer to a program's `e32_eip`: CS = flat code selector; DS = ES = SS = flat data selector;
FS = TIB selector; GS = 0; EAX = EBX = ECX = EDX = ESI = EDI = EBP = 0; ESP = top of the stack
object. The stack holds `[ESP+0]` return address (into a routine that calls `DosExit(1,EAX)`),
`[ESP+4]` module handle, `[ESP+8]` reserved, `[ESP+12]` environment data-object address,
`[ESP+16]` command-line linear address. A library's initialization/termination entry receives
the same segment state with `[ESP+8]` = 0 (init) or 1 (term); a protected-memory library gets a
GDT selector (PROTDS) in DS/ES that addresses the full linear space. [DOC-IBM - LX spec "Program
(EXE) startup registers and Library entry registers"]

---

## 3. NE - New Executable (16-bit)

The New Executable format carries 16-bit segmented modules (programs, DLLs, drivers). A module
is a set of variable-size **segments**, each optionally carrying its own relocation records;
imports resolve through a module-reference table plus imported/entry name tables.

### 3.1 The NE header (`struct new_exe`) [DOC-IBM]

Byte-packed, **64 bytes**. Offsets are from the start of the NE header (the location `e_lfanew`
points to).

| Off | Field | Size | Purpose |
|---|---|---|---|
| 0x00 | `ne_magic` | 2 | signature `"NE"` (`NEMAGIC` = 0x454E) |
| 0x02 | `ne_ver` | 1 | linker version |
| 0x03 | `ne_rev` | 1 | linker revision |
| 0x04 | `ne_enttab` | 2 | Entry Table offset (from the NE header) |
| 0x06 | `ne_cbenttab` | 2 | Entry Table size (bytes) |
| 0x08 | `ne_crc` | 4 | 32-bit CRC of the whole file |
| 0x0C | `ne_flags` | 2 | module flags (section 3.2) |
| 0x0E | `ne_autodata` | 2 | automatic data segment number |
| 0x10 | `ne_heap` | 2 | initial local heap size |
| 0x12 | `ne_stack` | 2 | initial stack size |
| 0x14 | `ne_csip` | 4 | initial CS:IP (segment:offset) |
| 0x18 | `ne_sssp` | 4 | initial SS:SP |
| 0x1C | `ne_cseg` | 2 | number of segment-table entries |
| 0x1E | `ne_cmod` | 2 | number of Module Reference Table entries |
| 0x20 | `ne_cbnrestab` | 2 | Non-Resident Name Table size (bytes) |
| 0x22 | `ne_segtab` | 2 | Segment Table offset |
| 0x24 | `ne_rsrctab` | 2 | Resource Table offset |
| 0x26 | `ne_restab` | 2 | Resident Name Table offset |
| 0x28 | `ne_modtab` | 2 | Module Reference Table offset |
| 0x2A | `ne_imptab` | 2 | Imported Names Table offset |
| 0x2C | `ne_nrestab` | 4 | Non-Resident Name Table offset (file-relative) |
| 0x30 | `ne_cmovent` | 2 | number of movable entries in the Entry Table |
| 0x32 | `ne_align` | 2 | segment/resource alignment shift count (log2 of the sector size) |
| 0x34 | `ne_cres` | 2 | number of resource entries |
| 0x36 | `ne_exetyp` | 1 | target OS (`NE_OS2` = 1, `NE_WINDOWS` = 2, ...) |
| 0x37 | `ne_flagsothers` | 1 | additional flags (below) |
| 0x38 | `ne_pretthunks` / `ne_modver` | 2 / 4 | (Windows: return-thunk offset) / (OS/2: module version, `NE_MODVER`) |
| 0x3A | `ne_psegrefbytes` | 2 | (Windows) segment-reference-bytes offset |
| 0x3C | `ne_swaparea` | 2 | (Windows) minimum code-swap-area size |
| 0x3E | `ne_expver` | 2 | (Windows) expected Windows version |

[DOC-IBM - `newexe.h` `struct new_exe` with in-source offset annotations]. Tail bytes 0x38..0x3F
are a union: for OS/2 modules the `Mod1` arm (`ne_modver` + reserved) applies; for Windows
modules the `Win3` arm applies. All table offsets except `ne_nrestab` are relative to the NE
header; `ne_nrestab` is file-relative. [DOC-IBM - `newexe.h` `union choice`]

`ne_flagsothers` bits: `NELONGNAMES` 0x01 (long-filename support), `NEWINISPROT` 0x02,
`NEWINGETPROPFON` 0x04, `NEWLOAPPL` 0x80 (WLO application). [DOC-IBM - `newexe.h`]

### 3.2 NE module flags (`ne_flags`) [DOC-IBM]

| Symbol | Value | Meaning |
|---|---|---|
| `NESOLO` | 0x0001 | solo data (shared single data segment) |
| `NEINST` | 0x0002 | instance data (per-process data segment) |
| `NEPPLI` | 0x0004 | per-process library initialization |
| `NEPROT` | 0x0008 | runs in protected mode only |
| `NEI086` | 0x0010 | 8086 instructions |
| `NEI286` | 0x0020 | 286 instructions |
| `NEI386` | 0x0040 | 386 instructions |
| `NEFLTP` | 0x0080 | floating-point instructions |
| `NENOTWINCOMPAT` | 0x0100 | incompatible with PM windowing |
| `NEWINCOMPAT` | 0x0200 | compatible with PM windowing |
| `NEWINAPI` | 0x0300 | uses the PM windowing API |
| `NEAPPTYP` | 0x0700 | application-type mask |
| `NEBOUND` | 0x0800 | bound family/API |
| `NEIERR` | 0x2000 | errors in the image |
| `NENOTMPSAFE` | 0x4000 | not multiprocessor-safe |
| `NENOTP` | 0x8000 | library module (not an `.EXE`) |

[DOC-IBM - `newexe.h` `NE*` flag defines]

### 3.3 Segment Table (`struct new_seg`) [DOC-IBM]

`ne_cseg` entries, each **8 bytes**:

| Off | Field | Size | Purpose |
|---|---|---|---|
| 0x00 | `ns_sector` | 2 | file offset of the segment data, in alignment sectors (`<< ne_align`); 0 = no file data |
| 0x02 | `ns_cbseg` | 2 | length of the segment in the file (bytes); 0 means 64 KB |
| 0x04 | `ns_flags` | 2 | segment attribute flags (below) |
| 0x06 | `ns_minalloc` | 2 | minimum runtime allocation (bytes); 0 means 64 KB |

Segment flags (`ns_flags`): [DOC-IBM]

| Symbol | Value | Meaning |
|---|---|---|
| `NSTYPE` | 0x0007 | segment-type mask |
| `NSCODE` | 0x0000 | code segment |
| `NSDATA` | 0x0001 | data segment |
| `NSITER` | 0x0008 | iterated segment |
| `NSMOVE` | 0x0010 | movable segment |
| `NSSHARED` / `NSPURE` | 0x0020 | shareable (pure) segment |
| `NSPRELOAD` | 0x0040 | preload segment |
| `NSEXRD` | 0x0080 | execute-only (code) / read-only (data) |
| `NSRELOC` | 0x0100 | segment has relocation records |
| `NSCONFORM` / `NSEXPDOWN` | 0x0200 | conforming code / expand-down data |
| `NSDPL` | 0x0C00 | I/O privilege level (286 DPL bits; shift `SHIFTDPL` = 10) |
| `NSDISCARD` | 0x1000 | discardable segment |
| `NS32BIT` | 0x2000 | 32-bit code segment |
| `NSHUGE` | 0x4000 | huge segment (length/min-alloc are in sector units) |
| `NSGDT` | 0x8000 | GDT allocation requested |

[DOC-IBM - `newexe.h` `struct new_seg`, `NS*` defines]

### 3.4 Per-segment relocation records (`struct new_rlc`) [DOC-IBM / DOC]

If a segment's `NSRELOC` flag is set, its file data is immediately followed by a 2-byte count
(`struct new_rlcinfo` `nr_nreloc`) and that many **8-byte** relocation records (`struct
new_rlc`):

| Off | Field | Size | Purpose |
|---|---|---|---|
| 0x00 | `nr_stype` | 1 | source type (below) |
| 0x01 | `nr_flags` | 1 | flags / target type (below) |
| 0x02 | `nr_soff` | 2 | source offset within the segment (head of the source chain) |
| 0x04 | union (4 bytes) | 4 | target data, selected by `nr_flags` |

Source type (`nr_stype`, mask `NRSTYP` = 0x0F): `NRSBYT` 0x00 (low byte), `NRSSEG` 0x02 (16-bit
segment/selector), `NRSPTR` 0x03 (16:16 pointer), `NRSOFF` 0x05 (16-bit offset), `NRPTR48` 0x06
(16:32 pointer), `NROFF32` 0x07 (32-bit offset), `NRSOFF32` 0x08 (32-bit self-relative). Flags
(`nr_flags`): reference-type mask `NRRTYP` 0x03 with `NRRINT` 0x00 (internal reference), `NRRORD`
0x01 (import by ordinal), `NRRNAM` 0x02 (import by name), `NRROSF` 0x03 (operating-system fixup);
`NRADD` 0x04 (additive); `NRICHAIN` 0x08 (internal chaining). [DOC-IBM - `newexe.h` `struct
new_rlc`, `NR*` defines]

The 4-byte target union depends on the reference type: [DOC]

- **Internal reference** (`nr_intref`): 1-byte segment number (0xFF = a movable segment), 1-byte
  reserved, then 2 bytes = offset in a fixed segment, or an Entry-Table ordinal for a movable
  segment.
- **Import** (`nr_import`): 2-byte module index (into the Module Reference Table) + 2-byte
  procedure ordinal or imported-name-table offset.
- **OS fixup** (`nr_osfix`): 2-byte OSFIXUP type + 2-byte reserved.

When `NRADD` is clear, the source field holds an 0xFFFF-terminated chain of source offsets within
the segment, each pointing at the next reference to the same target; when set, the target value
is *added* to the source contents instead. [DOC - NE format description "PER SEGMENT DATA";
cross-checked to `newexe.h`]

### 3.5 Entry Table (bundles) [DOC]

The NE Entry Table is a series of bundles, accessed by ordinal (from 1). Each bundle begins with:
a 1-byte **count** (0 terminates the table) and a 1-byte **segment indicator**:

- **0x00** - unused bundle: skip `count` ordinals; no per-entry data follows.
- **0x01-0xFE** - fixed-segment bundle; the indicator *is* the segment number. Each entry is
  **3 bytes**: 1-byte flag (0x01 exported, 0x02 uses global/shared data) + 2-byte offset within
  the segment.
- **0xFF** - movable-segment bundle. Each entry is **6 bytes**: 1-byte flag (0x01 exported, 0x02
  shared data) + the two bytes `INT 3Fh` + 1-byte segment number + 2-byte offset within the
  segment.

[DOC - NE format description "ENTRY TABLE"; the movable count is `ne_cmovent`, `newexe.h`]

### 3.6 Resident / Non-Resident Name Tables, Module Reference, Imported Names [DOC]

- **Resident Name Table** - length-prefixed strings, each followed by a 2-byte ordinal (an index
  into the Entry Table). The first string is the module's own name (its ordinal is ignored). A
  zero length byte ends the table. Strings are case sensitive and not null-terminated.
- **Non-Resident Name Table** - same string+ordinal format; its first string is the module
  description; located by `ne_nrestab`/`ne_cbnrestab`.
- **Module Reference Table** - `ne_cmod` entries, each a 2-byte offset into the Imported Names
  Table naming a referenced module. Import relocation records index this table.
- **Imported Names Table** - length-prefixed strings (1-byte length + ASCII, case sensitive, not
  null-terminated) for module and procedure names referenced by imports.

[DOC - NE format description "RESIDENT-NAME TABLE"/"MODULE-REFERENCE TABLE"/"IMPORTED-NAME TABLE";
offsets/counts from `newexe.h`]

---

## 4. LX vs NE at a glance [DOC-IBM]

| Aspect | LX (32-bit) | NE (16-bit) |
|---|---|---|
| New-header magic | `"LX"` (0x584C) | `"NE"` (0x454E) |
| Unit of memory | **object** (flat, page-mapped, up to 4 GB) | **segment** (16-bit, <= 64 KB) |
| Header size | 196 bytes (`struct e32_exe`) | 64 bytes (`struct new_exe`) |
| Page/segment table | Object Table + Object Page Table (per-page) | Segment Table (per-segment) |
| Relocations | Fixup Page Table + Fixup Record Table (per logical page) | per-segment relocation records following segment data |
| Fixup targets | internal / import-by-ordinal / import-by-name / internal-via-entry, + additive | internal / import-by-ordinal / import-by-name / OS-fixup, + additive |
| Names -> ordinal | Resident + Non-Resident Name Tables | Resident + Non-Resident Name Tables |
| Imports named via | Import Module + Import Procedure Name Tables | Module Reference + Imported Names Tables |
| Entry table | bundles: 16-bit / 286-gate / 32-bit / forwarder | bundles: fixed-segment / movable-segment |
| Compression | iterated data pages (`LX_Iter`) | iterated segments (`NSITER`) |
| Forwarders | yes (bundle type 4) | no |

---

## Sources

- **[DOC-IBM]** IBM OS/2 Toolkit header `exe386.h` (`@(#)exe386.h 6.10 92/01/09`) - LX C
  structures, field names, and manifest constants (`E32*`, `O32*`, `OBJ*`, `NR*`, `R32*`,
  bundle types, `LX_Iter`).
- **[DOC-IBM]** IBM OS/2 Toolkit header `newexe.h` (`@(#)newexe.h 6.3 92/03/15`) - DOS-stub, NE
  C structures, field names, and constants (`NE*`, `NS*`, `NR*`).
- **[DOC-IBM]** IBM, *LX - Linear eXecutable Module Format Description* (June 3, 1992) - LX file
  layout, header-field semantics, object/page/entry/fixup grammar, iterated-data and register
  entry state.
- **[DOC]** *New Executable* format description (community transcription of the NE/segmented
  `.EXE` specification) - NE entry-table bundles, per-segment relocation target grammar, name
  and module-reference tables; cross-checked against `newexe.h`.

## See also
- `module-dll.md` - how these modules are loaded at run time (`DosLoadModule`, imports, forwarders); `thunking.md` - the 16<->32 boundary the object/segment bits describe.
