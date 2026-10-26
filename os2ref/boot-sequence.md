# OS/2 Boot Sequence - kernel init to the Workplace Shell

How an OS/2 (Warp 4 / 4.5) system boots, stage by stage, with the **observable contract** each
stage establishes - the structures, APIs, and state an application can later query. Provenance
tags per the corpus [README](README.md): **[DOC-IBM]** documented by IBM, **[OBS-RE]** observed by
reverse-engineering the real binaries, **[DOC]** other published reference.

## Overview

| # | Stage | Observable contract it establishes |
|---|---|---|
| 1 | OS2LDR -> OS2KRNL | boot-drive identity |
| 2 | Kernel initialization | the Information Segments + `DosQuerySysInfo` surface; the memory-arena / selector model |
| 3 | DevHlp + kernel services | the driver-facing DevHlp API; the system clock |
| 4-5 | DASD / volume bring-up | physical- and logical-disk IOCtl surface; VPB/DPB; FS-attach / FS-info queries |
| 6 | `DEVICE=` PDD loading | the `\DEV\` device namespace + per-device IOCtl categories |
| 7 | `IFS=` filesystem install | the FS-attach / FS-control surface + the FSHelper contract an IFS runs against |
| 8 | CONFIG.SYS processing | the process environment block + NLS (codepage / country) queries |
| 9 | Session manager (not a boot stage - see Stage 9) | the session / screen-group model and its control APIs |
| 10 | `PROTSHELL=` launch | the protected-mode shell process |
| 11 | Presentation Manager | the Win* / Gpi* API, the message queue, the GPI->GRE->driver draw path |
| 12 | `RUNWORKPLACE=` | the shell reads an env var to launch the desktop program (default: the Workplace Shell) |

Each stage gives the mechanism and the contract, with sources. Full per-structure detail lives in
the subsystem references (`infoseg.md`, `kernel-services.md`, ...); this spine stays at contract level.

---

## Stage 1 - OS2LDR loads OS2KRNL

[DOC-IBM] The boot loader **OS2LDR** loads the kernel **OS2KRNL** and a micro-FSD / mini-FSD to read
the boot volume before the installable file systems are available. The observable residue an
application later sees is the **boot drive** - `DosQuerySysInfo(QSV_BOOT_DRIVE)` (index 5; 1 = A,
2 = B, ...) and the global InfoSeg field `SIS_BootDrv`. ([DOC-IBM] `QSV_BOOT_DRIVE == 5 /* 1=A, 2=B */`,
IBM Toolkit 4.5 `bsedos.h:2504`; `SIS_BootDrv` at offset 0x24, IBM DDK `infoseg.h:85-87`.)

## Stage 2 - Kernel initialization

[DOC-IBM] The kernel establishes protected mode, the GDT/IDT and per-process LDTs, paging, and the
memory arenas, then publishes the read-only **Information Segments** and the flat **`DosQuerySysInfo`**
surface an application queries.

- **Global Information Segment (GIS / `InfoSegGDT`)** - one system-wide, **114-byte** read-only
  segment: time, date, version, foreground session and PID, scheduler parameters, boot drive,
  session limits, error-logging status. Two identical copies are kept - one in the shared arena
  (user-readable) and one in the system arena (kernel-only) - both maintained by the kernel; the
  clock driver holds the read/write copy via the DevHlp `GetDOSVar`, all other code a read-only
  selector. ([DOC-IBM] `struct InfoSegGDT`, IBM DDK `infoseg.h:36-113` - ending at `SIS_perf_mec_table[32]`
  (offset 0x52), total 0x72 = 114 bytes; the two-copy shared-/system-arena model and clock-driver
  `GetDOSVar` read/write selector are the header's own comment, `infoseg.h:18-33`.)
- **Local Information Segment (LIS / `InfoSegLDT`)** - one per process, updated at context switch;
  only the running process holds the extra copy. **36 bytes on the uniprocessor kernel, 44 on SMP**
  (the SMP form appends `LIS_pTIB` / `LIS_pPIB` at 0x24 / 0x28). ([DOC-IBM] `struct InfoSegLDT`, IBM
  DDK `infoseg.h:183-219`; the 4-byte `LIS_pTIB`/`LIS_pPIB` pair is under `#ifdef SMP`, `infoseg.h:215-218`
  - appending them to the 36-byte base gives 44.)
