# OS/2 File and I/O API (Control Program)

The `Dos*` Control Program file interface an application calls to open, read, write, position,
resize, enumerate, query, rename, copy, delete, and lock files, plus the handle model those
calls share. All of these are 32-bit flat-model entry points exported from `DOSCALLS`; they take
zero-terminated path strings and return an `APIRET` (`0` = `NO_ERROR`). Paths are drive-and-
backslash form (`C:\OS2\FOO.TXT`), and the same info-level structures (`FILESTATUS*`,
`FILEFINDBUF*`) are shared across the query and find calls. A parallel `DosProtect*` family takes
an extra file-handle lock token but is otherwise identical; a parallel `*L` family widens sizes
and offsets to 64-bit for large-file (>2 GB) support.

Provenance: **[DOC-IBM]** OS/2 Toolkit 4.5 header `bsedos.h` (function prototypes, all constants,
`FILESTATUS*` / `FILEFINDBUF*` / `FILELOCK` / `FDATE` / `FTIME` struct layouts) and `bseerr.h`
(error-code values), `os2def.h` (`HFILE` / `LHANDLE` types); **[DOC]** IBM *Control Program
Programming Reference* (`DosFileLocks`, `DosDupHandle` remarks) for behavioural detail the header
does not carry.

---

## 1. Function map [DOC-IBM - `bsedos.h`]

| Function | Prototype (32-bit) | Purpose |
|---|---|---|
| `DosOpen` | `(PSZ pszFileName, PHFILE pHf, PULONG pulAction, ULONG cbFile, ULONG ulAttribute, ULONG fsOpenFlags, ULONG fsOpenMode, PEAOP2 peaop2)` | Open or create a file/device; returns a handle and the action taken |
| `DosClose` | `(HFILE hFile)` | Close a handle, flush and release its locks |
| `DosRead` | `(HFILE hFile, PVOID pBuffer, ULONG cbRead, PULONG pcbActual)` | Read up to `cbRead` bytes; `*pcbActual` = bytes actually read (0 = EOF) |
| `DosWrite` | `(HFILE hFile, PVOID pBuffer, ULONG cbWrite, PULONG pcbActual)` | Write `cbWrite` bytes; `*pcbActual` = bytes actually written |
| `DosSetFilePtr` | `(HFILE hFile, LONG ib, ULONG method, PULONG ibActual)` | Move the file pointer; `*ibActual` = new absolute position |
| `DosSetFileSize` | `(HFILE hFile, ULONG cbSize)` | Truncate or extend the file to `cbSize` bytes. The 16-bit export of the same call is named `DosNewSize` (section 4.2) |
| `DosSetFileLocks` | `(HFILE hFile, PFILELOCK pflUnlock, PFILELOCK pflLock, ULONG timeout, ULONG flags)` | Atomically unlock one range and/or lock another |
| `DosFindFirst` | `(PSZ pszFileSpec, PHDIR phdir, ULONG flAttribute, PVOID pfindbuf, ULONG cbBuf, PULONG pcFileNames, ULONG ulInfoLevel)` | Begin a directory search; fill `pfindbuf` with matching entries |
| `DosFindNext` | `(HDIR hDir, PVOID pfindbuf, ULONG cbfindbuf, PULONG pcFilenames)` | Continue a search opened by `DosFindFirst` |
| `DosFindClose` | `(HDIR hDir)` | Release a directory-search handle |
| `DosDelete` | `(PSZ pszFile)` | Delete a file (not read-only, not a directory) |
| `DosMove` | `(PSZ pszOld, PSZ pszNew)` | Rename/move a file or directory |
| `DosCopy` | `(PSZ pszOld, PSZ pszNew, ULONG option)` | Copy a file (or directory tree), with EAs |
| `DosDupHandle` | `(HFILE hFile, PHFILE pHfile)` | Duplicate a handle (share the same file pointer and locks) |
| `DosSetFHState` | `(HFILE hFile, ULONG mode)` | Change a handle's inheritance/cache/write-through state |
| `DosQueryFHState` | `(HFILE hFile, PULONG pMode)` | Query a handle's open-mode state word |
| `DosQueryHType` | `(HFILE hFile, PULONG pType, PULONG pAttr)` | Report whether a handle is a file, device, or pipe |
| `DosQueryFileInfo` | `(HFILE hf, ULONG ulInfoLevel, PVOID pInfo, ULONG cbInfoBuf)` | Query metadata for an open handle |
| `DosSetFileInfo` | `(HFILE hf, ULONG ulInfoLevel, PVOID pInfoBuf, ULONG cbInfoBuf)` | Set timestamps/attributes/EAs on an open handle |
| `DosQueryPathInfo` | `(PSZ pszPathName, ULONG ulInfoLevel, PVOID pInfoBuf, ULONG cbInfoBuf)` | Query metadata by path (no open handle needed) |
| `DosResetBuffer` | `(HFILE hFile)` | Flush a handle's buffered writes to the medium |

**Related whole-file / whole-volume calls in the same header** [DOC-IBM]: `DosCreateDir` /
`DosDeleteDir`, `DosSetCurrentDir` / `DosQueryCurrentDir`, `DosSetDefaultDisk` /
`DosQueryCurrentDisk`, `DosQueryFSInfo` / `DosSetFSInfo`, `DosSetVerify` / `DosQueryVerify`,
`DosSetMaxFH` / `DosSetRelMaxFH`, `DosForceDelete`, `DosEditName`.

**Variant families** [DOC-IBM]:
- `DosProtect*` (`DosProtectOpen`, `DosProtectClose`, `DosProtectRead`, `DosProtectWrite`,
  `DosProtectSetFilePtr`, `DosProtectSetFileSize`, `DosProtectSetFileLocks`,
  `DosProtectSetFHState`, `DosProtectQueryFHState`, `DosProtectQueryFileInfo`,
  `DosProtectSetFileInfo`) - `DosProtectOpen` *returns* an `FHLOCK fhFileHandleLockID` token, which the
  other `DosProtect*` operations then *take* (by value) as a trailing argument, so no other thread can
  operate on the handle without the token.
- `*L` large-file forms (`DosOpenL`, `DosSetFilePtrL`, `DosSetFileSizeL`, `DosSetFileLocksL`,
  `DosCancelLockRequestL`) - 64-bit `LONGLONG` sizes/offsets for files larger than 2 GB.

---

## 2. The handle model [DOC-IBM / DOC]

A file handle is an `HFILE` (`typedef LHANDLE HFILE;`, `LHANDLE = unsigned long`) [DOC-IBM
`os2def.h:76,235`]. Handles are per-process and are the object every I/O call operates on. A
handle carries an implicit **file pointer** (current byte position), an **open mode** word (the
access/sharing/flags it was opened with), and a set of held **byte-range locks**.

**Standard handles** [DOC - CP Reference, `DosDupHandle`]: three handle numbers are reserved by
convention for standard I/O - `0` = standard input, `1` = standard output, `2` = standard error.
`DosDupHandle` may be directed to bind a duplicate onto one of these specific numbers.

**Inheritance** [DOC-IBM `bsedos.h:713`]: by default a handle is inherited by a child process
created with `DosExecPgm`. Opening with `OPEN_FLAGS_NOINHERIT` (`0x0080`) marks the handle
private so the child does not receive it. `DosSetFHState` can set or clear the no-inherit bit on
an already-open handle.

**Duplication** [DOC / DOC-IBM `bsedos.h:1515`]: `DosDupHandle(hFile, pHfile)` returns a second
handle referring to the same open file. The two handles **share one file pointer and share
access to any locked regions**; a seek through one is visible through the other. If `*pHfile` is
passed as `0xFFFFFFFF`, the system allocates a new handle number; otherwise the value supplied is
used (a valid standard-handle number, allowing e.g. redirection of standard output). Locked
regions are shared across a `DosDupHandle` but are *not* inherited across a `DosExecPgm` call
[DOC - CP Reference, `DosFileLocks` remarks]. Because duplicates share one underlying open, a
`DosClose` on one of several duplicated handles does not update the directory or flush the file's
internal buffers to the medium - that happens only when the *last* duplicate is closed [DOC - EDM2
"DosClose (FAPI)"]. Closing a handle to a device notifies the device of the close [DOC - EDM2
"DosClose (FAPI)"].

---

## 3. `DosOpen` - flags, attributes, and action taken

`DosOpen` is the one entry point that both opens and creates. Its behaviour is driven by three
independent argument groups plus the "action" output.

### 3.1 `ulAttribute` - file attribute bits [DOC-IBM `bsedos.h:667-684`]

Applied when the file is **created**. Also the attribute set queried/set elsewhere.

| Constant | Value | Meaning |
|---|---|---|
| `FILE_NORMAL` | `0x0000` | No attributes |
| `FILE_READONLY` | `0x0001` | Read-only |
| `FILE_HIDDEN` | `0x0002` | Hidden |
| `FILE_SYSTEM` | `0x0004` | System |
| `FILE_DIRECTORY` | `0x0010` | Directory (reported, not created by `DosOpen`) |
| `FILE_ARCHIVED` | `0x0020` | Archive bit set |

> **Provenance corrected 2026-08-31 (Rule 1.7), second pass.** This claim was tagged `[OBS-RE]`
> and is now `[OBS]`. **No claim changed** - only the label. It is a capture
> from a running system, not an interpretation of a binary, and the two are
> re-verified differently (`README.md`, *Provenance*). Found on review: the first pass swept `[OBS-RE]` sites whose measurement language
> sat on the SAME line and declared "a mistag phrased without those words would
> survive". This one is phrased WITH those words - the keyword simply wrapped
> onto the next line, and this corpus hard-wraps prose. **The stated bound was
> wrong, not merely narrow**; the sweep that finds these is a proximity grep
> (+/-2 lines), not a line grep.

**Observed defaults - what a newly created object actually reports** `[OBS]`
(measured on OS/2 Warp Server for e-business, 2026-08-18 and 2026-08-19; not stated in the
Toolkit prose, which documents the constants but not the values a create leaves behind):

| Object | Reported `attrFile` | Note |
|---|---|---|
| file created by `DosOpen`, `ulAttribute = FILE_NORMAL` | `0x0020` | `FILE_ARCHIVED` |
| file created by `DosOpen`, `ulAttribute = FILE_READONLY` | `0x0021` | requested bit **plus** `FILE_ARCHIVED` |
| file created by `DosOpen`, `ulAttribute = FILE_HIDDEN\|FILE_SYSTEM` | `0x0026` | requested bits **plus** `FILE_ARCHIVED` |
| directory created by `DosCreateDir` | `0x0010` | `FILE_DIRECTORY` alone - **no** `FILE_ARCHIVED` |

> **Provenance corrected 2026-08-31 (Rule 1.7).** 1 claim in this document
> was tagged `[OBS-RE]` and is now `[OBS]`. **No claim changed** - only the
> label for how it was established. `[OBS-RE]` means *read out of a binary or the
> kernel debugger*, an interpretation; `[OBS]` means *a capture from a running
> system*, no interpretation. Each of these was a probe run on real OS/2 whose
> return codes were recorded, so `[OBS]` is the tag, and the re-verification is
> "run the probe again" rather than "read the bytes again". The two had drifted
> because `[OBS]` was in use throughout the corpus with **no definition at all**
> until that date; see `README.md`, *Provenance*.

**The 16-bit directory calls validate their trailing `reserved` parameter, and that
rejection takes precedence over the path outcome** `[OBS]` (measured 2026-08-19). `DosMkDir(PSZ, ULONG)`, `DosMkDir2(PSZ, PEAOP, ULONG)`
and `DosRmDir(PSZ, ULONG)` each reject a non-zero `reserved` with **87 `ERROR_INVALID_PARAMETER`**,
- `DosRmDir` against a path that does not exist answers 87 with `reserved = 1` and 3 with
`reserved = 0`. (That the word is checked *before* the path is resolved would be `[INF]`, not
`[OBS]` - precedence is observable, ordering is not; see section 6.1, which states this and is the
authority for the family.) The 32-bit forms have no such parameter: `DosMkDir` and
`DosMkDir2` are compatibility macros for `DosCreateDir(PSZ, PEAOP2)` [DOC-IBM `bsedos.h:1490-1491`],
and only the 16-bit API has two distinct entry points.

**An unreadable path pointer is not `ERROR_INVALID_PARAMETER` - it faults** `[OBS-RE]`.
`DosCreateDir(NULL, NULL)` does not return 87; it raises `SYS3175` (`c0000005`, access violation)
inside `DOSCALL1.DLL` and terminates the process. 87 *is* in the documented return list for the
function, but evidently for other invalid parameters, not for a pointer the kernel cannot read.

Two rules follow, and both are load-bearing for anything modelling this surface:

- **`DosOpen` sets `FILE_ARCHIVED` on every file it creates**, regardless of what the caller
  asked for - the caller's `ulAttribute` is added to it, not substituted for it.
- **A directory does not carry `FILE_ARCHIVED`.** A freshly created one reports `FILE_DIRECTORY`
  and nothing else.

`FILE_IGNORE` (`0x10000`) is used with `DosSetFileInfo` / `DosSetPathInfo` to leave the attribute
field unchanged [DOC-IBM `bsedos.h:676`]. The `MUST_HAVE_*` macros
(`(attr << 8) | attr`) build the "must-have/may-have" attribute masks used by directory searches
[DOC-IBM `bsedos.h:680-684`].

### 3.2 `fsOpenFlags` - what to do about existence [DOC-IBM `bsedos.h:691-703`]

The low two nibbles independently select the "if exists" and "if new" behaviour, OR'd together.

| Constant | Value | Applies when | Effect |
|---|---|---|---|
| `OPEN_ACTION_FAIL_IF_EXISTS` | `0x0000` | file exists | fail the open |
| `OPEN_ACTION_OPEN_IF_EXISTS` | `0x0001` | file exists | open it as-is |
| `OPEN_ACTION_REPLACE_IF_EXISTS` | `0x0002` | file exists | truncate to `cbFile` |
| `OPEN_ACTION_FAIL_IF_NEW` | `0x0000` | file absent | fail the open |
| `OPEN_ACTION_CREATE_IF_NEW` | `0x0010` | file absent | create it |

(The header also defines the older primitive bits `FILE_OPEN` `0x0001`, `FILE_TRUNCATE` `0x0002`,
`FILE_CREATE` `0x0010` that these compose from [DOC-IBM `bsedos.h:691-694`].)

### 3.3 `fsOpenMode` - access, sharing, and cache flags [DOC-IBM `bsedos.h:705-724`]

One access mode, one sharing mode, and any number of flag bits, OR'd into a single word.

| Group | Constant | Value |
|---|---|---|
| Access | `OPEN_ACCESS_READONLY` | `0x0000` |
| | `OPEN_ACCESS_WRITEONLY` | `0x0001` |
| | `OPEN_ACCESS_READWRITE` | `0x0002` |
| Sharing | `OPEN_SHARE_DENYREADWRITE` | `0x0010` |
| | `OPEN_SHARE_DENYWRITE` | `0x0020` |
| | `OPEN_SHARE_DENYREAD` | `0x0030` |
| | `OPEN_SHARE_DENYNONE` | `0x0040` |
| Flags | `OPEN_FLAGS_NOINHERIT` | `0x0080` |
| | `OPEN_FLAGS_SEQUENTIAL` | `0x0100` |
| | `OPEN_FLAGS_RANDOM` | `0x0200` |
| | `OPEN_FLAGS_RANDOMSEQUENTIAL` | `0x0300` |
| | `OPEN_FLAGS_NO_CACHE` | `0x1000` |
| | `OPEN_FLAGS_FAIL_ON_ERROR` | `0x2000` |
| | `OPEN_FLAGS_WRITE_THROUGH` | `0x4000` |
| | `OPEN_FLAGS_DASD` | `0x8000` |
| | `OPEN_FLAGS_NONSPOOLED` | `0x00040000` |
| | `OPEN_FLAGS_PROTECTED_HANDLE` | `0x40000000` |

The sharing mode declares what access the caller **denies to other openers** while its handle is
open; a subsequent `DosOpen` whose access conflicts with an existing opener's deny mode fails with
`ERROR_SHARING_VIOLATION`. `OPEN_FLAGS_DASD` opens the drive itself (raw volume) rather than a
file. `OPEN_FLAGS_FAIL_ON_ERROR` makes media errors return an error code to the caller instead of
raising a hard-error popup. `OPEN_FLAGS_WRITE_THROUGH` / `OPEN_FLAGS_NO_CACHE` control buffering.

### 3.4 `pulAction` - what actually happened [DOC-IBM `bsedos.h:686-689`]

On success `*pulAction` reports which branch was taken:

| Constant | Value | Meaning |
|---|---|---|
| `FILE_EXISTED` | `0x0001` | An existing file was opened |
| `FILE_CREATED` | `0x0002` | A new file was created |
| `FILE_TRUNCATED` | `0x0003` | An existing file was opened and truncated |

`cbFile` is the initial/allocation size used when creating or replacing; `peaop2` optionally
carries extended attributes to attach on create (may be `NULL`).

---

## 4. Positioning and sizing

### 4.1 `DosSetFilePtr` seek methods [DOC-IBM `bsedos.h:641-646`]

| Constant | Value | Origin |
|---|---|---|
| `FILE_BEGIN` | `0x0000` | Relative to start of file |
| `FILE_CURRENT` | `0x0001` | Relative to current pointer |
| `FILE_END` | `0x0002` | Relative to end of file |
| `FILE_SECTOR` | `0x8000` | Interpret `ib` as a sector number (raw/DASD) |

`ib` is a signed `LONG` displacement; `*ibActual` receives the resulting absolute offset. Seeking
beyond end-of-file is legal and, on a later write, extends the file. `DosSetFilePtrL` takes a
`LONGLONG ib` and `PLONGLONG ibActual` for 64-bit files. [DOC-IBM `bsedos.h:1630,1636`]

Measured [OBS - Warp Server for e-business 4.50, kernel revision 14.089, 32-bit probe]: a
`FILE_BEGIN` seek to -1 returns 131 `ERROR_NEGATIVE_SEEK`; method 3 returns 1 (not 87); a seek to 100
in a 10-byte file returns 0 with the pointer at 100. A read at end of file returns 0 with 0 bytes.
Reading a write-only handle, or writing a read-only one, returns 5.

### 4.2 `DosSetFileSize` - and its 16-bit name, `DosNewSize`
[DOC-IBM `bsedos.h:1612` for the prototype; `cp1.txt` "DosSetFileSize" for the contract - the
header is cited for the signature only, which is all a prototype can establish, and the correction
below is what that distinction cost]

Sets the file's length to `cbSize` - truncating (discarding data past the new end) or extending it.
`DosSetFileSizeL` is the 64-bit form. Requires write access.

