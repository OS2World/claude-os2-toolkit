# OS/2 Memory Model - Arenas and Selectors

The 32-bit OS/2 virtual address space, its arenas, and the segmented (selector:offset) addressing
the 16-bit ABI still uses. Established during kernel initialization (boot-sequence Stage 2).

Provenance: **[DOC-IBM]** IBM redbook GG24-3730 *OS/2 Version 2.0 Volume 1: Control Program*
(the arena map, the GDT/LDT split, the tiling algorithm); **[DOC-IBM]** IBM OS/2 Warp Server SMP
programming-reference addendum (the high-memory arenas); **[DOC-IBM]** IBM Toolkit `bsememf.h`
(`OBJ_TILE`).

Ratified (2026-07-26): checked against IBM redbook GG24-3730,
the OS/2 Warp Server SMP addendum, and the OS/2 Toolkit 4.5
header `bsememf.h`. The arena map, the 512 MB system/process split, the GDT-system/LDT-application
split, the 8192-entry tiled LDT, the 64 KB tile granularity, and the 16:16 <-> 0:32 conversion formula
were all confirmed in IBM primaries and upgraded to `[DOC-IBM]` (details at each site). The
`VIRTUALADDRESSLIMIT` range was corrected against the SMP addendum. The version-specific
shared-arena sub-region *hints* (0x14000000 etc.) were searched for but **not** found in any IBM
source and remain `[OBS-RE]`.

Added 2026-07-29, after that pass: section "Address space vs. committed storage". It restates claims
already sourced in this doc, `memory-api.md`, and `infoseg.md` and asserts nothing new against a
primary; its cites point at those sites.

## Virtual address space [DOC-IBM (redbook GG24-3730) / OBS-RE]

The 4 GB space splits at **512 MB (0x20000000)** into a **process region** (below) and the **system
region** (above): IBM redbook GG24-3730 section "Virtual Memory Management" - *"The system arena contains
all the memory objects that are in the system region. It maps the virtual address space between
512MB and 4GB."* (glossary "system region": *"the address region above 512MB, which is reserved for
operating system use"*; "compatibility region": the region below 512 MB). The process region holds
the per-process **private arena** (*"starts at the lowest address of the process region ... and has a
minimum size of 64MB"*, grows up) and the **shared arena** (*"allocated starting at the top end of
the process region and moves down towards the private arena ... minimum size of 64MB"*); their
internal boundary is dynamic - *"the upper limit of the private arena and the lower limit of the
shared move towards one another."* [DOC-IBM - GG24-3730 section "Virtual Memory Management",
IBM redbook GG24-3730 section "Virtual Memory Management".] The 512 MB / system-region split,
the min-64 MB arena sizes, and the grow-toward-each-other boundary are `[DOC-IBM]`; the specific
numeric internal sub-boundaries in the table below are `[OBS-RE]` (KDB observation on the real
kernel - not stated in IBM sources).

| Range | Region / arena | Contents |
|---|---|---|
| 0x00000000 - 0x00010000 | NULL-pointer guard | reserved |
| 0x00010000 - ~0x04000000 | **private arena** (grows up) | per-process: `.EXE`, heap, thread stacks (>= 64 MB, expandable) |
| ~0x04000000 - 0x13000000 | expansion region | where the dynamic private/shared boundary moves |
| 0x13000000 - 0x20000000 | **shared arena** (grows down) | DLLs, named shared memory, system semaphores |
| 0x20000000 - 0xFFFC0000 | **system arena** | ring-0 (kernel) |
| 0xFFFC0000 - 0xFFFFFFFF | hardware reserved | BIOS / hardware |

> **High-memory arenas** (Warp Server SMP / for e-business; later Warp 4 fixpacks; eCS / ArcaOS):
> the process region is extended above 0x20000000 - *"a high private arena at the low end and a high
> shared arena at the high end ... the high private arena grows up and the high shared arena grows
> down"* - up to the CONFIG.SYS `VIRTUALADDRESSLIMIT`, raising the system region accordingly.
> ~~"commonly 1024-3072 MB"~~ **corrected 2026-07-26 (Rule 1.7):** the SMP addendum gives the
> **default 2048** MB (2 GB) - a later fixpack lowered the shipped default to 1024 MB - and a
> **maximum 3072** MB (3 GB); values are rounded up to a 64 MB boundary, and *"no memory objects can
> span the 512 MB line."* Objects above 512 MB start on a 4 KB boundary and are **not** tileable
> (16-bit code cannot address them); objects below start on a 64 KB boundary and are tileable.
> [DOC-IBM - OS/2 Warp Server SMP programming-reference addendum, section "High Memory Support" /
> section "VIRTUALADDRESSLIMIT Parameter in CONFIG.SYS" / section "Implementation Details",
> OS/2 Warp Server SMP addendum section 042-045. Also *Inside OS/2 Warp Server for e-business*,
> SG24-5393 (not held locally).]

