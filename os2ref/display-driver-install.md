# Installing and configuring OS/2 display drivers - DSPINSTL, RSPDSPI, .DSC and .DSP

How OS/2 installs and switches display drivers, and how to drive that non-interactively: the two
installer programs and their command lines, the `.DSC`/`.DSP` data files that describe a driver
package, how a package is resolved and applied, and what a base-VGA install actually changes in
`CONFIG.SYS` and `OS2.INI`. Companion to `video-stack.md`, which covers who owns the screen once a
driver is installed.

Source tags: **[DOC-IBM]** = IBM DDK source or published IBM documentation; **[OBS]** = observed
directly in a shipped OS/2 install (Warp Server for e-business, `4.50`/`4.52`, and the DDK's own
`video/src/video/bbsinst/` driver-install sources). Nothing here is inferred; every claim is one or
the other.

---

## 0. The two installers

| Program | Location | Role |
|---|---|---|
| `DSPINSTL.EXE` | `\OS2\INSTALL` | The general display installer. Interactive (PM) with no arguments; fully unattended with arguments. Consumes a `.DSC` package description. |
| `RSPDSPI.EXE` | `\OS2\INSTALL` | The response/key-driven installer. Selects a package by *adapter type key* rather than by `.DSC` path. |

[DOC-IBM] *"DSPINSTL.EXE is an OS/2 executable that is used to install display drivers. It can be
invoked without parameters and will then guide the user with a PM interface or it can be invoked
with parameters and executes then without user prompting. It resides in the `\OS2\INSTALL`
subdirectory and is invoked from there."*

Two shipped `.CMD` wrappers drive `RSPDSPI` for the two base cases, and are the supported way to
reset a system's display without media [OBS]:

| Wrapper | Runs | Result |
|---|---|---|
| `\OS2\SETVGA.CMD  <target> <source>` | `RSPDSPI /PK:VGA /SK:NONE /S:<source> /T:<target>` | base, non-GRADD VGA (`IBMVGA32`) |
| `\OS2\SETGRADD.CMD <target> <source>` | `RSPDSPI /PK:DEFAULT /SK:NONE /S:<source> /T:<target>` | the GRADD stack |

Both default to `source = <bootdrive>:\OS2\INSTALL\VGA` when called with no arguments. `SETVGA.CMD`
is what the Alt+F1 -> **V** boot-recovery choice performs.

---

## 1. `DSPINSTL` command line

All switches are case-insensitive. [DOC-IBM DDDR/2, *Installing and Configuring Display Device
Drivers*]

| Switch | Meaning |
|---|---|
| `/PD:<path\file.dsc>` | primary `.DSC` package to install |
| `/SD:<path\file.dsc>` | secondary `.DSC` package (dual-display systems) |
| `/PK:<type key>` | primary adapter type key - selects a package by key instead of path |
| `/SK:<type key>` | secondary adapter type key (`NONE` for single-display) |
| `/S:<path>` | source directory holding the `.DSP` files and packed payload |
| `/T:<drive>` | target drive where OS/2 is installed |
| `/RES:<W>x<H>x<colors>` | default resolution for multi-resolution drivers |
| `/MC:<n>` | manufacturer code - SVGA packages only |
| `/L1:<path>` | log file path |
| `/U` | unattended: no prompting, no PM panels |

Standard type keys are `CGA`, `EGA`, `VGA`, `8514`, `XGA`, `SVGA` [DOC-IBM]; a shipped system also
accepts `DEFAULT` (the GRADD package) and `NONE` [OBS]. A package whose adapter is not one of the
standard types uses the type key `OTHER` in its `.DSC` [OBS].

`/?` is not a switch. An unparseable command line is reported only in the log, as
`ProcessCmdLine Failure` [OBS].

SVGA manufacturer codes for `/MC:` [DOC-IBM]: 1 Headland, 2 Trident, 3 Tseng ET4000, 4 Western
Digital, 5 ATI, 6 Speedway, 7 Cirrus Logic.

---

## 2. The `.DSC` file - a package description

