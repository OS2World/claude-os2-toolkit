# OS/2 CONFIG.SYS Processing, the Environment Block, and NLS

How OS/2 processes CONFIG.SYS and the process environment / national-language state it publishes.
Established during boot-sequence Stage 8.

Provenance: **[DOC-IBM]** the OS/2 Control Program reference and Toolkit `bsedos.h` (`DosScanEnv`
`bsedos.h:2616`, `DosQueryCp` `bsedos.h:2357`, `DosQueryCtryInfo` `bsedos.h:2339`, `COUNTRYINFO`
`bsedos.h:2314-2330`, `DosQueryDBCSEnv` `bsedos.h:2344`); the environment-block format is documented
OS/2 behaviour (CP reference `DosExecPgm` EnvPointer). CONFIG.SYS category order is period-documented
only - see the residual-uncertainty note below.

## CONFIG.SYS is processed in multiple passes by category, not line-by-line [DOC]

OS/2 reads CONFIG.SYS **several times, looking for different statement types on each pass** - it does
not execute the file top-to-bottom. A commonly-documented scan order:

1. `PSD=` - **Platform Specific Driver** (SMP CPU/interrupt-controller bring-up; corrected 2026-08-02,
   was wrongly glossed "protected-mode swapper device" with no source - see `drivers.md` "Platform
   Specific Drivers (PSD) - SMP CPU/interrupt bring-up" for the full sourced mechanism)
2. `BASEDEV=` - base device drivers (`.SYS` / `.ADD` / `.DMD`; loaded by file extension, not
   appearance order)
3. `DEVICE=` and `IFS=` - installable device drivers and file systems
4. `RUN=` / `CALL=` - programs run during init
5. general statements

`PROTSHELL=` starts the shell **last**. The directive categories also include the **environment**
group (`SET=` / `LIBPATH=` / `BEGINLIBPATH=` / `ENDLIBPATH=`) and **NLS** (`CODEPAGE=` / `COUNTRY=` /
`DEVINFO=`).

> **Provenance / residual uncertainty.** The multi-pass, by-category processing (and `PROTSHELL=`
> last) is documented; the scan order above is from period OS/2 references. **Sources disagree on
> where the environment group (`SET`/`LIBPATH`) and the NLS statements fall** relative to `DEVICE=` -
> some place environment creation *before* `DEVICE=` - so treat the precise placement of those two
> groups as not firmly settled. [DOC - blondeguy.com "About Config.Sys in OS/2" (the multi-pass scan
> order); EDM2 "CONFIG.SYS - Commands"; JaTomes "OS/2 Config.Sys Statements"]
>
> **Ratified 2026-07-26 - negative result:** searched the IBM Warp redbooks (`gg243731`
> CONFIG.SYS pages, `gg243774`) and the CP reference for an IBM primary that *fixes* the pass order
> and the placement of the environment/NLS groups; **none states an authoritative category-scan
> order**. The IBM pages describe individual directives and note only that "the order of the DEVICE
> and DEVICEHIGH commands ... is important" (IBM redbook GG24-3731 section CONFIG.SYS), not a whole-file pass
> order. So the multi-pass framing and the ranking above remain **[DOC]** from period references, not
> IBM-primary - do not upgrade without a source.
>
> **PARTLY SETTLED 2026-09-08 (Rule 1.7) - the negative result above still stands exactly as
> written, and the question it left open is now answered from a different tier.** No IBM *document*
> fixes the pass order; that has not changed. But the kernel's own ring-3 initialisation does, and
> it is readable: `syiProcess` calls `syicpInit` - which processes **all** of `COUNTRY=`,
> `CODEPAGE=` and `DEVINFO=` - and then `syicpActivate` - which issues `DosSetCp`, `VioSetCp` and
> `KbdSetCp` - **before `syiInstallDeviceDrivers`**, i.e. before any `DEVICE=` line is loaded.
> **So the NLS group precedes `DEVICE=`**, which is one of the two placements this note records as
> unsettled. See "Boot-time NLS initialisation" below for the full call sequence. `[OBS-RE]`
>
> **The environment group is NOT settled by that read, and must not be inferred from it.**
> `syiProcess` does call a routine named `syiInitEnvironment` before `syicpInit`, but what that
> routine consumes was not established - whether it processes CONFIG.SYS's `SET=`/`LIBPATH=` lines
> or only builds SYSINIT's own environment is unread, and the name is not evidence.

## The environment block [DOC-IBM]

The process environment is a flat, **double-null-terminated** block -
`"NAME1=value1\0NAME2=value2\0...\0\0"`; an empty environment is the two bytes
`"\0\0"`. It is pointed at by **`PIB.pib_pchenv`** (`bsetib.h:73`, `struct pib_s`) and walked by
**`DosScanEnv`** (`bsedos.h:2616`). `DosSetDateTime`-style APIs aside, most system settings surface
here.

The block format is IBM-documented under `DosExecPgm`'s **EnvPointer** [DOC-IBM CP ref, `DosExecPgm`]:
each entry is an ASCIIZ string of the form `variable=value`, and "the last ASCIIZ environment string
must be followed by an additional byte of zeros" - i.e. the trailing double-null above. A 0 EnvPointer
makes the child inherit the parent's environment. The environment is addressed as a **segment**
(`DosGetEnv` returns a selector, `PSEL`, to the environment segment [DOC-IBM CP ref, `DosGetEnv`]),
which is the origin of the customary **64 KB** ceiling.

Syntax rules:
- `LIBPATH=`, `BEGINLIBPATH=`, `ENDLIBPATH=` set their value **with no `SET` prefix**; every other
  variable requires `SET NAME=value`. A bare `PATH=...` (without `SET`) is not a recognized directive.
- Directive names are case-insensitive; variable **values** are case-sensitive. A duplicate `SET`
  replaces the earlier value (last wins).
- **Looking a variable up is case-sensitive.** With `PATH` in the environment, `DosScanEnv("PATH")`
  returns 0 and `DosScanEnv("path")` returns 203 `ERROR_ENVVAR_NOT_FOUND` [OBS - measured on Warp
  Server for e-business 4.50, kernel revision 14.089, 32-bit probe]. IBM's `DosScanEnv` page says
  nothing about case [DOC-IBM `cp1.txt`, "DosScanEnv"]. *(CORRECTED, Rule 1.7: this line said
  variable names are case-insensitive. Whether `SET` in CONFIG.SYS or CMD.EXE changes the case of
  a name when it stores it is not established here; what is established is that the lookup matches
  the stored spelling exactly.)* **The tell:** `getenv`-style code that finds a variable in one
  program and not in another - compare the exact spelling in the environment block.
- `PROTSHELL=` is a directive, not an env var; `SET PROTSHELL=...` is rejected.

## National Language Support [DOC-IBM `bsedos.h`]

- `DosQueryCp` (`bsedos.h:2357`, `= DosGetCp`) - the process's current code page (and the prepared
  system code-page list). [DOC-IBM] The returned list is word 1 = current process code page, words
  2..N = the prepared system code pages (CP ref `DosGetCp`).
