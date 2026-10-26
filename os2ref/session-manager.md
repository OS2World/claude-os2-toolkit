# OS/2 Session Manager - Sessions and Screen Groups

The protected-mode session manager governs **sessions** (also called screen groups): independent
console/PM contexts, exactly one of which holds the foreground at a time. Initialized during
boot-sequence Stage 9.

Provenance: **[DOC-IBM]** IBM Toolkit `bsedos.h` (the session control APIs and their structures),
`#ifdef INCL_DOSSESMGR` block (Toolkit 4.5 `H/bsedos.h:2681-2788`).

## Session control APIs [DOC-IBM `bsedos.h:2685-2788`]

- **`DosStartSession(PSTARTDATA psd, PULONG pidSession, PPID ppid)`** - starts a new session
  (prototype `bsedos.h:2768-2770`). The `STARTDATA` structure (`bsedos.h:2685-2708`) specifies the
  program and arguments (`PgmName` / `PgmInputs`), the session type (`SessionType`:
  `SSF_TYPE_FULLSCREEN` 1 / `SSF_TYPE_WINDOWABLEVIO` 2 / `SSF_TYPE_PM` 3 / `SSF_TYPE_VDM` 4, etc.,
  `bsedos.h:2725-2734`), foreground vs background (`FgBg`: `SSF_FGBG_FORE` 0 / `SSF_FGBG_BACK` 1,
  `:2714-2715`), whether the new session is related to the caller so the caller can control it
  (`Related`: `SSF_RELATED_INDEPENDENT` 0 / `SSF_RELATED_CHILD` 1, `:2711-2712`), inheritance
  (`InheritOpt`: `SSF_INHERTOPT_SHELL` 0 / `SSF_INHERTOPT_PARENT` 1, `:2721-2722`), and an optional
  icon (`IconFile`) / title (`PgmTitle`) / environment (`Environment`).
- **`DosStopSession(scope, idSession)`** - stops a session (prototype `bsedos.h:2777-2778`); `scope`
  is `STOP_SESSION_SPECIFIED` 0 (one) or `STOP_SESSION_ALL` 1 (all related) (`:2760-2761`).
- **`DosSelectSession(idSession)`** - brings a session to the foreground (prototype
  `bsedos.h:2775`).
- **`DosSetSession(idSession, PSTATUSDATA)`** - changes a session's status via the `STATUSDATA`
  structure (`bsedos.h:2744-2750`, prototype `:2772-2773`): selectability (`SelectInd`:
  `SET_SESSION_SELECTABLE` 1 / `SET_SESSION_NON_SELECTABLE` 2) and bond (`BondInd`:
  `SET_SESSION_BOND` 1 / `SET_SESSION_NO_BOND` 2) (`:2753-2757`).

### Starting a session from a batch file - synchrony is unconditional

**A batch file (`.CMD`) executes its program lines synchronously, and the
application's type is not a factor.** `CMD.EXE` waits for whatever a line
launched before advancing to the next line, whether that program is
full-screen, windowed-VIO, or Presentation Manager. There is no app-type test
that makes a launch asynchronous.

**This is the point most likely to be got wrong, because Windows behaves
differently.** Windows' `cmd.exe` waits for a console-subsystem program invoked
from a `.cmd` but *not* for a GUI-subsystem one - the asymmetry behind the PE
subsystem field and the reason `START /WAIT` exists there. **That convention is
Windows', not OS/2's**, and importing it produces a plausible, wrong model of
OS/2 batch behaviour. `DOS`/`COMMAND.COM` is not a useful analogy in the other
direction either: it is synchronous by construction, the OS being
single-tasking.

**What the application type DOES decide is the launch MECHANISM, not the
synchrony** - and conflating the two is what makes the Windows analogy look
plausible. `CMD.EXE` classifies the target with `DosQueryAppType` and then
picks: a target of its own kind runs in the same session via `DosExecPgm`; a
Presentation Manager target always goes through `DosStartSession` into a new
session. Both are then waited on - the in-session path through `DosExecPgm`'s
own synchronous form, the session path through the child session's termination
queue (the parent bonds the child with `DosSetSession` and blocks in
`DosReadQueue` on the `TermQ` it named in `STARTDATA`). Same contract, two
mechanisms.

`[DOC-IBM]` for the mechanism split - `DosStartSession` Notes, *"You must use
DosStartSession to start a new process from a process that is of a different
type. For example, use DosStartSession to start a Presentation Manager process
from a non-Presentation Manager process."* (Control Program Reference).
`[OBS-USER]` + `[OBS]` for the unconditional synchrony - firsthand testimony
from someone who ran OS/2 daily for a decade, 2026-08-19, corroborated by a
measured capture on real OS/2 the same day: a `.CMD` line running a 10-second
program produced a 10-second gap before the next line, while a `DETACH`ed one
produced none - the control proving the instrument could have shown the
non-halting outcome.

---

### Session-control semantics and return codes [DOC - EDM2]

**`DosStartSession`** - the returned session id and process id are set **only when `Related` = 1**
(a child session); for an independent session they are not returned. A parent session establishes a
parent *session*/child *session* relationship, **not** a parent/child *process* relationship - the
returned process id therefore cannot be used on calls that require process parentage (e.g.
`DosSetPrty`). Child-session termination is reported through a **termination queue** the parent
creates (a queue named in `TermQ`) before its first `DosStartSession`; the queue receives a
`{session id, result code}` element per terminating child.

> **Qualified 2026-10-12 `[OBS]`** (the statement above is kept as the documented contract):
> measured on Warp 4.50, it holds for an ordinary parent and **not when the parent is the
> registered shell itself** - the shell received no element, and its later starts naming a
> `TermQ` answered 461. See "A registered text-mode shell under `PROTECTONLY=YES`" below.
> Likewise *"for an independent session they are not returned"* holds (id 0, pid 0), but the
> session **is** created and its program runs.

**PROVENANCE UPGRADED [DOC - EDM2] -> [DOC-IBM]** (2026-08-19): verified verbatim
against IBM's own *Control Program Reference*, `DosStartSession`, "Parameter -
PID": *"The address of a doubleword that receives the process identifier
associated with the child process created. PID is returned only when the value
specified for Related is 1. The PID returned may not be used on any system
functions (for example, DosSetPriority) that require a parent process/child
process relationship."* The `SessID` out-parameter carries the same
`Related`-1-only condition in its own paragraph.

