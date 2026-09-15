# OS/2 Unicode Conversion API (`Uni*`)

The `Uni*` conversion interface an application calls to translate text between a code page (a
byte-oriented character encoding such as PC code page 850) and **UCS-2** - the fixed-width 16-bit
Unicode representation OS/2 uses internally. It is one part of OS/2's Universal Language Support
(ULS), the same subsystem that supplies locale, collation, and character-classification services;
this reference covers only the codepage<->Unicode conversion half. The model is a small, explicit
one: a program creates a **conversion object** (`UconvObject`) that binds a named code set, then
drives byte-buffer conversions (`UniUconvToUcs` / `UniUconvFromUcs`) or null-terminated-string
conversions (`UniStrToUcs` / `UniStrFromUcs`) through it, and frees the object when done. The
Unicode side is always a sequence of `UniChar` (16-bit) elements; the code-page side is a sequence
of `char` bytes whose meaning is fixed by the code set named at object-creation time. Code sets are
named by UCS-2 strings of the form `IBM-nnn` (e.g. `IBM-850`, `IBM-1200` for UCS-2 itself), which
`UniMapCpToUcsCp` derives from a numeric code-page identifier of the kind the NLS surface reports
(see `config-and-environment.md`, `DosQueryCp`).

Provenance: **[DOC-IBM]** OS/2 Toolkit 4.5 headers `uconv.h` (all conversion prototypes, the
`uconv_attribute_t` / `conv_endian_t` / `udcrange_t` structures, the `enum uconv_esid`, the
`UCONV_OPTION_*` / `CVTTYPE_*` / `DSPMASK_*` / `ENDIAN_*` constants, the code-set name macros, and
the per-function return-code comments), `unidef.h` (the `UniChar` typedef and the ULS type/category
model), `ulserrno.h` (the `ULS_*` return-code values), `callconv.h` (`CALLCONV` linkage). **[DOC]**
EDM2 *Universal Language Support API (Unicode)*, *UniUconvToUcs*, and *UconvObject* pages
(behavioural detail - partial-conversion / pointer-advance semantics - not spelled out in the
header). Cross-references to the code-page NLS surface point at `config-and-environment.md`, not
duplicated here.

---

## 1. Function map [DOC-IBM - `uconv.h`]

| Function | Prototype | Purpose |
|---|---|---|
| `UniCreateUconvObject` | `(UniChar *code_set, UconvObject *uobj)` | Create a conversion object bound to the named code set; returns the object handle |
| `UniFreeUconvObject` | `(UconvObject uobj)` | Destroy a conversion object |
| `UniUconvToUcs` | `(UconvObject uobj, void **inbuf, size_t *inbytes, UniChar **outbuf, size_t *outchars, size_t *subst)` | Convert a code-page byte buffer **to** UCS-2 |
| `UniUconvFromUcs` | `(UconvObject uobj, UniChar **inbuf, size_t *inchars, void **outbuf, size_t *outbytes, size_t *subst)` | Convert a UCS-2 buffer **from** Unicode to the code page |
| `UniStrToUcs` | `(UconvObject co, UniChar *target, char *source, int len)` | Convert a null-terminated code-page string to UCS-2 |
| `UniStrFromUcs` | `(UconvObject co, char *target, UniChar *source, int len)` | Convert a null-terminated UCS-2 string to the code page |
| `UniQueryUconvObject` | `(UconvObject uobj, uconv_attribute_t *attr, size_t size, char first[256], char other[256], udcrange_t udcrange[32])` | Read an object's attributes and multibyte lead/other-byte tables |
| `UniSetUconvObject` | `(UconvObject uobj, uconv_attribute_t *attr)` | Set the settable attributes on an object |
| `UniMapCpToUcsCp` | `(unsigned long ulCodePage, UniChar *ucsCodePage, size_t n)` | Map a numeric code-page identifier to its `IBM-nnn` UCS-2 code-set name |

All return an `int` (`uconv_error_t`, `= int`); `0` = success. The Unicode-side type is
`UniChar` and the object handle type is `UconvObject`; both are defined in section 2.

---

## 2. The UCS-2 model, `UniChar`, and code-set names

