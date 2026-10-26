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
| 5a | The SYSINIT process (pid 1) *(added 2026-10-01)* | the process that runs Stages 6-10; DOSCALL1 loaded; the boot's first VIO/BVS call |
| 6 | `DEVICE=` PDD loading | the `\DEV\` device namespace + per-device IOCtl categories |
| 7 | `IFS=` filesystem install | the FS-attach / FS-control surface + the FSHelper contract an IFS runs against |
| 8 | CONFIG.SYS processing | the process environment block + NLS (codepage / country) queries |
| 9 | Session manager ~~init~~ [2026-10-01: not a stage before 10; see Stage 9] | the session / screen-group model and its control APIs |
| 10 | `PROTSHELL=` launch | the protected-mode shell process |
| 11 | Presentation Manager | the Win* / Gpi* API, the message queue, the GPI->GRE->driver draw path |
| 12 | `RUNWORKPLACE=` | the shell reads an env var to launch the desktop program (default: the Workplace Shell) |

Each stage gives the mechanism and the contract, with sources. Full per-structure detail lives in
the subsystem references (`infoseg.md`, `kernel-services.md`, ...); this spine stays at contract level.

> **The stage numbers are not an execution order (corrected 2026-10-01).** Read top to bottom, the
> table puts `DEVICE=` (6) and `IFS=` (7) before CONFIG.SYS processing (8), which includes NLS. The
> kernel's own ring-3 initialisation does the reverse for the environment and NLS: `syiInitEnvironment`,
> `syicpInit` and `syicpActivate` all run **before** `syiInstallDeviceDrivers`, the step that loads
> `DEVICE=` and `IFS=` [OBS-RE: the call order in `syiProcess`, Stage 5a; `config-and-environment.md`,
> "The order, as the kernel's own initialisation calls it"]. The numbering groups contracts; Stage 5a
> gives the order. Stage 9 is not a boot step at all (see its own correction).

---

## Stage 1 - OS2LDR loads OS2KRNL

[DOC-IBM] The boot loader **OS2LDR** loads the kernel **OS2KRNL** and a micro-FSD / mini-FSD to read
the boot volume before the installable file systems are available. The observable residue an
application later sees is the **boot drive** - `DosQuerySysInfo(QSV_BOOT_DRIVE)` (index 5; 1 = A,
2 = B, ...) and the global InfoSeg field `SIS_BootDrv`. ([DOC-IBM] `QSV_BOOT_DRIVE == 5 /* 1=A, 2=B */`,
IBM Toolkit 4.5 `bsedos.h:2504`; `SIS_BootDrv` at offset 0x24, IBM DDK `infoseg.h:85-87`.)

[OBS-RE] A set of **implicit base device drivers is loaded that no CONFIG.SYS line ever names** -
`RESOURCE.SYS`, `CLOCK01/02.SYS`, `SCREEN01/02.SYS`, `KBDBASE.SYS`, plus ten mandatory MVDM
virtual device drivers (`vbios.sys`, `vdma.sys`, `vpic.sys`, `vflpy.sys`, `vtimer.sys`,
`vlpt.sys`, `vkbd.sys`, `vdsk.sys`, `vcmos.sys`, `vnpx.sys`). The filename lists are present in
the **OS2LDR image** as two parallel `01`/`02` variants (observed in both the UNI and SMP loader
builds, at build-specific offsets); of the four base-driver filenames only `RESOURCE.SYS` also
appears in the kernel, beside the BASEDEV extension-priority table.
[INF] **Which component loads them, and what selects the `01` vs `02` variant, are not
established** - `RESOURCE.SYS` is a `.SNP`-class BASEDEV (the earliest-loading class), which
points at the kernel's own BASEDEV machinery, while the other three appear only in the loader;
the `01`/`02` split is presumed ISA vs. ABIOS from the drivers' own source, not from any observed
selection code. What *is* observed is the outcome: `SCREEN$`/`SCREENDD$`/`KBD$`/`CLOCK$`/`RESMGR$`
exist before any CONFIG.SYS driver category is processed. Full breakdown, both candidate load
models, and the boot-to-PM video ownership timeline -> `video-stack.md` section 1.

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

## Stage 5a - The SYSINIT process: ring-3 initialisation, pid 1

*Added 2026-10-01. Earlier revisions of this file had no such stage, no DOSCALL1 load and no
boot-time VIO; Stages 6-10 read as if the kernel performed them directly.*

[DOC-IBM] Installable drivers are initialised inside a **process**: a PDD's strategy routine, at
INIT, *"will run under the thread of the System Initialization Process at Ring 3, with I/O
privilege"* (IBM *Physical Device Driver Reference*, "Physical Device Driver Initialization").
[DOC-IBM] That process is **pid 1**: the `.m` memory-object listing in IBM's worked examples names
`ptda 0001 *sysinit`, in the same listing as a running `pmshell.exe` PTDA (*The OS/2 Debugging
Handbook*, Vol. I, SG24-4640, ch. 14 "Worked Examples"). So SYSINIT is still present once the shell
is up. [INF] That it lasts for the life of the system: nothing read or observed ends it.

[OBS-RE] Its main routine, `syiProcess`, performs Stages 6-10 itself, in this order (Warp 4.5
kernel 14.104a, every routine named by IBM's `.sym`; the conditional halts to `syiAbortR3` and the
far calls between the named routines are omitted, and offsets are build-keyed):

```
syiOpenFiles               ; CON as handles 0, 1, 2
syiInitStdErrIntercept
syiInitEnvironment         ; the environment            (Stage 8)
syiCheckFileSys
syicpInit                  ; COUNTRY= CODEPAGE= DEVINFO= (Stage 8, NLS)
syiGetLoadableEntries      ; DOSCALL1.DLL loaded into SYSINIT
syiDisplaySavedMessagesR3  ; first flush of queued boot messages
syicpActivate              ; DosSetCp, VioSetCp, KbdSetCp (Stage 8, NLS)
syiRegisterJITDebug
syiBeginStdErrIntercept
syiInstallDeviceDrivers    ; DEVICE= and IFS=           (Stages 6, 7)
syiEndStdErrIntercept
syiFATAutoCheck
syiQuery16MBDevices
syiDisplayMessageR3, syiDisplaySavedMessagesR3   ; second flush
syiCloseFiles
syiStartDOSMode
syiBeginStdErrIntercept, syiStartAltF1Process, syiStartDaemonProcesses (RUN=, CALL=),
  syiEndStdErrIntercept, syiTerminateStdErrIntercept
