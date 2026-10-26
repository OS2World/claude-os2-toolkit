# OS/2 Error Codes and the APIRET Convention

How the OS/2 base (`Dos*`) API reports success and failure: every API returns an `APIRET`
value where **0 means success** and any non-zero value is an `ERROR_*` code drawn from a
single, flat, system-wide number space. The same space is partitioned into contiguous ranges
by subsystem, layered on top by two independent classification services - `DosErrClass`, which
maps any code to a *class / action / locus* triple, and the message retriever
(`DosGetMessage` and friends), which turns a code into human-readable text from a message file.
This reference gives the model of the convention, the range map, `DosErrClass`, the message
services, and representative `ERROR_*` values with their meanings.

Provenance: **[DOC-IBM]** the OS/2 Toolkit (Warp 4.5) headers `bseerr.h` (the authoritative
`ERROR_*` list, the classification constants, and the hard-error/allowed-response constants),
`bsedos.h` (`DosError`, `DosErrClass`, `DosGetMessage`, `DosInsertMessage`, `DosPutMessage`,
`DosQueryMessageCP`), and `os2def.h` (the `APIRET` type). Values, names, prototypes, and comment
text are transcribed from those headers.

---

## The APIRET convention [DOC-IBM]

`APIRET` is the return type of the base OS/2 API. From `os2def.h`:

| Type | Definition | Note |
|---|---|---|
| `APIRET`   | `unsigned long`  | 32-bit; the standard `Dos*` return type |
| `APIRET16` | `unsigned short` | 16-bit-API return type |
| `APIRET32` | `unsigned long`  | 32-bit-API return type |

The contract is uniform across the `Dos*` surface: a function returns `NO_ERROR` (`0`) on
success, or a non-zero `ERROR_*` code on failure. `NO_ERROR` is defined as `0` in `bseerr.h`.
The returned code is the *only* status channel - there is no separate `errno`; output values
are returned through caller-supplied out-pointers and are only valid when the function returned
`NO_ERROR`.

`ERROR_USER_DEFINED_BASE` is defined as `0xFF00` (65280): codes at or above this base are
reserved for application-defined use and are never assigned by the system. [DOC-IBM: `bseerr.h`]

### Two things the convention does not promise [OBS-RE - measured on Warp Server for e-business 4.50]

**A bad pointer is not reliably answered with 87.** Many calls do not check pointer arguments,
and a NULL or wild pointer ends the process with an exception instead of returning a code. Measured
cases:

| Call | NULL / bad pointer gives | Where |
|---|---|---|
| `DosCreateDir(NULL, NULL)` | SYS3175 trap in DOSCALL1 | `file-io.md` |
| `DosSetSignalExceptionFocus` with NULL or >= 512 MB `pulTimes` | the process ends | `exceptions.md` |
| `DosCreateThread` with a bad `ptid` | the process ends (not 115) | `process-thread.md` |
| `DosCreateQueue` with a NULL name, as the first queue call | the process ends silently | `ipc-synchronization.md` |
| 16-bit `DosAllocShrSeg(cb, name, NULL)` | trap | - |
| `VioGetPhysBuf` with an invalid far pointer | trap | `vio-kbd-mou.md` |
| `DosDevConfig(NULL, item)` | 87, no trap | `config-and-environment.md` |
| `DosErrClass` with a NULL class pointer | 87, no trap | below |

So 87 for a NULL is the exception, not the rule. Pass valid pointers; and in a test harness,
run any case that may trap last, after cleanup, because the trap ends every case after it.

**A failure can still write output.** `DosQueryCp` returning 473 and `DosQueryCtryInfo` returning
399 both fill the part of the buffer that fits; `DosDevConfig` returning 87 writes 0 into the
result byte; `DosQueryMessageCP` returning 111 writes what fits (`config-and-environment.md`,
`DosQueryMessageCP` below). Do not assume an out-buffer is untouched after an error, and do not
assume it is meaningful either - check what each call documents or what was measured.