> **CORRECTED 2026-09-05.** This paragraph read *"or extending (new bytes read back as zero)"*, tagged
> `[DOC-IBM bsedos.h:1612]` - a **prototype**, which cannot state a fill rule and does not. IBM says the
> opposite: *"If the file size is being extended, the file system tries to allocate additional bytes in a
> contiguous (or nearly contiguous) space on the medium. **The values of the new bytes are undefined.**"*
> [DOC-IBM `cp1.txt`, "DosSetFileSize - Remarks"; the identical sentence is in `cpgref.txt`, "Notes -
> DosSetFileSize"]. Measured on Warp Server for e-business CP2, kernel revision 14.089, C: HPFS,
> 2026-09-05: a 16-byte file grown to 64 and read back gives **48 bytes, none of them zero**, through both
> the 16-bit and the 32-bit entry point `[OBS]`. So the old sentence was wrong twice over - wrong about
> the contract, and citing a source that could not have established it. Kept marked rather than deleted:
> an implementation that zero-fills is *conformant* (undefined admits zero), and a reader who deletes the
> zero-fill in the belief that IBM requires garbage would be making the same class of error in reverse.

**The 16-bit spelling is a different export, not a different call.** At 32 bits `DosNewSize` is a macro -
`#define DosNewSize DosSetFileSize` [DOC-IBM `bsedos.h:1485`] - so there is no 32-bit entry point by that
name. At 16 bits `DosNewSize` is a real export with its own prototype, `APIRET APIENTRY DosNewSize(HFILE hf,
ULONG ulNewSize)` [DOC-IBM `bsedos16.h:1012`], mapped onto the internal `Dos16NewSize` [DOC-IBM
`bsedos16.h:824`]. `HFILE` is a `USHORT` to the 16-bit caller and a `ULONG` to the 32-bit one; nothing else
differs in the parameter list.

**The two widths are one implementation, and the 32-bit one is the derived half.** `DOSCALLS` ordinal 68 is
answered by the *kernel*, not by `DOSCALL1.DLL`, and the DLL's 32-bit entry `DOS32SETFILESIZE` has a
one-statement body that thunks down onto it `[OBS-RE]`. The callee-pop byte count for that kernel entry is
therefore recoverable as `pre_sci(6)` - `HFILE(2) + ULONG(4)` - and reads 6 in all four kernel builds
examined (SMP and UNI, base and debug); the neighbouring `DOSPROTECTNEWSIZE` reads `pre_sci(10)`, which is
the same two parameters plus an `FHLOCK(4)` and is the cross-check that 6 is a frame size rather than a
coincidence `[OBS-RE]`.

Consequences worth stating because they are what an application sees:

- **Both entry points answer identically.** Twelve cases - shrink, grow, grow to zero, a no-op resize to the
  current length, a large multi-extent grow, an unsatisfiable 4 GB grow, a read-only handle, a write-only
  handle, a closed handle, a never-opened handle, a character-device handle, and a grow followed by a
  read-back - give the same return code and the same resulting length through ordinal 68 and through
  ordinal 272 on the same volume `[OBS]`.
- **Return codes** are `0`, `5` `ERROR_ACCESS_DENIED`, `6` `ERROR_INVALID_HANDLE`, `26` `ERROR_NOT_DOS_DISK`,
  `33` `ERROR_LOCK_VIOLATION`, `87` `ERROR_INVALID_PARAMETER` and `112` `ERROR_DISK_FULL`
  [DOC-IBM `cp1.txt`, "DosSetFileSize Return Value - ulrc"]. Every one fits a `USHORT`, so the narrower
  16-bit return can not lose a value.
- **"Write access" means exactly that, and is not "opened read-write".** A handle opened
  `OPEN_ACCESS_READONLY` is refused **5**; a handle opened `OPEN_ACCESS_WRITEONLY` succeeds `[OBS]`. The
  documented sentence - *"the file must be open in a mode that allows write access"*
  [DOC-IBM `cp1.txt`, "DosSetFileSize - Remarks"] - is therefore about the access mode and not about the
  handle being read-write.
- **A closed handle and a never-opened one both give 6**, so the check is not distinguishable by an
  application as SFT-slot validity versus range validity `[OBS]`.
- **A character-device handle gives 6, not 1 or 87.** Measured on a handle opened to `NUL`: the call is
  refused `ERROR_INVALID_HANDLE` rather than "invalid function", even though the open itself succeeded
  `[OBS]`. One device, on one machine - a device with a *length*, such as a block device, is not covered.
- **A grow the volume cannot satisfy is refused `87`, not `112`, and the file is left unchanged.** Measured
  with `cbSize` = `0xFFFFFFFF` (4,294,967,295) against a volume whose total size is 2,096,608 KB, so the
  request exceeds the whole disk and could not succeed on an empty one: both entry points answer **87**
  `ERROR_INVALID_PARAMETER` with the file still at its previous length `[OBS]`. `112` `ERROR_DISK_FULL` is
  in the documented list and is the natural guess; it is not what this value produces, so the rejection is
  of the *argument* rather than an allocation that ran out of room. Where the boundary actually lies -
  volume size, filesystem maximum, 2 GB, or `0x80000000` - is **not established** by one point.
- **Shrinking is the case with no alternative.** IBM's own sample code uses this call for exactly that and
  says so at the call site: *"Not needed for expanding, ...but required for shrink"*
  [DOC-IBM DDK, `MME/SRC/MM/VSD/IBMVID/vsdini.c`].

---

## 5. Directory search - `DosFindFirst` / `DosFindNext` / `DosFindClose`

`DosFindFirst(pszFileSpec, phdir, flAttribute, pfindbuf, cbBuf, pcFileNames, ulInfoLevel)` opens a
search over the (possibly wildcarded) `pszFileSpec` and fills `pfindbuf` with up to `*pcFileNames`
entries (as many as fit in `cbBuf`); on return `*pcFileNames` is the count actually returned. The
same call returns the search handle in `*phdir`. `DosFindNext` continues it; `DosFindClose`
releases it. [DOC-IBM `bsedos.h:1536-1558`] After `DosFindClose`, a later `DosFindNext` on the
same handle fails unless an intervening `DosFindFirst` has re-opened it [DOC - EDM2 "DosFindClose (OS/2 1.x)"].

`*phdir` on entry selects the handle allocation [DOC-IBM `bsedos.h:658-660`]:

| Constant | Value | Meaning |
|---|---|---|
| `HDIR_SYSTEM` | `1` | Use the single per-process system search handle |
| `HDIR_CREATE` | `-1` | Allocate a new search handle |

`flAttribute` is a must-have/may-have attribute mask (see the `MUST_HAVE_*` macros, section 3.1)
selecting which directory entries match. `ulInfoLevel` selects the output record layout, the same
`FIL_*` levels used by `DosQueryFileInfo` (section 7).

**The may-have half does NOT behave as the CPREF literally states - measured 2026-08-16 (Warp
4.50, live system).** The CPREF's `Attribute` parameter text claims each low bit both includes
(when set) and *excludes* (when clear) files carrying that attribute, for all five of
RO/H/S/D/A [DOC-IBM cpgref "DosFindFirst - Parameter Attribute"]. Measured behaviour refutes the
exclusion clause for READONLY and ARCHIVED:

- `CMD.EXE`'s plain `dir` passes `flAttribute = 0x0016` (HIDDEN|SYSTEM|DIRECTORY - no RO, no A)
  `[OBS: the same shipped CMD binary's FindFirst2 call, argument logged]`, yet it lists
  read-only files (`attrib +r` file -> listed) and lists the ARCHIVED-attributed world (nearly
  every real file carries A). So **RO and A do not participate in may-have filtering - such
  files are returned regardless of the mask.** Only HIDDEN/SYSTEM/DIRECTORY are genuine
  may-have inclusion bits. `[OBS]`
- The must-have byte (bits 8-13) is a genuine filter per the CPREF text (unmeasured beyond
  common usage; no contradiction observed).

**Worked example - why the live INI files are invisible to `dir` (measured).** On a running
system, `dir /s C:\os2.ini` finds only `\OS2\INSTALL\OS2.INI`. The live profiles are present on
disk the whole time: `\OS2\OS2.INI` and `\OS2\OS2SYS.INI` carry **Archive+System+Read-only**,
their `\OS2\OS2.!!!` / `OS2SYS.!!!` companions carry **Archive+Hidden**, and the `\OS2\INSTALL`
copies carry plain Archive. Since CMD's find mask (0x0016) *includes* H and S, the find layer
returns the live INIs to CMD - the invisibility is CMD's own default display rule suppressing
H- and S-attributed entries (`dir /a` shows them; `attrib` sees them). They are not renamed or
removed while the system runs. `[OBS, all attribute values read via `attrib` on the live
system]`

### 5.1 Find-buffer records [DOC-IBM `bsedos.h:1003-1108`, `bsedos16.h:646-682`; cpgref/cp1 "DosFindFirst - Parameter pfindbuf"]

The record written into `pfindbuf` depends on **two** things: `ulInfoLevel`, and **which ABI
width the caller used**. All records lead with the three date/time pairs and the two sizes;
they differ in attribute width, whether an EA-list size is present, and whether a next-entry
offset chains packed variable-length records.

> **CORRECTED - the struct number is NOT the level number, and this section said it was.**
> The list below previously read *"`FILEFINDBUF3` ... (level 3)"*, *"`FILEFINDBUF4` ... (level 4)"*,
> *"(levels 3/4) a next-entry offset"* and *"`FILEFINDBUF3L`/`FILEFINDBUF4L` ... (levels 11/13
> counterparts)"*. All four are wrong, and the mistake is a natural one - the type names really
> do run 1, 2, 3, 4 and it is tempting to read them as level numbers. IBM's own `DosFindFirst`
> page says otherwise, in as many words: *"For Level 1 File Information (ulInfoLevel ==
> FIL_STANDARD): On output, pfindbuf contains the **FILEFINDBUF3** data structure without the
> last two fields"*, and *"For Level 2 File Information (ulInfoLevel == FIL_QUERYEASIZE): On
> output, pfindbuf contains the **FILEFINDBUF4** data structure"* [DOC-IBM cp1/cpgref,
> "DosFindFirst - Parameter pfindbuf"]. The large-file levels are **11 and 12**, not 11 and 13.
> Kept marked rather than rewritten: a reader who has the header in front of them will reach
> the same wrong conclusion, and the reason it is wrong is the useful part.

**The level->record map, by ABI width.** The narrow types are not obsolete and are not the
32-bit entry point's; they are what the **16-bit** entry points return, and IBM ships them in a
separate 16-bit header for exactly that reason.

| `ulInfoLevel` | 16-bit `DosFindFirst`/`DosFindFirst2`/`DosFindNext` | 32-bit `DosFindFirst`/`DosFindNext` |
|---|---|---|
| 1 `FIL_STANDARD` | `FILEFINDBUF` (name at +23) | `FILEFINDBUF3` (name at +29) |
| 2 `FIL_QUERYEASIZE` | `FILEFINDBUF2` (name at +27) | `FILEFINDBUF4` (name at +33) |
| 11 `FIL_STANDARDL` | `FILEFINDBUF3L` (name at +37) | `FILEFINDBUF3L` |
| 12 `FIL_QUERYEASIZEL` | `FILEFINDBUF4L` (name at +41) | `FILEFINDBUF4L` |

**The large-file levels are the SAME record in both widths** - only levels 1 and 2 narrow.
`[OBS]` - measured on a running OS/2 4.50 Warp Server for e-business (Convenience Package,
kernel Internal revision 14.089, C: HPFS), 2026-09-04, by filling the buffer with a sentinel
byte and reporting the offset at which the matched file's name appeared. The same fixture on
the same volume minutes apart gave `+23` to a 16-bit caller and `+29` to a 32-bit one at
level 1, so the difference is the ABI width and not the machine.

The 16-bit `DosFindFirst` has **no `ulInfoLevel` parameter at all** - its prototype types the
buffer `PFILEFINDBUF` and ends at `ulReserved` - so it is level 1 by construction. Only
`DosFindFirst2` takes a level. `DosFindNext` has no level parameter in either width: the record
shape is a property of the **search**, fixed when it was opened. [DOC-IBM `bsedos16.h:986-994`]

`FILEFINDBUF` (16-bit, level 1) - the base record the others extend:

| Field | Type | Offset | Notes |
|---|---|---|---|
| `fdateCreation` | `FDATE` | 0 | 2-byte packed date |
| `ftimeCreation` | `FTIME` | 2 | 2-byte packed time |
| `fdateLastAccess` / `ftimeLastAccess` | `FDATE` / `FTIME` | 4, 6 | |
| `fdateLastWrite` / `ftimeLastWrite` | `FDATE` / `FTIME` | 8, 10 | |
| `cbFile` | `ULONG` | 12 | Logical size |
| `cbFileAlloc` | `ULONG` | 16 | Allocated size |
| `attrFile` | `USHORT` | 20 | Attribute bits (section 3.1) |
| `cchName` | `UCHAR` | 22 | Length of `achName` |
| `achName` | `CHAR[CCHMAXPATHCOMP]` | 23 | Name (`CCHMAXPATHCOMP` = 256) |

- `FILEFINDBUF2` inserts `ULONG cbList` (full EA-set size) at +22, before `cchName`.
- `FILEFINDBUF3` prepends `ULONG oNextEntryOffset` (offset to the next packed record, 0 = last)
  and **widens `attrFile` to `ULONG`**, putting the name at +29.
- `FILEFINDBUF4` = `FILEFINDBUF3` plus `ULONG cbList`, name at +33.
- `FILEFINDBUF3L` / `FILEFINDBUF4L` are the large-file forms: `oNextEntryOffset`, `LONGLONG`
  `cbFile` / `cbFileAlloc`, `ULONG attrFile`; names at +37 and +41.

**Records are variable-length and tightly packed, and the padding rule differs by width.**
A record occupies `header + cchName + 1` (the name carries a terminating NUL). `[OBS]`, same
capture: the 32-bit level-1/level-2 records round that up to a multiple of 4 - a 7-character
name gave a stride of 40 against a need of 37 - while the **16-bit** level-1 record does not
round at all: strides of 31, 30 and 25 were measured for names of 7, 6 and 1 characters, none
of them a multiple of 4. The large-file records are not rounded in either width.

`CCHMAXPATH` is 260 and `CCHMAXPATHCOMP` (single component, incl. NUL) is 256 [DOC-IBM
`bsedos.h:630,636`].

### 5.2 Operand checks the find entry points apply [OBS]

Measured on the same system and in the same session as section 5.1, one variable at a time against a
call that otherwise succeeds:

| Condition | Answer | Width |
|---|---|---|
| `*pcSearch` (entry count) is 0 | `87` ERROR_INVALID_PARAMETER | both |
| `*phdir` is neither `HDIR_SYSTEM` nor `HDIR_CREATE` nor a live handle | `6` ERROR_INVALID_HANDLE | both |
| trailing `ulReserved` nonzero (16-bit `DosFindFirst`) | `87` | 16-bit |
| buffer too small for one record | `111` ERROR_BUFFER_OVERFLOW | both |
| nothing matches the specification | `18` ERROR_NO_MORE_FILES | both |
| `ulInfoLevel` 0 or 99 (16-bit `DosFindFirst2`) | `124` ERROR_INVALID_LEVEL | 16-bit |

Two of these are worth stating explicitly because a reasonable implementation gets them wrong.
A zero entry count is a **rejection**, not a request for zero entries - answering 0 with nothing
returned is a success for a call that did nothing. And a handle that is neither sentinel nor
live is refused **before** the search is set up, with the caller's own handle value left
unchanged, which is what lets a caller distinguish this from a successful reuse.

**A handle is written back on a buffer overflow, and it is NOT usable.** `[OBS]` When the
16-bit `DosFindFirst` refuses for `111`, `*phdir` comes back holding a non-sentinel value - the
caller is not left with `HDIR_CREATE` - and yet both `DosFindNext` and `DosFindClose` then answer
`6` for it. So "a search handle is still returned" describes what is *written*, not something the
caller may use. What the system does with the search it will not let the caller name is not
observable from outside and is not asserted here.

**The first search handle a process is given is 2, not 1.** `[OBS]` `HDIR_SYSTEM` is the value 1
and is never handed out as an allocated handle, so a caller can always distinguish its own search
from the shared one. An implementation that numbers handles from 1 makes the two
indistinguishable: passing the caller's own handle back would silently restart the *system*
search.

**Reusing a live handle re-establishes the record shape as well as the search.** `[OBS]` Handing
a live `HDIR` back to `DosFindFirst2` at a *different* `ulInfoLevel` restarts the search at the
new level, and a following `DosFindNext` - which has no level parameter - returns the **new**
level's record. Measured by reusing a level-1 handle at level 2 and reading the next entry back
at offset 27 (`FILEFINDBUF2`), not 23.

**The residual left in `*pcSearch` on a rejection is per-width, and it is not documented.**
`[OBS]` The 16-bit entry writes `65535` when it refuses for a bad count, a bad handle or a bad
level, and `0` when the search ran and returned nothing (buffer overflow, no match); the
nonzero-`ulReserved` refusal leaves the caller's value untouched. The 32-bit entry writes
nothing at all on any of those paths - the caller reads back what it passed in. A 16-bit
`DosFindNext` refusing an invalid handle produced a seventh value again - `280`, measured on two
different invalid-handle paths (an already-closed handle, and the unusable handle an overflow
leaves behind) and reproduced across captures. No IBM statement of any of these was found. Treat
`*pcSearch` after a nonzero return as undefined.

### 5.3 Packed date/time [DOC-IBM `bsedos.h:884-916`]

`FTIME` and `FDATE` are 16-bit bit-fields:

| `FTIME` field | Bits | | `FDATE` field | Bits |
|---|---|---|---|---|
| `twosecs` | 5 (0-29, x2 s) | | `day` | 5 (1-31) |
| `minutes` | 6 (0-59) | | `month` | 4 (1-12) |
| `hours` | 5 (0-23) | | `year` | 7 (relative to 1980) |

---

## 6. Whole-object operations - delete / move / copy

- `DosDelete(pszFile)` deletes a single file. It fails on a read-only file (`ERROR_ACCESS_DENIED`)
  and on a directory; `DosForceDelete` additionally bypasses the recovery/undelete hold. [DOC-IBM
  `bsedos.h:1504,1510`]
- `DosMove(pszOld, pszNew)` renames or moves a file or directory. Across directories on the same
  volume it is a rename; the header carries no cross-volume guarantee. [DOC-IBM `bsedos.h:1660`]
  Its full refusal set is section 6.4, and what happens to extended attributes is section 6.5.

- `DosCopy(pszOld, pszNew, option)` copies a file (or a directory tree) including its extended
  attributes. `option` is a bit mask [DOC-IBM `bsedos.h:662-665`]:

| Constant | Value | Meaning |
|---|---|---|
| `DCPY_EXISTING` | `0x0001` | Overwrite the target if it already exists |
| `DCPY_APPEND` | `0x0002` | Append to an existing target rather than replace it |
| `DCPY_FAILEAS` | `0x0004` | Fail if the target volume cannot hold the source's EAs |

  EA-copy behaviour is conditional [DOC - EDM2 "DosCopy (OS/2 1.x)"]: extended attributes are
  copied when creating a new file/directory or replacing an existing target file, but **not** when
  appending (`DCPY_APPEND`) or when copying into an existing target directory. A read-only target
  file cannot be replaced (returns an error). Source and target may be on different drives.
  Wildcards ("global file name characters") are not allowed in either name. On an I/O error mid-copy
  the partially-written target is cleaned up (deleted, or an appended target resized back). Beyond
  the section 10 codes, `DosCopy` may also return `ERROR_NOT_DOS_DISK` (26), `ERROR_SHARING_BUFFER_EXCEEDED`
  (36), `ERROR_FILENAME_EXCED_RANGE` (206, name too long), and `ERROR_DIRECTORY` (267, a
  file/directory type mismatch) [DOC - EDM2 "DosCopy (OS/2 1.x)"].

**Measured return codes** [OBS - measured on Warp Server for e-business 4.50, kernel revision
14.089, 32-bit probe, HPFS]:

| Call and input | Result |
|---|---|
| `DosCopy`, missing source | 3 (not 2) |
| `DosCopy`, target under a missing directory | 3 |
| `DosCopy` onto an existing file, no flags / with `DCPY_EXISTING` | 5 / 0 |
| `DosCopy` onto a read-only file | 5 |
| `DosCopy` of a source another handle has open deny-all | 32 `ERROR_SHARING_VIOLATION` |
| `DosCopy` with undefined flag 0x80000000 | 0 - the bit is ignored |
| `DosCopy` of a directory onto a file | 267 `ERROR_DIRECTORY` |
| `DosDelete` / `DosForceDelete`, bad path | 3 / 3; `DosForceDelete` of a missing file 2 |
| `DosDelete`, or `DosForceDelete`, of a file open deny-all | 32 |
| `DosDelete("*.TXT")` | 3 - wildcards are not expanded |
| `DosDeleteDir`, missing / bad path / not empty | 3 / 3 / 5 |
| `DosDeleteDir` of the current directory | 16 `ERROR_CURRENT_DIRECTORY` |
| `DosQueryPathInfo` of a file open deny-all / `DosSetPathInfo` of it | 0 / 32 |

