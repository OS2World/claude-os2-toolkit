# OS/2 Presentation Manager - Resources and Dialogs

How a Presentation Manager (PM) application keeps its user-interface description *outside* its
code - in **resources** compiled into a module - and how it builds interactive **dialogs** from
those resources. A resource is a typed, numbered, read-only object (a menu, a dialog template, a
string, an accelerator table, an icon, a bitmap) bound into an executable or DLL by the resource
compiler and loaded on demand by handle-plus-id. A dialog is a frame window whose child controls
are described by a **dialog-template** resource and driven by a **dialog procedure**. This
reference covers the resource model and its binary formats, the dialog manager (`WinLoadDlg` /
`WinDlgBox` / `WinProcessDlg` / `WinDismissDlg` and the dialog procedure), the string / pointer /
bitmap loaders, and the menu and accelerator subsystems that turn user gestures into
`WM_COMMAND` messages.

Provenance: **[DOC-IBM]** the version-correct OS/2 Toolkit headers `pmwin.h`, `os2def.h`,
`pmgpi.h`, and `bsedos.h` (every prototype, structure, constant value, and message id below is
transcribed from them, cited `file:line`); **[DOC-IBM]** the IBM OS/2 Presentation Manager
Programming Reference (extracted book text `pm2.txt` = the `Win*` function reference, `pm4.txt` =
the data-type reference) for API semantics and structure-field meaning. Where a value comes from
a header and its meaning from the book, both are cited. Resource-script (`.RC`) statement grammar
beyond what the opened sources confirm is marked **[unverified]** rather than originated.

The window/message model these APIs sit on - the anchor block, the message queue, the window
procedure, `MPARAM`/`MRESULT` packing, and the core `WM_*` set - is in `pm-window-messaging.md`
and is assumed here.

---

## 1. The resource model [DOC-IBM]

An application's fixed UI data is not compiled into its code; it is authored in a **resource
script** (a `.RC` file), compiled by the resource compiler, and bound into a module - either the
application's own `.EXE` or a separate `.DLL`. Each resource has:

- a **type** - one of the `RT_*` resource types (Section 2);
- an **integer id** - in the range `0`-`0xFFFF` (the loaders document this bound repeatedly, e.g.
  "must be greater or equal to 0 and less or equal to 0xFFFF" for menu, dialog, string, pointer,
  and accelerator ids) [DOC-IBM - PM Reference, `pm2.txt` WinLoadMenu/WinLoadString/...].

A resource is loaded at run time by naming **the module that holds it** and **the id within that
module**. Every resource loader takes an `HMODULE` argument for the module, and by convention
`NULLHANDLE` means *this application's own `.EXE`*, while any other value is a module handle
returned by `DosLoadModule` / `DosQueryModuleHandle` referencing a DLL that contains the resource
[DOC-IBM - PM Reference, `pm2.txt` WinLoadString/WinLoadDlg/WinLoadMenu/WinLoadPointer/WinLoadAccelTable].

| Loader | Loads | Section |
|---|---|---|
| `WinLoadString` / `WinLoadMessage` | A string-table string | 10 |
| `WinLoadPointer` | A mouse pointer / icon | 10 |
| `WinLoadMenu` | A menu template -> a menu window | 8 |
| `WinLoadDlg` / `WinDlgBox` | A dialog template -> a dialog window | 4 |
| `WinLoadAccelTable` | An accelerator table | 9 |
| `GpiLoadBitmap` | A bitmap | 10 |

A resource that is *referenced by another resource* - for example an icon named by an icon static
control inside a dialog template - is always sought in the **`.EXE`**, never in the DLL the
template was loaded from; to keep such secondary resources in a DLL, the application must load them
itself with an explicit call during `WM_INITDLG` [DOC-IBM - PM Reference, `pm2.txt:16179`
WinLoadDlg Remarks].

---

## 2. Resource types and their binary formats [DOC-IBM]

Every resource carries a numeric **type**. The OS/2 resource types are [DOC-IBM `bsedos.h:2246-2272`]:

| `RT_*` constant | Value | Resource | Compiled binary form |
|---|---|---|---|
| `RT_POINTER` | `1` | Mouse-pointer / icon shape | (bitmap-based) -> `WinLoadPointer` |
| `RT_BITMAP` | `2` | Bitmap | bitmap -> `GpiLoadBitmap` |
| `RT_MENU` | `3` | Menu template | `MENUITEM` hierarchy (Section 8) -> `WinLoadMenu` |
| `RT_DIALOG` | `4` | Dialog template | `DLGTEMPLATE` / `DLGTITEM` (Section 3) -> `WinLoadDlg` |
| `RT_STRING` | `5` | String tables | length-prefixed strings -> `WinLoadString` |
| `RT_FONTDIR` | `6` | Font directory | - |
| `RT_FONT` | `7` | Font | - |
| `RT_ACCELTABLE` | `8` | Accelerator tables | `ACCELTABLE` / `ACCEL` (Section 9) -> `WinLoadAccelTable` |
| `RT_RCDATA` | `9` | Binary (application-defined) data | raw bytes |
| `RT_MESSAGE` | `10` | Error-message tables | -> `WinLoadMessage` |
| `RT_DLGINCLUDE` | `11` | Dialog include-file name | (build-time) |
| `RT_VKEYTBL` ... `RT_FD` | `12`-`21` | Key/character/font-driver tables | (system) |
| `RT_RESNAMES` | `255` | Resource-names table | (system) |

`RT_MAX` (`22`) is the first unused type [DOC-IBM `bsedos.h:2271`].

The dialog-template, accelerator-table, and menu-template resources are the ones whose **binary
layout is a documented public structure** - the same headers define the very structs the compiler
emits, because a template may be passed to PM in memory as well as bound as a resource. The
`DLGTITEM`/`DLGTEMPLATE` and `ACCELTABLE`/`ACCEL` structures are explicitly `#pragma pack(2)` so
"the structures are identical in the 32-bit and 16-bit worlds ... because it has been documented
that one can pass a pointer to 'the binary resource format' when calling `WinCreateDlg`" [DOC-IBM
`pmwin.h:1867-1876`].

### The binary resource file - `.RES` [DOC-IBM `pm5.txt` "Resource (.RES) File Specification"]

