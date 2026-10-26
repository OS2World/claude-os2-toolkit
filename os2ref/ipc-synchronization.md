# OS/2 IPC and Synchronization API

The 32-bit OS/2 inter-process communication and thread-synchronization surface: the three
kinds of 32-bit semaphore (mutex, event, and muxwait) with their named `\SEM32\` model and
`HMTX` / `HEV` / `HMUX` handle types; anonymous and named pipes (`\PIPE\`); and the queue
API (`\QUEUES\`). All of these are kernel objects with system-wide names, created private by
default and shared either by giving them a name or by requesting the shared attribute
explicitly. Waiting operations share one timeout convention: a millisecond count, with
`SEM_INDEFINITE_WAIT` (-1) meaning block forever and `SEM_IMMEDIATE_RETURN` (0) meaning poll
and return at once.

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

**Name rules, measured** [OBS-RE - measured on Warp Server for e-business 4.50, kernel revision
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
[OBS-RE - measured, three single-purpose probes, one process each]. **The tell:** a program or test
that "just stops" at its first queue call with exit code 0. Never pass NULL; and in a test, put any
case that can end the process last.

**No small per-process limit.** One process created 60 queues and opened 4 more, then created a
61st and opened a 5th: both returned 0 [OBS-RE - measured, a 16-bit probe].

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

## See also
- `process-thread.md` - the threads/processes these semaphores, pipes, and queues coordinate; `memory-api.md` - the shared memory named IPC objects live alongside.