### 6.1 The 16-bit forms carry a `reserved` word, and it is enforced [OBS]

The 16-bit entry points take a trailing `reserved` ULONG the 32-bit forms do not:

```
USHORT APIENTRY DosDelete(PSZ pszFile, ULONG ulReserved);              /* ordinal 60  */
USHORT APIENTRY DosMove(PSZ pszOld, PSZ pszNew, ULONG ulReserved);     /* ordinal 67  */
APIRET APIENTRY DosForceDelete(PSZ pszFName, ULONG ulReserverd);       /* ordinal 203 */
```

[DOC-IBM Open Watcom 1.9 `h/os21x/bsedos.h:321,335`] for the first two.

**`DosForceDelete` has a 16-bit form too, ordinal 203** [DOC-IBM
Toolkit 4.5 `H/bseord.h`:389`] - added 2026-08-27, previously absent from this
document, which named only the 32-bit ordinal 110. Its declaration is scarce and worth pinning:
the **only** one in the DDK is DDK `video/rel/os2c/include/base/os2/
16bit/bsedos16.h:969` (IBM's own `ulReserverd` typo preserved above), which also shows the
exported name is `Dos16ForceDelete` at `:802` (~~`:850`~~ - CORRECTED 2026-08-27, Rule 1.7:
the claim was true and only the line was wrong; `:850` is the *next* ordinal's
`#define DosSetFileMode Dos16SetFileMode`, cited correctly as `:850` below, so do not "fix" that
one to match this). It is **absent from Watcom's entire `os21x` tree
and from MASM60's `BSEDOS.INC`**, so a search of either alone reports it as not existing.
IBM's argument-byte count is 8, the same as `DosDelete`'s - `pre_sci(8)` [OBS-RE]. The DDK's MASM prototypes give the
calling convention, which no other source states - `DosDelete PROTO FAR PASCAL pszFName:PSZ,
ulReserverd:DWORD` and `DosMove PROTO FAR PASCAL pszOld:PSZ, pszNew:PSZ, ulReserved:DWORD`
[DOC-IBM DDK `EXE/MASM60/ddktools/toolkits/masm60/include/BSEDOS.INC:678,745`] - so the
arguments are pushed left to right and `ulReserved` sits at the lowest stack address. IBM's own
argument-byte counts are 8 and 12, from the kernel's own entry stubs `pre_sci(8)` / `pre_sci(0xc)`
[OBS-RE].

There is also a **16-bit-only** set-attribute entry point with no 32-bit counterpart:
`USHORT APIENTRY DosSetFileMode(PSZ pszFName, USHORT usAttr, ULONG ulReserved)`, **ordinal 84**
[DOC-IBM Open Watcom 1.9 `h/os21x/bsedos.h:355`; `bsedos16.h:1081`, whose `:850` shows the
exported name `Dos16SetFileMode`]. The 32-bit API has no such call - attributes are set through
`DosSetPathInfo` at `FIL_STANDARD` - and the name appears nowhere in the Warp-4.5 Toolkit
headers. It is a real export, not a compatibility alias: none of these names appears in
`bsedos.h`'s 45-entry `#define` block on either side. IBM's argument-byte count is **10**,
`pre_sci(10)` in the kernel's own entry stub [OBS-RE], corroborated independently by IBM's MASM
binding - `PUSH@ ASCIIZ FileName / PUSH WORD NewAttribute / PUSH DWORD 0 / CALL DosSetFileMode`,
4+2+4 = 10, reserved at the lowest address [DOC-IBM `$OS2_EDM2/os2books/prcp/495_L2H_DosSetFileMode.html`].

~~Its `ulReserved` semantics are **not established** - the measurements above cover ordinals 60
and 67 only, and a sibling licenses nothing.~~ **MEASURED 2026-08-27 (Rule 1.7) - see the table
below, which now covers ordinals 84 and 203 as well. It behaves exactly as ordinals 60 and 67 do,
and that was established by measuring it rather than by inheriting from them.**

**No IBM prose states what a nonzero `ulReserved` does.** Searched the CP Guide and Reference
(`cpgref`, `cp1`, `cp2`, `cp3`), the Toolkit 4.5 `BOOK/` set and the DDK: `BSEDOS.INC` names the
parameter and says nothing about its semantics, and `cpgref` documents only the 32-bit forms,
which have no such parameter. Recorded as a negative result so it is not searched for again.

> **CORRECTED 2026-08-27 (Rule 1.7) - the claim survives, but its SEARCH SET was too small and
> the omission changes what the 87 is.** The set above leaves out `$OS2_EDM2/os2books/prcp/`,
> the **16-bit** CP Reference - the only edition that documents the 16-bit signature at all, and
> therefore the one edition that could have spoken to this parameter. It states, for **both**
> calls, *"Reserved (ULONG) - input - Reserved and must be set to zero"*
> (`088_L2_DosMove.html`, `022_L2_DosDelete.html`). The literal claim is still true - IBM says
> what you must pass, never what happens if you do not - so the 87 remains `[OBS]`. What
> changes is that the measured rejection is now **explained** by a documented requirement rather
> than merely observed against silence. Repair the search set before re-asserting the negative.

> **SEARCH SET REPAIRED AND RE-RUN 2026-08-27, for ordinals 84 and 203 this time, and the
> negative survives.** `prcp` has a full page for **ordinal 84** -
> [DOC-IBM `$OS2_EDM2/os2books/prcp/145_L2_DosSetFileMode.html`] - and it says exactly the same
> thing and no more: *"Reserved (ULONG) - input - Reserved must be set to zero."* What it adds is
> a **SECOND, UNRELATED MEANING FOR 87 ON THIS ORDINAL**, which is a hazard for anyone designing
> cases here: *"Attributes for Volume Label (0008H) and Subdirectory (0010H) cannot be changed
> using DosSetFileMode. If these attributes are specified, ERROR_INVALID_PARAMETER is returned."*
> So an 87 from ordinal 84 is not self-evidently a reserved-word 87, and a case that wants to
> measure the reserved word must pass a `usAttr` that is neither `0x08` nor `0x10`. (Same page:
> the documented rc list is 2, 3, 5, 26, 32, 36, 87, 108, 206 - so **both** 2 and 3 are
> documented for a missing path, making the not-found rc a measurement rather than a
> transcription; and a root directory's attributes cannot be changed, giving
> `ERROR_ACCESS_DENIED`.)
>
> For **ordinal 203** the negative is total. `grep -rli forcedelete` across
> `$OS2_EDM2/os2books/` and `$OS2_EDM2/inf_text/` yields only the **32-bit** one-argument form
> (`cpgref.txt`, `cp1.txt`, `wps2.txt`), the UNDELETE Redbook page
> (`gg243730/140_L3_UNDELETECommand.html`), and an SMP-addendum **trace-hook ID table**
> (`smpadd-19970312/507_L3_DosFunctions6of12.html`, `30/36 DosForceDelete`) carrying no
> semantics. **`prcp` - the only edition that documents 16-bit signatures - has no
> `DosForceDelete` page at all.** Recorded so this is not searched a third time.

**The static-RE route to this question is CLOSED, and that is a recorded negative result too.**
Zero of an earlier RE write-up's ~45 write-ups mentions `ForceDelete` or `SetFileMode` at all. The kernel
entry stubs decompile to nothing but their `pre_sci(N)`, and the FSD-level bodies
(`h_DOS_SetFileMode`, `w_ChMod`, `f_w_ChMod`) come back as `void f(void)` register-soup with no
recoverable frame. The same differential already established for the directory family applies:
`h_DOS_MkDir`/`h_DOS_RmDir`, whose reserved->87 rejection *is* measured, contain **zero**
occurrences of `0x57` in their decompiles. Measure; do not disassemble.

**Three adjacent facts the reverse-engineering notes DO answer, written back here so nobody
re-derives them:**

- The 32-bit `DOS32FORCEDELETE` in `DOSCALL1.DLL` is a **pure `THK32_UNITHUNK()` body**
  [OBS-RE - unpublished notes]. IBM's own 32-bit ordinal 110 is therefore a
  descriptor-driven thunk down to the 16-bit kernel entry - the two widths are not merely
  equivalent, they are the same code.
- `W_DOSDELETE` - the kernel's **UNDELETE/DELDIR wrapper**, not the ordinal-60 entry - saves the
  file, builds a delete record via `_CreateDeleteRecord`, and then calls `_DOSFORCEDELETE`
  [OBS-RE `.../os2krnld_uni_astrict/decompiled_16/W_DOSDELETE_000f:d82c.c`]. So `DosDelete` and
  `DosForceDelete` share one destruction path, `DosDelete` merely adding the recovery record -
  which is the mechanism behind section 6's "additionally bypasses the recovery/undelete hold".
- In that call Ghidra renders the argument list as `_DOSFORCEDELETE(ptr_off, ptr_seg, 0, 0)`,
  i.e. 8 bytes = far PSZ + `ULONG 0`. **That is a HYPOTHESIS, not an answer.** A recovered
  argument list is not evidence: this corpus already carries a correction where a five-argument
  call rendered as six in scrambled order, and the standing rule is to disassemble the pushes
  rather than read an argument list off a decompile. It is consistent with `pre_sci(8)`, which
  is the fact.

  **And this one does not need an appeal to a correction elsewhere - the file refutes itself,
  which is a sharper demonstration and was missed when the bullet was first written.** The
  *same* decompile calls the *same* function twice, with two different argument lists: line 57
  renders `_DOSFORCEDELETE(local_8 + 0x104, local_8._2_2_, 0, 0)` - four - and line 74, the
  `LAB_000f_d862` tail, renders a bare `_DOSFORCEDELETE()` - none. One of those is wrong about
  a function whose real frame is fixed at 8 bytes by `pre_sci(8)`, and nothing inside the
  decompile says which. **When you catch a decompiler disagreeing with itself about one symbol,
  that is worth more than any single rendering it produces** - and it is free to look for: grep
  the callee's name in its own caller's file and count the arities.
- Both ordinals are **kernel-resident** [OBS-RE `doscall1/data/doscalls_kernel_ords.tsv`:
  `203 2 0x26ba DOSFORCEDELETE`, `84 2 0x280b DOSSETFILEMODE`], while ordinal **110 is absent**
  from that file and so is DOSCALL1-resident - consistent with its being the thunk above. That
  residency is what makes the `pre_sci` counts above sound: each was read out of the module that
  actually answers the ordinal, not out of a same-named symbol in the other one.

**Measured instead** (Warp Server for e-business, 2026-08-26, an 8.3-only bit-clear 16-bit NE
module; capture retained project-side) [OBS]:

| call | `ulReserved` | path | result |
|---|---|---|---|
| `DosDelete` | 0 | nonexistent | 2 `ERROR_FILE_NOT_FOUND` |
| `DosDelete` | 1 | **same** nonexistent path | **87 `ERROR_INVALID_PARAMETER`** |
| `DosDelete` | `0xFFFFFFFF` | **same** nonexistent path | **87** |
| `DosDelete` | `0x00010000` (high word only) | **same** nonexistent path | **87** |
| `DosDelete` | 1 | existing file | 87, and the file is **still there** afterwards |
| `DosMove` | 0 | nonexistent source | 2 |
| `DosMove` | 1 | **same** nonexistent source | **87** |
| `DosMove` | `0xFFFFFFFF` | **same** nonexistent source | **87** |
| `DosMove` | `0x00010000` (high word only) | **same** nonexistent source | **87** |
| `DosMove` | 1 | existing source | 87; the source is **still there** and the destination was **never created** |
| `DosSetFileMode` | 0 | nonexistent | 2 `ERROR_FILE_NOT_FOUND` |
| `DosSetFileMode` | 1 | **same** nonexistent path | **87** |
| `DosSetFileMode` | `0xFFFFFFFF` | **same** nonexistent path | **87** |
| `DosSetFileMode` | `0x00010000` (high word only) | **same** nonexistent path | **87** |
| `DosSetFileMode` | 1 | existing file, `usAttr = FILE_NORMAL` | 87, and the file's attribute is **unchanged** (still `0x22`) |
| `DosForceDelete` | 0 | nonexistent | 2 |
| `DosForceDelete` | 1 | **same** nonexistent path | **87** |
| `DosForceDelete` | `0xFFFFFFFF` | **same** nonexistent path | **87** |
| `DosForceDelete` | `0x00010000` (high word only) | **same** nonexistent path | **87** |
| `DosForceDelete` | 1 | existing file | 87, and the file is **still there** afterwards |

The ordinal-84 and ordinal-203 rows were added 2026-08-27 from a second full capture of the same
probe. Each was measured **for itself**: a sibling licenses nothing, which is the same standard
that had all three of the directory family measured rather than two inferred from one. Every
ordinal-84 case passes `usAttr = FILE_NORMAL` (0x0000) and never `0x08`/`0x10`, so the
volume-label/subdirectory 87 documented above is excluded by construction rather than by
argument.

All four ordinals therefore validate the word `[OBS]`, and the reserved rejection **takes
precedence over the path outcome** `[OBS]` - the same path answers 2 with `ulReserved = 0` and 87 with
`ulReserved = 1`, so the word is read and its answer wins.

**A FIFTH ORDINAL, added 2026-08-30 (Rule 1.7 - the "all four" above is kept because it is what
had been measured when it was written): `DosQFileMode`, ordinal 75, behaves the same way** `[OBS]`
(Warp 4.50; capture retained project-side). It is 16-bit-only -
`USHORT APIENTRY DosQFileMode(PSZ, PUSHORT, ULONG)` [DOC-IBM
Open Watcom 1.9 `h/os21x/bsedos.h:343`], with no 32-bit counterpart in the Warp-4.5 Toolkit - and
it is a **query**, so it is the first member of this set for which the "a rejected call has no
effect" half can be observed on the *out-parameter* rather than on the filesystem:

| call | `ulReserved` | path | result |
|---|---|---|---|
| `DosQFileMode` | 0 | `\OS2` (an existing directory) | 0, `usAttr` = `0x0010` |
| `DosQFileMode` | 1 | **same** existing directory | **87**, and `usAttr` is **left untouched** (a preloaded `0xFFFF` sentinel survives) |
| `DosQFileMode` | 0 | `""` (the empty path) | 3 `ERROR_PATH_NOT_FOUND` |
| `DosQFileMode` | 1 | **same** empty path | **87** - the reserved rejection wins over the path rejection |

The untouched sentinel is worth its line: on `rc = 2`/`rc = 3` the same machine **overwrites** the
caller's word (`0x0004`, `0x0003`, `0x0017` on three different calls - leftover stack, not a
contract), so "reserved rejected => out-parameter not written" is a real, separable observation and
not merely the absence of a filesystem change. Only `ulReserved = 1` was exercised on this ordinal;
the `0xFFFFFFFF` and `0x00010000` cases that establish "the whole 32-bit word" for ordinals
60/67/84/203 were **not** measured here, so that narrower claim does not carry to ordinal 75 -
a sibling licenses nothing, in this direction too.

**And the negative result above needed repairing a third time.** section 6.1 records that the CP Guide,
the Toolkit and the DDK say nothing about this parameter, and that `$OS2_EDM2/os2books/prcp/` -
the 16-bit CP Reference - says *"Reserved must be set to zero"* for ordinals 60/67/84. It says the
same for ordinal 75 [DOC-IBM `$OS2_EDM2/os2books/prcp/112_L2_DosQFileMode.html`], and that page
also publishes the ordinal's **return-code list**: 2, 3, 26, **87**, 108, 206. So 87 is a
documented outcome of this call, the requirement is documented, and *what happens when you violate
it* is still documented nowhere - the rejection stays `[OBS]`, explained rather than transcribed.
`prcp` is the edition to search first for anything 16-bit-only.

**That the word is checked *before* the path is resolved is `[INF]`, not `[OBS]`, and the
distinction is worth keeping.** A capture can only show which answer comes out, never in which
order the kernel computed the two. "Reserved checked first, path never resolved" and "path
resolved, then reserved checked, and 87 overrides" produce identical output on every case here,
and no case in this capture can separate them. Ordering is stated as an inference from the
precedence; an implementation that validates first is *compatible* with the measurement, not
proven by it. (The same caution applies to section 11's ordering claim for the `NEWFILES` leaf filter,
which rests on the same shape of evidence.)

**The check covers the whole 32-bit word, not a masked part of it** `[OBS]`: `0x00010000` sets
no bit in the low word and is still rejected, so an implementation may test `ulReserved != 0`
rather than any narrower predicate. A rejected call has no effect, and for `DosMove` that was
checked at both ends - the source survives *and* the destination is not created, so the refusal
is not a copy. This is the same behaviour the directory family (`DosMkDir` 66, `DosMkDir2` 185,
`DosRmDir` 80) was separately measured to have, but it is established here by measuring these
two rather than inferred from those: a sibling's behaviour licenses nothing.

Four further results from the same capture [OBS]:

- `DosDelete` of a **read-only file** is **refused with 5 `ERROR_ACCESS_DENIED`**, and the file
  survives. section 6's first bullet above already asserted this refusal and named the code from the
  function's documented return list; the measurement is what turns that pairing from a
  reasonable reading of two separate statements into an observation. It confirms the CP
  Reference's Note - *"Read-only files cannot be deleted by DosDelete. To delete a read-only
  file, you must first issue DosSetFileInfo to change the file's read-only attribute to zero,
  then delete the file"* [DOC-IBM `cpgref` DosDelete Notes] - and supplies the return code,
  which that Note does not state (5 is in the function's documented return list, but the Note
  does not say the refusal uses it). Clearing the attribute with `DosSetFileMode` and re-issuing
  the delete then succeeds, i.e. the documented workaround is the real one. In the same capture
  the file's attribute reads back as `0x21` = 33 decimal, the value the capture prints
  (`FILE_READONLY | FILE_ARCHIVED`) - a newly created file carries the archive bit.
- `DosDelete` on a **directory** answers **5 `ERROR_ACCESS_DENIED`**. The CP Reference's Notes say
  only that the call "cannot be used to delete directories".
- `DosMove` onto an **existing target** is **refused with 5 `ERROR_ACCESS_DENIED`**, and the
  source is left in place - the move does not happen. The CP Reference's Notes mention only that
  read-only files in the target path "are not replaced".
- `DosMove` of a **directory** succeeds (0), matching the Reference's "a file or subdirectory".

Two more from the 2026-08-27 capture, both about the attribute word and neither previously
recorded here [OBS]:

- A file created HIDDEN through `DosOpen`'s `usAttribute` reads back as **`0x22`**
  (`FILE_HIDDEN | FILE_ARCHIVED`) - the archive bit is set on a fresh file whether or not the
  caller asked for it, the same behaviour section 3.1 already records for a `FILE_READONLY` create
  (`0x21`).
- `DosSetFileMode(..., FILE_NORMAL, 0)` on that file leaves it reading **`0x00`**, not `0x20`.
  So the call **replaces** the attribute word rather than merging into it, and the archive bit is
  replaced with the rest. A caller that wants to preserve archive must ask for it explicitly.

### 6.2 The 32-bit forms, measured directly, and the dispatch they share [OBS]

Everything in section 6.1 was measured through the **16-bit** entry points. The 32-bit forms
(`DosDelete` 259, `DosMove` 271, `DosForceDelete` 110) were measured separately on 2026-08-27 -
same machine, **HPFS boot volume**, capture retained project-side -
because a sibling's behaviour licenses nothing and the two widths have been measured to differ
elsewhere in this family.

