# Rebuilding an installed OS/2 package from source

*"Fix the bug where it lives"* is a discipline, not a preference - see `../START-HERE.md` section 3 and
`../os2-app-dev-guide.md` section 8 for why the workaround is the expensive branch. **This recipe is the
mechanics**: the path from "installed RPM" to "patched DLL loaded by one process", without touching
the system copy. It is written from a real case (patching `readline`), and every step below is a
failure that actually happened, in the order it happened.

**Which machine each step runs on.** This is written for a **cross setup**: a Linux (or other Unix)
host for fetching and `autoreconf`, an OS/2 box for the actual build. Every section below is tagged
*(host)* or *(OS/2)*. Nothing here requires the host - you can do the lot on OS/2 if you install
autoconf/automake/libtool there - but the failures in section 3 are OS/2's regardless of where the tarball
was unpacked, and section 2 is the one step that is genuinely easier off-box.

## 1. Get the source *(OS/2 to fetch, host to unpack)*

`yumdownloader` fetches the SRPM, but it is a **python2** script while the default `python` is 3 -
running it directly dies with a `SyntaxError` on `except ... , e:`. (Observed on WSEB 4.50 with the
netlabs RPM userland: the shebang is `#!/usr/bin/python`, `python --version` reports 3.9, and
`python2.7.exe` is present alongside. Check your own box rather than assuming the versions.) Invoke
it explicitly:

```sh
python2.7 /@unixroot/usr/bin/yumdownloader --source readline --destdir=N:/somewhere
```

Unpack on the **Linux** side (faster, and the tools are there). `rpm2cpio` comes with the `rpm`
package; `bsdtar` also reads an SRPM if you'd rather not install it:

```sh
rpm2cpio readline-8.0-3.oc00.src.rpm | cpio -idm      # -> a .zip/.tar + the .spec
unzip readline-github-8.0-os2-3.zip
```

**Read the `.spec` before building** - it carries the port's real build flags (e.g.
`LDFLAGS="-Zhigh-mem -Zomf -Zargs-wild -Zargs-resp -lcx"`), the `%configure` options, and often a
comment explaining a workaround you are about to rediscover.

## 2. Generate `configure` on the host, not on OS/2 *(host)*

bitwiseworks' GitHub source zips ship **no generated `configure`** (the spec runs `autoreconf -fvi`
in `%prep`), and the OS/2 box typically has no autoconf/automake/libtool. Don't install them there -
autoconf output is portable shell, so generate it on the host:

```sh
cd readline-os2-8.0-os2-3 && autoreconf -fvi
```

`autoheader` may fail on a package that ships its own `config.h.in` (readline does). That is fine as
long as `configure` was produced - check for the file rather than trusting the exit status.

## 3. The four OS/2 configure failures, in the order you will hit them *(OS/2)*

> **Everything measured in this section was measured on one machine:** OS/2 Warp Server for
> e-business 4.50, Convenience Pack 2 (`SYSLEVEL.OS2` reports `XR04503`), with the netlabs/RPM
> userland, GCC 9.2.0 (kLIBC) and autoconf 2.71-generated `configure` scripts.
>
> **ArcaOS may not match, and none of this was tested there.** A distribution that preconfigures its
> own userland can differ in exactly the three facts this section leans on. Check your own box before
> assuming - each is one line:
>
> ```sh
> ls -d /bin && /bin/sh -c 'echo yes'      # a: is /bin/sh already there?  (absent here)
> ls -l /@unixroot/usr/bin/gcc             # b: extensionless, or only gcc.exe?  (only .exe here)
> rpm --eval '%{_prefix}'                  # config.site path  (/@unixroot/usr here)
> ```
>
> If `/bin/sh` already runs on your box, **a** is already solved for you and autoconf's separator
> probe in **b** will work by itself - leaving `ac_executable_extensions` as the only thing to set.
> The mechanisms below hold regardless; which remedies you need does not. `[unverified]` on ArcaOS.

**a. There is no `/bin/sh`.** Configure dies running `support/config.sub`:

```
configure: error: cannot run /bin/sh ././support/config.sub
```

On the box above there is no `/bin` **directory** at all, and kLIBC does not alias it to `/usr/bin`:
`test -d /bin` false, `ls -d /bin` "No such file", `/bin/sh -c ...` "not found", and no `/bin`
special-casing in kLIBC's path resolution. **Check yours first** - a distribution that ships `/bin`
has already fixed this, and the rest of **a** does not apply. Two ways out. Per build:

```sh
SH=/@unixroot/usr/bin/sh.exe
export CONFIG_SHELL=$SH SHELL=$SH
$SH ./configure ...            # and pass SHELL=$SH to make as well
```

**Or give the machine the `/bin/sh` everything expects**, which is the better trade if you build
often - symlink it, so it does not go stale when the `ash`/`sh` package is updated:

```sh
mkdir -p /@unixroot/bin && ln -s /@unixroot/usr/bin/sh.exe /@unixroot/bin/sh.exe
```

The link is named `sh.exe`, not `sh` - `/bin/sh` then resolves because kLIBC appends `.exe` when
*executing*, even though it does not when calling `stat()` (see **b**.2). Tested: that makes explicit
`/bin/sh ...` invocations work, makes `#!/bin/sh` shebang scripts run, and - see **b** - makes
autoconf's `PATH_SEPARATOR` detection start working, since `/bin/sh` is exactly what it probes for.

**b. Configure finds no tools at all** - first `no acceptable C compiler`, then `no acceptable grep`.

**Two** independent things are broken, and **both** must be fixed; neither alone gets you past the
compiler check (measured, table below).

1. **`PATH` is `;`-separated with drive letters.** Autoconf does try to detect this. It sets `:`, then
   runs two probes - it switches to `;` only if `(PATH='/bin;/bin'; FPATH=$PATH; sh -c :)` **succeeds**
   *and* `(PATH='/bin:/bin'; FPATH=$PATH; sh -c :)` **fails**. With no `/bin` (see **a**) the first
   probe fails, so the fallback `:` stands. Splitting `C:/usr/bin;C:/usr/local/bin;...` on `:` then
   yields elements like `C` and `/usr/bin;C`, none of which hold the compiler.
   `[SRC]` autoconf `lib/m4sugar/m4sh.m4`, `_AS_PATH_SEPARATOR_PREPARE`.
   Fix it **either** by presetting the variable - it is honoured when set, the branch is commented
   "The user is always right" - **or** by creating `/bin/sh` per **a**, which makes the probe answer
   `;` by itself. Both tested; either is sufficient.
2. **The tools are `.exe` and kLIBC's `stat()` does not pretend otherwise.** `test -f
   /@unixroot/usr/bin/gcc` is **false**; `gcc.exe` is true. Autoconf's program search only tries
   `$ac_word` followed by each entry of `$ac_executable_extensions` - a variable autoconf **never
   assigns anywhere**, so it is yours to set and an exported value survives into configure's shell.
   `[SRC]` autoconf `lib/autoconf/programs.m4:52,132,427,557,670` - the five `for ac_exec_ext in ''
   $ac_executable_extensions` loops, and the only occurrences in the tree. (It does not govern
   *every* search: `_AS_DETECT_BETTER_SHELL` in `lib/m4sugar/m4sh.m4` hardcodes its own `.exe` test
   when hunting for a shell.)

```sh
export PATH_SEPARATOR=';' ac_executable_extensions='.exe'
```

Better for repeated builds, put them in a **`config.site`** instead of the environment:

```sh
cat > /@unixroot/usr/share/config.site <<'EOF'
PATH_SEPARATOR=';'
ac_executable_extensions='.exe'
EOF
```

**Mind how configure picks that file, because the automatic path is conditional.** `CONFIG_SITE` is
checked *first and unconditionally*; only if it is unset does configure fall back to
`$prefix/share/config.site` - **and `$prefix` is `NONE` unless `--prefix` was passed**, in which case
it uses `$ac_default_prefix` instead (usually `/usr/local`, or whatever the package's
`AC_PREFIX_DEFAULT` says). So:

- Building **under `rpmbuild`/`%configure`**: the file above is found automatically. Verified with
  `rpm --eval '%configure'` on the netlabs stack - it passes `--prefix=/@unixroot/usr`, and
  `rpm --eval '%{_prefix}'` is `/@unixroot/usr`, not `/usr`.
- Running **`./configure` by hand** as in **a** above, with no `--prefix`: the file is **not read**,
  silently - no "loading site script" line, and you are back to `no acceptable C compiler` with no
  hint why. Point `CONFIG_SITE` at it instead, which always works:

```sh
export CONFIG_SITE=/@unixroot/usr/share/config.site
```

Measured on the box named at the top of this section, running a generated `configure` containing only
`AC_PROG_CC`, `AC_PROG_GREP`, `AC_PROG_SED`, `AC_PROG_AWK`:

| `PATH_SEPARATOR=';'` | `ac_executable_extensions='.exe'` | `/bin/sh` exists | result |
|---|---|---|---|
| - | - | no | `no acceptable C compiler found in $PATH` |
| yes | - | no | `no acceptable C compiler found in $PATH` |
| - | yes | no | `no acceptable C compiler found in $PATH` |
| - | - | **yes** | `no acceptable C compiler found in $PATH` |
| **yes** | **yes** | no | exit 0 - `gcc`, `C:/usr/bin/grep.exe`, `C:/usr/bin/sed` |
| - | **yes** | **yes** | exit 0 |

(Paths in the last two rows are as configure printed them; `C:` is this box's `%UNIXROOT%`.)

The last two rows are the two supported combinations: fix the separator with the variable, or fix it
by giving autoconf the `/bin/sh` its probe wants. `ac_executable_extensions` is required either way.
Both settings also work from a site file, with one catch worth its own paragraph.

**The `config.site` route still needs `CONFIG_SHELL`, and omitting it fails at the very last step.**
`configure` sets `SHELL=${CONFIG_SHELL-/bin/sh}` (an inherited `SHELL` is ignored) and runs
`config.status` through it. A site file is read far too late to matter, and `config.status` does not
read one at all. Measured, with a `configure` that actually generates a `Makefile`:

| route | result |
|---|---|
| `CONFIG_SITE` only, no `/bin/sh`, no `CONFIG_SHELL` | every check passes, then `./configure: /bin/sh: not found` - **exit 1, no Makefile** |
| `CONFIG_SITE` + `CONFIG_SHELL` | exit 0, `Makefile` created |
| **`/bin/sh` symlink + `ac_executable_extensions`, nothing else** | exit 0, `Makefile` created |

That failure is the nastiest one in this recipe: `checking for gcc... gcc` and every other probe
succeeds, `creating config.status` prints, and *then* it dies - so the instinct is to go hunting in
the compiler checks. **The `/bin/sh` symlink from a is the one fix that covers all of it**: it
satisfies the separator probe, `config.status`, and any `#!/bin/sh` sub-script, leaving
`ac_executable_extensions` as the only thing you must still set.