The resource compiler (`RC`) compiles a resource script into a **binary resource file** (`.RES`),
which it - or a later `rc file.res exe` - adds to an executable [DOC-IBM `pm5.txt` "Creating and
Compiling a Resource File"]. Its format is a plain sequence, no header and no index:

```
(/TYPE NAME FLAGS SIZE BYTES/)+
```

| field | form |
|---|---|
| `TYPE` | a NUL-terminated string, **or** an ordinal: the byte `0xFF` then an `INT` - the `RT_*` value |
| `NAME` | the same form as `TYPE`; there are no predefined names |
| `FLAGS` | "an unsigned value containing the memory manager flags" - `NSMOVE` `0x0010`, `NSPURE` `0x0020`, `NSPRELOAD` `0x0040`, `NSDISCARD` `0x1000`, and the rest of the NE segment flags |
| `SIZE` | a `LONG`: the number of bytes that follow |
| `BYTES` | the resource itself |

"Any number of resources can appear one after another in the .RES file." [DOC-IBM `pm5.txt`.]
**The widths IBM's text does not state** - of the ordinal `INT` and of `FLAGS` - are **16 bits each**
by observation [OBS]: a one-entry `RCDATA 1` script compiled by Open Watcom's resource compiler in
its "Microsoft/IBM format" mode (`wrc -zm -bt=os2`; without `-zm` it writes a container of its own,
not this format) gives `FF 09 00  FF 01 00  30 00  08 00 00 00` then the eight data bytes - type 9,
name 1, flags `0x0030` (`NSMOVE|NSPURE`), size 8. IBM's own `RC.EXE` output was not captured.

### `DosGetResource` / `DosFreeResource` - what is counted `[OBS]`

Measured on WSeB 4.50 with an `RCDATA` resource of a DLL. `DosGetResource` returns the same address
each time (a shared-arena object of its own) and counts the gets **per process** - measured with two
processes: a child freeing the address its parent got, with no get of its own, gets 487 while the
parent's own free still succeeds - and after two gets,
two `DosFreeResource` calls return 0 - an address anywhere inside the resource counts as the resource
- and a third returns **487** `ERROR_INVALID_ADDRESS`. A resource still held when its DLL is freed
also gives 487 afterwards. `DosQueryProcAddr` on the caller's own EXE handle returns 6, and
`DosGetResource` on it, for an EXE with no resources, 87. For an address that is no resource: `NULL`, a static or a stack address
**87**; a code address, or one in no allocated object, **1**. The reference lists only 0 and 5 for
`DosFreeResource` [DOC-IBM `cp1.txt`]; 5 was not seen. A `ppb` that cannot be written (`NULL`)
is not an error return from `DosGetResource`: the caller ends with exception 5 (an access
violation; `SYS1808`) - a bad module handle is still 126 first `[OBS]` (measured, WSeB 4.50
revision 14.089 SMP).

**Resource-script statements.** The `.RC` source names each resource with a statement whose
keyword corresponds to the type - the dialog-template body is authored with a **`DIALOG`**
statement [DOC-IBM - PM Reference, `pm2.txt:16163` WinLoadDlg Remarks, which refers to "the
`DIALOG` statement within the dialog template"]. The other statement keywords conventionally used
(`MENU`, `SUBMENU`, `MENUITEM`, `STRINGTABLE`, `ACCELTABLE`, `ICON`, `POINTER`, `BITMAP`,
`PRESPARAMS`, `DLGTEMPLATE`, `WINDOWTEMPLATE`) belong to the Resource Compiler reference, which is
not among the `.INF` books; the *binary results* they produce (the `RT_*` types and the structures
in this document) are fully sourced.

### 2.1 A verified minimal `.RC` [OBS-RE]

The statements below were **compiled and run**, so the syntax is confirmed even though the
Resource Compiler reference was unavailable: `wrc` accepted this file, `WinCreateStdWindow`
(`FCF_MENU`) loaded the menu, `WinDlgBox` loaded the dialog, and `WinLoadString` read the string.

```rc
#include <os2.h>
#include "res.h"

MENU ID_MAINWIN
BEGIN
    SUBMENU "~File", IDM_FILE
    BEGIN
        MENUITEM "~Open...",  IDM_OPEN
        MENUITEM SEPARATOR
        MENUITEM "E~xit",     IDM_EXIT
    END
    SUBMENU "~Help", IDM_HELP
    BEGIN
        MENUITEM "~About...", IDM_ABOUT
    END
END

DLGTEMPLATE ID_ABOUTDLG
BEGIN
    DIALOG "About", ID_ABOUTDLG, 40, 40, 200, 80, , FCF_TITLEBAR | FCF_SYSMENU
    BEGIN
        CTEXT           "Resources loaded from a .RC", -1, 5, 52, 190, 10
        CTEXT           "menu + dialog + stringtable", -1, 5, 40, 190, 10
        DEFPUSHBUTTON   "OK", DID_OK, 75, 12, 50, 14
    END
END

STRINGTABLE
BEGIN
    IDS_TITLE   "Loaded from STRINGTABLE"
END
```

Points that are easy to get wrong:

- **`DLGTEMPLATE` wraps `DIALOG`.** The outer `DLGTEMPLATE <id>` names the resource; the inner
  `DIALOG` statement carries the text, id, position, size, and frame flags. Controls go in the
  `DIALOG`'s own `BEGIN`/`END`.
- **The empty parameter before the frame flags is required** - `DIALOG "About", id, x, y, cx, cy,
  , FCF_TITLEBAR | FCF_SYSMENU` - the omitted slot is the window style.
- **`~` marks the mnemonic** (`"~File"` -> Alt+F), where a Windows `.RC` uses `&` - **in menu
  items and in buttons**. It does **not** work in static text. `SS_TEXT` formats its text with
  only `DT_LEFT`/`DT_CENTER`/`DT_RIGHT`, one of `DT_TOP`/`DT_VCENTER`/`DT_BOTTOM`, and optionally
  `DT_WORDBREAK` - `DT_MNEMONIC` is not among them - and a static control's `WM_MATCHMNEMONIC`
  default processing "takes no action on this message, other than to set `rc` to FALSE"
  [DOC-IBM - `pm3.txt` "Static Control Styles" and "WM_MATCHMNEMONIC (in Static Controls) -
  Default Processing"]. A `~` left in an `LTEXT` is therefore **drawn literally**: converting
  Win32's `"Search Strin&g:"` mechanically yields a label reading `Search strin~g:` on screen.
  IBM's own workaround, in the same section: *"For 'static' text that can be selected, a Button
  Control with a style of `BS_NOBORDER` can be used."* [OBS-RE - confirmed on screen porting
  Notepad2's Find dialog; the tilde rendered in the label while the neighbouring checkboxes and
  push buttons underlined theirs correctly.]
- **A duplicated mnemonic is not an error and not a cycle - the second item just never fires.**
  An alphabetic key "selects the **first** menu item with the specified character as its mnemonic
  key" [DOC-IBM - `pmv2base.txt`, menu keyboard behaviour], and IBM's CUA guidance is to "assign a
  unique mnemonic to each ... choice ... unless no unique mnemonic can be found". Neither `wrc` nor the
  compiler checks this, and a converted Windows menu inherits whatever `&` placement the original
  had - so a menu that gains items during a port can silently acquire a dead one. Read each menu's
  mnemonics as a set after converting it - `check-mnemonics.py` does exactly that
  and exits non-zero on a duplicate. [OBS-RE - `Cu~t` and `Insert HTML/XML ~Tag` both claimed T in
  Notepad2's Edit menu after the Lines submenu was added; a later batch produced six at once.]
- **Dialog coordinates are dialog units with a bottom-left origin**, like everything else in PM:
  the `DEFPUSHBUTTON` at `y=12` sits near the *bottom* of an 80-unit-tall dialog.
- **`FCF_MENU` loads the menu automatically** - `WinCreateStdWindow` looks for a `MENU` resource
  whose id equals the window id passed as its second-to-last argument. No explicit `WinLoadMenu`.
- **`wrc` does not inherit the compiler's include path.** `#include <os2.h>` fails with
  `E062: Unable to open 'os2.h'` unless you pass `-i=` (see `recipes/build-pm-app.md`).
- **Prefer `CONTROL` with an explicit `WC_*` class over the shorthand statements for anything
  beyond text and buttons.** OpenWatcom's `wrc` compiles resources for *both* Windows and OS/2, and
  a bare `COMBOBOX` statement compiled without error but produced a template PM refused at
  `WinDlgBox` time - `DID_ERROR` (`0xFFFF`) with `WinGetLastError` = `PMERR_INVALID_HWND`
  (`0x1001`). The generic form works:
  ```rc
  CONTROL "", IDC_COMBO, 85, 78, 145, 60, WC_COMBOBOX,
          CBS_DROPDOWNLIST | WS_VISIBLE | WS_TABSTOP
  ```
  `LTEXT`, `CTEXT`, `ENTRYFIELD`, `DEFPUSHBUTTON`, `PUSHBUTTON` and `AUTOCHECKBOX` were all fine
  as shorthand - six `AUTOCHECKBOX`es loaded and toggled correctly in the same dialog whose
  `COMBOBOX` shorthand had to become `CONTROL`/`WC_COMBOBOX`. The split is not "shorthand is
  unreliable"; it is that the *composite* controls are.
  [OBS-RE - porting Notepad2's word-wrap settings and Find/Replace dialogs.]
- **A combo box's `cy` covers the entry field *plus* the dropped-down list**, so the entry field
  renders at the TOP of the control rectangle. Place each combo well below its label if you want
  them to line up.

### Presentation parameters - `PRESPARAMS` [DOC-IBM `pmwin.h:3132-3147`]

A control or window may carry **presentation parameters** - appearance attributes such as colors
and fonts, keyed by id - supplied inline in a template or set with `WinSetPresParam`:

```c
typedef struct _PARAM {        /* param */
    ULONG   id;                /* PP_* attribute id            */
    ULONG   cb;                /* size of the value in ab      */
    BYTE    ab[1];             /* the value                    */
} PARAM;

typedef struct _PRESPARAMS {   /* pres */
    ULONG   cb;                /* total size                   */
    PARAM   aparam[1];         /* array of PARAM               */
} PRESPARAMS;
```

---

## 3. The dialog template - `DLGTEMPLATE` / `DLGTITEM` [DOC-IBM]

A dialog-template resource is a `DLGTEMPLATE` header followed by an array of `DLGTITEM` records,
one per control (the frame dialog itself is the first item, its children follow). Strings,
presentation parameters, and class names referenced by an item are stored elsewhere in the
resource and reached by **byte offsets** from the template - which is why the record fields are
offsets/lengths rather than pointers. Both structures are `#pragma pack(2)` [DOC-IBM
`pmwin.h:1867`].

### `DLGTEMPLATE` [DOC-IBM `pmwin.h:1907-1917`]

```c
typedef struct _DLGTEMPLATE {  /* dlgt */
    USHORT   cbTemplate;       /* total size of the template, in bytes        */
    USHORT   type;             /* template type                               */
    USHORT   codepage;         /* code page of the template's text - should
                                  match the *queue* code page; see below       */
    USHORT   offadlgti;        /* offset to the DLGTITEM array                 */
    USHORT   fsTemplateStatus; /* template status flags                       */
    USHORT   iItemFocus;       /* index of the item to receive initial focus  */
    USHORT   coffPresParams;   /* count/offset of presentation parameters     */
    DLGTITEM adlgti[1];        /* the item array (dialog + its controls)       */
} DLGTEMPLATE;
```

> **`codepage` - match it to the message queue** [DOC-IBM - `pm5.txt`, section "Code Pages"]. This field
> declares the code page of the template's text. IBM's rule: "the code page of a resource (for
> example, a menu or dialog box) should match the code page of the queue" (`WinSetCp`/`WinQueryCp`),
> and "code page 850 is the best choice for both an application and its resources." A mismatch is
> silent - the dialog renders with wrong glyphs rather than failing. A PM process has three
> independent code-page scopes (process / queue / GPI); see `unicode-conversion.md` section 9.1.

### Resizable dialogs [OBS-RE]

A PM dialog does **not** reflow. Add `FCF_SIZEBORDER` and the user can drag the border, but every
control stays exactly where the template put it, so the dialog must lay itself out. Four things make
the obvious implementation wrong, and the first is the one that wastes a day.

**1. A dialog is never sent `WM_SIZE`.** Hanging the layout off `WM_SIZE` means it never runs at
all. A message trace of a dialog through a full resize drag shows `WM_ADJUSTWINDOWPOS`,
`WM_WINDOWPOSCHANGED`, `WM_FORMATFRAME` and `WM_PAINT`, repeating per mouse-move - and no `WM_SIZE`.

The books do say the default window procedure turns `SWP_SIZE` into a `WM_SIZE` [DOC-IBM -
`pm3.txt`, *WM_WINDOWPOSCHANGED - Default Processing*], and that is true of **`WinDefWindowProc`**.
A dialog runs **`WinDefDlgProc`**, which does not. Handle `WM_WINDOWPOSCHANGED`; handling `WM_SIZE`
as well costs nothing.

**2. Do not swallow the message.** A dialog *is* a frame window, and "the frame control window
procedure responds to this message by sending a `WM_FORMATFRAME` message to itself" [DOC-IBM -
`pm3.txt`, *WM_SIZE (in Frame Controls) - Default Processing*]. `WM_FORMATFRAME` is what positions
the frame's own controls - **the title bar and the sizing border among them**. A handler that
returns `0` instead of calling `WinDefDlgProc` suppresses the frame's entire layout, and the symptom
is not subtle: the window loses its border, stops being resizable, and its buttons vanish. Call the
default procedure **first**, then position your own controls on the geometry it settled on.

**3. Anchor by MARGIN, not by delta.** Record each control's distance to each dialog edge once, in
`WM_INITDLG`, then recompute absolute positions from those margins on every resize:

```c
/* captured once: l = swp.x, b = swp.y,
                  r = dlgCx - (swp.x + swp.cx), t = dlgCy - (swp.y + swp.cy) */
if (anchoredLeft && anchoredRight) { x = l; cx = dlgCx - l - r; }   /* stretches */
else if (anchoredRight)            { cx = keptWidth; x = dlgCx - r - cx; }  /* rides */
/* vertical is the same, but bottom-left origin means the TOP anchor is the high edge */
```

This is idempotent - it lands in the same place however many messages were missed or in what order -
and it sidesteps the dialog-units problem entirely, because the margins are measured from live
`WinQueryWindowPos` values in pels and the template's own numbers are never read. (The template is
in **dialog units**; `WinSetWindowPos` takes **pels**. `WinMapDlgPoints` converts if you need them.)

A delta-based version - track the last size, apply the difference - looks simpler and is not: it
accumulates state across messages, and one missed or re-baselined event corrupts every position
after it.

**4. Move everything in one `WinSetMultWindowPos`.** Positioned one at a time, controls lay out and
repaint in sequence, so a drag shows each one briefly against the others' old positions - labels and
borders visibly jumping before they settle. The batch call applies the layout as a unit; that is what
it is for [DOC-IBM - `pm2.txt`, *WinSetMultWindowPos*]. Skip the layout when only the position
changed: `WM_WINDOWPOSCHANGED` fires per mouse-move while the title bar is dragged, and the margins
would produce the same answer.

Finally, put **`WS_CLIPCHILDREN` in the `DIALOG` statement's window-style field** - the field left
blank on fixed-size dialogs, between the size and the `FCF_*` flags:

```
DIALOG "Browse", IDD_BROWSE, 20, 20, 360, 220, WS_CLIPCHILDREN, FCF_TITLEBAR | FCF_SYSMENU | FCF_SIZEBORDER
```

Without it the dialog paints its background over the controls during the resize repaint. Moving a
control also repaints neither what it uncovered nor what it landed on, so finish with
`WinInvalidateRect` plus whatever the control needs to re-flow its own contents - a `WC_CONTAINER`
wants `CM_INVALIDATERECORD` with `CMA_ERASE | CMA_REPOSITION` or its records keep the old columns.

### `DLGTITEM` - one control [DOC-IBM `pmwin.h:1882-1898`]

```c
typedef struct _DLGTITEM {     /* dlgti */
    USHORT  fsItemStatus;      /* item status flags                           */
    USHORT  cChildren;         /* number of child items of this item          */
    USHORT  cchClassName;      /* length of the class name                    */
    USHORT  offClassName;      /* offset to the class name string             */
    USHORT  cchText;           /* length of the item text                     */
    USHORT  offText;           /* offset to the item text string              */
    ULONG   flStyle;           /* window style (WS_* / class-specific)        */
    SHORT   x;                 /* position, in dialog coordinates             */
    SHORT   y;
    SHORT   cx;                /* size, in dialog coordinates                 */
    SHORT   cy;
    USHORT  id;                /* control id (used with WinWindowFromID etc.) */
    USHORT  offPresParams;     /* offset to this item's PRESPARAMS            */
    USHORT  offCtlData;        /* offset to class-specific control data       */
} DLGTITEM;
```

The class of each control is given by `offClassName`/`cchClassName` - either a system control
class (`WC_BUTTON`, `WC_ENTRYFIELD`, `WC_STATIC`, `WC_LISTBOX`, ... - see `pm-window-messaging.md`
section 4) or an application class name - and its `id` is what the dialog procedure and
`WinSendDlgItemMsg` use to address it. Positions and sizes are in **dialog coordinates** (the
mapping to window pixels is done with `WinMapDlgPoints`, `pmwin.h:1832-1835`).

---

## 4. Loading and running dialogs [DOC-IBM]

A dialog can be run **modally** (the caller blocks and the user must dismiss it before continuing)
or **modeless** (it coexists with the application's other windows). The dialog manager provides
both.

| Symbol | Prototype (from `pmwin.h`) | Purpose |
|---|---|---|
| `WinLoadDlg` | `HWND WinLoadDlg(HWND hwndParent, HWND hwndOwner, PFNWP pfnDlgProc, HMODULE hmod, ULONG idDlg, PVOID pCreateParams)` | Create a dialog window from template `idDlg` in `hmod`; returns the dialog handle. Returns immediately (the caller runs the loop). [`pmwin.h:1571-1576`] |
| `WinCreateDlg` | `HWND WinCreateDlg(HWND hwndParent, HWND hwndOwner, PFNWP pfnDlgProc, PDLGTEMPLATE pdlgt, PVOID pCreateParams)` | Same, but from an **in-memory** `DLGTEMPLATE` rather than a resource id. [`pmwin.h:1922-1926`] |
| `WinDlgBox` | `ULONG WinDlgBox(HWND hwndParent, HWND hwndOwner, PFNWP pfnDlgProc, HMODULE hmod, ULONG idDlg, PVOID pCreateParams)` | Load, run **modally**, and destroy a dialog in one call; returns the `WinDismissDlg` result. [`pmwin.h:1577-1582`] |
| `WinProcessDlg` | `ULONG WinProcessDlg(HWND hwndDlg)` | Run the modal message loop for an already-loaded dialog; returns the dismiss result. [`pmwin.h:1826`] |
| `WinGetDlgMsg` | `BOOL WinGetDlgMsg(HWND hwndDlg, PQMSG pqmsg)` | Message-loop helper for a **modeless** dialog. [`pmwin.h:1568-1569`] |
| `WinDismissDlg` | `BOOL WinDismissDlg(HWND hwndDlg, ULONG usResult)` | End a modal dialog, making `WinProcessDlg`/`WinDlgBox` return `usResult`. [`pmwin.h:1584-1585`] |
| `WinDefDlgProc` | `MRESULT WinDefDlgProc(HWND hwndDlg, ULONG msg, MPARAM mp1, MPARAM mp2)` | Default dialog-message handling (the dialog analogue of `WinDefWindowProc`). [`pmwin.h:1618-1621`] |

### Parameters shared by the loaders [DOC-IBM - PM Reference, `pm2.txt` WinLoadDlg/WinDlgBox]

- **`hwndParent`** - the dialog's parent (usually `HWND_DESKTOP` for a top-level dialog, or
  `HWND_OBJECT` for an object-window dialog) [`pm2.txt:16054`].
- **`hwndOwner`** - the *requested* owner. The manager recalculates the actual owner: it walks up
  the parent chain from `hwndOwner` until it finds a child of `hwndParent`; that window becomes the
  owner, or the owner is set to `NULLHANDLE` if none is found. This adjustment is what makes a
  later modal `WinProcessDlg` disable the right window [`pm2.txt:16165`].
- **`pfnDlgProc`** - the dialog procedure (Section 5).
- **`hmod` / `idDlg`** - the module (`NULLHANDLE` = the application `.EXE`) and template id; `idDlg`
  is also used as the created dialog window's id and must be `0`-`0xFFFF` [`pm2.txt:16078-16093`,
  `pm2.txt:7870-7873`].