**The FSD is where the policy lives, which is why the volume type is recorded.** `DosDelete`
dispatches to **`FS_DELETE` at FS_ENTRY `+0x1C`** and `DosMove` to **`FS_MOVE` at `+0x60`**
[OBS-RE `debugging_handbook.txt:13442,13486`], so these are the *file system driver's* answers,
not the kernel's, and an rc from one FSD is not automatically an rc from another. There is **no
`FS_FORCEDELETE` entry point and no `GDT_DOSFORCEDELETE` call gate** [OBS-RE
`debugging_handbook.txt:18749,18775`], so `DosForceDelete` necessarily reaches the FSD through
`FS_DELETE` and *cannot* carry a different attribute policy.

| behaviour | 32-bit result |
|---|---|
| `DosDelete` of a **read-only** file | **5**, file survives - same as the 16-bit form |
| `DosDelete` of a **hidden** file (`attr=0x22`) | **0**, deleted |
| `DosDelete` of a **system** file (`attr=0x24`) | **0**, deleted |
| `DosDelete` of a **hidden+system** file (`attr=0x26`) | **0**, deleted |
| `DosDelete` of a nonexistent 8.3 name | **2** - same as the 16-bit form |
| `DosForceDelete` of a plain file | **0** |
| `DosForceDelete` of a **read-only** file | **5**, file survives |
| `DosForceDelete` of a hidden+system file | **0**, deleted |
| `DosMove` file -> existing **file** | **5**, source in place |
| `DosMove` file -> existing **read-only** file | **5**; target neither replaced nor stripped (still `attr=0x21`) |
| `DosMove` file -> existing **directory** | **5**, source in place |
| `DosMove` directory -> existing **directory** | **5**, source in place |
| `DosMove` directory -> existing **file** | **5**, source in place |
| `DosMove("file.txt","File.Txt")` - case change | **0** |
| `DosMove(A, A)` - identical spelling | **0**, file survives |

Four things follow that no single row states:

- **HIDDEN and SYSTEM do not block deletion.** This is the measurement behind
  [DOC-IBM `cpgref.txt:32220`]: *"A read-only file cannot be opened for writing, nor can it be
  deleted. A hidden file (or directory) cannot be displayed by using an ordinary directory
  listing. A system file is excluded from normal directory searches."* IBM scopes hidden and
  system to listing **visibility**, and the HPFS FSD's own `DELETE` tests only bits `0x10`
  (directory) and `0x01` (read-only), never `0x02` or `0x04` [OBS-RE]. Contrast `DosDeleteDir`,
  which *does* refuse a directory containing hidden entries (`cpgref:3522`, `:32208`) - a
  different call.
- **`DosForceDelete` is NOT the documented way past the read-only refusal.** Its Notes
  (`cpgref:6119-6127`) are the same four paragraphs as `DosDelete`'s (`:3439-3447`) with exactly
  one substituted: the read-only clause is word-identical but for the function name, and the
  **sole** difference is that a `DosForceDelete`-d file cannot be recovered by UNDELETE. IBM's own
  sample (`cp1.txt:9636-9691`) clears the attribute with `DosSetFileInfo` **before** calling it.
- **The existing-target refusal is one rule and does not depend on either operand's kind** -
  five combinations, one answer. And no IBM prose on the measuring system states that outcome at all:
  `80 ERROR_FILE_EXISTS` and `183 ERROR_ALREADY_EXISTS` are **absent from `DosMove`'s documented
  return list in every edition** (`cpgref:8263-8277` gives 0, 2, 3, **5**, 17, 26, 32, 36, 87,
  108, 206, 250, 251), leaving the generic 5 as the only available code. Negative result
  recorded so the search is not repeated.
- **A same-object move is exempt from that refusal.** [DOC-IBM `cpgref.txt:8293-8295`] documents
  `DosMove("file.txt","File.Txt")` as the supported way to change a file's case on an
  FSD-controlled drive, and it answers 0; so does an exact self-move, which is documented
  nowhere. Any implementation of the refusal has to distinguish "the destination exists" from
  "the destination *is* the source", and on a case-insensitive resolver that distinction cannot
  be made by comparing the two path strings.

### 6.3 `\OS2\OS2.INI` and `\OS2\OS2SYS.INI` are read-only [OBS]

Both report `attrFile = 0x25` = `FILE_READONLY | FILE_SYSTEM | FILE_ARCHIVED` (2026-08-27, same
capture, `INI-os2ini-attr` / `INI-os2sysini-attr`). Independently corroborates the same pair
being recorded elsewhere in this document as Archive+System+Read-only.

Worth stating because of what it implies together with section 6.2: the shell rewrites both files during
bring-up, and a read-only file cannot be deleted or moved onto. So the shell must be clearing the
attribute first - IBM's own documented workaround (`cpgref:3443`) - rather than the files being
writable in practice.

---

### 6.4 `DosMove`'s refusals, and which layer owns each [OBS] + [OBS-RE] + [DOC-IBM]

`DosMove`'s documented return list is `0 2 3 5 17 26 32 36 87 108 206 250 251`
[DOC-IBM `cpgref.txt` "Return Value - rc", DosMove]. Its Notes state four rules,
and each was measured on real OS/2 (Warp Server for e-business 4.50, HPFS boot
volume, 2026-09-18; capture retained project-side) [OBS]:

| IBM's sentence | measured |
|---|---|
| "Global file-name characters are not allowed in the source or target name." | **3** for a wildcard in EITHER name, source untouched. Not 2 - a missing plain file is 2, so the wildcard code is distinct from the not-found code. Not expanded either: a real file matching the pattern did not move. |
| "If a drive is specified for the target, it must be the same as the one specified or implied by the source." | **17 `ERROR_NOT_SAME_DEVICE`** when the target names a DIFFERENT, EXISTING drive; **3** when it names a drive that does not exist. |
| "Any attempts to move a parent subdirectory to one of its descendant subdirectories will be rejected..." | **250 `ERROR_CIRCULARITY_REQUESTED`** |
| "Any attempts to move the current subdirectory or any of its ancestors ... will be rejected." | **251 `ERROR_DIRECTORY_IN_CDS`** |

Plus one the Notes do not mention: a source with **any** open handle answers
**32 `ERROR_SHARING_VIOLATION`**, measured with the only handle opened
`OPEN_SHARE_DENYNONE` [OBS]. So this is not deny-mode arbitration - a
`DENYNONE` handle permits every ordinary open and still refuses the move.

**THE DRIVE COMPARISON HAPPENS BEFORE THE TARGET PATH IS RESOLVED** [OBS]. A
target of `D:\<a directory that does not exist>\file` answers **17**, not a
not-found code, when D: is a valid drive. So the rule is about the drive
letters and not about whether the rest of the target resolves.

**IBM'S TWO EDITIONS DISAGREE ABOUT THE CIRCULARITY CODE, AND `cp1` IS WRONG.**
`cpgref`'s Notes say only "will be rejected". `cp1`'s Remarks says the same
case gives *"error code 251 (ERROR_DIRECTORY_IN_CDS)"* [DOC-IBM
`cp1.txt` "DosMove - Remarks"]. Both books list 250 and 251 in the return list,
so the prose is the only thing that distinguishes them - and only one of the two
books commits. The measurement above gives 250 for the circularity case and 251
for the current-directory case, i.e. `cpgref` is silent-and-right and `cp1` is
specific-and-wrong. Cite `cpgref` for this, never `cp1`.

#### These refusals belong to the KERNEL, not to the file system [OBS-RE]

Read out of a shipped `os2krnl` (object 10, USE16; disassembled and read
instruction by instruction):

- `h_FSD_Move` calls, in this order, `ShCloseFile`, then **`Ren_Check`**, then
  **`AddShare`**, and only then dispatches the FSD's own `FS_MOVE` through an
  indirect call on the file-system entry table.
- `Ren_Check` is 98 bytes and carries exactly three reachable answers -
  `mov ax,0xfa` (250), `mov ax,0xfb` (251) and `mov ax,0x5` - with the
  circularity test evaluated before the CDS test. A fourth constant,
  `mov ax,0x20` (32), sits in its body and is **unreachable from the entry** in
  the build read: the only branch to it is a `jnz` that cannot be taken. A
  decompiler drops it with an "unreachable block" warning, which is how it
  disappears from a reading that stops at the decompile.
- `AddShare` is therefore what produces the 32, and it runs after `Ren_Check`.

**Consequence for a reimplementation:** 250, 251 and 32 are owed on every
volume, whatever file system is underneath. A hosted FSD would never supply
them - what the FSD supplies is the rename itself. HPFS's `FS_MOVE` cracks both
paths and calls its own internal `MOVE`; its extended attributes ride along
because the object's on-disk structure does not move.

**What was read, and what was not** - because a citation covers exactly what
was read: `h_FSD_Move`'s first 40 instructions, and the whole of `Ren_Check`.
NOT followed: `ShCloseFile`, `AddShare`, `g_PrefLookupMFT`, `PathPref`,
`ScanCDS`. So the call order and the three constants are in the bytes; what
each of those helpers computes is not, and nothing above claims it.

### 6.5 Extended attributes follow a moved object [OBS]

**No edition documents this.** `DosCopy`'s page describes EA copying at length
and gives it a flag (`DCPY_FAILEAS`); `DosMove`'s page does not mention
extended attributes at all. It is therefore a measurement, taken in both
directions - present at the new name AND gone from the old one - in the three
shapes that are different mechanisms on a real FSD (Warp Server for e-business
4.50, HPFS, 2026-09-18) [OBS]:

| shape | result |
|---|---|
| same-directory rename | value byte-identical at the new name; the old name no longer exists |
| cross-directory move, same volume | value byte-identical at the new name |
| a file INSIDE a moved DIRECTORY | value byte-identical at the file's new path |

The third is the one worth noting: `DosMove` was never given that file's name.
On a real FSD all three are free, because the EAs hang off an on-disk structure
the rename does not touch. **A reimplementation that keys extended attributes on
the PATH owes work in all three cases, and work on objects the call does not
name in the third.**


## 6a. Name helpers - `DosEditName` and `DosSearchPath`

```c
APIRET APIENTRY DosEditName(ULONG metalevel, PSZ pszSource, PSZ pszEdit,
                            PBYTE pszTarget, ULONG cbTarget);
APIRET APIENTRY DosSearchPath(ULONG flag, PSZ pszPathOrName, PSZ pszFilename,
                              PBYTE pBuf, ULONG cbBuf);
```
[DOC-IBM `bsedos.h:1684,2630`; `flag` bits `SEARCH_CUR_DIRECTORY` 1, `SEARCH_ENVIRONMENT` 2,
`SEARCH_IGNORENETERRS` 4, `bsedos.h:728-731`]

### `DosEditName` - what the case of the result depends on

`DosEditName` applies a wildcard edit string to a name (`foo.bar` + `*.baz` gives `foo.baz`).
IBM's own page shows it both upper-casing the result and preserving case (`file.txt` + `*E.TMP`
giving `filE.TMP`) without saying which caller gets which [DOC-IBM `cp1.txt`, "DosEditName"].