- `DosQueryCtryInfo` (`bsedos.h:2339`, `= DosGetCtryInfo`) - returns the **`COUNTRYINFO`** structure
  (`bsedos.h:2314-2330`): `country`, `codepage`, `fsDateFmt`, `szCurrency[5]`,
  `szThousandsSeparator[2]`, `szDecimal[2]`, `szDateSeparator[2]`, `szTimeSeparator[2]`,
  `fsCurrencyFmt`, `cDecimalPlace`, `fsTimeFmt`, and `szDataSeparator[2]` (the list separator).
  [DOC-IBM] `fsDateFmt`: 0 = `mm/dd/yy`, 1 = `dd/mm/yy`, 2 = `yy/mm/dd` (CP ref `DosGetCtryInfo`).
- `DosQueryDBCSEnv` (`bsedos.h:2344`, `= DosGetDBCSEv`) - the DBCS (double-byte) environment vector
  for the country/codepage: a list of lead-byte range definitions (high byte = inclusive start, low
  byte = inclusive stop, per range). [DOC-IBM CP ref `DosGetDBCSEv`]

**Measured** [OBS - Warp Server for e-business 4.50, kernel revision 14.089, `CODEPAGE=437,850`,
32-bit probe; codes named from `bseerr.h`]:

- `DosQueryCp` with a 32-byte buffer returned 12 bytes: the process code page (437), then the
  prepared list (437, 850). With a buffer of 0 or 2 bytes it returns 473 `ERROR_CPLIST_TOO_SMALL`
  and writes nothing; with 4 bytes it returns **473 and still writes** what fits (the process code
  page, count 4). So a 473 can come with usable data.
- `DosSetProcessCp(850)` returns 0 and makes the first entry 850; an `EXEC_SYNC` child then reports
  850 (inherited). A code page not in `CODEPAGE=` (852), and 0, return 472
  `ERROR_INVALID_CODE_PAGE`.
- `DosQueryCtryInfo` for the configured country returns **38 bytes** of `COUNTRYINFO` (country 1,
  the code page asked for or the process's when 0, date MDY, `$`, `,` `.` `-` `:`, 2 decimals, list
  separator `,`). A buffer of 0 or 3 bytes returns 399 `ERROR_NLS_TABLE_TRUNCATED` with nothing
  written; 4 bytes returns **399 with those 4 bytes written**. A country with no entry returns
  398 `ERROR_NLS_NO_CTRY_CODE`. Asking for code page 852, which is not prepared, still returns 0.

## Hardware configuration - `DosDevConfig`