- **`DosQuerySysInfo` (QSV 1-31)** - version, page size, memory totals, timeslice bounds,
  foreground session / process, processor count, virtual-address limit, and more. ([DOC-IBM]
  `QSV_MAX_PATH_LENGTH == 1` ... `QSV_INT10ENABLED == 31`, `QSV_MAX == QSV_INT10ENABLED`, IBM Toolkit 4.5
  `bsedos.h:2499-2531`.)

Full field tables -> `infoseg.md`. The private / shared / system arena layout and the LDT selector
model -> `memory-model.md`.

## Stage 3 - DevHlp and kernel services come online

[DOC-IBM] With the kernel up, its service surfaces are available:
- **DevHlp** - the ~103 `DevHlp_*` routines device drivers call (memory / selector, synchronization,
  scheduling, timers, registration/IDC, interrupt, monitors). Numbers in the DDK `devhlp.inc`,
  prototypes in `dhcalls.h`. See `kernel-services.md`.
- **The system clock** - `DosGetDateTime` / `DosSetDateTime` return/set the 11-byte `DATETIME`
  (hours, minutes, seconds, hundredths, day, month, year, timezone, weekday). The InfoSeg time
  fields (`SIS_BigTime` seconds-since-1970, `SIS_MsCount` free-running ms, `SIS_ClkIntrvl` timer
  interval) and `QSV_TIMER_INTERVAL` (tenths of a ms) expose the tick. ([DOC-IBM] `DATETIME` =
  4xUCHAR + UCHAR day + UCHAR month + USHORT year + SHORT timezone + UCHAR weekday = 11 bytes, IBM
  Toolkit 4.5 `bsedos.h:2090-2101`; `SIS_BigTime` "Time from 1-1-1970 in seconds", `SIS_MsCount`
  "Freerunning milliseconds counter", `SIS_ClkIntrvl` "Timer interval (units=0.0001 secs)", IBM DDK
  `infoseg.h:40,41,47`; `QSV_TIMER_INTERVAL == 22 /* tenths of ms */`, `bsedos.h:2521`.)

## Stage 4-5 - DASD and volume bring-up

[DOC-IBM] Base disk drivers (ADD / DMD / filter) and the file-system layer bring storage online.
The observable disk/volume contract an application (a format / partition / backup tool, an
installer) depends on:
- **Physical disk** - `DosPhysicalDisk` enumerates partitionable disks and returns partition info;
  `DosDevIOCtl` category **`IOCTL_PHYSICALDISK` = 0x09** (`PDSK_*` functions). ([DOC-IBM]
  `IOCTL_PHYSICALDISK == 0x0009`, IBM Toolkit 4.5 `bsedev.h:41`; `DosPhysicalDisk` proto `bsedos.h:2857`.)
- **Logical disk / drive** - `DosDevIOCtl` category **`IOCTL_DISK` = 0x08** (`DSK_*`):
  `DSK_GETDEVICEPARAMS` (BPB / geometry), lock / unlock, media redetermine / removable, track
  read / write / verify, logical map, format. ([DOC-IBM] `IOCTL_DISK == 0x0008`, `bsedev.h:40`;
  `DSK_GETDEVICEPARAMS == 0x0063`, `DSK_LOCKDRIVE`/`DSK_UNLOCKDRIVE`/`DSK_REDETERMINEMEDIA`/
  `DSK_SETLOGICALMAP`/`DSK_BEGINFORMAT`/`DSK_READTRACK`/`DSK_WRITETRACK`/`DSK_VERIFYTRACK`,
  `bsedev.h:175-191`.)