**The caller's module decides.** A 16-bit NE program **without** the long-filename bit
(`NELONGNAMES`, set by the linker's `NEWFILES` option; see `executable-formats.md`) gets the
result upper-cased (`FOO.BAZ`, `FILE.TMP`); the same source linked **with** the bit gets case
preserved (`foo.baz`, `filE.TMP`). Nothing else changed between the two builds: every return code
was identical, and every one of the 21 differing outputs was exactly the upper-cased form. A 32-bit
LX caller gets case preserved, whether it calls the 32-bit entry point or reaches the 16-bit one
[OBS - measured on Warp Server for e-business 4.50, kernel revision 14.089: one 16-bit source
linked twice, plus a 32-bit probe calling both entry points]. **The tell:** the same rename
logic producing upper-case names in an old 16-bit tool and mixed case everywhere else.

Measured edit rules and return codes (32-bit caller, source `foo.bar` unless shown):

| Edit string, or input | Result |
|---|---|
| `*.*`, or `*` | `foo.bar` (unchanged) |
| `?.???` | `f.bar` - `?` copies one character |
| `?????` on source `ab` | `ab` - `?` past the end of the source adds nothing |
| `.baz` | `.baz` |
| `*.bak` on a source with no dot (`foo`) | `foo.bak` |
| `xyz` (no wildcards) | `xyz` |
| `""` | `""` |
| `*.baz   ` (trailing blanks) | `foo.baz` - trailing blanks dropped |
| `*.baz...` or `*.baz.` | `foo.baz.` - trailing dots collapse to one |
| `metalevel` 0 or 2 | 87 - only level 1 is accepted |
| `cbTarget` too small for the result plus its NUL (7 for a 7-character result), or 0 | **111** `ERROR_BUFFER_OVERFLOW` - IBM's list is 0, 87 and 123 only |
| a drive, `\` or `/` in the source or the edit string | 123 `ERROR_INVALID_NAME` - names, not paths |
| a `:` that is not the second character (`fo:o.bar`) | 0 - accepted |
| an edit string of 259 characters / of 260 | 0 / 3 |

### `DosSearchPath` - measured behaviour

[OBS - measured on Warp Server for e-business 4.50, 32-bit probe; results as found on disk]

- Results are always fully qualified, even for a relative path element or the current directory,
  and spelled with `\` even when the path was written with `/`. The first matching element wins.
  A double-quoted element (`"X:\A;B"`) is one element, `;` included. An unterminated quote finds
  nothing (2).
- `flag` 2 (`SEARCH_ENVIRONMENT`) with an unset variable returns 203; undefined flag bits (8) and
  `cbBuf` of 0x10000 return 87; `cbBuf` 0 returns 111 and leaves the buffer untouched.
- **An unassigned drive does not end the search.** `Q:\;C:\OS2` (Q unassigned) still finds the
  file in `C:\OS2` - with and without `SEARCH_IGNORENETERRS`.
- **A buffer one byte too short does not give 111.** When the found name fits but its NUL does
  not, the element is skipped and the call returns **2**; 111 comes only when the buffer is too
  small to build the candidate name at all.
- **Empty elements depend on position:** a leading empty element (`;C:\NOSUCH`) and an empty
  element after a relative one (`SUBX;;...`) search the current directory; an empty element after
  an absolute one (`C:\OS2;;C:\NOSUCH`) and a trailing one (`C:\NOSUCH;;`, `C:\OS2;`) do not.
- `.` and `..` components are resolved (`X:\OS2\SYSTEM\..`); with a lower-case element (`x:\os2`)
  only the drive letter is upper-cased in the result.
- Directories and hidden files are found; a wildcard name is returned as written (`SPF*.TXT`).

## 7. Metadata - `DosQueryFileInfo` / `DosSetFileInfo`

`DosQueryFileInfo(hf, ulInfoLevel, pInfo, cbInfoBuf)` fills `pInfo` with a `FILESTATUS*` record for
an open handle; `DosSetFileInfo` writes timestamps/attributes (and, at higher levels, the EA set)
back. `DosQueryPathInfo` is the by-path equivalent that needs no open handle. [DOC-IBM
`bsedos.h:1739,1750,1762`]

### 7.1 Info levels [DOC-IBM `bsedos.h:742-746` (FIL_* values); struct shapes from the `FILESTATUS*` definitions]

| Constant | Value | Record | Purpose |
|---|---|---|---|
| `FIL_STANDARD` | `1` | `FILESTATUS` | Standard date/time/size/attr |
| `FIL_QUERYEASIZE` | `2` | `FILESTATUS2` | Standard info + total EA-set size |
| `FIL_QUERYEASFROMLIST` | `3` | - | Return specific EAs named in a `GEA` list |
| `FIL_QUERYFULLNAME` | `5` | - | Fully-qualified name (`Dos*PathInfo` only) |
| `FIL_STANDARDL` | `11` | `FILESTATUS3L` | Large-file standard info |
| `FIL_QUERYEASIZEL` | `12` | `FILESTATUS4L` | Large-file info + EA-set size |
| `FIL_QUERYEASFROMLISTL` | `13` | - | Large-file, specific EAs |

### 7.2 `FILESTATUS` records [DOC-IBM `bsedos.h:1373-1461`]

`FILESTATUS` (level 1) - the base record all others extend:

| Field | Type |
|---|---|
| `fdateCreation` / `ftimeCreation` | `FDATE` / `FTIME` |
| `fdateLastAccess` / `ftimeLastAccess` | `FDATE` / `FTIME` |
| `fdateLastWrite` / `ftimeLastWrite` | `FDATE` / `FTIME` |
| `cbFile` | `ULONG` (logical size) |
| `cbFileAlloc` | `ULONG` (allocated size) |
| `attrFile` | `USHORT` |

- `FILESTATUS2` = `FILESTATUS` + `ULONG cbList` (EA-set size), level 2.
- `FILESTATUS3` = same fields but `attrFile` **widened to `ULONG`** (level 1 form used by the
  32-bit query path).
- `FILESTATUS4` = `FILESTATUS3` + `ULONG cbList`.
- `FILESTATUS3L` / `FILESTATUS4L` widen `cbFile` / `cbFileAlloc` to `LONGLONG` for large files.

### 7.2a Which record each width returns, and which levels the query accepts [OBS]

section 7.1's table gives the level constants; it does not say that the same level returns a
**different record to each ABI width**, which it does for levels 1 and 2 - the same split section 5.1
records for the find family. Measured on a running OS/2 4.50 Warp Server for e-business
(Convenience Package, kernel Internal revision 14.089, `C:` HPFS), 2026-09-04, by filling the
buffer with a sentinel byte and counting how many bytes the call left changed:

| Level | 16-bit `DosQFileInfo` | 32-bit `DosQueryFileInfo` |
|---|---|---|
| 1 `FIL_STANDARD` | `FILESTATUS`, **22** bytes | `FILESTATUS3`, **24** bytes |
| 2 `FIL_QUERYEASIZE` | `FILESTATUS2`, **26** bytes | `FILESTATUS4`, **28** bytes |
| 11 `FIL_STANDARDL` | `FILESTATUS3L`, **32** bytes | `FILESTATUS3L` |
| 12 `FIL_QUERYEASIZEL` | `FILESTATUS4L`, **36** bytes | `FILESTATUS4L` |

At level 1 the 16-bit call leaves the two bytes at +22 **untouched** (still the sentinel) where
the 32-bit call zeroes them - those two bytes are the widened half of `attrFile`. So handing a
16-bit caller's buffer to the 32-bit entry point does not merely mis-place a field, it writes
two bytes past the end of the record that caller declared.

The large-file levels are the same record in both widths; only levels 1 and 2 narrow.

**Levels 3, 4, 5 and 13 dereference the caller's buffer as an `EAOP` and trap if it is not
one.** `[OBS]` Called from a 16-bit program with a buffer that is not a well-formed `EAOP`,
each of those four killed the process outright - `SYS1811 ... trap number 000D`, a #GP - rather
than returning an error. Each level was run in its **own process**, one per invocation, and the
capture was retained; a level that traps prints nothing after its announcement, and that silence
is the result. That is consistent with the documented contract (level 3's `pInfo` is
an `EAOP` whose `fpGEAList` is a far pointer the system follows, section 7.1) and with there being no
validation of it. A probe that sweeps info levels must therefore run **one level per
invocation**, or a single trapping level destroys every result after it.

**The levels that answer, rather than trapping**, on the 16-bit query:

| Level | Answer |
|---|---|
| 0 | `124` ERROR_INVALID_LEVEL |
| 6 | `50` ERROR_NOT_SUPPORTED |
| 99 | `124` ERROR_INVALID_LEVEL |

Level 6 is the one worth noting: it is outside the documented set in the same way 0 and 99 are,
and it does **not** get the same code.

**Minimum `cbInfoBuf` at level 1 is 22 - the size of the SIXTEEN-BIT record**, not of the
record being filled. `[OBS]` `cb` of 0 and 21 both answer `111` ERROR_BUFFER_OVERFLOW; 22, 24
and 64 all succeed and all write 22 bytes. The 32-bit entry point accepts `cb` = 22 as well and
writes **24**, i.e. past what the caller declared.

### 7.3 `DosSetFileInfo` at level 1: the two ABI widths are DIFFERENT FUNCTIONS [OBS] [OBS-RE]

The `Set` side is not the `Query` side narrowed, and the 16-bit form is not the 32-bit form with
smaller parameters. Measured on a Warp Server for e-business system (Warp Server for e-business, internal revision
`14.097_UNI`, HPFS `C:`), 2026-08-31, both widths against one another on the same file and the same
volume:

| | 16-bit `DosSetFileInfo` | 32-bit `DosSetFileInfo` |
|---|---|---|
| prototype | `USHORT (HFILE, USHORT, PBYTE, USHORT)` `[DOC-IBM os21x/bsedos.h:354; prcp "DosSetFileInfo"]` | `APIRET (HFILE, ULONG, PVOID, ULONG)` `[DOC-IBM bsedos.h:1750]` |
| level-1 record | `FILESTATUS`, 22 bytes, `USHORT attrFile` at +20 `[DOC-IBM prcp: "fileattrib (USHORT)"]` | `FILESTATUS3`, `ULONG attrFile` at +20 `[DOC-IBM cpgref "Level 1 File Information"]` |
| minimum `cbInfoBuf`, level 1 | **12**; below it `122 ERROR_INSUFFICIENT_BUFFER` | **22** (`0x16`); below it `122` |
| minimum `cbInfoBuf`, level 11 | not measured | **32** (`0x20`) |
| `attrFile` | **ignored** - not validated (`0x8000` returns 0) and not applied (`FILE_READONLY` does not appear on readback) | validated against `~0x37` -> `87`, then applied |
| every level other than 1, 2, 11, 12 | `124 ERROR_INVALID_LEVEL` | `124` |
| level 11 | accepted - but `prcp` says "a value of 1 or 2 can be specified", so this is measured-only | accepted |
| NULL `pInfoBuf` | **GP-faults the kernel and stops the machine** | the process faults |

**The single-variable control that establishes the `attrFile` row**: the same file, the same HPFS
volume, the same `OPEN_ACCESS_READWRITE | OPEN_SHARE_DENYREADWRITE` open, minutes apart, with only
the ABI width different - the 32-bit arm reads back `attrFile = 0x21` after setting `FILE_READONLY`
and the 16-bit arm reads back `0x20`. A filesystem or sharing-mode refusal cannot explain a
difference the other arm does not show.

**Why**, from IBM's own binaries:

- The 16-bit kernel worker copies six words of date/time out of the caller's buffer, zeroes the two
  size fields, and takes the attribute **from the SFT** rather than from the caller -
  `local_12e = *(byte *)(SFT + 0x78)` - then sets the record length to `0x16`. Its own guard is
  `if (cb < 0xc) return 0x7a`. `[OBS-RE os2krnld_uni_astrict SFT_SetFileInfo @ 000e:5c51]`
- The 32-bit entry point is itself a marshalling shim: it reads `attrFile` as a `ULONG` at `+0x14`,
  rejects `attr & 0xffffffc8` with `0x57`, then **narrows the field to its low word in the caller's
  own buffer**, delegates, and restores the caller's dword afterwards.
  `[OBS-RE DOSCALL1 DOS32SETFILEINFO @ 1c028b10]`
- The size and level rules are literal in the layer below it:
  `uVar2 = 0x20; if ((level == 0xb) || (uVar2 = 0x16, level == 1)) if (cb < uVar2) return 0x7a;`
  then `if (level != 0xc && level != 2) return 0x7c;`.
  `[OBS-RE DOSCALL1 DOS32PSETFILEINFO @ 1c0254c4]`

So the record the kernel actually consumes is the **22-byte, `USHORT`-`attrFile`** one on both
widths. `FILESTATUS3` exists at the 32-bit boundary and nowhere below it.

**`FILE_DIRECTORY` is inside the mask and still refused.** `0x10 & 0xffffffc8 == 0`, so it passes
`DOS32SETFILEINFO`'s test, yet setting it on a plain file answers `87`. The refusal is below the
mask, not in it - the mask really is `0x37`.

### 7.4 Date and time validation is a FIELD-RANGE check, not a calendar check [OBS]

Identical on both widths, swept field by field rather than generalised from one out-of-range value:

| input | result |
|---|---|
| month `0`, month `13`, day `0` | `87 ERROR_INVALID_PARAMETER` |
| hour `24`, minute `60` | `87` |
| **day `31` of a 30-day month** | **accepted**, and normalised - 1995-06-31 reads back as 1995-07-01 |
| **`twosecs` = 30 (i.e. 60 seconds)** | **accepted**, and normalised - 12:34:60 reads back as 12:35:00 |

`twosecs` is not range-checked at all. Note that "these cannot denote a real date, so they must be
rejected" predicts the wrong answer for the last two rows.

**A zero date/time PAIR means "leave unchanged"** `[DOC-IBM cpgref "Notes - DosSetFileInfo"]`, and
both editions add that if *either* member is non-zero "both attributes of the file are set to the new
values". The second half is not what the machine does:

| input | result |
|---|---|
| date `0`, time `0` | nothing changes |
| date set, time `0` | both written; the time becomes `00:00` |
| **date `0`, time set** | **the existing date is KEPT** and only the time is written |

### 7.4a The three checks run in a fixed order, three layers deep [OBS] [OBS-RE]

Measured with cases that cross two axes at once - a single-axis sweep cannot
observe precedence at all:

| input | result |
|---|---|
| illegal `attrFile` + `cbInfoBuf` = 12 | `87` - the attribute mask beats the size check |
| illegal `attrFile` + `cbInfoBuf` = 0 | `87` - even at zero |
| out-of-range date + `cbInfoBuf` = 12 | `122` - but the size check beats the date |

So the order is **`attrFile` mask -> `cbInfoBuf` -> date/time**, and that is
exactly where the three checks live in IBM's own layering: the mask in
`DOS32SET*INFO`, the size in `DOS32PSET*INFO`, and the date validation below
both. Note the consequence for the mask: it is applied to `attrFile` at `+0x14`
(or `+0x1c` at level 11) **before the buffer size has been validated**, so a
caller passing `cbInfoBuf` = 12 still has that dword read.

The 16-bit form has only two of the three, in the same relative order -
`cbInfoBuf` -> date - because it never consults `attrFile` at all (section 7.3).

### 7.4b `DosSetPathInfo` shares all of it [OBS] [OBS-RE]

The by-path setter is not a separate contract. Measured independently of the
handle form rather than inferred from it: level-1 minimum **22** answering
`122`, levels 1/2/11 accepted and every other level `124`, the same `~0x37`
mask answering `87`, `FILE_DIRECTORY` on a plain file refused with `87`, the
same date-domain rules, and the same attr-mask-before-size precedence.

IBM's binaries say the same independently - `DOS32SETPATHINFO` is structurally
identical to `DOS32SETFILEINFO`, and `DOS32PSETPATHINFO` carries the same
`0x20 / 0x16 / 0x7a / 0x7c` table as its handle-form counterpart.

The one thing it cannot share is the **write-access** requirement of section 7.5: an
open mode is a property of a handle, and this entry point has none.

**An empty path is not the drive root.** `DosSetPathInfo("", 1, ...)` answers
`2 ERROR_FILE_NOT_FOUND` and modifies nothing.

### 7.5 What `DosSetFileInfo` requires of the handle [OBS]

- **Write access, and nothing about sharing.** A handle opened `OPEN_ACCESS_READONLY` answers
  `5 ERROR_ACCESS_DENIED` whatever its share mode; every mode carrying write access succeeds
  whatever its share mode, including `OPEN_SHARE_DENYWRITE | OPEN_ACCESS_WRITEONLY`. IBM's note that
  the call "is successful only when the file is opened for write access, and access by other
  processes is prevented by a deny-both sharing mode" - `[DOC-IBM cpgref "Notes - DosSetFileInfo"]`
  for the 32-bit form and `prcp` "DosSetFileInfo" Remarks in the same words for the 16-bit one -
  does not describe the shipped behaviour: read strictly it forbids a case that demonstrably works.
- **The handle must be a disk file.** A handle to a character device - `DosOpen("\DEV\NUL")` - is
  refused with `6 ERROR_INVALID_HANDLE`, as are a never-opened handle and a closed one. (IBM
  documents `130 ERROR_DIRECT_ACCESS_HANDLE` for this API as well; only the character-device case
  was measured.)

### 7.6 `DosQueryPathInfo` at level 5 (`FIL_QUERYFULLNAME`) [DOC-IBM] [OBS]

`[DOC-IBM cp1 "DosQueryPathInfo - Parameter pInfoBuf"]`: "Level 5 returns the fully qualified ASCIIZ name of
pszPathName in pInfoBuf. pszPathName may contain global file-name characters." The rest is `[OBS]`: Warp Server
for e-business 4.50 (revision 14.089), HPFS boot drive C:, 2026-10-16, a 32-bit probe with the current drive C:
and its current directory set to `C:\OS2`, each name passed to `DosQueryPathInfo(name, 5, buf, 300)`:

| name | rc | result |
|---|---|---|
| `foo.txt`, `Foo.Txt` | 0 | `C:\OS2\foo.txt`, `C:\OS2\Foo.Txt` |
| `c:foo` | 0 | `C:\OS2\foo` |
| `SYSTEM\oso001.msg` | 0 | `C:\OS2\SYSTEM\oso001.msg` |
| `..\x` | 0 | `C:\x` |
| `..\..\..\x`, `\a\..\..\b` | 3 | - |
| `C:\OS2\`, `c:\os2\system\` (a trailing `\`) | 3 | - |
| `c:/os2/../Dll` | 0 | `C:\Dll` |
| `c:\os2\.\dll\.` | 0 | `C:\os2\dll` |
| `C:\NOSUCHDIR\X` | 0 | `C:\NOSUCHDIR\X` |
| `*.EXE`, `c:\os2\*.?xe` | 0 | `C:\OS2\*.EXE`, `C:\os2\*.?xe` |
| `.`, `..` | 0 | `C:\OS2`, `C:\` |
| `c:\` | 0 | `C:\` |
| `C:` | 2 | - |
| `` (empty) | 2 | - |
| `q:\x`, `q:x` (no such drive) | 15 | - |
| `\\srv\share\x` (no redirector) | 3 | - |
| `a\\b` | 0 | `C:\OS2\a\b` |
| `con` | 0 | `\DEV\CON` |
| `x.` | 0 | `C:\OS2\x` |
| `foo.txt` into a 4-byte buffer | 111 | - |

What this establishes:
- **Nothing need exist** (`C:\NOSUCHDIR\X`), and global characters pass through unchanged.
- **The drive letter is upper-cased; every other character keeps the case it was given** - the typed name's, and
  the current directory's as it was set (`C:\OS2`, set in upper case, beside a typed `c:\os2\...`).
- `/` is a separator, a doubled separator collapses, `.` components are dropped, `..` removes the component
  before it; **`..` above the root is 3**, not clamped.
- **A trailing `\` is 3**, except the root itself (`c:\`).
- A trailing `.` on the last component is dropped (`x.` -> `x`).
- A reserved device name answers `\DEV\<name>`.
- `C:` alone and the empty name are 2; a drive that does not exist is 15; a UNC name with no redirector is 3; a
  buffer too small is 111.

**The length limit** `[OBS]`: the same machine, 2026-10-19, a 32-bit probe with the current directory `C:\` (and, for
the last rows, `C:\OS2`, or a 258-byte current directory on a JFS drive), names built from short components such as
`a\` repeated, none of which need exist, each asked with a buffer of 260 and of 1024 bytes. The buffer size changed
no answer. `QSV_MAX_PATH_LENGTH` was 260.

| name | rc |
|---|---|
| `C:\a\a...`, 256-259 bytes | 0, the name itself |
| `C:\a\a...`, 260, 261, 300, 600 bytes | 206 |
| `a\a...` at `C:\`, 256 bytes (a 259-byte result) | 0 |
| `a\a...` at `C:\`, 257 and 258 bytes (results of 260 and 261) | 206 |
| `a\a...` at `C:\`, 259 bytes | 3 |
| `a\a...` at `C:\`, 260 bytes and more | 206 |
| a component taking the result past 259, then `\..`, `\.`, `\c` or `\` | 3 |
| a component ending the result at exactly 259, then `\..` or `\.` | 0 |
| a last component `bb.`: the result 260 bytes with its dot, 259 without | 206 |
| `q:\...`, a trailing `\`, `\\srv\...`, each 260 bytes or more | 206 (not 15, 3, 3) |
| `x\..\` 60 times, then `y` (301 bytes; the result would be `C:\y`) | 206 |
| `f` to `ffff` under a 258-byte current directory | 206 |
| `..\f` under the same directory | 0 |
| `...\NUL`, `...\CON`, `...\DEV\NUL` after `a\` components, relative, under `C:\` or under `\`, 257-259 bytes | 0, `\DEV\NUL` or `\DEV\CON` |
| the same device names, 260, 261 and 300 bytes | 206 |

What this establishes:
- **A name of 260 bytes or more is 206**, checked before every other answer: before 15 for a drive that does not
  exist, 3 for a UNC name or a trailing separator, and device recognition.
- **Otherwise the result is built a component at a time**, the current directory first for a relative name. A
  component that makes the result 260 bytes or longer is **206 when it is the name's last component and 3 when
  anything follows it**, even a `.` or a `..` that would bring the result back under the limit. A result of 259 bytes
  is 0. The component is counted as typed, a trailing `.` included (the `.` is dropped afterwards).
- **A device name below 260 bytes** answers `\DEV\<name>` whatever the components before it would have built.
- `[DOC-IBM cp1 "DosQueryPathInfo - Return Value"]` lists 206 `ERROR_FILENAME_EXCED_RANGE` and points at
  `QSV_MAX_PATH_LENGTH`; it does not say when 206 or 3 is given. That part is measurement only.

---

## 8. Handle state and type

- `DosSetFHState(hFile, mode)` / `DosQueryFHState(hFile, pMode)` set and read the handle's state
  word - the inheritance bit (`OPEN_FLAGS_NOINHERIT`), cache, write-through, and fail-on-error
  flags from section 3.3. The access and sharing bits fixed at open time cannot be changed here. [DOC-IBM
  `bsedos.h:1518,1524`] Within the state word the settable bits are write-through (bit 14),
  fail-errors (bit 13), no-cache (bit 12), and inheritance (bit 7); the write-through, fail-errors,
  and no-cache bits are **not inherited by child processes**, and the reserved bit fields should be
  written back with the values `DosQueryFHState` returned [DOC - EDM2 "DosSetFHandState"]. The
  fail-errors bit also gives a recovery path: on an unhandleable critical error an application can
  clear the bit and reissue the call, so the same error re-raises and is routed to the system
  critical-error handler instead of back to the caller [DOC - EDM2 "DosSetFHandState"].
- `DosQueryHType(hFile, pType, pAttr)` reports what kind of object a handle refers to. `*pType`
  values [DOC-IBM `bsedos.h:936-941`]:

| Constant | Value | Meaning |
|---|---|---|
| `HANDTYPE_FILE` | `0x0000` | Disk file |
| `HANDTYPE_DEVICE` | `0x0001` | Character device |
| `HANDTYPE_PIPE` | `0x0002` | Pipe |
| `HANDTYPE_PROTECTED` | `0x4000` | Protected handle (opened via `DosProtectOpen`) - OR'd flag |
| `HANDTYPE_NETWORK` | `0x8000` | Network - OR'd flag |

Measured [OBS - Warp Server for e-business 4.50, kernel revision 14.089, 32-bit probe]:

- A file opened `OPEN_ACCESS_READWRITE | OPEN_SHARE_DENYNONE` reports state 0x0042;
  `DosSetFHState(OPEN_FLAGS_NOINHERIT)` returns 0 and the state reads 0x00C2. Trying to change the
  access bits returns 87.
- `DosQueryHType` of a disk file returns type 0 with the attribute word 0x4 (IBM defines that
  word only for character devices).
- `DosResetBuffer` of one handle, of all handles (-1), and of a read-only handle all return 0.
- `DosDupHandle` to a new handle shares the file pointer, and the copy's `NOINHERIT` bit is clear;
  duplicating onto an open handle closes it and redirects it; a target of 1000 returns 114
  `ERROR_INVALID_TARGET_HANDLE`. With the default handle table, nine more duplicates after the test's
  own handles returned 4 `ERROR_TOO_MANY_OPEN_FILES`.
- Every handle call on a closed handle returns 6.

How the kernel derives two of these answers `[OBS-RE]` (Warp 4.5 kernel, read 2026-09-30):
- **`HANDTYPE_PROTECTED`.** It is reported when a dword of the handle's file-table entry is non-zero.
  That dword is written in only two places:
  - entry allocation clears it;
  - a protected open stamps it with the running file-table allocation counter. The same open fails
    with 87 if it was given no place to return its lock id.
- **A `DosPhysicalDisk` handle cannot be typed.** `DosPhysicalDisk` function 2 opens its handle with
  an internal "physical disk" flag, and the entry's device pointer then addresses the partitionable-disk
  table, not a device header. `DosQueryHType` on such a handle returns **6 `ERROR_INVALID_HANDLE`**.
  `[INF]`: the kernel also accepts a name of the form `\\.\Physical_Disk<n>` for the same kind of
  handle. The exact accepted form was not established.
- **Console redirection depends on the device's header, per direction.** A read or write on a
  device handle is redirected to the caller's own VIO/KBD (`ERROR_VIOKBD_REQUEST`, 116, handled
  inside `DosRead`/`DosWrite`) purely by the console bits that the opened device's header carried:
  writes when it has `DEV_COUT`, reads when it has `DEV_CIN`. IBM's shipped headers give this
  pattern [DOC-IBM DDK `kbddata.asm`, `screen01.asm`]:

  | device | header bits | redirected | sent to the strategy |
  |---|---|---|---|
  | `KBD$` | `DEV_CIN` only | reads | writes |
  | `SCREEN$` | `DEV_COUT` only | writes | reads |
  | `CON` | both | both | neither |

- **A redirected console read is line-buffered per process** `[OBS-RE]`. On 116, the `DosRead` half in
  the process serves the read from a per-process buffer of about 0xFE bytes and refills it only when it
  is empty. The caller gets `min(buffered, requested)` bytes, and the rest waits for the next `DosRead`.
  The 32-bit read picks the refill by a **per-handle** bit: the extended handle state (`DosQueryFHState`'s
  internal high word, bit 4), which the kernel lets change only on a console device. It does not use
  the keyboard's binary mode, which the 16-bit `DosRead` tests instead.
  - **Clear (the default):** `KbdStringIn(length 0xFE, IO_WAIT, hkbd 0)`. The previous line's length
    is kept as `cchIn`, so the previous line is the editor's template. **CR LF** is appended unless the
    line starts with `^Z`, which reads as 0 bytes. One **LF** is then echoed through `VioWrtTTY`.
  - **Set:** `KbdCharIn`, `IO_WAIT` for the first key and `IO_NOWAIT` after, until a key without
    `KBDTRF_FINAL_CHAR_IN`. An extended key (`00`, or `E0` with a scan code) is stored as two bytes.
  - A keyboard error is returned as `DosRead`'s rc.

- **The null device transfers nothing, and the two directions report different counts** `[OBS-RE]`.
  The kernel tests the entry's null bit (the header's `DEV_NUL`, `0x0004`; `NUL`'s attribute is `0x8084`) before
  anything else, so the strategy is never called:
  - a **write** returns at once with the count register untouched: **every byte is reported written**, rc 0;
  - a **read** completes as an empty transfer: **0 bytes**, rc 0, and nothing is stored in the buffer.

**Which device a name opens** `[OBS-RE]` + `[DOC-IBM]`. The kernel keeps character-device names in
one table, keyed by name and by *class*, and a name lookup takes the highest class present. It has two
classes:
- **class 1**, device-driver headers;
- **class 2**, pseudo-character devices attached with `DosFSAttach`, which outrank class 1.

A `DEVICE=` driver whose header names an existing character device replaces that device's entry once
its INIT succeeds. This is the PDD reference's "Replacing Character Device Drivers": *"OS/2 character
device drivers can be replaced ... the appropriate bits in the attribute field of the device driver
header and the name of the character device driver must match"*. So `DosOpen("CON")` opens whichever
`CON` was installed last, or an FSD's `\DEV\CON` if one is attached.

**When a name is a device at all** `[OBS-RE]` (Warp 4.5 SMP kernel, read 2026-10-14) + `[DOC-IBM]`.
The kernel runs the device test on the caller's raw string. It does this before canonicalising the
path and before asking any file system. If the canonical form begins `X:\DEV\`, it runs the test once
more. Only then does the name go to the file system. This is IBM's *"DosOpen checks for a device name
before checking for a file name"* (*Control Program Guide*, "Device Names").

The test, for an ordinary (non-DOS) process:
- **A leading drive is ignored**, and the **last path component** is taken whole, extension included.
- The lookup key is that component **upper-cased, with trailing blanks and dots removed**, and it must
  equal a registered name exactly. So `nul`, `NUL.` and `NUL ` are the device. `NUL.TXT` is a file.
- **A device-driver name matches as the last component of any path.** `C:\ANYDIR\NUL` opens NUL even
  when `ANYDIR` does not exist.
- A pseudo-character device attached with `DosFSAttach` matches **only** under the `\DEV\` prefix
  (case-insensitive). IBM says the `\dev\` *"is a required part of the name"* for those (CP Guide,
  "Devices").
  - The exception: a device-driver header of the same name already existed when the attach was made.
    The attach then records that, and the bare name matches too `[OBS-RE]`.
- A trailing `:` (`LPT1:`) is not removed by this test. The name then fails path canonicalisation
  with **123 `ERROR_INVALID_NAME`** `[OBS-RE]` + `[OBS]` (see below).

A DOS-session process uses DOS's rules instead: the extension is dropped and at most 8 characters are
compared.

**`PRN` is an alias, and it needs two lookups** `[OBS-RE]` + `[OBS]`.
1. `PRN` must itself be a registered name. IBM's printer driver declares a `PRN` header [DOC-IBM DDK
   printer PDD source, `prtddtsk.asm`].
2. The kernel then opens the `LPT1` record instead. If there is no `LPT1`, the name is not a device.

So without the printer driver, `PRN` is an ordinary file name even when something else provides
`LPT1`. Measured: `DosOpen("PRN")` gave 110, and 3 under a missing directory. With the printer
driver, `DosFindFirst("PRN")` reports the name `LPT1`. The kernel never makes `AUX` a device; only a
driver header named `AUX` would.

**A `:` inside a path component is 123** `[OBS-RE]` + `[OBS]`.
- The kernel's canonicaliser checks every non-DBCS byte of each component against a character-class
  table. A drive colon is consumed first.
- The bytes the table rejects are `0x00`-`0x1F`, `"`, `/`, `:`, `<`, `>`, `\` and `|`. Any of them
  in a component fails with **123 `ERROR_INVALID_NAME`**.
- So `COM1:`, `NUL:` and an arbitrary `ZZZQ:` all give 123 from `DosOpen` and `DosQueryPathInfo`.
- `DosFindFirst` on the same names answered **3** in the measurement below, and why was not
  established.

**What a non-device name gets.** It is an ordinary path, and the answer is the file system's:
- `\DEV\NOSUCH$` becomes the path `X:\DEV\NOSUCH$`. Real Warp 4.50 answers **3
  `ERROR_PATH_NOT_FOUND`** `[OBS]`, which is `[INF]` the missing directory `DEV`. There is no
  device-layer "no such device" code. No real `\DEV` directory was present when this was measured.
- A bare `NOSUCH$` is a file name in the current directory. `[INF]`: open-if-exists gives 2, and a
  create creates the file.

All the kernel's open entries share this one name translation. The 16-bit and 32-bit `DosOpen` therefore
resolve the same names `[OBS-RE]` for the 16-bit entries; `[INF]` for the 32-bit path, whose kernel
transition was not decoded. Only the 32-bit form was measured.

**Device names that exist on every system.**
- **Kernel-resident headers:** `NUL`, `CON` and `OEMHLP$` `[OBS-RE]`. That is the complete static
  header chain in every kernel build examined.
- **The loader's implicit base drivers**, never named in CONFIG.SYS (`video-stack.md` section 1.2):
  - `CLOCK$` (`CLOCK01`/`02.SYS`);
  - `SCREEN$` (`SCREEN01`/`02.SYS`);
  - `KBD$` (`KBDBASE.SYS`);
  - `RESMGR$` (`RESOURCE.SYS`).

  [DOC-IBM DDK `clockdd.asm`, `screen01.asm`, `kbddata.asm` for the first three header names.]

**Device names that exist only when CONFIG.SYS loads their driver.**
- `LPT1`-`LPT3` and `PRN`: the printer base driver, `BASEDEV=PRINT01.SYS` on a stock install.
- `COM1`-`COM4`: `COM.SYS`.
- `COM1`-`COM9` and `LPT1`-`LPT9` as **placeholders that refuse to open**: the IBM LAN Requester's
  `RDRHELP.200` (see below).
- `MOUSE$` and `POINTER$`: the mouse and pointer drivers.
- `LOG$` and every other installable name.

IBM's reserved-name list in the CP Guide covers base-driver names. That list is not a claim that all of
them always exist, and the same page makes the COM and mouse names conditional.

**`COMn` / `LPTn` with no driver behind them: 20 `ERROR_BAD_UNIT`** `[OBS]` + `[OBS-RE]`.

The measurement `[OBS]` was made on real OS/2 Warp 4.50 (WSeB, SMP kernel) on 2026-10-14. A 32-bit
program ran as `PROTSHELL` and probed each name bare, as `\DEV\<n>`, as `C:\NODIR\<n>`, as `<n>.TXT`
and as `<n>:`. For each form it called `DosOpen` (open-if-exists, fail-if-new, read-only, deny-none),
`DosQueryHType`, `DosQueryPathInfo(FIL_STANDARD)` and `DosFindFirst`. It ran in two boots, with and
without `PRINT01.SYS` and `COM.SYS`.
- **`COM1`-`COM9` and `LPT1`-`LPT9` gave `DosOpen` 20** in every form except `.TXT` and `:`, for every
  unit that had no real driver. With the real driver loaded, the unit opened normally.
- **Those names still behave as devices to calls that do not open them.** `DosQueryPathInfo` gives
  **12**, and `DosFindFirst` succeeds and returns the name. Those are the same answers `NUL` or a
  working `COM1` gives.
- `COM10`, `LPT10` and `AUX` were ordinary file names: 110 bare, 3 under a directory that does not
  exist.

**Where the 20 comes from** `[OBS-RE]`. It is not a kernel rule. The kernel's device table holds only
the names of real device headers (and `DosFSAttach` pseudo-devices), and it reserves no `COM` or `LPT`
pattern. The names come from the LAN Requester's small device driver `RDRHELP.200`, which this
installation loads from CONFIG.SYS:
- It carries headers named `COM1`-`COM9` and `LPT1`-`LPT9`.
- At INIT it asks `DevHlp_AttachDD` about each name, and registers its header only for the names that
  no driver holds yet. So a real driver loaded earlier is never shadowed. One loaded later replaces
  the placeholder, as for any character driver of the same name.
- Its OPEN returns the request status "error, unknown unit" (`0x8001`). The kernel maps driver status
  `01h` to **20 `ERROR_BAD_UNIT`**. Its headers' attribute words are `0x98C0` (COM) and `0x8880` (LPT).

So **the reserved set is exactly that driver's header list, `COM1`-`COM9` and `LPT1`-`LPT9`**: not a
pattern, no `COM0`/`LPT0`, nothing past 9.
- `[INF]`, not measured: on a system without the LAN Requester, an absent `COM5` is an ordinary file
  name.
- `[INF]`: the placeholders exist so that a requester redirection (`NET USE LPT4 ...`, a
  `DosFSAttach` of the name) matches the bare name and not only `\DEV\LPT4` (see the exception
  above).
- Not established: what `DosDelete`, `DosMove`, or a creating `DosOpen` return for these names.

---

## 9. Byte-range locking - `DosSetFileLocks`

`DosSetFileLocks(hFile, pflUnlock, pflLock, timeout, flags)` atomically **unlocks** the range in
`*pflUnlock` and then **locks** the range in `*pflLock`; either pointer may be `NULL` (a
zero-filled range meaning "no operation"). A locked range denies read/write access to that region
by other openers of the file until it is unlocked. It is not a whole-file share mode (section 3.3 is
the whole-file mechanism, ranges are the fine-grained one). [DOC-IBM `bsedos.h:967`; DOC - CP
Reference `DosFileLocks` remarks]

> **CORRECTED (Rule 1.7):** this paragraph also said *"the lock is advisory between processes"*.
> It is **mandatory**: IBM's access table has a non-owner's read and write of an exclusive range,
> and everyone's write of a shared range, wait and then fail [DOC-IBM `cp1.txt`, "DosSetFileLocks -
> Remarks"], and that is what was measured (below). Nothing has to cooperate for the lock to bite.

**Measured** [OBS - Warp Server for e-business 4.50, kernel revision 14.089, 32-bit probes and
their children]:

- **The owner is the handle, not the process.** Inside an exclusive lock taken through one handle,
  a *second* `DosOpen` of the same file in the same process reads 33 and writes 33
  `ERROR_LOCK_VIOLATION`, and cannot unlock the first handle's range (33). A `DosDupHandle` of the
  owner handle reads, writes and unlocks as the owner. A handle inherited by a child is a non-owner
  (33), as IBM says ("Access to locked file ranges is not duplicated across DosExecPgm").
- **Non-owner I/O fails at once.** Another process's read or write of an exclusively locked range
  returned 33 with no wait (0 ms), and a read straddling the range boundary failed the same way; a
  read outside the range succeeded.
- **The lock call's own timeout is honoured:** a second process's conflicting `DosSetFileLocks`
  failed (33) after 0 ms with timeout 0 and after 2,000 ms with timeout 2000.
- **Shared lock:** other processes read; the owner's own write is refused (33).
- Locking a range already locked through the same handle returns 33; an overlapping range 33;
  a negative length or offset 33; unlocking a range never locked 33.
- After the original handle is closed, a surviving duplicate still holds the lock; once every
  handle is closed, others' I/O succeeds.

**The tell:** a second `DosOpen` of a file inside your own program gets 33 on a region the
program itself locked.

`FILELOCK` [DOC-IBM `bsedos.h:943-947`]:

| Field | Type | Meaning |
|---|---|---|
| `lOffset` | `LONG` | Byte offset of the range start |
| `lRange` | `LONG` | Range length in bytes |

`FILELOCKL` is the 64-bit form (`LONGLONG lOffset` / `lRange`) used by `DosSetFileLocksL` [DOC-IBM
`bsedos.h:951-955`].

- `timeout` - milliseconds to wait for a contended lock before giving up.
- `flags` - selects shared-vs-exclusive and whether the unlock/lock pair is performed atomically.
  If the medium/FSD cannot honour an atomic lock request, the call returns
  `ERROR_ATOMIC_LOCK_NOT_SUPPORTED` (174) [DOC-IBM `bseerr.h:227`]. The bits are defined in IBM's
  reference, not in `bsedos.h`: **bit 0 Share** (0 = exclusive, the default; 1 = shared read-only
  access for every process), **bit 1 Atomic** (unlock and lock as one operation, valid only when the
  two ranges are equal; otherwise an error), bits 2-31 reserved [DOC-IBM `cp1.txt`,
  "DosSetFileLocks Parameter - flags"]. *(Previously marked `[unverified]` here.)*

`DosCancelLockRequest(hFile, pflLock)` cancels a pending (blocked) lock request for a range.
Duplicating a handle duplicates access to its locked regions; closing a handle (or process exit)
releases the process's locks in no defined order. [DOC - CP Reference `DosFileLocks` remarks]

`DosResetBuffer(hFile)` flushes the handle's buffered writes to the medium (the 32-bit successor to
the older `DosBufReset`). [DOC-IBM `bsedos.h:1628`] The flush updates the file's directory entry as
if the file had been closed, but the file **remains open** [DOC - EDM2 "DosBufReset"]. In the older
16-bit `DosBufReset`, passing the handle `0xFFFF` flushed *all* of the process's open file handles
at once [DOC - EDM2 "DosBufReset"].