- **`pCreateParams`** - an application pointer handed to the dialog procedure in `WM_INITDLG`'s
  `mp2`; it "MUST be a pointer rather than a long" [`pm2.txt:16095-16102`].

### Visibility and creation semantics [DOC-IBM `pm2.txt:16162-16185` WinLoadDlg Remarks]

Unless the template's `DIALOG` statement gives the dialog `WS_VISIBLE`, the dialog is created
**invisible** - which is preferred, because it lets an experienced user "type ahead" and lets PM
optimize (a dialog dismissed by type-ahead need never be shown). `WinProcessDlg` does not show the
dialog while `WM_CHAR` messages remain in the queue; it shows it only when the input queue is
empty. `WinLoadDlg` sends `WM_INITDLG` to the dialog procedure **before it returns**, and - because
each child is created during the call - the dialog procedure may receive control notifications
before `WinLoadDlg` returns. Child text is passed through `WinSubstituteStrings`, so `%`
substitution strings in control text are expanded (upper limit 256 characters after substitution).

### The modal contract [DOC-IBM]

`WinDlgBox` is exactly [DOC-IBM `pm2.txt:7894-7899`]:

```c
WinLoadDlg(...);          /* create (invisible) */
WinProcessDlg(dlg);       /* run modally until dismissed */
WinDestroyWindow(dlg);    /* destroy */
return result;            /* the WinDismissDlg value */
```

