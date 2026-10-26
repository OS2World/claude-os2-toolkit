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
| `DosSetFileSize` | `(HFILE hFile, ULONG cbSize)` | Truncate or extend the file to `cbSize` bytes |
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

### 4.2 `DosSetFileSize` [DOC-IBM `bsedos.h:1612` for the prototype; `cp1.txt` "DosSetFileSize" for the contract]

Sets the file's length to `cbSize` - truncating (discarding data past the new end) or extending
it. When the file grows, **the contents of the new bytes are undefined** [DOC-IBM `cp1.txt`,
"DosSetFileSize - Remarks"; `DosOpen`'s remarks say the same of an initial `cbFile`].
`DosSetFileSizeL` is the 64-bit form. Requires write access.

> **CORRECTED (Rule 1.7):** this paragraph used to say *"extending (new bytes read back as
> zero)"*, citing `bsedos.h:1612`. A prototype cannot state a fill rule, and IBM's book says the
> opposite. Measured on Warp Server for e-business 4.50 (kernel revision 14.089, HPFS): a 16-byte
> file grown to 64 bytes read back 48 new bytes, none of them zero, through both the 16-bit and the
> 32-bit entry points [OBS-RE - measured]. **The tell:** code that grows a file and then reads the
> tail expecting zeros - write the zeros yourself. (An implementation that does zero-fill is still
> conformant; "undefined" admits zero.)

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

