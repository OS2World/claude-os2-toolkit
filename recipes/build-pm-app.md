# Building an OS/2 app (both toolchains)

The shape of a build for a PM or console app, for each toolchain. Exact flags vary by version -
**verify against your toolchain's docs** (same discipline as the API work). Pick a toolchain with
`choosing-a-toolchain.md`.

An OS/2 app is: your `.c`/`.cpp` sources, an optional `.rc` resource script (menus, dialogs,
strings, icons - see `../os2ref/resources-and-dialogs.md`), and a `.def` module-definition file that
sets the **application type** (see `../os2ref/calling-convention.md`, `../os2ref/module-dll.md`).

**Start from a scaffold** rather than an empty file - each builds as it stands and checks every
return value: `../scaffolds/hello-console/` (a VIO console app), `../scaffolds/hello-pm/` (a minimal
PM window) and `../scaffolds/hello-pm-menu/` (a PM app with a menu, a modal dialog, an accelerator
table and a `.RC`). Each has a `BUILD.md`.

`.def` application type - this decides how OS/2 runs the process:
```
NAME hello WINDOWAPI      ; a Presentation Manager (GUI) app
NAME hello WINDOWCOMPAT   ; a VIO-windowable console app (runs in a PM window)
NAME hello NOTWINDOWCOMPAT ; a full-screen text app
```

> **Omitting the `.def` does not reliably fail - it fails *situationally*, which is worse.** An
> executable with no application type is not marked as PM, and whether it works then depends on the
> session it is launched from. A PM program built without one may run perfectly when started one way
> and **exit instantly and silently** when started another - typically working over SSH or from a
> detached context while dying from a `CMD.EXE` prompt, or the reverse. There is no error message:
> `WinCreateStdWindow` simply returns `NULLHANDLE`, and a `main` that checks it and returns exits so
> fast the window never appears.
>
> The tell is exactly that asymmetry - *"it works when I launch it from X but not from Y"* - and it
> is worth checking before suspecting anything in your own code. Pass the `.def` on the `gcc`/`g++`
> command line (or use `-l=os2v2_pm` with `wcl386`) and confirm the app starts from a plain command
> prompt, not just from whatever your build script uses. [OBS-RE - a Notepad2 port ran correctly over
> SSH for an entire session with no `.def` at all, and exited without a word from `CMD.EXE`.]

## OpenWatcom (local on Linux, cross-compiling) - verified with 1.9

```sh
# environment (from install-openwatcom.md): WATCOM, PATH set; and:
export INCLUDE="$WATCOM/h;$WATCOM/h/os2"   # both dirs, ';'-separated - os2.h is in h/os2/
wrc -r hello.rc                        # compile resources .rc -> .res   (if you have resources)
# compile + link in one step:
wcl386 -bt=os2 -l=os2v2_pm hello.c -fe=hello.exe    # PM app
#   -bt=os2      target OS/2
#   -l=os2v2_pm  32-bit OS/2 Presentation Manager link spec (sets PM format + libs)
wrc hello.res hello.exe                # bind the resources into the .exe
```
The bind step **fails if the program is still running** - OS/2 holds a running `.EXE` open, and
`wrc` reports `E007: Error renaming temporary file ... Permission denied`. In an edit-build-test
loop this is the one failure that leaves you testing the *previous* binary while everything appears
to succeed, so kill the running copy first and confirm the `.exe` timestamp moved
(`recipes/setup-test-vm.md`).

For a **console** app use `-l=os2v2` instead. **Do not use `-bg`** for an OS/2 PM app - the
`os2v2_pm` system already makes it a PM app; adding `-bg` links the default-windowing startup and the
entry point is lost (`W1023: no starting address`, a tiny broken .exe). To honor a hand-written
`.def`, note that `wlink`'s `@file` reads *wlink directive* syntax, not module-definition
syntax - so `@hello.def` does **not** work. Either let the compiler flags set the
module type (as above), or translate the `.def` into wlink directives (`NAME`, `OPTION DESCRIPTION`,
`EXPORT`) in a separate directive file. Multi-file builds: compile each with `wcc386 -bt=os2`, then
`wlink`.

