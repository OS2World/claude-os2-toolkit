# kLIBC / LIBC Next: the POSIX-on-OS/2 Runtime Glue

How **kLIBC** - specifically **LIBC Next** ("LIBCn"), bitwiseworks' maintained fork of the
original netlabs kLIBC - makes GCC-compiled Unix/POSIX-style C (and C++) code run on OS/2.
kLIBC is the C runtime a GCC-on-OS/2 program links against; this reference documents its
*glue layer*: how POSIX file descriptors, `fork`/`exec`, signals, `malloc`, and BSD sockets
are actually implemented on top of the native OS/2 primitives the rest of `os2ref/` describes
(`DosOpen`/`Read`/`Write`, `DosExecPgm`, `DosSetExceptionHandler`, `DosAllocMem`, the OS/2
TCP/IP stack). Where the native docs describe *what OS/2 offers*, this doc describes *what
kLIBC does with it* to make a `read(2)`/`fork(2)`/`signal(2)`-shaped program work.

## Provenance - a new tag for this doc

This doc is verified against **running source code**, not IBM documentation or reverse
engineering of a binary, so it introduces one additional tag on top of the corpus-wide
scheme in `README.md` (that legend - `[DOC-IBM]`/`[OBS-RE]`/`[DOC]`/`[unverified]` - is
unchanged and still applies where those kinds of claims appear here too):

- **[SRC]** - read directly from the LIBC Next source tree, with the file and line/function
  cited. Paths are given relative to the repository root, e.g. `src/emx/src/lib/sys/__read.c:74`.
  The tree used for this pass is bitwiseworks' `libc` GitHub repository (see `sources.md`).
  Clone it anywhere; every path cited below is relative to that repository root, so they
  resolve in your checkout regardless of where it lives.

One caveat specific to this pass: the local checkout's `src/emx/src/lib/sys/pty.c` (and its
companion `src/emx/include/pty.h`) are **not part of bitwiseworks' upstream history** - `git
log` shows them as untracked additions in that checkout, apparently added by a separate,
unrelated local project (their copyright header names a different project entirely, and they
cite design docs that do not exist anywhere in the tree). This
doc therefore does **not** cite `pty.c` as evidence of upstream LIBC Next pty behaviour, and
flags console/tty ioctl handling as [unverified] rather than guess from that file.

## 1. Overview: the glue problem

kLIBC/LIBC Next is the C runtime a GCC-on-OS/2 program links (statically or against
`LIBCn0xx.DLL`/`LIBC0xx.DLL`). Its job is to make `open`/`read`/`write`/`fork`/`mmap`-shaped
POSIX code - most of it written with Linux or generic Unix semantics in mind - run correctly
on a system that has none of: a real `fork()`, a unified byte-stream file-descriptor space
that already includes pipes/sockets/ttys, POSIX signals, `mmap`-style anonymous memory, or a
BSD kernel socket layer. Every one of those had to be *synthesized* on top of what OS/2
actually offers (`DosOpen`, named pipes, `DosExecPgm`, `DosSetExceptionHandler`/`XCPT_*`,
`DosAllocMem`, and a separate TCP/IP stack whose "sockets" are not Control Program file
handles at all - see `tcpip-sockets.md`). The result is a fairly elaborate backend layer
(`src/emx/src/lib/sys/`, prefixed `__libc_Back_*`/`__libc_back_*`) sitting under the
POSIX-named entry points (`src/emx/src/lib/io/`, `lib/process/`, `lib/malloc/`, ...) that
application code actually calls. The single most important seam in that backend is the
per-descriptor **file-handle (fh) framework** covered next - nearly everything else (pipes,
sockets, ttys) is a plug-in to it.

Confirmed from the CRT init/startup design comment: [SRC `src/emx/src/lib/startup/startup.c:122-198`]
gives kLIBC's own top-to-bottom account of `LIBCxy.DLL` init -> your DLLs' init ->
your `.EXE`'s `crt0.s`/`__init()` -> `main()` -> `exit()`; section 6 below expands on it.

---

## 2. The file-handle (fh) framework

### 2.1 Shape: `__LIBC_FH` + `__LIBC_FHOPS`

Every kLIBC file descriptor is backed by a `__LIBC_FH` ("LIBCFH") struct, reachable through
a global table (`gpapFHs`, an array of `__LIBC_PFH` pointers indexed by fd) maintained in
`src/emx/src/lib/sys/filehandles.c`. [SRC `filehandles.c:70-78`]

```c
/** Common part of a per 'file' handle structure. */
typedef struct __libc_FileHandle
{
    volatile unsigned int   fFlags;       /* O_*/F_*/FD_* bits, see below      */
    volatile int            iLookAhead;   /* look-ahead byte cache             */
    __LIBC_PCFHOPS          pOps;         /* NULL = plain OS/2 handle; non-NULL
                                              = custom backend vtable          */
    dev_t                   Dev;
    ino_t                   Inode;
    __LIBC_PFSINFO          pFsInfo;
    char                   *pszNativePath;
} __LIBC_FH;                                               /* [SRC emx/io.h:508-539] */
```

`fFlags`'s high nibble is a *type* tag distinguishing what kind of thing the descriptor is:
`F_FILE`, `F_DEV`, `F_PIPE`, `F_SOCKET`, `F_DIR` [SRC `emx/include/emx/io.h:63-72`] - this is
independent of whether `pOps` is set.

**The dispatch rule that runs the whole framework:** if `pFH->pOps == NULL`, the descriptor
is a plain OS/2 handle and every operation goes straight to the matching `Dos*` call; if
`pOps` is non-`NULL`, every operation instead calls through a **vtable of function pointers**
(`__LIBC_FHOPS`) that a custom backend (currently: BSD sockets - see section 7) installed when the
descriptor was created:

```c
typedef struct __libc_FileHandleOperations
{
    __LIBC_FHTYPE enmType;      /* enmFH_Socket43 / enmFH_Socket44 / enmFH_Directory / ... */
    int (*pfnClose)       (struct __libc_FileHandle *pFH, int fh);
    int (*pfnRead)        (struct __libc_FileHandle *pFH, int fh, void *pvBuf, size_t cbRead, size_t *pcbRead);
    int (*pfnWrite)       (struct __libc_FileHandle *pFH, int fh, const void *pvBuf, size_t cbWrite, size_t *pcbWritten);
    int (*pfnDuplicate)   (struct __libc_FileHandle *pFH, int fh, int *pfhNew);
    int (*pfnFileControl) (struct __libc_FileHandle *pFH, int fh, int iRequest, int iArg, int *prc);
    int (*pfnIOControl)   (struct __libc_FileHandle *pFH, int fh, int iIOControl, int iArg, int *prc);
    int (*pfnSelect)      (int cFHs, struct fd_set *pRead, struct fd_set *pWrite, struct fd_set *pExcept, struct timeval *tv, int *prc);
    int (*pfnForkParent)  (struct __libc_FileHandle *pFH, int fh, __LIBC_PFORKHANDLE pForkHandle, __LIBC_FORKOP enmOperation);
    int (*pfnForkChild)   (struct __libc_FileHandle *pFH, int fh, __LIBC_PFORKHANDLE pForkHandle, __LIBC_FORKOP enmOperation);
} __LIBC_FHOPS;                                            /* [SRC emx/io.h:393-499] */
```

A custom backend struct embeds the common `LIBCFH core;` as its first member and appends its
own fields after it - e.g. BSD sockets use `LIBCSOCKETFH { LIBCFH core; int iSocket; ... }`
[SRC `InnoTekLIBC/tcpip.h:104-115`], the same "base-struct-first" convention `pty.c`'s
(non-upstream, see caveat above) `__libc_PtyFH` also follows.

### 2.2 read()/write(): the fork in the road

`__read()` and `__write()` (the low-level syscalls `read(2)`/`write(2)` reduce to) both do
exactly this dispatch. From `__read()`: [SRC `src/emx/src/lib/sys/__read.c:19-76`]

```c
pFH = __libc_FH(handle);
if (!pFH) { errno = EBADF; return -1; }