**The may-have bits do not all filter.** IBM's parameter text says each may-have bit (read-only,
hidden, system, directory, archived) includes files with that attribute when set and *excludes*
them when clear [DOC-IBM `cp1.txt`, "DosFindFirst Parameter - flAttribute"]. Observed behaviour
contradicts that for **read-only and archived**: `CMD.EXE`'s plain `dir` passes `flAttribute =
0x0016` (hidden, system, directory - no read-only, no archived), yet it lists read-only files and
archived files (nearly every file is archived) [OBS-RE - measured on Warp 4.50 by logging the
mask CMD's find call passes]. So read-only and archived files come back whatever the mask says;
only hidden, system and directory act as may-have inclusion bits. The must-have byte (bits 8-13)
was not measured separately; ordinary use has not contradicted IBM's description. **The tell:** a search that "should"
exclude read-only files returns them - filter on `attrFile` yourself. (`dir` hiding hidden and
system files is CMD's own display rule; the find call does return them under that mask.)

### 5.1 Find-buffer records [DOC-IBM `bsedos.h:1003-1108`; DDK `base/h/bsedos16.h:646-682`; `cp1.txt` "DosFindFirst Parameter - pfindbuf"]

The record written into `pfindbuf` depends on **two** things: `ulInfoLevel`, and **which ABI width
the caller used**. All records lead with the three date/time pairs and the two sizes; they differ in
attribute width, whether an EA-list size is present, and whether a next-entry offset chains packed
variable-length records.

> **CORRECTED (Rule 1.7) - the struct number is not the level number.** The list below used to
> read *"`FILEFINDBUF3` ... (level 3)"*, *"`FILEFINDBUF4` ... (level 4)"*, *"(levels 3/4) a
> next-entry offset"* and *"`FILEFINDBUF3L`/`FILEFINDBUF4L` ... (levels 11/13 counterparts)"*. All
> four were wrong. The type names run 1, 2, 3, 4 and invite reading them as level numbers, but IBM's
> `DosFindFirst` page says level 1 (`FIL_STANDARD`) returns `FILEFINDBUF3` and level 2
> (`FIL_QUERYEASIZE`) returns `FILEFINDBUF4` [DOC-IBM `cp1.txt`, "DosFindFirst Parameter -
> pfindbuf"], and the large-file levels are **11 and 12** (`FIL_STANDARDL`, `FIL_QUERYEASIZEL`;
> 13 is `FIL_QUERYEASFROMLISTL`) [DOC-IBM `bsedos.h:745-747`]. `extended-attributes.md`
> section 6 already had the level 1/2 mapping right.

| `ulInfoLevel` | 16-bit `DosFindFirst`/`DosFindFirst2`/`DosFindNext` | 32-bit `DosFindFirst`/`DosFindNext` |
|---|---|---|
| 1 `FIL_STANDARD` | `FILEFINDBUF` (name at +23) | `FILEFINDBUF3` (name at +29) |
| 2 `FIL_QUERYEASIZE` | `FILEFINDBUF2` (name at +27) | `FILEFINDBUF4` (name at +33) |
| 11 `FIL_STANDARDL` | `FILEFINDBUF3L` (name at +37) | `FILEFINDBUF3L` |
| 12 `FIL_QUERYEASIZEL` | `FILEFINDBUF4L` (name at +41) | `FILEFINDBUF4L` |

Only levels 1 and 2 narrow at 16 bits; the large-file records are the same in both widths. The
narrow types are what the 16-bit entry points return, which is why they live in the 16-bit header.
The 16-bit `DosFindFirst` has no level parameter at all (it is level 1 by construction); only
`DosFindFirst2` takes one, and `DosFindNext` takes none in either width - the record shape is fixed
when the search is opened [DOC-IBM DDK `base/h/bsedos16.h:986-994`]. The name offsets were measured
on Warp Server for e-business 4.50 (kernel revision 14.089) by filling the buffer with a sentinel
byte and finding where the matched name landed; the same fixture gave +23 to a 16-bit caller and
+29 to a 32-bit one [OBS-RE - measured]. Records are packed: the 32-bit level-1/2 records are
rounded up to a multiple of 4, the 16-bit level-1 record is not rounded, and the large-file records
are not rounded in either width [OBS-RE - measured, same run].

`FILEFINDBUF` (16-bit, level 1) - the base record the others extend:

| Field | Type | Notes |
|---|---|---|
| `fdateCreation` | `FDATE` | 2-byte packed date |
| `ftimeCreation` | `FTIME` | 2-byte packed time |
| `fdateLastAccess` / `ftimeLastAccess` | `FDATE` / `FTIME` | |
| `fdateLastWrite` / `ftimeLastWrite` | `FDATE` / `FTIME` | |
| `cbFile` | `ULONG` | Logical size |
| `cbFileAlloc` | `ULONG` | Allocated size |
| `attrFile` | `USHORT` | Attribute bits (section 3.1) |
| `cchName` | `UCHAR` | Length of `achName` |
| `achName` | `CHAR[CCHMAXPATHCOMP]` | Name (`CCHMAXPATHCOMP` = 256) |

- `FILEFINDBUF2` adds `ULONG cbList` (full EA-set size) before `cchName` (16-bit level 2).
- `FILEFINDBUF3` prepends `ULONG oNextEntryOffset` (offset to the next packed record, 0 = last)
  and **widens `attrFile` to `ULONG`** (32-bit level 1).
- `FILEFINDBUF4` = `FILEFINDBUF3` plus `ULONG cbList` (32-bit level 2).
- `FILEFINDBUF3L` / `FILEFINDBUF4L` are the large-file forms with `LONGLONG cbFile` /
  `cbFileAlloc` (levels 11 and 12).

`CCHMAXPATH` is 260 and `CCHMAXPATHCOMP` (single component, incl. NUL) is 256 [DOC-IBM
`bsedos.h:630,636`].

### 5.2 Packed date/time [DOC-IBM `bsedos.h:884-916`]

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

---

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

---

## 9. Byte-range locking - `DosSetFileLocks`

`DosSetFileLocks(hFile, pflUnlock, pflLock, timeout, flags)` atomically **unlocks** the range in
`*pflUnlock` and then **locks** the range in `*pflLock`; either pointer may be `NULL` (a
zero-filled range meaning "no operation"). A locked range denies read/write access to that region
by other openers of the file until it is unlocked; the lock is advisory between processes, not a
whole-file share mode (section 3.3 is the whole-file mechanism, ranges are the fine-grained one). [DOC-IBM
`bsedos.h:967`; DOC - CP Reference `DosFileLocks` remarks]

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
  `ERROR_ATOMIC_LOCK_NOT_SUPPORTED` (174) [DOC-IBM `bseerr.h:227`]. The individual `flags` bit
  values are not defined in `bsedos.h` and are omitted here rather than guessed. [unverified - exact `flags` bit constants]

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
| `ERROR_ATOMIC_LOCK_NOT_SUPPORTED` | `174` | Atomic lock requested where unsupported |

---

## Sources opened
- `README.md`, `memory-model.md` (house style).
- `bsedos.h` - all prototypes, constants, and `FILESTATUS*` /
  `FILEFINDBUF*` / `FILELOCK` / `FDATE` / `FTIME` / `FSINFO` layouts.
- `bseerr.h` - error-code values.
- `os2def.h` - `HFILE` / `LHANDLE` types.
- IBM *Control Program Programming Reference* (`prcp`): `DosFileLocks`, `DosDupHandle` pages - lock
  and duplicate-handle behavioural remarks.
- EDM2 (community wiki) reference pages - behavioural remarks and per-call return codes for
  `DosClose (FAPI)`, `DosCopy (OS/2 1.x)`, `DosFindClose (OS/2 1.x)`, `DosSetFHandState`, and
  `DosBufReset`.
