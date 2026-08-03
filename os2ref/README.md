# OS/2 Internals Reference

A **project-agnostic** reference on how OS/2 (Warp 4 / 4.5) works internally - the boot
sequence, kernel structures, ABIs, and subsystem contracts - synthesized and verified from
IBM primary sources and reverse engineering of the real OS/2 binaries.

## Why this exists
OS/2's internals are absent from LLM training data and scattered across the IBM DDK, the
OS/2 Toolkits, redbooks, and decaying community archives. This corpus collects the verified
facts in one ingestible place so **any** OS/2 project - or any model - can use them as
reference. It describes **OS/2 itself** - the system's own behaviour and interfaces, independent of
any particular implementation or codebase that consumes it.

## Provenance - every fact is sourced
Much of this is reverse-engineered, so each claim is tagged with how it was established, so a
reader knows what is IBM's word versus an observation of the binaries, and can re-verify it:

- **[DOC-IBM]** - IBM documentation: the DDK (`infoseg.h`, `devhlp.inc`, the PDD / GRADD /
  DISPLAY reference books), the OS/2 Toolkit headers (`bsedos.h`, `bsedev.h`), redbooks.
  Authoritative for **meaning** - units, semantics, error codes.
- **[OBS-RE]** - observed by reverse-engineering the real OS/2 binaries (the debug kernel
  `os2krnl` + symbols, `PMMERGE`, `PMDD`, ...) or the OS/2 kernel debugger on real hardware / a
  VM. Authoritative for **shape** - offsets, sizes, call order - and for facts IBM never
  documented. This is an interpretation of the binary; it is marked so it is never mistaken
  for IBM's word.
- **[DOC]** - other published references (osFree, EDM2), cross-checked.
- **[SRC]** - read directly from the source of a component that is *not* OS/2 itself but ships
  with it or on it, with file and line cited (e.g. kLIBC / LIBC Next, in
  `klibc-runtime-glue.md`). Authoritative for **what that component actually does** - it is the
  implementation, not a description of it - but it is *not* IBM's word about OS/2, and it can
  change with the component's version in a way an OS/2 ABI fact cannot. Where a `[SRC]` reading
  and a `[DOC-IBM]` statement disagree about OS/2 itself, `[DOC-IBM]` describes the platform and
  `[SRC]` describes that one implementation's behaviour on it.
- **[unverified]** - an inline marker on an individual claim the author could not confirm against
  any source at hand (used sparingly, in place of asserting it); everything else is sourced.

A doc may also carry a dated **"Ratified"** note. That records a pass where the doc's claims were
re-checked field-by-field against a named primary (a Toolkit/DDK header, an IBM book) and either
confirmed, upgraded to `[DOC-IBM]`, or corrected in place. It is a statement about *that* review,
not a guarantee: a doc without one has simply not had that second pass, and its own per-claim
provenance tags still apply.

Canonical **IBM names** are used throughout (`InfoSegGDT`, `SIS_FgndPID`, `DosQuerySysInfo`),
never a project's transcription of them.

## How to read this corpus
Start with **`boot-sequence.md`** - the 12-stage spine that names every subsystem and links to its
deep reference. From there, the **internals** docs explain how the system works; the
**application-programming** docs are the API surface a program calls (grouped below by area) and are
each self-contained (a struct or flag may be repeated across docs by design, so any one reads on its
own). Most docs end with a **See also** pointing to their closest neighbours.

## Router - task -> doc(s)
Find the row that matches what you are doing and load only those docs.

