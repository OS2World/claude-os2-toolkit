# OS/2 Extended Attributes

An **extended attribute** (EA) is a named piece of out-of-band metadata that an OS/2 file
system attaches to a file object (a file or a directory), stored and maintained by the file
system separately from the file's own data. Level 1 file information - name, size, and the
creation/access/write timestamps - is the fixed set every file object carries; EAs are the
open-ended extension. A file object may carry any number of EAs; each EA is a **name / value**
pair whose value can be text, a bitmap, an icon, or arbitrary binary data, and whose format is a
contract between the applications that write and read it (the file system does not interpret the
value). Each EA can be up to 64 KB, and the sum of all EAs on one file object must not exceed
64 KB. This reference describes the wire structures through which EAs are passed (`FEA2` / `GEA2`
and their lists, `EAOP2`), the data-type value convention (the `EAT_*` prefix), the ten Standard
Extended Attributes, and the Control-Program functions and info levels that read and write EAs.

Provenance: **[DOC-IBM]** the OS/2 Control Program Guide and Reference (`cpgref.inf`) for the EA
model, the data-type conventions, the Standard Extended Attributes, and the per-function info-level
semantics; **[DOC-IBM]** the OS/2 Toolkit 4.5 header `bsedos.h` for every structure layout,
constant value, and function prototype (each cited `file:line`); **[DOC-IBM]** `pmwin.h` for the
`.ASSOCTABLE` ownership flags. Where the book supplies meaning and the header supplies the value,
both are cited.

---

## 1. The EA model [DOC-IBM]

An EA is metadata the file system keeps for a file object but keeps *outside* the file's data
stream. EAs live on the same volume as the file object and are connected to it by the file system;
they are not part of the file's bytes and are not seen when the file is read. Every EA has:

- a **name** - a NUL-terminated string, restricted to the legal file-name character set. An EA
  name of length 0 is illegal and causes EA functions to fail.
- a **value** - an opaque byte string the file system never inspects. By convention (Section 3)
  the value begins with a type word.

An EA **value length of 0 is special**: *setting* an EA with a zero-length value **deletes** that
EA if possible; *getting* an EA and receiving a zero-length value means the EA **is not present**
on the object.

EAs are supported by the OS/2 High Performance File System and by the OS/2 FAT file system from
OS/2 1.2 onward; they are not supported by the pre-1.2 FAT file system or by DOS. Because EAs are
stored separately, they are lost when a file object is moved to a volume whose file system does
not support them, or handled by a tool that does not preserve them; the `EAUTIL` utility exists to
split EAs into a hold file and reattach them so EA-unaware tools can process the file safely.

The six Control-Program functions that manipulate EAs are `DosOpen`, `DosFindFirst` (with
`DosFindNext`), `DosQueryFileInfo`, `DosQueryPathInfo`, `DosSetFileInfo`, and `DosSetPathInfo`;
`DosEnumAttribute` enumerates EA names/sizes, `DosCreateDir` sets EAs on a new directory, and the
`DosProtect*` variants add a file-handle lock token. Provenance: **[DOC-IBM]** `cpgref.inf`
"Extended Attributes", "About Extended Attributes", "Managing Extended Attributes".

### EA concurrency and consistency [DOC-IBM]

EAs inherit the sharing/access protection of the file object they belong to. Handle-based access
follows the open mode: a file open for read permits *querying* EAs, a file open for write permits
*setting* EAs. Path-based access adds the object to the sharing set for the duration of the call -
querying (`DosQueryPathInfo`) requires read access and deny-write sharing, setting
(`DosSetPathInfo`) requires write access and deny-read-write sharing; the call fails if another
process holds conflicting rights. EA operations are **not atomic**: if an error occurs partway
through setting a list, some, all, or none of the EAs may remain set, and the returned `oError`
identifies the offending list entry. Provenance: **[DOC-IBM]** `cpgref.inf` "Controlling Access to
Extended Attributes".

### Critical EAs and EA-aware programs [DOC-IBM]

