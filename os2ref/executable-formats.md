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

**Where an EXE's stack comes from, and what happens with none** [OBS: WSeB 4.50 revision 14.089,
2026-09-30; a one-segment 32-bit object whose entry is a `ret` and which has no `STACK`-class segment,
linked by VisualAge C++ 3's `ILINK`, then run; and a survey of the 623 LX EXEs of an installed system]:
- The stack is an object of the module: `e32_stackobj`/`e32_esp` name the object and the initial ESP
  inside it. Every one of the 623 installed EXEs has one. The linker builds it from a `STACK`-class
  segment (a compiler's C startup code supplies one) or from the `.DEF`'s `STACKSIZE`, which it places
  in the automatic data object.
- `e32_stacksize` is not what the loader goes by: 32 of the 623 carry 0 there and still have a stack
  object (the survey read headers; none of the 32 was run). The commonest stack sizes are 32 KB (193
  EXEs) and 64 KB (75).
- With no `STACKSIZE` and no stack segment, `ILINK` warns `LNK4021: no stack segment` and still writes
  the EXE, with `e32_stackobj` = 0 and `e32_stacksize` = 0. `STACKSIZE` given with no automatic data
  segment draws `LNK4049: ignoring non-zero stack size` and the same header.
- **The loader refuses such an EXE**: running it gives `SYS0189` - `ERROR_INVALID_STACKSEG` (189,
  `bseerr.h`). Neither the linker nor the loader supplies a default stack.

**What `DosExecPgm` returns for a module it cannot run** [OBS: WSeB 4.50 revision 14.089, 2026-09-30;
a 32-bit LX program calling `DosExecPgm(EXEC_SYNC)` on each file below, the load-failure object name
buffer read back]. `bseerr.h` names each code; `DosExecPgm`'s documented return list includes 190,
191 and 192 but not 193, which it returns all the same:

| the file | rc | the object buffer |
|---|---|---|
| a DLL (`DOSCALL1.DLL`) | 190 `ERROR_INVALID_MODULETYPE` | the file's name |
| an EXE with module flag 0x2000 (not loadable) set | 192 `ERROR_EXE_MARKED_INVALID` | the file's name |
| a text file named `.EXE` | 191 `ERROR_INVALID_EXE_SIGNATURE` | the file's name |
| an `MZ` header whose new-header offset is 0 | 191 | the file's name |
| an LX EXE with `e32_border` = 1 (big-endian) | 191 | the file's name |
| an LX EXE cut off just past the header's first 0x30 bytes | 193 `ERROR_BAD_EXE_FORMAT` | the file's name |
| an LX EXE whose object table offset points past the file | 193 | the file's name |
| an LX EXE with `e32_cpu` = 0x40 (no such CPU) | 0 - it runs normally | empty |
| an LX EXE cut to half its length (headers whole, pages missing) | 0 - it loads; the process ends with `codeTerminate` 1 and `codeResult` 14 | empty |

The loader reads the header and the tables at load time and pages the rest in on demand, so a body
cut short is not seen until a missing page is touched, and then as the program's fault.

### 2.3 Module flags (`e32_mflags`) [DOC-IBM]

| Symbol | Value | Meaning |
|---|---|---|
| `E32LIBINIT` | 0x00000004 | per-process library initialization (else global) |
| `E32SYSDLL` | 0x00000008 | system DLL - **internal fixups discarded** (spec lists 0x08 as "reserved for system use") |
| `E32NOINTFIX` | 0x00000010 | internal fixups have been **applied**; the records are **retained** in the file |
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

> **CORRECTED - an earlier revision of this section was wrong.** It claimed
> *"`E32NOINTFIX` decides whether a module can be relocated ... the module can only be
> loaded *there*"*, and called a preferred address a **hard requirement** for such a
> module. That is not what the flag means and not what OS/2 does. The wrong claim is
> kept here because it is a natural misreading - the symbol name reads as "no internal
> fixups", which suggests the records are gone - and because the correction below is
> the useful part.

**`E32NOINTFIX` marks a preferred address, not an immovable one.** `[DOC-IBM]` The LX
specification is explicit that the fixup records survive:

> `00000010h` = Internal fixups for the module have been applied. The setting of this
> bit in a Linear Executable Module indicates that each object of the module has a
> **preferred** load address specified in the Object Table Reloc Base Addr. **If the
> module's objects can not be loaded at these preferred addresses, then the relocation
> records that have been retained in the file data will be applied.**

So the flag is a preference plus an optimization: a loader that honours every preferred
address may skip the internal fixups entirely, and one that cannot must apply the
retained records - the module relocates either way. section 2.12 states the same thing from
the other side, explaining that fixups are sorted so external and internal
selector/pointer records precede internal non-selector records *"to allow the loader to
ignore internal fixups if the loader is able to load all objects at the addresses
specified in the object table."*

**The genuinely immovable case is a different bit.** `E32SYSDLL` (0x08) is defined as
*"System DLL, Internal Fixups discarded"* - with the records gone there is nothing left
to apply. This is the condition the Object Table's own wording refers to (section 2.4): the
Reloc Base Addr is *"the address the object is currently relocated to"*, and only *"if
the internal relocation fixups for the module have been removed"* is it *"the address
the object will be allocated at by the loader"*. For any other module the field is
**informational** - a record of how the linker last laid the module out.

> **Provenance corrected 2026-08-31 (Rule 1.7), third pass.** 2 claims here
> were tagged `[OBS-RE]` and are now `[OBS]`. **No claim changed.** The
> discriminator is the METHOD, not the subject: `[OBS-RE]` names RE of a binary
> or the kernel debugger; `[OBS]` names a program run on real OS/2 whose result
> was recorded. Both rest on ring-3 probes run on the machine, one of which
> retains its capture. A ring-3 probe that *reads memory* is still a capture -
> you re-verify it by running the probe again, not by reading bytes - and that
> edge is what made these look like `[OBS-RE]`. Found on review: the earlier sweeps' keyword list did not match "observed on" or
> "on a live", so these sat outside a bound that claimed to cover them.

**What OS/2 actually does with the two cases** `[OBS]` - observed on OS/2 Warp 4.50
by comparing every loaded module's live object addresses (via `DosQuerySysState`
`QS_MTE`, and `DosQueryProcAddr` anchored on known exports) against the object table in
the corresponding file on disk:

- **A preferred address is honoured only for an `E32NOINTFIX` module.** Every one of 13
  such objects kept its base. **Not one** relocatable DLL object was placed at its
  preferred shared-arena base - they were allocated from the arena instead, even where
  the preferred range was free. (The only relocatable objects found at their preferred
  addresses were `.EXE` objects in the private arena, where nothing contends.)
- **An already-loaded module is never displaced.** Loading further fixed-address modules
  onto an occupied base moved nothing; the newcomer relocates.
- **An address collision is never a load failure.** A fixed-address module whose
  preferred base was occupied loaded successfully and was relocated, its retained
  records applied - exactly as section 2.2 describes.
- **Objects are placed independently.** One module's first object moved by 0x2AD0000
  while another of its objects landed somewhere unrelated; there is no single
  per-module delta.

The practical consequence for a loader is the opposite of the retracted claim above:
because relocatable modules never compete for a preferred base, a fixed-address module
reliably gets its own without any reservation machinery - and when it cannot, it
relocates like anything else.

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

**A bundle type of `GATE16` is overridden by the target object's Big/Default flag.**
`[OBS-RE]` Shipped OS/2 DLLs contain entries whose bundle declares a 286 call gate while
the target object is a 32-bit (Big) object - 16 such entries across the DLLs under
`\OS2`, in `VIDEOCFG.DLL` and `COMETDLL.DLL`. OS/2 resolves these as ordinary flat 32-bit
entries and does not build a call gate: five such entries in one module, all into the same
Big object, each resolved to *object base + the entry's offset* and so all implied the
same object base - which could not hold if a gate had been interposed. A loader that
trusts the declared bundle type over the object's Big flag will build a 16-bit thunk where
OS/2 builds none.

The mirror case exists too and its handling is **not established**: 5 entries in the same
corpus declare `ENTRY32` against a non-Big object.

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

**The loader does not validate a target offset against the target object's size, and does
not reinterpret one.** `[OBS]` Two things follow, both observed on OS/2 Warp 4.50 by
reading the resolved dword in a loaded module's memory and comparing it against the
candidate values:

- **An offset past the object's virtual size is applied as-is.** A shipped PM DLL contains
  an internal fixup targeting an object at `+0x432FC` where that object's virtual size is
  only `0xFFDC`; the corresponding memory holds exactly *target base + 0x432FC*. Treating
  such a record as corrupt and skipping it silently leaves stale data at the source.
