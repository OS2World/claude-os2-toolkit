# OS/2 Presentation Manager - Third-Party Control Classes, by License

PM ships 15 preregistered control classes and no more (`pm-controls.md`). There is no stock
toolbar, no status bar, no progress bar, no splitter, no tooltip and no 3D group box, so every OS/2
application that wanted one either wrote its own `WinRegisterClass` class or borrowed someone
else's. This doc surveys the borrowable ones in the Hobbes archive and answers the question that
decides whether you can use each: **what license is it under, and which file says so.**

It is a companion to `pm-controls.md`, which documents IBM's own control set. That doc is
`[DOC-IBM]` throughout. **This one contains no IBM material and carries no IBM authority** - it
describes third-party software that runs on OS/2, which `CONTRIBUTING.md` section 3 puts in scope.

Provenance: **[SRC]** for facts read out of a package's own files - what it registers, what it
ships, what its license text says - cited as `archive.zip :: path-inside`. Archive paths are
relative to the Hobbes tree (`pub/os2/...`); see `sources.md` section 5. Note this stretches
`[SRC]` slightly: `os2ref/README.md` defines it for *implementation* readings, and a `LICENSE.txt`
is legal text, not implementation. It is used here because the reading is still primary - the
package's own bytes - and no better tag exists. **[OBS-RE]** marks facts produced by scanning the
archive, where the method is the evidence. Nothing here is `[DOC-IBM]`, and nothing here is legal
advice - the citation exists so you can read the terms yourself.

Every verdict below was read from the package. Verified 2026-08-03 against the 11-Jan-2024 Hobbes
snapshot; a *later* release may be relicensed, so check the version you download.

---

## 1. How the licenses were established, and two traps

**Do not trust the catalog.** Hobbes' `license` field is empty for 10,694 of its 12,253 entries,
and package blurbs are written by uploaders, not authors `[OBS-RE catalog.json]`.

**Terms live in four places**, in descending order of authority. All four must be checked; the
last two are where most of this archive keeps them:

```sh
unzip -l PKG.zip | grep -iE 'licen[cs]e|copying|readme|read\.me|\.txt|\.text|\.doc|\.htm|\.now|\.1st|\.diz|\.nfo'
unzip -p PKG.zip LICENSE.txt              # 1. dedicated license file
unzip -p PKG.zip HTML_Docs/thing.html     # 2. terms in any doc, including HTML
unzip -p PKG.zip src/thing.c | head -40   # 3. per-file notice - binding, and invisible in a listing
unzip -p PKG.zip readme.txt               # 4. informal grant in plain prose
```

**Then do it again one level down.** The common OS/2 release layout is binaries plus a nested
`source.zip`, and the license frequently ships with the source, not the wrapper. A top-level
listing shows a `.zip` and stops:

```sh
unzip -l PKG.zip | grep -i '\.zip'                  # is there a nested archive?
unzip -p PKG.zip inner.zip > /tmp/inner.zip && unzip -l /tmp/inner.zip
```

DrDialog Controls (section 3.1) is BSD-licensed entirely on the strength of a `Readme.txt` inside
its nested zip; the outer archive states nothing. Skipping this step also hides roughly half the
archive's PM source outright (section 4).

**Trap 1: a keyword scan inverts negated grants.** Matching license names against package text is
the obvious way to do this at scale. Two of the packages below were classified backwards by exactly
that method, both granting permission where the text denies it:

- SplitPane read as shareware. Its terms say commercial *"(including shareware)"* use is
  **negotiable with the author** - the word sits inside the exclusion.
- Extended List Boxes read as public domain, from a sentence saying it is **not** public domain.

**Trap 2 - the expensive one: a keyword scan cannot see a grant that names no license.** Much of
this archive licenses in plain prose - *"its yours to play with"*, *"Feel free to modify it as you
please"*, *"Use the sourcecodes supplied for any commercial or noncommercial product"*. A scanner
looking for `GPL|BSD|MIT` scores every one of those as **silence**, and silence reads as *"you may
not use this"* - the exact inverse of what the author wrote. Six of the eighteen packages first
surveyed here were wrong for this reason before they were read by hand.

**The tell.** If a package's verdict is "no terms" and nobody has opened its readme and the first
40 lines of its sources, the verdict means "my scanner has no pattern for this", not "the author
granted nothing". Treat any automated classification as a worklist of files to read.