`WinProcessDlg` **disables the owner window** (and its descendants) on entry, dispatches queue
messages to the appropriate window/dialog procedure until `WinDismissDlg` is called, then returns
the dismiss value; `WinDismissDlg` re-enables the disabled owner and **hides** the dialog without
destroying it [DOC-IBM `pm2.txt:20652-20663`, `pm2.txt:7583-7594`]. A `WM_QUIT` encountered before
dismissal makes `WinProcessDlg` issue `WinDismissDlg` itself and re-post `WM_QUIT` so the
application's main loop still terminates normally [DOC-IBM `pm2.txt:20655`]. If the dialog has no
owner it behaves *modeless-ly* even under `WinProcessDlg` [DOC-IBM `pm2.txt:20663`].

`WinDismissDlg` is normally called by the dialog procedure, **or implicitly** when the dialog
procedure passes a `WM_COMMAND` to `WinDefDlgProc` (`WinDefDlgProc` also calls it on `WM_CLOSE`)
[DOC-IBM `pm2.txt:7584`, `pm2.txt:5957`]. A dialog loaded with `WinLoadDlg` (not `WinDlgBox`) must
be destroyed by the application with `WinDestroyWindow` [DOC-IBM `pm2.txt:7590`].

### The modeless contract [DOC-IBM + OBS-RE]

A modeless dialog is `WinLoadDlg` **without** the `WinProcessDlg`. Two practical consequences,
both of which bite a Win32 port:

- **PM needs no `IsDialogMessage` equivalent.** In Win32 a modeless dialog only works because the
  application's message loop hands every message to `IsDialogMessage` first, and forgetting that
  call is the classic "my modeless dialog ignores Tab and Enter" bug. In PM the dialog is an
  ordinary window in the same message queue: a plain `WinGetMsg` / `WinDispatchMsg` loop delivers
  to it, and `WinDefDlgProc` supplies the tabbing, the default-button and the Esc-cancels
  behaviour. `WinGetDlgMsg` exists for a dialog that wants to run its *own* loop; it is not
  required to make an ordinary loop work. [OBS-RE - Notepad2's Find/Replace dialog, verified with
  Tab moving between combo boxes, Enter firing the default button and Esc closing.]
- **`WinDismissDlg` hides; it does not destroy.** Reusing the handle to "switch" a Find dialog to a
  Replace dialog therefore leaks a window per toggle. Destroy with `WinDestroyWindow` and reload,
  or keep both dialogs alive deliberately.

Because the dialog is created invisible unless the template says `WS_VISIBLE`, the `WinShowWindow`
after `WinLoadDlg` is **required**, not cosmetic - the one line whose absence produces a dialog
that "did not open" while every control in it exists and works.

### Standard item ids [DOC-IBM `pmwin.h:1626-1628`]

The values conventionally passed to `WinDismissDlg` and returned by `WinDlgBox`/`WinProcessDlg`:

| Constant | Value | Meaning |
|---|---|---|
| `DID_OK` | `1` | The dialog was accepted (OK / Enter). |
| `DID_CANCEL` | `2` | The dialog was cancelled. |
| `DID_ERROR` | `0xffff` | An error occurred creating/running the dialog. |

Possible `WinGetLastError` returns from the loaders include `PMERR_INVALID_HWND` (`0x1001`),
`PMERR_RESOURCE_NOT_FOUND` (`0x100A`), and the atom-table errors `PMERR_INVALID_INTEGER_ATOM`
(`0x1016`), `PMERR_INVALID_ATOM_NAME` (`0x1015`), `PMERR_ATOM_NAME_NOT_FOUND` (`0x1017`) [DOC-IBM
`pm2.txt:16187-16204`].

---

## 5. The dialog procedure and `WM_INITDLG` [DOC-IBM]

A dialog procedure has the ordinary window-procedure signature
(`MRESULT EXPENTRY DlgProc(HWND, ULONG, MPARAM, MPARAM)`; see `pm-window-messaging.md` section 3) and must
pass every message it does not handle to **`WinDefWindowProc`**'s dialog counterpart,
`WinDefDlgProc`. `WinDefDlgProc`'s behaviour is "precisely the same as for the frame window
procedure except for `WM_CLOSE`, where `WinDismissDlg` will be called" [DOC-IBM `pm2.txt:5957`].

A dialog procedure receives **`WM_INITDLG`** (`0x003b`, `pmwin.h:975`) in place of `WM_CREATE`. It
arrives after all the dialog's controls exist, so it is the point to initialize control contents.
Its parameters [DOC-IBM - PM Reference; and see `pm-window-messaging.md` section 8]:

- `mp1` = the handle of the control that will receive the initial focus;
- `mp2` = the `pCreateParams` pointer passed to `WinLoadDlg` / `WinDlgBox`.

#### `WM_INITDLG`'s return value is INVERTED from Win32's `WM_INITDIALOG` [DOC-IBM]

The return is a **focus-set indicator**, not a "handled" flag [DOC-IBM - `pm3.txt`, *WM_INITDLG
Return Value*]:

| Return | PM meaning |
|---|---|
| `TRUE` | "Focus window **is changed**" - *the dialog procedure has set the focus itself*, e.g. with `WinSetFocus` to some other control. PM does not assign it. |
| `FALSE` | "Focus window is **not changed**" - PM assigns the default focus (the control in `mp1`). |

**Win32's `WM_INITDIALOG` is the exact opposite**: there, returning `TRUE` asks the system to set
the default focus and `FALSE` means the application set it. So the single most common line in a
ported dialog procedure - `return TRUE;` at the end of the init case - is **backwards on PM**.

The failure is completely silent and looks like a drawing or event bug, not a dialog bug:

- the dialog appears, correctly laid out, with all control values initialized;
- **no control has the focus, so the dialog never becomes active** - its title bar stays in the
  inactive colour while the owner's stays active;
- every keystroke goes to the owner window. Enter, Escape, Tab and all typing are simply inert.

Return `FALSE` from `WM_INITDLG` unless you have genuinely called `WinSetFocus` yourself.