### How the header is conditionally included [DOC-IBM]
`bseerr.h` splits the code space into two sets guarded by preprocessor symbols: codes **0-302**
are compiled when `INCL_DOSERRORS` or `INCL_ERROR_H` is defined (the header calls this
"set 0 - 302"), and codes **303 and up** when `INCL_DOSERRORS` or `INCL_ERROR2_H` is defined.
Defining `INCL_ERRORS` turns on all of them. This split is historical (the second set originated
in a separate `error2.h`); at runtime it is one continuous number space.

---

## The ERROR_* number space - range map [DOC-IBM]

Codes are grouped into contiguous ranges by originating subsystem. The table below maps the
ranges present in `bseerr.h`; representative members of the important ranges follow in later
sections.

| Range | Subsystem / origin |
|---|---|
| `0` | `NO_ERROR` - success |
| `1`-`~49` | DOS-compatible base errors (file, path, handle, memory, media/disk) - the classic INT 21h heritage |
| `50`-`~74` | LAN / network redirector (`ERROR_NOT_SUPPORTED` ... `ERROR_REDIR_PAUSED`) |
| `80`-`~95` | more file / process base errors |
| `99`-`~113` | semaphore, device-in-use, pipe, disk-full |
| `115`-`~166` | protection, category/level, JOIN/SUBST, thread/module, muxwait |
| `180`-`~223` | dynamic-link and executable **loader** errors (bad EXE format, ordinal, segment) |
| `224`-`~302` | pipes (named), EA (extended attributes), 32-bit semaphores, session (`SMG`) |
| `303`-`~347` | process control (`DosSub*` suballocation, PID/TID, screen-group) and **queue** (`QUE`) |
| `316`-`321` | message retriever (`MR`) errors |
| `322`-`~328` | timer (`TS`) / system-internal |
| `349`-`~471` | `VIO` (video), `SMG`/`SGS`/`SCS` (session manager), `KBD` (keyboard), `MOU`/`MOUSE`, `MON` (device monitor), `NLS` (national language) |
| `472`-`~535` | code page, selectors, trace (`TRC`), logfile (`LF`), timer (`TMR`) |
| `537`-`~548` | performance view (`PVW`) / profiling (`PRF`) |
| `639`-`651` | virtual DOS machine / virtual device driver (`VDM` / `VDD`) |
| `671`-`684` | bidirectional-text (`BIDI`) API parameter errors |
| `730`-`~731` | device monitor buffer / corrupted module |
| `2055`-`2060` | logfile facility results (`LF_*` timeout / success) |
| `32768`-`~32904` | swapper, page-memory-manager (`PMM`), and memory-manager internal errors |
| `65026`-`65079` | code-page-switch I/O (`CPSIO`) |
| `0xFF00` (65280) and up | `ERROR_USER_DEFINED_BASE` - application-reserved |

Note: the ranges are not perfectly dense - some numeric positions in 1-1000 are consumed by
*message* IDs rather than error IDs (the header notes that a message ID in a given position
makes that position unusable as an error code), so a few numbers are intentionally skipped.
[DOC-IBM: `bseerr.h` module header]

---

## Representative ERROR_* values [DOC-IBM]

All names and values below are transcribed verbatim from `bseerr.h`.

