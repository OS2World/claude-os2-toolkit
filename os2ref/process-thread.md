# OS/2 Process and Thread API (Control Program)

The Control Program (base "Dos" API) surface for creating, controlling, and terminating
processes and threads. A **process** owns an address space, a set of open handles, an
environment, and a `.EXE` module; a **thread** is a schedulable unit of execution within a
process. Every process has at least one thread (the initial thread, ordinal 1), and threads
share the process's address space and handles. Each thread has its own stack, register set,
priority, and exception-handler chain, exposed through the Thread Information Block (TIB); the
process-wide state an application can read is exposed through the Process Information Block
(PIB). This reference covers the process/thread lifecycle calls, priority and scheduling
control, termination handlers, and the TIB/PIB an application sees.

Provenance: **[DOC-IBM]** OS/2 Toolkit 4.5 headers `H/bsedos.h` (prototypes, `EXEC_*`,
`PRTYC_*`/`PRTYS_*`/`PRTYD_*`, `EXLST_*`, `DCWA_*`/`DCWW_*`, `CREATE_*`/`STACK_*`, `EXIT_*`,
`DKP_*`, `PT_*`, `PS_*`, `RESULTCODES`, `THREADCREATE`), `H/bsetib.h` (TIB / TIB2 / PIB),
`H/os2def.h` (`PID`/`TID`/`PTID`/`PPID` base types), and `H/bseerr.h` (`ERROR_*` values).
All function names, prototypes, constants, structure fields, and error numbers below are
transcribed from those headers.

---

## Base handle types [DOC-IBM - os2def.h]

| Type | Definition | Note |
|---|---|---|
| `PID` | `LHANDLE` (`unsigned long`) | process identifier |
| `TID` | `LHANDLE` (`unsigned long`) | thread identifier |
| `PPID` | `PID *` | pointer to a PID |
| `PTID` | `TID *` | pointer to a TID |

TIDs are numbered per-process starting at 1 (the initial thread). PIDs are system-wide.

---

## Function summary

### Process lifecycle [DOC-IBM - bsedos.h]

| Function | Purpose |
|---|---|
| `DosExecPgm` | Load and start a child program, synchronously or asynchronously |
| `DosExit` | End the calling thread, or the whole process |
| `DosWaitChild` | Wait for a child process to end and collect its result codes (alias `DosCwait`) |
| `DosKillProcess` | Post a termination request to another process (or a process tree) |
| `DosSetPriority` | Set the priority class/delta of a process, process tree, or thread (alias `DosSetPrty`) |

### Thread lifecycle [DOC-IBM - bsedos.h]

| Function | Purpose |
|---|---|
| `DosCreateThread` | Create a new thread in the current process |
| `DosCreateThread2` | Create a thread using a `THREADCREATE` parameter block |
| `DosSuspendThread` | Suspend execution of a thread in the current process |
| `DosResumeThread` | Resume a suspended thread |
| `DosWaitThread` | Wait for a thread in the current process to end |
| `DosKillThread` | Request termination of a thread in the current process |
| `DosSleep` | Suspend the calling thread for a time interval |

### Termination handlers and critical sections [DOC-IBM - bsedos.h]

| Function | Purpose |
|---|---|
| `DosExitList` | Register / remove a routine to run at process termination |
| `DosEnterCritSec` | Suspend all other threads of the process (enter a critical section) |
| `DosExitCritSec` | Resume the other threads (leave a critical section) |
| `DosEnterMustComplete` | Begin a must-complete (non-interruptible-by-signal) region |
| `DosExitMustComplete` | End a must-complete region |

### Information

| Function | Purpose |
|---|---|
| `DosGetInfoBlocks` | Return pointers to the calling thread's TIB and the process's PIB |

---

## The Thread Information Block (TIB) [DOC-IBM - bsetib.h]

`DosGetInfoBlocks` returns a pointer to the per-thread TIB. The TIB has two parts: the base
`TIB` (public, cross-version fields) and the `TIB2` (system-specific fields) it points to.

