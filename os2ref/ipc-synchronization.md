# OS/2 IPC and Synchronization API

The 32-bit OS/2 inter-process communication and thread-synchronization surface: the three
kinds of 32-bit semaphore (mutex, event, and muxwait) with their named `\SEM32\` model and
`HMTX` / `HEV` / `HMUX` handle types; anonymous and named pipes (`\PIPE\`); and the queue
API (`\QUEUES\`). All of these are kernel objects with system-wide names, created private by
default and shared either by giving them a name or by requesting the shared attribute
explicitly. Waiting operations share one timeout convention: a millisecond count, with
`SEM_INDEFINITE_WAIT` (-1) meaning block forever and `SEM_IMMEDIATE_RETURN` (0) meaning poll
and return at once.

Sections 1-4 describe the 32-bit (OS/2 2.0 and later) surface. The older **16-bit `DosSemXxx`
family and its RAM semaphores** - still used internally by shipped Presentation Manager code -
are in section 5.

Provenance: **[DOC-IBM]** OS/2 Toolkit 4.5 header `bsedos.h` (all function prototypes,
semaphore/pipe/queue constants, and structure layouts) and `bseerr.h` (error-code values);
**[DOC]** the IBM Control Program Guide and Reference for the `\SEM32\` / `\PIPE\` / `\QUEUES\`
naming conventions and the object-lifetime semantics; **[OBS-RE]** noted where a behavior is an
observation rather than a documented rule.

---

## 1. Semaphores

OS/2 provides three distinct 32-bit semaphore types, all declared under `INCL_DOSSEMAPHORES`.
Each is a `ULONG` handle. **[DOC-IBM - `bsedos.h`]**

| Type | Handle | Purpose |
|---|---|---|
| Mutex semaphore | `HMTX` (`typedef ULONG HMTX`) | Mutual-exclusion lock; one owner at a time, ownership-tracked, nestable by the owner. |
| Event semaphore | `HEV` (`typedef ULONG HEV`) | Signal that an event occurred; posted / reset state with a post count; wakes waiters. |
| MuxWait semaphore | `HMUX` (`typedef ULONG HMUX`) | Composite that waits on a set of up to 64 mutex or event semaphores, for *any* or *all*. |

The generic semaphore-handle type used by the muxwait record is `HSEM` (`typedef ULONG HSEM`),
which is the common type an `HEV` or `HMTX` is passed as when placed in a muxwait set.
**[DOC-IBM - `bsedos.h`]**

### 1.1 Shared vs. private, and the `\SEM32\` name model [DOC-IBM / DOC]

A semaphore's scope is decided at creation, by the first parameter of the create call:

- **Named (shared) semaphore.** The name is a string beginning `\SEM32\` (for example
  `\SEM32\MYAPP\READY`). Any process can obtain a handle to the same object by passing that name
  to the corresponding `DosOpen...Sem` call. A named semaphore is inherently shared. **[DOC]**
- **Unnamed private semaphore.** The name pointer is `NULL`. The semaphore is private to the
  creating process unless the `DC_SEM_SHARED` (`0x01`) attribute is set, in which case an
  unnamed semaphore is placed in the shared arena and its handle can be inherited by / passed to
  other processes even though it has no name. **[DOC-IBM - `bsedos.h`: "`DC_SEM_SHARED` ...
  indicate whether the semaphore is shared or private when the PSZ is null"]**

### 1.2 Creation attributes [DOC-IBM - `bsedos.h`]

Passed in the `flAttr` parameter of the create calls:

| Constant | Value | Applies to | Meaning |
|---|---|---|---|
| `DC_SEM_SHARED` | `0x01` | mutex / event / muxwait | Make an *unnamed* semaphore shared. |
| `DCMW_WAIT_ANY` | `0x02` | muxwait | Wait satisfied when *any* member is posted/released. |
| `DCMW_WAIT_ALL` | `0x04` | muxwait | Wait satisfied when *all* members are posted/released. |
| `DCE_AUTORESET` | `0x1000` | event | Event auto-resets on post (returns to reset state). |
| `DCE_POSTONE` | `0x0800` | event | Post wakes only one waiter and auto-resets when multiple wait. |

### 1.3 Timeout convention [DOC-IBM - `bsedos.h`]

The `ulTimeout` parameter of the blocking calls (`DosRequestMutexSem`, `DosWaitEventSem`,
`DosWaitMuxWaitSem`) is a `ULONG` millisecond count, with two named sentinels:

| Constant | Value | Meaning |
|---|---|---|
| `SEM_INDEFINITE_WAIT` | `-1L` | Block until the semaphore is available. |
| `SEM_IMMEDIATE_RETURN` | `0L` | Do not block; return immediately with the current state. |

A wait that times out returns `ERROR_TIMEOUT` (640) or `ERROR_SEM_TIMEOUT` (121) depending on
the call. **[DOC-IBM - `bseerr.h`]**

### 1.4 Mutex semaphore functions [DOC-IBM - `bsedos.h`]

| Function | One-line purpose |
|---|---|
| `DosCreateMutexSem` | Create a mutex semaphore, optionally named / shared / initially owned. |
| `DosOpenMutexSem` | Obtain a handle to an existing named mutex semaphore. |
| `DosCloseMutexSem` | Release this process's handle to a mutex semaphore. |
| `DosRequestMutexSem` | Acquire (request) the mutex, blocking up to a timeout; nestable by the owner. |
| `DosReleaseMutexSem` | Release one level of ownership of the mutex. |
| `DosQueryMutexSem` | Return the current owner's PID/TID and the nesting request count. |

```c
APIRET APIENTRY DosCreateMutexSem(PSZ pszName, PHMTX phmtx, ULONG flAttr, BOOL32 fState);
APIRET APIENTRY DosOpenMutexSem(PSZ pszName, PHMTX phmtx);
APIRET APIENTRY DosCloseMutexSem(HMTX hmtx);
APIRET APIENTRY DosRequestMutexSem(HMTX hmtx, ULONG ulTimeout);
APIRET APIENTRY DosReleaseMutexSem(HMTX hmtx);
APIRET APIENTRY DosQueryMutexSem(HMTX hmtx, PID *ppid, TID *ptid, PULONG pulCount);
```

`fState` on create is `TRUE` to create the mutex already owned by the caller. A mutex is
**ownership-tracked**: only the owning thread may release it, and `DosRequestMutexSem` may be
called repeatedly by the owner (nested), each request requiring a matching release. If the owning
thread ends without releasing, a subsequent request returns `ERROR_SEM_OWNER_DIED` (105); the
non-owner release attempt returns `ERROR_NOT_OWNER` (288). **[DOC-IBM - `bsedos.h` /
`bseerr.h`]**

### 1.5 Event semaphore functions [DOC-IBM - `bsedos.h`]

| Function | One-line purpose |
|---|---|
| `DosCreateEventSem` | Create an event semaphore in posted or reset state, optionally named / shared. |
| `DosOpenEventSem` | Obtain a handle to an existing named event semaphore. |
| `DosCloseEventSem` | Release this process's handle to an event semaphore. |
| `DosPostEventSem` | Post the event (wake waiters), incrementing the post count. |
| `DosResetEventSem` | Return the event to the reset state and read the post count since the last reset. |
| `DosWaitEventSem` | Block until the event is posted, up to a timeout. |
| `DosQueryEventSem` | Read the current post count without altering the semaphore. |

```c
APIRET APIENTRY DosCreateEventSem(PSZ pszName, PHEV phev, ULONG flAttr, BOOL32 fState);
APIRET APIENTRY DosOpenEventSem(PSZ pszName, PHEV phev);
APIRET APIENTRY DosCloseEventSem(HEV hev);
APIRET APIENTRY DosResetEventSem(HEV hev, PULONG pulPostCt);
APIRET APIENTRY DosPostEventSem(HEV hev);
APIRET APIENTRY DosWaitEventSem(HEV hev, ULONG ulTimeout);
APIRET APIENTRY DosQueryEventSem(HEV hev, PULONG pulPostCt);
```

`fState` on create is `TRUE` to create the event **posted**, `FALSE` to create it **reset**.
An event carries a **post count**: `DosPostEventSem` increments it, `DosResetEventSem` clears the
posted state and returns via `pulPostCt` how many posts occurred since the previous reset, and
`DosQueryEventSem` reads that count non-destructively. Posting an already-posted event returns
`ERROR_ALREADY_POSTED` (299); resetting an already-reset event returns `ERROR_ALREADY_RESET`
(300) [DOC-IBM - `bseerr.h:331-332`]. With `DCE_AUTORESET` the event returns to the reset state automatically once waiters have
been released. **[DOC-IBM - `bsedos.h`]**

### 1.6 MuxWait semaphore functions [DOC-IBM - `bsedos.h`]

A muxwait groups a set of existing event *or* mutex semaphores so a thread can wait on the whole
set at once. The set is described by an array of `SEMRECORD` and a count; a single muxwait holds
only one kind (all events or all mutexes), and up to 64 members.

| Function | One-line purpose |
|---|---|
| `DosCreateMuxWaitSem` | Create a muxwait over an initial array of semaphore records, ANY or ALL. |
| `DosOpenMuxWaitSem` | Obtain a handle to an existing named muxwait semaphore. |
| `DosCloseMuxWaitSem` | Release this process's handle to a muxwait semaphore. |
| `DosWaitMuxWaitSem` | Block until the ANY/ALL condition over the set is met, up to a timeout. |
| `DosAddMuxWaitSem` | Add a semaphore record to an existing muxwait set. |
| `DosDeleteMuxWaitSem` | Remove a member semaphore (by its `HSEM`) from the set. |
| `DosQueryMuxWaitSem` | Read back the member records and the muxwait attributes. |

```c
APIRET APIENTRY DosCreateMuxWaitSem(PSZ pszName, PHMUX phmux, ULONG cSemRec,
                                    PSEMRECORD pSemRec, ULONG flAttr);
APIRET APIENTRY DosOpenMuxWaitSem(PSZ pszName, PHMUX phmux);
APIRET APIENTRY DosCloseMuxWaitSem(HMUX hmux);
APIRET APIENTRY DosWaitMuxWaitSem(HMUX hmux, ULONG ulTimeout, PULONG pulUser);
APIRET APIENTRY DosAddMuxWaitSem(HMUX hmux, PSEMRECORD pSemRec);
APIRET APIENTRY DosDeleteMuxWaitSem(HMUX hmux, HSEM hSem);
APIRET APIENTRY DosQueryMuxWaitSem(HMUX hmux, PULONG pcSemRec, PSEMRECORD pSemRec,
                                   PULONG pflAttr);
```

The set member is a `SEMRECORD` (structure tag `psr`): **[DOC-IBM - `bsedos.h`]**

```c
typedef struct _PSEMRECORD {   /* psr */
   HSEM   hsemCur;             /* handle of a member event or mutex semaphore */
   ULONG  ulUser;             /* caller-defined value returned when this member fires */
} SEMRECORD, *PSEMRECORD;
```

On a satisfied `DosWaitMuxWaitSem`, the `ulUser` value of the member that satisfied the wait is
returned through `pulUser`, letting the caller identify which semaphore fired. `flAttr` selects
`DCMW_WAIT_ANY` (`0x02`) or `DCMW_WAIT_ALL` (`0x04`), combined with `DC_SEM_SHARED` for an unnamed
shared muxwait. **[DOC-IBM - `bsedos.h`]**

### 1.7 Common semaphore error codes [DOC-IBM - `bseerr.h`]

| Error | Value | Meaning |
|---|---|---|
| `ERROR_INVALID_HANDLE` | 6 | The handle is not a valid semaphore handle. |
| `ERROR_INTERRUPT` | 95 | The wait was interrupted (e.g. by a signal). |
| `ERROR_TOO_MANY_SEMAPHORES` | 100 | System/process semaphore limit reached. |
| `ERROR_EXCL_SEM_ALREADY_OWNED` | 101 | Exclusive semaphore already owned. |
| `ERROR_SEM_IS_SET` | 102 | Semaphore is in the set/posted state. |
| `ERROR_SEM_OWNER_DIED` | 105 | Mutex owner thread ended without releasing. |
| `ERROR_SEM_TIMEOUT` | 121 | Timeout expired before the semaphore became available. |
| `ERROR_SEM_NOT_FOUND` | 187 | Named semaphore does not exist. |
| `ERROR_DUPLICATE_NAME` | 285 | A semaphore of that name already exists. |
| `ERROR_MUTEX_OWNED` | 287 | Mutex is owned (e.g. on a close attempt). |
| `ERROR_NOT_OWNER` | 288 | Releasing thread is not the mutex owner. |
| `ERROR_TOO_MANY_HANDLES` | 290 | Too many open handles to the semaphore. |
| `ERROR_SEM_BUSY` | 301 | Semaphore is busy. |
| `ERROR_TIMEOUT` | 640 | Generic timeout (e.g. muxwait). |

---

## 2. Pipes

OS/2 has two pipe families: **anonymous** pipes (a read/write handle pair for a parent and its
child) and **named** pipes (a `\PIPE\`-named bidirectional server/client channel). Named-pipe
declarations are under `INCL_DOSNMPIPES`; `DosCreatePipe` is under `INCL_DOSQUEUES`.

### 2.1 Anonymous pipes [DOC-IBM - `bsedos.h`]

```c
APIRET APIENTRY DosCreatePipe(PHFILE phfRead, PHFILE phfWrite, ULONG cb);
```

`DosCreatePipe` returns two file handles - a read handle and a write handle - connected by a
buffer of `cb` bytes. The handles are ordinary `HFILE`s usable with `DosRead` / `DosWrite` /
`DosClose`, and are inherited by child processes, which is how an anonymous pipe connects a parent
and its child. It has no name and cannot be opened by unrelated processes. **[DOC-IBM -
`bsedos.h`]**

### 2.2 Named pipes - the `\PIPE\` model [DOC-IBM / DOC]

A named pipe has a name of the form `\PIPE\name`. One process is the **server** - it creates the
pipe with `DosCreateNPipe` and manages the connection with `DosConnectNPipe` /
`DosDisConnectNPipe` - and other processes are **clients**, which reach it by opening the same
`\PIPE\name` with `DosOpen` (the pipe presents as a file). Named pipes can be duplex and support a
byte-stream or message mode. **[DOC-IBM - `bsedos.h`; DOC - Control Program Reference]**

| Function | One-line purpose |
|---|---|
| `DosCreateNPipe` | (Server) Create a named-pipe instance with access/pipe modes and buffer sizes. |
| `DosConnectNPipe` | (Server) Place the pipe in the LISTENING state, ready for a client to open. |
| `DosDisConnectNPipe` | (Server) Disconnect the current client, returning the pipe to DISCONNECTED. |
| `DosCallNPipe` | (Client) Open, write a request, read a reply, and close - a one-shot transaction by name. |
| `DosTransactNPipe` | Write a request and read a reply over an already-open message-mode pipe. |
| `DosWaitNPipe` | (Client) Wait for a pipe instance to become available when all are busy. |
| `DosPeekNPipe` | Read pipe data without removing it, plus available-byte counts and state. |
| `DosQueryNPHState` | Query the handle state (read/blocking mode, server/client end, instance count). |
| `DosSetNPHState` | Set the handle state (blocking mode, read mode). |
| `DosQueryNPipeInfo` | Query pipe attributes (buffer sizes, instance counts, name). |
| `DosQueryNPipeSemState` | Report, via an attached semaphore, which pipe handles have data/space. |
| `DosSetNPipeSem` | Attach an event semaphore to a pipe for readiness notification, with a key. |
| `DosRawReadNPipe` / `DosRawWriteNPipe` | Raw (protocol-level) read/write of pipe data. |

```c
APIRET APIENTRY DosCreateNPipe(PSZ pszName, PHPIPE pHpipe, ULONG openmode, ULONG pipemode,
                               ULONG cbInbuf, ULONG cbOutbuf, ULONG msec);
APIRET APIENTRY DosConnectNPipe(HPIPE hpipe);
APIRET APIENTRY DosDisConnectNPipe(HPIPE hpipe);
APIRET APIENTRY DosCallNPipe(PSZ pszName, PVOID pInbuf, ULONG cbIn, PVOID pOutbuf,
                             ULONG cbOut, PULONG pcbActual, ULONG msec);
APIRET APIENTRY DosTransactNPipe(HPIPE hpipe, PVOID pOutbuf, ULONG cbOut, PVOID pInbuf,
                                 ULONG cbIn, PULONG pcbRead);
APIRET APIENTRY DosWaitNPipe(PSZ pszName, ULONG msec);
APIRET APIENTRY DosPeekNPipe(HPIPE hpipe, PVOID pBuf, ULONG cbBuf, PULONG pcbActual,
                             PAVAILDATA pAvail, PULONG pState);
```

**The `cbInbuf` / `cbOutbuf` names above are the Toolkit header's and are WRONG:** argument 5
sizes the **outbound** buffer, as the Control Program Reference says (section 2.2.9, measured).

The pipe handle type is `HPIPE` (`typedef LHANDLE HPIPE`). **[DOC-IBM - `bsedos.h`]**

#### 2.2.1 `DosCreateNPipe` open-mode flags (`openmode`) [DOC-IBM - `bsedos.h`]

| Constant | Value | Meaning |
|---|---|---|
| `NP_ACCESS_INBOUND` | `0x0000` | Client -> server only. |
| `NP_ACCESS_OUTBOUND` | `0x0001` | Server -> client only. |
| `NP_ACCESS_DUPLEX` | `0x0002` | Bidirectional. |
| `NP_INHERIT` | `0x0000` | Handle inherited by child processes. |
| `NP_NOINHERIT` | `0x0080` | Handle not inherited. |
| `NP_WRITEBEHIND` | `0x0000` | Write-behind allowed. |
| `NP_NOWRITEBEHIND` | `0x4000` | Write-behind disabled. |

#### 2.2.2 `DosCreateNPipe` pipe-mode flags (`pipemode`) and instance count [DOC-IBM - `bsedos.h`]

| Constant | Value | Meaning |
|---|---|---|
| `NP_READMODE_BYTE` | `0x0000` | Read as a byte stream. |
| `NP_READMODE_MESSAGE` | `0x0100` | Read as messages. |
| `NP_TYPE_BYTE` | `0x0000` | Byte-type pipe. |
| `NP_TYPE_MESSAGE` | `0x0400` | Message-type pipe. |
| `NP_END_CLIENT` | `0x0000` | Client end. |
| `NP_END_SERVER` | `0x4000` | Server end. |
| `NP_WAIT` | `0x0000` | Blocking operations. |
| `NP_NOWAIT` | `0x8000` | Non-blocking operations. |
| `NP_UNLIMITED_INSTANCES` | `0x00FF` | No fixed limit on instances. |

The low byte `NP_ICOUNT` (`0x00FF`) of the pipe mode holds the instance-count field. The
handle-state word queried by `DosQueryNPHState` uses the parallel bit set `NP_NBLK` (`0x8000`,
non-blocking), `NP_SERVER` (`0x4000`, server end), `NP_WMESG` (`0x0400`, write messages),
`NP_RMESG` (`0x0100`, read as messages). **[DOC-IBM - `bsedos.h`]**

#### 2.2.3 Pipe states and state machine [DOC-IBM - `bsedos.h`]

A named pipe moves through four states. Two constant sets name them - the `NP_STATE_*` set used
by `DosPeekNPipe`/`DosQueryNPHState`, and the plain `NP_*` set:

| State | `NP_STATE_*` | `NP_*` | Reached by |
|---|---|---|---|
| Disconnected | `NP_STATE_DISCONNECTED` `0x0001` | `NP_DISCONNECTED` `1` | After create or server disconnect. |
| Listening | `NP_STATE_LISTENING` `0x0002` | `NP_LISTENING` `2` | After server `DosConnectNPipe`. |
| Connected | `NP_STATE_CONNECTED` `0x0003` | `NP_CONNECTED` `3` | After a client opens the pipe. |
| Closing | `NP_STATE_CLOSING` `0x0004` | `NP_CLOSING` `4` | After client or server close. |

The documented transition table (from `bsedos.h`): a server `DosCreateNPipe` produces
DISCONNECTED; a server connect moves DISCONNECTED -> LISTENING; a client open moves LISTENING ->
CONNECTED; a server disconnect returns CONNECTED (or CLOSING) -> DISCONNECTED; a client close moves
CONNECTED -> CLOSING. If the server disconnects its end, the client end enters a state where any
future operation except close returns an error. **[DOC-IBM - `bsedos.h`]**

#### 2.2.4 Named-pipe timeout sentinels [DOC-IBM - `bsedos.h`]

| Constant | Value | Meaning |
|---|---|---|
| `NP_INDEFINITE_WAIT` | `-1` | Block forever (the `msec` parameter). |
| `NP_DEFAULT_WAIT` | `0L` | Use the pipe's default wait time. |

#### 2.2.5 Named-pipe structures [DOC-IBM - `bsedos.h`]

```c
typedef struct _AVAILDATA {   /* AVAILDATA */
   USHORT  cbpipe;            /* bytes left in the pipe */
   USHORT  cbmessage;         /* bytes left in the current message */
} AVAILDATA, *PAVAILDATA;