syiStartShell              ; PROTSHELL=                 (Stage 10)
syiInitStdErrIntercept, syiBeginStdErrIntercept, syi2StartDaemonProcesses,
  syiEndStdErrIntercept, syiTerminateStdErrIntercept
```

What this stage establishes:

- **DOSCALL1 is loaded into SYSINIT, before any `DEVICE=` driver.** [OBS-RE] `syiGetLoadableEntries`
  resolves thirteen DOSCALL1 entry points by ordinal through an ordinary ring-3 `DosLoadModule` /
  `DosGetProcAddr`, and the loader runs the library's initialisation for that load. DOSCALL1's
  per-process initialisation therefore runs in SYSINIT, including its VIO process initialisation,
  which builds the screen-group table with control blocks for screen groups 0 and 3 before any
  session manager exists. A `DEVICE=` driver's INIT-time `DosWrite` runs DOSCALL1's code in this
  process. Detail: `video-stack.md` section 4.2a.
- **The boot's first VIO/BVS call is SYSINIT's, at the kernel's own boot message.** [OBS-RE] Until
  DOSCALL1's entry points are resolved, boot messages are queued, not printed
  (`config-and-environment.md`, "How a boot-time message is rendered"); `syiDisplaySavedMessagesR3`
  is the first flush. [OBS] 2026-10-01, WSeB 4.50 Rev 14.089, HStrict SMP debug kernel with the SMP
  `DOSCALL1.DLL`, one virtual CPU; two clean boots under the kernel debugger with hardware
  breakpoints on `BVSDINIT`, `VIOWRTTTY`, `DOSPUTMESSAGE` and `BVSMAIN`, one with every removable
  console-writing `DEVICE=` driver taken out and one with a `DEVICE=` driver that writes a banner at
  INIT. In both, the first `BVSDINIT` entry comes from pid 1 in screen group 0, printing the kernel's
  `Processors Initialized: 1` through `syiDisplayMessageR3` -> `DosPutMessage` -> `DosWrite` ->
  `VioWrtTTY`, before the first `DEVICE=` driver's INIT. In the boot without a banner writer, that
  write's `BVSDINIT` entries carry function codes `0x24`, `0x08`, `0x24`, `0x11`. What VIO does on
  that first write, and which handler-load arm `BVSDINIT` takes: `video-stack.md` section 4.2a. Not
  measured: a uniprocessor kernel, which may print no processor message.
- [INF] **NLS activation follows that write.** `syicpActivate` runs after the first flush, so on the
  boot above its `VioSetCp` is issued after VIO's first-write setup has run. The same boot shows one
  further `0x24` entry with no `VioWrtTTY` before it, consistent with that `VioSetCp` reaching BVS;
  its caller was not captured.
- **The shell is SYSINIT's child.** [OBS-RE] `syiStartShell` runs after the stderr intercept has
  ended, which re-duplicates handle 2 from handle 1 (CON). ~~[OBS] On the boots above, the next process,
  pid 2, has parent pid 1 and runs in screen group 0.~~ [2026-10-01, corrected by a later capture `[OBS]` (kernel debugger, Warp Server for e-Business kernel 14.089 SMP, template CONFIG.SYS, PMSHELL and CMD.EXE as PROTSHELL, 2026-10-01): pid 2 is the JFS file-system check program (parent 1, screen group 0); the RUN= daemons follow with parent 0, screen group 0 and process type 4; the shell is pid 0x13 on both boots, parent 1, screen group 0, process type 0. The shell's pid depends on how many processes SYSINIT starts before it; what holds is that its parent is pid 1 and its screen group is 0.]

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
`config-and-environment.md`. [DOC]) [2026-10-01: for the ring-3 phase the kernel's own code settles
it. The environment (`syiInitEnvironment`) and NLS (`syicpInit`, `syicpActivate`) run **before**
`DEVICE=`/`IFS=` (`syiInstallDeviceDrivers`), so this stage precedes Stages 6-7 in execution;
[OBS-RE], Stage 5a.] It publishes:
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

## Stage 9 - Session manager ~~initialization~~

[2026-10-01: **not a boot stage, and not before Stage 10.** No step of SYSINIT's `syiProcess`
initialises a session manager (Stage 5a). The session manager is set up by the shell **after**
`PROTSHELL=` launches it: the shell registers through `DosSMInitialize`, which has no authorization
gate (this file's own Stage 10 retraction), and `session-manager.md`, "The shell IS the session
manager", gives the registration and serve sides [OBS-RE]. The contract listed below stands; only
its position in the boot sequence was wrong.]

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
id.

**`PROTSHELL=` is ~~OS/2's PID-1 equivalent~~ the system's lifetime supervisor process, and this is a contract, not a convention.** [2026-10-01: pid 1 on OS/2 is the SYSINIT process (Stage 5a), and `PROTSHELL=` runs as SYSINIT's child: ~~pid 2~~ parent pid 1, screen group 0 on the measured SMP boots `[OBS]` (kernel-debugger LIS reads, 2026-10-01); its own pid was 0x13, after the file-system check program (pid 2) and the RUN= daemons ~~(Warp Server for e-Business 14.104a SMP kernel)~~ [the measured kernel was 14.089 SMP; 14.104a is the build whose bytes were read]. The "PID-1" analogy was to a Unix init; what it was meant to convey, that the shell never exits and supervises the system, stands as written below.] An earlier
version of this paragraph said the process is "launched like any other"; that is wrong in emphasis
and misleads about three things at once.

- **It does not exit.** In normal operation the shell process runs for the life of the system.
  **Exiting it takes the system down: with `PROTSHELL=CMD.EXE`, typing `exit` at the prompt
  reboots the machine.** `[OBS - author, from daily OS/2 use 1995-2006]` So "the shell
  terminated" is not an event a running OS/2 has a state for; it is shutdown.
- **It is a supervisor.** `[DOC-IBM]` *"It is the Shell process that is responsible for restarting
  the Workplace process in the event that it is killed as a result of a trap"* - the Shell process
  (`PROTSHELL=`) launches the Workplace process (`SET RUNWORKPLACE=`) and restarts it if it traps.
  Both default to `PMSHELL.EXE`, which *"is designed to distinguish between being started as the
  Shell process versus being started as the Workplace process."* (IBM Workplace Shell Programming
  Guide, "The Workplace process".)
- **It is NOT privileged, and session-manager authority has nothing to do with it.** ~~The kernel
  gives it privileged identity ... authority cannot be self-granted by calling more APIs.~~
  **RETRACTED the same day it was written** (observed): *"you can set `PROTSHELL=CMD.EXE` and at
  the command prompt run `pmshell` and it works fine. The session manager contract isn't because it
  was or wasn't specified in `PROTSHELL=`, it's because it registered itself with the session
  manager APIs."* Confirmed by disassembly: `DOSSMINITIALIZE` (obj3+0x9ef0) has **no authorization
  gate at all** - prologue straight to `cmp word [es:di],0x10` on the caller's own block, then it
  writes `ShellPID` from the caller's LIS. Any process may call it; ~~the last valid caller becomes
  the base shell~~ **only the first registration takes effect** [2026-10-12, Rule 1.7: a second
  `DOSSMINITIALIZE` finds the session manager already initialised, skips the `ShellPID` store and
  returns 0, so it does not take over `[OBS-RE]`]. See `session-manager.md`, "The shell IS the
  session manager", and "What registration runs" for what the first registration does.

So the PID-1 analogy is right about **lifecycle** and wrong about **authority**: `PROTSHELL=` is the
process the kernel starts and whose exit ends the system, and that is all. It gets no session
privilege the shell it launches could not have taken for itself - and on a `PROTSHELL=CMD.EXE`
system, running `pmshell` by hand is exactly a process taking it.

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
  order, so it stays deliberately hedged (see `config-and-environment.md`). [2026-10-01: for the
  ring-3 phase it is no longer hedged: environment and NLS precede `DEVICE=`/`IFS=`, [OBS-RE] from
  the kernel's `syiProcess` call order (Stage 5a). Not covered by this ratification: Stage 5a itself,
  and the corrections to the overview and Stages 8-9, all added 2026-10-01.]