**`UniChar`** is the unit of the Unicode side [DOC-IBM `unidef.h:41`, `uconv.h:27`]:

```c
typedef unsigned short UniChar;   /* a single UCS-2 code unit, 16 bits */
```

A Unicode string is a contiguous array of `UniChar`, conventionally null-terminated (a `UniChar` of
value 0) for the `UniStr*` helpers. OS/2's internal Unicode form is **UCS-2** - one 16-bit code
unit per character - not a variable-length encoding; the multibyte/UTF forms exist only as *code
sets* on the code-page side of a conversion (see the `esid` table, section 5). [DOC-IBM `uconv.h`]

**`UconvObject`** is the conversion-object handle [DOC-IBM `uconv.h:22`; DOC - EDM2 *UconvObject*]:

```c
typedef void *UconvObject;        /* opaque conversion-object handle */
```

It is an opaque pointer; a program obtains one from `UniCreateUconvObject` and never dereferences
it directly - its contents are read through `UniQueryUconvObject` and changed through
`UniSetUconvObject`.

**Code-set names** are themselves UCS-2 strings (`UniChar *`). `uconv.h` provides ready-made macros
for the common ones by casting wide-string literals (`wchar_t` is 16-bit here, so `L"..."` is
already an array of `UniChar`) [DOC-IBM `uconv.h:292-297`]:

| Macro | Expands to | Code set |
|---|---|---|
| `IBM_437` | `L"IBM-437"` | US PC code page 437 |
| `IBM_819` / `ISO8859_1` | `L"IBM-819"` | ISO 8859-1 (Latin-1) |
| `IBM_850` | `L"IBM-850"` | Multilingual PC code page 850 |
| `UTF_8` | `L"IBM-1208"` | UTF-8 |
| `UCS_2` | `L"IBM-1200"` | UCS-2 |

Any other supported code set is named by passing the corresponding `IBM-nnn` UCS-2 string to
`UniCreateUconvObject`; `UniMapCpToUcsCp` (section 7) builds that string from a numeric code page.

---

## 3. Object lifecycle - `UniCreateUconvObject` / `UniFreeUconvObject`

```c
int UniCreateUconvObject(UniChar *code_set, UconvObject *uobj);
int UniFreeUconvObject(UconvObject uobj);
```

`UniCreateUconvObject` allocates a conversion object bound to the code set named by the UCS-2 string
`code_set` and stores the handle in `*uobj`. The object records the code page and a default set of
conversion attributes (substitution options, endianness, conversion type, display mask - see section 6)
that later govern every conversion driven through it. `UniFreeUconvObject` releases the object.
[DOC-IBM `uconv.h:137-139,221-222`]

Return codes for `UniCreateUconvObject` [DOC-IBM `uconv.h:128-135`]:

| Code | Meaning |
|---|---|
| `0` | Object initialized |
| `UCONV_EMFILE` | Per-process open-file limit reached |
| `UCONV_ENFILE` | Too many files open system-wide |
| `UCONV_ENOMEM` | Insufficient memory |
| `UCONV_EINVAL` | The named code set / modifier is not recognized |

`UniFreeUconvObject` returns `0` or `UCONV_EBADF` (the handle is not a valid conversion object).
[DOC-IBM `uconv.h:216-222`]

---

## 4. Buffer conversion - `UniUconvToUcs` / `UniUconvFromUcs`

These are the core converters. They operate on **counted buffers** (not null termination) and use a
pointer-and-count model on both sides so a conversion can be resumed after a partial result.

```c
int UniUconvToUcs  (UconvObject uobj, void   **inbuf, size_t *inbytes,
                    UniChar **outbuf, size_t *outchars, size_t *subst);
int UniUconvFromUcs(UconvObject uobj, UniChar **inbuf, size_t *inchars,
                    void   **outbuf, size_t *outbytes, size_t *subst);
```

- `UniUconvToUcs` reads code-page bytes from `*inbuf` and writes `UniChar` elements to `*outbuf`;
  `*inbytes` is the input length **in bytes**, `*outchars` the output capacity **in `UniChar`
  elements**. [DOC-IBM `uconv.h:186-192`]