if (!pFH->pOps)
{
    /* Standard OS/2 filehandle. */
    ...
    rc = DosRead(handle, pvBuf_safe ? pvBuf_safe : buf, cbToRead, &cbRead);
}
else
{
    /* Non-standard filehandle. */
    size_t cbRead2;
    rc = pFH->pOps->pfnRead(pFH, handle, buf, cbToRead, &cbRead2);
    cbRead = cbRead2;
}
```

`__write()` is the mirror image, calling `DosWrite` or `pFH->pOps->pfnWrite`
[SRC `__write.c:19-84`]. Both also contain an OS/2-specific quirk unrelated to the vtable
split: **device handles (`F_DEV`) reject buffers above the 512 MB line**, so a buffer at a
"high" address is bounced through a low-memory bounce buffer (`_lmalloc`) before/after the
`DosRead`/`DosWrite` call [SRC `__read.c:44-57`, `__write.c:43-67`] - this is the same
32-bit-flat/high-memory boundary discussed in section 5.

Plain **files, character devices, and (OS/2 native) named pipes all have `pOps == NULL`** -
confirmed at the point a descriptor is created by `open()`'s backend, which allocates the fh
with `pOps=NULL` regardless of whether it classified the target as `F_FILE`, `F_DEV`, or
`F_PIPE` [SRC `src/emx/src/lib/sys/b_ioFileOpen.c:345-376`]. So the "everything is a plug-in"
framing has one important exception: **regular files, devices, and OS/2 named pipes ride
straight through to `DosRead`/`DosWrite`/`DosDevIOCtl` with no vtable at all** - they are the
default backend, not a custom one. It is the things OS/2 has no native file-handle concept
for - a BSD socket, or (in principle, per the vtable's design) a userspace pty - that need
`pOps` set to a custom struct so `read`/`write`/`select`/`ioctl`/`close`/`fork` can be taught
what to do with them. section 7 shows the one custom backend actually present here, BSD sockets.

### 2.3 ioctl(): the same split, one layer up

`ioctl(2)` [SRC `src/emx/src/lib/io/ioctl.c:20-96`] always calls `__ioctl2()`
[SRC `sys/__ioctl2.c:21-124`], which repeats the `pOps` split:

```c
if (!pFH->pOps)
{
    /* Standard OS/2 filehandle. */
    switch (__IOCLW(request))
    {
        case __IOCLW(FGETHTYPE):
            rc = DosQueryHType(handle, &type, &flags);   /* classify: file/char-dev/pipe */
            ...
        default:
            errno = EINVAL;
            return -1;
    }
}
else
{
    rc = pFH->pOps->pfnIOControl(pFH, handle, request, arg, &rcRet);
}
```

Note the standard-handle branch here implements only `FGETHTYPE` (via `DosQueryHType`); it is
explicitly marked `/** @todo lots of FIO* things to go!! */` [SRC `__ioctl2.c:87`]. In
particular `tcgetattr()`/`tcsetattr()` reduce to `ioctl(fd, _TCGA/_TCSA*, ...)`
[SRC `lib/termios/tcgetatt.c`, `tcsetatt.c`], but this `__ioctl2.c` does not handle those
request codes for a plain (`pOps==NULL`) handle - **how/whether termios ioctls on a real
OS/2 console handle are serviced in this codebase is [unverified]** from what was read;
older parallel code paths exist under `src/emx/src/os2/{fileio,xf86sup,tcpip}.c` that do
handle `_TCGA`/`_TCSA*` [SRC grep hits in those files], suggesting this may be legacy/parallel
code not fully unified with the newer `lib/sys` backend, but confirming that needs more
reading than this pass did. A generic `DosDevIOCtl`-based mapping for console raw-mode
should not be assumed without checking further.

### 2.4 select(): only custom backends are selectable

`__select()` [SRC `sys/__select.c:71-206`] walks the caller's `fd_set`s and, for each bit set,
requires `pFH->pOps` to be non-NULL and to share one common `pfnSelect`:

```c
if (!pFH->pOps || (pfnSelect && pFH->pOps->pfnSelect != pfnSelect))
{
    errno = EINVAL;
    return -1;
}
```
[SRC `__select.c:118-123`]

This means **`select()` only works on descriptors that have a custom fh backend** - i.e.
sockets (section 7) - and fails with `EINVAL` on a plain OS/2 file, character device, or named-pipe
handle (the `pOps==NULL` case). A caller mixing a socket and, say, a console handle in one
`select()` call gets `EINVAL` outright once it reaches a non-socket fd (the framework also
special-cases "wait only" calls with no fd_sets - `nfds==0` - as a pure `DosWaitEventSem`
[SRC `__select.c:43-69`,`95-96`], which needs no fh at all).

### 2.5 Handle table lifetime, inheritance, and fork

The handle table (`gpapFHs`) is sized from `DosSetRelMaxFH` at `__libc_fhInit()` time
[SRC `filehandles.c:106-166`], with the first 3 fds pre-populated (stdin/out/err) and the
rest allocated lazily on first use. Across `fork()`/`spawn()`, a child doesn't simply inherit
raw OS/2 handles the way a Unix `fork()` inherits fds "for free" - LIBC Next packs an explicit
**inherit bundle** (`__LIBC_SPMINHERIT`/`pFHBundles`) describing every open fd (standard,
directory, or socket-43/44 - the `__LIBC_SPM_INH_FHB_TYPE_*` list at HEAD has no `pty` entry;
one unused `0x60` slot is reserved as a commented-out placeholder
[SRC `InnoTekLIBC/sharedpm.h:165-177`]) that is handed to the child via shared memory and
unpacked by `__libc_fhInit()` on the child side [SRC `filehandles.c:146-253`,
`sys/__spawnve.c:45-153` (`doInherit()`)]. This bundle, not raw handle inheritance, is what
makes fd-passing across `spawn()`/`fork()` work - see section 3 for why that indirection exists at
all. (A local, uncommitted patch in some checkouts adds a `pty` bundle type and a
`case enmFH_Pty:` pack/unpack block to `filehandles.c` for an unrelated pty project - same
caveat as section 8.2: not upstream, not cited here as real LIBC Next behavior.)

---

## 3. Process/thread creation: fork/exec/spawn on top of `DosExecPgm`

OS/2 has **no address-space-duplicating `fork()`** - `DosExecPgm` only ever *starts a fresh
program image*, it never clones a running one. LIBC Next's `fork()` fakes the POSIX
contract by combining `DosExecPgm` (to get a second copy of the *same* executable running)
with an explicit **page-copy handshake** between the two processes over shared memory. This
is real, working, general-purpose `fork()` emulation (not merely spawn-and-hope) - but it
is expensive and has hard preconditions, detailed below.

### 3.1 `fork()` -> `__libc_Back_processFork()`

`fork(2)` is a thin wrapper: [SRC `lib/process/fork.c:47-55`]
```c
pid_t _STD(fork)(void)
{
    pid_t pid = __libc_Back_processFork();
    ...
}
```
which lands in `src/emx/src/lib/sys/libcfork.c` (1600+ lines). The file's own header comment
lays out the parent/child choreography: [SRC `libcfork.c:761-790`]

> The communication between parent and child is as follows:
> 1. Parent releases fork buffer and does `DosExecPgm`.
> 2. Child takes fork buffer and processes it. Child then does initialization and gives the
>    buffer back to the parent.
> 3. Parent does the main fork run. During this the buffer might go back and forth between
>    the two processes a lot.
> 4. Child does the main fork run.

The parent-side driver `forkParDo()` performs, in order: get the process's registered
"forkable modules" list, verify the executable is fork-capable (`forkParCanFork()`),
allocate a fork handle, run pre-exec parent-side callbacks, `DosExecPgm` the child
(`forkParExec()`), then run the actual "fork" payload - the page duplication - in both
parent and child context [SRC `libcfork.c:790-890`]. `forkParExec()` literally calls
`DosExecPgm(szErr, sizeof(szErr), EXEC_ASYNCRESULT, fibGetCmdLine(), NULL, &rsc, szPgm)`
(or a `"forking\0forking\0"` sentinel argv) to start the child [SRC `libcfork.c:1291,1293`].
Memory is transferred in `FORKPGCHUNK` units - address, size, virtual size, and page
attributes of a duplicated range [SRC `libcfork.c:65-82`] - copied with one of several
page-copy implementations chosen at runtime by CPU feature (`forkBthCopyPagesPlain`/`MMX`/
`MMXNonTemporal`/`SSE2`, selected via `pfnForkBthCopyPages`) [SRC `libcfork.c:234-239,264`].

### 3.2 The precondition: `-Zfork` and "forkable modules"

`forkParDo()` refuses outright if the executable wasn't built fork-capable:
```c
if (forkParCanFork(pModules))
{
    LIBC_ASSERTM_FAILED("Can't fork this process, the executable wasn't built with -Zfork!\n");
    LIBCLOG_ERROR_RETURN_INT(-ENOSYS);
}
```
[SRC `libcfork.c:805-809`]

Every module (the `.exe` and every DLL it links) that wants to participate in a `fork()`
must register itself via `__libc_ForkRegisterModule()`, called from crt0/dll0 startup code,
which links a `__LIBC_FORKMODULE` describing the module's data-segment range and its
`pfnAtFork` callback into a per-process list [SRC `libcfork.c:328-380` (doc comment),
`InnoTekLIBC/fork.h`]. `forkParValidateModules()` [SRC `libcfork.c:1028-1049` region] checks
every module in that chain can actually be handled before committing to the fork. This is
the practical, source-confirmed shape of the well-known kLIBC constraint: **`fork()` only
works for code (and every DLL it depends on) that was compiled/linked with GCC's `-Zfork`
support**; a fork of a process using a non-fork-aware DLL fails with `ENOSYS` rather than
silently doing the wrong thing.

### 3.3 Practical limitations vs POSIX `fork()`

From the mechanism above, the following follow directly and are consistent with kLIBC's
long-documented `fork()` caveats (the exact wording of user-facing caveats beyond what's
quoted above is **[unverified]** against this pass, but the mechanics fully explain them):

- **It is heavy**: every `fork()` is a real `DosExecPgm` (a fresh OS/2 process, with its own
  loader work) plus a full page-copy handshake - not a cheap copy-on-write clone.
- **Every linked module must be fork-aware** (`-Zfork`); one non-participating DLL in the
  process breaks `fork()` for the whole process.
- **Timing window between `DosExecPgm` and the page-copy completing**: the comment's own
  phrase "the buffer might go back and forth ... a lot" implies the child is not immediately
  a full memory image of the parent - the two sides are still actively reconciling state
  after the child process technically exists.
- fd inheritance goes through the explicit inherit-bundle mechanism in section 2.5, not implicit
  handle duplication - this is *by design*, not a missing feature, because OS/2 handles
  don't carry the same "inherited on fork" semantics a Unix kernel enforces for free.
- **`fork()` breaks when LIBCN0.DLL itself is side-loaded as a second copy via
  `LIBPATHSTRICT=T` + `BEGINLIBPATH`** [OBS-RE, 2026-08, LIBC Next 0.1.14 on Warp 4.52].
  Measured with a byte-identical copy of the installed `libcn0.dll` placed in a private
  directory and a shell launched under `SET LIBPATHSTRICT=T` + `SET BEGINLIBPATH=<that dir>`:
  `bash -c "id; id"` hangs on the first fork - and the same binary works when the DLL
  resolves to the system copy (with or without `LIBPATHSTRICT=T` set). So the trigger is the
  *second resident copy of LIBC*, not the DLL's contents and not `LIBPATHSTRICT` alone.
  Symptom cluster, from per-process strict-build logs of a hung run: the parent stops making
  libc calls before ever reaching `waitpid` (its wait thread still receives the child-death
  notification and queues SIGCHLD); the fork child arrives missing native handles that were
  `FD_CLOEXEC`/`O_NOINHERIT` in the parent (`fhForkChild1`'s strict check trips on
  `DosQueryFHState` = `ERROR_INVALID_HANDLE`); and the first grandchild's early stdout is
  truncated to its tail. The child *does* inherit the `BEGINLIBPATH`/`LIBPATHSTRICT` state
  and loads the same private copy, so this is not a mixed-copy parent/child split; the
  failing step is inside the fork handshake itself (specific mechanism **[unverified]** -
  private per-process loads plausibly break an address-identity assumption, but that reading
  has not been confirmed against the code). Practical rule: never test a rebuilt LIBC by
  side-loading it; install it as the system copy (on a snapshot) and reboot. Side-loading
  other DLLs this way remains fine.

### 3.4 `exec*()`/`spawn*()` -> `__spawnve()`

Unlike `fork()`, the `exec`/`spawn`/`system()` family maps far more directly onto
`DosExecPgm`, because POSIX `exec()` semantics (replace the current image) and OS/2
`DosExecPgm` (start a new, unrelated process) are not fighting each other the way `fork()`
and `DosExecPgm` are - `execve()` on kLIBC is implemented as a synchronous spawn
(`P_OVERLAY` internally) followed by the parent process terminating with the child's exit
code, in `src/emx/src/lib/sys/__spawnve.c` (1289 lines). Highlights, all read from that file:

- **Program resolution** tries the name as given, then with `.exe` appended, resolving via
  `__libc_back_fsResolve()` [SRC `__spawnve.c:305-326`].
- **Script/interpreter detection**: before calling `DosExecPgm`, `__spawnve()` peeks at the
  target file's first bytes. If it's an MZ/kLIBC stub it proceeds normally; if not, and the
  first line starts with `#!`, it extracts the interpreter path and args and re-resolves
  against *that* [SRC `__spawnve.c:344-464` - the `#!`/hash-bang scan]; `.cmd`/`.bat`/`.btm`
  get `%COMSPEC% /C` treatment as a fallback if `DosExecPgm` reports
  `ERROR_INVALID_EXE_SIGNATURE`/`ERROR_BAD_EXE_FORMAT` [SRC `__spawnve.c:868-895`].