typedef struct _PIPEINFO {    /* nmpinf */
   USHORT  cbOut;             /* length of outgoing I/O buffer */
   USHORT  cbIn;              /* length of incoming I/O buffer */
   BYTE    cbMaxInst;         /* maximum number of instances   */
   BYTE    cbCurInst;         /* current number of instances   */
   BYTE    cbName;            /* length of pipe name           */
   CHAR    szName[1];         /* start of name (variable)      */
} PIPEINFO, *PPIPEINFO;

typedef struct _PIPESEMSTATE {   /* nmpsmst */
   BYTE    fStatus;   /* 0=EOI, 1=read ok, 2=write ok, 3=pipe closed */
   BYTE    fFlag;     /* 0x01 = a thread is waiting on this end       */
   USHORT  usKey;     /* the user key set with DosSetNPipeSem         */
   USHORT  usAvail;   /* bytes of data/space available if status 1/2 */
} PIPESEMSTATE, *PPIPESEMSTATE;
```

The `PIPESEMSTATE.fStatus` values have named forms: `NPSS_EOI` (0), `NPSS_RDATA` (1),
`NPSS_WSPACE` (2), `NPSS_CLOSE` (3); the `fFlag` bit `NPSS_WAIT` is `0x01`. **[DOC-IBM -
`bsedos.h`]**

#### 2.2.6 `DosConnectNPipe` behavior and return codes [DOC - EDM2 "DosConnectNmPipe"]

The server issues this once before the first client and again (after `DosDisConnectNPipe`) before
each subsequent client. On return the pipe is in the LISTENING state; a client `DosOpen` to a pipe
that is not listening fails. Behavioral edge cases:

- If the client end is already open, the call returns at once with no effect.
- In blocking mode with no client yet open, it waits for the client `DosOpen`; in non-blocking mode
  it returns `ERROR_PIPE_NOT_CONNECTED` (233) but still leaves the pipe LISTENING so a following
  client `DosOpen` can succeed.
- If the pipe was closed by a previous client but not yet disconnected by the server, it always
  returns `ERROR_BROKEN_PIPE` (109).
- Called on the *client* end it returns `ERROR_BAD_PIPE` (230); an interrupted blocking wait
  returns `ERROR_INTERRUPT` (95).

Return codes: `NO_ERROR`, `ERROR_INTERRUPT` (95), `ERROR_BROKEN_PIPE` (109), `ERROR_BAD_PIPE`
(230), `ERROR_PIPE_NOT_CONNECTED` (233). **[DOC - EDM2 "DosConnectNmPipe"]**

> **Checked 2026-10-01** against the kernel and by measurement at both widths (section 2.2.11): every
> rule above holds. section 2.2.11 adds what this page does not say: a blocked connect is not woken by
> a disconnect or a close of its handle, and a disconnect returns 0 in every state of a server
> end.

#### 2.2.7 The 16-bit `NmPipe` family is a SEPARATE API surface, not an alias [DOC-IBM / OBS-RE]

Everything above is the 32-bit API. The 16-bit Control Program has its own named-pipe family, and
it is **not** the same names under an old spelling: IBM writes `NmPipe` in 16-bit and `NPipe` in
32-bit, and the verbs differ too (16-bit `DosMakeNmPipe` versus 32-bit `DosCreateNPipe`). The
toolkit's own old-name compatibility `#define` block - the block that maps `DosMkDir`->
`DosCreateDir` and 44 other pairs - contains **no pipe entry at all**, so the two families are
genuinely distinct exports rather than an alias pair. IBM's own 32-bit header corroborates the
`NmPipe` spelling in its prose while declaring `NPipe` prototypes, e.g. the comment
`/* DosPeekNmPipe() pipe states */` and the state-machine note `server DosMakeNmPipe` sitting
inside `#ifdef INCL_DOSNMPIPES`. **[DOC-IBM - `bsedos.h`, the compatibility block and the
`INCL_DOSNMPIPES` prose.]**

The 14 entry points, their ordinals, and their callee-pop byte counts. The ordinals are IBM's
own - `NAMPIPES.DLL` is a pure forwarder DLL whose ordinals 1-14 forward to `DOSCALLS.#399`-
`#412` in order, and it names every one in its resident-name table. The byte counts are read off
each entry's own `retf n`, because these ordinals are answered by `DOSCALL1.DLL` and not by the
kernel (see below); each count equals the sum of its prototype's parameter widths, which is the
cross-check that ties the two columns together. **[DOC-IBM - the ordinal constants
`ORD_DOSMAKENMPIPE`...`ORD_DOSQNMPIPESEMSTATE` = 1...14, `bseord.h:231-244`. DOC - the 16-bit
prototypes, from the OS/2 1.x Control Program header as reproduced by OpenWatcom
(`h/os21x/bsedos.h`); IBM's own base Toolkit ships only the 32-bit `NPipe` declarations. OBS-RE -
the shipped `NAMPIPES.DLL` entry + resident-name tables, and each `retf n` in the shipped
`DOSCALL1.DLL`.]**

| `NAMPIPES` ord | `DOSCALLS` ord | 16-bit entry point | `retf n` | 16-bit prototype |
|---|---|---|---|---|
| 1 | 399 | `DosMakeNmPipe` | 20 | `(PSZ,PHPIPE,USHORT,USHORT,USHORT,USHORT,ULONG)` |
| 2 | 400 | `DosQNmPipeInfo` | 10 | `(HPIPE,USHORT,PBYTE,USHORT)` |
| 3 | 401 | `DosConnectNmPipe` | 2 | `(HPIPE)` |
| 4 | 402 | `DosDisConnectNmPipe` | 2 | `(HPIPE)` - note the capital **C** |
| 5 | 403 | `DosQNmPHandState` | 6 | `(HPIPE,PUSHORT)` |
| 6 | 404 | `DosSetNmPHandState` | 4 | `(HPIPE,USHORT)` |
| 7 | 405 | `DosPeekNmPipe` | 20 | `(HPIPE,PBYTE,USHORT,PUSHORT,PUSHORT,PUSHORT)` |
| 8 | 406 | `DosWaitNmPipe` | 8 | `(PSZ,ULONG)` |
| 9 | 407 | `DosTransactNmPipe` | 18 | `(HPIPE,PBYTE,USHORT,PBYTE,USHORT,PUSHORT)` |
| 10 | 408 | `DosCallNmPipe` | 24 | `(PSZ,PBYTE,USHORT,PBYTE,USHORT,PUSHORT,ULONG)` |
| 11 | 409 | `DosRawReadNmPipe` | 12 | `(HPIPE,PBYTE,USHORT,PUSHORT)` - internal-only, see below |
| 12 | 410 | `DosRawWriteNmPipe` | 12 | `(HPIPE,PBYTE,USHORT,PUSHORT)` - internal-only, see below |
| 13 | 411 | `DosSetNmPipeSem` | 8 | `(HPIPE,HSEM,USHORT)` |
| 14 | 412 | `DosQNmPipeSemState` | 10 | `(HSEM,PBYTE,USHORT)` |

`HPIPE` is `SHANDLE` (a `USHORT`) in 16-bit, not the 32-bit `LHANDLE`, which is why
`DosConnectNmPipe` pops 2 and its 32-bit counterpart takes a 4-byte handle.

**`DosRawReadNmPipe` and `DosRawWriteNmPipe` are deliberately unpublished.** They are exported,
ordinal-assigned (`ORD_DOSRAWREADNMPIPE` 11 / `ORD_DOSRAWWRITENMPIPE` 12, `bseord.h:241-242`) and
named in `NAMPIPES.DLL`'s resident-name table exactly like their twelve siblings - but no
prototype for either appears in the base Toolkit headers, where all twelve siblings do appear.
The reason is recorded in the LAN Manager named-pipe header the API originates from, which
declares both **inside an `/**INTERNAL_ONLY**/` ... `/**END_INTERNAL**/` bracket**. So their absence
from `bsedos.h` is a decision, not an omission, and it should not be read as evidence that the
entry points do not exist. That same bracket carries the prototypes, which is why the table above
can state them:

```c
/**INTERNAL_ONLY**/
extern API_FUNCTION
  DosRawWriteNmPipe(unsigned, char FAR *, unsigned short, unsigned short FAR *);

extern API_FUNCTION
  DosRawReadNmPipe(unsigned, char FAR *, unsigned short, unsigned short FAR *);
/**END_INTERNAL**/
```

Widths sum to 2 + 4 + 2 + 4 = **12** for both, matching the measured `retf 0xc` - so these two
rows now satisfy the same count-equals-prototype check as their twelve siblings rather than
asserting a count with nothing to check it against. (`unsigned` is the 16-bit `HPIPE`/`SHANDLE`,
rendered as such above for consistency with the sibling rows.) **[DOC-IBM - the prototypes, from
the LAN Manager named-pipe header as redistributed in the IBM LAN Server API toolkit,
`nmpipe.h:101-107`; OBS-RE - the shipped `NAMPIPES.DLL` name table and the `retf 0xc` on both
`DOSCALL1.DLL` entries.]** The IFS DDK separately documents their *request-packet* parameter
blocks (`npr_param` / `npw_param`, each `{len, dlen, nbyt}`), which is the driver-facing view, not
the API signature.

**Which module answers them: `DOSCALL1.DLL`, not the kernel.** None of `#399`-`#412` appears in
the kernel pseudo-module's entry table; all fourteen are type-2 callgate exports in `DOSCALL1.DLL`
object 4, and each is a thin argument-forwarding shim - `enter 0,0`, re-push the caller's words,
one far call, `leave`, `retf n`. A trap follows from this and is worth stating explicitly: the
kernel **also** carries symbols named `DOSMAKENMPIPE`, `DOSQNMPHANDSTATE` and friends, with
`pre_sci(N)` counts that agree - but `DOSCALLS.#399` does not route to the kernel's. A name match
against a kernel symbol table is therefore not proof that a given ordinal reaches it. **[OBS-RE.]**
> **Qualified 2026-09-30.** The first half stands: `#399` is DOSCALL1's export, not the kernel's.
> But the shim's one far call is an import of `DOSCALLS.#167`, and in OS2KRNL 14.104a SMP the stub
> for #167 **is** the symbol `DOSMAKENMPIPE` (section 2.2.8). So "does not route to the kernel's" is false
> for that build, by one hop. The breakpoint observation below names an object-11 symbol on an
> unstated build; how it squares with this was not established.
Corroborated live on real hardware: a `DosMakeNmPipe` call does not trip a breakpoint set on the
kernel's 16-bit `DOSMAKENMPIPE`. Three things the next reader needs in order to re-run it rather
than take it on trust:

- **Break by address, not by name.** The run used `%ffebd688`, `ln`-verified. That address is
  build-specific (re-resolve it with `ln` on the kernel under test), but resolving it at all is
  the point: `DOSCALL1.DLL` **also** exports a `DOSMAKENMPIPE` symbol, so a bare
  `bp DOSMAKENMPIPE` can silently resolve into `DOSCALL1` and fail `Past end of segment`.
- **The positive control that makes the silence mean something.** The breakpoint stayed silent
  across a full boot *and* across a probe's own direct 16-bit `DosMakeNmPipe` call issued in the
  same debugger session. The second case is what rules out a dead session: the call demonstrably
  happened, with the debugger live, and the kernel entry still did not fire.
- **Where the call goes instead**, so the negative result has a positive counterpart: into the
  kernel's internal `h_w_MakeNmPipe`-family workers in `os2krnl` object 12 - not the object-11
  `DOSMAKENMPIPE` entry the name match suggests.

**[OBS - a kernel-debugger breakpoint that did not fire on a real system; re-check by re-running
it there, not by re-reading a decompile.]**

#### 2.2.8 What the 16-bit shims call, and how the calls behave [OBS-RE / OBS]

**The shims forward to kernel-export ordinals.** Each 16-bit `DOSCALL1.DLL` shim above makes one
far call, and that call is an **import of a `DOSCALLS` ordinal answered by the kernel**:

| 16-bit | calls | 16-bit | calls | 16-bit | calls |
|---|---|---|---|---|---|
| 399 | #167 | 404 | #174 | 409 | #179 |
| 400 | #172 | 405 | #171 | 410 | #180 |
| 401 | #169 | 406 | #176 | 411 | #177 |
| 402 | #170 | 407 | #175 | 412 | #178 |
| 403 | #173 | 408 | #168 | | |

- Each kernel export pops the same byte count as its public 16-bit form, and its entry stub is
  `pre_sci` of that count.
- The **32-bit** `NPipe` entries are `DOSCALL1` thunks to these 16-bit shims: `DosCreateNPipe` ->
  #399, `DosTransactNPipe` -> #407, `DosRawReadNPipe` #246 -> #409, and so on. So all three widths run
  one kernel worker. Each thunk's argument descriptor was not decoded; that the arguments arrive in
  order is inferred.
  > **Decoded 2026-10-01 (section 2.2.11):** the arguments arrive in order, and counts and modes are
  > pushed as 16-bit words.
- **[OBS-RE - the shim far-call fixups in the shipped `DOSCALL1.DLL` object 4, resolved to their
  import ordinals; each 32-bit entry's `mov eax, <16:16>` target; the kernel stubs in OS2KRNL
  14.104a SMP.]**

In 14.104a SMP the stub for #167 is the symbol `DOSMAKENMPIPE`, at `000c:7ab8` in object 12. The
breakpoint observation in section 2.2.7 names an object-11 `DOSMAKENMPIPE` and does not say which kernel
build it was on. Whether those are the same routine, and so whether the two results agree, was **not
established**.

**Behaviour, measured** on a WSeB 4.52 CP2 system, 2026-09-30, with one probe built at both widths;
both widths gave the same answers. **[OBS]**

*`DosTransactNPipe` / `DosTransactNmPipe`.* The checks run in this order:
1. A handle that is not open: 6. A disk-file handle: 50. Any other handle that is not a named pipe
   (an anonymous pipe, say): 1.
2. A byte-**type** pipe: 11. A message pipe whose handle is in byte read mode **succeeds**: the
   transact reads in message mode regardless. The reference page says it fails.
3. An end that lacks a direction (either end of an `NP_ACCESS_INBOUND` or `NP_ACCESS_OUTBOUND`
   pipe): 5.
4. `cbOut` or `cbIn` of 0: 87, which is not on the page.
5. Data already waiting to be read at this end: 231.
6. The other end gone (closed, or a server end listening or disconnected): 109, or 157 when that
   end left unread data.
7. A reply longer than `cbIn`: 234 with `cbIn` bytes, and the rest is readable afterwards.

Also:
- A no-wait handle still waits for the reply.
- On 6 or 1, `*pcbRead` gets `cbOut`. On 50 it gets a value nothing documents (53188 in every run
  here). On the other refusals it gets 0.
- The 32-bit entry keeps only the low 16 bits of each count: `cbIn` 0x10000 behaves as 0 (87) and
  0x10040 as 64.

**[OBS-RE: the order matches the kernel worker `np_trans_sft`, which tests the end's `0x0400`
(`NP_WMESG`) bit for the type.]**