- `UniUconvFromUcs` is the reverse: `*inchars` `UniChar` elements in, code-page bytes out, with
  `*outbytes` the output capacity in bytes. [DOC-IBM `uconv.h:207-213`]
- `subst` returns the count of **non-identical conversions** - characters that had no exact mapping
  and were replaced by the substitution character (see the substitution options, section 6). [DOC-IBM
  `uconv.h:192`; DOC - EDM2 *UniUconvToUcs*]

**Pointer-advance / resumption semantics** [DOC - EDM2 *UniUconvToUcs*; DOC-IBM `uconv.h:172-213`
return-code comments]: on return the `in*`/`out*` pointers are advanced past the data consumed and
produced, and the `*inbytes`/`*inchars` and `*outchars`/`*outbytes` counts are decremented by the
amounts processed. If the whole input was converted, the input count reaches `0`; if conversion
stopped early, the input count is non-zero and the pointers mark exactly where it stopped, so the
caller can enlarge the output buffer (or handle the offending byte) and call again to continue.

Stop conditions are reported by the return code:

| Code | `UniUconvToUcs` / `UniUconvFromUcs` meaning |
|---|---|
| `0` | Entire input converted |
| `UCONV_EBADF` | `uobj` is not a valid conversion object |
| `UCONV_E2BIG` | Stopped: no room left in the output buffer |
| `UCONV_EINVAL` | Stopped: incomplete character / shift sequence at end of input |
| `UCONV_EILSEQ` | Stopped: an input byte does not belong to the input code set |

[DOC-IBM `uconv.h:174-205`]

---

## 5. Encoding schemes - `enum uconv_esid`

Each code set carries an **encoding-scheme identifier** describing its byte structure. It is
reported in the `esid` field of the object attributes (section 6) and is the primary check on whether a
code page is valid for a given use (process text, display, VIO, GPI). [DOC-IBM `uconv.h:59-81`]

| Enumerator | Value | Scheme |
|---|---|---|
| `ESID_sbcs_data` | `0x2100` | Single-byte, data |
| `ESID_sbcs_pc` | `0x3100` | Single-byte, PC |
| `ESID_sbcs_ebcdic` | `0x1100` | Single-byte, EBCDIC |
| `ESID_sbcs_iso` | `0x4100` | Single-byte, ISO |
| `ESID_sbcs_windows` | `0x4105` | Single-byte, Windows |
| `ESID_sbcs_alt` | `0xF100` | Single-byte, alternate |
| `ESID_dbcs_data` | `0x2200` | Double-byte, data |
| `ESID_dbcs_pc` | `0x3200` | Double-byte, PC |
| `ESID_dbcs_ebcdic` | `0x1200` | Double-byte, EBCDIC |
| `ESID_mbcs_data` | `0x2300` | Multi-byte, data |
| `ESID_mbcs_pc` | `0x3300` | Multi-byte, PC |
| `ESID_mbcs_ebcdic` | `0x1301` | Multi-byte, EBCDIC |
| `ESID_ucs_2` | `0x7200` | UCS-2 |
| `ESID_ugl` | `0x72FF` | UGL (Universal Glyph List) |
| `ESID_utf_8` | `0x7807` | UTF-8 |
| `ESID_upf_8` | `0x78FF` | UPF-8 |

---

## 6. Object attributes - `UniQueryUconvObject` / `UniSetUconvObject`

```c
int UniQueryUconvObject(UconvObject uobj, uconv_attribute_t *attr, size_t size,
                        char first[256], char other[256], udcrange_t udcrange[32]);
int UniSetUconvObject  (UconvObject uobj, uconv_attribute_t *attr);
```

`UniQueryUconvObject` fills `*attr` (the caller passes its size in `size`) with the object's current
attributes and, for multibyte code sets, fills the `first[256]` and `other[256]` byte-class tables
(which byte values are valid as a first byte vs. a subsequent byte of a multibyte character) and the
`udcrange[32]` array of user-defined character ranges. `UniSetUconvObject` writes back the settable
subset of `*attr`. [DOC-IBM `uconv.h:149-169`] Return codes: `0`, `UCONV_EBADF` (bad object), and -
for `UniSetUconvObject` - `UCONV_BADATTR` (an attribute value is invalid for this object). [DOC-IBM
`uconv.h:144-166`]