Note this was measured with **autoconf 2.71**. `ac_executable_extensions` is not a knob ancient
configure scripts know about `[unverified]` - netlabs packages ship a range of vintages, so if a
package's `configure` ignores it, fall back to naming the tools absolutely.

Naming every tool absolutely (`CC=/@unixroot/usr/bin/gcc.exe`, `GREP=...`, `SED=...`, and so on) also
works and is what you will see in older notes, but it is an ever-growing list, and it does nothing
for the `AC_PATH_PROG` searches inside macros you do not control. Prefer the two variables.

**A third variable pair from older EMX-era notes, `ac_exeext`/`ac_cv_exeext`, is not needed on the
autoconf this section targets** - measured against a minimal `AC_PROG_CC; AC_EXEEXT` `configure`
(autoconf 2.71): with `ac_executable_extensions` already set, adding
`export ac_exeext=.exe ac_cv_exeext=.exe` produced a byte-identical configure log
(`checking for suffix of executables... .exe` either way) - a no-op. Exporting *only*
`ac_exeext`/`ac_cv_exeext`, without `ac_executable_extensions`, still fails at
`checking for gcc... no` - they answer the later "what suffix do compiled binaries get" question, not
"where is the compiler", so they cannot substitute for the fix above.

**Tested against real autoconf 2.13 too** (`autoconf213`, `netlabs-rel`) - and it changes the picture.
2.13's own `AC_EXEEXT` (`acspecific.m4:2679`) carries **built-in EMX/OS2 detection**:

```
checking for path separator... ;
checking for EMX/OS2 environment... yes
checking for executable suffix... .exe
```

That appears with *only* the `/bin/sh` per-build fix (`CONFIG_SHELL`/`SHELL`) in the environment - no
`PATH_SEPARATOR`, no `ac_executable_extensions` needed at all. Autoconf dropped that native EMX/OS2
branch somewhere between 2.13 and 2.71, which is *why* section **b** above has to reconstruct the
equivalent by hand for modern autoconf. So a package still built with `autoconf213` (a Mozilla-style
holdout, per the `autoconf213`-vs-`autoconf` split netlabs itself ships) needs none of section **b**'s
fixes - check `AC_PREREQ`/the `.spec`'s autoconf invocation before applying them blind.

Dave Yeo's vars *do* measurably do something on 2.13, just not what's needed for `configure` to
succeed: `AC_EXEEXT` wraps its probe in `AC_CACHE_VAL(ac_cv_exeext, ...)`, so presetting
`ac_cv_exeext` skips the probe outright - `checking for executable suffix... (cached) .exe` instead of
running it fresh (diffed, that cache line is the *only* difference). Harmless here since the fresh
probe already works, but it would matter as a workaround if that specific probe were ever unreliable on
a given box. Quoting them (`export ac_exeext=.exe` vs `export ac_exeext=".exe"`) made no difference
either way - plain assignment, no embedded whitespace to protect.

(Why `sed` resolves without the suffix in that table while `gcc` does not: `/usr/bin/sed` happens to
be a **symlink** to `sed.exe`. Which tools are symlinked is packaging accident - do not rely on it.)

**Do not "fix" this by prepending a `:`-style entry to `PATH`** - that merges into the first
`;`-separated element and destroys it. (Symptom: the shell suddenly cannot find `tail`.)