- **A target offset with the high bit set is not a signed offset from the end of the
  object.** A record with `trgoff = 0xFFFF36E0` against an object of size `0x23EE0`
  resolved to *target base + 0xFFFF36E0* (i.e. base - 0x0C920), not to
  *base + size - 0x0C920*. Nine such records exist across the shipped DLLs.

A bulk appearance of out-of-range target offsets is, however, the characteristic signature
of a **desynchronised fixup-record stream** - the records are variable-length with no
length field and no re-anchoring, so one mis-sized field corrupts every later record on
the page. Isolated occurrences are genuine data; a page full of them means the parse is
wrong.

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

`NELONGNAMES` is the bit the linker sets for the module-definition statement `NEWFILES`. It is
meaningful on program modules, not on DLLs (a DLL runs under its caller's bit), and it decides
whether the process may pass non-8.3 names to the thirteen file-system functions IBM lists and
see them from `DosFindFirst`/`DosFindNext` - the rule, the function list and the measured
consequence are in `file-io.md` section 11. No LX-header equivalent is documented, and a 32-bit LX
program is **not** subject to the long-name filter at all - measured [OBS]: it creates and queries
non-8.3 names exactly like 8.3 ones, i.e. it behaves as if `NEWFILES` were always set. The filter
is therefore a property of the 16-bit NE program model, not something an LX module carries or an LX
process is subject to (see `file-io.md` section 11 for the measurement). [DOC-IBM - `cpgref` "Long File
Names"; the 32-bit measurement is `[OBS]`, Warp 4.50]

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

## 3.7 Absolute-value (`:ABS`) exports and how a fixup consumes one [DOC-IBM / OBS-RE / OBS]

Not every export is a code or data *address*. Some are **absolute values** - a
constant an importer wants at a fixup site, not a callable entry point. In
DOSCALLS these include `DOSHUGESHIFT` (135) / `DOSHUGEINCR` (136), the
huge-segment shift and increment (`memory-api.md`), `_DosFlatCS` (369) /
`_DosFlatDS` (370), the flat code/data selector values, and `DOSIODELAYCNT`
(427), the boot-computed I/O-delay loop count.

- **How they are declared and referenced.** IBM's assembler declares the import
  `EXTRN <name>:ABS` (or `EXTERNDEF <name> :ABS`) and reads it at a **value
  site** - an immediate/offset, never a call: `mov ax, OFFSET DOSHUGEINCR`, or
  `db 0B8h ; dw DOSIODELAYCNT` (`mov ax, imm16`). [DOC-IBM, DDK
  `.../base/inc/iodelay.inc:201` `EXTRN DOSIODELAYCNT:ABS`,
  `.../dev/parallel/par1284/parmisc.c` `mov ax, OFFSET DOSIODELAYCNT`,
  `.../mme/wpddlib/iodelay.asm`, and `.../video/.../vga32/vgainc/extern.inc:486`
  `EXTERNDEF DOSHUGEINCR :ABS`.] The linker emits an ordinary
  import-by-ordinal fixup whose SOURCE type is a **value** type - `OFFSET16`
  (NE `0x05` / LX `0x05`), `LOBYTE` (`0x00`), or a 16-bit `SEGMENT` fixup
  (`0x02`); the DDK `.DEF` binds the name, e.g. `IMPORTS _DOSIODELAYCNT =
  DOSCALLS.427`.
- **How the loader resolves the ordinal to a value.** The DOSCALLS exporter is
  the kernel's own entry table, not a normal module. A record there is *tagged*:
  **tag 1 = "direct 16-bit value, selector 0"** and **tag 4 = "direct value via
  an indirect table"**. Both resolve to a 16:16 pair of **`(selector = 0, offset
  = value)`** - the value lands in the *offset* half. [OBS-RE,
  `_ldrGetEntAddr` scheme C, `case 1: off = value; sel = 0;` / `case 4: off =
  TBL[idx]; sel = 0;`, from the held kernel decompiles; the DOSCALLS export
  table `dcm_entrytblstart` carries e.g. `01 03 00` at ordinal 135 = tag 1,
  value 0x0003.]
- **How the importer's fixup then writes it, per source type.** The fixup
  applier takes the slice its source type names from that `(sel=0, off=value)`
  pair.
  - **`OFFSET16` writes the offset half - the value.** `[OBS]` measured on
    OS/2 Warp Server for e-business (kernel 14.089_UNI): a 16-bit NE program
    importing `DOSCALLS.136` through an `OFFSET16` fixup receives **8**.
  - **A 16-bit `SEGMENT` fixup writes the selector half - 0.** `[OBS]` same
    machine, same program, an added `SEG` reference to the same ordinal
    receives **0**. This half is worth measuring rather than assuming: it is
    not obvious that a constant referenced "as a segment" yields zero rather
    than the constant, and binaries that do it exist - so a loader that writes
    the *value* into a `SEGMENT` slot is diverging.
  - **`LOBYTE` is NOT established.** The rule predicts the low byte of the
    value, but the measurement could not be taken: a 16-bit NE program with a
    `LOBYTE` fixup against an absolute export **dies on the same machine**
    (`Bus error`), reproducibly, while the identical program without that one
    reference runs to completion. Whether that is a loader limitation on
    `LOBYTE`-against-imported-ordinal or a property of the particular
    instruction encoding is **not distinguished by anything measured**, so no
    `LOBYTE` behaviour is asserted here. Binaries using this shape do exist.
- **Selector-valued exports are the reason the general far-pointer case is not
  trivial.** `_DosFlatCS`/`_DosFlatDS` are absolute *selectors*: their value
  belongs in the *selector* position when a program builds a segment reference
  from them. Whether a **16:16 far-pointer (`PTR1616`, source `0x03`)** fixup to
  such an export should place the value in the selector half (with the offset
  from the fixup's additive) is not settled by the value/offset rule above and
  is release/toolchain-specific; treat a `PTR1616` reference to an absolute
  export as a case to verify, not to assume.

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

## 5. How the system classifies an executable: `DosQueryAppType` [DOC-IBM / OBS-RE / OBS]

**The API, [DOC-IBM]:** `DosQueryAppType(PSZ pszName, PULONG pFlags)` (32-bit, DOSCALLS 323)
and `DosQAppType(PSZ, PUSHORT)` (16-bit, DOSCALLS 163; the DDK's 16-bit `bsedos16.h` gives the
output as a USHORT). Flags are the `FAPPTYP_*` set in `bsedos.h`, including `WINDOWSREAL`
0x200, `WINDOWSPROT` 0x400 and `WINDOWSPROT31` 0x1000, which the Control Program reference's
page does not list.

**Structure, [OBS-RE]:** one API over two binaries.
- The 32-bit entry in DOSCALL1 unithunks into the 16-bit #163, also in DOSCALL1, which applies
  the page's name rules.
- #163 then calls DOSCALLS 202 (`DosIQAppType`, the kernel's `DOSIQAPPTYPE` ->
  `_LDRQAppType`), which opens the name exactly as given.

**#163's name rules, [OBS-RE]:**
- A name longer than 0x103 characters -> 123.
- A name that is empty, has `:` as its second character, or contains any `/` or `\` is used as
  is. In a DBCS environment a lead byte skips the byte after it.
- Otherwise `DosSearchPath(3, "PATH", ...)`: current directory first, then the `PATH` variable.
- On rc 2 or 191 for a name with no extension (no `.` after the last separator), `.EXE` is
  appended and the lookup repeats.
- On 191 for an extension of `COM` in any case -> rc 0, flags 0x20.

**The kernel's classification, [OBS-RE]:**
- **Reads:** 0x40 bytes at offset 0. `LX`/`NE` means the new header is here; `MZ` (0x5A4D) or 0x5A4F
  means it is at `e_lfanew`. Anything else is not an executable.
- **Not an executable:** 0x20 if the name ends in exactly `.COM` or `.com`, else 191. A file
  shorter than 0x40 bytes fails the first read instead: 193, or still 0x20 when its name ends in
  exactly `.COM`/`.com` (the kernel marks it "not an executable" before that read).
- **After an `MZ`:** `LE` -> 191; `PE` -> 0x5000 (0x5010 when the COFF characteristics have
  `IMAGE_FILE_DLL`); any other or unreadable new header -> 0x20 (DOS).
- **LX/NE errors:** an LX with a non-zero byte or word order or level, or an OS field other than
  1, -> 191. Module flag 0x2000 (not loadable) -> 192. An unknown module-type field -> 193.
- **Base flags:** module-flags bits 8-11 -> `FAPPTYP` bits 0-3 (type and `BOUND`). An NE
  header is first rewritten into the LX shape, and there `ne_flags` keeps only 0xAB07.
- **Windows NEs** (target OS 2 or 4): a WLO program -> type 3. It is WLO if the other-flags byte
  (NE+0x37) has bit 7, or a module reference names `DOSCALLS`, `KERNEL_B`, `PMWIN`, `GDI_B` or
  `USER_B`. Otherwise, from the expected Windows version (NE+0x3E minor, +0x3F major):
  - 3.10 -> 0x1000;
  - 3.0, or NE+0x37 bit 1 or 2 -> 0x400;
  - below 3 -> 0x200;
  - anything else -> 0x1000.

  No `DLL` bit is added.
- **Otherwise:**
  - a library -> `DLL`;
  - an LX PDD -> `DLL|PHYSDRV`;
  - an LX VDD -> `DLL|VIRTDRV`;
  - a protected-memory library -> `DLL` (**`PROTDLL` is never returned**);
  - any LX -> `32BIT`.

  **The type bits are kept for a DLL**, although the page says they are zeroed.
- **Cache:** one (time, name-hash, flags) entry for the whole system, filled only by a
  successful query. It answers without opening the file while `SIS_BigTime` is below the fill
  time + 4. The hash sums each byte rotated left by 4,*i* mod 32, over the string the kernel
  received. So it is case-sensitive, and names differing by a swap of characters *i* and *i*+8
  collide.

**What reaches the caller's output, [OBS-RE] then [OBS]:**
- **The kernel classifies into its worker's own local** and returns it only on success.
- **#202's worker stores a WORD on every return**, and it is 0 when the call failed.
- **#163** writes the caller's word only through #202 and on its `.COM` path, so a failed `PATH`
  search leaves the word as it was.
- **The 32-bit entry** leaves #163's word in the low half and **always clears the high half**:
  on success, on failure, and for a NULL name (rc 87).
- **NULL pointers:** the 32-bit entry answers 87 for a NULL name or a NULL output. The 16-bit
  #202 with a NULL output and #163 with a NULL name **trap**: neither tests the pointer.
- **An empty name** through the 32-bit entry answers 2, leaving 0 in the output.

**Measured, [OBS]:** WSeB 4.52 (Convenience Pak 2), 2026-09-30, through all three entries.
- **Type bits kept:** an NE library of type 2 (`OS2\BOOT\TIMER0.SYS`) -> 0x0012.
- **Drivers:** `OS2\SESDD32.SYS` -> 0x4050, `MMOS2\VAUDIO.SYS` -> 0x4090.
- **Windows NEs:** the TCP/IP kit's `WPING.EXE` -> 0x0400, `WINSOCK.DLL` -> 0x1000.
- **Header forms:** a written PE -> 0x5000, LE -> 191. A bound-flagged NE header at offset 0 ->
  0x000A, a not-loadable LX header -> 192.
- **Name rules:** `ATTRIB` and `ATTRIB.EXE` from elsewhere -> 0x0002 through #323, and 2 through
  #202. A 64-byte text file named `.Com` -> 191 through #202 and 0x20 through #163. A directory
  -> 5. `NOSUCHDIR\ATTRIB.EXE` (relative) -> 3. NULL `pFlags` or `pszName` through #323 -> 87.
- **Cache:** within 4 s, a replaced file, a deleted file, a colliding name and a child process
  all get the cached answer. A lower-case spelling misses, a failed query is not cached, and
  the entry expires after 5 s.

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
- **[DOC-IBM]** IBM OS/2 Toolkit `bsedos.h` (`FAPPTYP_*`); the DDK's 16-bit `bsedos16.h` (`DosQAppType`);
  Control Program Guide and Reference, "DosQueryAppType".
- **[OBS-RE]** section 5: the SMP kernel's `_LDRQAppType`, `_ldrOpenNewExe`, `_ldrOpenPath`,
  `_ldrMungeFlags`, `_ldrExpandHeader` (with the `_mptbl` word table), `_ldrCheckForWLO`
  (with `_ldrWLOTbl`) and `_ldrHashQATName`; DOSCALL1's #323 thunk and #163 body read at their
  entry-table addresses, with imports resolved from the fixup table.
- **[DOC]** *New Executable* format description (community transcription of the NE/segmented
  `.EXE` specification) - NE entry-table bundles, per-segment relocation target grammar, name
  and module-reference tables; cross-checked against `newexe.h`.

## See also
- `module-dll.md` - how these modules are loaded at run time (`DosLoadModule`, imports, forwarders); `thunking.md` - the 16<->32 boundary the object/segment bits describe.