### DOS-compatible base errors (1-39)
| Value | Name | Meaning |
|---|---|---|
| 0 | `NO_ERROR` | success |
| 1 | `ERROR_INVALID_FUNCTION` | function code not valid |
| 2 | `ERROR_FILE_NOT_FOUND` | file does not exist |
| 3 | `ERROR_PATH_NOT_FOUND` | path does not exist |
| 4 | `ERROR_TOO_MANY_OPEN_FILES` | out of file handles |
| 5 | `ERROR_ACCESS_DENIED` | access denied |
| 6 | `ERROR_INVALID_HANDLE` | handle not valid |
| 8 | `ERROR_NOT_ENOUGH_MEMORY` | insufficient memory |
| 9 | `ERROR_INVALID_BLOCK` | invalid memory-block address |
| 11 | `ERROR_BAD_FORMAT` | invalid format |
| 13 | `ERROR_INVALID_DATA` | data not valid |
| 15 | `ERROR_INVALID_DRIVE` | drive does not exist |
| 18 | `ERROR_NO_MORE_FILES` | end of directory search |
| 19 | `ERROR_WRITE_PROTECT` | media write-protected |
| 21 | `ERROR_NOT_READY` | drive not ready |
| 23 | `ERROR_CRC` | data (CRC) error |
| 26 | `ERROR_NOT_DOS_DISK` | unknown media |
| 31 | `ERROR_GEN_FAILURE` | general failure |
| 32 | `ERROR_SHARING_VIOLATION` | sharing violation |
| 33 | `ERROR_LOCK_VIOLATION` | lock violation |
| 38 | `ERROR_HANDLE_EOF` | end of file reached |
| 39 | `ERROR_HANDLE_DISK_FULL` | disk full |

### Base process / parameter / semaphore / pipe (87-234)
| Value | Name | Meaning |
|---|---|---|
| 87 | `ERROR_INVALID_PARAMETER` | a parameter is not valid |
| 95 | `ERROR_INTERRUPT` | operation interrupted |
| 99 | `ERROR_DEVICE_IN_USE` | device already in use |
| 105 | `ERROR_SEM_OWNER_DIED` | semaphore owner terminated |
| 109 | `ERROR_BROKEN_PIPE` | pipe broken |
| 111 | `ERROR_BUFFER_OVERFLOW` | buffer / filename too long |
| 112 | `ERROR_DISK_FULL` | disk full |
| 115 | `ERROR_PROTECTION_VIOLATION` | protection violation |
| 117 | `ERROR_INVALID_CATEGORY` | invalid IOCtl category |
| 120 | `ERROR_CALL_NOT_IMPLEMENTED` | function not implemented (bad dynalink) |
| 121 | `ERROR_SEM_TIMEOUT` | semaphore wait timed out |
| 122 | `ERROR_INSUFFICIENT_BUFFER` | supplied buffer too small |
| 123 | `ERROR_INVALID_NAME` | name contains invalid characters |
| 124 | `ERROR_INVALID_LEVEL` | information level not valid |
| 126 | `ERROR_MOD_NOT_FOUND` | module (DLL) not found |
| 127 | `ERROR_PROC_NOT_FOUND` | procedure / entry point not found |
| 206 | `ERROR_FILENAME_EXCED_RANGE` | name too long |
| 230 | `ERROR_BAD_PIPE` | named pipe in a bad state |
| 231 | `ERROR_PIPE_BUSY` | all pipe instances busy |
| 232 | `ERROR_NO_DATA` | no data on non-blocking pipe read |
| 234 | `ERROR_MORE_DATA` | more data available |

### Executable / dynamic-link loader (180-214)
| Value | Name | Meaning |
|---|---|---|
| 182 | `ERROR_INVALID_ORDINAL` | export ordinal not valid |
| 190 | `ERROR_INVALID_MODULETYPE` | module type not valid |
| 191 | `ERROR_INVALID_EXE_SIGNATURE` | not an executable |
| 192 | `ERROR_EXE_MARKED_INVALID` | executable marked invalid |
| 193 | `ERROR_BAD_EXE_FORMAT` | bad executable format |
| 196 | `ERROR_DYNLINK_FROM_INVALID_RING` | dynamic link attempted from wrong ring |
| 197 | `ERROR_IOPL_NOT_ENABLED` | IOPL not enabled |
| 213 | `ERROR_BAD_DYNALINK` | invalid dynamic link |
| 214 | `ERROR_TOO_MANY_MODULES` | module-table limit reached |