| If you are... | Load |
|---|---|
| Opening/reading/writing files, directories, find-first | `file-io.md` |
| Reading or writing extended attributes | `extended-attributes.md` |
| Allocating, sharing, or suballocating memory | `memory-api.md` (+ `memory-model.md` for why) |
| Diagnosing `ERROR_NOT_ENOUGH_MEMORY` - arena limit or actual RAM? | `memory-model.md` section "Address space vs. committed storage" |
| Starting processes or threads, exit lists, priorities | `process-thread.md` |
| Semaphores, pipes, queues, IPC | `ipc-synchronization.md` |
| Installing an exception handler, handling a trap | `exceptions.md` |
| Loading a DLL / resolving a proc address / `_DLL_InitTerm` | `module-dll.md` |
| Writing a `.DEF`, fixing ordinals or linkage errors | `calling-convention.md` + `module-dll.md` |
| Decoding an `APIRET` / `ERROR_*` / `PMERR_*` | `error-codes.md` |
| Timers, date/time | `timers.md` |
| Creating a PM window, message loop, `WM_*` handling | `pm-window-messaging.md` |
| Buttons, entry fields, containers, notebooks | `pm-controls.md` |
| Needing a toolbar, status bar, progress bar, splitter, tooltip - a control PM does not ship | `pm-controls-thirdparty.md` |
| Dialog templates, menus, string tables, `.RC` resources | `resources-and-dialogs.md` |
| Standard file / font dialog (`WinFileDlg`, `FILEDLG`, `FDS_*`, `DID_*`) | `resources-and-dialogs.md` section 10 |
| Which DLL really implements a `Win*`/`Gpi*` API; replacing or interposing on a system DLL | `module-dll.md` section "Where the PM APIs actually live" |
| Drawing: lines, areas, bitmaps, coordinate spaces | `gpi-drawing.md` |
| Fonts, text metrics, metafiles | `gpi-fonts-and-metafiles.md` |
| Printing / the spooler / `DevOpenDC` | `printing-spooler.md` |
| Clipboard or DDE | `clipboard-dde.md` |
| Drag and drop | `drag-drop.md` |
| Text-mode (VIO/KBD/MOU) console apps | `vio-kbd-mou.md` |
| `.INI` profiles (`PrfQueryProfileData`, ...) | `profiles-ini.md` |
| Code pages, Unicode, `UniTranslateString` | `unicode-conversion.md` |
| Video playback / DIVE / MMPM/2 | `dive-video.md`, `mmpm2-multimedia.md` |
| Real-time PCM audio / DART / low-latency sound / game audio | `dart-audio.md` |
| REXX: embedding, external functions, macrospace | `rexx-api.md` |
| Subclassing a WPS class, SOM methods | `wps-classes.md` + `som.md` |
| Sockets / TCP-IP | `tcpip-sockets.md` |
| Porting Unix/POSIX code with GCC/kLIBC (fd/`fork`/signal/`malloc`/socket emulation) | `klibc-runtime-glue.md` |
| Why `fork()` fails, is slow, or needs `-Zfork`; how kLIBC fd/signal/socket internals map to `Dos*` calls | `klibc-runtime-glue.md` |
| Which signal a `SIGSEGV`/`SIGCHLD`/job-control signal actually maps to, or why `SIGWINCH` never fires | `klibc-runtime-glue.md` section 4 |
| Hosting a console/curses app off a pty - keyboard input or terminal size wrong | `klibc-runtime-glue.md` section 8 |
| `setpgid`/`tcsetpgrp`/`ttyname`/`FIONREAD`/`select` on a tty returning ENOSYS or EINVAL; job control won't start | `klibc-runtime-glue.md` section 9.1 |
| A shell hangs on every *external* command (but `exec cmd` and builtins work) - custom fd backend missing its fork hook | `klibc-runtime-glue.md` section 9.2 |
| `/dev/tty` opens and `isatty()` says yes, but reads fail | `klibc-runtime-glue.md` section 9.3 |
| Rebuilding an installed OS/2 package to patch it (SRPM -> autoconf on OS/2 -> private-DLL test) | `../recipes/rebuild-a-netlabs-package.md` |
| Writing a device driver or IFS | `drivers.md` (+ `kernel-services.md` for DevHlp) |
| 16<->32-bit thunking | `thunking.md` |
| Inspecting an LX/NE binary, fixups, page layout | `executable-formats.md` |
| Understanding boot order or where a subsystem fits | `boot-sequence.md` |
| Disk/volume IOCtl, VPB/DPB | `dasd-volume.md` |
| CONFIG.SYS processing, the environment block | `config-and-environment.md` |
| Sessions / screen groups | `session-manager.md` |
| Device monitors, debug output | `device-monitors-and-debug.md` |
| InfoSeg / `DosQuerySysInfo` | `infoseg.md` |
| The PM message queue's kernel wake | `message-queue.md` |
| The PM graphics path (PMMERGE/GRADD) | `pm-graphics.md` |

## Kernel variant
OS/2 ships **uniprocessor** and **SMP** kernel variants. Where they differ (e.g. the local
InfoSeg is 36 bytes on the uniprocessor kernel, 44 on SMP), **both forms are given** and the
difference noted. An SMP kernel runs correctly on a single CPU (it reports one processor);
the LIS form follows the kernel *variant*, not the CPU count.

## Contents
- **`boot-sequence.md`** - kernel init -> the Workplace Shell, stage by stage, with the
  observable contract each stage establishes. The spine the subsystem references hang off.
- Per-subsystem deep references (full field-level detail the boot sequence points to):
  - `infoseg.md` - Information Segments (GIS / LIS) + `DosQuerySysInfo`
  - `memory-model.md` - arenas and selectors
  - `kernel-services.md` - DevHlp and the DOSCALLS surface
  - `dasd-volume.md` - disk IOCtl categories, volume/drive query, VPB/DPB
  - `config-and-environment.md` - CONFIG.SYS processing, the environment block, NLS
  - `session-manager.md` - sessions / screen groups
  - `drivers.md` - physical-device-driver and installable-file-system ABIs
  - `pm-graphics.md` - the Presentation Manager graphics path
  - `message-queue.md` - the PM message queue and its kernel wake
  - `thunking.md` - 16<->32-bit thunking
