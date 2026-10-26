# OS/2 Memory Management API (Control Program)

The application-level Control Program interface for allocating, protecting, and sharing
memory: the `Dos*Mem` family. These calls operate on the virtual address space and arenas
described in `memory-model.md` - this reference documents the *API surface* (functions,
flags, sharing models, and the committed-vs-reserved distinction), and defers the arena and
selector internals to that document. All memory is page-granular: `DosAllocMem` and its
relatives round sizes and addresses to the page, and OS/2 tracks memory in whole-page units.

Provenance: **[DOC-IBM]** OS/2 Toolkit 4.5 headers `bsedos.h` (prototypes) and `bsememf.h`
(all `PAG_*`, `OBJ_*`, `DOSSUB_*`, and `fXXX` flag constants), `bseerr.h` (error codes);
**[DOC]** the x86 4 KB page granularity and general semantics cross-checked against published
OS/2 references. Every prototype, flag value, and error number below is transcribed from those
headers.

## The committed / reserved / decommitted model [DOC]

OS/2 separates **reserving** address space from **committing** backing storage:

- **Reserved** - a range of the virtual address space is set aside for an object, but no
  physical/swap storage backs it. Touching a reserved-but-uncommitted page faults.
- **Committed** - storage is guaranteed for the page; it may be read/written subject to its
  access protection.
- **Decommitted** - a previously committed page whose storage has been released, while the
  address range remains reserved (it can be re-committed later).

`DosAllocMem` reserves the whole object and, if `PAG_COMMIT` is passed, commits it in the same
call; otherwise the object is reserved uncommitted and the caller commits ranges on demand with
`DosSetMem`. This lets a program reserve a large contiguous region cheaply and pay for storage
only as it is used.

## Access protection flags - `PAG_*` [DOC-IBM `bsememf.h`]

Every committed page carries an access-protection attribute. These flags appear in
`DosAllocMem`, `DosSetMem`, the `DosGet*/DosGive*` sharing calls, and are returned by
`DosQueryMem`.

| Flag | Value | Meaning |
|---|---|---|
| `PAG_READ` | `0x00000001` | read access |
| `PAG_WRITE` | `0x00000002` | write access |
| `PAG_EXECUTE` | `0x00000004` | execute access |
| `PAG_GUARD` | `0x00000008` | guard page - first access raises a guard-page fault, then the page becomes normally accessible |
| `PAG_COMMIT` | `0x00000010` | commit storage |
| `PAG_DECOMMIT` | `0x00000020` | decommit storage |
| `PAG_DEFAULT` | `0x00000400` | default (initial) access |

Convenience combinations defined in `bsememf.h`:

| Macro | Expansion | Value |
|---|---|---|
| `fPERM` | `PAG_EXECUTE \| PAG_READ \| PAG_WRITE` | `0x00000007` |
| `fSET` | `PAG_COMMIT + PAG_DECOMMIT + PAG_DEFAULT + fPERM` | `0x00000437` |

## Allocation-attribute flags - `OBJ_*` [DOC-IBM `bsememf.h`]

These control *where* and *how* an object is placed, and its shareability. They are set at
allocation time.

| Flag | Value | Meaning |
|---|---|---|
| `OBJ_TILE` | `0x00000040` | place the object in the low 512 MB so it is addressable by a 16:16 tiled selector for 16-bit callers |
| `OBJ_PROTECTED` | `0x00000080` | protect object - **NOTE (header): not available at the API level** |
| `OBJ_GETTABLE` | `0x00000100` | object may be obtained by another process (via `DosGetSharedMem`) |
| `OBJ_GIVEABLE` | `0x00000200` | object may be given to another process (via `DosGiveSharedMem`) |
| `OBJ_ANY` | `0x00000400` | allocate memory anywhere (permit placement in high-memory arenas where available) |
| `OBJ_SELMAPALL` | `0x00000800` | the first selector maps the whole object (for `DosAllocMem` / `DosAliasMem`) |

Convenience combinations defined in `bsememf.h`:

| Macro | Expansion | Value |
|---|---|---|
| `fSHARE` | `OBJ_GETTABLE \| OBJ_GIVEABLE` | `0x00000300` |
| `fALLOC` | `OBJ_TILE \| PAG_COMMIT \| fPERM` | `0x00000057` |
| `fALLOCSHR` | `OBJ_TILE \| PAG_COMMIT \| fSHARE \| fPERM` | `0x00000357` |
| `fGETNMSHR` | `fPERM` | `0x00000007` |
| `fGETSHR` | `fPERM` | `0x00000007` |
| `fGIVESHR` | `fPERM` | `0x00000007` |

> `OBJ_ANY` (`0x400`) and `PAG_DEFAULT` (`0x400`) share a numeric value; they are disambiguated
> by which API consumes them - `OBJ_ANY` is an allocation attribute, `PAG_DEFAULT` a set/protect
> attribute. [DOC-IBM `bsememf.h`]

## Function summary

| Function | Purpose |
|---|---|
| `DosAllocMem` | reserve (and optionally commit) a private memory object |
| `DosFreeMem` | free an object obtained from `DosAllocMem` / a shared-memory get/give |
| `DosSetMem` | commit, decommit, or change the protection of pages within an object |
| `DosQueryMem` | query the allocation flags and size of the range at an address |
| `DosAllocSharedMem` | reserve (optionally commit) a shareable object, optionally named `\SHAREMEM\...` |
| `DosGetNamedSharedMem` | map a named shared object into the caller's address space |
| `DosGiveSharedMem` | grant a specific process access to a giveable shared object |
| `DosGetSharedMem` | obtain access to a gettable shared object by its address |
| `DosSubSetMem` | initialize or grow a suballocation pool within an existing object |
| `DosSubAllocMem` | suballocate a block from a pool |
| `DosSubFreeMem` | return a suballocated block to its pool |
| `DosSubUnsetMem` | discard a suballocation pool |
| `DosAliasMem` | create a second mapping (alias) of an existing range |
| `DosQueryMemState` | query the per-page present/resident/swappable state of a range |

(`DosAliasMem`, `DosQueryMemState`, and `DosQueryMem`'s returned-flag set are included for
completeness; the core application surface is the allocate/set/share/sub families below.)

## Private allocation

```c
APIRET APIENTRY DosAllocMem(PPVOID ppb, ULONG cb, ULONG flag);   /* bsedos.h:1849 */
APIRET APIENTRY DosFreeMem(PVOID pb);                            /* bsedos.h:1853 */
APIRET APIENTRY DosSetMem(PVOID pb, ULONG cb, ULONG flag);       /* bsedos.h:1855 */
```
[DOC-IBM `bsedos.h`]