An EA is **non-critical by default**. An EA is marked **critical** by setting **bit 7 of the flags
byte** of its `FEA2` (the symbolic constant is `FEA_NEEDEA`, Section 2). A file "has critical EAs"
if at least one of its EAs is critical (directories' EAs cannot be marked critical). A program that
does not recognise EAs is barred from operations it could not complete correctly on a file with
critical EAs - notably a non-truncating open - but may still delete such files. A program declares
itself EA-aware (and long-name-aware) with the `NEWFILES` declaration in its module-definition
file. Provenance: **[DOC-IBM]** `cpgref.inf` "Protecting Extended Attributes"; the flag value is
`bsedos.h`.

---

## 2. The EA structures [DOC-IBM]

Two structure families exist. The original `FEA`/`GEA` family (used by the level-0/1 `EAOP` block)
is retained for source compatibility; **all current EA APIs use the `FEA2`/`GEA2` family** through
an `EAOP2` block. The `FEA2`/`GEA2`/`EAOP2` group is declared under `#pragma pack(1)`
(`bsedos.h:1153,1220`), so the layouts below are byte-packed.

| Symbol | Role |
|---|---|
| `GEA2` | A *Get EA* - one EA **name** to fetch. |
| `GEA2LIST` | A length-prefixed list of `GEA2` - the set of names to fetch. Query input. |
| `FEA2` | A *Full EA* - one EA's flags, **name, and value**. |
| `FEA2LIST` | A length-prefixed list of `FEA2` - the EAs returned by a query, or the EAs to set. |
| `EAOP2` | The operation block binding a `GEA2LIST`, an `FEA2LIST`, and an error offset. The parameter every EA API takes. |
| `DENA1` | The name/size record returned by `DosEnumAttribute` (level 1). |

### `GEA2` / `GEA2LIST` - the names to fetch [DOC-IBM `bsedos.h:1174-1187`]

```c
typedef struct _GEA2 {          /* gea2 */
    ULONG   oNextEntryOffset;   /* 0x00: bytes to next GEA2, 0 = last  */
    BYTE    cbName;             /* 0x04: name length, excluding NUL    */
    CHAR    szName[1];          /* 0x05: ASCIIZ attribute name         */
} GEA2;

typedef struct _GEA2LIST {      /* gea2l */
    ULONG   cbList;             /* total size of the list, incl. cbList */
    GEA2    list[1];
} GEA2LIST;
```

A `GEA2` names a single EA to retrieve; `cbName` is the name length **not** counting the trailing
NUL. Entries in a `GEA2LIST` are doubleword-aligned and chained by `oNextEntryOffset` (bytes from
the start of the current entry to the start of the next); the last entry's `oNextEntryOffset` is
**0**. A `GEA2LIST` is a required *input* to the query functions (`DosQueryFileInfo`,
`DosQueryPathInfo`, and the level-3 `DosFindFirst`). Provenance: layout **[DOC-IBM]**
`bsedos.h:1174-1187`; semantics **[DOC-IBM]** `cpgref.inf` "Get Extended Attribute (GEA2) Data
Structure".

### `FEA2` / `FEA2LIST` - the full EAs [DOC-IBM `bsedos.h:1156-1172`]

```c
typedef struct _FEA2 {          /* fea2 */
    ULONG   oNextEntryOffset;   /* 0x00: bytes to next FEA2, 0 = last     */
    BYTE    fEA;                /* 0x04: flags (FEA_NEEDEA = critical)    */
    BYTE    cbName;             /* 0x05: name length, excluding NUL       */
    USHORT  cbValue;            /* 0x06: value length in bytes            */
    CHAR    szName[1];          /* 0x08: ASCIIZ name, then the value      */
} FEA2;

typedef struct _FEA2LIST {      /* fea2l */
    ULONG   cbList;             /* total size of the list, incl. cbList   */
    FEA2    list[1];
} FEA2LIST;
```

The 8-byte `FEA2` header is followed by the name (`cbName` bytes plus a terminating NUL) and then
the value (`cbValue` bytes). `cbName` excludes the NUL; `cbValue` is the raw value length. Entries
are doubleword-aligned and chained by `oNextEntryOffset` (0 in the last). An `FEA2LIST` is the
*output* of the query functions and the required *input* to the set functions. On a query, a
returned `cbValue` of 0 means the named EA is not present; on a set, a `cbValue` of 0 deletes the
EA. Provenance: layout **[DOC-IBM]** `bsedos.h:1156-1172`; semantics **[DOC-IBM]** `cpgref.inf`
"Full Extended Attribute (FEA2) Data Structure".

**`fEA` flag** [DOC-IBM `bsedos.h:1135`]:

| Constant | Value | Meaning |
|---|---|---|
| `FEA_NEEDEA` | `0x80` | Bit 7 of the flags byte - the EA is **critical** (its loss would break the application/system). Clear = non-critical (the default). |

### `EAOP2` - the operation block [DOC-IBM `bsedos.h:1189-1195`]

```c
typedef struct _EAOP2 {         /* eaop2 */
    PGEA2LIST   fpGEA2List;     /* 0x00: the GEA2 set (names to get)    */
    PFEA2LIST   fpFEA2List;     /* 0x04: the FEA2 set (full EAs)        */
    ULONG       oError;         /* 0x08: offset of the FEA2/GEA2 in error */
} EAOP2;
```

Every EA-bearing API takes a pointer to an `EAOP2`. Which of the two list pointers is used, and in
which direction, depends on the operation (Sections 4-6): a *get-by-list* fills `fpGEA2List` with
the names wanted and receives the results through `fpFEA2List`; a *set* fills `fpFEA2List` with the
EAs to write and ignores `fpGEA2List`. On an error during a set, `oError` is the offset of the
`FEA2` entry that failed; on a level-3 get, `oError` points to the `GEA2` entry that failed.
Provenance: layout **[DOC-IBM]** `bsedos.h:1189-1195`; semantics **[DOC-IBM]** `cpgref.inf` "EAOP2"
and the per-function InfoLevel descriptions.

### Legacy `FEA` / `GEA` / `EAOP` family [DOC-IBM `bsedos.h:1112-1150`]

The original 16-bit-era structures are still declared: `GEA` `{ BYTE cbName; CHAR szName[1]; }`,
`GEALIST` `{ ULONG cbList; GEA list[1]; }`, `FEA` `{ BYTE fEA; BYTE cbName; USHORT cbValue; }`,
`FEALIST` `{ ULONG cbList; FEA list[1]; }`, and `EAOP` `{ PGEALIST fpGEAList; PFEALIST fpFEAList;
ULONG oError; }`. The `*2` forms add the `oNextEntryOffset` chaining field; `FEA2` also adds an
in-line `szName` (legacy `FEA` has no name field - the name is implied by position), whereas legacy
`GEA` already carries `szName[1]`. Current code uses the `FEA2`/`GEA2`/`EAOP2` family. Provenance: **[DOC-IBM]**
`bsedos.h:1112-1150`.

---

## 3. EA value data types - the `EAT_*` convention [DOC-IBM]

So that a reader can interpret an EA value it did not write, the **first WORD of an EA value
specifies its data type**. For the length-preceded types, that WORD is followed by a length word
and then the data. Values `0x8000` and up are reserved; `0x0000`-`0x7FFF` are user-definable
(user-defined types should also be length-preceded). Symbolic constants are in `bsedos.h`.

| Constant | Value | Meaning |
|---|---|---|
| `EAT_BINARY` | `0xFFFE` | Binary (non-text) data; a length WORD follows the type WORD. |
| `EAT_ASCII` | `0xFFFD` | ASCII text; length-preceded. |
| `EAT_BITMAP` | `0xFFFB` | Bitmap data; length-preceded. |
| `EAT_METAFILE` | `0xFFFA` | Metafile data; length-preceded. |
| `EAT_ICON` | `0xFFF9` | Icon data; length-preceded. |
| `EAT_EA` | `0xFFEE` | ASCIIZ **name of another EA** on the same file whose contents are to be included in place; length-preceded. |
| `EAT_MVMT` | `0xFFDF` | **Multi-valued, multi-typed** - two or more values, each with its own type word. |
| `EAT_MVST` | `0xFFDE` | **Multi-valued, single-typed** - two or more values, all one type. |
| `EAT_ASN1` | `0xFFDD` | ASN.1 field data (the ISO standard for describing multi-valued data streams). |

Provenance: values **[DOC-IBM]** `bsedos.h:1207-1216`; meaning **[DOC-IBM]** `cpgref.inf`
"Extended Attribute Data Type Conventions". (`0xFFFC` is defined as unused, `bsedos.h:1204`.)

A single-valued length-preceded example - the string `"Hello"`:

```
EAT_ASCII  0005  H e l l o
 (WORD)   (WORD)
```

### Multi-valued layouts [DOC-IBM]

**`EAT_MVMT`** - each value carries its own type:

```
EAT_MVMT  Codepage  NumEntries  [ DataType  <value> ] ...
 WORD      WORD       WORD          WORD
```

**`EAT_MVST`** - one type word governs all values:

```
EAT_MVST  Codepage  NumEntries  DataType  [ <value> ] ...
 WORD      WORD       WORD        WORD
```

`Codepage` names the code page of the value text (0 = the file default; the operating system does
not itself examine EA code-page information); `NumEntries` is the count of values. Whether each
value is itself length-preceded depends on its data type. When a "default" applies to a
multi-valued EA, the **first** entry is the default. Provenance: **[DOC-IBM]** `cpgref.inf`
"Multi-Value Data Type Fields", "Multi-Valued, Multi-Typed Data Type", "Multi-Valued, Single-Type
Data Type".

---

## 4. Reading and writing EAs by name/handle [DOC-IBM]

### The info levels [DOC-IBM `bsedos.h:742-751`]

`DosQueryPathInfo`, `DosQueryFileInfo`, `DosSetPathInfo`, and `DosSetFileInfo` all take a `ULONG`
info level; the EA-relevant levels are:

| Constant | Value | Structure in the buffer | Use |
|---|---|---|---|
| `FIL_STANDARD` | `1` | `FILESTATUS3` (query) / `FILESTATUS3` (set) | Level 1 file information - no EAs. |
| `FIL_QUERYEASIZE` | `2` | `FILESTATUS4` on query; `EAOP2` on set | Query: report the **total EA size**. Set: write a list of EAs. |
| `FIL_QUERYEASFROMLIST` | `3` | `EAOP2` | Query only: return the **values** of a named list of EAs. |
| `FIL_QUERYFULLNAME` | `5` | ASCIIZ path (path APIs only) | Fully-qualified name. (Level 4 is simply *absent* from the Toolkit headers - not defined; "reserved" would be an inference. The DDK's 16-bit `bsedos16.h` does define `FIL_QUERYALLEAS` 4, for the find calls - see section 6.) |

Large-file (`>2 GB`) analogues are `FIL_STANDARDL` (11), `FIL_QUERYEASIZEL` (12), and
`FIL_QUERYEASFROMLISTL` (13), using `FILESTATUS3L`/`FILESTATUS4L`. Provenance: **[DOC-IBM]**
`bsedos.h:742-751`; per-level semantics **[DOC-IBM]** `cpgref.inf` "DosQueryPathInfo",
"DosSetPathInfo", "DosQueryFileInfo", "DosSetFileInfo".

### `FILESTATUS4` - level-2 query result carries the EA size [DOC-IBM `bsedos.h:1416-1429`]

```c
typedef struct _FILESTATUS4 {   /* fsts4 */
    FDATE  fdateCreation;   FTIME  ftimeCreation;
    FDATE  fdateLastAccess; FTIME  ftimeLastAccess;
    FDATE  fdateLastWrite;  FTIME  ftimeLastWrite;
    ULONG  cbFile;          /* file size                                   */
    ULONG  cbFileAlloc;     /* allocated size                              */
    ULONG  attrFile;        /* standard attribute bits                     */
    ULONG  cbList;          /* size, in bytes, of the file's entire EA set */
} FILESTATUS4;
```

`FILESTATUS4` is `FILESTATUS3` (`bsedos.h:1402-1413`) plus the trailing `cbList`. A level-2 query
returns in `cbList` the size of the **entire** EA set on disk. This is the sizing step: the buffer
needed to hold the EAs from a level-3 query is **less than or equal to twice** `cbList`.
Provenance: layout **[DOC-IBM]** `bsedos.h:1416-1429`; semantics **[DOC-IBM]** `cpgref.inf`
"DosQueryPathInfo" (Level 2 File Information).

### The query functions [DOC-IBM]

| Symbol | Prototype (from `bsedos.h`) | EA behaviour |
|---|---|---|
| `DosQueryPathInfo` | `APIRET DosQueryPathInfo(PSZ pszPathName, ULONG ulInfoLevel, PVOID pInfoBuf, ULONG cbInfoBuf)` | By **name**. Level 2 -> `FILESTATUS4.cbList` = total EA size. Level 3 -> caller supplies `EAOP2.fpGEA2List` (names), receives EAs through `EAOP2.fpFEA2List`. |
| `DosQueryFileInfo` | `APIRET DosQueryFileInfo(HFILE hf, ULONG ulInfoLevel, PVOID pInfo, ULONG cbInfoBuf)` | By open **handle**; same info-level semantics. |
| `DosProtectQueryFileInfo` | `... , FHLOCK fhFileHandleLockID)` | Handle form with a file-handle lock token. |

For a level-3 query: on **input** `pInfoBuf` is an `EAOP2` whose `fpGEA2List` points to the
(doubleword-aligned, `oNextEntryOffset`-chained, last-entry-zero) list of names to fetch and whose
`fpFEA2List` points to a buffer whose leading `cbList` gives the buffer size; `oError` is ignored.
On **output** the `fpFEA2List` buffer is filled with the matching `FEA2`s. If a requested EA is not
attached, its `FEA2` is returned with `cbValue` = 0. If the buffer is too small the call returns
`ERROR_BUFFER_OVERFLOW` and `cbList` is still valid (the full on-disk EA size). Provenance:
prototypes **[DOC-IBM]** `bsedos.h:1739-1748,1761-1771`; semantics **[DOC-IBM]** `cpgref.inf`
"DosQueryPathInfo"/"DosQueryFileInfo" (Level 3 File Information).

### The set functions [DOC-IBM]

| Symbol | Prototype (from `bsedos.h`) | EA behaviour |
|---|---|---|
| `DosSetPathInfo` | `APIRET DosSetPathInfo(PSZ pszPathName, ULONG ulInfoLevel, PVOID pInfoBuf, ULONG cbInfoBuf, ULONG flOptions)` | By **name**, level 2. `pInfoBuf` is an `EAOP2`; `fpFEA2List` points to the EAs to set; `fpGEA2List` and `oError` are ignored on input. |
| `DosSetFileInfo` | `APIRET DosSetFileInfo(HFILE hf, ULONG ulInfoLevel, PVOID pInfoBuf, ULONG cbInfoBuf)` | By open **handle**; same. |
| `DosProtectSetFileInfo` | `... , FHLOCK fhFileHandleLockID)` | Handle form with a lock token. |

A level-2 set writes a series of EA name/value pairs from the `FEA2LIST`. The `FEA2` entries must
be doubleword-aligned and `oNextEntryOffset`-chained with a 0 in the last. An entry with `cbValue`
= 0 **deletes** that EA. On error, `oError` is the offset of the failing `FEA2`. `DosSetPathInfo`'s
`flOptions` accepts `DSPI_WRTTHRU` (`0x10`, `bsedos.h:1788`), which forces the EAs to be flushed to
disk before the call returns; all other bits are reserved and must be zero. Provenance: prototypes
**[DOC-IBM]** `bsedos.h:1750-1759,1773-1785`; semantics **[DOC-IBM]** `cpgref.inf` "DosSetPathInfo"
/ "DosSetFileInfo" (Level 2 File Information).

### Setting EAs at create time [DOC-IBM]

`DosOpen`'s final parameter is a `PEAOP2` (`bsedos.h:1264-1272`); the EAs in its `fpFEA2List` are
applied only when the open **creates, replaces, or truncates** the file - a plain open of an
existing file sets no EAs (`fpGEA2List` and `oError` are ignored). `DosCreateDir(PSZ pszDirName,
PEAOP2 peaop2)` (`bsedos.h:1692-1697`) attaches EAs to a directory at creation; passing a null EA
buffer creates the directory with no EAs. The `DosProtectOpen`/`DosProtectOpenL`/`DosOpenL`
variants carry the same `PEAOP2`. Provenance: prototypes **[DOC-IBM]** `bsedos.h:1264-1338`;
semantics **[DOC-IBM]** `cpgref.inf` "DosCreateDir", "DosOpen".

---

## 5. Enumerating EA names - `DosEnumAttribute` [DOC-IBM]

`DosEnumAttribute` identifies the **names and value-lengths** of a file object's EAs without
returning the values. It is the standard way to discover which EAs exist and to size the buffer for
a subsequent level-3 get.

```c
APIRET APIENTRY DosEnumAttribute(ULONG  ulRefType,   /* 0 = handle, 1 = path name */
                                 PVOID  pvFile,       /* &HFILE, or ASCIIZ name    */
                                 ULONG  ulEntry,      /* 1-based EA ordinal to start at */
                                 PVOID  pvBuf,        /* out: DENA1 records        */
                                 ULONG  cbBuf,
                                 PULONG pulCount,     /* in: #EAs wanted (-1 = all that fit); out: #returned */
                                 ULONG  ulInfoLevel); /* 1 (ENUMEA_LEVEL_NO_VALUE) */
```

| Constant | Value | Meaning |
|---|---|---|
| `ENUMEA_REFTYPE_FHANDLE` | `0` | `pvFile` addresses an open file handle. |
| `ENUMEA_REFTYPE_PATH` | `1` | `pvFile` is an ASCIIZ file or subdirectory name. |
| `ENUMEA_REFTYPE_MAX` | `1` | Highest valid ref type. |
| `ENUMEA_LEVEL_NO_VALUE` | `1` | The only valid info level - return names/lengths, no values. |

`ulEntry` is a 1-based ordinal into the object's EA list (0 is reserved); enumeration continues by
re-calling with `ulEntry` = previous start + returned count. On input `*pulCount` is the number of
EAs wanted (-1 = as many as fit in `pvBuf`); on output it is the number actually returned. Results
are a series of doubleword-aligned **`DENA1`** records. Provenance: prototype **[DOC-IBM]**
`bsedos.h:1792-1798`; constants **[DOC-IBM]** `bsedos.h:1829-1833`; semantics **[DOC-IBM]**
`cpgref.inf` "DosEnumAttribute".

### `DENA1` - the enumerated name record [DOC-IBM `bsedos.h:1813-1819`]

```c
typedef struct _DENA1 {   /* dena1 - packed */
    UCHAR   reserved;     /* 0x00: 0                              */
    UCHAR   cbName;       /* 0x01: name length, excluding NUL     */
    USHORT  cbValue;      /* 0x02: value length                   */
    UCHAR   szName[1];    /* 0x04: ASCIIZ attribute name          */
} DENA1;
```

> **Note on the source:** the Control Program reference's field-level *description* of the
> `DosEnumAttribute` output presents an `oNextEntryOffset`-chained record (like a `GEA2`); the
> version-correct Toolkit header defines the packed `DENA1` above (no `oNextEntryOffset` - entries
> are walked by `cbName`/`cbValue`). The header layout is authoritative here.

(The book calls the returned record `DENA2`; `bsedos.h:1822-1823` defines `typedef FEA2 DENA2;` -
so the historical `DENA1` above is the name/size record, while `DENA2` is an alias of `FEA2`.) From
a `DENA1` a caller computes the `FEA2` buffer size a level-3 get needs, per the formula: 4
(`oNextEntryOffset`) + 1 (`fEA`) + 1 (`cbName`) + 2 (`cbValue`) + `cbName` + 1 (name NUL) +
`cbValue`, each entry doubleword-aligned.

`DosEnumAttribute` does not lock the EA list. If the object is reachable by other processes (the
path-name case, or a handle opened in a shared mode), the list can change between calls and return
inconsistent results; to enumerate consistently, open the file **deny-write** first (a subdirectory
name needs no such protection, since no sharing is possible). `DosProtectEnumAttribute`
(`bsedos.h:1800-1807`) is the handle-lock variant. Provenance: **[DOC-IBM]** `bsedos.h:1813-1823`;
**[DOC-IBM]** `cpgref.inf` "DosEnumAttribute" (Notes).

---

## 6. Getting EAs through a directory search - `DosFindFirst` [DOC-IBM]

`DosFindFirst`/`DosFindNext` can return EA information alongside each matched directory entry, via
the `ulInfoLevel` argument (`bsedos.h:1536-1551`). The three levels IBM's books document reuse the
`FIL_STANDARD`/`FIL_QUERYEASIZE`/`FIL_QUERYEASFROMLIST` values from Section 4, but the buffer shape
differs by level. Every level always includes level-1 information for each entry.

> **CORRECTED (Rule 1.7):** this said *"The three EA-relevant levels"*. Those are the three the
> books describe, not the whole space. IBM's headers define more find levels, and two families name
> them differently: the 32-bit `bsedos.h` has `FIL_STANDARDL` 11, `FIL_QUERYEASIZEL` 12 and
> `FIL_QUERYEASFROMLISTL` 13 [DOC-IBM `bsedos.h:745-747`], and the 16-bit header has
> `FIL_QUERYALLEAS` 4, "return all EA's" [DOC-IBM DDK `base/h/bsedos16.h:509`]. Neither family
> defines the other's values. Level 13 is level 3's large-file twin: the same `EAOP2` frame and
> `FEA2LIST`, with the 64-bit `cbFile`/`cbFileAlloc` widening the header so the record starts with
> `FILEFINDBUF4L` where level 3's starts with `FILEFINDBUF4` [OBS-RE - DOSCALL1 handles 3/4 and
> 13/14 in shared code paths; measured on Warp Server for e-business 4.50, where an 8-character
> name landed at `0x24 + cbList`].

| Level | Value | Result buffer format |
|---|---|---|
| `FIL_STANDARD` | `1` | `FILEFINDBUF3` - entries chained by `oNextEntryOffset`; **no EAs**. |
| `FIL_QUERYEASIZE` | `2` | `FILEFINDBUF4` - level-1 fields plus **`cbList`** = the entry's total on-disk EA size. |
| `FIL_QUERYEASFROMLIST` | `3` | An `EAOP2` (input names) followed, per matched object, by the level-1 `FILEFINDBUF3` fields, the `cbList`, the returned `FEA2LIST`, and the object's name. |

`FILEFINDBUF4` (`bsedos.h:1057-1073`) is the level-2 form: it carries `oNextEntryOffset`, the six
date/time fields, `cbFile`, `cbFileAlloc`, `attrFile`, then **`cbList`** (the EA-set size), then
`cchName`/`achName`. (The older `FILEFINDBUF2`, `bsedos.h:1023-1038`, is the 16-bit-attribute
level-2 form with the same trailing `cbList`.) For a level-3 search the caller supplies an `EAOP2`
whose `fpGEA2List` names the EAs to fetch; on output the buffer holds, for each match, the EAOP2,
the `FILEFINDBUF3` fields, the `cbList`, an `FEA2LIST`, and the name. A requested EA that is absent
appears as an `FEA2` with a zero length. If the buffer cannot hold the first entry's EAs the call
returns `ERROR_EAS_DIDNT_FIT` (a search handle is still returned, and `DosQueryPathInfo` with the
same GEA list and the returned name can retrieve that entry's EAs). Provenance: prototype
**[DOC-IBM]** `bsedos.h:1536-1551`; `FILEFINDBUF4` **[DOC-IBM]** `bsedos.h:1057-1073`; semantics
**[DOC-IBM]** `cpgref.inf` "DosFindFirst" (ResultBuf, Level 1/2/3).

The idiomatic name search is a **two-pass** operation: call `DosFindFirst` at level 2 to obtain
`cbList` (the EA size, hence the buffer to allocate), then call at level 3 to obtain the EA values.
Provenance: **[DOC-IBM]** `cpgref.inf` "Searching for Extended Attributes".

---

## 7. The Standard Extended Attributes [DOC-IBM]

Conventionally-named EAs (Standard Extended Attributes, **SEAs**) - the reference enumerates ten of
them while its own prose says "nine" (a documented inconsistency in the source) - carry information many
applications share. **An SEA name begins with a dot (`.`)** - the leading dot is reserved, so
applications must not define their own EAs starting with a dot, and the characters `$`, `@`, `&`,
and `+` are reserved for system use. Where an SEA value is ASCII text, **case is significant**. To
keep application-specific EA names unique, IBM's convention is to prefix them with a company and
application abbreviation (e.g. `AB.STUFF`). Provenance: **[DOC-IBM]** `cpgref.inf` "Standard
Extended Attributes", "Extended Attribute Naming Conventions".

| SEA name | Purpose |
|---|---|
| `.TYPE` | The file object's file-type - a length-preceded ASCII string, similar to a file-name extension; used to pick a default program/icon and to bind the file to an `.ASSOCTABLE` entry. Predefined types include Plain Text, OS/2 Command File, DOS Command File, Executable, Metafile, Bit map, Icon, Binary Data, Dynamic Link Library, and various language source types. Writing `.TYPE` first is recommended for FIFO-EA file systems. |
| `.ASSOCTABLE` | Associates data files with the applications that create/use them: `EAT_MVMT` entries binding a `.TYPE` name, a file extension, an ownership flag, and `EAT_ICON` icon data. Built by the Resource Compiler from an `ASSOCTABLE` resource. |
| `.LONGNAME` | Holds a file object's original long name when it is stored on a file system that cannot represent it (so it can be restored on copy back to a long-name file system). |
| `.COMMENTS` | Miscellaneous notes/reminders about the file; may be multi-valued and of any type. (The book's body text spells the stored name `.COMMENT`.) |
| `.KEYPHRASES` | Key text phrases (ASCII), each in a separate multi-valued entry (`EAT_MVST`/`EAT_ASCII`); usable for database-style search. |
| `.SUBJECT` | A single-valued ASCII summary of the file's content/purpose; must be **fewer than 40 characters**. |
| `.HISTORY` | The file's modification history as an `EAT_MVMT`/ASCII multi-value list; each entry is `PERSON  ACTION(created/changed/printed)  DATE`. |
| `.ICON` | The physical icon (`EAT_ICON`) used to represent the file object; the data is a `BITMAPARRAYFILEHEADER` (as loaded by `GpiLoadBitmap`/`WinLoadPointer`). Overrides the `.TYPE`-derived default icon. |
| `.CODEPAGE` | The code page of the file (and, by default, of its EA data); absent -> system default or application-defined. |
| `.VERSION` | The file-format version number (ASCII or binary); only the creating application should modify it. |

Provenance: **[DOC-IBM]** `cpgref.inf` per-SEA sections ("The .TYPE Standard Extended Attribute",
etc.).

### `.ASSOCTABLE` ownership flags [DOC-IBM `pmwin.h:3541-3543`]

The flag field of an `.ASSOCTABLE` entry (an `EAT_BINARY` value) uses the `EAF_*` bits, which may
be OR-ed:

| Constant | Value | Meaning |
|---|---|---|
| `EAF_DEFAULTOWNER` | `0x0001` | The application is the default owner for data files of this `.TYPE` (double-click launches it). |
| `EAF_UNCHANGEABLE` | `0x0002` | The entry describing this file type cannot be edited. |
| `EAF_REUSEICON` | `0x0004` | Reuse the previous entry's icon (this entry defines no icon data of its own). |

Provenance: values **[DOC-IBM]** `pmwin.h:3541-3543`; meaning **[DOC-IBM]** `cpgref.inf` "The
.ASSOCTABLE Standard Extended Attribute".

---

## See also
- `file-io.md` - the Control-Program file API (`DosOpen`/`DosFindFirst`/`DosQueryPathInfo` ...)
  whose info levels carry EAs.
- `dasd-volume.md` - the file systems (HPFS, FAT) that store and preserve EAs.