[OBS-RE - hit while porting Notepad2's `ColumnWrapDlgProc`; the mechanically-translated
`return TRUE` produced a perfectly-rendered dialog that ignored the keyboard entirely, and the
one-character fix restored it.]

Two related dialog messages a procedure may see or answer: **`WM_QUERYDLGCODE`** (`0x003a`,
`pmwin.h:974`) - a control answers with a `DLGC_*` bit set describing what kind of dialog item it
is (Section below) - and **`WM_SUBSTITUTESTRING`** (`0x003c`, `pmwin.h:976`), sent while control
text is run through `WinSubstituteStrings`.

**`DLGC_*` dialog codes** (`WM_QUERYDLGCODE` reply) [DOC-IBM `pmwin.h:1813-1823`]:
`DLGC_ENTRYFIELD` `0x0001`, `DLGC_BUTTON` `0x0002`, `DLGC_RADIOBUTTON` `0x0004`, `DLGC_STATIC`
`0x0008`, `DLGC_DEFAULT` `0x0010`, `DLGC_PUSHBUTTON` `0x0020`, `DLGC_CHECKBOX` `0x0040`,
`DLGC_SCROLLBAR` `0x0080`, `DLGC_MENU` `0x0100`, `DLGC_TABONCLICK` `0x0200`, `DLGC_MLE` `0x0400`.

---

## 6. Addressing dialog controls by id [DOC-IBM]

Controls in a dialog are reached by their template `id` rather than by handle. The dialog-item
functions wrap the ordinary window operations with an id->handle lookup (each is equivalent to
`WinWindowFromID(hwndDlg, idItem)` followed by the corresponding window call) [DOC-IBM
`pm2.txt:32476-32483`].

| Symbol | Prototype (from `pmwin.h`) | Purpose |
|---|---|---|
| `WinSendDlgItemMsg` | `MRESULT WinSendDlgItemMsg(HWND hwndDlg, ULONG idItem, ULONG msg, MPARAM mp1, MPARAM mp2)` | Send `msg` to the control `idItem`; equivalent to `WinSendMsg(WinWindowFromID(hwndDlg, idItem), ...)`. [`pmwin.h:1827-1831`] |
| `WinQueryDlgItemText` | `ULONG WinQueryDlgItemText(HWND hwndDlg, ULONG idItem, LONG cchBufferMax, PSZ pchBuffer)` | Copy a control's text into `pchBuffer`; returns the character count (excluding the null, max `cchBufferMax-1`), or `0` on error. [`pmwin.h:1610-1613`, `pm2.txt:23444-23452`] |
| `WinQueryDlgItemTextLength` | `LONG WinQueryDlgItemTextLength(HWND hwndDlg, ULONG idItem)` | Length of a control's text. [`pmwin.h:1615-1616`] |
| `WinSetDlgItemText` | `BOOL WinSetDlgItemText(HWND hwndDlg, ULONG idItem, PSZ pszText)` | Set a control's text. [`pmwin.h:1600-1602`] |
| `WinQueryDlgItemShort` | `BOOL WinQueryDlgItemShort(HWND hwndDlg, ULONG idItem, PSHORT pResult, BOOL fSigned)` | Read a control's text as a number. [`pmwin.h:1587-1590`] |
| `WinSetDlgItemShort` | `BOOL WinSetDlgItemShort(HWND hwndDlg, ULONG idItem, USHORT usValue, BOOL fSigned)` | Set a control's text from a number. [`pmwin.h:1591-1594`] |
| `WinEnumDlgItem` | `HWND WinEnumDlgItem(HWND hwndDlg, HWND hwnd, ULONG code)` | Walk the dialog's items by tab/group order (`EDI_*`). [`pmwin.h:1836-1838`] |
| `WinMapDlgPoints` | `BOOL WinMapDlgPoints(HWND hwndDlg, PPOINTL prgwptl, ULONG cwpt, BOOL fCalcWindowCoords)` | Convert between dialog coordinates and window pixels. [`pmwin.h:1832-1835`] |
| `WinSubstituteStrings` | `LONG WinSubstituteStrings(HWND hwnd, PSZ pszSrc, LONG cchDstMax, PSZ pszDst)` | Expand `%` substitution variables in a string. [`pmwin.h:1845-1848`] |

`WinEnumDlgItem` codes [DOC-IBM `pmwin.h:1854-1861`]: `EDI_FIRSTTABITEM` `0`, `EDI_LASTTABITEM`
`1`, `EDI_NEXTTABITEM` `2`, `EDI_PREVTABITEM` `3`, `EDI_FIRSTGROUPITEM` `4`, `EDI_LASTGROUPITEM`
`5`, `EDI_NEXTGROUPITEM` `6`, `EDI_PREVGROUPITEM` `7`. Tab and group order come from the
`WS_TABSTOP`/`WS_GROUP` styles on the items (see `pm-window-messaging.md` section 4).

Convenience macros over `WinSendDlgItemMsg` for the common button/control operations [DOC-IBM
`pmwin.h:1769-1804`]:

| Macro | Expands to |
|---|---|
| `WinCheckButton(hwndDlg, id, usCheckState)` | `WinSendDlgItemMsg(..., BM_SETCHECK, ...)` - set a button's check state, returns the previous one |
| `WinQueryButtonCheckstate(hwndDlg, id)` | `WinSendDlgItemMsg(..., BM_QUERYCHECK, ...)` - read a button's check state |
| `WinEnableControl(hwndDlg, id, fEnable)` | `WinEnableWindow(WinWindowFromID(hwndDlg, id), fEnable)` |
| `WinShowControl(hwndDlg, id, fShow)` | `WinShowWindow(WinWindowFromID(hwndDlg, id), fShow)` |
| `WinIsControlEnabled(hwndDlg, id)` | `WinIsWindowEnabled(WinWindowFromID(hwndDlg, id))` |

### Message boxes [DOC-IBM]

A message box is a self-contained modal dialog needing no template: `WinMessageBox(HWND hwndParent,
HWND hwndOwner, PSZ pszText, PSZ pszCaption, ULONG idWindow, ULONG flStyle)` displays text with a
standard button set and returns the button chosen (an `MBID_*` value) [DOC-IBM `pmwin.h:1650-1655`].
The `MB_*` button/icon/modality style flags and the `MBID_*` return values are catalogued in
`pm-window-messaging.md` section 8. `WinAlarm(HWND hwndDesktop, ULONG rgfType)` sounds a system alarm:
`WA_WARNING` (`0`), `WA_NOTE` (`1`), `WA_ERROR` (`2`) [DOC-IBM `pmwin.h:1631-1638`].

---

## 7. Menus [DOC-IBM]

A menu is a resource of type `RT_MENU` (Section 2). `WinLoadMenu` instantiates it as a **menu
window**:

```c
HWND APIENTRY WinLoadMenu(HWND hwndFrame, HMODULE hmod, ULONG idMenu);   /* pmwin.h:2374-2376 */
```