```c
APIRET APIENTRY DosDevConfig(PVOID pdevinfo, ULONG item);   /* bsedos.h:2835 */
```
`item` is one of `DEVINFO_PRINTER` 0, `DEVINFO_RS232` 1, `DEVINFO_FLOPPY` 2,
`DEVINFO_COPROCESSOR` 3, `DEVINFO_SUBMODEL` 4, `DEVINFO_MODEL` 5, `DEVINFO_ADAPTER` 6
(`bsedos.h:2838-2844`); the answer is one byte. Measured [OBS - Warp Server for e-business 4.50
on a virtual machine with two serial ports, no parallel port and an empty floppy drive]: 0 printers,
2 serial ports, 1 diskette drive (the drive counts with no disk in it), coprocessor 1, submodel 1,
model 252 (0xFC, AT class), adapter 1. Item 7 and item 0xFFFFFFFF return 87 **and write 0 into the
byte**. A NULL `pdevinfo` returns 87 rather than trapping. The values come from a table the kernel
copies from the loader at boot [OBS-RE - the kernel's `DosDevConfig` worker read] - a boot-time
snapshot.

`SET RUNWORKPLACE=` also lives in this environment - it is the variable the Presentation-Manager
shell reads (boot-sequence Stage 12) to choose the desktop program.


## Boot-time NLS initialisation: what halts, what warns, and what is dropped [OBS-RE] + [DOC-IBM]

*Added 2026-09-08. The APIs above are the query surface; this section is the **initialisation**
that fills it, and its failure contract. `[OBS-RE]` is a disassembly of the shipped ring-3
SYSINIT objects of four debug kernels (SMP and UNI, each Astrict and Hstrict) with IBM's own
`.sym` supplying every symbol named below; `[DOC-IBM]` is the shipped `OSO001.MSG` catalogue,
`cdib.inc`, and the Control Program / Command Reference books. Symbols are IBM's and are stable;
the object-relative offsets that back them are **build-keyed** and are deliberately not repeated
here.*

*__Which claims were re-derived, and which were carried.__ Re-derived while writing this section,
from the artifacts themselves: every `SYSxxxx` number and its text (parsed out of a shipped
`OSO001.MSG` index), the `COUNTRY.SYS` header and entry table (read out of a shipped file), and the
`XTLen` arithmetic cited in `vio-kbd-mou.md` section 3.7. **Not re-derived here**: the kernel
disassembly - the call order, the severity routines, `syicpFatal`'s zero callers, each decision
branch, and the ordinal table - all of which come from a separate reverse-engineering pass and are
tagged for what that pass read. Where that pass states it did not follow something, this section
says so rather than completing it.*

### The order, as the kernel's own initialisation calls it

Ring-3 SYSINIT's main routine `syiProcess` calls, in this order:

```
syiOpenFiles              ; opens CON:   -> SYS1724 / SYS1725 on failure = HALT
syiInitStdErrIntercept
syiInitEnvironment
syiCheckFileSys           ;             -> SYS0732 on failure = HALT
syicpInit                 ; <-- COUNTRY= , CODEPAGE= , DEVINFO=  (all three)
syiGetLoadableEntries     ; resolve 13 DOSCALL1 entry points BY ORDINAL
syiDisplaySavedMessagesR3 ; first moment anything queued is printed
   (an SICG packet, then an `smsw` / EM-bit test -> SYS2030 on failure = HALT)
syicpActivate             ; <-- DosSetCp + VioSetCp + KbdSetCp
   ...
syiInstallDeviceDrivers   ; <-- DEVICE= processing starts HERE
   ...
syiDisplaySavedMessagesR3 ; second flush
syiCloseFiles
   ... daemons, PROTSHELL ...
```

**Three orderings this fixes.** (1) **All NLS work precedes `DEVICE=` processing** - the code
pages are prepared and `VioSetCp`/`KbdSetCp` are issued before a single `DEVICE=` line is loaded,
so the devices they address are the base drivers the loader already brought up, never one
CONFIG.SYS named. (2) `syicpInit` runs **after** the file-system check, so `COUNTRY.SYS` is opened
through the real file system by `DosOpen`, not through the loader's mini-FSD. (3) `syicpActivate`
must follow `syiGetLoadableEntries`, because `VioSetCp` and `KbdSetCp` are two of the entry points
that routine resolves.

### Three severities, separated by which routine is called

| kind of failure | what OS/2 does |
|---|---|
| **`COUNTRY=` file-level** - cannot open, cannot size, short read, bad signature, malformed section | **HALT.** `syiAbortR3` -> ring-0 `SYIAbort` -> the specific message, then **SYS2065** *"The system is stopped."* -> `sti; jmp $` |
| **`COUNTRY=` content-level** - country code not in the file; the requested code page not in the file for that country | **WARNING, boot continues** on a documented fallback |
| **`CODEPAGE=` not usable by the display or the keyboard** | **WARNING, boot continues** on the device default |
| **`DEVINFO=` file cannot be opened** | **MESSAGE, boot continues, that one line is dropped** - and it does not even set the warning bit |

The three severity routines are `syicpFatal`, `syicpWarning` and the shared `syicpError`.
**`syicpFatal` has zero callers in all four builds examined**; only `syicpWarning` is called, at
five sites. The one thing the fatal bit gates inside `syicpError` is a `DosFreeSeg` of the CDIB
segment - **a resource release, not a halt.** So no `CODEPAGE=` or `DEVINFO=` condition can stop a
boot. Only `COUNTRY.SYS` *file* conditions can, and they do it through the **generic** `syiAbortR3`
that also serves out-of-memory and a missing `CON:` - there is no NLS-specific halt path at all.

> **Scope, stated because it is the one hole worth closing.** This was measured in four **debug**
> kernels; the **retail** kernel was not disassembled. A retail kernel's `.map` does list
> `inicp$syicpFatal`, but a map records a symbol's address, not whether anything calls it, so it
> neither confirms nor refutes the finding.

### `COUNTRY=` - the decision tree

`syicpCountry` builds the default path `<bootdrive>:\COUNTRY.SYS` when no `COUNTRY=` line is
present. Which message a failure selects depends only on that: with no `COUNTRY=` line the
not-found case is **SYS1518** and the invalid case **SYS1733** (one insert, the path); with a
`COUNTRY=` line present they are **SYS1718** and **SYS2069** (three inserts - line number,
statement, file).

| # | condition | outcome |
|---|---|---|
| C1 | `DosOpen` fails - missing file, wrong path, drive absent, sharing denied | **HALT** |
| C2 | seek-to-end or seek-to-0 fails, or the file size's high word is non-zero | **HALT** |
| C3 | `DosAllocSeg` for the file image fails | **HALT**, SYS2030 |
| C4 | `DosRead` fails, or returns fewer bytes than the file size | **HALT** |
| C5 | the first 8 bytes are not `FF 'COUNTRY'` | **HALT** |
| C6 | the country-entry table pointer's high word is non-zero (a 32-bit offset) | **HALT** |
| C7 | a per-entry data pointer's high word is non-zero | **HALT** |
| C8 | a section pointer's high word is non-zero | **HALT** |
| C9 | any section fails its own 8-byte signature, or a `CTYINFO` section does not fit in 0x30 bytes | **HALT** |
| C10 | **the country code named in `COUNTRY=` is not in the file** | **WARNING, continue.** SYS1196 with the country code as insert 3; the country falls back to the file's own first entry |
| C11 | **the country exists but not for any code page in `CODEPAGE=`** | **WARNING, continue.** SYS1196, then the lookup is retried with code page **0**, i.e. "whatever entry this country has first" |

**The line is "can I parse this file", not "did I get what CONFIG.SYS asked for".** C10/C11 are
corroborated by IBM's own prose `[DOC-IBM]` (`cp3.txt` section "Code Page Preparation"): *"If a resource
cannot be prepared for the selected code page during system initialization, it is prepared for a
default code page. ... The country information defaults to the code page of the first entry found in
the COUNTRY.SYS file for the country code."*

Note the asymmetry inside the file: a **bad section signature halts** (C9) while **no matching
section at all warns** (C11).

### `COUNTRY.SYS` layout, as the kernel walks it

`[OBS-RE]` from the consumer, then confirmed byte-for-byte against a shipped Warp 4.5
`\OS2\SYSTEM\COUNTRY.SYS` (50,947 bytes, dated 2001-09-24) - re-derived for this document.

```
+0x00   8 bytes   FF 'C' 'O' 'U' 'N' 'T' 'R' 'Y'      signature, checked
+0x13   WORD      offset of the country-entry table   (measured 0x0017)
+0x15   WORD      MUST BE ZERO - high half of a 32-bit offset

at that offset:
        WORD      number of entries                  (measured 0x0130 = 304)
        then N x 14 bytes:
          +0x00 WORD  entry length                   (measured 0x000c)
          +0x02 WORD  country code                   (measured 1 = US)
          +0x04 WORD  code page id                   (measured 850, then 437)
          +0x06 WORD  reserved
          +0x08 WORD  reserved
          +0x0a WORD  offset of the country data block
          +0x0c WORD  MUST BE ZERO

country data block:
        WORD      number of sections
        then M x 8 bytes:
          +0x00 WORD  reserved
          +0x02 BYTE  section type  1=CTYINFO  2=UCASE  6=COLLATE  7=DBCS
          +0x03 BYTE  reserved
          +0x04 WORD  offset of the section
          +0x06 WORD  MUST BE ZERO

each section begins with its own checked 8-byte signature:
        FF 'CTYINFO'    FF 'COLLATE'    FF 'UCASE  '    FF 'DBCS   '
```

**The order of entries in the file is the fallback order** - the shipped file's first two entries
for country 1 are code page 850 then 437, which is what C11's "prepare in the default code page"
resolves to. Each section handler that succeeds sets a bit in a per-entry flag byte (1 = CTYINFO,
2 = COLLATE, 4 = UCASE, 8 = DBCS); if no section of a matching entry loads for any prepared code
page, the result is C11.

**The four section handlers are one rule with four sets of numbers.** Each is called with
`ES:BX` = the `CDIB_codepage_data_section` being filled, `SI` = the section's offset in the file
image, `CX` = the file size (the bound), a far pointer to a **caller-owned cursor** seeded from
`CDIB_length`, and the file image's segment. Each one, in order: rejects the section
unless `SI + K <= CX`; compares eight bytes at the section's start against its own signature
literal; takes the cursor's value, advances the cursor by `L`, and stores the old value into its
slot of the code-page data section; writes `L` as the new section's own length word and copies
`C` bytes from the file section's `+H` to just past that word; returns 0, or the literal
**0x6C5** on either rejection.

| handler | section type | bound `K` | CDIB slot | length `L` | skip `H` | copies `C` |
|---|---|---|---|---|---|---|
| `syicpFormat` | 1 `CTYINFO` | 0x30 | `CDIB_cpd_format_ptr` +0x02 | 0x24 | 0x0e | 0x22 |
| `syicpCollate` | 6 `COLLATE` | 0x10a | `CDIB_cpd_collate_ptr` +0x04 | 0x102 | 0x0a | 0x100 |
| `syicpCasemap` | 2 `UCASE` | 0x8a | `CDIB_cpd_casemap_ptr` +0x06 | 0x82 | 0x0a | 0x80 |
| `syicpDBCS` | 7 `DBCS` | 0x0a + the WORD at section +0x08 | `CDIB_cpd_DBCS_ptr` +0x08 | that WORD + 2 | 0x0a | that WORD |

Every `L` is `cdib.inc`'s own structure size `[DOC-IBM]`. **Three of the four bounds are
HARDCODED CONSTANTS, not computed** - `syicpFormat`, `syicpCollate` and `syicpCasemap` each carry
their `K` as an immediate, and only `syicpDBCS` derives it, as `0x0a` plus the WORD the section
itself declares. That the three constants each *equal* `0x0a` plus the payload length the shipped
`COUNTRY.SYS` carries (`0x0a+0x26`, `0x0a+0x100`, `0x0a+0x80`) is an observation about that file,
not a rule the kernel applies - `[OBS]` on one file, not `[OBS-RE]` on the code. **The difference
is behavioural and a reimplementation must keep it:** a section whose declared payload length
disagrees with the type's expected one is bounds-checked by IBM against the CONSTANT, so it is
accepted or rejected on the size the type implies and never on the size the file claims. Computing
all four bounds from the file would diverge on exactly that input.
`CTYINFO` is the single asymmetry and it is not a different header: its payload is 0x26 bytes and
the handler starts its copy four bytes in, which is why its `C` is 0x22 and not 0x26.
`CDIB_cpd_length` is the literal **0x0a**, written before any parsing.

**THE CURSOR THE HANDLERS ADVANCE IS A STACK LOCAL, NOT `CDIB_length` ITSELF, and that is the whole
reason a failed code page costs no image space.** `syicpData` copies `[es:0]` into two stack locals,
passes `SS:&local` to each handler, and writes the result back to `CDIB_length` only at the very
end, after every section of that code page has loaded. A code page that fails part-way therefore
leaves the CDIB's own length untouched and the next one reuses the same offset. An implementation
that hands the handlers a pointer to `CDIB_length` directly produces the same *image* for a
successful load and leaks a partial section for every failed one.

Note the slot order is **not** the dispatch order: the pointers run
format/collate/casemap/DBCS while the dispatch ladder tests 1, 2, 6, 7 - so `UCASE` is dispatched
second and stored third.

**A rejecting handler returns the literal 0x6C5, which is the number 1733** - the number
`basemid.h` names `MSG_SYSINIT_SCFILE_INVAL` `[DOC-IBM]`. That the handler *means* that message is
`[INF]`, not established: the descriptor words the callers actually report through could not be
resolved to message numbers from the shipped image. It does not matter on this path, and that is
the checkable half - **the callers discard the returned value** and report through their own
context-selected descriptor, so 0x6C5 is dead here and is not the mechanism by which a message is
chosen.

**An unrecognised section type is STEPPED OVER, not rejected - and the shipped file contains two
of them.** The dispatch ladder tests exactly 1, 2, 6 and 7; its unmatched arm is the loop's own
advance to the next 8-byte record, not the malformed-file path that a failed signature or a
non-zero pointer high half takes. A Warp 4.5 `COUNTRY.SYS` gives country 1 **six** sections per
entry, of types 1, 2, **4**, **5**, 6 and 7: type 5 carries the signature `FF 'FCHAR  '`, and type
4 points at the *same* file offset as the entry's type-2 `UCASE` section, so its signature would
have passed had it been dispatched. A reimplementation that treats an unknown type as malformed
therefore halts on IBM's own data, and no signature test can catch the mistake. Nothing is
reported for a skipped type and no flag bit is set, so an entry whose only sections were
unrecognised falls out as "no section loaded" - SYS1196, a warning - rather than as a bad file.

> ~~**Not read:** the bodies of the `COLLATE`, `UCASE` and `DBCS` handlers past their signature
> checks and dispatch - what each copies into the CDIB is unestablished, though `cdib.inc` gives
> the destination shapes.~~ **SUPERSEDED 2026-09-11: all three were read in full, and the table
> above is what they do.** Kept marked rather than deleted because a *wrong negative is the most
> expensive record this corpus writes* - it closes a question permanently - and because this one
> was cited as a named blocker by a build plan, which then correctly declined to invent what the
> handlers copy rather than guessing. The three bodies are ~100 bytes each and structurally
> identical to `syicpFormat`, whose row had already been read; what the negative cost was that
> nobody spent the next disassembly. Verified against IBM's own shipped file as well as the bytes:
> applying the table to a Warp 4.5 `\OS2\SYSTEM\COUNTRY.SYS` reproduces the WORD at +0x08 as
> 0x26/0x100/0x80/0x02 for the four types, and decodes the `CTYINFO` payload field-for-field onto
> `cdib.inc`'s `CDIB_format_section` as a coherent US locale.

### `CODEPAGE=` - parse, prepare, activate

**The routine is `syicpID`, and there is no `syicpCodepage`.** `syicpInit` calls it with
`DI` = the `CODEPAGE=` category list's **tail** word, the same selection every single-valued
statement gets (see "The order" above). No symbol containing *codepage* exists in the kernel's
SYSINIT object; a reimplementation looking for one will not find it. `[OBS-RE]` read in full.

**THE CODE-PAGE SECTION EXISTS ON EVERY BOOT, WHETHER OR NOT A `CODEPAGE=` STATEMENT DOES - and
this is the half an implementer is most likely to get wrong, because H's own wording invites the
opposite.** `syicpID` writes the CDIB header *before* it tests whether it was handed a statement
at all: `CDIB_length` = 0x10, `CDIB_codepage_ptr` = **0x10**, and the six other header pointers
zero. Only then does it test `DI`. So:

* `CDIB_codepage_ptr` is **never zero** on a real OS/2. Testing it against zero tests a state the
  kernel does not produce.
* The section's length is **`4 + S * max(n, 1)`** where `S` is the id-slot size, **not** `4 + S*n`.
  Literally: `mul byte [<a SYSINIT data byte>]` by `n`, `add ax,4` for the two header words, then
  `or cx,cx / jnz / add ax,4` - *one extra slot when `n` is zero*. `S` is **4**, read from the
  write loop's own stride (`add si,byte +0x4`) and from that second `add ax,0x4`, which is one
  slot; the multiplier **byte** at the SYSINIT data offset was not read, so that it equals the
  stride is `[INF]` - the two must agree or the reservation would not cover the walk, and
  `cdib.inc`'s `CDIB_cp_id_section` is 4 bytes `[DOC-IBM]`. With no code page named the section is
  therefore **8 bytes** with one id slot whose `CDIB_cp_id` is explicitly stored as **zero**, and
  `CDIB_cp_number_codepages` = 0.
* A **missing** `CODEPAGE=` statement and an **empty** one (`CODEPAGE=` with no operand) take the
  same path and produce the same 8-byte section; the only difference is where `n = 0` came from.

That minimum of one reserved slot is what makes H's `CDIB_cp_first_id` warning coherent - *"an id
section may exist with number-codepages zero, so test existence by comparing cp length against the
size of the codepage section"* `[DOC-IBM]` `cdib.inc`. The kernel reserves the slot precisely so
that the zero-count section still has one, and it then **writes through it**: `syicpCountry`'s
code-page-0 retry is reached exactly when the count is zero (see "`COUNTRY=` - the decision tree"),
and it passes the id array's start. An implementation that publishes a 4-byte section, or none,
has no legal slot for that write to land in.

**The duplicate-collapse above is this routine, and it leaves a HOLE.** On a duplicate the loop
decrements the stored count but still advances its write cursor by one slot - so
`CODEPAGE=850,850` publishes `cp_length` = 12 with `CDIB_cp_number_codepages` = 1, and the second
slot is reserved, unwritten, and outside the count. `cp_length = 4 + 4 * max(n,1)` therefore does
**not** hold across a duplicate; the length is computed from the *statement's* operand count before
the collapse. Read from the bytes: `mov [si],ax` / `mov [si+0x2],cx` write the length and the count
once, at the top, and the duplicate arm's only write is `dec word [bx+0x2]` - the **count** - while
`add si,byte +0x4` advances the cursor on both arms. Nothing ever rewrites `cp_length`. `[OBS-RE]`

**`syicpID` writes no data pointer.** Each id slot gets only its `CDIB_cp_id`; every
`CDIB_cp_data_ptr` stays zero until `syicpCountry` fills it from `COUNTRY.SYS`.

* **Duplicate code page IDs are silently collapsed.** `CODEPAGE=850,850` prepares one code page,
  with no message: the parse loop compares each incoming id against those already stored and, on a
  hit, decrements the stored count instead of appending.
* At most two are allowed - `CODEPAGE= xxx [,yyy]`, *"Two pages can be active simultaneously"*
  `[DOC-IBM]` `cmdref21.txt`. A malformed *value* is rejected on the parse side with **SYS0443**
  *"The CODEPAGE= statement in the CONFIG.SYS file is incorrect."* Which syntax errors select
  SYS0443 rather than SYS1196 is **unestablished** - the CONFIG.SYS parser itself was not read.
* If a `CODEPAGE=` statement existed but the prepared list ends up **empty**, initialisation emits
  **SYS1737** *"Code page switching is not available."* and **continues**.

`syicpActivate` is the activation, and it is short enough to state completely. Only the **primary**
(first) code page is ever passed to the devices; a secondary appears only as message text.

```
if no CDIB, or no code pages prepared:   return
dx = the PRIMARY code page id
DosSetCp(dx, 0)

rc = VioSetCp(0, dx, 0)
if (rc != 0 && rc != 470 && dx != 874)   warn SYS1729

rc = KbdSetCp(0, dx, 0)
if (rc == 0)                             return
if (rc == 442 && a DEVINFO=KBD entry exists)
        warn SYS1196, insert 3 = the KBD subtype
else    warn SYS1730   (insert = "cp1,cp2" when two are prepared)
```

with `[DOC-IBM]` `bseerr.h`:

* **470 `ERROR_VIO_NO_CP` is tolerated silently.** A display with no code-page support at all is
  not an error condition here - **no SYS1729 is issued.**
* **Code page 874 is exempted from the display check by value.**
* **442 `ERROR_KBD_CODEPAGE_LOAD_INCOMPL`** selects the SYS1196 form of the keyboard failure
  rather than SYS1730.

**`syicpActivate` cannot halt.** Every outcome above is a warning.

### `DEVINFO=` - the kernel opens the file and closes it, and never reads it

`syicpDevInfo` walks the `DEVINFO=` list and for **each** entry:

1. `DosOpen(filename)`.
   * **Success** -> an immediate `DosClose`, then step 2. It never seeks, never reads, never
     validates a header.
   * **Failure** -> **SYS1718** (3 inserts: line number, statement, file) queued **directly**,
     bypassing `syicpWarning` so the warning bit is not even set -> **this entry is skipped and the
     walk continues.**
2. If the CDIB slot for this device type is already non-zero, **skip** - the **first** `DEVINFO=`
   for a device wins, and a later duplicate is dropped **with no message at all**.
3. Build a `CDIB_device_section` `[DOC-IBM]` `cdib.inc`, exactly to IBM's structure:
   `{ WORD length; BYTE subtype[8]; WORD filename_ptr; WORD number_ROM_fonts; ROM_font[n];
   char filename[] }` - i.e. the **path string**, the 8-byte subtype and the `ROM=` list, nothing
   from inside the file.
4. For the keyboard only, the 8-byte subtype is additionally stashed where `syicpActivate` can name
   it in the SYS1196 form of the keyboard failure.

Device type indices, from the CDIB pointer order in `cdib.inc` `[DOC-IBM]`:

| devtype | CDIB slot | device |
|---|---|---|
| 0 | +4 | country - not reachable from `DEVINFO=` |
| **1** | **+6** | **SCR** |
| **2** | **+8** | **KBD** |
| 3 / 4 / 5 | +10 / +12 / +14 | LPT1 / LPT2 / LPT3 |

**So a failed `DEVINFO=SCR` does not halt, and it does not halt "before anything can render".** It
leaves the CDIB screen slot null, prints SYS1718 later in the boot, and the display **keeps
whatever font it already had**. `[DOC-IBM]` `cp3.txt` states the fallback: the display *"defaults
to the code page of ROM_0 for the device ... the device native code page or the lowest addressed ROM
code page"*, and for the keyboard, *"A keyboard layout defaults to the code page of the translate
table designated as the default layout in the KEYBOARD.DCP file. ... You must explicitly specify
KEYBOARD.DCP in the DEVINFO statement for the keyboard in CONFIG.SYS."*

**Whoever does read the two `.DCP` files, it is not the kernel's CONFIG.SYS processing.**

> ~~See `vio-kbd-mou.md` section 3.7 for the keyboard file's own layout and for what is still
> unestablished about its reader.~~ **ANSWERED 2026-09-09 - kept and marked rather than
> rewritten.** There is not one reader but **two, in two different modules**, and neither is the
> kernel. The subsection below names them; `vio-kbd-mou.md` section 3.7 remains the place for the
> keyboard file's own layout.

### The CDIB - the block the three NLS statements are processed *into*, and its two readers

`COUNTRY=`, `CODEPAGE=` and `DEVINFO=` do not each have a consumer. They have **one** consumer, and
it is a **structure**: the **Codepage Data Information Block (CDIB)**. `syicpInit` lays it out;
`syicpActivate` then issues `DosSetCp`, `VioSetCp` and `KbdSetCp` against it; `syiInstallDeviceDrivers`
runs afterwards (the call order above). IBM's own header says what the device sections are for
`[DOC-IBM]` `cdib.h:42-46`:

> *"Device Section - This section appears once for each device (screen, keyboard, LPT1, LPT2, and
> LPT3) for which a `DEVINFO=` statement was specified in the CONFIG.SYS file"*