### 6.1 `uconv_attribute_t` [DOC-IBM `uconv.h:96-112`]

Fields are marked in the header as **Q** (query-only) or **Q/S** (query and set):

| Field | Type | Q/S | Meaning |
|---|---|---|---|
| `version` | `unsigned long` | Q/S | Structure version - must be zero |
| `mb_min_len` | `char` | Q | Minimum code-page character size (bytes) |
| `mb_max_len` | `char` | Q | Maximum code-page character size (bytes) |
| `usc_min_len` | `char` | Q | Minimum UCS size |
| `usc_max_len` | `char` | Q | Maximum UCS size |
| `esid` | `unsigned short` | Q | Encoding-scheme ID (section 5) |
| `options` | `char` | Q/S | Substitution options (section 6.2) |
| `state` | `char` | Q/S | State for stateful conversions |
| `endian` | `conv_endian_t` | Q/S | Source and target endianness (section 6.3) |
| `displaymask` | `unsigned long` | Q/S | Display/data control mask (section 6.4) |
| `converttype` | `unsigned long` | Q/S | Conversion type (section 6.5) |
| `subchar_len` | `unsigned short` | Q/S | MBCS substitution length (`0` = table default) |
| `subuni_len` | `unsigned short` | Q/S | Unicode substitution length (`0` = table default) |
| `subchar[16]` | `char` | Q/S | MBCS substitution character(s) |
| `subuni[8]` | `UniChar` | Q/S | Unicode substitution character(s) |

### 6.2 Substitution options - `options` [DOC-IBM `uconv.h:32-38`]

When a character has no exact mapping, the object either substitutes a replacement (counted in the
`subst` output, section 4) or stops with `UCONV_EILSEQ`, per these bits:

| Constant | Value | Meaning |
|---|---|---|
| `UCONV_OPTION_SUBSTITUTE_FROM_UNICODE` | `1` | Substitute when converting from Unicode |
| `UCONV_OPTION_SUBSTITUTE_TO_UNICODE` | `2` | Substitute when converting to Unicode |
| `UCONV_OPTION_SUBSTITUTE_BOTH` | `3` | Substitute in both directions |

### 6.3 Endianness - `conv_endian_t` [DOC-IBM `uconv.h:83-94`]

```c
typedef struct _conv_endian_rec {
    unsigned short source;   /* used by FromUcs */
    unsigned short target;   /* used by ToUcs   */
} conv_endian_t;
```

Each half takes one of: `ENDIAN_SYSTEM` (`0x0000`), `ENDIAN_BIG` (`0xFEFF`), `ENDIAN_LITTLE`
(`0xFFFE`). [DOC-IBM `uconv.h:86-88`]

### 6.4 Display mask - `displaymask` [DOC-IBM `uconv.h:47-57`]

A bit mask over the control codes `0x00`-`0x1F`: a set bit means the corresponding code is treated
as a control character, a clear bit means it is treated as a displayable glyph.

| Constant | Value | Meaning |
|---|---|---|
| `DSPMASK_DATA` | `0xFFFFFFFF` | All control codes are controls (data mode) |
| `DSPMASK_DISPLAY` | `0x00000000` | None are controls (display all as glyphs) |
| `DSPMASK_TAB` | `0x00000200` | Treat TAB as a control |
| `DSPMASK_LF` | `0x00000400` | Treat LF as a control |
| `DSPMASK_CR` | `0x00002000` | Treat CR as a control |
| `DSPMASK_CRLF` | `0x00002400` | Treat CR and LF as controls |

### 6.5 Conversion type - `converttype` [DOC-IBM `uconv.h:40-45`]

A bit mask selecting conversion behaviour:

| Constant | Value | Meaning |
|---|---|---|
| `CVTTYPE_CTRL7F` | `0x00000001` | Treat `0x7F` as a control |
| `CVTTYPE_CDRA` | `0x00000002` | Use CDRA control mapping |
| `CVTTYPE_PATH` | `0x00000004` | Treat the string as a path name |

### 6.6 User-defined character ranges - `udcrange_t` [DOC-IBM `uconv.h:117-120`]