A `.DSC` names one installable display package and lists the `.DSP` steps it is built from. `.DSC`
files live in `\OS2\INSTALL`; `DSPINSTL` searches its own directory first, then `DPATH`
[DOC-IBM].

Syntax: values are double-quoted strings, one per line; `*` begins a comment; `\"` embeds a quote.
A shipped file may carry a resource ordinal (`^ 6`) in place of a literal title string, in which
case the text comes from `DSPRES.DLL` [OBS].

Field order:

```
"<title>"                 * shown in the driver list
"<action DLL>"            * package-specific logic, "" if none (e.g. "SVGA.DLL")
"<type key>"              * VGA | SVGA | XGA | 8514 | CGA | EGA | OTHER
"<n extra parameters>"    * "0" for everything but SVGA
"<n chain elements>"      * how many steps follow
```

then, repeated once per chain element:

```
"<DSP key>"               * matched against a .DSP file's :KEY (NOT a filename)
"<general prompt>"
"<diskette prompt>"
"<volume label>"
"<resolution string>"     * "" when the step is not resolution-dependent
```

### The base-VGA package versus the GRADD package [OBS]

| | `PSVGA32.DSC` | `VGAGRADD.DSC` |
|---|---|---|
| title | `Video Graphics Array (VGA)` | `Video Graphics Array (VGA) GRADD` |
| type key | `VGA` | `OTHER` |
| chain | `CFGDEL` -> `COMBASE` -> `VGA32` | `CFGDEL` -> `COMBASE` -> `VGA32` -> `COMGRADD` -> `VGAGRADD` |

The GRADD package is the base VGA package plus two further steps. Installing the base package is
therefore not a separate driver so much as the same chain stopped early, with `CFGDEL` removing
whatever the previous package added.

---

## 3. The `.DSP` file - one installation step

A `.DSP` is an interpreted script of tagged sections. Keywords are uppercase and colon-prefixed;
`*` begins a comment.

**Selection is by `:KEY`, not by filename.** *"In each step, all the DSP files in the current source
directory (whose keyword strings match the keyword string for that step) are interpreted."*
[DOC-IBM] This matters in practice: the shipped file satisfying the `COMBASE` step is named
`COMVGA.DSP` [OBS]. Do not reason about a package's completeness from filenames - grep `:KEY`.

### Sections

| Tag | Effect |
|---|---|
| `:KEY` | this file's keyword (max 64 bytes, no embedded blanks) |
| `:TITLE` | descriptive only |
| `:FILES` | copy source files to destinations |
| `:APPEND` | append to an existing target file |
| `:CONFIG` | add lines to `CONFIG.SYS` |
| `:DEL_CONFIG_LINE` | delete lines from `CONFIG.SYS` |
| `:AUTO_EXEC` | update `AUTOEXEC.BAT` |
| `:OS2INI` | add or delete `OS2.INI` / `OS2SYS.INI` / named-`.INI` entries |
| `:WININI` | update WIN-OS/2 `WIN.INI` / `SYSTEM.INI` |
| `:RUN` | run a program; its stdout is interpreted as further DSP commands |
| `:SET_DRIVER` | register the 32-bit driver (`NAME=`, `DESC=`, `PATHNAME=`, `PARMS=`) |
| `:SET_RESOLUTION` | set the initial resolution (`WIDTH=`, `HEIGHT=`, `COLORS=`, `PLANES=`) |

Substitutions available in a section body include `%BOOTDRIVE%`, `%WINPATH%`, `%NLV%`, `%CS%`,
`%PRI%`, and `%ANYSTRING%` as an `.INI`-value wildcard [OBS].

### `:MODE=` qualifiers

Any section except `:KEY` may be qualified, and a section runs only if every qualifier on it holds.
IBM documents `PRIMARY`, `SECONDARY`, `DOS`, `WINDOWS` [DOC-IBM]. Shipped `.DSP` files use a wider
set, and also a **negated** form `:MODE!=X` that the published description does not mention [OBS]:

- display role - `PRIMARY`, `SECONDARY`, `DUAL`
- subsystem - `DOS`, `WINDOWS`, `WINOS2`, `WINDOWS_H`, `WINDOWS_J`, `WINDOWS_T`
- character set / locale - `SBCS`, `DBCS`, `BIDI`, `ARABIC`, `GR`, `JP`, `CN`, `KR`
- version - `V4`

Example, both forms on one file:

```
:CONFIG :MODE=PRIMARY :MODE=SBCS :MODE!=BIDI
SET VIO_VGA=DEVICE(BVHVGA)
```

---

## 4. `CFGDEL` - the teardown step

Every display package begins with the `CFGDEL` step, whose job is to remove the previous driver's
configuration before the new one is written. It is what makes switching drivers idempotent rather
than cumulative. [OBS]

Its `:DEL_CONFIG_LINE` section is a **literal list of exact `CONFIG.SYS` lines to delete** - not a
pattern match. It enumerates every line any shipped display package can produce: each
`DEVICE=...\GRADD.SYS`, `XGA.SYS`, vendor `.SYS`; every `SET C1=` GRADD chain spelling
(`GENGRADD`, `GENGRADD,SBFILTER`, `GENGRADD,SBFILTER,VGAGRADD`, `S3GRADD`, `MGAGRADD`, ...);
`SET GRADD_CHAINS=C1`; and every `SET VIDEO_DEVICES=` / `SET VIO_*=DEVICE(...)` variant.

**Consequence:** a hand-edited `CONFIG.SYS` line that differs from the shipped spelling - different
whitespace, a chain order not in the list, a driver the list predates - survives the install. After
an automated driver switch, verify `CONFIG.SYS` rather than assuming the teardown was complete.

`CFGDEL` also clears the stale resolution keys from `OS2.INI` (`WIN_RES_*`), clears
`InstallWindow`'s `VIOADAPTERSTR` / `SVGA_RESOLUTION` from `REINSTAL.INI` so Selective Install
re-detects, and deletes `PRIVATE.DIF` and `SDDPMI.CFG`.

---

## 5. What a base-VGA install produces

`CONFIG.SYS`, after `CFGDEL` removes the previous package and `VGA32` writes its own [OBS]:

```
DEVINFO=SCR,VGA,<bootdrive>:\OS2\BOOT\VIOTBL.DCP
SET VIDEO_DEVICES=VIO_VGA
SET VIO_VGA=DEVICE(BVHVGA)          ; SBCS, non-BIDI
DEVICE=<bootdrive>:\OS2\MDOS\VVGA.SYS   ; when DOS support is installed
```

`SET VIO_VGA` varies by locale mode: `DEVICE(BVHVGA,BDBVH)` under BIDI, `DEVICE(BVHVGA,BVHVGA2)`
under DBCS.

`OS2.INI`:

```
PM_DISPLAYDRIVERS  IBMVGA32       IBMVGA32
PM_DISPLAYDRIVERS  CURRENTDRIVER  IBMVGA32
PM_DISPLAYDRIVERS  DEFAULTDRIVER  IBMVGA32
```

Note what is *absent* relative to a GRADD install: no `DEVICE=...\GRADD.SYS`, no `SET C1=`, no
`SET GRADD_CHAINS=`.

---

## 6. Installing without media

`\OS2\INSTALL\VGA` on an installed system is a complete, self-contained source directory for the
base-VGA and GRADD packages - no diskette or CD image is required to switch a system's display
driver. [OBS]

| File | `:KEY` | Satisfies |
|---|---|---|
| `CFGDEL.DSP` | `CFGDEL` | teardown step |
| `COMVGA.DSP` | **`COMBASE`** | common base-video step |
| `VGA.DSP` | `VGA32` | the `IBMVGA32` driver step |
| `COMGRADD.DSP` | `COMGRADD` | GRADD common step |
| `G_VGRADD.DSP` | `G_VGRADD` | generic VESA/VGA GRADD step |