---

## 10. Common error codes [DOC-IBM - `bseerr.h`]

`APIRET` `0` (`NO_ERROR`) is success. Values relevant to this API surface:

| Constant | Value | Typical trigger |
|---|---|---|
| `ERROR_FILE_NOT_FOUND` | `2` | Named file does not exist |
| `ERROR_PATH_NOT_FOUND` | `3` | A directory in the path does not exist |
| `ERROR_TOO_MANY_OPEN_FILES` | `4` | Per-process handle limit reached (see `DosSetMaxFH`) |
| `ERROR_ACCESS_DENIED` | `5` | Attribute/permission conflict (e.g. delete read-only) |
| `ERROR_INVALID_HANDLE` | `6` | Handle not open in this process |
| `ERROR_NOT_ENOUGH_MEMORY` | `8` | System out of memory for the request |
| `ERROR_NO_MORE_FILES` | `18` | `DosFindFirst` / `DosFindNext` exhausted the match set |
| `ERROR_SEEK` | `25` | Seek error |
| `ERROR_SHARING_VIOLATION` | `32` | Open conflicts with an existing opener's deny mode |
| `ERROR_LOCK_VIOLATION` | `33` | Requested range overlaps a range held by another |
| `ERROR_FILE_EXISTS` | `80` | Create-only open of an existing file |
| `ERROR_INVALID_PARAMETER` | `87` | Bad flag combination or argument |
| `ERROR_DRIVE_LOCKED` | `108` | Volume locked by another process |
| `ERROR_OPEN_FAILED` | `110` | Open failed (general) |
| `ERROR_BUFFER_OVERFLOW` | `111` | Name/result too long for the supplied buffer |
| `ERROR_DISK_FULL` | `112` | No space to complete a write/create |
| `ERROR_NEGATIVE_SEEK` | `131` | Seek to a negative offset |
| `ERROR_INVALID_NAME` | `123` | Illegal characters in a path |
| `ERROR_FILENAME_EXCED_RANGE` | `206` | A name component outside the 8.3 form from a program whose `NEWFILES` bit is clear (section 11); also a genuinely over-long name |
| `ERROR_ATOMIC_LOCK_NOT_SUPPORTED` | `174` | Atomic lock requested where unsupported |

### 10.1 `2` vs `3` - which not-found code a path API gives [OBS]

Both codes are documented outcomes of the same call - `DosQFileMode`'s own published list carries
2, 3, 26, 87, 108 and 206 [DOC-IBM `$OS2_EDM2/os2books/prcp/112_L2_DosQFileMode.html`], and so
does `DosSetFileMode`'s (section 6.1) - so *which* one applies to *which* input is a measurement, never a
transcription. The determinant is the one the table above names: **3 is "a directory in the path
does not exist"**, i.e. the answer is decided by the **directory portion** of the path, not by the
leaf.

Measured on Warp 4.50, one call per row, capture retained project-side (ordinal 75):

| path | shape | rc |
|---|---|---|
| `\NOSUCH.XYZ` | leaf missing, parent (the root) present | **2** `ERROR_FILE_NOT_FOUND` |
| `\NOSUCH\FILE` | intermediate directory missing | **3** `ERROR_PATH_NOT_FOUND` |
| `""` | the empty path | **3** |

The pair is what makes either line mean anything: a capture showing only the second could not
distinguish "3 for a missing directory" from "3 for anything not found".

**Independently corroborated on a different ordinal**, from the `NEWFILES` work in section 11: a long
*parent* that is **missing** answers 3, while a long parent that **exists** resolves normally so
an absent child under it answers "the ordinary not-found code (2 from `DosQueryPathInfo`)" `[OBS]`.
Two ordinals, two sessions, the same rule. Corroboration of the **mechanism** only - a sibling
licenses nothing, which is why ordinal 75 was asked for itself.

**Two shapes of this question are NOT established and must not be inferred from the above:**

- an intermediate component that **exists but is not a directory** (Linux would report `ENOTDIR`
  rather than `ENOENT`). Reading 3's definition literally suggests 3, but nothing here measures it.
- a **trailing separator** on a missing name (`\NOSUCH\`).

Recorded as a negative result so they are not re-derived by argument: the definition of error 3 is
a documented *meaning*, and a meaning does not settle a *behaviour* (Rule 1.2).

---

## 11. Long file names and the `NEWFILES` bit

Whether a program may use names outside the 8.3 form is decided by **the program's own
executable header** - not by the volume, and not by which API width it calls. The rule
[DOC-IBM `cpgref` "Long File Names"; the same text is in the Control Program Guide, `cp2`
"Long File Names"]:

> "Programs that recognize long file names must indicate this by including the NEWFILES
> statement in their module definition file. This statement directs the linker to set a bit in
> the executable file header. It indicates that the module supports long file names. ...
> This bit has meaning when attached to program modules, not when attached to DLLs. Whether the
> program recognizes long file names format is entirely dependent on the value of its NEWFILES
> bit and the effect of the bit extends into any calls to DLLs."

The bit is `NELONGNAMES` (`0x01`) in the NE header's `ne_flagsothers` byte at NE+0x37
[DOC-IBM `newexe.h` `struct new_exe`, `#define NELONGNAMES 0x01`; see `executable-formats.md`
section 3.1]. For a program **without** it, IBM documents these restrictions [DOC-IBM, same passage]:

- Any name not representable in 8.3 form **is not returned by `DosFindFirst` or `DosFindNext`**
  ("the application's buffers are unlikely to be large enough to handle longer names").
- "Any long file name passed to the file system functions listed below are rejected in exactly
  the same way as under previous versions of the OS/2 operating system. It is not acceptable to
  create and manipulate a name that you cannot find." The list, verbatim: `DosOpen`,
  `DosDelete`, `DosMove`, `DosQueryPathInfo`, `DosSetPathInfo`, `DosCreateDir`, `DosDeleteDir`,
  `DosFindFirst`, `DosFindNext`, `DosQueryFSAttach`, `DosFSAttach`, `DosCopy`, `DosSearchPath`.
- `DosSetCurrentDir` and `DosQueryCurrentDir` accept long names from every program, "so that all
  programs can use all directories" - restated in both functions' own reference pages
  ("Programs running without the NEWFILES bit set are allowed to issue DosSetCurrentDir for a
  directory that is not in the 8.3 file-name format") [DOC-IBM `cpgref` "DosSetCurrentDir",
  "DosQueryCurrentDir" (Remarks)].