**The third parameter really is a process id, and it is 16-bit.** The 32-bit
prototype is `DosStartSession(PSTARTDATA, PULONG pidSession, PPID ppid)`
(`os2tk45/.../bsedos.h:2768`), and the 16-bit one is
`DosStartSession(PSTARTDATA, PUSHORT, PUSHORT)`
(Open Watcom 1.9 `h/os21x/bsedos.h:720`) - so both out-parameters narrow to
`USHORT` in the 16-bit API, consistent with "Process identifiers" above. Worth
stating explicitly because the two facts pull in opposite directions and invite a
wrong reading: the value **is** a real pid (so it must come from the pid space),
while it is simultaneously **not** usable for parent/child process operations (so
it must not be treated as making the caller that process's parent).

| rc | Name | Meaning |
|----|------|---------|
| 0 | NO_ERROR | success |
| 370 | ERROR_SMG_NO_SESSIONS | no sessions available to start |
| 418 | ERROR_SMG_INVALID_CALL | call not valid |
| 453 | ERROR_SMG_INVALID_START_MODE | `FgBg` value not valid |
| 454 | ERROR_SMG_INVALID_RELATED_OPT | `Related` value not valid |
| 457 | ERROR_SMG_START_IN_BACKGROUND | foreground start requested but neither caller nor any descendant is in the foreground - session was started in the background |
| 460 | ERROR_SMG_PROCESS_NOT_PARENT | caller is not the parent session |
| 461 | ERROR_SMG_INVALID_DATA_LENGTH | `STARTDATA` `cb` (length) not valid |
| 478 | ERROR_SMG_INVALID_TRACE_OPTION | `TraceOpt` value not valid |
| 491 | ERROR_SMG_INVALID_PROGRAM_TYPE | program type not valid for the requested session |
| 492 | ERROR_SMG_INVALID_PGM_CONTROL | `PgmControl` value not valid |
| 493 | ERROR_SMG_INVALID_INHERIT_OPT | `InheritOpt` value not valid |
| 503 | ERROR_SMG_INVALID_DEBUG_PARMS | debug/trace parameters not valid |

Any error from `DosOpen`, `DosLoadModule`, or `DosExecPgm` may also be returned.
[DOC - EDM2 "DosStartSession (OS/2 1.x)"]

`[OBS-RE]` (added 2026-10-12): a DOS session type (`SessionType` 4, 7 or 0xD-0x12) started under a
non-PM shell on a system whose MVDM is not initialised returns **641 `ERROR_VDM_DOWN`**, from the
kernel's `DosCreateVDM`, which the table above does not list; under a PM shell on a `PROTECTONLY=YES`
system the same start answers 491. See "A DOS-type session start with no VDM" below.

**`DosStopSession`** - may be issued by a parent only for a child session started with `Related` = 1;
independent sessions cannot be stopped this way, and stopping a session also terminates its
descendants. A normal return code does **not** guarantee termination - the target process may refuse
to exit; the only certain confirmation is the termination-queue notification. [DOC - EDM2
"DosStopSession (OS/2 1.x)"]

| rc | Name | Meaning |
|----|------|---------|
| 0 | NO_ERROR | success |
| 369 | ERROR_SMG_INVALID_SESSION_ID | `SessID` not valid (ignored when scope = all) |
| 418 | ERROR_SMG_INVALID_CALL | call not valid |
| 452 | ERROR_SMG_SESSION_NOT_PARENT | caller is not the parent of the target session |
| 458 | ERROR_SMG_INVALID_STOP_OPTION | scope/target option not valid |
| 459 | ERROR_SMG_BAD_RESERVE | reserved parameter was not a zeroed doubleword |

[DOC - EDM2 "DosStopSession (OS/2 1.x)"]

## Application type [DOC-IBM `bsedos.h:2781-2811`]

`DosQueryAppType(pszName, PULONG pFlags)` (prototype `bsedos.h:2781-2786`) reports an executable's
type via `FAPPTYP_*` bits (`bsedos.h:2795-2811`) - distinguishing Presentation Manager
(`FAPPTYP_WINDOWAPI` 0x0003), VIO-windowable (`FAPPTYP_WINDOWCOMPAT` 0x0002), full-screen
(`FAPPTYP_NOTWINDOWCOMPAT` 0x0001), and DOS/Windows programs (`FAPPTYP_DOS` 0x0020,
`FAPPTYP_WINDOWSREAL` 0x0200, `FAPPTYP_WINDOWSPROT` 0x0400) - which the session manager uses to
decide the session kind a program needs. (Also aliased `DosQAppType`, `bsedos.h:2765`.)

## Foreground and screen-group state [DOC-IBM]

The current foreground is observable through several surfaces (see `infoseg.md`):
- `DosQuerySysInfo(QSV_FOREGROUND_FS_SESSION)` - the foreground full-screen session id
  (`QSV_FOREGROUND_FS_SESSION` = 24, Toolkit `bsedos.h:2523`; there is also
  `QSV_FOREGROUND_PROCESS` = 25 for the foreground process id, `:2524`).
- The Global InfoSeg `SIS_CurScrnGrp` (foreground screen group) and `SIS_FgndPID` (foreground PID)
  (IBM DDK `base/h/infoseg.h:69,76`).
- The Local InfoSeg `LIS_CurScrnGrp` and `LIS_Fgnd` (whether this process is in the foreground)
  (IBM DDK `base/h/infoseg.h:194,200`).

**These are the *surfaces*. Which call MOVES each of them, and in what order on
each path, is "The complete foreground contract" below** - added 2026-09-20, and
cross-referenced here because the two sections were written nine hundred lines
apart and neither pointed at the other. That section also adds the two the list
above does not name: the kernel words behind `QSV_FOREGROUND_FS_SESSION` and
`QSV_FOREGROUND_PROCESS`, which are **not** copies of the InfoSeg fields.

## Process and session enumeration [DOC-IBM]

`DosQProcStatus` / `DosQuerySysState` return a snapshot of the process, thread, session, module, and
semaphore tables - used for task lists, "which session owns this process," and hung-application
detection. The 32-bit `DosQuerySysState(EntityList, EntityLevel, pid, tid, pDataBuf, cbBuf)` is
confirmed at Toolkit `bsedos.h:3589-3594`, with the `QS*REC` record structures for each table
threaded off `QSPTRREC` (`bsedos.h:3578-3587`): `QSGREC` global, `QSPREC` process, `QSTREC` thread,
`QSS16HEADREC`/`QSS32REC` semaphore, `QSMREC` shared-mem, `QSLREC` module/MTE, `QSFREC`
file-system. `DosQProcStatus` is the 16-bit predecessor and is **not present in the 4.5 Toolkit
32-bit header** - sourced only to its 32-bit successor here [OBS-RE for the 16-bit name].

## Internal mechanism: how a session is created and how the foreground switches [OBS-RE]

Everything above is the documented public contract. This section is the internal implementation
behind it - reverse-engineered from the real Warp 4.5 binaries (`SESMGR.DLL`, `DOSCALL1.DLL`,
`PMMERGE.DLL`) by static disassembly plus live confirmation on a running debug-kernel VM (KDB).
Provenance for this whole section is **[OBS-RE]** unless a line says otherwise; no IBM document
describing this mechanism is known to exist (checked: IBM's own DDK, the Toolkit 4.5 Control
Program Guide and Reference, and the EDM2 article corpus all cover only the public API surface
above, never the internals).

### `SESMGR.DLL` is a pure forwarder

`SESMGR.DLL` (the module `DosStartSession`/`Select`/`Set`/`StopSession` resolve to via `DOSCALLS`)
carries no code of its own - every one of its ~35 ordinals (`STARTSESSION`, `SELECTSESSION`,
`SETSESSION`, `STOPSESSION`, `SMSWITCH`, `SMSERVEAPPREQ`, `SMGETAPPREQ`, `SMSTART`, `SMSETTITLE`,
`SMPAUSE`, and others) forwards straight through to internal entry points inside `DOSCALL1.DLL`.
The real implementation - and the real complexity - lives there, not in `SESMGR.DLL` itself.

### The unified request-block object

All four public session-lifecycle calls (`DosStartSession`/`Select`/`Set`/`StopSession`) build the
**same kind of object**: a variable-sized "request-block," fresh per call, sized by operation (~~218
bytes for Start~~ **0x77E or 0x882 bytes for Start** - corrected 2026-10-12, see "`DosStartSession` on
the requester side" below; 218 is the SGCB's size; smaller, ~38-44-byte records for
Select/Set/Stop). Every block shares a small
universal header - a constant tag byte, an operation-code byte (`0`=Start/`1`=Select/`2`=Set/
`3`=Stop), and a few fields copied from the target screen group's control block at allocation time
- followed by an operation-specific payload (for Start: the `STARTDATA` fields, including four
packed, null-terminated strings - title, program name, command-line inputs, and the `TermQ` queue
name - laid out back to back with an offset table pointing at each).

Every operation is dispatched through **one single internal function**, keyed on the block's
operation-code byte. For a Start request specifically, that dispatcher calls the internal
`ExecPgm` entry point directly (mapping `STARTDATA`'s fields onto the real 7-parameter
`Dos16ExecPgm`-shaped signature: object name/length, exec flags, argument string, environment,
result buffer, and the program name), and - for every operation, not just Start - writes the
**entire request-block, unmodified, as the payload** of a queue-write to a well-known named queue,
`\QUEUES\SESMGR\APPREQQ`. The queued packet *is* the request-block, not a separately-assembled
wire format.

> **EXTENDED `[OBS-RE]` - the queue write is not a notification, and reading it as one understates
> the mechanism.** The sentence here used to end "that queue write is how the session-manager UI
> (the Window List) learns a new session exists or a session's state changed." True as far as it
> goes, and wrong about the shape: **the AppReq queue is a synchronous request/response channel,
> and the request-block doubles as the response.** The serve-side dispatcher writes the operation's
> real result code back into the block's own `+0x06` field - the same offset the requester writes on
> its own error path - and then posts **two completion semaphores embedded in the block itself**, at
> `+0x10` and `+0x18`, to release the requester that is blocked on them. So the requester does not
> fire and forget: it builds the block, queues it, blocks, and reads its answer out of the block it
> allocated.
>
> The dispatcher reads the operation from `+0x04`, range-checks it `0`-`3` (out of range ->
> `0x1a1`), and holds a single session-mutation lock (obj5+`0x45e`, shared with `DOSSMSWITCH` and
> `DOSSMCHILDEXIT`) for the whole of one request. `+0x08` carries the requesting session's own
> group id.

### `DosStartSession` on the requester side: the `STARTDATA` validator, the block, and its lifetime `[OBS-RE]`

Read 2026-10-11 and 2026-10-12 from the Warp 4.5 uniprocessor `DOSCALL1.DLL` with its matched
`.SYM`, and recorded in unpublished notes; the validator was
re-read the second day, which agrees. Offsets are
object-3 offsets of that image unless named. Items marked *one read* were read once and not
re-read.

**The validator.** `DOSSTARTSESSION` passes the caller's `STARTDATA` to an unlabelled helper
(obj3+0x8ca8) with `StartParmsMaxLen` (obj5+0xb76, IBM's own symbol) as the maximum. It never
returns early: each failing check overwrites the answer, so **the last failing check in this order
wins**:

1. `Length` > the maximum -> 461. With no PM (`PM_Present` 0) the helper's own copy of the length is
   also clamped to the maximum.
2. length >= 30 and `InheritOpt` > 1 -> 493.
3. length >= 32: `SessionType` 5, 6, 8-12 or > 0x12 -> 491; the DOS types (4, 7, 0xD-0x12) -> 491 only
   when `SMG_Flags` bit 2 is set (below).
4. length >= 50 and `PgmControl & 0x7FF0` -> 492.
5. `TraceOpt` 2 without `Related` 1 and a `TermQ` -> 503.
6. `Related` > 1 -> 454, else `TraceOpt` > 2 -> 478, else `FgBg` > 1 -> 453.
7. length not one of 24, 30, 32, 50 or the maximum -> 461.

- **The clamp is of the helper's own copy, never of the caller's field.** `DOSSTARTSESSION` then
  reads `InheritOpt`, `Environment` and `SessionType` by the caller's own `Length`, so a start that
  skipped the `SessionType` check still uses the `SessionType` it was given.
- **The helper writes the caller's `STARTDATA`:** at length >= 32 with `SessionType` 4 or 0xD-0x12
  (not 7) it clears `PgmControl` bit 3 (`SSF_CONTROL_NOAUTOCLOSE`), at `+0x28`, whatever the
  caller's `Length`.
- **With no PM, any final 461 is forgiven** (obj3+0x34f4-0x3507) - an over-long, short or odd
  `Length` alike - and the start goes on. A forgiven start that later fails with 343 answers **461**
  instead (obj3+0x3843-0x384e): a missing `\QUEUES\SESMGR\APPREQQ`, or the shell's open of the
  `TermQ` failing, whose 343 comes back the same way.
  **`[OBS]` 2026-10-12** (a registered non-PM shell, `PROTECTONLY=YES`, so a maximum of 30 and a
  32-byte `STARTDATA` forgiven): a start before `APPREQQ` existed, and a start naming a `TermQ`
  that did not exist, each answered **461**, never 343 - what this rule predicts. But "the start
  goes on" is not the whole story for an odd length: **a `Length`-23 start never returned**
  (3 of 3 runs, the shell as requester). Where it stopped - the requester's wait, the string
  copy into a block of `Length` + 8 bytes (below), or the serving thread - is not established;
  a kernel-debugger look at both threads of the hung shell would settle it.
- **The maximum is set by the registering shell** (`DOSSMINITIALIZE`): 60 for a PM block; 32 for a
  non-PM block, or for a PM block whose `OS2SM.DLL` entry points do not resolve; and **30 when
  `SIS_ProtMdOnly` (Global InfoSeg `+0x1b`) is set and there is no PM**. The same `SIS_ProtMdOnly`
  branch sets `SMG_Flags` bit 2. A census of a linear disassembly finds that branch DOSCALL1's only
  reader of `SIS_ProtMdOnly`, and bit 2's only setter, with check 3 its only test.
- So **under `PROTECTONLY=YES` a DOS session type answers 491 only under a PM shell.** With no PM the
  maximum is 30, the clamped length never reaches check 3, and the start reaches the shell, where it
  fails with 641 - see "A DOS-type session start with no VDM" below.
  **`[OBS]` 2026-10-12, both halves measured under a non-PM shell with `PROTECTONLY=YES`:** a
  32-byte background start of `SessionType` 4 answered **641**, and one of `SessionType` 5 answered
  **0** with a session (id 16), where a maximum of 32 would have given 491.

**The block's size.** The validator leaves the size in `BX`: 0x776 for lengths 24, 30 and 32, 0x87A
for 50 and the maximum, then `add bx,8` (obj3+0x8d7e) - so a Start block is **0x77E or 0x882
bytes**. A length outside the five (check 7's 461, forgiven with no PM) leaves `BX` = `Length` + 8,
smaller than the copy that follows. `DOSSMGETMEM`'s failure is its allocator's rc - `DosAllocSeg`'s
or `DosReAllocSeg`'s when a heap segment cannot be made or grown, `DosSubAlloc`'s when every heap is
full - so an exhausted allocation answers 8; 463 does not come from there (*one read*).

**The strings.** `PgmTitle`, `PgmName`, `PgmInputs` and `TermQ` are copied at every length;
`IconFile`, the fifth, only at length >= 50. The copy (obj3+0x3665-0x36b0) is an unbounded
`lodsb`/`stosb` loop to the NUL, into the block from `+0x62`, each string's offset stored from
`+0x38` on; a zero selector copies an empty string. Nothing bounds it: a string longer than the
block overruns it (*one read*).

**The block's lifetime.**
- `REQUESTBLOCKALOC` gates the caller (418; the related-start 460), registers `PARENTEXITLIST` with
  `DosExitList` on every request unless the caller is already in exit-list processing, files the
  block in the next slot of an **outstanding-request table** and sets the block's `+0x18`. The table
  is reached through `SMG_INSTANCE` (obj5+0xae2), a far pointer into DOSCALL1's per-process instance
  object, so **the table is per process**; its count is at `+0x80`.
- `APPSENDREQUEST` clears `+0x06`, queues the block (`+0x1c` = 1, then 2) and waits on `+0x10` with
  no timeout, **retrying while the wait answers 95** (`ERROR_INTERRUPT`). For `InheritOpt` 1 it then
  runs its own exec, stores the rc at `+0x06` and handshakes a second time on `+0x10`/`+0x14`.
- **Signals are held across the request:** `APPSENDREQUEST` brackets it with `DosHoldSignal(1)` /
  `DosHoldSignal(0)` (DOSCALLS #13), and `REQUESTBLOCKALOC` brackets its table insert the same way.
  So only process termination ends the wait.
- **The requester frees its own block, after the answer:** it removes its slot (the rest shifted
  down) and frees the block with `DOSSMFREEMEM`.
- **A requester that dies with requests outstanding is cleaned up by `PARENTEXITLIST`.** It walks the
  table: first, for every block, `+0x1e` := 1 (abandoned) and a clear of `+0x14`; then, per block, if
  `+0x1c` is 2 (queued, not yet taken) it waits on `+0x18` (retrying on 95), and unless `+0x1c` is 1
  it frees the block with `DOSSMFREEMEM`. The shell's `DOSSMGETAPPREQ` skips an abandoned block
  (clears `+0x18`, answers 0xDEAD), which `DOSSMSERVEAPPREQ` treats as "loop again".

**The serve side's answer** (`APPSTARTSESSION`'s tail, read 2026-10-11): on failure the answer's
session id and pid (`+0x42`/`+0x44`) are zeroed; `WinInitSwEntry` is called only when `PM_Present`
is 1; and for an independent start (`Related` 0) `+0x42`/`+0x44` are zeroed again, so **an
independent start answers no session id and no pid**. `[OBS]` 2026-10-12, a non-PM shell as
requester: rc 0, id 0, pid 0 - **and the session exists**: `DosSMGetStatus` listed it right after
the call and its program ran. The zeroing hides the answer; it does not undo the start.
`DOSSMDOAPPREQ` takes `SMRoutSem` (obj5+0x45e) with DOSCALLS #161 `DosFSRamSemRequest`.

**Defects on the failure paths** (read 2026-10-12; IBM's behaviour as found, not a contract to
copy):
- The string copy's failure exit (obj3+0x3826-0x3842) frees the block and the environment segment
  but **leaves the block's slot filed**. The next `APPSENDREQUEST` then removes slot 0 - that stale
  pointer - and `PARENTEXITLIST` would free it a second time.
- `PARENTEXITLIST`'s free test is only `+0x1c == 1` (obj3+0xab3d-0xab4e), so **a block the shell
  has taken (state 3) is freed at once**, and the shell's later writes to `+0x06`, `+0x18` and
  `+0x10` land in freed memory.
- `PARENTEXITLIST`'s own group lookup, `DOSSMGETSGCB(LIS screen group, 0)` (obj3+0xab63-0xab70),
  **takes `SMQueueRamSem`**: with bit 15 of the flags clear, `DOSSMGETSGCB` brackets the lookup with
  `DosHoldSignal` and `DosFSRamSemRequest`/`Clear` (#161/#162) on `SMQueueRamSem` (obj7+0xc0),
  released before it returns. `APPSTARTSESSION`'s and `REQUESTBLOCKALOC`'s lookups pass 0x8000 and
  take none.
- `APPSTARTSESSION`'s failed SGCB lookup enters its failure tail at obj3+0x3c9d, past the `pop si`
  at 0x3c9c. The rollback closes `TermQ` and clears `SGCB+0x14` bit 3 only when `SGCB+0x20` is
  non-zero; `SGCB+0x1e` := 0 always.
- `APPSENDREQUEST` closes its `APPREQQ` handle only when the answer is 0 and the caller is not the
  shell (obj3+0x3f5f-0x3f78), so **any failed start leaves that queue handle open in the requester**
  (unpublished notes; whether a later request reuses it was not followed).

### The persistent Screen Group Control Block (SGCB)

> **SUPERSEDED 2026-09-04 by the field table below, which is read out of the
> instructions rather than assembled from two partial readings. The block is
> kept, not deleted (Rule 1.7).** `[OBS-RE]` Enumerated rather than summarised,
> because correcting one row and leaving the rest silently certifies the rest:
>
> - **`+0x4c`/`+0x4e` is wrong in kind** - it is not a far pointer and holds no
>   buffer address. See "corrected, not refined" below.
> - **`+0x2`/`+0x4` and `+0x6`/`+0x8` are given in the wrong order.** They are
>   *offset then selector*, which is what `lfs si,[fs:si+0x2]` in `APPSTOPSESSION`
>   requires and what `mov [es:di+0x2],di` / `mov [es:di+0x4],es` writes.
> - **`+0x26` is a word, not a byte** (`mov word [es:di+0x26],0x0`,
>   `test word [fs:si+0x26],0x1`), and bit 1 is also in use.
> - **`+0x10` is a word, not a byte**, and calling it a repeat of `+0xa`'s high
>   byte understates it: it is independent storage that happens to be written
>   with the same value, and one of its two writers touches only its low half.
> - The prose above the table says the pointer table is "confirmed to grow
>   dynamically past" 25 slots. **That is right** - `DOSSMADDSGCB` compares the
>   new sgid against a slot-count byte and, when it does not fit, does
>   `add byte [fs:si],0x8`, `shl cx,3` and reallocates, i.e. it grows by eight
>   slots at a time. (An earlier revision of this very block called that claim
>   wrong. It was not; the reallocation is right there in the constructor's tail.
>   Kept visible per Rule 1.7, because a correction pass asserting something it
>   had not checked is the failure this document class exists to prevent.) What
>   *is* corrected is the **stride**: 8 bytes per slot, see below.
> - **Everything else in the table survives**, and `+0xa`, `+0x12`, `+0x26` bit 0,
>   `+0x30` and `+0x88` are now confirmed instruction-by-instruction rather than
>   carried.
> - **The documented sgid ranges in the prose below the table are NOT re-examined
>   here** and remain as they were; nothing in this pass measured them.

Separately from the transient request-block above, each screen group (session) has a **persistent,
218-byte control block**, allocated once and kept in a doubly-linked list, indexed by a fixed
groupId-keyed pointer table (25 slots at boot, confirmed to grow dynamically past that once more
sessions are created). Known fields, by byte offset:

| Offset | Field |
|---|---|
| `+0x2`/`+0x4` | forward list-link (segment/offset) |
| `+0x6`/`+0x8` | backward list-link (segment/offset) |
| `+0xa` | packed id: `(type << 8) \| sgid` |
| `+0x10` | type byte (repeats `+0xa`'s high byte) |
| `+0x12` | bound child session's sgid (0 = none) |
| `+0x26` | flag byte; bit 0 = "has a bound child" / parent-eligible |
| `+0x30` | `sgid * 0x20` |
| `+0x4c`/`+0x4e` | a far pointer, written when the session's screen buffer is saved - plausibly the session's LVB (Logical Video Buffer) location, not fully confirmed |
| `+0x88` | the session's registered keyboard-focus handle |

#### The field table, read out of `DOSCALL1.DLL` `[OBS-RE]`

**Established 2026-09-04 against the Warp 4.5 / WSeB `DOSCALL1.DLL` (2002 file
set), in both its SMP and its uniprocessor build.** Every row cites the
instruction that reads or writes the offset; a row with no cited access is not
carried. Offsets are given as byte displacements from the start of the block.

**On build-independence, because an offset is otherwise a fact about one file.**
Every function below was disassembled in both the SMP and the uniprocessor
`DOSCALL1.DLL`, and the complete set of segment-override memory accesses is
byte-identical between them for `DOSSMADDSGCB` (39 accesses), `DOSSMDELSGCB`
(37), `DOSSMSETSESSIONTYPE` (4), `GETBOUNDSESSION` (3), `SESSIONRELATED` (3),
`VIOSAVREDRAWWAIT` (2) and `KBDSWITCHFGND` (1). `KBDSETFGND` differs in exactly
two instructions, and neither touches the block: a `test byte [es:di+0x32],0x8`
guard present only in the SMP build, on a different structure. So the offsets are
a property of the interface, not of one build; the *addresses* are not, and none
is given here.

| Offset | Width | Field | The instruction that establishes it |
|---|---|---|---|
| `+0x2`/`+0x4` | far ptr | forward list-link (offset, then selector) | `DOSSMADDSGCB`: `mov [es:di+0x2],di` / `mov [es:di+0x4],es` on an empty list; otherwise `mov eax,[fs:si+0x2]` / `mov [es:di+0x2],eax` copying the predecessor's link |
| `+0x6`/`+0x8` | far ptr | backward list-link (offset, then selector) | `DOSSMADDSGCB`: `mov [es:di+0x6],si` / `mov [es:di+0x8],fs` |
| `+0xa` | word | packed id, `(type << 8) \| sgid` | `DOSSMADDSGCB`: `mov [es:di+0xa],dx`, where `dl` is separately compared against the slot count and shifted left 3 to index the block table, and `dh` is stored as the type |
| `+0xb` | byte | session type - the high byte of `+0xa`, *and* an independently written copy | `DOSSMSETSESSIONTYPE`: `mov [es:di+0xb],bl`, in the instruction immediately after it writes the same value to `+0x10` |
| `+0xc` | word | the session's owning process id | `APPSTOPSESSION`, twice: `push byte +0x0` then `push word [fs:si+0xc]` into an external call - action `0` is ~~the single-process form of the kill-process call~~ **`DKP_PROCESSTREE`** (`bsedos.h:621`; corrected 2026-10-11, see "How a session is stopped") of the kill-process call, whose identity comes from resolving the import fixup and not from these bytes. `DOSSMADDSGCB` seeds it with `mov [es:di+0xc],cx` |
| `+0x10` | word | session type, second copy | `DOSSMSETSESSIONTYPE`: `cmp word [es:di+0x10],byte +0x4` / `cmp word [es:di+0x10],byte +0x7` then `mov [es:di+0x10],bx`. `DOSSMADDSGCB` writes only its low byte, `mov [es:di+0x10],dh` |
| `+0x12` | word | bound child session's sgid, `0` = none | `GETBOUNDSESSION`: `cmp word [fs:si+0x12],byte +0x0` -> `462`, else `mov bx,[fs:si+0x12]` |
| `+0x16` | word | first-child sgid | `DOSSMADDSGCB` writes the new session's id into the *parent's* `+0x16` when it is zero: `cmp word [fs:di+0x16],byte +0x0` / `mov [fs:di+0x16],dx` |
| `+0x18` | word | next-sibling sgid - **and the last sibling holds the *parent's* id**, which is what terminates the walk | `DOSSMADDSGCB` seeds the new block with `mov [es:di+0x18],bx` (the parent id), then walks `[fs:di+0x18]` from the parent's first child until it finds a node whose `+0x18` equals the parent id, and appends with `mov [fs:di+0x18],dx` |
| `+0x1a` | word | the packed id (`+0xa`) of the sibling this session was appended after | `DOSSMADDSGCB`: `mov ax,[fs:di+0xa]` / `mov [es:di+0x1a],ax` |
| `+0x14` | word | **switch flags.** Bit 0 gates the `DOSSGRESTORE` call OUT; bit 1 is the pop-up bit; bit 2 gates the `DOSSGSAVE` call OUT; bit 3 is the family/termination-notify bit. See the note below the table - what is established is which call each bit *suppresses*, not what a set bit *means* | `DOSSGSWITCHFOREGROUND`: `test word [fs:di+0x14],0x1` / `jnz` past the `call 0xe01e:0xb711` (`DOSSGRESTORE`), then `and word [fs:di+0x14],byte -0x2` at the end. `DOSSGSWITCHBACKGROUND` (obj3+`0x5474`, and it is a NAMED export - a linear disassembly loses its label because obj3+`0x5473` mis-decodes over it): `test word [es:di+0x14],0x4` / `jnz` past the `call 0xe01e:0x563a` (`DOSSGSAVE`), then `or word [es:si+0x14],byte +0x1` / `and word [es:si+0x14],byte -0x5`. `POPALL` sets bit 1, `DOSSGSWITCHPOPUP` tests it; `DOSSMCHILDEXIT_POSTDT` sets bit 2; `FOREGROUNDFAMILY` sets and clears bit 3, `WRITETERMQUEUE` tests it |
| `+0x1c` | word | the parent link - a family link compared against a requesting session's id | `SESSIONRELATED`: `cmp [gs:di+0x1c],bx`. Written by `DOSSMADDSGCB`: `mov [es:di+0x1c],bx`, from the same register as `+0x18`, so at creation the two are equal and they diverge only when a later sibling is appended |
| `+0x24` | word | zeroed at creation, meaning not established | `DOSSMADDSGCB`: `mov word [es:di+0x24],0x0` |
| `+0x26` | word | flags. Bit 0 = "has a bound child"; bit 1 set when the session was created with a related parent | `DOSSMADDSGCB`: `mov word [es:di+0x26],0x0`, then `mov word [es:di+0x26],0x2` when a parent was supplied, and `or word [fs:di+0x26],byte +0x1` on the parent. `GETBOUNDSESSION` and `SESSIONRELATED` both open with `test word [,+0x26],0x1` |
| `+0x2c` | word | a **second** family link, compared against a requesting session's id | `SESSIONRELATED`: `cmp [gs:di+0x2c],bx`, tried after `+0x1c` fails. Written by `DOSSMSGSTART`, not by the constructor |
| `+0x30` | word | `sgid * 0x20` - the session's slot offset in the session-name table | `DOSSMADDSGCB`: `xor dh,dh` / `imul dx,dx,byte +0x20` / `mov [es:di+0x30],dx` |
| `+0x34`...`+0x3d` | 5 words | **VIO alternate-subsystem function masks, one word per registration group.** `+0x34` = `flFun1` low, `+0x36` = `flFun1` high, `+0x38` = `flFun2` low, `+0x3a` = `flFun2` high (group 3, never selected by any function code), `+0x3c` = a fifth word derived by a bit-gather from `flFun1` | `VIOREGISTER` writes its own two `ULONG` mask ARGUMENTS here: `mov ax,[bp+0x10]` / `mov [gs:bx+0x34],ax`, `mov ax,[bp+0x12]` / `mov [gs:bx+0x36],ax`, `mov eax,[bp+0xc]` / `mov [gs:bx+0x38],eax`, and `mov [gs:bx+0x3c],cx` where `cx` is built from `[bp+0x10]`/`[bp+0x12]` by `shr ch,1` / `and al,0x7` / `and cl,0xe0` / `shr cx,2` / `or cl,al` / `ror ax,3` / `and ax,0xe000` / `or cx,ax`. `viorout` reads one WORD at `+0x34 + group_index` (`lea di,[bx+0x34]` / `add di,cx` / `mov dx,[gs:di]`) and ANDs it with the function's bit, `group_index` in {0,2,4,6,8} from the level-1 table at `BVSGLOBAL+0x1ca`. Teardown clears `+0x34` and `+0x38` as dwords |
| `+0x3e` | far ptr | the VIO registration record - a **188-byte** (`0xbc`) block, not the 299-byte one the keyboard and mouse use | `VIOREGISTER`: `lea ax,[bx+0x3e]` pushed with `0xbc` to the same `0xe01e:0x423a` allocator, then `les di,[gs:bx+0x3e]`; the module name is copied to `record+0x1c`, the entry name to `record+0x9d`. Freed through `0xe01e:0x4332` and the cell re-zeroed |
| `+0x44` | word | VIO registration count | `VIOREGISTER`: `inc word [gs:bx+0x44]` on success, `dec word [gs:bx+0x44]` on the failure unwind |
| `+0x4c` | word | process id of the thread registered for screen save/redraw | `VIOSAVREDRAWWAIT`: `mov [gs:bx+0x4c],ax` where `ax` came from the process-id cell of the caller's own instance segment. Cleared by `VIOSAVREDRAWUNDO` |
| `+0x4e` | word | thread id of that same thread | `VIOSAVREDRAWWAIT`: `mov ax,[es:0x6]` - `LINFOSEG`'s current-thread id - then `mov [gs:bx+0x4e],ax`. `viorout` tests ownership with four separate `cmp si,[gs:bx+0x4e]` / `cmp dx,[gs:bx+0x4c]` pairs |
| `+0x84`/`+0x86` | word/word | keyboard alternate-subsystem function mask, low and high halves | `KBDREGISTER`: `mov [es:bx+0x84],ax` / `mov [es:bx+0x86],dx`; `ROUTER` dispatches on `and ax,[es:bx+0x84]` / `and dx,[es:bx+0x86]` |
| `+0x88` | word | the session's registered keyboard-focus handle | `KBDSETFGND`: `mov [es:bx+0x88],ax`; `KBDSWITCHFGND`: `mov ax,[es:bx+0x88]`. **These are the only two accesses at this displacement anywhere in `DOSCALL1`'s two 16-bit code objects** |
| `+0x9c` | far ptr | the keyboard registration record | `KBDREGISTER`: `mov [es:bx+0x9c],ax` then `les bx,[es:bx+0x9c]` to dereference it; `DOSSMDELSGCB` **frees it** - `cmp dword [gs:di+0x9c],byte +0x0` / `jz` past, else `push dword [gs:di+0x9c]` / `call 0xe01e:0x4332` |
| `+0xa0`/`+0xa2` | word/word | mouse alternate-subsystem function mask, low and high halves | `MOUREGISTER`: `mov [es:bx+0xa0],ax` / `mov [es:bx+0xa2],dx` |
| `+0xb2` | far ptr | the mouse registration record | `MOUREGISTER`: `les bx,[es:bx+0xb2]`; `DOSSMDELSGCB` frees it identically to `+0x9c` |
| `+0xc6` | far ptr | a **26-byte** (`0x1a`) record allocated **only for a windowable-VIO process** | `SGCBINIT` (obj4): `mov es,[0x8a]` / `cmp word [es:0x124],byte +0x2` - `procTYPE == PT_WINDOWABLEVIO` - then `mov ax,bx` / `mov dx,[es:0x154]` / `add ax,0xc6` / `push dx` / `push ax` / `push byte +0x1a` / `call 0xe01e:0x423a`. The same routine frees it (`push word [es:bx+0xc8]` / `push word [es:bx+0xc6]` / `call 0xe01e:0x4332`) and zeroes both halves, and `DOSSMDELSGCB` frees it as a dword alongside the other three. Its first two fields are set immediately after allocation: `record+0x6 = 4`, `record+0x10 = 0xa`. **What it holds is not established** |

> **`+0x14` ADDED 2026-09-05. The attribution holds; the METHOD NOTE THAT
> FIRST ACCOMPANIED IT DID NOT REPRODUCE and is replaced here rather than
> deleted, because how it failed is the reusable part.** Its numbers were
> wrong - it said *"fifteen groups ... split in two with no overlap"* and then
> listed 7 + 12 = 19, calling the second list "eight" - and its stated
> discriminator was false on its own evidence. Same shape as every previous
> per-pass count published for this corpus.
>
> **What the grouping actually is.** Disassemble both 16-bit code objects
> whole, then group every `[seg:reg+0x14]` access by *(function, seg:reg)*
> **together with every other displacement used on that same register in that
> same function**. Re-derived 2026-09-05: **33 groups - 27 in object 3 and 6 in
> object 4** - and **at least four different structures**, not two:
>
> - **the SGCB** - `DOSSGSWITCHFOREGROUND` `fs:di` {`10 14`}, `DOSSGSWITCHPOPUP`
>   `es:di` {`c 14`}, `DOSSMCHILDEXIT` `es:di` {`c 10 14 16 26`},
>   `DOSSMCHILDEXIT_POSTDT` `fs:si` {`6 8 a 14 16 18 1a 26`}, `DOSSMSGSWITCH`
>   `es:si` {`2 a 14`}, `FOREGROUNDFAMILY` `fs:si`
>   {`a 14 16 1c 1e 20 22 2c 2e`}, `PARENTNOTIFY` `fs:si`
>   {`a 12 14 16 1e 20 22`} and `gs:di` {`14 18 1e 20 26`}, `POPALL` `es:di`
>   {`2 4 6 8 a c 10 14 18 1a 1c 24 26 2c 2e 30`} and `gs:si`
>   {`8 a c e 14 26`}, `WRITETERMQUEUE` `fs:si` {`14 1e 20`};
> - **the queue package** - `_Q_Delete`, `_Q_Scan`, `_Q_Tbl`, `_ScanQname`,
>   `_L_Remove`, `W_DOSREADQUEUE` / `W_DOSWRITEQUEUE` / `W_DOSPEEKQUEUE`,
>   `_FuncInit`, `C_EXITLISTQUEUE2`, `CharIComp`, `TRY_DISK`, on `es:bx` and
>   `ss:si`;
> - **a VIO registration record** - `VIODEREGISTER`, `VIOREGEXIT` and `viorout`
>   in object 4, all on `es:di`, all carrying `12` and `1a`, and two of them
>   writing `0xffff` there;
> - **`BvsMVDMTranPop`** `ss:si` {`4 8 c 10 14 20 24 2c`} and
>   **`AVS_PRTSCTOGGLE`** `es:di` / `gs:bx`, whose bases are not established.
>
> **The `+0x16` discriminator the first note offered is FALSE.** It claimed the
> queue package is distinguishable because its groups carry a `+0x16`
> *"no SGCB path uses"*. Several SGCB-side groups carry `16` -
> `DOSSMCHILDEXIT`, `DOSSMCHILDEXIT_POSTDT`, `FOREGROUNDFAMILY`,
> `PARENTNOTIFY` - and the field table two screens above has a **`+0x16` row of
> its own** (first-child sgid). There is no single displacement that separates
> the families; what separates them is the *whole set* on one register, and
> even that is evidence rather than proof.
>
> **THE GROUPING INHERITS THE SYMBOL TABLE'S BOUNDARIES, AND A LINEAR PASS'S
> RESYNC ERRORS WITH THEM. That is the caveat the first note omitted, and it is
> the one that matters.** A linear disassembly attributes code to the nearest
> preceding `.SYM` label, so a mis-decoded byte that swallows a label silently
> merges two functions. Worked instance, in this very set: the group listed as
> `DOSSGSWITCHFOREGROUND` `es:si` {`a 10 14`} is not in that function at all -
> that function ends at `1C035472 ret`, and `1C035473` mis-decodes as a 4-byte
> instruction that covers `1C035474`, where **`DOSSGSWITCHBACKGROUND`** begins.
> The `es:si` accesses belong to it. `POPALL` likewise absorbs code from
> `DOSSMSGSTART` and the `DOSSMCHILDEXIT` region. **Anchor by symbol
> (`--sym-name`) before believing a label a linear pass printed.**
>
> **What survives, and it is symbol-anchored rather than linear.** Inside
> `DOSSGSWITCHFOREGROUND` proper, on **one base register**, `fs:di`:
> `cmp word [fs:di+0x10],byte +0x4` at `1C035319` and
> `cmp word [fs:di+0x10],byte +0x7` at `1C035320` - which is
> `DOSSMSETSESSIONTYPE`'s own test of the session type, verbatim - and
> `test word [fs:di+0x14],0x1` at `1C03540B` gating the `DOSSGRESTORE` call.
> That is the same register the field-table row cites, so the two halves of
> this document agree. `POPALL`'s and `DOSSMCHILDEXIT_POSTDT`'s groups
> corroborate it with nine and eight independently established SGCB offsets
> each.
>
> **All four bits are only ever `test`/`or`/`and`ed, never compared**, so the
> field is a flags word rather than a state. And the naming discipline the
> `+0x24` row states applies here in full: what is established is which call
> each bit switches OFF. "Bit 0 = needs restore" is the reading a name invites
> and it is **backwards** - a set bit 0 makes the restore be *skipped*, and the
> mechanism is coherent: `DOSSGSWITCHBACKGROUND` sets bit 0 on the path where
> it *skipped* the save, and `DOSSGSWITCHFOREGROUND` then skips the restore.
> Nothing was saved, so there is nothing to put back.
>
> **`+0x22` is placed on the SGCB by the same grouping** (`FOREGROUNDFAMILY`
> and `PARENTNOTIFY` reach it on an `fs:si` that also carries `+0xa`, `+0x16`,
> `+0x1c` and `+0x2c`) and is deliberately **not** given a row: knowing which
> structure a field belongs to and knowing what it holds are different claims,
> and only the first is established. **Fourteen of the 33 groups are not
> attributed to any structure here**, and that is stated rather than left to be
> counted.
>
> `[OBS-RE]`, the shipped Warp 4.5 / WSeB `DOSCALL1.DLL` read with its
> **uniprocessor** `.SYM`; counts re-derived 2026-09-05 by re-running the
> grouping, not carried from the pass that first published them.

> **CORRECTED 2026-09-05 - the `+0x34`...`+0x44` row above said *"the internal
> split of the region is not established"*, and an earlier RE write-up says the words there are per-group ENTRY POINTS.
> Both are wrong, and the second is the one worth marking, because an
> implementation built on it would store an address where OS/2 stores a mask.**
> `VIOREGISTER` writes the caller's own two published `ULONG` masks into
> `+0x34`...`+0x3b` verbatim - they are its arguments, read straight out of the
> `[bp+...]` slots four instructions earlier - plus a fifth derived word at
> `+0x3c`; and `viorout` ANDs the word it finds at `+0x34 + group_index` with
> the function's own bit, which is a mask test and not a call. The resolved
> entry point does not go into the SGCB at all: `VIOREGISTER` passes two
> per-process `BVHINSTANCE` (object 8) cells as out-parameters - `+0xe4` to
> `DosLoadModule`, which fills it with the WORD module handle, and `+0xe6` to
> `DosGetProcAddr`, which fills that and `+0xe8` with the far pointer to the
> entry point. So the ENTRY POINT is `+0xe6`; `+0xe4` is the handle, and an
> earlier revision of this sentence named the pair as though both held the
> address. Same shape as the keyboard's and mouse's, whose `DosGetProcAddr`
> out-parameters are `+0x54e` and `+0x552`.
> **CORRECTED 2026-09-05 - the `+0x9c` and `+0xb2` rows said `DOSSMDELSGCB`
> *"refuses to free a block whose `cmp dword [gs:di+0x9c]` is non-zero"*. It does
> the OPPOSITE: it FREES the record, and the `cmp` is a null-check that skips
> the free when there is nothing to free.** Read in full at obj3+0x8f90, the
> tail is four identical three-instruction groups -
> `cmp dword [gs:di+N],byte +0x0` / `jz` past / `push dword [gs:di+N]` /
> `call 0xe01e:0x4332` - for **`+0x3e`, `+0x9c`, `+0xb2` and `+0xc6`**, and then
> `push dword [fs:si]` / the same call to free the block itself,
> **unconditionally**. `DOSSMDELSGCB` has exactly ONE refusal and it is at its
> head, before any of this: `cmp [es:di+0xa],dx` / `jnz` -> `mov ax,0x171`, i.e.
> **369 on a session-id mismatch**, which has nothing to do with registrations.
>
> **The conclusion the wrong sentence was carrying - that a registration record
> cannot outlive its session - is nevertheless RIGHT**, which is what made the
> error survive: it is a true conclusion resting on a false premise, and IBM
> reaches it by freeing rather than by refusing. The distinction is not
> academic for anyone implementing the VIO half: a reader who believes
> "refuses" builds a refusal into session teardown that IBM does not have, and
> `+0x3e` is freed by exactly the same three instructions as `+0x9c`.
>
> `[OBS-RE]`, the shipped Warp 4.5 / WSeB `DOSCALL1.DLL` read with its
> **uniprocessor** `DOSCALL1.SYM`; the pairing was checked against the image's
> own LX entry table first (32 of 32 named exports agree), because the SMP
> `.SYM` of the same release resolves cleanly to WRONG addresses against a
> uniprocessor image and reports nothing.

### The keyboard and mouse registration record, 299 bytes

`[OBS-RE]`, read out of `KBDREGISTER` (obj4+0x2890) and `MOUREGISTER`
(obj4+0x2ca4), which are the same routine at two displacements. Both push the
literal `0x12b` = **299** to the session-manager block allocator
(`call 0xe01e:0x423a`) with a far pointer to their own `SGCB+0x9c` / `SGCB+0xb2`
cell as the output slot - so the far pointer the SGCB carries is the
allocator's, and 299 is the whole record.

| offset | size | meaning | evidence |
|---|---|---|---|
| `+0x00` | word | no write observed, in either register or either deregister routine | - |
| `+0x02` | word | the **registering process id** | `mov es,[0x52]` / `mov cx,[es:0x126]` - `_CurrentPID`, IBM's own symbol for that instance cell - then `les bx,[es:di]` / `mov [es:bx+0x2],cx` |
| `+0x04` | word | the **module handle**, filled by `DosLoadModule` writing through this cell | `KBDREGISTER` pushes `record + 4` as the 16-bit `DosLoadModule`'s `phmod` out-parameter (14 bytes of arguments), re-reads it as `DosGetProcAddr`'s first argument, and `KBDDEREGISTER` pushes it to `DosFreeModule` |
| `+0x06`...`+0x26` | 33 bytes | the **entry-point name**, ASCIIZ | `lea si,[bx+0x6]`, then a `repne scasb` + `rep movsw` copy of the caller's `pszEntryPt`. `_CheckRegisterParms` caps the name at 32, so 32 + NUL fits exactly |
| `+0x27`...`+0x12a` | 260 bytes | the **module name**, ASCIIZ | `add ax,0x27`, then the same copy idiom for `pszModName`. The field is `CCHMAXPATH` while the validator caps the name at 128 |

**The order of writes is `DOSSMGETMEM` -> `DosLoadModule` -> `DosGetProcAddr` ->
the SGCB masks -> the record's pid -> the entry name -> the module name.** The
masks are fourth of seven, and what is load-bearing is narrower than "last":
they are the LAST OF THE SGCB FIELDS, written only after the record pointer at
`+0x9c`/`+0xb2` is already in place. That ordering is what makes the mask a
sound "a registration exists" flag for every later reader - `ROUTER`'s dispatch
test, and `KBDREGISTER`'s own already-registered test - because no reader can
see a set mask whose record pointer is not yet published. The record's own
three fields are written afterwards, and a reader that followed the pointer in
that window would find a record whose pid and names are not yet filled in.

**`KBDREGISTER`'s guards, in the order it applies them:** `_CurrentSGID == 3` ->
410; `procTYPE == 2` (`PT_WINDOWABLEVIO`) -> 410; either mask word non-zero -> 410
`ERROR_KBD_REGISTER`; `_KbdCheckProcType()` non-zero -> that value;
`_KbdGetSemaphore(0xffff,0xffff)` non-zero -> 447 `ERROR_KBD_KEYBOARD_BUSY`; then
`_CheckRegisterParms` -> rc 2 = 408 `ERROR_KBD_INVALID_ASCIIZ`, any other
non-zero = 409 `ERROR_KBD_INVALID_MASK`; then the allocator's, the loader's and
`DosGetProcAddr`'s own rc, propagated verbatim. `MOUREGISTER` is identical with
415 / 413 / 414 and its own semaphore. `VIOREGISTER` guards differently and more
strictly: `_CurrentSGID == 3` -> 430, `procTYPE == 4` -> 465
`ERROR_VIO_DETACHED`, `procTYPE > 0` -> 494, i.e. **only a full-screen process
may register a VIO alternate subsystem.**

**`_CheckRegisterParms` (obj4+0x358c), the whole parameter contract:**
`strlen(pszModName)` must be 1...128 (`cmp di,0x80` / `ja`), `strlen(pszEntryPt)`
must be 1...32 (`cmp di,0x20` / `ja`) - either failure is rc 2 - and the 32-bit
mask must be non-zero and at most **`0x003FFFFF`**: `cmp word [bp+0xe],0x3f`
with `jc` accepting, `ja` rejecting, and the equal case accepting any low word
(`cmp word [bp+0xc],0xffff` / `jna`). So only bits 0...21 are accepted. The
routine is referenced by `KBDREGISTER` and `MOUREGISTER` only; `VIOREGISTER`
validates its own two masks separately, and has to, because its registration
space is per-group words rather than one flat 32-bit mask.

**`KBDDEREGISTER`'s entitlement rule is wider than "the registrant".** It tests
the record pointer, not the masks (`mov ax,[es:bx+0x9e]` / `or ax,[es:bx+0x9c]`
/ `jz` -> 411), then accepts the caller if **either** `record+0x02` **or**
`SGCB+0x0c` - the session's owner pid - equals `_CurrentPID`. So the session
owner may deregister a registration another process made, which is why the
record must be reachable from a process other than the registrant. It then calls
`DosFreeModule(record+0x04)`, frees the record through `0xe01e:0x4332`, and
zeroes, in this order, `+0x86`, `+0x84`, `+0x9e`, `+0x9c`, plus the two instance
cells holding the resolved entry point.

### `ROUTER`'s dispatch test, and the 16-bit shift inside it

`ROUTER` (obj4+0x2326) is the shared keyboard/mouse dispatcher; bit `0x100` of
the pushed function code selects the family. Its whole decision is:

```
mov ax,0x1
mov cl,[bp+0x16]        ; the function code, low byte
shl ax,cl               ; SIXTEEN-BIT shift
cwd                     ; DX = 0xFFFF iff AX bit 15 is set, else 0
and ax,[es:bx+0x84]     ; SGCB kbd_mask_lo   (+0xa0 for the mouse)
and dx,[es:bx+0x86]     ; SGCB kbd_mask_hi   (+0xa2)
or  dx,ax
jnz -> the alternate subsystem
```

A `shl` on a 16-bit register against a 32-bit published mask has three
consequences, and the third is a defect a reimplementation must reproduce
rather than correct:

| function code | effect |
|---|---|
| 0...14 | tests exactly bit *code* of the low mask - the clean 1:1 case |
| 15 | tests bit 15 of the low mask **or any bit at all of the high mask** |
| 16...31 | `AX` and `DX` are both 0, so the alternate subsystem is **unreachable** - even though `_CheckRegisterParms` accepts bits up to 21 |

The alternate subsystem returns `-1` to mean *"not handled, pass it on"*, and
the fall-back to the base subsystem is unconditional on `-1`, which is what
makes a partial registration work.

**Function codes, re-derived from the shipped export stubs** - each is
`push <code>` / `call ROUTER` / `retf n`, so the code is read out of the image
rather than taken from a write-up. Mouse 0...18: `MOUGETNUMBUTTONS`,
`MOUGETNUMMICKEYS`, `MOUGETDEVSTATUS`, `MOUGETNUMQUEEL`, `MOUREADEVENTQUE`,
`MOUGETSCALEFACT`, `MOUGETEVENTMASK`, `MOUSETSCALEFACT`, `MOUSETEVENTMASK`,
`MOUGETTHRESHOLD`, `MOUSETTHRESHOLD`, `MOUOPEN`, `MOUCLOSE`, `MOUGETPTRSHAPE`,
`MOUSETPTRSHAPE`, `MOUDRAWPTR`, `MOUREMOVEPTR`, `MOUGETPTRPOS`, `MOUSETPTRPOS`;
then 20 `MOUFLUSHQUE` and 21 `MOUSETDEVSTATUS`. Keyboard: 1 `KBDPEEK`,
2 `KBDFLUSHBUFFER`, 3 `KBDGETSTATUS`, 4 `KBDSETSTATUS`, 6 `KBDOPEN`,
7 `KBDCLOSE`, 10 `KBDGETCP`, 11 `KBDSETCP`, 12 `KBDXLATE`, 13 `KBDSETCUSTXT`,
16 `KBDGETHWID`. Codes 0, 5, 8 and 9 have no stub of that shape -
`KBDCHARIN`, `KBDSTRINGIN`, `KBDGETFOCUS` and `KBDFREEFOCUS` have real bodies
that reach `ROUTER` internally - so their codes are not recoverable this way;
the published `KR_*` bits give them as 0, 5, 8 and 9.

**Two documentation-versus-binary conflicts fall out, and both are unobservable
through `ROUTER` because of the shift above.** `bsesub.h` `[DOC-IBM]` defines
`MR_MOUINITREAL` as bit 19 and `MR_MOUSETDEVSTATUS` as bit 20, while the shipped
stubs give `MOUFLUSHQUE` code 20 and `MOUSETDEVSTATUS` code 21, and
`MOUINITREAL` has no `ROUTER` stub at all. Conversely `bsesub.h` leaves bits 9
and 10 undefined while the binary assigns them to `MOUGETTHRESHOLD` and
`MOUSETTHRESHOLD`, which **are** dispatchable. So the documented bit list is
neither complete nor correct at its top end, and the two errors sit on opposite
sides of the reachability boundary.

**The size is 218 bytes (`0xda`), re-derived rather than carried.** Three
allocation sites push that literal to the block allocator: one in
`DOSSMADDSGCB`, two in `DOSSMINITSGCB`. The highest displacement observed
anywhere is `+0xb2`, which falls inside it.

**The registry's stride is 8, not 24, and the slot index *is* the sgid.**
`DOSSMINITSGCB` allocates a 200-byte pointer table and sets the slot-count byte
to `0x19` = 25 - 25 x 8 = 200 - and both `DOSSMGETSGCB` and `DOSSMADDSGCB` index
it with `shl ,,byte 0x3`. A parallel 50-byte table (25 x 2) holds one process id
per slot, and `DOSSMGETSGCB` scans *that* one instead when its flags argument's
low byte is 1, i.e. **the block can be looked up by process id as well as by
session id**. `DOSSMINITSGCB`'s two boot blocks land at table `+0x02` and
`+0x1a`, three slots apart, and are seeded `+0xa` = `0x103` and `0x100` - session
3 and session 0, both of type 1 - so slot index equals sgid by construction, and
`0x18` is a three-slot step rather than a stride.

**And there are two registries, not one - that is not reconciled here.** The
lookup routine bounds itself with a slot-count byte in the shared *character*
segment and indexes the table hung off it; the constructor grows a *separate*
count in the shared session segment, doing `cmp bl,[fs:si]` against the new
sgid, `add byte [fs:si],0x8`, `shl cx,3` and a reallocation - so the table
grows eight slots at a time - and reallocates the parallel per-slot process-id
table alongside it with `shr cx,2`, which is `slots * 2` bytes and confirms that
table's 2-byte stride independently. Both use stride 8 and stride 2
respectively; whether they are two views of one allocation or two allocations is
**not** established.

> **SETTLED 2026-10-12 `[OBS-RE]`: there is ONE registry; the paragraph above is kept (Rule 1.7).**
> The constructor's slot count, table pointer, process-id table pointer, initialised flag and lock
> are reached through five far pointers in the session segment, and those pointers' selector halves
> carry relocations to the very data object the lookup routine loads directly, at the offsets it
> uses. So the constructor, the destructor and the lookup touch the same cells. In full:
>
> - **Initialisation** (`DOSSMINITSGCB`, run by the first constructor or lookup that finds the
>   initialised flag clear): the 200-byte table (25 slots), the slot count 25, the 50-byte
>   process-id table, and **two blocks created directly in slots 0 and 3** (packed ids `0x100` and
>   `0x103`, type 1). Those two are **not** linked into the session list and not counted as
>   allocated ids; the constructor never builds them.
> - **Growth**: when a new session id is at or above the slot count - first at **id 25** - the
>   constructor adds 8 slots and grows both tables: a new zero-filled block, the old contents
>   copied, the pointer swapped, the old block freed. A failed grow returns its error from the
>   constructor.
> - **Each process's view**: a grown table can move to another selector, so the lookup compares
>   the table's current selector with a per-process cached one and, when they differ, calls
>   `DosGetSeg` on it before indexing.

**`+0x4c`/`+0x4e` is corrected, not refined.** The superseded table called it *"a
far pointer ... plausibly the session's LVB (Logical Video Buffer) location"*. It
is not a pointer and holds no buffer address: it is the **process id and thread
id of the thread that called `VioSavRedrawWait`**, written from the caller's own
current-process and current-thread cells and compared back as a pair by
`viorout` on every routed call. It reads as one dword in exactly one place - a
zero test in `VIOSRFUNBLOCK` - which is what made the far-pointer reading look
natural. The paragraph below this table drew an inference from the old reading
("so the screen buffer itself is set up lazily..."); that inference has no support
from this field, whatever its merits from elsewhere.

**`+0x88` has one writer and it is not the session-creation path.** A census of
every segment-override access at `+0x88` across both 16-bit code objects returns
two instructions: the write in `KBDSETFGND` and the read in `KBDSWITCHFGND`.
The block constructor does not touch it, and neither does any `*Register`
routine. Both reach the block through a **global** far pointer held in
`DOSCALL1`'s per-process instance segment - not through the by-sgid lookup - so
the field is written into whichever block that global currently designates.

**What `DosSMGetSGCB` requires of its caller: nothing.** The routine ends
`retf 0x8` - four words of arguments - and its whole body never references the
shared segment that holds the registered shell's process id. It checks an
initialised flag, optionally takes the session lock (suppressed when the caller
passes bit `0x8000`, meaning it already holds it), indexes, and returns `371` if
the slot is empty. So it is not restricted to the registered shell.

Most of the remaining ~150 bytes are unmapped (owned by other subsystems - video state, semaphore
handles - each would need that subsystem's own init code traced to identify). SGID numbering is a
single byte, with documented ranges: `0` = Hard Error Popups, `1` = Shell, `2` = Real Mode, `3` =
VioPopUp, `4`-`15` = FullScreen sessions, `16`-`31` = Windowable VIO sessions, `32`-`255` = PM
sessions. Two groups (`0` and `3`) are bootstrapped lazily on first access rather than created
through the normal session-creation path; every other SGCB is created on demand when a session
starts.

**Session creation does not set up screen/VIO buffer space - that is deferred.** The SGCB
constructor writes only bookkeeping at creation time: the id/type fields above, the related/bound-
parent linkage (populated directly from the caller's own "related" request, when given), the
`sgid`-derived offset, and - a session-manager-UI detail, not previously documented here - a
short (up to 30 bytes) null-terminated name string copied into a separate table. *(Resolved
2026-08-15, superseding the original "almost certainly the Window List display name" guess: that
table is the session's title store **only on a system without PM**. When PM is present the table
is allocated as a 10-byte-per-slot stub and never string-copied; the live title store is the PM
switch-list entry. Full mechanism in "The switch list (Window List) and session titles" below.)* **It never writes `+0x4c`/`+0x4e`** (the likely LVB
pointer above) - that field is only ever populated later, during a foreground switch, by the
screen-save mechanism described next. So the screen buffer itself is set up lazily: either on the
session's first foreground activation, or by the session's own process once it starts running and
first calls into VIO - not by the session-creation call itself.

### How a session is stopped: `APPSTOPSESSION` `[OBS-RE]`

`DosStopSession`'s public entry validates and queues a request block (above); the
work happens in the serve loop, at **`APPSTOPSESSION`** (`DOSCALL1.DLL`
obj3+0xa232). It reads three fields from the request block -
`+0x24` scope, `+0x08` the **caller's own** session, `+0x22` the target - and
branches on scope:

- **`STOP_SESSION_ALL` (scope 1)** starts from the **caller's own** session, not
  from the session named in the call, and walks the family from there: it takes
  the SGCB's first-child link (`+0x16`), or follows `+0x2` to a sibling and reads
  that node's `+0xa`, depending on bit 1 of `SGCB+0x22`. So the reach of a
  scope-1 stop is structurally limited to the caller's own descendants. The
  `idSession` argument is never read on this path - consistent with the
  documented meaning, "all sessions started by this process".
- **`STOP_SESSION_SPECIFIED` (scope 0)** looks up the named target directly and
  stops it.

The scope-1 walk, read whole `[OBS-RE]`: with `SGCB+0x22` bit 1 clear it takes the
first child (`+0x16`) and then each next sibling (`+0x18`); the last sibling's
`+0x18` holds the parent's own id, and **the walk stops when it arrives back at
the caller's session** - so it reaches the caller's **immediate** children only
(a grandchild ends through its own parent's exit list, below). With bit 1 set it
walks the whole session list (`+0x02`) and stops only sessions whose `+0x2c` (the
debugger link) names the caller. **A failed kill or lookup ends the walk, and that
code is `DosStopSession`'s answer.** `APPSTOPSESSION` only kills: each session ends
as its processes do, through the child-wait thread.

The client side `[OBS-RE]` (`DOSSTOPSESSION`, obj3+0x97d6): the reserved `ULONG`
not 0 and not `0xCDEF1234` -> 459; scope above 1 -> 458; scope 0 naming session 0
or the caller's own screen group (by its low byte) -> 369; scope 1 never reads the
id. The process that made a related start carries an exit-list routine
(`PARENTEXITLIST`, obj3+0xaae6) that, when the caller's own `SGCB+0x1e` still names
it, sets `SGCB+0x22` bit 0 and calls `DosStopSession(1, own screen group, 0)`,
clearing `+0x1e` when that fails: **a parent's exit stops its related children**.
The base shell is its own server, so its own exit list's request would be queued
to a serve thread that has already ended - not established on a real system.

Both paths stop a session the same way: **`DosKillProcess(0, SGCB+0x0c)`**
(`DOSCALLS.#10`, called from obj3+0xa29e and obj3+0xa2dd). ~~Action 0 is the
single-process form, so **one** process is killed per session - the one whose pid
the SGCB carries at `+0x0c`.~~ **Corrected 2026-10-11:** action 0 is
`DKP_PROCESSTREE` (`[DOC-IBM]` Toolkit `bsedos.h:621`, `#define DKP_PROCESSTREE 0`;
`DKP_PROCESS` is 1), so the **whole process tree** of the process whose pid the
SGCB carries at `+0x0c` is killed `[OBS-RE + DOC-IBM]`. (IBM's DosStopSession page
separately says a stopped child's own related sessions "will also be ended"; that is
the session-level rule, and this is the process-level one.) That also fixes the meaning of that field: it is the
session's owning process id, established here by its use as `DosKillProcess`'s
pid argument rather than inferred from the call that fills it.

### The shell IS the session manager: `PROTSHELL` registers, and only it is served `[OBS-RE]`

The session manager is not a kernel service that runs itself. `DOSCALL1` supplies
primitives and shared state; **the protected-mode shell named by `PROTSHELL=`
sets the subsystem up and then serves it**, and on a normal system that shell is
`PMSHELL.EXE` (through `PMMERGE`'s `WIN16INITSESSIONMGR`).

Its state lives in DOSCALL1's **object 5**, the shared data segment, and IBM's
own symbols name every field involved:

| obj5 offset | symbol | role |
|---|---|---|
| `+0x454` | `ShellPID` | the registered shell's process id |
| `+0x0a51` | `PM_Present` | set when the registering shell declares itself PM |
| `+0x0b70` | `SMG_Flags` | bit 0 = the session manager is present at all |
| `+0x0b72` | `DOSSMSYSINIT` | the system-init semaphore (DOSCALLS ordinal 855) |

**Registration.** `DosSMInitialize` writes `ShellPID`, sets `PM_Present` for a PM
shell, and marks `SMG_Flags`. `WIN16INITSESSIONMGR` clears the `DOSSMSYSINIT`
semaphore via `DosSemClear` once init completes - which is what that otherwise
odd-looking far-pointer-to-a-data-export at ordinal 855 is for.

**Request side.** An application's `DosStartSession`/`SelectSession`/
`SetSession`/`StopSession` does **not** perform the operation. It allocates a
request block through `REQUESTBLOCKALOC` - gated on `SMG_Flags` bit 0 and on the
CALLER's own `LIS_CurScrnGrp` and `LIS_ProcType`, answering **418
`ERROR_SMG_INVALID_CALL`** when the caller is not entitled - and `APPSENDREQUEST`
queues it on `\QUEUES\SESMGR\APPREQQ`.

**Serve side, and this is the part that makes the shell load-bearing.** The
dispatcher `DOSSMDOAPPREQ` opens by refusing to run for anyone but the
registered shell:

```
1C03323C  mov es,[0x432]     ; LocalSelector -> the CALLER's local infoseg
1C033240  mov ax,[0x454]     ; ShellPID
1C033243  cmp [es:0x0],ax    ; LIS_CurProcID == ShellPID ?
1C033248  jnz  -> bail
```

`InfoSegLDT+0x0` is `LIS_CurProcID`, so only the process whose pid is in
`ShellPID` proceeds to the ownership check and the `APP*SESSION` handlers.

> **CAVEAT - the shell performs the BOOKKEEPING, but not always the SPAWN (Rule
> 1.7, 2026-08-23) `[OBS-RE]`.** The "the request side does not perform the
> operation; the serve side does" split above is complete for `DosSelectSession`,
> `DosSetSession` and `DosStopSession` - bookkeeping-only operations that create
> no process. It is INCOMPLETE for `DosStartSession`, whose process SPAWN is
> routed by `STARTDATA.InheritOpt`, not unconditionally carried out by the shell:
>
> - For `SSF_INHERTOPT_PARENT` (1), the CALLER creates the process itself,
>   inline, after the request returns. `APPSENDREQUEST` (`DOSCALL1` obj3)
>   far-calls `DosExecPgm` at `1C033E89`, reached only when the request block's
>   inherit-option **word** gates it in at `1C033E31`
>   (`cmp word [es:di+0x4a],byte +0x1` - a word compare against a sign-extended
>   byte immediate; an earlier revision of this bullet said "byte", corrected
>   2026-08-23, Rule 1.7). This half is byte-confirmed on the caller side.
>   `[OBS-RE]`
> - For `SSF_INHERTOPT_SHELL` (0), the spawn happens on the serve side, inside
>   the shell's `DOSSMSGSTART` (obj3+0x2a78), which execs at `0x2DE0` on its
>   `!= 1` branch. `[OBS-RE]`
>
> **PROVENANCE UPGRADED 2026-08-23 (Rule 1.7). The second bullet used to read:
> "That this handler's argument (`param_8`) is `InheritOpt` is `[INF]`, not
> `[OBS-RE]` - Ghidra's 16-bit parameter recovery is unreliable, so the
> caller-side gate is confirmed while the shell-side mapping is strong inference
> only." That hedge was too weak, and the reason it was too weak is the reusable
> part: the identification never depended on Ghidra's parameter recovery at
> all.** `param_8` is only Ghidra's *name* for the frame slot `[bp+0x16]`. The
> chain to `InheritOpt` is three ordinary instructions plus arithmetic, and
> every link is byte-exact:
>
> 1. `DOSSTARTSESSION` obj3+0x3576 copies the field out of the caller's
>    `STARTDATA` into the request record - `mov ax,[si+0x1c]` /
>    `mov [es:di+0x4a],ax` - under a `cmp word [si],byte +0x1e` /
>    `jc` length gate at +0x356F. `STARTDATA + 0x1c` **is** `InheritOpt`
>    `[DOC-IBM]`, from the version-correct Warp-4.5 toolkit header
>    Toolkit 4.5 `H/bsedos.h`; and `0x1e` is exactly
>    `0x1c + 2`, i.e. the `Length` at which that field first exists -
>    independent corroboration from the gate itself. Its neighbours in the same
>    copy block agree too: `[si+0x18]` (`Environment`) -> record `+0x46`, the
>    slot `APPSENDREQUEST` pushes as `pEnv`; `[si+0x1e]` (`SessionType`) ->
>    record `+0x28`, the slot it tests against 4/7.
> 2. `APPSTARTSESSION` obj3+0x3BFA pushes that record field
>    (`push word [es:di+0x4a]`) into the `DOSSMSGSTART` call at +0x3C0D. The
>    16 bytes pushed after it - `es`, `di`, a dword, `cx`, `dx`, a dword - plus
>    4 (far return) + 2 (`enter 0x20,0`'s saved BP) place that push at exactly
>    `[bp+0x16]`, and the `push es` / `push di`
>    pair two slots later at `[bp+0x12]` - which is precisely where
>    `DOSSMSGSTART` does `lds si,[bp+0x12]` at +0x2BA0 to reach the record.
>    Self-consistent with no slack.
> 3. So `0x2B9A cmp word [bp+0x16],byte +0x1` is literally
>    `record+0x4a == SSF_INHERTOPT_PARENT`.
>
> **Nothing in that mapping remains `[INF]`** - a `mov` from a `[DOC-IBM]`
> structure offset, a `push` of the same record field, and a `cmp` against a
> frame slot whose offset is derived arithmetically from the push sequence. The
> one documentary link is the `STARTDATA` offset; the rest is bytes. The two
> functions are complementary halves keyed on one field - `APPSENDREQUEST`
> execs when it is 1, `DOSSMSGSTART` execs when it is not, and in the `== 1`
> case `DOSSMSGSTART` instead fills in the `pName`/`pArg` far pointers
> (`+0x4c`/`+0x4e`, `+0x50`/`+0x52`) that `APPSENDREQUEST` will push. Exactly
> one exec happens either way. `[OBS-RE]`
>
> **The caution the old hedge was reaching for is still real, just misapplied
> here:** Ghidra's argument *lists* for these 16-bit functions genuinely are
> untrustworthy (a five-argument call has been observed rendered as six, in
> scrambled order). The
> remedy is to read the pushes, which is what the chain above does - not to
> discount a conclusion that never used the argument list.
>
> **No correction is owed for `DosSelectSession`, `DosSetSession` or
> `DosStopSession`** - they carry no spawn, so "the shell drains it and performs
> it" describes them in full. Do not over-correct them.

**Registration is UNPRIVILEGED and self-conferring, and `obj5+0x432` is not an
authority token** `[OBS-RE + OBS]`. This is worth stating flatly because
the natural reading of the gate is the opposite one, and an earlier RE write-up reached
the opposite reading:

- **`DOSSMINITIALIZE` (obj3+0x9ef0) has no authorization check whatsoever.** Its
  prologue goes straight to `cmp word [es:di],0x10` on the caller's own block,
  and it later stores `ShellPID` from the caller's LIS. There is no
  `DOSSMBASESHELL` call in it, no `PROTSHELL=` test, no privilege of any kind.
  ~~**Any process may register, and the last valid caller wins** - `0x454` is
  overwritten on every valid call, with no ownership, refcount or handback.~~
  **Corrected 2026-10-11:** any process may register, but **only the first
  registration takes effect** `[OBS-RE]`. `DOSSMINITIALIZE` calls `DOSSMSGINIT`
  (obj3+0x9fbc), which returns 418 when obj5+0xadc is already set
  (obj3+0x9ceb-0x9cf2). `DOSSMINITIALIZE` forgives only 481
  (`ERROR_SMG_NO_HARD_ERRORS`, obj3+0x9fc4) and jumps past the `ShellPID` store at
  obj3+0xa04a on any other non-zero result (obj3+0x9feb), so a second
  registration does not take over. **It returns 0, not 418:** the 418 travels in
  DX and AX is overwritten at obj3+0xa096 (`lea ax,[bp-0x4]`) before the tail's
  test, so neither DOSSMINITIALIZE's 461 nor this 418 reaches the caller. On that
  path `DOSSMSGINIT` never writes its out-parameter, yet `DOSSMINITIALIZE` copies
  through it (`lds si,[bp-4]` / `lodsb`/`stosb`, obj3+0x9fc1-0x9fde) into
  obj5:0x327: an uninitialised far pointer, a hazard, not a contract. Whether
  anything resets obj5+0xadc (for example `DOSSMTERMINATE`) was not read.
  **[2026-10-12 `[OBS-RE]`: `DOSSMTERMINATE` does not - its whole body is the
  session lock and one kill call ("The shell's private entry points" below). Any
  other writer of obj5+0xadc is still not read.]**
- **Behavioural proof** (observed): set `PROTSHELL=CMD.EXE`, then type
  `pmshell` at the prompt. It works. Before that command, `DosStartSession` is
  refused (`SMG_Flags` bit 0 clear); after it, sessions work - one anecdote that
  exercises the whole registration contract end to end.
- **`obj5+0x432` therefore confers nothing.** It is read as a *selector*
  (`mov gs,[0x432]`), and obj5 is a format-SHARED object - one copy
  system-wide - so it can only hold a value that is valid in **every** process:
  the architectural LDT selector through which any process reaches its **own**
  local infoseg. What differs per process is the *contents* behind it
  (`LIS_CurProcID`), not the selector. A field that is the same constant for
  everyone cannot be what distinguishes the shell.

**An earlier RE write-up was wrong here**: it searched both binaries for a writer of `0x432`, found none, and
concluded the field is *"most plausibly kernel-populated at process-creation
time for whichever process is launched as `PROTSHELL=`"*, with the practical
upshot that *"a minimal client can't self-prime this field; it's a
process-launch-level property, not a client-callable one."* The negative search
was sound and the inference was not. The field needs no priming by the client
because it is the same for everyone, and the corpus's own live test - a
hand-written `sessmgr.exe` whose gate **passed** - is what self-registration
predicts and what a PROTSHELL privilege would forbid.

**Consequence:** with a `PROTSHELL` that never registers - `CMD.EXE` is the
standard example - `SMG_Flags` is never set, so `DosStartSession` is refused with
418 at the request side; and even a queued request would never be served, because
no process satisfies the `ShellPID` test. Session management is absent, not
degraded. `TSHELL.EXE` is the other historical shell that does register (it
imports `DosSMInitialize`/`DosSMStart`/`DosSMSwitch`/`DosSMServeAppReq`/
`DosSMGetStatus` and nothing of PM).

> **This paragraph is correct, has been here since 2026-08-21, and was still
> missed repeatedly - recorded 2026-08-23 because the miss is the useful part.**
> Restated plainly (*"`Dos*Session` will not
> work if PMSHELL isn't running. It's what builds the window list and interfaces
> with the kernel session/screen group code. If you're taking `PROTSHELL` and
> setting it to anything other than PMSHELL, it's going to be broken"*), adding
> that they had had the conversation *"too many times to count."* A reader who
> reaches this section already has the answer; the failure mode is not reaching
> it. So the operational form of the rule now lives where sessions are actually
> pointed - and this note is the pointer back.
>
> **One distinction that this paragraph does NOT make, and that its number
> invites.** "Refused with 418" describes a real machine whose `PROTSHELL` never
> registers: an ordinary caller, in its own session, missing only the
> registration. It does **not** describe a harness in which a *test probe* is
> itself `PROTSHELL` - a configuration real OS/2 never runs, where the caller
> lands in session 1 and therefore **is** the shell, making every session
> identity degenerate rather than merely unregistered. The same 418 can come
> back from both, and only one of them is a measurement of OS/2. Do not read
> this paragraph as licensing the second.

### What registration runs: `DOSSMSGINIT`, `DOSSSINIT` and the four session-manager threads `[OBS-RE]`

Read 2026-10-12 from the Warp 4.5 uniprocessor `DOSCALL1.DLL` with its matched `.SYM` and its
object-5 image, `HARDERR.EXE` with its `.SYM`, and the SMP 14.104a kernel; recorded in unpublished notes. Offsets are object 3 unless named.

`DOSSMINITIALIZE`'s first call runs `DOSSMSGINIT`, which calls `DosSGSwitchMe(1, 0)`, caches the
InfoSeg selectors and `SIS_MaxScrnGrp`, runs `DOSSMINITALLOC` (the `FreeGroups` seed, `ShellPID`),
and then, in IBM's order:

1. sets `SMG_Flags` bit 1 (device-driver notification enabled) only when `HardError_Do_NotifyDD`
   (obj5+0xb02) is 0;
2. `DosExecPgm` of `HARDERR.EXE` with **flags 5 `EXEC_LOAD`** - loaded frozen - and the result into
   `HardErrPID`; **a failed exec is tolerated**: its rc is discarded and `HardErrPID` keeps its image
   value 0;
3. only when the exec succeeded, `DosSGSwitchProc2(HardErrPID, 0, 0)` (DOSCALLS #105) - HARDERR
   into screen group 0;
4. `DOSSSINIT` (below);
5. `DOSSGDDNOTIFY(0x8000, 0x8001, 0)`, rc not tested - which publishes `SIS_CurScrnGrp` = **1**
   (below);
6. `KbdCharIn(&CharData, IO_NOWAIT, hkbd 0)`, rc not tested;
7. `DosGetEnv`, then the `OS2_SHELL` scan (below); **when no `OS2_SHELL` is found the routine goes
   straight to step 9 with rc 0, so the threads of step 8 are not started**;
8. four `DOSSMNEWTHREADS` calls, stopping at the first failure;
9. only when `HardErrPID` != 0: set `HdeSMGRamSem`, `DosSystemService(0, {1, HardErrPID}, 0)` -
   service 0, subfunction 1, which **thaws the single process HARDERR** that step 2 loaded frozen -
   then wait up to 10 s on `HdeSMGRamSem`;
10. return the rc - **unless `HdeRC` (obj5+0xa28) is non-zero, which replaces it**.

A failure of step 4, of `DosGetEnv`, or of a thread start skips to step 9.

`[OBS]` 2026-10-12 (Warp 4.50, a flag-0 registration by a text-mode `PROTSHELL`, `PROTECTONLY=YES`):
`DosSMInitialize` answered 0, and the shell's `LIS_CurScrnGrp` and `SIS_CurScrnGrp` then read 1.
In one configuration it **did not return, 2 of 2 boots** - after the same shell had run a child
process, three VIO-writing threads and two `VioWrtTTY` threads, all ended, before registering (the
conditions in full: "A registered text-mode shell under `PROTECTONLY=YES`" below). Which of the
steps above it stopped in is not established; a kernel-debugger stack of the hung thread would say.

**`HdeRC` decides what registration answers.** Its image value is 481 `ERROR_SMG_NO_HARD_ERRORS`.
`HARDERR.EXE` gets a far pointer to `HdeSMGRamSem` from `DosSMHDEInit`, starts its own threads, and
then zeroes `HdeRC` (that pointer + 4) **only when all of its threads started**, and clears
`HdeSMGRamSem`, which ends step 9's wait. So `DOSSMINITIALIZE` answers 0 on a boot where HARDERR
started its threads, and **481 otherwise - on every path**, masking a failed `DOSSSINIT`, a failed
`DosGetEnv`, a missing `OS2_SHELL` or a failed thread start. `DOSSMINITIALIZE` carries on past 481
(above). The writer being outside DOSCALL1, through a pointer, is why a search of DOSCALL1 for the
cell finds only reads.

**`DOSSSINIT`** (obj3+0xaf96) claims the screen-save manager: a zero `ssmgr_pid` is claimed with the
caller's pid and save records (the 92-byte records of "The screen save/restore record" below) are set
up for **screen groups 0 to 3**; a different pid gets **425 `ERROR_SCS_NOT_SESSION_MGR`**; the same
pid gets 0 and creates nothing. Each record gets a **16-bit system semaphore**: `SSSEMSETUP` calls
DOSCALLS #24 `DosCreateSem(noexclusive, &record+0x2f, name)`, the name being `\SEM\LKNED000.SEM` with
the group's three decimal digits written in. So registration creates **`\SEM\LKNED000.SEM` ...
`\SEM\LKNED003.SEM`**, and every later record one more. A create failure answers **479
`ERROR_VIO_INTERNAL_RESOURCE`**; on success the record's semaphores at `+0x33`, `+0x37`, `+0x3b` and
`+0x3f` are cleared. The index pool holds sixteen 9-byte slots and a record takes two (the 18-byte
index entry `SSFINDSG` walks), so one pool page holds **8 records**; a ninth grows object 5 with
`DosReAllocSeg`.

**The closing `DOSSGDDNOTIFY` publishes 1, not 0.** The call pushes `dword 0x80008001` then `byte 0`;
a 16-bit `push dword` stores the low word at the lower address, so the arguments are 0x8000, 0x8001,
0. The second is not 0xFFFF, so `DOSSGDDNOTIFY` looks up group 1's save record - which `DOSSSINIT`
created, this call being reached only after it succeeded - and calls `DosSGSwitch` (#54), whose
kernel entry stub loads `AX` = 0x8000, `BX` = 0x8001, `DX` = 0. `h_w_DosSGSwitch` skips the task
searches for `AX` and `BX` (high byte 0x80), ignores `DX`'s group 0, and stores `BL` into both copies
of `SIS_CurScrnGrp`: **1**. So a boot ends with `SIS_CurScrnGrp` = 1 whether or not #54 is reached,
`DosSGSwitchMe(1, 0)` having already published 1. `KbdSwitchFgnd(1)` follows and moves nothing,
group 1's `SGCB+0x88` being still 0.

**The `OS2_SHELL` scan** compares the nine characters `OS2_SHELL` and **does not test that the next
character is `=`**. On a match it stores the value's program name and arguments (`CmdName`,
`CmdArgs`, read later by `DOSSMGETNAMES` as the default program for a session start) and **writes a
NUL into the caller's own environment segment** at the first blank after the program name. So when
the value carries arguments, the registering shell's own `OS2_SHELL` variable is truncated to the
program name; when it carries none, the store rewrites the terminator and nothing visible changes.

**The four threads**, from the `NewThreads` table in object 5 (obj5+0xab6), each created with
`DosCreateThread` on a stack from `DOSSMGETMEM`, all in the registering shell's process:

| thread | stack | first wait | what releases it |
|---|---|---|---|
| `DOSSMCHILDWAIT` | 4 KB | `DosSetPrty` to time-critical, then a request of `StartRamSem` (obj5+0x470) with no timeout; `DOSSMINITALLOC` set it | `DOSSMSGSTART`'s clear; then `DosCWait` ("Who notices that a session ended") |
| `DOSSMHDEPOPUP` | 2 KB | `DosMuxSemWait` on a one-entry list: `HdeVioRamSem` (obj5+0xa2a) | the pop-up handshake in `DOSSMSGDOPOPUP`/`DOSSMSGENDPOPUP`, reached from `VioPopUp`/`VioEndPopUp`; it then switches to or from the pop-up group with `DOSSMGSWITCH` under `SwitchRamSem` |
| `DOSSMPOPUPTLECHG` | 2 KB | `DosMuxSemWait` on `PopVioRamSem` (obj5+0xa6c) and `STitleRamSem` (obj5+0xa88) | index 0, the pop-up routines: `PopUpBlockSem`, `DOSSMGSWITCH`, `DOSSMAPPNOTIFY`; index 1, `DOSSMSGSETTITLE` from `DosSMSetTitle`: the title change |
| `DOSSMPAUDAEMON` | 1 KB | `DosSystemService(0, {2}, &PauseResponsePacket)` - service 0, subfunction 2 | the Ctrl+NumLock event; see "Where the hotkey thread sleeps" |

**All four ignore their wait's return code**: an interrupted wait would run the arm the stale index
or response cell selects. On OS/2 such a return is harmless as far as is known - a 95 from process
termination returns through a ring transition, where the thread dies first - and whether any other
`ERROR_INTERRUPT` can reach these waits is not established.

> **The two corpus write-ups disagree on two of these semaphores, and that is left unsettled
> here.** A 2026-10-11 offset census of the decompile (unpublished notes,
> which says a reference in a form the grep misses is not excluded) found no reference to
> `HdeVioRamSem` and only `DOSSMINITALLOC`'s to `STitleRamSem`. The 2026-10-12 read of the threads
> finds both in the threads' wait lists, written as far pointers, and finds `HdeVioRamSem` cleared
> by the pop-up routines and `STitleRamSem` by `DOSSMSGSETTITLE`. The table follows the second
> read, which names its instructions. **The two also name obj5+0xa6c differently** - `SGInitSem` in
> the first (no reference found), `PopVioRamSem` in the second (set by `DOSSMSGINIT`, waited on by
> `DOSSMPOPUPTLECHG`); the `.SYM` was not re-opened here to say which is IBM's.

**Defects in these routines** (IBM's behaviour as found, not a contract to copy; *one read* where
marked):
- `SSGETSGCB`'s found arm sets up the wrong record: when the record `SSFINDSG` found has a zero
  semaphore handle, `SSSEMSETUP` reloads its record pointer from `sgpointeroff` (obj5+0xc12), which
  only the create path writes, so the **last-created** record is set up instead. Reachable only after
  a failed `DosCreateSem`.
- `SSSEMSETUP`'s digit loop has no bound: it divides the group number by 10 into the name's digits,
  writing backwards, until zero.
- The DBCS-vector walk in the `OS2_SHELL` compare has no bound (*one read*).
- `savelockflag` (obj5+0xc6d) is the `client` word of the `DOSFSRSEM` at obj5+0xc65, and
  `DOSFSRAMSEMCLEAR` zeroes it (*one read*).
- `DOSSMREPE`/`DOSSMREPNE` treat 0x09-0x0D, the space, and 0x81 0x40 (a DBCS space) as separators
  (*one read*).

### There are TWO serve loops, and a PM shell does not use `DosSMServeAppReq` `[OBS-RE]`

`DosSMServeAppReq` (`DOSCALL1` obj3+0x99ea) is a real body, not a thunk: base-shell check,
re-entrancy guard (obj5+`0x452`, `0x1a2` if a loop is already running), then a blocking
`DosSMGetAppReq` -> `DosSMDoAppReq` loop. **It is `TSHELL.EXE`'s path** - TShell imports it by name
and has no PM.

**PMSHELL never calls it.** PMMERGE carries its own equivalent loop and drives the same two
primitives directly:

```
PMMERGE obj2  STARTAPPREQUESTLOOP  +0x9906   ; starts the thread
              APPREQUESTLOOP       +0x99ba   ; the loop itself
  99DF: lea ax,[bp-8] / push ss / push ax    ; &pRequest, a local slot
        call far [0x202]                     ; -> DosSMGetAppReq
        mov si,ax / or si,si / jnz -> retry  ; nonzero rc simply loops again
        les bx,[bp-8]                        ; ES:BX = the served request-block
        cmp word [es:bx+4],1                 ; SELECT gets extra switch-entry work first
        ...
  9A43: push [bp-6] / push [bp-8]            ; the block's far pointer
        call far [0x206]                     ; -> DosSMDoAppReq
```

`0x202` and `0x206` are PMMERGE DGROUP function-pointer slots resolved at init, siblings of the
already-documented `PFNDOSSMSWITCH` at `+0x1FA`. So on a PM system the serve loop lives in PMMERGE
and only `DosSMGetAppReq` and `DosSMDoAppReq` are load-bearing; `DosSMServeAppReq` can be absent
entirely without a PM boot noticing.

### The ownership check: `DOSSMDOAPPREQ` -> `SESSIONRELATED` `[OBS-RE]`

The published rule - only a parent may stop its own `Related=CHILD` session (see
"Session-control semantics and return codes" above, `[DOC - EDM2]`) - **is
enforced, once, for the whole family of operations**, in the serve-loop
dispatcher rather than in any individual handler.

`DOSSMDOAPPREQ` (obj3+0x322c) sits between the request queue and the four
`APP*SESSION` handlers. Before dispatching, it loads the requester's own session
from request-block `+0x8` and the target from `+0x22`, and calls
**`SESSIONRELATED`** (obj3+0x9c82):

```
1C03327E  mov bx,[es:di+0x8]   ; the REQUESTER's own session
1C033282  mov cx,[es:di+0x22]  ; the TARGET session
1C033295  call 0x9c82          ; SESSIONRELATED -> nonzero = refuse
```

`SESSIONRELATED` resolves both SGCBs and applies the rule:

```
1C039CB2  test word [fs:si+0x26],0x1   ; requester's SGCB: "has children" bit
1C039CB8  jz  -> ax = 0x1C4            ; 452 ERROR_SMG_SESSION_NOT_PARENT
1C039CBA  cmp [gs:di+0x1c],bx / jz ok  ; target's parent reference == requester
1C039CC0  cmp bx,cx           / jz ok  ; requester IS the target
1C039CC4  cmp [gs:di+0x2c],bx / jnz -> 0x1C4
```

`+0x26` bit 0 and `+0x1c` are the same SGCB fields the creation-time field map
above records.

`[OBS]` 2026-10-12 (Warp 4.50, a registered non-PM shell): `DosSelectSession`,
`DosSetSession` and `DosStopSession` each answered **452** - from a program in a
child session naming the shell's own session, and from the shell naming its
child's child. IBM's pages list 460 for that case; the dispatcher's 452 is what
a caller sees.

Two details of the same code `[OBS-RE]`: **before** `SESSIONRELATED`, a target
whose low byte is not 1 and is below 4 or at or past `SMArraySize` (the session
table's size byte, initially 25 and grown by 8) is refused with **369** without
the relationship test (obj3+0x3279-0x32b7); and the "requester is the target" arm
still needs the requester's has-children bit - a session with no children cannot
name itself. After the handler runs, the dispatcher pulses the shell's
`ShellRedrawSem` when the base shell is `TopMost` - for a start, and for a
`DosSetSession` whose `SelectInd` is not 0; never for a select or a stop.

**It governs Select and Set as well as Stop.** The dispatcher runs it for
request-block `+0x4` opcodes 1, 2 and 3 (`APPSELECTSESSION`, `APPSETSESSION`,
`APPSTOPSESSION`) and exempts only opcode 0 (`APPSTARTSESSION`) - a session
being created has no parent relationship to test yet.

**One documented bypass, for stop only.** When `SESSIONRELATED` *fails* and the
opcode is 3, the dispatcher reads the reserved `ULONG` the caller passed to
`DosStopSession` (request block `+0x26`) and, if it is exactly `0xCDEF1234`,
erases the failure:

```
1C033298  cmp dx,3 / jnz            ; STOP only
1C03329D  or  ax,ax / jz            ; only when the check FAILED
1C0332A3  mov ebx,[es:di+0x26]
1C0332A8  cmp ebx,0xcdef1234 / jnz
1C0332B1  xor ax,ax                 ; failure erased, the stop proceeds
```

That is what the otherwise-undocumented sentinel in `DosStopSession`'s reserved
parameter is for: an authorization override.

> **CORRECTED 2026-08-21 (Rule 1.7).** This section previously recorded a
> **negative result** - that no such check existed anywhere in `DOSSTOPSESSION`,
> `REQUESTBLOCKALOC`, `APPSENDREQUEST` or `APPSTOPSESSION`. Those four were read
> correctly; the check is one frame further up, in the dispatcher that calls
> them, which was not read. A negative result is only as wide as its search, and
> that one was reported as though it were a census.

What *additionally* constrains a caller, and is not the ownership rule: the
scope-1 walk starts at the caller's own session (above), and
`REQUESTBLOCKALOC`'s gates reject on the caller's SM-present flag,
`LIS_CurScrnGrp` and `LIS_ProcType` - i.e. on session **type**.

### Select and Set on the serve side, and the select that is sent again `[OBS-RE]`

The clients (`DOSSELECTSESSION` obj3+0x96a8, `DOSSETSESSION` obj3+0x971c):
`DosSelectSession` refuses a non-zero reserved word with 459 and its own screen
group (by the id's low byte; id 0 selects yourself) with 369. `DosSetSession`
refuses `Length` != 6 with 461, `SelectInd` > 2 with 456, `BondInd` > 2 with 455,
and a non-zero `SelectInd`, or `BondInd` 1, aimed at id 0 or the caller's own
group with 369. Both then build a request block (the target at `+0x22`;
`SelectInd`/`BondInd` at `+0x24`/`+0x26`) and send it to the shell.

**`APPSELECTSESSION`** (obj3+0xabbc): the requester must be in the foreground
family (`FOREGROUNDFAMILY`, else 451); it waits up to **5 seconds** for
`PopUpBlockSem`, and if a pop-up still holds it the answer is not an error code
but the marker **`0xABCD`**, on which the requester's `APPSENDREQUEST` **sends the
same request again** (obj3+0x3f42) - a select made under a pop-up waits for the
pop-up to end. A target other than the requester is followed down its **bond
chain** (each session's bound child, `+0x12`, until one has none); the session
switched to is the last one found, and a session that is not full screen (`+0x10`
neither 1 nor 4) switches to screen group 1, PM's. The switch is
`DOSSMSGSWITCH(0, it, its debugger link, 0)`; under PM, `WinSetExtIDFocus` is
called around it.

**`APPSETSESSION`** (obj3+0xac76): under PM, `WinSetSwEntry` and `SelectInd`
zeroed; then `DOSSMSGSET`, which writes the target's `+0x24` := `SelectInd` - 1
(non-selectable when non-zero) and the requester's `+0x12` := the target for
`BondInd` 1, 0 for 2.

### The shell's other small entries `[OBS-RE]`

- **`DOSSMPARENTSWITCH(sgid)`** (obj3+0x94bd): `PopUpBlockSem` tried without
  waiting (held -> 451); `SMRoutSem`; the session (369 if none) and **its parent**
  (371 if none); then the end-of-session foreground hand-back
  (`PARENTSWITCH`) run on the **parent** - so the foreground moves to the parent's
  ancestor when the parent is on top, else 451.
- **`DOSSMSETSESSIONTYPE(sgid, type)`** (obj3+0xaef4): base shell only (431); a
  type other than 4 or 7 -> 491; a session whose own type is not 4 or 7 -> 491; else
  both type copies (`+0x10`, `+0x0b`) set and, for 7, `DosSetFgnd(3, sgid)`. It
  moves a DOS session between full screen and a window and refuses every other.
- **`DOSSMPOPUPTLECHG`'s title arm** (obj3+0xa91c): woken when `DosSMSetTitle`
  clears `STitleRamSem`; it sets the semaphore again and, with no pop-up up,
  calls `DOSSMAPPNOTIFY(0, 1, 0)` - the shell's own session notified as if it
  had ended - which pulses the shell to redraw and, when the shell has started
  related sessions, closes the shell's termination queue and clears its
  `+0x1e`; under a pop-up the change is counted and replayed when the pop-up
  ends.

### `DosStartSession`'s two segments `[OBS-RE]`

`DOSSTARTSESSION` (obj3+0x361e-0x37c4) gives the shell two more things besides the
request block. With `Length` 60 the `ObjectBuffer`: with `InheritOpt` 1 the
caller's own buffer (the requester's exec writes it), otherwise a segment of
`ObjectBuffLen` bytes the shell's exec writes, copied back into the caller's
buffer when the start fails. The `Environment`: for a DOS type it goes through
the VDM layer's conversion; with `InheritOpt` 1 the caller's pointer is kept;
otherwise its length to the double NUL is measured and it is copied into a
segment of its own. A failed allocation is the call's return code.

### Which callers actually pass that gate: measured `[OBS]`

The gate above is read out of the binary; this is what it does to real
processes. One probe binary, run unmodified from four launch contexts on
**Warp 4.50 (Warp Server for e-business), 2026-08-30**, reporting its own `LIS_CurScrnGrp`
and `LIS_ProcType` and then calling `DosStartSession` on `CMD.EXE /C EXIT`:

| launch context | `LIS_CurScrnGrp` | `LIS_ProcType` | `DosStartSession` |
|---|---|---|---|
| `RUN=` in CONFIG.SYS | 0 | 4 `LIS_PT_DETACHED` | **418**, retried 1/s for 180 s, never changed |
| a remote shell (ssh) | 17 | 4 `LIS_PT_DETACHED` | **418** |
| child of a detached parent | 17 | 4 (inherited) | - |
| **`STARTUP.CMD`** | 17 | **2 `LIS_PT_VIOWIN`** | **0**, on the first call at t=0 |

**A `RUN=` process is a detached app and stays one.** It is `LIS_PT_DETACHED`
by IBM's own taxonomy - the same category `DETACH` produces - and a detached
process has no session, so it cannot be a session's parent. This is not a
timing window: the probe re-read its context after 180 seconds, long after
`PMSHELL` had registered, and both fields were unchanged. **Waiting for the
session manager to come up does not make a `RUN=` process eligible**, which is
the natural design and it does not work.

**`STARTUP.CMD` is eligible immediately.** `PMSHELL` launches it via
`DosStartSession`, so it is `LIS_PT_VIOWIN` in a real screen group, and
`DosStartSession` succeeds on the first attempt with no polling - necessarily,
since the session manager is what launched it. Both `InheritOpt` values work
(`SSF_INHERTOPT_SHELL` and `_PARENT` returned 0 and distinct session ids);
`InheritOpt` selects who performs the spawn (fact above) and has no bearing on
who is permitted to ask.

**`ProcType` is inherited from the parent, not derived from the executable.**
Measured with a single-variable comparison: one source file built twice,
differing only in the declared application type in the module header -
`WINDOWCOMPAT` (`0x0200`) and `WINDOWAPI` (`0x0300`) - both `DosExecPgm`'d by
the same detached parent. Both children reported `sg=17 ptype=4`, identical to
the parent. The PM-typed one started cleanly (exit 0); the kernel did not
refuse it, it simply ran it detached.

**So detachment is inescapable from inside a detached process**, because all
three exits are closed at once:

- **No setter.** The Toolkit exposes `DosGetInfoSeg` and `DosQueryProcType`,
  both read-only, and the session APIs act on *other* sessions. Nothing writes
  `LIS_CurScrnGrp` or `LIS_ProcType`.
- **No inheritance escape.** `DosExecPgm` propagates the parent's context
  regardless of what the child's own header declares (measured above).
- **The only call that assigns a fresh `ProcType` is `DosStartSession`** -
  which is exactly what a detached caller is refused.

A detached process and its entire descendant tree are therefore permanently
sessionless. Anything that must start sessions has to be **created** by a
process that is not detached.

**A trap worth stating, because the enumerations nearly agree.**
`SSF_TYPE_*` (the `STARTDATA` input) and `LIS_PT_*` (the observed result) are
different enumerations that coincide on three of five values:

| value | `SSF_TYPE_*` (input) | `LIS_PT_*` (observed) |
|---|---|---|
| 0 | `DEFAULT` | `FULLSCRN` |
| 1 | `FULLSCREEN` | `REALMODE` / `VDM` |
| 2 | `WINDOWABLEVIO` | `VIOWIN` |
| 3 | `PM` | `PRESMGR` |
| 4 | `VDM` | **`DETACHED`** |

Reading an observed `ProcType` back through the `SSF_TYPE_*` names reports a
detached daemon as a VDM.

`LIS_PT_*` values are `[DOC-IBM]`, Table 77 "LIS_ProcType Flag Definitions" in
the *OS/2 Debugging Handbook Vol. IV* (SG24-4643-00), which also fixes the
field offsets the gate reads: `LIS_CurScrnGrp` at `InfoSegLDT+0x8` (word) and
`LIS_ProcType` at `+0xe` (byte) - so `cmp byte [gs:0xe],0x4` in
`REQUESTBLOCKALOC` is literally testing `LIS_ProcType == LIS_PT_DETACHED`.

**Not measured:** a program launched from a **Startup folder object**. It is
presumably equivalent to `STARTUP.CMD`, since `PMSHELL` creates both through
`DosStartSession`, but that was not run and the assumption is exactly the kind
this section exists to replace.

**Added 2026-10-12 `[OBS]`: a sixth context, a detached child of the registered
shell itself.** A process the registered text-mode shell (next section) started
with `DosExecPgm` `EXEC_BACKGROUND` got **460** from `DosStartSession`, and **452**
from `DosSelectSession`, `DosSetSession` and `DosStopSession` (scope 0, a child's
id) - not 418. Its own `LIS_CurScrnGrp` and `LIS_ProcType` were not captured.
`[INF]` from the gate above: it inherits the shell's group 1, and the `== 1`
accept branch runs before the `LIS_PT_DETACHED` test, so it reaches the
related-start rule (460) and the ownership check (452). So the table's 418 is
not the answer for every detached process.

### A registered text-mode shell under `PROTECTONLY=YES`: what the session calls answered `[OBS]`

Captured 2026-10-12 on Warp Server for e-business 4.50 (revision 14.089, the
retail SMP kernel) in a 2-vCPU VirtualBox guest, with `PROTECTONLY=YES` and
`PROTSHELL=` set to a 16-bit text-mode test program. That program registers
with `DosSMInitialize` using a flag-0 block (no PM), serves requests with
`DosSMServeAppReq` on a second thread, and then makes the calls below itself.
Its own sessions are copies of the same program, which report their InfoSeg
fields and run an exit list that records its termination code. One capture
per row unless a count is given. Under this configuration `StartParmsMaxLen`
is 30, and every start below used a 32-byte `STARTDATA` unless a row says
otherwise, so every start was over the maximum and its 461 forgiven
("`DosStartSession` on the requester side" above).

**Registration.**
- Before `DosSMInitialize`: `DosStartSession` -> **418**. After it: the shell's
  `LIS_CurScrnGrp` and `SIS_CurScrnGrp` both read **1**, as "What registration
  runs" below reads.
- A start made **after `DosSMInitialize` but before the serving thread
  existed** answered **461, not 343** (4 of 4 boots), with the session-id word
  0 and the process-id word set to **1918** each time, a value no process had
  (the caller had zeroed it). `[INF]` this matches the 343 -> 461 rule above: the start was a
  forgiven one and `\QUEUES\SESMGR\APPREQQ` did not exist yet. The capture
  does not distinguish that from another cause.
- **`DosSMInitialize` did not return, 2 of 2 boots**, in one configuration:
  the same shell, before registering, had run a child process with
  `DosExecPgm` and waited for it, run three threads making VIO calls in its own
  session at once, and then run two threads each issuing 200
  `VioWrtTTY`/`VioGetCurPos` pairs; every one of those threads had ended. The
  shell's log ends at the `DosSMInitialize` call. In five other boots of the
  same pass, without those rows before it, `DosSMInitialize` returned 0. The
  cause is not established.

**`DosStartSession`, the shell as requester.**

| `STARTDATA` | answer |
|---|---|
| `Related` 1, `FgBg` 0, `InheritOpt` 0, `SessionType` 1, a `TermQ` | 0, session id 4 |
| `InheritOpt` 1 | 0, an id |
| `Length` 50, `PgmControl` 0x0010 | 0, a session (the length is clamped before the `PgmControl` check) |
| `SessionType` 5 | **0**, session id **16**, an id from above the full-screen range |
| `SessionType` 4, background, no `Environment` | **641** (`ERROR_VDM_DOWN`), id 0 |
| `SessionType` 0 | 0; the program runs full-screen (`LIS_ProcType` 0) in its own group |
| `FgBg` 1 | **0**, not 457; `SIS_CurScrnGrp` stays 1 |
| `PgmName` naming no file | **2** (`ERROR_FILE_NOT_FOUND`), id 0, pid 0 |
| `InheritOpt` 2 / `TraceOpt` 2 with `Related` 0 / `Related` 2 / `TraceOpt` 3 / `FgBg` 2 | 493 / 503 / 454 / 478 / 453 |
| `Related` 0, a program that ends by itself | **0, id 0, pid 0 - and a session was created and the program ran**: `DosSMGetStatus` listed one new session right after the call |
| `Length` **23** | **the call never returned** (3 of 3 runs; the shell's log ends at the call) |

- Every session's program reported the **shell's** pid as its parent -
  including programs whose sessions were started by a program in another
  session, and one started with `InheritOpt` 1.
- A related start by a second process in a child session (a process the
  session's program had started with `DosExecPgm`), made while the session's
  program had a related session alive, answered **460**.
- From a program the shell started in the **background** (so its family did
  not hold the foreground): a foreground, related start answered **457** and
  the session started in the background; `DosSelectSession` of that new
  session answered **451**.

**The termination queue.**
- **When the requester is the registered shell, no element arrives.** The
  first start naming the shell's own queue answered 0 and its program ran and
  ended, but no element was read, in three runs (in the last, the read waited
  30 s after the session had left `DosSMGetStatus`'s list). **Every later start by the shell that
  named a `TermQ` answered 461** - its own queue, again, in the foreground or
  the background (five starts across two runs), and a queue name that did not
  exist. Starts that named no `TermQ` kept answering 0.
- **A requester that is not the shell gets the documented element.** Each of
  three programs in sessions of their own started a related program naming
  its own queue, stopped it, and read one element: request 0, 8 bytes,
  {session id, result 0, 0, 0}, written by a process other than the reader,
  and nothing else in the queue.
- `[INF]`: a 461 from a forgiven start is what the 343 -> 461 rule gives when
  the shell's open of the `TermQ` fails, which would explain the missing name.
  Why the shell's own queue fails after its first use, and why the first use
  delivers nothing, is not established; see "The `TermQ` write" below.

**Select, Set, Stop, switch and foreground.**
- `DosSelectSession` of the shell's own child: **0**, and `SIS_CurScrnGrp`
  moved 1 -> 6; `DosSelectSession(0)` then answered 0 and moved it back to 1.
- In the selected program after that select: `LIS_CurScrnGrp` 6,
  **`LIS_Fgnd` 0000**, `SIS_FgndPID` not its own pid, and through a child it
  started, `QSV_FOREGROUND_FS_SESSION` (24) = **6** and
  `QSV_FOREGROUND_PROCESS` (25) neither that child nor the selected program.
  Compare a full-screen child started in the **foreground** earlier the same
  boot: its child read QSV 24 = **0x104** (260) and QSV 25 = its parent.
  See "The switch sequence, in order" below for the reading this disagrees with.
- A program started in the background read `LIS_Fgnd` FFFF and
  `SIS_FgndPID` = its own pid, with `SIS_CurScrnGrp` still 1. Of two programs
  started back to back in the background, the first read `LIS_Fgnd` 0000 at
  its first read and the second FFFF.
- Select, Set and Stop of a session the caller did not start each answered
  **452** - both a program in a child session naming the
  shell's session, and the shell naming its child's own child. IBM's pages
  list 460 for "not the parent".
- The shell made a child non-selectable and bonded to it with `DosSetSession`
  (0, 0). `DosSMSwitch(2, ...)` to that child then answered **450**;
  `DosSMSwitch(0, 1)` - to the shell's own group - brought the **bonded
  child** forward (group 4); and `DosSelectSession` of the non-selectable child
  answered 0 with it still in the foreground (it was already there, so this
  row does not show a move of its own).
- `DosStopSession` of that bonded child, which had a related child of its own
  and was in the foreground: 0; the child's child ended (exit-list termination
  code **3**, `TC_KILLPROCESS`) and left `DosSMGetStatus`'s list, the
  foreground returned to group 1, and a later `DosSMSwitch(0, 1)` showed
  group 1 (the bond was gone).
- `DosStopSession(1, 0)` with two children alive: 0, and both were gone 2 s
  later.
- A program in a child session started a related session and then ended
  without stopping it: that session ended too, with exit-list termination code
  **3**. Every stopped session's exit list also reported 3.
- When the shell's foreground child ended, `SIS_CurScrnGrp` read 1.
- `DosSetFgnd` (`DOSCALLS` 101) scope 0 with a background child's pid: 0;
  `SIS_FgndPID` became that child and its `LIS_Fgnd` read FFFF, and
  `SIS_CurScrnGrp` stayed 1. Scope 3 with that child's group (6): 0;
  `SIS_CurScrnGrp` stayed 1 and QSV 24 read 6. Scope 5: 308. These agree with
  "`DosSetFgnd` (`#101`) is a scope dispatcher" below.

**`DosSMStart`** (flag 0, background, type 1, no title): 0, and the output word
**0x0104** (type 1, session id 4); the program ran in group 4. `DosStopSession`
of that id answered **452**, as for an independent session.

The other answers of this pass agreed with the tables above and the readings
below: `DosSelectSession` 369 (its own group's id, and an id past the table),
459; `DosSetSession` 0, 461, 456, 455, 369; `DosStopSession` 0, 458, 459, 369;
`DosSMSwitch` 371 for an unknown id.


### The shell's private entry points: `DosSMStart`, `DosSMSwitch`, `DosSMGetStatus`, `DosSMTerminate` `[OBS-RE]`

IBM publishes no prototype for any of these four (no header or DDK source declares them); they are
`DOSCALL1.DLL` exports, reached through `SESMGR.DLL`'s forwarders, and what follows is read from the
Warp 4.5 `DOSCALL1.DLL` (uniprocessor build, its matched `.SYM`). All are 16-bit Pascal entries.
Two locks recur: **`PopUpBlockSem`** and the session-mutation lock **`SMRoutSem`**, both
`DosFSRamSemRequest`ed with no timeout and retried on 95 `ERROR_INTERRUPT`.

**`DosSMStart` (`DOSCALLS` 708) is a body, not a thunk, and it is a direct start that bypasses
`STARTDATA` and the request queue.** Its 26-byte frame is eight arguments, in declaration order:

| # | width | meaning |
|---|---|---|
| 1 | word | low byte used only for a foreground start of type 1 or 4: 1 = do not switch the outgoing screen group to the background (no save) |
| 2 | word | 0 = start in the foreground, otherwise in the background |
| 3 | word | session type; **3 is treated as 4** |
| 4 | far pointer | the title, ASCIIZ; `NULL` or empty = the default title (below) |
| 5 | far pointer | the program name |
| 6 | far pointer | the program's arguments |
| 7 | far pointer | out: one word, the new session's packed id `(type << 8) \| sgid`, written before the session block's creation is checked |
| 8 | dword | **never read** |

It takes `PopUpBlockSem` (a failure other than 95 is ignored) and `SMRoutSem`, runs the same start
engine `DosStartSession`'s serve side reaches, and releases both. The engine runs as for an
**untraced, independent** start (`ExecFlags` 5 `EXEC_LOAD`, no parent, no requester, no completion
callback, `InheritOpt` 0), and its `RESULTCODES` go to a session-manager global rather than to the
caller. **It answers 431 `ERROR_SMG_NOT_BASESHELL` unless the caller is the registered shell**, 370
when no session id is free, and otherwise the engine's answer, as for any start.
`[OBS]` 2026-10-12 (Warp 4.50, a registered non-PM shell): `DosSMStart(0, 1, 1, NULL, program,
arguments, &word, 0)` answered 0 with the word **0x0104** (type 1, session 4), the program ran in
group 4, and `DosStopSession` of session 4 answered **452** - the independent start the engine
makes has no parent to stop it.

**`DosSMSwitch` (687)**, `retf 8`: `(USHORT mode, USHORT sgid, ULONG reserved)`. It takes both locks;
mode 1 is treated as mode 0; an unknown id answers 371; a session whose block is marked
non-selectable answers **450 `ERROR_SMG_SESSION_NON_SELECT`**; mode 5 becomes mode 4 and skips the
bond walk, every other mode follows the bond chain to its end. **With PM present it then calls PM's
`WinSetExtIDFocus(sgid, the third argument)`**; a target whose type is not 1 or 4 is replaced by
screen group 1; and it calls the inner switch with `(mode, sgid, the session block's +0x2C word,
the third argument)` - the inner switch stores that word as the session manager's
`IncomingDebugger` - - except mode 4 (and so 5), which passes mode 0 and 0. **The inner switch treats
that dword as reserved: non-zero, or a mode above 3, answers 459 `ERROR_SMG_BAD_RESERVE`.** So the
third argument means something only to PM, and only modes 4 and 5 can carry a non-zero one through.
PM's Window List passes `(4 or 5, its packed id, 0 : the offset of its switch entry)`; a shell passes
0. The inner switch answers 431 for a caller that is not the registered shell.
`[OBS]` 2026-10-12 (Warp 4.50, a registered non-PM shell): mode 2 to an unknown id answered 371,
to a non-selectable child 450, and to a selectable child 0 (and back with `(0, 1)`); and after the
shell had bonded a child, **`DosSMSwitch(0, 1)` brought the bonded child forward**, not the shell's
own group - the bond walk.
`[OBS]` 2026-10-13 (Warp 4.50, a registered non-PM shell switching between two full-screen children
A and B, each blocked in a keyboard read): **mode 2 saves no screen, and a group switched away from
with mode 2 was not restored when a later mode-2 switch brought it back.** Whether a mode-0 switch
restores it was not tried. The first `DosSMSwitch(2, B)` showed B's screen,
which B had written while in the background. After it, no switch changed the physical screen. On
`DosSMSwitch(2, A)` (rc 0, `SIS_CurScrnGrp` = A), B's text stayed up and A's next write appeared at
A's cursor over it. With **mode 0**, every switch saved the outgoing screen and restored the
incoming one. This fits the switch's background half, which skips the save for switch kind 2 and
marks the outgoing session block (`+0x14` bit 0), so the foreground half later skips its restore.
That the mode word arrives as that switch kind is `[INF]`; it was not read from the bytes.

**`DosSMGetStatus` (703)**, `retf 6`: `(USHORT level, PVOID buffer)`.
- `level` >= 4 -> **432 `ERROR_SMG_BAD_STATUSREQ`**, tested first; a caller that is not the registered
  shell -> **431**.
- The buffer starts with a header the caller sizes: `+0` = the header length in bytes, `+6` = the
  size of one record. The call writes **`+2` = the number of allocated session ids** and **`+4` =
  the id of the first selectable session after the foreground one** in the session manager's
  forward list (the foreground one if none is selectable). A text-mode shell switches to this id
  for Alt+Esc, so it is the session manager's nomination for the next session `[INF]` from that
  use.
- **Level 2** stops after the header. Levels 0, 1 and 3 then write one record per session,
  `+6` bytes each, starting at `buffer + header length`, walking the whole list once: from the
  foreground session for **level 0**, from the shell's session for **levels 1 and 3**; **level 3**
  writes only the session whose packed id equals the word the caller left at `+2`.
- Records are written only if the header length is at least 8, and **the walk does not check the
  buffer's own length**: a caller must size the buffer for every session that can exist.
- A record, truncated to the record size: `+0x00` the session id (word); `+0x02` the title, 32
  bytes, copied to its NUL and padded with spaces, no terminator - **written only when PM is not
  present** (with PM the 32 bytes are skipped); then nine words from the session block -
  `+0x22` the non-selectable mark, `+0x24` the flags word, `+0x26` the first child's id, `+0x28`
  the next sibling's id, `+0x2A` the bound child's id, `+0x2C` the parent link, `+0x2E` the session
  type, `+0x30`/`+0x32` the second family link and the word after it. A full record is 52 bytes;
  a 36-byte record carries the id, the title and the non-selectable mark.
- Returns 0.

**`DosSMTerminate` (705)**, `retf 6`, never reads its frame. It takes `SMRoutSem`, calls the 16-bit
`DosKillProcess` with **one** word pushed (0) where that call takes two, releases the lock and returns
the kill call's answer. The kernel therefore reads a process id of 0 and, as the action, the word
above it - `DosSMTerminate`'s own saved frame pointer. `[INF]` from the kernel's argument checks:
the answer is 13 `ERROR_INVALID_DATA` for any action other than 0 or 1, else 303
`ERROR_INVALID_PROCID` for process id 0, so **`DosSMTerminate` ends nothing**. Not measured.


### The foreground-switch mechanism

Switching which session is foreground (Ctrl-Esc/Alt-Esc, or a Window List selection) is a
**different operation from session creation/selection above** - a lower-level primitive the public
`DosSelectSession` API does not even call (confirmed: a real Window List switch, live-traced, never
touches `DosSelectSession`'s own entry point). The real chain, symbol-verified end to end on a live
Warp 4.5 system:

1. The Window List (part of the PM shell) resolves the internal switch entry point once, at PM
   init, and calls it through a stored function pointer thereafter - the call is never a static
   reference, which is why it cannot be found by disassembling call sites; only observing the live
   pointer value (or single-stepping into the call) reveals it.
2. That call reaches the session-manager's own switch dispatcher inside `DOSCALL1.DLL`, which
   acquires two locks (global session-manager state, shared across all processes), looks up the
   target SGCB, and dispatches to a mid-level orchestrator by request type (foreground switch,
   background switch, popup, child-exit, and others share this same entry point).
3. The mid-level orchestrator re-derives both the outgoing and incoming SGCB and type-dispatches
   to one of three handlers: **switch-to-foreground**, **switch-to-background**, or
   **switch-to-popup**.
4. All three handlers converge on the same two real operations: a **screen-buffer save/restore**
   call (which itself is mostly a gate - it checks whether the tracked "current" session already
   matches the target and no-ops if so, only actually invoking the restore machinery on a genuine
   change) and a **device-driver notify** call.
5. The device-driver notify call walks a registered-driver notify chain and - for the keyboard
   specifically - invokes the keyboard driver's own focus-switch entry point, which looks up the
   target session's registered focus handle (the SGCB `+0x88` field above) via a table-driven
   lookup and returns it as the new keyboard-focus owner. This is table-driven, per-session-handle
   dispatch, not a broadcast to every process.

**The switch-mechanism chain above has no mouse-equivalent of the keyboard-focus handoff** - every
function in that chain was read in full; the device-notify step only ever invokes the keyboard's
handler, never an analogous mouse one. **This is not because mouse has no switch-aware mechanism at
all** - the mouse driver has its own, reached through a different path (its own IOCtl category's
session-control notification, carrying explicit pre-switch/post-switch/creation/termination event
types, distinct from the notify chain above). It tracks which session is currently foreground and
does real work on a switch: transferring to a full-screen/DOS-compatibility session runs a real
begin/end-switch sequence through the legacy mouse-emulation interface; transferring to a
non-full-screen (windowed/PM) session instead **explicitly disables the driver's own mouse-data
processing** - a deliberate hand-off, not an omission. That's why PM's own input routing shows no
per-session mouse-focus table the way keyboard has one: mouse events there carry their own screen
coordinate and are delivered by ordinary hit-testing against whichever window is visible on top,
and the driver has already stepped out of the way by the time PM is foreground. Keyboard input
carries no spatial coordinate, so it needs the explicit per-session handle handoff described above
even while PM is running - the asymmetry is real, but it exists between "how PM handles mouse vs.
keyboard while it's foreground," not between "mouse has a switch mechanism and keyboard doesn't."

> **CORRECTED 2026-09-20 (Rule 1.7). THE PARAGRAPH BELOW IS WRONG ABOUT THE
> ORDER, AND THE "not confirmed" IT ENDS ON IS ANSWERED. It is kept and marked
> rather than rewritten - the misreading it records is the natural one - and the
> correction is placed HERE, above it, so a reader going top to bottom never
> acquires the wrong prior first.**
>
> `_schSetScreenGroupFgnd` is the sole writer of the kernel's `_FgndSGID`, and it
> runs **four** steps, not "both sweeps, then the store":
>
> 1. return 0 immediately when the requested group already equals `_FgndSGID` -
>    an already-foreground group succeeds without scanning anything;
> 2. the **outgoing** sweep, revoking the boost of every task in the group
>    `_FgndSGID` currently names - it is handed `_FgndSGID` itself, so it must
>    precede the store;
> 3. **the store**;
> 4. the **incoming** sweep, applying the boost - *after* the store.
>
> So exactly one of the two sweeps runs before the tracking variable moves. The
> difference is not cosmetic: the store happens **even when the incoming group
> has no tasks**, and the call then returns `369 ERROR_SMG_INVALID_SGID` with
> `_FgndSGID` already pointing at the empty group - so a caller that reads 369 as
> "nothing happened", and an implementation that refuses and changes nothing,
> both diverge.
>
> `[OBS-RE]`, identical in the SMP and UNI builds. Established 2026-09-05 and
> recorded in unpublished notes with the listing, and corroborated independently in two
> others.
>
> **And the link the paragraph leaves open is `DosSetFgnd` (`#101`) scope 3**,
> which `DOSSMGSWITCH` issues on the incoming screen group after the screen-group
> publish - see "The switch sequence, in order", below.

A separate, kernel-level mechanism propagates scheduling priority during a switch: every task
belonging to the outgoing screen group has its priority boost revoked, and every task belonging to
the incoming one has its priority boost applied, before the screen group's "current foreground"
tracking variable is updated. Whether/how this kernel-level priority mechanism is invoked from the
`DOSCALL1.DLL` chain above is not confirmed - both are independently observed real mechanisms; only
the link between them (if any) remains open.

### The complete foreground contract: which call writes which quantity, and in what order  `[OBS-RE]` + `[DOC-IBM]`

**Established 2026-09-20 by reading the sequence end to end - every `DOSCALLS`
ordinal call site in `DOSCALL1.DLL`'s four code objects resolved by import
fixup, and each routine on the path read from its entry.** Read as a *sequence*,
because a routine-against-routine comparison cannot see an ordering.

**"Foreground" is not one value.** OS/2 maintains five. They answer different
questions, they have disjoint writers, and IBM keeps them in step by **sequence**
rather than by any assertion between them - so a reimplementation that treats any
two of them as copies of one another will be right at rest and wrong in flight.

**The documented surfaces are already above** - "Foreground and screen-group
state", with IBM's own header citations - **and the field layouts, the writer
census and the reader census are in `infoseg.md`.** Neither carries the map
below, which is the only thing this table adds: *which call* moves each one.

| quantity | where | width | sole writer |
|---|---|---|---|
| `SIS_CurScrnGrp` | Global InfoSeg `+0x18`, and the kernel-data copy `_SISData+0x18` | byte | `DosSGSwitch` (`#54`); `DosSGSwitchMe` (`#55`) when its second argument is 0; the boot copy |
| `SIS_FgndPID` | Global InfoSeg `+0x1c`, and `_SISData+0x1c` | word | `_schSetKbdLocus`, reached only by `DosSetFgnd` (`#101`) scope 0; and `f_ProcessTerminate`, which zeroes it |
| `_FgndSGID` | kernel data - the source of `QSV_FOREGROUND_FS_SESSION` | word | `_schSetScreenGroupFgnd`, reached only by `DosSetFgnd` scope 3 |
| `_tkFgndPID` | kernel data - the source of `QSV_FOREGROUND_PROCESS` | word | `_schSetKbdLocus` only - written in the instruction next to the `SIS_FgndPID` store |
| `LIS_Fgnd` | Local InfoSeg `+0x0c`, and the owning PTDA's copy | word | `_schSetKbdLocus` only: it clears the outgoing process's copy and sets the incoming one's |

Two more are per-process rather than global and belong with them: `LIS_CurScrnGrp`
(Local InfoSeg `+0x08`, the process's own screen group) and `LIS_ProcType`
(`+0x0e`), both written by `DosSGSwitchProc2` (`#105`) into a *target* process,
and by `DosSGSwitchMe` (`#55`) into the caller's own.

And one is the session manager's own bookkeeping, not an InfoSeg field at all:
**`TopMost`** and **`BottomMost`**, a pair of far pointers in `DOSCALL1`'s
session-manager data segment naming the incoming and outgoing `SGCB` of the last
switch. `DosSGQueryTopmost` returns `TopMost`'s **packed** id, `(type << 8) | sgid`
(`DOSSGQUERYTOPMOST`, obj3+0xa39c: `SwitchRamSem` requested until had, `TopMost`'s
`+0x0a` word read whole, `SwitchRamSem` cleared) `[OBS-RE]`.

**`SIS_CurScrnGrp` and `_FgndSGID` are not the same number, and IBM maintains no
invariant between them** - a `#54`/`#55` switch moves one and a `#101` scope-3
call moves the other. That, IBM's own `QSV_FOREGROUND_FS_SESSION` gloss, and the
live capture showing a foreground screen group and a foreground pid belonging to
*different* sessions are in `infoseg.md` ("How `DosQuerySysInfo` is answered" and
"Measured on a live Warp 4.5 system"); they are not repeated here.

#### `DosSetFgnd` (`#101`) is a scope dispatcher, and only two of its scopes touch these

`DosSetFgnd(scope, value)` - two words, scope pushed first. `w_SetFgnd` reads
`DX` = scope, `AX` = value, and dispatches:

| scope | reaches | effect |
|---|---|---|
| **0** | `_schSetKbdLocus(pid)` | `SIS_FgndPID`, `_SISData+0x1c`, `_tkFgndPID`, and `LIS_Fgnd` for both the outgoing and incoming process |
| **2** | `_schMapPid` -> `_TKTidTo_iSlot` -> on success `_schWindowBoost` | a **thread**, not a session - PM's window boost |
| **3** | `_schSetScreenGroupFgnd(sgid)` | `_FgndSGID`, plus the un-boost/boost sweeps |
| **8, 9** | `_schWindowBoost(value, scope)` | window boost |
| **0xA** | reads a word out of a PTDA-relative structure | a query, writes nothing - **that structure is now identified and the word is the caller's own thread slot number; see the subsection below** |
| anything else | - | `308 ERROR_INVALID_SCOPE` |

`_schSetScreenGroupFgnd`'s own body - the no-op case, the order of its two
sweeps around the store, and the `369` that stores anyway - is in the correction
block above this section.

**`_schSetKbdLocus` writes the two InfoSegs through two different aliases**, which
a decompile flattens into one: the `SIS_FgndPID` store goes through the *Global*
InfoSeg alias, and the `LIS_Fgnd` stores go through the *Local* one. It finds the
outgoing process by **atomically exchanging** the new pid into `_SISData+0x1c`
and reading back what was there - so the kernel-data copy of `SIS_FgndPID` is
the authoritative "who was foreground", not a mirror.

##### What each scope means, and what the caller observes

**The ordinal is undocumented; most of what it does is not.** `[DOC-IBM]`
`bseord.h`'s `DOSCALLS` block runs `...97, 98, 99` and then jumps to `104` -
ordinals 100-103 are omitted, and no IBM header, reference book or published
API page names `DosSetFgnd` at all. But the **operations** it performs are
documented under other names: scope 0's under `KbdSetFgnd`, and scopes 2/8/9's
as the scheduler's **window boost** (`CLASSMOD_WINDOW`) - see
`process-thread.md`, *"Dynamic priority variation - the six boosts"*, which is
the reference for everything about what a boost is, how much it is worth, and
that it does not decay.

**The carry flag is computed from `AX`, once, for every scope** `[OBS-RE]`. The
shared epilogue is `cmp ax,1` / `cmc` / `ret`, so **CF is clear exactly when
`AX == 0`**. That is the ordinary convention for a success/error code - but this
call has one scope that returns a *value*, and the epilogue does not know the
difference (see scope 10).

| scope | value is | on success | on failure |
|---|---|---|---|
| **0** | a **process id**; `0` is mapped to the caller's own pid, not rejected | `0` | `303 ERROR_INVALID_PROCID` - the pid resolves to no process control block |
| **2** | a **thread ordinal (TID) in the calling process** | `0` | **indeterminate** - see below |
| **3** | a **screen group id** | `0` | `369 ERROR_SMG_INVALID_SGID` - but the foreground group is moved anyway; the failure is not atomic |
| **8** / **9** | a **thread slot number** | `0` | **none - this scope cannot fail** |
| **10** | - (query) | the caller's own **thread slot number** | - |
| other | - | - | `308 ERROR_INVALID_SCOPE` |

**Scopes 8 and 9 have no failure return at all** `[OBS-RE]`. The worker returns
`0` on every path, including every refusal: a slot beyond the end of the
thread-slot table, a slot whose entry is null, a thread latched by scope 2, and
a system configured `PRIORITY=ABSOLUTE`. An implementation that answers an error
from these scopes is refusing where the system does not.

**Scope 2 is scopes 8/9 with a TID->slot lookup in front**, and the boost it
applies is the same one `[OBS-RE]`. It additionally sets a **per-thread latch**:
once a process has named one of its own threads with scope 2, that thread
**permanently ignores scopes 8 and 9**, the latch being cleared only when the
control block is re-initialised at thread creation. The sibling latch bit on the
same byte plays the same role for `DosSetPriority`, so this is a general
"the owner has taken this axis" convention rather than a quirk of this call.

**Scope 2's failure value is indeterminate, and that is the contract**
`[OBS-RE]`. The TID->slot helper genuinely computes `309 ERROR_INVALID_THREADID`
on failure, but the dispatcher discards it: the instruction that loads the
resolved slot into the return register is hoisted **above** the success branch,
so the failure path returns that same stack local - which the helper does not
write when it fails and the dispatcher never initialises. `309` is an internal
code **no caller ever sees**, and a caller testing CF will usually see an error
carrying a meaningless number.

**Scope 2 maps a zero value with the *process*-id mapper, not the thread one**
`[OBS-RE]`. The kernel ships both; this arm calls the pid one. A non-zero value
is passed through unchanged by either, so the difference is observable on
exactly one input: `scope 2, value 0` substitutes the **calling process's id**
and then uses that number as a **thread ordinal**. It does *not* mean "the
current thread".

**Scope 10 answers the caller's own thread slot number** `[OBS-RE]` - it reads
the per-process "current thread control block" pointer and returns the field IBM
documents as *"Thread slot number"*, at offset `+2`, distinct from the *"Ordinal
number of thread in PTDA"* (the TID) at `+0`. That completes the family: **scope
10 tells a caller its slot, scopes 8 and 9 boost and un-boost by slot, and scope
2 reaches the same boost through a TID.** It is not a session, screen-group or
process value.

> **And scope 10 returns with CF SET for every thread but slot 0**, because the
> epilogue above computes carry from `AX` and cannot tell a returned *value*
> from a returned *error code*. A caller that branches on carry will read every
> successful query as a failure. This is the system's own behaviour, not a
> defect in the caller.

**Scope 0 moves a different boost from scopes 2/8/9** `[DOC-IBM]` + `[OBS-RE]`.
`KbdSetFgnd`, the documented public call that performs this operation, is
specified as: *"This call raises the priority of the foreground keyboard's
thread ... KbdSetFgnd marks the current process that owns the keyboard. Threads in
this process receive a priority boost. The previous foreground keyboard threads
lose their priority boost."* The kernel does exactly that - it walks every
thread of the outgoing process and every thread of the incoming one, moving
`CLASSMOD_KEYBOARD` (`0x04`) - which is a **different modifier bit** from the
window boost (`0x40`). **The two scopes act on independent axes and do not
interact.** `KbdSetFgnd` also carries IBM's scoping rule for the operation:
*"This function should only be issued by a Keyboard Subsystem during KbdCharIn
or KbdStringIn processing."*

> `KbdSetFgnd` is declared `USHORT KbdSetFgnd(VOID)` and documents
> `447 ERROR_KBD_KEYBOARD_BUSY` and `504 ERROR_KBD_EXTENDED_SG`. Those are the
> **wrapper's own** codes, from its session check one layer up; the scope-0
> operation beneath it answers `303` instead. Do not carry them downward.


#### The switch sequence, in order

A hotkey, a Window List selection and `DosSelectSession` all converge on the same
chain. `DosSelectSession`'s serve-side handler `APPSELECTSESSION` calls
`DosSMGSwitch`'s caller directly, exactly as the hotkey path does.

1. **`DOSSMSWITCH`** takes the session-mutation lock and the pop-up block
   semaphore, resolves the target `SGCB`, refuses with `450` if the target's
   `SGCB+0x24` is non-zero, tells PM through `WinSetExtIDFocus` when PM is
   present, and calls -
2. **`DOSSMSGSWITCH`**, which compares the target against **`TopMost`**'s own
   screen-group id to detect a no-op, records the caller's argument in
   `IncomingDebugger`, and calls -
3. **`DOSSMGSWITCH`**, the orchestrator. **Its first act is to READ
   `SIS_CurScrnGrp`** - through the Global-InfoSeg selector the session manager
   cached at init - **and use it to resolve the OUTGOING session's `SGCB`.**
   This is the step that makes the publish load-bearing: *a switch that does not
   publish leaves the NEXT switch resolving the wrong outgoing session.*
4. It resolves the incoming `SGCB`, and replaces its own target argument with
   that `SGCB`'s `+0x0a` packed id.
5. `VIOSRFBLOCK`.
6. **`DosSMNotifyDD`** with a `{length 12, action 0x20}` record carrying
   incoming id, incoming type, outgoing id, outgoing type.
7. **`DOSSGSWITCHBACKGROUND`** on the outgoing session (`DOSSGSAVE`, unless
   `SGCB+0x14` bit 2 suppresses it), then **`DOSSGSWITCHFOREGROUND`** on the
   incoming one, which is where the publish happens:
   - `DosSMNotifyDD` `{length 8, action 0x02}` - post-session save;
   - **`DOSSGDDNOTIFY`**, and this is the whole of it: `DOSSGDDNOTIFY` calls
     **`DosSGSwitch` (`#54`)**, passing the incoming screen group in the argument
     `#54` loads into `BX`, whose low byte `#54` stores into **both** copies of
     `SIS_CurScrnGrp`. On return, and only when the incoming session is not a
     DOS session, `DOSSGDDNOTIFY` calls **`KbdSwitchFgnd`**, which reads ~~the
     incoming session's~~ registered keyboard-focus process out of `SGCB+0x88` and
     issues **`DosSetFgnd` scope 0** on it - moving `SIS_FgndPID`, `_tkFgndPID`
     and both processes' `LIS_Fgnd`;
     **Corrected 2026-10-12 `[OBS-RE]`:** the `SGCB` it reads is not the
     incoming session's. `KbdSwitchFgnd` ignores its argument and reads the
     block named by the *calling process's* own instance cell (`DOSCALL1`
     obj8 `+0x152`, `.sym` name `SGCB`), which `VioShellInit` sets to the
     shell's own session block; nothing on the switch path changes it. So a
     switch hands the locus to the last process that read the keyboard in the
     **shell's** session, or moves nothing when that field is 0; the incoming
     session's program regains it at its next `KbdCharIn`/`KbdStringIn`/
     `KbdGetFocus`. See "The keyboard locus on a select" below;
   - `DosSGSwitchProc2` on the pop-up process, on the pop-up flavour of the
     switch only;
   - `DOSSGRESTORE` on the incoming session, unless `SGCB+0x14` bit 0 suppresses
     it;
   - **`TopMost` := the incoming `SGCB`, `BottomMost` := the outgoing one**;
   - `DosSMNotifyDD` `{length 8, action 0x04}` - post-session restore;
   - clear `SGCB+0x14` bit 0.
8. Back in `DOSSMGSWITCH`: **`DosSetFgnd` scope 3 on the incoming screen group**,
   which is the `_FgndSGID` write and the priority propagation. **So
   `SIS_CurScrnGrp` is published BEFORE `_FgndSGID`, by two different calls, on
   one path.**
9. `VIOSRFUNBLOCK`.

**`DOSSGDDNOTIFY` has exactly four callers** - `DOSSGSWITCHFOREGROUND`,
`DOSSGSWITCHPOPUP`, `DOSSMSTARTSWITCH` and `DOSSMSGINIT` - and **`#54` has
exactly one caller in the whole of `DOSCALL1.DLL`: `DOSSGDDNOTIFY`.** So every
runtime publish of `SIS_CurScrnGrp` passes through that one routine.
`DOSSGSWITCHBACKGROUND` does **not** call it: saving the outgoing session
publishes nothing.

**`DOSSGDDNOTIFY` does not always publish.** When its flags argument is `0xFFFF`
it skips `#54` entirely and instead sets bit 15 of the session's screen-save
record - the same bit `DOSSGSAVE` sets to mean "saved". `DOSSMSTARTSWITCH` uses
exactly that form, so **the session-start notify marks a session saved and
publishes nothing.**

> **`[OBS]` 2026-10-12 - DISAGREES with steps 4 and 8 as read, not settled.**
> Steps 4 and 8 together say the scope-3 call receives the incoming `SGCB`'s
> packed id, `(type << 8) | sgid`. Measured on Warp 4.50 under a registered
> non-PM shell, after `DosSelectSession` moved `SIS_CurScrnGrp` to group 6, a
> full-screen session: `QSV_FOREGROUND_FS_SESSION` read **6**, not 0x106. A
> full-screen session started in the foreground the same boot read **0x104**
> (session 4), so a packed value does reach `_FgndSGID` after a start
> (`[INF]`: from one of `DOSSMSGSTART`'s own scope-3 calls, "The other paths"
> below) but not after this select. Also after the select: the selected program's `LIS_Fgnd` read **0000**
> and `SIS_FgndPID` was not its pid, though it had read FFFF before; `[INF]`
> consistent with `KbdSwitchFgnd` issuing scope 0 for a session whose
> keyboard-focus field `SGCB+0x88` is 0 (the program had made no keyboard
> call), which scope 0 maps to the caller's own pid - not established. What
> would settle both: the argument `_schSetScreenGroupFgnd` and
> `_schSetKbdLocus` receive during one `DosSelectSession`, under the kernel
> debugger, or `DOSSMGSWITCH`'s `DX` between steps 4 and 8 re-read.
>
> **SETTLED for `_FgndSGID` from the bytes, 2026-10-12 `[OBS-RE]`:** `DX` was
> re-read. `DOSSGSWITCHFOREGROUND` (`DOSCALL1.DLL` obj3+0x52c2) clears `DH`
> (`xor dh,dh`, obj3+0x52ca) and masks `DX` (`and dx,0x3fff`, obj3+0x5387) and
> does not restore it before its `ret`, so step 8's scope-3 call receives the
> **plain** screen-group id after a switch - 6, as measured. The packed 0x104
> after a start comes from `DOSSMSGSTART`'s own scope-3 call, which passes
> `TopMost`'s packed word itself. The `LIS_Fgnd`/`SIS_FgndPID` half is not
> settled by this.
>
> **The `LIS_Fgnd`/`SIS_FgndPID` half, 2026-10-12 `[OBS-RE]`: narrowed, still
> not settled.** See "The keyboard locus on a select" below.
> **Settled the same day `[OBS]` + `[OBS-RE]`:** the locus goes to the shell's own
> pid; see the last item of "The keyboard locus on a select".

#### The keyboard locus on a select `[OBS-RE]` + `[OBS]`

Read from the bytes of `DOSCALL1.DLL` (Warp 4.50) and `os2krnl` (SMP):

- **Only `DosSetFgnd` scope 0 moves the keyboard locus.** `_schSetKbdLocus` has
  one caller, `w_SetFgnd`'s scope-0 arm; the process's locus byte and its
  `LIS_Fgnd` copy in the PTDA are written by `_schSetKbdLocus` and by the
  PTDA's construction, and by nothing else.
- **`DOSCALL1` issues scope 0 in four places:** `DOSSMSGSTART` step 13 (the new
  session's lead) and step 14 (`TopMost`'s pid, when `TopMost` is not group 1),
  `KbdSetFgnd`, and `KbdSwitchFgnd`. Its other seven `DosSetFgnd` calls are
  scope 3. No other module a non-PM system loads imports `DosSetFgnd`.
- **So on a select, the locus can move only through `KbdSwitchFgnd`**, and that
  reads the session manager's *own* session block (above): the switch gives
  the locus to the last keyboard reader in the shell's session, or leaves it
  where it was.
- ~~**Measured `[OBS]`, and not explained by that reading:** under a registered
  non-PM shell whose processes never call the keyboard, a program started in
  the background read `LIS_Fgnd` FFFF and `SIS_FgndPID` = itself; after
  `DosSelectSession` brought its session forward it read `LIS_Fgnd` **0000** and
  `SIS_FgndPID` not itself, and a child it then started read
  `QSV_FOREGROUND_PROCESS` = neither that child nor the program. Eight boots
  gave the same answer. By the reading above the shell's block's `+0x88` must
  have held some other process's pid. **Which process, and so where the locus
  went, is not established.** One capture printing `QSV_FOREGROUND_PROCESS`'s
  value beside the shell's and the hard-error daemon's pids after the select
  would settle it, as would a kernel-debugger breakpoint on `_schSetKbdLocus`
  during one `DosSelectSession`.~~ (superseded 2026-10-12, below: the premise "whose processes never call the
  keyboard" was wrong - the session manager's own initialisation calls it.)
- **Where the locus goes on a select: to the session manager (the shell) itself.** `[OBS]` + `[OBS-RE]`, 2026-10-12.
  Measured on Warp 4.50 under a registered non-PM shell (pid 19) whose own code makes no keyboard call: after
  `DosSelectSession` brought a background-started full-screen session forward, the selected program (pid 40)
  read `SIS_FgndPID` = **19**, and a child it then started (pid 41) read `QSV_FOREGROUND_PROCESS` = **19**;
  `DosGetPPID(19)` = 1. The hard-error daemon was not the holder: the shell's only children existing just after
  `DosSMInitialize` returned were pids 23 and 26. The path, read from the bytes of `DOSCALL1.DLL`:
  `DOSSMSGINIT`, which runs in the shell's process, calls **`KbdCharIn(&CharData, IO_NOWAIT, 0)`** (obj3+0x9DC5..
  0x9DCF, a far call to `KBDCHARIN`, right after its closing `DOSSGDDNOTIFY(0, 0x80008001)`; its rc is not
  tested) - after `DosSGSwitchMe(1)` has put the shell in group 1 and after `VIOSHELLINIT` has pointed the
  shell's per-process session-block cell at group 1's block. `KbdCharIn` runs `GetCharIn`, whose first call is
  `KbdSetFgnd`: the shell's group (1) is `SIS_CurScrnGrp` (1, also measured just after `DosSMInitialize`), so
  it issues `DosSetFgnd(0, <shell pid>)` and stores the shell's pid in group 1's `SGCB+0x88`. That is the only
  `KBDCHARIN` call in `DOSCALL1`'s session-manager object. Every later switch runs `KbdSwitchFgnd` in the
  shell's process, which reads that same block and issues `DosSetFgnd(0, <shell pid>)`: the shell takes the
  locus, the selected program's `LIS_Fgnd` drops to 0000, and it regains the locus only at its own next
  keyboard read.

#### The other paths

- **A pop-up.** `DOSSGSWITCHPOPUP` runs the same two writes in the **opposite
  order**: `DosSetFgnd` scope 3 first, then `DosSGSwitchProc2` on the pop-up
  process, then `DOSSGDDNOTIFY` -> `#54`. It never calls scope 0 itself; the
  keyboard follows through `DOSSGDDNOTIFY`'s own `KbdSwitchFgnd` call.
- **`DosStartSession`.** `DOSSMSGSTART` assigns the new process with
  `DosSGSwitchProc2`, and reaches `DOSSMGSWITCH` directly or through
  `DOSSMSTARTSWITCH`. `[DOC-IBM]` constrains the outcome: *"New sessions may only
  be started in the foreground when the caller's session (or one of the caller's
  descendant sessions) is currently executing in the foreground"*, and otherwise
  *"DosStartSession will override the foreground request and start the new
  session in the background."*

  > **CONTESTED, 2026-09-20 - recorded rather than decided.** The read that
  > produced this section also had `DOSSMSGSTART` itself issuing `DosSetFgnd`
  > **scope 3 then scope 0**, twice - once on the new session and once restoring
  > the previous foreground from `TopMost` (or from `WinQueryExtIDFocus` when
  > `TopMost` is screen group 1 and PM is present) - *before* it reaches
  > `DOSSMGSWITCH`. An earlier read of the same routine, 2026-09-05, disagrees: it
  > prints `DOSSMSGSTART`'s raw
  > disassembly in program order, shows the switch called early at `1C032B8C`,
  > shows **no** `DosSetFgnd` inside the routine at all, and places the scope-3
  > call afterwards in PM (`WinInitSwEntry` -> `WININITSWENTRY` -> `SETFGND`),
  > saying in as many words *"IBM does NOT use DosSetFgnd here"*. **The earlier
  > note carries a listing and this one does not, so the claim is not asserted
  > here.** What would settle it: one disassembly of `DOSSMSGSTART` with every
  > `#101` import fixup in its span resolved. Until then, treat the
  > twice-moved-foreground reading as unestablished.

  > **SETTLED 2026-09-30 `[OBS-RE]` (Warp 4.5 UNI `DOSCALL1.DLL`), by exactly the read named above:**
  > every import fixup in `DOSSMSGSTART`'s span resolved. There are **four** `DOSCALLS.#101` calls, at
  > obj3+`0x2F50`, `0x2F5B`, `0x2FB8`, `0x2FC0`: `DosSetFgnd(3, new sgid)`, `DosSetFgnd(0, new pid)`, then
  > the same pair for the restored foreground (TopMost's group and pid, or `WinQueryExtIDFocus`'s group
  > when TopMost is screen group 1 and PM is present). **Both earlier readings were partly wrong:** the
  > calls exist (against "no `DosSetFgnd` inside the routine"), but they run **after** `DOSSMSTARTSWITCH`
  > (`call 0x3117` at `0x2B8C`) and after the exec, the screen-group assignment and the thaw described
  > in "Session start: exec, adoption, thaw" below - not before the switch.

- **Session start: exec, adoption, thaw** `[OBS-RE]` (same build). `DosStartSession` copies
  `STARTDATA.TraceOpt` into the request as the `DosExecPgm` ExecFlags - 0 -> **5 `EXEC_LOAD`**, 1 -> 3
  `EXEC_TRACE`, 2 -> 2 (then 6 `EXEC_ASYNCRESULTDB`) - and `InheritOpt` into the word `DOSSMSGSTART`
  tests to decide who execs. `EXEC_LOAD` is IBM's *"loaded into storage and made ready to execute, but
  ... not executed until the session manager dispatches the threads belonging to the process"*
  `[DOC-IBM]`. After the exec, `DOSSMSGSTART`: stores the child pid in the SGCB; on success
  `DosSetPrty(PRTYS_PROCESSTREE, PRTYC_REGULAR, 0, pid)`; **when the requester did the exec
  (`InheritOpt` 1), `DosSystemService(0, {4, pid}, NULL)`, which re-parents the child to the shell**
  (kernel `_TKAdoptTask`); `DosSGSwitchProc2` for every type but 4/7; **unless the exec was
  `EXEC_TRACE`, `DosSystemService(0, {1, 3, sgid}, NULL)`, which thaws every process of the new screen
  group** (kernel `Sys_FreezeThaw` -> `_TKScanTasks` with `_tkSysFrzThwWrkr`); clears `StartRamSem`; then
  the four `DosSetFgnd` calls above. Before a shell-side exec it also offers the request to a
  `\QUEUES\SESMGR\SECURITY` queue owner and waits for its answer, when that queue exists.
  *(Refined 2026-09-30, `[OBS-RE]`, by reading the whole block: there is no "answer".)*
  - **The request.** The shell gives the queue owner a 0x51C-byte segment holding the requester's pid
    and tid, a flag (1, or 0 for a DOS session), a RAM semaphore it has set, two zero dwords, the
    program name, and a second string. It writes this with the request word = its own LINFOSEG
    `tidCurrent`, then blocks in `DosSemWait(sem, -1)` until the owner clears the semaphore.
  - **Nothing is read back.** If the wait fails, or any step before it fails, the start returns
    **5 `ERROR_ACCESS_DENIED`** without exec'ing. A missing queue skips the whole hold.
  - **So the owner can only hold or release the start.** It cannot pass a result back.
  - **No module of the Warp 4.5 file set examined (every LX object unpacked) contains the queue name except `DOSCALL1.DLL`, the opener**, so on that install nothing owns it.
- **A background request** `[OBS-RE]` (Warp 4.5 UNI `DOSCALL1.DLL`). When `STARTDATA.FgBg` is 1,
  `APPSTARTSESSION` skips the foreground decision altogether: it calls neither `FOREGROUNDFAMILY` nor the
  zero-timeout `PopUpBlockSem` request (obj3 `0x3B00`-`0x3B05` jumps past both), so the start never holds that
  semaphore and **answers 0, not 457**. 457 `ERROR_SMG_START_IN_BACKGROUND` is the answer only to a *foreground*
  request that was refused (`0x3B36`, `0x3B4C`). A background start still runs `DOSSMSTARTSWITCH`'s background arm -
  `DOSSGDDNOTIFY(sg, 0xFFFF, 0)` and `VIORESTORE(sg, 4)` for types 0-2 - and, after the exec, the `DosSetFgnd` pairs
  above. The session word `DOSSMSGSTART` passes as `sg` there is the new screen-group id in its low byte; its high
  byte is the high byte of the requesting session's debugger link (SGCB `+0x2C`), 0 for an untraced start
  (`0x2A9D`-`0x2AA0`). The shell's own `DosExecPgm` receives as its argument string a buffer in `DOSCALL1`'s shared
  data holding the program name, a NUL and the program inputs (`DOSSMCOPYNAMES`, `0x30C4`), and the request's
  environment, which is null - the shell's own is inherited - when the requester gave none.
- **Boot.** `DOSSMSGINIT` obtains the InfoSeg selectors, caches `SIS_MaxScrnGrp`,
  and calls **`DosSGSwitchMe` with screen group 1 and a zero second argument** -
  which sets the session manager's own `LIS_CurScrnGrp` *and*, because that
  argument is zero, publishes `SIS_CurScrnGrp = 1`, the Shell Screen Group. It
  later starts `HARDERR.EXE`, assigns it to **screen group 0** with
  `DosSGSwitchProc2`, and issues `DOSSGDDNOTIFY` ~~with a screen group of 0, whose
  `#54` call would publish 0. *(Whether that last publish is reached was not
  settled: `DOSSGDDNOTIFY` gates it on its screen-save-record lookup succeeding,
  and that lookup creates the record when absent, so on the face of it it is
  reached - but the failure modes of the allocation inside it were not read.)*~~
  **CORRECTED 2026-10-12 `[OBS-RE]`:** the call is `DOSSGDDNOTIFY(0x8000, 0x8001, 0)`,
  and its `#54` call publishes **1**, not 0 - the arguments were earlier read with
  the pushed dword's two words in the wrong order. It is reached only after
  `DOSSSINIT` succeeded, and when it is not reached the 1 that `DosSGSwitchMe`
  published stands, so **a boot ends with `SIS_CurScrnGrp` = 1 either way**. The
  `DosSGSwitchProc2` call runs only when HARDERR's exec succeeded, and the exec's
  failure is tolerated. Full order: "What registration runs" above (unpublished notes).
- **Teardown.** See the next subsection.

#### Who notices that a session ended `[OBS-RE]`

`DOSSMSGINIT` starts four session-manager threads in the shell from a table in `DOSCALL1`'s shared
data; the first, **`DOSSMCHILDWAIT`**, loops on **`DosCWait`**. When a child of the shell ends it looks
up that pid's SGCB, then asks `DosCWait(DCWA_PROCESSTREE, DCWW_NOWAIT, ..., lead pid)`: if descendants
remain (anything but 128 `ERROR_WAIT_NO_CHILDREN`) it starts another `DOSSMCHILDWAIT` thread on that
tree; only when the lead's **whole process tree** has ended does it call **`DOSSMCHILDEXIT`**. That is
why every session's lead must be the shell's child - the re-parenting in "Session start" above.

> **The secondary thread's stack and the constructor's wait do not line up** `[OBS-RE]`, 2026-10-12.
> A secondary `DOSSMCHILDWAIT` gets a 4 KB stack (the thread table's first record; nothing rewrites
> its size) and its far pointer is stored in the session registry slot's second dword. The thread's
> own semaphore - set when it starts, cleared just before it exits - sits **8 bytes below the top of
> that stack** (`+0xFF6` from the block; `+0xFFA` if the kernel's 16-bit `DosCreateThread` puts
> nothing on the new stack, which is `[INF]` either way). When a later session reuses that slot,
> the constructor clears the slot's second dword, waits on **`+0x3F6`** of the old block and frees
> it. `0x3F6` is where that semaphore would be for a **1 KB** stack, the size of the session
> manager's fourth thread. So the wait is on a word inside the dead thread's stack, not on the
> semaphore it cleared; `[INF]` it returns at once if that word is 0, and what it holds at run time
> is not observed.
`DOSSMCHILDEXIT` then, in order: `DOSSMAPPNOTIFY` (the `STARTDATA.TermQ` write and the parent
notification), PM's `WinEndSession` when PM is present, the device-driver termination notification
(`DEV_SYSTEMNOTIFYPDD` Action 8, below), `VIOFREE` (session kinds 2/3) or `DOSSGFREE` (kind 1, which
itself calls `VIOFREE`) ~~or the VDM slot (4/7)~~, and last `DOSSMDELSGCB`. **Corrected 2026-10-12
`[OBS-RE]`:** for kinds 4/7 the dispatch calls through obj5+0xbbc, which is **`WinDestroyConsole`**
(`PMVIOP` ordinal 2), filled only by a PM registration - so under a non-PM shell it calls nothing,
and kinds 4/7 get no `VIOFREE` or `DOSSGFREE` (unpublished notes).

**The `TermQ` write** `[OBS-RE]` (read 2026-10-11, unpublished notes). `DOSSMAPPNOTIFY` reaches `PARENTNOTIFY`, which writes only when the child was started related,
the parent's `SGCB+0x22` is 0, the start did not fail, and the parent has a queue. Its
`WRITETERMQUEUE` allocates an 8-byte giveable segment holding {child session id, result code, 0, 0},
gives it with `DosGiveSeg` to the pid in the parent's `SGCB+0x1e`, writes it with
`DosWriteQueue(SGCB+0x20, request, 8, ...)` - or through `DO32BITWRITEQ` when the parent's `SGCB+0x14`
bit 3 is set - and frees its own copy. So **the writer is the shell, after the lead's whole process
tree has ended, and a failed start writes no `TermQ` element.** When no related child remains,
`PARENTNOTIFY` closes the `TermQ` and clears `SGCB+0x1e`, so the session may start related children
again.

> **`[OBS]` 2026-10-12 - the element arrives for an ordinary parent, and not for the shell.**
> Warp 4.50, a registered non-PM shell: three programs in sessions of their own each got
> {session id, result 0, 0, 0}, 8 bytes, request 0, written by another process - the shape read
> above. **When the requester was the registered shell itself, no element arrived** for its first
> `TermQ`-naming start, whose program ran and ended, and **every later start by the shell naming a
> `TermQ` answered 461** (its own queue five times, a missing one twice, across runs), while starts
> naming none answered 0. `[INF]` under the 343 -> 461 rule a 461 here is the shell's `TermQ` open
> failing. Which of the conditions above fails for the shell's own session (`SGCB+0x22`, the
> `+0x1e` owner, the handle at `+0x20`), and why the open fails after the first start, are not
> established: the shell's `SGCB+0x1e`/`+0x20`/`+0x22` before and after its child ends, and the
> rc of `APPSTARTSESSION`'s `TermQ` open for the second start, read under the kernel debugger,
> would settle both.

**The shell's redraw and termination semaphores** `[OBS-RE]` (decompile read 2026-10-11, unpublished notes). `DOSSMINITIALIZE` stores the registering block's two RAM
semaphores at obj5 `ShellRedrawSem` (+0x456) and `ShellTermSem` (+0x45a). Only two routines clear
them, and each **pulses** - DOSCALL1's own `DOSSEMCLEAR` then `DOSSEMSET`:
- `DOSSMDOAPPREQ`, after an `APP*SESSION` arm, when the shell's own SGCB is `TopMost` and the arm
  returned 0 (or 2 with the request's `+0x24` set): `ShellRedrawSem`;
- `DOSSMAPPNOTIFY`, after `WRITETERMQUEUE` and `PARENTNOTIFY`, with its third argument 0:
  `ShellRedrawSem` when `TopMost` is screen group 1 (the shell on top), else `ShellTermSem` when
  `TopMost`'s group equals its second argument. Its callers are `DOSSMCHILDEXIT`, from the shell's
  `DOSSMCHILDWAIT`, and `DOSSMPOPUPTLECHG`.

The 2026-10-11 read left open in which process `DOSSMPOPUPTLECHG` runs; it is one of the four
threads `DOSSMSGINIT` creates in the shell ("What registration runs" above), so **both pulses run in
the registered shell's own process** `[INF]`, from the two reads together.

The device-driver notifications are IBM's `DEV_SYSTEMNOTIFYPDD`, Category 0Bh Function 41h `[DOC-IBM]`
(PDD reference): Action 16 *"Session creation"* with {Session ID, Session Type}, Action 8 *"Session
termination"* with {Session Type, Session ID}, *"Termination and creation notifications are given in
all cases."* `[OBS-RE]`: `DOSSMSGSTART` sends {8, 0x10, sgid, type} before `DOSSMSTARTSWITCH`, and
`DOSSMCHILDEXIT` sends {8, 8, type, sgid}; both go through `DOSSMNOTIFYDD`, which does nothing unless
`SMG_Flags` bit 1 is set, and issues `DosDevIOCtl2(..., 0x41, 0x0B, handle)` to each registered driver
whose registration mask has the action bit.

*(Added 2026-10-12, `[OBS-RE]`, unpublished notes)* `SMG_Flags` bit 1 is set by `DOSSMSGINIT` only when
`HardError_Do_NotifyDD` (obj5+0xb02) is 0. `DOSSMNOTIFYDD` recognises its internal callers by
**selector**: its length check (0x18, else 461) and type check (0x80 or 0x100, else 516) run only
when the packet's selector is not 0x9807, object 5's own; no size is involved. With `SMG_Flags`
bit 1 clear it returns 0x9807 itself (the `AX` it loaded), not a status. Each internal notice is
bracketed by the DD-notification semaphore at obj5+0xb04 - in `DOSSMINITIALIZE`, `DOSSMSGSTART`,
`DOSSMGSWITCH`, `DOSSGSWITCHFOREGROUND`/`BACKGROUND`/`POPUP`, `DOSSMCHILDEXIT` and
`DOSSMPOPUPTLECHG` (an offset census of the decompile).

#### What happens to the foreground when a session ends

`[DOC-IBM]`, `DosStartSession` Remarks, "Termination Considerations": *"When a
child session is executing in the foreground at the time it ends, the parent
session becomes the foreground session."* and *"When an independent session,
created specifying a value of 0 for Related, ends in the foreground, the Shell
selects the next foreground session."* `DosStopSession`'s Remarks repeat the
first sentence.

`[OBS-RE]` that is implemented, and it is worth knowing **which component does
it**, because three different ones each do part:

1. **`DOSSMCHILDEXIT`** calls **`DOSSMAPPNOTIFY`**, which calls
   **`PARENTSWITCH`**. `PARENTSWITCH` reads `TopMost`; when `TopMost` is the
   shell's screen group 1 and PM is present it asks **`WinQueryExtIDFocus`** who
   really has focus; it then walks the `SGCB+0x1c` parent chain to a live
   ancestor and either hands the foreground to PM via **`WinSetExtIDFocus`**, or,
   with no PM, calls **`DOSSMSGSWITCH`** on the parent - i.e. it re-enters the
   ordinary switch sequence above, and the publish happens there. **There is no
   separate teardown publish:** `DOSSMCHILDEXIT` contains zero calls to
   `DOSSGDDNOTIFY` and zero to `DOSSMGSWITCH`.
2. **`DOSSMDELSGCB`**, which runs afterwards, unlinks the dying `SGCB` - when
   either pointer named it, `BottomMost` is repointed to the backward link and
   `TopMost` to the **forward** link - and sets `SGCB+0x14` bit 2 on the new
   `TopMost`, suppressing the `DOSSGSAVE` that would otherwise try to save a
   session that was never on screen. It touches no InfoSeg field.
   **Made exact 2026-10-12 `[OBS-RE]`:** the bit-2 store sits inside the
   "the dying block was `TopMost`" arm, after `TopMost` is repointed. When the
   dying session was **not** `TopMost` - a background session, or a start that
   failed before its switch - `TopMost` and its flags word are left as they were.
3. **The kernel, at `f_ProcessTerminate`.** If the terminating process's own pid
   equals `_SISData+0x1c`, the kernel zeroes `SIS_FgndPID` in **both** copies.
   It does **not** choose a successor, and it does **not** touch
   `SIS_CurScrnGrp`. `_tkFgndPID` is not cleared there either, so `QSV`
   `FOREGROUND_PROCESS` still reports the dead pid - the full statement, and why
   it matters, is in `infoseg.md`, "`SIS_FgndPID` is zeroed on process
   termination; `_tkFgndPID` is not".

#### Who READS each quantity - and the two that are this subsystem's own

The reader census for the two Global-InfoSeg fields - `PostSigFocus`'s
`SigFocus` table index, `KSGKillProcess`'s below-4 exemption, `DOSSMGSWITCH`'s
own read (step 3 above) and `KbdSetFgnd`'s two gates - is in `infoseg.md`,
"`SIS_CurScrnGrp` and `SIS_FgndPID` - the READER census", along with the kernel
words' readers (`_VR32QuerySysInfo` for `QSV` 24 and 25, and the window boost).
It is not repeated here. The two readers that belong to the session manager
rather than to the info segments are:

| reader | reads | what it does with it |
|---|---|---|
| `KbdSwitchFgnd` | `SGCB+0x88` | reads back the focus pid `KbdSetFgnd` stored there and issues `DosSetFgnd` scope 0. Refuses with **`407 ERROR_KBD_SMG_ONLY`** unless the caller is the session manager. |
| `FOREGROUNDFAMILY`, `PARENTSWITCH` | `TopMost`, and `WinQueryExtIDFocus` when PM is present | decide whether the caller's session family holds the foreground; `451` when it does not. **Under PM they ask PM, not the InfoSeg.** |

**The consequence for this subsystem, in one sentence:** `SIS_CurScrnGrp` is a
dispatch key and not reportage, so a missed publish does not fail at the write -
it misroutes Ctrl-C, exempts the wrong screen groups from Ctrl-Break kill,
resolves the *next* switch's outgoing session wrongly, and leaves `KbdSetFgnd`
- which `[DOC-IBM]` declares as `KbdSetFgnd(VOID)`, so those two fields plus its
own per-session record are its entire input - unable to grant keyboard focus to
anyone.

**What PM itself uses.** `PMMERGE.DLL` imports `DosSetFgnd` at four call sites
and calls it with **scope 3** (twice, once with a literal screen group 1) and
**scope 2** (twice). It imports **none** of `DosSGSwitch`, `DosSGSwitchMe` or
`DosSGSwitchProc2`, and never uses scope 0. So PM moves the scheduler's
foreground and the window boost directly, and leaves the screen group and the
keyboard locus to the session manager.

#### The device-driver notification is IBM-documented, and the records match it byte for byte

`[DOC-IBM]` `DEV_SYSTEMNOTIFYPDD` - IOCtl category `0x0B`, function `0x41` - is
documented in the Physical Device Driver Reference with an `Action` bitmap: `1`
pre-session save, `2` post-session save, `4` post-session restore, `8` session
termination, `16` session creation, `32` start of session switch, `64` end of
session switch, `128`/`256` the alternate-input-method pair. A driver registers
for a combination of them with `DosSMRegisterDD`, and an `Action` it did not
register for draws `ERROR_INVALID_PARAMETER`. IBM also states the rule that
matters most here: *"Session-switching and saving/restoring notifications are
not given when switching between non-full-screen sessions (that is, between
Presentation Manager sessions and text-windowed sessions). Termination and
creation notifications are given in all cases."*

`[OBS-RE]` the records the session manager builds match that contract exactly:
`DOSSMGSWITCH` emits `{length 12, action 0x20}` with incoming id, incoming type,
outgoing id, outgoing type - IBM's documented length and payload for action 32 -
and `DOSSGSWITCHFOREGROUND` emits `{length 8, action 0x02}` and
`{length 8, action 0x04}`. *(Added 2026-09-30.)* `DOSSMGSWITCH` emits the same
twelve-byte record with **action `0x40`, "end of session switch", after the switch** and its
`DosSetFgnd(3, ...)`. Only a successful switch sends it. The order inside `DOSSMGSWITCH` is:
1. take `SwitchRamSem`;
2. resolve the outgoing session from `SIS_CurScrnGrp`, then the incoming one;
3. `VIOSRFBLOCK`;
4. action 32;
5. background save;
6. foreground restore;
7. `DosSetFgnd(3, target)` (the PM focus id when the target is screen group 1 and PM is present);
8. `VIOSRFUNBLOCK`;
9. action 64;
10. release the semaphore.

`DOSSGDDNOTIFY` returns the rc of its save-record lookup, not that of `DosSGSwitch` (`#54`). IBM's own shipped `KBDBASE.SYS` source implements the
receiving end at `SGController`, dispatching on the same bit values and naming
the same payload fields.

### The screen save/restore record: `DOSSGSAVE`, `DOSSGRESTORE`, `VIORESTORE` `[OBS-RE]`

**Established 2026-09-05 against the shipped Warp 4.5 / WSeB `DOSCALL1.DLL`
(2002 file set) paired with its uniprocessor `.SYM`.** Screen save and restore
are the session manager's own work and are **not** in the SGCB: they use a
separate, `sgid`-keyed structure that the SGCB holds no pointer to and that
holds no pointer to the SGCB.

**Both entry points are session-manager-only.** `DOSSGSAVE` (obj3+`0x563a`) and
`DOSSGRESTORE` (obj3+`0xb711`) open identically:

```
mov ax,0x9807 / mov ds,ax          ; DOSCALL1's instance segment
mov es,[0xbf8] / mov bx,[es:0x0]   ; LINFOSEG +0x0 - the current process id
cmp bx,[0xc16] / jz ok             ; against the registered session manager's
mov ax,0x1a9                       ; 425 ERROR_SCS_NOT_SESSION_MGR
```

`[DOC-IBM]` for the numbers, Control Program Guide and Reference error table:
*"419 ERROR_SCS_SG_NOTFOUND"* and *"425 ERROR_SCS_NOT_SESSION_MGR"*.

**The lookup is a two-level structure, and the level everyone reads first is the
INDEX.** `SSFINDSG` (obj3+`0x58b8`, 69 bytes) walks a table at `memory_pool` -
the `.SYM`'s own data-symbol name, obj5 `+0xdb9` - with an **18-byte stride**:

```
mov di,0xdb9                 ; memory_pool
mov dx,0xffff / mov cx,0xffff
loop:  cmp [di],dx           ; 0xffff marks the end of a table block
       cmp [di+0x3],bx       ; the SGID key
       cmp [di+0x5],cx       ; must be 0xffff - the in-use marker
       ...
       add di,byte +0x12     ; 18 bytes to the next entry
       ...
       cmp [di+0x2],cx / mov di,[di+0x2]   ; follow the chain to the next block
found: mov di,[di+0x7]       ; DI := the RECORD POINTER
miss:  mov ax,0x1a3          ; 419
```

**So the 18-byte entry is an index entry, and `+0x7` addresses the record.**
The record is **92 bytes** (`0x5c`): `SSCBSETUP` (obj3+`0xb8fc`) is a
`rep movsb` of `cx = [0xdb7]` bytes from `si = 0xd5b`, and the `.SYM` names
those two `sgcb_str_len` and `sgcb_str`; `sgcb_str_len` holds `0x5c` in the
shipped image, which is also exactly `0xdb9 - 0xd5b`. `SSCBSETUP` stamps the
caller's sgid into `sgcb_str+0` before the copy. Every `[di+NN]` displacement
in `DOSSGSAVE` and `DOSSGRESTORE` - `+0x4`, `+0x6`, `+0x8`, `+0xc`, `+0x12`,
`+0x16`, `+0x1a`, `+0x20`, `+0x26`, `+0x2f`, `+0x3b`, `+0x3f` - is an offset
into **that** 92-byte record. Two of them are initialised to `0xffff` by the
template (`+0x0c` and `+0x1a`), which are exactly the two `DOSSGSAVE` and
`DOSSGRESTORE` compare against `-1`.

**`DOSSGSAVE`'s shape**, in order: the 425 gate; `SSFINDSG`; on a **419 miss**
only, `SSMEMMAP` -> `SSCBSETUP` -> `SSSEMSETUP` to create the record; then

```
1C03567C  cmp word [di+0x26],byte +0x0
1C035680  jz  out
1C035682  push dword 0xa
1C035688  call <DosSleep>
1C03568D  jmp short 0x567c
```

- **a spin on the RECORD's `+0x26`, on `DI`, with no segment override.** It is
not `SGCB+0x26`, which is the bond-flags word two paragraphs of this document
up and which a parent with a live child never clears; nothing in `DOSSGSAVE`
loads an SGCB at all. The routine ends `or word [di+0x8],0x8000` - **bit 15 of
the record's `+0x8` means "saved"**.

**`DOSSGRESTORE`'s shape**: the same 425 gate and `SSFINDSG`; then, selected by
the record's `+0x6` (a pid), `+0xc` and `+0x1a` (both `0xffff` at creation),
either `call 0xe026:0x1050` - **`VIORESTORE`**, obj4+`0x1050`, passed the same
two arguments `DOSSGRESTORE` itself received - or one of two internal helpers
(obj3+`0xb626`, obj3+`0xb6af`); then `SSTHAWPIDS` (obj3+`0xbdc2`);
`and word [di+0x8],0x7fff` to clear bit 15, at five sites; and
`push dword [di+0x2f]` into a semaphore post - so the record carries a **32-bit
semaphore handle at `+0x2f`**.

**Who calls them.** `DOSSGSWITCHFOREGROUND` (obj3+`0x52c2`) calls
`DOSSGRESTORE` on the incoming session, gated out by that session's
`SGCB+0x14` bit 0; **`DOSSGSWITCHBACKGROUND` (obj3+`0x5474`)** calls
`DOSSGSAVE` on the outgoing one, gated out by `SGCB+0x14` bit 2, and skips the
call entirely when the outgoing session's `SGCB+0x10` (session type) is `4`.

**Both are called from `DOSSMGSWITCH` (obj3+`0x50c0`), in that order** -
`call 0x5474` at obj3+`0x51d8`, then `call 0x52c2` at obj3+`0x51e3` - so the
sequence is *save the outgoing, then restore the incoming*. `DOSSMGSWITCH`'s
own callers are `DOSSMSTARTSWITCH` (twice), ~~`POPALL`~~, `DOSSMSGSWITCH`,
`DOSSMHDEPOPUP` and ~~`DOSSMPAUSE` (twice)~~ **`DOSSMPOPUPTLECHG` (twice), plus
`DOSSMSGSTART` itself** - *corrected 2026-09-20 by resolving each call site's
containing symbol against the module's own symbol table rather than by reading
a decompile's nearest label; each struck name is the symbol that PRECEDES the
real one, which is what a nearest-symbol lookup returns when the routine's own
entry is not where the reader assumed.* `[OBS-RE]`; and `DOSSMSTARTSWITCH` is reached
from `DOSSMSGSTART` (obj3+`0x2a78`, `call 0x3117` at obj3+`0x2b8c`), which is
the **session-start** path. **So starting a session that takes the foreground
drives the same save-and-restore chain an explicit switch does** - it is not a
special case that skips it.

*(`DOSSGSWITCHBACKGROUND` is a named export. A linear disassembly loses its
label, because obj3+`0x5473` mis-decodes as a four-byte instruction covering
obj3+`0x5474`, and then attributes its code to the preceding symbol - see the
method note under the field table.)*

### What actually triggers a switch: the hotkey path

A Ctrl-Esc/Alt-Esc keypress is not a special side-channel - it is recognized during **completely
ordinary keyboard-message processing** (the standard character-message a window receives for any
keystroke), gated on the message's own documented modifier-key bits (a "this is a scan-code event"
flag, together with the Alt or Ctrl modifier flag). A classifier function reads a value out of the
user's own `OS2.INI` profile (under a semaphore-protected profile-read, i.e. the session-switch
hotkey is a **user-configurable Desktop setting**, not a hardcoded key combination) and, on a match,
invokes the same lower-level primitives the Window List itself uses to request and then wait for a
switch - the wait step also boosts the requesting thread's own priority while it waits. Both the
request and the wait step are implemented as ordinary 32-bit PM code that thunks down into the
16-bit `DOSCALL1.DLL` switch primitives above via the universal 32-to-16 thunk interpreter
documented in `thunking.md` (`THK32_UNITHUNK`) - the packed "descriptor" a caller loads into `EAX`
before invoking the interpreter is, in this case, literally the target's own 16:16 far address,
confirmed by watching the interpreter unpack it and transfer control there. Below the PM level,
the same Ctrl-Esc/Alt-Esc combination is independently detected a second time, at the keyboard
driver's own interrupt handler (every keystroke, not just the ones that reach a message queue) -
see `vio-kbd-mou.md`'s device-driver section for that half of the chain, and for the mouse
driver's own separate switch-notification mechanism.

### Where the hotkey thread sleeps: `DosSystemService` and the kernel's SM event queue

The consumer side - the dedicated Session-Manager thread that turns queued hotkey events into
switch requests - blocks in the kernel via **`DosSystemService` (DOSCALLS ordinal 88)**, a small
multiplexed system-service gate. Decoded from the kernel binary (dispatcher, per-service handlers,
and the dispatch table read at its exact coded location; the caller's exact call site
independently confirmed by resolving its import fixup to `DOSCALLS.88`):

- Signature (16-bit, 10 argument bytes, Pascal convention):
  `DosSystemService(USHORT service, PUSHORT psubfn, PUSHORT pout)`. In the kernel worker the
  service index arrives in `DI`; valid services are `0`-`6`, dispatched through a 7-entry table
  of `{owner-PID, handler}` pairs in kernel data.
- The service table (handler symbol names from the kernel's own debug symbols):
  `0=SysServSM` (Session Manager), `1=SysServHE` (hard error), `2=SysServPS`, `3=SysServVP`,
  `4=SysServVDM`, `5=SysServJIT`, `6=SysServJIT2`.
- **First-caller-claims ownership**: a service's table slot stores the PID of the first process
  ever to call it; any other process calling that service is refused. (The shell process
  naturally claims service 0 at boot.) **Refined 2026-10-12 `[OBS-RE]`** (unpublished notes): every caller of service 0 runs in the
  registering shell's process, and the first claims it - **`DOSSMSGINIT`'s HARDERR thaw**
  (subfunction 1, on thread 1, before the session-manager threads start) on a boot where HARDERR
  was loaded, otherwise **`DOSSMPAUDAEMON`'s first call** (subfunction 2, below). PM's
  `WAITFORHOTKEY` (subfunctions 0 and 5) and TShell's main loop (subfunction 0) run in the same
  process. The claim is released by `_SysServTerm`, which `_TKTermThread` calls in the dying
  process's exit sequence, after its other threads are gone and its DLL exit list has run; it
  clears every owner word equal to that pid.
- **`SysServSM` subfunction 0** (the subfunction word is fetched through `psubfn`) parks the
  caller on a kernel event queue - the block named **`SMHotKeyQ`** in the kernel symbols; the
  adjacent queue block is `SMDosSessionQ`, which the VDM service demonstrably waits on, a good
  cross-check of the naming. The wait returns when the producer half -
  `SysServQueueEvent`/`SysServWake`, reached from the keyboard driver's interrupt-level hotkey
  classification (`kbd` driver `HotKeyCheck`/`event_SMKey`, see `vio-kbd-mou.md`) - queues an
  event; the dequeued event ~~word is~~ **BLOCK is** returned through `pout`.

  > **CORRECTED 2026-09-06. `pout` addresses a TWO-WORD block, not one word, and
  > the singular is what a reimplementation gets wrong.** The prototype above
  > types it `PUSHORT`, which is right about the pointer and misleading about
  > what it points at. Read out of the Session-Manager thread's own consumer in
  > the PM merge module `[OBS-RE]`: it pushes `psubfn` and `pout` as two
  > separate frame slots 14 bytes apart, and after the call it reads **both**
  > `[pout+0]` and `[pout+2]`, neither of which it initialised beforehand - so
  > both are produced by the service.
  >
  > - **word 0 is an event CLASS.** The consumer dispatches it through a
  >   `dec ax`/`jnz` ladder accepting exactly **{1, 2, 3, 4, 6}** - 5 is skipped
  >   - and anything else sends it straight back to the wait. Class **1** is a
  >   session-manager hotkey; class **2** is Ctrl+Alt+Del, whose arm increments
  >   a flag the module's own debug symbols name `FCTRLALTDEL` and spawns the
  >   thread those symbols name `SHLCTRLALTDELPOPUP`.
  > - **word 1 is the `idHotKey`**, and it is read *only* on class 1. Its own
  >   sub-ladder tests 1, 2 and 3 and calls the module's `DOSWITCH` with 0, 2
  >   and 7 respectively, plus `CANCELSHUTDOWN`. So word 1 drives the switch and
  >   word 0 selects the class.
  >
  > **IBM states the class/argument shape independently** `[DOC-IBM]`
  > (`DevHelp_SendEvent(EventType, Parm)`, PDD reference): event **6** is
  > *"Session Manager hot key from the keyboard"* with the argument *"Hot Key
  > ID ... set through the use of the IOCtl 'Set Session Manager Hot Key'
  > (Function 56h)"*, and event **7** is *"Reboot key sequence from the
  > keyboard"*. The id is the ARGUMENT of a classified event, never the event.
  >
  > **But word 0 is NOT the `DevHelp_SendEvent` EventType, and assuming it is
  > will be wrong in both directions** `[OBS-RE]`. The kernel's SendEvent
  > handler remaps before queueing (its `case 1` stores at index 4 and its
  > `case 2` at index 1), and `SysServWaitQ` special-cases dequeued entries
  > whose first word is 4 or 6 on this queue specifically. Three numberings are
  > in play: the DevHlp EventType, the queue entry, and the consumer's class
  > ladder - in which 2 means Ctrl+Alt+Del where the DevHlp 2 means Ctrl+C and
  > the DevHlp 7 is the reboot sequence. What the producer deposits in word 0
  > is recoverable from `SysServQueueEvent` and `SysServSM` and is **not
  > established here**.
- Consequence worth stating plainly: on a boot where no hotkey is ever pressed, this call
  **blocks indefinitely** - a debugger watching the kernel-side entry point during an ordinary
  desktop boot will never see it complete, which is easy to misread as "never used."
- **On a boot without PM, the base system neither fills the hot-key table nor waits on `SMHotKeyQ`** `[OBS-RE]` (added 2026-10-13). The keyboard driver's session-manager hot-key table ships empty and is programmed only through category 4 function 56h ("Set Session Manager Hot Key"); a scan of every module under `C:\OS2` of a Warp 4.50 install for the issuing idiom finds it only in the PM merge module (its three registrations: Ctrl+Esc id 1, Alt+Esc id 2, Alt+Home id 3) - not in `DOSCALL1.DLL`, whose own category-4 requests use the same idiom and are found. And none of `DOSCALL1`'s own `DosSystemService` calls is subfunction 0: they are subfunction 4 and 1 in `DOSSMSGSTART`, 1 in `DOSSMSGINIT`'s hard-error thaw, `DOSSCRLOCK` and `SSTHAWPIDS`, and 2 in `DOSSMPAUDAEMON`, plus a thunk that carries an application's own request. So under a text-mode `PROTSHELL` a keyboard hot key switches sessions only if that program both registers the keys with function 56h (becoming the driver's `SwitchPID`, the only process allowed to change entries) and runs a thread blocked in `DosSystemService(0, {0}, pout)` that acts on class 1 - the IBM sample text shell TShell does both, registering Ctrl+Esc as id 1 and Alt+Esc as id 2 and handling either the same way (a session-manager switch call, then a repaint of its own list). The ids, and what each one does, are the shell's: the kernel only carries the id. A shell that does neither has no session-manager hot keys; the keys reach the foreground session as ordinary keystrokes.
- **Measured end to end** `[OBS]` 2026-10-13 (Warp 4.50, four boots). The shell is a text-mode `PROTSHELL` that registers with the session manager, issues function 56h for Alt+Esc only (`{0x0A00, 0x01, 0x81, id 2}`, rc 0), and waits on `DosSystemService(0, {0}, pout)` on its main thread. Two full-screen children each block in `KbdCharIn`.
  - Every Alt+Esc returned class 1, id 2: with Alt released first, and with Esc released first.
  - Ctrl+Esc, which nothing had registered, reached the foreground child as an ordinary key (`chChar` 1Bh, `chScan` 01h, `fbStatus` 40h, `fsState` 0104h) and switched nothing.
  - After the shell's switch, the incoming child's first key saw `SIS_FgndPID` = the shell, and its second key saw itself.
  - A letter sent in the same burst as the hot key was read by the new foreground child. The injector paced the bytes about 11 ms apart, so the letter arrived about 44 ms after the hot key's break, after the shell had switched. This is a timing observation, not a contract.
  - The first Ctrl+Alt+Del returned class 2 to the waiter, which ignored it. The second reset the machine, and the line the waiter had written after the first press was on disk afterwards. That the reset path flushes the file systems first is read from the kernel's bytes; this capture does not show it.
- **`SysServSM` subfunction 2 is the Ctrl+NumLock channel, and its consumer is DOSCALL1's own
  `DOSSMPAUDAEMON` thread - a second caller of service 0 in the shell** `[OBS-RE]` (added
  2026-10-12; unpublished notes, the kernel half from
  the corpus's annotation of the SMP 14.104a `SysServSM`). The thread loops forever on
  `DosSystemService(0, &PauseActionPacket, &PauseResponsePacket)`, the action packet's word being 2.
  Subfunction 2 waits (`SysServWaitQ`) on the queue block **`CtrlNumLkQ`**, not `SMHotKeyQ`, so its
  copy-out is **one raw word**; it blocks interruptibly while the queue is empty, and an interrupted
  block answers 95. The only producer is the kernel's `DevHelp_SendEvent` handler for **event 3**,
  which queues `Parm` unchanged. `[DOC-IBM]` the PDD reference (`DevHelp_SendEvent`) names event 3
  *"Ctrl+NumLock: Foreground session number"*, while the DDK's `devhlp.inc` names it
  `event_CtrlScrLk` - so the word is the foreground session's screen group. The thread hands it to
  **`DOSSMPAUSE(sg)`**, ignoring the call's return code: group 1 (the shell's) is ignored; otherwise
  the SGCB is looked up under `SMQueueRamSem` and, when found, a toggle - `SGCB+0x47` 0 -> set the
  semaphore at `SGCB+0x48` and store 1; else store 0 and clear it. `DOSSMPAUSE` always returns 0.
- **Service 4, `SysServVDM`, is claimed by the shell's VDM server thread** on the first DOS-type
  `DosStartSession`; a failed wait there answers 1, not 95. See the next section.

### A DOS-type session start with no VDM: `DosCreateVDM` answers 641 `[OBS-RE]`

Read 2026-10-12 from the Warp 4.5 uniprocessor `DOSCALL1.DLL` with its `.SYM`, the SMP AStrict debug
kernel (the 32-bit `DosCreateVDM`) and the SMP 14.104a kernel (`DosSystemService`); recorded in unpublished notes. **Read, not measured: no capture of a DOS-type
`DosStartSession` exists.** The case: `SIS_ProtMdOnly` set, MVDM never initialised, a non-PM shell
registered, and a well-formed `DosStartSession` with `SessionType` 4 (`SSF_TYPE_VDM`), 7
(`SSF_TYPE_WINDOWEDVDM`) or 0xD-0x12 (the WIN-OS/2 `PROG_*` types of `pmshl.h`).

**What IBM documents** `[DOC-IBM]`: `PROTECTONLY=YES` *"Selects only OS/2 sessions; you cannot run
programs in DOS sessions"* (Command Reference). 641 `ERROR_VDM_DOWN` is defined in `bseerr.h`
(`MSG%none`, so no message text) and listed in the Control Program Reference's error list; no page
says when it is returned, and `DosStartSession`'s return list names neither 491 nor 641.
**`DosCreateVDM` has a name and an ordinal and nothing more**: the DDK's private 16-bit import
library `os2286p.lib` maps `DOSCREATEVDM` to `DOSCALLS` ordinal 213, and the *OS/2 Debugging
Handbook* Vol. IV lists `213 DOSCREATEVDM`; no header or book gives a prototype, parameters or
return codes.

**The path, in order:**
1. **The requester lets it through.** The validator's maximum is 30 (above), so the `SessionType`
   check is never reached. `DOSSTARTSESSION` maps 0xD-0x12 to 7, recording the subtype in request
   bits that only the PM `WinCreateConsole` arm reads, so under a non-PM shell a 0xD-0x12 start is
   exactly a type-7 start. With a non-null `Environment` the requester first loads **`PMVDMP`** and
   converts the DOS settings with its ordinal 13, `DOSTRANSPROPSTRLTOBIN`, which queries each name
   with `DosQueryDOSProperty` and drops every setting that answers 203 - so with no VDM the conversion
   itself does not fail `[INF]`. A load failure ends the start with its rc, a zero size with 8.
   Whether `PMVDMP` loads at all on a system without PM is not established.
2. **The shell creates the VDM server first, and only once.** `APPSTARTSESSION`, for type 4 or 7
   with `SMG_Flags` bit 3 clear, calls `CREATEVDMSERVER` (through a 16->32 stack switch), which
   creates the thread `VDMSTARTSESSION` in the shell's process (`DosCreateThread`, flags 0, 4 KB
   stack) and stores its tid in `VDMServerTID` (obj5+0xa54); success sets bit 3, which nothing
   clears. The creation's rc is never propagated, and it runs **before** the start can fail.
3. **`DOSSMSGSTART` allocates the session.** Both types get an id above `MaxFullScrnGrps`; an absent
   title becomes `"DOS Session"`; an empty program name is **not** defaulted to the `OS2_SHELL`
   program; there is no `VIORESTORE`; the DD creation notice goes out as for any type. A
   **foreground type-4** start switches the screen to the new, empty group before any VDM exists
   (`DOSSGSWITCHFOREGROUND` marks an incoming DOS group 0x4000, which skips the save record and
   `KbdSwitchFgnd` but still reaches `DosSGSwitch`); a foreground type-7 start switches to group 1
   when it is not on top. `WinCreateConsole` (`PMVIOP` ordinal 1) is filled only by a PM
   registration, so its arm is skipped.
4. **It calls `DosCreateVDM` (DOSCALLS #213) where every other type calls `DosExecPgm`** - from the
   shell for `InheritOpt` 0, from the requester's `APPSENDREQUEST` for `InheritOpt` 1.
5. **The kernel answers 641 at once.** #213 is a kernel entry (DOSCALL1 exports no 213) that routes
   a 32-byte Pascal frame to `_VDMMApiCreateVDM`, whose **first statement** tests `_fIsMVDMPresent`
   and returns 0x281 = 641 having read no argument and written or allocated nothing.
   `_fIsMVDMPresent` is set only by a complete `VDMMINIT` - the `INITTIME(0)` that also clears
   `SIS_ProtMdOnly`, see `infoseg.md` - so MVDM never run, or run and failed, answers 641. It is a
   facility test, not a test of the `PROTECTONLY=` setting.
6. **The failure arm unwinds.** `SGCB+0x14` bit 1 ("failed start"); no adopt, no
   `DosSGSwitchProc2`, no thaw, no `DosSetFgnd`; `DOSSMCHILDEXIT` at once, which writes no `TermQ`
   element for a failed start, sends the DD termination notice and calls nothing for 4/7 under a
   non-PM shell; then a switch back to the pre-start `TopMost` if the start moved it.
7. **The requester gets 641**, and for a related start `*pidSession` = 0 and `*ppid` = 0, which are
   written whatever the rc. The 343 -> 461 rule leaves 641 alone.

Under a **PM shell** on the same system the maximum is 60 (or 32), check 3 runs, and a DOS type
answers **491** from the requester's validator with nothing queued - unless a later failing check
overrides it.

**`DosCreateVDM`'s arguments** `[OBS-RE]`, from both DOSCALL1 call sites and the kernel body's frame,
in Pascal order (IBM publishes no parameter names; these are descriptive): the object-buffer far
pointer; a `ULONG` object-buffer length; the argument string; the converted DOS-settings environment
block; `&RESULTCODES`; the program name; a `ULONG` new screen-group id; the requesting VDM's current
directory, or 0.

**The VDM server is a reverse channel, not a VDM creator.** `VDMSTARTSESSION` creates the event
semaphore **`\SEM32\VDMSTART\DONE`** and loops forever on `DosSystemService(4, ...)` - `SysServVDM`,
which claims service 4 for the shell, dequeues an address from the kernel queue **`SMDosSessionQ`**,
copies a 0x400-byte record and relocates its string pointers. On success the thread stores the
record's screen group in `StartVDMSGID` and its current directory in `VDMCurDir`, calls
`DosStartSession` on the record's `STARTDATA`, writes the rc back and posts the semaphore. The only
producer is the kernel's `demStartSession` - **a DOS program inside a VDM calling
`DosStartSession`** through the INT 21h OS/2-API gateway - and the kernel's `_demVDMStartDoneSem` is
the same name string, which the VDM side waits on before queueing its next record. For the server
thread's own requests, `REQUESTBLOCKALOC` presents the start as coming from the requesting VDM's
session (its packed id, its lead pid, tid 1), so the new session becomes that VDM's child, and sets a
block bit that passes `VDMCurDir` to `DosCreateVDM`. With no VDM the thread sleeps in the kernel for
the shell's life and that arm never applies.

**State a refused DOS-type start leaves behind:** the VDM server thread, blocked for the shell's
life; `VDMServerTID` and `SMG_Flags` bit 3, never cleared; the service-4 owner word, until the shell
exits; `\SEM32\VDMSTART\DONE`; the screen-group id, still allocated as the deferred `LastSGFreed`
until the next `DOSSMDELSGCB`; and in the requester, `PMVDMP` if an `Environment` was given and the
open `APPREQQ` handle. No SGCB, process, PTDA or VDM remains.

**Not established:** whether `VDMMINIT` runs at all under `PROTECTONLY=YES` (the 641 does not depend
on it); the order of the `PROTECTONLY=` statement's own write of `SIS_ProtMdOnly` against
`VDMMINIT`; whether `PMVDMP` loads without PM; and the kernel side of the type-4 switch with no VDM,
read from the decompile only.

## The switch list (Window List) and session titles

The **switch list** is the system-wide table behind the Window List ("Task List" in IBM's own
glossary: *"the list of programs that is active"*), `WinQuerySwitchList`, Alt+Esc rotation, and -
less obviously - **every session-title query in the system**. On a PM system there is no separate
"session title" store: the title lives in the switch-list entry, and `DosSMSetTitle`,
`WinQuerySessionTitle`, and the `FCF_TASKLIST` frame title all resolve to the same 61-byte field.

### The documented contract [DOC-IBM]

Structures (Toolkit 4.5 `H/pmshl.h`): `MAXNAMEL` = **60** (`pmshl.h:56`); `SWCNTRL`
(`pmshl.h:322-333`) = `{ HWND hwnd; HWND hwndIcon; HPROGRAM hprog; PID idProcess; ULONG idSession;
ULONG uchVisibility; ULONG fbJump; CHAR szSwtitle[MAXNAMEL+4]; ULONG bProgType; }` (96 bytes in
the 32-bit form); `SWENTRY` = `{ HSWITCH hswitch; SWCNTRL swctl; }`; `SWBLOCK` = `{ ULONG
cswentry; SWENTRY aswentry[1]; }` (`pmshl.h:355-367`). Visibility: `SWL_VISIBLE` 4 /
`SWL_INVISIBLE` 1 / `SWL_GRAYED` 2; jump: `SWL_JUMPABLE` 2 / `SWL_NOTJUMPABLE` 1
(`pmshl.h:337-344`). `bProgType` uses the `PROG_*` values (DEFAULT 0 / FULLSCREEN 1 /
WINDOWABLEVIO 2 / PM 3 / VDM 4 / WINDOWEDVDM 7; WIN-OS/2 subtypes never appear in this structure -
PM Reference `pm4.inf`, "SWCNTRL").

Documented semantics (PM Reference `pm2.inf`/`pm3.inf`, CP Reference `cp2.inf`/Guide `cp3.inf` -
cited by INF topic since these are compiled books):

- **`WinAddSwitchEntry(PSWCNTRL) -> HSWITCH`** - *"If the szSwtitle field ... is 0, the system uses
  the name under which the application is started. This only applies for the first call to this
  function since the program started. Otherwise, a NULL entry name is invalid."* Title truncated
  to 60 chars; leading/trailing blanks removed (WinCreateSwitchEntry topic). Defaults: `hprog` 0 ->
  the handle the program was loaded under; `idProcess`/`idSession` 0 -> caller's; errors
  `PMERR_NO_SPACE` 0x1201, `PMERR_INVALID_SESSION_ID` 0x120B, `PMERR_INVALID_WINDOW` 0x1206.
- **`FCF_TASKLIST`** (pm3.inf, Frame Creation Flags): *"the program title is added to the front of
  the frame window text, the resulting string is used as the window title and is also entered on
  the task list. In this context, the program title is the text string used by the Desktop Manager
  to identify the program, or the text string specified as a parameter in the START command. If
  neither string has been defined, the filename and extension of the .EXE file are used as the
  program title. Note that a WinSetWindowText will **not** change the entry in the switch list."*
  `FCF_STANDARD` includes `FCF_TASKLIST`; frames with these flags auto-update the Window List on
  main-window create/destroy/title-change.
- **`WinQuerySessionTitle(hab, ulSession, pszTitle, ulTitlelen)`** - *"obtains the title under
  which a specified application is started, or is added to the Window List"*; after a Window List
  entry exists, *"the title in the Window List entry is obtained."* `ulSession` 0 = caller's own.
  `WinQueryTaskTitle` is the same minus the hab (*"use WinQuerySessionTitle for preference"*).
- **`STARTDATA.PgmTitle`** (cp2.inf) - up to **61 bytes including the NUL**; if 0/empty, *"the
  initial title is PgmName minus any leading drive and path information."* CP Guide (cp3.inf):
  *"the title specified in STARTDATA (or the application title if no title is specified) is added
  to the Window List"* when a session is created.

### The real implementation [OBS-RE, Warp 4.5 `PMMERGE.DLL` + `DOSCALL1.DLL` decompile/disasm]

**There are two title stores, selected by whether PM is present** (the session manager's
PM-present flag, shared-data offset `+0xa51`):

1. **No PM (text-mode boot):** `DOSCALL1.DLL` keeps a per-SGID name table in its own allocated
   segment (selector stored at shared-data `+0x490`), **32 bytes per slot indexed `sgid*0x20`**,
   format `[length byte][<=30 chars][NUL]`; the SGCB's `+0x30` field is that slot offset. Read
   back by `DosSMGetStatus` (shell-only), which emits per-session records with a 32-byte
   space-padded title. When PM **is** present this table is allocated as a 10-byte stub and never
   used - the copy code in the SGCB constructor and in `DosSMGetStatus` is explicitly gated on
   the PM flag being clear.

   **The default title, from the bytes (2026-10-12) `[OBS-RE]`.** Before the session block is
   built, the start engine fixes three strings. For types other than 4 and 7, a `NULL` or empty
   program name becomes the shell's own command processor name, and **only then** a `NULL` or
   empty argument string becomes the shell's own arguments (a given name keeps empty arguments).
   A `NULL` or empty title becomes **"DOS Session"** for types 4 and 7; for every other type it is
   **the program name from just past its last `\` or `:`**, extension included, with DBCS lead
   bytes recognised so a trail byte is never taken as a separator. That is IBM's documented
   "PgmName minus any leading drive and path information", implemented. The constructor copies it
   into the slot (up to 30 bytes) as for a given title; then, **when the title was defaulted and PM
   is not present, the slot's length byte is set to 0**, so the file name stays in the slot's text
   with a recorded length of 0. `DosSMGetStatus` copies the text to its NUL and does not read the
   length byte.
2. **PM present:** the title is **`szSwtitle` of the session's switch-list entry, and nothing
   else**. PMMERGE never reads the DOSCALL1 name table.

**Switch-entry storage (PMMERGE):** a singly-linked list of **0x7E (126)-byte** nodes in a
dedicated 16-bit heap segment (`SELSWL`), list head `pswiList` in PMMERGE's DGROUP. Field map
(from the allocator/copy/find routines):

| off | field |
|---|---|
| +0x00 | next-entry far pointer (offset, selector) |
| +0x04 | signature word `0x4453` "SD" (validity-checked with the handle) |
| +0x06 | flags word - see below |
| +0x08 | hwnd , +0x0c hwndIcon , +0x10 hprog |
| +0x14 | pid (word) |
| +0x16 | **idSession (low byte)** - the lookup key for all title queries; high byte doubles as a program-type copy |
| +0x18 | uchVisibility (byte) , +0x19 fbJump (byte) |
| **+0x1a** | **szSwtitle - 61 bytes (60 + NUL); THE title store on a PM system** |
| +0x57 | bProgType (byte) , +0x58 parent/related session id |
| +0x5a | owner/root hwnd , +0x5e-0x66 task size/pos |
| +0x68 | session type , +0x76/+0x7a far pointers to related/bonded entries |

Flags word: `0x01` removed , `0x02` tombstoned (a session-owned entry is not freed on
`WinRemoveSwitchEntry` - it is marked `|=3` and kept; a later `WinAddSwitchEntry` from the same
session revives it **without clearing the stored title**) , `0x04` related-child , `0x80`
session-entry-without-window-yet , `0x200` the shell/task-manager's own entry (skipped by every
lookup) , **`0x400` title-was-derived** - the gate for `DosSMSetTitle` (below) , `0x2000`/`0x4000`
bond linkage. **`HSWITCH` encoding:** the entry's offset within the switch-list heap segment
(segment word must be 0); validity = segment 0 + "SD" signature + not-removed.

**How a session's title is established - `WinInitSession` (PMMERGE #3143), the write side.** The
session-start transaction (the AppReq serve loop hands the ~~218-byte~~ session request-block - 0x77E
or 0x882 bytes, corrected 2026-10-12, see "`DosStartSession` on the requester side" - to
PMMERGE) allocates the session's switch entry and resolves the title with this exact priority:

1. **`STARTDATA.PgmTitle`** (request-block string `+0x38`), verbatim, if non-empty.
2. Else, if the session was started **by program handle** (`hprog`): the program object's title
   from the OS2.INI program list (program-record `+0xc`).
3. Else: flags `|= 0x400` (title is *derived*), and the title = **basename of
   `STARTDATA.PgmName`** (request-block string `+0x3a`) - the copy loop restarts at each `\`,
   `/`, or `:`, DBCS-aware. If PgmName is empty too, a built-in default (the registered
   command-processor name).

Then `szSwtitle` (`+0x1a`) is written (61-byte copy) and the shell is notified (Window List
refresh). This is byte-for-byte the documented `FCF_TASKLIST` fallback chain (Desktop-Manager
title -> START title -> exe filename), with "START title / WPS object title" arriving as
`PgmTitle`. The DOSCALL1 side mirrors the same policy for its non-PM table (`PgmTitle` -> basename
of `PgmName` -> default; explicit title => length byte set) - two independent implementations of
one rule.

**`DosSMSetTitle` - the only after-the-fact setter.** DOSCALL1's dispatcher: if PMMERGE has
registered its `WinSetTitle` callback, call it - PMMERGE finds the **caller's own session's**
entry (`LIS_CurScrnGrp`) and rewrites `+0x1a`, but **only if flag `0x400` is set** (title was
derived); an explicit launch-time `PgmTitle` makes the title immutable - error 372
(`ERROR_SMG_SET_TITLE`, Toolkit `bseerr.h:` "MSG%SMG_SET_TITLE" - the "title fixed at session
start" refusal). Rejected too for VDM-class
sessions and empty strings. Without PM, the same call writes the DOSCALL1 name table under the
same explicit-title latch (there via the slot's length byte). `DosSMSetTitle` takes **no target
parameter** - it always titles the caller's own session, so a command processor calling it
retitles the whole session's Window List entry.

**The read side - `WinQueryTaskTitle`/`WinQuerySessionTitle` (one function; Session is a
forwarder to Task).** `idSession` 0 -> the caller's `LIS_CurScrnGrp`; find the first live entry
whose `+0x16` session byte matches; copy `+0x1a`. **If the session has no switch entry at all**,
the call fails (`PMERR_INVALID_SESSION_ID` class, 0x120B) and copies a fallback template string
instead - a string **resource** (id 19 in PMMERGE, the text `"Switch to"`) loaded into a DGROUP
buffer at PM init, with the session id substituted in. A title of "Switch to" is therefore the
signature of *querying a session that has no switch entry*, not a normal default.

**The `FCF_TASKLIST` auto-add (frame creation).** Frame creation with `FCF_TASKLIST` calls an
internal helper that: queries `WinQuerySwitchHandle(hwnd, 0)`; picks the title = the frame's
creation text if non-empty, **else `WinQueryTaskTitle(0, ...)`** - i.e. *the session's existing
switch-entry title*; fills `SWCNTRL{hwnd, pid (from the caller's LIS), idSession 0 -> own,
SWL_VISIBLE, SWL_JUMPABLE, PROG_PM}`; then `WinAddSwitchEntry` (or `WinChangeSwitchEntry` when an
entry already existed) **and pushes the same string into the title bar** (`WM_SETWINDOWPARAMS` to
`FID_TITLEBAR`). So the "program title" the documentation says is prefixed to the window title is
literally the session's switch-entry title read back through `WinQueryTaskTitle` - the frame
never consults the PIB command line, the MTE module name, or OS2.INI (checked; the only OS2.INI
title reader, the legacy Program List `GetGroupTitle`/"ProgramEntry" path, is not on this chain).

**Lifecycle notes.** Every switch-list API fails (`0x1205`) until the shell has registered via
`WinSwitchProgramRegister` (which also creates the shell's own `0x200`-flagged entry and starts
the hard-error/AppReq/hotkey threads). A dying entry is not removed synchronously - death parks
the entry in pending-switch state and pulses the switch-request rendezvous so the switch engine
picks a new foreground; removal cascades to related-child entries in the same session, notifying
the shell per entry. `WinChangeSwitchEntry` ignores an empty incoming title (never clears a
stored one). `WinQuerySwitchHandle(NULL, pid)` falls back to *"the most proximal ancestor
process"*'s entry - the only documented ancestry-based inheritance in the whole surface.

**Consequence worth stating plainly:** there is **no per-process title anywhere** - both stores
are keyed by session id. A process launched into an existing session (plain `DosExecPgm`)
inherits that session's title for every query; a program that shows *its own* name in its title
bar on a command-line launch does so because its launcher started it in a **new session** whose
derived title is the exe basename (command processors classify PM executables via
`DosQueryAppType` and start them as sessions rather than exec'ing them into their own).

---

### A command processor's own switch entry gates its batch wait  `[OBS-RE]`

Added 2026-08-20. Read out of the shipped `CMD.EXE` (Warp 4.5, corpus member
`cmd`) and `PMMERGE.DLL`; both are disassembly-confirmed, not inferred from
names.

**A command processor holds its own switch handle, acquired by process id.** At
init, when PM is present, `CMD.EXE` loads the LINFOSEG far pointer out of its
DGROUP, takes **`LIS_CurProcID`** (`+0x00`) as its own process id, and calls
**`WinQuerySwitchHandle(hwnd = NULL, pid)`** - the by-pid form. It caches the
`HSWITCH` and, when non-zero, follows with `WinQuerySwitchEntry` to fill a
local `SWCNTRL`. It also uses the same pid to build its termination-queue name.

**The by-pid lookup matches `SWCNTRL.idProcess`.** `WIN16QUERYSWITCHHANDLE`
(PMMERGE `1e81:5df4`) walks the switch list from its head comparing
**entry `+0x14`** against the caller's pid, skipping entries whose flag byte at
`+0x06` has either of two bits set, and - this is the documented ancestry
fallback, seen in the code as an outer retry loop - replaces the pid with its
parent's and walks again. Exhausted, it returns **0** with `0x1204`.
`+0x14` is the same field the session-start callback (`WinPreThaw`) writes when
a session's process id first becomes known.

**Failing that lookup silently disables the batch wait.** After a successful
`DosStartSession`, a PM-present command processor runs, in order:

1. `WinChangeSwitchEntry(hswitch, &own_swctl)` - with `uchVisibility` and
   `fbJump` both set to 1 first. **A bad `HSWITCH` fails `BADSWITCH` and
   returns `0x1202`**; zero is not a wildcard here.
2. only for a windowable-VIO launcher, and only once per process:
   `WinQueryWindowPos(own_frame, &swp)`, then
   `WinPostMsg(own_frame, WM_SYSCOMMAND, MPFROMSHORT(SC_MINIMIZE), 0)` - this
   is why a command processor minimises itself when it launches a PM program.
3. `DosSetSession(idSession, STATUSDATA{ Length = 6, SelectInd = 0,
   BondInd = 1 })` - the bond - followed by the wait on the child session's
   `TermQ`.

**Steps 1 and 2 each `return` on failure, before step 3.** So a command
processor that cannot resolve its own switch entry does not bond and does not
wait: it runs the next batch line immediately. The observable failure is a
batch file that appears to launch asynchronously - which OS/2 never does (see
"Starting a session from a batch file" above) - with no error reported
anywhere. Nothing on this path consults the child's application type; the
whole gate is about the *launcher's* own switch entry.

---

*Ratified (2026-07-26): checked against IBM Toolkit 4.5 `H/bsedos.h` (`INCL_DOSSESMGR` block,
lines 2681-2811; `DosQuerySysInfo`/QSV indices 2498-2610; `DosQuerySysState`/`QS*REC` 3130-3594)
and IBM DDK `base/h/infoseg.h` (foreground fields). All session-control prototypes, the `STARTDATA`
/ `STATUSDATA` layouts and their `SSF_*` / `SET_SESSION_*` / `STOP_SESSION_*` constants, the
`DosQueryAppType` `FAPPTYP_*` bits, `QSV_FOREGROUND_FS_SESSION` (=24), and the four InfoSeg
foreground fields matched IBM sources and were upgraded from a general `[DOC-IBM]` tag to
line-precise citations. Nothing in the original doc contradicted IBM sources. (The `QS*REC` record
names added here were taken directly from `QSPTRREC` at `bsedos.h:3578-3587`: `QSLREC` = module/MTE,
`QSMREC` = shared-mem, `QSS16HEADREC`/`QSS32REC` = semaphore - there is no `QSSREC`.) `DosQProcStatus`
(the 16-bit name) could not be sourced to the 4.5 Toolkit and is left noted as such.*

*Internal-mechanism section added 2026-07-30: reverse-engineered from `SESMGR.DLL`/`DOSCALL1.DLL`/
`PMMERGE.DLL` (static disassembly, symbol tables from matching debug-build `.SYM` files) with live
confirmation via KDB on a running Warp 4.5 debug-kernel VM, including single-stepping the hotkey
trigger chain through a genuine keypress to its real destination. No IBM document covering this
mechanism is known - everything here is [OBS-RE]. Two items remain open and are noted as such
above: the exact meaning of SGCB `+0x4c`/`+0x4e`, and whether the kernel-level priority-propagation
mechanism connects to the `DOSCALL1.DLL` chain or runs in parallel to it.*

*`DosSystemService`/`SMHotKeyQ` subsection added 2026-08-02: decoded by static disassembly of the
Warp 4.5 debug kernel (dispatcher `h_w_SystemService`, `SysServSM`, the `DOSSYSTEMSERVICE` entry
thunk; service table read out of the decompressed kernel data object at the offset the dispatcher
codes) plus fixup-table resolution of the one real caller's import. [OBS-RE]. Open: the producer
side's event-word encoding (what value `SysServQueueEvent` queues for each hotkey), and the
subfunctions of `SysServSM` other than 0 (the disassembly shows at least 1, 2 and 4 exist, with
subfunction 2 waiting on a second queue block). [2026-10-12: subfunction 2's queue block is
`CtrlNumLkQ`, fed by `DevHelp_SendEvent` event 3 (Ctrl+NumLock) and consumed by `DOSSMPAUDAEMON`; see
the subfunction-2 bullet in "Where the hotkey thread sleeps".]*

*`SysServSM` subfunctions decoded 2026-09-30 `[OBS-RE]` (Warp 4.5 debug kernel, 16-bit `SysServSM`;
32-bit targets named from the SMP debug kernel's symbols): **1** = fetch two words *a*, *b* and call
`Sys_FreezeThaw`: *a* >= 4 -> 13; otherwise `_TKScanTasks(a | 1, b, _tkSysFrzThwWrkr, a)`, whose worker
freezes every thread of each matched process when *a* is even and thaws it when *a* is odd; **2** =
wait on the second queue block; **3** = refused (carry); **4** = fetch a pid and call
`_TKAdoptTask(pid)`: 303 `ERROR_INVALID_PROCID` if there is no such process, else the process is
unlinked from its parent's child list and linked as a child of the caller; **5** = reboot.*

*Mouse-focus paragraph corrected 2026-07-30, later the same day: the original text (based only on
the `DOSCALL1.DLL`/`PMMERGE.DLL` switch chain) concluded mouse had no switch-aware mechanism at
all. Reading IBM's real mouse-driver source directly - the actual shipped driver, not this
chain - found a genuine one, reached through a different IOCtl path than the notify chain traced
above. Corrected in place per the source's own discipline (mark superseded, don't delete): the PM
routing conclusion (hit-testing, no per-session table) still holds, now for a driver-confirmed
reason instead of an inferred one.*

*"Session creation does not set up screen space" paragraph added 2026-07-30, later still, in
answer to a direct question about whether `DosStartSession`/`DosExecPgm` allocates a new session's
screen buffer. [OBS-RE], from reading the real SGCB-constructor's own field writes. Not fully
closed: `DOSEXECPGM`'s own kernel-level body (as opposed to the request-block wrapper that maps
`STARTDATA` onto it) was not itself disassembled - the concrete next step if this needs settling
with full certainty rather than by elimination.*

*Switch-list/session-title section added 2026-08-15. [DOC-IBM] half: Toolkit 4.5 `H/pmshl.h`
(structures, by line) and the PM Reference / CP Reference+Guide INF books (by topic name -
`WinAddSwitchEntry`, `WinCreateSwitchEntry`, `WinQuerySessionTitle`, `WinQueryTaskTitle`, "Frame
Creation Flags" for `FCF_TASKLIST`, "STARTDATA Field - PgmTitle"). [OBS-RE] half: full Ghidra
decompile + targeted raw disassembly of the Warp 4.5 `PMMERGE.DLL` (`WININITSESSION`,
`WIN16ADDSWITCHENTRY`, `ALLOCSWITCHENTRY`/`FREESWITCHENTRY`/`FINDSWITCHENTRY`/`CHANGESWITCH`,
`SETTITLE`, `WIN16QUERYTASKTITLE`, the frame-creation `FCF_TASKLIST` helper with its five PMSHAPI
import fixups resolved from the LX records) and `DOSCALL1.DLL` (`DOSSMSETTITLE`,
`DOSSMSGSETTITLE`, `DOSSMGETNAMES`, `DOSSMADDSGCB`, `DOSSMSGSTART`, `DOSSMGETSTATUS`,
`DOSSMINITALLOC`). The two-store split and the identical title-priority policy on both sides were
each read from the code, not inferred from one another. Open, flagged not guessed: whether the
non-PM store's quirk of never re-setting its length byte after a successful `DosSMSetTitle`
(leaving the title re-settable indefinitely in text mode) is intended behavior; and the internal
handle->segment helper both name-table users call (an unresolved low-band DOSCALLS fixup).*