```c
typedef struct {
    unsigned short first;   /* first code point */
    unsigned short last;    /* last code point  */
} udcrange_t;
```

`UniQueryUconvObject` returns up to 32 of these describing the object's user-defined-character code
point ranges.

---

## 7. Null-terminated string helpers - `UniStrToUcs` / `UniStrFromUcs`

```c
int UniStrToUcs  (UconvObject co, UniChar *target, char    *source, int len);
int UniStrFromUcs(UconvObject co, char    *target, UniChar *source, int len);
```

These are convenience forms for whole, **null-terminated** strings, without the caller managing the
pointer/count pairs of section 4. `UniStrToUcs` converts the code-page string `source` to UCS-2 in
`target`; `UniStrFromUcs` converts the UCS-2 string `source` to the code page in `target`. `len` is
the capacity of the `target` buffer - in `UniChar` elements for `UniStrToUcs`, in bytes for
`UniStrFromUcs` - and **the output buffer must be large enough to hold the terminating null**.
[DOC-IBM `uconv.h:242-276`]

Return codes [DOC-IBM `uconv.h:244-268`]:

| Code | Meaning |
|---|---|
| `0` | Converted successfully |
| `UCONV_EBADF` | Invalid conversion object |
| `UCONV_EILSEQ` | An unmappable character was hit with substitution off |
| `UCONV_E2BIG` | Reached the maximum number of characters (output buffer full) |

---

## 8. Code-page number -> code-set name - `UniMapCpToUcsCp`

```c
int UniMapCpToUcsCp(unsigned long ulCodePage, UniChar *ucsCodePage, size_t n);
```

Converts a numeric code-page identifier (`ulCodePage`, e.g. `850`) into the UCS-2 code-set name
(`IBM-nnn`) that `UniCreateUconvObject` expects, writing it into `ucsCodePage`; `n` is that buffer's
capacity in `UniChar` elements and must leave room for the terminating null. Returns `0` on success
or `UCONV_E2BIG` if the buffer is too small (on any error the output is undefined). [DOC-IBM
`uconv.h:224-239`]

This is the bridge from the numeric NLS code-page world to the named-code-set conversion world: a
program takes the current code page from the NLS surface (section 9) and feeds it through
`UniMapCpToUcsCp` to obtain the name for a conversion object.

---

## 9. Relation to the NLS code-page surface

The numeric code pages this API converts between are the same ones the Control Program's National
Language Support calls report and select - documented in `config-and-environment.md`, not repeated
here. The relevant connection points [DOC-IBM `bsedos.h`, per `config-and-environment.md`]:

- `DosQueryCp` reports the process's current code page and the prepared system code-page list (the
  values a program would pass to `UniMapCpToUcsCp` to name a conversion object).
- `DosQueryCtryInfo` / `COUNTRYINFO` and `DosQueryDBCSEnv` describe the country/code-page locale and
  the DBCS lead-byte ranges - the byte-structure the multibyte `first`/`other` tables of
  `UniQueryUconvObject` (section 6) describe for a specific conversion object.

The division of labour: the NLS `Dos*` calls are about *which* code page is in effect and its
locale conventions; the `Uni*` conversion API is about *transcoding bytes* between a chosen code
page and UCS-2.

### 9.1 The three code-page scopes a PM application has [DOC-IBM]

**A PM process does not have "a" code page - it has three independent ones**, and setting one does
not set the others. This is the single most common source of mojibake in a PM application, and it is
silent: text renders as the wrong glyphs rather than raising an error. [DOC-IBM - `pm5.txt`,
section "Code Pages"]:

| Scope | Set / query | Governs |
|---|---|---|
| **Process** | `DosSetProcessCp` / `DosQueryCp` | The process code page. IBM notes explicitly that this leaves **keyboard/display not changed**. |
| **Message queue** | `WinSetCp(hmq, ...)` / `WinQueryCp(hmq)` | The code page in which **text is delivered to the application** - "Text entered in a dialog box is supplied to the application in the code page of the queue (*queue code page*)". |
| **GPI** | `GpiSetCp` / `GpiQueryCp`; `GpiCreateLogFont` | The code page used when **drawing** text; logical fonts are created in a code page. |

