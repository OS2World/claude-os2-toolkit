# OS/2 Information Segments and DosQuerySysInfo

The read-only system and process state OS/2 publishes for applications to query: the **Global
Information Segment (GIS)**, the per-process **Local Information Segment (LIS)**, and the flat
**`DosQuerySysInfo`** surface. Established during kernel initialization (boot sequence Stage 2).

Provenance: **[DOC-IBM]** IBM DDK `infoseg.h` (`COMBASE/DDK/base/h/infoseg.h`, IBM 1992) for the
InfoSeg layouts; IBM Toolkit 4.5 `bsedos.h` for the `DosQuerySysInfo` indices and prototype. IBM
canonical field names.

Ratified (2026-07-26): checked field-by-field against IBM DDK `COMBASE/DDK/base/h/infoseg.h`
(`struct InfoSegGDT` lines 36-115, `struct InfoSegLDT` lines 183-222, `#ifdef SMP` `LIS_pTIB`/
`LIS_pPIB` lines 215-218, `LIS_PT_*`/`LIS_PS_EXITLIST`/`LF_LOG*` lines 254-282), IBM Toolkit 4.5
`bsedos.h` (`QSV_*` 2499-2531, `DosQuerySysInfo` prototype 2610-2613), and the IBM
Toolkit 4.5 import library `os2386.lib` (IMPDEF -> DOSCALLS ordinal 348). SMP-vs-UNI
split corroborated by the OS/2 for SMP book (section DosQuerySysInfo, `QSV_NUMPROCESSORS`
= "Number of processors in the machine"). Every GIS/LIS offset, both structure sizes (0x72 = 114,
36 UNI / 44 SMP), and all 31 QSV indices matched the IBM sources exactly; nothing was corrected.
No IBM primary was found in os2undoc for the InfoSeg (absent - the DDK header remains the source).

## Semantics [DOC-IBM]

- The **GIS** is kept in **two identical copies** - one in the tiled **shared arena** (user-mode
  readable, and therefore potentially overwritable from ring 2) and one in the **system arena**
  (kernel-only). All kernel code maintains both. The clock device driver obtains the read/write
  copy via the DevHlp `GetDOSVar`; all other requestors receive a read-only selector.
  `DosGetInfoSeg` returns a pointer/selector to the shared-arena copy.
- The **LIS** is per-process, in the private arena, **updated at context-switch time**; only the
  currently running process holds the live extra copy.

### How the two GIS copies are kept identical, and the one carve-out  `[OBS-RE]`

**Read the build tag before any address below.** Every address here is from
**`os2krnld`, SMP Astrict (the SMP debug kernel)**, and the cells this mechanism
turns on move between builds: `_Sis2` is at `0002:00002EFE` there and at
`0002:00002EE6` in SMP Hstrict, so `[0x2f04]` - `_Sis2 + 6` in the debug build -
is `SMHotKeyQ + 4` in the base build. The *mechanism* is build-independent; the
numbers are not.

**IBM states the rule and its exception in one paragraph** `[DOC-IBM]`
(`infoseg.h`, above `struct InfoSegGDT`): *"All kernel code (**except the clock
driver**) is responsible for updating BOTH copies of the infoseg. The copy kept
in the system arena is addressable as DOSGROUP:SISData, and the copy in the
shared arena is addressable via a system arena alias. **16:16 and 0:32 pointers
to the alias are stored in `_Sis2`**."*

Both halves of that sentence are load-bearing, and the second one is the trap:
there are **two** ways kernel code reaches the shared-arena copy, and a reading
that follows only the selector misses the other. `_PGInitInfoSegs` writes both
cells, adjacently - `mov [0x22efe],ebx` (the flat pointer) then
`mov [0x22f04],cx` (the selector) - so `_Sis2 + 0` is the 0:32 pointer and
`_Sis2 + 6` is the selector half of the 16:16 pointer.

**At boot the alias is seeded by one whole-segment copy**, in
`h_SYIInitOS2_Part2` (`0012A2E0`-`0012A47C`), after its call to
`syiInitOS2Components` and before `syiDiscardDosHlp`:

```
0012A3B2  mov es,[0x2f04]     ; ES = the GIS alias selector  (_Sis2+6)
0012A3B6  xor di,di
0012A3B8  mov si,0x280        ; source = _SISData  (DS = 0x17 -> flat 0x20280)
0012A3BB  mov cx,0x1c
0012A3BE  rep movsd           ; 28 dwords = 112 bytes
0012A3C1  mov cx,0x2
0012A3C4  rep movsb           ; + 2 bytes  =  114 = 0x72 = sizeof(InfoSegGDT)
0012A3C6  mov es,[0x2f10]     ; and the LIS alias selector   (_Lis2+6)
0012A3CA  xor di,di
0012A3CC  mov si,0xffc2
0012A3CF  mov cx,0xb
0012A3D2  ss rep movsd        ; 11 dwords = 44 bytes = the SMP InfoSegLDT
```

**This runs once, on the SYSINIT path, and never again.** It is not a
reconciler, and nothing in the kernel lazily reconciles the two copies at
runtime: IBM's rule holds exactly as written, and the runtime writers below each
write both cells themselves.

**The exception IBM names - the clock driver - is implemented by the kernel
doing the alias half on the driver's behalf, at two sites.** IBM states the
driver's own half three lines above the paragraph quoted opposite `[DOC-IBM]`
(`infoseg.h:21-23`): *"The actual table is statically defined in SDATA.ASM.
Ring 0, read/write access is obtained by the clock device driver using the
DevHlp GetDOSVar function. (GetDOSVar returns a ring 0, read-only selector to
all other requestors.)"* So after the clock driver has had a chance to move the
time, the kernel copies the time/date/version prefix across.

**How `GetDOSVar` tells the clock driver apart - because IBM's reference page
for it does not** `[OBS-RE]`. `PDD/00245.HTM` lists index 1 as
`GlobalInfoSeg:WORD` and calls the set *"read only variables"* twice; it has no
read/write index, and it does not mention the clock at all. The read/write
answer is a **private index the kernel substitutes and a caller cannot ask
for**. `GetDOSVar` (`0003:1340`) bounds the index at the door and then, for
index 1 and only index 1, may rewrite it:

```
00031345  3C15        cmp al,0x15
00031347  0F83B900    jae 0x31404          ; >= 0x15 is REFUSED, so 0x15 itself
                                           ;   is unreachable from outside
...
00031369  3C01        cmp al,1
0003136B  751A        jne 0x31387          ; any other index -> straight to the table
0003136D  BB1700      mov bx,0x17
00031370  8EDB        mov ds,bx
00031372  C51EA032    lds bx,[0x32a0]      ; DS:BX = BClock, a 16:16 far pointer
00031376  8B5F12      mov bx,[bx+0x12]
00031379  8B7E00      mov di,[bp]          ; the caller's saved frame
0003137C  368BBD0E00  mov di,ss:[di+0xe]
00031381  3BDF        cmp bx,di
00031383  7502        jne 0x31387
00031385  B015        mov al,0x15          ; 21 - the index IBM does not publish
00031387  ...         xor ah,ah / mov bx,ax / shl bx,1 / mov bx,[bx+0x2940]
```

The two table entries it selects between, read out of the data image:

| index | `[0002:2940 + i*2]` | symbol | image value of that cell |
|---|---|---|---|
| 1 | `0x00A6` | `_SysInfoSeg` (WORD) | `0x0000` - filled at run time |
| `0x15` = 21 | `0x2F16` | `rwSysInfoSeg` (WORD) | `0x0080` - **statically initialised** |

`0x0080` is `GDT_SYSINFOSEG`. The `.MAP`'s segment `0007` *is* the GDT, with
offset = selector value: `GDT` at 0, 193 symbols at 8-byte spacing, `GDT_GDT`
`0x08`, `GDT_SAS` `0x70`, `GDT_SYSINFOSEG` `0x80`. So the carve-out is a
private index handing back a **GDT** selector - and it is a different cell from
the alias selector this section otherwise turns on, `_Sis2 + 6` (`0002:2F04`),
which is `0x0000` in the image and is written at boot by `_PGInitInfoSegs`.
That is the evidence for "the clock driver never sees the alias", which IBM
does not state anywhere.

