# OS/2 Module and Dynamic-Link-Library Management

How an OS/2 program locates, loads, and calls code in a dynamic link library (DLL): the
run-time module-manager API (`DosLoadModule`, `DosFreeModule`, `DosQueryProcAddr`,
`DosQueryModuleHandle`, `DosQueryModuleName`, `DosQueryProcType`), the DLL model itself
(load-time versus run-time linking, import by name versus by ordinal, the `_DLL_InitTerm`
library entry point and its per-process versus global forms, exported entry points and
forwarders), and how a module-definition (`.DEF`) file declares what a module exports and
imports. This reference covers the module *interface*; the on-disk executable/DLL container
layout (the LX/NE segment and object tables) is in `executable-formats.md`, and the `_System`
linkage plus the full `.DEF` `LIBRARY`/`EXPORTS`/`IMPORTS` syntax are in `calling-convention.md`
and are not duplicated here.

Provenance: **[DOC-IBM]** the OS/2 Toolkit header `bsedos.h` (all module-manager prototypes,
`INCL_DOSMODULEMGR`), `os2def.h` (`HMODULE`, `PFN` types), the OS/2 Linear-eXecutable reference
`lxref.htm` (the library initialization/termination register-and-stack contract and the
module-flag bits), a Toolkit `SAMPLES` DLL entry point and `.DEF` files (the `_DLL_InitTerm`
prototype and the `LIBRARY ... INITINSTANCE TERMINSTANCE` form); **[DOC]** the IBM OS/2 2.0
Programming Guide (GG24-3774) "Dynamic Link Libraries" / "Creating a DLL" / "Using a DLL" and the
Control Program reference stubs (the OS/2 1.x names and load-failure buffer). Every prototype and
constant below is transcribed from a source file that was opened; nothing is supplied from memory.

---

## The dynamic-linking model [DOC / DOC-IBM]

A DLL is a module containing code and/or resources that one or more programs share at run time
rather than binding a private copy at link time. Multiple processes use the same memory-resident
copy of the DLL code, and the code in a DLL can be changed without re-linking the programs that
use it. [DOC - GG24-3774 "Dynamic Link Libraries".] A program resolves the external references to
a DLL's exported entry points in one of two ways:

- **Load-time (implicit) linking.** The reference is resolved by the loader when the program
  module is loaded: the executable records an import of "export *N* (or export name *S*) of module
  *M*", and the loader loads *M* and binds the reference before the program runs. The program
  declares these imports through an `IMPORTS` statement in its `.DEF` file, or by linking against an
  **import library** (built with `IMPLIB` from a `.DEF`); the system's own `OS2386.LIB` / `OS2.LIB`
  is itself an import library describing the DLLs that implement the OS/2 API. [DOC - GG24-3774
  "Using a DLL".]
- **Run-time (explicit) linking.** The program has no compile-time reference; it calls
  `DosLoadModule` to load a named DLL, `DosQueryProcAddr` to obtain the address of an entry point
  (by name or by ordinal), calls through the returned function pointer, and `DosFreeModule` when
  finished. [DOC-IBM - `bsedos.h`.]

Both forms reach the same exported code; the calling convention (`_System` for 32-bit,
`_Far16 _Pascal` for 16-bit - see `calling-convention.md`) is a property of the declared prototype,
independent of which linking method or which reference form (name/ordinal) resolved it.

### Import by name versus by ordinal [DOC-IBM]

Each export a DLL provides is identified both by its name and by a small integer **ordinal**
assigned in the `.DEF` `EXPORTS` statement (`name @N`). An importer may bind to an export **by
ordinal** (`MODULE.N`) - the compact, position-stable form used for the core system DLLs
(`DOSCALLS`, `PMWIN`, ...) - or **by name** (`MODULE.EXPORTNAME`), resolved by string match. The
`.DEF` syntax for both is documented in `calling-convention.md` ("Ordinal vs by-name imports").

---

## The run-time module-manager API

