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

> **Provenance corrected 2026-08-31 (Rule 1.7), third pass.** 1 claim here
> was tagged `[OBS-RE]` and is now `[OBS]`. **No claim changed.** The
> discriminator is the METHOD, not the subject: `[OBS-RE]` names RE of a binary
> or the kernel debugger; `[OBS]` names a program run on real OS/2 whose result
> was recorded.  A ring-3 probe that *reads memory* is still a capture -
> you re-verify it by running the probe again, not by reading bytes - and that
> edge is what made this look like `[OBS-RE]`. Found on review: the earlier sweeps' keyword list did not match "observed on" or
> "on a live", so this sat outside a bound that claimed to cover it.

> **A DLL's objects are placed once, system-wide; later processes attach to that placement.**
> `[OBS]` "The same memory-resident copy" has a consequence that is easy to miss when
> reimplementing the loader: the *addresses* are a system-wide property, not a per-process
> decision. Observed on Warp 4.50 - a DLL already loaded by one process is found at identical
> object addresses in every other process that uses it, and nothing re-places it. The loader
> lives in the kernel and holds one view of the shared arena; a second user attaches rather
> than deciding for itself.
>
> This is what makes it safe for code in a DLL's shared data to cache a resolved entry-point
> address and for another process to call it - which OS/2 code does. It also means a design
> with one loader *per process*, each choosing addresses independently, is not merely slower
> but wrong: two processes will disagree about where a DLL's code lives, and any cached
> cross-process pointer becomes a wild branch. Preferred load addresses (section executable-formats,
> `E32NOINTFIX`) hide this for as long as every module happens to land where its header asked,
> and stop hiding it the moment one relocates.

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
> `ERROR_PROC_NOT_FOUND`**, not 123, and leaves `*ppfn` untouched [OBS - measured on Warp Server
> for e-business 4.50, kernel revision 14.089, against a DLL of the probe's own]. A by-name lookup
> on `DOSCALLS` likewise returns 127. Code that tests for 123 to mean "no such export" never sees
> it.

**More measured module-manager results** [OBS - same system; a 32-bit probe and two DLLs of its
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

**The three failures are 126, 87 and 87 - and 126 is not "resource not found"** [OBS + OBS-RE - measured
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
module returns 487 `ERROR_INVALID_ADDRESS`; a `BuffLen` of 2 still returns 0 [OBS - measured on
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

### A module handle is the caller's only if the caller uses the module `[OBS]`

Measured on WSeB 4.50: a process that never loaded PMWIN gets its handle from
`DosQueryModuleHandle("PMWIN")` (PMWIN being loaded by other processes), and then
`DosQueryProcAddr` on that handle - by name or by ordinal - returns **6**
`ERROR_INVALID_HANDLE`, `DosGetResource` returns **6**, and `DosFreeModule` returns **6**. A handle
that names no module at all gives `DosQueryProcAddr` 6 but `DosGetResource` **126**.

### Argument edges of the module calls `[OBS]`

Measured on WSeB 4.50 (revision 14.089, SMP), one process per case:

- **`DosLoadModule`**: a `phmod` that cannot be written (`NULL`, or an address in code) returns
  **87** `ERROR_INVALID_PARAMETER` whether or not the load itself succeeded. When it succeeded, the
  module is left loaded (`DosQueryModuleHandle` in the same process then finds it) and `pszName` is
  untouched; when it failed - a missing import - `pszName` still names the failing module, but the
  return is 87, not the load's own error. A failed load writes **0** to `*phmod`. A
  fully-qualified name whose directory does not exist is **3** `ERROR_PATH_NOT_FOUND`; one whose
  directory exists but whose file does not is **2**; both copy the name given to `pszName`.
- **The internal name against the file name** (`[OBS-RE]` the kernel's internal-name check, read
  at the instruction level in two SMP builds; `[OBS]` measured, three runs). On a library load - a
  `DosLoadModule`, or an import - take *B*, the basename of the file opened, uppercased and cut at
  its last `.` whatever the extension, and *N*, the module's internal name (its first resident
  name). For *B* up to 8 characters the load fails with **123** `ERROR_INVALID_NAME` exactly when
  *B* differs from *N* **and** *N* is no longer than *B*; `pszName` then receives the uppercased
  full path. So a module named `INST` loads from `INST.DLL`, `INST.FOO`, `E.DLL`, `INS.DLL` and
  `A.B.DLL`, and is refused from `ELDLL.DLL`, `ELDLL.FOO`, `INSTX.DLL`, `INST.X.DLL` and
  `ABCDEFGH.DLL`. Whether another module of that internal name is already loaded plays no part.
  For a basename over 8 characters the comparison runs past the 8-byte name field and gives no
  rule (9-, 10- and 13-character names were refused and a 20-character one loaded, on one boot).
  The check runs before the module is linked, so a refused module is never loaded. After loading,
  a module is found by its internal name for a bare-name request or an import, and by its full
  path for a path-qualified one `[OBS-RE]` (the kernel's module lookup: global modules matched by
  module name, specific ones by full path).
- **`DosQueryProcAddr`**: the handle is checked first - with a bad handle every case below is 6. A
  `pszName` of the form `"#n"` (ordinal 0) returns ordinal *n*'s address. Ordinal 0 with a `NULL`
  `pszName` is **115** `ERROR_PROTECTION_VIOLATION`. The ordinals tried above the documented limit
  of 65533 - 65534, 65535, 65536 and 70000 - and 65533 itself, like an ordinal the module does not
  export, were **182** `ERROR_INVALID_ORDINAL`. A `ppfn` that cannot be written
  (`NULL`) is **not** an error return: the caller ends with exception 5 (an access violation;
  `SYS1808`).
- **`DosQueryModuleHandle`**: a bare name finds the module with or without its `.DLL` extension; a
  fully-qualified name finds it only when it names the file the module was loaded from (another
  directory is **126**). On 126, `*phmod` is overwritten - 0x9F44 was read back whatever it held
  before; what that value is was not established.
- **`DosFreeMem`** on the base of a DLL's own object returns **0**: the object is freed. On the
  EXE's own code object the caller ends with exception 5 before it prints again (that it died
  returning into freed code is the likely mechanism; only the `SYS1808` was observed).

### Which DLLs get a termination call, and in what order `[OBS-RE]`

**Only a module with the per-process termination bit (`0x40000000`, `TERMINSTANCE`) is handed
its termination call** - on both paths that terminate DLLs: at process exit, and when
`DosFreeModule` lets a module go while the process lives. The kernel keeps the LX module flags
verbatim in the module table entry and both paths select on that bit; a module without it is let
go with no call. The global form above ("likewise for termination", `lxref.htm`) is not reached
by either path. **Measured [OBS], WSeB 4.50:** a DLL marked `INITGLOBAL` without `TERMINSTANCE`,
whose entry routine logs every call to a file, is initialized on `DosLoadModule`, gets **no** call on
`DosFreeModule`, and none when a process exits with it loaded; loaded again after the last process
let it go, it is initialized again. IBM's CP Guide table of `LIBRARY` options lists `INITINSTANCE`, `INITGLOBAL` and
`TERMINSTANCE` only `[DOC-IBM]`.

**Order at process exit:** the terminations are exit-list entries (after the ordinary exit-list
routines), run on thread 1. The kernel visits its module chain - path-loaded ("specific")
modules and `LIBPATH`-loaded ("global") ones in separate lists, each newest first - and puts each
module's entry in front of the others of its order, so the routines run **path-loaded modules
oldest first, then `LIBPATH` modules oldest first**, "oldest" being when the module was entered in
the chain. Termination order is therefore **not** the reverse of initialization order.
`DosFreeModule`'s terminations, for the modules a free lets go, run in the same order.
**Not established:** whether a module is entered in the chain before or after the modules it
imports, so whether dependants terminate before their dependencies.
[OBS-RE - SMP kernel: `_LDRDLLExitList`, `_ldrRegisterDLLTerm`, `_ldrSetupDLLTerm`,
`_ldrEnumDLLTerm`, `_ldrRunGraph`, `_ldrLinkMTE`, `_tkAddExitListRoutine`, `_ldrCreateMte`.]

---

## The `DOSCALLS` ordinal namespace is split across two modules `[OBS-RE]`

`DOSCALLS.#N` is **one 1..1117 ordinal namespace answered by two different
modules**, not by one file:

- a **kernel-resident pseudo-module** - `_DosModMte`, whose module name is the
  literal string `DOSCALLS` inline at `MTE+0x18`, with its own entry table
  (`dcm_entrytblstart`). `DOSCALL1.DLL` never sees calls to these ordinals; and
- **`DOSCALL1.DLL`'s own 555 LX exports.**

Partition over 1..1117: **371** kernel-only, **550** DOSCALL1-only, **5** in
both, **191** holes. The five overlaps are four LX forwarders (`#449`-`#452`, by
construction) plus `#12 DOSPTRACE`, which has both a `DOSCALL1.DLL` body and a
kernel gate - the kernel gate wins, and the body is unreachable through the
ordinal.

**The proof that `DOSCALLS` cannot mean "this file":** `DOSCALL1.DLL` exports 555
ordinals (12..999) but **imports 298 distinct `DOSCALLS.#N`** (2..1117), and
**271 of those it does not export** - 118 of them past its own highest export. A
module cannot import from itself an ordinal it does not export. The same pattern
holds for other importers: `PMMERGE.DLL` imports 197 and 49 are absent from
DOSCALL1's table; `PMWP.DLL` imports 98 with 2 absent. The absent ones are
exactly what a 16-bit program calls most - `#2 DOSCWAIT`, `#5 DOSEXIT`,
`#34 DOSALLOCSEG`, `#59 DOSCLOSE`.

**Consequence worth knowing:** which module answers an ordinal is not guessable
from its number or its name. The VIO block `770`-`844`, for instance, is
**entirely** DOSCALL1's - zero of those 75 appear in the kernel table - so those
entry points are real code ending in `retf N`, not thin kernel-gate stubs.

**Worked instances of the split, one from each side.** Both are reached only through another
module's forwarder. Which side an ordinal falls on decides what can be recovered about it and
how - and the pair below shows that answering the side question is a smaller thing than
identifying the entry point, not the same thing:

- **`#541` is kernel-side, and it is not known which kernel entry point it is.** It is reached
  through `DOSCALL1.DLL`'s own ordinal 567, one of that DLL's five forwarder entries. The RE
  corpus places it on the kernel side (tag 2, gate `0x272a`) and **declines to name it**: its
  table's name column for this ordinal holds a caller list rather than a name, and the
  `name_source` column reads `callers` - the corpus's explicit could-not-name bucket, which holds
  12 of the tag-2 ordinals. So the kernel-vs-`DOSCALL1` question is answered for `#541` while the
  identity question is not, and the two are genuinely separable. Nor does the byte count settle
  it: several plausible candidate entry points in the kernel share the same `pre_sci` immediate,
  so matching a count matches a family, not a function. Resolving `0x272a` through a live GDT
  walk is the open route. Recorded as a negative result so it is not re-found and mistaken for
  identification: third-party ordinal tables (the osfree wiki's `DOSCALLS` page, the 2ine import
  map) do put a name on `#541`, but the wiki annotates its own entry "internal undocumented
  function", osfree's `.def` files - which supply names for
  139 other ordinals - do not carry it, and the 2ine map assigns `#541` two different names in
  the same table. **[OBS-RE.]**
- **`#649 DosCloseMessageFile` is `DOSCALL1`-side.** It is reached through `MSG.DLL` ordinal 9 -
  the only one of that forwarder DLL's nine entries that leaves the contiguous `#383`-`#390`
  block. Being `DOSCALL1`-resident it has **no** `pre_sci` stub, so the count comes off its own
  exit instead: the entry at object 3 + `0x6f00` ends in a **bare `retf` with no immediate**, so
  the callee pops nothing and the count is **0** - matching a decompiled signature of
  `(void)`. **[DOC-IBM - `ORD_DOSCLOSEMESSAGEFILE EQU 9`, `bseord.inc:188`, at the end of the MSG
  block whose 1-8 match `MSG.DLL`'s forwarder table entry for entry; and the *OS/2 Debugging
  Handbook* System Ordinal Cross-Reference, `649 MSGCLOSEMESSAGEFILE`. OBS-RE - the shipped
  `MSG.DLL` and `DOSCALL1.DLL` tables and the entry's own `retf`.]**

**A name in the kernel's symbol table does not mean the ordinal routes there.** The kernel carries
`pre_sci` entry stubs for symbols it does not answer the `DOSCALLS` ordinal for - the 16-bit
named-pipe family `#399`-`#412` is the clean case: all fourteen are `DOSCALL1.DLL` object-4
callgates, yet the kernel also has `DOSMAKENMPIPE`, `DOSQNMPHANDSTATE` and their siblings as
`pre_sci` stubs whose counts agree. They agree because `DOSCALL1`'s entries are thin
argument-forwarding shims onto the same workers, not because the ordinal reaches the kernel stub.
Resolve which module answers an ordinal from the entry tables, not from a symbol-name match.
**[OBS-RE.]**

**Trap when using the Redbook's ordinal cross-reference.** The *OS/2 Debugging Handbook* carries
both a System Ordinal Cross-Reference and an error-code table, and the two are keyed by numbers
drawn from the same small range, so a bare numeric search hits both: `649` appears as
`649 MSGCLOSEMESSAGEFILE` in the ordinal table and as `649 VLPT DEVICE BUSY` in the error table,
and `541` as `541 PVW INVALID COUNTER BLK` in the error table with no ordinal entry at all. Read
the surrounding table, not the matched line. **[DOC-IBM.]**

Enumerated ordinal by ordinal in unpublished notes (v1, 2026-08-26), which also document a
hardcoded `DOSCALL1` check in IBM's own loader used to select the kernel table.

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

**A forwarder entry and a resident-name entry are independent, so a forwarder table does not
necessarily identify its own targets.** Both are optional per ordinal, and the shipped system
DLLs use every combination. Measured across four of them:

| Module | Forwarder entries | How many it also NAMES |
|---|---|---|
| `NAMPIPES.DLL` | 14 (ords 1-14 -> `DOSCALLS.#399`-`#412`) | **all 14** |
| `SESMGR.DLL` | 40 | includes ord 34 `QHKEYBDHANDLE` -> `#856`, ord 35 `QHMOUSEHANDLE` -> `#857` |
| `MSG.DLL` | 9 (ords 1-8 -> `#383`-`#390`, ord 9 -> `#649`) | **5 of 9** - including ord 9 |
| `DOSCALL1.DLL` | 5 (`#449`-`#452`, plus ord 567 -> `#541`) | **none of the 5** |

Where a forwarder is named, the name is the target's identity straight from IBM with no
disassembly - `SESMGR`'s ordinals 34/35 identify `DOSCALLS.#856`/`#857` as the keyboard and mouse
handle pair, each corroborating the other by adjacency. Where it is not, as with every one of
`DOSCALL1.DLL`'s five, the target has to be identified some other way. **[OBS-RE - the shipped
modules' entry and resident-name tables.]**

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


---

## The forwarder DLLs, and the complete shipped mapping `[DOC-IBM]`

`VIOCALLS`, `KBDCALLS`, `MOUCALLS` and eleven siblings are **pure forwarders**:
their exports are LX **type-4 entries** (`ENTRYFWD = 0x04`, 7-byte `FWDENT`,
`FWD_ORDINAL 0x01`) that name a target ordinal in another module - for all
fourteen, `DOSCALLS`. Nothing executes in them. An import of `VIOCALLS.#1` is an
import of `DOSCALLS.#726`.

**THE MAPPING APPEARS IN NO IBM HEADER, which is why it is transcribed here in
full.** `bseord.h`'s public DOSCALLS block **publishes nothing in the 719-865
band**, and that band is where the Vio/Kbd/Mou targets live. Surveyed 2026-08-26
across all 12 in-tree `bseord.h` copies: 11 have a DOSCALLS section, only the two
`toolkt21` copies stop at 646, nine publish names above it up to 999 - and **all
eleven agree the 719-865 band is empty**. (`watcom19/watcom/h/os2/bseord.h` has
no DOSCALLS section and is not evidence either way.) So the mapping exists only
in the shipped binaries.

**It is frozen.** These DLLs were shipped by IBM and their entry tables cannot
change, so this table is read once and true thereafter. It was produced by a
single scan of the fourteen DLLs in `\OS2\DLL` of an installed Warp 4.5 system on 2026-09-02,
parsing each entry table directly; each file's md5 is recorded below so a
different build can be told apart from this one rather than silently assumed
identical (the target is a 25-year binary family).

**241 forwarder entries across 14 DLLs.** `tools/forwarder_audit.py` still
exists and re-derives this from the same binaries, but **this table is the
record and the tool is the convenience** - the mapping is frozen, so it is read
once and true thereafter, and a fact that lives only inside a script is a fact
that has to be re-run to be known. Use the tool to re-check a *different* set of
DLLs (a different fixpak, another OS/2 release); use this table to know what
ours say.

### ANSICALL.DLL  (3 forwarder entries)
md5 `e6b18409e12afa88eb3b2e832dddef7c`, imports `DOSCALLS`

| ord | name in this DLL | forwards to |
|---|---|---|
| 1 | ANSIINJECT | DOSCALLS.#848 |
| 2 | ANSIKEYDEF | DOSCALLS.#849 |
| 3 | ANSIINTERP | DOSCALLS.#850 |

### BKSCALLS.DLL  (1 forwarder entries)
md5 `5c5123cdf735ca188c216ab0e0e76096`, imports `DOSCALLS`

| ord | name in this DLL | forwards to |
|---|---|---|
| 1 | BKSMAIN | DOSCALLS.#851 |

### BMSCALLS.DLL  (1 forwarder entries)
md5 `a06f9d863ee01e3abe9d79db581b5ce0`, imports `DOSCALLS`

| ord | name in this DLL | forwards to |
|---|---|---|
| 1 | BMSMAIN | DOSCALLS.#852 |

### BVSCALLS.DLL  (3 forwarder entries)
md5 `2f40f09f0b59a2c3e3cdee1e3e84b756`, imports `DOSCALLS`

| ord | name in this DLL | forwards to |
|---|---|---|
| 1 | BVSGETPTRDRAWNAME | DOSCALLS.#847 |
| 3 | BVSMAIN | DOSCALLS.#845 |
| 4 | BVSREDRAWSIZE | DOSCALLS.#846 |

### DOSCALL1.DLL  (5 forwarder entries)
md5 `a76530aa60c8e77db5001769d432783b`, imports `DOSCALLS, SESMGR`

| ord | name in this DLL | forwards to |
|---|---|---|
| 449 | *(unnamed)* | DOSCALLS.#449 |
| 450 | *(unnamed)* | DOSCALLS.#450 |
| 451 | *(unnamed)* | DOSCALLS.#451 |
| 452 | *(unnamed)* | DOSCALLS.#452 |
| 567 | *(unnamed)* | DOSCALLS.#541 |

### KBDCALLS.DLL  (25 forwarder entries)
md5 `702c35d8fac0e6a17ce3cdd291c48db1`, imports `DOSCALLS`

| ord | name in this DLL | forwards to |
|---|---|---|
| 1 | KBDSETCUSTXT | DOSCALLS.#745 |
| 2 | *(unnamed)* | DOSCALLS.#746 |
| 3 | KBDGETCP | DOSCALLS.#747 |
| 4 | KBDCHARIN | DOSCALLS.#748 |
| 5 | KBDSETCP | DOSCALLS.#749 |
| 6 | KBDLOADINSTANCE | DOSCALLS.#750 |
| 7 | KBDSYNCH | DOSCALLS.#751 |
| 8 | KBDREGISTER | DOSCALLS.#752 |
| 9 | KBDSTRINGIN | DOSCALLS.#753 |
| 10 | KBDGETSTATUS | DOSCALLS.#754 |
| 11 | KBDSETSTATUS | DOSCALLS.#755 |
| 12 | KBDGETFOCUS | DOSCALLS.#756 |
| 13 | KBDFLUSHBUFFER | DOSCALLS.#757 |
| 14 | KBDXLATE | DOSCALLS.#758 |
| 15 | KBDSWITCHFGND | DOSCALLS.#759 |
| 16 | KBDSHELLINIT | DOSCALLS.#760 |
| 17 | KBDCLOSE | DOSCALLS.#761 |
| 18 | KBDFREEFOCUS | DOSCALLS.#762 |
| 19 | KBDFREE | DOSCALLS.#763 |
| 20 | KBDDEREGISTER | DOSCALLS.#764 |
| 21 | KBDSETFGND | DOSCALLS.#765 |
| 22 | KBDPEEK | DOSCALLS.#766 |
| 23 | KBDOPEN | DOSCALLS.#767 |
| 24 | KBDGETHWID | DOSCALLS.#768 |
| 25 | *(unnamed)* | DOSCALLS.#769 |

### MOUCALLS.DLL  (28 forwarder entries)
md5 `c17ec2ea5e301ac04212e7c26c49f603`, imports `DOSCALLS`

| ord | name in this DLL | forwards to |
|---|---|---|
| 1 | MOUGETPTRSHAPE | DOSCALLS.#719 |
| 2 | MOUSETPTRSHAPE | DOSCALLS.#720 |
| 3 | MOUGETNUMMICKEYS | DOSCALLS.#721 |
| 4 | MOUGETHOTKEY | DOSCALLS.#853 |
| 5 | *(unnamed)* | DOSCALLS.#723 |
| 6 | MOUGETSCALEFACT | DOSCALLS.#724 |
| 7 | MOUFLUSHQUE | DOSCALLS.#725 |
| 8 | MOUGETNUMBUTTONS | DOSCALLS.#726 |
| 9 | MOUCLOSE | DOSCALLS.#727 |
| 10 | MOUSETHOTKEY | DOSCALLS.#854 |
| 11 | MOUSETSCALEFACT | DOSCALLS.#729 |
| 13 | MOUGETNUMQUEEL | DOSCALLS.#730 |
| 14 | MOUDEREGISTER | DOSCALLS.#731 |
| 15 | MOUGETEVENTMASK | DOSCALLS.#732 |
| 16 | MOUSETEVENTMASK | DOSCALLS.#733 |
| 17 | MOUOPEN | DOSCALLS.#734 |
| 18 | MOUREMOVEPTR | DOSCALLS.#735 |
| 19 | MOUGETPTRPOS | DOSCALLS.#736 |
| 20 | MOUREADEVENTQUE | DOSCALLS.#737 |
| 21 | MOUSETPTRPOS | DOSCALLS.#738 |
| 22 | MOUGETDEVSTATUS | DOSCALLS.#739 |
| 23 | MOUSYNCH | DOSCALLS.#740 |
| 24 | MOUREGISTER | DOSCALLS.#741 |
| 25 | MOUSETDEVSTATUS | DOSCALLS.#742 |
| 26 | MOUDRAWPTR | DOSCALLS.#743 |
| 27 | MOUINITREAL | DOSCALLS.#744 |
| 29 | MOUGETTHRESHOLD | DOSCALLS.#722 |
| 30 | MOUSETTHRESHOLD | DOSCALLS.#728 |

### MSG.DLL  (9 forwarder entries)
md5 `fb316c5a33d90490cf251da51ef3cce1`, imports `DOSCALLS`

| ord | name in this DLL | forwards to |
|---|---|---|
| 1 | DOSPUTMESSAGE | DOSCALLS.#383 |
| 2 | DOSTRUEGETMESSAGE | DOSCALLS.#384 |
| 3 | DOSINSMESSAGE | DOSCALLS.#385 |
| 4 | *(unnamed)* | DOSCALLS.#386 |
| 5 | *(unnamed)* | DOSCALLS.#387 |
| 6 | *(unnamed)* | DOSCALLS.#388 |
| 7 | DOSIQUERYMESSAGECP | DOSCALLS.#389 |
| 8 | *(unnamed)* | DOSCALLS.#390 |
| 9 | DOSCLOSEMESSAGEFILE | DOSCALLS.#649 |

### NAMPIPES.DLL  (14 forwarder entries)
md5 `3465d1cfd955c62faaf20fecb92257a8`, imports `DOSCALLS`

| ord | name in this DLL | forwards to |
|---|---|---|
| 1 | DOSMAKENMPIPE | DOSCALLS.#399 |
| 2 | DOSQNMPIPEINFO | DOSCALLS.#400 |
| 3 | DOSCONNECTNMPIPE | DOSCALLS.#401 |
| 4 | DOSDISCONNECTNMPIPE | DOSCALLS.#402 |
| 5 | DOSQNMPHANDSTATE | DOSCALLS.#403 |
| 6 | DOSSETNMPHANDSTATE | DOSCALLS.#404 |
| 7 | DOSPEEKNMPIPE | DOSCALLS.#405 |
| 8 | DOSWAITNMPIPE | DOSCALLS.#406 |
| 9 | DOSTRANSACTNMPIPE | DOSCALLS.#407 |
| 10 | DOSCALLNMPIPE | DOSCALLS.#408 |
| 11 | DOSRAWREADNMPIPE | DOSCALLS.#409 |
| 12 | DOSRAWWRITENMPIPE | DOSCALLS.#410 |
| 13 | DOSSETNMPIPESEM | DOSCALLS.#411 |
| 14 | DOSQNMPIPESEMSTATE | DOSCALLS.#412 |

### NLS.DLL  (8 forwarder entries)
md5 `e9365d14d36dd27aee61660db4825fa6`, imports `DOSCALLS`

| ord | name in this DLL | forwards to |
|---|---|---|
| 1 | DOSCASEMAP | DOSCALLS.#391 |
| 2 | DOSGETCOLLATE | DOSCALLS.#392 |
| 3 | DOSGETCTRYINFO | DOSCALLS.#393 |
| 4 | DOSGETDBCSEV | DOSCALLS.#394 |
| 5 | *(unnamed)* | DOSCALLS.#395 |
| 6 | *(unnamed)* | DOSCALLS.#396 |
| 7 | *(unnamed)* | DOSCALLS.#397 |
| 8 | *(unnamed)* | DOSCALLS.#398 |

### OS2CHAR.DLL  (13 forwarder entries)
md5 `adb56f17db46e70e1bd493c3caeb2d31`, imports `DOSCALLS`

| ord | name in this DLL | forwards to |
|---|---|---|
| 1 | *(unnamed)* | DOSCALLS.#682 |
| 2 | *(unnamed)* | DOSCALLS.#683 |
| 3 | *(unnamed)* | DOSCALLS.#684 |
| 4 | *(unnamed)* | DOSCALLS.#685 |
| 5 | *(unnamed)* | DOSCALLS.#858 |
| 6 | *(unnamed)* | DOSCALLS.#859 |
| 7 | *(unnamed)* | DOSCALLS.#860 |
| 8 | *(unnamed)* | DOSCALLS.#862 |
| 9 | *(unnamed)* | DOSCALLS.#864 |
| 99 | *(unnamed)* | DOSCALLS.#861 |
| 148 | *(unnamed)* | DOSCALLS.#865 |
| 149 | *(unnamed)* | DOSCALLS.#863 |
| 152 | *(unnamed)* | DOSCALLS.#718 |

### QUECALLS.DLL  (16 forwarder entries)
md5 `7a87f748dcdbb4d7a840e311b8c16d6e`, imports `DOSCALLS`

| ord | name in this DLL | forwards to |
|---|---|---|
| 1 | DOSREADQUEUE | DOSCALLS.#674 |
| 2 | DOSPURGEQUEUE | DOSCALLS.#675 |
| 3 | DOSCLOSEQUEUE | DOSCALLS.#676 |
| 4 | DOSQUERYQUEUE | DOSCALLS.#677 |
| 5 | DOSPEEKQUEUE | DOSCALLS.#678 |
| 6 | DOSWRITEQUEUE | DOSCALLS.#679 |
| 7 | DOSOPENQUEUE | DOSCALLS.#680 |
| 8 | DOSCREATEQUEUE | DOSCALLS.#681 |
| 9 | *(unnamed)* | DOSCALLS.#661 |
| 10 | *(unnamed)* | DOSCALLS.#662 |
| 11 | *(unnamed)* | DOSCALLS.#663 |
| 12 | *(unnamed)* | DOSCALLS.#664 |
| 13 | *(unnamed)* | DOSCALLS.#665 |
| 14 | *(unnamed)* | DOSCALLS.#666 |
| 15 | *(unnamed)* | DOSCALLS.#667 |
| 16 | *(unnamed)* | DOSCALLS.#668 |

### SESMGR.DLL  (40 forwarder entries)
md5 `7e9d0be080fdcac819de5b03f018a6a8`, imports `DOSCALLS`

| ord | name in this DLL | forwards to |
|---|---|---|
| 1 | DOSSMSGDOPOPUP | DOSCALLS.#686 |
| 2 | DOSSMSWITCH | DOSCALLS.#687 |
| 3 | DOSSMSERVEAPPREQ | DOSCALLS.#688 |
| 4 | DOSGETTIMES | DOSCALLS.#689 |
| 5 | DOSSMSETTITLE | DOSCALLS.#690 |
| 6 | DOSSCRUNLOCK | DOSCALLS.#691 |
| 7 | DOSSMDOAPPREQ | DOSCALLS.#692 |
| 8 | DOSSTOPSESSION | DOSCALLS.#693 |
| 9 | DOSSELECTSESSION | DOSCALLS.#694 |
| 10 | DOSSCRLOCK | DOSCALLS.#695 |
| 11 | DOSSAVREDRAWWAIT | DOSCALLS.#696 |
| 12 | DOSSAVREDRAWUNDO | DOSCALLS.#697 |
| 13 | DOSSMSGENDPOPUP | DOSCALLS.#698 |
| 14 | DOSSETSESSION | DOSCALLS.#699 |
| 15 | DOSSETMNLOCKTIME | DOSCALLS.#700 |
| 16 | DOSMODEUNDO | DOSCALLS.#701 |
| 17 | DOSSTARTSESSION | DOSCALLS.#702 |
| 18 | DOSSMGETSTATUS | DOSCALLS.#703 |
| 19 | DOSMODEWAIT | DOSCALLS.#704 |
| 20 | DOSSMTERMINATE | DOSCALLS.#705 |
| 21 | DOSSMGETAPPREQ | DOSCALLS.#706 |
| 23 | DOSSMINITIALIZE | DOSCALLS.#707 |
| 24 | DOSSMSTART | DOSCALLS.#708 |
| 25 | DOSSMPARENTSWITCH | DOSCALLS.#709 |
| 26 | DOSSMPAUSE | DOSCALLS.#710 |
| 27 | DOSSMHDEINIT | DOSCALLS.#711 |
| 28 | DOSSMPMPRESENT | DOSCALLS.#712 |
| 29 | DOSSMREGISTERDD | DOSCALLS.#713 |
| 30 | DOSSMSYSINIT | DOSCALLS.#855 |
| 31 | DOSSMNOTIFYDD | DOSCALLS.#714 |
| 32 | DOSSMNOTIFYDD2 | DOSCALLS.#715 |
| 33 | DOSSMOPENDD | DOSCALLS.#716 |
| 34 | QHKEYBDHANDLE | DOSCALLS.#856 |
| 35 | QHMOUSEHANDLE | DOSCALLS.#857 |
| 36 | *(unnamed)* | DOSCALLS.#717 |
| 37 | *(unnamed)* | DOSCALLS.#669 |
| 38 | *(unnamed)* | DOSCALLS.#670 |
| 39 | *(unnamed)* | DOSCALLS.#671 |
| 40 | *(unnamed)* | DOSCALLS.#672 |
| 41 | DOSREGISTERNOTIFICATION | DOSCALLS.#673 |

### VIOCALLS.DLL  (75 forwarder entries)
md5 `0a227adfb4d70da6e089f614c4f4c3d3`, imports `DOSCALLS`

| ord | name in this DLL | forwards to |
|---|---|---|
| 1 | VIOENDPOPUP | DOSCALLS.#770 |
| 2 | VIOGETPHYSBUF | DOSCALLS.#771 |
| 3 | VIOGETANSI | DOSCALLS.#772 |
| 4 | *(unnamed)* | DOSCALLS.#773 |
| 5 | VIOSETANSI | DOSCALLS.#774 |
| 6 | VIODEREGISTER | DOSCALLS.#775 |
| 7 | VIOSCROLLUP | DOSCALLS.#776 |
| 8 | VIOPRTSC | DOSCALLS.#777 |
| 9 | VIOGETCURPOS | DOSCALLS.#778 |
| 10 | VIOWRTCELLSTR | DOSCALLS.#779 |
| 11 | VIOPOPUP | DOSCALLS.#780 |
| 12 | VIOSCROLLRT | DOSCALLS.#781 |
| 13 | VIOWRTCHARSTR | DOSCALLS.#782 |
| 14 | *(unnamed)* | DOSCALLS.#783 |
| 15 | VIOSETCURPOS | DOSCALLS.#784 |
| 16 | *(unnamed)* | DOSCALLS.#785 |
| 17 | *(unnamed)* | DOSCALLS.#786 |
| 18 | VIOSCRUNLOCK | DOSCALLS.#787 |
| 19 | VIOWRTTTY | DOSCALLS.#788 |
| 20 | *(unnamed)* | DOSCALLS.#789 |
| 21 | VIOGETMODE | DOSCALLS.#790 |
| 22 | VIOSETMODE | DOSCALLS.#791 |
| 23 | VIOSCRLOCK | DOSCALLS.#792 |
| 24 | VIOREADCELLSTR | DOSCALLS.#793 |
| 25 | VIOSAVREDRAWWAIT | DOSCALLS.#794 |
| 26 | VIOWRTNATTR | DOSCALLS.#795 |
| 27 | VIOGETCURTYPE | DOSCALLS.#796 |
| 28 | VIOSAVREDRAWUNDO | DOSCALLS.#797 |
| 29 | VIOGETFONT | DOSCALLS.#798 |
| 30 | VIOREADCHARSTR | DOSCALLS.#799 |
| 31 | VIOGETBUF | DOSCALLS.#800 |
| 32 | VIOSETCURTYPE | DOSCALLS.#801 |
| 33 | VIOSETFONT | DOSCALLS.#802 |
| 34 | *(unnamed)* | DOSCALLS.#803 |
| 35 | VIOMODEUNDO | DOSCALLS.#804 |
| 36 | *(unnamed)* | DOSCALLS.#805 |
| 37 | VIOMODEWAIT | DOSCALLS.#806 |
| 38 | *(unnamed)* | DOSCALLS.#807 |
| 40 | VIOGETCP | DOSCALLS.#808 |
| 41 | *(unnamed)* | DOSCALLS.#809 |
| 42 | VIOSETCP | DOSCALLS.#810 |
| 43 | VIOSHOWBUF | DOSCALLS.#811 |
| 44 | VIOSCROLLLF | DOSCALLS.#812 |
| 45 | VIOREGISTER | DOSCALLS.#813 |
| 46 | VIOGETCONFIG | DOSCALLS.#814 |
| 47 | VIOSCROLLDN | DOSCALLS.#815 |
| 48 | VIOWRTCHARSTRATT | DOSCALLS.#816 |
| 49 | VIOGETSTATE | DOSCALLS.#817 |
| 50 | VIOPRTSCTOGGLE | DOSCALLS.#818 |
| 51 | VIOSETSTATE | DOSCALLS.#819 |
| 52 | VIOWRTNCELL | DOSCALLS.#820 |
| 53 | VIOWRTNCHAR | DOSCALLS.#821 |
| 54 | *(unnamed)* | DOSCALLS.#822 |
| 55 | VIOASSOCIATE | DOSCALLS.#823 |
| 56 | VIOCREATEPS | DOSCALLS.#824 |
| 57 | VIODELETESETID | DOSCALLS.#825 |
| 58 | VIOGETDEVICECELLSIZE | DOSCALLS.#826 |
| 59 | VIOGETORG | DOSCALLS.#827 |
| 60 | VIOCREATELOGFONT | DOSCALLS.#828 |
| 61 | VIODESTROYPS | DOSCALLS.#829 |
| 62 | VIOQUERYSETIDS | DOSCALLS.#830 |
| 63 | VIOSETORG | DOSCALLS.#831 |
| 64 | VIOQUERYFONTS | DOSCALLS.#832 |
| 65 | VIOSETDEVICECELLSIZE | DOSCALLS.#833 |
| 66 | VIOSHOWPS | DOSCALLS.#834 |
| 67 | VIOGETPSADDRESS | DOSCALLS.#835 |
| 68 | *(unnamed)* | DOSCALLS.#836 |
| 69 | *(unnamed)* | DOSCALLS.#837 |
| 70 | VIOGLOBALREG | DOSCALLS.#838 |
| 71 | XVIOSETCASTATE | DOSCALLS.#839 |
| 72 | XVIOCHECKCHARTYPE | DOSCALLS.#840 |
| 73 | XVIODESTROYCA | DOSCALLS.#841 |
| 74 | XVIOCREATECA | DOSCALLS.#842 |
| 75 | VIOCHECKCHARTYPE | DOSCALLS.#843 |
| 76 | XVIOGETCASTATE | DOSCALLS.#844 |

<!-- total forwarder entries: 241 -->