**A local trap worth naming** `[OBS-RE]`**.** These packages are CP437/CP850, so a `.c` file with
one accented character is `Non-ISO extended-ASCII`. Tools that skip binary files - `ugrep -I`, and
anything wrapping it - silently return nothing on them, exit 0, and look identical to "no match".
Use `LC_ALL=C grep -a`, as `recipes/read-ibm-books.md` says for the IBM books; the same failure
applies to source. A full GPLv2 notice went undetected here for exactly this reason.

---

## 2. The widgets

Language is what the code *is*, not what the extension says (see section 3.6). "Stated in" is the
file to read.

### Permissive - usable in closed source, with attribution

| Widget | Provides | Lang | License | Stated in |
|---|---|---|---|---|
| Cantatore's Libraries 0.1 | 9 classes (3D group box, status bar, ext/combo list box, ...) | C | BSD-3-Clause | `LICENSE.txt` |
| DrDialog Controls 0.1.5 | percent bar, bubble help, image, histogram | C | BSD-3-Clause | `Readme.txt` |
| PmCtlsPP | behaviour changes to stock controls | C | BSD-3-Clause | `PmCtlsPP/License.txt` |
| Cell Toolkit 0.7b | split views, toolbars | C++ | BSD-2-Clause | `license.txt` |

### Copyleft - check what it does to your program before linking

| Widget | Provides | Lang | License | Stated in |
|---|---|---|---|---|
| Shape Window Library 2.00 | non-rectangular windows | C | LGPL-2.1-or-later (code only) | `LGPL_en.txt` |
| AsuaCtl 1.0 | toolbar, status bar, progress bar, buttons | C | GPL-2.0-only | per-file notices |
| XWorkplace helpers 0.9.7 | splitter, tooltip, text view, shape window | C | GPL-2.0-only | `XWPH0208.ZIP::COPYING` |
| XWPWidget 0.7.3 | XCenter widgets (not PM controls) | C | GPL-2.0-only | per-file notices |

### Informal grant - permission given, but not in license form

| Widget | Provides | Lang | Granted | Stated in |
|---|---|---|---|---|
| OS/2 Primecuts | canvas + terminal window classes | C/C++ | any commercial or noncommercial use of the sources | `OS!2 Primecuts Information.text` section 4 |
| Shaded Buttons 0.2 / 1.15 | gradient push button | C / C++ | modify for your own programs; redistribute | `Buttons.TXT`, `HTML_Docs/ShadeBtn.html` |
| DayField | day-of-week entry field | C | "yours to play with", acknowledgement asked | `readme.txt` |

### Sample-code notice with rights reserved - study, do not ship

| Widget | Provides | Lang | Stated in |
|---|---|---|---|
| Designing Custom Controls | `3DFrame`, `3DLine`, `3DText`, `Patterns` | C | `CONTROLS.C` header |
| Custom Controls | `ImageBtn` bitmap push button | C | `IMAGEBTN.C` header |
| List Box Replacement 1.2 | list box replacement | C | `listmgr.c` header |
| Toolbar/Frame Subclass | frame subclassing (not a control) | C | `TOOLBAR.C` header |

### Non-free, or silent

| Widget | Provides | Lang | Status | Stated in |
|---|---|---|---|---|
| SplitPane 1.0 | splitter | C | free programs, binary only; commercial negotiable | `splitpane/license.txt` |
| Extended List Boxes 1.3 | list box extensions | C++ | modify yes, sell derivatives no | `ELISTBOX.HPP` |
| PMDLL 2.12 | `WC_TREE` tree control | C | "may not be sold, hired, leased **or modified**" | `ReadMe.txt` |
| Multi-Column PM | multi-column list box, restricted entry fields | C | no terms anywhere - verified by reading every member | - |
| PMLib | C++ wrappers over stock controls | C++ | no grant; copyright asserted by two parties | `source/*.h` |