### Shared-arena sub-regions [DOC-IBM]
Version-specific (Warp 4 / V3 FP19) region hints, not a hard ABI: R/W-basing at 0x14000000,
global-shared (read-only) 0x18000000-0x1C000000, 16-bit packed code at 0x19000000, pre-based DLLs at
0x1A000000; the shared arena tops out at 0x1FFF0000 (512 MB - 64 KB).

## Address space vs. committed storage [DOC-IBM]

Two different ceilings are both called "memory", and the arena map above bounds only the first:

- **Address space** is a *per-process* limit fixed by the 32-bit architecture: the private arena,
  the shared arena, and - where high-memory support is present - the high arenas, up to
  `VIRTUALADDRESSLIMIT` (3072 MB maximum). No amount of installed RAM widens it; a 32-bit pointer
  cannot reach further.
- **Committed storage** is a *machine-wide* limit. Reserving address space costs no storage;
  committing a page guarantees backing for it out of one pool of physical memory plus swap that
  every process on the system draws from (`memory-api.md` section "The committed / reserved / decommitted
  model" `[DOC]`). It is indifferent to which process's arena the address came from.

The arena map is asymmetric between the two. Only the **private** arena is per-process; the
**shared** arena (DLLs, named shared memory, system semaphores) and the **system** arena above
512 MB are one instance for the whole machine - a shared object occupies the same linear address in
every process that maps it. So a process can exhaust shared address space with its private arena
nearly empty (many DLLs loaded system-wide), or exhaust its private arena on a machine with
gigabytes free. Neither failure is about installed RAM.

OS/2's own API keeps the two families apart. In `DosQuerySysInfo` (`infoseg.md`),
`QSV_TOTPHYSMEM` / `TOTRESMEM` / `TOTAVAILMEM` report **storage**, machine-wide - the last is
explicitly *available for all processes*; `QSV_MAXPRMEM` / `MAXSHMEM`, and their high-memory
counterparts `QSV_MAXHPRMEM` / `MAXHSHMEM`, report **address space** *for the calling process*.
Reading a per-process figure as a machine-wide one, or the reverse, is the usual source of
confusion.

`ERROR_NOT_ENOUGH_MEMORY` (`8`) is returned for **both** conditions - *"no address space / no
storage to commit"* (`memory-api.md` section "Error codes" `[DOC-IBM bseerr.h]`) - so the return code alone
does not distinguish them. An allocation that fails in the low hundreds of MB on a machine with RAM
to spare has hit an arena or tiling boundary (`OBJ_TILE` confines an allocation to the first 512 MB),
not a storage shortage; compare `QSV_MAXPRMEM` / `MAXSHMEM` against `QSV_TOTAVAILMEM` to tell which.

**Two different strengths of support, and the difference is load-bearing.**

*Verifiable in IBM prose today* [DOC-IBM - *OS/2 Debugging Handbook* Vol. I,
Ch. 13, "the shared arena is further subdivided into a number of regions"]: the
arena *"starts **initially** at the 304MB boundary and ends at 512MB"* - IBM's
own "initially" is doing work, see the MEMMAN note below; **Protected** is
reachable only by DLLs "assigned data selector 63"; **Based** is "reserved for
non-protected DLLs that have a preferential base address assigned by the linkage
editor by using the BASE option"; **Packed** is "reserved for 16-bit DLL code
segments", packed contiguously, and inside it "the compatibility region mapping
algorithm does not apply" - so a 16->32 address conversion there requires
scanning the LDT.

*IBM's own worked-example dump output* [DOC-IBM - same handbook, six `.vmda`
arena dumps: Vol. I lines 8899, 14041, 14097 and Vol. II lines 13830, 13850,
13996]: every one carries the identical record `%04000000 007 ... max=%1fff0000`,
across three separate dump sessions in two volumes. **This is where the corpus's
`0x1FFF0000` comes from, and it is held in this tree** - IBM's *prose* says
"512 MB" (`0x20000000`), and only the dumps supply the 64 KB. Re-verified the
way a binary read is, by reading the dump again, not by re-running anything.
`[INF]` on one point, stated rather than assumed: that record's `va` is
`%04000000` = **64 MB**, *below* the 304 MB arena bottom, so `max=` plausibly
bounds the whole user address space rather than the shared arena specifically.
Either reading puts the top of user-addressable arena space at `0x1FFF0000`,
which is what the line above claims; which of the two `max=` means is not
established here.