- Application programming interfaces (the API surface a program calls - the "how to build an
  OS/2 application" half):
  - `calling-convention.md` - the `_System`/`APIENTRY` linkage, `.DEF` files, ordinals
  - `error-codes.md` - the `APIRET` convention, the `ERROR_*` space, `DosErrClass` / messages
  - `file-io.md` - the Control Program file & I/O API (`DosOpen`/`Read`/`Write`/`FindFirst`/...)
  - `memory-api.md` - the application memory API (`DosAllocMem`, shared memory, suballocation)
  - `process-thread.md` - processes, threads, exit lists, priorities (`DosExecPgm`/`CreateThread`/...)
  - `ipc-synchronization.md` - mutex/event/muxwait semaphores, pipes, queues
  - `exceptions.md` - the `DosSetExceptionHandler` chain, `XCPT_*` codes, unwind / signals
  - `module-dll.md` - `DosLoadModule`/`DosQueryProcAddr`, `_DLL_InitTerm`, imports/forwarders
  - `timers.md` - `DosStartTimer`/`DosAsyncTimer`, the high-res timer, date/time
- Presentation Manager and text-mode application programming:
  - `pm-window-messaging.md` - `WinRegisterClass`/`WinCreateStdWindow`, the message loop, `WM_*`
  - `pm-controls.md` - the standard control classes (`WC_BUTTON`/`WC_ENTRYFIELD`/`WC_CONTAINER`/`WC_NOTEBOOK`/...) and their messages
  - `pm-controls-thirdparty.md` - third-party control classes (toolbar, status bar, splitter, 3D controls) surveyed by license, with each license read from the package that states it
  - `resources-and-dialogs.md` - resources (`.RC`, `DLGTEMPLATE`, menus, accelerators, strings) and dialog programming
  - `clipboard-dde.md` - the clipboard API and Dynamic Data Exchange (`WM_DDE_*`)
  - `drag-drop.md` - Direct Manipulation (drag & drop): `DRAGINFO`/`DrgDrag`/`DM_*`
  - `printing-spooler.md` - printing via a queued DC, `DevEscape`, the `Spl*` spooler API
  - `gpi-drawing.md` - the `Gpi*` drawing API, device contexts, presentation spaces, transforms
  - `gpi-fonts-and-metafiles.md` - GPI logical/outline fonts (`FATTRS`), bitmaps, and metafiles
  - `vio-kbd-mou.md` - text-mode video / keyboard / mouse (`Vio*`/`Kbd*`/`Mou*`)
- Persistence and file metadata:
  - `profiles-ini.md` - the `Prf*` profile (INI) API for persistent settings (`OS2.INI`/`OS2SYS.INI`)
  - `extended-attributes.md` - the EA model (`FEA2`/`GEA2`/`EAOP2`), standard EAs, `DosQueryPathInfo`/`DosSetPathInfo`
- Module format:
  - `executable-formats.md` - the LX (32-bit) and NE (16-bit) executable module formats
- Multimedia, internationalization, and networking:
  - `mmpm2-multimedia.md` - MMPM/2: the Media Control Interface (`mciSendCommand`/`mciSendString`) and MMIO
  - `dart-audio.md` - DART (Direct Audio RouTines): low-latency PCM streaming via `MCI_MIXSETUP`/`MCI_BUFFER` and the mixer's direct `pmixWrite`/`pmixEvent` entry points
  - `dive-video.md` - DIVE (Direct Interface Video Extensions): direct/offscreen video blitting
  - `unicode-conversion.md` - the `Uni*` codepage<->UCS-2 conversion API (`UconvObject`)
  - `tcpip-sockets.md` - the BSD-style sockets API (`socket`/`bind`/`soclose`/`select`)
- POSIX/Unix compatibility layer (source-verified, not IBM documentation - see the doc's own
  provenance preamble for the `[SRC]` tag this section introduces):
  - `klibc-runtime-glue.md` - how kLIBC/LIBC Next (the GCC C runtime) implements POSIX fds,
    `fork`/`exec`/`spawn`, signals, `malloc`, and BSD sockets on top of the native `Dos*`
    APIs and OS/2 TCP/IP stack documented elsewhere in this corpus

- Object model (the SOM runtime and the Workplace Shell built on it):
  - `som.md` - the System Object Model: classes, method resolution, IDL, the runtime API
  - `wps-classes.md` - Workplace Shell object classes (`WPObject` hierarchy) and class programming
- Scripting, diagnostics, and specialized services:
  - `rexx-api.md` - the REXX SAA C interface (`RexxStart`, `RXSTRING`, function/subcommand/exit handlers)
  - `device-monitors-and-debug.md` - device monitors (`DosMon*`) and the `DosDebug` interface

Each deep reference documents one subsystem's structures and ABIs to full field-level
detail; the boot sequence stays at contract level and points to them.