- Names used with non-file-system functions (IBM's example is `DosCreateSem`) are not filtered.
- The bit is meaningless in a DOS session and before OS/2 1.2; a bound program with the bit sees
  long names in OS/2 mode and only 8.3 names in a DOS session. On a FAT volume a long name is an
  error in OS/2 mode and is silently truncated in DOS mode.
- A program **with** the bit is still refused, on a FAT volume, a directory name with blanks
  immediately before the dot (`"file .txt"` rejected, `"file.txt"` accepted) [DOC-IBM `cpgref`
  "DosCreateDir" (Remarks)].
- Because DLLs do not carry the bit and run under the caller's, IBM requires that a DLL never
  create internal temporary files or directories outside 8.3 form and never return a long name
  to its caller.

IBM's text says "rejected" and names no return code.

**Measured - Warp 4.50, live system, one volume that accepts long names (not FAT) [OBS]:** one
16-bit program, linked twice from the same object code - once with `NEWFILES`
(`ne_flagsothers = 0x01`), once without (`0x00`), code and data segments byte-identical - called
`DosMkDir` (the 16-bit `DosCreateDir`) on five names in the root:

| name component | form | bit clear | bit set |
|---|---|---|---|
| `LFNTEST8` | 8 | 0 | 0 |
| `LFNTEST9X` | 9 | **206** | 0 |
| `LFNTEST12XYZ` | 12 | **206** | 0 |
| `LFNTEST.EXT` | 8.3 | 0 | 0 |
| `LFNTEST.EXTX` | 8.4 | **206** | 0 |

So the determinant is the module's bit, exactly as documented, and the rejection surfaces from
`DosMkDir` as `ERROR_FILENAME_EXCED_RANGE` (206).

**The rejection code is 206 across the file-system functions, now measured [OBS]** (Warp 4.50,
HPFS, live, 2026-08-23). A bit-clear 16-bit program passing a **long leaf** returns 206 - before
the operation's own not-found code - from every one of `DosCreateDir`, `DosDeleteDir` (`DosRmDir`,
80), `DosOpen` (70), `DosDelete` (60), `DosMove` (67) and `DosQueryPathInfo` (98). This supersedes
the earlier note that 206 was `[INF]` "measured for `DosMkDir` only": it is the observed code for
six of the thirteen functions. (The remaining seven -
`DosSetPathInfo`, `DosFindFirst`/`DosFindNext`, `DosQueryFSAttach`, `DosFSAttach`, `DosCopy`,
`DosSearchPath` - are still unmeasured; `DosFindFirst`/`DosFindNext` *filter results* rather than
reject an input, so a distinct check.) [`DosSearchPath` was measured 2026-09-30; see the next
paragraph.]
**`DosSearchPath`, measured 2026-09-30 [OBS]** (WSeB 4.52 CP2, one 16-bit program linked with and
without `NEWFILES`): a quoted path element naming a directory `A;B` (not representable in 8.3),
searched for the 8.3 leaf `SPQ.TXT`, answers **2** without the bit and finds the file with it.
**What rejects the element is not established [INF]:** the leaf is 8.3, and the filter
described above checks the leaf. The final 2 is consistent with a rejection code from the
continue table (section 15) being passed over, but no per-element code was captured.