*`DosCallNPipe` / `DosCallNmPipe`.*
- A name outside `\PIPE\`: 230. A pipe that does not exist: **3**, not the page's 2. An over-long
  name: 3, with `*pcbActual` not written.
- With no instance listening (created but never connected, or its only instance in use) the call
  waits `msec` and returns **121**, not the page's 231 or 95. `msec` 0 waits the pipe's own creation
  timeout.
- A byte pipe: 11. An inbound or outbound pipe: 5. A count of 0: 87.
- A reply longer than `cbOut`: 234, with `*pcbActual` set to **0**.
- The client end is closed when the call returns: the server's next read gets 0 bytes, and it can
  disconnect and reconnect.

*`DosWaitNPipe`.* A pipe that does not exist: 3. A name outside `\PIPE\`: 230. A timeout: 121.
`msec` 0 waits the pipe's creation timeout.

*`DosCreateNPipe`.*
- A name outside `\PIPE\`: 3.
- 87 for any of: access value 3; `NP_READMODE_MESSAGE` with `NP_TYPE_BYTE`; an instance count of 0.
- Another create beyond the instance count: 231.

*`DosConnectNPipe` / `DosDisConnectNPipe`.* Measured:
- both give 230 on a client end;
- `DosConnectNPipe` gives 109 for a client that opened and closed before the server disconnected
  (as section 2.2.6), while `DosDisConnectNPipe` on such a pipe gives 0;
- `DosConnectNPipe` gives 1 for a handle that is not a named pipe.

After a disconnect the client's next read is 233, and the server's next read is 0 bytes with rc 0.

*`DosQueryNPHState` / `DosSetNPHState`.*
- The state word includes the pipe type. A server end created as a 1-instance message pipe in
  message read mode with no-wait reads `0xC501`.
- **A client end starts with the creator's read mode and in blocking mode:** `0x0501` on that same
  pipe. The reference page says a client starts in byte read mode. **[OBS-RE: the kernel's open
  copies the creator's pipe mode `& 0x3F00` to the client end.]**
- `DosSetNPHState` with any bit of `0x46FF`: 87. Message read mode on a byte pipe: 87.
- A handle that is not a named pipe: 1, with the state word written as 0.

*`DosQueryNPipeInfo`.*
- `cbName` counts the terminating NUL: a 13-character name gives 14.
- Level 2 returns 4 zero bytes for a local pipe.
- A 4-byte buffer at level 1: 111, with the 4 bytes that fit filled.
- Level 3: 124. A handle that is not a named pipe: 1.

*`DosPeekNPipe`.*
- The data is returned without being consumed.
- `cbpipe` counts the instance buffer, where each message is a 2-byte length then its bytes: one
  24-byte message reads `cbpipe` 26, `cbmessage` 24.
- With nothing queued, a client end peeking with a 64-byte buffer reads `cbmessage` 0 while the
  server is connected, and 0xFFFF once the server has closed; the state is then 4
  (`NP_STATE_CLOSING`). A separate capture read 0xFFFF from a **server** end, connected, peeking
  with a buffer of 0. Which of the two differences (the end, or the buffer size) decides it was not
  separated.
  > **Separated 2026-10-01 (section 2.2.11):** the buffer size decides it. With nothing queued,
  > `cbmessage` is 0xFFFF for a buffer of 0, or once the writer has gone, at either end.
- A client of an inbound pipe: 5. A disk-file handle: 50.

*Raw I/O (`DosRawReadNmPipe` / `DosRawWriteNmPipe`, and 32-bit #246/#247).* The 32-bit forms,
unlike the 16-bit ones (section 2.2.7), are declared in the base Toolkit
(`DosRawReadNPipe(HPIPE, PVOID, ULONG, PULONG)` and the matching `DosRawWriteNPipe`).
**[DOC-IBM - `bsedos.h`, `INCL_DOSNMPIPES`.]**
- They move that buffer encoding directly: a 5-byte message raw-reads as `05 00` and its 5 bytes,
  and a raw write of those 7 bytes arrives as one 5-byte message.
- A raw read on a no-wait handle still waits.
- A missing direction: 5, with the count written back unchanged.
- **[OBS-RE: both workers mask the end's mode with `0x42FF`, clearing `NP_NBLK`, `NP_WMESG` and
  `NP_RMESG`.]**

*`DosSetNPipeSem` / `DosSetNmPipeSem` and `DosQueryNPipeSemState` / `DosQNmPipeSemState`.*
Measured on the same system, 2026-10-01. Each width used its own semaphore kind: a shared 32-bit
event at 32 bits, a 16-bit system semaphore at 16 bits. **[OBS]**
- **Attaching:**
  - A shared 32-bit event semaphore or a 16-bit system semaphore is accepted.
  - A private 32-bit event, a shared 32-bit mutex, or a shared muxwait: **292** (`ERROR_WRONG_TYPE`),
    not on the page. The page calls a muxwait attachable.
  - A handle that is no semaphore: 187. A pipe handle that is not open: 6. A disk-file handle: 1.
  - A client end whose server has disconnected it: 233.
  - The semaphore attaches to **that end**; a second call replaces the first, and only the second
    is posted afterwards.
- **When it is posted:** when bytes move at one end, the **other** end's semaphore is posted. A
  server's write posts the client's; a client's read posts the server's.
  - Writing at an end does not post that end's own semaphore, and neither does a peek.
  - Closing or disconnecting the server end posts the client's.
  - **[OBS-RE: the kernel's `np_poke_user_sem` posts the other end's slot when the byte count is
    nonzero and the operation is not a peek; close and disconnect post it directly.]**
- **Querying:**
  - Every instance on the system whose slot holds the semaphore is reported, including a pipe opened
    by another process: newest instance first, server slot before client.
  - Records are 6-byte `PIPESEMSTATE`s, ended by a **one-byte** `NPSS_EOI`.
  - A connected end gives `{NPSS_WSPACE, waiting, key, space}` when its write space is more than 2,
    and none when the end has no write buffer (a simplex pipe). The space is the buffer size less what
    is queued, lengths included: 512 for an empty 512-byte buffer, 486 with one 24-byte message queued.
  - It then gives `{NPSS_RDATA, waiting, key, bytes}` when data is queued. Bytes count each
    message's 2-byte length: a 24-byte message reads 26.
  - An end whose other end has closed gives `{NPSS_CLOSE, 0, key, 0}`. If what the closed end wrote
    is still unread, it is followed by `{NPSS_RDATA, ..., key, bytes}`.
  - `fFlag` (`NPSS_WAIT`) is set on the write-space record of the direction a reader is blocked on.
  - `cbBuf` 0: 87. A buffer that fits the records but not the EOI byte: 111, with the records
    written. One too small for the first record: 111, with nothing written.
  - A semaphore attached to no pipe, or a handle that is no semaphore: rc 0, with just the EOI.
    > **Explained 2026-10-01 (section 2.2.11):** a handle that is no semaphore is taken as a RAM
    > semaphore's address, which no slot holds. A 16-bit handle of the system-semaphore form that
    > is not in use instead ends the caller with a trap, from both calls.
- **What a close and a disconnect do to the data:**
  - When an end closes, the buffer it was reading is emptied: data written to it is discarded, and the
    other end's next DosTransactNPipe returns 157 [OBS]. A plain write takes the same test in the
    kernel's write path [OBS-RE: `NPwriteiob` returns 157 when the saved count is nonzero]; that was
    not captured. The buffer it was writing keeps its data for the other end.
  - A disconnect empties both buffers. After the server reconnects, the next client reads only what is
    written from then on. A client cut off by the disconnect gets 233 on its next read or write.
  - **[OBS-RE: `flushpipe` saves a departing reader's unread count and empties its buffer; a
    departing writer only drops its count; a disconnect forces both.]**
- **The kernel's per-instance block, the NP** (state, server and client counts, pipe mode, the two
  semaphore slots and keys), is documented field by field in the IBM debugging handbook's "Named Pipe
  Structures" section. It is allocated from the system arena, one per open instance. Each data buffer
  has its own NPB (bytes queued, reader and writer counts, lock words), allocated from the kernel
  resident heap. **[DOC-IBM]**
  - **Refined by section 2.2.9:** only buffers of up to 4,176 bytes come from that heap; a larger
    buffer is a separate memory object of its own. **[OBS-RE, OBS]**

#### 2.2.9 Buffer sizes and buffer memory [DOC-IBM / OBS-RE / OBS]

**What IBM documents.**
- `DosCreateNPipe` argument 5 is "the number of bytes to allocate for the **outbound** (server to
  client) buffer", and argument 6 the **inbound** one. **[DOC-IBM - Control Program Reference,
  `DosCreateNPipe` parameters `cbOutbuf` / `cbInbuf`]** The 16-bit `DosMakeNmPipe` has the same
  order (`OutBufSize`, `InBufSize`, both `USHORT`), and calls each size "an **advisory** to the
  system". **[DOC-IBM - `bsedos16.h` `DosMakeNmPipe(..., cbOutBuf, cbInBuf, ulTimeOut)`; DOC - EDM2
  "DosMakeNmPipe"]**
- **The Warp 4.5 Toolkit's 32-bit `bsedos.h` names argument 5 `cbInbuf` and argument 6 `cbOutbuf`.
  Those names are wrong**; the prototype in section 2.2 above copies them. Measured below (rows "argument
  order"): argument 5 sizes the outbound buffer at both widths, as the Reference says.
- "The in and out buffers can be up to 64KB in size." **[DOC-IBM - Control Program Guide,
  "Creating Named Pipes"]**
- `DosQueryNPipeInfo` level 1 returns "the **actual** size of the buffer" for each direction.
  **[DOC-IBM - Control Program Reference, `DosQueryNPipeInfo`]**
- Return codes `DosCreateNPipe` and `DosMakeNmPipe` document: 0, 3, **8**
  `ERROR_NOT_ENOUGH_MEMORY`, **84** `ERROR_OUT_OF_STRUCTURES`, 87, 231. **[DOC-IBM; DOC - EDM2]**
- Writes: a no-wait byte-pipe write takes "as many bytes as will fit"; a no-wait message write
  that would fit an empty buffer but not the space left returns 0 bytes written; a message larger
  than the buffer **blocks** until it is all written, whatever the blocking mode. **[DOC-IBM -
  Control Program Guide, "Writing to Named Pipes"]**
- A 32-bit write of a message "cannot span 64k boundaries due to the current design of the thunk
  layer". **[DOC-IBM - Control Program Reference, `DosRead`/`DosWrite` remarks]**
- **Not documented anywhere searched:** the size given for a request of 0, any minimum, the actual
  maximum, whether a byte is kept back, the size or growth of the kernel resident heap, any
  CONFIG.SYS statement affecting pipe buffers, and a system-wide limit on pipe instances. The
  CONFIG.SYS reference has no statement about pipe buffers or kernel heaps. (The 512-byte default
  documented for a size of 0 belongs to the anonymous `DosCreatePipe`, not to named pipes.)

**What the kernel does with a requested size.** Both APIs reach one worker: the 32-bit entry
passes each size through the 16-bit one, keeping only the **low 16 bits**. **[OBS - table below;
the 32-bit entry's thunk descriptor was not decoded]** *(Decoded 2026-10-01, section 2.2.11: each size is
pushed as a 16-bit word.)* The worker then sets each size:

| requested (low 16 bits) | size in force |
|---|---|
| direction absent (`NP_ACCESS_INBOUND` has no outbound buffer, `NP_ACCESS_OUTBOUND` no inbound) | 0, whatever was asked |
| 0, 1 or 2 | **1,024** |
| 3 to 65,512 | exactly as requested |
| 65,513 to 65,535 | **65,512** |

**[OBS-RE: 14.104a SMP kernel, `h_w_MakeNmPipe` and its helper `npm_chk_buf_size` - below 3
becomes `0x400`, at or above `0xFFE8` becomes `0xFFE8`, and the access mode decides which
directions get a buffer.]** No size is ever refused: every request above returned 0.

**What a buffer is.** The kernel allocates `size + 23` bytes for each buffer: a 22-byte header
(the NPB, section 2.2.8's last item) and then `size + 1` bytes of ring buffer. One byte of the ring is
always kept free, so a program sees exactly `size`. 65,512 is therefore the largest size whose
block fits one 64 KB segment (65,512 + 23 = 65,535). **[OBS-RE: `npm_memalloc` sets `npb_first`
to 0x16 and `npb_last` to `size + 0x17`; `wrt_chk_avail` gives `npb_last - npb_first - 1` free
on an empty buffer; `DosQueryNPipeInfo`'s helper reports `npb_last - 0x17`.]**
- **A total under 4,200 bytes (a size up to 4,176)** is a block in the kernel's first resident
  heap, owner `npipenbuf` (0xff9f) - the heap the debugging handbook names. **[OBS-RE:
  `npm_memalloc` compares the total with 0x1068 and calls `SELAllocKHB` with heap handle 1;
  handle 1 is the first resident heap created, the resident read/write heap (owner 0xffec).
  [INF] that handle numbering follows creation order, from `VMCreateKH`'s slot search.]**
- **A size of 4,177 or more** is a separate segment from the kernel's segment allocator, same
  owner, not a heap block. **[OBS-RE: `h_SegAlloc` -> `SegAlloc` -> `VMAllocMem`]**
- Both kinds are **resident**: resident memory rose by about 8.4 KB per duplex instance at size
  4,176, about 16.4 KB at 4,177 (two pages per buffer) and about 131.6 KB at 65,512 (64 KB per
  buffer). **[OBS: `DosQuerySysInfo(QSV_TOTRESMEM)` between creates, WSeB 4.50 14.089, 160 MB
  and 2 GB VMs, 2026-10-01]**
- The resident read/write heap's ceiling is 16 MB, or half of physical memory on a machine with
  under 6 MB (1,536 pages). **[OBS-RE: `VMInit` passes `0x1000000` to `VMCreateKH`, or
  `pgPhysPages x 4096 / 2` when `PGGlobalFlags & 0x10`; `PGInit` sets that bit when
  `pgPhysPages < 0x600`.]** Growth inside the ceiling was not read.

**Measured, every view** (WSeB 4.50, 14.089, 2026-10-01; duplex pipe, both sizes equal, no-wait
server end, a connected client; `DosQueryNPipeInfo` level 1, the server end's `NPSS_WSPACE` value
from `DosQueryNPipeSemState`, and the bytes a no-wait byte-pipe write of 65,535 took):

| requested | 16-bit (`DosMakeNmPipe`) | 32-bit (`DosCreateNPipe`) |
|---|---|---|
| 0, 1, 2 | rc 0; 1024 in every view | same |
| 3, 4, 16, 512, 4096, 4176, 4177 | rc 0; the request in every view | same |
| 65511, 65512 | rc 0; the request | same |
| 65513, 65534, 65535 | rc 0; 65512 | same |
| 65536, 65537 | - | rc 0; **1024** |
| 65539 | - | rc 0; **3** |
| 100000 (0x186A0) | - | rc 0; **34464** (0x86A0) |
| 0xFFFFFFFF | - | rc 0; **65512** |

- **Largest message a no-wait write puts into an empty message-pipe buffer: `size - 2`** (its
  2-byte length goes in too). With a 1-byte message already queued, a message of `size - 4` got 0
  bytes written and `size - 5` was taken whole, at every size from 16 to 65,512, both widths (at
  32 bits above about 63,000 only from a 64 KB-aligned buffer, for the reason in the next item).
  A message longer than `size - 2` was not tried: the kernel's no-wait test lets such a message
  through to the blocking path (above), so with no reader the probe would hang. **[OBS; OBS-RE: `wrt_chk_avail`'s
  message branch accepts when free >= length + 2, returns "no room" when the message fits the
  buffer, and proceeds otherwise.]**
- **The 32-bit write splits a message at a 64 KB boundary of the caller's buffer.** A 65,510-byte
  message from a 64 KB-aligned buffer was taken whole; from a buffer 1,000 bytes short of a 64 KB
  boundary, rc 0 with **1,000** bytes written, the free space falling by 1,002: the part before
  the boundary was queued as a message of its own and the rest refused. Same at size 4,096.
  **[OBS]**
- **Argument order:** created duplex with argument 5 = 100 and argument 6 = 200,
  `DosQueryNPipeInfo` gives `cbOut` 100, `cbIn` 200; outbound-only gives 100 / 0; inbound-only
  0 / 200; and a 0 for a present direction gives 1024 - identical at both widths. **[OBS]**

**When buffer memory runs out** (a disposable clone of WSeB 4.50 14.089, 2026-10-01; one process,
`DosSetMaxFH(5100)`, creating no-wait pipes without connecting them until a create fails, closing
them all, then repeating):
- **A system-wide limit on named-pipe instances comes first: 1,483 instances, then rc 84
  `ERROR_OUT_OF_STRUCTURES`.** The same 1,483 with a unique name per instance, with one name and
  `NP_UNLIMITED_INSTANCES`, simplex or duplex, at sizes 3, 4,176, 4,177 and (on 2 GB) 65,512, and
  on a 160 MB and a 2 GB machine; after the failure, a create of size 3 under a new name also got
  84. **[OBS]** The kernel keeps every instance's 44-byte NP in one pool segment
  (`NmpBmpSel`, created by `NmpInit` with block size 0x2c) that cannot pass 64 KB, and
  `get_free_np` returns 84 when the pool cannot supply one. **[OBS-RE]** Whether instances
  belonging to other processes on the machine were part of the 1,483 was not established.
  > **Established 2026-10-01 (section 2.2.11):** they are. With another process holding 500 instances,
  > the count was 983.
- **Buffer memory itself fails with rc 8 `ERROR_NOT_ENOUGH_MEMORY`.** On a 160 MB machine at size
  65,512 (128 KB resident per instance), creates failed with 8 at **942, 941 and 932** instances,
  resident memory then about 157 MB of 160 MB. A size-3 create straight afterwards succeeded. The
  machine stayed up and answered. **[OBS]** Both allocation routes return 8 on failure.
  **[OBS-RE: `npm_memalloc`]**
- **A failed create leaves nothing behind.** Every repeat round reached the same 1,483 (or the
  same memory limit, +/-10 with free memory), so no NP and no buffer was kept by a failure.
  **[OBS]** The failure path frees both buffers and the NP. **[OBS-RE: `npcl_dealloc_all`]**
- **The resident heap was not exhausted, and could not be by pipes alone here:** the largest
  heap-allocated buffers (4,176, both directions) times the 1,483-instance limit is about 12.5 MB,
  under the 16 MB ceiling, and the run ended with 84 on a healthy machine. Whether other kernel
  users of that heap would fail first near that level was not tested.


#### 2.2.10 Reading and writing against the buffer [DOC-IBM / OBS]

IBM's programming guide states the write and read rules ("Writing to Named Pipes", "Reading
from Named Pipes", "Synchronizing Named Pipe Dialogs" in the Control Program Programming
Guide). **[DOC-IBM]** Each row below was run on WSeB 4.50 (14.089), 2026-10-01, at both widths
(the 32-bit `Dos*NPipe` calls and the 16-bit `Dos*NmPipe` calls), with identical results.
Pipes were 512-byte duplex message pipes unless stated, and the server end was no-wait. **[OBS]**

- **A no-wait message write that does not fit now gets 0 bytes.** Five 100-byte messages filled
  510 of 512 bytes (each takes 102: the 2-byte length and the message). The sixth returned rc 0
  with 0 bytes written.
- **With 2 bytes left, the end has no write-space record.** In the same full state, a query of
  the client end's semaphore gave `{2,0,k,512}{1,0,k,510}` and none for the server end (whose
  space is 2). `DosPeekNPipe` at the client gave `cbpipe` 510, `cbmessage` 100, state 3.
- **A no-wait message larger than the whole buffer is written whole.** A 1000-byte message into
  the 512-byte buffer returned rc 0 with 1000 bytes written, while a reader in message read mode
  drained it. The reader got it in one read of 1000 bytes.
  > **Qualified 2026-10-01 (section 2.2.11):** this holds only while 2 or more bytes are free. With 1 or
  > 0 bytes free, the message's 2-byte length is torn or lost, and the reader then waits for a
  > message of a false length.
- **A no-wait byte-pipe write takes what fits:** 1000 bytes into an empty 512-byte buffer
  returned rc 0 with 512 written.
- **A blocking write larger than the buffer waits for a reader.** A 600-byte message into an
  empty 512-byte buffer returned only after a reader, started 300 ms later, had begun. It
  returned 600, and the reader got one 600-byte message.
- **A raw read after a partial `DosRead` starts with the remaining length.** Of a 24-byte
  message, `DosRead` of 10 returned 234 with 10 bytes. A raw read of 64 then returned 16 bytes,
  `0E 00` followed by the 14 bytes left. A partly read message keeps its remaining length in front
  of the rest. **[OBS-RE: `nprcb` writes it back]**
- **A 1-byte raw read at a message boundary returns the length's low byte, and then `DosRead`
  waits.** With one 10-byte message queued, a raw read of 1 returned `0A`. A `DosRead` of 64 at the
  same end then did not return within 1 s, although that end was no-wait. When the client closed,
  that read returned 234 with 9 bytes. **[INF: the read takes the length's high byte and the first
  message byte as a new length, and waits for that message]** - *confirmed and made precise from
  the kernel's read routine, 2026-10-01:* the read takes that false length, copies the 9 bytes
  that are there, and writes the unread remainder back in front of the read position. Because
  the message is now partly read, it waits for the rest; the no-wait bit is tested only when no
  part of a message is present. When the writer count reaches 0 it ends with 234. **[OBS-RE]**
- **A disconnect empties a half-written raw frame.** Client A raw-wrote 12 bytes: a length of 24
  and 10 of its bytes. The server disconnected and reconnected, and client B wrote a 24-byte
  message. The server's next read returned exactly B's message.
- **A reader cut by a disconnect leaves no waiting flag behind.** A client blocked in `DosRead`
  got 233 when the server disconnected. After the server reconnected with a new client, a query
  of the server end's semaphore gave `{2,0,k,512}`, with no `NPSS_WAIT`.
- **`DosResetBuffer` on a pipe waits for the other end to read.** The client wrote 24 bytes and
  called `DosResetBuffer` (`DosBufReset` at 16 bits). It had not returned after 300 ms. It returned
  rc 0 after the server read the message.
- **A blocking read reaches end of file once the client has gone.** After a disconnect and
  reconnect, while the cut client A still held its handle, client B wrote 10 bytes and closed. The
  server's blocking reads returned 10 bytes, then rc 0 with 0 bytes.

**How the buffer does this.** Read out of the 14.104a SMP kernel's named-pipe routines,
2026-10-01. **[OBS-RE]** unless marked.

- **The ring.**
  - Data lives in `[npb_first, npb_last)`, with `npb_in` the next byte written and `npb_out` the
    next byte read. Both wrap from `npb_last` to `npb_first`.
  - One byte is always left free, so `npb_in == npb_out` means empty.
  - When the writer finds the ring empty, it moves both positions back to `npb_first`.
  - A message's 2-byte length is little-endian and may be split across the wrap.
- **`npb_data`** is written once, when the buffer's reader count reaches 0. It records the bytes
  left unread, and the ring is then emptied. A later write that finds no reader returns 157
  (`ERROR_DISCARDED`) if it is nonzero, else 109.
- **The four control words** (`npb_rdlck`, `npb_wtlck`, `npb_rdsem`, `npb_wtsem`):
  - Each is a "set" byte followed by a "someone is blocked" byte. They hold no counts and no owner
    ids. A thread blocks on the word's own address (DevHlp `ProcBlock`), interruptibly.
  - A reader keeps the read lock, and a writer the write lock, for the whole call, including while
    blocked.
  - Writes signal `npb_rdsem` after each piece copied. Every read pass signals `npb_wtsem`. Close
    and disconnect signal both, then wait to take the lock.
  - An interrupted wait gives 95 (`ERROR_INTERRUPT`). A wait during system shutdown gives 274.
  - Switching an end to no-wait while one of its threads is inside a read or write gives 231.
- **A write is checked in this order.**
  1. A no-wait end first tests for room: a message that could fit later is refused with 0 bytes.
  2. Then the reader count (109/157) and the writer count (233).
  3. A message larger than the whole buffer is written as a blocking write in pieces, even on a
     no-wait end.
  4. A message write interrupted part-way keeps going. A byte write interrupted part-way returns
     the bytes written so far.
- **A read ends at the first of these** (each pass first signals the writer side):
  1. the request filled;
  2. the writer count 0, which is end of file when nothing was read;
  3. the reader count 0, giving 233;
  4. otherwise, for a message read mode read of a partly transferred message, it **waits even on
     a no-wait end**;
  5. with nothing at all present, a no-wait end gives 232 (`ERROR_NO_DATA`) and a blocking end
     waits.
- **Byte read mode on a message pipe** skips the lengths but returns at most one message per call.
  A message longer than the request is shortened in place, with no 234. **[OBS-RE, not
  measured]** IBM's guide says such a pipe "is read as if it were a byte pipe". **[DOC-IBM]**
  > **Measured 2026-10-01 (section 2.2.11):** both halves hold at both widths. The "not measured" tag
  > above is superseded.
- **`DosResetBuffer` on a pipe** waits until the caller's own outgoing ring is empty. It holds the
  write lock, ignores no-wait, and is woken by each read at the other end. ~~If the reader leaves
  first, it returns 109 or 157.~~
  > **WRONG, corrected 2026-10-01 (section 2.2.11):** it returns **0**. The 109/157 was read off the
  > commit routine's order of checks; the layer above it discards that error. Measured: 0 when
  > the server closes, 0 when it disconnects, and 0 at once on a client end already cut off.
- **Pipe-mode bits 0x3800**, which no header names, set a wait limit on every block of that end:
  ((mode & 0x3800) >> 11) x 2 s, ending in 95. Creation and `DosSetNPHState` pass them through.
  **[OBS-RE, not measured]**
  > **Measured, and named, 2026-10-01 (section 2.2.11):** 0x0800 gives 95 after 2 s and 0x3800 after
  > 14 s, at both widths. The Toolkit headers do not name the bits, but IBM's debugging handbook
  > does: `NP_TIMOUT` 0x3800, "Timeout np_sem_blk and np_sem_wait". **[DOC-IBM]** "which no
  > header names" stands for the Toolkit only.

#### 2.2.11 Waiting, opening, connecting, querying and closing [DOC-IBM / OBS-RE / OBS]

**How these were established.** Each **[OBS]** line was run on WSeB 4.50 (kernel 14.089 SMP) on
2026-10-01, with one probe built at both widths: the 32-bit `Dos*NPipe` calls and the 16-bit
`Dos*NmPipe` calls. Both widths gave the same answers except where a line says otherwise. Unless
stated, pipes were 512-byte duplex message pipes in message read mode, with the server end
no-wait. **[OBS-RE]** lines were read from the 14.104a SMP kernel; addresses are facts about that
one build.

##### The block and the wake

- **`ProcBlock` returns three ways.** The kernel's `h_ProcBlock` converts its register arguments
  and calls the 32-bit sleep. A result of 0 is a normal wake (CF clear). 95 or 3000 is an
  interruption (CF set, ZF clear). Any other nonzero result is a timeout (CF set, ZF set).
  `h_ProcRun` wakes the threads blocked on the event and returns their count. **[OBS-RE]** That
  is the DevHlp contract, and ProcRun "awakens all the threads that were blocked for this
  particular event identifier". **[DOC-IBM - PDD reference, ProcBlock / ProcRun]**
- **Every named-pipe wait is interruptible, and an interruption gives 95.** Measured for a thread
  blocked in `DosRead`, `DosConnectNPipe` and an indefinite `DosWaitNPipe`. At 32 bits the
  waiting thread's handler continued `XCPT_ASYNC_PROCESS_TERMINATE` while another thread ended
  the process. At 16 bits a second thread called `DosFlagProcess` on its own process, so thread
  1's signal handler ran. Each call returned 95. **[OBS]**
- **Only three things wake a waiter.** **[OBS-RE]**
  - A `DosConnectNPipe` that moves an instance from DISCONNECTED to LISTENING wakes every
    `DosWaitNPipe` waiter on that name. The event is the name record's key. **[DOC-IBM -
    debugging handbook, "NPN": "Its key value is used as the ProcBlock key for waiters on the
    pipe"]**
  - A client's open wakes a blocked `DosConnectNPipe`. The event is the instance's NP block.
  - The NPB control words wake readers and writers (section 2.2.10).

  `DosClose` and `DosDisConnectNPipe` wake neither of the first two. Consequences, all measured:
  - a blocking `DosConnectNPipe` whose handle another thread closes is still waiting 1.5 s
    later;
  - so is one that another thread disconnects. A client open after that disconnect gets 231,
    because the instance is DISCONNECTED again;
  - a `DosWaitNPipe(2000)` whose pipe's only instance is closed returns 121 after 2000 ms. **[OBS]**
  - **[OBS-RE]** A connect woken later re-checks its handle and returns 230 if the handle has
    gone. Only a client open of an instance can wake it.

##### `NP_TIMOUT`, the pipe-mode bits 0x3800

- IBM names them in the debugging handbook's table of `np_pipmod` / `sf_pipmod` bits:
  `NP_TIMOUT 0x3800 Timeout np_sem_blk and np_sem_wait`. **[DOC-IBM]**
- **Every NPB wait at that end is limited to ((mode & 0x3800) >> 11) x 2 s, and then fails
  with 95.** Each case below did a blocking `DosRead` with no data. **[OBS]**
  - **0x0800 gives 95 after 2.0 s.** This held for:
    - a server end created with the bit, whose `DosSetNPHState` repeated it;
    - the client end of such a pipe;
    - a pipe created without the bit, to which `DosSetNPHState` added it.
  - **0x3800 gives 95 after 14.0 s,** in the first two of those cases.
- **Nothing strips the bits.** A no-wait server end created with 0x0800 reads `0xCD01`, and its
  client `0x0D01`; with 0x3800 they read `0xFD01` and `0x3D01`. **[OBS]**
- **`DosSetNPHState` replaces the bits.** Setting `0x0100` alone dropped them: the state became
  `0x4501`, and a read then waited with no limit. **[OBS]**
- **A byte write that hits the limit returns what it wrote.** A blocking 1000-byte write into an
  empty 512-byte byte pipe with no reader returned rc 0, 512 bytes, after 2 s. **[OBS]**
- **A message write that hits the limit keeps going.** A blocking 1000-byte message into an empty
  512-byte message pipe with no reader was still waiting after 5 s. It returned rc 0 with 1000
  written once a reader took the message. **[OBS]** A message write whose wait fails goes back
  round its loop, so a message is never left half written by a timeout. **[OBS-RE]**
- **`DosConnectNPipe` has no limit.** It waits on its own event, not on an NPB word. A blocking
  connect on such a pipe was still waiting after 5 s, and returned 0 when a client opened.
  **[OBS]**

##### `DosWaitNPipe` / `DosWaitNmPipe`

**[OBS-RE]** The name is translated first. Translation errors come back unchanged:
`DosCallNPipe` turns 206 into 230, but `DosWaitNPipe` does not. Then:
1. A name that is not a local `\PIPE\` name gives 230.
2. No pipe with that name gives 3.
3. If any instance is LISTENING, the call returns 0 at once. No other state counts as available:
   not DISCONNECTED, CONNECTED or CLOSING, and not the internal "client open in progress" state
   (`NP_LISTEN2` 0x12, debugging handbook).
4. Otherwise the call waits on the name's event: for `msec`, or for `msec` 0 the timeout stored
   in the first instance, or forever for `NP_INDEFINITE_WAIT`. It is interruptible.
   - A wake returns 0 **without looking again**, so every waiter returns 0 even when only one
     can then open the pipe.
   - A timeout gives 121. An interruption gives 95.

**All instances of a name share one timeout.** A create for a name that already exists copies
the existing instance's timeout and instance count. Only the high byte of its pipe mode (type,
read mode, blocking, `NP_TIMOUT`) is its own. **[OBS-RE]** A timeout of 0 is stored as 50 ms.
**[OBS-RE]**

**Measured:** **[OBS]**

| case | result |
|---|---|
| no pipe with that name | 3 |
| a name outside `\PIPE\` | 230 |
| a 280-character name | 3 |
| the only instance DISCONNECTED, CONNECTED or CLOSING; `msec` 500 | 121 after about 500 ms |
| an instance LISTENING | 0 at once |
| an indefinite wait, then a no-wait `DosConnectNPipe` 300 ms later | 0, at the connect |
| two waiters, one connect | both 0; the first open succeeds and the second gets 231 |
| `msec` 0; two instances created with timeouts 200 then 1500 | 121 after about 220 ms (both use 200) |
| `msec` 0; created with timeout 0 | 121 after about 60 ms |
| interrupted | 95 |

##### A client's `DosOpen` of a pipe

**[OBS-RE]** The pipe's open routine checks, in this order:
1. The open action `0x10` (create if new, fail if it exists) gives 110.
2. No pipe with that name gives 3.
3. No instance LISTENING gives **231** (`ERROR_PIPE_BUSY`). That one code covers every instance
   in use and a server that is not listening (disconnected, closing, or never connected).
4. Read access needs the outbound (server-to-client) buffer, and write access the inbound one.
   A missing buffer, or an access value above 2, gives 5.
5. The instance becomes CONNECTED, by way of `NP_LISTEN2`, and a blocked `DosConnectNPipe` is
   woken.

The action written back is 3 when the open-action bit `0x02` is set, otherwise 1. The client's
handle state is the creator's pipe mode `& 0x3F00`, so it includes `NP_TIMOUT` (see above, and
section 2.2.8).

**Measured:** **[OBS]**

| case | rc | action |
|---|---|---|
| no pipe with that name | 3 | 10 |
| a 280-character name | 206 | not written |
| created but never connected | 231 | 10 |
| the only instance already connected | 231 | 10 |
| closed by its client and not yet disconnected (CLOSING) | 231 | 10 |
| two instances, only the second listening: first open, then a second | 0, then 231 | 1, then 10 |
| open action `0x10`, and open action `0x00` | 110 | not meaningful |
| access 3 | 12 | not meaningful |
| open action `0x12`, and `0x02` | 0 | 3 |
| inbound pipe: write-only / read-only / read-write | 0 / 5 / 5 | 1 / 10 / 10 |
| outbound pipe: read-only / write-only / read-write | 0 / 5 / 5 | 1 / 10 / 10 |

`ERROR_ACCESS_DENIED` and `ERROR_INVALID_ACCESS` come from different layers: 12 for access 3
appears before the pipe's own check, which gives 5. On these failures the action word was
written with 10 by something not traced; it is not documented, and a program cannot use it.

##### `DosConnectNPipe` / `DosDisConnectNPipe`, checked against section 2.2.6

Every rule in section 2.2.6 holds in the kernel and by measurement. **[OBS-RE]** The connect routine:
- the handle check gives 1 (not a pipe) or 6;
- a client end gives 230;
- CLOSING gives 109;
- CONNECTED gives 0 and changes nothing;
- DISCONNECTED becomes LISTENING, and `DosWaitNPipe` waiters are woken;
- a no-wait end then returns 233. A blocking end waits on the instance, interruptibly
  (interrupted: 95). When it wakes it re-checks the handle (gone: 230) and the state, and this
  time CLOSING counts as success.

The disconnect routine gives 230 on a client end, and otherwise always 0, in any state:
- the client end is cut off: its next read or write gets 233, and its state word's low byte reads
  0 (below);
- the instance becomes DISCONNECTED;
- both buffers are emptied;
- the client's semaphore slot is posted and released.

**Measured:** **[OBS]**

| case | result |
|---|---|
| a blocking connect | waits; returns 0 after the client's open, about 340 ms later; another connect then gives 0 |
| a client opened and closed; two connects with no disconnect | 109, 109; a client open then gives 231 |
| a disconnect on a pipe never connected | 0; the state stays 1; a no-wait connect then gives 233 |
| a disconnect while LISTENING | 0; the state is 1 again; a client open gives 231 |
| two disconnects of a connected pipe | 0, 0; the cut client's state word reads `0x0500` |
| a client end; a handle that is not a pipe | 230; 1 (section 2.2.8) |
| interrupted | 95 |

##### `DosQueryNPHState`

**[OBS-RE]** The state word is the end's handle-state high byte, with the creator's instance
count as the low byte. For a client end cut off by a disconnect, the low byte is 0.

**Measured:** **[OBS]**
- A no-wait message pipe in message read mode with `NP_UNLIMITED_INSTANCES`: server `0xC5FF`,
  client `0x05FF`. The client after a disconnect reads `0x0500`, and the server after the
  disconnect `0xC5FF`.
- A byte pipe with instance count 3: server `0xC003`, client `0x0003`. With the client set
  no-wait it reads `0x8003`; the server after the client's close reads `0xC003`.

##### `DosQueryNPipeInfo`

**[OBS-RE]** The routine:
- `cbBuf` 0 gives 87;
- the handle check gives 1 or 6;
- a client end cut off by a disconnect gives **233**;
- level 1 returns `PIPEINFO`:
  - `cbOut` and `cbIn` are the buffer sizes;
  - `cbMaxInst` is the instance count from creation;
  - `cbCurInst` counts every instance of the name, in any state;
  - the name is "`\PIPE\`" followed by the stored name, with `cbName` counting the NUL;
  - each piece is copied as far as it fits. A buffer that does not hold the whole name and its
    NUL gives 111, with the bytes that fit written.
- Level 2 returns 4 bytes: a field of the client end's file entry that the open copies from the
  opening thread (**[INF]** a network server's per-file identifier, from its name). It is 0
  when no client is connected. A buffer under 4 gives 111 with nothing written.
- Any other level gives 124.

**Measured:** **[OBS]**
- Level 1 is identical from either end. For a 13-character name it writes 21 bytes:
  `cbOut` 512, `cbIn` 512, 1, 1, 14, then the name.
- Buffers of 6, 7, 13 and 20 bytes give 111, with 6, 7, 13 and 20 bytes written. A buffer of 21
  gives 0. `cbBuf` 0 gives 87.
- Level 2 gives 4 zero bytes from either end, with a local client connected and with none.
  Level 2 with 3 bytes gives 111, with nothing written.
- A cut client end gives 233.
- Three instances of one name: `cbCurInst` 3 from each, 2 after one closes. Each instance
  reports its own buffer sizes: one created with 100 and 300 reads `cbOut` 100, `cbIn` 300.

##### `DosPeekNPipe`: how the three counts are made

**[OBS-RE]** The peek runs the read routine with the end's handle state changed: no-wait set,
"peek" set, message *read* mode cleared. The message *type* is kept. Nothing is consumed. The
routine also reads the instance's state byte. The results:
- **`*pcbActual`** is the bytes copied.
  - A byte pipe copies everything present, up to the buffer.
  - A message pipe copies **one message** at most, up to the buffer, whatever the read mode.
- **`cbpipe`** is every byte in the ring, 2-byte message lengths included, whatever the buffer
  size.
- **`cbmessage`** on a message pipe is the length of the first message. If there is no message:
  - it is **0** when the writer is still there and the buffer was not 0;
  - it is **0xFFFF** when the writer has gone, or when the buffer size is 0.

  On a byte pipe `cbmessage` is always 0.
- **The state** is the instance's state. `NP_LISTEN2` reads as 2.
- **A client end cut off by a disconnect** returns 0, with 0 bytes, `cbpipe` and `cbmessage` 0,
  and state 1 (section 2.2.8).

This settles section 2.2.8's open point: **the buffer size decides** the 0xFFFF, not the end.

**Measured:** **[OBS]**

| pipe | queued | buffer | n | cbpipe | cbmessage | state |
|---|---|---|---|---|---|---|
| byte | nothing | 64 or 0 | 0 | 0 | 0 | 3 |
| byte | 10 + 10 bytes | 64 / 5 / 0 | 20 / 5 / 0 | 20 | 0 | 3 |
| byte | 20 bytes, then the server closed | 64 | 20 | 20 | 0 | 4 |
| byte | drained after the server closed | 64 | 0 | 0 | 0 | 4 |
| message | nothing (client and server ends alike) | 64 | 0 | 0 | 0 | 3 |
| message | nothing (client and server ends alike) | 0 | 0 | 0 | 0xFFFF | 3 |
| message | messages of 10 and 20 | 64 / 4 / 0 | 10 / 4 / 0 | 34 | 10 | 3 |
| message | the same, the end in byte read mode | 64 | 10 | 34 | 10 | 3 |
| message | after a 4-byte byte-read-mode read of the first | 64 | 6 | 30 | 6 | 3 |
| message | the same, then the server closed | 64 | 6 | 30 | 6 | 4 |
| message | drained after the server closed | 64 or 0 | 0 | 0 | 0xFFFF | 4 |

##### A no-wait call while another thread of the same end is inside one

**[OBS-RE]** A no-wait end does not wait for that end's read or write lock: the lock routine
returns failure with **AX 0**. What the caller then sees depends on the path.
- **A read** returns error 0, which a program sees as success with 0 bytes.
- **A write** returns as its "error" the offset of the instance's NP block, left in AX by a pop.
- **A peek** fails before it stores the `AVAILDATA`, so that is not written.

To make the first thread hold the lock while the end is no-wait, it ran a call that waits
regardless: a raw read with nothing queued, or a no-wait message longer than the buffer. A
blocking end simply waits for the lock.

**Measured:** **[OBS]**
- A raw read was blocked on the server end. A no-wait `DosRead` on the same end returned
  **rc 0, 0 bytes**.
- A `DosPeekNPipe` there returned rc 0 and 0 bytes, with the state written (3) and the
  `AVAILDATA` **not written**.
- A no-wait 1000-byte message write was blocked on the server end. A no-wait 10-byte
  `DosWrite` on the same end returned **rc 546, 0 bytes**: not an error code.

**Why the read and the write differ, from the bytes** (14.104a SMP) **[OBS-RE]**. Both paths
call the same lock routine, which on a no-wait end returns CF set with AX 0 for a held lock.
- The read path pushes four registers on entry. On failure it pushes **AX (0)** as the result,
  so the caller gets error 0: rc 0 with 0 bytes.
- The write path pushes the same four plus a **second copy of DI**. Its success path drops that
  copy with `pop ax` before it calls the write routine, and its failure path does the same
  `pop ax` and then pushes **AX** as the result. AX now holds that copy of DI. DI was loaded from
  the handle's file-table entry (`les di,[es:di+0x1d]`), so it is the offset of the instance's
  NP block in the kernel's NP pool. The count is computed as the requested count minus itself,
  so 0.
- The layers above the pipe write keep AX when CF is set, and so does the 16-bit `DosWrite`:
  0 bytes is a short write, so it asks the handle's type, gets a pipe (not a file), and returns
  the first result unchanged (see the closing case below for that routine).

So the value is **not undefined**: every byte that produces it is accounted for, and it is the
NP block's offset. It is **not an error code** either. 546 is in the Toolkit's error list as
`ERROR_PRF_ALREADY_STARTED` (`bseerr.h`) **[DOC-IBM]**, and that is a coincidence: other
offsets give other numbers.

**Measured, 2026-10-01, WSeB 4.50 (14.089 SMP), both widths, identical** **[OBS]**. Each row
held the write lock with a blocked 1000-byte message write, then made a no-wait 10-byte write
on the same end:

| instances created first, and kept open | where the lock was held | rc of the 10-byte write |
|---|---|---|
| none | server end | 546 (0x222) |
| 1 | server end | 942 (0x3AE) |
| 2 | server end | 986 (0x3DA) |
| 5 | server end | 1118 (0x45E) |
| none | client end, set no-wait | 546 (0x222) |
| none, 100-byte buffers | server end | 546 (0x222) |
| none; 5 created after the pair | server end | 546 (0x222) |
| a first pair still open | the second pair's server end | 942 (0x3AE) |

The result moves only with instances allocated **before** the pair, not with the end, the
buffer size, or instances allocated after: it is the block's offset. Each further block lies
0x2C above the last, and the first allocation took a free block at 0x222 below them. **[INF]**
that the pool is filled first-fit: the allocator itself (a far call from `get_free_np`) was not
read. The pool is system-wide, so the number also depends on what other processes hold.

##### More about reading

- **No-wait, nothing queued: rc 232 (`ERROR_NO_DATA`), with the count written as 0.** This held
  at both ends of a message pipe and on a byte pipe. **[OBS]** That is the `DosCreateNPipe`
  page's code. The programming guide's "returns immediately with 0 in the Bytes-Read parameter"
  is true of the count. **[DOC-IBM]**
- **Byte read mode on a message pipe returns one message per call.** Two 10-byte messages
  queued: two reads of 64 returned 10 bytes each.
  A 4-byte read of a 10-byte message returned rc 0 with 4 bytes, and no 234. The message was
  shortened in place: a peek then showed `cbpipe` 8 and `cbmessage` 6. The next read returned
  the 6 bytes, and the 10 were intact. **[OBS]**
- **A blocking read on a server end with no client returns rc 0 with 0 bytes, at once.** This
  held whether the instance was DISCONNECTED (never connected) or LISTENING. **[OBS]** The
  writer count of the server's read buffer is 0 until a client opens, and the read routine
  checks it before waiting. **[OBS-RE]**
- **A read of 0 bytes returns rc 0 at once.** The kernel's read returns before it reaches the
  pipe. **[OBS; OBS-RE]**

##### A no-wait message longer than the buffer, into a nearly full ring

section 2.2.10's rule that such a message "is written whole" holds only while **2 or more bytes** are
free. Each case below filled a 512-byte message buffer, then wrote a 600-byte message no-wait,
with a reader in message read mode draining after 300 ms. **[OBS]**
- **2 bytes free:** the reader read the five fill messages, then the 600.
- **1 byte free:** the writer returned rc 0 with 600 written. The reader read the five fill
  messages and then waited. The ring held the length's low byte (`58`) and then the message: the
  high byte was lost. A peek read `cbmessage` 31320 (`0x7A58`: the low byte and the first message
  byte).
- **0 bytes free:** the length was lost entirely. The peek read 31354 (`0x7A7A`, two message
  bytes).

**[OBS-RE]** The write routine copies the 2-byte length with the same ring copy as the body, and
does not check what was left over. For a message larger than the whole buffer, the no-wait room
test answers "room" whatever is free. A reader that meets a torn length waits for a message of
that length.

##### `DosResetBuffer`

- **The result is 0 once the handle is valid.** **[OBS-RE]** The routine:
  - returns 0 at once, without flushing, while a system flag (`NoResetBuffer`) is set;
  - checks the handle, its physical handle and the entry lock, and fails with their errors (6);
  - runs the commit.

  The commit's result is then lost: restoring a thread flag (`and al,0xfd`) clears CF before the
  result is tested. So a pipe's 109, 157 or 233 never reaches the caller.
- **Measured:** **[OBS]**
  - nothing written: 0 at once;
  - 24 bytes written and waiting: 0 when the server closed its end 350 ms later, and 0 when the
    server disconnected 350 ms later;
  - a client end already cut off: 0 at once;
  - on the server end, waiting for the client to read: 0 at the read.

##### Closing an end while another thread of the same process is blocked on it

**[OBS-RE]** `DosClose` runs the pipe's close before it waits for the entry's other users. That
close empties the closing end's read buffer, drops its writer count, signals both buffers, and
waits for the blocked thread to leave. The blocked thread wakes, finds its counts gone, and
fails with 233.

**Measured:** **[OBS]**

| blocked thread | other thread | result |
|---|---|---|
| client, in `DosRead` | closes the client end | close 0 at once; the read returns **233**; the server's peek shows state 4 |
| server, in `DosRead` | closes the server end | close 0; the read returns **233**; the client's next read is end of file (0 bytes) |
| client, writing a 1000-byte message into the 512-byte buffer | closes the client end | close 0; the write returns **233** at 32 bits and **6** at 16 bits; the server still sees the partial message, `cbpipe` 512 and `cbmessage` 1000 |
| server, writing 1000 bytes into a 512-byte byte pipe | closes the server end | close 0; the write returns **233** at 32 bits and **6** at 16 bits; the client reads the 512 bytes |
| in `DosConnectNPipe` | closes the server end | close 0; the connect is still waiting 1.5 s later |
| in `DosWaitNPipe(2000)` | closes the only instance | 121 after 2000 ms |

~~**The 16-bit 6 is the 16-bit `DosWrite`'s own doing.** **[OBS-RE, `DOSWRITE` in the measured
system's own `DOSCALL1.DLL`]** When fewer bytes were written than asked, it calls `DosQHandType` on the handle.
If the type's low byte is 0, which means a file, it runs a disk-full recovery routine and
repeats the write. With the handle already closed, `DosQHandType` fails without writing the type.
So the test reads whatever the local held, and the repeated write fails with 6. **[INF]** that
the result depends on that leftover stack content; both measurements gave 6.~~

**WRONG in one part, corrected 2026-10-01.** The routine is described correctly. The claim that
`DosQHandType` "fails without writing the type" is false: the kernel's 16-bit entry for it
writes the type on failure too, as **0**. So nothing depends on leftover stack. The 6 is a
defined result: the repeated write's honest answer on a closed handle. The earlier reading
described the kernel call without following it.

**The 16-bit `DosWrite` (`DOSWRITE`, `DOSCALL1.DLL` 0003:e3c0, the measured system's build)**
**[OBS-RE]**:
1. It calls the write (`DOSPWRITE`, which calls the kernel's 16-bit write, `DOSCALLS.87`) and
   keeps the result.
2. If the count written differs from the count asked, **or** the result is 112
   (`ERROR_DISK_FULL`), it calls `DosQHandType` (`DOSCALLS.77`) on the **same handle number**.
   The result of that call is not looked at.
3. If the type's low byte is nonzero (a device or a pipe), it returns the first result.
4. If it is 0 (a file), it calls a routine that purges the `DELDIR` delete directory
   (`_EraseFiles`), then repeats the write with the same arguments and returns the repeat's result
   and count. The purge routine was read only as far as its exit when `DELDIR` is not set, which
   it takes at once; that it purges the delete directory otherwise is **[INF]** from its strings
   (`DELDIR`, `\CONTROL.DEL`).

**The kernel's 16-bit `DosQHandType` on a closed handle** **[OBS-RE]**. The entry stub calls the
worker through the common far-call helper. When the worker fails, that helper moves the error to
DI, sets **AX to 0**, and returns to the same tail as success. The tail stores AX into the type
and BX into the attribute, so a failed call writes **type 0** and an attribute of whatever BX
held. The worker fails because the handle's entry is free, which gives 6.

So for a closed handle the 16-bit `DosWrite` sees type 0, takes it for a file, and repeats the
write. The repeat finds no handle and returns 6 with the count 0.

**Measured, 2026-10-01, WSeB 4.50 (14.089 SMP)** **[OBS]**:
- `DosQHandType` on a closed handle, both outputs preset to 0xBEEF: rc 6, type 0, attribute 3
  (the handle number was also 3). The same at 32 bits (`DosQueryHType`).
- A client blocked writing a 1000-byte message into a 512-byte buffer; another thread closed the
  client end and then, at time-critical priority, at once duplicated another handle into the
  freed handle number. Three runs of each:

| duplicated into the freed number | 16-bit `DosWrite` | 32-bit `DosWrite` |
|---|---|---|
| nothing | rc 6, 0 bytes (3 of 3) | rc 233, 0 bytes (3 of 3) |
| a new file | **rc 0, 1000 bytes; the file holds 1000 bytes** (3 of 3) | rc 233, 0 bytes; the file is empty (3 of 3) |
| `NUL` | rc 233, 0 bytes (2 of 3); rc 0, 1000 bytes (1 of 3) | rc 233, 0 bytes (3 of 3) |

The file row shows the repeat going to the same handle number. The `NUL` row shows the type test
and the repeat as two separate calls. When the duplicate lands before the type query, the device
type stops the repeat and the first result, 233, comes back. In the one run where it landed
between the query and the repeat, the query saw a closed handle (type 0) and the repeat wrote to
`NUL`. The 32-bit `DosWrite` has no such repeat.

##### Semaphore handles that resolve to nothing

**[OBS-RE]** Both `DosSetNPipeSem` and `DosQueryNPipeSemState` first ask whether the handle is a
32-bit semaphore: the 32-bit handle form, found in the shared or the per-process table. Anything
else, including a 32-bit-form handle with no entry, goes to the 16-bit semaphore lookup:
- **A high word of 2 or 3 is a 16-bit system-semaphore handle.** An index or entry that is not
  in use takes the lookup's failure path (`SemProtFault`); measured below, the caller is ended
  by a trap. What that path does internally was not followed.
- **Any other value is treated as a RAM semaphore's address and returned unchecked.** Then:
  - `DosSetNPipeSem` accepts only a system semaphore, so it gives **187**;
  - `DosQueryNPipeSemState` accepts any nonzero value. It walks the instances for one whose
    slot holds that value, finds none, and returns **0 with just the EOI**.

  This is why section 2.2.8 measured 187 from one call and 0 from the other for the same handle.

**Measured:** **[OBS]**
- At 32 bits, each of these gave `DosSetNPipeSem` 187 and `DosQueryNPipeSemState` 0 with the EOI
  byte:
  - a shared event semaphore created and closed (`0x800100F5`);
  - a private one created and closed (`0x00010000`);
  - the never-issued handles `0x8001FFF0` and `0x0001FFF0`.
- At 16 bits, three handles: a system semaphore created and closed (`0x0002001C`), and the
  never-issued `0x000300FE` and `0x000200FE`. Each call ended the process with a trap, SYS3175,
  `c0000005`. The address was the instruction after the call into the kernel.

##### The named-pipe instance limit is system-wide

On a disposable clone of WSeB 4.50 (14.089), 2026-10-01: **[OBS]**
- One process created duplex instances until a create failed: 1,483, then 84, as section 2.2.9 says.
- With a second process holding 500 instances, the same run stopped at **983**.
- After the second process ended, 1,483 again.

**[OBS-RE]** The pool of NP blocks and the active-instance list are single variables in the
kernel's data, so every process's instances count against one limit.

##### What the 32-bit entries pass to the 16-bit ones

**[OBS-RE, `DOSCALL1.DLL` (a March 2002 build), its 32-bit entries and `THK32_UNITHUNK`]**
Each 32-bit named-pipe entry
loads a descriptor and enters a general thunk that converts each argument for the 16-bit
routine. Decoded:

| 32-bit entry | arguments as the 16-bit routine receives them |
|---|---|
| `DosCreateNPipe` | name (a string); `PHPIPE` (a 2-byte result whose high word is zeroed); open mode, pipe mode, outbound size and inbound size, each **pushed as a 16-bit word**; `msec` (32 bits) |
| `DosWaitNPipe` | name (a string); `msec` (32 bits) |
| `DosQueryNPipeInfo` | handle (word); level (word); buffer (its size taken from the next argument); size (word) |
| `DosPeekNPipe` | handle (word); buffer (sized by the next argument); size (word); `pcbActual` (2-byte result, high word zeroed); `AVAILDATA` (4 bytes); `pState` (2-byte result, high word zeroed) |
| `DosTransactNPipe` | handle; out-buffer and its size; in-buffer and its size; `pcbRead` (2-byte result, high word zeroed). The handle and sizes are words |
| `DosRawReadNPipe` / `DosRawWriteNPipe` | handle (word); buffer and its size (word); count (2-byte result, high word zeroed) |

So each 32-bit count and mode keeps only its low 16 bits. That is the mechanism behind section 2.2.8's
`cbIn` 0x10000 behaving as 0 and section 2.2.9's size table.

##### What a program can observe of buffer memory

Only two things:
- a create that fails with 8;
- the system's resident-memory count growing per instance (`QSV_TOTRESMEM`, section 2.2.9).

The allocator's segment flags and the way the resident heap commits pages inside its 16 MB
ceiling are mechanism behind those two, with no further effect a program can see. They were not
read further. **[INF]**

### 2.3 Pipe error codes [DOC-IBM - `bseerr.h`]

| Error | Value | Meaning |
|---|---|---|
| `ERROR_BROKEN_PIPE` | 109 | The other end of the pipe has closed. |
| `ERROR_BAD_PIPE` | 230 | Handle is not a named pipe, or bad state for the operation. |
| `ERROR_PIPE_BUSY` | 231 | All pipe instances are busy. |
| `ERROR_PIPE_NOT_CONNECTED` | 233 | Pipe has no connected client. |
| `ERROR_MORE_DATA` | 234 | Message read was truncated; more data remains. |

---

## 3. Queues

A queue is a named, single-owner FIFO/LIFO/priority list of elements that many processes can
write to and the owner reads from. Each element is a `(request-code, data-pointer, length)`
triple tagged with the writing process's PID. Declared under `INCL_DOSQUEUES`. The handle type is
`HQUEUE` (`typedef LHANDLE HQUEUE`). The queue name must begin `\QUEUES\`. **[DOC-IBM -
`bsedos.h`; DOC - Control Program Reference]**

> **CORRECTED (Rule 1.7):** this said the name begins `\QUEUES\` "by convention". It is a rule:
> `DosCreateQueue` refuses a name without the prefix with 335 `ERROR_QUE_INVALID_NAME`.

**Name rules, measured** [OBS - measured on Warp Server for e-business 4.50, kernel revision
14.089, by 32-bit probes calling `DosCreateQueue` / `DosOpenQueue`]:

| Name | Result |
|---|---|
| `""`, `NOPREFIX`, or the bare prefix `\QUEUES\` | 335 |
| `\queues\lower` (prefix in lower case) | 0 |
| total length 9 (prefix plus one character) up to 259 | 0 |
| total length 260 or more | 335 - the name *including its NUL* must fit 260 bytes (`CCHMAXPATH`) |
| two 130-character names identical in their first 127 characters | 0 and 0 - two distinct queues; the whole name is significant |
| create `\QUEUES\CANONCASE`, open `\queues\canoncase` | both 0 - one queue; names compare case-insensitively |
| create `/QUEUES/SLASHCRE` | 0 - `/` is accepted |
| create `\QUEUES\CANONSEP`, open `/QUEUES/CANONSEP` | both 0 - one queue; `/` and `\` are the same separator |

**The NULL-name trap.** `DosCreateQueue(&hq, QUE_FIFO, NULL)` as a process's **first** call into the
queue API ends the process silently: no further output, exit status 0, no SYS3175 pop-up and no
`POPUPLOG.OS2` entry. Once the process has made any earlier `DosCreateQueue` call, whether it
succeeded or was refused (335), the same NULL call returns 87 and the process carries on
[OBS - measured, three single-purpose probes, one process each]. **The tell:** a program or test
that "just stops" at its first queue call with exit code 0. Never pass NULL; and in a test, put any
case that can end the process last.

**No small per-process limit.** One process created 60 queues and opened 4 more, then created a
61st and opened a 5th: both returned 0 [OBS - measured, a 16-bit probe].

| Function | One-line purpose |
|---|---|
| `DosCreateQueue` | Create and own a named queue with an ordering discipline. |
| `DosOpenQueue` | Obtain a write handle to an existing named queue; returns the owner's PID. |
| `DosCloseQueue` | Close this process's handle to the queue (destroys it for the owner). |
| `DosReadQueue` | (Owner) Remove and return the next / a specific element, optionally blocking. |
| `DosPeekQueue` | (Owner) Read an element without removing it. |
| `DosWriteQueue` | Add an element (request code, data, priority) to the queue. |
| `DosPurgeQueue` | (Owner) Discard all elements. |
| `DosQueryQueue` | Return the number of elements currently in the queue. |

```c
APIRET APIENTRY DosCreateQueue(PHQUEUE phq, ULONG priority, PSZ pszName);
APIRET APIENTRY DosOpenQueue(PPID ppid, PHQUEUE phq, PSZ pszName);
APIRET APIENTRY DosCloseQueue(HQUEUE hq);
APIRET APIENTRY DosReadQueue(HQUEUE hq, PREQUESTDATA pRequest, PULONG pcbData, PPVOID ppbuf,
                             ULONG element, BOOL32 wait, PBYTE ppriority, HEV hsem);