## GCC + kLIBC (on the OS/2 VM, over SSH)

```sh
# on the VM (ssh in - see setup-test-vm.md). kLIBC + GCC installed via RPM.

# -Zomf links through emxomfld, which defaults to IBM's ilink.exe. If you installed the
# toolchain from the netlabs/Arca RPMs you have Watcom's linker as `wl.exe` and NO ilink,
# so emxomfld fails with "ilink.exe: No such file or directory". Point it at wlink:
export EMXOMFLD_TYPE=wlink
export EMXOMFLD_LINKER=wl.exe

# wrc does NOT inherit the compiler's include path. A .RC with `#include <os2.h>`
# fails with "E062: Unable to open 'os2.h'" unless you point it at the headers:
wrc -r -i=C:/usr/include hello.rc       # compile .rc -> .res  (-i= is required)
gcc -Zomf -Zargs-wild -O2 hello.c hello.def -o hello.exe
#   -Zomf     emit OMF objects + link via emxomfld (produces an LX .exe)
#   hello.def a .def on the gcc command line sets the app type / exports
wrc hello.res hello.exe                 # bind resources

# C++ builds the same way with g++ (gcc-c++ RPM). GCC 9.2 handles C++11/14/17 fine.
```

### `-std=c++11` hides every kLIBC extension

`-std=c++NN` and `-std=cNN` (as opposed to `-std=gnu++NN`) define `__STRICT_ANSI__`, and kLIBC's
headers gate their non-standard functions on it:

```c
/* /usr/include/stdlib.h */
#if (!defined (__STRICT_ANSI__) && !defined (_POSIX_SOURCE)) || defined (_WITH_UNDERSCORE) \
    || defined(__USE_EMX)
...
int _execname (char *, size_t);
```

So `_execname`, `_abspath`, `_fnexplode`, `_chdir2`, `_filesys` and the rest are **visibly present in
the header you are reading and still not in scope**, and the compiler says
`'_execname' was not declared in this scope` - which reads as "kLIBC does not have it". It does.
Either build with `-std=gnu++11`, or `#define __USE_EMX` before the include (the header's own opt-in,
and the narrower change if the rest of the project wants strict ISO). [OBS-RE]

> **Check what you have with `rpm -qa`, not `command -v`.** The RPM package names are
> `gcc`, `gcc-c++`, `gcc-wlink`, `gcc-wrc`, `libstdc++`, `libstdc++-devel`. `command -v g++`
> can report nothing even when `/usr/bin/g++.exe` exists (the shell mishandles the `+`
> characters), and `yum` needs working repo metadata while `rpm -qa` does not.
kLIBC gives POSIX (`fork`/`pipe`/`openpty`/sockets-as-fds) and `/@unixroot` paths. Build **and run**
happen on the VM. Watch `BEGINLIBPATH`/`LIBPATH` so your app finds its DLLs at run time (a common
`SYS2070`/`SYS1804` cause - see `../os2-app-dev-guide.md` "When something fails").

## After building - verify before you run
If the app has a `.RC`, check it - the compiler, `wrc` and the linker all accept both of these
defects silently:
```sh
check-rc-ids.py app.h app.rc *.c   # a dialog the code loads but the .RC lacks; colliding ids
check-mnemonics.py app.rc          # two menu items claiming the same ~ mnemonic
```
Both exit non-zero on a finding, so they can gate the build; run them after **every** `.RC` edit. A
missing `DLGTEMPLATE` shows up only at run time, as `WinLoadDlg` returning `NULLHANDLE` with
`PMERR_RESOURCE_NOT_FOUND` (`0x8100A`) - and a whole-file rewrite of a `.RC` is exactly how a
template goes missing (`../tools/rc-ids/README.md`).

Inspect the module actually exports/imports what you intended (`inspect-a-binary.md`):
```sh
lx_export.py hello.exe      # exports/imports of the LX binary
lx_disasm.py hello.exe ...  # disassemble an object:offset
```
Then run it on the target (`setup-test-vm.md`); on a crash, read `C:\POPUPLOG.OS2`.