`struct tib_s` (`TIB`) - 6 pointer/`ULONG` fields:

| Offset | Field | Type | Meaning |
|---|---|---|---|
| 0x00 | `tib_pexchain` | `PVOID` | head of the thread's exception-handler chain |
| 0x04 | `tib_pstack` | `PVOID` | pointer to the base of the thread's stack |
| 0x08 | `tib_pstacklimit` | `PVOID` | pointer to the end (limit) of the thread's stack |
| 0x0C | `tib_ptib2` | `PTIB2` | pointer to the system-specific TIB2 |
| 0x10 | `tib_version` | `ULONG` | version number of this TIB structure |
| 0x14 | `tib_ordinal` | `ULONG` | thread ordinal number |

`struct tib2_s` (`TIB2`) - the system-specific block `tib_ptib2` points to:

| Offset | Field | Type | Meaning |
|---|---|---|---|
| 0x00 | `tib2_ultid` | `ULONG` | thread ID |
| 0x04 | `tib2_ulpri` | `ULONG` | thread priority (class in the high byte, delta in the low bits) |
| 0x08 | `tib2_version` | `ULONG` | version number of this structure |
| 0x0C | `tib2_usMCCount` | `USHORT` | must-complete nesting count |
| 0x0E | `tib2_fMCForceFlag` | `USHORT` | must-complete force flag |

The base of the TIB is what the FS segment register addresses in a running thread:
`FS:[0]` is `tib_pexchain`, the head of the exception-handler chain. [OBS-RE - the FS-relative
TIB layout is observed of the running kernel; the field list itself is [DOC-IBM].]

## The Process Information Block (PIB) [DOC-IBM - bsetib.h]

`struct pib_s` (`PIB`) - 7 `ULONG`/pointer fields:

| Offset | Field | Type | Meaning |
|---|---|---|---|
| 0x00 | `pib_ulpid` | `ULONG` | process ID |
| 0x04 | `pib_ulppid` | `ULONG` | parent process ID |
| 0x08 | `pib_hmte` | `ULONG` | module handle of the program's `.EXE` |
| 0x0C | `pib_pchcmd` | `PCHAR` | pointer to the command-line string |
| 0x10 | `pib_pchenv` | `PCHAR` | pointer to the environment block |
| 0x14 | `pib_flstatus` | `ULONG` | process status flags |
| 0x18 | `pib_ultype` | `ULONG` | process type code |

**`pib_pchcmd`** points to the argument strings: the program name (ASCIIZ) immediately followed
by the argument string (ASCIIZ), the pair terminated by a second null. **`pib_pchenv`** points
to the environment block: a sequence of `NAME=value` ASCIIZ strings terminated by an extra null
byte.

**`pib_ultype` - process type codes** [DOC-IBM - bsedos.h]:

| Value | Constant | Meaning |
|---|---|---|
| 0 | `PT_FULLSCREEN` | full-screen application |
| 1 | `PT_REALMODE` | real-mode process |
| 2 | `PT_WINDOWABLEVIO` | VIO (text) windowable application |
| 3 | `PT_PM` | Presentation Manager application |
| 4 | `PT_DETACHED` | detached application (no session) |

**`pib_flstatus` - process status flags** [DOC-IBM - bsedos.h]:

| Value | Constant | Meaning |
|---|---|---|
| 1 | `PS_EXITLIST` | the thread is currently running in an exit-list routine |

---

## Process creation - `DosExecPgm` [DOC-IBM - bsedos.h]

```c
APIRET APIENTRY DosExecPgm(PCHAR pObjname,       /* failing-object-name buffer   */
                           LONG  cbObjname,       /* size of that buffer          */
                           ULONG execFlag,        /* EXEC_* mode                  */
                           PSZ   pArg,            /* argument strings             */
                           PSZ   pEnv,            /* environment block            */
                           PRESULTCODES pRes,     /* result codes (out)           */
                           PSZ   pName);          /* program file to run          */
```