- **Argument marshalling** distinguishes kLIBC children (which can receive `argv` directly,
  `args_unix` mode, tagged with `__KLIBC_ARG_SIGNATURE`) from `cmd.exe`/`4os2.exe` and other
  (non-kLIBC) targets, which get a single quoted command-line string built with
  emx/cmd.exe-style quoting rules [SRC `__spawnve.c:334-790`]. Arguments/environment that
  don't fit `DosExecPgm`'s ~32 KB-per-half limit are passed via `DosAllocSharedMem` instead
  [SRC `__spawnve.c:544-654`, comment on `ARG_MAX` at 546-553].
- **stdio proxying for non-kLIBC children**: if fd 0/1/2 is a custom-backend handle (e.g. a
  socket) rather than a plain OS/2 handle, `__spawnve()` cannot just let a non-kLIBC child
  inherit it (the child wouldn't know what to do with it), so it splices in an OS/2 native
  pipe and a dedicated `fdMapper()` proxy thread that pumps bytes between the pipe and the
  real (possibly custom-backend) fd using the low-level `__read`/`__write` [SRC
  `__spawnve.c:189-225` (`fdMapper`), `794-841`].
- **The actual launch**: `DosExecPgm(szObj, sizeof(szObj), EXEC_ASYNCRESULT, pszArgsBuf,
  pszEnv, &resc, pszPgmName)` [SRC `__spawnve.c:865`].
- **Mode handling** (`P_WAIT`/`P_NOWAIT`/`P_OVERLAY`) after a successful `DosExecPgm`:
  `P_NOWAIT` returns the pid immediately; `P_WAIT` calls `wait4()` and returns the child's
  status; `P_OVERLAY` (how `execve()` is built) waits for the child, forwards its exit
  reason/signal through `__libc_spmTerm()`, and calls `DosExit()` so the calling process
  itself disappears, completing the "exec replaces the process" illusion [SRC
  `__spawnve.c:1033-1254`].

### 3.5 Threads

`DosCreateThread` is the underlying primitive (see `process-thread.md`); kLIBC's
`_beginthread()`-family and internal `__libc_back_threadCreate()` (used e.g. by the
`fdMapper` proxy thread above [SRC `__spawnve.c:1018`]) layer per-thread bookkeeping
(`__LIBC_PTHREAD` TLS-backed thread structures, signal-pending state, etc. - see
`b_threadStartup.c`, `b_threadInit.c`, `thread_internals.c`) on top of it; full field-level
detail of that layer is **[unverified]** in this pass - the `libcfork.c`/`b_thread*.c` file
names are confirmed to exist but were not read line-by-line.

---

## 4. Signal emulation: `XCPT_*` -> POSIX signal numbers

### 4.1 What gets installed, and when

Every kLIBC process installs its own OS/2 exception handler at the head of the initial
thread's chain (see `exceptions.md` for the chain mechanism itself) during `__init()`
(the `.exe`'s pre-`main()` startup, run from `crt0.s`): [SRC `sys/__init.c:388` inside
`__init()`, calling] `__libc_back_signalInitExe(&pStackFrame->ExcpRegRec)`, which does:

```c
pRegRec->prev_structure   = END_OF_CHAIN;
pRegRec->ExceptionHandler = __libc_Back_exceptionHandler;
int rc = DosSetExceptionHandler(pRegRec);
...
rc = DosSetSigHandler((PFNSIGHANDLER)__libc_back_signalOS2V1Handler16bit, NULL, NULL,
                      SIGA_ACCEPT, SIG_PFLG_A);
...
DosSetSignalExceptionFocus(SIG_SETFOCUS, &cTimes);
```
[SRC `sys/signals.c:628-654`]

So two separate OS/2 mechanisms are wired up at once: the modern 32-bit exception-handler
chain (`DosSetExceptionHandler`, `XCPT_*` codes) *and* the legacy 16-bit `DosSetSigHandler`/
`SIG_PFLG_A` path (for `SIGA_ACCEPT`-style external signal delivery, e.g. Ctrl-C from a
detached session) with `DosSetSignalExceptionFocus` claiming the signal focus for this
session [SRC `sys/signals.c:643-648`]. Each additional thread created via
`__libc_back_threadCreate()` installs the *same* `__libc_Back_exceptionHandler` at its own
`FS:[0]` root [SRC `sys/b_threadStartup.c:41`], since the exception chain is per-thread
(`exceptions.md`).

### 4.2 The dispatch table

`__libc_Back_exceptionHandler()` [SRC `sys/exceptions.c:71-367`] is the single function that
maps every OS/2 `XCPT_*` exception the kernel can raise to a POSIX signal, by calling
`__libc_Back_signalRaise()` for the mapped `si_signo`/`si_code`:

| OS/2 `XCPT_*` | POSIX signal | `si_code` | Source |
|---|---|---|---|
| `XCPT_SIGNAL` w/ `XCPT_SIGNAL_INTR` | `SIGINT` | - | `exceptions.c:99-117` |
| `XCPT_SIGNAL` w/ `XCPT_SIGNAL_BREAK` | `SIGBREAK` | - | `exceptions.c:100,114` |
| `XCPT_SIGNAL` w/ `XCPT_SIGNAL_KILLPROC` | `SIGTERM` | - | `exceptions.c:101,115` |
| `XCPT_ACCESS_VIOLATION` | `SIGSEGV` | `SEGV_ACCERR` | `exceptions.c:126-158` |
| `XCPT_DATATYPE_MISALIGNMENT` | `SIGBUS` | `BUS_ADRALN` | `exceptions.c:163-168` |
| `XCPT_INTEGER_DIVIDE_BY_ZERO` | `SIGFPE` | `FPE_INTDIV` | `exceptions.c:173-178` |
| `XCPT_INTEGER_OVERFLOW` | `SIGFPE` | `FPE_INTOVF` | `exceptions.c:180-185` |
| `XCPT_FLOAT_DIVIDE_BY_ZERO` | `SIGFPE` | `FPE_FLTDIV` | `exceptions.c:187-192` |
| `XCPT_FLOAT_OVERFLOW` | `SIGFPE` | `FPE_FLTOVF` | `exceptions.c:194-199` |
| `XCPT_FLOAT_UNDERFLOW` | `SIGFPE` | `FPE_FLTUND` | `exceptions.c:201-206` |
| `XCPT_FLOAT_DENORMAL_OPERAND` | `SIGFPE` | `FPE_FLTINV` (comment: "???") | `exceptions.c:208-213` |
| `XCPT_FLOAT_INEXACT_RESULT` | `SIGFPE` | `FPE_FLTRES` | `exceptions.c:215-220` |
| `XCPT_FLOAT_INVALID_OPERATION` | `SIGFPE` | `FPE_FLTINV` | `exceptions.c:222-227` |
| `XCPT_FLOAT_STACK_CHECK` | `SIGFPE` | `FPE_FLTINV` (comment: "???") | `exceptions.c:229-234` |
| `XCPT_ARRAY_BOUNDS_EXCEEDED` | `SIGFPE` | `FPE_FLTSUB` | `exceptions.c:236-241` |
| `XCPT_ILLEGAL_INSTRUCTION` | `SIGILL` | `ILL_ILLOPC` | `exceptions.c:247-252` |
| `XCPT_INVALID_LOCK_SEQUENCE` | `SIGILL` | `ILL_ILLADR` (comment: "??????") | `exceptions.c:254-259` |
| `XCPT_PRIVILEGED_INSTRUCTION` | `SIGILL` | `ILL_PRVOPC` | `exceptions.c:261-266` |
| `XCPT_SINGLE_STEP` | `SIGTRAP` | `TRAP_TRACE` | `exceptions.c:271-276` |
| `XCPT_BREAKPOINT` | `SIGTRAP` | `TRAP_BRKPT` | `exceptions.c:277-282` |
| `XCPT_ASYNC_PROCESS_TERMINATE` | (poke mechanism; not delivered as a normal signal) | - | `exceptions.c:288-323` |
| `XCPT_PROCESS_TERMINATE` | - (no-op today; comment: reserved for future TLS cleanup) | - | `exceptions.c:325-327` |

`XCPT_ACCESS_VIOLATION` has a special case ahead of the `SIGSEGV` mapping: if the process
links kLib's electric-fence heap debugger (`kHeapDbgException`, a `#pragma weak` symbol), the
handler first asks it whether the faulting access was one of its own guard pages and, if so,
resumes execution (`XCPT_CONTINUE_EXECUTION`) instead of raising `SIGSEGV`
[SRC `exceptions.c:126-152`].

Return value convention: the handler returns `XCPT_CONTINUE_SEARCH` (pass on to the next,
outer handler) unless `__libc_Back_signalRaise()`'s result has the `__LIBC_BSRR_PASSITON` bit
clear, in which case it returns `XCPT_CONTINUE_EXECUTION` [SRC `exceptions.c:366`] - i.e. a
user signal handler that doesn't itself terminate/longjmp can let execution resume at the
faulting instruction, matching POSIX semantics for a caught, returned-from `SIGSEGV`/`SIGFPE`
handler (which is normally undefined behaviour in C, but OS/2's re-execute semantics make it
at least *possible* here).

`__libc_Back_signalRaise()` and the actual POSIX signal-disposition bookkeeping
(`sigaction`, pending-signal sets, per-thread signal masks) live in the separate, much larger
`src/emx/src/lib/sys/signals.c` (3154 lines) and `lib/process/sig*.c` files; this pass
confirmed the exception->raise entry points above but did not trace `signals.c`'s internal
queuing/masking logic field-by-field - that deeper level is **[unverified]** here.

### 4.3 The complete signal table - every signal's default action

section 4.2 only covers the signals an OS/2 *exception* can produce. The full POSIX signal space -
what `kill()`/`raise()`/`sigaction()` see, and every signal's default disposition - is a static
table in `signals.c`, `gafSignalProperties[]`, one entry per `__SIGSET_MAXSIGNALS` signal
number, each a bitmask of a *return action*, a *default action*, and *properties*
[SRC `sys/signals.c:297-368`]. The bit meanings [SRC `sys/signals.c:99-142`]:

| Field | Values |
|---|---|
| Return action (`SPR_*`) | `SPR_KILL` = terminate after handling; `SPR_CONTINUE` = restart the interrupted instruction after handling |
| Default action (`SPA_*`) | `SPA_IGNORE`; `SPA_KILL` (terminate); `SPA_CORE` (coredump+terminate); `SPA_STOP`/`SPA_STOPTTY` (suspend the process - job control); `SPA_RESUME`; `SPA_NEXT`/`SPA_NEXT_KILL`/`SPA_NEXT_CORE` (defer to the next handler in the exception chain, or kill/core if this *is* the primary handler) |
| Properties (`SPP_*`) | `SPP_NOBLOCK` (catchable, not blockable); `SPP_NOCATCH` (not catchable at all); `SPP_ANYTHRD` (any thread may service it); `SPP_THRDONE` (only thread 1 may); `SPP_QUEUED` (siginfo is queued, e.g. for `SA_SIGINFO`); `SPP_NORESET` (no SysV auto-reset-to-`SIG_DFL` on delivery) |

The full table, decoded [SRC `sys/signals.c:300-368`]:

| # | Name | Default action | Notable properties |
|---|---|---|---|
| 0 | `SIG0` | ignore | - |
| 1 | `SIGHUP` | kill | any thread |
| 2 | `SIGINT` | kill | any thread |
| 3 | `SIGQUIT` | core | any thread |
| 4 | `SIGILL` | core (next-handler if not primary) | no auto-reset |
| 5 | `SIGTRAP` | core (next-handler if not primary) | no auto-reset |
| 6 | `SIGABRT` | core | - |
| 7 | `SIGEMT` | core | any thread |
| 8 | `SIGFPE` | core (next-handler if not primary) | - |
| 9 | `SIGKILL` | kill | any thread, unblockable, uncatchable |
| 10 | `SIGBUS` | core | - |
| 11 | `SIGSEGV` | core (next-handler if not primary) | - |
| 12 | `SIGSYS` | core | - |
| 13 | `SIGPIPE` | kill | any thread |
| 14 | `SIGALRM` | kill | any thread |
| 15 | `SIGTERM` | kill (next-handler if not primary) | any thread |
| 16 | `SIGURG` | ignore | - |
| 17 | `SIGSTOP` | stop (job control) | thread-1-only, unblockable, uncatchable |
| 18 | `SIGTSTP` | stop-from-tty (job control) | thread-1-only |
| 19 | `SIGCONT` | resume | thread-1-only |
| 20 | `SIGCHLD` | ignore | any thread, queued |
| 21 | `SIGTTIN` | stop-from-tty | thread-1-only |
| 22 | `SIGTTOU` | stop-from-tty | thread-1-only |
| 23 | `SIGIO` | ignore | any thread |
| 24 | `SIGXCPU` | kill | - |
| 25 | `SIGXFSZ` | kill | - |
| 26 | `SIGVTALRM` | kill | any thread |
| 27 | `SIGPROF` | kill | any thread |
| 28 | `SIGWINCH` | ignore - **comment: "not implemented"** | any thread |
| 29 | `SIGBREAK` | kill (next-handler if not primary) | any thread - OS/2 Ctrl-Break, EMX legacy number 21 |
| 30 | `SIGUSR1` | kill | any thread |
| 31 | `SIGUSR2` | kill | any thread |
| 32 | `SIGBREAK` (dup) | kill (next-handler if not primary) | any thread |
| 33-63 | `SIGRT0`...`SIGRT30` (`SIGRTMIN`...`SIGRTMAX`) | core | any thread, queued |

All entries default to `sa_handler == SIG_DFL` in `gaSignalActions[]` at process start
[SRC `sys/signals.c:374-410`] until a `sigaction()` call changes them.

**Gotchas this table makes explicit:**

- **`SIGWINCH` is defined but wired to `SPA_IGNORE` with an explicit "not implemented" comment**
  [SRC `sys/signals.c:331`] - a kLIBC program is never told the console/window size changed.
  Anything that wants live resize (a curses app, a shell prompt with `$COLUMNS`) has to poll
  `VioGetMode`/`DosDevIOCtl` itself; `SIGWINCH`-driven redraw, the normal Unix idiom, does not
  fire. This matters directly for pty/terminal work: a master side resizing its pty has no
  signal to deliver to the child even if the transport itself supported one.
- **Job control (`SIGSTOP`/`SIGTSTP`/`SIGCONT`/`SIGTTIN`/`SIGTTOU`) is a real, working
  software emulation, not a stub** - `signalJobStop()` sends a synthetic `SIGCHLD` (with
  `si_code = CLD_STOPPED`) to the parent, then blocks the whole process on
  `DosWaitEventSem(__libc_back_ghevWait, ...)` until resumed [SRC `sys/signals.c:2022-2050`];
  `signalJobResume()` sends `SIGCHLD`/`CLD_CONTINUED` back [SRC `sys/signals.c:2056-2071`].
  But it is **restricted to thread 1** (`SPP_THRDONE`, asserted in `signalJobStop()`
  [SRC `sys/signals.c:2029`]) - only the main thread can be job-control-stopped, so a
  multi-threaded process's other threads keep running under a "stopped" process. Whether a
  given terminal/pty layer actually *sends* `SIGTSTP`/`SIGTTIN`/`SIGTTOU` in the first place
  (real ttys do this from the line discipline on `^Z`/background-read/-write) is a separate,
  transport-level question this doc doesn't answer: it depends on the pty/terminal layer you are
  running on, not on LIBC Next's signal machinery. This doc covers only upstream LIBC Next; if
  your pty layer is a local one, its own design notes are where that answer lives.
- **`SIGCHLD` delivery on ordinary exit**, not just job-control stop/continue, exists too -
  grep `sys/signals.c` for the other `SigInfo.si_signo = SIGCHLD;` send sites around process
  termination if you need that path; this pass confirmed the job-control sends above but did
  not trace the plain-exit-notifies-parent path field-by-field, so mark that specific call
  site **[unverified]** here even though `SIGCHLD`'s existence and the wait-effecting intent
  are confirmed.
- **EMX legacy signal numbers differ from the POSIX numbers used everywhere else** - `signals.c`
  keeps a second, older numbering (`EMX_SIGHUP=1 ... EMX_SIGKILL=9 ... EMX_SIGPIPE=13 ...
  EMX_SIGALRM=14 ... EMX_SIGUSR1=16, EMX_SIGUSR2=17, EMX_SIGCHLD=18, EMX_SIGWINCH=28`
  [SRC `sys/signals.c:145-167`]) that a `switch` translates to/from at specific 16-bit/legacy
  boundaries (visible around `sys/signals.c:2200-2220`, `case SIGHUP: ... case SIGKILL: ... case
  SIGPIPE: ... case SIGALRM: ... case SIGUSR1:`). If you ever see a signal number in a debugger or
  an old EMX-era log that doesn't match `<signal.h>`, this is why - check which numbering the
  code path you're looking at uses before assuming the POSIX table above applies.

---

## 5. Memory: `malloc`/`free`/`sbrk` on `DosAllocMem`

### 5.1 The default (low) heap: `sbrk()` over `DosAllocMemEx`

kLIBC's default `malloc` arena is a classic Unix-style **sbrk-growable heap** - `_um_default_alloc()`
(the heap-expansion callback wired into the umalloc arena) rounds the request up to 64 KB and calls
`sbrk()` [SRC `lib/malloc/defalloc.c:14-79`]; `_um_default_expand()` extends the *current* top
object in place if possible, also via `sbrk()` [SRC `lib/malloc/defexpan.c:13-39`]. `sbrk()`
itself is the classic OS/2 emx primitive: `_sys_expand_heap_by()`/`_sys_shrink_heap_by()` under
a dedicated mutex (`_sys_heap_fmutex`) [SRC `sys/sbrk.c:14-35`], which in turn calls
`DosAllocMemEx(&p, size, PAG_READ | PAG_WRITE | OBJ_FORK)` when it needs to grow the top heap
object with a fresh OS/2 memory object [SRC `sys/heap.c:20-48` (`alloc_above`), used from
`_sys_expand_heap_obj_by()` at `heap.c:54`]. `OBJ_FORK` here matters for section 3: memory objects the
low heap allocates are tagged so the `fork()` machinery knows to duplicate them into a forked
child.

### 5.2 The high-memory heap (>512 MB) and the 32-bit flat-model boundary

OS/2's 32-bit flat model gives an application up to roughly 512 MB of "low" address space by
default (see `memory-model.md` for why); some OS/2 configurations extend the usable flat
address space beyond that. LIBC Next detects this and, when available, uses a **separate
high-memory heap implementation** in `src/emx/src/lib/sys/heaphigh.c` (546 lines) that
explicitly does **not** use `sbrk()` (file header: *"Note. High memory heap does not mess
around with sbrk()"* [SRC `heaphigh.c:5`]). It manages memory in large chunks
(`HIMEM_CHUNK_SIZE` = 16 MB, minimum 64 KB, committed in 256 KB increments -
`HIMEM_CHUNK_SIZE`/`_MIN`/`HIMEM_COMMIT_SIZE` [SRC `heaphigh.c:31-40`]), allocated via
`DosAllocMemEx(&pv, cbAlloc, PAG_READ | PAG_WRITE | OBJ_ANY | OBJ_FORK)` [SRC
`heaphigh.c:351-361`] - `OBJ_ANY` lets OS/2 place the object anywhere in the address space
(including above 512 MB), unlike the low heap's plain allocation. Availability of this arena
is gated by:

```c
int __libc_HasHighMem(void)
{
    return _sys_gcbVirtualAddressLimit > 512*1024*1024;
}
```
[SRC `heaphigh.c:542-545`]

i.e. the 512 MB figure is not a hardcoded assumption in application code - it is the literal
threshold LIBC Next itself tests against `_sys_gcbVirtualAddressLimit` (a value queried from
the system at startup, per the `startup.c` init-order comment in section 6) to decide whether to
enable the high-memory arena at all. section 2.2's read/write bounce-buffer logic (devices reject
buffers >= 512 MB) is the *consumer*-side version of the same boundary: a device driver talks
in 16-bit-segment terms and can't accept a "high" linear address, regardless of whether the
memory above the line is otherwise usable.

Which heap ordinary `malloc()`/`free()` actually uses (low vs. high, and the app-level
opt-in/veto bit mentioned in `__init()`'s `fFlags` parameter - "Bit 0: If set the application
is open to put the default heap in high memory" [SRC `sys/__init.c:312-313`]) is
**[unverified]** in the depth this pass read; the two arena implementations and their
`DosAllocMem*` backing are confirmed, but the selection policy between them was not traced
end-to-end.

---

## 6. Startup/CRT: from the OS/2 loader to `main()`

LIBC Next's own internal doc-comment in `startup.c` is authoritative here and worth quoting
directly rather than paraphrasing loosely - it is the single clearest primary source for the
whole sequence: [SRC `src/emx/src/lib/startup/startup.c:122-198`]

> **LIBCxy.DLL:**
> - `dll0.s` gets control and calls `__init_dll` in `sys/__initdll.c`
>   - `__init_dll` calls `__libc_HeapVote()` to do the heap voting.
>   - initiates `_osminor`/`_osmajor`, `_sys_gcbVirtualAddressLimit`, `_sys_pid`/`_sys_ppid`.
>   - creates `_sys_heap_fmutex`, `_sys_gmtxHimem`, `__libc_gmtxExec`.
>   - initiates `__libc_gpTLS` (an allocated TLS `ULONG`) - the thread struct itself is
>     lazily initialized on first reference.
>   - calls `_sys_init_environ()` (which calls `_hmalloc()`, initiating the high heap) to
>     build `environ`/`_org_environ`.
>   - calls `__libc_spmSelf()` (init the Shared Process Manager state; pick up anything
>     inherited from a parent - see section 2.5/section 3.4).
>   - calls `_sys_init_largefileio()` (checks for large-file APIs).
>   - calls `__libc_fhInit()` - initializes the fd table (section 2).
>   - processes `LIBC_HOOK_DLLS` if present in the environment.
>   - initializes `_sys_clock0_ms`.
> - `dll0.s` calls `_DLL_InitTerm` (`startup/dllinit.c`), which calls `_CRT_init()`
>   (initializes the file-handle tables, then runs the registered CRT init functions in
>   `__crtinit1__`) and `__ctordtorInit()` (static-C++-constructor equivalent, exception
>   registration).
>
> **Your.DLL:** repeats the `dll0.s`/`__init_dll`/`_DLL_InitTerm` shape, but most of the above
> is a no-op the second time (already done for `LIBCxy.DLL`); this DLL's own `_CRT_init()`
> call and `__ctordtorInit()` still run its own constructors.
>
> **Your.exe:**
> - `crt0.s` calls `___init_app` (`sys/386/appinit.s`) -> `__init()` (`sys/__init.c`).
>   - `__init()` calls `__init_dll()` (common init, mostly already done).
>   - parses the OS/2 command line (`fibGetCmdLine()`) to size and then build `argv`.
>   - allocates stack space for the argument array *and* `main()`'s call frame together.
>   - calls `__libc_spmInheritFree()` to release the (now-consumed) inherit data.
>   - installs the exception handler and sets the signal focus (section 4.1).
>   - "returns" via the `___init_ret` trampoline in `sys/386/appinit.s`.
> - `crt0.s` regains control with `esp` pointing at a fully-formed call frame for `main()`.
> - `crt0.s` calls `_CRT_init()` (a no-op - already done via `LIBCxy.DLL`'s init).
> - `crt0.s` calls `main()`.
> - `crt0.s` calls `exit()` with `main()`'s return value, which runs `atexit()` handlers and
>   calls `DosExit` with the exit code.

Concretely, `__init()`'s stack-frame layout for `main()` and `argv` construction is:
[SRC `sys/__init.c:320-402`]

```c
struct stackframe
{
    int                          argc;
    char **                      argv;
    char **                      envp;
    EXCEPTIONREGISTRATIONRECORD  ExcpRegRec;
    char *                       apszArg[1];   /* argv storage follows on the stack */
} *pStackFrame;
...
cb = parse_args(fibGetCmdLine(), NULL, NULL);       /* size the args */
cb += (argc + 1) * sizeof(char *) + sizeof(struct stackframe);
pStackFrame = alloca(cb);                            /* allocate on THIS stack */
pStackFrame->envp = _org_environ;
pStackFrame->argc = argc;
pStackFrame->argv = &pStackFrame->apszArg[0];
parse_args(fibGetCmdLine(), pStackFrame->argv, (char*)&pStackFrame->argv[argc + 1]);
```

i.e. `argv` is parsed twice (once to measure, once to fill in) directly from the OS/2
loader's raw command-line string returned by `fibGetCmdLine()` (a wrapper over the process's
FIB/command-line info - see `infoseg.md`/`process-thread.md` for the PIB this ultimately
comes from), and `argv`/the exception-registration record/`main`'s call frame are all
allocated together in one `alloca()`'d block so they share the initial thread's real stack.
`DosGetInfoBlocks` (documented in `process-thread.md`) is the general TIB/PIB accessor;
this pass did not find a distinct kLIBC path that avoids it for argv/environ (`environ` is
built by `_sys_init_environ()` per the doc-comment above, not read line-by-line in this pass
- **[unverified]** at that level of detail).

---

## 7. Sockets: BSD API over OS/2 TCP/IP

`tcpip-sockets.md` already establishes the key native fact this section builds on: an OS/2
socket, as returned by the TCP/IP stack, **is not a Control Program file handle** and cannot
be reached with `DosRead`/`DosWrite`/`DosClose` - the stack ships its own `_System`-linkage
entry points (`soclose`, `so_cancel`, etc.). kLIBC's job is to make a socket look like an
ordinary POSIX fd anyway, and it does so with exactly the fh-framework plug-in point section 2
describes.

**The socket fh backend.** `LIBCSOCKETFH` embeds the common `LIBCFH core` and adds the raw
OS/2 socket number: [SRC `InnoTekLIBC/tcpip.h:104-115`]
```c
typedef struct __libc_SocketHandle
{
    LIBCFH      core;
    int         iSocket;                                 /* the native OS/2 socket number */
    struct __libc_SocketHandle * volatile pNext, * volatile pPrev;
} LIBCSOCKETFH, *PLIBCSOCKETFH;
```
`TCPNAMEG44(AllocFH)`/`TCPNAMEG43(AllocFH)` and the `...AllocFHEx` variants
[SRC `InnoTekLIBC/tcpip.h:218-270`] are what `socket()`/`accept()` call to mint a kLIBC fd
(with `pOps` pointing at the socket ops vtable and `enmType` = `enmFH_Socket44` or
`enmFH_Socket43`) that wraps a given native `iSocket`. The `43`/`44` split names two
generations of the OS/2 TCP/IP stack's socket ABI (pre- and post-BSD-4.4-style headers); the
`TCPNAME`/`TCPNAMEG` macros pick the build-time default
[SRC `InnoTekLIBC/tcpip.h:42-75`].

**Where the actual socket calls go.** The header declares a long list of `_System`-linkage
`__libsocket_*` entry points - `__libsocket_socket`, `_bind`, `_connect`, `_accept`, `_recv`,
`_send`, `_recvfrom`, `_sendto`, `_setsockopt`, `_getsockopt`, `_shutdown`, `_soclose`,
`_ioctl`, `_os2_ioctl`, `_os2_select`, `_bsdselect`, ... [SRC `InnoTekLIBC/tcpip.h:151-197`].
These resolve to entry points in the OS/2 TCP/IP stack's socket-support DLL, loaded
dynamically; `src/emx/src/lib/sys/tcpip.c` documents the load/reload path used specifically
to keep the *same* module handle valid across a `fork()` (`__libc_tcpipForkLoadModule()`,
which calls `DosLoadModule`, and if the freshly loaded handle doesn't match the parent's,
retries by full path via `DosQueryModuleName`) [SRC `tcpip.c:61-108`]. This is the socket
analogue of section 3's forkable-module registration: a socket fd surviving `fork()` requires the
child to re-resolve the same TCP/IP stack DLL the parent had loaded, not just copy a handle
number.

**How this plugs into read/write/close/select.** Once `pOps` is set to the socket vtable,
every one of section 2's dispatch points (`__read`/`__write`/`__ioctl2`/`__select`/`close`) takes
the `pOps != NULL` branch and calls through to a socket-specific `pfnRead`/`pfnWrite`/
`pfnIOControl`/`pfnSelect` that is presumably implemented in terms of the `__libsocket_*`
entry points above (e.g. `recv`/`send`/`os2_ioctl`/`bsdselect`) - this pass confirmed the
vtable-installation and `__libsocket_*` entry-point sides but did not read the socket
backend's actual `pfnRead`/`pfnWrite` implementation bodies, so the exact
`__libsocket_recv`->`pfnRead` wiring is **[unverified]** at the line level (the shape strongly
implies it, per section 2.1's general contract, but it wasn't read directly). One confirmed use of
this plumbing: `__spawnve()`'s `P_OVERLAY` path explicitly calls
`TCPNAME(imp_shutdown)(((PLIBCSOCKETFH)pFH)->iSocket, SHUT_RD)` on a socket sitting on stdin
to unblock a proxy thread's read - i.e. application code already gets a real BSD `shutdown()`
effect through a plain kLIBC fd [SRC `sys/__spawnve.c:1169-1176`].

---

## 8. Two console bypasses: `_read_kbd()`/`KbdCharIn` (input) and `_scrsize()`/`VioGetMode` (terminal size)

Everything in section 2 describes a *uniform* fd model: whatever the backend, `read()` on a kLIBC fd
goes through `__read()`/the `pOps` dispatch. A full-text search of every `Vio*`/`Kbd*`/`Mou*`
call anywhere under `src/emx/src/lib` turns up exactly **two** hits, in two different files -
not one. Both matter to anyone hosting a kLIBC console program (bash, readline, curses/PDCurses
apps) behind a pty or any other non-physical-console transport, because both talk to the native
OS/2 console subsystem directly instead of through an fd:

| Entry point | What it does | Bypasses via |
|---|---|---|
| `_read_kbd()` -> `__read_kbd()` | reads one keystroke | `KbdCharIn`/`KbdGetStatus`/`KbdSetStatus` [SRC `sys/__read_kbd.c`] |
| `_scrsize()` | reports terminal column/row count | `VioGetMode` [SRC `sys/scrsize.c:22` at HEAD / `:55` in a checkout with the local pty patch described below] |

### 8.1 Keyboard input - `_read_kbd()`

`_read_kbd(echo, wait, sig)` [SRC `lib/misc/readkbd.c:7-10`] is a thin public wrapper that calls
straight into `__read_kbd()` [SRC `sys/__read_kbd.c:17-101`]. `__read_kbd()` talks **directly to
the OS/2 KBD subsystem** - `KbdGetStatus`/`KbdSetStatus` to flip ASCII/binary mode, then
`KbdCharIn(&key, wait ? IO_WAIT : IO_NOWAIT, 0)` to pull one keystroke
[SRC `sys/__read_kbd.c:53-67`], decoding extended/scan-code sequences and, if `echo` is set,
echoing the character back with a raw `DosWrite(1, &c, 1, &n)` [SRC `sys/__read_kbd.c:84-89`].

There is no `pOps`/`LIBCFH` lookup anywhere in this path - no fd number is even taken as a
parameter. `KbdCharIn` talks to the physical (or session's virtualized) keyboard device the
process's screen group owns, full stop:

- A process whose stdin (fd 0) has been redirected - to a pipe, a named pipe standing in for
  a pty's slave side, a socket, anything that is not the literal console keyboard queue -
  still gets real keyboard input if it calls `_read_kbd()`, and gets **nothing** from
  whatever was piped to fd 0 via that call (it would have to use `read(0, ...)` instead, which
  *does* go through section 2's framework and *does* honor redirection).
- Conversely, a process **hosted off-console** (no session/screen-group keyboard focus at
  all - the situation a pty master/slave pair is trying to create) has no `KbdCharIn` source
  to read from in the first place; with `wait=0` this returns `-1` immediately every call.

A checkout used while researching this doc carries a local, uncommitted diagnostic comment in
`__read_kbd.c` describing exactly this failure mode; that specific comment's wording is a local
annotation, not bitwiseworks' own, but the underlying `KbdCharIn` call and bypass it describes
is confirmed unmodified upstream code (`git log`/`git show HEAD:...` for this file shows no
history beyond the original import).

### 8.2 Terminal size - `_scrsize()`

`_scrsize(int *dst)` fills `dst[0]`/`dst[1]` with the terminal's column/row count. At HEAD (the
unmodified, tracked source) it does exactly one thing: call `VioGetMode(pvmi, 0)` and copy out
`pvmi->col`/`pvmi->row` [SRC `sys/scrsize.c:22` - `git show HEAD:src/emx/src/lib/sys/scrsize.c`].
Like `KbdCharIn`, `VioGetMode` queries the process's VIO session directly - there is no fd
involved and no way to redirect it. A process with no VIO session (again, the pty-hosted case)
gets whatever `VIOMODEINFO` happens to contain, unwritten by `VioGetMode` - observed in practice
as garbage column/row values, not an error return.

**A checkout used while researching this doc carries a local, uncommitted patch** to
`scrsize.c` (confirmed via `git diff HEAD` - not part of bitwiseworks' tracked history) that
checks, before calling `VioGetMode`, whether fd 1 or fd 0's `__libc_FH()` entry has
`pOps->enmType == enmFH_Pty` and if so calls `TIOCGWINSZ` via `__ioctl2()` instead. `enmFH_Pty`
itself is also a local, uncommitted addition to the `__LIBC_FHTYPE` enum in `emx/io.h` - it does
not exist in bitwiseworks' upstream `enmFH_*` list (`enmFH_File`/`enmFH_Socket43`/
`enmFH_Socket44`/`enmFH_Directory` only, per `git show HEAD:src/emx/include/emx/io.h`). Neither
the pty-aware `_scrsize()` branch nor `enmFH_Pty` should be cited as real LIBC Next behaviour;
they document one local project's in-progress attempt to fix exactly the problem this section
describes, not bitwiseworks' shipped fix (there isn't one upstream as of this pass).

### 8.3 Practical upshot

Both entry points are narrow - confirmed to be the *only* two `Vio*`/`Kbd*`/`Mou*` call sites
in all of `src/emx/src/lib` - but both are load-bearing for anything that expects a console
program's stdio redirection to also redirect its *terminal* behaviour. Redirecting stdin/stdout
is necessary but not sufficient: if the guest program (or a library it links, e.g. a curses
port) calls `_read_kbd()`/`getch()`-style input or `_scrsize()`-style size queries instead of
`read(0, ...)` / `ioctl(TIOCGWINSZ)`, no amount of fd-level plumbing reaches it upstream - the fix
has to happen above this layer, exactly as the local (non-upstream) patches above attempt for
`_scrsize()`. This is the mirror image of section 2's fh-framework story: most of kLIBC generalizes
cleanly to arbitrary fd backends, but keyboard input and terminal-size query are the two places
a native OS/2 subsystem is called out-of-band, and both are [SRC]-confirmed as unmodified
upstream behaviour in the tracked history, not a bug introduced by any local project.

---

## 9. Terminal support: what is missing, and the fork hook that breaks shells

section 8 covers the two calls that bypass the fd layer. This section covers the rest of what a program
expecting a POSIX terminal asks for and does **not** get - the practical inventory for anyone
hosting a console program (a shell, a curses app) on anything other than a physical console.

### 9.1 The unimplemented surface

Every one of these is a *generic POSIX expectation*, not an OS/2 peculiarity, and each fails in a way
that looks like a bug in the calling program:

| Call | Upstream state | Consequence |
|---|---|---|
| `setpgid()` | `errno = ENOSYS; return -1;` [SRC `lib/misc/setpgid.c`] | job control cannot initialise; a shell reports `initialize_job_control: setpgid: Function not implemented` |
| `tcsetpgrp()` / `tcgetpgrp()` | `ENOSYS` [SRC `lib/termios/tcsetpgr.c`, `tcgetpgr.c`] | no foreground-process-group concept; `^C` has no target |
| `setsid()` | `EPERM` [SRC `lib/misc/setsid.c`] | no session leader |
| `ioctl(FIONREAD)` | defined [SRC `sys/__ioctl2.c:92`] and used by callers [SRC `io/ioctl.c:72`], but the standard-handle branch implements only `FGETHTYPE`, marked `/** @todo lots of FIO* things to go!! */` [SRC `sys/__ioctl2.c:87`] | "how much input is waiting?" fails; readline falls back to a degraded one-character path |
| `select()` on a tty | only descriptors with a custom fh backend are selectable (section 2.4) [SRC `sys/__select.c:118-123`] | `select(stdin)` returns `EINVAL` on a real console handle |
| `SIGWINCH` | `SPA_IGNORE`, comment "not implemented" [SRC `sys/signals.c:331`] | **resize can only ever be discovered by polling** (section 4.3) |
| `ttyname()` | not implemented (prints `ttyname() not implemented` at runtime) | callers cannot name their terminal |

Note the `pgrp` asymmetry: the Shared Process Manager already carries a per-process `pgrp` that is
**inherited by children on spawn** [SRC `sys/sharedpm.c:607`], is readable via
`__libc_spmGetId(__LIBC_SPMID_PGRP)` [SRC `sys/sharedpm.c:1152`], and is already used to enumerate a
group [SRC `sys/sharedpm.c:858`] and to deliver signals to one [SRC `sys/sharedpm.c:1845`]. `waitpid()`
likewise implements the process-group form (`pid < -1` -> `P_PGID` [SRC `lib/process/wait4.c:90-97`],
matched at [SRC `sys/b_processWait.c:910`]). Everything for POSIX process groups exists - only the
**setter** was never written, which is why `setpgid()` is a one-line `ENOSYS`.

**A trap if you do implement it:** `waitpid`'s group matching compares against the **termination-notify**
record's `pgrp` (`pWait->pgrp = Notify.pgrp` [SRC `sys/b_processWait.c:530`]), and that copy is captured
at spawn time [SRC `sys/sharedpm.c:617`]. A shell re-groups each child immediately after spawning it,
so updating only the live process record leaves the notify copy stale and the group wait never
matches - the parent waits forever.

### 9.2 A custom fh backend MUST implement `pfnForkChild`

This is the highest-cost lesson here, because the failure is remote from the cause.

`fork()` (section 3) copies the child's memory, but **not** the parent's OS/2 kernel resources: a shared
memory object mapped by the parent is not mapped in the child, and named semaphores opened by the
parent are not open in it. The fh framework's answer is the per-descriptor fork hooks
(`pfnForkParent`/`pfnForkChild`, section 2.1), called with `__LIBC_FORK_OP_FORK_CHILD` [SRC
`InnoTekLIBC/fork.h`] so each backend can re-establish itself in the child.

If a backend leaves `pfnForkChild` as a stub, everything *looks* fine until a process holding such a
descriptor forks. Observed symptom: an interactive shell **hangs on every external command** - because
a shell `fork()`s per command - while `exec`-ing the same command directly works, builtins work, and
the same program spawned (not forked) onto the same descriptor works. Those four facts together are
the signature; `exec cmd` versus `cmd` is the one-line discriminator.

The hook must re-attach **by name**, and it must not dereference the backend's shared-object pointer
to find that name: in the child that memory is not mapped yet. Cache whatever identifies the object
(an id or name) in the per-descriptor struct at creation time, rebuild the object names from it, map
and open the child's own references, then adjust any open/reference counts the object keeps.

### 9.3 `/dev/tty` is rewritten to the console device

`/dev/tty` does not reach a caller's controlling terminal: the path-rewrite layer maps it to
`/dev/con` [SRC `sys/pathrewrite.c` - `gBltinRule_dev_tty`], i.e. the physical console. A program
hosted off-console therefore *opens* `/dev/tty` successfully and gets a handle that reports
`isatty() == 1`, but reads on it fail (`EINVAL`) - an open that succeeds and then does nothing, which
is considerably more confusing than an open that fails.

### 9.4 The consequence at application level (why a shell still fails)

Worth knowing before debugging your own layer: **`bash` on OS/2 does not use its bundled readline** -
it links the external `READLN8.DLL` (readline 8.x), so reading bash's own `lib/readline/` source
describes code that does not execute. Confirm what a binary actually imports with `lx_export.py`
(`recipes/inspect-a-binary.md`), or attribute a live call with
`DosQueryModFromEIP(__builtin_return_address(0))`.

That port has a defect worth knowing about independently of any pty work. Under
`#if defined(__LIBCN__)`, `rl_gather_tyi()` and `_rl_input_available()` use `_read_kbd(0, 0, 0)` - a
**destructive** read - as an *availability test*, stashing what it removed in a `waiting_char`
global. `waiting_char` is assigned in those two places and **never read back anywhere in the tree**;
`rl_getc()` reads a *fresh* character. So every character consumed by an availability poll is
discarded. With a human typing, the poll almost always finds nothing pending and nothing is lost -
which is why it survives; but any input arriving faster than it is consumed (**a paste, a pipe, or a
multi-byte escape sequence such as an arrow key**) loses roughly every other byte. This corrupts
pasted input on a stock OS/2 console, not only on a pty.

---

## 10. See also

- **`file-io.md`** - the native `DosOpen`/`DosRead`/`DosWrite`/`DosDevIOCtl` surface that
  backs a `pOps==NULL` fh (section 2.2-2.3) and that `open()`/`sopen()` ultimately call into.
- **`process-thread.md`** - `DosExecPgm`/`DosCreateThread`/the TIB and PIB that section 3's
  `fork()`/`spawn()` emulation and section 6's `argv`/environ construction are built on.
- **`exceptions.md`** - the `DosSetExceptionHandler` chain and `XCPT_*` numbering that section 4's
  signal emulation installs into and translates from.
- **`memory-api.md`** (+ `memory-model.md`) - `DosAllocMem`/`DosAllocMemEx`, `PAG_*`/`OBJ_*`
  flags, and the 512 MB flat-model boundary that section 5's low/high heap split is built on.
- **`tcpip-sockets.md`** - the native BSD-style socket API section 7 wraps in a kLIBC fd, including
  why an OS/2 socket isn't a Control Program handle in the first place.
- **`module-dll.md`** - `DosLoadModule`/`_DLL_InitTerm`, the mechanism section 6 (per-DLL crt init)
  and section 7 (dynamic resolution of the TCP/IP stack's socket entry points) both depend on.
- **`vio-kbd-mou.md`** - the native `Vio*`/`Kbd*`/`Mou*` API that section 8's `_read_kbd()` and
  `_scrsize()` call directly, bypassing every other convention in this document.