**Where the filter applies - resolved [OBS]** (same session; supersedes the earlier "not
established" note that only recorded a long *missing* parent answering 3):

- **It checks the LEAF (final) component's 8.3 form, and does so *before* path resolution of that
  leaf.** A long leaf under a **missing** 8.3 parent still answers 206 - not the
  `ERROR_PATH_NOT_FOUND` (3) that resolving the missing parent alone would give.
- **It is leaf-only, not component-wide.** A long *non-leaf* (parent) component is **not**
  filter-rejected: a long parent that is *missing* answers 3, and a long parent that *exists*
  resolves normally so an absent 8.3 child under it answers the ordinary not-found code (2 from
  `DosQueryPathInfo`), never 206.
- **A long leaf is rejected even when it exists.** `DosQueryPathInfo` on an existing directory
  whose own name is non-8.3 answers 206, not 0 - the leaf's *format* is checked, independent of
  whether it is found.

So the model is: validate the final component against 8.3 (reject 206 if non-8.3 and the program's
`NEWFILES` bit is clear) *before* resolving the path; intermediate components are not format-checked
and undergo ordinary resolution.

**A 32-bit (LX) program is not subject to the filter at all - resolved [OBS]** (same session;
supersedes the earlier "not established" negative result). Measured directly: a 32-bit LX program
passing non-8.3 names (9-, 12-character, and 8+4-extension) to `DosCreateDir`, `DosOpen`,
`DosDelete` and `DosQueryPathInfo` gets results byte-identical to the 8.3 case - the long directory
or file is created, and a non-existent long name returns the ordinary not-found code, never 206. An
LX module cannot carry the NE `NELONGNAMES` bit and the LX format reference documents no equivalent
flag (the negative documentary result still stands: every `NEWFILES` occurrence in `cpgref`, `cp1`,
`cp2`, `cp3`, `cmdref21`, the Toolkit headers and `lxref` was searched, and only the NE/`.DEF`
passages exist). A 32-bit program therefore behaves as if `NEWFILES` were always set - the long-name
filter is a property of the 16-bit NE program model, not of 32-bit LX programs.

---

## 12. Two process-global settings file I/O depends on: the current drive, and the handle limit

Both are **per-process** values, both are inherited from the parent at process start, and both
have a 16-bit and a 32-bit entry point. They are grouped here because a program that gets either
one wrong misreads every relative path or every later open, and because the documented contract
for the second one is **wrong on a shipping build** in a way only measurement shows.

### 12.1 The current drive [DOC-IBM] [OBS]

| what | 32-bit | 16-bit |
|---|---|---|
| set | `DosSetDefaultDisk(ULONG disknum)` | `DosSelectDisk(USHORT usDrvNum)` |
| query | `DosQueryCurrentDisk(PULONG pdisknum, PULONG plogical)` | `DosQCurDisk(PUSHORT pusDrvNum, PULONG pulLogDrvMap)` |

The old names are the 16-bit exports; at 32 bits they are **macros** onto the new ones
[DOC-IBM `bsedos.h:1493-1494`: `#define DosSelectDisk DosSetDefaultDisk`,
`#define DosQCurDisk DosQueryCurrentDisk`], while the 16-bit header declares each as a real
entry point with a narrower prototype [DOC-IBM `bsedos16.h:1046-1047`, `:847`].

**Numbering** [DOC-IBM `cpgref`/`cp1` "DosSetDefaultDisk - Parameter disknum"]: *"The value 1
means drive A, 2 means drive B, 3 means drive C, and so on. The maximum possible value is 26,
which corresponds to drive Z. Values outside this range will cause an error."* The logical-drive
map is a bitmap over the same numbering, bit 0 = A.

**The complete documented return list is two values** - `0 NO_ERROR` and `15
ERROR_INVALID_DRIVE` [DOC-IBM ibid., "Return Value - ulrc"]. That is unusually short and it is
worth relying on: an implementation reaching for `87 ERROR_INVALID_PARAMETER` on a bad drive
number is answering with a code this call never gives.

**The parameter space, measured on Warp Server for e-business (Convenience Package, "The
Operating System/2 Version is 4.50", kernel Internal revision 14.089), 2026-09-05, at BOTH ABI
widths on the same machine** `[OBS]`. Most of it the documentation already settles by the range
sentence above - every value outside 1..26 errors, and the table confirms it rather than
discovering it. **One input is genuinely unsettled and two properties are not stated at all**;
those three are called out under the table.

| input | rc | current drive afterwards |
|---|---|---|
| `0` | `15` | unchanged |
| a letter present in the map (`3` = C:, the boot volume) | `0` | that drive |
| a letter absent from the map (`5` = E:) | `15` | unchanged |
| `26` (Z:, the documented maximum, absent from the map) | `15` | unchanged |
| `27` (one past the documented maximum) | `15` | unchanged |
| `255` | `15` | unchanged |
| `0xFFFF` | `15` | unchanged |
| `0x10000`, `0xFFFFFFFF` (32-bit entry only) | `15` | unchanged |

**The one genuinely unsettled input, and the two properties IBM never states:**

- **`0` is not a synonym for "the current drive"**, which is the plausible reading and is wrong:
  several sibling calls do spell the current drive as 0 - `DosQCurDir`'s `usDrvNum` is exactly
  that [DOC-IBM `bsedos16.h:1049-1050`] - so the ambiguity is real. Here 0 is simply an invalid
  drive number.
- **A rejected call leaves the current drive untouched.** Every `15` above was followed
  immediately by a query, and the answer was the starting drive every time. So the call either
  succeeds completely or changes nothing; there is no partial state to unwind.
- **The range check does not distinguish "outside 1..26" from "inside 1..26 but not mounted".**
  `26` and `27` are one apart, on opposite sides of the documented maximum, and both answer `15`.
  That is the single-variable control that says the rc carries no information about *which*
  reason applies; a caller that needs to tell them apart must read the logical-drive map.

**The drive is per process and is inherited, not global** [DOC-IBM `cpgref` "About Directories"]:
*"When an application starts, it inherits the current directory and drive from the application
that starts it."* It is also only one of two independent defaults - the other being that drive's
own current directory - so a driveless path takes the first, and a driveless **rooted** path
(`\FOO`) takes the first and not the second.

**A current directory never goes above the root** `[OBS]`: Warp Server for e-business 4.50, 2026-10-18, a 32-bit
probe, each line `DosSetCurrentDir` then `DosQueryCurrentDir`:

| from | set | rc | current directory after |
|---|---|---|---|
| `\` | `\` | 0 | `\` |
| `\` | `..` | 3 | `\` |
| `\` | `..\OS2` | 3 | `\` |
| `\` | `\..` | 3 | `\` |
| `\` | `\OS2` | 0 | `\OS2` |
| `\OS2` | `..\..` | 3 | `\OS2` |

Any `..` that would leave the root answers 3 and changes nothing, whatever follows it; it is not clamped at the root.
`DosQueryPathInfo` level 5 follows the same rule (section 7.6). `[DOC-IBM cpgref "DosSetCurrentDir - Return Value"]` lists 3
among the returns but not this case.

### 12.2 The per-process file-handle limit [DOC-IBM] [OBS]

| what | 32-bit | 16-bit |
|---|---|---|
| set (absolute) | `DosSetMaxFH(ULONG cFH)` | `DosSetMaxFH(USHORT usHandles)` |
| set (relative) + query | `DosSetRelMaxFH(PLONG pcbReqCount, PULONG pcbCurMaxFH)` | *none - see below* |

**Note the pairing shape, which is unlike section 12.1's**: there is **no compatibility `#define`** for
this one, because the 32-bit entry carries the *same name* at a wider argument type
[DOC-IBM `bsedos.h:1734` `APIRET APIENTRY DosSetMaxFH(ULONG cFH);` against `bsedos16.h:1059`
`APIRET APIENTRY DosSetMaxFH(USHORT usHandles);`]. Two entry points, one name, two widths.

**There is no 16-bit read-back.** No `DosQueryMaxFH` exists in any edition, and the 16-bit header
declares no relative form: `RelMaxFH` occurs **zero** times in `bsedos16.h`, and Open Watcom
1.9's 16-bit `h/os21x/bsedos.h` declares only `DosSetMaxFH(USHORT)`. So a 16-bit program can
raise its handle limit and can never ask what it is. At 32 bits `DosSetRelMaxFH` **is** the query,
and IBM's own example code says so: a zero increment changes nothing and fills in the current
count - *"Using 0 here will return the current number of file handles"*
[DOC-IBM `cp1` "DosSetMaxFH - Example Code"].

**Documented return list**: `0 NO_ERROR`, `8 ERROR_NOT_ENOUGH_MEMORY`, `87
ERROR_INVALID_PARAMETER` [DOC-IBM `cp1` "DosSetMaxFH - Return Value"].

**Documented behaviour** [DOC-IBM `cp1` "DosSetMaxFH - Remarks"], quoted because two of its three
clauses are refuted below:

> "OS/2 initially allocates 50 file handles to a process. ... If an application tries to set the
> number of file handles using DosSetMaxFH to a value less than the number of file handles set by
> OS/2 or a parent process it will return an error return code of 87, ERROR_INVALID_PARAMETER. If
> a higher limit is set, it can be lowered, but not lower than the value inherited from the system
> or the parent process."

**Measured on the same machine and the same day as section 12.1, at both widths** `[OBS]`:

| step | request | rc | count afterwards |
|---|---|---|---|
| start (child of the command processor) | - | - | **20** |
| raise | 100 | `0` | 100 |
| raise | 200 | `0` | 200 |
| lower, still far above the inherited 20 | 60 | **`87`** | 200 |
| raise | 0xFFFF | **`87`** | 200 |
| raise | 0x10000 | **`87`** | 200 |
| raise | 16384 | `0` | 16384 |
| raise to the ceiling | 32768 | `0` | 32768 |
| one past the ceiling | 32769 | **`87`** | 32768 |
| well past it | 33000 | **`87`** | 32768 |
| **exactly the current count** | 32768 | `0` | 32768 |
| **the current count - 1** | 32767 | **`87`** | 32768 |
| lower, to exactly the INHERITED value | 20 | **`87`** | 32768 |
| lower | 0 | `87` | 32768 |

Every row is one run of one program on one machine, and the whole of it is retained rather
than summarised: the last four rows of the group above are the pair that separates the two
findings, because **32768 is issued twice at two different current counts** - once as a raise
from 16384, once when it already *is* the current count - so "the ceiling is 32768" and
"setting exactly the current count is allowed" are two observations rather than one number
doing double duty. `32769` and `32767` bracket it on either side, one variable each.

**Four corrections follow. The fourth lands exactly on the boundary IBM's own sentence names,
and it is the sharpest of them:**

1. **The initial 50 is a system default, not an invariant.** This process started at **20**.
   ~~inherited from its parent command processor - which the same paragraph allows for ("or the
   parent process").~~ Nothing may treat 50 as a constant.

   **THE ATTRIBUTION IS REFUTED, 2026-09-06 (Rule 1.7 - struck, not deleted, because the
   reasoning was plausible and the next reader will reach for it too).** The parent command
   processor does not supply the 20. Measured 2026-09-06 on OS/2 4.50 (WSeB Convenience
   Package), kernel Internal revision 14.089_SMP: one probe binary, launched twice, minutes
   apart, changing one thing - once *through* `CMD.EXE` and once directly, with no command
   processor anywhere in the chain. Both runs report a starting count of **20**. Taking the
   command processor out entirely does not move the number. `[OBS]`.

   **The real source is structural, and it is a fact about the PTDA rather than about
   inheritance**: the PTDA carries an **inline JFN table sized for exactly 20 entries** - a
   0x28-byte array of WORDs - and a fresh process starts on it. The kernel's own `DosSetMaxFH`
   worker corroborates from the other side: its special case is *"if the current length is 20,
   move the table off the inline array into an allocated segment"*, which is the growth step
   that array exists to make necessary. `[OBS-RE]`, read in two kernel builds.
   Two further candidates were eliminated rather than merely doubted: **memory** - reported as the
   same 20 on 2048 MB and 3072 MB images of one install lineage, though the larger image's capture
   was **not retained**, so what actually eliminates memory is that the count comes from a
   **fixed-size structure** that cannot scale with RAM - and the **`FILES=` CONFIG.SYS
   statement**,
   whose value happened to be 20 on the measured machine - *"FILES= has no effect in OS/2
   sessions"*, `[OBS-USER]`, the author quoting OS/2's own online help, which is not among
   the books held here.

   **Residual, stated because it is genuinely open**: all four observations are of processes
   whose ancestors were themselves at 20, so *inheritance* and *fresh-process default* remain
   indistinguishable by measurement alone - it is the structure, not the captures, that
   answers it.
2. **There is a hard ceiling at exactly 32768**, and exceeding it gives `87`, not the `8
   ERROR_NOT_ENOUGH_MEMORY` the documented rc list makes plausible. ~~Whether 32768 is
   architectural or per-machine is **not established** - one build, one machine.~~

   **SETTLED 2026-09-06 (Rule 1.7): it is architectural, and it is a literal in the kernel's own
   guard.** The worker behind `DosSetMaxFH` sets its return to `87` *first* and then tests the
   request against `0x8000`, jumping straight to that pre-set return when the request is larger:
   so the request must be **<= 32768**, and **that is also why the answer is 87** - exceeding the
   bound skips every path that would replace the default. `[OBS-RE]`. **The method has two steps that carry
   different weight, so they are stated separately rather than summed.** The guard was
   **disassembled** - not read off a decompiler - in **one** build, kernel revision 14.089 SMP.
   The same eleven-byte string was then **byte-searched** and found verbatim in three further
   shipped kernel images, one of them a **different fixpak** (14.104a). A byte search is the
   weaker instrument and it is not symmetric: a pattern found really is there, but *"not found"*
   proves nothing, because a shipped LX kernel stores relocation data inside operand slots and a
   sought byte may sit in one.

   `[OBS]` corroboration on **two** machines whose captures are retained, differing in kernel
   flavour (UNI/SMP) at **equal memory**. A third image with more memory gave the same answers,
   but **its capture was not kept**, so it is named as an uncorroborated report and not counted -
   which means **the memory comparison is not, on retained evidence, a controlled one**. What
   actually settles "not derived from memory or configuration" is not that comparison at all: it
   is that the bound is a **literal in the instruction stream**, which cannot vary with either.
3. **The floor is the CURRENT count, not the inherited one, so the call is effectively
   grow-only.** The quoted sentence says a raised limit "can be lowered, but not lower than the
   value inherited"; the measurement refutes it directly - inherited 20, current 200, request 60,
   answer `87`. Setting *exactly* the current count succeeds (32768 against a current 32768) and
   one less fails (32767), which is the single-variable control that fixes the threshold on the
   current value. **Read the sentence as describing an intent that this build does not
   implement**, and treat `DosSetMaxFH` as monotonic.
4. **And the request for 20 refutes the same sentence a second time, at the value the sentence
   itself picks out.** The inherited count here is 20. IBM says a limit may be lowered "but not
   lower than the value inherited" - and **20 is not lower than 20**, so by that wording the
   request must succeed. Real OS/2 answers `87`. Correction 3 shows the rule is wrong *somewhere*
   between 20 and 200; this one shows it is wrong *at the named value*, which leaves no reading
   of the sentence under which the documented behaviour is the implemented one. Anyone deriving
   an expected value from that paragraph will get this case backwards, which is exactly what
   makes it worth stating separately.

**What follows for a program**: use `DosSetRelMaxFH` to query and adjust, which is what IBM's own
Remarks recommend for a different reason (*"Applications should instead use DosSetRelMaxFH, to
query first and then to set"*). A 16-bit program has neither the query nor a way to discover the
ceiling, so its only safe pattern is to ask for what it needs, once, and check the rc.

**Not measured, and worth stating so nobody assumes it**: what happens to a lowering when the
process already holds more open handles than the requested maximum; ~~and whether
`DosSetRelMaxFH` with a negative increment obeys the same current-count rule or the inherited
one.~~

**The `DosSetRelMaxFH` half of that is ANSWERED, 2026-09-06 - and the answer is "neither"
(Rule 1.7).** The relative form is a different contract from the absolute one, in IBM's text and
in the code, and reading one off the other is the mistake this note was guarding against:

- IBM documents a decrease here as **advisory**: *"The system treats a decrease in the maximum
  number of file handles as an advisory request that may or may not be granted"*, and *"The
  return code is set to NO_ERROR even if the system defers or disregards a request for a
  decrease. You should examine the value of `pcbCurMaxFH` to determine the result."* Its
  documented return-value list has exactly one entry, `0 NO_ERROR` - where `DosSetMaxFH`'s
  carries an error code. `[DOC-IBM]`
- The kernel's relative worker **clamps at both ends and never returns an error of its own**: an
  increase is clamped to the same **32768** ceiling; a decrease is **honoured**, floored at
  **20** - the inline-table size from correction 1 - and is a no-op when the count is already 20.
  So the floor of the relative form is a **constant**, not the current count and not the
  inherited one. `[OBS-RE]`
- It also writes **two** values back to the caller, not one: `pcbCurMaxFH` receives the new
  maximum, and `pcbReqCount` - which IBM's parameter list calls **input** - receives the
  **granted delta** (new count - old count). `[OBS-RE]`

**Not measured on a running machine**: none of the three points above. They are read from IBM's
text and from the kernel's instructions; the only live observation of this call with a non-zero
increment is a single `+32` on a fresh process yielding 52 - firsthand, by the author, in unrelated application code, with no capture retained. `[OBS-USER]`

---

## 13. Verify mode - `DosSetVerify` / `DosQueryVerify`, a per-process setting

**The calls** [DOC-IBM - `bsedos.h:1730-1732`; `os21x/bsedos.h:348,359`; cp1/cpgref pages]:
`DosSetVerify(BOOL32)` (32-bit; 16-bit `DosSetVerify(USHORT)`) returns 0 or 118
`ERROR_INVALID_VERIFY_SWITCH`; `DosQueryVerify(PBOOL32)` (16-bit `DosQVerify(PUSHORT)`) returns 0
and the mode, 0 or 1. The page's meaning: when active, "the operating system verifies that data
written to the disk is recorded correctly". `DosQVerify` is `DosQueryVerify`'s 16-bit name
(`bsedos.h:1498`).

**Where it lives** [OBS-RE - kernel 14.104a SMP, UNI debug kernel agrees]: one byte, `VerFlg`, at
PTDA+0x43E - the process's own control block. Set (`w_SetVerify`) stores a value below 2 and answers 118 otherwise;
Query returns the byte. A new process's PTDA starts as a copy of its parent's, so the mode is
**inherited**. Only Set and Query were found touching the byte; no reader that acts on it was found
(a search keyed on that expression, which cannot rule out a reader through another pointer).

**Measured on Warp Server for e-business 4.50, rev 14.089 (SMP), 2026-09-29** [OBS] - paired 32-bit
and 16-bit programs calling each function directly, one call per case, plus a child process for the
inheritance and trap cases:
- A program started from the shell sees 0. A child sees its parent's value; a child's change never
  reaches the parent. Several programs at once each keep their own value.
- **The 32-bit `DosSetVerify` uses only the low 16 bits** of its argument: 0x10000 is accepted as 0,
  0x10001 as 1; 0xFFFFFFFF answers 118. A failed set leaves the mode unchanged.
- The 32-bit query writes exactly 4 bytes, the 16-bit one exactly 2 (a guard word after the target
  is left unchanged).
- **A NULL query pointer answers 87 on the 32-bit entry and traps (#GP) on the 16-bit one.**

## 14. `DosShutdown` - locking the file systems, and what ends the machine afterwards

**The call** [DOC-IBM - Toolkit `bsedos.h:1790`; Open Watcom 1.9 `h/os21x/bsedos.h:360`; `cp1`
"DosShutdown"]: `DosShutdown(ULONG)` - the Toolkit names the parameter `ulReserved`, the `cp1` page
`ulShutDownValue` - and 16-bit `USHORT DosShutdown(ULONG)`. The page:
0 = "full system shutdown and file-system lock", 1 = "buffer and cache flushing to make system
quiescent"; returns 0, 87, 274 `ERROR_ALREADY_SHUTDOWN`; after 0, "allocated memory cannot be
increased".

**What the kernel does** [OBS-RE - kernel 14.104a, the `w_Shutdown` sequence and its gates, SMP
decompiles agreeing]: the value arrives split into low and high words; **bits 16-17 are masked out**
of both classifying tests. 0 runs the full sequence: take the shutdown semaphore; 274 if already
shut down; stamp shutdown state 1 into every SFT segment; **wait until a count of the built-in file
system's calls in flight reaches 0** (those calls wait from state 1, and count themselves in and out
around their work); stamp state 7 (bit 2 is what the SFT lock tests - the lock takes effect here);
replace every file system's entry points with a blocking stub (read, write, seek and FS-info get
filters that block the same way); send Strategy command 1Ch (start) to each driver of level 2, or
above level 2 with capability bit 0 set; `FS_SHUTDOWN(0)`; for each SFT entry (three classes
skipped) an `FSD_Commit`; then routines named `FSD_FlushBuf(0,0)` and `FatDirtyBitClear` (their
bodies not read); `FS_SHUTDOWN(1)`; command 1Ch (end); return. 1 calls only `FSD_FlushBuf(0,0)`. **Any other value**
answers 87 only if the process in TCB slot 1 is dying; otherwise it continues as a full shutdown and
ends in the internal-caller exit, which prints messages and **halts**.

**The gates** [OBS-RE]: after the lock a thread that reaches a file-system entry point (all of them
replaced), or locks an SFT entry (the read/write path, seek, close, new size), is parked for ever -
the block loops if woken. The one exception: **`DosDevIOCtl` on a device handle** (SFT `sf_flags` bit 0x80, "local I/O
device" [DOC-IBM - *Debugging Handbook* table 116]) takes a lock routine without the shutdown test,
so a device IOCtl on a handle opened *before* the lock reaches its driver. The installable-file-system
side of the contract is `FS_SHUTDOWN` [DOC - EDM/2 "FS_SHUTDOWN"]: at type 0 no new I/O reaches the
FSD and it must finish data-modifying calls before returning; then every SFT is committed and every
volume flushed; type 1 ends it.

**Measured on Warp Server for e-business 4.50, rev 14.089 (SMP), 2026-09-29** [OBS] - paired 32-bit
and 16-bit programs, each full shutdown on a freshly restored system; a second thread and a 10-second
flag to tell "blocked" from "returned":
- 1 and 0x10001 return 0, and file I/O works afterwards. 0 returns 0; a second 0 returns 274.
  0x10000 returns 0 and a following 0 returns 274 - it is read as 0. **0x40000 halts the machine
  like 2** (both widths): a bit above 17 is not masked, so only bits 16-17 are.
- After 0: `DosWrite`, `DosOpen` and `DosRead` from another thread do not return within 10 s;
  `DosDevIOCtl` on a device handle opened before the call returns; `DosAllocMem` of 64 KB still
  succeeds. About 30 s after the program's last line its shell had not prompted again - the process
  had not finished terminating while those threads stayed blocked.
- **2 does not return 87: the machine halts.** The display leaves PM for a text screen; from a
  16-bit caller it reads "OS/2 cannot be started. The error code is: ... 1199 The system is stopped.
  Correct the preceding error and restart the system." (1199 = 0x4AF, the reason the kernel sets for
  an invalid value); a 32-bit caller showed only "0" for 2, and the full text for 0x40000.
- After the lock, a process's **first** VIO call blocks; one made before the lock keeps working.

**What ends the machine** [DOC - XWorkplace `src/startshut/shutdown.c` and `apm.c`, with
xwphelpers `src/helpers/apmh.c`]: `DosShutdown` never powers off or reboots; a program does that
afterwards. Reboot: open `\DEV\DOS$` *before* `DosShutdown(0)`, then `DosDevIOCtl` category D5h
function ABh on it (which the device exception above lets through). APM power-off: `DosShutdown(1)`,
then, on `\DEV\APM$` (opened by xwphelpers' `apmhOpen`), "send power event, set power state off,
all devices". XWorkplace's reason for `DosShutdown(1)` there is that 0 "would block any subsequent
DosDevIOCtl calls" (`apm.c`) - which the kernel's device exception above and the capture contradict
for a device handle opened beforehand; what blocks the APM case was not established. ACPI: `DosShutdown(0)`, then an S5 sleep request. Otherwise
the program shows "shutdown complete" and blocks for ever; the user switches off.

## 15. `DosSearchPath` - how a search path is walked [DOC-IBM / OBS-RE / OBS]

**The API, [DOC-IBM]:**
- `DosSearchPath(ULONG flag, PSZ pszPathOrName, PSZ pszFilename, PBYTE pBuf, ULONG cbBuf)`
  (32-bit, DOSCALLS 228) and the 16-bit form with `USHORT` flag and length (DOSCALLS 151).
- Flag bits: implied current directory 1, path is an environment-variable name 2, ignore network
  errors 4.
- Documented returns: 0, 1, 2, 87, 111, 203.
- The page says the result is fully qualified, and that global file-name characters stay in
  place.

**How it works, [OBS-RE]:** both entries are DOSCALL1 code, one algorithm coded twice, over a
32-bit and a 16-bit set of helpers.

**Checks,** in order:
- `cbBuf` 0 -> 111, and the buffer is untouched.
- 32-bit: reserved flag bits, or a length above 0xFFFF -> 87.
- 16-bit: a buffer whose offset plus length runs past its segment, then reserved flag bits -> 87.
- Every failure except `cbBuf` 0 clears the buffer's first byte, the 87s included.

**Order of search:**
- **The implied current directory** is built as the element `"."`: the process's current drive and
  directory, then `\.\`, then the name. So it needs two bytes more than the result (measured: a
  buffer of the result's length + 2 answers 2, and `cbBuf` 4 at the root answers 111).
- **An element longer than 0x104 characters** is skipped, and the rest of it is parsed as the next
  element (measured: 0x105 characters of junk followed by `C:\OS2` finds the file in `C:\OS2`).
- **Elements:**
  - a quote toggles quoting and is dropped, and a string that ends inside a quote skips its element;
  - `/` becomes `\`;
  - `;` separates;
  - **an empty element is the current directory unless the previous element's second character
    was `:`**: IBM tests the element buffer's second byte without checking the element is
    non-empty, and an empty element does not overwrite it. Measured: `;X` and `SUBX;;X` search
    the current directory, `C:\OS2;;X` and `C:\NOSUCH;;` do not;
  - a relative element hangs off its drive's current directory.
- **Buffer:** each candidate is built in the caller's buffer.
  - If even the directory does not fit, the search ends with 111.
  - If only directory plus name does not fit, that element is skipped.

**Matching:**
- `DosFindFirst` with attributes hidden | system | **directory**, so hidden and system files,
  directories and wildcard patterns are all found.
- **A miss continues only for the codes in a 25-entry table.** The table is: 2, 3, 18, 206, 26;
  then 12, 54, 56, 57, 58, 59, 60, 64, 66, 69, 71, 86, 240, 51, 53, 55, 67, 71, 65, 5 (71 twice
  in IBM's data).
- **How much of the table is scanned depends on the width:**
  - 16-bit: 5 entries, or 25 with the network bit;
  - 32-bit: 10 entries, or 50 words with the network bit, so the 32-bit entry continues on 12
    (`ERROR_INVALID_ACCESS`) and 54, 56, 57, 58 (network) even without the bit. Past entry 25
    the image holds no error code, but at run time word 25 is set to 36
    (`ERROR_SHARING_BUFFER_EXCEEDED`) by DOSCALL1's initialisation, so with the bit the 32-bit
    entry also continues on 36.
  - At the 32-bit entry's implied-current-directory try, the bit that is tested is not reloaded
    from the flag: the register still holds a buffer address there. That site's scan length is
    therefore not established.
- Any other code ends the search and is returned.

**Result:** passed through `DosCanonicalize`, whose body was not read. What it does is under
"Measured" below. The drive letter is upper-cased earlier, when the element is built
(`& 0xDF`).

**Measured, [OBS]** (WSeB 4.52 CP2, 2026-09-30, both widths identical):
- **Current directory:** a hit there returns a fully qualified name.
- **Elements:** an empty element finds the file in the current directory; `/` separators work; a
  quoted element containing `;` works.
- **What matches:** a directory name, a hidden file and `SPF*.TXT` are found; the wildcard stays
  in the result.
- **Canonical spelling:** `C:\.\OS2`, `C:\OS2\SYSTEM\..`, `C:\OS2\` and `C:\OS2\.` all give
  `C:\OS2\ATTRIB.EXE`, and `c:\os2` gives `C:\os2\ATTRIB.EXE`. So `.` and `..` components and
  doubled `\` go, the drive letter is upper-cased, and directory spelling is kept. `..` at the
  root and UNC names were not measured.
- **An element on an unassigned drive does not end the search.** `DosFindFirst` itself answers 3
  for `Z:\ATTRIB.EXE` and `Q:\ATTRIB.EXE`, not 15, and 3 continues.
- **Error returns:**
  - a NULL or empty path -> 2; a missing variable -> 203; reserved bits -> 87;
  - `cbBuf` 0 -> 111 with the buffer untouched;
  - a buffer one byte short of the result -> 2;
  - a 4-byte buffer -> 111 even for a file that exists nowhere.
- **The width-specific 87s:** a 16-bit buffer at offset 0xFFF0 with length 0x20, and a 32-bit
  length of 0x10000.
- **After any failure** except `cbBuf` 0, the buffer's first byte is 0.

## Sources opened
- `README.md`, `memory-model.md` (house style).
- section 14 only: Toolkit `bsedos.h:1790`, Open Watcom 1.9 `h/os21x/bsedos.h:360`, IBM `cp1`/`cpgref`
  "DosShutdown"; the kernel 14.104a `w_Shutdown`, `ShutdownCheck`, `ShutdownBlock`, `SFLock`,
  `SFLockNoSD` and `w_DevIOCtl` (disassembly), and the SMP decompiles of the same; IBM *OS/2
  Debugging Handbook* table 116 (`sf_flags`); EDM/2 "FS_SHUTDOWN"; XWorkplace `src/startshut/
  shutdown.c` (`xsdFinishStandardReboot`, `xsdFinishStandardMessage`) and `apm.c`
  (`apmPreparePowerOff`, `apmDoPowerOff`, `acpiPreparePowerOff`, `acpiDoPowerOff`); xwphelpers
  `src/helpers/apmh.c` (`apmhOpen`); an annotated disassembly of the kernel's `filesys/opncreat.asm` (the
  in-flight count).
- section 13 only: Toolkit `bsedos.h:1498` (`#define DosQVerify DosQueryVerify`), `:1730`/`:1732` (the 32-bit
  prototypes), `bseerr.h:170` (118); Open Watcom 1.9 `h/os21x/bsedos.h:348`/`:359` (the 16-bit
  prototypes); IBM `cp1` (*Control Program Programming Reference*) and `cpgref` (*CP Guide and
  Reference*) "DosSetVerify" and `cp1` "DosQueryVerify" (neither book has a `DosQVerify` page; only its
  prototype and the Toolkit alias were opened for it) - Syntax, Parameters, Return Value, Remarks;
  the kernel 14.104a SMP
  decompiles `w_SetVerify`, `f_w_SetVerify` (a 2-byte entry falling into it) and `h_w_QVerify`, and the
  UNI debug kernel's; the PTDA structure (`VerFlg` at +0x43E) and the exec-path field inheritance from
  the same kernel's reverse-engineered notes.
- section 12 only: `bsedos.h:1493-1494` (the two compatibility `#define`s) and `:1705`/`:1734`/`:1736`
  (the 32-bit prototypes); `bsedos16.h:847`, `:854`, `:1046-1047`, `:1049-1050`, `:1059` (the
  16-bit prototypes and the internal-name mapping) - and the same file is the source of the
  NEGATIVE result that no 16-bit `DosSetRelMaxFH` exists (`RelMaxFH` occurs zero times in it),
  cross-checked against Open Watcom 1.9 `h/os21x/bsedos.h`, which declares only
  `DosSetMaxFH(USHORT)`; IBM *Control Program Programming Reference* `cp1`/`cpgref`
  "DosSetDefaultDisk" and "DosSetMaxFH" (Syntax, Parameters, Return Value, Remarks and
  Example Code) for the documented contracts, including the two Remarks clauses section 12.2
  refutes; and the kernel's own `pre_sci(N)` entry stubs for `DOSSELECTDISK`, `DOSSETMAXFH`
  and `DOSQCURDISK`, read from decompiles of all four kernel builds.
  The section 12 measurements are two paired probes run on Warp Server for e-business (kernel
  Internal revision 14.089) on 2026-09-05, at both ABI widths on the same machine minutes
  apart. **Every value in both tables is a line of retained program output**, including the
  ceiling and current-count block - an earlier draft of section 12.2 quoted those two findings from
  a throwaway probe that no longer existed, which `README.md` makes a misuse of the `[OBS]`
  tag rather than a thin citation: a firsthand result with nothing retained is `[OBS-USER]`,
  and it names an observer. The sweep was folded into the paired probe and re-captured in
  full rather than appended.
- `bsedos.h` - all prototypes, constants, and `FILESTATUS*` /
  `FILEFINDBUF*` / `FILELOCK` / `FDATE` / `FTIME` / `FSINFO` layouts.
- `bseerr.h` - error-code values.
- IBM *Control Program Programming Reference* (`cpgref`) "Long File Names" (the `NEWFILES`
  rule and its thirteen-function rejection list), "DosCreateDir" / "DosSetCurrentDir" /
  "DosQueryCurrentDir" Remarks; `newexe.h` (`NELONGNAMES`). The section 11 table is a live
  measurement on Warp 4.50.
- `os2def.h` - `HFILE` / `LHANDLE` types.
- section 6.1 only: the **16-bit** prototypes Open Watcom 1.9 `h/os21x/bsedos.h:321,335`; the DDK's MASM
  prototypes DDK `EXE/MASM60/ddktools/toolkits/masm60/include/BSEDOS.INC:678,745`, the only
  source that states the FAR PASCAL convention and so fixes the argument order; the kernel's own
  `pre_sci(N)` entry stubs for `DOSDELETE` / `DOSMOVE`, read from kernel decompiles; and the measurement itself,
  a 16-bit `DosDelete`/`DosMove` probe on Warp Server for e-business, 2026-08-26.
  The negative result recorded there - that no IBM prose on the measuring system states what a nonzero
  `ulReserved` does - was established by searching `cpgref`/`cp1`/`cp2`/`cp3`, the Toolkit 4.5
  `BOOK/` set and the DDK.
- IBM *Control Program Programming Reference* (`prcp`): `DosFileLocks`, `DosDupHandle` pages - lock
  and duplicate-handle behavioural remarks. Also `112_L2_DosQFileMode.html` - the **16-bit**
  edition's page for ordinal 75, which supplies that call's *"Reserved must be set to zero"* and
  its published return-code list (2, 3, 26, 87, 108, 206) for section 6.1 and section 10.1. **`prcp` is the only
  edition on the measuring system that documents 16-bit signatures**, and it has now been omitted from a
  "no IBM prose exists" search set twice (ordinals 60/67 in section 6.1, and again for
  ordinal 75 in the probe's own case table, project-side).
- section 10.1: the measurement is a 16-bit `DosQFileMode` probe (Warp 4.50,
  2026-08-30), corroborated on a second ordinal by section 11's own `DosQueryPathInfo` observation.
- section 7.3-7.5: the measurements are three probe captures - 16-bit and 32-bit `DosSetFileInfo`,
  and 32-bit `DosSetPathInfo` (Warp Server for e-business `14.097_UNI`, HPFS `C:`,
  2026-08-31) - one run of one binary per arm, the first two differing in nothing but the ABI, and
  the third measuring the by-path entry point separately rather than inheriting it from its
  handle-form sibling. section 7.4a rests on cases that cross two axes at once; the single-axis sweeps
  that preceded them could not observe precedence and reported a wrong order as untested. The RE half is the DOSCALL1
  and kernel decompiles named inline (unpublished notes). The IBM prose half
  is **`prcp` "DosSetFileInfo"**, the 16-bit edition's page - and that is the THIRD time this
  file's own Sources warning has had to be applied: the section 7.3 draft asserted "IBM's own reference
  documents none of the 16-bit form" from a `cpgref`-only search, and `prcp` documents the
  prototype, the `FILESTATUS` record, the return-code list and the Remarks. **Search `prcp` before
  writing that no IBM prose exists for a 16-bit call.**
- EDM2 (community wiki) reference pages - behavioural remarks and per-call return codes for
  `DosClose (FAPI)`, `DosCopy (OS/2 1.x)`, `DosFindClose (OS/2 1.x)`, `DosSetFHandState`, and
  `DosBufReset`.
- section 8 device names, `COMn`/`LPTn` placeholders, `PRN` and the `:` rule (2026-10-14):
  - **Measurement:** one probe program run as `PROTSHELL` on Warp 4.50 WSeB (SMP kernel), in two
    boots, with and without `PRINT01.SYS` and `COM.SYS`.
  - **Bytes:** the SMP 14.104a kernel's character-device table inserters, its path canonicaliser and
    its character-class table, and the LAN Requester's `RDRHELP.200` (version stamp
    `IBM:53.44`, 2001) headers and strategy routine.
  - **IBM:** DDK `devhlp.inc` for `DevHlp_AttachDD` = 2Ah, and the PDD reference's status-code table.