### 32-bit semaphores and extended attributes (275-301)
| Value | Name | Meaning |
|---|---|---|
| 282 | `ERROR_EAS_NOT_SUPPORTED` | file system does not support EAs |
| 285 | `ERROR_DUPLICATE_NAME` | duplicate semaphore name |
| 287 | `ERROR_MUTEX_OWNED` | mutex semaphore is owned |
| 288 | `ERROR_NOT_OWNER` | caller is not the mutex owner |
| 290 | `ERROR_TOO_MANY_HANDLES` | too many semaphore handles |
| 292 | `ERROR_WRONG_TYPE` | wrong semaphore type |
| 298 | `ERROR_TOO_MANY_POSTS` | event-semaphore post count exceeded |
| 299 | `ERROR_ALREADY_POSTED` | event semaphore already posted |
| 300 | `ERROR_ALREADY_RESET` | event semaphore already reset |
| 301 | `ERROR_SEM_BUSY` | semaphore busy |

### Queue subsystem (`QUE`, 329-347)
| Value | Name | Meaning |
|---|---|---|
| 330 | `ERROR_QUE_PROC_NOT_OWNED` | process does not own the queue |
| 332 | `ERROR_QUE_DUPLICATE` | duplicate queue |
| 333 | `ERROR_QUE_ELEMENT_NOT_EXIST` | queue element does not exist |
| 342 | `ERROR_QUE_EMPTY` | queue is empty |
| 343 | `ERROR_QUE_NAME_NOT_EXIST` | named queue does not exist |
| 344 | `ERROR_QUE_NOT_INITIALIZED` | queue not initialized |

### Memory-manager / swapper internal (32768+)
| Value | Name | Meaning |
|---|---|---|
| 32768 | `ERROR_SWAPPER_NOT_ACTIVE` | swapper not active |
| 32772 | `ERROR_SWAP_FILE_FULL` | swap file full |
| 32775 | `ERROR_PMM_INSUFFICIENT_MEMORY` | page-memory-manager: out of memory |
| 32776 | `ERROR_PMM_INVALID_FLAGS` | page-memory-manager: invalid flags |
| 32777 | `ERROR_PMM_INVALID_ADDRESS` | page-memory-manager: invalid address |
| 32902 | `ERROR_NOMEMORY` | loader: no memory |
| 32903 | `ERROR_NOACCESS` | loader: no access |

> These high codes are internal to the memory manager and loader; they are surfaced by
> low-level services rather than routine application calls, and most have no user message
> (`MSG%none` in the header).

---

## Error classification - `DosErrClass` [DOC-IBM]

Any `ERROR_*` code can be mapped, without a lookup table of the caller's own, to a triple that
tells a program how to *react* to an error it does not specifically recognize. `DosErrClass`
performs that mapping:

```c
APIRET APIENTRY DosErrClass(ULONG  code,      /* in:  the ERROR_* code to classify */
                            PULONG pClass,     /* out: ERRCLASS_* - what kind of error */
                            PULONG pAction,    /* out: ERRACT_*   - suggested response */
                            PULONG pLocus);    /* out: ERRLOC_*   - where it occurred */
```

The three output enumerations are defined in `bseerr.h`:

### Class - `ERRCLASS_*` (the *kind* of failure)
| Value | Name | Meaning |
|---|---|---|
| 1 | `ERRCLASS_OUTRES` | out of resource |
| 2 | `ERRCLASS_TEMPSIT` | temporary situation |
| 3 | `ERRCLASS_AUTH` | permission / authority problem |
| 4 | `ERRCLASS_INTRN` | internal system error |
| 5 | `ERRCLASS_HRDFAIL` | hardware failure |
| 6 | `ERRCLASS_SYSFAIL` | system failure |
| 7 | `ERRCLASS_APPERR` | application error |
| 8 | `ERRCLASS_NOTFND` | item not found |
| 9 | `ERRCLASS_BADFMT` | bad format |
| 10 | `ERRCLASS_LOCKED` | resource locked |
| 11 | `ERRCLASS_MEDIA` | media failure |
| 12 | `ERRCLASS_ALREADY` | collision with an existing item |
| 13 | `ERRCLASS_UNK` | unknown / other |
| 14 | `ERRCLASS_CANT` | (no comment in header) |
| 15 | `ERRCLASS_TIME` | (no comment in header) |