**Layout is not repeated here.** `cdib.inc` is authoritative for offsets and widths, `cdib.h` for
meaning, and reading both is necessary rather than optional - the C header's pointers are
`near *` and its scalars bare `unsigned`, so only the `.inc` settles that every field is 16-bit.
`[DOC-IBM]` DDK `base/inc/cdib.inc`, `.../h/cdib.h`.

**It is published as a named shared segment, `\SHAREMEM\DOS\CDIB`**, and a reader attaches by
that name through `DosGetShrSeg`. `[DOC-IBM]`, three shipped IBM sites, two of which are the
readers below:

| the literal | site |
|---|---|
| `CDIBname db '\SHAREMEM\DOS\CDIB',0` | DDK `video/src/video/vdh/vdhgetcp.asm:75` |
| `idh_cdib db '\SHAREMEM\DOS\CDIB',0` (pushed at `idhinfo.asm:839`) | `.../vdh/idhequ.inc:160` |
| `DosGetShrSeg("\\SHAREMEM\\DOS\\CDIB", ...)` | `.../svdh/bvhfont.c:428` |

The kernel additionally records the CDIB's selector in the SAS: `SAS_info_CDIB`, *"selector for
Codepage Data"*. `[DOC-IBM]` `.../base/h/sas.h:128`, `.../base/inc/sas.inc:86`.