APIRET APIENTRY DosPeekQueue(HQUEUE hq, PREQUESTDATA pRequest, PULONG pcbData, PPVOID ppbuf,
                             PULONG element, BOOL32 nowait, PBYTE ppriority, HEV hsem);
APIRET APIENTRY DosWriteQueue(HQUEUE hq, ULONG request, ULONG cbData, PVOID pbData,
                              ULONG priority);
APIRET APIENTRY DosPurgeQueue(HQUEUE hq);
APIRET APIENTRY DosQueryQueue(HQUEUE hq, PULONG pcbEntries);
```

### 3.1 Ordering discipline (`priority` on create) [DOC-IBM - `bsedos.h`]

| Constant | Value | Meaning |
|---|---|---|
| `QUE_FIFO` | `0L` | First-in, first-out. |
| `QUE_LIFO` | `1L` | Last-in, first-out. |
| `QUE_PRIORITY` | `2L` | Ordered by the per-element priority byte (0-15, 15 highest). |
| `QUE_NOCONVERT_ADDRESS` | `0L` | Do not address-convert element data across the 16/32-bit boundary. |
| `QUE_CONVERT_ADDRESS` | `4L` | Address-convert 16-bit element data pointers for the reader. |

The discipline and the convert flag are OR-combined in the `priority` parameter of
`DosCreateQueue`. **[DOC-IBM - `bsedos.h`]**

### 3.2 Element identity [DOC-IBM - `bsedos.h`]

Each read/peek fills a `REQUESTDATA` identifying who wrote the element and carrying a
caller-defined `ULONG`:

```c
typedef struct _REQUESTDATA {   /* reqqdata */
   PID    pid;      /* PID of the process that wrote the element */
   ULONG  ulData;   /* caller-defined value (the request code)   */
} REQUESTDATA, *PREQUESTDATA;
```

The queue stores a pointer to the element data, not a copy; the writer and the owner must share
access to that memory (for example via shared memory), which is why `QUE_CONVERT_ADDRESS` exists
for 16-bit writers. A blocking `DosReadQueue` (`wait = TRUE`) sleeps until an element is
available; alternatively an event semaphore (`hsem`) can be supplied and posted when the queue
becomes non-empty. **[DOC-IBM - `bsedos.h`]**

On write, the per-element priority byte is honoured only for a `QUE_PRIORITY` queue: priority 15
adds the element at the top (LIFO within that priority), 0 adds it at the tail, and elements of
equal priority stay FIFO. Reading with an `element` code of 0 removes elements in the queue's
creation-order discipline; a non-zero code (obtained from `DosPeekQueue`) removes a specific
element. **[DOC - EDM2 "DosWriteQueue (OS/2 1.x)", "DosReadQueue (OS/2 1.x)"]**

### 3.3 Per-call return codes [DOC - EDM2 "DosReadQueue (OS/2 1.x)", "DosWriteQueue (OS/2 1.x)"]

- `DosReadQueue` returns `NO_ERROR`, `ERROR_QUE_PROC_NOT_OWNED` (330 - a non-owner tried to read),
  `ERROR_QUE_ELEMENT_NOT_EXIST` (333), `ERROR_QUE_INVALID_HANDLE` (337), `ERROR_QUE_EMPTY` (342 -
  empty queue with no-wait requested), or `ERROR_QUE_INVALID_WAIT` (433).
- `DosWriteQueue` returns `NO_ERROR`, `ERROR_QUE_NO_MEMORY` (334), or `ERROR_QUE_INVALID_HANDLE`
  (337 - returned when the owning process has terminated or the queue was closed before the write).

### 3.4 Queue error codes [DOC-IBM - `bseerr.h`]

| Error | Value | Meaning |
|---|---|---|
| `ERROR_QUE_PROC_NOT_OWNED` | 330 | Only the owner may read/peek/purge. |
| `ERROR_QUE_DUPLICATE` | 332 | A queue of that name already exists. |
| `ERROR_QUE_ELEMENT_NOT_EXIST` | 333 | The requested element does not exist. |
| `ERROR_QUE_NO_MEMORY` | 334 | Out of memory managing the queue. |
| `ERROR_QUE_INVALID_NAME` | 335 | Malformed queue name. |
| `ERROR_QUE_INVALID_PRIORITY` | 336 | Invalid ordering/priority value. |
| `ERROR_QUE_INVALID_HANDLE` | 337 | Invalid queue handle. |
| `ERROR_QUE_EMPTY` | 342 | Queue has no elements. |
| `ERROR_QUE_NAME_NOT_EXIST` | 343 | Named queue does not exist (on open). |
| `ERROR_QUE_NOT_INITIALIZED` | 344 | Queue subsystem not initialized. |
| `ERROR_QUE_INVALID_WAIT` | 433 | Invalid wait combination. |

---

## 4. Naming and lifetime summary [DOC / DOC-IBM]

| Object | Handle | Name prefix | Created private by | Made shared by |
|---|---|---|---|---|
| Mutex semaphore | `HMTX` | `\SEM32\` | unnamed create | a name, or `DC_SEM_SHARED` |
| Event semaphore | `HEV` | `\SEM32\` | unnamed create | a name, or `DC_SEM_SHARED` |
| MuxWait semaphore | `HMUX` | `\SEM32\` | unnamed create | a name, or `DC_SEM_SHARED` |
| Anonymous pipe | `HFILE` pair | (none) | always | handle inheritance |
| Named pipe | `HPIPE` | `\PIPE\` | - (server-owned, client-opened) | its name |
| Queue | `HQUEUE` | `\QUEUES\` | - (single owner, many writers) | its name |

All named objects live in the shared arena and persist as long as at least one handle to them
remains open; the object is destroyed when the last handle closes (for a queue, closing the
owner's handle destroys it). A named semaphore/pipe/queue name is a case-insensitive path-style
string under its prefix. **[DOC - Control Program Reference; DOC-IBM - `bsedos.h` for the
attribute mechanics]**

---

## 5. 16-bit RAM semaphores - the `DosSemXxx` family

The three 32-bit semaphore types above are the OS/2 2.0 API. OS/2 also retains the **16-bit
semaphore family** inherited from OS/2 1.x, and it is not vestigial: shipped 32-bit Presentation
Manager code still reaches it through 32->16 thunks for its own internal locking, so this family
is live on any running OS/2 system regardless of what applications call.

### 5.1 The API [DOC-IBM - `bsedos16.h`]

```c
#define SEM_INDEFINITE_WAIT       -1L
#define SEM_IMMEDIATE_RETURN       0L