**Three bounds, stated because none of them is established here**
(a citation covers exactly what was read):
- **What the two compared words are is NOT decoded.** `[BClock + 0x12]` and
  `[[bp] + 0x0e]` are what the instructions address; that one is the clock's
  data segment and the other the caller's would be a reasonable guess and is
  not claimed.
- **That `GDT_SYSINFOSEG`'s descriptor covers the system-arena copy follows
  from IBM's prose, not from this read.** `SDATA.ASM` = `DOSGROUP:SISData` =
  the system-arena copy, per the two `infoseg.h` quotations above. The
  descriptor's base is built at boot and was not traced; settling it means
  finding the writer of that GDT entry.
- **A byte census will not settle it, and that is measured.** `rwSysInfoSeg`'s
  own address occurs **nowhere** in code: `16 2F` and `16 2F 02 00` over all
  eight executable objects of this image (3, 4, 9, 13, 14, 15, 16, 17, filtered
  by the image's own object table) return **0 and 0**. The table at
  `0002:2940` is its only reader. Both sites are
gated on `SDevAtt & DEV_CLOCK` (`0x0008` - `devhdr.inc` `SysDev`, `devhdr.h:72`)
`[DOC-IBM]`, and both copy **exactly `0x00`-`0x17`**, i.e. everything below
`SIS_CurScrnGrp`:

| site | when | gate |
|---|---|---|
| `cpu_stint` (`00139512`-`0013965A`, `dev\int.asm`) at `0013963B` | after dispatching an interrupt to a handler whose own data segment is not the kernel's `0x53` | `test word [fs:0x4],0x8`, `FS` = the handler's data segment (`[edi+0x8]` of the chain node - the same selector the dispatcher loads into `DS` before calling it) |
| `DevIOCall` (`000309B1`-) at `00030B4E` | after a Strategy call whose `PktCmd` (`[es:bx+0x2]`) is `CMDOUTPUT` (8) or `CMDOUTPUTV` (9) | `test word [si+0x4],0x8`, `DS:SI` = the device header the caller passed in |

```
0013963B  mov esi,0x20280         ; _SISData
00139640  mov edi,[dword 0x22efe] ; [_Sis2+0] -- the 0:32 pointer, NOT the selector
00139646  mov ecx,0x6
0013964B  rep movsd               ; 6 dwords = 24 bytes = 0x00..0x17
```

> **`DevIOCall`'s address read `00030B4F` until 2026-09-19, one byte inside its
> own instruction, and that is not a typo class** (Rule 1.7). The
> instruction is at `00030B4E` and is six bytes,
> `64 66 8B 3E FE 2E` = `mov edi,fs:[0x2efe]`. Disassembling at the cited
> `...4F` consumes the five bytes after the `0x64` and yields
> `66 8B 3E FE 2E` = `mov edi,[0x2efe]` - **a well-formed instruction, with the
> same mnemonic, the same register and the same displacement, differing only in
> that the `FS` override is gone.** So the wrong address does not fail; it hands
> the next reader a segment-less read of a *kernel-DS* cell in a routine whose
> whole point is that `FS` was just loaded with `0x17` two instructions earlier
> (`00030B4C mov fs,ax`). Almost certainly produced by a byte search for
> `66 8B 3E FE 2E` that matched inside the prefixed form - Rule 2.7's shape,
> where the pattern is a proxy for the instruction.
>
> **The rule this yields: round-trip every cited address through a
> disassembler, from the containing symbol, before writing it.** Done for this
> section on 2026-09-19: the other sixteen code addresses it cites
> (`0012A3B2`...`0012A3D2`, `0013963B`/`40`/`46`/`4B`, and the `GetDOSVar` block
> below) are all instruction boundaries; this was the only one that was not.

Offset `+0x4` of a PDD's data segment is `SDevAtt` because IBM requires the
device header at the start of it `[DOC-IBM]` (`PDD/00017.HTM`: *"the device
header must be located at the beginning of the file"*, which is why the data
segment must be the first segment); that is what lets `cpu_stint` read the
attribute word straight out of the handler's `DS` without a header pointer.

**What a reimplementation owes.** Keep the two copies coherent field by field at
the moment of the write - that is what IBM's own code does - and reproduce the
one asymmetry: the clock's time/date fields are published by the *kernel*, after
the driver returns, and nothing else in the segment is ever published that way.

### `SIS_CurScrnGrp` (`+0x18`) - the complete writer set, by census  `[OBS-RE]`

Same build (`os2krnld` SMP Astrict). Censused over all **eight executable
objects** - the image's own object table marks the other nine non-executable,
and excluding them is load-bearing: the byte pattern for the `_SISData` store
also occurs twice inside the `RW-` data object at `0xd471c`/`0xd4848`, where it
is data.

Both access paths were enumerated, because IBM documents both (above): every
reference to the selector cell (`[0x2f04]` / `[0x22f04]`, **14 sites**) and every
reference to the flat pointer (`[0x2efe]` / `[0x22efe]`, **7 sites**); and, on
the other side, every store to `_SISData + 0x18` (`0x298` / `0x20298`, in all the
`mov`-to-memory encodings - **2 sites**, both of them in the table below).

| writer | kernel-data copy `_SISData+0x18` | shared-arena copy `+0x18` |
|---|---|---|
| `h_w_DosSGSwitch` (`#54`) | `00108E57  mov [0x298],al` | `00108E5A  mov fs,[0x2f04]` / `00108E5E  mov [fs:0x18],al` |
| `h_w_DosSGSwitchMe` (`#55`), **only when `BX == 0`** | `00108EE5`, same pair | `00108EE8`, same pair |
| `h_SYIInitOS2_Part2`'s boot copy | - | seeds it once from `_SISData`, at boot only |

**There is no other writer, by either path.** The other selector-cell sites are:
three `lock`ed bit operations on `SIS_SysLog` (`+0x48`) at `000318A9`/`000318BF`/
`000318F3`; one `mov [fs:0xc],bx` on `SIS_TimeZone` at `00034C57`; two sites on
`SIS_FgndPID` (`+0x1c`) - `_schSetKbdLocus` at `0013C770` and the zeroing site at
`0010C4FB`; three copies into the MEC tables - a fixed 32 bytes into `+0x26` at
`00122DC1` and two caller-sized copies, into `+0x26` at `0014659D` and into
`SIS_perf_mec_table` (`+0x52`) at `00146515`; the boot copy; `_PGInitInfoSegs`
writing the cell itself at `002079E3`; and one site that does not touch the
segment at all - `0012E2FF` loads the selector *value* into `BX` and clears the
DPL bits of its GDT descriptor (`and byte [bx+0x5],0x9f`).

The flat-pointer sites are the two clock copies above (`cpu_stint`, `DevIOCall`),
`INITTIME` writing `SIS_ProtMdOnly` at `00156CDF` (`mov [ecx+0x1b],al`, having
loaded `ecx` from `[0x22efe]`), `_PGSwitchContext` writing two dwords at `+0x72`
and `+0x76` - **past the end of `InfoSegGDT`**, which this document does not
describe - `_PGInitInfoSegs` writing the pointer cell, and two readers:
`_THEGlobalInfoSeg_get`, which copies the segment out to a caller buffer, and
`_smSIOInit`, which reads `SIS_BootDrv` (`+0x24`).

**Consequence, and it is the reason the census was worth doing.**
`SIS_CurScrnGrp` moves only when a screen-group *switch* moves it. No scheduler
path, no focus path and no clock path touches it - in particular
`_schSetKbdLocus`, which does publish `SIS_FgndPID`, leaves `+0x18` alone, so the
two fields are allowed to name a process and a screen group that do not
correspond.

**Bounds, stated because a negative closes a question.** This censuses
*references to the two pointer cells*. A routine handed the selector or the flat
pointer in a register by a caller would not appear; none of the 21 sites passes
either value on, and the only routine that exposes the segment to anyone else is
`_THEGlobalInfoSeg_get`, which hands out a **copy**. It is also a byte census
over one build, so it is evidence about what that kernel does and not proof about
the family; the two `#54`/`#55` writers were then read end to end, and the boot
copy's containing routine was read from its entry.

### `SIS_CurScrnGrp` and `SIS_FgndPID` - the READER census, and what each reader keys on  `[OBS-RE]`

**Added 2026-09-20.** The writer census above answers *who moves these fields*.
It does not answer the question that decides whether a reimplementation may skip
a write: **what reads them, and what breaks when the value is stale.** Same
build, same method - every reference to the selector cell and to the `0:32`
pointer, over the eight executable objects, plus the shipped
`DOSCALL1.DLL` read for its own accesses.

**`SIS_CurScrnGrp` is a dispatch key in three subsystems, not reportage.**

| reader | copy read | what it does with it |
|---|---|---|
| `PostSigFocus` | `_SISData+0x18` | `mov bl,[0x298]` / `shl bx,2` / `add bx,dx` / `mov dx,[bx+0x2e24]` - it **indexes the `SigFocus` table by screen group**, four bytes per group, one word slot selected by `dx` (`0` for signal 1, `2` for signal 4). A zero slot falls through to `KSGKillProcess`; a non-zero one gets the signal. A process registers *its own* slot from **its own** `LIS_CurScrnGrp` (the PTDA's `+0x73a`, `shl 2`), so **a stale global byte misroutes Ctrl-C and Ctrl-Break.** |
| `KSGKillProcess` | `_SISData+0x18`, and `+0x19` `SIS_MaxScrnGrp` | `cmp dx,4 / jc exit` and `cmp dl,[0x299] / jnc exit` - it refuses to act when the current screen group is **below 4** or **at or above `SIS_MaxScrnGrp`**. So the four system screen groups (`0` hard-error pop-ups, `1` shell, `2` real mode, `3` VioPopUp) are exempt from Ctrl-Break kill **by construction**, not by policy. |
| `DOSCALL1`'s `DOSSMGSWITCH` | the shared copy, through a selector the session manager caches at init under IBM's own name `GlobalSelector` | `mov gs,[GlobalSelector]` / `mov al,[gs:0x18]` - **the first act of the switch orchestrator, and it resolves the OUTGOING session's control block.** This is what makes publishing load-bearing rather than cosmetic: a switch that does not publish leaves the *next* switch saving the wrong session's screen. |
| `DOSCALL1`'s `KbdSetFgnd` | the shared copy, through a far pointer IBM names `_global_info` | reads `+0x18` and compares it against a screen group held in the keyboard subsystem's own per-session record; **`447 ERROR_KBD_KEYBOARD_BUSY` if they differ.** It then reads `+0x1c` and compares it against that record's process id, **returning success having done nothing** if they already match. `[DOC-IBM]` the Toolkit declares this call `KbdSetFgnd(VOID)` - it takes no arguments at all, so these two fields are the whole of its input besides that record. |

There are **no other readers of `+0x18` in either image**: three references in the
kernel's 16-bit objects (two of them the `#54`/`#55` stores, and the reads above),
and in `DOSCALL1.DLL` exactly three accesses through `GlobalSelector` - the
switch orchestrator's read, the session manager's initialisation, and a routine
that only loads the two InfoSeg selectors into segment registers for its
caller - plus three through `_global_info`, all inside `KbdSetFgnd`.

**And the two KERNEL words behind `QSV` 24 and 25 have their own, much shorter
reader set**, which is why they cannot be answered out of an info segment:
`_FgndSGID` is read by `_VR32QuerySysInfo` (index 24), by the window-boost
routine `_schWindowBoost`, and twice inside its own writer; `_tkFgndPID` is read
by `_VR32QuerySysInfo` (index 25) and by nothing else. Censused over the whole
32-bit kernel object. The disjoint-writer consequence of that is "How
`DosQuerySysInfo` is answered" below, and is not restated here.

**Bound, same as the writer census:** this counts references to the two pointer
cells. A routine handed the selector in a register by a caller does not appear,
and one of the three `DOSCALL1` sites does exactly that, so a reader reached
that way is outside this census.

### `SIS_FgndPID` is zeroed on process termination; `_tkFgndPID` is not  `[OBS-RE]`

`f_ProcessTerminate` loads the terminating process's own pid from its PTDA and
then, with the kernel data selector:

```
cmp ax,[MUF_Pid]  ; clear it if it named this pid
cmp ax,[HDE_Pid]  ; clear it if it named this pid
cmp ax,[0x29c]    ; _SISData + 0x1c -- the kernel-data copy of SIS_FgndPID
     mov word [0x29c],0
     mov fs,[the Global InfoSeg selector cell]
     mov word [fs:0x1c],0
```

So when the **foreground process** dies, `SIS_FgndPID` becomes **0 in both
copies** - *"no foreground process"* - and **no successor is chosen at this
layer**. `SIS_CurScrnGrp` is not touched: the screen group outlives the process.

**`_tkFgndPID` is not cleared there, and THAT is the whole of what this section
adds.** The disjoint-writer half is not new and is not restated here: "How
`DosQuerySysInfo` is answered" below already establishes that `_tkFgndPID` has
one writer (`_schSetKbdLocus`, the instruction after the `SIS_FgndPID` store),
that `_FgndSGID` has one (`_schSetScreenGroupFgnd`), and that `_VR32QuerySysInfo`
only reads them. **What that block could not know is that the pairing BREAKS**,
and this is where: it calls index 25 *"incidentally safe, because
`_schSetKbdLocus` writes `_tkFgndPID` and `SIS_FgndPID` in the same breath - a
coincidence of one writer, not a maintained invariant"*, and `f_ProcessTerminate`
is a **second** writer of `SIS_FgndPID` that is not a writer of `_tkFgndPID`.

**Consequence:** between the death of a foreground process and the next
`DosSetFgnd` scope-0 call, the Global InfoSeg reports **no** foreground process
while `DosQuerySysInfo(QSV_FOREGROUND_PROCESS)` still reports the **dead** one.
An implementation that answers index 25 out of `SIS_FgndPID` is answering a
different question, and the two answers separate at exactly that moment.

**`_schSetKbdLocus` also uses the kernel-data copy as working state**, which is
why that copy is not a mirror: it `LOCK`-exchanges the new pid into
`_SISData+0x1c` and reads back the old one, and *that* is how it knows whose
`LIS_Fgnd` to clear. It then writes `LIS_Fgnd` through the **Local** InfoSeg
alias (`0` for the outgoing process, `0xFFFF` for the incoming), and the matching
`+0x73e` word in each PTDA, and broadcasts both across the per-CPU control
blocks. A decompile of this routine renders both aliases as one segment; the
disassembly shows two distinct selector loads, the Global one for `+0x1c` and the
Local one for `+0xc`.

The whole sequence these fields sit in - five quantities, which call writes each,
and in what order on each path - is in `session-manager.md`, "The complete
foreground contract".


## Global Information Segment - `InfoSegGDT`, 114 bytes (0x72) [DOC-IBM]

| Off | Field | Type | Meaning |
|---|---|---|---|
| 0x00 | `SIS_BigTime` | ULONG | time in seconds since 1970-01-01 |
| 0x04 | `SIS_MsCount` | ULONG | free-running millisecond counter |
| 0x08 | `SIS_HrsTime` / `SIS_MinTime` / `SIS_SecTime` / `SIS_HunTime` | 4xUCHAR | hours / minutes / seconds / hundredths |
| 0x0C | `SIS_TimeZone` | USHORT | minutes from GMT (set to EST) |
| 0x0E | `SIS_ClkIntrvl` | USHORT | timer interval, units of 0.0001 s |
| 0x10 | `SIS_DayDate` / `SIS_MonDate` | 2xUCHAR | day (1-31) / month (1-12) |
| 0x12 | `SIS_YrsDate` | USHORT | year (>= 1980) |
| 0x14 | `SIS_DOWDate` | UCHAR | day of week (1-1-80 = Tue = 3) |
| 0x15 | `SIS_VerMajor` / `SIS_VerMinor` / `SIS_RevLettr` | 3xUCHAR | major / minor version, revision letter (20 / 45 = Warp 4.5) |
| 0x18 | `SIS_CurScrnGrp` | UCHAR | foreground screen-group number |
| 0x19 | `SIS_MaxScrnGrp` | UCHAR | maximum number of screen groups |
| 0x1A | `SIS_HugeShfCnt` | UCHAR | shift count for huge segments |
| 0x1B | `SIS_ProtMdOnly` | UCHAR | protect-mode-only indicator |
| 0x1C | `SIS_FgndPID` | USHORT | foreground process id |
| 0x1E | `SIS_Dynamic` | UCHAR | dynamic-priority-variation flag |
| 0x1F | `SIS_MaxWait` | UCHAR | maxwait (seconds) |
| 0x20 | `SIS_MinSlice` / `SIS_MaxSlice` | 2xUSHORT | minimum / maximum timeslice (ms) |
| 0x24 | `SIS_BootDrv` | USHORT | drive the system was booted from (1 = A) |
| 0x26 | `SIS_mec_table[32]` | 32 B | RAS Major Event Code table |
| 0x46 | `SIS_MaxVioWinSG` / `SIS_MaxPresMgrSG` | 2xUCHAR | max VIO-windowable / Presentation-Manager screen groups |
| 0x48 | `SIS_SysLog` | USHORT | error-logging status (`LF_LOGENABLE` 0x01, `LF_LOGAVAILABLE` 0x02) |
| 0x4A | `SIS_MMIOBase` | USHORT | memory-mapped-I/O selector |
| 0x4C | `SIS_MMIOAddr` | ULONG | memory-mapped-I/O address |
| 0x50 | `SIS_MaxVDMs` | UCHAR | max Virtual DOS Machines |
| 0x51 | `SIS_Reserved` | UCHAR | - |
| 0x52 | `SIS_perf_mec_table[32]` | 32 B | performance MEC table (added 1997) |

Total 0x72 = 114 bytes.

## Local Information Segment - `InfoSegLDT`; 36 bytes UNI, **44 bytes SMP** [DOC-IBM]

Per-process; the SMP kernel appends `LIS_pTIB` / `LIS_pPIB` (IBM DDK `infoseg.h`, `#ifdef SMP`).

| Off | Field | Type | Meaning |
|---|---|---|---|
| 0x00 | `LIS_CurProcID` / `LIS_ParProcID` | 2xUSHORT | current / parent process id |
| 0x04 | `LIS_CurThrdPri` / `LIS_CurThrdID` | 2xUSHORT | current thread priority / thread id |
| 0x08 | `LIS_CurScrnGrp` | USHORT | screen group |
| 0x0A | `LIS_ProcStatus` | UCHAR | process-status bits (`LIS_PS_EXITLIST` 0x01) |
| 0x0B | `LIS_fillbyte1` | UCHAR | filler |
| 0x0C | `LIS_Fgnd` | USHORT | process is in foreground |  *(see the measured section below - IBM's Toolkit calls this **keyboard focus**)*
| 0x0E | `LIS_ProcType` | UCHAR | 0 full-screen / 1 real-mode / 2 VIO-windowable / 3 Presentation Manager / 4 detached |
| 0x0F | `LIS_fillbyte2` | UCHAR | filler |
| 0x10 | `LIS_AX`...`LIS_DS` | 7xUSHORT | .EXE-derived: environment selector, command-line offset, data-segment length, STACKSIZE, HEAPSIZE, module handle, data-segment handle |
| 0x1E | `LIS_PackSel` / `LIS_PackShrSel` / `LIS_PackPckSel` | 3xUSHORT | first tiled / above-shared-arena / above-packed-arena selector |
| **0x24** | **`LIS_pTIB`** | ULONG | **[SMP] flat pointer to the current TIB** |
| **0x28** | **`LIS_pPIB`** | ULONG | **[SMP] flat pointer to the PIB** |

UNI ends at 0x24 (36); SMP ends at 0x2C (44).

## `DosQuerySysInfo` - QSV indices 1-31 [DOC-IBM]

`DosQuerySysInfo` - prototype `APIRET APIENTRY DosQuerySysInfo(ULONG iStart, ULONG iLast, PVOID
pBuf, ULONG cbBuf)` (IBM Toolkit 4.5 `bsedos.h:2610-2613`); imported by ordinal **348** from
module **DOSCALLS** (IBM Toolkit 4.5 `os2386.lib`, OMF IMPDEF record: internal name
`DosQuerySysInfo`, module `DOSCALLS`, import-by-ordinal 348). On Warp 4.5 `QSV_MAX =
QSV_INT10ENABLED = 31` (`bsedos.h:2530-2531`); the Warp-v3 Toolkit stops at 25.

| # | Name | Meaning / units |
|---|---|---|
| 1 | `QSV_MAX_PATH_LENGTH` | maximum path length |
| 2-4 | `QSV_MAX_TEXT_SESSIONS` / `MAX_PM_SESSIONS` / `MAX_VDM_SESSIONS` | session limits |
| 5 | `QSV_BOOT_DRIVE` | 1 = A, 2 = B, ... |
| 6 | `QSV_DYN_PRI_VARIATION` | 0 = absolute, 1 = dynamic |
| 7 | `QSV_MAX_WAIT` | seconds |
| 8-9 | `QSV_MIN_SLICE` / `MAX_SLICE` | milliseconds |
| 10 | `QSV_PAGE_SIZE` | bytes |
| 11-13 | `QSV_VERSION_MAJOR` / `_MINOR` / `_REVISION` | version, revision letter |
| 14 | `QSV_MS_COUNT` | free-running millisecond counter |
| 15-16 | `QSV_TIME_LOW` / `TIME_HIGH` | low / high dword of time in seconds |
| 17-19 | `QSV_TOTPHYSMEM` / `TOTRESMEM` / `TOTAVAILMEM` | physical / resident / available-for-all-processes memory |
| 20-21 | `QSV_MAXPRMEM` / `MAXSHMEM` | available private / shared memory for the calling process |
| 22 | `QSV_TIMER_INTERVAL` | **tenths of a millisecond** |
| 23 | `QSV_MAX_COMP_LENGTH` | max length of one path component |
| 24-25 | `QSV_FOREGROUND_FS_SESSION` / `FOREGROUND_PROCESS` | foreground session id / process id |
| 26 | `QSV_NUMPROCESSORS` | processor count (an SMP kernel on one CPU reports 1) |
| 27-28 | `QSV_MAXHPRMEM` / `MAXHSHMEM` | high (> 512 MB) private / shared memory |
| 29 | `QSV_MAXPROCESSES` | maximum processes |
| 30 | `QSV_VIRTUALADDRESSLIMIT` | virtual-address limit |
| 31 | `QSV_INT10ENABLED` | INT 10h (VGA BIOS) video enabled |

## How `DosQuerySysInfo` is answered - the QSV table is a copy of the GIS  `[OBS-RE]`

The index list above says what each index *means*. This section says where the
kernel gets the values, which is a different question and one the table alone
does not answer. Established 2026-08-26 by reading IBM's own kernel; the RE
corpus's ~45 write-ups cover none of this (searched - see "Negative results"
below), so it is recorded here so nobody derives it twice.

**`DosQuerySysInfo` is a table copy.** `_VR32QuerySysInfo` validates, refreshes
a handful of live cells, then block-copies out of a static array:

```c
/* _VR32QuerySysInfo, os2krnl obj 0x00165de0 */
if ((iLast < iStart) || (iStart < 1) || (0x20 < iLast))  return 0x57;  /* 87  */
if (cbBuf < (iLast - iStart + 1) * 4)                    return 0x6f;  /* 111 */
...
_TKSuBuff(pBuf, &_aulSysInfo + (iStart-1)*4, (iLast-iStart+1)*4, 0x83);
```

Three things follow that are not visible from the index list:

1. **Index *N* lives at `_aulSysInfo + (N-1)*4`.** The arithmetic is the check
   on itself: every one of the 31 indices lands on a cell whose initialiser
   matches its documented meaning.
2. **The validation order is range, then buffer size, then nothing.** `pBuf` is
   reached only by the trailing `_TKSuBuff`, i.e. a bad pointer **faults**
   rather than returning an rc - measured, `RC=139`, and the reason `cbBuf = 0`
   on a valid range answers **111**, not 87.
3. **The accepted range is 1...32, one past `QSV_MAX`.** `0x20 < iLast` is the
   only upper bound. Index 32 reads a cell `_tkInitSysInfo` never writes and
   measures as `rc=0, value 0`; index 33 answers 87. Treat 32 as an off-by-one
   in IBM's validation, **not** as a 32nd index - no IBM source names one.

**`_tkInitSysInfo` fills that table at boot, mostly from the Global InfoSeg.**
This is the load-bearing part: several QSV answers are not independent values
at all, they are copies of `SIS_*` fields, so the two surfaces cannot disagree
on a correct implementation.

| QSV | source in `_tkInitSysInfo` | = GIS field |
|---|---|---|
| 1 `MAX_PATH_LENGTH` | literal `0x104` = 260 | - |
| 2 `MAX_TEXT_SESSIONS` | `[_SISData+0x46]` | **`SIS_MaxVioWinSG`** |
| 3 `MAX_PM_SESSIONS` | `[_SISData+0x47]` | **`SIS_MaxPresMgrSG`** |
| 4 `MAX_VDM_SESSIONS` | **`__MaxProcesses`** | **NOT `SIS_MaxVDMs`** - see below |
| 5 `BOOT_DRIVE` | `[_SISData+0x24]` | `SIS_BootDrv` |
| 6 `DYN_PRI_VARIATION` | `[_SISData+0x1E]` | `SIS_Dynamic` |
| 7 `MAX_WAIT` | `[_SISData+0x1F]` | `SIS_MaxWait` |
| 8 `MIN_SLICE` | `[_SISData+0x20]` | `SIS_MinSlice` |
| 9 `MAX_SLICE` | `[_SISData+0x22]` | `SIS_MaxSlice` |
| 10 `PAGE_SIZE` | literal `0x1000` = 4096 | - |
| 11-13 version | `[_SISData+0x15/0x16/0x17]`, revision `<< 16` | `SIS_VerMajor` / `VerMinor` / `RevLettr` |
| 14 `MS_COUNT` | live per call, `[_SISData+0x04]` | **`SIS_MsCount`** |
| 15 `TIME_LOW` | live per call, `_SISData+0x00` | **`SIS_BigTime` - SECONDS since 1970** |
| 16 `TIME_HIGH` | literal **0**, never refreshed | - |
| 17 `TOTPHYSMEM` | `(_pgHighPages + _pgPhysPages) * 4096` | - |
| 18 `TOTRESMEM` | live, `_pgResidentPages << 12` | - |
| 19 `TOTAVAILMEM` | live, `_PGAllocSizeQuery` | - |
| 20 / 21 | live, `_VMQueryArenaAvailMem(0x2000000 / 0x4000000)` | - |
| 22 `TIMER_INTERVAL` | `[_SISData+0x0E]` | **`SIS_ClkIntrvl`** |
| 23 `MAX_COMP_LENGTH` | literal `0xFF` = 255 | - |
| 24 / 25 foreground | live, `_FgndSGID` **and `_tkFgndPID`** - two separate words | **NEITHER - see the correction below** |
| 26 `NUMPROCESSORS` | a kernel global, refreshed | - |
| 27 / 28 high arenas | live, `_VMQueryArenaAvailMem(0x2008000 / 0x4008000)` | - |
| 29 `MAXPROCESSES` | **`__MaxProcesses`** | - |
| 30 `VIRTUALADDRESSLIMIT` | `_VirtualAddressLimit >> 20` (i.e. **MB**) | - |
| 31 `INT10ENABLED` | literal **1**, unconditional | - |

> **CORRECTED 2026-09-19 (Rule 1.7) - ROW 24/25 WAS WRONG IN BOTH OF
> ITS COLUMNS, AND THE SECOND ERROR IS THE EXPENSIVE ONE.**  The row read
> *"live, `_FgndSGID` low / high word"* against *"`SIS_CurScrnGrp` /
> `SIS_FgndPID`"*.
>
> **They are two separate symbols, not two halves of one dword.**  `_FgndSGID`
> and `_tkFgndPID` are adjacent 16-bit kernel data words, and
> `_VR32QuerySysInfo` reads each with its own instruction and zero-extends it
> into its own dword slot.  Read in the base build, where the symbol arithmetic
> is checkable end to end (`_aulSysInfo` = `0x000ddf88`, so index *N* at
> `+ (N-1)*4` puts 24 at `0xddfe4` and 25 at `0xddfe8`):
>
> ```
> 00165E51  33C0          xor eax,eax        ; <- the zero-extend, ONCE, for BOTH
> 00165E53  66A1E8290D00  mov ax,[0xd29e8]   ; _FgndSGID
> 00165E59  A3E4DF0D00    mov [0xddfe4],eax  ; QSV 24
> 00165E5E  66A1EA290D00  mov ax,[0xd29ea]   ; _tkFgndPID
> 00165E64  837D5014      cmp [ebp+0x50],0x14 ; unrelated, interleaved
> 00165E68  A3E8DF0D00    mov [0xddfe8],eax  ; QSV 25
> ```
>
> > **Printed whole 2026-09-19 (Rule 1.7), because the earlier two-line
> > rendering omitted the instruction that makes its own claim true.** It showed
> > only the `mov ax` / `mov ...,eax` pairs and said the reads *zero-extend*.
> > `mov ax` does not zero the upper half of `EAX`; `xor eax,eax` at
> > `00165E51` does, and it was not in the quotation. It also matters **where**
> > it is: it executes **once, ahead of both loads**, so QSV 25's upper half is
> > zero only because nothing between `00165E51` and `00165E68` disturbs it -
> > a dependency the two-line form hid, and one that an implementer copying the
> > excerpt would not reproduce. The `->` arrows also implied adjacency the
> > bytes do not have: `00165E64` sits between the second load and its store.
>
> Confirmed independently in the debug build, where every address differs and
> the arithmetic still lands: `_aulSysInfo` = `0x000ecfcc` -> 24 at `0xed028`,
> 25 at `0xed02c`.  **The "low / high word" reading is an artefact of the two
> symbols being two bytes apart** - `_FgndSGID` and `_tkFgndPID` are adjacent in
> both builds (`0xd29e8`/`0xd29ea` base, `0xd44c4`/`0xd44c6` debug).
>
> **AND THE "= GIS field" COLUMN IS REFUTED, WHICH IS WHY THIS SECTION'S OWN
> TITLE OVERSTATES.**  `_VR32QuerySysInfo` (`00165DE0`-`0016604F` in the base
> build, its whole body to the `int3` padding) makes **zero** `fs:` accesses, so
> these two answers never touch an info segment.  They are not copies of `SIS_CurScrnGrp` / `SIS_FgndPID`, and for
> index 24 they cannot be, because **the two values have disjoint writers**:
>
> | value | written by | behind the `sgspid` latch? |
> |---|---|---|
> | `SIS_CurScrnGrp` (GIS `+0x18`) | `h_w_DosSGSwitch` and `h_w_DosSGSwitchMe` - the only *runtime* writers, plus the boot-time bulk copy in `h_SYIInitOS2_Part2` documented above | yes |
> | `_FgndSGID` (QSV 24's source) | `_schSetScreenGroupFgnd` - **its only writer** | no |
>
> > **BOTH CELLS OF THAT COLUMN WERE RE-CITED 2026-09-19 (Rule 1.7), AND THE
> > SECOND ONE HAD NO CITATION AT ALL.** It read *"`#101 DosSetFgnd` scope 3,
> > **only**"*. The `[OBS-RE]` tag on this block covers a byte census, and a
> > census finds *symbols*, not ordinals - so the ordinal half was carried from
> > the brief that commissioned the work, and the notes it came from say that
> > sentence described a different implementation's code, not IBM's, and was
> > never checked against IBM's.
> >
> > **What IS measured, in both SMP builds, and is what the row now says.**
> > Ghidra merges the two adjacent words into one 4-byte `_FgndSGID`, so the low
> > half (`._0_2_`) is `_FgndSGID` and the high half (`._2_2_`) is `_tkFgndPID`.
> > Four routines reference the pair in the base build and exactly one **writes
> > the low half** - `_schSetScreenGroupFgnd` (`0013B4A0` base / `0013C8F8`
> > debug), `_FgndSGID._0_2_ = (short)param_1`. `_schSetKbdLocus` writes only
> > `._2_2_` and `SIS_FgndPID` (`DAT_0002029c` = `_SISData + 0x1c`), which is the
> > coincidence of one writer this block relies on for index 25;
> > `_schInitTCB` only compares; `_VR32QuerySysInfo` only reads.
> >
> > **The ordinal is left unestablished on purpose, and the next step is named.**
> > A `CALL rel32` census over the 32-bit executable objects finds **one** caller
> > in each build - `0013194C` base, `00132255` debug - and the nearest preceding
> > map symbol to both is `_StartTHUNK_TEXT`, with the debug build's single
> > absolute reference sitting in `_ThunkTable` (`000C19DC`). So it is the 32-bit
> > body behind a 16-bit entry, reached through the kernel's thunk table, which
> > is why no named caller exists and why a census cannot name the ordinal.
> > Settling it means decoding that thunk-table entry, not another census.
>
> **So there is NO IBM invariant between `QSV 24` and `SIS_CurScrnGrp`.**  A
> `#54`/`#55` switch moves the GIS field and leaves `QSV 24` alone; a `#101`
> scope-3 call does the reverse.  An implementation that answers `QSV 24` from
> the GIS field is not merely unsourced - it is answering a different question,
> and the two diverge the moment a guest calls `#55`.  This is the switch-vs-
> screen-group decoupling, surfacing in the QSV table.  Index 25 is incidentally
> safe, because `_schSetKbdLocus` writes
> `_tkFgndPID` and `SIS_FgndPID` in the same breath - but that is a coincidence
> of one writer, not a maintained invariant.
>
> > **QUALIFIED 2026-09-20 (Rule 1.7) - and the correction is ABOVE, not here.**
> > The coincidence does not merely fail to be an invariant; it **ends**, at a
> > nameable moment. `f_ProcessTerminate` is a second writer of `SIS_FgndPID`
> > (it zeroes it, in both copies) and is not a writer of `_tkFgndPID`, so from
> > the death of a foreground process until the next `DosSetFgnd` scope-0 call
> > the two disagree by construction. Read
> > "`SIS_FgndPID` is zeroed on process termination; `_tkFgndPID` is not",
> > above. Nothing else in this block changes: the disjoint-writer finding for
> > index 24 and the `_aulSysInfo` arithmetic stand as written.
>
> `[OBS-RE]`, both SMP builds, 2026-09-19.  The table base is what makes this
> checkable rather than a plausible reading of two adjacent stores, and it is
> confirmed by symbol in both builds (`_aulSysInfo`, above).

**Index 4 is not "max VDM sessions" in any useful sense, and this is the trap.**
It is set from `__MaxProcesses` - the *same cell* as index 29 - and
`SIS_MaxVDMs` is read for nothing in `_tkInitSysInfo`. So on a real machine the
two disagree by construction: the Warp-4.5-family machine measured below reports
`QSV[4] = QSV[29] = 1025` beside its own `SIS_MaxVDMs = 0`. The invariant that *is* universal across
configurations is **`QSV[4] == QSV[29]`**.

**`__MaxProcesses` is configuration-derived, not a constant.**
`_PGSetupUserAddressSpace` computes it from system-arena size and per-process
context cost, clamps it to 4096 and then by `MaxThreads` (the `THREADS=`
CONFIG.SYS setting), and prints it at boot. The oracle carries `THREADS=1024`
and answers 1025. **So a number captured for indices 4 or 29 describes one
machine's configuration and must not be transcribed as an OS/2 fact.**
`[INF]`, flagged rather than asserted: `1025 == THREADS + 1` is a suggestive
correlation on a single sample; the decompiled arithmetic does not by itself
yield the `+1`.

**Several of these are compile-time constants in the kernel image.** Read
directly out of `_SISData` in **two independent kernel builds** (both agreeing):
`SIS_ClkIntrvl` **310**, `SIS_MaxScrnGrp` **16**, `SIS_MaxVioWinSG` **16**,
`SIS_MaxPresMgrSG` **16**, `SIS_MaxVDMs` **0**. The genuinely boot-set
neighbours read **zero** in the image - `SIS_Dynamic`, `SIS_MaxWait`,
`SIS_MinSlice`, `SIS_MaxSlice`, all set from CONFIG.SYS - which is the control
that makes the static read meaningful rather than incidental, and it matches
the live capture where those four read 1 / 3 / 32 / 32.

### Which of these report a CAPABILITY, and which only look like it  `[OBS-RE]`

> **The tag is right and has been checked (2026-08-31).** Automated sweeps have
> flagged this heading repeatedly on capture-shaped language, which belongs to
> the *preceding* section (a live GIS read) and falls inside the sweep's context
> window, not to this one. Every observation below rests on reading the binary: a
> decompiled `INITTIME`, the image byte at `_SISData +0x1B`, and a literal
> compared across all four held `os2krnl` builds. No capture is involved and
> none is needed.

Two of the values above read as though a program could branch on them to learn
what the system supports. Only one of them can, and the difference is not
visible from either name.

**`SIS_ProtMdOnly` (GIS +0x1B) does report VDM-manager state, and it is set at
run time rather than from the image.** Its image default is **1** (`_SISData`
+0x1B reads byte `0x01`), and its only writer anywhere in the 32-bit kernel is
four lines long:

```c
/* INITTIME, os2krnl 0x00152cd5 */
void INITTIME(int param_1) {
  DAT_0002029b                  = (undefined1)param_1;  /* _SISData + 0x1B      */
  *(undefined1 *)(_Sis2 + 0x1b) = DAT_0002029b;         /* the second GIS copy  */
  _fIsInitTime    = param_1;
  _fIsMVDMPresent = (uint)(param_1 == 0);
}
```

(The second store is the *"two identical copies"* rule from **Semantics**
above, visible in one routine: every kernel writer of a GIS field maintains
both. Which of `_SISData` / `_Sis2` is the shared-arena copy and which the
system-arena one was **not** established here and is not needed for the point
below.)

The fourth line is the whole finding: IBM's own *"is the MVDM present"*
variable is the **inverse** of this field - which is what the DDK name already
says, *"protect-mode-only indicator"*, i.e. 1 = protect mode only = no DOS box.

Its only two callers are `VDMMINIT`'s bookends - `INITTIME(1)` at entry,
`INITTIME(0)` at its single `return 0`, with ten early-return paths in between
- so the field means **"the VDM manager finished initialising"**. A VDM manager
that fails partway leaves it at 1. It is therefore *not* a CONFIG.SYS setting
read back: `PROTECTONLY=` controls whether VDM support is **configured**, this
reports whether it **initialised**, and the two can differ.

**`QSV_INT10ENABLED` (index 31) reports no capability at all, despite the
name.** That cell is a literal `1` written unconditionally by `_tkInitSysInfo`
in **all four** `os2krnl` builds held in the corpus (SMP and UNI, base and
debug).
`_tkInitSysInfo` contains no `if` at all; `_VR32QuerySysInfo` never refreshes
index 31; and grepping each build's entire `decompiled_32` tree for that cell's
address returns `_tkInitSysInfo` **and nothing else**. The cell is written once,
at boot, before any VDM decision is taken - so index 31 answers 1 on a machine
with a DOS box and on a `PROTECTONLY=YES` machine without one, alike.

**The contrast is the result, and it settles the question the name raises.**
IBM demonstrably *had* a mechanism for reporting VDM capability and used it at
`SIS_ProtMdOnly`; at index 31 they did not use it. A field that cannot
distinguish those two machines carries no capability information, so **no
correct program can branch on index 31 to learn whether INT 10h is usable** -
one that tried would already be wrong on every kernel examined here.

**Scope of that "every", stated rather than left to generalise.** The four
builds are four *configurations* of one kernel family - SMP and UNI, base and
debug - **not four releases**, so agreement across them is evidence that the
literal is not configuration-dependent and is *not* evidence that it holds
across OS/2 versions. The corpus identifies them by configuration only
(`os2krnl{b,d}_{smp,uni}_{h,a}strict`) and no release is established for them
here beyond the Warp-4.5 family this whole section works in. The finding
therefore covers **that family** and says nothing about earlier ones, which is
not a hedge: index 31 does not exist before Warp 4 at all. The Warp-v3 Toolkit's `QSV_MAX` stops at 25 (see the table note above), so
on those releases the index is out of range rather than uninformative `[INF]`
- that the older kernel's own range check therefore rejects it is the obvious
reading of the mechanism described above, but no pre-Warp-4 kernel is held in
this corpus, so it is not measured here. Read the
conclusion as "wherever index 31 exists in this family it carries no capability
information", not as a statement about every OS/2 ever shipped.

*(The index arithmetic is checked, not assumed. The base cell in each build is
the one receiving `0x104` - index 1, `MAX_PATH_LENGTH` = 260 - and index N is
base + (N-1)x4. The control is index 26, `QSV_NUMPROCESSORS`: a literal `1` in
the two UNI builds and a variable read in the two SMP builds. A wrong base
would not reproduce that split. The same arithmetic shows the cell for index 32
is never written in any build, which is the other half of "32 is an off-by-one,
not an index".)*

### `QSV_VIRTUALADDRESSLIMIT` (30) is per-machine; the image default is 2048 MB  `[OBS-RE]`

`_tkInitSysInfo` sets it to `_VirtualAddressLimit >> 20`, so the reported unit
is **megabytes**. `_VirtualAddressLimit` is a runtime variable, not a constant:

- its static initialiser is **`0x80000000` = 2048 MB in all four kernel
  builds**, read out of each build's own data object;
- `_PGSetupUserAddressSpace` rounds it **up to a 64 MB boundary**
  (`+ 0x3ffffff & 0xfc000000`) and then runs its page-table remap block only
  when the result differs from that `0x80000000` default - which is the proof
  the value is settable rather than fixed.

**So a number captured for index 30 describes one machine's configuration**,
exactly the trap indices 4 and 29 carry above. A Warp-4.5-family machine
measured **1024 MB**, which is neither the image default nor an OS/2 constant;
do not transcribe it as one.

`[INF]` the setter was not traced. The `VIRTUALADDRESSLIMIT` keyword string is
in the kernel image (object 8, +0x1EC0, beside `MAXWAIT` +0x1DF1,
`PROTECTONLY` +0x1E41, `THREADS` +0x1EA5 and `TIMESLICE` +0x1EAD), and no
32-bit writer of the variable exists in the corpus, so it is presumably the
16-bit CONFIG.SYS handler.

### `SIS_MinSlice` / `SIS_MaxSlice` come from `TIMESLICE=`, whose default pair IBM does not name  `[DOC-IBM]`

`TIMESLICE=x,y` sets the pair. IBM documents that `x` *"must be an integer
greater than, or equal to, 32"*, that `y` must be `>=` `x` and less than
65,536, and that *"if you do not have a TIMESLICE= statement in your CONFIG.SYS
file, the minimum and maximum default values are set"* - but **never names that
default pair numerically**. Consistent with that, both fields read zero in the
kernel image (above) and are written at boot.

`[OBS]` a Warp-4.5-family machine carrying no `TIMESLICE=` line reports
**32 / 32**, through `DosGetInfoSeg` and through `QSV_MIN_SLICE`/`MAX_SLICE`
alike. One machine, one sample: the floor of 32 is documented, the pair is
measured.

### `SIS_SysLog` (+0x48) reports a service, and the service is two CONFIG.SYS lines  `[DOC-IBM]`

The field is the bit pair in the GIS table above: `LF_LOGENABLE` 0x0001,
`LF_LOGAVAILABLE` 0x0002, so a value of **3** is "available and enabled".
IBM's Error Logging Service requires **both** `DEVICE=LOG.SYS` *and*
`RUN=LOGDAEM.EXE` - *"The two CONFIG.SYS statements can occur in either
order"* - and once activated it can be paused and resumed, either by `LOG.SYS`'s
own `/P` parameter or from the `SYSLOG` utility. `[INF]`, not stated by IBM:
that split is what the two bits look like - available = the service is
activated, enabled = it is not paused.


### The 16-bit `DosQSysInfo` (ord 166) is a DIFFERENT index space  `[OBS]`

Not a narrowed `DosQuerySysInfo`. Its space is **`{0}`**: index 0 answers 260
(max path length) as a `USHORT`, and **every** index from 1 to 35 answers 87.
Its validation order is index -> buffer (`DosQSysInfo(1, buf, 0)` answers 87
where `DosQSysInfo(0, buf, 0)` answers 111), the minimum buffer is 2 bytes, and
a NULL buffer with a valid index **faults** as the 32-bit form does.

**IBM's headers are consistent about this once each is read with the function
it declares** - corrected 2026-08-26, having first been recorded here as two
headers disagreeing. Every header that declares `DosQSysInfo` itself defines
`Q_MAX_PATH_LENGTH` as **0**: the `bsedos16.h`/`bsedos16.inc` pair in two
independent DDK trees (one of them under the comment `/* definition for
DOSQSYSINFO */`, and containing no `QSV_*` symbol at all), and the OS/2 1.x
MASM `BSEDOS.INC` under `; DosQSysInfo index`. The `= QSV_MAX_PATH_LENGTH`
(i.e. 1) form appears only in `bsedos.h`, under the comment `/* indices for
DosQuerySysInfo */`, in the same file that does `#define DosQSysInfo
DosQuerySysInfo` and prototypes the 32-bit call - so it is **ord 348's** index
space reached through a compatibility macro that retires the old name, not a
second opinion about the 16-bit call. A name may be a macro in one width and a
real export in the other; that alias block is a pairing map, not a conflict.

What documentation genuinely does **not** give is the *extent* of the space:
`Q_MAX_PATH_LENGTH == 0` establishes that index 0 is valid and says nothing
about 1, 2 or 17, and **no IBM prose documents the 16-bit form at all**
(`grep -rn "QSysInfo"` over all 30 books in `~/os2docs/inf_text/`: zero hits).
`{0}` being the whole space is measured, not read.

### Negative results (Rule 1.6 - do not re-search these)

- **None of the author's reverse-engineering write-ups covers `DosQuerySysInfo`.** Searching
  all 123 of them for `QuerySysInfo|QSV_|QSysInfo|MaxProcesses|
  TIMER_INTERVAL|MS_COUNT` returns four files and every hit is incidental. The
  *decompiles* have everything; the write-ups have nothing.
- **`FSH_QSYSINFO` is not this API.** It is an unrelated FSHelper routine that
  shares four letters - the same class of trap as "SM = Swap Manager, not
  Session Manager".
- **No IBM source states a value or a derivation for `QSV_MAXPROCESSES`**, and
  no book text mentions `QSV_INT10ENABLED`'s meaning for a caller.

### Provenance

`[OBS-RE]` from decompiles of the kernel and its raw data object 2 (`_SISData` at file offset
0x280), cross-read against the SMP debug kernel. Offsets in the right-hand column are arithmetic from
`_SISData = 0x00020280` onto `[DOC-IBM]`
DDK `base/h/infoseg.h`, `struct InfoSegGDT`.

Added 2026-08-26, for the three sections between the QSV table and the 16-bit
one: decompiles from the same build, and the kernel's data object 8 for the CONFIG.SYS keyword
strings. The cross-build claims - index 31's literal `1`, index 26's UNI/SMP
split, index 32's unwritten cell, and `_VirtualAddressLimit`'s `0x80000000`
initialiser - were read out of **all four** builds present in the corpus
(`os2krnlb_smp_hstrict`, `os2krnld_smp_astrict`, `os2krnlb_uni_hstrict`,
`os2krnld_uni_astrict`), each from its own `decompiled_32` tree, its own
`symbols_va.txt` and its own object images, rather than from one build's
arithmetic applied to the rest. `[DOC-IBM]` prose for `TIMESLICE=` and
`LOG.SYS`/`LOGDAEM.EXE` is the IBM *OS/2 Command Reference* under those two
entries.
Added 2026-09-19, for the two sections between the LIS/GIS summary and the GIS
table, and for the QSV 24/25 correction: `os2krnld` **SMP Astrict** and
`os2krnlb` **SMP Hstrict**, disassembled from the images with their own `.SYM`
and cross-read against their own linker `.MAP` for every symbol address quoted
(`_Sis2`, `_Lis2`, `_SISData`, `SMHotKeyQ`, `_FgndSGID`, `_tkFgndPID`,
`_aulSysInfo`). The `+0x18` census is a byte census over the eight executable
objects of the SMP Astrict image, filtered by that image's own object table.
`[DOC-IBM]` for the device-header facts: DDK `base/inc/devhdr.inc`
(`SysDev`, `SDevAtt` at `+0x4`), DDK `base/h/devhdr.h:72`
(`DEV_CLOCK 0x0008`), DDK `base/inc/devsym.inc:49-52`
(the `Packet` struc: `PktLen`, `PktUnit`, `PktCmd` - three `db`s, so `PktCmd`
is at `+0x2`), DDK `base/inc/devcmd.inc:9-10` and
DDK `base/h/devcmd.h:36-37` (`CMDOUTPUT 8`,
`CMDOUTPUTV 9`) and DDK `HTML/REF/PDD/00017.HTM` (the device header at the
start of the data segment).

> **Those two command codes were cited to `devsym.inc` until 2026-09-19, and
> they are not defined there** (Rule 1.7 - the values were always
> right, only the authority was wrong). `devsym.inc:110-111` reads
> `;CMDOUTPUT equ 8` / `;CMDOUTPUTV equ 9` - both **commented out**, IBM's
> documentary copy of constants the file expects from elsewhere; its own line
> 140 (`WriteBypassAdj equ CMDOutputBypass-CMDOUTPUT`) *uses* `CMDOUTPUT`
> without defining it. `PktCmd` is genuinely `devsym.inc`'s, so the citation
> was half right, which is why it read as sound.

`[OBS]` live values measured on a Warp-4.5-family machine (Server for
e-business, CP2), 2026-08-26 - one machine, one session, three probes: a
32-bit `DosQuerySysInfo` sweep, a 16-bit `DosQSysInfo` sweep, and a 16-bit
`DosGetInfoSeg` GIS dump. Verbatim captures are kept with the probes that
produced them; the artifact paths are recorded on the project side, since a
path into one project's tree is not a fact about OS/2.

## See also
- `memory-model.md` - the arenas and selectors the InfoSegs live in; `boot-sequence.md` (Stage 2) - where they are published.


---

## Measured on a live Warp 4.5 system  `[OBS]`

Captured 2026-08-20 from a running OS/2 Warp 4.5 (Server for e-business, CP2)
with the PM desktop up, using two probes: a 16-bit `DosGetInfoSeg` reader, and
a 32-bit `DosQuerySysState` dump of every process's screen group. Both probes
and their verbatim captures are retained project-side (see `README.md`,
"Where a capture lives, and why its path is not here").

### The InfoSeg selectors are `0xDFF4` and `0xDFFC`

`DosGetInfoSeg` returned `selGlobal=DFF4 selLocal=DFFC`. Both are GDT
selectors. Note the LIS is **`0xDFFC`, not `0xDFFF`** - worth stating because
`0xDFFF` is the documented **TLMA** selector, a *different* selector, and they
are adjacent rather than the same one with the TLMA at an offset inside it.

### `sgCurrent` / `LIS_CurScrnGrp` is the process's OWN session id - PM sessions do NOT share one

IBM's two headers name this field differently - Toolkit 4.5 `H/driver.h:212`
`sgCurrent` *"session"*, DDK `base/h/infoseg.h` `LIS_CurScrnGrp` *"screen
group"* - and the Debugging Handbook's glossary says sessions and screen groups
correspond *"though the range of numbers is extended to included PM sessions,
which all share then same screen group"* (`debugging_handbook_vol2.txt:19730`,
`[DOC-IBM]`). That parenthetical invites the reading that every PM program
reports one shared number. **Measured, it does not**:

| pid | ppid | sgid | type |
|---|---|---|---|
| 1 | 0 | 0 | 0 (kernel) |
| 16 | 1 | **1** | 0 - the shell (PMSHELL) |
| 27 | 16 | **16** | **3 = PM** |
| 36 | 16 | 18 | 2 = windowable VIO |
| 28 | 16 | 17 | 2 = windowable VIO |
| 37 | 16 | **19** | **3 = PM** |
| 38 | 37 | **19** | **3 = PM** - child, inherits its parent's session |
| 17 | 16 | 4080 | 1 = real mode / VDM |

Two PM processes in **different** sessions (16 and 19), so the field carries a
unique per-session id for a PM program exactly as it does for any other type.
A child started into an existing session inherits it (38 under 37).

### Session ids are allocated sequentially, NOT from per-type ranges

The Debugging Handbook's table (`0` popups, `1` shell, `2` real mode, `3`
VioPopUp, `4-15` full-screen, `16-31` windowable VIO, `32-255` PM) does **not**
describe what Warp 4.5 does. Live ids were `1, 16, 17, 18, 19` for a mix of PM
(3) and windowable-VIO (2) sessions, i.e. one sequential counter shared by all
types. Treat the range table as Warp-3-era, and do not derive a session's type
from its id or vice versa.

### `SIS_MaxScrnGrp` is not an upper bound on session ids

`SIS_MaxScrnGrp` read **16** on the same system whose live sessions included
17, 18 and 19. Whatever it counts, it is not "the largest legal session id",
and validating a session id against it would reject real ones.

> **ANSWERED 2026-08-27 (Rule 1.7): it counts the FULL-SCREEN screen groups**, and the
> conclusion above stands unchanged - it is still not an upper bound on session ids, and
> validating against it would still reject real ones. What it *is*: IBM's Base Video
> Subsystem computes `bvsg_maxbase = SIS_MaxScrnGrp - 1` at init and then classifies each
> session as full-screen or windowed by `SGID <= bvsg_maxbase` - that comparison picks
> which video device handler the session dispatches through. IBM's windowed handler
> derives the same boundary independently and its own comment reads *"get max full-screen
> SGs"*. `[OBS-RE]` + `[DOC-IBM]`; mechanism in `video-stack.md` section 4.4a.
>
> **Still not measured, and it is the interesting half:** whether a real full-screen
> session's id actually lands at or below that boundary on Warp 4.5. The capture above
> contained no full-screen session - every id in it is above 15 - so it neither confirms
> nor refutes the boundary, and the paragraph above it (*"do not derive a session's type
> from its id"*) remains the safe rule until someone captures one.

### `LIS_Fgnd` is about THIS process, not about the system

Toolkit 4.5 `H/driver.h:215` is the more specific of IBM's two comments:
*"current process has keyboard focus"* (the DDK header says only "current
process is in foreground"). Measured: a **detached** process (type 4) reported
`fForeground=0` while the GIS reported `SIS_CurScrnGrp=1` and
`SIS_FgndPID=36` - so the field is not "a foreground exists", it is a property
of the reader.

**Not measured:** whether a *focused PM application* whose session is not the
foreground screen group reports 1. Producing that capture needs GUI
interaction the ssh oracle path cannot drive.