**"No terms" is not permission, and it is rarer than it looks.** Only two of these twenty grant
nothing. For the four IBM/Prominare sample packages the notice is a *scope-limited* grant plus an
explicit reservation ("provided to you solely for the purpose of assisting you in the development
of your applications" + "All Rights Reserved") - materially different from silence, and from a
license. PMLib is the sharpest case: no grant at all, and clearing rights would need **two**
holders, Dmitry A. Steklenev and eCo Software `[SRC source/pm_groupbox.h:2-3]`.

---

## 3. Per-widget detail

### 3.1 Permissive

**Cantatore's Libraries 0.1** - `pub/os2/dev/libraries/misc/CantatoreLibs_0-1.zip`
BSD-3-Clause, `Copyright (c) 2016, OS2World` `[SRC LICENSE.txt]`. Nine classes in C across two
DLLs, each with a `Register*` entry point `[SRC 3dctlsdll/*.C, afcpmu00dll/*.C]`:

| DLL | Classes |
|---|---|
| `3dctls.dll` | `WC_3DGROUPBOX`, `WC_STATUSBAR` |
| `afcpmu00.dll` | `WC_BAR`, `WC_COMPLISTBOX`, `WC_EXTLISTBOX`, `WC_MOREBOX`, `WC_EDLGSIMG`, `WC_3DGROUPBOX`, `WC_STATUSBAR` |

`WC_BAR` is a decorative bar - 103 lines handling `WM_CREATE`/`WM_PAINT`/`WM_ADJUSTWINDOWPOS` -
**not** a toolbar `[SRC afcpmu00dll/bar.C]`, a natural misread from the name. The package ships
three `.LIB` files but **no DLL**; the LIBs are 1.5-3.5 KB import libraries, so you can link but
not run until you build.

**One caveat the package does not resolve.** The BSD grant is dated 2016 and held by *OS2World*,
laid over code whose own headers read `Copyright Alessandro Cantatore, 1997-1999`. Section 3.5
records the same author's SplitPane reserving all rights to his work. Whether OS2World had
authority to relicense is not answerable from the package; it is the one open question on the
archive's largest permissive control set.

**DrDialog Controls 0.1.5** - `pub/os2/dev/proglang/rexx/DrDlg_Ctrl_1-5_1-7.zip`
BSD-3-Clause, `Copyright (c) Chris Wohlgemuth 2001-2003` `[SRC drdialog-controls-0_1_5.zip ::
Readme.txt]`. Registers `DRD_PERCENTBAR`, `DRD_BUBBLEHELP`, `DRD_IMAGE` and `DRD_HISTOGRAM`
`[SRC source/drusrctl.c]`; ships the DLL plus 125 KB of C source.

Written as user controls for the DrDialog REXX GUI builder, but they are ordinary PM window
classes registered with `WinRegisterClass` and usable from C. **This is the only permissive
progress bar and the only permissive tooltip in the archive** - the alternatives
(AsuaCtl's `WC_PROGRESSBAR`, the XWorkplace tooltip) are both GPL. Note the license lives in the
readme of a *nested* zip, which is why it is easy to miss.

**PmCtlsPP** - `pub/os2/dev/libraries/GUI/PmCtlsPP_2003-06-01.zip`
BSD-3-Clause, `Copyright (c) 2015, Noller & Breining Software` `[SRC PmCtlsPP/License.txt]`. Not
new classes: it changes stock control behaviour (double-click in an entry field selects one word,
and similar). Ships DLL and LIB.

**Cell Toolkit 0.7b** - `pub/os2/dev/libraries/GUI/Cell_Toolkit_0-7b.zip`
BSD-2-Clause - two clauses, no non-endorsement `[SRC license.txt]`. Split views and toolbars, C++
(`libcell/cell.cpp`), with `simple`, `status`, `multibar` and notebook samples. A Pascal
translation ships separately as `Cell_Toolkit_Pascal_2005-02-16.zip`; there is no C translation.

### 3.2 Copyleft

**Shape Window Library 2.00** - `pub/os2/dev/libraries/graphics/ShapeWindowLibrary_2-00.zip`
LGPL-2.1-or-later, `Copyright (C) 1998-2001 Software Research Associates, Inc.`
`[SRC shapewin.200/README_en.txt:14]`. Registers `ShapeWin` and an internal `ShapeWinRegion`
`[SRC shapewin.200/shapewin.c]`. LGPL, so dynamic linking from a differently-licensed program is
the intended use.

**The LGPL does not cover the whole package.** `README_en.txt:29-30` states the 21 files in
`bitmaps/` are converted from a third party's products *"under his permission"* - a personal
permission to this author, which does not transfer to you. They are most of the package by size.
Redistribute the code, not the artwork.

**AsuaCtl 1.0** - `pub/os2/dev/samples/PM/AsuaCtl_1-0.zip`
**GPL-2.0-only**, and easy to get wrong: the package has **no** `LICENSE` file, so it reads as
unlicensed from a file listing. Every source file and header carries a full notice - *"under the
terms of the GNU General Public License Version 2 as published by the Free Software Foundation"*,
with no "or later" `[SRC src/toolbar.c:1-14, include/asuactl.h:12-25]`. Copyright Wojciech Gazda
and Przemyslaw Dobrowolski, 1999-2001.

The most complete third-party control set in C here: `WC_TOOLBAR`, `WC_STATUS`, `WC_PROGRESSBAR`,
`WC_WINBUTTON`, plus the toolbar's internal `INTC_MINITITLE`, `INTC_ROTATEBTN` and
`INTC_OBJECTPAD` `[SRC src/toolbar.c, src/status.c, src/progbar.c, src/winbutt.c]`. The toolbar is
a real control with a `TM_*` protocol (insert/delete/move/query objects, tooltips, autosize,
rotate), docking and floating via `WM_ADJUSTWINDOWPOS` / `WM_CALCVALIDRECTS` / `WM_OWNERPOSCHANGE`
/ `WM_TRACKFRAME`, and horizontal/vertical rotation.

Three author-stated limits: `TBS_SCROLLABLE` and `TBS_MULTILINE` are declared but marked "not
implemented yet" `[SRC doc/src/toolbar/doc/toolbar.inc, "Window styles"]`;
`TM_CALCNEWRECT`/`TM_QUERYWIDTH`/`TM_QUERYHEIGHT` ignore the rotate button
`[SRC same file, "Known errors"]`; and the progress bar is shipped untested - *"and progress bar
(which is not tested)"* `[SRC readme.txt]`. Documentation is IPF and only the Toolbar and Statusbar
chapters were translated to English, with some missing `[SRC doc/README.txt]`; in-code comments are
Polish `[SRC src/toolbar.c]`. No prebuilt DLL - build from `src/makefile`.

**XWorkplace helpers 0.9.7** - `pub/os2/util/wps/xworkplace/widgets/XWPHelpers_src_0-9-7.zip`
GPL-2.0-only, `Copyright (C) 1997-2000 Ulrich Moeller`, *"in version 2 as it comes in the COPYING
file"* `[SRC XWPH0208.ZIP::src/helpers/cctl_splitwin.c:17-26; XWPH0208.ZIP::COPYING]`. Registers
`WC_SPLITWINDOW`, `COMCTL_TOOLTIP_CLASS`, `WC_XTEXTVIEW` and `WC_SHAPE_WINDOW`
`[SRC XWPH0208.ZIP::src/helpers/cctl_*.c]`.

Despite living under `util/wps/`, these are general-purpose PM controls, not WPS or XCenter
plug-ins - which is what distinguishes this package from XWPWidget below. **It is the archive's
only splitter that is not encumbered** (SplitPane, section 3.5, is non-free), and the source is
inside a nested `XWPH0208.ZIP`, which is why it is easy to miss.

**XWPWidget 0.7.3** - `pub/os2/util/wps/xworkplace/widgets/XWPWidget_wdgt_src_0-7-3.zip`
GPL-2.0-only `[SRC include/*.h]`. These are **XCenter widgets** - plug-ins for the XWorkplace
panel, not controls you can drop into an arbitrary frame. Useful as worked examples of that
plug-in model.

### 3.3 Informal grants

One-sentence permissions in a readme. They are what the author said; none names a license,
disclaims warranty, or addresses modified-source redistribution.

**OS/2 Primecuts** - `pub/os2/dev/samples/PM/OS2Primecuts_2000-08-26.zip`
A numbered **LICENSE** section, not silence `[SRC OS2 Primecuts/OS!2 Primecuts Information.text
section 4]`. You may *"use the sourcecodes supplied for any commercial or noncommercial product"*
and spread the original unmodified archive; you may not redistribute a modified archive under the
Primecuts name or spread unmodified sources in your name. A snippet collection including canvas and
terminal window classes and auto-resizing client controls.

One file dissents: `Time_since_IPL.c:9` reads `(C) Treadstone, 1999. All rights reserved.`, and
`WaveAudioPlayer/ProgressBar.cpp` adds its own *"Feel free to use in whichever way suits you"*. The
package is a collection of contributions and is licensed per-file where a file says so.

**Shaded Buttons** - 0.2 at `pub/os2/dev/samples/PM/ShadedButtons_0-2.zip`, 1.15 at
`pub/os2/dev/libraries/GUI/ShadedButtons_1-15.zip`
Hubert Chan. Gradient-filled push buttons with optional rounded sides, icons and vertical
gradients; 0.2's sample is adapted from Petzold. **Both** releases carry the same grant -
*"Feel free to modify it as you please for your own programs"* - plus *"COST: Free"* and *"Feel
free to upload it to other sites"* `[SRC 0.2 Buttons.TXT; 1.15 HTML_Docs/ShadeBtn.html]`. In 1.15
the terms are in the HTML documentation only, not in the source or headers.

**Language differs between the two releases.** 0.2's `.CPP` file is C - *"Although the file
extension for the source file is .CPP, it's just a normal C file. The only difference is it uses
C++'s '//' comments"* `[SRC Buttons.TXT]`. That does **not** hold for 1.15, whose `shadebtn.cpp:76`
contains `extern "C" {` and is genuinely C++ `[SRC shadebtn.cpp:76]`. 1.15 also needs a `pmcx.h`
that is not in the package.

**DayField** - `pub/os2/dev/libraries/misc/DayField_1989-07-31.zip`
*"if you use this code elsewhere, please at least acknowledge that it came from me, other than
that, its yours to play with"* - Paul Montgomery `[SRC readme.txt]`. A day-of-the-week control
built by subclassing `WC_ENTRYFIELD`, registered through `RegisterDayFieldClass`
`[SRC dayregst.c]`. Ships DLL and LIB. At 1,202 bytes of registration code it is the clearest
minimal example of the custom-control idiom here.

### 3.4 Sample-code notice with rights reserved

Four packages carry the IBM (and, in three cases, Prominare) sample-code notice. It disclaims
warranties, states the code is not part of any IBM product, and limits the grant to one purpose -
the code is *"provided to you solely for the purpose of assisting you in the development of your
applications"* - alongside `Copyright IBM Corp` and `Copyright Prominare Inc. All Rights Reserved`.
Study them; the notice does not grant redistribution.

- **Designing Custom Controls** - `pub/os2/dev/samples/PM/CtrlDes_1993-05-04.zip`. Registers
  `3DFrame`, `3DLine`, `3DText`, `Patterns` from a 55 KB `CONTROLS.C` built as a DLL, plus a driver
  app `[SRC CONTROLS.C, DRIVER.C]`. Companion to a Spring 1993 *OS/2 Developer* article of the same
  name by Matt Smith (Prominare) and Mark Benge (IBM) `[SRC README.TXT]`. The best-explained
  custom-control example in the archive.
- **Custom Controls** - `pub/os2/dev/samples/PM/CustomControls_1993-05-04.zip`. An `ImageBtn`
  bitmap push button, 74 KB of C, built as a DLL with a testbed `[SRC IMAGEBTN.C, TESTBED.C]`.
- **List Box Replacement 1.2** - `pub/os2/dev/samples/PM/ListBoxReplacement_1-2.zip`. A list box
  replacement with entry field and sound `[SRC ListBox.C, listmgr.c, Driver.C]`; terms in
  `listmgr.c`, documentation in `README.NOW`.
- **Toolbar/Frame Subclass** - `pub/os2/dev/samples/PM/ToolBarFrmSub_1992-10-07.zip`. Despite the
  name this is **not** a toolbar control: it is the frame-subclassing technique for placing a bar
  in a frame, and the only class it registers is the app's own client window
  `[SRC TOOLBAR.C:88]`. The right reference for frame integration, the wrong one for a toolbar.

### 3.5 Non-free, or silent

- **SplitPane 1.0** - `pub/os2/dev/samples/PM/SplitPane_1-0.zip`. *"This is beta code and it still
  lacks a real software license."* Until then: copyright Alessandro Felice Cantatore; use for
  experimental purposes or in free programs **in binary format only**; commercial including
  shareware negotiable `[SRC splitpane/license.txt]`. Source redistribution is not granted. For a
  usable splitter see the XWorkplace helpers (section 3.2).
- **Extended List Boxes 1.3** - `pub/os2/dev/samples/PM/ExtendedListBoxes_1-3.zip`. `(C) Copyright
  Stephen B. Behman, 1993 -- All Rights Reserved`. You **may** modify and extend it; you may not
  sell derivative works without permission. The header adds *"It is not intended that this code be
  put into the Public Domain NOW, when the code is finished it will be"* - an intent never acted on
  `[SRC ELISTBOX.HPP:13-18]`. C++.
- **PMDLL 2.12** - `pub/os2/util/system/PMDLL_2-12.zip`. Registers `WC_TREE` and `WC_MAIN`
  `[SRC source.zip::pmdll.c]`, but the terms forbid the thing you would want it for: *"can be
  considered freeware, this utility may not be sold, hired, leased **or modified**, it may be
  freely copied as a complete package"* `[SRC ReadMe.txt]`. Sources also carry
  `Copyright Steven Levine and Associates` / `Arthur Van Beek. All rights reserved`.
- **Multi-Column PM** - `pub/os2/dev/samples/PM/Multi-ColPM_1993-05-27.zip`. A multi-column list
  box that avoids a monospaced font, plus restricted-input entry fields `[SRC LISTBX.C, EDIT.C]`.
  Genuinely silent: every member was read and nothing bearing on rights appears.
- **PMLib** - `pub/os2/dev/libraries/GUI/PMLib_2012-08-03.zip`. A large C++ library wrapping the
  stock controls (`pm_button`, `pm_checkbox`, `pm_container`, ...) rather than adding classes.
  Copyright notices span 2000-2012 across two holders, Dmitry A. Steklenev and eCo Software
  `[SRC source/pm_window.cpp:1-5, source/pm_groupbox.h:2-3]`, with no grant anywhere.

### 3.6 The `.CPP` extension proves nothing

Shaded Buttons 0.2 ships `.CPP` files its author states are C `[SRC Buttons.TXT]`; Shaded Buttons
1.15 ships a `.cpp` that really is C++ `[SRC shadebtn.cpp:76]`. Do not filter this archive by
extension when looking for C. The Lang column above records what each file *is*.

---

## 4. What is not in this list, and what may still be missing

- **Binary-only control packs.** `pub/os2/dev/tools/toolkits/HWOS2DevCollection_1997-06-29.zip`
  advertises 3D static text, a toolbar, a status bar and bubble help. The package holds six files -
  `INSTALL.EXE`, two `.DAT`, `README.1ST`, `HWIDEV.TXT`, `FILE_ID.DIZ` - and no source. Terms are
  stated: *"The OS/2 Developer Collection is Shareware. Registered users will receive full source
  code of everything"* `[SRC HWIDEV.TXT]`.
- **Teaching samples that register a class without offering a reusable control.** The Petzold and
  *Art of OS/2 Programming* book trees are the archive's largest source of registration examples,
  and IBM's `OS290` courseware adds more (`WC_CHART`, `WC_BOUNCE`)
  `[SRC pub/os2/info/courseware/OS290-v2_90-OS2WProgramming-rel1.zip]`. They teach the idiom rather
  than supply a widget. See `sources.md` section 3b for the Petzold text.
- **Controls embedded in applications.** Several are worth reading - FleetStreet's
  `WC_COLORWHEEL`/`WC_COLORSELECT`, KIME's Hangul list box, an editor's 404-line `WC_TOOL` toolbar
  class - but lifting one inherits the whole application's licensing question, and these
  applications bundle third-party code under further terms of its own.
- **One archive that cannot be opened.** `pub/os2/dev/libraries/misc/OOL_1-0fix1.zip` (1.7 MB, an
  OS/2 object library) has a damaged central directory: both `unzip` and Python refuse it. Its
  source is recoverable by scanning raw local file headers, and it does register a class, but its
  license could not be established by any method tried, so it is listed here rather than above
  `[OBS-RE]`.

**Coverage.** This survey searched all 11,350 archives, including source shipped inside nested
`.zip` members - the common "binaries + `source.zip`" layout, which hides roughly half the
archive's PM source from a top-level scan. 440 archives register or subclass a PM window class;
406 register one; 331 do so from C `[OBS-RE]`. Those are counts of *archives containing the call*,
not of widget libraries - every PM application registers its client window, so the call is a
starting point, not a verdict. The twenty packages above are what survived reading them.

---

## See also
- `pm-controls.md` - IBM's own 15 control classes, their messages and notifications. Read it first:
  much of what a third-party widget is reached for can be had from `WC_CONTAINER`, `WC_VALUESET` or
  an owner-drawn `WC_BUTTON`.
- `pm-window-messaging.md` - `WinRegisterClass`, `WinSubclassWindow`, `WinDefWindowProc` and the
  window-procedure model every control above is built on. If nothing here is licensed the way you
  need, this is what you write your own against.
- `module-dll.md` - packaging a control as a DLL with a `Register*` entry point, the shape the
  redistributable ones use.
- `sources.md` - where the Hobbes archive lives, and its rights caveat: circulating through a
  community archive is not itself a license.