### Action - `ERRACT_*` (the *recommended response*)
| Value | Name | Meaning |
|---|---|---|
| 1 | `ERRACT_RETRY` | retry immediately |
| 2 | `ERRACT_DLYRET` | delay, then retry after a pause |
| 3 | `ERRACT_USER` | ask the user to re-supply information |
| 4 | `ERRACT_ABORT` | abort with clean-up |
| 5 | `ERRACT_PANIC` | abort immediately |
| 6 | `ERRACT_IGNORE` | ignore the error |
| 7 | `ERRACT_INTRET` | retry after user intervention |

### Locus - `ERRLOC_*` (*where* the error occurred)
| Value | Name | Meaning |
|---|---|---|
| 1 | `ERRLOC_UNK` | no appropriate value |
| 2 | `ERRLOC_DISK` | random-access mass storage |
| 3 | `ERRLOC_NET` | network |
| 4 | `ERRLOC_SERDEV` | serial device |
| 5 | `ERRLOC_MEM` | memory |

The value of this service is that a program can respond sensibly to codes it has never seen: a
class of `ERRCLASS_TEMPSIT` with an action of `ERRACT_DLYRET` says "wait and retry" regardless of
the specific code.

---

## Hard errors and the INT 24h codes [DOC-IBM]

A distinct, small code space describes **hard errors** - device-level failures raised through the
critical-error (INT 24h) heritage path. These `ERROR_I24_*` codes are numbered independently of
the main `ERROR_*` space (they start again at 0) and appear in a hard-error report:

| Value | Name | Meaning |
|---|---|---|
| 0 | `ERROR_I24_WRITE_PROTECT` | attempted write to a write-protected disk |
| 1 | `ERROR_I24_BAD_UNIT` | bad unit |
| 2 | `ERROR_I24_NOT_READY` | drive not ready |
| 4 | `ERROR_I24_CRC` | CRC (data) error |
| 6 | `ERROR_I24_SEEK` | seek error |
| 8 | `ERROR_I24_SECTOR_NOT_FOUND` | sector not found |
| 10 | `ERROR_I24_WRITE_FAULT` | write fault |
| 11 | `ERROR_I24_READ_FAULT` | read fault |
| 12 | `ERROR_I24_GEN_FAILURE` | general failure |
| 20 | `ERROR_I24_DEVICE_IN_USE` | device in use |

The report also carries a set of **allowed-response** flags (`ALLOWED_*`) indicating which
responses the caller may return, and the packed `I24_*` fields describing the operation:

| Constant | Value | Meaning |
|---|---|---|
| `ALLOWED_FAIL` | `0x0001` | may respond "fail" |
| `ALLOWED_ABORT` | `0x0002` | may respond "abort" |
| `ALLOWED_RETRY` | `0x0004` | may respond "retry" |
| `ALLOWED_IGNORE` | `0x0008` | may respond "ignore" |
| `ALLOWED_ACKNOWLEDGE` | `0x0010` | may respond "acknowledge" |
| `ALLOWED_REGDUMP` | `0x0020` | register dump allowed |
| `ALLOWED_DISPATCH` | `0x8000` | dispatch (also `ALLOWED_DETACHED`) |
| `I24_OPERATION` | `0x01` | read/write operation bit |
| `I24_AREA` | `0x06` | affected-area field |
| `I24_CLASS` | `0x80` | error-class bit |

### Controlling hard-error and exception pop-ups - `DosError` [DOC-IBM]

```c
APIRET APIENTRY DosError(ULONG error);   /* bitwise OR of the FERR_* flags below */
```

`DosError` enables or disables the automatic system pop-up dialogs for hard errors and for
program exceptions, at process scope. The flags (from `bsedos.h`):

