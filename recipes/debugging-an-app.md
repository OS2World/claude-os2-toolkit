# Debugging an OS/2 app you built

The app-level debug loop. (Kernel/driver work -> `kdb-reference.md`.)

## A crash -> find the instruction
OS/2 writes every unhandled exception to **`C:\POPUPLOG.OS2`** (the kernel appends on each fault).
Read it after a crash:
```sh
ssh os2@<vm> 'cat C:/POPUPLOG.OS2' | tail -40
```
An entry gives the **process**, the **fault type** (`SYS3175` access violation, `SYS2070`
demand-load/bad-ordinal), the register dump, and a `MODULE object:offset`. Map that back:
```sh
lx_disasm.py your.exe <object>:<offset>  # the faulting instruction
```
Copy `object:offset` straight from the log - the object number is decimal, the offset is hex
(`1:0001a2b4`), which is how `lx_disasm.py` reads it. No `.SYM` file is needed; pass `--sym your.sym`
as well if you have one and want symbol labels rather than bare addresses.

This turns "it crashed" into "it crashed executing *this* instruction," which is usually enough.

## Why did a call fail? - ask the API, not the return value
OS/2 reports *why* through an error code, not the boolean/handle it returns:
- **PM (`Win*`/`Gpi*`) returned `FALSE`/`NULLHANDLE`:** call `WinGetLastError(hab)` and look the
  `PMERR_*` up in `../os2ref/` (the doc for that subsystem lists error semantics).
- **Control Program (`Dos*`) returned non-zero:** that's an `ERROR_*` - meaning is in
  `../os2ref/error-codes.md` and the per-call doc.

## Load failures (`SYS2070` / `SYS1804`) are linkage, not logic
The module loaded but an import didn't resolve (`SYS2070` bad ordinal), or a module/DLL wasn't found
(`SYS1804`). Almost always a `.def`, import-name/ordinal, or `LIBPATH` problem - not your code:
```sh
lx_export.py your.exe  # what it imports (DLL + ordinal/name) and exports
```
Confirm the imported DLL exports that ordinal/name, and that dependent DLLs are on
`LIBPATH`/`BEGINLIBPATH` (`export BEGINLIBPATH=/path/to/dlls` before running). See
`../os2ref/module-dll.md`, `../os2ref/calling-convention.md`.

**kLIBC gotcha - a versioned-runtime mismatch reads as a bad ordinal.** kLIBC's C runtime DLL is
**versioned**: `libcnN.dll`, where `N` is the build "version high" (VH). An app is bound to one
version at link time. If you rebuild kLIBC as a different version (e.g. `libcn9.dll`) but the app
still imports `LIBCN0`, or the installed `libcn0.dll` predates a symbol you added, you get
`SYS2070  <APP>->LIBCN<x>.<ordinal>` - the DLL loaded, but that ordinal isn't in *this* version.
Diagnose: the ordinal maps to a symbol in the libc `.def` (`grep <ordinal> libc.def` - typically a
symbol newer than the installed runtime, e.g. `openpty`); check which `libcnN.dll` actually exports
it (`strings libcnN.dll | grep
<symbol>`); then make the app and the on-`LIBPATH` DLL the *same* version - either relink the app
against the version that has the symbol, or install that `libcnN.dll` where the loader finds it.

## Getting debug output out of your app
Pick the channel by **context** - the wrong one is silent or crashes:
- **Normal code:** ordinary logging / `printf` to a file. Over a no-PTY SSH session a console app's
  stdout may not come back - **redirect to a file and read it back**
  (`ssh os2@vm 'app.exe >out.txt 2>&1'; ssh os2@vm 'cat out.txt'`), as in `setup-test-vm.md`.
- **Inside an exception handler / signal-unsafe context:** do the minimum, async-signal-safely - no
  heavy `printf`/allocation; write a preformatted line to an already-open fd. (This channel-choice
  discipline is expanded in `../c-guide.md` section 8.)

## Interactive debugging
- **`gdb`** - the kLIBC toolchain ships a `gdb` (install via RPM on the VM); debug a kLIBC-built app
  the familiar way over SSH. OpenWatcom has its own debugger (`wd`/`wdw`).
- **Kernel debugger (KDB)** - escalate here only for driver/IFS/kernel-level faults; see
  `kdb-reference.md`.

## The discipline
Fail honestly: when you don't understand a failure, stop at the cause and report it - never fake a
success or route around a guard to "make it run." In OS/2 a dishonest success (a wrong window style,
an unhandled message, a bad `.DEF`) resurfaces as a crash far from the cause. (`../os2-app-dev-guide.md`,
`../c-guide.md`.)