The menu window is created with parent and owner both `hwndFrame` and with the id **`FID_MENU`**
(the frame's menu-control id; see `pm-window-messaging.md` section 4). An action-bar menu is created as a
visible child of the frame; submenus are created as object windows owned by the frame. If
`hwndFrame` is `HWND_OBJECT` (or an object window) the menu itself is created as an object window
[DOC-IBM `pm2.txt:16649-16652`]. A frame created by `WinCreateStdWindow` with the `FCF_MENU` flag
loads its menu from the frame's resource id automatically.

`WinCreateMenu(HWND hwndParent, PVOID lpmt)` builds a menu from an **in-memory** menu template
(`MT`/`MTI`) instead of a resource [DOC-IBM `pmwin.h:2428-2429`].

### `MENUITEM` - one menu entry [DOC-IBM `pmwin.h:2457-2465`]

```c
typedef struct _MENUITEM {   /* mi */
    SHORT   iPosition;       /* zero-based position, or MIT_END           */
    USHORT  afStyle;         /* MIS_* style bits                          */
    USHORT  afAttribute;     /* MIA_* attribute bits                      */
    USHORT  id;              /* command id sent in WM_COMMAND             */
    HWND    hwndSubMenu;     /* submenu window (if MIS_SUBMENU)           */
    ULONG   hItem;           /* item handle (text / bitmap / owner data)  */
} MENUITEM;
```

**Item styles** `MIS_*` (`afStyle`) [DOC-IBM `pmwin.h:2481-2503`]:

| Constant | Value | Meaning |
|---|---|---|
| `MIS_TEXT` | `0x0001` | Item is text. |
| `MIS_BITMAP` | `0x0002` | Item is a bitmap. |
| `MIS_SEPARATOR` | `0x0004` | Item is a separator line. |
| `MIS_OWNERDRAW` | `0x0008` | Owner draws the item. |
| `MIS_SUBMENU` | `0x0010` | Item opens a submenu (`hwndSubMenu`). |
| `MIS_MULTMENU` | `0x0020` | Multiple-choice submenu. |
| `MIS_SYSCOMMAND` | `0x0040` | Selection sends `WM_SYSCOMMAND` (not `WM_COMMAND`). |
| `MIS_HELP` | `0x0080` | Selection sends `WM_HELP`. |
| `MIS_STATIC` | `0x0100` | Non-selectable static item. |
| `MIS_BUTTONSEPARATOR` | `0x0200` | Button-style separator. |
| `MIS_BREAK` / `MIS_BREAKSEPARATOR` | `0x0400` / `0x0800` | Column break / break with separator. |
| `MIS_GROUP` / `MIS_SINGLE` | `0x1000` / `0x2000` | Multiple-choice group start / single-choice. |

**Item attributes** `MIA_*` (`afAttribute`) [DOC-IBM `pmwin.h:2505-2509`]: `MIA_NODISMISS`
`0x0020`, `MIA_FRAMED` `0x1000`, `MIA_CHECKED` `0x2000`, `MIA_DISABLED` `0x4000`, `MIA_HILITED`
`0x8000`. **Position sentinels** `MIT_*` [DOC-IBM `pmwin.h:2470-2476`]: `MIT_END`/`MIT_NONE`/
`MIT_ERROR` `(-1)`, `MIT_FIRST` `(-2)`, `MIT_LAST` `(-3)`.

### Manipulating a menu at run time - `MM_*` messages [DOC-IBM `pmwin.h:2381-2403`]

Menus are controlled by sending messages to the menu window: `MM_INSERTITEM` (`0x0180`),
`MM_DELETEITEM` (`0x0181`), `MM_QUERYITEM` (`0x0182`), `MM_SETITEM` (`0x0183`),
`MM_QUERYITEMCOUNT` (`0x0184`), `MM_SELECTITEM` (`0x0189`), `MM_QUERYSELITEMID` (`0x018a`),
`MM_QUERYITEMTEXT` (`0x018b`), `MM_SETITEMTEXT` (`0x018e`), `MM_ITEMIDFROMPOSITION` (`0x0190`),
`MM_QUERYITEMATTR` (`0x0191`), `MM_SETITEMATTR` (`0x0192`), `MM_QUERYDEFAULTITEMID` (`0x0431`),
`MM_SETDEFAULTITEMID` (`0x0432`). Checking or enabling an item is `MM_SETITEMATTR` with
`MIA_CHECKED` / `MIA_DISABLED` (the library provides `WinCheckMenuItem` / `WinEnableMenuItem` /
`WinIsMenuItemChecked` wrappers over these) [DOC-IBM `pmwin.h:2548-2596`].

### What a menu selection delivers [DOC-IBM]

The menu itself does not perform the command; it **notifies** the frame's owner. The relevant
messages [DOC-IBM `pmwin.h:944-970`]:

| Message | Value | Delivered when |
|---|---|---|
| `WM_INITMENU` | `0x0033` | A menu is about to be displayed (last chance to update item states). |
| `WM_MENUSELECT` | `0x0034` | A menu item is highlighted. `mp1` = `SHORT1FROMMP` item id, `mp2` = menu window handle. |
| `WM_MENUEND` | `0x0035` | Menu interaction ended. |
| `WM_NEXTMENU` | `0x004e` | Navigation off the end of a menu. [DOC-IBM `pmwin.h:2809`] |
| `WM_COMMAND` | `0x0020` | A normal item was chosen - the item's `id` is the command. |
| `WM_SYSCOMMAND` | `0x0021` | A `MIS_SYSCOMMAND` item was chosen. |
| `WM_HELP` | `0x0022` | A `MIS_HELP` item was chosen. |

`WM_MENUSELECT` parameter usage - `usItemId = SHORT1FROMMP(mp1); hwndMenu = HWNDFROMMP(mp2);` - is
shown in the reference's own example [DOC-IBM `pm2.txt:1780-1782`].

`WM_COMMAND`/`WM_SYSCOMMAND`/`WM_HELP` share a parameter layout accessed through `CMDMSG` [DOC-IBM
`pmwin.h:1004-1017`]:

```c
#pragma pack(1)
typedef struct _COMMANDMSG {   /* commandmsg */
    USHORT  cmd;               /* mp1 : the command (item / accelerator / button) id */
    USHORT  unused;
    USHORT  source;            /* mp2 : CMDSRC_* - where the command came from        */
    USHORT  fMouse;            /* mp2 : mouse-initiated flag                          */
} CMDMSG;
```

The command **source** distinguishes a menu selection from a button or an accelerator [DOC-IBM
`pmwin.h:994-1002`]: `CMDSRC_OTHER` (`0`), `CMDSRC_PUSHBUTTON` (`1`), `CMDSRC_MENU` (`2`),
`CMDSRC_ACCELERATOR` (`3`), `CMDSRC_FONTDLG` (`4`), `CMDSRC_FILEDLG` (`5`), `CMDSRC_PRINTDLG` (`6`),
`CMDSRC_COLORDLG` (`7`).

---

## 8. Accelerators [DOC-IBM]

An **accelerator table** maps keystrokes to command ids, so a key such as `F3` or `Ctrl+S` produces
the same `WM_COMMAND` a menu item would. It is a resource of type `RT_ACCELTABLE` (Section 2), and
its binary format is a public structure. The handle type is `HACCEL` (`typedef LHANDLE HACCEL`,
`pmwin.h:3480`).

### `ACCEL` and `ACCELTABLE` [DOC-IBM]

```c
typedef struct _ACCEL {        /* acc - os2def.h:634-639 */
    USHORT  fs;                /* AF_* option flags        */
    USHORT  key;               /* the key (char, VK_*, or scan code per fs) */
    USHORT  cmd;               /* command id delivered in WM_COMMAND/SYSCOMMAND/HELP */
} ACCEL;

typedef struct _ACCELTABLE {   /* acct - pmwin.h:3508-3513 */
    USHORT  cAccel;            /* number of ACCEL entries  */
    USHORT  codepage;          /* code page of the entries */
    ACCEL   aaccel[1];         /* the entries              */
} ACCELTABLE;
```

`ACCEL.cmd` is "the value to be placed in the `uscmd` parameter of a `WM_HELP`, a `WM_COMMAND`, or a
`WM_SYSCOMMAND`" [DOC-IBM `pm4.txt` ACCEL Field - cmd].

**Accelerator option flags** `AF_*` (`ACCEL.fs`) [DOC-IBM `pmwin.h:3491-3499`] - the first six
deliberately share values with the `KC_*` keyboard flags:

| Constant | Value | Meaning |
|---|---|---|
| `AF_CHAR` | `0x0001` | `key` is a character code. |
| `AF_VIRTUALKEY` | `0x0002` | `key` is a virtual key (`VK_*`). |
| `AF_SCANCODE` | `0x0004` | `key` is a hardware scan code. |
| `AF_SHIFT` | `0x0008` | Shift must be down. |
| `AF_CONTROL` | `0x0010` | Ctrl must be down. |
| `AF_ALT` | `0x0020` | Alt must be down. |
| `AF_LONEKEY` | `0x0040` | The key pressed and released alone. |
| `AF_SYSCOMMAND` | `0x0100` | Deliver `WM_SYSCOMMAND` instead of `WM_COMMAND`. |
| `AF_HELP` | `0x0200` | Deliver `WM_HELP`. |

The system default accelerator table has 16 entries - e.g. `HELP` on `VK_F1` -> command `0`,
`ALT+F4` -> `SC_CLOSE`, `ALT+F7` -> `SC_MOVE`, `ALT+F9` -> `SC_MINIMIZE` - all `VIRTUALKEY`
accelerators [DOC-IBM `pm4.txt` ACCELTABLE Field - aaccel].

### Accelerator-table resource script [DOC-IBM]

IBM's own example of the `.RC` form [DOC-IBM - `pmv2base.txt`, "Creating an Accelerator-Table
Resource"] - entries are `key, command, flags`:

```rc
ACCELTABLE ID_ACCEL_RESOURCE
BEGIN
    VK_ESC,    IDM_ED_UNDO,  AF_VIRTUALKEY | AF_SHIFT
    VK_DELETE, IDM_ED_CUT,   AF_VIRTUALKEY
    VK_F2,     IDM_ED_COPY,  AF_VIRTUALKEY
    VK_INSERT, IDM_ED_PASTE, AF_VIRTUALKEY
END
```

The `AF_` prefix may be dropped in the flags column (`VIRTUALKEY, SHIFT`), and a character
accelerator is written with the character in quotes: `"c", IDM_COPY, CHAR, CONTROL`. Both forms
were compiled and run [OBS-RE].

**Associating it with a frame:** pass the table's id as the `idResources` argument of
`WinCreateStdWindow` and include **`FCF_ACCELTABLE`** in the frame flags; the frame then loads it
automatically, exactly as `FCF_MENU` loads a `MENU` of the same id.

Accelerators are dispatched by the frame **before** the focus window is offered the key, so they
work even when a focused child control consumes `WM_CHAR`. They are not a substitute for the
forwarding contract in `pm-window-messaging.md` - menu *mnemonics* still require it.

### Accelerator functions [DOC-IBM `pmwin.h:3518-3535`]

| Symbol | Prototype | Purpose |
|---|---|---|
| `WinLoadAccelTable` | `HACCEL WinLoadAccelTable(HAB hab, HMODULE hmod, ULONG idAccelTable)` | Load an accelerator-table resource; returns an `HACCEL` owned by the calling process (auto-deleted at process end). |
| `WinCreateAccelTable` | `HACCEL WinCreateAccelTable(HAB hab, PACCELTABLE pAccelTable)` | Build one from an in-memory `ACCELTABLE`. |
| `WinCopyAccelTable` | `ULONG WinCopyAccelTable(HACCEL haccel, PACCELTABLE pAccelTable, ULONG cbCopyMax)` | Copy a table's contents into a buffer (or query its size). |
| `WinDestroyAccelTable` | `BOOL WinDestroyAccelTable(HACCEL haccel)` | Destroy an accelerator table. |
| `WinSetAccelTable` | `BOOL WinSetAccelTable(HAB hab, HACCEL haccel, HWND hwndFrame)` | Make a table the active table for a frame. |
| `WinQueryAccelTable` | `HACCEL WinQueryAccelTable(HAB hab, HWND hwndFrame)` | Query the active table. |
| `WinTranslateAccel` | `BOOL WinTranslateAccel(HAB hab, HWND hwnd, HACCEL haccel, PQMSG pqmsg)` | Translate a `WM_CHAR` in `*pqmsg` into `WM_COMMAND`/`WM_SYSCOMMAND`/`WM_HELP`. |

An accelerator-table resource is owned by the process that loads it and cannot be accessed from
another process; loading the same id twice yields two distinct handles [DOC-IBM `pm2.txt:15973-15976`].

### How a keystroke becomes a command [DOC-IBM `pm2.txt:42260-42271` WinTranslateAccel Remarks]

`WinTranslateAccel` examines `*pqmsg`; if it is a `WM_CHAR` that matches an entry in `haccel`, it
**rewrites the message in place** into a `WM_COMMAND`, `WM_SYSCOMMAND`, or `WM_HELP` (per the entry's
`AF_*` flags), with `hwnd` - normally a frame handle - as the target, and returns `TRUE`. A
`NULL` `haccel` means the current table. If a matching command corresponds to a **disabled** menu
item, the message is rewritten to `WM_NULL` instead. Crucially, applications "generally do not have
to call this function; it is usually called automatically by `WinGetMsg` and `WinPeekMsg`" when a
`WM_CHAR` arrives for the active window - so the application never sees the `WM_CHAR`, only the
resulting `WM_COMMAND`, and the standard frame procedure forwards that `WM_COMMAND` to its
`FID_CLIENT`. It does not highlight menu items.

The frame owns the accelerator table via the `FCF_ACCELTABLE` (`0x00008000`, `pmwin.h:2702`) /
`FS_ACCELTABLE` (`0x00000002`, `pmwin.h:2721`) creation flags and the frame messages
`WM_SETACCELTABLE` (`0x0049`), `WM_QUERYACCELTABLE` (`0x004a`), and `WM_TRANSLATEACCEL` (`0x004b`)
[DOC-IBM `pmwin.h:2804-2806`].

---

## 9. Strings, pointers, and bitmaps [DOC-IBM]

### Strings - `WinLoadString` / `WinLoadMessage` [DOC-IBM `pmwin.h:675-700`]

```c
LONG APIENTRY WinLoadString (HAB hab, HMODULE hmod, ULONG id, LONG cchMax, PSZ pchBuffer);
LONG APIENTRY WinLoadMessage(HAB hab, HMODULE hmod, ULONG id, LONG cchMax, PSZ pchBuffer);
```

`WinLoadString` copies string `id` from a string-table (`RT_STRING`) resource in `hmod`
(`NULLHANDLE` = the application's own resources) into `pchBuffer`, returning the length excluding
the terminating null - `0` on error, otherwise at most `cchMax-1`. String ids are `0`-`0xFFFF`, and
the maximum string length is **256 characters** [DOC-IBM `pm2.txt:17134-17163`]. Keeping
user-visible text in a string table rather than in code is what lets an application be translated
without recompiling. `WinLoadMessage` is the same for a message-table (`RT_MESSAGE`) resource.

### Pointers and icons - `WinLoadPointer` [DOC-IBM `pmwin.h:3829-3831`]

```c
HPOINTER APIENTRY WinLoadPointer(HWND hwndDesktop, HMODULE hmod, ULONG idres);
```

Loads a pointer / icon resource (`RT_POINTER`) into the system and returns an `HPOINTER`
(`NULLHANDLE` on error); `hwndDesktop` is `HWND_DESKTOP` or a desktop handle, `Resource` is the
module (`NULLHANDLE` = the application), and `idres` is `0`-`0xFFFF` [DOC-IBM `pm2.txt:16860-16910`].
The resulting `HPOINTER` is used as a window-class icon, a frame icon (`FCF_ICON`), or the mouse
pointer.

### Bitmaps - `GpiLoadBitmap` [DOC-IBM `pmgpi.h:1947-1951`]

```c
HBITMAP APIENTRY GpiLoadBitmap(HPS hps, HMODULE Resource, ULONG idBitmap, LONG lWidth, LONG lHeight);
```

Loads a bitmap resource (`RT_BITMAP`) into a presentation space and returns an `HBITMAP`, optionally
stretching to `lWidth`x`lHeight`; `Resource` follows the same module convention. The bitmap is then
drawn with the Gpi bit-blit functions (`GpiWCBitBlt`, `pmgpi.h:1956`) or, on a window PS, with
`WinDrawBitmap` (`pmwin.h:597`). The Gpi drawing model is in `pm-graphics.md`.

---

## 10. The standard dialogs - file and font [DOC-IBM]

PM ships two ready-made dialogs an application can raise instead of authoring its own: the
**file dialog** (`INCL_WINSTDFILE`) and the **font dialog** (`INCL_WINSTDFONT`), both declared
in `pmstddlg.h`. They are ordinary dialogs - template plus dialog procedure - but the template
and the procedure are supplied by the system, and the application communicates with them through
a single parameter block rather than through `WM_INITDLG` and control messages.

**Where they actually live:** `WinFileDlg` is **not** in `PMWIN` - it is exported from
`PMCTLS.DLL` (ordinal 4; `WinDefFileDlgProc` 5, `WinFreeFileDlgList` 6, `WinFontDlg` 2,
`WinDefFontDlgProc` 3), and the dialog *templates* live in the resource-only module
`PMSDMRI.DLL`. See `module-dll.md` section "Where the PM APIs actually live" before attempting any
interposition. [OBS-RE]

### 10.1 `WinFileDlg` [DOC-IBM]

```c
#define INCL_WINSTDFILE
HWND    APIENTRY WinFileDlg(HWND hwndP, HWND hwndO, PFILEDLG pfild);   /* pmstddlg.h:183 */
MRESULT APIENTRY WinDefFileDlgProc(HWND, ULONG, MPARAM, MPARAM);       /* pmstddlg.h:186 */
BOOL    APIENTRY WinFreeFileDlgList(PAPSZ papszFQFilename);            /* pmstddlg.h:191 */
```

`hwndP` is the parent (`HWND_DESKTOP` or a window), `hwndO` the requested owner - the actual
owner is computed by the `WinLoadDlg` algorithm (section 4). The return is the dialog `HWND` when
`FDS_MODELESS` is set, otherwise `TRUE`/`NULLHANDLE` for success/failure. [DOC-IBM - `pm2.txt`
WinFileDlg.] **Everything else passes through `FILEDLG`**, which is both input and output:

`FILEDLG` - `pmstddlg.h:141-177`. Fields that carry the contract:

| Field | Meaning |
|---|---|
| `cbSize` | Must be set to `sizeof(FILEDLG)` before the call. |
| `fl` | `FDS_*` flags (below). |
| `lReturn` | Result of dismissal - `DID_OK` / `DID_CANCEL`. |
| `lSRC` | System return code - `FDS_SUCCESSFUL` (0) or an `FDS_ERR_*` (`pmstddlg.h:103-116`). |
| `pszTitle`, `pszOKButton` | Override the title-bar and OK-button text. |
| `pfnDlgProc` | **Application's own dialog procedure** (see 10.2). |
| `pszIType`, `papszITypeList` | Initial EA type filter, and the type list. |
| `pszIDrive`, `papszIDriveList` | Initial drive, and the drive list. |
| `hMod`, `usDlgId` | **Application's own dialog template** (see 10.2). |
| `szFullFile[CCHMAXPATH]` | In: initial path/file. Out: the fully-qualified selection. |
| `papszFQFilename`, `ulFQFCount` | Multi-select results; free with `WinFreeFileDlgList`. |
| `sEAType` | Selected file's EA type. |

`FDS_*` style flags - `pmstddlg.h:79-91`:

`FDS_CENTER` `0x1`, `FDS_CUSTOM` `0x2`, `FDS_FILTERUNION` `0x4`, `FDS_HELPBUTTON` `0x8`,
`FDS_APPLYBUTTON` `0x10`, `FDS_PRELOAD_VOLINFO` `0x20`, `FDS_MODELESS` `0x40`,
`FDS_INCLUDE_EAS` `0x80`, `FDS_OPEN_DIALOG` `0x100`, `FDS_SAVEAS_DIALOG` `0x200`,
`FDS_MULTIPLESEL` `0x400`, `FDS_ENABLEFILELB` `0x800`, `FDS_NATIONAL_LANGUAGE` `0x80000000`.

`FDS_FILTERUNION` selects the *union* of the string filter and the EA-type filter; without it
the dialog uses their *intersection* - the default. [DOC-IBM - `pm4.txt:4070`.]

### 10.2 Customization - the sanctioned extension path [DOC-IBM]

The file dialog is designed to be replaced piecewise by the application, without touching any
system file:

- **Own template:** set `FDS_CUSTOM`; then `hMod` is the module holding the template and
  `usDlgId` its resource id. "A custom dialog template is used to create the dialog. The `hMod`
  and `usDlgID` fields must be initialized." [DOC-IBM - `pm4.txt:4066-4067`.] `hMod = NULLHANDLE`
  pulls the resource from the current `.EXE` [DOC-IBM - `pm4.txt:4162`].
- **Own procedure:** set `pfnDlgProc`. The custom procedure handles what it wants and **chains
  everything else to `WinDefFileDlgProc`**, exactly as a window procedure chains to
  `WinDefWindowProc`.

A custom template must keep the standard control ids, because the system procedure addresses its
controls by id (`pmstddlg.h:198-214`):

| Id | Control | | Id | Control |
|---|---|---|---|---|
| `DID_FILE_DIALOG` 256 | the dialog itself | | `DID_DIRECTORY_TXT` 263 | "Directory" text |
| `DID_FILENAME_TXT` 257 | "Open filename" text | | `DID_DIRECTORY_LB` 264 | directory listbox |
| `DID_FILENAME_ED` 258 | filename entry field | | `DID_FILES_TXT` 265 | "File" text |
| `DID_DRIVE_TXT` 259 | "Drive" text | | `DID_FILES_LB` 266 | files listbox |
| `DID_DRIVE_CB` 260 | drive combobox | | `DID_HELP_PB` 267 | Help button |
| `DID_FILTER_TXT` 261 | "Type of file" text | | `DID_APPLY_PB` 268 | Apply button |
| `DID_FILTER_CB` 262 | filter combobox | | `DID_READ_ONLY` 269 | read-only checkbox |
| `DID_OK_PB` = `DID_OK` | OK | | `DID_DIRECTORY_SELECTED` 270 | selected-directory text |
| `DID_CANCEL_PB` = `DID_CANCEL` | Cancel | | | |

Three messages let a custom procedure participate in filtering and validation
(`pmstddlg.h:121-127`):

| Message | `mp1` | Purpose |
|---|---|---|
| `FDM_FILTER` (`WM_USER+40`) | `PSZ pszFileName` | Accept/reject each file for the listbox. |
| `FDM_VALIDATE` (`WM_USER+41`) | `PSZ pszPathName` | Validate the final selection. |
| `FDM_ERROR` (`WM_USER+42`) | `USHORT` error id | Override the dialog's error reporting. |

> **Consequence for anyone replacing the dialog system-wide.** Because an application may supply
> its own template *and* its own procedure through these fields, a replacement that substitutes
> its own window cannot honour such a caller. Any global file-dialog replacement therefore needs
> a per-application exclusion path. This is a design constraint, not an implementation detail.

### 10.3 `WinFontDlg` [DOC-IBM]

Same shape: `FONTDLG` (`pmstddlg.h:285`), `FNTS_*` style flags (`pmstddlg.h:326-339` - including
`FNTS_CUSTOM` `0x2`, `FNTS_OWNERDRAWPREVIEW` `0x4`, `FNTS_BITMAPONLY` `0x100`,
`FNTS_VECTORONLY` `0x200`, `FNTS_FIXEDWIDTHONLY` `0x400`, `FNTS_PROPORTIONALONLY` `0x800`), and
`FNTS_ERR_*` results (`pmstddlg.h:372-376`). Font selection itself - `FATTRS`, `FONTMETRICS`,
point sizes - is in `gpi-fonts-and-metafiles.md`.

> **Two ways to get nothing back from it** [OBS-RE]:
>
> - **`FNTS_INITFROMFATTRS` (`0x80`) means "seed the dialog from `fd.fAttrs`".** Set the flag
>   without filling `fAttrs` - easy to do, since the struct is usually `memset` to zero first - and
>   the dialog opens from an empty `FATTRS` with `usRecordLength` 0 rather than from the current
>   font. Either fill `fAttrs` properly or drop the flag and let it seed from `pszFamilyname` +
>   `fxPointSize`, which are ordinary in/out fields.
> - **`pszFamilyname` and `fAttrs.szFacename` are not the same string.** The dialog writes the
>   selected **family** back into the `pszFamilyname` buffer (sized by `usFamilyBufLen`), while
>   `fAttrs.szFacename` is the **face** - "Courier Bold" where the family is "Courier". Handing a
>   face name onward as a family does not match, and the silent substitution described in
>   `gpi-fonts-and-metafiles.md` section 2.1 then renders a different font entirely. Read the family from
>   `pszFamilyname`.

---

## 11. Handle and structure summary [DOC-IBM]

| Type / struct | Definition | Meaning |
|---|---|---|
| `HMODULE` | `os2def.h` | Module that holds resources (`NULLHANDLE` = the application `.EXE`). |
| `HACCEL` | `pmwin.h:3480` | Accelerator-table handle. |
| `HPOINTER` | `os2def.h:644` | Pointer / icon handle. |
| `HBITMAP` | `os2def.h:272` (`typedef LHANDLE HBITMAP`) | Bitmap handle. |
| `DLGTEMPLATE` / `DLGTITEM` | `pmwin.h:1907-1917` / `1882-1898` | Dialog-template binary format (`RT_DIALOG`). |
| `ACCELTABLE` / `ACCEL` | `pmwin.h:3508-3513` / `os2def.h:634-639` | Accelerator-table binary format (`RT_ACCELTABLE`). |
| `MENUITEM` | `pmwin.h:2457-2465` | One menu entry (`RT_MENU`). |
| `PRESPARAMS` / `PARAM` | `pmwin.h:3141-3147` / `3132-3137` | Presentation parameters (colors, fonts). |
| `CMDMSG` | `pmwin.h:1010-1017` | `WM_COMMAND`/`WM_SYSCOMMAND`/`WM_HELP` parameter access. |
| `FILEDLG` | `pmstddlg.h:141-177` | Standard file-dialog parameter block (`WinFileDlg`). |
| `FONTDLG` | `pmstddlg.h:285` | Standard font-dialog parameter block (`WinFontDlg`). |

---

## See also
- `pm-window-messaging.md` - the anchor block, message queue, window procedure, `WinCreateStdWindow`
  and the frame controls (`FCF_*`, `FID_*`), the `WM_*` core set, `MPARAM` packing, `WinMessageBox`
  and its `MB_*`/`MBID_*` flags, and the system window classes (`WC_BUTTON`, `WC_ENTRYFIELD`, ...)
  used as dialog-control classes.
- `pm-graphics.md` - the Gpi drawing path a loaded bitmap or a `WM_PAINT` presentation space feeds.
- `module-dll.md` - `DosLoadModule` / `DosQueryModuleHandle`, which produce the `HMODULE` that names
  a DLL holding resources.