| Constant | Value | Meaning |
|---|---|---|
| `FERR_DISABLEHARDERR` | `0x00000000L` | disable hard-error pop-ups |
| `FERR_ENABLEHARDERR` | `0x00000001L` | enable hard-error pop-ups |
| `FERR_ENABLEEXCEPTION` | `0x00000000L` | enable exception pop-ups |
| `FERR_DISABLEEXCEPTION` | `0x00000002L` | disable exception pop-ups |

**`AUTOFAIL=YES` overrides `DosError`** [OBS-RE - measured on Warp Server for e-business 4.50,
kernel revision 14.089, booted with and without `AUTOFAIL=YES` in CONFIG.SYS; the process's
setting was read back through `DosSysCtl` function 27, an undocumented interface]. With
`AUTOFAIL=YES` every process starts with the value 2 (hard-error pop-ups off, exception pop-ups
off), and `DosError(0)` .. `DosError(3)` each return 0 but leave it at 2 - a program cannot turn
the pop-ups back on. Without the line, a process starts at 1 and `DosError` sets 0-3 as asked.
`DosError(4)` returns 87; `DosError(0x80000001)` returns 0. **The tell:** a program that calls
`DosError(FERR_ENABLEHARDERR)` still gets no "drive not ready" pop-up on a machine whose CONFIG.SYS
has `AUTOFAIL=YES`.

`DosErrClass` with a NULL class pointer returns 87 (no trap) [OBS-RE - same system].

---

## Abnormal-termination codes - `TC_*` [DOC-IBM]

When a process ends abnormally, a small `TC_*` code records the cause (defined in `bseerr.h`).
These are termination causes, not `APIRET` values:

| Value | Name | Meaning |
|---|---|---|
| 0 | `TC_NORMAL` | normal termination |
| 1 | `TC_HARDERR` | ended by a hard error |
| 2 | `TC_GP_TRAP` | general-protection trap |
| 3 | `TC_SIGNAL` | ended by a signal |
| 4 | `TC_XCPT` | ended by an unhandled exception |

---

## Turning a code into text - the message services [DOC-IBM]

`ERROR_*` codes carry associated message IDs. The header notes that "the message id's for the
first 1000 error codes ... are constructed from the comment on the `#define`" - i.e. the
`/* MSG%NAME */` comments in `bseerr.h` (and `MSG%none` marks an error with no user-visible
message). At runtime the text lives in a compiled **message file** (the base system messages are
built from a source such as `oso001.txt`), and programs retrieve it with the message API in
`bsedos.h`.

| Function | One-line purpose |
|---|---|
| `DosGetMessage` | Retrieve a message by number from a message file, substituting variable text |
| `DosInsertMessage` | Substitute variables into a message string already in memory (no file) |
| `DosPutMessage` | Write a (retrieved) message to an open file handle |
| `DosQueryMessageCP` | Query the code pages / languages a message file supports |
| `DosInsMessage` | Alias for `DosInsertMessage` (defined in `bsedos.h`) |

### `DosGetMessage` [DOC-IBM]
```c
APIRET APIENTRY DosGetMessage(PCHAR* pTable,      /* in:  table of variable substitution strings */
                              ULONG  cTable,       /* in:  count of substitution strings */
                              PCHAR  pBuf,         /* out: buffer receiving the formatted message */
                              ULONG  cbBuf,        /* in:  size of pBuf */
                              ULONG  msgnumber,    /* in:  message number to retrieve */
                              PSZ    pszFile,      /* in:  message-file name (e.g. the .MSG file) */
                              PULONG pcbMsg);      /* out: length of the returned message */
```
`pTable`/`cTable` supply the strings that replace the `%1`, `%2`, ... insertion points in the
stored message; `msgnumber` selects the message; `pszFile` names the `.MSG` file to read it from;
the formatted result is written to `pBuf` and its length returned in `pcbMsg`.
(In C++ compilation `pszFile` is typed `PCSZ`; otherwise `PSZ`.)

