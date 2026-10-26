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
  returns 0 and `DosScanEnv("path")` returns 203 `ERROR_ENVVAR_NOT_FOUND` [OBS-RE - measured on Warp
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

`SET RUNWORKPLACE=` also lives in this environment - it is the variable the Presentation-Manager
shell reads (boot-sequence Stage 12) to choose the desktop program.

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
