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

**`tib_ordinal` is not the thread ID, although its name suggests it is.** IBM's reference
text gives it only as "thread ordinal number" [DOC-IBM]. The kernel's `_tkSetTIB`, which
fills the TIB on the thread's first return to ring 3, writes `tib2_ultid` from the word at
TCB+0 and `tib_ordinal` from the word at TCB+2 [OBS-RE - `os2krnl` debug kernel,
`_tkSetTIB` instructions `movzx ecx,word [ecx]` and `mov dx,[ecx+0x2]`; the SMP 14.104a
decompile of the same function agrees]. The Debugging Handbook names those two TCB cells:
TCB+0 is `TCBOrdinal`, "the unique thread id assigned to the thread within the process", and
TCB+2 is `TCBNumber`, the thread's system-wide slot [DOC-IBM - Debugging Handbook vol. 2].
So the names cross over. The TIB field called `tib_ordinal` holds the **slot number**, which
is system-wide, and the per-process thread ID (1 for the main thread) is found only in
`tib2_ultid`. Code that wants "which thread of this process am I" must read `tib2_ultid`.

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

**The environment segment a new process receives** [DOC-IBM - *Control Program Reference*,
`DosExecPgm`, parameter `pEnv`; the 16-bit *Programming Reference* `DosExecPgm` page gives the
same figure]: `eo:` the environment strings, then a byte of zeros; `po:` the fully qualified file
specification of the executable (IBM: "this name is copied into \"po\"", parameter `pName`);
`ao:` argument string 1 and argument string 2 (by the `CMD.EXE` convention, the program name as
entered and then its parameters), then a byte of zeros. `ao` is the command-line offset: a
16-bit program receives it in `BX` and from `DosGetEnv`; a 32-bit program on the stack at
`SS:[ESP+16]`. So the string immediately before `ao` is the program's fully qualified name.
[DOC] One C runtime relies on that, read in its published source: OpenWatcom's 16-bit
executable startup (`startup/os2/maino16.c`, `_OS2Main`, the arm built when the target is not a
DLL) takes its program name by backing up from `ao` to the previous null, citing "OS/2 2.0
docs", and its 32-bit DLL startup (`startup/386/dmaino32.c`, `__LibMain`, the arm for a DLL that
is not the runtime DLL) does the same from `pib_pchcmd`. Its 32-bit executable startup was not
found to read the program name this way.

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

## Process identifiers - width, allocation and reuse

A **PID is sixteen bits**, range `1..65535`. This is not a convention or an
implementation detail of one build; it is how the kernel is constructed, and the
32-bit API is a zero-extended *view* of it.

**NEGATIVE RESULT [DOC-IBM].** No IBM document states a PID range, width or
reuse behaviour. Searched: the *OS/2 Debugging Handbook* volumes I, II and IV,
the Control Program Guide and Reference, the Toolkit 4.5 headers, the DDK, and
the Developer Connection toolkits. The Control Program Reference does not
document `QSV_MAXPROCESSES` at all, and its `DosWaitChild` return-code list
(0/13/128/129/184/303) **omits 87**, which the shipped binary demonstrably
returns. The facts below therefore rest on reverse engineering and on live
measurement, and the binary wins where the two disagree. Do not go looking for a
document; it is not there.

### Width [OBS-RE]

| Evidence | What it shows |
|---|---|
| `_tkNewPid` (`os2krnl` obj17 `0x001A0514`) | increments a **WORD** counter (`inc ax`) |
| `PTDA+0x72a` (PPID `+0x72c`) | the PID is stored as a **WORD**. A whole-image scan of every 32-bit kernel object finds ~120 accesses to that offset and **every one is `movzx r32,word` or `mov r16` - zero dword loads**. Identical in all four kernel builds (smp/uni x base/debug); only the global's address moves, so this is a property of the family, not of one binary |
| `DOSCALL1!DOS32EXECPGM` | allocates a **16-bit** `RESULTCODES` on its own stack, calls the 16-bit worker, then widens with `lodsw / movzx / stosd` into the caller's 32-bit struct. IBM's own 32-bit `DosExecPgm` therefore **cannot** return a `codeTerminate` above `0xFFFF` |
| `_tkSetPIB` | `xor edx,edx / mov dx,[ecx+0x72a]` - `PIB.pib_ulpid`'s top 16 bits are always zero |
| `CWait` | truncates its argument on entry (`movzx ecx,cx`), compares 16-bit throughout, and packs the PID into the low half of its block token under an `0xffc2` tag - the wait-token encoding structurally requires a 16-bit PID |

The header split says the same thing: `typedef USHORT PID`
(`os21x/os2def.h:122`) against `typedef LHANDLE PID` (`os2def.h:233,76`), and
`RESULTCODES` as `{USHORT,USHORT}` (`os21x/bsedos.h:80`) against `{ULONG,ULONG}`
(`bsedos.h:181`).

### Out-of-range is rejected, not truncated [OBS - measured, Warp 4.50]

`DosWaitChild(DCWA_PROCESS, DCWW_NOWAIT, ...)`:

| PID passed | rc |
|---|---|
| a pid that fits but names no child | 128 `ERROR_WAIT_NO_CHILDREN` |
| 65535 | 128 |
| **65536** | **87 `ERROR_INVALID_PARAMETER`** |
| 957507 | **87** |