#### The two readers are in different modules, and only one of them talks to a driver

This is the part worth carrying, because the asymmetry is the design:

| half | who reads the `.DCP` | how it reaches the driver |
|---|---|---|
| **`DEVINFO=SCR`** | the **base video handler** - `BVHVGA`'s `GETCODEPAGE`. `DosGetShrSeg` -> `CDIB_screen_ptr` -> `CDIB_dev_filename_ptr` -> `DosOpen`. | **It does not.** There is no `DosDevIOCtl` on that path at all - the handler already owns the adapter, so it loads the font into its own buffers and programs the character generator itself. |
| **`DEVINFO=KBD`** | **`DOSCALL1` itself** - `KbdSetCp` -> `KBDSETCP` -> `ROUTER` -> `_KBDBASESUBSYS` -> `BKSMAIN` -> `SetCodepage` -> **`Init_CP`**, which reads `CDIB_keyboard_ptr`, `DosOpen`s the named file and walks its directory. | **`KBD$` category 4 function `0x5C` `SetCodePage`**, then `0x58` `SetInUseCP`. The driver never sees a filename - only tables. |

IBM ships the screen half as source, and it matches the shipped handler operation for operation:
`vdhgetcp.asm` `_GetCodePage` (*"Get CodePage Fonts from the Font File"*), with a near-identical
copy in `idhinfo.asm` `GetCodePage`. `[DOC-IBM]`

