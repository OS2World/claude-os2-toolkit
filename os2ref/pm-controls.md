# OS/2 Presentation Manager - Standard Control Classes

Presentation Manager ships a set of **preregistered window classes** - the buttons, entry
fields, list boxes, scroll bars, containers, notebooks, and other controls every PM
application builds its user interface from. Each is a public window class already registered
by the system; an application uses one simply by naming its `WC_*` class name in
`WinCreateWindow` / `WinCreateStdWindow` or in a dialog template, without registering a class
of its own. This reference documents each class's purpose, its principal styles, the messages
an application sends it, and the notifications it sends back to its owner. It is the companion
to `pm-window-messaging.md`, which covers the underlying window / message *model* (the anchor
block, the message queue, the window procedure, the core `WM_*` set, painting, and dialogs);
that model is assumed here and not repeated.

Provenance: **[DOC-IBM]** the IBM OS/2 Presentation Manager Programming Reference - the
per-control chapters "Control Window Message Processing" (button, entry field, container,
frame, static, list box, menu, scroll bar, slider, spin button, value set, title bar,
combination box, notebook) and the "Data Types" chapter, cited as `pm3.txt` / `pm4.txt`; the
Notebook Controls guide chapter (`pm5.txt`) - for every semantic claim (purpose, style meaning,
notification meaning). **[DOC-IBM]** the version-correct OS/2 Toolkit 4.5 headers `pmwin.h`,
`pmmle.h`, and `pmstddlg.h` - for every symbol name, constant value, message id, and structure
layout, cited as `file:line`. Where the book supplies meaning and the header supplies a value,
both are cited. A claim not confirmable in a header or the book is omitted.

---

## 1. How controls work [DOC-IBM]

A control is a child window of a system-provided class. The system implements each class's
window procedure; the application interacts with a control entirely through **messages** - it
*sends* the control class-specific messages (`BM_*`, `EM_*`, `LM_*`, `CM_*`, ...) to query or
change its state, and the control *notifies* its owner when a significant event occurs.

**The predefined control classes** [DOC-IBM `pmwin.h:241-262`; purposes from PM Reference,
pm3.txt "Control Window Message Processing"]:

| Class name | Value | Purpose |
|---|---|---|
| `WC_FRAME` | `0xffff0001` | A composite window - the frame that carries a title bar, menu, borders, scroll bars, and a client window. |
| `WC_COMBOBOX` | `0xffff0002` | An entry field and a list box merged into a single control. |
| `WC_BUTTON` | `0xffff0003` | Buttons and boxes the operator selects by clicking or with the keyboard (push buttons, check boxes, radio buttons). |
| `WC_MENU` | `0xffff0004` | A list of items shown horizontally as an action bar or vertically as a pull-down; the command interface. |
| `WC_STATIC` | `0xffff0005` | Simple display items (text, icon, bitmap, box) that do not respond to keyboard or pointer events. |
| `WC_ENTRYFIELD` | `0xffff0006` | A single line of editable text. |
| `WC_LISTBOX` | `0xffff0007` | A list of text items from which the operator makes selections. |
| `WC_SCROLLBAR` | `0xffff0008` | Scroll bars by which the operator requests scrolling of an associated window's contents. |
| `WC_TITLEBAR` | `0xffff0009` | Displays the window title/caption and lets the operator move its owner. |
| `WC_MLE` | `0xffff000A` | A multiple-line editable text window (multi-line entry field). |
| `WC_SPINBUTTON` | `0xffff0020` | A scrollable ring of choices the operator spins through. |
| `WC_CONTAINER` | `0xffff0025` | Holds objects (programs, files, images, records) and displays them in several views. |
| `WC_SLIDER` | `0xffff0026` | Sets/displays/modifies a value by moving an arm along a shaft. |
| `WC_VALUESET` | `0xffff0027` | Selects one choice from a group of mutually exclusive choices, shown as images, colors, text, or numbers. |
| `WC_NOTEBOOK` | `0xffff0028` | Organizes information on tabbed pages the user turns through. |

### Owner-notification: `WM_CONTROL`, `WM_COMMAND`, `WM_HELP` [DOC-IBM pm3.txt]

A control notifies its owner in one of three ways [DOC-IBM `pmwin.h:944,946,965`]:

| Message | Value | Use |
|---|---|---|
| `WM_CONTROL` | `0x0030` | The general control notification. `mp1` packs the control **id** (`SHORT1FROMMP`) and a **notification code** (`SHORT2FROMMP`); `mp2` carries control-specific information (often the control's window handle). |
| `WM_COMMAND` | `0x0020` | Posted by a control that issues a command (a push button, a menu item). The command source is in the `CMDMSG` `source` field - `CMDSRC_PUSHBUTTON`, `CMDSRC_MENU`, `CMDSRC_ACCELERATOR`, `CMDSRC_OTHER`. |
| `WM_HELP` | `0x0022` | Posted when the operator requests help on the control (e.g. a `BS_HELP` button); source encoded as for `WM_COMMAND`. |

The `WM_CONTROL` packing (id in the low half of `mp1`, notification code in the high half) is
the shape every control's notification set below is delivered in [DOC-IBM pm3.txt "WM_CONTROL
(in Button Controls)"; packing macros in `pm-window-messaging.md` section 2]. Two owner-draw
notifications, `WM_DRAWITEM` (`0x0036`) and `WM_MEASUREITEM` (`0x0037`), are sent to the owner
of an owner-drawn list box, menu, container, slider, or value set [DOC-IBM `pmwin.h:971-972`].

Message-id numbering is grouped by control: the first characters of a message name identify the
control (`BM`/`BN` button, `EM`/`EN` entry field, `MLM`/`MLN` MLE, `LM`/`LN` list box,
`CBM`/`CBN` combo box, `SBM` scroll bar, `MM` menu, `SPBM`/`SPBN` spin button, `SLM`/`SLN`
slider, `VM`/`VN` value set, `CM`/`CN` container, `BKM`/`BKN` notebook, `TBM` title bar)
[DOC-IBM pm3.txt "Notation Conventions"].

---

## 2. `WC_FRAME` - frame window [DOC-IBM]

A frame is a composite window that groups a client window with its decorative and functional
frame controls (title bar, system menu, menu bar, borders, min/max buttons, scroll bars). A
standard frame is normally built with `WinCreateStdWindow` (see `pm-window-messaging.md` section 4),
which selects the frame controls with `FCF_*` creation flags; the individual controls are child
windows found by the `FID_*` ids. The `FCF_*` creation flags and `FID_*` control ids are
documented in `pm-window-messaging.md` section 4.

**Frame styles** (`FS_*`) - used when a frame is created from a dialog template [DOC-IBM
`pmwin.h:2720-2742`; meanings pm3.txt "Frame Control Styles"]:

| Constant | Value | Meaning |
|---|---|---|
| `FS_ICON` | `0x0001` | Load an icon from resources. |
| `FS_ACCELTABLE` | `0x0002` | Load an accelerator table. |
| `FS_SHELLPOSITION` | `0x0004` | The shell chooses position/size. |
| `FS_TASKLIST` | `0x0008` | Add the frame to the window/task list. |
| `FS_NOBYTEALIGN` | `0x0010` | Do not byte-align the window (no horizontal snapping). |
| `FS_NOMOVEWITHOWNER` | `0x0020` | Do not move when the owner moves. |
| `FS_SYSMODAL` | `0x0040` | System-modal frame. |
| `FS_DLGBORDER` | `0x0080` | Dialog border. |
| `FS_BORDER` | `0x0100` | Thin border. |
| `FS_SCREENALIGN` | `0x0200` | Position coordinates are relative to the screen's top-left. |
| `FS_MOUSEALIGN` | `0x0400` | Position coordinates are relative to the pointer at creation time. |
| `FS_SIZEBORDER` | `0x0800` | Sizing border. |
| `FS_AUTOICON` | `0x1000` | Auto-repaint the minimized icon. |
| `FS_STANDARD` | `0x000F` | `FS_ICON` + `FS_ACCELTABLE` + `FS_SHELLPOSITION` + `FS_TASKLIST`. |

**Frame messages** - the frame procedure processes layout, focus, and background messages sent
to a frame window; the principal ones are `WM_FORMATFRAME` (`0x0041`), `WM_UPDATEFRAME`
(`0x0042`), `WM_FOCUSCHANGE` (`0x0043`), `WM_MINMAXFRAME` (`0x0046`), `WM_TRANSLATEACCEL`
(`0x004b`), `WM_ERASEBACKGROUND` (`0x004f`), and `WM_QUERYFRAMEINFO` [DOC-IBM `pmwin.h:2794-2818`;
also `pm-window-messaging.md` section 6 "Frame messages"].

---

## 3. `WC_TITLEBAR` - title bar; the system menu [DOC-IBM]

The title bar (`WC_TITLEBAR`, `0xffff0009`) displays the window's title/caption and lets the
operator move the owner window by dragging it [DOC-IBM pm3.txt "Control Window Message
Processing"]. In a standard frame it is the child with id `FID_TITLEBAR` (`0x8003`).

**Title-bar messages** [DOC-IBM `pmwin.h:2930-2931`]:

| Message | Value | Purpose |
|---|---|---|
| `TBM_SETHILITE` | `0x01e3` | Set the title bar's highlight (active/inactive) state. |
| `TBM_QUERYHILITE` | `0x01e4` | Query the highlight state. |

The title text is read and written with the generic `WinQueryWindowText` / `WinSetWindowText`
and with `WM_QUERYWINDOWPARAMS` / `WM_SETWINDOWPARAMS`.

**The system menu** is *not* a distinct window class - there is no `WC_SYSMENU` class constant.
It is a `WC_MENU` control instance carrying the frame-control id `FID_SYSMENU` (`0x8002`)
[DOC-IBM `pmwin.h:241-262` (no `WC_SYSMENU` present); `FID_SYSMENU` in `pm-window-messaging.md`
section 4]. It is manipulated with the menu messages of section 5.

---

## 4. `WC_BUTTON` - buttons and boxes [DOC-IBM]

A button control is a small rectangular child window the operator can "switch" on or off by
clicking it or by pressing the space bar when it has the focus. Buttons may be used alone or in
groups, labeled or not, and change appearance when clicked; a disabled button is drawn in a
different emphasis and does not respond [DOC-IBM pm3.txt "Button Control Window Processing"].

**Button styles** (`BS_*`) [DOC-IBM `pmwin.h:1979-2003`; meanings pm3.txt "Button Control
Styles"]:

| Constant | Value | Meaning |
|---|---|---|
| `BS_PUSHBUTTON` | `0` | A box containing a string; notifies the parent when pushed. |
| `BS_CHECKBOX` | `1` | A square with a label; checked/unchecked; the owner sets the state. |
| `BS_AUTOCHECKBOX` | `2` | Check box that toggles its own state on click. |
| `BS_RADIOBUTTON` | `3` | Like a check box, used in groups where one is checked; owner manages the group. |
| `BS_AUTORADIOBUTTON` | `4` | Radio button that checks itself and unchecks the others in its group automatically. |
| `BS_3STATE` | `5` | Check box that can also be half-toned (a third, indeterminate state). |
| `BS_AUTO3STATE` | `6` | Three-state check box that cycles its state on click. |
| `BS_USERBUTTON` | `7` | Application-drawn button; its owner receives `BN_PAINT`. |
| `BS_NOTEBOOKBUTTON` | `8` | A push button that becomes part of a notebook page's common button area when it is a child of a notebook page. |
| `BS_TEXT` | `0x0010` | Text on the button (combine with `BS_BITMAP`/`BS_ICON`/`BS_MINIICON` to show both). |
| `BS_MINIICON` | `0x0020` | A mini-icon (half-size) on a push button. |
| `BS_BITMAP` | `0x0040` | A bitmap instead of text (push button only). |
| `BS_ICON` | `0x0080` | An icon instead of text (push button only). |
| `BS_HELP` | `0x0100` | Posts `WM_HELP` instead of `WM_COMMAND`. |
| `BS_SYSCOMMAND` | `0x0200` | Posts `WM_SYSCOMMAND` instead of `WM_COMMAND`. |
| `BS_DEFAULT` | `0x0400` | Default push button (thick border); also activated by Enter/Return. |
| `BS_NOPOINTERFOCUS` | `0x0800` | Does not take the focus when clicked with the pointer. |
| `BS_NOBORDER` | `0x1000` | Push button drawn without a border. |
| `BS_NOCURSORSELECT` | `0x2000` | Auto-radio button does not select itself merely on gaining focus by arrow/tab. |
| `BS_AUTOSIZE` | `0x4000` | The button sizes itself to fit its contents. |
| `BS_PRIMARYSTYLES` | `0x000F` | Mask of the primary (mutually exclusive) button types. |

**Button messages** (`BM_*`) [DOC-IBM `pmwin.h:2042-2049`]:

| Message | Value | Purpose |
|---|---|---|
| `BM_CLICK` | `0x0120` | Simulate a click (as if the operator pressed the button). |
| `BM_QUERYCHECKINDEX` | `0x0121` | Return the 0-based index of the checked button within its group. |
| `BM_QUERYHILITE` | `0x0122` | Query the highlight (pressed) state. |
| `BM_SETHILITE` | `0x0123` | Set the highlight state. |
| `BM_QUERYCHECK` | `0x0124` | Query the check state (0 unchecked, 1 checked, 2 indeterminate). |
| `BM_SETCHECK` | `0x0125` | Set the check state. |
| `BM_SETDEFAULT` | `0x0126` | Set/clear the default-button emphasis. |
| `BM_AUTOSIZE` | `0x0128` | Resize the button to fit its contents. |

**Button notifications** (`BN_*`), delivered in `WM_CONTROL` / (for push buttons) `WM_COMMAND`
[DOC-IBM `pmwin.h:2053-2055`; meanings pm3.txt "WM_CONTROL (in Button Controls)"]:

| Code | Value | Meaning |
|---|---|---|
| `BN_CLICKED` | `1` | The button has been pressed. |
| `BN_DBLCLICKED` | `2` | The button has been double-clicked. |
| `BN_PAINT` | `3` | A `BS_USERBUTTON` requires painting; `mp2` points to a `USERBUTTON` giving the draw state (`BDS_DISABLED`/`BDS_HILITED`/`BDS_DEFAULT`). |

**Button control data** - passed as `pCtlData` at creation [DOC-IBM `pmwin.h:2014-2020`]:

```c
typedef struct _BTNCDATA {   /* btncd */
    USHORT  cb;
    USHORT  fsCheckState;    /* initial check state    */
    USHORT  fsHiliteState;   /* initial highlight state */
    LHANDLE hImage;          /* bitmap/icon handle      */
} BTNCDATA;
```

The owner-draw payload for `BN_PAINT` [DOC-IBM `pmwin.h:2030-2036`]:

```c
typedef struct _USERBUTTON {   /* ubtn */
    HWND    hwnd;
    HPS     hps;
    ULONG   fsState;
    ULONG   fsStateOld;
} USERBUTTON;
```

---

## 5. `WC_MENU` - menus [DOC-IBM]

A menu presents a list of items, shown horizontally as an action bar or vertically as a
pull-down; menus are the usual command interface [DOC-IBM pm3.txt "Control Window Message
Processing"]. Selecting an item posts `WM_COMMAND` (or `WM_SYSCOMMAND`/`WM_HELP`) to the owner
with `CMDSRC_MENU`.

**Menu messages** (`MM_*`) [DOC-IBM `pmwin.h:2381-2403`]:

| Message | Value | Purpose |
|---|---|---|
| `MM_INSERTITEM` | `0x0180` | Insert a menu item (`MENUITEM` + text). |
| `MM_DELETEITEM` | `0x0181` | Delete an item and its resources. |
| `MM_QUERYITEM` | `0x0182` | Copy an item's `MENUITEM` into a caller buffer. |
| `MM_SETITEM` | `0x0183` | Set an item's `MENUITEM`. |
| `MM_QUERYITEMCOUNT` | `0x0184` | Number of items in the menu. |
| `MM_STARTMENUMODE` | `0x0185` | Enter menu (interaction) mode. |
| `MM_ENDMENUMODE` | `0x0186` | Leave menu mode. |
| `MM_REMOVEITEM` | `0x0188` | Remove an item without freeing its resources. |
| `MM_SELECTITEM` | `0x0189` | Select (highlight) an item. |
| `MM_QUERYSELITEMID` | `0x018a` | Id of the selected item. |
| `MM_QUERYITEMTEXT` | `0x018b` | Copy an item's text. |
| `MM_QUERYITEMTEXTLENGTH` | `0x018c` | Length of an item's text. |
| `MM_SETITEMHANDLE` | `0x018d` | Set an item's handle (`hItem`). |
| `MM_SETITEMTEXT` | `0x018e` | Set an item's text. |
| `MM_ITEMPOSITIONFROMID` | `0x018f` | Position of an item given its id. |
| `MM_ITEMIDFROMPOSITION` | `0x0190` | Id of an item given its position. |
| `MM_QUERYITEMATTR` | `0x0191` | Query an item's attributes (`MIA_*`). |
| `MM_SETITEMATTR` | `0x0192` | Set an item's attributes. |
| `MM_ISITEMVALID` | `0x0193` | Whether an item can be selected. |
| `MM_QUERYITEMRECT` | `0x0194` | Bounding rectangle of an item. |
| `MM_QUERYDEFAULTITEMID` | `0x0431` | Id of the default item. |
| `MM_SETDEFAULTITEMID` | `0x0432` | Set the default item. |

**Menu-item styles** (`MIS_*`, the `MENUITEM.afStyle` field) [DOC-IBM `pmwin.h:2481-2503`]:
`MIS_TEXT` (`0x0001`), `MIS_BITMAP` (`0x0002`), `MIS_SEPARATOR` (`0x0004`), `MIS_OWNERDRAW`
(`0x0008`), `MIS_SUBMENU` (`0x0010`), `MIS_MULTMENU` (`0x0020`), `MIS_SYSCOMMAND` (`0x0040`),
`MIS_HELP` (`0x0080`), `MIS_STATIC` (`0x0100`), `MIS_BUTTONSEPARATOR` (`0x0200`), `MIS_BREAK`
(`0x0400`), `MIS_BREAKSEPARATOR` (`0x0800`), `MIS_GROUP` (`0x1000`), `MIS_SINGLE` (`0x2000`).

**Menu-item attributes** (`MIA_*`, the `MENUITEM.afAttribute` field) [DOC-IBM `pmwin.h:2505-2509`]:
`MIA_NODISMISS` (`0x0020`), `MIA_FRAMED` (`0x1000`), `MIA_CHECKED` (`0x2000`), `MIA_DISABLED`
(`0x4000`), `MIA_HILITED` (`0x8000`).

**`MENUITEM`** - one menu entry [DOC-IBM `pmwin.h:2457-2464`]:

```c
typedef struct _MENUITEM {   /* mi */
    SHORT   iPosition;       /* position within the menu           */
    USHORT  afStyle;         /* MIS_* item style                   */
    USHORT  afAttribute;     /* MIA_* item attributes              */
    USHORT  id;              /* command id                         */
    HWND    hwndSubMenu;     /* submenu window (if MIS_SUBMENU)     */
    ULONG   hItem;           /* item handle (bitmap/owner data)     */
} MENUITEM;
```

### 5.1 A pop-up menu built at run time - the two traps [OBS-RE]

A context menu whose items depend on state has to be built dynamically: create a menu window, fill it
with `MM_INSERTITEM`, then `WinPopupMenu`. Both traps below leave every API call reporting success -
`WinPopupMenu` returns `TRUE`, `WinGetLastError` is `0`, and the menu window is real, correctly sized
and `WS_VISIBLE` - while nothing appears on screen. There is no diagnostic to find.

**1. Do not destroy the menu after `WinPopupMenu` returns.** It "returns as soon as the pop-up menu
has been invoked, **which might be before the user has completed interacting with** it" [DOC-IBM
`pm2.txt`, *WinPopupMenu - Return Value*]. It is not modal and does not wait for a selection, so
tearing the menu down on the next line removes it instantly. Destroy the *previous* menu when you
build the next one instead.

**2. Do not raise it from inside a `WM_COMMAND` handler.** A pop-up shown while PM is still unwinding
accelerator or menu-bar processing is dismissed again as that unwinds. This is the one that survives
every plausible fix, because the call itself succeeds. **Post yourself a private message and show the
menu when that arrives**, so it comes up from a clean dispatch:

```c
case IDM_CONTEXTMENU:                      /* accelerator or menu item */
    WinPostMsg(hwndTarget, WM_MYCONTEXTMENU, 0, 0);
    break;

case WM_MYCONTEXTMENU:                     /* clean dispatch - the menu survives */
    hwndMenu = WinCreateWindow(HWND_DESKTOP, WC_MENU, "", MS_VERTICALFLIP,
                               0, 0, 0, 0, HWND_DESKTOP, HWND_TOP, 0, NULL, NULL);
    /* ... MM_INSERTITEM per item ... */
    WinPopupMenu(hwnd, hwnd, hwndMenu, x, y, 0,
                 PU_HCONSTRAIN | PU_VCONSTRAIN | PU_MOUSEBUTTON1 | PU_KEYBOARD);
    break;
```

Reaching this from a mouse click needs no such care - `WM_BUTTON2DOWN` *is* a clean dispatch, and
button 2 is the OS/2 context button (there is no `WM_CONTEXTMENU`).

Two further points measured while chasing the above, both worth not re-testing:

- IBM states the menu "must have been created, by use of either the `WinCreateMenu` or `WinLoadMenu`
  functions" [DOC-IBM `pm2.txt`, *WinPopupMenu - Parameters*]. In practice a `WC_MENU` window created
  with `WinCreateWindow` and filled with `MM_INSERTITEM` works, which is what a dynamic menu needs;
  a resource menu loaded with `WinLoadMenu` behaved identically, including failing in the same way
  before trap 2 was fixed.
- The `hwndParent` argument may be either `HWND_DESKTOP` (with the position mapped by
  `WinMapWindowPoints`) or the owning window itself (with window-relative coordinates). Both display
  correctly; `PU_HCONSTRAIN`/`PU_VCONSTRAIN` constrain to the desktop either way.

Remember PM's origin is the **lower-left** corner, so the coordinates you pass are the menu's bottom
edge and it grows *upward* from the point - the opposite of the Win32 habit of dropping down from it.

An empty label is not a PM convention but Scintilla's, meaning "separator"; PM wants
`MIS_SEPARATOR` in `afStyle`, and `MIA_DISABLED` in `afAttribute` for a greyed item.

---

## 6. `WC_STATIC` - static display items [DOC-IBM]

A static control is a simple display item - text, an icon, a bitmap, a box, or a filled/framed
rectangle - that does not respond to keyboard or pointer events [DOC-IBM pm3.txt "Static Control
Window Processing"]. It sends no notifications of its own.

**Static styles** (`SS_*`) [DOC-IBM `pmwin.h:1942-1960`; meanings pm3.txt "Static Control
Styles"]:

| Constant | Value | Meaning |
|---|---|---|
| `SS_TEXT` | `0x0001` | Formatted text; combine with `DT_*` alignment flags in the low style byte. |
| `SS_GROUPBOX` | `0x0002` | A box with a label in its upper-left corner, used to group controls. |
| `SS_ICON` | `0x0003` | An icon named by the control text (resource id). |
| `SS_BITMAP` | `0x0004` | A bitmap named by the control text. |
| `SS_FGNDRECT` | `0x0005` | Rectangle filled with the foreground color. |
| `SS_HALFTONERECT` | `0x0006` | Rectangle filled with halftone shading. |
| `SS_BKGNDRECT` | `0x0007` | Rectangle filled with the background color. |
| `SS_FGNDFRAME` | `0x0008` | Box framed in the foreground color. |
| `SS_HALFTONEFRAME` | `0x0009` | Box with a halftone-shaded frame. |
| `SS_BKGNDFRAME` | `0x000a` | Box framed in the background color. |
| `SS_SYSICON` | `0x000b` | A system icon named by an `SPTR_*` id. |
| `SS_AUTOSIZE` | `0x0040` | The control sizes itself to fit its contents. |

---

## 7. `WC_ENTRYFIELD` - single-line entry field [DOC-IBM]

An entry field is a single line of text the operator can edit; when it has the focus, a cursor
marks the insertion point [DOC-IBM pm3.txt "Entry Field Control Window Processing"].

**Entry-field styles** (`ES_*`) [DOC-IBM `pmwin.h:2074-2093`; meanings pm3.txt "Entry Field
Control Styles"]:

| Constant | Value | Meaning |
|---|---|---|
| `ES_LEFT` | `0x0000` | Left-justified text (default). |
| `ES_CENTER` | `0x0001` | Centered text. |
| `ES_RIGHT` | `0x0002` | Right-justified text. |
| `ES_AUTOSCROLL` | `0x0004` | Scroll automatically when the cursor moves off the visible end. |
| `ES_MARGIN` | `0x0008` | Draw a border with a margin around the editable text. |
| `ES_AUTOTAB` | `0x0010` | Generate a tab automatically when the field fills. |
| `ES_READONLY` | `0x0020` | Created read-only (text cannot be inserted). |
| `ES_COMMAND` | `0x0040` | Marks the field as a command entry field (for Help Manager command help). |
| `ES_UNREADABLE` | `0x0080` | Display each character as an asterisk (passwords). |
| `ES_AUTOSIZE` | `0x0200` | The field sizes itself to fit its contents. |
| `ES_SBCS` | `0x1000` | Single-byte text only (DBCS environments). |
| `ES_DBCS` | `0x2000` | Double-byte text only. |
| `ES_MIXED` | `0x3000` | Mixed SBCS/DBCS, protected against conversion overrun. |

(`ES_ANY` = `0x0000` - mixed SBCS/DBCS, the default when no DBCS style is set.)

**Entry-field messages** (`EM_*`) [DOC-IBM `pmwin.h:2172-2190`]:

| Message | Value | Purpose |
|---|---|---|
| `EM_QUERYCHANGED` | `0x0140` | Whether the text changed since the last query. |
| `EM_QUERYSEL` | `0x0141` | Query the selection (min/max character offsets). |
| `EM_SETSEL` | `0x0142` | Set the selection. |
| `EM_SETTEXTLIMIT` | `0x0143` | Set the maximum number of characters. |
| `EM_CUT` | `0x0144` | Cut the selection to the clipboard. |
| `EM_COPY` | `0x0145` | Copy the selection to the clipboard. |
| `EM_CLEAR` | `0x0146` | Delete the selection. |
| `EM_PASTE` | `0x0147` | Paste the clipboard over the selection. |
| `EM_QUERYFIRSTCHAR` | `0x0148` | Offset of the first visible character. |
| `EM_SETFIRSTCHAR` | `0x0149` | Scroll so a given character is first visible. |
| `EM_QUERYREADONLY` | `0x014a` | Query the read-only state. |
| `EM_SETREADONLY` | `0x014b` | Set the read-only state. |
| `EM_SETINSERTMODE` | `0x014c` | Set insert vs. overtype mode. |

**Entry-field notifications** (`EN_*`) in `WM_CONTROL` [DOC-IBM `pmwin.h:2195-2202`]:

| Code | Value | Meaning |
|---|---|---|
| `EN_SETFOCUS` | `0x0001` | The field gained the focus. |
| `EN_KILLFOCUS` | `0x0002` | The field lost the focus. |
| `EN_CHANGE` | `0x0004` | The text changed. |
| `EN_SCROLL` | `0x0008` | The field scrolled. |
| `EN_MEMERROR` | `0x0010` | Out of memory. |
| `EN_OVERFLOW` | `0x0020` | The text limit was exceeded. |
| `EN_INSERTMODETOGGLE` | `0x0040` | Insert/overtype mode toggled. |

**Entry-field control data** [DOC-IBM `pmwin.h:2156-2162`]:

```c
typedef struct _ENTRYFDATA {   /* efd */
    USHORT  cb;
    USHORT  cchEditLimit;      /* max characters                 */
    USHORT  ichMinSel;         /* selection start                */
    USHORT  ichMaxSel;         /* selection end                  */
    PVOID   pHWXCtlData;       /* reserved                       */
} ENTRYFDATA;
```

---

## 8. `WC_MLE` - multi-line entry field [DOC-IBM]

The multi-line entry field (MLE) is a rectangular window displaying multiple editable lines;
the cursor marks the insertion/replacement point when it has the focus [DOC-IBM pm3.txt
"Multi-Line Entry Field Control Window Processing"]. It supports word-wrap, undo, import/export
of text, and clipboard operations.

**MLE styles** (`MLS_*`) [DOC-IBM `pmmle.h:46-53`]:

| Constant | Value | Meaning |
|---|---|---|
| `MLS_WORDWRAP` | `0x0001` | Wrap text at word boundaries. |
| `MLS_BORDER` | `0x0002` | Draw a border around the control. |
| `MLS_VSCROLL` | `0x0004` | Include a vertical scroll bar. |
| `MLS_HSCROLL` | `0x0008` | Include a horizontal scroll bar. |
| `MLS_READONLY` | `0x0010` | Created read-only. |
| `MLS_IGNORETAB` | `0x0020` | Tab moves to the next control instead of inserting a tab. |
| `MLS_DISABLEUNDO` | `0x0040` | Disable the undo facility. |
| `MLS_LIMITVSCROLL` | `0x0080` | Limit vertical scrolling. |

**MLE messages** (`MLM_*`) - the fuller set [DOC-IBM `pmmle.h:192-256`]:

| Message | Value | Purpose |
|---|---|---|
| `MLM_SETTEXTLIMIT` / `MLM_QUERYTEXTLIMIT` | `0x01b0` / `0x01b1` | Set/query the maximum text length. |
| `MLM_SETFORMATRECT` / `MLM_QUERYFORMATRECT` | `0x01b2` / `0x01b3` | Set/query the formatting rectangle. |
| `MLM_SETWRAP` / `MLM_QUERYWRAP` | `0x01b4` / `0x01b5` | Set/query word-wrap. |
| `MLM_SETTABSTOP` / `MLM_QUERYTABSTOP` | `0x01b6` / `0x01b7` | Set/query tab-stop spacing. |
| `MLM_SETREADONLY` / `MLM_QUERYREADONLY` | `0x01b8` / `0x01b9` | Set/query read-only state. |
| `MLM_QUERYCHANGED` / `MLM_SETCHANGED` | `0x01ba` / `0x01bb` | Query/set the changed flag. |
| `MLM_QUERYLINECOUNT` | `0x01bc` | Number of lines. |
| `MLM_CHARFROMLINE` / `MLM_LINEFROMCHAR` | `0x01bd` / `0x01be` | Convert between line number and character offset. |
| `MLM_QUERYLINELENGTH` / `MLM_QUERYTEXTLENGTH` | `0x01bf` / `0x01c0` | Length of a line / of all text. |
| `MLM_FORMAT` | `0x01c1` | Set the import/export text format. |
| `MLM_SETIMPORTEXPORT` | `0x01c2` | Set the import/export buffer. |
| `MLM_IMPORT` / `MLM_EXPORT` | `0x01c3` / `0x01c4` | Import/export text through the buffer. |
| `MLM_DELETE` | `0x01c6` | Delete a range of text. |
| `MLM_QUERYFORMATLINELENGTH` / `MLM_QUERYFORMATTEXTLENGTH` | `0x01c7` / `0x01c8` | Formatted line / text length. |
| `MLM_INSERT` | `0x01c9` | Insert text at the cursor. |
| `MLM_SETSEL` / `MLM_QUERYSEL` / `MLM_QUERYSELTEXT` | `0x01ca` / `0x01cb` / `0x01cc` | Set/query the selection; copy the selected text. |
| `MLM_QUERYUNDO` / `MLM_UNDO` / `MLM_RESETUNDO` | `0x01cd` / `0x01ce` / `0x01cf` | Query, perform, reset undo. |
| `MLM_QUERYFONT` / `MLM_SETFONT` | `0x01d0` / `0x01d1` | Query/set the font. |
| `MLM_SETTEXTCOLOR` / `MLM_QUERYTEXTCOLOR` | `0x01d2` / `0x01d3` | Set/query the text color. |
| `MLM_SETBACKCOLOR` / `MLM_QUERYBACKCOLOR` | `0x01d4` / `0x01d5` | Set/query the background color. |
| `MLM_QUERYFIRSTCHAR` / `MLM_SETFIRSTCHAR` | `0x01d6` / `0x01d7` | Query/set the first visible character. |
| `MLM_CUT` / `MLM_COPY` / `MLM_PASTE` / `MLM_CLEAR` | `0x01d8`-`0x01db` | Clipboard operations and delete. |
| `MLM_ENABLEREFRESH` / `MLM_DISABLEREFRESH` | `0x01dc` / `0x01dd` | Enable/suspend screen refresh during bulk edits. |
| `MLM_SEARCH` | `0x01de` | Search (and optionally replace) text. |
| `MLM_QUERYIMPORTEXPORT` | `0x01df` | Query the import/export buffer. |

**MLE notifications** (`MLN_*`) in `WM_CONTROL` [DOC-IBM `pmmle.h:259-272`]:

| Code | Value | Meaning |
|---|---|---|
| `MLN_OVERFLOW` | `0x0001` | An operation would exceed the text limit. |
| `MLN_PIXHORZOVERFLOW` | `0x0002` | Horizontal pixel overflow. |
| `MLN_PIXVERTOVERFLOW` | `0x0003` | Vertical pixel overflow. |
| `MLN_TEXTOVERFLOW` | `0x0004` | Text overflow. |
| `MLN_VSCROLL` / `MLN_HSCROLL` | `0x0005` / `0x0006` | Vertical / horizontal scroll occurred. |
| `MLN_CHANGE` | `0x0007` | The text changed. |
| `MLN_SETFOCUS` / `MLN_KILLFOCUS` | `0x0008` / `0x0009` | Focus gained / lost. |
| `MLN_MARGIN` | `0x000a` | A pointer event occurred in the margin. |
| `MLN_SEARCHPAUSE` | `0x000b` | A search paused (to allow the app to continue it). |
| `MLN_MEMERROR` | `0x000c` | Out of memory. |
| `MLN_UNDOOVERFLOW` | `0x000d` | The undo buffer overflowed. |
| `MLN_CLPBDFAIL` | `0x000f` | A clipboard operation failed. |

---

## 9. `WC_LISTBOX` - list box [DOC-IBM]

A list box presents a list of text items from which the operator makes selections [DOC-IBM
pm3.txt "List Box Control Window Processing"].

**List-box styles** (`LS_*`) [DOC-IBM `pmwin.h:2218-2227`]:

| Constant | Value | Meaning |
|---|---|---|
| `LS_MULTIPLESEL` | `0x0001` | Allow multiple items selected at once. |
| `LS_OWNERDRAW` | `0x0002` | The owner draws the items (`WM_DRAWITEM`/`WM_MEASUREITEM`). |
| `LS_NOADJUSTPOS` | `0x0004` | Do not adjust the control size to a whole number of items. |
| `LS_HORZSCROLL` | `0x0008` | Provide a horizontal scroll bar. |
| `LS_EXTENDEDSEL` | `0x0010` | Extended selection (ranges). |

**List-box messages** (`LM_*`) [DOC-IBM `pmwin.h:2240-2257`]:

| Message | Value | Purpose |
|---|---|---|
| `LM_QUERYITEMCOUNT` | `0x0160` | Number of items. |
| `LM_INSERTITEM` | `0x0161` | Insert an item (index or `LIT_END`/`LIT_SORTASCENDING`/...). |
| `LM_SETTOPINDEX` | `0x0162` | Scroll so a given item is at the top. |
| `LM_DELETEITEM` | `0x0163` | Delete an item. |
| `LM_SELECTITEM` | `0x0164` | Select/deselect an item. |
| `LM_QUERYSELECTION` | `0x0165` | Index of the (next) selected item. |
| `LM_SETITEMTEXT` | `0x0166` | Set an item's text. |
| `LM_QUERYITEMTEXTLENGTH` | `0x0167` | Length of an item's text. |
| `LM_QUERYITEMTEXT` | `0x0168` | Copy an item's text. |
| `LM_SETITEMHANDLE` | `0x0169` | Set an item's application handle. |
| `LM_QUERYITEMHANDLE` | `0x016a` | Query an item's handle. |
| `LM_SEARCHSTRING` | `0x016b` | Find an item by text. |
| `LM_SETITEMHEIGHT` | `0x016c` | Set the item height. |
| `LM_QUERYTOPINDEX` | `0x016d` | Index of the top visible item. |
| `LM_DELETEALL` | `0x016e` | Delete all items. |
| `LM_INSERTMULTITEMS` | `0x016f` | Insert several items at once. |
| `LM_SETITEMWIDTH` | `0x0660` | Set the horizontal-scroll item width. |

**List-box notifications** (`LN_*`) in `WM_CONTROL` [DOC-IBM `pmwin.h:2232-2236`]:

| Code | Value | Meaning |
|---|---|---|
| `LN_SELECT` | `1` | The selection changed. |
| `LN_SETFOCUS` | `2` | The list box gained the focus. |
| `LN_KILLFOCUS` | `3` | The list box lost the focus. |
| `LN_SCROLL` | `4` | The list scrolled. |
| `LN_ENTER` | `5` | An item was chosen (double-click / Enter). |

Item-index constants used with `LM_*` [DOC-IBM `pmwin.h:2262-2272`]: `LIT_CURSOR` (`-4`),
`LIT_ERROR` (`-3`), `LIT_MEMERROR` (`-2`), `LIT_NONE`/`LIT_FIRST`/`LIT_END` (`-1`),
`LIT_SORTASCENDING` (`-2`), `LIT_SORTDESCENDING` (`-3`).

### 9.1 Owner-drawn items, and where the selection state really lives [OBS-RE]

A plain list box "only draws items that are represented by text strings and emphasizes selected items
by inverting them" [DOC-IBM `pm3.txt`, *WM_DRAWITEM (in List Boxes) - Remarks*]. Anything else - a
per-item icon, a colour, two-column layout - needs the **`LS_OWNERDRAW`** style, after which the
control sends **`WM_DRAWITEM`** to its **owner** for each item. Returning `TRUE` means "I drew it";
returning `FALSE` asks the control to draw it after all, which is the right answer for any control
that is not yours.

**The item's selected state is in `OWNERITEM.fsState`, not in `LM_QUERYSELECTION`.** This is the trap.
Asking the control which item is selected *while handling `WM_DRAWITEM`* returns `LIT_NONE` - the
selection has not been committed yet - so the obvious implementation quietly draws every item,
including the highlighted one, in unselected colours:

```c
case WM_DRAWITEM: {
    POWNERITEM poi = (POWNERITEM)PVOIDFROMMP(mp2);
    /* WRONG: answers LIT_NONE for every item at this point.
       BOOL sel = (SHORT1FROMMR(WinSendMsg(poi->hwnd, LM_QUERYSELECTION,
                                MPFROMSHORT(LIT_FIRST), 0)) == poi->idItem); */
    BOOL sel = (poi->fsState & 1) != 0;      /* observed value; no LIA_* constant exists */
    ...
    return MRFROMLONG(TRUE);
}
```

`os2emx.h` defines no `LIA_*` constant for that bit, so it has to be written as a literal with a
comment - the value was measured as `1` on a selected item and `0` otherwise.

The rest of the item comes from where you would expect: `LM_QUERYITEMTEXT` for the text (the item
text must not be changed while drawing it), `OWNERITEM.rclItem` for the rectangle in **window**
coordinates, and `OWNERITEM.hps` for the presentation space. Two practical notes: `rclItem` is PM
y-up, so anything drawing in a top-down coordinate system must flip it against the list box's own
height; and item height is set with `LM_SETITEMHEIGHT` rather than by answering `WM_MEASUREITEM`,
which is simpler when the height depends on content you register later.

---

## 10. `WC_COMBOBOX` - combination box [DOC-IBM]

A combination box merges an entry field and a list box into one control; the list is displayed
below the entry field [DOC-IBM pm3.txt "Combination-Box Control Window Processing"]. Because it
is composed of the two, it also accepts the `EM_*` and `LM_*` messages of its parts.

**Combo-box styles** (`CBS_*`) [DOC-IBM `pmwin.h:2100-2110`]:

| Constant | Value | Meaning |
|---|---|---|
| `CBS_SIMPLE` | `0x0001` | Entry field with the list box always displayed. |
| `CBS_DROPDOWN` | `0x0002` | Entry field with a drop-down list the user opens. |
| `CBS_DROPDOWNLIST` | `0x0004` | Drop-down list only; the entry field is read-only (choose from the list). |
| `CBS_COMPATIBLE` | `0x0008` | Size the control for compatibility with earlier releases. |

**Combo-box messages** (`CBM_*`) [DOC-IBM `pmwin.h:2124-2126`]:

| Message | Value | Purpose |
|---|---|---|
| `CBM_SHOWLIST` | `0x0170` | Show or hide the drop-down list. |
| `CBM_HILITE` | `0x0171` | Highlight the entry field. |
| `CBM_ISLISTSHOWING` | `0x0172` | Whether the list is currently displayed. |

**Combo-box notifications** (`CBN_*`) in `WM_CONTROL` [DOC-IBM `pmwin.h:2128-2134`]:

| Code | Value | Meaning |
|---|---|---|
| `CBN_EFCHANGE` | `1` | The entry-field text changed. |
| `CBN_EFSCROLL` | `2` | The entry field scrolled. |
| `CBN_MEMERROR` | `3` | Out of memory. |
| `CBN_LBSELECT` | `4` | An item was selected in the list. |
| `CBN_LBSCROLL` | `5` | The list scrolled. |
| `CBN_SHOWLIST` | `6` | The list was shown/hidden. |
| `CBN_ENTER` | `7` | An item was chosen (Enter/double-click). |

---

## 11. `WC_SCROLLBAR` - scroll bar [DOC-IBM]

A scroll bar lets the operator request scrolling of an associated window's contents [DOC-IBM
pm3.txt "Scroll Bar Control Window Processing"]. A standalone scroll bar sends `WM_HSCROLL` /
`WM_VSCROLL` to its owner; the frame's `FID_HORZSCROLL` / `FID_VERTSCROLL` scroll bars send
those to the frame.

**Scroll-bar messages** (`SBM_*`) [DOC-IBM `pmwin.h:2618-2622`]:

| Message | Value | Purpose |
|---|---|---|
| `SBM_SETSCROLLBAR` | `0x01a0` | Set the slider position and range in one message. |
| `SBM_SETPOS` | `0x01a1` | Set the slider (thumb) position. |
| `SBM_QUERYPOS` | `0x01a2` | Query the slider position. |
| `SBM_QUERYRANGE` | `0x01a3` | Query the scroll range (min/max). |
| `SBM_SETTHUMBSIZE` | `0x01a6` | Set the proportional thumb size (visible vs. total). |

**Scroll commands** (`SB_*`) - carried in the high half of `mp2` of `WM_HSCROLL` / `WM_VSCROLL`
[DOC-IBM `pmwin.h:2626-2636`]:

| Command | Value | Meaning |
|---|---|---|
| `SB_LINEUP` / `SB_LINELEFT` | `1` | Scroll one line up / left. |
| `SB_LINEDOWN` / `SB_LINERIGHT` | `2` | Scroll one line down / right. |
| `SB_PAGEUP` / `SB_PAGELEFT` | `3` | Scroll one page up / left. |
| `SB_PAGEDOWN` / `SB_PAGERIGHT` | `4` | Scroll one page down / right. |
| `SB_SLIDERTRACK` | `5` | The slider is being dragged (tracking). |
| `SB_SLIDERPOSITION` | `6` | The slider was released at a new position. |
| `SB_ENDSCROLL` | `7` | Scrolling ended (no more `SB_*` follow). |

**Scroll-bar control data** [DOC-IBM `pmwin.h:2646-2655`]:

```c
typedef struct _SBCDATA {   /* sbcd */
    USHORT  cb;
    USHORT  sHilite;        /* reserved, set to 0        */
    SHORT   posFirst;       /* range minimum             */
    SHORT   posLast;        /* range maximum             */
    SHORT   posThumb;       /* initial thumb position    */
    SHORT   cVisible;       /* visible units (thumb size)*/
    SHORT   cTotal;         /* total units               */
} SBCDATA;
```

---

## 12. `WC_SPINBUTTON` - spin button [DOC-IBM]

A spin button presents a scrollable ring of choices - either a numeric range or an
application-supplied array of strings - the operator spins through with up/down arrows [DOC-IBM
pm3.txt "Spin Button Control Window Processing"]. A **master** spin button owns the entry-field
and arrow visuals; one or more **servant** spin buttons share a master.

**Spin-button styles** (`SPBS_*`) [DOC-IBM `pmstddlg.h:527-561`]:

| Constant | Value | Meaning |
|---|---|---|
| `SPBS_ALLCHARACTERS` | `0x0000` | Accept any character in the field (default). |
| `SPBS_NUMERICONLY` | `0x0001` | Accept only digits and navigation keys. |
| `SPBS_READONLY` | `0x0002` | The entry field is not editable. |
| `SPBS_JUSTRIGHT` | `0x0004` | Right-justify the field text. |
| `SPBS_JUSTLEFT` | `0x0008` | Left-justify the field text. |
| `SPBS_JUSTCENTER` | `0x000C` | Center the field text. |
| `SPBS_MASTER` | `0x0010` | This is the master spin button. |
| `SPBS_SERVANT` | `0x0000` | This is a servant spin button (default). |
| `SPBS_NOBORDER` | `0x0020` | Borderless spin field. |
| `SPBS_PADWITHZEROS` | `0x0080` | Pad numbers with leading zeros. |
| `SPBS_FASTSPIN` | `0x0100` | Allow accelerated spinning. |

**Spin-button messages** (`SPBM_*`) [DOC-IBM `pmstddlg.h:581-605`]:

| Message | Value | Purpose |
|---|---|---|
| `SPBM_OVERRIDESETLIMITS` | `0x200` | Set the spin limits, overriding validation. |
| `SPBM_QUERYLIMITS` | `0x201` | Query the current numeric limits. |
| `SPBM_SETTEXTLIMIT` | `0x202` | Set the maximum entry-field character count. |
| `SPBM_SPINUP` | `0x203` | Spin the value up. |
| `SPBM_SPINDOWN` | `0x204` | Spin the value down. |
| `SPBM_QUERYVALUE` | `0x205` | Retrieve the current value (text or numeric). |
| `SPBM_SETARRAY` | `0x206` | Set the array of strings to spin through. |
| `SPBM_SETLIMITS` | `0x207` | Set the numeric lower/upper limits. |
| `SPBM_SETCURRENTVALUE` | `0x208` | Set the current value. |
| `SPBM_SETMASTER` | `0x209` | Tell a servant which spin button is its master. |

**Spin-button notifications** (`SPBN_*`) in `WM_CONTROL` [DOC-IBM `pmstddlg.h:571-576`]:

| Code | Value | Meaning |
|---|---|---|
| `SPBN_UPARROW` | `0x20A` | The up arrow was pressed. |
| `SPBN_DOWNARROW` | `0x20B` | The down arrow was pressed. |
| `SPBN_ENDSPIN` | `0x20C` | The mouse button was released (spinning ended). |
| `SPBN_CHANGE` | `0x20D` | The spin-field text changed. |
| `SPBN_SETFOCUS` | `0x20E` | The spin field gained the focus. |
| `SPBN_KILLFOCUS` | `0x20F` | The spin field lost the focus. |

**Spin-button control data** [DOC-IBM `pmstddlg.h:611-619`]:

```c
typedef struct _SPBCDATA {   /* spbcd */
    ULONG   cbSize;
    ULONG   ulTextLimit;     /* entry-field text limit       */
    LONG    lLowerLimit;     /* numeric lower limit          */
    LONG    lUpperLimit;     /* numeric upper limit          */
    ULONG   idMasterSpb;     /* servant's master id          */
    PVOID   pHWXCtlData;     /* reserved                     */
} SPBCDATA;
```

---

## 13. `WC_SLIDER` - slider [DOC-IBM]

A slider lets the user set, display, or modify a value by moving an arm along a shaft [DOC-IBM
pm3.txt "Slider Control Window Processing"]. It carries a scale of tick marks, optional detents,
and optional spin buttons at the shaft ends.

**Slider styles** (`SLS_*`) [DOC-IBM `pmstddlg.h:1709-1729`] - orientation, shaft placement, and
behavior, including: `SLS_HORIZONTAL` (`0x0000`) / `SLS_VERTICAL` (`0x0001`); `SLS_CENTER`
(`0x0000`), `SLS_BOTTOM`/`SLS_LEFT` (`0x0002`), `SLS_TOP`/`SLS_RIGHT` (`0x0004`) shaft offset;
`SLS_SNAPTOINCREMENT` (`0x0008`) snap to the nearest tick; `SLS_BUTTONSBOTTOM`/`SLS_BUTTONSLEFT`
(`0x0010`), `SLS_BUTTONSTOP`/`SLS_BUTTONSRIGHT` (`0x0020`) end buttons; `SLS_OWNERDRAW`
(`0x0040`); `SLS_READONLY` (`0x0080`); `SLS_RIBBONSTRIP` (`0x0100`); `SLS_HOMETOP`/`SLS_HOMERIGHT`
(`0x0200`); `SLS_PRIMARYSCALE2` (`0x0400`).

**Slider messages** (`SLM_*`) [DOC-IBM `pmstddlg.h:1678-1687`]:

| Message | Value | Purpose |
|---|---|---|
| `SLM_ADDDETENT` | `0x0369` | Add a detent niche at a position. |
| `SLM_QUERYDETENTPOS` | `0x036a` | Query a detent's position. |
| `SLM_QUERYSCALETEXT` | `0x036b` | Query the text at a tick. |
| `SLM_QUERYSLIDERINFO` | `0x036c` | Query slider state (arm/shaft/ribbon dimensions or position). |
| `SLM_QUERYTICKPOS` | `0x036d` | Query a tick's position. |
| `SLM_QUERYTICKSIZE` | `0x036e` | Query a tick's size. |
| `SLM_REMOVEDETENT` | `0x036f` | Remove a detent. |
| `SLM_SETSCALETEXT` | `0x0370` | Set the text above a tick. |
| `SLM_SETSLIDERINFO` | `0x0371` | Set a slider parameter (arm position, dimensions). |
| `SLM_SETTICKSIZE` | `0x0372` | Set a tick's size. |

**Slider notifications** (`SLN_*`) in `WM_CONTROL` [DOC-IBM `pmstddlg.h:1688-1691`]:

| Code | Value | Meaning |
|---|---|---|
| `SLN_CHANGE` | `1` | The slider arm position changed. |
| `SLN_SLIDERTRACK` | `2` | The arm is being dragged. |
| `SLN_SETFOCUS` | `3` | The slider gained the focus. |
| `SLN_KILLFOCUS` | `4` | The slider lost the focus. |

**Slider control data** [DOC-IBM `pmstddlg.h:1696-1703`]:

```c
typedef struct _SLDCDATA {   /* sldcd */
    ULONG   cbSize;
    USHORT  usScale1Increments;   /* divisions on scale 1        */
    USHORT  usScale1Spacing;      /* pels between increments     */
    USHORT  usScale2Increments;   /* divisions on scale 2        */
    USHORT  usScale2Spacing;      /* pels between increments     */
} SLDCDATA;
```

---

## 14. `WC_VALUESET` - value set [DOC-IBM]

A value set lets the user select one choice from a group of mutually exclusive choices; the
items can be bitmaps, icons, colors, text, or numbers arranged in a grid of rows and columns
[DOC-IBM pm3.txt "Value Set Control Window Processing"].

**Value-set styles** (`VS_*`) [DOC-IBM `pmstddlg.h:1899-1908`]:

| Constant | Value | Meaning |
|---|---|---|
| `VS_BITMAP` | `0x0001` | Items default to bitmaps. |
| `VS_ICON` | `0x0002` | Items default to icons. |
| `VS_TEXT` | `0x0004` | Items default to text strings. |
| `VS_RGB` | `0x0008` | Items default to RGB color values. |
| `VS_COLORINDEX` | `0x0010` | Items default to color indices. |
| `VS_BORDER` | `0x0020` | Border around the whole control. |
| `VS_ITEMBORDER` | `0x0040` | Border around each item. |
| `VS_SCALEBITMAPS` | `0x0080` | Scale bitmaps to the cell size. |
| `VS_RIGHTTOLEFT` | `0x0100` | Right-to-left item ordering. |
| `VS_OWNERDRAW` | `0x0200` | The owner draws the value-set background. |

**Value-set messages** (`VM_*`) [DOC-IBM `pmstddlg.h:1827-1834`]:

| Message | Value | Purpose |
|---|---|---|
| `VM_QUERYITEM` | `0x0375` | Query the item (data) at a row/column. |
| `VM_QUERYITEMATTR` | `0x0376` | Query an item's attributes. |
| `VM_QUERYMETRICS` | `0x0377` | Query the control metrics. |
| `VM_QUERYSELECTEDITEM` | `0x0378` | Query the selected item's row/column. |
| `VM_SELECTITEM` | `0x0379` | Select an item. |
| `VM_SETITEM` | `0x037a` | Set the item (data) at a row/column. |
| `VM_SETITEMATTR` | `0x037b` | Set an item's attributes. |
| `VM_SETMETRICS` | `0x037c` | Set the control metrics. |

**Value-set notifications** (`VN_*`) in `WM_CONTROL` [DOC-IBM `pmstddlg.h:1836-1845`]:

| Code | Value | Meaning |
|---|---|---|
| `VN_SELECT` | `120` | An item was selected. |
| `VN_ENTER` | `121` | An item was chosen (Enter/double-click). |
| `VN_DRAGLEAVE` | `122` | A drag left the control. |
| `VN_DRAGOVER` | `123` | A drag is over an item. |
| `VN_DROP` | `124` | A drop occurred on an item. |
| `VN_DROPHELP` | `125` | Help was requested for a drop. |
| `VN_INITDRAG` | `126` | A drag was initiated on an item. |
| `VN_SETFOCUS` | `127` | The value set gained the focus. |
| `VN_KILLFOCUS` | `128` | The value set lost the focus. |
| `VN_HELP` | `129` | Help was requested. |

**Value-set control data** [DOC-IBM `pmstddlg.h:1850-1855`]:

```c
typedef struct _VSCDATA {   /* vscd */
    ULONG   cbSize;
    USHORT  usRowCount;     /* number of rows     */
    USHORT  usColumnCount;  /* number of columns  */
} VSCDATA;
```

---

## 15. `WC_CONTAINER` - container [DOC-IBM]

The container holds objects - programs, files, images, database records - and displays them in
several **views** [DOC-IBM pm3.txt "Container Control Window Processing"]. It is the richest of
the standard controls: it owns a linked list of application **records**, an optional set of
**detail-column** field descriptors, and a control-wide `CNRINFO` block.

### The container model [DOC-IBM]

- **Records.** Each item is a record whose first member is a `RECORDCORE` (or, if the container
  is created `CCS_MINIRECORDCORE`, a smaller `MINIRECORDCORE`); an application subclasses it by
  allocating extra bytes past the core with `CM_ALLOCRECORD` and links records into the
  container with `CM_INSERTRECORD` [DOC-IBM pm3.txt "Container Control Styles and Selection
  Types"].
- **Views.** The `flWindowAttr` field of `CNRINFO` selects the view with `CV_*` flags: `CV_TEXT`
  (`0x0001`), `CV_NAME` (`0x0002`), `CV_ICON` (`0x0004`), `CV_DETAIL` (`0x0008`), `CV_FLOW`
  (`0x0010`), `CV_MINI` (`0x0020`), `CV_TREE` (`0x0040`), `CV_GRID` (`0x0080`) [DOC-IBM
  `pmstddlg.h:1085-1093`], combined with title attributes `CA_*` (`CA_CONTAINERTITLE`
  `0x0200`, `CA_DETAILSVIEWTITLES` `0x8000`, `CA_TREELINE` `0x00400000`, ...) [DOC-IBM
  `pmstddlg.h:1098-1111`].
- **Detail columns.** In detail view, each column is a `FIELDINFO`; columns are allocated with
  `CM_ALLOCDETAILFIELDINFO` and inserted with `CM_INSERTDETAILFIELDINFO`. A column's `flData`
  and `flTitle` carry `CFA_*` alignment/type flags (`CFA_LEFT` `0x0001`, `CFA_STRING` `0x0800`,
  `CFA_BITMAPORICON` `0x0100`, `CFA_DATE` `0x2000`, `CFA_TIME` `0x4000`, ...) [DOC-IBM
  `pmstddlg.h:1286-1311`].
- **Emphasis.** A record's `flRecordAttr` carries `CRA_*` state bits - `CRA_SELECTED`
  (`0x0001`), `CRA_TARGET` (`0x0002`), `CRA_CURSORED` (`0x0004`), `CRA_INUSE` (`0x0008`),
  `CRA_FILTERED` (`0x0010`), `CRA_EXPANDED`/`CRA_COLLAPSED` (`0x0080`/`0x0100`), ... [DOC-IBM
  `pmstddlg.h:1316-1331`].

**Container styles and selection types** (`CCS_*`) [DOC-IBM `pmstddlg.h:1070-1080`; meanings
pm3.txt "Container Control Styles and Selection Types"]:

| Constant | Value | Meaning |
|---|---|---|
| `CCS_EXTENDSEL` | `0x0001` | Extended selection (ranges). |
| `CCS_MULTIPLESEL` | `0x0002` | Multiple selection (zero or more). |
| `CCS_SINGLESEL` | `0x0004` | Single selection (default; the only type for tree view). |
| `CCS_AUTOPOSITION` | `0x0008` | Auto-arrange items in icon view on size/insert/font/title change. |
| `CCS_VERIFYPOINTERS` | `0x0010` | Verify that record pointers belong to the container's list before use. |
| `CCS_READONLY` | `0x0020` | The whole container's text is read-only. |
| `CCS_MINIRECORDCORE` | `0x0040` | Interpret records as `MINIRECORDCORE` rather than `RECORDCORE`. |
| `CCS_MINIICONS` | `0x0800` | Support mini-icons. |
| `CCS_NOCONTROLPTR` | `0x1000` | Do not send `WM_CONTROLPOINTER`. |

**Container messages** (`CM_*`) [DOC-IBM `pmstddlg.h:1336-1374`]:

| Message | Value | Purpose |
|---|---|---|
| `CM_ALLOCDETAILFIELDINFO` | `0x0330` | Allocate one or more `FIELDINFO` column descriptors. |
| `CM_ALLOCRECORD` | `0x0331` | Allocate one or more records (with extra bytes). |
| `CM_ARRANGE` | `0x0332` | Arrange items in icon view. |
| `CM_ERASERECORD` | `0x0333` | Erase a record's on-screen image. |
| `CM_FILTER` | `0x0334` | Filter which records are shown (via a callback). |
| `CM_FREEDETAILFIELDINFO` | `0x0335` | Free column descriptors. |
| `CM_FREERECORD` | `0x0336` | Free records. |
| `CM_HORZSCROLLSPLITWINDOW` | `0x0337` | Scroll the split (detail) window horizontally. |
| `CM_INSERTDETAILFIELDINFO` | `0x0338` | Insert column descriptors. |
| `CM_INSERTRECORD` | `0x0339` | Insert records into the container. |
| `CM_INVALIDATEDETAILFIELDINFO` | `0x033a` | Mark columns changed / repaint. |
| `CM_INVALIDATERECORD` | `0x033b` | Mark records changed / repaint. |
| `CM_PAINTBACKGROUND` | `0x033c` | Owner paints the background. |
| `CM_QUERYCNRINFO` | `0x033d` | Copy the container's `CNRINFO`. |
| `CM_QUERYDETAILFIELDINFO` | `0x033e` | Enumerate column descriptors. |
| `CM_QUERYDRAGIMAGE` | `0x033f` | Query the drag image. |
| `CM_QUERYRECORD` | `0x0340` | Enumerate records. |
| `CM_QUERYRECORDEMPHASIS` | `0x0341` | Find a record with a given emphasis. |
| `CM_QUERYRECORDFROMRECT` | `0x0342` | Find records within a rectangle. |
| `CM_QUERYRECORDRECT` | `0x0343` | Bounding rectangle of a record. |
| `CM_QUERYVIEWPORTRECT` | `0x0344` | The container's viewport rectangle. |
| `CM_REMOVEDETAILFIELDINFO` | `0x0345` | Remove column descriptors. |
| `CM_REMOVERECORD` | `0x0346` | Remove records. |
| `CM_SCROLLWINDOW` | `0x0347` | Scroll the container window. |
| `CM_SEARCHSTRING` | `0x0348` | Find a record by text. |
| `CM_SETCNRINFO` | `0x0349` | Change fields of the `CNRINFO`. |
| `CM_SETRECORDEMPHASIS` | `0x034a` | Set a record's emphasis (`CRA_*`). |
| `CM_SORTRECORD` | `0x034b` | Sort records (via a comparison callback). |
| `CM_OPENEDIT` / `CM_CLOSEEDIT` | `0x034c` / `0x034d` | Begin/end direct (in-place) text editing. |
| `CM_COLLAPSETREE` / `CM_EXPANDTREE` | `0x034e` / `0x034f` | Collapse/expand a tree-view branch. |
| `CM_QUERYRECORDINFO` | `0x0350` | Refresh application record data. |
| `CM_INSERTRECORDARRAY` | `0x0351` | Insert an array of records. |
| `CM_MOVETREE` | `0x0352` | Move a tree node to a new parent. |
| `CM_SETTEXTVISIBILITY` | `0x0353` | Show/hide record text. |
| `CM_SETGRIDINFO` / `CM_QUERYGRIDINFO` | `0x0354` / `0x0355` | Set/query the icon-grid layout. |
| `CM_SNAPTOGRID` | `0x0356` | Snap icons to the grid. |

**Container notifications** (`CN_*`) in `WM_CONTROL` [DOC-IBM `pmstddlg.h:1379-1401`]:

| Code | Value | Meaning |
|---|---|---|
| `CN_DRAGAFTER` | `101` | Drag over an ordered target (insert-after point). |
| `CN_DRAGLEAVE` | `102` | A drag left the container. |
| `CN_DRAGOVER` | `103` | A drag is over the container. |
| `CN_DROP` | `104` | A drop occurred. |
| `CN_DROPHELP` | `105` | Help requested for a drop. |
| `CN_ENTER` | `106` | A record was chosen (Enter/double-click). |
| `CN_INITDRAG` | `107` | A drag was initiated. |
| `CN_EMPHASIS` | `108` | A record's emphasis changed. |
| `CN_KILLFOCUS` / `CN_SETFOCUS` | `109` / `112` | Focus lost / gained. |
| `CN_SCROLL` | `110` | The container scrolled. |
| `CN_QUERYDELTA` | `111` | The scroll position reached the delta threshold (request more records). |
| `CN_REALLOCPSZ` | `113` | Direct-edit needs the app to reallocate the text buffer. |
| `CN_BEGINEDIT` / `CN_ENDEDIT` | `114` / `115` | Direct (in-place) editing began / ended. |
| `CN_COLLAPSETREE` / `CN_EXPANDTREE` | `116` / `117` | A tree branch was collapsed / expanded. |
| `CN_HELP` | `118` | Help requested. |
| `CN_CONTEXTMENU` | `119` | A context-menu request occurred. |
| `CN_VERIFYEDIT` | `134` | Verify direct-edit text. |
| `CN_PICKUP` | `135` | Lazy-drag pick-up. |
| `CN_DROPNOTIFY` | `136` | Lazy-drag drop notification. |
| `CN_GRIDRESIZED` | `137` | The icon grid was resized. |

### Using a container in practice [OBS-RE]

Everything below follows from one fact: **the container owns the record storage, not the
application.** A first container that ignores this compiles and then misbehaves in ways that look
unrelated to memory.

- **Allocate records with `CM_ALLOCRECORD`, never `malloc`.** `mp1` is the number of extra bytes
  wanted *beyond* the core, `mp2` how many records. `CM_FREERECORD` (or `CM_REMOVERECORD` with
  `CMA_FREE`) releases them.
- **`cb` in the core is the size of the CORE**, `sizeof(MINIRECORDCORE)` or `sizeof(RECORDCORE)` -
  not the size of your subclassed record. Setting it to the subclass size is a natural mistake and
  the control believes you.
- **The `PSZ` fields must point at storage that outlives the insert.** The container keeps the
  pointer, it does not copy the string, so pointing `pszIcon`/`pszText` at a local buffer leaves the
  control rendering freed stack. Put the text in the extra bytes you allocated past the core - that
  is what they are for, and their lifetime is exactly the record's.
- **The record struct must match the container's style.** `CCS_MINIRECORDCORE` means records are
  `MINIRECORDCORE`; without it they are `RECORDCORE`. The style lives in the `.RC` and the struct in
  the `.C`, so nothing checks that they agree.
- **Set the view through `CNRINFO.flWindowAttr` + `CM_SETCNRINFO`** with `CMA_FLWINDOWATTR`, e.g.
  `CV_NAME | CV_MINI | CV_FLOW` for a flowed mini-icon list - that combination needs no `FIELDINFO`
  columns at all, unlike `CV_DETAIL`.
- **Insert with a `RECORDINSERT`** whose `pRecordOrder` is `(PRECORDCORE)CMA_END` and `zOrder`
  `CMA_TOP`. Set `fInvalidateRecord = FALSE` while bulk-filling and send one
  `CM_INVALIDATERECORD` at the end.
- **`CN_ENTER` (double-click / Enter) arrives via `WM_CONTROL` with a `NOTIFYRECORDENTER *` in
  `mp2`** - one more payload shape behind that message, so check `SHORT2FROMMP(mp1)` before
  dereferencing (see `pm-window-messaging.md`).

For a plain directory listing the records come from `DosFindFirst`/`DosFindNext`, and per-file icons
from `WinLoadFileIcon(path, FALSE)` - the `FALSE` asks for a *shared* pointer, which is what you want
when only displaying it. A container record carries its own `HPOINTER`, so nothing like a Win32
image list is required.

### Key container structures [DOC-IBM]

**`RECORDCORE`** - the record base for the full record model [DOC-IBM `pmstddlg.h:1160-1176`]:

```c
typedef struct _RECORDCORE {   /* recc */
    ULONG       cb;
    ULONG       flRecordAttr;         /* CRA_* record attributes         */
    POINTL      ptlIcon;              /* icon-view position              */
    struct _RECORDCORE *preccNextRecord;
    PSZ         pszIcon;              /* text for CV_ICON                */
    HPOINTER    hptrIcon;             /* icon (non-mini)                 */
    HPOINTER    hptrMiniIcon;         /* icon (CV_MINI)                  */
    HBITMAP     hbmBitmap;            /* bitmap (non-mini)               */
    HBITMAP     hbmMiniBitmap;        /* bitmap (CV_MINI)                */
    PTREEITEMDESC pTreeItemDesc;      /* tree-view icons                 */
    PSZ         pszText;              /* text for CV_TEXT                */
    PSZ         pszName;              /* text for CV_NAME                */
    PSZ         pszTree;              /* text for CV_TREE                */
} RECORDCORE;
```

**`MINIRECORDCORE`** - the compact record base (`CCS_MINIRECORDCORE`) [DOC-IBM
`pmstddlg.h:1181-1189`]:

```c
typedef struct _MINIRECORDCORE {   /* minirec */
    ULONG       cb;
    ULONG       flRecordAttr;
    POINTL      ptlIcon;
    struct _MINIRECORDCORE *preccNextRecord;
    PSZ         pszIcon;
    HPOINTER    hptrIcon;
} MINIRECORDCORE;
```

**`FIELDINFO`** - one detail-view column [DOC-IBM `pmstddlg.h:1142-1154`]:

```c
typedef struct _FIELDINFO {   /* fldinfo */
    ULONG      cb;
    ULONG      flData;                /* CFA_* data attributes/type      */
    ULONG      flTitle;               /* CFA_* title attributes          */
    PVOID      pTitleData;            /* column-heading string or HBITMAP*/
    ULONG      offStruct;             /* offset from record to this cell */
    PVOID      pUserData;
    struct _FIELDINFO *pNextFieldInfo;
    ULONG      cxWidth;               /* column width in pels            */
} FIELDINFO;
```

**`CNRINFO`** - the container-wide control block (queried with `CM_QUERYCNRINFO`, changed with
`CM_SETCNRINFO`) [DOC-IBM `pmstddlg.h:1208-1242`]:

```c
typedef struct _CNRINFO {   /* ccinfo */
    ULONG       cb;
    PVOID       pSortRecord;          /* sort comparison function        */
    PFIELDINFO  pFieldInfoLast;       /* last column in the left split   */
    PFIELDINFO  pFieldInfoObject;     /* column that receives in-use emph*/
    PSZ         pszCnrTitle;          /* container title                 */
    ULONG       flWindowAttr;         /* CV_* view + CA_* title attrs    */
    POINTL      ptlOrigin;            /* icon-view virtual origin        */
    ULONG       cDelta;               /* delta threshold                 */
    ULONG       cRecords;             /* number of records               */
    SIZEL       slBitmapOrIcon;       /* icon/bitmap size in pels        */
    SIZEL       slTreeBitmapOrIcon;   /* tree icon/bitmap size           */
    HBITMAP     hbmExpanded;          /* tree "expanded" bitmap          */
    HBITMAP     hbmCollapsed;         /* tree "collapsed" bitmap         */
    HPOINTER    hptrExpanded;         /* tree "expanded" icon            */
    HPOINTER    hptrCollapsed;        /* tree "collapsed" icon           */
    LONG        cyLineSpacing;        /* row spacing                     */
    LONG        cxTreeIndent;         /* child indent                    */
    LONG        cxTreeLine;           /* tree-line thickness             */
    ULONG       cFields;              /* number of detail columns        */
    LONG        xVertSplitbar;        /* split-bar position (0xFFFF=none)*/
} CNRINFO;
```

---

## 16. `WC_NOTEBOOK` - notebook [DOC-IBM]

A notebook organizes information on individual **pages** the user turns through, with **tabs**
(major and minor sections), an optional **status line**, a binding, and - in the "new" style - a
common **button area** and a page list [DOC-IBM pm5.txt "Notebook Controls"]. Each page is
identified by a page id (`ULONG`) and is associated with an application window or dialog whose
contents fill the page (`BKM_SETPAGEWINDOWHWND`). The book supports both an "old" and a "new"
visual style, selected by the `BKS_*` style bits.

**Notebook styles** (`BKS_*`) [DOC-IBM `pmstddlg.h:2038-2082`; meanings pm5.txt "Notebook Styles"]
- back-page corner (`BKS_BACKPAGESBR` `0x0001`, `BKS_BACKPAGESBL` `0x0002`, `BKS_BACKPAGESTR`
`0x0004`, `BKS_BACKPAGESTL` `0x0008`), major-tab edge (`BKS_MAJORTABRIGHT` `0x0010`,
`BKS_MAJORTABLEFT` `0x0020`, `BKS_MAJORTABTOP` `0x0040`, `BKS_MAJORTABBOTTOM` `0x0080`), tab shape
(`BKS_SQUARETABS` `0x0000`, `BKS_ROUNDEDTABS` `0x0100`, `BKS_POLYGONTABS` `0x0200`), binding
(`BKS_SOLIDBIND` `0x0000`, `BKS_SPIRALBIND` `0x0400`), status-text justification
(`BKS_STATUSTEXTLEFT` `0x0000`, `BKS_STATUSTEXTRIGHT` `0x1000`, `BKS_STATUSTEXTCENTER` `0x2000`),
tab-text justification (`BKS_TABTEXTLEFT` `0x0000`, `BKS_TABTEXTRIGHT` `0x4000`,
`BKS_TABTEXTCENTER` `0x8000`), and `BKS_TABBEDDIALOG` (`0x0800`) for a tabbed-dialog notebook.

**Notebook messages** (`BKM_*`) [DOC-IBM `pmstddlg.h:1956-1979`]:

| Message | Value | Purpose |
|---|---|---|
| `BKM_CALCPAGERECT` | `0x0353` | Convert between notebook and page rectangles. |
| `BKM_DELETEPAGE` | `0x0354` | Delete one or more pages. |
| `BKM_INSERTPAGE` | `0x0355` | Insert a page (returns its page id). |
| `BKM_INVALIDATETABS` | `0x0356` | Repaint the tab area. |
| `BKM_TURNTOPAGE` | `0x0357` | Turn to (display) a page. |
| `BKM_QUERYPAGECOUNT` | `0x0358` | Number of pages. |
| `BKM_QUERYPAGEID` | `0x0359` | Query a page id (first/last/next/prev/top). |
| `BKM_QUERYPAGEDATA` / `BKM_SETPAGEDATA` | `0x035a` / `0x035f` | Query/set a page's application data. |
| `BKM_QUERYPAGEWINDOWHWND` / `BKM_SETPAGEWINDOWHWND` | `0x035b` / `0x0360` | Query/set the window shown on a page. |
| `BKM_QUERYTABBITMAP` / `BKM_SETTABBITMAP` | `0x035c` / `0x0362` | Query/set a tab's bitmap. |
| `BKM_QUERYTABTEXT` / `BKM_SETTABTEXT` | `0x035d` / `0x0363` | Query/set a tab's text. |
| `BKM_SETDIMENSIONS` | `0x035e` | Set tab / page-button dimensions. |
| `BKM_SETSTATUSLINETEXT` / `BKM_QUERYSTATUSLINETEXT` | `0x0361` / `0x0366` | Set/query the status-line text. |
| `BKM_SETNOTEBOOKCOLORS` | `0x0364` | Set the notebook color scheme. |
| `BKM_QUERYPAGESTYLE` | `0x0365` | Query a page's style bits. |
| `BKM_SETPAGEINFO` / `BKM_QUERYPAGEINFO` | `0x0367` / `0x0368` | Set/query a page's full `BOOKPAGEINFO`. |
| `BKM_SETTABCOLOR` | `0x0374` | Set the tab color. |
| `BKM_SETNOTEBOOKBUTTONS` | `0x0375` | Define the common push buttons. |

**Notebook notifications** (`BKN_*`) in `WM_CONTROL` [DOC-IBM `pmstddlg.h:1981-1985`]:

| Code | Value | Meaning |
|---|---|---|
| `BKN_PAGESELECTED` | `130` | The user selected a new page. |
| `BKN_NEWPAGESIZE` | `131` | The application page-window size changed. |
| `BKN_HELP` | `132` | Help requested. |
| `BKN_PAGEDELETED` | `133` | A page was deleted. |
| `BKN_PAGESELECTEDPENDING` | `134` | A new page selection is pending. |

**Page-insertion/query flags** (`BKA_*`) used with `BKM_INSERTPAGE` / `BKM_QUERYPAGEID` and the
tab styles [DOC-IBM `pmstddlg.h:1990-2029`]: `BKA_MAJOR` (`0x0040`) / `BKA_MINOR` (`0x0080`) tab
level, `BKA_MAJORTAB` (`0x0001`) / `BKA_MINORTAB` (`0x0002`), `BKA_STATUSTEXTON` (`0x0001`),
`BKA_AUTOPAGESIZE` (`0x0100`), `BKA_LAST` (`0x0002`) / `BKA_FIRST` (`0x0004`) / `BKA_NEXT`
(`0x0008`) / `BKA_PREV` (`0x0010`) / `BKA_TOP` (`0x0020`) / `BKA_END` (`0x0200`) insertion/query
position, `BKA_TEXT` (`0x0400`) / `BKA_BITMAP` (`0x0800`) tab-data kind.

---

## See also
- `pm-window-messaging.md` - the window / message model these controls live in: `WinCreateWindow`
  / `WinCreateStdWindow`, `WinRegisterClass`, the core `WM_*` set, the message loop, the packing
  macros (`SHORT1FROMMP`/`SHORT2FROMMP`/`MPFROM2SHORT`), dialogs, and the `FCF_*`/`FID_*` frame
  controls.
- `pm-controls-thirdparty.md` - the controls PM does *not* ship (toolbar, status bar, progress bar,
  splitter, 3D group box), surveyed across the Hobbes archive by license, with every license read
  from the package that states it. Read the present doc first: much of what a third-party widget is
  reached for can be had from `WC_CONTAINER`, `WC_VALUESET` or an owner-drawn `WC_BUTTON`.
- `pm-graphics.md` - the Gpi drawing path an owner-drawn control (`WM_DRAWITEM`, `BN_PAINT`) uses.
- `calling-convention.md` - the `APIENTRY`/`EXPENTRY` linkage every window/dialog procedure uses.