The default comes from `CODEPAGE=` in `CONFIG.SYS`; these calls "work independently of the
CONFIG.SYS file" [DOC-IBM - `pm5.txt`]. `WinQueryCpList` enumerates the code pages the system
supports, and `WinCpTranslateChar` / `WinCpTranslateString` transcode between two code pages without
going through UCS-2.

**Resources must match the queue.** This is what the `codepage` fields in `DLGTEMPLATE`, the
accelerator table (`resources-and-dialogs.md`), and `FATTRS` (`gpi-fonts-and-metafiles.md`) are for
- they declare the code page of the *resource's* text, and IBM's rule is that it should agree with
the queue's [DOC-IBM - `pm5.txt`]: "If possible, the code page of a resource (for example, a menu or
dialog box) should match the code page of the queue. In general, **code page 850 is the best choice
for both an application and its resources**" - because 850 "contains most of the characters in other
supported code pages."

**The queue code page can change under you.** ~~"The `HK_CODEPAGECHANGE` hook"~~ CORRECTED: the hook
constant is **`HK_CODEPAGECHANGED`** (12) [DOC-IBM `pmwin.h:4045`]; `HK_CODEPAGECHANGE` does not exist,
so code written from the old spelling fails to compile. The slip is easy to make because IBM documents
the hook procedure as `CodePageChangedHook`, taking the queue handle, the previous code page and the
new one [DOC-IBM - `pm1.txt` *CodePageChangedHook*; `pmwin.h:4046`]. It notifies that a message
queue's code page has changed; "the new code page is set before this hook is called" [DOC-IBM -
`pm1.txt`]. Cached text measurements or converted buffers must be invalidated when it fires.

Two consequences for a program that caches conversion objects:

- **An object cached by code-page number is not stale after the hook fires.** A numbered table does
  not change; what changes is *which* number the queue uses. Query `WinQueryCp` when you need it
  rather than remembering it, and the cache needs no invalidation.
- **Cache for stateless use only.** A conversion object carries shift state for stateful code sets
  (the `state` attribute, section 6.1), so an object reused across whole buffers can begin one
  conversion in the state the previous one ended in. Reusing one per character for a PC keyboard or
  display code page is safe; for whole files, open a fresh object or reset it.

> **Porting note.** Code arriving from a UTF-16 platform (Win32 `W` APIs) or a UTF-8 one has *one*
> string encoding; PM has three scopes plus a per-resource declaration. The conversion boundary must
> be chosen deliberately - typically UCS-2 internally via the `Uni*` API above, converting to the
> queue code page at input and the GPI code page at draw time - rather than assuming a single
> process-wide encoding exists.

### 9.2 OS/2 converts; it does not *detect*

Worth stating explicitly, because the two get conflated and the conclusion drawn from the confusion
is wrong in both directions.

**OS/2 does know about Unicode.** `UCONV.DLL` ships in `\OS2\DLL`, `uconv.h` and `unidef.h` are
installed headers, and beyond the conversion API documented above the `Uni*` surface includes
collation (`UniStrcoll`, `UniStrxfrm`), case mapping (`UniTransLower` / `UniTransUpper`,
`UniStrlwr` / `UniStrupr`), character classification (`UniQueryCharType`, `UniQueryAlnum`, ...), and
locale objects (`UniCreateLocaleObject`, `UniQueryLocaleItem`, `UniStrftime`, `UniStrfmon`). It is
UCS-2, contemporary with early NT - not an afterthought.

> **Probe warning.** These symbols are **not** in `os2emx.h`. They are in `uconv.h` and `unidef.h`.
> A grep of `os2emx.h` alone returns nothing and reads as "OS/2 has no Unicode support", which is
> false. This exact false negative has been produced more than once - see `os2-app-dev-guide.md`
> section 3, and use the positive control: `grep -l Uni /usr/include/*.h`.

**What is genuinely absent is detection.** There is no `IsTextUnicode` equivalent: nothing in the
API will guess whether a byte buffer is UTF-8, UCS-2, or a single-byte code page. `UniUconvToUcs`
converts *from a code set you name*. So an editor or importer must supply its own heuristic - BOM
sniff first, then a UTF-8 well-formedness check, then fall back to the process code page.