The keyboard chain and the identification of `GETCODEPAGE` are **`[INF]`** - read out of the
shipped `DOSCALL1` and `BVHVGA` binaries, corroborated by the IBM sources named above, but not
raised above the provenance those reads were recorded at. Entry-point **names** are IBM's and are
stable; the object-relative offsets that back them are build-keyed and are deliberately not
repeated here, per this section's opening note.

**Two consequences an implementer needs, and neither is guessable from the statement syntax.**
(1) `DEVINFO=SCR` and `DEVINFO=KBD` are the *same statement* processed into the *same structure*
and then consumed by **two unrelated modules on two unrelated schedules** - so a working screen
font says nothing about the keyboard table, and vice versa. (2) `Init_CP` byte-swaps the first word
of `CDIB_dev_subtype` as it copies it out, which is the same byte-swapped layout-ID convention
`vio-kbd-mou.md` section 3.7 records for the `KEYBOARD.DCP` directory - the two agree, and a reader that
matches the subtype literally will select the wrong country.

Where each file's own format is documented: the keyboard file in `vio-kbd-mou.md` section 3.7, the screen
file in `video-stack.md` section 2.1.1.

### How a boot-time message is rendered - and it is not `OSO001.MSG`, not at first

Every message initialisation can emit is a small descriptor - `{ WORD msgno; WORD n_inserts;
far pointer per insert }` - and `msgno` indexes `OSO001.MSG` directly. But:

* Until `syiGetLoadableEntries` has resolved DOSCALL1's ordinals, **every message is queued, not
  printed**, into a 0x800-byte linked list in a dedicated segment, with an overflow counter that
  later renders as **SYS2068** *"%1 messages were lost."*
* **The halt path needs no message file at all.** Ring-0 `syiRetrieveMessage` performs its own
  `%1..%9` substitution, and ring-0 `syiShowMessage` writes the result through the kernel's own
  direct-to-screen writer `h_WrtToScrn`.
* `OSO001.MSG` enters only once **`DosTrueGetMessage` (`DOSCALLS` ordinal 384)** has been resolved.

The halt itself, ring-0 `SYIAbort`, is: flush every queued message, display the specific failure
message, display **SYS2065**, `sti`, then an infinite interruptible spin. Only Ctrl-Alt-Del leaves
it.

### `PAUSEONERROR=YES` is the default, and it is why a warning *looks* like a halt

`syiDisplayMessageR3` sets an `error_messages_displayed` flag whenever the rendered text begins
`"SYS"` with a `':'` at index 7, then calls `syiPauseOnErrorR3`. That pauses only if the flag is
set, `PAUSEONERROR` is on, and the keyboard/message entry points are resolved; it then flushes the
keyboard buffer, renders **SYS1726** *"Press Enter to continue..."* and blocks on `KbdStringIn`.

`[DOC-IBM]` `cmdref21.txt`: *"**This is the default.** If there is not a PAUSEONERROR statement in
your CONFIG.SYS file, PAUSEONERROR=YES is assumed"*, and the pause happens *"before starting the
specified user interface or command processor"*.

**So on a default system any NLS warning stops the boot for a keypress.** That is observationally
close to a halt and is the likeliest origin of a belief that these failures are fatal - but it is a
*pause*, it requires a keyboard, and `PAUSEONERROR=NO` removes it entirely.

**Unestablished:** whether a boot with three warnings prompts once or three times. IBM's prose says
once, before the shell; the code arms and clears the flag around *each* message. One boot of a
system with three deliberately broken CONFIG.SYS lines, counting the prompts, settles it.

### The message numbers, and four that are not boot messages at all