- **`DosAllocMem`** - `ppb` receives the base address of the new object; `cb` is the size in
  bytes (rounded up to a page); `flag` is a combination of `PAG_*` protection and `OBJ_*`
  attribute flags. If `PAG_COMMIT` is set the object is committed as well as reserved. Passing
  `OBJ_TILE` forces placement in the tileable low 512 MB (see `memory-model.md`, "Segmentation
  and tiling"). The whole object is freed as a unit by `DosFreeMem`.
- **`DosFreeMem`** - releases the object whose base is `pb`. `pb` must be the base returned by
  the allocating call (or a shared-memory get/give), not an interior pointer.
- **`DosSetMem`** - operates on `cb` bytes starting at `pb` *within* an already-reserved object.
  With `PAG_COMMIT` it commits the range; with `PAG_DECOMMIT` it decommits it; with a
  protection combination (`fPERM` subset, or `PAG_GUARD`, or `PAG_DEFAULT`) it changes access.
  The legal flag set is `fSET` (`PAG_COMMIT + PAG_DECOMMIT + PAG_DEFAULT + fPERM`).

### `DosSetMem` access protection - `PAG_DEFAULT`, the required bit, and execute

`PAG_DEFAULT` (`0x400`) asks for *"the access protection specified when the object was
allocated in the address space of the requesting process"*, and unless `PAG_DECOMMIT` is set
*"the PAG_DEFAULT bit or at least one of the bits PAG_READ, PAG_WRITE, or PAG_EXECUTE must be
specified. All other bits must be clear."* [DOC-IBM `cp1.txt`, "DosSetMem Parameter - flag"].
On the 386 *"execute and read access are equivalent. Also, write access implies both read and
execute access."* [DOC-IBM `cp1.txt`, "DosSetMem - Remarks"], so a page committed without
`PAG_EXECUTE` still runs code, and `DosQueryMem` reports no execute bit for it.

IBM does not say which error a bad flag combination returns, nor what happens when
`PAG_DEFAULT` is combined with an access bit or applied to memory the program did not allocate
itself. Measured [OBS: WSeB CP2, 2026-09-17; each call covered one page - either a page of an
object the program had allocated, or the page containing the item named]:

| call | result |
|---|---|
| `PAG_COMMIT` with no access bit | `87` |
| `PAG_DEFAULT` with `PAG_READ`, with `PAG_WRITE`, or with `PAG_EXECUTE` (each tried alone) | `87` |
| `PAG_COMMIT\|PAG_DEFAULT` on reserved pages of a `PAG_READ\|PAG_WRITE` object | `0`; the page is readable, writable and executable |
| `PAG_COMMIT\|PAG_DEFAULT` on reserved pages of a `PAG_READ` object | `0`; the page reads and executes, and a write faults |
| `PAG_COMMIT\|PAG_DEFAULT` on pages that are **already committed** | `5` (`ERROR_ACCESS_DENIED`), on every object tried - the executable's code and data, the thread stack, the environment block, the TIB and a DLL's code |
| `PAG_DEFAULT` alone on any of those objects, or on an already-committed page of the caller's own | `0`, and the object's protection is unchanged - a code object stays read+execute and a write to it still faults |
| `PAG_DEFAULT` (with or without `PAG_COMMIT`) on a free address | `487` |

Two consequences worth stating plainly. **`PAG_DEFAULT` restores the *allocation's* protection,
not the protection set by the last `DosSetMem`**: on a `PAG_READ` object made writable with
`DosSetMem(pb, cb, PAG_READ|PAG_WRITE)`, a following `DosSetMem(pb, cb, PAG_DEFAULT)` returns
`0` and writes fault again. And **`PAG_DEFAULT` works on memory the program never allocated** -
loader objects, the stack, the environment block, the TIB - because each of those is an object
with a protection of its own (see below).

A newly committed page reads as zero: *"When pages are committed, they are backed by demand
pages. The first attempt to read or write the page causes a page of zeros to be created"*
[DOC-IBM `cp1.txt`, "DosSetMem - Remarks"]; measured on the page committed above, whose first
doubleword read `0` [OBS: same capture].

### Every page belongs to an object: extent, `PAG_BASE`, and `DosFreeMem`

Nothing in a process's address space is anonymous memory with no owner. The executable's code
and data, each DLL's objects, the thread stack, the environment and command-line block and the
TIB are all memory objects, and `DosQueryMem` answers for them exactly as it does for an object
the program allocated itself. Two sets of measurements follow [OBS: WSeB CP2, 2026-09-17]. The
first queries chosen addresses inside one `DosAllocMem` object. The second queries, for each
item named, the **page containing it** - so every row of that table is the answer for that page,
not for the item's own address.

Queried at an exact address, in a 65536-byte object allocated
`PAG_READ|PAG_WRITE|PAG_COMMIT`:

| queried at | `cb` | flags |
|---|---|---|
| the base | `65536` | `0x10013` `PAG_BASE\|PAG_COMMIT\|PAG_WRITE\|PAG_READ` |
| base `+4000` (still in the first page) | `61536` | `0x10013` |
| base `+4096` | `61440` | `0x00013` - no `PAG_BASE` |

Queried at the page containing each item, in a small 32-bit program that also loads a DLL:

| the page containing | `cb` from that page | flags |
|---|---|---|
| the executable's code (`main`) | `11098` | `0x10015` `PAG_BASE\|PAG_COMMIT\|PAG_EXECUTE\|PAG_READ` |
| the executable's initialised data, and separately its `bss` - one object | `67632` | `0x10013` |
| a stack local | `2096` | `0x00013` - no `PAG_BASE`: the stack lies inside the data object, and this `cb` ends exactly at `tib_pstacklimit` |
| the environment block, and separately the command-line block - one object | `401` | `0x10013` |
| the TIB | `4096` | `0x10013` |
| a loaded DLL's code | `142468` | `0x02015` `PAG_SHARED\|PAG_COMMIT\|PAG_EXECUTE\|PAG_READ` |

Where the PIB and the TIB sit [OBS: WSeB 4.50 revision 14.089, 2026-09-30; a 32-bit LX program's
`DosQueryMem` at the addresses `DosGetInfoBlocks` returned, then `DosFreeMem`]: the **PIB is the
base** of a one-page object (`cb` 4096, `0x10013`), the **TIB lies at +0x30** in the same object and
**TIB2 right after the TIB**, at +0x48. The environment block is another object, and the command line
lies inside it. `DosFreeMem` of the PIB's address returns 0 - the object, with the TIB in it, is
freed, and the thread carried on through a `DosWrite`. (A `DosFreeMem` of the TIB's address, made
afterwards, returned 487; the object was already free by then, so this run does not separate "not
a base" from "free" - the pointer 0x30 into the TIB's object in the `DosFreeMem` measurements below,
487, is the one that does.) In the same program the code object was at `0x10000` and the data object
at `0x20000`.

**A second thread** [OBS: WSeB 4.50 revision 14.089, 2026-09-30; `DosCreateThread` with a 64 KB stack,
then `DosQueryMem` from the new thread]: its **TIB is in the same object as the PIB and thread 1's TIB**,
at +0x60 - 0x30 after thread 1's - with its TIB2 again 0x18 after its TIB. A thread created after it
had ended got the same TID, TIB and stack addresses. **Its stack is an object of its own** (64 KB at
`0x90000`, the TIB's `tib_pstack`/`tib_pstacklimit` its bounds). With the default `STACK_SPARSE` the
base page reads `0x10003` - `PAG_BASE|PAG_WRITE|PAG_READ`, **not committed** - for 57344 bytes, while
the top pages the thread was using are committed; with `STACK_COMMITTED` the base page reads `0x1001b`,
**committed and `PAG_GUARD`**, for one page.

**A guard page touched** [OBS: WSeB 4.50 revision 14.089, 2026-09-30; a one-page object allocated
`PAG_COMMIT|PAG_GUARD|PAG_READ|PAG_WRITE` (`DosAllocMem` 0), then two stores 4 and 8 bytes into it]:
the first store raises `XCPT_GUARD_PAGE_VIOLATION` (0x80000001) with `fHandlerFlags` 0, `cParameters`
2, `ExceptionInfo[0]` = `XCPT_WRITE_ACCESS` (2), and **`ExceptionInfo[1]` = the page's address, not the
store's** (`bsexcpt.h` calls it "FaultAddr"). It is raised **once**: the second store raises nothing.
Whether the handler answers `XCPT_CONTINUE_EXECUTION` or `XCPT_CONTINUE_SEARCH`, both stores land and
execution goes on - by IBM's account the page is already ordinary when the exception is raised
[DOC-IBM `cp2.txt` `XCPT_GUARD_PAGE_VIOLATION`].

So `cb` is counted **from the queried address**, not from the object's base, and it is not
rounded up to a page - the executable's code object ends mid-page and `cb` says so. `PAG_BASE`
marks the object's **first page** rather than its exact base address: it is still set 4000 bytes
in, and clear one page in.

What `cb` spans is the run with the **same attributes**, which can end before the object does.
Walking a loaded DLL by querying `address + cb` repeatedly, for the eight regions the walk was
allowed to take, one pair shows it plainly: `32` bytes reported `0x12015`
(`PAG_BASE|PAG_SHARED|PAG_COMMIT|PAG_EXECUTE|PAG_READ`) and the next `65504` bytes reported
`0x12005`, the same without `PAG_COMMIT`. Both addresses lie in the first page of one object, so
a committed run and a reserved run of the same object are separate answers. Across those eight
regions **every one carried `PAG_SHARED`**, `PAG_BASE` was set on exactly those addresses that
fell in an object's first page, and the protections differed: `0x2001`, `0x2005`, `0x2015`,
`0x12005`, `0x12013`, `0x12015`.

A free address answers differently again: one tried at `0x1F000000` returned `0` with `PAG_FREE`
and a 64 KB extent, while `0x00F00000` returned `487` - what separates the two was not
established.

`DosFreeMem` frees **the whole object, by its base**, and refuses anything else [OBS: same
machine and date]: the object's own base returns `0`; base + 4096 returns `487`; a stack local
returns `487`; a pointer 0x30 into the TIB's object returns `487`; a free address and an
unmapped address return `487`. It does not refuse an object the loader created: passing the base
of the executable's data object frees it and the process dies at its next access, which is what
a program asking for that gets.

Measured again with every other `DosAllocMem`/`DosFreeMem` return, on a second machine [OBS: WSeB
4.50 revision 14.089, SMP kernel, 2026-09-30; a 32-bit program making each call once, the
unwritable-pointer call in a child process]:

| call | result |
|---|---|
| `DosAllocMem(&p, 1, PAG_COMMIT\|PAG_READ\|PAG_WRITE)` | `0`; `DosQueryMem` reports `4096` bytes, `0x10013`; the page reads zero |
| two such allocations | both bases 64 KB aligned (`0x00090000`, `0x000A0000`) |
| `flag = PAG_COMMIT` alone (no access bit) | `87` - *"At least one of the bits PAG_READ, PAG_WRITE, or PAG_EXECUTE must be set"* [DOC-IBM `cp1.txt`, "DosAllocMem - Parameters"] |
| an undefined flag bit (`0x1000`) with `PAG_COMMIT\|PAG_READ` | `87` |
| `cb = 0` | `87` |
| `cb = 0x7FFF0000`, reserve only | `8` |
| `ppb` pointing at an unwritable page (`0x1000`) | **`87`, and the call returns** - no exception reaches the caller |
| `DosFreeMem` of a base already freed | `487` |
| `DosFreeMem(pib_pchenv)` | `0` - `pib_pchenv` is its object's base (`DosQueryMem` flags `0x10013`) |

The 64 KB alignment is the Remarks' *"the system allocates a 64K object without attributes on
every allocation"* [DOC-IBM `cp1.txt`, "DosAllocMem - Remarks"] seen from outside. IBM lists `95`
`ERROR_INTERRUPT` for both calls and `5` `ERROR_ACCESS_DENIED` for `DosFreeMem`; none of these
calls produced either, and freeing the environment object - the one recipe tried for `5` -
succeeded.

## Shared memory

OS/2 supports two sharing models, both producing an object other processes can map at the
**same virtual address**:

1. **Named shared memory** - the object is created with a name of the form `\SHAREMEM\<name>`;
   any process that knows the name maps it with `DosGetNamedSharedMem`. This is the rendezvous
   model - no prior handshake between the processes is required.
2. **Anonymous give/get** - the object is created unnamed but `OBJ_GIVEABLE` and/or
   `OBJ_GETTABLE`. The owner either *gives* it to a specific process by PID
   (`DosGiveSharedMem`), or another process *gets* it by its address (`DosGetSharedMem`). This
   requires the two processes to already share the object's address or the target PID.

```c
APIRET APIENTRY DosAllocSharedMem(PPVOID ppb, PSZ pszName, ULONG cb, ULONG flag);  /* bsedos.h:1882 */
APIRET APIENTRY DosGetNamedSharedMem(PPVOID ppb, PSZ pszName, ULONG flag);         /* bsedos.h:1871 */
APIRET APIENTRY DosGiveSharedMem(PVOID pb, PID pid, ULONG flag);                   /* bsedos.h:1859 */
APIRET APIENTRY DosGetSharedMem(PVOID pb, ULONG flag);                             /* bsedos.h:1863 */
```
[DOC-IBM `bsedos.h`]

- **`DosAllocSharedMem`** - `ppb` receives the base; `pszName` is the `\SHAREMEM\...` name, or
  `NULL` for an anonymous object; `cb` is the size; `flag` combines `PAG_*` protection with the
  sharing attributes `OBJ_GETTABLE` / `OBJ_GIVEABLE` (and optionally `OBJ_TILE`, `PAG_COMMIT`).
  The header's canonical flag set for this call is `fALLOCSHR`
  (`OBJ_TILE | PAG_COMMIT | fSHARE | fPERM`). A named object need not also be giveable/gettable -
  the name alone lets others reach it via `DosGetNamedSharedMem`.
- **`DosGetNamedSharedMem`** - maps the named object into the caller with protection `flag`
  (`fGETNMSHR` = `fPERM`); `ppb` receives the address at which it is mapped.
- **`DosGiveSharedMem`** - the owner of a giveable object grants process `pid` access to the
  range at `pb`, with protection `flag` (`fGIVESHR` = `fPERM`).
- **`DosGetSharedMem`** - a process that already knows the address `pb` of a gettable object
  maps it with protection `flag` (`fGETSHR` = `fPERM`).

A shared object obtained by any of these is released with `DosFreeMem`; the object's storage
persists as long as any process still holds it.

**Measured** [OBS - measured on Warp Server for e-business 4.50, kernel revision 14.089, a
32-bit program and its child; codes named from `bseerr.h`]:

| Input | Result |
|---|---|
| `DosAllocSharedMem` of a name that already exists | 183 `ERROR_ALREADY_EXISTS` |
| a name without the `\SHAREMEM\` prefix (`DosAllocSharedMem` or `DosGetNamedSharedMem`) | 123 `ERROR_INVALID_NAME` |
| `DosGetNamedSharedMem` of a name that does not exist | 2 |
| `DosGetNamedSharedMem` in the allocating process itself | 0, the same address |
| a named object whose only holder exits without freeing it, then asked for by name | 2 - the name goes when the last holder exits |
| `DosGetSharedMem` of an address in no object | 487 `ERROR_INVALID_ADDRESS` |
| `DosFreeMem` by a process that has not got the object, or at an interior address | 487 |

- **A gettable object is not there until it is got.** In a child that has not called
  `DosGetSharedMem`, `DosQueryMem` on the object's address returns 0 with `PAG_FREE` (0x4000), and a
  read of it faults. After the get, the flags are 0x12011 (read, commit, shared, base) and the read
  works.
- `DosGetSharedMem` asking for read/write on an object created read-only returns 0.
- Access added later applies at once: a child that got the object read-only and had already read
  it could write it after the parent's `DosGiveSharedMem` granted read/write.
- An uncommitted gettable object reports the same flags (0x12003) in its allocator and in a getter.

**The tell:** a child faults reading a shared address that the parent can see - the child has not
called `DosGetSharedMem` (or been given the object) yet.

> **C++ prototypes.** Under `__cplusplus`, `bsedos.h` declares `pszName` as `PCSZ` (const) for
> `DosAllocSharedMem` (line 1877) and `DosGetNamedSharedMem` (line 1867); the C prototypes use
> `PSZ`. Signature and behaviour are otherwise identical. [DOC-IBM `bsedos.h`]

## 16-bit named shared segments - `DosAllocShrSeg` / `DosGetShrSeg` / `DosFreeSeg`

The 16-bit API's named shared memory. **There is no 32-bit form of either
`*ShrSeg` call** - IBM's own 1.3->2.0 migration table lists both as "N/A"
[DOC-IBM redbook GG24-3774, "Memory Management Functions"]; the 32-bit
equivalents in spirit are `DosAllocSharedMem` / `DosGetNamedSharedMem` above.

```c
USHORT DosAllocShrSeg(USHORT cb, PSZ pszName, PSEL psel);   /* DOSCALLS.35, 10 arg bytes */
USHORT DosGetShrSeg  (PSZ pszName, PSEL psel);              /* DOSCALLS.36,  8 arg bytes */
USHORT DosFreeSeg    (SEL sel);                             /* DOSCALLS.39,  2 arg bytes */
USHORT DosSizeSeg    (SEL sel, PULONG pcb);                 /* DOSCALLS.126,  6 arg bytes */
```
[DOC-IBM 16-bit Toolkit `bsedos.h`]; the argument-byte counts are the
kernel's own `pre_sci(N)` entry stubs [OBS-RE].

**Contract** [DOC: the CP Reference pages for `DosAllocShrSeg` /
`DosGetShrSeg` / `DosFreeSeg`, as reprinted on EDM2 - local mirror
`~/os2docs/edm2/DosAllocShrSeg.html`, `DosGetShrSeg.html`, `DosFreeSeg.html`]:

- `cb` is the segment size in bytes, at most 65535; **`cb == 0` means
  65536**. The segment is "movable and swappable", up to 64KB.
- `pszName` must be `\SHAREMEM\` followed by a name "in the format of an
  OS/2 filename". `DosGetShrSeg` returns **the same selector** the creator
  received.
- **A usage count** is kept per named segment: `DosAllocShrSeg` starts it at
  1, each `DosGetShrSeg` increments it, each `DosFreeSeg` decrements it, and
  at zero the segment is deallocated - "once the segment has been
  deallocated, it must be reinitialized by a call to DosAllocShrSeg". The
  count is capped at 65535; exceeding it is `ERROR_GEN_FAILURE` (31)
  [DOC-IBM CP Reference, error 31 note]. "The maximum number of segments a
  process can define with DosAllocShrSeg or access with DosGetShrSeg is 256"
  (`ERROR_TOO_MANY_OPEN_FILES`, 4) [DOC, `DosAllocShrSeg` page].

| rc | `DosAllocShrSeg` | `DosGetShrSeg` | `DosFreeSeg` |
|---|---|---|---|
| 0 | NO_ERROR | NO_ERROR | NO_ERROR |
| 2 | - | ERROR_FILE_NOT_FOUND (no such name) | - |
| 4 | - | ERROR_TOO_MANY_OPEN_FILES | - |
| 5 | - | - | ERROR_ACCESS_DENIED (selector not freeable - including one already freed [OBS]) |
| 8 | ERROR_NOT_ENOUGH_MEMORY | - | - |
| 123 | ERROR_INVALID_NAME | ERROR_INVALID_NAME | - |
| 183 | ERROR_ALREADY_EXISTS | - | - |
| 212 | - | - | ERROR_LOCKED [DOC, `DosFreeSeg` page] |

**Measured on OS/2 Warp 4.50, 2026-08-22** [OBS], with a 16-bit probe run
once and its output kept verbatim:

- Name rule, exactly: `DOSSHR16` (no prefix), `\SHAREMEM\` (nothing after
  it) and `SHAREMEM\X` (no leading backslash) are all **123**, for alloc and
  for get. Names are **case-insensitive**: `\sharemem\dosshr16` attaches to
  `\SHAREMEM\DOSSHR16`.
- Lifetime, exactly as documented: alloc (count 1) -> get (2) -> free (1) ->
  get (2) -> free -> free (0): a further get is **2**, a further alloc of the
  same name is **0** and returns a fresh segment.
- `DosFreeSeg` on a selector that has already been freed is **5**.
- The selector is identical across processes: a child spawned with
  `DosExecPgm` that calls `DosGetShrSeg` gets the value the parent stored in
  the segment, and each sees the other's writes.
- `DosSizeSeg` reports the segment's descriptor size: **4096** for a named
  segment created with `cb=4096`, **65536** for `cb=0`. On a plain
  `DosAllocSeg(n)` segment it reports **`n`** - the descriptor is byte-granular
  there (e.g. **4000** for `DosAllocSeg(4000)`, **4096** for `DosAllocSeg(4096)`).
  On a **GDT** (TI=0) selector, and on a **stale/freed** selector, it is **5**
  (`ERROR_ACCESS_DENIED`); on that error path the caller's `*pcb` is left with
  an undocumented value (real OS/2 leaves kernel garbage there).
- `DosAllocShrSeg(cb, name, NULL)` does not return; the process traps.
- **A `DosFreeSeg` that releases the descriptor leaves a null selector in ES
  and in DS afterwards; one that does not, leaves them alone.** Measured by
  loading the register with the selector, freeing, and reading it back: a
  named segment's destroying free (count 1->0) -> ES = 0, and DS = 0 in the
  same experiment on DS; a non-destroying free (count 2->1) -> ES unchanged;
  a plain `DosAllocSeg` segment's free -> ES = 0. So a program that keeps the
  selector in ES across the call (`p[i] = x; DosFreeSeg(sel);`) continues
  normally. [INF] The mechanism is the kernel's ring-0 return path: loading
  the trap frame's DS/ES for a descriptor that is no longer present is fixed
  up to the null selector rather than faulting. Only the freeing thread's
  own registers were observed.
- **A `DosAllocSeg` selector's descriptor is gone after its `DosFreeSeg`**:
  a second `DosFreeSeg` on it is **5**, the same answer as for a freed named
  segment's selector.

**Kernel mechanism** [OBS-RE, `os2krnl` decompiles - the *mechanism* below
is the same in all four held builds (retail/debug x SMP/UNI); any literal
offset is quoted from the build named beside it and differs per build]:

- The 16-bit entries `DOSALLOCSHRSEG`/`DOSGETSHRSEG` are `pre_sci` stubs;
  the workers `w_AllocShrSeg`/`w_GetShrSeg` thunk into **32-bit** kernel
  code - `_vmAllocNamedShrMem` and `_vmGetNamedShrMem`, the same two
  functions `_VM32ApiAllocSharedMem` / `_VM32ApiGetNamedSharedMem` call.
  **Both widths share one registry** (under `_vmNamShrSem`) and one name
  validator.
- `ValidateName`: a compare against the kernel's single `\SHAREMEM\`
  literal, then "at least one character follows"; either failure is `0x7b`
  (123). No length cap, no character-class check, in that function.
- The usage count: `_vmGetNamedShrMem` increments (refusing, and backing
  out, when it would wrap - the 65535 rule) and `_vmFreeNamedSharedMem`
  decrements, releasing the name record at zero. In the decompiles it is a
  16-bit word in a segment the name lookup returns, touched only under
  `_vmNamShrSem`, with a second word at +4 from it that is bumped on a new
  attach and decremented at destroy. The word's offset is a per-build
  value - `0x9442` (retail SMP), `0x9508` (debug SMP), `0x6646` (retail
  UNI), `0x671c` (debug UNI) - so it is not a fact about OS/2, only about
  an image. [INF] Whether that segment is a per-object record or a global
  table is not established from the decompile alone.
- A 16-bit object's selector is `(la >> 13) | 7` - the tiled LDT selector
  of its system-wide linear address, which is why it is the same value in
  every process. (A 32-bit object - flag `0x8000` to the allocator - gets no
  selector.)
- `h_w_FreeSeg` answers 5 for a selector whose TI bit is clear (not an LDT
  selector) before reaching its worker.

### `DosSizeSeg` (`DOSCALLS.126`) - the size of a 16-bit segment

`DosSizeSeg(SEL sel, PULONG pcb)` writes a segment's size through `pcb`. It is
**16-bit only**: there is no 32-bit form and no compatibility macro maps one
onto it - IBM's 32-bit interface deliberately omits `DosSizeSeg` "although the
16-bit entry points are still supported for compatibility purposes" [DOC-IBM
redbook GG24-3774, "32-bit Interface Construction"; the Warp-4.5 Toolkit
`bsedos.h` carries no prototype and no `#define`].

**Contract** [DOC-IBM, CP Reference `DosSizeSeg` page, local mirror
`~/os2docs/os2books/prcp/157_L2_DosSizeSeg.html`]:

- For a **non-huge** segment the size is "in the range 0 through 64KB". For a
  **huge** segment `sel` must be the base selector and the size is
  `(NUMSEG << 16) + ASIZE` - the last values passed successfully to
  `DosAllocHuge`/`DosReallocHuge` for that segment. A `cb == 0` allocation
  reports **65536** (the 64KB endpoint), consistent with `DosAllocShrSeg`'s
  `cb == 0` rule above.
- **The documented return list is `NO_ERROR` only.** The call exists "for
  family applications that must run in DOS or OS/2 mode", returning "the actual
  size of memory allocated by a `DosAllocSeg` or `DosAllocHuge` request".
- **A real error return is nonetheless load-bearing** [DOC-IBM, IBM's own PM
  sample `titlebar.c`, `WM_SETWINDOWPARAMS`]: that code does
  `rc = DosSizeSeg(SELECTOROF(mp1), &SegSize); if (rc != NO_ERROR) bail;` and
  only then bounds-checks against the returned size - using `DosSizeSeg` as a
  **selector-validity probe**. So a bad selector must fail even though the
  reference lists only `NO_ERROR`; the binary wins over the doc.

**Kernel mechanism** [OBS-RE, `os2krnl` decompiles - the mechanism is the same
in all four held builds (retail/debug x SMP/UNI); any literal offset is per
image]:

- `DOSSIZESEG` is a `pre_sci(6)` entry stub; the worker `h_w_SizeSeg` returns
  the 32-bit size in **DX:AX**, and the stub stores it through the caller's far
  `PULONG` with no visible pointer validation.
- The size is the process's **LDT descriptor `limit + 1`**, page-expanded when
  the granularity (G) bit is set - obtained via `_SELGetOd` ->
  `_SELGetDescInfo`, the same descriptor decode the kernel uses elsewhere. It
  is **not** the committed VM-object size and **not** a stored "requested cb".
- The worker answers **5** (`ERROR_ACCESS_DENIED`) before any lookup for a
  selector whose TI bit is clear (a **GDT**, i.e. non-application, selector);
  and after the lookup for an **absent/not-present** descriptor (internally
  `_SELGetDescInfo` returns 87, which the worker maps to 5) or one whose access
  byte lacks the DPL>=2 bit. The only non-5 error passed through is `0x5f`
  (`ERROR_INTERRUPT`), an in-kernel interruption case.
- The **huge** path additionally verifies the descriptor base equals the
  object's linear address and sums successive selectors' sizes via
  `_SELGetSize`.

### `DosReallocSeg` (`DOSCALLS.38`) - change a 16-bit segment's size

```c
USHORT DosReallocSeg(USHORT cbNewSize, SEL sel);   /* DOSCALLS.38, 4 arg bytes */
```
[DOC Open Watcom 1.9 `h/os21x/bsedos.h:385`]; the argument-byte count is the
kernel's own `pre_sci(4)` entry stub [OBS-RE].

**Contract** [DOC, the CP Reference `DosReallocSeg` page as reprinted on EDM2]:
`cbNewSize == 0` means 65536. The listed return codes are 0 `NO_ERROR`, 5
`ERROR_ACCESS_DENIED` and 8 `ERROR_NOT_ENOUGH_MEMORY`; the kernel routine also
has exits that return 87 and 212 [OBS-RE].

**Measured on OS/2 Warp Server for e-business 4.50, Revision 14.089, retail SMP
kernel, 2026-09-14** [OBS], a 16-bit probe run once, its capture retained:
`DosAllocSeg(0x2000, &sel, flags)`, then `DosReallocSeg(0x1000, sel)`, then
`DosSizeSeg`.

| `AllocFlags` | rc | size after |
|---|---|---|
| `0x0` | 0 | `0x1000` |
| `0x1` (`SEG_GIVEABLE`) | 5 | `0x2000` |
| `0x2` (`SEG_GETTABLE`) | 5 | `0x2000` |
| `0x3` | 5 | `0x2000` |
| `0xB` | 0 | `0x1000` |
| `0x8` | 0 | `0x1000` |

Growing to `0x2000` from `0x1000` is 0 for both `0x0` and `0x3`; `cbNewSize = 0`
gives `0x10000` for both. `DosReallocSeg` on selector `0x0007` is 5.

**Measured on the same machine, 2026-09-15** [OBS], a 16-bit probe run once,
its capture retained, on a loaded DLL's own data
objects, each reached through the selector of one of that DLL's 16:16 data
exports: a SHARED data object answered a shrink with 5 and kept its size, and
a grow with 0; an instance data object answered both a shrink and a grow
with 0, and `DosSizeSeg` followed each.

**Kernel mechanism** [OBS-RE; the addresses below are the uniprocessor kernel
image's, where the sequence spans `0014FB2A`..`0014FB49`; the SMP kernel image
carries the same instruction sequence at `0019BD0A`..`0019BD29`]: the rule is taken
from the segment record's own flag word. A record with `0x400` or `0x2` set is
refused every resize (`0014FB2A`); one with `0x800` set and `0x1` clear is
refused a size smaller than its current one (`0014FB35`..`0014FB49`); a record
without `0x800` never reaches the size comparison. The same conjunction appears
in a second build's decompile.

### The huge-segment shift and increment - `DosGetHugeShift`, `DOSHUGESHIFT`, `DOSHUGEINCR`

A "huge" allocation (`DosAllocHuge`, `DOSCALLS.40`) spans several 64 KB
segments, and **each segment has its own selector**. The selectors are not
consecutive integers; they step by a fixed **increment**, and a program
computes the increment from a **shift count**:

- **`DosGetHugeShift(PUSHORT pShiftCount)`** (`DOSCALLS.41`) returns the shift
  count. To get the next segment's selector, "take the value 1, shift it left
  by the number of bits specified in shift count, and use the resulting value
  as an increment to add to the previous selector, using the selector returned
  by `DosAllocHuge` as the first" [DOC-IBM, IBM Control Program Reference
  (16-bit), the `DosGetHugeShift` and `DosAllocHuge` pages].
- The same two facts are **also exported as absolute-value symbols**, for code
  that wants them as a link-time constant rather than a call:
  **`DOSHUGESHIFT` (`DOSCALLS.135`)** is the shift count and
  **`DOSHUGEINCR` (`DOSCALLS.136`)** is the increment `= (1 << DOSHUGESHIFT)`.
  Both are `:ABS` exports - a program references them at a value site, e.g.
  `EXTRN DOSHUGEINCR:ABS` then `mov ecx, DOSHUGEINCR` [DOC-IBM, DDK
  `EXTERNDEF DOSHUGEINCR :ABS`, `.../video/src/video/vga32/vgainc/extern.inc:486`;
  used at `.../svga256/scanline.asm:2996` and `driver.inc:862` "either 10h for
  the physical display or DOSHUGEINCR for memory bitmaps"]. See
  `executable-formats.md`, "Absolute-value exports", for how a fixup consumes
  one.
- **The RELATION is architectural; the VALUES are per-build.** Keep them apart -
  the first is IBM's stated contract, the second is a reading of particular
  binaries, and conflating them is how a fact about one build gets published as
  a fact about the family.
  - **`DOSHUGEINCR = (1 << DOSHUGESHIFT)`** - `[DOC-IBM]`, stated in the CP
    Reference passage quoted above ("shift 1 left by the shift count and use the
    result as the increment"). This holds wherever the API does.
  - **`DOSHUGESHIFT` = 3 and `DOSHUGEINCR` = 8** - so consecutive huge-segment
    selectors differ by 8, one LDT slot, an LDT selector being
    `(index << 3) | ring`. `[OBS-RE]` the kernel's own DOSCALLS export table
    `dcm_entrytblstart` holds `01 03 00` (tag 1 "direct value, selector 0";
    value 0x0003) at ordinal 135 and `01 08 00` (value 0x0008) at ordinal 136,
    read out of a Warp-4.5-era `os2krnl` and identical across the four builds of
    that family; independently `[OBS-RE]` the kernel's `DosGetHugeShift` worker
    is literally `mov ax,0x3`. And `[OBS]` a **running** OS/2 Warp Server for
    e-business machine (kernel Internal revision 14.089_UNI) answered **3**
    through `DosGetHugeShift` and delivered **8** to a 16-bit program importing
    `DOSCALLS.136`.
  - **Scope of those two numbers.** They are established for the builds just
    named, not for every OS/2 release: an offset or a value read out of one
    binary is a fact about that binary until it is corroborated on another, and
    the releases this API spans are decades apart. The *relation* is what
    generalises. A program that needs the numbers should ask
    `DosGetHugeShift` - which is why IBM provides the call at all - rather than
    compile 3 and 8 in.
  - The CP Reference's own worked example uses a *hypothetical* shift of 4 /
    increment 16; that is an illustration, and not a value any measurement here
    produced.

  > **CORRECTED 2026-09-04 (Rule 1.7 - the wrong version is kept because both
  > mistakes are easy to repeat).** This bullet previously read *"corroborated by
  > `DosGetHugeShift`, whose worker returns 3"* and *"The 8 is architectural (the
  > increment IS `1<<shift`), so it is stable across the releases whose selectors
  > are laid out this way."* Two defects. **(1) The corroborator was ambiguous
  > and, read the likely way, circular** - "the worker" does not say *whose*, so
  > a reader checking it against an implementation's own hardcoded 3 would be
  > citing that implementation as authority for itself. The corroboration is
  > only worth something when it names an independent artifact: IBM's kernel
  > bytes, or a running machine. Both are now named. **(2) The architectural
  > claim was smuggled onto the wrong half.** `1<<shift` is architectural; **8**
  > is not - 8 is what you get *given* `shift == 3`, which is a per-build
  > reading. The old hedge ("stable across the releases whose selectors are laid
  > out this way") is circular: it defines the set it claims to range over by the
  > very property in question, so it excludes no release and constrains nothing.

## Suballocation heap

The `DosSub*` family manages a **heap within an already-allocated object**. The application
first obtains a memory object (private via `DosAllocMem`, or shared via `DosAllocSharedMem`),
then hands its base to `DosSubSetMem` to turn it into a managed suballocation pool. Blocks are
then carved from the pool by `DosSubAllocMem` and returned by `DosSubFreeMem`. This gives
fine-grained (sub-page) allocation without a kernel call per block, and - for a pool inside a
shared object - a heap shared across processes.

```c
APIRET APIENTRY DosSubSetMem(PVOID pbBase, ULONG flag, ULONG cb);         /* bsedos.h:1906 */
APIRET APIENTRY DosSubAllocMem(PVOID pbBase, PPVOID ppb, ULONG cb);       /* bsedos.h:1894 */
APIRET APIENTRY DosSubFreeMem(PVOID pbBase, PVOID pb, ULONG cb);          /* bsedos.h:1900 */
APIRET APIENTRY DosSubUnsetMem(PVOID pbBase);                             /* bsedos.h:1912 */
```
[DOC-IBM `bsedos.h`]

Older Toolkit aliases exist as macros: `DosSubAlloc`/`DOSSUBALLOC`, `DosSubFree`/`DOSSUBFREE`,
`DosSubSet`/`DOSSUBSET`, `DosSubUnset`/`DOSSUBUNSET` all map to the corresponding `*Mem`
function (`bsedos.h:1892-1911`). [DOC-IBM]

- **`DosSubSetMem`** - `pbBase` is the base of the backing object; `flag` selects the operation
  (see `DOSSUB_*` below); `cb` is the pool size. `DOSSUB_INIT` establishes a new pool;
  `DOSSUB_GROW` enlarges an existing one.
- **`DosSubAllocMem`** - carves `cb` bytes from the pool at `pbBase`, returning the block
  address in `ppb`.
- **`DosSubFreeMem`** - returns the `cb`-byte block at `pb` to the pool at `pbBase`.
- **`DosSubUnsetMem`** - discards the pool management for the object at `pbBase` (the underlying
  object itself is still freed separately with `DosFreeMem`).

> **[DOC - EDM2 "DosSubFree"]** The suballocator detects an invalid free: returning a block
> that overlaps memory in the object that was never suballocated is rejected. A block size
> that is not a multiple of four bytes is rounded up to a multiple of four. The legacy 16-bit
> binding surfaces these two conditions as `ERROR_DOSSUB_OVERLAP` (`312`) and
> `ERROR_DOSSUB_BADSIZE` (`313`).
>
> **[DOC - EDM2 "DosSubUnsetMem"]** Every `DosSubSetMem` should be balanced by a
> `DosSubUnsetMem`, and the unset must occur *before* the backing object is freed -
> `DosSubUnsetMem` releases only the suballocator's own management resources, not the object.
> It returns `ERROR_DOSSUB_CORRUPTED` (`532`) if the pool's control data is corrupt.

**Measured** [OBS - measured on Warp Server for e-business 4.50, kernel revision 14.089, 32-bit
probe; codes named from `bseerr.h`]:

| Input | Result |
|---|---|
| `DosSubSetMem(INIT)` with `cb` 0x48 | 0 - the smallest pool accepted |
| `INIT` with `cb` 0x40, or with an undefined flag bit (0x41) | 87 |
| `DosSubSetMem` without `INIT` on a live pool | 0 (attaches) |
| `DosSubSetMem` without `INIT` on zeroed memory that was never a pool | 87 |
| `GROW` to a larger size / to a smaller size | 0 / 310 `ERROR_DOSSUB_SHRINK` |
| `DosSubAllocMem` of 64 bytes in a new pool | 0; the block is at pool base + 0x40 |
| free that block and allocate 64 again | the same offset (first fit) |
| allocate 13 bytes, then 8 | the second block starts 16 bytes after the first |
| `cb` 0 | 87 |
| larger than the pool | 311 `ERROR_DOSSUB_NOMEM` |
| `DosSubFreeMem` of an address outside the pool | 87 |
| the same block freed twice | 312 `ERROR_DOSSUB_OVERLAP` |
| `DosSubUnsetMem` twice | 0 both times |

The 13-then-8 result means blocks are rounded to **8** bytes on this system, not the multiple of
four EDM2 describes above. A `DOSSUB_INIT | DOSSUB_SERIALIZE` pool in named shared memory, hammered
by two processes at once (2,000 allocate/free pairs each), stayed consistent.

### `DOSSUB_*` flags for `DosSubSetMem` [DOC-IBM `bsememf.h`]

| Flag | Value | Meaning |
|---|---|---|
| `DOSSUB_INIT` | `0x01` | initialize the object for suballocation |
| `DOSSUB_GROW` | `0x02` | increase the size of the suballocation pool |
| `DOSSUB_SPARSE_OBJ` | `0x04` | `DosSub` manages commitment of the pages the pool spans (the backing object may be reserved-but-uncommitted; the suballocator commits pages as needed) |
| `DOSSUB_SERIALIZE` | `0x08` | `DosSub` serializes access to the pool (safe for concurrent callers) |

## Querying memory

```c
APIRET APIENTRY DosQueryMem(PVOID pb, PULONG pcb, PULONG pFlag);          /* bsedos.h:1888 */
APIRET APIENTRY DosQueryMemState(PVOID pb, PULONG cb, PULONG pFlag);      /* bsedos.h:1845 */
```
[DOC-IBM `bsedos.h`]

- **`DosQueryMem`** - for the address `pb`, returns in `*pcb` the size of the contiguous range
  sharing the same attributes and in `*pFlag` the attributes of that range. Measured, that
  range runs from `pb` to the end of the object, and `PAG_BASE` reports the object's first page:
  see "Every page belongs to an object" above.
- **`DosQueryMemState`** - returns in `*pFlag` the per-page residency state of the range.

### Flags returned by `DosQueryMem` [DOC-IBM `bsememf.h`]

In addition to the `PAG_*` protection bits (read/write/execute/guard) and commit state, the
returned flag word can carry:

| Flag | Value | Meaning |
|---|---|---|
| `PAG_COMMIT` | `0x00000010` | the range is committed |
| `PAG_SHARED` | `0x00002000` | the object is shared |
| `PAG_FREE` | `0x00004000` | the pages are free (unallocated) |
| `PAG_BASE` | `0x00010000` | this is the first page of the object |

### Page-state values returned by `DosQueryMemState` [DOC-IBM `bsememf.h`]

| Value | Constant | Meaning |
|---|---|---|
| `0x00000000` | `PAG_NPOUT` / `PAG_INVALID` | page not present, not in core (or invalid) |
| `0x00000001` | `PAG_PRESENT` | page is present |
| `0x00000002` | `PAG_NPIN` | page not present, but in core |
| `0x00000003` | `PAG_PRESMASK` | present-state mask |
| `0x00000010` | `PAG_RESIDENT` | page is resident (not swappable) |
| `0x00000020` | `PAG_SWAPPABLE` | page is swappable |
| `0x00000030` | `PAG_DISCARDABLE` / `PAG_TYPEMASK` | page is discardable / type mask |

## 16-bit huge segments - measured sharing behaviour

A 16-bit program allocates a "huge" block as a run of 64 KB segments whose selectors are spaced
by a fixed increment [DOC-IBM DDK `base/h/bsedos16.h:1119-1156`]:

```c
APIRET APIENTRY DosAllocHuge(USHORT cSegs, USHORT cbPartialSeg, PSEL psel,
                             USHORT cMaxSegs, USHORT fsAlloc);
APIRET APIENTRY DosReallocHuge(USHORT cSegs, USHORT cbPartialSeg, SEL sel);
APIRET APIENTRY DosGetHugeShift(PUSHORT pusShiftCount);   /* increment = 1 << shift */
APIRET APIENTRY DosGiveSeg(SEL sel, PID pid, PSEL pSelRecipient);
APIRET APIENTRY DosGetSeg(SEL sel);
APIRET APIENTRY DosFreeSeg(SEL sel);
APIRET APIENTRY DosSizeSeg(SEL sel, PULONG pcbSize);
/* fsAlloc: SEG_NONSHARED 0, SEG_GIVEABLE 1, SEG_GETTABLE 2, SEG_DISCARDABLE 4 */
```

`DosGetHugeShift` returned 3 on the measuring system, so the selector increment is 8
[OBS - measured]. **Sharing is per block, not per segment**, which IBM does not state
[OBS - measured on Warp Server for e-business 4.50, a 16-bit parent and child]:

- **One `DosGetSeg` of the base selector attaches every segment:** the child could read both the
  base segment and `base + increment` after a single get.
- One `DosGiveSeg` of the base likewise gives the whole block; giving an interior selector
  (`base + increment`) returns 5.
- A child that has attached the block sees a later `DosReallocHuge` grow by the parent - both the
  new size (via `DosSizeSeg`) and the new segment's contents - and an allocator sees a grow made
  by a process that got the block.
- `DosGetSeg` of a block allocated without `SEG_GETTABLE` returns **87** (not in IBM's list for
  the call).
- `DosFreeSeg` of an interior selector returns 5 and leaves the block intact; `DosFreeSeg` of the
  base frees it, and a second `DosFreeSeg` returns 5.

## Aliasing

```c
APIRET APIENTRY DosAliasMem(PVOID pb, ULONG cb, PPVOID ppbAlias, ULONG fl);   /* bsedos.h:1840 */
```
[DOC-IBM `bsedos.h`]

`DosAliasMem` creates a second address (`*ppbAlias`) that maps the same `cb` bytes of physical
storage as `pb`, so the same memory is reachable through two ranges (for example, to obtain a
tiled 16:16-addressable alias of a flat object). Alias-specific `fl` bits, from `bsememf.h`:
`OBJ_TILE` (`0x40`), `OBJ_SELMAPALL` (`0x800`), `SEL_CODE` (`0x01` - selector is code), and
`SEL_USE32` (`0x02` - selector is USE32). [DOC-IBM `bsememf.h`]

**[DOC - EDM2 "DosAliasMem"]** The alias is **process-private** - reachable only by the
process that created it, even when the original is a shared object (a common use is aliasing a
read-only shared object as read/write so only the owner can update it). The original range must
already be accessible to the caller, `pb` must be 4 KB-aligned, and with `OBJ_SELMAPALL` the
range must be committed and lie within a single object; without `OBJ_SELMAPALL` the size is
rounded up to a 4 KB multiple and the alias inherits the original pages' permissions. `OBJ_TILE`
is currently enforced whether or not it is passed, so alias LDT selectors always fall on 64 KB
boundaries. An alias is removed by calling `DosFreeMem` on the alias address.

Return codes [DOC - EDM2 "DosAliasMem"]:

| Code | Value | Meaning |
|---|---|---|
| `NO_ERROR` | `0` | alias created |
| `ERROR_NOT_ENOUGH_MEMORY` | `8` | no storage/selector available for the alias |
| `ERROR_INVALID_PARAMETER` | `87` | invalid flag, size, or alignment argument |
| `ERROR_INTERRUPT` | `95` | the call was interrupted |
| `ERROR_CROSSES_OBJECT_BOUNDARY` | `32798` | the range spans more than one memory object |

## Error codes [DOC-IBM `bseerr.h`]

The memory calls return `APIRET` (`0` = `NO_ERROR`). Common non-zero returns:

| Code | Value | Typical cause |
|---|---|---|
| `ERROR_ACCESS_DENIED` | `5` | operation not permitted on the object (e.g. protection change on memory the caller may not modify) |
| `ERROR_NOT_ENOUGH_MEMORY` | `8` | request could not be satisfied (no address space / no storage to commit) |
| `ERROR_INVALID_PARAMETER` | `87` | a flag combination or size argument is invalid |
| `ERROR_INVALID_NAME` | `123` | a shared-memory name is malformed (not a valid `\SHAREMEM\...` name) |
| `ERROR_ALREADY_EXISTS` | `183` | a named shared object with that name already exists |
| `ERROR_INVALID_ADDRESS` | `487` | `pb` does not point into a valid object / not an object base where one is required |
| `ERROR_CROSSES_OBJECT_BOUNDARY` | `32798` | a range argument spans more than one memory object |

(Values transcribed from `bseerr.h`; a given call returns the subset applicable to its inputs.)

## See also
- `memory-model.md` - the virtual address space, private/shared/system arenas, the GDT/LDT
  selector split, and the 64 KB tiling that `OBJ_TILE` targets.
- `kernel-services.md` - the DOSCALLS surface these APIs belong to.