- **Volume / FS** - `DosQueryFSInfo` (volume label + serial number; **not** the FS type - see
  `dasd-volume.md`), `DosQueryFSAttach` (which FSD is attached to a drive, and the FS/FSD *name*;
  local vs remote), `DosQueryCurrentDisk` / `DosSetDefaultDisk`
  (the drive-letter map), `DosQueryHType` (handle is disk / device / pipe). ([DOC-IBM] prototypes
  IBM Toolkit 4.5 `bsedos.h` - `DosQueryHType:1531`, `DosQueryFSAttach`/`DosQueryFSInfo` (headers
  `:815`/`:861`), `DosSetDefaultDisk:1705`, `DosQueryCurrentDisk:1707`.)
- **VPB / DPB** - the Volume and Drive Parameter Blocks carry serial, label, FS name, and geometry.

IOCtl function tables and the VPB/DPB layouts -> `dasd-volume.md`.

## Stage 6 - `DEVICE=` physical device drivers

[DOC-IBM] Installable physical device drivers (PDDs) load. Each publishes a **`\DEV\` device name**
and an IOCtl surface. Two contract facts:
- **Device-name resolution** - `DosOpen("\DEV\NAME")` matches a device *before* a file of the same
  name; the device namespace is resolved first.
- **The PDD ABI** - a PDD is a header (strategy-routine offset, device attributes) whose Strategy
  routine is far-called with **ES:BX -> request packet** (DS = the driver's data segment); it uses
  DevHlp services and, for storage / block drivers, the IORB interface.

PDD header layout, request-packet formats, the ES:BX ABI -> `drivers.md`.

## Stage 7 - `IFS=` installable file systems

[DOC-IBM / OBS-RE] Installable file systems (HPFS, JFS, ...) load and attach to drives. The contract:
- `DosFSAttach` attaches / detaches an FSD to a drive (and, with `DosQueryFSAttach`, reports which
  FSD owns a drive); `DosFSCtl` passes FS-specific control through to the FSD. ([DOC-IBM]
  `DosFSAttach` proto IBM Toolkit 4.5 `bsedos.h:1561`.)
- **Feature surface** an application observes: extended attributes (the `FEA2` / `GEA2` / `EAOP2`
  structures) via `DosQueryPathInfo`, long names and case behaviour, and the FS/FSD *name* via
  `DosQueryFSAttach` (`DosQueryFSInfo` returns only label + serial - see `dasd-volume.md`).
  ([DOC-IBM] `struct _FEA2`/`_GEA2`/`_EAOP2` (and the `FEA2LIST`/`GEA2LIST` list forms), IBM Toolkit
  4.5 `bsedos.h:1156-1194`.)
- **The FSHelper (`FSH_*`) contract** - the kernel services an FSD itself calls (volume I/O,
  name canonicalization, sharing, semaphores, buffer probing, driver dispatch). [OBS-RE] Much of
  this surface is documented only in the DDK's IFS sample sources and by RE of shipped FSDs.

The FSD entry-point set (`FS_*`), the FSHelper surface, and the VPB volume model -> `drivers.md`.

## Stage 8 - CONFIG.SYS processing

The kernel reads CONFIG.SYS in **multiple passes by category**, not line-by-line; `PROTSHELL=` runs
last. (Period references give a scan order PSD -> BASEDEV -> DEVICE/IFS -> RUN/CALL -> general, but the
placement of the `SET`/`LIBPATH` and NLS groups varies across sources - see
`config-and-environment.md`. [DOC]) For the ring-3 phase the kernel's own code settles part of this:
the environment and NLS are set up **before** `DEVICE=`/`IFS=` drivers are installed, so in execution
this stage precedes Stages 6-7. See "Who runs Stages 6-10" below. It publishes:
- **The environment** - a flat, double-null-terminated block (`"NAME=value\0...\0\0"`, <= 64 KB) at
  `PIB.pib_pchenv`, walked by `DosScanEnv`. `LIBPATH=` / `BEGINLIBPATH=` / `ENDLIBPATH=` set their
  value with **no `SET` prefix**; every other variable requires `SET NAME=value`. Directive names
  are case-insensitive; *values* are case-sensitive; and `DosScanEnv` matches a variable's name
  case-sensitively (corrected - see `config-and-environment.md`).
- **NLS** - `DosQueryCp` (codepage), `DosQueryCtryInfo` (the `COUNTRYINFO` structure - date / time /
  currency / decimal formats), `DosQueryDBCSEnv`. ([DOC-IBM] `DosScanEnv` proto IBM Toolkit 4.5
  `bsedos.h:2616`; `struct _COUNTRYINFO` with `fsDateFmt`/`szCurrency[5]`/`szDecimal[2]`/
  `szDateSeparator[2]`/`szTimeSeparator[2]`/`fsCurrencyFmt`/`fsTimeFmt`, `bsedos.h:2314-2331`;
  `DosQueryCtryInfo:2339`, `DosQueryDBCSEnv:2344`, `DosQueryCp:2357`.)

The env-block format and NLS structures -> `config-and-environment.md`.

### Who runs Stages 6-10: the SYSINIT process

Installable drivers are initialised inside a **process**: IBM says a PDD's strategy routine at INIT
time runs under the thread of the System Initialization Process, at ring 3 with I/O privilege
[DOC-IBM *Physical Device Driver Reference*, "Physical Device Driver Initialization"]. That process
is **pid 1**: IBM's worked examples list a PTDA `0001 *sysinit` alongside a running `pmshell.exe`,
so it is still there once the shell is up [DOC-IBM *OS/2 Debugging Handbook* Vol. I, SG24-4640,
"Worked Examples", the `.m` listing].

Its main routine, `syiProcess`, performs the CONFIG.SYS work itself, in this order [OBS-RE - Warp
4.5 UNI kernel 14.104a with its `.sym`; disassembled, from the directory holding both, with
`lx_disasm.py os2krnl --sym os2krnl.sym --sym-name h_syiProcess --bits 16 --count 140`]:

| Call | Does |
|---|---|
| `syiInitEnvironment` | the environment (Stage 8) |
| `syicpInit` | `COUNTRY=` / `CODEPAGE=` / `DEVINFO=` (Stage 8, NLS) |
| `syicpActivate` | activates the code pages (Stage 8, NLS) |
| `syiInstallDeviceDrivers` | `DEVICE=` and `IFS=` (Stages 6-7) |
| `syiStartShell` | `PROTSHELL=` (Stage 10) |

`RUN=`/`CALL=` daemons start between the driver installation and the shell
(`syiStartDaemonProcesses`), and a second daemon pass runs after it (`syi2StartDaemonProcesses`)
[OBS-RE - same routine and command].

## Stage 9 - Session manager

**CORRECTED (Rule 1.7): not a boot stage, and not before Stage 10.** This heading used to read
"Session manager initialization", placed before `PROTSHELL=`. No step of `syiProcess` sets up a
session manager. The shell does that **after** `PROTSHELL=` starts it, by registering through
`DosSMInitialize` (16-bit `DOSCALLS` ordinal 707 [DOC - osFree ordinal list]; `PMMERGE.DLL`
imports `DOSCALLS.#707` [OBS-RE - `lx_resolve_imports.py --all-objects --kind import
--summary PMMERGE.DLL`, run in `\OS2\DLL` of an installed system]). The contract below is
unchanged; only its place in the sequence was wrong.

[DOC-IBM] The protected-mode session manager governs **sessions** (screen groups). Contract:
- `DosStartSession` (with the `STARTDATA` structure: program, session type, foreground / background,
  inheritance), `DosStopSession`, `DosSelectSession`, `DosSetSession` (`STATUSDATA`). ([DOC-IBM]
  `struct _STARTDATA` - `FgBg`/`PgmName`/`InheritOpt`/`SessionType`/`Related`/`TermQ`, IBM Toolkit 4.5
  `bsedos.h:2685-2708`; `STATUSDATA` `:2744`; `DosStartSession:2768`, `DosSetSession:2772`,
  `DosSelectSession:2775`, `DosStopSession:2777`.)
- `DosQueryAppType` - an executable's type (Presentation Manager / VIO-windowable / full-screen /
  detached). ([DOC-IBM] `DosQueryAppType` proto IBM Toolkit 4.5 `bsedos.h:2781`; the LIS process-type
  codes `LIS_PT_FULLSCRN`/`LIS_PT_VIOWIN`/`LIS_PT_PRESMGR`/`LIS_PT_DETACHED`, IBM DDK `infoseg.h:254-258`.)
- **Foreground / screen-group state** - `QSV_FOREGROUND_FS_SESSION`, the InfoSeg `SIS_CurScrnGrp` /
  `SIS_FgndPID`, and `DosQProcStatus` for session / process enumeration. ([DOC-IBM]
  `QSV_FOREGROUND_FS_SESSION == 24`, IBM Toolkit 4.5 `bsedos.h:2523`; `SIS_CurScrnGrp` (offset 0x18) /
  `SIS_FgndPID` (offset 0x1C), IBM DDK `infoseg.h:69,76`.)

The session model and control APIs -> `session-manager.md`.

## Stage 10 - `PROTSHELL=` launches the shell

[DOC-IBM] The last CONFIG.SYS category, `PROTSHELL=`, names the protected-mode shell - normally
`PMSHELL.EXE`, which brings up the Presentation Manager (Stage 11). `PIB.pib_ulpid` is its process
id. The shell is a **child of the SYSINIT process** (parent pid 1), not pid 1 itself. On a measured
SMP Warp 4.50 boot its pid was 0x13, after the file-system check program and the `RUN=` daemons
[OBS-RE - kernel-debugger reads of the local InfoSeg].

## Stage 11 - Presentation Manager

[DOC-IBM / OBS-RE] PMSHELL.EXE is a thin front over a **federation of DLLs** - `PMWIN` (Win* API),
`PMGPI` (Gpi* API), and `PMMERGE` (the complete window manager + GPI engine + GRE dispatch) - over
the graphics chain **GRE -> GENGRADD -> VMAN -> SOFTDRAW**. The contract:
- **The Win* / Gpi* API** - `WinInitialize` (an anchor block, HAB), `WinCreateMsgQueue` (HMQ),
  windows (HWND) and their presentation spaces (HPS) bound to device contexts (HDC), `DevOpenDC`,
  `GpiCreatePS`, `WinQuerySysValue`.
- **The message queue** - create / post / get / dispatch / send; a window paints on `WM_PAINT` by
  drawing GPI primitives into a cached micro-PS. The queue block/wake is a kernel event
  primitive surfaced as DOSCALL1 ordinals 590 / 591, `Dos32PMPostEventSem` / `Dos32PMWaitEventSem`
  ([DOC-IBM] `ORD_DOS32PMPOSTEVENTSEM EQU 590` / `ORD_DOS32PMWAITEVENTSEM EQU 591`, IBM Toolkit 4.5
  `INC/bseord.inc:595-596`); [OBS-RE] that it is reached through a 32->16 call gate is observed from
  the shipped binaries (the ordinal *identity* is IBM-documented; the call-gate *mechanism* is RE).
- **The draw path** - `WM_PAINT` -> micro-PS -> GPI -> GRE -> the driver rasterizes into the video
  aperture; each process maps its own aperture (`VMGlobalToProcess`, `INITPROCOUT.ulVRAMVirt`) onto
  the single shared scanout, writing its window's clipped region under VMAN serialization.
- **Cross-process state** - PMMERGE's shared data objects (the desktop window, the HWND->PWND handle
  table, the master message-queue list) are one physical copy system-wide; per-process device
  contexts and VRAM apertures are each process's own.

The GPI / GRE / VMAN draw path -> `pm-graphics.md`; the message queue and wake -> `message-queue.md`;
the 16<->32 thunk ABI -> `thunking.md`.

## Stage 12 - `RUNWORKPLACE=` starts the desktop

[DOC-IBM / OBS-RE] `RUNWORKPLACE=` is a CONFIG.SYS `SET` variable (an environment variable, Stage 8),
read by the already-running PMSHELL to decide **what program to run as the desktop**. The default is
`PMSHELL.EXE` itself, which - being the workplace process - loads the **Workplace Shell** (`PMWP.DLL`)
and the System Object Model (`SOM.DLL`) it is built on. It is fully configurable: `CMD.EXE`, or any
program, may be the workplace. This is a userspace configuration read at Presentation-Manager time,
not a kernel component.

The SOM object model and the WPS class hierarchy (`WPObject`, `WPFolder`, ...) are userspace subsystems
documented, if needed, in their own references.

---

## Ratification

**Ratified (2026-07-26):** checked against the IBM Toolkit 4.5 headers
(`{bsedos.h,bsedev.h}`, `INC/bseord.inc`) and the IBM DDK
(`COMBASE/DDK/base/h/infoseg.h`). All numeric / structural claims **matched** their IBM primary:

- **Confirmed, provenance upgraded to [DOC-IBM] with exact citations** - `QSV_BOOT_DRIVE == 5`
  (`bsedos.h:2504`); the QSV surface is 1-31, `QSV_MAX == QSV_INT10ENABLED == 31` (`bsedos.h:2499-2531`);
  GIS `struct InfoSegGDT` = 114 bytes, ending at `SIS_perf_mec_table[32]` at 0x52 (`infoseg.h:36-113`);
  LIS `struct InfoSegLDT` = 36 bytes UNI / 44 SMP, `LIS_pTIB`/`LIS_pPIB` under `#ifdef SMP` at 0x24/0x28
  (`infoseg.h:183-219`); `DATETIME` = 11 bytes (`bsedos.h:2090-2101`); `SIS_BigTime`/`SIS_MsCount`/
  `SIS_ClkIntrvl` semantics (`infoseg.h:40,41,47`); `QSV_TIMER_INTERVAL == 22` tenths-ms (`bsedos.h:2521`);
  `IOCTL_DISK == 0x08` / `IOCTL_PHYSICALDISK == 0x09` and the `DSK_*`/`PDSK_*` function numbers
  (`bsedev.h:40-41,175-200`); `DosPhysicalDisk` (`bsedos.h:2857`), `DosQueryHType`/`DosQueryFSAttach`/
  `DosQueryFSInfo`/`DosSetDefaultDisk`/`DosQueryCurrentDisk` prototypes; `FEA2`/`GEA2`/`EAOP2`
  (`bsedos.h:1156-1194`); `DosScanEnv` (`bsedos.h:2616`), `COUNTRYINFO` + `DosQueryCtryInfo`/
  `DosQueryDBCSEnv`/`DosQueryCp` (`bsedos.h:2314-2357`); `STARTDATA`/`STATUSDATA` + `DosStartSession`
  family (`bsedos.h:2685-2777`), `DosQueryAppType` + LIS process-type codes (`bsedos.h:2781`,
  `infoseg.h:254-258`); `QSV_FOREGROUND_FS_SESSION == 24` (`bsedos.h:2523`), `SIS_CurScrnGrp`/`SIS_FgndPID`
  offsets (`infoseg.h:69,76`); **and the PM message-queue wake ordinals 590 / 591 =
  `Dos32PMPostEventSem` / `Dos32PMWaitEventSem`**, previously tagged [OBS-RE], now confirmed in IBM
  `INC/bseord.inc:595-596` (only the call-gate *mechanism* remains [OBS-RE]).
- **No discrepancies found** - every checked value agreed with its IBM source.
- **Left unpinned (not re-derived):** the "~103 DevHlp routines" figure - the DevHlp count varies by
  source (Toolkit 4.5 `devhlp.inc` lists 117 entries up to number 131; a subset DDK `DEVHLP.INC` lists
  53), so the approximate "~103" is retained and its precise enumeration is left to `kernel-services.md`.
  The Stage 8 CONFIG.SYS category *scan order* remains [DOC] - period references disagree on the exact
  order, so it stays deliberately hedged (see `config-and-environment.md`). For the ring-3 phase it
  is no longer hedged: environment and NLS precede `DEVICE=`/`IFS=` (Stage 8, from `syiProcess`'s
  call order). That correction, the Stage 9 correction and the SYSINIT section were added after
  this ratification pass and are not covered by it.