`pObjname`/`cbObjname` name a caller buffer that, on a load failure, receives the name of the
object (e.g. a missing DLL) that caused the failure. `pArg` is an argument block in the same
double-null form as `pib_pchcmd`; `pEnv` is an environment block in the same form as
`pib_pchenv` (pass `NULL` to inherit the caller's environment). `pName` is the program file to
execute.

**`execFlag` values** [DOC-IBM - bsedos.h]:

| Value | Constant | Meaning |
|---|---|---|
| 0 | `EXEC_SYNC` | run synchronously; `DosExecPgm` returns when the child ends |
| 1 | `EXEC_ASYNC` | run asynchronously; return immediately, result codes discarded |
| 2 | `EXEC_ASYNCRESULT` | asynchronous, but the child's result is retained for `DosWaitChild` |
| 3 | `EXEC_TRACE` | asynchronous, child started under debug (trace) control |
| 4 | `EXEC_BACKGROUND` | run as an independent background process |
| 5 | `EXEC_LOAD` | load the program but leave it ready/frozen (do not begin execution) |
| 6 | `EXEC_ASYNCRESULTDB` | asynchronous with retained result, under debug control |

**`pRes` - `RESULTCODES`** [DOC-IBM - bsedos.h]:

```c
typedef struct _RESULTCODES {   /* resc */
   ULONG codeTerminate;         /* how the child ended / child PID */
   ULONG codeResult;            /* the child's exit result code    */
} RESULTCODES;
```

For `EXEC_SYNC`, on return `codeTerminate` is the termination reason and `codeResult` is the
value the child passed to `DosExit`. For the asynchronous "result" modes
(`EXEC_ASYNCRESULT`/`EXEC_ASYNCRESULTDB`), `codeTerminate` receives the new child's PID, and the
final result is later collected with `DosWaitChild`.

**`codeTerminate` - synchronous termination reasons** [DOC - EDM2 "DosExecPgm (FAPI)"]: for a
synchronous child, `codeTerminate` reports *why* it ended (these are the same values a waiting
parent sees from `DosWaitChild`):

| Value | Meaning |
|---|---|
| 0 | normal exit (child called `DosExit`) |
| 1 | hard-error abort |
| 2 | trap (exception) |
| 3 | unintercepted `DosKillProcess` |

## Process termination and waiting

### `DosExit` [DOC-IBM - bsedos.h]

```c
VOID APIENTRY DosExit(ULONG action, ULONG result);
```

Ends the current thread or the whole process. This function does not return.

| `action` | Constant | Effect |
|---|---|---|
| 0 | `EXIT_THREAD` | end only the calling thread |
| 1 | `EXIT_PROCESS` | end the whole process (all threads); registered exit-list routines run |

`result` is the exit code delivered to a waiting parent in `RESULTCODES.codeResult`. Ending the
initial thread with `EXIT_THREAD` terminates the process. Note the low-level `EXIT_*` codes
(0/1) are distinct from the higher-level `EXLST_EXIT` used with `DosExitList`.

### `DosWaitChild` (alias `DosCwait`) [DOC-IBM - bsedos.h]

```c
APIRET APIENTRY DosWaitChild(ULONG action,       /* DCWA_* : which children     */
                             ULONG option,        /* DCWW_* : wait or poll       */
                             PRESULTCODES pres,    /* result codes (out)          */
                             PPID  ppid,           /* PID that ended (out)        */
                             PID   pid);           /* which child, or 0 for any   */
```

| `action` | Constant | Scope |
|---|---|---|
| 0 | `DCWA_PROCESS` | wait on the specified child only |
| 1 | `DCWA_PROCESSTREE` | wait on the child and its descendant tree |

| `option` | Constant | Behaviour |
|---|---|---|
| 0 | `DCWW_WAIT` | block until a matching child ends |
| 1 | `DCWW_NOWAIT` | return immediately; if no child has ended, report that |

`pres` receives the ended child's `RESULTCODES`, and `*ppid` receives its PID. `pid` selects a
specific child (0 = any child). Only children started with a result-retaining mode
(`EXEC_ASYNCRESULT` / `EXEC_ASYNCRESULTDB`) can be waited on this way.

### `DosKillProcess` [DOC-IBM - bsedos.h]

```c
APIRET APIENTRY DosKillProcess(ULONG action, PID pid);
```

| `action` | Constant | Scope |
|---|---|---|
| 0 | `DKP_PROCESSTREE` | terminate the process and its descendant tree |
| 1 | `DKP_PROCESS` | terminate only the named process |

---

## Thread creation and control

### `DosCreateThread` [DOC-IBM - bsedos.h]

```c
typedef VOID APIENTRY FNTHREAD(ULONG);
typedef FNTHREAD *PFNTHREAD;

APIRET APIENTRY DosCreateThread(PTID  ptid,       /* new thread's TID (out)      */
                                PFNTHREAD pfn,     /* thread entry function       */
                                ULONG param,       /* argument passed to pfn      */
                                ULONG flag,        /* CREATE_* | STACK_*          */
                                ULONG cbStack);    /* stack size in bytes         */
```

The new thread begins at `pfn`, receiving `param` as its single argument. `*ptid` receives the
new thread's ID. `cbStack` is the stack size to allocate (rounded up as the system requires).

**`flag` bits** [DOC-IBM - bsedos.h]:

| Value | Constant | Meaning |
|---|---|---|
| 0 | `CREATE_READY` | start the thread immediately (ready to run) |
| 1 | `CREATE_SUSPENDED` | create the thread suspended; a later `DosResumeThread` starts it |
| 0 | `STACK_SPARSE` | reserve stack, commit pages on demand |
| 2 | `STACK_COMMITTED` | commit the whole stack up front |

(`CREATE_*` and `STACK_*` are combined with bitwise OR; `CREATE_READY`/`STACK_SPARSE` are the
zero defaults.)

### `DosCreateThread2` [DOC-IBM - bsedos.h]

```c
typedef struct _THREADCREATE {   /* F150593 */
   ULONG     cbSize;             /* size of this structure       */
   PTID      pTid;              /* new thread's TID (out)       */
   PFNTHREAD pfnStart;          /* thread entry function        */
   ULONG     lParam;           /* argument passed to pfnStart  */
   ULONG     lFlag;            /* CREATE_* | STACK_* flags     */
   PBYTE     pStack;           /* caller-supplied stack, or 0  */
   ULONG     cbStack;          /* stack size in bytes          */
} THREADCREATE;
typedef THREADCREATE *PTHREADCREATE;

APIRET APIENTRY DosCreateThread2(PTHREADCREATE ptc);
```

A parameter-block form of `DosCreateThread` that additionally allows the caller to supply the
thread stack (`pStack`). `cbSize` must be set to `sizeof(THREADCREATE)`.

[DOC - EDM2 "DosCreateThread2"] `pStack` is the address of the **top** (high end) of the
caller-allocated stack, not its base, and must lie within the first 512MB of the address space
(below `0x20000000`); a higher stack address returns `ERROR_INVALID_PARAMETER`. Unlike
`DosCreateThread` (which reserves 64KB of address space per thread but commits only ~8KB, and
adds guard pages for automatic stack growth), the caller owns the stack's size and location
here.

### `DosSuspendThread` / `DosResumeThread` [DOC-IBM - bsedos.h]

```c
APIRET APIENTRY DosSuspendThread(TID tid);
APIRET APIENTRY DosResumeThread(TID tid);
```

Suspend or resume a thread of the *calling* process, named by its TID. A thread created with
`CREATE_SUSPENDED` is started with `DosResumeThread`.

### `DosWaitThread` [DOC-IBM - bsedos.h]

```c
APIRET APIENTRY DosWaitThread(PTID ptid, ULONG option);
```

Waits for a thread of the calling process to terminate. `*ptid` names the thread to wait for on
entry (0 waits for any thread) and receives the TID of the thread that ended on return.
`option` takes the same `DCWW_WAIT` (0, block) / `DCWW_NOWAIT` (1, poll) values as
`DosWaitChild`.

[DOC - EDM2 "DosWaitThread"] A thread cannot wait on its own termination, nor on the initial
thread (input `*ptid` = 1); either returns `ERROR_INVALID_THREADID`. Under `DCWW_NOWAIT` with no
thread yet ended, `*ptid` is left unchanged. A common use is to reclaim an ended thread's
resources (e.g. its stack).

### `DosKillThread` [DOC-IBM - bsedos.h]

```c
APIRET APIENTRY DosKillThread(TID tid);
```

Requests termination of a thread of the calling process.

### `DosSleep` [DOC-IBM - bsedos.h]

```c
APIRET APIENTRY DosSleep(ULONG msec);
```

Suspends the calling thread for at least `msec` milliseconds. `DosSleep(0)` yields the remainder
of the current time slice to another ready thread.

[DOC - EDM2 "DosSleep (FAPI)"] The `DosSleep(0)` yield goes only to a ready thread of *equal or
higher* priority - it does not yield to a lower-priority thread - and returns immediately if no
such thread is ready. A non-zero interval is rounded up to the scheduler-clock resolution, so
the actual sleep can be a tick or two longer than requested; it is therefore not a substitute
for a real-time clock.

---

## Priority and scheduling - `DosSetPriority` (alias `DosSetPrty`) [DOC-IBM - bsedos.h]

```c
APIRET APIENTRY DosSetPriority(ULONG scope,      /* PRTYS_* : what to change    */
                               ULONG ulClass,     /* PRTYC_* : priority class    */
                               LONG  delta,       /* -31..+31 within the class   */
                               ULONG PorTid);     /* target PID or TID           */
```

A thread's dispatch priority is a **class** plus a signed **delta** within that class. `scope`
chooses what the change applies to; `PorTid` is the target PID or TID (0 = the current process
or thread, per scope).

**`scope` - `PRTYS_*`:**

| Value | Constant | Applies to |
|---|---|---|
| 0 | `PRTYS_PROCESS` | all threads of the named process |
| 1 | `PRTYS_PROCESSTREE` | the process and its descendant tree |
| 2 | `PRTYS_THREAD` | a single thread |

**`ulClass` - `PRTYC_*` priority classes:**

| Value | Constant | Meaning |
|---|---|---|
| 0 | `PRTYC_NOCHANGE` | leave the class unchanged (adjust delta only) |
| 1 | `PRTYC_IDLETIME` | idle-time (runs only when nothing else is ready) |
| 2 | `PRTYC_REGULAR` | regular (normal application priority) |
| 3 | `PRTYC_TIMECRITICAL` | time-critical (highest; real-time-sensitive threads) |
| 4 | `PRTYC_FOREGROUNDSERVER` | foreground-server (boosted while serving the foreground) |

**`delta` - `PRTYD_*` bounds:**

| Value | Constant |
|---|---|
| -31 | `PRTYD_MINIMUM` |
| +31 | `PRTYD_MAXIMUM` |

The delta is a signed adjustment (`PRTYD_MINIMUM`..`PRTYD_MAXIMUM`) applied within the chosen
class.

---

## Termination handlers - `DosExitList` [DOC-IBM - bsedos.h]

```c
typedef VOID APIENTRY FNEXITLIST(ULONG);
typedef FNEXITLIST *PFNEXITLIST;

APIRET APIENTRY DosExitList(ULONG ordercode, PFNEXITLIST pfn);
```

Registers (or removes) a routine to run when the process terminates. Exit-list routines execute,
in a defined order, on **thread 1**, after every other thread of the process has ended - however the
process began to end: `DosExit(EXIT_PROCESS)` from any thread, any `DosExit` from thread 1
(including thread 1's function returning), or a kill that nothing intercepts [OBS-RE - the Warp 4.5
SMP debug kernel's `_TKExit`, `_TKDieSoonPTDA` and `_TKTermThread`]. *(CORRECTED, Rule 1.7: this
said "on the process's last surviving thread during `EXIT_PROCESS` shutdown". The two readings
differ whenever the exiting thread is not thread 1.)* Measured from a 16-bit program on Warp 4.50
(kernel revision 14.089, SMP) [OBS-RE - measured]: in every case above the routine ran with
`tidCurrent` 1; other threads, sleeping or spinning, made no further progress; a thread blocked in
`DosCWait(DCWW_WAIT)` never returned, and the process ended at once rather than waiting for the
child. The termination code passed to the routine was 0 (`TC_EXIT`) for the `DosExit` cases and 3
(`TC_KILLPROCESS`) for the kill. Routines with equal order values ran last-added first. While
an exit routine runs, `PS_EXITLIST` is set in `pib_flstatus`. Each routine must finish by
calling `DosExitList` with `EXLST_EXIT`, which passes control to the next registered routine.

**`ordercode`** packs a function code (low byte) with an ordering value (upper bits) [DOC-IBM -
bsedos.h function codes]:

| Value | Constant | Meaning |
|---|---|---|
| 1 | `EXLST_ADD` | add `pfn` to the exit list (OR with an ordering byte, 0x00-0xFF) |
| 2 | `EXLST_REMOVE` | remove a previously added `pfn` |
| 3 | `EXLST_EXIT` | this routine is done; continue to the next exit-list routine |

For `EXLST_ADD`, the upper bits of `ordercode` carry an ordering value (0 = run earliest,
higher = later), letting cooperating routines sequence their cleanup.

---

## Critical sections and must-complete

### `DosEnterCritSec` / `DosExitCritSec` [DOC-IBM - bsedos.h]

```c
APIRET APIENTRY DosEnterCritSec(VOID);
APIRET APIENTRY DosExitCritSec(VOID);
```

`DosEnterCritSec` suspends **all other threads** of the calling process, giving the calling
thread exclusive run of the process until it calls `DosExitCritSec`. It is a coarse mutual-
exclusion mechanism for a whole process; the calls nest.

[DOC - EDM2 "DosExitCritSec (OS/2 1.x)"] An outstanding-entry count is kept: `DosEnterCritSec`
increments it, `DosExitCritSec` decrements it, and normal thread dispatching is only restored
when it returns to 0. An excess `DosExitCritSec` returns `ERROR_CRITSEC_UNDERFLOW`.

### `DosEnterMustComplete` / `DosExitMustComplete` [DOC-IBM - bsedos.h]

```c
APIRET APIENTRY DosEnterMustComplete(PULONG pulNesting);
APIRET APIENTRY DosExitMustComplete(PULONG pulNesting);
```

Bracket a region that must not be interrupted by signal/exception-driven termination, so a
critical update completes atomically with respect to asynchronous signals. `*pulNesting`
receives the resulting nesting level (these regions nest). The corresponding per-thread state is
visible in `TIB2.tib2_usMCCount` / `tib2_fMCForceFlag`.

---

## Information - `DosGetInfoBlocks` [DOC-IBM - bsedos.h]

```c
APIRET APIENTRY DosGetInfoBlocks(PTIB *pptib, PPIB *pppib);
```

Returns, without copying, pointers to the calling thread's TIB and the process's PIB.
`*pptib` receives the `PTIB`, `*pppib` the `PPIB`; either pointer argument may be `NULL` if that
block is not wanted. The structures are live kernel-maintained data mapped into the process - an
application reads them, it does not allocate them.

---

## Error codes [DOC-IBM - bseerr.h]

Values these calls return on failure (0 = `NO_ERROR` on success):

| Value | Constant | Typical cause |
|---|---|---|
| 1 | `ERROR_INVALID_FUNCTION` | invalid action/flag combination |
| 2 | `ERROR_FILE_NOT_FOUND` | `DosExecPgm`: program file not found |
| 8 | `ERROR_NOT_ENOUGH_MEMORY` | cannot allocate thread stack / process resources |
| 13 | `ERROR_INVALID_DATA` | malformed argument/environment block |
| 90 | `ERROR_NOT_FROZEN` | `DosResumeThread`: the thread was not suspended |
| 95 | `ERROR_INTERRUPT` | the wait was interrupted |
| 128 | `ERROR_WAIT_NO_CHILDREN` | `DosWaitChild`: no waitable children exist |
| 129 | `ERROR_CHILD_NOT_COMPLETE` | `DCWW_NOWAIT`: children exist but none has ended |
| 164 | `ERROR_MAX_THRDS_REACHED` | `DosCreateThread`: per-process thread limit reached |
| 228 | `ERROR_NO_CHILDREN` | no child processes |
| 294 | `ERROR_THREAD_NOT_TERMINATED` | `DosWaitThread` (`DCWW_NOWAIT`): thread still running |
| 303 | `ERROR_INVALID_PROCID` | unknown process ID |
| 304 | `ERROR_INVALID_PDELTA` | priority delta out of the `PRTYD_MINIMUM`..`PRTYD_MAXIMUM` range |
| 307 | `ERROR_INVALID_PCLASS` | invalid `PRTYC_*` class |
| 308 | `ERROR_INVALID_SCOPE` | invalid `PRTYS_*` scope |
| 309 | `ERROR_INVALID_THREADID` | unknown thread ID |
| 650 | `ERROR_NESTING_TOO_DEEP` | must-complete / critical-section nesting overflow |

**Additional per-call return codes documented by EDM2** (not in the header table above) [DOC]:

| Value | Constant | Call / meaning |
|---|---|---|
| 87 | `ERROR_INVALID_PARAMETER` | `DosCreateThread2`: bad parameter (e.g. stack address at/above 512MB) [DOC - EDM2 "DosCreateThread2"] |
| 115 | `ERROR_PROTECTION_VIOLATION` | `DosCreateThread2`: memory-protection violation [DOC - EDM2 "DosCreateThread2"] |
| 305 | `ERROR_NOT_DESCENDANT` | `DosKillProcess` (action `DKP_PROCESSTREE`): target is not the current process or one of its descendants [DOC - EDM2 "DosKillProcess (OS/2 1.x)"] |
| 322 | `ERROR_TS_WAKEUP` | `DosSleep`: the sleep was ended by something other than the interval running out - a forced action (an exit or a signal) delivered to the thread. 0 and 322 are the only returns [DOC-IBM `cp1.txt`, "DosSleep Return Value - ulrc"]. In the kernel the sleep is interruptible, `DosSleep(0xFFFFFFFF)` becomes a sleep of `0xFFFFFFFE` ms rather than an infinite one, and a suspend does not interrupt it [OBS-RE - the SMP kernel's `_VRSleep` / `_TKSleep`]. Measured on Warp Server for e-business 4.50: a thread sleeping 5000 ms whose process's other thread called `DosExit(EXIT_PROCESS)` 200 ms in (with a handler continuing `XCPT_ASYNC_PROCESS_TERMINATE`) got 322 after about 210-225 ms [OBS-RE - measured]. *(Previously "listed as a possible return (EDM2 does not further define it)".)* |
| 485 | `ERROR_CRITSEC_UNDERFLOW` | `DosExitCritSec`: more `DosExitCritSec` calls than matching `DosEnterCritSec` calls [DOC - EDM2 "DosExitCritSec (OS/2 1.x)"] |

---

## Related calls (out of scope here, cross-reference)

`DosCreateThread2`'s affinity companions `DosQueryThreadAffinity` / `DosSetThreadAffinity` (with
`MPAFFINITY`, `AFNTY_THREAD`/`AFNTY_SYSTEM`) and the thread-local-storage calls
`DosAllocThreadLocalMemory` / `DosFreeThreadLocalMemory` are declared alongside these in
`bsedos.h` [DOC-IBM]. `DosQueryAppType` (session-manager surface, `FAPPTYP_*`) reports a
program's type before executing it. See the memory-model and session-manager references for the
address-space and session context these operate in.

## See also
- `exceptions.md` - the per-thread TIB `FS:[0]` exception chain; `ipc-synchronization.md` - the primitives threads synchronize with; `session-manager.md` - session-level process control.