All prototypes are declared under `#ifdef INCL_DOSMODULEMGR` in `bsedos.h`. `HMODULE` is a module
handle (`typedef LHANDLE HMODULE`, i.e. `unsigned long`; `PHMODULE` is its pointer -
`os2def.h:232,242`); `PFN` is an `APIENTRY`-linkage function pointer (`os2def.h:112`). Every
function returns an `APIRET` (0 = success, non-zero `ERROR_*`). [DOC-IBM - `bsedos.h`, `os2def.h`.]

| Symbol | Purpose |
|---|---|
| `DosLoadModule` | Load a DLL by name (run-time linking); return its handle, or the name of the object that caused a load failure |
| `DosFreeModule` | Release a handle obtained from `DosLoadModule`; unload the DLL when its use count reaches zero |
| `DosQueryProcAddr` | Get the address of an exported entry point, by ordinal or by name |
| `DosQueryModuleHandle` | Get the handle of an already-loaded module, by name |
| `DosQueryModuleName` | Get the fully-qualified file name of a module, from its handle |
| `DosQueryProcType` | Report whether a given entry point is 16-bit or 32-bit code |
| `DosQueryModFromEIP` | Identify the module (and object/offset) containing a given code address |
| `DosReplaceModule` | Replace an in-use module file with a new one (or restore a backup) |

### `DosLoadModule` [DOC-IBM]

```c
APIRET APIENTRY DosLoadModule(PSZ pszName, ULONG cbName, PSZ pszModname, PHMODULE phmod);
```
(`bsedos.h:2142-2151`; `PCSZ` in the C++ variant.)

The parameter naming is easy to misread: `pszModname` (parameter 3) is the **input** - the name of
the module to load - and `pszName`/`cbName` (parameters 1-2) are an **output error buffer** and its
length, into which the loader writes the name of the object (typically a dependent module) that
caused the load to fail when the call returns an error. A Toolkit sample illustrates the argument
order - `DosLoadModule(szLoadError, sizeof(szLoadError), szDevDLLName, &hModHandle)`
(`SAMPLES/MM/ADMCT/loadsubs.c`, shown in a commented-out reference line). `phmod` receives the
module handle on success.

If the named module is already loaded, its existing handle is returned and its use count is
incremented rather than a second image being mapped; the module is not physically unloaded until
every `DosLoadModule` is matched by a `DosFreeModule`.

The 16-bit predecessor took the same argument order - an object-name buffer (returned), the buffer
length, the module-name string, and the returned handle - under the OS/2 1.x name (see "Naming"
below). [DOC - Control Program reference `DosLoadModule` stub.]

### `DosFreeModule` [DOC-IBM]

```c
APIRET APIENTRY DosFreeModule(HMODULE hmod);
```
(`bsedos.h:2153`.) Releases one reference to `hmod`. The module image is unloaded - and its
per-process termination routine (below) run - when the last reference in the process is freed.

### `DosQueryProcAddr` [DOC-IBM]

```c
APIRET APIENTRY DosQueryProcAddr(HMODULE hmod, ULONG ordinal, PSZ pszName, PFN *ppfn);
```
(`bsedos.h:2156-2165`; `PCSZ` in the C++ variant.) Returns, in `*ppfn`, a callable pointer to an
export of `hmod`. The export is selected **by ordinal** if `ordinal` is non-zero, otherwise **by
name** using the string `pszName`. The returned pointer is invoked with the convention of its
declared prototype.

The `ordinal` must be <= 65 533, and the name match is not case sensitive. For entries within the
`DOSCALLS` module only **ordinal** references are supported - a by-name reference to `DOSCALLS`
returns an error - which is why `DOSCALLS` ordinals are resolved by linking against `OS2386.LIB`.
If the call returns `ERROR_INVALID_HANDLE`, the module may not be loaded; reissue `DosLoadModule`
and repeat. [DOC - EDM2 "DosQueryProcAddr".]