**Skip a byte-order mark only if one is actually there** [OBS-RE]. Once you have written that
heuristic it is tempting to pair it with "and the decoder strips the BOM" - but the decoder gets
called in two quite different situations, and only one of them has a mark to strip:

- *detected* encoding - the BOM is what identified it, so it is present by construction;
- *chosen* encoding - the user picked it from a menu **because detection had nothing to go on**,
  which usually means there is no mark at all.

An unconditional `pIn += 2` for UTF-16 therefore works perfectly on every file that announces
itself, and silently eats the first character of every file that does not. Nothing errors, the byte
count is off by one or two, and the text looks almost right. Check the bytes before skipping them,
and check that the mark matches the encoding being applied:

```c
if (enc == UCS2LE && cb >= 2 && b[0] == 0xFF && b[1] == 0xFE) { p += 2; cb -= 2; }
else if (enc == UCS2BE && cb >= 2 && b[0] == 0xFE && b[1] == 0xFF) { p += 2; cb -= 2; }
else if (enc == UTF8SIG && cb >= 3 && b[0] == 0xEF && b[1] == 0xBB && b[2] == 0xBF) { p += 3; cb -= 3; }
```

A "reload as this encoding" command is the fastest way to find this bug, and a good reason to build
one early: it is the only path that routinely feeds the decoder a buffer whose encoding was asserted
rather than detected.

The practical split for a Win32 port:

| Win32 | OS/2 |
|---|---|
| `MultiByteToWideChar` / `WideCharToMultiByte` | `UniUconvToUcs` / `UniUconvFromUcs` (section 4), or `UniStrToUcs` / `UniStrFromUcs` (section 7) |
| `LCMapString(LCMAP_SORTKEY)` | `UniStrxfrm`; direct compare with `UniStrcoll` |
| `CompareString`, `lstrcmpi` | `UniStrcoll`, `UniStrcmpi` |
| `GetLocaleInfo` | `UniQueryLocaleItem` |
| `GetDateFormat` / `GetTimeFormat` | `UniStrftime` |
| `CharUpper` / `CharLower` | `UniTransUpper` / `UniTransLower` |
| `GetACP` / `GetOEMCP` | `DosQueryCp` (section 9) |
| **`IsTextUnicode`** | **nothing - write the heuristic** |

### 9.3 Getting the bytes right is only half of it - GPI draws in the GPI code page

Converting a file into UTF-8 correctly does **not** make it appear correctly. `GpiCharStringPosAt`
and `GpiQueryTextBox` interpret the bytes you hand them in the **GPI** code page (section 9.1), so UTF-8
passed straight through draws each byte as its own 8-bit glyph: the word "cafe" with an e-acute is
`63 61 66 C3 A9` in UTF-8, so GPI draws five glyphs - `c`, `a`, `f`, then whatever 0xC3 and 0xA9
happen to be in the current GPI code page (under CP850, a box-drawing piece then `(R)`) - with no
error anywhere. Any editor or text control that holds Unicode internally must **transcode at the
drawing boundary**, not just at the file boundary.

Two details make that more than a call to `UniUconvFromUcs`:

- **A text engine usually indexes character positions by source byte.** The converted string has a
  different length, so the conversion has to carry a *source-byte -> converted-prefix-length* map
  alongside the bytes, or every width lookup lands in the wrong place.
- **Every byte of a multi-byte sequence must report the same x position** - the end of its
  character. Otherwise a caret can be placed *inside* a character.

A character the display code page cannot represent should be drawn as a visible substitute rather
than dropped: dropping it silently shifts everything after it and is much harder to recognise.

**The substitute you get is not `?`.** `UniUconvFromUcs` substitutes by default (section 6.2), and
converting to code page 437 the substitute came back as byte `0x7F`, which GPI draws as the small
"house" glyph. A `?` only appears if your own code supplies one for a conversion that produced
nothing. [OBS-RE - Greek letters in a UTF-8 buffer, converted one character at a time to CP437 for
drawing, each drew as the house glyph, which is `0x7F` in CP437; separately, a byte with no mapping,
converted to CP437 when a file was saved, was stored as `0x7F`.] *Tell:* rows of little houses where
accented or foreign letters should be.