The boundary is exactly `0xFFFF`/`0x10000`, matching `DOS32WAITCHILD`'s own
guard in the shipped `DOSCALL1` (`cmp eax,0xffff / ja -> mov eax,0x57`). Note
that `957507 & 0xFFFF = 40003`, and the system does **not** answer as though
that truncated value had been passed - so truncating an out-of-range pid is not
an approximation of this behaviour, it is a different behaviour.

### Allocation and reuse [OBS-RE + OBS + testimony]

**The rule, stated plainly:** a pid is **always the next available number**,
counting up; on overflow the counter wraps and again takes the next available
number. Nothing is reserved and nothing is hashed - it is a counter with a
skip-if-taken check. (Maintainer testimony 2026-08-19, from a decade of daily
OS/2 use; independently matched by the disassembly below, which is why it is
recorded here as the rule rather than as one observer's impression.)


`_tkNewPid` increments a WORD counter and skips the wrap-to-zero. On its slow
path it scans the task list **and the zombie-PTDA chain**, skipping any
candidate already in use - so pids **wrap and are reused**, and a pid is not
recycled while a terminated process's record can still be claimed.

Measured live (Warp 4.50): 25 consecutive spawns produced `242, 248, ... 386` -
monotone, +1 per creation. `QSV_MAXPROCESSES` returns **1025**, so the
concurrency bound is far below the pid space and wrap is rare in practice.
Observed values elsewhere: PID 1 for kernel threads, 2 for `PMSHELL`, and
ordinary children in the low hundreds (159 measured).

A full round trip, measured: `DosExecPgm(EXEC_ASYNCRESULT)` ->
`codeTerminate=411` -> `DosWaitChild(411)` -> `rc=0, outpid=411`, with the child
independently confirming its own pid as 411.

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

**Measured return codes for process creation and waiting** [OBS - measured on Warp Server for
e-business 4.50, kernel revision 14.089, 32-bit probe; codes named from `bseerr.h`]:

| Call and input | Result |
|---|---|
| `DosWaitChild` with no children at all | 128 `ERROR_WAIT_NO_CHILDREN` |
| `DosWaitChild` on an `EXEC_ASYNCRESULT` child already collected | 128 |
| `DosWaitChild(DCWW_NOWAIT)` on a running child | 129 `ERROR_CHILD_NOT_COMPLETE` |
| `DosWaitChild(DCWW_WAIT)` on a running **`EXEC_ASYNC`** child (no result kept) | blocks **until that child ends**, then returns 128 |
| `DosWaitChild` naming the caller's own pid, or pid 0xFFF0 | 128 (not 184 or 303) |
| `DosWaitChild` with action 5, or option 5 | 13 `ERROR_INVALID_DATA` (not 87) |
| `DosExecPgm`, missing program | 2; the object-name buffer holds the name as passed |
| `DosExecPgm`, missing directory | 3; object name as passed, upper-cased |
| `DosExecPgm`, a text file named `.EXE` | 193 `ERROR_BAD_EXE_FORMAT`; object name the full upper-cased path |
| `DosExecPgm`, a program importing from a missing DLL | 2; the object name is the **DLL's** module name |
| `DosExecPgm`, exec flag 7 | 13 |
| `EXEC_SYNC` child exiting with 70000 | `codeResult` 4464 - the result is a 16-bit value (70000 mod 65536) |
| `DosKillProcess` of a child, then `DosWaitChild` | 0, then `codeTerminate` 3 (`TC_KILLPROCESS`) |
| `DosKillProcess` of a child that has ended but not been collected | 303 |
| `DosKillProcess` with action 5 | 13 |

A handle opened `OPEN_FLAGS_NOINHERIT` reads as 6 (`ERROR_INVALID_HANDLE`) in the child; the child
starts in the parent's current drive and directory with the parent's verify setting. **The tell:**
a "hang" in `DosWaitChild` on a child you started `EXEC_ASYNC` - it is waiting for that child to
end, and will then report 128 because there is no result to give.

### `DosKillProcess` [DOC-IBM - bsedos.h]

```c
APIRET APIENTRY DosKillProcess(ULONG action, PID pid);
```

| `action` | Constant | Scope |
|---|---|---|
| 0 | `DKP_PROCESSTREE` | terminate the process and its descendant tree |
| 1 | `DKP_PROCESS` | terminate only the named process |

What the target sees [DOC-IBM `cp1.txt` "DosKillProcess - Remarks", `cp2.txt` "Signal Exceptions"]:
the KILLPROCESS exception (`XCPT_SIGNAL`, `ExceptionInfo[0]` = `XCPT_SIGNAL_KILLPROC`), sent **only to
thread 1**, delivered **whether or not** the process called `DosSetSignalExceptionFocus`. A handler may
intercept it; otherwise the process ends and its parent's `DosWaitChild` gets termination code 3.
Measured [OBS: WSeB 4.50 revision 14.089, 2026-09-30; a parent starting a child `EXEC_ASYNCRESULT`,
waiting 1.5 s while the child sleeps in `DosSleep(10000)`, then `DosKillProcess(DKP_PROCESS, pid)` and
`DosWaitChild`]:
- no handler: `DosKillProcess` 0; `DosWaitChild` 0, `codeTerminate` 3, `codeResult` 0;
- thread 1's handler answers `XCPT_CONTINUE_EXECUTION` to `XCPT_SIGNAL_KILLPROC`: **the child's
  `DosSleep` returns 322 `ERROR_TS_WAKEUP`** and the child runs on to its own `DosExit` -
  `codeTerminate` 0 and the child's own result.

---

## Thread creation and control

### System-wide thread limit - CONFIG.SYS `THREADS=` [DOC-IBM - OS/2 online help for the CONFIG.SYS `THREADS` statement]

The system supports a maximum of **4095 threads**, allocated across the kernel itself and every
application running on it - a **system-wide** pool, not a per-process limit. The `THREADS=`
statement in CONFIG.SYS sets the pool size; with no `THREADS` statement, the default is **64**.
IBM's own guidance: reducing the count while running complex applications or system extensions
can force activities that could run concurrently to run serially, slowing performance.

A process that exhausts the pool sees `DosCreateThread` fail with `ERROR_MAX_THRDS_REACHED`
(164) - see the error-code table below.

*Attribution: quoted verbatim from the OS/2 online help for the CONFIG.SYS `THREADS` statement
by the author, 2026-08-13 (the containing .INF is not in this tree - checked, zero in-tree
hits for "4095 threads" before this entry). The "default is 64" figure was author-corrected
from a truncated paste that read "6".*

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
A `cbStack` of **0** is refused with **87** `ERROR_INVALID_PARAMETER`; 1 succeeds (`[OBS]`, measured
on WSeB 4.50 revision 14.089 SMP; `[OBS-RE]` the kernel's 32-bit `DosCreateThread` entry checks it).

**`flag` bits** [DOC-IBM - bsedos.h]:

| Value | Constant | Meaning |
|---|---|---|
| 0 | `CREATE_READY` | start the thread immediately (ready to run) |
| 1 | `CREATE_SUSPENDED` | create the thread suspended; a later `DosResumeThread` starts it |
| 0 | `STACK_SPARSE` | reserve stack, commit pages on demand |
| 2 | `STACK_COMMITTED` | commit the whole stack up front |

**Measured behaviour** [OBS - measured on Warp Server for e-business 4.50, kernel revision
14.089, retail SMP, 32-bit probe; three concurrent copies agreed]:

- **TIDs are reused lowest-first.** With threads 2 and 3 alive and 4 ended, the next thread
  created got TID 4. The main thread is TID 1, and a new thread's `tib2_ultid` matches the TID
  returned in `*ptid`.
- **A bad `ptid` faults; it does not return 115.** Passing `ptid` = 0x10, or a pointer into
  read-only code, ended the calling process with an exception (`codeTerminate` 4,
  `TC_EXCEPTION`), not `ERROR_PROTECTION_VIOLATION`.
- **The thread ceiling.** On a system with `THREADS=1024` in CONFIG.SYS, one process created 897
  threads before `DosCreateThread` returned 164 `ERROR_MAX_THRDS_REACHED`. The limit is system-wide
  (`THREADS=` counts every process's threads), so the number a program reaches depends on what
  else is running.
- `CREATE_SUSPENDED` threads do not run until `DosResumeThread`; `DosWaitThread` with TID 0 returns
  whichever thread ended, `DCWW_NOWAIT` on a live thread returns 294 `ERROR_THREAD_NOT_TERMINATED`,
  and a TID never created returns 309 `ERROR_INVALID_THREADID`.

`DosVerifyPidTid(pid, tid)`, measured [OBS - same system]: the caller's own pid with TID 1
returns 0, with TID 99 or TID 0 returns 309 `ERROR_INVALID_THREADID`; pid 0 and pid 0xFFFF return
303 `ERROR_INVALID_PROCID`; a live child's TID 1 returns 0 and its unused TID 2 returns 309; a child
that has ended returns 303.

A 16-bit thread created by `DosCreateThread` starts with a usable `DS` (measured, 16-bit probe with
its stack in its own `DosAllocSeg` segment).

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

> **Provenance corrected 2026-08-31 (Rule 1.7).** 3 claims in this document
> were tagged `[OBS-RE]` and are now `[OBS]`. **No claim changed** - only the
> label for how it was established. `[OBS-RE]` means *read out of a binary or the
> kernel debugger*, an interpretation; `[OBS]` means *a capture from a running
> system*, no interpretation. Each of these was a probe run on real OS/2 whose
> return codes were recorded, so `[OBS]` is the tag, and the re-verification is
> "run the probe again" rather than "read the bytes again". The two had drifted
> because `[OBS]` was in use throughout the corpus with **no definition at all**
> until that date; see `README.md`, *Provenance*.

**A terminated thread's TID stops being waitable if nothing was already blocked in
`DosWaitThread` for it - `[OBS]`, measured 2026-08-18, real OS/2 (WSEB Warp, `a Warp Server for e-business system`),
not documented in any IBM source found so far.** Create N short-lived threads, let them all
genuinely finish (confirmed via each thread's own completion flag, plus a real elapsed delay),
*then* call `DosWaitThread` for each by its recorded TID: every call returns
`ERROR_INVALID_THREADID` (309), even though the thread ran to completion and its TID was never
reused for anything else. The **`*ptid = 0`** ("wait for any next thread") form fails identically
once every thread has already terminated with nothing having been blocked waiting - it is not
specific-TID-vs-any that matters. This does **not** contradict the EDM2 "reclaim an ended thread's
resources" framing above - it sharpens it: unlike a POSIX `pthread_join`, which can reap a thread
at any point after it exits (the exited thread persists in a joinable/zombie state until then), OS/2
does not appear to retain that state past termination unless a `DosWaitThread` call is already
outstanding for it (specific TID) or for "any" thread. A caller that creates a batch of threads and
plans to reap them all in a later, separate loop - a completely ordinary pattern under POSIX
threading - will lose the race for any thread that finishes before its turn in that loop comes up.
The safe pattern is to synchronize on each thread's own completion (an event semaphore, or a
polled flag the thread sets before returning) and treat `DosWaitThread` as best-effort resource
reclamation afterward, not as the actual completion signal. Found via a
concurrent `DosOpen` stress probe's thread-join helper, whose own comment
project-side has the reproduction.

**Two `DosWaitThread` calls outstanding for the SAME terminating thread - one
wait-specific, one wait-for-any (`*ptid = 0`) - BOTH return `NO_ERROR` with that
thread's TID; neither gets `ERROR_INVALID_THREADID`. `[OBS]`, measured
2026-08-23, real OS/2 (WSeB Warp 4.5, OS/2 2.45).** A target thread is left
running; a second thread blocks in `DosWaitThread(&targetTID, DCWW_WAIT)` and a
third blocks in `DosWaitThread(&0, DCWW_WAIT)`; the target then terminates. Both
waiters wake, both return `0`, and both report the target's TID (measured
identically across three runs). So a termination with two waits outstanding is
delivered to BOTH - the specific waiter and the "any" waiter each observe it -
rather than the kernel handing the thread to exactly one and failing the other.
This is only reachable while the waits are ALREADY BLOCKED before termination:
consistent with the paragraph above, once the target has terminated with nothing
outstanding, a later `DosWaitThread` cannot reach it - a specific wait returns
`ERROR_INVALID_THREADID` (309) and an `*ptid = 0` wait returns
`ERROR_THREAD_NOT_TERMINATED` (294) with `*ptid` left 0 (no thread waitable),
both measured. The practical consequence for a caller is unchanged: do not build
on which waiter "owns" a termination - synchronize on the thread's own
completion signal (above) and treat `DosWaitThread` as best-effort reclamation.

**A terminated-and-reaped thread's resources are fully released, so an
unbounded create/reap loop never exhausts memory - `[OBS]`, measured
2026-08-22, real OS/2 (Warp 4.5, `a Warp Server for e-business system`).** Creating threads in batches
of 8, flag-polling each to completion, then `DosWaitThread`-reaping each, for
2000 threads per run - both with each worker idle and with each worker doing one
`DosCreateDir`+`DosDeleteDir` - sustains with no `ERROR_NOT_ENOUGH_MEMORY` (8)
at any count (`CTLOOP.EXE`; a `DosCreateThread` stress probe reproduces the
same at 5600/arm on real OS/2). So a thread's stack and per-thread kernel state
are reclaimed at termination, not merely reserved for the process lifetime, and
`DosCreateThread` failing after a few hundred create/reap cycles is not faithful
behaviour.

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

**Return codes, and what interrupts a sleep.** `DosSleep` returns `0` or `322`
`ERROR_TS_WAKEUP` [DOC-IBM `cp1.txt`, "DosSleep"]. In the kernel [OBS-RE: the SMP kernel's 32-bit
`DosSleep` worker, `_VRSleep`, and the sleep primitive `_TKSleep` it calls]: `DosSleep(0)` yields;
`DosSleep(0xFFFFFFFF)` becomes a sleep of `0xFFFFFFFE` ms (about 49.7 days), not an infinite one;
any other interval is an **interruptible** sleep on an address nothing else wakes, and the call
returns `0` if the interval ran out and `322` for anything else. A forced action delivered to the
thread - an exit or a signal - ends the sleep at once, and one already pending ends it before it
starts; a suspend (a freeze) does not interrupt it. Measured [OBS: WSeB 4.50 revision 14.089, SMP
kernel, 2026-09-30]: a thread sleeping 5000 ms, whose process's other thread called
`DosExit(EXIT_PROCESS, ...)` 200 ms in, with an exception handler that continued
`XCPT_ASYNC_PROCESS_TERMINATE`, saw `DosSleep` return `322` after 211-225 ms; `DosSleep(200)`
measured 211-234 ms by `QSV_MS_COUNT` (a 31 ms tick).

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

### Dynamic priority variation - the six boosts  `[DOC-IBM]` + `[OBS-RE]`

`DosSetPriority` sets a thread's **class** and **delta**. Those are not the whole
of its dispatch priority: the scheduler adds a set of **priority-class modifier
bits** - *boosts* - and the final priority is computed from class, modifiers and
delta together.

**The six modifiers** `[DOC-IBM]` (*OS/2 Debugging Handbook*, `TCBPriClassMod`
Definitions):

| Bit | Constant | Boost |
|---|---|---|
| `0x04` | `CLASSMOD_KEYBOARD` | keyboard |
| `0x08` | `CLASSMOD_STARVED` | processor starvation |
| `0x10` | `CLASSMOD_DEVICE` | device I/O done |
| `0x20` | `CLASSMOD_FOREGROUND` | foreground |
| `0x40` | `CLASSMOD_WINDOW` | window |
| `0x80` | `CLASSMOD_VDM_INTERRUPT` | VDM simulated interrupt |

**How they combine** `[DOC-IBM]`: *"Priority class and modifier values are
logically ORed to form an index into the priority class translation table, which
is located at global symbol `_schPriClassTbl`. The resulting value is logically
ORed with the priority level. The final value is subject to the minimum thread
priority (`TCBPriorityMin`)."* So a boost is **not** a delta added to the
priority - it selects a different row of a published table, and the delta is
ORed into the low bits of whatever that row yields. The table itself is printed
in the handbook.

**What the table says about magnitude** `[DOC-IBM]`, reading the unboosted row
against the window-boost row:

| class | no boost | window boost |
|---|---|---|
| Regular | `0x200` | `0x500` |
| Foreground-server | `0x300` | `0x500` |
| Idle | `0x100` | `0x100` |
| Time-critical | `0x800` | `0x800` |

Hence the handbook's three rules: *"Priority boosts do not affect the priority of
idle and time-critical threads"*; *"Priority level has little or no effect on the
priority of boosted regular and server class threads"* - a boosted regular thread
outranks **any** unboosted regular thread whatever its delta; and
*"`CLASSMOD_KEYBOARD` has no effect on `CLASS_SERVER`"*.

**Boosts are counted, not flagged.** The TCB carries `TCBcWindowBoost`,
*"Window Boost count"* `[DOC-IBM]`, alongside the class fields. The modifier bit
moves only on the 0->1 and 1->0 transitions of that count, so *N* boosts require
*N* releases `[OBS-RE]`.

**Boosts are a configuration option, and turning them off is supported**
`[DOC-IBM]`: the `PRIORITY=` CONFIG.SYS statement selects `DYNAMIC` (the
default), under which *"I/O priority boosts are generated for keyboard input,
window, foreground, processor starvation, device I/O, and DOS Session
interrupts"*, or `ABSOLUTE`, which *"performs no calculation. There is no
system-applied boost for foreground ... Only the application can adjust the
priority of the threads."* A single Global InfoSeg field, `SIS_Dynamic`
(*"Dynamic variation flag (1=enabled)"*, offset `0x1E`) `[DOC-IBM infoseg.h]`,
carries that setting, and at least one boost routine tests it directly and
becomes a no-op when it is clear `[OBS-RE]`.

**Relation to `DosSetPriority`.** The two are orthogonal axes that meet in one
expression: the API owns **class** and **delta**, the scheduler owns the
**modifier bits**, and `_schPriClassTbl` combines them. Under `ABSOLUTE` only the
API moves anything. IBM's own advice to a thread being starved by another
thread's boost is either to set `PRIORITY=ABSOLUTE` or *"to call `DosSetPriority`
on a regular basis to keep the thread's priority at the desired level"*
`[DOC-IBM]` - i.e. the boost is not something an application can clear, only
out-bid.

**Which boosts decay and which do not** `[OBS-RE]`. The starvation and device-I/O
bits are set and cleared continuously by the scheduler's own timeslice, sleep and
wake paths. The **window** bit is not touched by any of them: it is held until
explicitly released, or until the thread terminates and its control block is
re-initialised for the slot's next occupant. Treating the window boost as
self-expiring is therefore wrong.

**The window boost has two entry points, and they do not share a count**
`[OBS-RE]`. One is the scope-dispatched foreground call described in
`session-manager.md`; the other is the device-help routine `ModifyPriority`
(DevHlp `0x2C`), which IBM's own `devhlp.inc` annotates *"Undocumented (used by
PM)"* `[DOC-IBM]`. Both take a **thread slot number**, both bounds-check it
against the thread-slot table, and both honour the same per-thread latch - but
the DevHlp is an uncounted toggle gated on the bit itself, and it is **not**
gated on `SIS_Dynamic`, so it boosts under `PRIORITY=ABSOLUTE` where the
foreground call does nothing. Mixing the two therefore desynchronises the count
from the bit.

---

## Termination handlers - `DosExitList` [DOC-IBM - bsedos.h]

```c
typedef VOID APIENTRY FNEXITLIST(ULONG);
typedef FNEXITLIST *PFNEXITLIST;

APIRET APIENTRY DosExitList(ULONG ordercode, PFNEXITLIST pfn);
```

Registers (or removes) a routine to run when the process terminates. Exit-list routines execute,
in a defined order, ~~on the process's last surviving thread during `EXIT_PROCESS` shutdown~~
on **thread 1**, after every other thread of the process has ended, however the process began to
end - `DosExit(EXIT_PROCESS)` from any thread, any `DosExit` from thread 1 (including thread 1's
function returning), or a kill that nothing intercepts **[OBS-RE, SMP debug kernel, `_TKExit`,
`_TKDieSoonPTDA`, `_TKTermThread`, 2026-09-26]**. Measured the same way from a 16-bit program on
Warp 4.50 (revision 14.089, retail SMP), 2026-09-26 **[OBS]**, for `DosExit(EXIT_PROCESS)` from a
second thread (with thread 1 sleeping, and with thread 1 in a pure loop), from thread 1,
`DosExit(EXIT_THREAD)` from thread 1, `main` returning, `DosKillProcess` of the process itself, and a
second thread blocked in `DosCWait(DCWW_WAIT)` on a sleeping child (and the same with thread 1 the
blocked one): in every case the routine runs with `tidCurrent` 1, a sleeping and a spinning thread
make no further progress, the blocked `DosCWait` never returns and the process ends at once rather
than waiting for the child, and the routine's own `DosCWait(DCWW_NOWAIT)` on that child answers 129
(`ERROR_CHILD_NOT_COMPLETE`). The termination code passed to the routine is 0 (`TC_EXIT`) for the
`DosExit` cases and 3 (`TC_KILLPROCESS`) for the kill, whose parent sees `RESULTCODES` 3/0; the
parent sees the `DosExit` result for the others (the `main` return value for `main` returning).
Routines of equal order run last-added first **[DOC-IBM cp1.txt "DosExitList Parameter -
ordercode"; OBS, same machine and date]**. While
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

**Measured** [OBS - measured on Warp Server for e-business 4.50, kernel revision 14.089, a
32-bit program with a 32-bit DLL; codes named from `bseerr.h`]:

| Input | Result |
|---|---|
| `EXLST_ADD` of a routine already on the list (same order value) | 183 `ERROR_ALREADY_EXISTS` |
| the same routine added again with a different order value | 0 - a second, separate record |
| `EXLST_REMOVE` with an order byte set | 13 `ERROR_INVALID_DATA` |
| `EXLST_REMOVE` (no order byte) | 0, and again 0 - one record each time |
| `EXLST_REMOVE` once nothing is left | 127 |
| `EXLST_EXIT` outside an exit, or function code 4 | 1 |
| `EXLST_ADD` with bit 0x40 set in the function byte | 1 - refused |
| `DosFreeModule` of a DLL that has a routine on the list | 12, and the routine still runs at exit |
| `DosExecPgm` from inside an exit-list routine | 1 - refused while exit processing runs |

- **Order:** the order value only sorts, lowest first. Bit 0x80 of the *function* byte puts that
  routine ahead of all others whatever its order value. A DLL's own termination routine runs
  after every exit-list routine.
- **One routine's failure does not stop the next:** a routine that faults with no handler, or
  calls `DosExit(EXIT_PROCESS)`, is followed by the next routine on the list.
- The termination code a routine receives for an unhandled trap on thread 1 is 4 (`TC_EXCEPTION`).
- Inside a routine, `pib_flstatus` has `PS_EXITLIST` (0x01) set (0x27 in an `EXEC_SYNC` child).

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
when it returns to 0. An excess `DosExitCritSec` returns `ERROR_CRITSEC_UNDERFLOW`. The count is
kept in a **word**; on overflow it is pinned at its maximum, **no operation is performed**, and the
call returns an error.

**Return codes** [DOC-IBM - `bseerr.h`]:

| Code | Name | Raised by |
|---|---|---|
| 0 | `NO_ERROR` | both |
| 484 | `ERROR_CRITSEC_OVERFLOW` | `DosEnterCritSec`, nesting count would wrap |
| 485 | `ERROR_CRITSEC_UNDERFLOW` | `DosExitCritSec`, count already 0 |
| 309 | `ERROR_INVALID_THREADID` | `DosEnterCritSec`, another thread already owns it |

**The kernel's own implementation** [OBS-RE - `os2krnl` UNI, decompiled]. Both public entry points
are thin wrappers over near workers, and these are the exact semantics:

```c
w_EnterCritSec @ 000f:9232
    if (owner == 0 || owner == pTCBCur) {      /* owning TCB slot */
        if (++count == 0) { --count; return 0x1e4; }   /* 484, pinned */
        owner = pTCBCur; return 0;
    }
    return 0x135;                                       /* 309 */

w_ExitCritSec @ 000f:92ba
    if (count == 0) return 0x1e5;                       /* 485 */
    if (--count == 0) { owner = 0; /* reschedule */ }
    return 0;
```

Two details worth having: the kernel tracks an **owning TCB**, not merely a count - so a second
thread calling `DosEnterCritSec` while another owns the section is refused rather than allowed to
take it over. And `w_ExitCritSec` **does not validate the caller against that owner**; it does not
need to, since every other thread is suspended and only the owner can be running to call it.

**Measured** [OBS - measured on Warp Server for e-business 4.50, kernel revision 14.089, retail
SMP; one functional run and two concurrent stress copies]: `DosExitCritSec` without an entry
returns 485 `ERROR_CRITSEC_UNDERFLOW`; after one `DosExitCritSec` of two nested entries the other
threads are still frozen; nesting is refused after **65,535** entries with 484
`ERROR_CRITSEC_OVERFLOW`. Under contention, a thread calling `DosEnterCritSec` while another
thread of the process holds it gets 309 `ERROR_INVALID_THREADID`, and its matching
`DosExitCritSec` then returns 485. **The tell:** code that treats `DosEnterCritSec` as unable to
fail runs its "protected" region unprotected whenever two threads race to enter - check the return
code.

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
| 322 | `ERROR_TS_WAKEUP` | `DosSleep`: the sleep was interrupted (an exit or signal forced action) rather than timed out - see `DosSleep` above [DOC - EDM2 "DosSleep (FAPI)"; OBS-RE; OBS] |
| 485 | `ERROR_CRITSEC_UNDERFLOW` | `DosExitCritSec`: more `DosExitCritSec` calls than matching `DosEnterCritSec` calls [DOC - EDM2 "DosExitCritSec (OS/2 1.x)"] |

---

## Thread Local Memory Area (TLMA)

`DosAllocThreadLocalMemory` / `DosFreeThreadLocalMemory` allocate from a per-thread region
called the **Thread Local Memory Area (TLMA)**.

**Size and allocation granularity** [DOC-IBM, *Control Program Guide*, `cp3.txt`]:

> "The thread local memory region is **32 DWORDS** (4 bytes per DWORD) in size, and up to
> **8 DWORDS** can be allocated with each call to `DosAllocThreadLocalMemory`. To allocate
> more than 8 DWORDS, a thread must call `DosAllocThreadLocalMemory` more than once."

The same text warns that thread local memory "should be used sparingly" and that an
application should not consume the whole 128-byte region.

**How it is made per-thread - the part that is easy to get wrong** [DOC-IBM, *OS/2 Debugging
Handbook* Vol. I glossary and Vol. II]:

> "The Thread Local Memory Area (TLMA) [is] an area of private arena memory that is
> instantiated at a thread level. This is achieved by **copying the contents of the TLMA to
> `dfff:0024` when a thread switch occurs**. The TLMA contents are saved in the TCB at
> `TCBTLMA`."

> "Descriptor `dfff` maps a global shared memory object, but its data is **copied from the
> incoming PTDA and TCB when a context switch occurs**. This achieves the effect of thread
> local memory."

So the TLMA is **not** a distinct mapping per thread. It lives at **one fixed address, shared
by every thread**, and the kernel gives it per-thread semantics by **copying its contents in
and out on every context switch**, saving the outgoing thread's copy into that thread's TCB.

Consequences that follow directly, and matter to anyone reimplementing this:
- A pointer returned by `DosAllocThreadLocalMemory` is **the same address in every thread**.
  Caching it in per-process (even global) storage is therefore correct and is what real code
  does - the value never varies; only the memory behind it is swapped.
- Reading the TLMA in a debugger shows **the current thread's** contents only. Another
  thread's copy must be read from that thread's `TCBTLMA`.

**Layout and bookkeeping** [DOC-IBM, *Debugging Handbook* Vol. IV structure tables, Vol. I]:

| item | location | size | note |
|---|---|---|---|
| `TCBTLMA` | TCB `+0x74` (`+0x78` after Warp 3 FixPak 7) | `0x80` (128 bytes) | the saved per-thread copy; matches the 32 DWORDs above |
| TLMA itself | LDT descriptor `dfff`, immediately after the LIS - **`dfff:0024` on UNI, `dfff:002C` on SMP** (see below) | - | tiled selector `0xDFFF` -> flat `0x1BFF0000` |
| `ptda_TLMA` | PTDA | 4 | "in use flag and dword copy" |
| `ptda_TLMABM` | PTDA | 4 | allocation bitmap |
| `ptda_TLMASizeMap` | PTDA | `0x20` | per-allocation size map |

**The offset depends on the kernel flavour, and this is easy to get wrong.** The LIS
(`InfoSegLDT`) is mapped at `dfff:0000` and the TLMA begins immediately after it, so the TLMA's
offset *is* `sizeof(InfoSegLDT)`:

- **UNI: 36 bytes (`0x24`)** -> TLMA at `dfff:0024`, which is the figure the *Debugging Handbook*
  quotes (a February 1996, Warp-3-era book).
- **SMP: 44 bytes (`0x2C`)** -> TLMA at `dfff:002C`. The SMP `InfoSegLDT` appends two fields
  [DOC-IBM, DDK `base/h/infoseg.h`]:
  ```c
  #ifdef SMP
  unsigned long   LIS_pTIB;       /* Pointer to TIB */
  unsigned long   LIS_pPIB;       /* Pointer to PIB */
  #endif
  ```
> **RETAGGED `[OBS]`, THEN RESTORED TO `[OBS-RE]` - 2026-08-31 (Rule 1.7).**
> A third correction pass moved the claim below from `[OBS-RE]` to `[OBS]`,
> reasoning that "the value is a RETURN VALUE from a live call" and that a ring-3
> probe reading memory is still a capture. The tag is restored, and the reason is
> **not** that the value is unreachable from ring 3 - it is reachable, and saying
> otherwise was the retag's mirror-image error.
>
> **What makes this `[OBS-RE]` is the ATTRIBUTION, not the value.** The claim is
> not "this cell holds `0x1BFF002C`" - a ring-3 read after initialisation returns
> that in every process. The claim is that the value is *the out-parameter of the
> first `DosAllocThreadLocalMemory` call `PMMERGE` makes during `WinInitTerm`*,
> and nothing you can read at run time says so. That step comes from
> disassembling the gate and resolving its import from the module's own fixup
> record - an interpretation of the binary, re-verified by reading the bytes
> again, which is what `[OBS-RE]` names (`README.md`, *Provenance*). A capture
> gives you the number; only the binary tells you which call site produced it.
> (Precisely: the fixup record yields an *ordinal*, `DOSCALLS.#454`. Putting the
> name `DosAllocThreadLocalMemory` to that ordinal is a separate step resting on
> published ordinal lists - a weaker source, and one this corpus never treats as
> authority. The tag is unaffected: the interpretive step it turns on is that
> this cell is the out-parameter of the call at that site, which is read from
> the binary alone.)
>
> **The site does not name its own instrument, and that is the general case.**
> The tag is settled by what the load-bearing step requires, not by anything the
> site says. A keyword sweep cannot decide that; only a semantic read of each
> remaining `[OBS-RE]` claim can.

  Corroborated `[OBS-RE]` (2026-08-02; the instrument is not recorded at the
  site - the tag rests on the attribution being established by disassembly, see
  the note above): on a live Warp Server for e-business kernel,
  `PMMERGE`'s own first `DosAllocThreadLocalMemory(7, &p)` during `WinInitTerm` returns
  **`0x1BFF002C`** - i.e. slot 0 of a TLMA based at `0x2C`, not slot 2 of one based at `0x24`.

**Field detail, from IBM's own worked example** [DOC-IBM, Vol. I, "Exploring 32-bit Presentation
Manager Under WARP" - a live `dd %<tcb>+74` dump]:

| offset in TLMA | contents |
|---|---|
| `+0x08` | last PM error on this thread (the example shows `00041304`, severity 4 / `PMERR_NOT_IN_IDX`) |
| `+0x0c` | the PMQ - pointer to this thread's PM message queue |

Vol. I's prose says "offset `+0x0c` into the TLMA are the AAB registers"; its own dump puts the
error word at `+0x08` and the queue pointer at `+0x0c`. Prefer the dump.

**Principal consumer - PM.** "A PM Application Anchor Block is allocated in the Thread Local
Memory Area (TLMA) when a PM application thread creates a message queue. The AAB contains a
pointer to the MQ which allows PM to find the MQ in any context." [DOC-IBM, Vol. I] Because the
TLMA is saved in each thread's TCB, a debugger can locate the message queue of any PM thread in
the system.

## How this survives SMP - one linear address, per-processor memory

The copy-on-context-switch mechanism above cannot work as literally stated on a multiprocessor:
two threads of one process, running on two CPUs, both reach `dfff:0024`, and repainting on
switch-in cannot give them different contents at one address.

**OS/2 resolves this with per-processor aliasing of a linear address, and IBM documents the
mechanism** [DOC-IBM, *SMP Programming Addendum*, `SMP.INF`, describing a Platform Specific
Driver's Processor Local Memory Area]:

> "pPSDPLMA points to the PSD's processor local memory area. **This area contains different
> physical memory at the same linear address across all processors.** You can use the area to
> store variables such that each processor accesses unique values, but all the code references
> the same variables."

That is stated for the PSD's PLMA (256 bytes, minimum guaranteed size), not for the TLMA.
**`[INF]`** - but it is the mechanism that makes the TLMA coherent on SMP, and no other is
available: each CPU has its own physical page behind `dfff`, and the kernel repaints *that
CPU's* copy for the thread it schedules there. The consequence worth carrying:

> **The number of live TLMA copies equals the PROCESSOR count, not the thread count.** Correctness
> then follows from "one thread runs per CPU at a time" - which is free. On a uniprocessor there
> is exactly one copy and exactly one running thread, and the plain copy-on-switch description is
> literally true.

**Negative result** [Rule 1.6 - expensive to establish, free to record]: the *Debugging
Handbook* does **not** document any SMP structure variants. Its TCB and PTDA tables vary by
version and fixpack only (Warp V3.0, +FixPak, +FixPak 11, V2.11, V2.11+FixPak 90; ALLSTRICT vs
RETAIL), and its SMP content is spin-lock and serialization guidance. Do not re-search it for
per-CPU layout; the *SMP Programming Addendum* is where the SMP architecture lives.

## Related calls (out of scope here, cross-reference)

`DosCreateThread2`'s affinity companions `DosQueryThreadAffinity` / `DosSetThreadAffinity` (with
`MPAFFINITY`, `AFNTY_THREAD`/`AFNTY_SYSTEM`) are declared alongside these in `bsedos.h`
[DOC-IBM]; the thread-local-storage calls are described under "Thread Local Memory Area"
above. `DosQueryAppType` (session-manager surface, `FAPPTYP_*`) reports a
program's type before executing it. See the memory-model and session-manager references for the
address-space and session context these operate in.

## See also
- `exceptions.md` - the per-thread TIB `FS:[0]` exception chain; `ipc-synchronization.md` - the primitives threads synchronize with; `session-manager.md` - session-level process control.