*Inference, not IBM's word* `[INF]`: that **Protected** *begins* at **448 MB**
(`0x1C000000`). IBM's only use of that boundary - its single occurrence in all
held IBM text, Vol. I Ch. 13 - is a statement about **application
addressability**: *"In General 16- and 32-bit applications do not have
addressability above the 448MB boundary."* Read beside the selector-63 sentence
that is verbatim above, a protected region starting there is a good inference and
nothing more; the start address is implied, never stated.

*Resting on a figure not held in the source set used here*: the three interior addresses
**0x14000000, 0x19000000 and 0x1A000000**. Their source is *Figure 10, "Virtual
Address Space Regions"* (same handbook, section 3.4.1.1) - an **image, not present in
the text extraction held here**, so the citation cannot be followed in this tree
(the same caveat the SMP-addendum citation above states as *"not held
locally"*). None of the three literals occurs in any held IBM text. Treat them
as IBM's, unre-readable here, until the figure is obtained.

**Why the boundaries are soft, from IBM rather than from us** [DOC-IBM, same
chapter]: `MEMMAN=NOPROTECT` subsumes the protected region into the based one
and, under OS/2 2.x, moves **based and packed up by 64 MB**; `MEMMAN=NOPACK`
disables packing. So the region *positions* are a CONFIG.SYS-dependent runtime
layout, which is what "not a hard ABI" means and why the observation below finds
the same shape at different addresses. That characterisation is no longer ours
by inference.

**One unresolved oddity, inherited not introduced**: as transcribed, packed
(0x19000000) and based (0x1A000000) fall *inside* the stated global-shared range
0x18000000-0x1C000000. Consistent with the MEMMAN note - a fixed table cannot
describe a movable layout - but which reading Figure 10 intends is exactly what
the unheld figure would settle.

> **Provenance corrected 2026-08-31 (Rule 1.7), third pass.** The claim below
> was tagged `[OBS-RE]` and is now `[OBS]`. **No claim changed.** It is the same
> method as `executable-formats.md`'s placement observations - a ring-3 probe on
> real OS/2 comparing live object addresses against the on-disk object table -
> and `[OBS-RE]` names RE of a binary or the kernel debugger, neither of which
> was used.
>
> ~~The section heading above keeps `[OBS-RE]`, which is correct for the
> version-specific region hints it introduces.~~ **THAT SENTENCE WAS FALSE, and
> the heading is now `[DOC-IBM]` (Rule 1.7, same day).** The region figures are
> not reverse-engineered at all: they are an IBM-published memory map, cited
> above. The sentence adjudicated a tag by asserting it rather than by checking
> the source, in a note whose whole subject was tag provenance. **And the first
> attempt to fix it repeated the shape one level up** (Rule 1.7, same day): it
> cited the handbook without checking the cited text is readable here, and
> offered a second project doc as independent corroboration when that doc says
> in its own heading that it is folded from the same archive file. Two copies of
> one source are not two sources - and an
> automated sweep flagged this heading on three consecutive passes, each of
> which read that sentence and moved on. **A disposition recorded without a
> source is what makes a candidate stop being examined**, which is worse than
> leaving it undispositioned.

**A second, independent observation - Warp 4.50 (Server for e-business).** `[OBS]`
Sampling where the loader actually placed **relocated DLL objects** (comparing every loaded
module's live object addresses against the object table in the file on disk) shows the same
*shape* as the hints above - writable low, read-only high - at different addresses, which is
what "version-specific, not a hard ABI" predicts:

| landing band | object permission | count |
|---|---|---|
| `0x17______` | writable | 17 (0 executable) |
| `0x1E______` | executable or read-only | 12 EXEC + 5 RO (0 writable) |

Two things generalise beyond the specific addresses:

- **The split is by writability, not by the LX `SHARED` object flag.** That hypothesis was
  tested and refuted - objects both with and without the flag appear in both bands, while the
  read/write permission separates them cleanly.
- **A relocated DLL object stays inside the shared arena.** Objects whose preferred base was
  unavailable - or which had none - were re-placed elsewhere *within* 0x13000000-0x20000000,
  never into the private arena. Both bands sit below the 512 MB line and are therefore
  tileable, so 16-bit code can still address a relocated object through a 16:16 alias.

**Allocation direction, measured.** Four successive loads of the same module descended in 64 KB
steps - `0x1E160000` -> `0x1E140000` -> `0x1E120000` -> `0x1E100000` - corroborating the "grows
down" note in the table above from live behaviour rather than documentation. (An *ascending*
sequence of addresses observed across a boot is load order over a downward-growing arena, not an
upward allocator.)

## Selectors - GDT for the system, LDT for applications [DOC-IBM / OBS-RE]

OS/2 uses the **GDT for system/kernel selectors** and a **per-process LDT for application, DLL, and
shared-memory selectors**. The split is documented: the GDT stores *"the segment base addresses of
all memory segments in the system ... used by the operating system ... not available to processes
executing in the system,"* while the LDT stores *"the segment base addresses for memory segments
used by the current process"* [DOC-IBM - GG24-3730 glossary "global descriptor table" / "local
descriptor table", IBM redbook GG24-3730 p.298, `314`]. *That the SAS and specific kernel
structures sit at particular GDT selectors is `[OBS-RE]` (KDB on the real kernel).* An
application/shared selector is an LDT, ring-3 selector, constructed as `(index << 3) | 7`
(TI = 1, RPL = 3), from a tiled LDT of **up to 8192 descriptors** [DOC-IBM - GG24-3730 section "Address
Conversion and Translation": *"A tiled LDT contains up to 8192 descriptors";* the `| 7` low bits
match IBM's `far16 = MAKEP(HIGH(near32) << 3 + 7, LOW(near32))`, IBM redbook GG24-3730 p.088].
Descriptors for shared objects are inserted downward from the top of the LDT and private-object
descriptors upward from the bottom, mirroring the arena layout [DOC-IBM - same page].

## Segmentation and tiling [DOC-IBM / OBS-RE]

16-bit code addresses memory as **selector:offset**. To let 16-bit and 32-bit code share the same
storage, 16-bit segments are **tiled at 64 KB granularity** - IBM: *"A tiled LDT contains up to 8192
descriptors, where the segment base address in each descriptor is a multiple of 64KB, and each
descriptor therefore points to a 64KB region of memory ... each code or data selector reserves a full
64KB of linear address space."* A flat linear address `L` corresponds to the tiled selector whose
base is `L & ~0xFFFF` with offset `L & 0xFFFF`, i.e. the selector index is a function of the linear
address (`sel = ((L >> 16) << 3) | 7`). This is exactly IBM's arithmetic:
*`near32 = SEL(far16) >> 3 << 16 + OFFSET(far16)`* and
*`far16 = MAKEP(HIGH(near32) << 3 + 7, LOW(near32))`*. A 16:16 far pointer thus converts to a 32-bit
flat pointer, and vice-versa, deterministically; both the LDT entry (16:16) and the page-table entry
(0:32) translate to the same physical memory. The 0x10000 (64 KB) tile granularity is the recurring
unit of the 16-bit segment model. [DOC-IBM - GG24-3730 section "Address Conversion and Translation",
IBM redbook GG24-3730 p.088; glossary "tiled local descriptor table" `362`.]

`DosAllocMem` allocates page-granular memory in the private (or, with the shared flag, shared) arena;
`OBJ_TILE` (`0x00000040`, IBM Toolkit `bsememf.h:55`, in the default `fALLOC` mask) requests
placement in the first 512 MB so the region is addressable by a 16:16 tiled selector for 16-bit
callers - IBM: below the 512 MB line objects *"start on a 64 KB boundary ... and the memory will be
tileable,"* above it they are 4 KB-granular and untileable. [DOC-IBM - `bsememf.h:55`; SMP addendum
section "New OBJ_ANY Memory Attribute", OS/2 Warp Server SMP addendum section 044.]

## See also
- `memory-api.md` - the application-level `Dos*` memory API (`DosAllocMem`, `DosAllocSharedMem`, `DosSetMem`) that allocates within these arenas.
- `infoseg.md` - `DosQuerySysInfo`, whose `QSV_*` fields report the machine-wide storage figures and the per-process address-space figures separately.