Extracted from a shipped `OSO001.MSG` by parsing its MKMSGF index (header `FF "MKMSGF" 00`,
component `"SYS"`, count word at +0x0b = 3507, DWORD offset table at +0x1f) - re-derived for this
document, and sanity-checked against two known entries (index 2 = *"The system cannot find the file
specified."*, index 5 = *"Access is denied."*).

| # | sev | text | emitted by | halt? |
|---|---|---|---|---|
| 0443 | E | The CODEPAGE= statement in the CONFIG.SYS file is incorrect. | CONFIG.SYS parse | no |
| 1196 | E | The parameter "%3" on line %1 ... is not acceptable for the %2 statement.  Line %1 is ignored. | `syicpValidateCountry`, `syicpData`, `syicpActivate` | no |
| 1518 | I | The system cannot find the file "%1". ... | `syicpCountry`, default path | **YES** |
| 1718 | E | The system cannot find the file %3 specified in the %2 statement on line %1 ... Line %1 is ignored. | `syicpCountry` (`COUNTRY=` present) | **YES** |
| 1718 | E | (the same message, a different call site) | `syicpDevInfo` | no |
| 1726 | P | Press Enter to continue... | `syiPauseOnErrorR3` | - |
| 1729 | E | The code page %1 is not acceptable for the display. | `syicpActivate` | no |
| 1730 | E | The code-page combination %1 is not acceptable for the keyboard or the DEVINFO command is incorrect. | `syicpActivate` | no |
| 1733 | E | The country information file %1 is incorrect. | `syicpCountry`/`syicpData`, default path | **YES** |
| 1737 | I | Code page switching is not available. | `syicpInit` | no |
| 2030 | I | The system does not have enough memory to start the operating system. | `syicpInit`, `syicpCountry` | **YES** |
| 2065 | I | The system is stopped.  Correct the preceding error and restart the system. | ring-0 `SYIAbort`, always last | - |
| 2068 | E | %1 messages were lost. | message-queue overflow | no |
| 2069 | E | The country information file %3 specified in the %2 statement on line %1 ... is incorrect. | `syicpCountry`/`syicpData` (`COUNTRY=` present) | **YES** |

**SYS0396-SYS0401 are not boot messages.** They are the NLS **API** return codes - 396
`ERROR_NLS_NO_COUNTRY_FILE`, 397 `ERROR_NLS_OPEN_FAILED`, 398 `ERROR_NO_COUNTRY_OR_CODEPAGE`, 399
`ERROR_NLS_TABLE_TRUNCATED` - rendered by whatever command hit them. **SYS0400 and SYS0401 have no
text of their own**: both are the generic *"Record this message number and contact your service
representative."* in the shipped catalogue, and both are blank in the explanation companion
`OSO001H.MSG`. Nothing in boot-time NLS initialisation emits any of the six.

Likewise the SYS17xx keyboard-translation messages are **not** initialisation's.
**SYS1741 and SYS1742 name their caller in their own text** - *"The **KEYB command** cannot find
the translation table file for the keyboard in the path specified by the DEVINFO= statement"* -
and **SYS1745 is an interactive `(Y/N)` prompt** (*"Do you want to load the translation table for
the default code page (Y/N)?"*), which a boot has no way to answer. SYS1746, SYS1750 and SYS1751
sit in the same catalogue run and describe the same operation, but **their text names no caller**,
so attributing them to the same command is `[INF]`, not read out of anything.

### The thirteen `DOSCALLS` entry points initialisation resolves, by ordinal

`syiGetLoadableEntries` loads the module `DOSCALL1` once and then calls `DosGetProcAddr` thirteen
times **in the ordinal form** (a far pointer whose selector is zero). Both failure paths - SYS1722
cannot load the DLL, SYS1723 cannot find the entry point - go to `syiAbortR3`, so **every one of
the thirteen is a halt if it is missing**.

| ordinal | symbol in the kernel's own `.sym` |
|---|---|
| 144 | `pDosExecPgm` |
| 384 | `pDosGetMessage` |
| 383 | `pDosPutMessage` |
| 649 | `pDosCloseMessageFile` |
| 757 | `pKbdFlushBuffer` |
| 753 | `pKbdStringIn` |
| 748 | `pKbdCharIn` |
| **749** | **`pKbdSetCp`** |
| **810** | **`pVioSetCp`** |
| 713 | *(unnamed in the map)* |
| 143 | *(unnamed in the map)* |
| 141 | *(unnamed in the map)* |
| 855 | `pDosSMSysInitSem` |

The ordinals are `[OBS-RE]`, read as words in the descriptor table; the symbols are IBM's own. The
five that matter to NLS - `DosGetMessage`, `DosPutMessage`, `DosCloseMessageFile`, `KbdSetCp`,
`VioSetCp` - are each independently confirmed by how the call site uses them.


---

**Ratified (2026-07-26):** checked against the IBM Toolkit 4.5 headers
(`bsedos.h`, `bsetib.h`) and the IBM OS/2 Control Program reference
(IBM OS/2 Control Program Reference, redbooks `gg243731`/`gg243774`).
Confirmed and upgraded to **[DOC-IBM]**: the environment-block double-null format (via `DosExecPgm`
EnvPointer, CP ref); `PIB.pib_pchenv` (`bsetib.h:73`); `DosScanEnv` (`bsedos.h:2616`, semantics per
CP ref); `DosQueryCp` current-code-page-then-prepared-list semantics (CP ref `DosGetCp`);
`DosQueryCtryInfo` / `COUNTRYINFO` full field layout (`bsedos.h:2314-2330`) and `fsDateFmt` values (CP
ref `DosGetCtryInfo`); `DosQueryDBCSEnv` lead-byte-range format (CP ref `DosGetDBCSEv`).
Not upgraded (negative result, kept **[DOC]**): the CONFIG.SYS multi-pass category-scan order and the
placement of the environment/NLS groups - no IBM primary consulted fixes the pass order; residual
uncertainty note preserved.

## See also
- `session-manager.md` - sessions that inherit this environment; `boot-sequence.md` (Stage 8) - where CONFIG.SYS is processed.
- `vio-kbd-mou.md` section 3.7 - `DEVINFO=KBD`'s other half: the `KEYBOARD.DCP` file's own layout, and
  what installs a translate table into the keyboard driver.
- `video-stack.md` section 2.1.1 - `DEVINFO=SCR`'s other half: the code-page font file (`.DCP`) format
  and the ROM-font fallback a dropped `DEVINFO=SCR` line leaves in place.