**c. A library that isn't there is reported under its _last-tried_ name, which reads like a demand
for `foo_s.a`.** It is not one:

```
weakld: cannot open library file '\@unixroot\usr\lib\curses_s.a'
```

`LDFLAGS=-Zomf` links via **emxomfld**, which searches **the current directory first**, then each
directory in `LIB`, trying every suffix below in order with the prefix `lib` and then no prefix as
the inner loop `[SRC]` `src/emx/src/emxomf/emxomfld.c:924-934` (the suffix and prefix arrays) and
`:976-981` (the `.\` pre-seed), all in `find_lib()`. It reads only the `LIB` environment variable
(`:982`) - `-L` still works as you expect, because gcc composes `LIB` from its `-L` list plus its own
defaults (`gcc -print-search-dirs`) and passes it down:

| emxomfld link mode | suffixes, in order |
|---|---|
| shared - the default | `_dll.lib` `_dll.a` `.lib` `.a` `_s.lib` `_s.a` |
| shared + dll - `-Zdll-search` | as above, with `.dll` inserted after `.a` |
| static - `-Bstatic`, `-static`, `-non_shared`, `-dn` | `_s.lib` `_s.a` `.lib` `.a` |

**Those are `emxomfld`'s options, and most of them do not survive being put in `LDFLAGS`**, because
`LDFLAGS` goes to `gcc` first. Measured - `gcc -Zomf <flag> t.c -L. -lzznothing`:

| flag | what actually happens |
|---|---|
| `-static` | **works** - reports `zznothing.a`, the last suffix of the static list |
| `-Bstatic` | links, but reports `zznothing_s.a` - **the shared order; static was not selected** |
| `-Zdll-search` | `gcc: error: unrecognized command line option` |
| `-Zno-autoconv` | `gcc: error: unrecognized command line option` |
| `-non_shared` | `gcc: error: unrecognized command line option` |
| `-dn` | silently misparsed by `cc1` as a debugging option |

So through gcc, `-static` is the one that selects the static order; pass the rest to the linker
directly with `-Wl,` - which is measured, not assumed: with only `zz7.dll` present, `-lzz7` fails
(`.dll` is not in the default list) while `gcc -Zomf -Wl,-Zdll-search ... -lzz7` **links**, and
`-Wl,-non_shared` reports `zznothing.a`, the static list's last suffix. `-Bstatic` is the trap - it
neither errors nor works.

`_s.a` is merely the **last** candidate. On failure `find_lib()` leaves that last constructed name in
the buffer, and weakld prints it when it cannot open it `[SRC]`
`src/emx/src/emxomf/emxomfld.c:1151`, `src/emx/src/emxomf/weakld.c:2990`. So the message means
**nothing matching that library name was found in the build directory or any `LIB` directory** - it
is not a statement about formats. (The build directory being searched first also means a stray
`foo.lib` sitting in your tree silently outranks the packaged one.) Two consequences that follow from the table:

- **OMF import libraries resolve fine.** `.lib` is tried *before* `_s.a`, so `-lfoo` finds `foo.lib`,
  and `LDFLAGS="-Zomf" ... -lmmpm2` works once the Toolkit import libraries are on the `LIB` path.
  Those come from **`os2tk45-libs`** in `netlabs-rel` - `yum -C provides '*/mmpm2.lib'` names that
  package directly. Measured four ways: with only `zztest.lib` present and no
  `.a` of any name, `gcc -Zomf t.c -L. -lzztest` links and the `.exe` runs; a *deliberately corrupt*
  `.lib` fails inside `emxomf` ("is not an a.out file"), proving the file is opened rather than
  skipped; a valid `.lib` beside a corrupt `_s.a` links; and a corrupt `.lib` beside a valid `_s.a`
  **fails on the `.lib`** - so `.lib` is genuinely tried first, not merely accepted.
- **a.out `.a` archives work too** - measured: a lone `foo.a` links under `-Zomf`. emxomfld converts
  them to OMF during the link unless you pass `-Zno-autoconv`
  `[SRC]` `src/emx/src/emxomf/emxomfld.c:178,1016-1022`. The same branch converts an
  **LX `.dll`** it opens. Note that conversion is *not* gated on `-Zdll-search`: that flag only adds
  `.dll` to the suffix list, so it governs whether a bare `-lfoo` will *find* `foo.dll`, not whether
  a `.dll` can be linked - naming one explicitly works either way `[SRC]` same file, `:959,965,1723`.

So the real diagnosis is almost always a **name**, not a format. `ls /@unixroot/usr/lib | grep -i
<name>` - and read the answer carefully, because "present" is not the same as "linkable". In the
readline case there was nothing named `curses*` that the default search would take. Two separate
reasons, and both are worth checking on your own box:

- **ncurses may not be installed at all.** It is a real netlabs package - `ncurses-devel` is in
  **`netlabs-rel`** (`yum -C list available ncurses-devel` finds `5.7-4`, `5.9-1` and `6.4-1.oc00`),
  and the installed copies are bitwiseworks builds, same vendor and build host as `readline`. But
  being *available* is not being *present*: on the machine here
  `rpm -q --qf '%{INSTALLTIME:date}'` dates the base packages to 2015 and `ncurses`, `ncurses-base`
  and `ncurses-libs` to **late 2025**, pulled in years after `readline` itself. How much a given box
  already has depends entirely on what has been installed on it, so check rather than assume:
  `rpm -qa | grep -i ncurses`.
- **Even with it installed, `-lcurses` still fails** - `ncurses-libs` ships `libcurses.dll`, and
  `.dll` is not in the default suffix list (see the table; it needs `-Zdll-search`). What `-l`
  wants is the import library from **`ncurses-devel`**, which is a separate package.

Fix it by naming the libraries that exist (`-lncurses -ltinfo`, and see **d** below),
and only override the make variable outright when the makefile hard-codes something you cannot reach
- e.g. readline's link libs come from `SHLIB_LIBS`:

```sh
make SHELL=$SH SHLIB_LIBS="/@unixroot/usr/lib/tinfo.lib /@unixroot/usr/lib/ncurses.lib"
```

**Two older copies of this list circulate, and both disagree with the code.** `[DOC]`
`doc/ReleaseNotes.os2:966-989` in the kLIBC tree gives the same three modes with `.a` suffixes only
(`libfoo_dll.a`, `libfoo.a`, `libfoo_s.a`, ...) - note it sits under the **v3.2.2 Beta 4** heading,
even though the file ships in the GCC 3.3.5 doc directory, so grepping the 3.3.5 sections for it
finds nothing. And `find_lib()`'s **own header comment**
(`src/emx/src/emxomf/emxomfld.c:893-905`) gives a third, shorter order with no `.a` entries at all
and `.dll` in a different position. Where a comment and the arrays disagree, the arrays are what
runs. `[unverified]` when the `.lib` entries were added - they are already present in the oldest
commit touching those lines in this tree, so do not assume the release note was ever accurate.

**d. ncurses splits the termcap entry points into `tinfo.lib`.** Linking only `ncurses.lib` leaves
`tgetent`/`tgetstr`/`tgetflag`/`tgetnum`/`tputs`/`tgoto`/`PC`/`BC`/`UP` undefined. Link **both**.
Confirmed against the shipped DLLs: an import library generated with `emximp` from `ncurses6.dll`
carries `initscr` and *none* of the termcap entry points, while one from `tinfo6.dll` carries
`tgetent`, `tgetflag`, `tputs` and `tgoto` and no `initscr`. (Probe note: `strings` on such a library
emits names tab-prefixed, so match on substring - an anchored `grep -x` finds nothing and looks like
proof of absence.)
(A cryptic `sed -i -e 's/tinfo//'` in a spec file is usually a hint that this bit the packager too.)

Install the devel packages first: `yum -y install ncurses-devel libcx-devel`. Note this pulls ncurses
into a tree that may not have had it - which is fine for building, but means the resulting binary now
has a dependency the target box may not carry. Check what the `.spec` actually requires rather than
inheriting whatever your build machine accumulated.

**e. A `libtool`-using `configure` needs the shared/static choice spelled out.** Don't rely on the
platform default - pass it explicitly:

```sh
./configure --disable-static --enable-shared   # building a DLL
./configure --enable-static --disable-shared   # building a static archive
```

Measured against a minimal `LT_INIT`-based `configure` (autoconf 2.71, netlabs RPM userland): both
combinations are honoured - `checking whether to build shared libraries...`/`...static
libraries...` flip accordingly with no other change in configure's output.

**That confirms the flag, not the link.** Finishing the actual DLL link with the *generic* `libtool`
that a plain `autoreconf` bundles (upstream `ltmain.sh`, not netlabs' patched one) hit real
shell-compatibility bugs in this environment: under `sh.exe` (ash), `eval`-ing the generated
`archive_cmds` drops the backslash in `$ECHO`'s `printf %s\n`, so the `.def` file loses its newlines
(`printf %sn LIBRARY foo0 INITINSTANCE...` in an `sh -x` trace) and `emxbind` rejects it; switching
`CONFIG_SHELL`/`SHELL` to `bash.exe` fixes that but then mangles `$SED`'s path (`C:\usr\bin/sed` ->
`C:usrbin/sed`) instead.

**Confirmed: the netlabs-packaged `libtool` avoids both.** `yum -y install autoconf automake libtool`
on the OS/2 box itself (not the host), then `autoreconf -fvi` there instead of cross-generating on
Linux - this pulls in netlabs' patched `libtool.m4`/`ltmain.sh`. Under `sh.exe`, the same `.def`
generation this time produced a well-formed file first try:

```
LIBRARY foo0 INITINSTANCE TERMINSTANCE
DESCRIPTION "foo"
DATA MULTIPLE NONSHARED
EXPORTS
  "_foo"
```

- no `eval`/backslash corruption. That much matches Dave Yeo's claim about bitwiseworks' patches
directly. **So: generate `configure` on the OS/2 box with its own `autoconf`/`libtool` when a package
uses `LT_INIT`, not by cross-generating on the host** - this recipe's section 2 advice to generate on
the host is still right for plain `autoconf` packages (no libtool involved), but does not carry over to
libtool-using ones, since the fix lives in the *macros*, not just the generated shell.

**A second, unrelated blocker turned up finishing the link, worth knowing about separately.** The
netlabs libtool's `archive_cmds` link with `-Zdll -Zomf`, and `emxomfld -Zdll` shells out to an
*external* OMF linker it does not bundle - `emxomfld` with no arguments documents this:

```
EMXOMFLD_TYPE: WLINK | VAC365 | VAC308 | LINK386   (default: VAC365, i.e. ilink.exe)
```

On this VM none of the three backends (`ilink.exe`, `wlink.exe`, `link386.exe`) exist anywhere on
disk, and none are provided by any package in the `netlabs-rel` repo (`yum -C provides` on all three
comes back empty) - so `-Zomf` DLL linking cannot complete on a box built only from `yum install
gcc libtool automake autoconf`, independent of anything libtool does right or wrong. A real netlabs
build server evidently has one of these three installed from outside the RPM repo (Open Watcom's
`wlink` is the most plausible, non-commercial option - `EMXOMFLD_TYPE=WLINK` once it's present;
`watcom-wlink-hll` in `netlabs-rel` provides it as `wl.exe`, so set `EMXOMFLD_LINKER=wl.exe` too).
Check for one of the three before trusting a `-Zomf` DLL build to complete; a missing-`ilink.exe`
failure this late (after configure, after compiling, after generating a correct `.def`) reads like a
libtool bug and is not one.

**Which IBM linker actually works, measured (2026-08) [OBS-RE].** Not every `ilink.exe` can link
what `emxomfld` emits; generations behave differently against the same object set (a large mixed
16/32-bit DLL, LIBC Next's own `libcn0.dll`):

| linker | verdict |
|---|---|
| `LINK386` (OS/2 Toolkit 4.5 `link386.exe`) | rejects: `L2050 use16/use32 attribute conflict - segment: CODE16 in group: CGROUP` |
| ilink 1.00.05 (VisualAge C++ 3.0, 1995) | same `LNK2050` rejection |
| ilink 03.06 (IBM C/C++ 3.6.5, 1998) | links small exes; fails rc=5 on large links, and its diagnostics print as blank lines unless its message file (`CPPLLM36.MSG`) is reachable via `DPATH` - budget for flying blind |
| ilink 5.0 (2003) | links everything tested, no setup beyond its own directory |

ilink 5.0 circulates as a standalone `ilink50.zip` (~300 KB: `ilink.exe` plus `hll4pk50.dll`/
`hll6pk50.dll`) in community archives (os2site.com's vacpp directory, among others). Unzip anywhere,
put that directory on `BEGINLIBPATH` (or `LIBPATH`), and use `EMXOMFLD_TYPE=VAC365`
`EMXOMFLD_LINKER=<dir>/ilink.exe`. Note `emxomfld`'s "VAC365" default expects this ilink-5
generation, not the 3.6.5-vintage 03.06 the name suggests. `wlink` links the same inputs fine, and
for LIBC Next the wlink- and ilink5-linked DLLs behaved identically in testing (differing LX object
layout, same runtime behavior) - so wlink remains the right default when you have no ilink.

One `emxomfld` debugging note [SRC `src/emx/src/emxomf/emxomfld.c`, observed 2026-08]: with `-t` it
prints the response file it passed to the linker, but it reads the file back *after* the child linker
has run and temp cleanup may have removed it - an empty `--- Response file ---` dump does not mean an
empty response file. Do not chase that.

## 4. Load the patched DLL for one process only

Never overwrite the system copy while testing. OS/2 supports per-process library paths:

```sh
SET LIBPATHSTRICT=T          # see below: without it a *resident* system copy still wins
SET BEGINLIBPATH=C:\mylibs
```

**`BEGINLIBPATH` is not an ordinary environment variable** - it is applied via `DosSetExtLIBPATH`, so
`env VAR=... prog` is silently ignored. Measured: under `env BEGINLIBPATH=C:/marker prog`, `getenv()`
returns `C:/marker` while `DosQueryExtLIBPATH()` still reports the real path. Set it with `SET` inside
a `.cmd` file (or call the API).

**What `LIBPATHSTRICT` actually buys you, and why forgetting it fails only sometimes.** It is *not*
what makes `BEGINLIBPATH` outrank `LIBPATH` - that happens anyway. It is what defeats a copy **already
resident in the shared arena**. Measured with two DLLs of the same name, one on `LIBPATH` and one in a
private directory:

| situation | which copy loaded |
|---|---|
| no `BEGINLIBPATH` | the `LIBPATH` one |
| `BEGINLIBPATH` alone, **nothing else holding the DLL** | the private one - shadowing works |
| `BEGINLIBPATH` alone, **another process holding it** | **the `LIBPATH` one** - resident copy wins |
| `LIBPATHSTRICT=T` + `BEGINLIBPATH`, holder running | the private one |

So the omission is **intermittent by construction**: it works on a quiet box and silently stops
working the moment anything else has that DLL open - which is precisely when you are mid-debug with
another instance running. Set it always.

**Correction (2026-08): this technique must NOT be used when the DLL under test is LIBCN0.DLL
itself.** The advice above stands for ordinary DLLs, and recommending it for every DLL was the
natural reading - but a second resident copy of LIBC Next breaks kLIBC `fork()` outright
[OBS-RE]: a shell launched this way runs builtins and spawn-path (last-command) externals fine,
then hangs forever on the first real `fork()` - even when the side-loaded file is a
byte-identical copy of the installed `libcn0.dll`, which acquits the DLL's contents and
convicts the second copy. The failure is silent and looks exactly like a bug in whatever patch
you are testing; symptoms and detail in `../os2ref/klibc-runtime-glue.md` section 3.3. To test a
rebuilt LIBC: snapshot the VM, install it as the system copy, reboot. The system copy cannot be
overwritten or renamed while loaded (`SYS0032`), so stage the new file and copy it from the top
of `STARTUP.CMD` - at that point only native (non-kLIBC) processes have started, and the copy
succeeds.

**Verify which copy actually loaded.** OS/2 keys loaded DLLs **by name in the shared arena**, so a
copy already resident in another process can win over your private one and you will test the wrong
binary - the third row above is that happening. A ten-line probe settles it, and it is what produced
that table:

```c
#define INCL_DOSMODULEMGR
HMODULE h; char err[260], name[260];
DosLoadModule(err, sizeof err, "READLN8", &h);
DosQueryModuleName(h, sizeof name, name);      /* prints the path actually resolved */
```

Run it under the same environment as your program. Kill every process holding the DLL before
re-testing, or you are measuring the resident copy.

## 5. Deploy safely (the trap that invalidates test results)

**A running program locks its `.EXE` and its DLLs**, so a `cp` over them *fails* - and if your build
script filters output, the failure is invisible and every subsequent test measures the **old**
binary. This is `setup-test-vm.md`'s "running `.EXE` is locked" trap in its most expensive form.

```sh
ps | awk '$5=="myapp"'           # find holders (OS/2 ps: no .exe suffix, no `ax`)
# kill them, then deploy, then CHECK THE TIMESTAMP MOVED:
cp new.dll C:/mylibs/ && ls -l C:/mylibs/new.dll
```

Rules that follow, both learned the hard way:

- **Kill every holder before deploying**, then verify the size/timestamp changed.
- **Never filter build output down to a keyword.** `... | grep -iE "DEPLOYED|error:"` turned a failed
  deploy into *silence*, which reads as success. Print an unfiltered tail.
- If a process ignores `kill`, you need a ring-0 killer; see `setup-test-vm.md`. Do not assume it
  will: a plain kLIBC program blocked in `sleep()` dies on an ordinary SIGTERM here. The stubborn
  cases are the ones worth naming, and which they are is `[unverified]` - a PM message loop or a
  thread blocked in a device call are the usual suspects. Try `kill`, then `kill -9`, and reach for
  the ring-0 tool only when both leave the process in `ps`.

### 5a. A subset build breaks every system binary that imports the DLL — check the export table [OBS-RE]

**Measured 2026-09-05, rebuilding `ncurses`'s `tinfo6.dll`.** A locally rebuilt DLL replaced the
shipped one and every stock binary that imported it — `infocmp`, `tput`, `tic` — died with
**`SYS2070`** (`Bus error`, rc 138), while the rebuilt DLL's *own* runtime paths worked fine.

Cause: the rebuild produced a DLL with a **different export table** than the shipped one. OS/2
binaries import a DLL **by ordinal**, and `emxexp`/the linker assign ordinals *sequentially in the
order the object files are exported*. So dropping even one exported symbol shifts every later
ordinal, and a stock caller's ordinal-N import (say `_nc_capcmp`) then binds to a *different*
function in your DLL → it calls the wrong code with the wrong arguments → `SYS2070`. Here the
rebuild had been configured `--without-progs`, which dropped 31 terminfo-compiler functions from
the library: **280 exports shipped, 249 in mine.** Nothing about the *code* was wrong; the export
*surface* was a subset.

`lx_export.py` names this failure in one line — "compare the importing
side's requested ordinal against the exporting side's entry table" — and `SYS2070` in
`C:\POPUPLOG.OS2` resolves to `IMPORTER->DLL.symbol` at an offset, which points at the *expected*
symbol, not the one actually run (a red herring that sent this investigation at codegen and the
linker first; both were exonerated).

**Rules:**

- **Build the whole package to the spec's `%configure`.** A subset build (a stripped flag like
  `--without-progs`, a dropped source, a different `--with-termlib`/`--with-ticlib` split) is not a
  smaller version of the DLL — it is an ABI-incompatible one.
- **Gate a rebuilt DLL on its export table before trusting it**, by diffing against the shipped
  import library or the shipped DLL:
  ```sh
  # names the shipped side exports (its import lib lists them):
  nm /@unixroot/usr/lib/<name>_dll.a | awk '/=.*\./{print $NF}' | sed 's/=.*//' | sort -u
  # vs. your rebuild's, or use the toolkit tool on the DLLs directly:
  lx_export.py <your>.dll        # exports + imports + ordinals
  ```
  Equal symbol *set* built from the same configure ⇒ equal ordinals. A different count ⇒ stop.
- This is why section 4's "load for one process only" is the safe way to *test* a rebuild: your own
  test program imports by name and tolerates a subset, so it passes while the system binaries that
  import by ordinal would crash — the subset defect is invisible until you deploy over the system copy.

## 5b. Package notes: rebuilding LIBC Next itself (`libc`)

Everything above applies, plus traps specific to this one package, all measured on a rebuild of
`libc-0.1.14` from its SRPM (2026-08) [OBS-RE unless tagged otherwise]:

- **Build in the spec's three phases, not one `kmk ... libs`.** The spec runs `kmk ... tools`,
  then `kmk ... -f libonly.gmk libc-std.h`, then `kmk ... libs`, with a comment that a kmk
  `.NOTPARALLEL` bug over the `$(_STD_WILDWILD)` deps forces the separate `libc-std.h` step
  [SRC `libc.spec` %build]. It is not pedantry: if any `include/` header changed, a plain
  `libs` invocation dies regenerating `libc-std.h` before the DLL links.
- **`OPTIMIZE_FLAGS` must target i486 or later.** Plain `-march=i386` fails at link with
  unresolved `__atomic_fetch_add_4`/`__atomic_fetch_sub_4` from `sem_*` - gcc emits libatomic
  calls i386 cannot inline. The shipped `.pentium4` packages imply `-march=pentium4`; the
  `rpm --eval %{optflags}` on a stock box prints the generic i386 default, which is *not* what
  built the binaries you have installed.
- **The full `libs` target rarely goes green end-to-end here; `libcn0.dll` links long before
  the stragglers fail.** Observed stragglers: profile/log archive steps dying in `ar` (both the
  `ar -M` script form and an `ar rcs @objlist` with an empty objlist), and `emxomf` conversions
  of archives the earlier failure never produced. Check for `out/opt/omf/libcn0.dll` with a
  fresh timestamp instead of trusting the exit code - and per section 5, never filter the log.
- **Programs calling newly added exports need `libc_alias.lib` and `libc_dll.lib` as explicit
  link inputs**, in that order. Public names are aliases: the DLL exports `__std_<name>` and
  `libc_alias.lib` maps `<name>` to it, so linking against the import lib alone leaves the
  plain name unresolved.
- **Do not run builds while a strict/log-flavor LIBC is the system copy.** The strict build's
  asserts fire on latent bugs in ordinary tooling (observed: `__spawnve.c` assertion in a shell
  pipeline), killing builds mid-flight - and the log flavor writes per-process logs to
  `%UNIXROOT%\var\log\app` at hundreds of MB per hour of activity, which on a small system
  volume ends in `Disk full` failures that read as silent `kmk` exits. Deploy strict/log
  flavors only for a short diagnostic window, then swap back and clean the log directory.
- Testing the result: see the section 4 correction - never side-load a rebuilt LIBC; install
  it as the system copy on a snapshot.

## 6. Upstreaming the fix

If the bug is real, send it back - these ports are maintained and small fixes land.

- **Preserve line endings.** Many of these files are CRLF; editing them with a Unix tool silently
  converts the whole file and a 15-line change appears as a 135-line diff. `file <path>` before you
  edit; restore with `sed -i 's/$/\r/'` if you flattened it.
- Keep each logical fix a separate change - a reviewer can take three small correct patches far more
  easily than one large one, and partial acceptance still improves the tree.
- Cite the mechanism, not just the symptom: the maintainer can verify "this variable is assigned in
  two places and never read" from their own source without reproducing your setup.
