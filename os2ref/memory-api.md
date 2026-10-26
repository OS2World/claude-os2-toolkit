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

**Measured** [OBS-RE - measured on Warp Server for e-business 4.50, kernel revision 14.089, a
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

**Measured** [OBS-RE - measured on Warp Server for e-business 4.50, kernel revision 14.089, 32-bit
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
  sharing the same attributes and in `*pFlag` the attributes of that range.
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
[OBS-RE - measured]. **Sharing is per block, not per segment**, which IBM does not state
[OBS-RE - measured on Warp Server for e-business 4.50, a 16-bit parent and child]:

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