Alongside them sit the packed payload archives `VGA`, `VGADOS` and `GRADD`, plus a private copy of
`DSPINSTL.EXE` and `DSPRES.DLL`. The `VGA` archive carries `IBMVGA32.DLL`, `BVHVGA.DLL`,
`BVHSVGA.DLL`, `DISPLAY.DLL`, `VIDEOPMI.DLL`, `SCREEN01.SYS` and `SCREEN02.SYS` - the whole base
video set. `COMBASE` unpacks `VGA` and `VGADOS` to the boot drive and copies `DSPRES.DLL` into
`\OS2\DLL`.

`CFGDEL` + `COMVGA` + `VGA` is exactly `PSVGA32.DSC`'s three-element chain, so either of these
installs base VGA with nothing but what is already on disk:

```
\OS2\SETVGA.CMD C: C:\OS2\INSTALL\VGA

C:\OS2\INSTALL\DSPINSTL.EXE /PD:C:\OS2\INSTALL\PSVGA32.DSC /S:C:\OS2\INSTALL\VGA /T:C: /U
```

The GRADD package needs `COMGRADD` and a GRADD step as well; `\OS2\SETGRADD.CMD C: C:\OS2\INSTALL\VGA`
is the corresponding reverse.

---

## 7. Operational notes

- **Environment.** `DSPINSTL` resolves `.DSC` files through its own directory and then `DPATH`, and
  needs its message file on `DPATH` to report anything; run from `\OS2\INSTALL` with `PATH` and
  `DPATH` including `<boot>:\`, `<boot>:\OS2` and `<boot>:\OS2\INSTALL`. The shipped `SETVGA.CMD`
  sets exactly these before invoking `RSPDSPI`. Invoked without them it fails with
  `Message file not found` [OBS].
- **Logs are the diagnostic channel**, not the exit code: `\OS2\INSTALL\DSPINSTL.LOG` and
  `DISPLAY.LOG`. They record the resolved primary `.DSC`, the source directory, detected adapter,
  each `.DSP` interpreted, each `CONFIG.SYS` line written, and argument-parsing failures.
- **Reboot.** A driver switch takes effect on reboot. A package that replaces the base video
  drivers (`SCREEN01.SYS` / `SCREEN02.SYS`) needs the reboot *before* `DSPINSTL` runs, and another
  after - hence the two-phase `SETUP.CMD`-then-`DSPINSTL` pattern in IBM's CID stanzas. [DOC-IBM]
- **CID/LCU.** In an LCU command file the install is two products - a `SETUP.CMD` that lays down
  the package and its `.DSC`, then `DSPINSTL` with `/PD:` - separated by a state change and a
  reboot. [DOC-IBM]

---

## Sources

- IBM DDK, `video/src/video/bbsinst/` - IBM's own display-driver install sources: `vga/psvgabb.dsc`,
  `vga/psvga32.dsp`, `vga/combase.dsp`, `vga/cfgdel.dsp`, `gradd/*.dsp`, and the CID/LCU install
  stanza documented in `bga/sbcs/readme.txt`.
- IBM Developer Connection, `cid/svgacid/readme` - IBM's description of `DSPINSTL`'s parameters
  (`/PK:`, `/SK:`, `/S:`, `/T:`, `/MC:`), the SVGA manufacturer-code table, and the LCU product
  stanza.
- DDDR/2, *Installing and Configuring Display Device Drivers* - the `.DSC`/`.DSP` file formats, the
  full switch list including `/PD:`, `/SD:`, `/RES:`, `/L1:` and `/U`, and `:KEY`-based DSP
  matching. Reprinted at
  <https://www.edm2.com/index.php/DDDR/2_-_Installing_and_Configuring_Display_Device_Drivers>.
- Shipped OS/2 Warp Server for e-business (`4.50`/`4.52`) system - `\OS2\INSTALL\*.DSC`,
  `\OS2\INSTALL\VGA\`, `\OS2\SETVGA.CMD`, `\OS2\SETGRADD.CMD`, `\OS2\INSTALL\DSPINSTL.LOG`.
- IBM, *Returning the System to VGA Mode in OS/2 Warp*, and the OS2World wiki's
  "How to force OS/2 to VGA-Mode" - the `RSPDSPI /PK:VGA /SK:NONE /S: /T:` recovery form.