| `rc` | Value | Meaning |
|---|---|---|
| `NO_ERROR` | `0` | Address returned in `*ppfn` |
| `ERROR_INVALID_HANDLE` | `6` | `hmod` is not a valid loaded-module handle |
| ~~`ERROR_INVALID_NAME`~~ | ~~`123`~~ | ~~`pszName` does not name an export of the module~~ - see the correction below |
| `ERROR_INVALID_ORDINAL` | `182` | `ordinal` does not name an export of the module |
| `ERROR_ENTRY_IS_CALLGATE` | `65079` | The entry point is reachable only via a call gate |

[DOC - EDM2 "DosQueryProcAddr".]

> **CORRECTED (Rule 1.7):** for a name the module does not export, real OS/2 returns **127
> `ERROR_PROC_NOT_FOUND`**, not 123, and leaves `*ppfn` untouched [OBS-RE - measured on Warp Server
> for e-business 4.50, kernel revision 14.089, against a DLL of the probe's own]. A by-name lookup
> on `DOSCALLS` likewise returns 127. Code that tests for 123 to mean "no such export" never sees
> it.

**More measured module-manager results** [OBS-RE - same system; a 32-bit probe and two DLLs of its
own, plus lookups on `DOSCALLS`, `DOSCALL1` and `UCONV`]:

- `DosLoadModule` of a missing DLL returns 2 and names it in the object buffer. A DLL whose
  initialisation routine fails returns 295 `ERROR_INIT_ROUTINE_FAILED`, is not loaded, and leaves
  the object buffer untouched. When DLL B imports DLL A, A's initialisation runs before B's.
- `INITGLOBAL` initialisation runs once system-wide; `INITINSTANCE` runs in every process; a
  process that ends with the DLL loaded runs its termination once. `DosFreeModule` runs the
  termination; freeing the same handle again returns 6.
- `DosQueryModuleHandle` of a DLL that is not loaded returns 126 `ERROR_MOD_NOT_FOUND`.
- `DosQueryModuleName` returns the path the module was loaded from; a buffer too small returns 24
  `ERROR_BAD_LENGTH`; a bad handle 6.
- `DosQueryProcAddr` and `DosQueryProcType` with the program's own (EXE) handle return 6.
- **`DOSCALLS` and `DOSCALL1` are different modules to the loader.** `DosLoadModule("DOSCALLS")`
  returns its own handle (7 on that system), which `DosQueryModuleName` reports as
  `C:\OS2\DLL\DOSCALLS.DLL`, while `DOSCALL1` has another (0xF7). An ordinal looked up through
  `DOSCALLS` (348, `DosQuerySysInfo`) gives the same address as through `DOSCALL1`, and
  `DosQueryModFromEIP` on that address reports `DOSCALL1`. A by-name lookup works on `DOSCALL1`
  (`DOSSUBALLOC`, reported `PT_16BIT`) and fails with 127 on `DOSCALLS`.

### `DosQueryModuleHandle` [DOC-IBM]

```c
APIRET APIENTRY DosQueryModuleHandle(PSZ pszModname, PHMODULE phmod);
```
(`bsedos.h:2168-2173`; `PCSZ` in the C++ variant.) Returns, in `*phmod`, the handle of a module
that is **already loaded**, located by name. Unlike `DosLoadModule` it does not load the module and
does not change its use count.

### `DosQueryModuleName` [DOC-IBM]

```c
APIRET APIENTRY DosQueryModuleName(HMODULE hmod, ULONG cbName, PCHAR pch);
```
(`bsedos.h:2175-2177`.) The inverse of `DosQueryModuleHandle`: writes the fully-qualified file
name of the module identified by `hmod` into the caller's buffer `pch` of length `cbName`.

### `DosQueryProcType` [DOC-IBM]

```c
APIRET APIENTRY DosQueryProcType(HMODULE hmod, ULONG ordinal, PSZ pszName, PULONG pulproctype);
```
(`bsedos.h:2183-2192`.) Selects an export the same way as `DosQueryProcAddr` (by `ordinal` if
non-zero, else by `pszName`) and reports its code width in `*pulproctype`:

| Constant | Value | Meaning |
|---|---|---|
| `PT_16BIT` | `0` | The entry point is 16-bit code |
| `PT_32BIT` | `1` | The entry point is 32-bit code |

(`bsedos.h:2179-2180`.) This lets a caller thunking across the 16/32 boundary discover which
convention a resolved entry point actually uses (see `thunking.md`).

### `DosGetResource` / `DosFreeResource` / `DosQueryResourceSize` - measured failure codes

```c
APIRET APIENTRY DosGetResource(HMODULE hmod, ULONG idType, ULONG idName, PPVOID ppb);
APIRET APIENTRY DosFreeResource(PVOID pb);
APIRET APIENTRY DosQueryResourceSize(HMODULE hmod, ULONG idt, ULONG idn, PULONG pulsize);
```
(`bsedos.h:2284-2296`; `DosGetResource2` is a macro for `DosGetResource`.) `hmod` 0 means the
calling program's own EXE.

**The three failures are 126, 87 and 87 - and 126 is not "resource not found"** [OBS-RE - measured
on Warp Server for e-business 4.50, kernel revision 14.089, with a DLL of the probe's own; the
kernel's loader read with its symbols]:

| Condition | Result |
|---|---|
| `hmod` is not a live module (never was one, or freed) | 126 `ERROR_MOD_NOT_FOUND` (IBM's list has 6) |
| a live module with no resources at all (including `hmod` 0 for an EXE without any) | 87 |
| a live module that has resources, but not this type/id | 87 |
| `idType` above 0xFFFF | 87 |

`DosQueryResourceSize` gives the same codes for the same conditions, and leaves `*pulsize`
untouched when it fails; a failed `DosGetResource` leaves `*ppb` untouched.

**References are counted per resource object.** `DosGetResource` of the same resource twice gives
the same address; two gets need two `DosFreeResource` calls (0, 0) and a third returns 487. Two
different resource ids that the linker placed in one object share that count: get id 1, get id 3,
then three frees of id 3 return 0, 0, 487. `DosQueryResourceSize` takes no reference.
`DosFreeResource` of an address inside a resource frees it (0); of a static, NULL or a stack address
it returns 87; of a code address, 1.
**The tell:** code that maps 87 to "bad handle", or 126 to "missing resource", reports the wrong
problem.

### `DosQueryModFromEIP` and `DosReplaceModule` (related) [prototypes DOC-IBM; behavior inferred from the parameter names]

```c
APIRET APIENTRY DosQueryModFromEIP(HMODULE *phMod, ULONG *pObjNum, ULONG BuffLen,
                                   PCHAR pBuff, ULONG *pOffset, ULONG Address);
APIRET APIENTRY DosReplaceModule(PSZ pszOldModule, PSZ pszNewModule, PSZ pszBackupModule);
```
(`bsedos.h:2194-2199, 2213-2220`.) `DosQueryModFromEIP` maps a code address (`Address`) back to the
module handle, object number, name, and offset that contain it - the basis of a symbolic
backtrace. **The object number is zero-based** (LX object 1 is reported as 0); an address in no
module returns 487 `ERROR_INVALID_ADDRESS`; a `BuffLen` of 2 still returns 0 [OBS-RE - measured on
Warp Server for e-business 4.50, kernel revision 14.089]. `DosReplaceModule` swaps a module's on-disk file (optionally saving a backup) so a
loaded module can be updated. (The prototypes are transcribed from `bsedos.h`; the header carries
no descriptive prose, so the behavioral summaries above are read from the parameter names, not a
documented sentence.) The related function `DosQueryModFromCS` - the callable Toolkit symbol is
`Dos16QueryModFromCS` (`bsedos.h:2233`), `DosQueryModFromCS` being the documentation-level name in
the header comment - returns a `QMRESULT` `{ USHORT seg; USHORT hmte; CHAR name[CCHMAXPATH]; }`
(`bsedos.h:2225-2229`); it and `QMRESULT` are guarded `#if __IBMC__ || __IBMCPP__` (IBM-compiler only).

The `DosReplaceModule` behavior read from the parameter names above is confirmed by community
documentation: the function loads the entire in-use module (`pszOldModule`) into memory and
releases the filesystem's hold on the file, optionally copies the current image to
`pszBackupModule`, then replaces the on-disk file with `pszNewModule`; the system keeps using the
cached old module until every reference is released, and the next reference reloads from the new
file. Only protect-mode executable/DLL files may be replaced (not DOS/Windows programs or data
files); `pszNewModule` and `pszBackupModule` may be NULL. The entry point is `DOSCALLS.417` and is
defined in `OS2386.LIB`. [DOC - EDM2 "DosReplaceModule".]

| `rc` | Value | Meaning |
|---|---|---|
| `NO_ERROR` | `0` | Module replaced (or cached) |
| `ERROR_FILE_NOT_FOUND` | `2` | A named file does not exist |
| `ERROR_PATH_NOT_FOUND` | `3` | A named path does not exist |
| `ERROR_ACCESS_DENIED` | `5` | Access to a named file was denied |
| `ERROR_NOT_THE_SAME_DEVICE` | `17` | Files are not on the same device |
| `ERROR_NOT_DOS_DISK` | `26` | Target is not a recognized disk |
| `ERROR_SHARING_VIOLATION` | `32` | A sharing conflict on a named file |
| `ERROR_INVALID_PARAMETER` | `87` | A parameter is invalid |
| `ERROR_DRIVE_LOCKED` | `108` | The drive is locked |
| `ERROR_DISK_FULL` | `112` | No space to cache/back up the module |
| `ERROR_DIRECTORY` | `267` | A name refers to a directory |
| `ERROR_MODULE_IN_USE` | `296` | Module-in-use condition |
| `ERROR_MODULE_CORRUPTED` | `731` | The replacement module image is corrupt |

[DOC - EDM2 "DosReplaceModule".]

---

## The `_DLL_InitTerm` entry point [DOC-IBM]

A DLL may name a single **library entry routine** that the loader calls when a process gains or
loses access to the DLL. By convention the C runtime supplies this routine under the name
`_DLL_InitTerm`; a Toolkit sample gives its exact prototype and behaviour:

```c
unsigned long _System _DLL_InitTerm(unsigned long handle, unsigned long flag);
```
(`SAMPLES/OPEN32/DLLENTRY/dllmain.c:47`.) It receives the DLL's own module `handle` and a `flag`
selecting the direction:

| `flag` | Direction | Meaning (from the sample's own comments) |
|---|---|---|
| `0` | **Initialization** | "A process is gaining access to this DLL" |
| non-zero | **Termination** | "A process is losing access to this DLL" |

The return value reports success: a **non-zero** return means the routine succeeded, and a **zero**
return means it failed (the sample returns `0` when `_CRT_init()` fails and `TRUE` otherwise). On
initialization the routine performs C-runtime setup and C++ static constructors
(`_CRT_init`, `__ctordtorInit`); on termination it runs destructors and C-runtime teardown
(`__ctordtorTerm`, `_CRT_term`). [DOC-IBM - `SAMPLES/OPEN32/DLLENTRY/dllmain.c:47-95`.]

### The underlying loader contract [DOC-IBM]

`_DLL_InitTerm` sits on top of the module's declared **library entry address**. The LX executable
reference specifies the register/stack state at which the loader enters that address. On
**initialization** and **termination** the loader enters with (`lxref.htm`, "Library initialization
/ termination registers"):

| Location | Value |
|---|---|
| `EIP` | Library entry address |
| `CS` | Code selector for the base of the linear address space |
| `DS = ES = SS` | Data selector for the base of the linear address space |
| `FS` | Data selector for the base of the Thread Information Block (TIB) |
| `GS`, `EAX`, `EBX`, `ECX`, `EDX`, `ESI`, `EDI`, `EBP` | `0` |
| `[ESP+0]` | Return address to the system (`EAX` = return code) |
| `[ESP+4]` | Module handle for the library module |
| `[ESP+8]` | `0` = Initialization, `1` = Termination |

This is exactly the `(handle, flag)` pair `_DLL_InitTerm` receives - `[ESP+4]` is `handle`,
`[ESP+8]` is `flag` - so `flag == 0` is init and `flag == 1` (non-zero) is termination, agreeing
with the sample. A library whose entry-address object number is **zero** has no entry routine.
[DOC-IBM - `lxref.htm`.]

### Per-process versus global initialization/termination [DOC-IBM]

Whether the entry routine runs **once per process** that attaches to the DLL or **once globally**
for the whole system is fixed by two module flags recorded in the DLL's header
(`lxref.htm`, module flags):

| Flag | Value | Effect |
|---|---|---|
| Per-Process Library Initialization | `0x00000004` | Entry routine runs on init **for each process** that gains access |
| Per-process Library Termination | `0x40000000` | Entry routine runs on term for each process that loses access |

When the initialization bit is **not** set (but a valid entry address exists), **Global Library
Initialization** is assumed - the routine runs only once - and likewise for termination. If the
per-process **termination** bit is set, the entry-address object must be a 32-bit object. Setting
either bit is invalid for a program (`.EXE`) module. [DOC-IBM - `lxref.htm`.]

These flags are chosen through the `.DEF` `LIBRARY` statement. The `INITINSTANCE` and
`TERMINSTANCE` keywords request the **per-process** (instance) form - "any initialization code
should be executed for each process which accesses the DLL" - e.g.
`LIBRARY MYDLL INITINSTANCE TERMINSTANCE` (IBM redbook GG24-3774 p.122; also
`SAMPLES/TCPIPTK/SAMPDLL/sampdllm.def`). Absent those keywords the global form (single init/term)
applies. [DOC-IBM - GG24-3774 "Creating a DLL"; Toolkit `.DEF` samples.] A DLL accessed by
separate processes generally also declares `DATA MULTIPLE` so each process gets its own copy of the
DLL's data segment. [DOC - GG24-3774 "Creating a DLL".]

---

## Exported entry points and forwarders

### Exportable entry points [DOC]

An **exportable entry point** is a function invoked from outside its own module - either called
explicitly by another module or called back by the system (a window procedure invoked by
Presentation Manager is the canonical example). [DOC - GG24-3774 glossary "exportable entry
point".] A DLL lists each such function in its `.DEF` `EXPORTS` statement, optionally pinning an
ordinal (`name @N`) and optionally aliasing an external name to a different internal one
(`externalname=internalname`); the full syntax is in `calling-convention.md`.

### Forwarders [DOC / OBS-RE]

An export entry need not name code in its own module: it may **forward** to an export of another
module, so that a reference resolved to `A.foo` is transparently satisfied by `B.bar`. This lets a
DLL re-export another DLL's entry points (or rename/relocate an API across module boundaries)
without a stub. In OS/2, forwarders are used heavily by the thin system DLLs that re-export the
kernel's `DOSCALLS` entries. The forwarder is recorded in the module's entry table as a reference
to a target module + target export (by name or ordinal); the on-disk encoding of a forwarder entry
belongs to `executable-formats.md`. [DOC - the LX entry-table forwarder form; OBS-RE - the system
DLLs that forward into `DOSCALLS`.]

### Replacing a system DLL with a forwarder: measured traps [OBS]

Measured on Warp Server for e-business CP2 by replacing `PMGPI.DLL` system-wide with a DLL whose
slots forward to IBM's original, renamed. Each item is a trap, the fact, and the tell.

- **Building forwarders with OpenWatcom 1.9 `wlink`.** The linker guide documents no forwarder
  syntax, but exporting a symbol that is itself an `IMPORT` emits an LX forwarder entry with no
  stub (`IMPORT x PMGPI.358` then `EXPORT x.358`). `ANONYMOUSEXPORT`, documented for Win16/Win32
  only, also works for OS/2 LX and leaves the name out of both name tables - needed to reproduce a
  module that leaves slots unnamed. Trap: with no `OPTION DESCRIPTION`, the first exported name
  lands in the non-resident table's description slot and that ordinal loses its name. Verify with
  `lx_export.py`: every slot should print as `forwarder`.
- **The renamed original needs a different internal module name.** The forwarder must be named
  `PMGPI` internally, and so is IBM's file; renaming only the file leaves two modules with one
  name. A same-length name patched into the resident name table's first entry (`pmgpi` ->
  `pmgpx`, one byte) avoids the clash. Check first that the module never names itself: search its
  unpacked objects (packed pages hide strings - `executable-formats.md`), with a positive control.
- **An all-forwarder replacement can stop the boot.** Tell: the PROTSHELL message *"The file
  PMMERGE->PMGPI specified in the PROTSHELL statement ... does not contain a valid program"*, with
  no return code. The same DLL loads and works at runtime. `DosLoadModule` run from a CONFIG.SYS
  `CALL=` line, before PM, returns **180 `ERROR_INVALID_SEGMENT_NUMBER`** with failing module
  "PMMERGE->PMGPI". Cause, as far as measured: `PMMERGE`'s 16-bit object reaches seven `PMGPI`
  ordinals through **16:16-pointer fixups** (source type 3), and resolving those through a
  forwarder fails at boot; giving just those seven ordinals real entries (a far `JMP` from a USE16
  object to the original, a near `JMP` for the two 32-bit ones) makes the boot succeed. The same
  fixups through a forwarder resolve at runtime, so the boot difference is inferred to be that the
  target module is still inside the unfinished `PMMERGE` import cycle - not isolated further.
  How to find such ordinals: list the importer's fixups (`lx_resolve_imports.py --kind import
  --all-objects`) and keep the source-type-3 ones.
- **`DosQueryProcAddr` follows a forwarder** to the final entry, 16-bit targets included, and
  **`DosQueryProcType` takes the entry's type from the object's bitness**: Watcom writes entries
  in a USE16 object as `entry32` bundles, yet `DosQueryProcType` reports them 16-bit.
- **Install without touching IBM's file.** `LIBPATH` is searched in order at boot too, so a DLL in
  a directory listed before `\OS2\DLL` replaces the system one; removing it restores the stock
  module. A dedicated directory added at the front of `LIBPATH` (after a leading `.`) keeps test
  DLLs apart from any real product's. Read `LIBPATH` from the target's own CONFIG.SYS: the systems
  measured begin theirs with `.`, and file copies of CONFIG.SYS taken at other times did not match.
- **A control for a module-load test needs a boot on which nothing has loaded the module.** A
  program started from a directory without the DLL still ran while another process had it loaded
  - inferred to be the loaded module satisfying the import by name; not isolated.

---

## Where the PM APIs actually live [OBS-RE]

**The DLL you link against is usually not the DLL that implements the function.** The `Win*` API
surface is spread across several modules, and the most-linked one is almost entirely forwarders.
This matters whenever you are resolving an ordinal, diagnosing `SYS2070`, replacing a module, or
interposing on an API - reasoning from the linked name will send you to the wrong binary.

Verify on the target system before relying on any row: the split is a property of the installed
build, not of the API.

| Module | What it really is |
|---|---|
| `PMWIN.DLL` | **Almost entirely forwarders into `PMMERGE`.** On Warp Server for e-business CP2 (XR04503) it is ~11 KB with **738 entry-table slots, every one a forwarder, and one imported module: `PMMERGE`**. It contains essentially no code. |
| `PMGPI.DLL` | **Real code, not a thin layer** (corrected; an earlier revision of this row called it "likewise thin over `PMMERGE`" by analogy with `PMWIN` - natural, but wrong). On WSeB CP2: **638 entry-table slots** - 294 16-bit entries, 343 32-bit, 1 forwarder (slot 399 -> `PMMERGE`) - with only **298 names**: every 16-bit entry and 4 of the 32-bit ones. The 32-bit API (`Gpi32CharString` #358, `Gpi32QueryFontMetrics` #453, ...) is **unnamed** and bound by ordinal only, so the ordinals in `bseord.h` are the only map. Imports `PMMERGE`, `DOSCALLS`, `PMGRE`, `PMWIN` and others. [OBS-RE - `lx_export.py`, name tables read directly] |
| `PMMERGE.DLL` | The actual window manager + GPI engine + GRE dispatch. |
| `PMCTLS.DLL` | **Real code.** Owns the standard dialogs: `WINFONTDLG` @2, `WINDEFFONTDLGPROC` @3, `WINFILEDLG` @4, `WINDEFFILEDLGPROC` @5, `WINFREEFILEDLGLIST` @6. 287 entry-table slots (254 32-bit, 33 16-bit, 24 of them named), **zero** forwarders. Also the multi-line edit control and the container (`PMMLE.DLL` imports only `PMCTLS`). |
| `PMSDMRI.DLL` | **Resource-only** - 0 exports, 0 imports, one read-only data object. Holds the standard dialog *templates* (the file dialog is `RT_DIALOG` id 256) and nothing else. |
| `PMSHAPI.DLL`, `PMDRAG.DLL`, `PMWP.DLL` | Shell API, direct manipulation, Workplace Shell class API. |

Two practical consequences:

- **Applications bind these by ordinal, at load time.** The OS/2 System Editor (`E.EXE`) imports
  `PMCTLS #2, #3, #4, #5` - i.e. the font and file dialog entry points - with no names involved.
  When you replace a module you must reproduce its **ordinals**, not just its names.
- **A resource-only module can only be changed cosmetically.** Swapping `PMSDMRI.DLL` alters how
  a standard dialog *looks*; it cannot alter what it *does*, because there is no code in it.
  Behaviour lives in `PMCTLS`.

Establish these facts yourself with `lx_export.py` (`--exports` / `--imports`) rather than
trusting the table; that is exactly what it is for, and it takes one command per module.

---

## Naming: `DosQueryProcAddr` versus `DosGetProcAddr` [DOC-IBM / DOC]

Several dynamic-linking function names were changed in OS/2 2.0 "to conform to the consistent
naming rules introduced in OS/2 Version 2.0." [DOC - GG24-3774 "Dynamic Linking".] The 32-bit
module-manager API therefore uses `DosQueryProcAddr` (`bsedos.h`), whereas the OS/2 1.x
(16-bit) Control Program used `DosGetProcAddr` for the same operation - get the address of an
exported procedure by name (`Control Program reference DosGetProcAddr` stub). `DosLoadModule` and
`DosFreeModule` kept their names across the transition. When reading older documentation, treat
`DosGetProcAddr` as the historical spelling of `DosQueryProcAddr`; the 32-bit toolkit does not
declare `DosGetProcAddr`. [DOC-IBM - `bsedos.h` (present: `DosQueryProcAddr`); absent:
`DosGetProcAddr`.]

---

## See also
- `calling-convention.md` - the `_System`/`APIENTRY` linkage and the full `.DEF`
  `LIBRARY`/`EXPORTS`/`IMPORTS` syntax (ordinal vs by-name).
- `executable-formats.md` - the on-disk LX/NE module container: object/segment tables and the
  entry-table encoding of ordinary and forwarder exports.
- `thunking.md` - how a resolved 16-bit entry point (see `DosQueryProcType`) is called from 32-bit
  code and vice-versa.