### `DosInsertMessage` [DOC-IBM]
```c
APIRET APIENTRY DosInsertMessage(PCHAR* pTable,   /* in:  substitution strings */
                                 ULONG  cTable,    /* in:  count of substitution strings */
                                 PSZ    pszMsg,    /* in:  source message text (in memory) */
                                 ULONG  cbMsg,     /* in:  length of pszMsg */
                                 PCHAR  pBuf,      /* out: buffer receiving the result */
                                 ULONG  cbBuf,     /* in:  size of pBuf */
                                 PULONG pcbMsg);   /* out: length of the result */
```
Same variable substitution as `DosGetMessage`, but on a message string already held in memory
rather than read from a file. (In C++ compilation `pszMsg` is typed `PCSZ`.)

Measured [OBS-RE - Warp Server for e-business 4.50, kernel revision 14.089, 32-bit probe]:

| Message, inserts | Result |
|---|---|
| `A%1B%2C%9D%0`, 9 inserts `<0>`..`<8>` | 0, `A<0>B<1>C<8>D%0` - `%1` is the first insert, `%9` the ninth, and `%0` is left as text |
| `x%1y%2z`, 1 insert | 0, `x<0>y%2z` - a `%n` with no insert is left as text |
| 10 inserts | 320 `ERROR_MR_INV_IVCOUNT` (the limit is 9); `*pcbMsg` untouched |
| `abc%1def%2ghi` into a 5-byte buffer | 316 `ERROR_MR_MSG_TOO_LONG`, `*pcbMsg` 5 |
| `plain`, 0 inserts | 0, `plain` |

### `DosPutMessage` [DOC-IBM]
```c
APIRET APIENTRY DosPutMessage(HFILE hfile,   /* in: file handle to write to */
                              ULONG cbMsg,    /* in: length of the message */
                              PCHAR pBuf);    /* in: the message text */
```
Writes a message (typically one just produced by `DosGetMessage`/`DosInsertMessage`) to an open
file or device handle, honouring line-width formatting.

### `DosQueryMessageCP` [DOC-IBM]
```c
APIRET APIENTRY DosQueryMessageCP(PCHAR  pb,          /* out: buffer for the code-page/language info */
                                  ULONG  cb,           /* in:  size of pb */
                                  PSZ    pszFilename,  /* in:  message-file name */
                                  PULONG cbBuf);       /* out: length of information returned */
```
Reports the code pages and languages a message file contains, so a caller can select the correct
one. (In C++ compilation `pszFilename` is typed `PCSZ`.)

Measured through the entry point the Toolkit's stub calls (`DosIQueryMessageCp`, with an empty
message segment) [OBS-RE - Warp Server for e-business 4.50]: the full path of `OSO001.MSG` returns 0
and 10 bytes; a **bare file name returns 2** when the session has no `DPATH` (a detached ssh session
had none) - the file is looked up along `DPATH`, not the current directory; a missing file returns
2; a 3-byte buffer returns 111 with those 3 bytes written.

---

## Sources opened
- `bseerr.h` - the full `ERROR_*` list (both sets), `ERRCLASS_*` /
  `ERRACT_*` / `ERRLOC_*`, `ERROR_I24_*`, `ALLOWED_*` / `I24_*`, `TC_*`, `ERROR_USER_DEFINED_BASE`,
  and the module-header notes on message IDs.
- `bsedos.h` - prototypes for `DosError`, `DosErrClass`,
  `DosGetMessage`, `DosInsertMessage` (`DosInsMessage`), `DosPutMessage`, `DosQueryMessageCP`, and
  the `FERR_*` flags.
- `os2def.h` - the `APIRET` / `APIRET16` / `APIRET32` typedefs.

## See also
- `calling-convention.md` - the `APIRET` return convention these codes travel in. Individual `Dos*`/`Win*` docs list the codes each call returns.