APIRET APIENTRY DosSemClear   (HSEM hsem);
APIRET APIENTRY DosSemSet     (HSEM hsem);
APIRET APIENTRY DosSemWait    (HSEM hsem, LONG lTimeOut);
APIRET APIENTRY DosSemSetWait (HSEM hsem, LONG lTimeOut);
APIRET APIENTRY DosSemRequest (HSEM hsem, LONG lTimeOut);
```

(Under `INCL_NOXLATE_DOS16` these are spelled `Dos16SemClear` ... `Dos16SemWait`.) The timeout is
the same millisecond convention as the 32-bit API, with the same two named extremes.

### 5.2 Two kinds of `HSEM`, discriminated by the selector [OBS-RE]

An `HSEM` in this family is either a **system-semaphore handle** or a **far pointer to a RAM
semaphore** - a caller-allocated dword of memory rather than a kernel object. The kernel tells
them apart by the *selector half* of the argument: the values **2 and 3** are type tags selecting
the system-semaphore paths, and any other value is treated as a real selector and the argument as
a `selector:offset` pointer to the RAM semaphore itself. The same two-value test appears
independently at the head of the kernel's `SemWait`, `SemSet` and `SemClear` bodies, each falling
through to the RAM-semaphore path when it does not match; the entry stub for `DosSemWait` loads
the selector half into the register those tests read.

A RAM semaphore therefore has **no handle, no name, and no kernel-side object**: it is memory the
owning code declares, and the kernel only ever visits it when a fast-path acquire has already
failed. It cannot be shared by name; it is shared exactly as far as the memory holding it is.

### 5.3 The `FastSafeRamSemStruc` wrapper [DOC-IBM]

IBM defines a standard wrapper that pairs a RAM semaphore with the ownership bookkeeping the raw
word does not carry. It appears identically in two independent DDK sources - `FastSafeRamSemStruc`
(video DDK `sem.inc`) and `FSRST`, "fast safe ramsem with timeout" (base DDK `dbgapi.inc`) - and
the system's own debug API enumerates instances of it (`DBSEM_FSRST`), so it is an architectural
structure rather than one component's convention.

| Offset | Field | Size | Meaning [DOC-IBM - `sem.inc` prose] |
|---|---|---|---|
| `+0x00` | `fs_Length` | 2 | Size of this structure in bytes. |
| `+0x02` | `fs_Padding` | 2 | Padding, explicitly "for 32 bit alignment". |
| `+0x04` | `fs_ProcID` | 2 | Process ID of the owner, or zero if unowned. |
| `+0x06` | `fs_ThrdID` | 2 | Thread ID of the owner, or zero if unowned. |
| `+0x08` | `fs_Usage` | 2 | Reference count: incremented on each acquire by the current owner, decremented on each release; **ownership is not actually released until it reaches zero** (i.e. the lock is recursive). |
| `+0x0A` | `fs_Client` | 2 | Not interpreted by the semaphore code - a field the owner may use to record *which* resource it holds, zeroed when the semaphore is first acquired. Intended for a `DosExitList` handler deciding on cleanup. |
| `+0x0C` | `fs_Timeout` | 4 | Timeout to use when waiting on the RAM semaphore. |
| `+0x10` | `fs_RAMSem` | 4 | **The RAM semaphore itself**, manipulated "in the same manner as the ring 3 semaphore code in CPDOS (e.g. `DOSSEMREQUEST` and `DOSSEMCLEAR`)". |

Note `fs_ProcID`/`fs_ThrdID` are adjacent halves of one aligned dword, and code that owns such a
semaphore compares ownership with a single dword compare against its own PID:TID pair. **[OBS-RE]**
The two halves are in the order the thread's own local InfoSeg supplies them: `LIS_CurProcID` at
LINFOSEG `+0x00` is the low half and `LIS_CurThrdID` at `+0x06` the high half, so an owner stamps
this dword by reading those two fields and can then test ownership in one compare. The structure
layout, the InfoSeg layout, and the observed instruction sequence agree independently.
**[DOC-IBM for both layouts; OBS-RE for the sequence]**

### 5.4 The RAM semaphore word itself [OBS-RE, with [DOC-IBM] for the owner byte]

`fs_RAMSem` is declared as a **dword**. The lock itself lives in the low **word**, in three
distinct fields:

> **Provenance corrected 2026-08-31 (Rule 1.7).** 1 claim in this document
> was tagged `[OBS-RE]` and is now `[OBS]`. **No claim changed** - only the
> label for how it was established. `[OBS-RE]` means *read out of a binary or the
> kernel debugger*, an interpretation; `[OBS]` means *a capture from a running
> system*, no interpretation. Each of these was a probe run on real OS/2 whose
> return codes were recorded, so `[OBS]` is the tag, and the re-verification is
> "run the probe again" rather than "read the bytes again". The two had drifted
> because `[OBS]` was in use throughout the corpus with **no definition at all**
> until that date; see `README.md`, *Provenance*.


> **CORRECTED [OBS], measured on a live system:** an earlier revision of this section said
> "every kernel operation on it addresses the low word". That is **false** - the kernel also
> writes the **upper word**. A probe that sets `fs_RAMSem = 0x00000001` and takes one contended
> wait reads back e.g. `0x3E1B0101`: byte 1 is the waiter flag (below), and bytes 2-3 carry a
> kernel-stamped value that increases monotonically and **persists across processes**. What it
> counts is not established. The practical consequence is for anyone building a futex-style wait
> on this field: the upper half changes for reasons unrelated to the lock, so a 32-bit wait on
> the whole dword will see spurious wakes (harmless, since every waiter re-tests the lock, but
> it must be expected rather than discovered).

> **NARROWED 2026-08-27 [OBS-RE]** (marked, not rewritten - the measurement above is exactly what
> the probe saw, and the box is kept because the natural reading of it is the part that turned out
> to be wrong). Two claims in it are narrower than they read, and the routine that settles both is
> **`PutRamSemID` `0003:30F2`**, disassembled directly from the kernel image because the corpus
> listing stops 92 bytes short of it:
>
> ```
> 000330F2  8B4702        mov ax,[bx+0x2]
> 000330F5  0BC0          or  ax,ax
> 000330F7  0F851300      jnz near 0x310e      ; assign ONCE, never re-assign
> 000330FB  681700        push word 0x17
> 000330FE  07            pop es
> 000330FF  F026FF063E8C  lock inc word [es:0x8c3e]   ; CurrentRamSemID++, system-wide
> 00033105  74F8          jz  0x30ff                  ; skip 0 on wrap
> 00033107  26A13E8C      mov ax,[es:0x8c3e]
> 0003310B  894702        mov [bx+0x2],ax             ; stamp the ID into sem+0x2
> 0003310E  C3            ret
> ```
>
> - **"increases monotonically" describes the ALLOCATOR, not the field.** `CurrentRamSemID` is a
>   16-bit counter, so the ID space wraps at 65535 and values are reused; `jz` skips zero because
>   zero is the "unassigned" value the `or ax,ax` test depends on. The `lock inc` is atomic but the
>   value is then **re-read** unsynchronised, so two threads can stamp the same ID into two
>   different semaphores. Uniqueness is IBM's intent, not an invariant IBM enforces.
> - **"the upper half changes for reasons unrelated to the lock" is true at most ONCE per
>   semaphore, not continuously.** The `or ax,ax / jnz` makes the stamp idempotent: the ID is
>   assigned lazily on the first contended wait (`RamSemWait` calls it at `00032ED4`, just before
>   blocking) and never re-assigned. Release does not disturb it either - the ring-3 release is a
>   **16-bit** `xchg` against the lock word only, so `sem+0x2` survives, which is precisely what
>   the idempotence assumes. So a 32-bit wait on the whole dword can see **one** such spurious
>   wake in the life of a semaphore, on its first contention - and a host that does not assign
>   these IDs at all sees none, because nothing else on any path writes the upper word. Either
>   way it stays harmless for the reason the box already gives: every woken waiter re-tests the
>   lock (section 5.5), and the held-test is `word & 0xF0FF`, which cannot see the upper half at all.

| Bits | Field | Role |
|---|---|---|
| 0-7 | owner byte | Non-zero = held. IBM names this sub-field **`RamSemOwner`** and reserves the value `0xDB` (`DBG_RAMSEM_OWNED`) to mean the system debugger holds it - so it carries an owner *value*, not merely a 0/1 flag. **[DOC-IBM - `dbgapi.inc`]** |
| 8-11 | waiter flags | Set by the kernel to publish "a thread is blocked on this semaphore". **Flags, not a count** - see section 5.6. |
| 12-15 | set bits | Part of the "is it held" test alongside the owner byte. |

The kernel's held-test is therefore `word & 0xF0FF`, deliberately excluding the waiter nibble:
a semaphore with waiters but no owner reads as *free*. `SemSet` sets exactly `0xF0FF`; the
release paths (`SemClear`, and the kernel's own RAM-sem acquire) clear with `and word, 0x0F00`,
i.e. they clear the owner byte and the set bits while **preserving the waiter flags**. **[OBS-RE]**

> **CORRECTED 2026-09-15 [OBS-RE] - "preserving the waiter flags" is true of `SemClear`'s `and`
> alone, not of the release.** Its next two instructions are `xor al,al` / `xchg al,[bx+0x1]`:
> the waiter byte is zeroed and its old value kept, and control enters `RamSemWakeSub`'s per-bit
> dispatch (bit 8 of the word wakes a thread blocked directly on the semaphore, bit 9 a
> registered MuxWait). A semaphore released through `SemClear` reads `0x0000` in its low word.
> Scope: `SemClear` only; the RAM-sem acquire path named above was not re-read. SMP debug
> kernel `os2krnld`, `SemClear` (`0003:2C52`), instructions `00032CA8`-`00032CAF`.

### 5.5 The two-level protocol [OBS-RE]

A RAM semaphore is acquired in ring 3 without entering the kernel at all, and the kernel is
called only on contention:

- **Acquire, fast path.** The owner does an atomic `xchg` of a byte against the owner byte. If it
  read zero, it now holds the semaphore; it stamps `fs_ProcID`/`fs_ThrdID` from its own InfoSeg
  and bumps `fs_Usage`. A recursive acquire is recognised by the owner compare and only bumps
  `fs_Usage`.
- **Acquire, slow path.** On a failed `xchg` the caller calls `DosSemWait`/`DosSemRequest` with a
  far pointer to the semaphore word and a timeout, then **loops**: on return it re-runs its own
  `xchg` rather than assuming it now owns the lock. The kernel never hands over ownership - it
  only blocks and wakes.
- **Release.** The owner decrements `fs_Usage` and stops there unless it hit zero. At zero it
  clears the owner dword and atomically exchanges the whole semaphore word with zero, **keeping
  the old value**. If the old value's high byte was non-zero there were waiters, and it calls the
  wake entry point passing that old high byte and the semaphore's address.

The consequence worth stating plainly: **a wake does not transfer the lock.** Every woken waiter
re-competes via `xchg`, so a wait that returns is a prompt to retry, never a grant.

A worked instance of that protocol, useful because it names the exact argument the slow path
passes **[OBS-RE]**: a 32-bit ring-3 wrapper takes the `FastSafeRamSemStruc` **base**, runs its
fast path as `xchg al,[base+0x10]`, and on failure calls the 32-to-16 wait gate with the two
arguments the structure supplies directly -

```
push dword [base+0x0c]   ; fs_Timeout
lea  eax,[base+0x10]     ; &fs_RAMSem
push eax
call <wait gate>
```

- then tests the result and jumps back to its own `xchg` on **both** the "observed free" code and
the interrupted code, propagating anything else. So the pointer a wait implementation receives
addresses `fs_RAMSem`, not the structure base: the owner fields sit at a **negative** offset from
it (`fs_ProcID` at `-0x0C`), and `fs_Timeout` at `-0x04`. That is also the reason the wait may
return "not acquired" without violating anything - see the retry rule above.

### 5.6 The kernel's wait, and why the waiter field is flags [OBS-RE]

The kernel's RAM-semaphore wait runs with interrupts disabled and uses `lock`-prefixed
read-modify-writes, in this order:

1. Test `word & 0xF0FF`. If zero the semaphore is free - return at once and let the caller retry.
2. Save the current waiter byte.
3. `lock or byte [sem+1], 0x01` - **publish** that a thread is about to block.
4. **Re-test** `word & 0xF0FF`. If it is still held, block (recording the semaphore address as the
   thread's block ID, with the caller's timeout).
5. If it became free in the window, retract: if the saved byte shows the flag was already set by
   *another* waiter, leave it alone; otherwise `lock and byte [sem+1], 0xFE` to clear the bit this
   thread set, and return.

After a successful block-and-wake the kernel loops back to step 1 rather than returning ownership,
mirroring the ring-3 retry discipline.

This is publish-before-recheck with a retraction step, and it is why the waiter field is a set of
**flags rather than a counter**: the kernel only ever ORs a bit in and ANDs it out - nothing
increments. The wake side confirms it from the other end. The argument the releaser passes is not
a count of threads to wake but a **bitmask of waiter bits to clear**: the kernel complements it,
`lock and`s it into the waiter byte, and then dispatches on *which* bits were named - bit 8 and
bit 9 of the word select different wake actions. Passing back the exact bits the releaser observed
(rather than clearing the field wholesale) is what stops a waiter that arrived between the release
and the wake from being lost.

A releaser reading the field as a scalar - "non-zero means someone is waiting" - behaves
identically under either reading, which is why the counter interpretation is a natural misreading
from the ring-3 side alone.

### 5.7 Return codes on this path [OBS-RE, values [DOC-IBM - `bseerr.h`]]

| Value | Name | When |
|---|---|---|
| 0 | - | The semaphore was observed free, or a block completed. The caller must still re-acquire. |
| 95 (`0x5F`) | `ERROR_INTERRUPT` | The block was interrupted rather than satisfied. Retryable. |
| 121 (`0x79`) | `ERROR_SEM_TIMEOUT` | The timeout expired - including immediately, when the caller passed `SEM_IMMEDIATE_RETURN` (0). |

Both of the constants in section 5.1 land on distinct kernel paths: a zero timeout returns
`ERROR_SEM_TIMEOUT` without blocking, and `SEM_INDEFINITE_WAIT` (-1) is recognised as a sentinel
that suppresses the remaining-timeout arithmetic across repeated blocks. **[OBS-RE]**

### 5.8 Sources for this section

**[DOC-IBM]** DDK `base/src/dev/pcmcia/flash/h/bsedos16.h` and `DBCS/H/bsedos16.h` (the
prototypes and the two timeout constants); DDK `video/src/video/vga32/ibmvga32/sem.inc`
(`FastSafeRamSemStruc` and the field-by-field prose); DDK `base/inc/dbgapi.inc` (`FSRST`,
`DBSEM_FSRST`, `RamSemOwner`, `DBG_RAMSEM_OWNED`); Toolkit 4.5 `bseerr.h` (error values).
**[OBS-RE]** Disassembly of the OS/2 kernel's 16-bit semaphore workers - the `DosSemWait` entry
stub and its `SemWait` / `RamSemWait` / `SemBlock` / `VerifyRamSemAddr` chain, `SemSet`,
`SemClear`, `PutRamSemID` (`0003:30F2`, and the `CurrentRamSemID` global at `0002:8C3E` it
increments), and the RAM-semaphore wake worker and its sub-dispatcher - together with the ring-3
fast-path acquire and release routines in `PMMERGE.DLL`'s 16-bit object.

### 5.9 16-bit SYSTEM semaphores - `DosCreateSem` / `DosOpenSem` / `DosCloseSem`, and what Set/Clear/Request/Wait do to them

section 5.2-section 5.7 describe the RAM-semaphore half of this family. This section is the other half: the
named, kernel-owned **system semaphore** that the same `DosSemXxx` calls accept when the `HSEM`
is a handle rather than a pointer.

> **How to read the tags here.** `[DOC-IBM]` is IBM's own text: the Control Program error list
> (`cp2`/`cpgref` INF), the Physical Device Driver Reference (`pddref`), the Toolkit/DDK headers,
> and the *OS/2 Debugging Handbook* redbooks. `[DOC]` is the EDM2 reprint of the OS/2 1.x Control
> Program Reference, the **only** place the create/open/set/wait pages survive in the material
> searched. `[OBS-RE]` is a reading of the SMP **debug** kernel of Warp 4.5 (`os2krnld`, with its
> `.sym` and linker map), checked for layout against a 14.104a SMP retail kernel; addresses below
> are the debug kernel's and move between builds - they locate the reading, they are not the
> contract. `[INF]` is a conclusion over those, and `[unverified]` a
> point neither settles. ~~**No `[OBS]` capture from a running system backs anything in this
> section yet.**~~ **Superseded 2026-09-24:** `[OBS]` below is a capture from **OS/2 Warp
> Server for e-business, `ver /r` 4.50 Revision 14.089, retail SMP kernel**, run 2026-09-24 by
> a 16-bit test program whose single cases drive up to three processes and three threads of its
> own, and whose stress cases (the twenty kills in section 5.9.8) drive up to four worker processes at
> once, with hard-error and exception pop-ups disabled (`DosError(2)`). "**Traps the caller**" below means
> the calling process was ended with SYS3175, exception c0000005, and no return code came
> back. The system's pop-up log recorded each such fault either in `DOSCALL1.DLL` object 3
> (offsets 0x6CB, 0x722, 0x77C, 0x7E1, 0x80A, 0x8E4 were seen) or in the calling program's
> own code segment; which call produced which entry was not established from the log.
> `DOSCALL1.DLL` was the one shipped with that system. Several `[INF]`/`[unverified]` points below are settled
> by it and are marked where they stand; two readings of the bytes were wrong and are
> corrected in place.
>
> **IBM text found after this section was written:** IBM's *OS/2 Programming Reference*
> (control-program function calls of the 16-bit API) - that the book is IBM's own text is
> **[INF]**, from its title and structure; the converted copy read carries no copyright
> line - has reference pages for `DosCreateSem`,
> `DosOpenSem`, `DosCloseSem`, `DosSemRequest`, `DosSemClear`, `DosSemSet`, `DosSemSetWait`
> and `DosSemWait`. Where this section cites the EDM2 reprint as `[DOC]`, the same text is in
> that book; the pages this section said were absent are quoted where they matter, tagged
> `[DOC-IBM]`. Each of those citations carries the one **[INF]** above - that the book is
> IBM's - and it is not repeated at each site. *(They were tagged `[DOC-IBM, attribution INF]`
> until 2026-09-25; that is not a ratified tag, see `README.md`.)*

#### 5.9.1 The calls and their ordinals [DOC-IBM]

| Call | `DOSCALLS` ordinal | Arg bytes | Where it runs |
|---|---|---|---|
| `DosCreateSem(USHORT NoExclusive, PHSYSSEM phsem, PSZ pszName)` | 24 | 10 | kernel entry |
| `DosOpenSem(PHSEM phsem, PSZ pszName)` | 25 | 8 | kernel entry |
| `DosCloseSem(HSEM hsem)` | 23 | 4 | kernel entry |
| `DosSemSetWait(HSEM hsem, LONG lTimeOut)` | 20 | 8 | kernel entry |
| `DosMuxSemWait(PUSHORT piSem, PVOID pList, LONG lTimeOut)` | 22 | 12 | kernel entry |
| `DosSemRequest(HSEM hsem, LONG lTimeOut)` | 140 | 8 | `DOSCALL1` ring-3 wrapper |
| `DosSemClear(HSEM hsem)` | 141 | 4 | `DOSCALL1` ring-3 wrapper |
| `DosSemWait(HSEM hsem, LONG lTimeOut)` | 142 | 8 | `DOSCALL1` ring-3 wrapper |
| `DosSemSet(HSEM hsem)` | 143 | 4 | `DOSCALL1` ring-3 wrapper |

The ordinals are `ORD_DOS*` in the Warp 4.5 Toolkit `bseord.h` and agree with the DDK copy
**[DOC-IBM]**. The argument-byte counts are the `pre_sci(N)` value each kernel entry stub pushes
(`DOSCREATESEM` 10, `DOSOPENSEM` 8, `DOSCLOSESEM` 4, `DOSSEMSETWAIT` 8) and the `retf N` of each
`DOSCALL1` wrapper (`DOSSEMREQUEST` `retf 8`, `DOSSEMCLEAR` `retf 4`, `DOSSEMWAIT` `retf 8`,
`DOSSEMSET` `retf 4`) **[OBS-RE]**; `DosMuxSemWait`'s 12 is the sum of its three documented
parameters **[INF]** (its stub was not read here). The four ring-3 wrappers appear in
`DOSCALL1`'s own entry table as object-3 entries **[OBS-RE]**; the five kernel entries do not.

The prototypes and constants are in DDK `bsedos16.h` **[DOC-IBM]**: `typedef LHANDLE HSYSSEM`,
`CSEM_PRIVATE 0`, `CSEM_PUBLIC 1`, and `MUXSEMLIST` with a 16-entry array. **Naming trap:** that
header calls `DosCreateSem`'s first parameter `fExclusive`, but its meaning is the opposite -
the documented parameter is `NoExclusive`, where **0 = exclusive and 1 = non-exclusive**
**[DOC]**, which is also what `CSEM_PRIVATE 0` / `CSEM_PUBLIC 1` name **[DOC-IBM]**, and what the
kernel does (a create with the value 0 sets the exclusive flag; 1 does not) **[OBS-RE]**.

#### 5.9.2 What a system-semaphore handle is [DOC-IBM / OBS-RE]

- A system semaphore handle is a 32-bit value **[DOC-IBM - `HSYSSEM`, "32-bit value used as a
  system semaphore handle"]**, and it shares the `HSEM` parameter slot with a RAM semaphore's far
  pointer **[DOC]**.
- In the kernel read here, an application's handle is **`0002:index`**: the create and open
  workers return `DX = 2`, `AX = index` **[OBS-RE - `h_w_CreateSem`, `h_w_OpenSem`]**. `index` is
  the slot in one **system-wide** 256-entry table (`SysSemDataTable`, 6 bytes per entry)
  **[OBS-RE - `GetSysSemEntry` scans 0x100 entries; DOC-IBM - the handbook sizes the table
  "256\*6 bytes"]**. So the numeric handle for a given semaphore is the **same value in every
  process** that opens it **[INF - the index is global and nothing process-specific enters the
  returned value]** - **settled [OBS]**: a create returned `0002:000C` and the next create
  `0002:000D`; another process opening the first name got `0002:000C`.
- The kernel also has an internal anonymous create that claims a slot with no name and no
  per-process accounting and returns `0003:index` directly **[OBS-RE - `CreateAnonSem`]**.
- The value **3** in the selector half is the *system-specific* handle a device driver obtains
  with `DevHlp_SemHandle`, as opposed to the *task-specific* handle an application holds
  **[DOC-IBM - `pddref` SemHandle: "The caller-supplied semaphore handle refers to task-specific
  system semaphore structures ... SemHandle converts the task-specific handle to a
  system-specific handle"]**; the kernel's entry filter refuses a `0003:` handle from ring 3 with
  115 **[OBS-RE - `SemStampRPL`, and `w_CloseSem`'s own `cmp ax,3`]**.
- **The two sources disagree on the encoding.** The *Debugging Handbook* gives the handle
  structure as `SysSemHighWord` "0x8000 for sys sems" at +0 and `SysSemPTDAIndex` at +2
  **[DOC-IBM]**; the kernel bytes test for the selector values 2 and 3 and never for 0x8000
  **[OBS-RE]**. The bytes govern behaviour; the handbook value may describe an earlier kernel
  **[INF]**.
- A process can use a handle only if it has it open: the pointer-validation routine refuses a
  `0002:index` whose per-process open count is zero, an index >= 0x100, or a table entry with a
  zero reference count, and each refusal is **115 `ERROR_PROTECTION_VIOLATION`** **[OBS-RE -
  `GetSysSemPtr`]**. That routine returns 115 through `SemProtFault`, which under a kernel-state
  condition ~~not identified here~~ (`_InterruptLevel` = 0xFF and a non-zero `_cInDos`, both named
  by the debug kernel's linker map **[OBS-RE, 2026-09-25]**; that 0xFF means task time is **[INF]**
  from the name, and what the count means was not read) *also* calls the kernel's user-argument-fault routine
  (`h_UsrArgFault`) - so whether a bad handle is a plain 115 or a fault delivered to the caller is
  **[unverified]**.
  **SETTLED 2026-09-24 [OBS] - it is a fault; the "115" above is the routine's internal value,
  and no caller ever sees it.** `DosSemClear`, `DosSemWait(0)`, `DosSemRequest(0)`, `DosSemSet`
  and `DosCloseSem` given a handle another process created and the caller never opened each
  **trap the caller**; so do `0002:00FF`, `0002:0100` and `0003:0001`, and a `DosCloseSem` of a
  handle whose last open this process has already closed. Control: the same process's calls on
  a handle it did open returned 0. (Every semaphore in these cases was non-exclusive.)

#### 5.9.3 The kernel's per-semaphore state [DOC-IBM names / OBS-RE use]

Each table entry is `SysSemTblStruc` **[DOC-IBM - handbook, Table 47]**:

| Off | Field [DOC-IBM] | What the kernel does with it [OBS-RE] |
|---|---|---|
| +0 | `SysSemOwner` (W) - "thread owning this semaphore" | The owning thread's slot number, 0 = clear. Written by request and by set; zeroed by clear. **Never zeroed by the owner-died paths** (section 5.9.8). |
| +2 | `SysSemFlag` (B) | The `SYSSEM_*` bits below. |
| +3 | `SysSemRefCnt` (B) - "number of references" | 1 on create; +1 per open; -1 per close; at 0 the name is removed and the slot is free. A driver's in-use `SemHandle` also holds a reference, as the PDD Reference requires **[DOC-IBM]** (the `SemHandle` worker itself was not re-read). |
| +4 | `SysSemProcCnt` (B) - "number of requests for this owner" | **Exclusive semaphores only**: +1 per request/set by the owner, -1 per clear; released at 0. |
| +5 | `SysSemPad` | Not seen accessed. |

`SysSemFlag` bits, names and descriptions **[DOC-IBM - handbook Table 48]**, and who sets them
**[OBS-RE]**:

| Bit | Name | Set by | Cleared by |
|---|---|---|---|
| 0x01 | `SYSSEM_WAITING` | a waiter, before blocking | clear (which then wakes all waiters); owner-died paths |
| 0x02 | `SYSSEM_MUXWAITING` | a `DosMuxSemWait` registrant (setter not re-read) | clear (which then wakes muxwaiters) |
| 0x04 | `SYSSEM_OWNER_DIED` | owner-died paths | request / set / clear |
| 0x08 | `SYSSEM_EXCLUSIVE` | create with `NoExclusive = 0` | never |
| 0x10 | `SYSSEM_NAME_CLEANUP` | "name table entry needs to be removed" **[DOC-IBM]** - deferred by a driver's interrupt-time release (setter not re-read) | the next create or open, which removes the name first |
| 0x20 | `SYSSEM_THREAD_OWNER_DIED` | owner-died path, in the exiting-process case (section 5.9.8) | exit-list takeover; request / set / clear |
| 0x40 | `SYSSEM_EXITLIST_OWNER` | exit-list takeover | process teardown; request / set / clear |

Each process also has a **byte per table index** counting its own opens, "per-semaphore use
counts" in a PTDA table (`SysSemPTDATbl`) **[DOC-IBM - handbook]**, incremented by create and
open, decremented by close, and zeroed at process teardown **[OBS-RE]**. A process that opens the
same name twice therefore holds one handle value with a count of 2 and must close it twice
**[INF - the open path returns the same `0002:index` and only increments]** - **settled [OBS]**:
create, open, open returned one handle value; three closes returned 0, and an open by name then
returned 187.

**255** references is the most one semaphore can have **[OBS]** - for a
non-exclusive semaphore, a create plus 254 opens succeeded in one process, and the next open returned 106, in that process
and in another process that held no open of it at all. That the count is kept in a byte is
**[INF]**, from that limit and the handbook's byte-wide `SysSemRefCnt` (section 5.9.3's table).

Names live in a resource map (`SysSemRmpHdl`, owner id `syssemrmp` 0xff36) whose records begin
with the table offset of their entry **[DOC-IBM - handbook]**; lookup is by the name text, and
removal by the entry offset **[OBS-RE - `FindSysSemName`, `AddSysSemName`, `RemSysSemName`]**.
A semaphore exists exactly as long as its reference count is non-zero **[OBS-RE]**, which is the
kernel form of the documented rule that the semaphore is deleted when its last user closes it
**[DOC]**.

#### 5.9.4 `DosCreateSem` [DOC / OBS-RE]

Documented contract **[DOC]**: creates a system semaphore and returns a handle for the creating
process; the name must begin `\SEM\`, and although it has the form of a file path the `\SEM`
directory does not exist - "system semaphores and their names are kept in memory"; creation does
**not** set or own the semaphore - ownership comes from `DosSemRequest`. Documented returns: 0,
87, 100, 123, 183.

What the kernel does, in order **[OBS-RE - `h_w_CreateSem` -> `CleanUpSysSemName`,
`GetSysSemEntry`, `GetSysSemPTDAIndex`, `AddSysSemName`]**:

1. Removes any names left pending by an interrupt-time driver release (`SYSSEM_NAME_CLEANUP`).
2. **`NoExclusive` >= 2 -> 87** `ERROR_INVALID_PARAMETER`. Otherwise claims the first free table
   slot (reference count 0 and no pending cleanup), zeroes its owner, flags and use count, sets
   its reference count to 1, and sets `SYSSEM_EXCLUSIVE` unless `NoExclusive == 1`. **No free
   slot -> 100** `ERROR_TOO_MANY_SEMAPHORES`.
3. Increments the caller's per-process count for that index; an overflow returns **106**
   `ERROR_SEM_USER_LIMIT` and releases the slot.
4. Canonicalises the name with the kernel's path canonicaliser and validates it against the
   required `\SEM\` prefix; **either failure -> 123** `ERROR_INVALID_NAME`. Looks the name up:
   **already present -> 183** `ERROR_ALREADY_EXISTS`. Otherwise adds it; a failure to add -> **100**.
   Any failure here undoes steps 2-3.
5. Returns the handle `0002:index` through `phsem`.

Consequences: the check order means a full table answers 100 *before* a duplicate name would
answer 183, and a bad `NoExclusive` answers 87 before either **[INF from the order above]** -
**settled [OBS]**: with the table full, a duplicate name returned 100 and `NoExclusive = 2`
returned 87; with it not full, `NoExclusive` 2 and 0xFFFF returned 87, also on an existing name.
The table filled after 244 creates on a booted system whose first free slot was index 0x0C, and
a create from the process that filled it, and from a second process, then returned 100 **[OBS]**.
That the slots it could not claim belong to the system's own users is **[INF]**: no capture lists
who holds them.
Name comparison is case-insensitive **[INF - the name passes through the filesystem path
canonicaliser before lookup]** - **settled [OBS]**: `\sem\lower.sem` created and
`\SEM\LOWER.SEM` opened the same semaphore. The canonicaliser's other effects, also **[OBS]**:
`/` separators become `\` (`/SEM/SLASH.SEM` opens as `\SEM\SLASH.SEM`), `X\..` is resolved, and
a subdirectory, a space, or a component longer than 8.3 are accepted; `SEM\X.SEM`, `\SEMX\A`,
`\SEM\`, `\SEM\*.SEM`, and names of 274 and 310 characters return 123. A NULL name pointer to
the create or the open traps the caller.
Whether `*phsem` is written on a failed create is
**[unverified]** - the entry stub's store was read only on its success path - **settled
[OBS]: it is written, and not with a handle**: a duplicate-name create (183) left `0600:0000` in it on
the retained captures, and a `NoExclusive = 2` create (87) also overwrote it. *(This read
"`0000:0000`, `0300:0000`, `0400:0000` or `0600:0000` ... differing from run to run" until
2026-09-25; only `0600:0000` is in a retained capture.)* EDM2 does not list
106, which the kernel can return **[OBS-RE]**; that it is reachable on a *create* at all
**[unverified]**, since a free slot's per-process counts should already be zero.

#### 5.9.5 `DosOpenSem` [DOC / OBS-RE]

Documented contract **[DOC]**: returns a handle to an existing semaphore created by another
process; "merely returns the handle of the semaphore; it does not test or change the value of the
semaphore". Handles are inherited by a `DosExecPgm` child, which does not inherit *ownership*.
Documented returns: 0, 100, 106, 123, 187 (the same five in the *OS/2 Programming Reference*
`DosOpenSem` page **[DOC-IBM]**).

**CORRECTED 2026-09-24 [OBS] - the inheritance sentence does not hold on this system.** A child
started by `DosExecPgm` while its parent had a semaphore open and owned, using the parent's
handle value without opening the name, **trapped** on `DosSemWait(0)`, on `DosSemRequest(0)`,
again after the parent cleared it, and on `DosCloseSem` - exactly as a process that never
opened it does (section 5.9.2). The IBM page says *"the new process inherits the handles to these
semaphores"*; on 4.50 revision 14.089 a child must open the name itself.

What the kernel does **[OBS-RE - `h_w_OpenSem` -> `CleanUpSysSemName`, `FindSysSemName`,
`GetSysSemPTDAIndex`]**: pending-name cleanup; canonicalise and validate the name (**123**);
look it up (**absent -> 187** `ERROR_SEM_NOT_FOUND`); increment the caller's per-process count
(**overflow -> 106**); increment the entry's reference count (**overflow -> 106**, undone); return
`0002:index`. No step reads or writes the owner or the flags **[OBS-RE]**, which is the kernel
form of "does not test or change the value" **[DOC]**.

- No path in those three routines returns **100**, although EDM2 lists it **[OBS-RE - scope:
  exactly those three routines]** - **[OBS]**: with the table full, an open of an existing name
  returned 0.
- **The open does not test `SYSSEM_EXCLUSIVE`** **[OBS-RE]**: an exclusive semaphore can be
  opened by name from another process - **[OBS]**, it returned 0. See section 5.9.9 for what that
  process can then do with it.
- **The 106 path is not undone for the caller [OBS] - a kernel defect, section 5.9.13.** "Overflow ->
  106, undone" above is true of the reference count and false of the caller's own per-process
  count.

#### 5.9.6 `DosCloseSem` [DOC-IBM / OBS-RE]

~~There is no reference page for `DosCloseSem` in the material searched (see section 5.9.11); its
contract is recovered from the error list and the kernel.~~ **CORRECTED 2026-09-24:** the *OS/2
Programming Reference* has one **[DOC-IBM]**: returns 0 and 102 `ERROR_SEM_IS_SET`; the semaphore
is deleted when every process that obtained a handle has closed it; and on process termination
it repeats the `DosCreateSem` remarks quoted in section 5.9.8. The search that missed it covered EDM2
and the INF texts, not that book. The one IBM statement about it is the
text of error **102 `ERROR_SEM_IS_SET`: "DosCloseSem found semaphore set."** **[DOC-IBM -
`cp2`/`cpgref` error list]**; EDM2's `DosCreateSem` example also treats a non-zero close as "still
set -- cannot close now" **[DOC]**.

What the kernel does **[OBS-RE - `w_CloseSem` / `CloseSem` -> `GetSysSemPtr`, `RemSysSemName`]**:

1. A `0003:` handle from ring 3 -> **115**; an invalid handle -> **115** (section 5.9.2).
2. **102** is returned when *all* of these hold: neither `SYSSEM_OWNER_DIED` nor
   `SYSSEM_THREAD_OWNER_DIED` is set; the semaphore has an owner; that owner thread belongs to the
   **calling process**; and this is the caller's **last** open of it (per-process count 1).
3. Otherwise decrements the per-process count and the reference count; at 0 it removes the name,
   which deletes the semaphore.

So "found semaphore set" means *owned or set by a thread of the process that is closing its last
handle* **[INF from 2]**. Closing while a thread of **another** process owns it succeeds, as does
closing one of several handles the process holds **[OBS-RE]**. Nothing on the close path wakes a
thread blocked on the semaphore **[OBS-RE - no wake call in `CloseSem`]**. **All confirmed
[OBS]:** the last close returned 102 after a request (non-exclusive and exclusive) and after a
set (non-exclusive; a set of an exclusive semaphore followed by its last close was not run); with
two handles the first close returned 0 and the second 102 (non-exclusive); a close while another
process owned it returned 0 (non-exclusive) - whether the name then survives while that process
still holds it open was **not** checked, because the open by name (187) was issued only after
that process had also cleared and closed it; a close of a second handle left a thread blocked
in `DosSemWait(-1)` blocked until a clear released it (non-exclusive).

#### 5.9.7 Set, Clear, Request and Wait on a system handle [DOC / OBS-RE]

How each call gets there. `DOSCALL1`'s wrappers test the selector half of `hsem` against 2 and
send a system handle to a kernel fast path - `DosSemRequest` -> kernel `DOSISEMREQUEST` (#18),
`DosSemClear` -> `DOSISYSSEMCLEAR` (#17), `DosSemSet` -> `DOSISYSSEMSET` (#19), `DosSemWait` ->
`DOSISEMWAIT` (#21) **[OBS-RE - the wrappers' own `cmp`s and their import fixups; the ordinal names
from the IBM ordinal list]**. Any other selector is treated as a RAM-semaphore address (section 5.2-section 5.5).
`DosSemWait`'s wrapper converts a kernel return of 3000 (0x0BB8) into **95** `ERROR_INTERRUPT`
**[OBS-RE]**; where the kernel produces 3000 was not traced.

Two properties decide everything below: whether the semaphore is **exclusive**, and the owner
test, which is by **thread**. The owner check used by Set and Clear passes if the semaphore is
non-exclusive, unowned, marked `SYSSEM_OWNER_DIED`, or owned by the calling thread; if it is
exclusive and owned by another thread - or marked `SYSSEM_THREAD_OWNER_DIED` - it returns **101
`ERROR_EXCL_SEM_ALREADY_OWNED`** **[OBS-RE - `ChkSysSemPtr`]**. A further branch in the same routine,
on a kernel state byte, returns 104 `ERROR_INVALID_AT_INTERRUPT_TIME` **[OBS-RE for the value]**;
~~what that byte is was not identified **[unverified]**~~ - the byte is the kernel's
`_InterruptLevel`, named by the debug kernel's own linker map, and the routine takes the 104 branch
when it is not 0xFF **[OBS-RE - the SMP debug kernel's `.map` and `ChkSysSemPtr`'s
`cmp byte [_InterruptLevel],0xFF`, 2026-09-25]**. That 0xFF means task time, so that the branch is
a Set or Clear on an exclusive, owned semaphore issued at interrupt time, is **[INF - from the name
and 104's meaning; the byte's writers were not read]**. It sits
after the exclusive and unowned tests, so it never applies to a non-exclusive or unowned semaphore
**[OBS-RE]**. Nothing on these paths compares the calling **process** with the creator
**[OBS-RE]**.

| Call | Non-exclusive semaphore | Exclusive semaphore |
|---|---|---|
| **`DosSemRequest`** | Unowned -> caller's thread becomes owner, 0. Owned by *anyone* - **including the calling thread** - -> block until clear, then retry. Not recursive. | Unowned -> owner = caller, use count 1, 0. Owned by the caller -> use count +1, 0 (**overflow -> 103** `ERROR_TOO_MANY_SEM_REQUESTS`). Owned by another thread -> block, then retry. |
| **`DosSemClear`** | Any thread of any process holding a handle may clear it: owner <- 0, waiters woken, owner-died flags cleared; 0 even if it was not set. | Owner thread (or unowned): use count -1, and only at 0 is it released and waiters woken. Another thread -> **101**. |
| **`DosSemSet`** | Owner <- calling thread, unconditionally (it may already be set by someone else); 0. | Owned by another thread -> **101**. Otherwise owner <- caller and use count +1 (**103** on overflow) - i.e. a non-blocking request. |
| **`DosSemWait`** | Returns 0 at once if unowned; else blocks until the owner field reads 0, **re-testing after every wake** (level-triggered). Takes no ownership. | Same - the wait does **not** apply the owner check, so any handle holder may wait. |
| **`DosSemSetWait`** | Set, then Wait, as one kernel call. | Set (101 if another thread owns it), then Wait. |

Sources: **[OBS-RE - `SysSemRequest`, `SysSemClear`, `SysSemSet`, `SysSemWait`, `SemSetWait`]**;
the documented descriptions agree where they speak: exclusive semaphores keep a use count
"incremented by DosSemRequest calls and decremented by DosSemClear calls" and are released only
when cleared as many times as requested, "so exclusive system semaphores can be used in recursive
routines" **[DOC - DosCreateSem]**; `DosSemSet` "cannot be issued against a system semaphore that
is owned by another thread, unless the NoExclusive option was set" **[DOC - DosSemSet]**;
`DosSemWait` "is level-triggered" and "does not establish ownership" **[DOC - DosSemWait]**.

**The table is confirmed row by row [OBS]**: a non-exclusive semaphore's second request from its
own owner returned 121 (at once with timeout 0, after the full 500 ms with 500); an exclusive one
was requested three times by its owner, stayed held after two clears and was released by the
third; the 256th request - or the 256th set - by the owner returned 103, so the use count is a
byte; another thread's or process's clear of a held non-exclusive semaphore returned 0 and
released it, of a held exclusive one 101; a set over another's ownership of a non-exclusive
semaphore returned 0, and on an exclusive one acted as a request (another thread then got 121 for
a request and 101 for a set); another thread's `DosSemWait(500)` on an exclusive semaphore it did
not own returned 121 after the full time, never 101; clearing a clear semaphore, setting a set
one and clearing an unowned exclusive one each returned 0. A signal delivered by `DosFlagProcess`
to a process blocked in `DosSemRequest(-1)` ran its handler, and the request returned 95.

Consequences worth stating **[INF from the table]** - the first two **confirmed [OBS]**:

- A thread that requests a **non-exclusive** semaphore it already owns deadlocks against itself
  until its timeout.
- `DosSemSetWait` on an **exclusive** semaphore makes the caller its owner and then waits for a
  clear that only the caller may perform (other threads get 101), so it can end only by timeout or
  interruption. **[OBS]:** another thread's clear returned 101, the call returned 121 after its
  full 1000 ms, and the caller still owned it afterwards.
- On a non-exclusive semaphore "set" and "owned" are the same state - both write the owner
  field - which is why the signalling idiom (one side sets, the other side clears) works across
  processes, and why "found semaphore set" is also the close-time test for ownership.

Timeouts follow section 5.1: -1 waits indefinitely, 0 returns at once, and a positive value is a
millisecond limit **[DOC]**; a request or wait that runs out returns **121 `ERROR_SEM_TIMEOUT`**
and an interrupted block **95** **[DOC]**. The system-semaphore wait blocks through the same
kernel `SemBlock` routine the RAM path uses **[OBS-RE - both `SysSemWait` and `RamSemWait` call
it]**, so the timeout handling of section 5.7 applies to it **[INF]**. **Not settled [OBS]:** a thread
in another process doing `DosSemWait(300)` on an exclusive semaphore owned by the creating
process returned 121 in under 150 ms, where the same wait from a thread of the owning process
ran its full time; and a `DosSemWait(-1)` returned during 200 clear-then-set pairs, which cannot
tell a level-triggered wake from one that happened to see the semaphore clear. The request fast path never blocks:
when the semaphore is held it hands the call to the blocking entry **[OBS-RE - `DOSISEMREQUEST`
calls `SysSemRequest` with its no-block flag and falls through to the general stub on "would
block"]**.

#### 5.9.8 When the owner dies [DOC / OBS-RE - the two do not match in structure]

**Documented [DOC - DosCreateSem remarks]:** a *non-exclusive* semaphore held by a process that
terminates is cleared by OS/2, and "returns ERROR_SEM_OWNER_DIED to the next thread that gets the
resource because of a DosSemRequest call"; that thread should repair the resource and then
`DosSemClear`, which "resets the error condition". For an *exclusive* semaphore, "ownership of the
semaphore is transferred to the thread executing any exit list routines. If no exit list routines
have been identified ... the system closes the handle". The handbook adds: "the first requestor is
given a return code that indicates the situation" **[DOC-IBM]**.

**What the kernel does [OBS-RE - `SysSemOwnerDiedWorker`, `SysSemExitListWorker`,
`FreeSysSemWorker`, `EachSysSem`]**, for each system semaphore the dying process has open:

1. **A thread ends** while it owns one: depending on one per-process status bit, either
   `SYSSEM_OWNER_DIED` is set and blocked waiters are woken, or `SYSSEM_THREAD_OWNER_DIED` is set
   and the process id is recorded for the entry. ~~That the bit means "the process has begun
   exiting" is **[INF]**, from the handbook's description of the per-entry pid table as "only used
   ... during process/thread termination" **[DOC-IBM]**.~~ The bit is `PS_XITALL` (below).
2. **Exit-list stage:** the same step for the running thread's own semaphores, then every entry
   marked `THREAD_OWNER_DIED` whose recorded pid is this process is **taken over by the running
   thread** (`SYSSEM_EXITLIST_OWNER`, owner <- that thread).
3. **Process teardown:** the exit-list step again, then any semaphore still owned by the running
   thread is marked `SYSSEM_OWNER_DIED` and its waiters woken; the process's open count is
   subtracted from the reference count, and at 0 the semaphore is deleted.

~~The workers were read; their callers were not. That step 2 runs when exit-list processing begins
and step 3 at final teardown is **[INF]** from the worker names and the handbook's flag
descriptions ("the exitlist thread owns the sem") **[DOC-IBM]**.~~ **The callers were read
2026-09-26 [OBS-RE, SMP debug kernel, `_TKTermThread` and `_TKDieSoonPTDA`]:** step 1 is the end of
every thread other than thread 1 (`f_SysSemOwnerDied`); step 2 is thread 1, after it has waited for
every other thread of the process to end and after setting `PS_XITLST`, immediately before the first
exit-list routine (`f_SysSemExitList`); step 3 is `FreeSysSem`, from the final teardown. The "one
per-process status bit" is `ProcStatus`'s `PS_XITALL` (0x04), which `_TKDieSoonPTDA` sets once, when
the process begins to end - by `DosExit(EXIT_PROCESS)` from any thread, any `DosExit` from thread 1,
or a kill that nothing intercepts - so the bit does mean "the process has begun exiting", and a
thread that ends while its process continues takes the `SYSSEM_OWNER_DIED` arm.

None of these steps tests `SYSSEM_EXCLUSIVE` **[OBS-RE]**: the exit-list takeover the
documentation describes only for exclusive semaphores is applied to both kinds, conditional
instead on *when* the owner died. And none of them clears the owner field **[OBS-RE]**.

**Observed [OBS]:** a **non-exclusive** semaphore held by a process that was killed, with no
exit-list routine, answered the next `DosSemRequest` with 105; an **exclusive** semaphore whose
owner was killed with no exit-list routine was **not** tested. A process that ended itself
(`DosExit`) holding a semaphore, with a do-nothing exit-list routine registered, left 105 for
the next request, exclusive and non-exclusive alike. What was seen is **consistent with** the exclusive takeover the documentation describes, but does
not establish it: the semaphore was owned by the dying process's **second** thread, and that
process's exit-list routine cleared it with 0; the next request by another process then returned
0. That rules out the thread-owner-died state, in which a clear by another thread returns 101
(section 5.9.7), but not the owner-died state, in which a clear by any thread returns 0 (below). That
the routine ran on the process's first thread is **[INF]**, from where it was registered; no
capture shows the thread. *(This read "the exclusive takeover ... was seen where it can be told
apart" until 2026-09-25.)* An exit-list routine that cleared
a semaphore its own thread owned also returned 0, for both kinds, with the same result. When a
**secondary thread** ended owning a **non-exclusive** semaphore while its process continued, the
next request - from that process or from a thread already blocked in another process - returned
105 - in two retained captures of the whole program, 2026-09-24 and 2026-09-25 (the
second for the process's own request only); one earlier capture of the same cases, run on
their own and not retained, showed the secondary thread's request and the process's own request
never returning, and that conflict is **not resolved** here. All the observations in the list below are of non-exclusive semaphores.

Then, on an owner-died semaphore:

- **`DosSemRequest`** takes ownership at once and returns **105 `ERROR_SEM_OWNER_DIED`** - the
  caller **is** the owner (use count 1, owner-died flags cleared) and must clear it
  **[OBS-RE - `SysSemRequest`, and `SysSemWait`'s request-mode check]**. A requester already
  blocked is woken and gets the same result **[OBS-RE]**. **Confirmed [OBS]**, including the
  ownership: after 105 a third process's request returned 121, and after the new owner cleared
  it, 0. Twenty kills in a row gave 105 twenty times (non-exclusive).
- **`DosSemSet`** and **`DosSemClear`** clear the owner-died flags silently and return 0
  **[OBS-RE]** - **[OBS]**: each returned 0, and the next request returned 0, not 105.
- **`DosSemWait`** does **not** return: it waits for the owner field to read 0, and the owner-died
  paths leave it non-zero **[INF - from the wait loop's test and the absence of an owner write in
  all three workers]**. It ends when some thread clears the semaphore, or by timeout. **Settled
  [OBS]:** `DosSemWait(1000)` returned 121 after the full second and `DosSemWait(0)` 121 at once;
  a thread already blocked in `DosSemWait(2000)` when the owner died was not released and
  returned 121 after two seconds. The documented "OS/2 clears the semaphore" does not describe
  what a waiter sees.
- **`DosCloseSem`** is allowed even by the process whose thread "owns" it, because the 102 test is
  skipped when an owner-died flag is set **[OBS-RE]** - **[OBS]**: after its second thread ended
  owning it, the process closed its only handle with 0.

#### 5.9.9 Exclusivity, restated [INF]

Putting section 5.9.5, section 5.9.7 and section 5.9.8 together: in the kernel read here, an **exclusive** system
semaphore is one whose ownership is **recursive and thread-checked** - only the owning thread may
set or clear it while it is owned - rather than one confined to its creating process. Another
process can open it by name, wait on it, request it (and block), and set or clear it whenever it is
unowned. The documented description, "only threads of the creating process may alter the state of
the semaphore" **[DOC]**, is therefore either enforced somewhere this reading did not reach, or
describes the effect of the thread check under ordinary use **[unverified]** - **settled [OBS]:
nothing enforces it.** A second process opened an exclusive semaphore by name (0), requested it
while unowned (0 - the creator's request then returned 121), cleared it (0) and set it (0); while
the creator owned it, the second process's clear and set returned 101 and its `DosSemWait(0)`
121.

#### 5.9.10 `DosMuxSemWait` over system semaphores [DOC]

Documented **[DOC - DosMuxSemWait]**: the list is a count plus up to 16 `{reserved zero word,
HSEM}` entries, and may mix system handles and RAM pointers; it returns when *any* listed
semaphore is clear, and unlike `DosSemRequest`/`DosSemWait`/`DosSemSetWait` it is
**edge-triggered** - a semaphore cleared and set again before the call begins is an event lost.
Returns 0, 95, 101, 121, 151 `ERROR_INVALID_EVENT_COUNT`, 152 `ERROR_TOO_MANY_MUXWAITERS`,
153 `ERROR_INVALID_LIST_FORMAT` **[DOC; values DOC-IBM - `bseerr.h`]**. The system-semaphore half of
the kernel's mux worker was **not read** for this section; that clearing a system semaphore wakes
registered muxwaiters is from the clear path alone **[OBS-RE - `SysSemClear` tests
`SYSSEM_MUXWAITING`]**. **[OBS]:** a list of two system semaphores and one RAM semaphore, all
set, returned index 1 when the second was cleared during the wait, and index 2 at once when the
RAM one was clear; all set with timeout 0 returned 121; a count of 0 or 17 returned 151, and a
non-zero reserved word 153. An exclusive semaphore held by another thread counted as not clear:
the list returned 121 (at once, and after 300 ms), never 101. A wait on a single semaphore
cleared and set again while it was blocked returned 0 with index 0.

#### 5.9.11 Return codes on the system-semaphore path [values DOC-IBM - `bseerr.h`]

| Value | Name | Returned by (this section) |
|---|---|---|
| 87 | `ERROR_INVALID_PARAMETER` | create, `NoExclusive` >= 2 |
| 95 | `ERROR_INTERRUPT` | a blocked request/wait interrupted |
| 100 | `ERROR_TOO_MANY_SEMAPHORES` | create: table full, or the name could not be stored |
| 101 | `ERROR_EXCL_SEM_ALREADY_OWNED` | set/clear of an exclusive semaphore owned by another thread |
| 102 | `ERROR_SEM_IS_SET` | close, section 5.9.6 |
| 103 | `ERROR_TOO_MANY_SEM_REQUESTS` | exclusive use count overflow |
| 105 | `ERROR_SEM_OWNER_DIED` | request of an owner-died semaphore - **with ownership granted** |
| 106 | `ERROR_SEM_USER_LIMIT` | open (either count overflows); create (per-process count) |
| ~~115~~ | ~~`ERROR_PROTECTION_VIOLATION`~~ | ~~any call given a handle the process has not open, or a `0003:` handle~~ - **CORRECTED [OBS]: never returned; those calls trap the caller (section 5.9.2)** |
| 121 | `ERROR_SEM_TIMEOUT` | request/wait timeout, including timeout 0 on a held semaphore |
| 123 | `ERROR_INVALID_NAME` | create/open, name fails canonicalisation or lacks `\SEM\` |
| 183 | `ERROR_ALREADY_EXISTS` | create of an existing name |
| 187 | `ERROR_SEM_NOT_FOUND` | open of a name that does not exist |

**Also [OBS]: a TRAP of the caller, not a code**, for any call on a handle it has not open
(section 5.9.2), a NULL name pointer, and `DosOpenSem` of `\SEM\*.SEM` in one of two runs (section 5.9.13).

Error texts **[DOC-IBM - `cp2`/`cpgref`]**: 101 "Exclusive semaphore already owned", 102
"DosCloseSem found semaphore set", 103 "Too many exclusive semaphore requests", 105 "Previous
semaphore owner ended without freeing semaphore", 106 "Semaphore limit exceeded". The "returned
by" column is **[OBS-RE]** except 95/121, which are **[DOC]**.

#### 5.9.12 Sources for this section

**[DOC-IBM]** Warp 4.5 Toolkit `bseord.h` and `bseerr.h`; DDK `DBCS/H/bsedos16.h`, `bseord.h`,
`bseerr.h`; *Control Program* INF error list (`cp2`, `cpgref`); *Physical Device Driver
Reference*, `SemHandle` and the system-semaphore overview; *OS/2 Debugging Handbook* - section 11.2.1
"16-Bit Semaphores", the System Semaphore control-block tables (46 `SysSemHandleStruc`, 47
`SysSemTblStruc`, 48 `SysSemFlag`), and the "SysSem" block-ID description. **[DOC]** EDM2's
reprints of the OS/2 1.x Control Program Reference pages `DosCreateSem`, `DosOpenSem`,
`DosSemSet`, `DosSemWait`, `DosMuxSemWait`. ~~**Searched and absent:** a reference page for
`DosCloseSem`, `DosSemRequest`, `DosSemClear` or `DosSemSetWait` in the EDM2 set and in the
Control Program, PDD, and 2.x Control Program Guide INF texts (all hits for those names are the
error list and a device-driver example) - so their contracts above rest on the kernel and on the
remarks of the neighbouring pages.~~ **CORRECTED 2026-09-24:** that search was right about the
material it covered and wrong as a conclusion - the *OS/2 Programming Reference* (16-bit
control-program function calls) has all four pages **[DOC-IBM]**: `DosCloseSem` returns 0, 102;
`DosSemRequest` 0, 95, 100, 105, 121; `DosSemClear` 0, 101; `DosSemSetWait` 0, 95, 101, 103, 121.
**[OBS]** OS/2 Warp Server for e-business 4.50 revision 14.089, retail SMP kernel, 2026-09-24: a
16-bit program exercising every case above from up to three processes, and four worker processes
in its stress cases (see the header note). **[OBS-RE]** Disassembly, SMP debug kernel `os2krnld` with
`.sym`/map: the entry stubs `DOSCREATESEM`, `DOSOPENSEM`, `DOSCLOSESEM`, `DOSSEMSETWAIT`,
`DOSISEMREQUEST`, `DOSISYSSEMCLEAR`; the workers `h_w_CreateSem`, `CreateAnonSem`, `h_w_OpenSem`,
`w_CloseSem`/`CloseSem`, `FindSysSemName`, `AddSysSemName`, `CanonBuf`, `GetSysSemEntry`,
`GetSysSemPTDAIndex`, `CleanUpSysSemName`, `GetSysSemPtr`/`GetSysSemPtrChk`/`ChkSysSemPtr`,
`SemProtFault` (entry only), `SysSemRequest`, `SysSemClear`, `SysSemSet`, `SysSemWait`,
`SemSetWait`, `SemSet`, `SemWait`, `SemStampRPL`, `FreeSysSem`/`FreeSysSemWorker`,
`SysSemExitListWorker`, `SysSemOwnerDiedWorker`, `EachSysSem`; `SemProtFault` cross-read in a
14.104a SMP retail kernel. `DOSCALL1.DLL` object 3: `DOSSEMREQUEST`, `DOSSEMCLEAR`, `DOSSEMWAIT`,
`DOSSEMSET`, with their import fixups resolved. **Not read:** `DOSMUXSEMWAIT` and its workers;
the producer of the 3000 wait return; the condition inside `SemProtFault`; `h_TaskOnly`; the
PTDA handle-table copy (if any) at `DosExecPgm`.

#### 5.9.13 Two kernel failures seen from ring 3 [OBS]

Both on OS/2 Warp Server for e-business 4.50 revision 14.089, retail SMP kernel, 2026-09-24.

1. **`DosOpenSem` of `\SEM\*.SEM`, after `DosCreateSem` of the same name returned 123, stopped
   the system in one run and ended only its caller in another.** In the stopping run the open
   was issued by a second process of the program. The retained capture ends at the program's
   announcement of that open, and the retained stop screen reads *"Exception in module: OS2KRNL
   ... TRAP 0006 ... The system detected an internal processing error at location
   ##0168:fff0f76c - 000f:e76c. 60000, 9084 ... Internal revision 14.089_SMP ... The system is
   stopped"*. In the other run the retained capture also ends at that announcement, and the pop-up
   log has one SYS3175 c0000005 entry for the calling process, in its own code segment
   (0001:0BE4). No retained capture shows whether the system stayed up after it. What decides
   between the two was not established.
   **`DosOpenSem` of `\SEM\`**, after its create returned 123: one retained stop screen shows the
   same location with TRAP 000d. The capture of the run it was taken in was not retained, so that
   this open caused it is **[unverified]**. Whether the open alone, without the failed create
   first, is enough was not tested.
   The *OS/2 Programming Reference* lists 123 `ERROR_INVALID_NAME` among `DosOpenSem`'s returns
   **[DOC-IBM]**.
   *(This item read "`\SEM\` stops the system ... on each of the four runs that reached this call ...
   TRAP 000d three times and TRAP 0006 once", and cited a screenshot of the system running after
   the caller-only `\SEM\*.SEM` run, until 2026-09-25. Those counts and that screenshot are not
   in a retained capture, and the TRAP 0006 screen belongs to the `\SEM\*.SEM` run.)*
2. **A `DosOpenSem` that fails 106 because the semaphore's reference count is full leaves the
   caller's own per-process open count raised.** A process whose open got 106 could afterwards
   `DosSemWait(0)` successfully on a *new* semaphore that took the same table slot, which it had
   never opened (a process that never opened a semaphore traps, section 5.9.2); and when that process
   later opened the new semaphore once and was killed, the semaphore was deleted although another
   process still held it open - an open by name then returned 187, and the holder's own
   `DosSemWait(0)` trapped. This is consistent with process teardown subtracting the inflated
   count from the reference count (section 5.9.8 step 3) **[INF]**.

## See also
- `process-thread.md` - the threads/processes these semaphores, pipes, and queues coordinate; `memory-api.md` - the shared memory named IPC objects live alongside; `thunking.md` - how 32-bit code reaches the 16-bit semaphore family in section 5.