~~"This is a genuine limit of an 8-bit display page, not a defect - CP850 has no Greek."~~ CORRECTED:
it is a limit of *transcoding to the 8-bit GPI code page*, not of GPI. A logical font requested in
code page 1200 or 1208 with a Unicode outline face draws Greek, Cyrillic and Japanese directly, and
in 1208 needs no source-byte map at all - see `gpi-fonts-and-metafiles.md` section 2.6. The wrong
reading was natural: the transcoding path was the only one that had been tried.

> **`GpiQueryCp` is a hint, not an answer.** It can report `0` ("the default") on a freshly created
> presentation space, and can report a value `UniMapCpToUcsCp` will not map. Code that trusts it and
> gives up on failure ends up with no conversion object at all, and then *every* non-ASCII character
> draws as a substitute - which looks like a broken converter rather than a bad code-page query.
> Fall back through the queried page, then a sensible display page (`850`), then `437`. [OBS-RE]

---

## 10. Error codes and linkage

### 10.1 Return-code space [DOC-IBM `ulserrno.h`, `uconv.h:278-290`]

The conversion functions return `int` values from the ULS return-code enum. `uconv.h` defines
`UCONV_*` aliases for backward compatibility that map onto the `ULS_*` values in `ulserrno.h`
(base `0x00020400`, i.e. `ULS_API_ERROR(x) = 0x00020400 | x`):

| `UCONV_*` alias | `ULS_*` value | Numeric |
|---|---|---|
| `UCONV_EOTHER` | `ULS_OTHER` | `0x00020401` |
| `UCONV_EILSEQ` | `ULS_ILLEGALSEQUENCE` | `0x00020402` |
| `UCONV_EMFILE` | `ULS_MAXFILESPERPROC` | `0x00020403` |
| `UCONV_ENFILE` | `ULS_MAXFILES` | `0x00020404` |
| `UCONV_ENOMEM` | `ULS_NOMEMORY` | `0x0002040D` |
| `UCONV_EINVAL` | `ULS_INVALID` | `0x0002040E` |
| `UCONV_EBADF` | `ULS_BADOBJECT` | `0x0002040F` |
| `UCONV_E2BIG` | `ULS_BUFFERFULL` | `0x00020412` |
| `UCONV_BADATTR` | `ULS_BADATTR` | `0x00020415` |
| `UCONV_NOTIMPLEMENTED` | `ULS_NOTIMPLEMENTED` | `0x0002040C` |

`ULS_SUCCESS` is `0`. (`uconv_error_t` is `#define`d to plain `int` in `uconv.h:122`.)

### 10.2 Calling convention [DOC-IBM `callconv.h:24`]

Every `Uni*` entry point is declared `CALLCONV`, which `callconv.h` defines as `_System` - the
standard OS/2 32-bit API linkage (arguments pushed right-to-left, callee cleans the stack; see
`calling-convention.md`). (The EDM2 *UniUconvToUcs* page lists the convention as "Cdecl32"; the
Toolkit header's `_System` is taken as authoritative here. [DOC - EDM2, noted as a discrepancy])

---

## Sources opened
- `README.md`, `file-io.md` - house style.
- `config-and-environment.md` - NLS code-page surface (`DosQueryCp`,
  `DosQueryCtryInfo`, `DosQueryDBCSEnv`) for the section 9 cross-reference.
- `uconv.h` - all conversion prototypes, `uconv_attribute_t` /
  `conv_endian_t` / `udcrange_t`, `enum uconv_esid`, `UCONV_OPTION_*` / `CVTTYPE_*` / `DSPMASK_*` /
  `ENDIAN_*` constants, code-set name macros, `UconvObject` typedef, per-function return codes.
- `unidef.h` - `UniChar` typedef, ULS type/category model.
- `ulserrno.h` - `ULS_*` return-code enum values.
- `callconv.h` - `CALLCONV` = `_System`.
- EDM2 - *Universal Language Support API (Unicode)*, *UniUconvToUcs*, *UconvObject*
  pages (partial-conversion / pointer-advance behaviour; calling-convention discrepancy note).
