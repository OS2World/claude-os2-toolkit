# OS/2 Presentation Manager - Windows and Message Programming

The application programming model a Presentation Manager (PM) program is built on: the anchor
block and per-thread message queue an application must establish before it can call PM, the
window class / window procedure model, the get-and-dispatch message loop, the core `WM_*`
message set, painting, and dialogs. This is the **API surface a PM program calls and the
contract its window procedure must honour** - the message queue's internal delivery and kernel
wake are covered separately in `message-queue.md`, and the drawing path a `WM_PAINT` feeds is
covered in `pm-graphics.md`.

Provenance: **[DOC-IBM]** the OS/2 Toolkit header `pmwin.h` and the base type header `os2def.h`
(every prototype, structure, and constant below is transcribed from them); **[DOC-IBM]** the IBM
OS/2 PM Programming Reference for API semantics. Where a behavioural claim is not stated by a
header it is tagged **[DOC]**.

---

## 1. The anchor block and the message queue [DOC-IBM]

Two things are per-application/per-thread and must exist before any window can:

- An **anchor block** (`HAB`, *hab*) - a thread's handle to the PM environment. A thread that
  will call PM window functions obtains one with `WinInitialize`.
- A **message queue** (`HMQ`, *hmq*) - created with `WinCreateMsgQueue`. **Each thread that
  creates windows, or that receives messages, must have its own message queue** [DOC]; a queue
  belongs to the thread that created it. A thread with windows but no queue cannot receive
  input or `WM_PAINT`.

Both handles are `LHANDLE` (`unsigned long`) [DOC-IBM `os2def.h:76,258,599`].

| Symbol | Prototype (from `pmwin.h`) | Purpose |
|---|---|---|
| `WinInitialize` | `HAB APIENTRY WinInitialize(ULONG flOptions)` | Register the calling thread with PM; returns its anchor block (`NULLHANDLE` on failure). `flOptions` is reserved - pass 0. |
| `WinCreateMsgQueue` | `HMQ APIENTRY WinCreateMsgQueue(HAB hab, LONG cmsg)` | Create this thread's message queue. `cmsg` is the requested queue size in messages; 0 requests the default. |
| `WinDestroyMsgQueue` | `BOOL APIENTRY WinDestroyMsgQueue(HMQ hmq)` | Destroy the thread's queue. |
| `WinTerminate` | `BOOL APIENTRY WinTerminate(HAB hab)` | Release the anchor block and all PM resources the thread still owns. |
| `WinQueryAnchorBlock` | `HAB APIENTRY WinQueryAnchorBlock(HWND hwnd)` | Recover the anchor block associated with a window. |
| `WinQueryVersion` | `ULONG APIENTRY WinQueryVersion(HAB hab)` | PM version/environment. |
| `WinQueryQueueInfo` | `BOOL APIENTRY WinQueryQueueInfo(HMQ hmq, PMQINFO pmqi, ULONG cbCopy)` | Fill an `MQINFO` describing a queue. |

Provenance: **[DOC-IBM]** `pmwin.h:409-415, 1040-1047`.

The canonical startup/shutdown sequence for a PM thread is therefore
`WinInitialize` -> `WinCreateMsgQueue` -> (register classes, create windows, run the message loop)
-> `WinDestroyMsgQueue` -> `WinTerminate` [DOC].

### `MQINFO` - queue information [DOC-IBM `pmwin.h:1025-1033`]

```c
typedef struct _MQINFO {   /* mqi */
    ULONG   cb;            /* structure size                */
    PID     pid;           /* owning process                */
    TID     tid;           /* owning thread                 */
    ULONG   cmsgs;         /* number of messages in queue   */
    PVOID   pReserved;
} MQINFO;
```

### Predefined window handles [DOC-IBM `pmwin.h:227-237`]

| Symbol | Value | Meaning |
|---|---|---|
| `HWND_DESKTOP` | `(HWND)1` | The desktop window; the root parent for top-level windows, and the `hwndDesktop` argument to many query functions. |
| `HWND_OBJECT` | `(HWND)2` | The object-window parent (a window with no presentation, for message-only use). |
| `HWND_TOP` | `(HWND)3` | Z-order top (for `hwndInsertBehind`). |
| `HWND_BOTTOM` | `(HWND)4` | Z-order bottom. |
| `HWND_THREADCAPTURE` | `(HWND)5` | Used with mouse capture. |

---

## 1a. `WinCreateMsgQueue` gates on the process type AND the session  `[OBS-RE]`

Read out of a shipped `PMMERGE.DLL` (Warp 4.5) 2026-08-20, byte-exact. This is
not documented anywhere in the Toolkit or the DDK, and it decides whether a
process can have a message queue at all - so a system that reports process
identity wrongly gets `WinCreateMsgQueue` failures with no obvious cause.

PM keeps one system-wide word, `sgidInit` (IBM's own symbol), holding **the
session id of the first process to create a message queue**. The first caller
sets it; every later caller is checked against it.

**First caller** (`sgidInit == 0`) - the only requirement is that it is not a
detached process:

```
mov ecx,[ppibCurrent] / cmp dword [ecx+0x18],4   ; PIB.pib_ultype == PT_DETACHED?
jnz ok
  PMTrace("First CreateMsgQueue failed PT_D...") ; return 0
ok:
mov eax,[plisCurrent] / mov ax,[eax+8]           ; LINFOSEG.sgCurrent
mov [sgidInit],ax                                ; remember this session
```

**Every later caller** (`PMMERGE` obj4 `+0x151064`):

```
mov ecx,[ppibCurrent]
mov ecx,[ecx+0x18]        ; PIB.pib_ultype
cmp ecx,3 / jz pass       ; PT_PM       -> EXEMPT
cmp ecx,4 / jz pass       ; PT_DETACHED -> EXEMPT
mov ecx,[plisCurrent]
mov dx,[sgidInit]
cmp [ecx+8],dx            ; LINFOSEG.sgCurrent vs sgidInit
jz pass
push 0x6000 / push 0x81051 / call SetErrorInfo
xor eax,eax               ; return 0 - WinCreateMsgQueue FAILS
```

So, in words: **a process whose `PIB.pib_ultype` is neither `PT_PM` (3) nor
`PT_DETACHED` (4) may create a message queue only if its
`LINFOSEG.sgCurrent` equals the first message-queue creator's session.** A PM
or detached process is exempt and may create one from any session.

Both inputs are per-process values a host must get right independently:
`pib_ultype` is `PIB+0x18`, and `sgCurrent` is `LINFOSEG+0x08` reached through
PM's `plisCurrent`. Note the failure is silent to the caller beyond a `NULL`
return plus error `0x81051` - nothing logs, and nothing says which of the two
inputs was wrong.

## 2. Message parameters - `MPARAM`, `MRESULT`, and packing [DOC-IBM]

A message carries two parameters and returns one result. All three are pointer-sized opaque
types:

```c
typedef VOID *MPARAM;    /* mp   */    /* os2def.h:591 */
typedef VOID *MRESULT;   /* mres */    /* os2def.h:593 */
```

Because they are opaque, PM defines a family of macros to pack standard scalar types into an
`MPARAM`/`MRESULT` and to unpack them again. **These macros are the ABI for how a message's data
is laid out in its two parameters** - a window procedure reads its `mp1`/`mp2` with the
`*FROMMP` macros exactly as the sender wrote them with the `MPFROM*` macros.

| Pack (into `MPARAM`) | Definition | Unpack (from `MPARAM`) | Definition |
|---|---|---|---|
| `MPVOID` | `((MPARAM)0L)` | `PVOIDFROMMP(mp)` | `((VOID *)(mp))` |
| `MPFROMP(p)` | `((MPARAM)((ULONG)(p)))` | `HWNDFROMMP(mp)` | `((HWND)(mp))` |
| `MPFROMHWND(hwnd)` | `((MPARAM)(HWND)(hwnd))` | `CHAR1FROMMP(mp)` | `((UCHAR)((ULONG)mp))` |
| `MPFROMCHAR(ch)` | `((MPARAM)(USHORT)(ch))` | `CHAR2FROMMP(mp)` | `((UCHAR)((ULONG)mp >> 8))` |
| `MPFROMSHORT(s)` | `((MPARAM)(USHORT)(s))` | `CHAR3FROMMP(mp)` | `((UCHAR)((ULONG)mp >> 16))` |
| `MPFROM2SHORT(s1,s2)` | `((MPARAM)MAKELONG(s1,s2))` | `CHAR4FROMMP(mp)` | `((UCHAR)((ULONG)mp >> 24))` |
| `MPFROMSH2CH(s,c1,c2)` | `((MPARAM)MAKELONG(s,MAKESHORT(c1,c2)))` | `SHORT1FROMMP(mp)` | `((USHORT)(ULONG)(mp))` |
| `MPFROMLONG(l)` | `((MPARAM)(ULONG)(l))` | `SHORT2FROMMP(mp)` | `((USHORT)((ULONG)mp >> 16))` |
| | | `LONGFROMMP(mp)` | `((ULONG)(mp))` |

The `MRESULT` side mirrors this: `MRFROMP`, `MRFROMSHORT`, `MRFROM2SHORT`, `MRFROMLONG` to
build a result, and `PVOIDFROMMR`, `SHORT1FROMMR`, `SHORT2FROMMR`, `LONGFROMMR` to read one.

The key packing idiom is `MPFROM2SHORT(low, high)` - two 16-bit values packed into one parameter,
low half in bits 0-15 and high half in bits 16-31 - recovered with `SHORT1FROMMP` (low) and
`SHORT2FROMMP` (high). Many messages use it (e.g. `WM_SIZE` carries the new width and height this
way, `WM_COMMAND` carries the command id).

Provenance: **[DOC-IBM]** `pmwin.h:172-205`, `os2def.h:591-594`.

---

## 3. The window procedure [DOC-IBM]

Every window class has a **window procedure** (`PFNWP`) - the function PM calls to deliver each
message. Its signature is fixed:

```c
typedef MRESULT (EXPENTRY FNWP)(HWND, ULONG, MPARAM, MPARAM);   /* pmwin.h:223 */
typedef FNWP *PFNWP;
```

That is, `MRESULT EXPENTRY WndProc(HWND hwnd, ULONG msg, MPARAM mp1, MPARAM mp2)`. The procedure
switches on `msg`, interprets `mp1`/`mp2` according to that message (Section 6), and returns an
`MRESULT`. **Any message it does not handle it must pass to `WinDefWindowProc`**, which supplies
the system default behaviour:

```c
MRESULT APIENTRY WinDefWindowProc(HWND hwnd, ULONG msg, MPARAM mp1, MPARAM mp2);   /* pmwin.h:330 */
```

A window procedure must be exported (named in the module definition file) so PM can call it
across the module boundary. Provenance: **[DOC-IBM]** `pmwin.h:208-224, 330-333`.

### Subclassing an existing window [DOC-IBM]

To change the behaviour of a window whose class you do not own - a push button, an entry field, a
frame - replace its window procedure:

```c
PFNWP APIENTRY WinSubclassWindow(HWND hwnd, PFNWP pfnwp);   /* pmwin.h:746-747 */
```

It installs `pfnwp` and **returns the procedure it displaced**. Save that pointer: it is the only
way to reach the original behaviour. Thereafter every message sent or posted to the window arrives
at the new procedure first. [DOC-IBM `pmv2base.txt` - "An application subclasses a window by using
the `WinSubclassWindow` function to replace the window's original window procedure".]

> **A subclass procedure must chain to the saved procedure, NOT to `WinDefWindowProc`.** This is the
> one rule that inverts the normal habit of section 3. Everything that makes a button a button - its
> painting, its keyboard handling, its `WM_COMMAND` notifications - lives in the class procedure you
> just displaced, and `WinDefWindowProc` knows none of it. Send unhandled messages to the system
> default instead of the saved procedure and the control keeps its appearance for a moment but stops
> behaving like a control. [DOC-IBM `pmv2base.txt` - "If the new window procedure does not process a
> particular message, it must pass the message to the original window procedure, not to
> `WinDefWindowProc`, for default processing".]

Store the saved `PFNWP` in a **window word** (section 9) rather than a global when more than one instance
may be subclassed - one global holds one procedure, and the second subclassed control overwrites
the first, so the two instances chain into each other.

Note that OS/2 uses "subclass" for two unrelated things: this, and the SOM/WPS sense of deriving a
class (`som.md`, `wps-classes.md`). Container records are subclassed in a third sense again
(`pm-controls.md`). They share no mechanism.

---

## 4. Registering a class and creating windows [DOC-IBM]

### `WinRegisterClass` [DOC-IBM `pmwin.h:317-328`]

```c
BOOL APIENTRY WinRegisterClass(HAB hab, PSZ pszClassName, PFNWP pfnWndProc,
                               ULONG flStyle, ULONG cbWindowData);
```

Registers an application window class: its name, its window procedure, its default class style
(`CS_*`), and `cbWindowData` - the number of extra bytes of storage to reserve in every window of
this class (the *window words*, Section 9).

**Class styles** (`flStyle`) [DOC-IBM `pmwin.h:299-308`]:

| Constant | Value | Meaning |
|---|---|---|
| `CS_MOVENOTIFY` | `0x00000001` | Window is sent notification when moved. |
| `CS_SIZEREDRAW` | `0x00000004` | Whole window is redrawn on any size change. |
| `CS_HITTEST` | `0x00000008` | Window receives `WM_HITTEST`. |
| `CS_PUBLIC` | `0x00000010` | Class is public (visible to all processes). |
| `CS_FRAME` | `0x00000020` | Class is a frame class. |
| `CS_CLIPCHILDREN` | `0x20000000` | Exclude child windows from the window's drawing. |
| `CS_CLIPSIBLINGS` | `0x10000000` | Exclude sibling windows. |
| `CS_PARENTCLIP` | `0x08000000` | Clip to the parent. |
| `CS_SAVEBITS` | `0x04000000` | Save the bits the window obscures. |
| `CS_SYNCPAINT` | `0x02000000` | Paint synchronously (send `WM_PAINT` immediately rather than queuing). |

`WinRegisterClass` returns `TRUE` on success and `FALSE` on failure; on failure the reason is
retrievable with `WinGetLastError` [DOC - EDM2 "WinRegisterClass"]:

| Error | Value | Meaning |
|---|---|---|
| `PMERR_PARAMETER_OUT_OF_RANGE` | `0x1003` | A parameter was out of range (e.g. a private class name clashing with a public class in the same process). |
| `PMERR_INVALID_HATOMTBL` | `0x1013` | An invalid atom-table handle was passed. |
| `PMERR_INVALID_ATOM_NAME` | `0x1015` | An invalid atom-name string was given. |
| `PMERR_INVALID_INTEGER_ATOM` | `0x1016` | The atom specified is not a valid integer atom. |
| `PMERR_ATOM_NAME_NOT_FOUND` | `0x1017` | The atom name given was not in the atom table. |
| `PMERR_INVALID_FLAG` | `0x1019` | An invalid bit was set for a parameter. |
| `PMERR_INVALID_PARAMETERS` | `0x1208` | One or more parameters were invalid. |

Class-name and lifetime semantics [DOC - EDM2 "WinRegisterClass"]: a private class name must not
clash with the name of a public class in the same process (that returns `FALSE` /
`PMERR_PARAMETER_OUT_OF_RANGE`); a private class may, however, override an older private class of
the same name, in which case the new parameters replace the old ones. Private classes are
discarded when the owning process terminates. `CS_PUBLIC` may only be specified by the shell
process (a class registered by a DLL loaded by the shell at startup) - an application registering
its own class leaves it off.

### Predefined (system) window classes [DOC-IBM `pmwin.h:241-275`]

Class names of the form `((PSZ)0xffff00nnL)` are the built-in PM control classes:

| Constant | Value | Control |
|---|---|---|
| `WC_FRAME` | `0xffff0001` | Frame window |
| `WC_COMBOBOX` | `0xffff0002` | Combination box |
| `WC_BUTTON` | `0xffff0003` | Push/check/radio button |
| `WC_MENU` | `0xffff0004` | Menu |
| `WC_STATIC` | `0xffff0005` | Static text/icon |
| `WC_ENTRYFIELD` | `0xffff0006` | Single-line entry field |
| `WC_LISTBOX` | `0xffff0007` | List box |
| `WC_SCROLLBAR` | `0xffff0008` | Scroll bar |
| `WC_TITLEBAR` | `0xffff0009` | Title bar |
| `WC_MLE` | `0xffff000A` | Multi-line entry field |
| `WC_SPINBUTTON` | `0xffff0020` | Spin button |
| `WC_CONTAINER` | `0xffff0025` | Container |
| `WC_SLIDER` | `0xffff0026` | Slider |
| `WC_VALUESET` | `0xffff0027` | Value set |
| `WC_NOTEBOOK` | `0xffff0028` | Notebook |

### `WinCreateWindow` [DOC-IBM `pmwin.h:439-452`]

```c
HWND APIENTRY WinCreateWindow(HWND hwndParent, PSZ pszClass, PSZ pszName, ULONG flStyle,
                              LONG x, LONG y, LONG cx, LONG cy,
                              HWND hwndOwner, HWND hwndInsertBehind, ULONG id,
                              PVOID pCtlData, PVOID pPresParams);
```

The general window-creation primitive: parent, class name, text, window style (`WS_*`), position
and size, owner, Z-order insertion point, child id, class-specific control data, and presentation
parameters.

**Window styles** (`flStyle`) [DOC-IBM `pmwin.h:280-295`]:

| Constant | Value | Meaning |
|---|---|---|
| `WS_VISIBLE` | `0x80000000` | Window is visible. |
| `WS_DISABLED` | `0x40000000` | Window is disabled (no input). |
| `WS_CLIPCHILDREN` | `0x20000000` | Clip out children when drawing. |
| `WS_CLIPSIBLINGS` | `0x10000000` | Clip out siblings. |
| `WS_PARENTCLIP` | `0x08000000` | Clip to parent. |
| `WS_SAVEBITS` | `0x04000000` | Save obscured bits. |
| `WS_SYNCPAINT` | `0x02000000` | Synchronous painting. |
| `WS_MINIMIZED` | `0x01000000` | Created minimized. |
| `WS_MAXIMIZED` | `0x00800000` | Created maximized. |
| `WS_ANIMATE` | `0x00400000` | Animate show/hide. |
| `WS_GROUP` | `0x00010000` | Dialog: first control of a group. |
| `WS_TABSTOP` | `0x00020000` | Dialog: a tab stop. |
| `WS_MULTISELECT` | `0x00040000` | Dialog: multiple-selection control. |

#### Building a transient overlay - tooltip, call tip, dropdown [OBS-RE]

An overlay that must be able to **overhang** its owner (a tooltip, a call tip, an autocomplete list)
cannot be a child of the window it belongs to, because a child is clipped to its parent. The PM
pattern separates the two relationships that Win32 tends to conflate:

```c
hwndTip = WinCreateWindow(
    HWND_DESKTOP,        /* PARENT: the desktop, so the overlay is not clipped   */
    "MyTipClass", "",
    WS_CLIPSIBLINGS,     /* NOT WS_VISIBLE - created hidden, shown on demand     */
    0, 0, 0, 0,
    hwndOwner,           /* OWNER: the window it belongs to; gets notifications  */
    HWND_TOP, 0, NULL, NULL);
```

Points worth knowing before you debug them:

- **Register the class `CS_SAVEBITS`.** PM then saves the pixels the overlay covers and restores them
  when it goes away, instead of forcing the window underneath through a repaint on every dismissal.
  That is what the style is for; a transient overlay is the case it was designed around.
- **It will not steal the focus.** PM gives a window the focus only when something calls
  `WinSetFocus` for it, so typing keeps going to the owner while the overlay is up. Nothing extra is
  needed - unlike Win32, where a plain popup can take activation unless you prevent it.
- **Attach your instance pointer *after* `WinCreateWindow` returns**, with `WinSetWindowPtr`, and have
  the window procedure ignore messages that arrive before it is set. That is simpler than decoding
  the pointer out of `WM_CREATE`, and the early messages have nothing to do anyway.
- **If the overlay paints, set its drawing surface up against its OWN window handle**, not the
  owner's. Anything that flips y (and on PM that is anything drawing in a top-down coordinate system)
  computes the flip from the window it was given, so passing the owner silently offsets every
  primitive by the difference in their heights.

Position it with `WinMapWindowPoints` to convert the owner's coordinates to the desktop's, then
`WinSetWindowPos`.

### `WinCreateStdWindow` [DOC-IBM `pmwin.h:2772-2781`]

```c
HWND APIENTRY WinCreateStdWindow(HWND hwndParent, ULONG flStyle, PULONG pflCreateFlags,
                                 PSZ pszClientClass, PSZ pszTitle, ULONG styleClient,
                                 HMODULE hmod, ULONG idResources, PHWND phwndClient);
```

Creates a **standard frame window** - a `WC_FRAME` window together with the frame controls
selected by `*pflCreateFlags` (title bar, system menu, min/max buttons, borders, menu, etc.) and,
if `pszClientClass` is given, a **client window** of that class as the frame's child. The client
window handle is returned through `phwndClient`; the function's return value is the *frame*
handle. `hmod`/`idResources` name a resource module and resource id from which the frame loads a
menu, accelerator table, and icon.

**Frame creation flags** (`FCF_*`) [DOC-IBM `pmwin.h:2686-2717`]:

| Constant | Value | Frame control |
|---|---|---|
| `FCF_TITLEBAR` | `0x00000001` | Title bar |
| `FCF_SYSMENU` | `0x00000002` | System menu |
| `FCF_MENU` | `0x00000004` | Action-bar menu |
| `FCF_SIZEBORDER` | `0x00000008` | Sizing border |
| `FCF_MINBUTTON` | `0x00000010` | Minimize button |
| `FCF_MAXBUTTON` | `0x00000020` | Maximize button |
| `FCF_MINMAX` | `0x00000030` | Both min and max buttons |
| `FCF_VERTSCROLL` | `0x00000040` | Vertical scroll bar |
| `FCF_HORZSCROLL` | `0x00000080` | Horizontal scroll bar |
| `FCF_DLGBORDER` | `0x00000100` | Dialog border |
| `FCF_BORDER` | `0x00000200` | Thin border |
| `FCF_SHELLPOSITION` | `0x00000400` | Let the shell choose position/size |
| `FCF_TASKLIST` | `0x00000800` | Add to the window/task list |
| `FCF_ICON` | `0x00004000` | Load an icon from resources |
| `FCF_ACCELTABLE` | `0x00008000` | Load an accelerator table |
| `FCF_SYSMODAL` | `0x00010000` | System-modal frame |
| `FCF_HIDEBUTTON` | `0x01000000` | Hide button |
| `FCF_CLOSEBUTTON` | `0x04000000` | Close button (when no min/max present) |
| `FCF_AUTOICON` | `0x40000000` | Auto-repaint minimized icon |
| `FCF_STANDARD` | `0x0000CC3F` | The common set: title bar, system menu, menu, sizing border, min/max, icon, accelerator table, shell position, task list |

**Frame control window IDs** (`FID_*`) - the child id of each frame control, usable with
`WinWindowFromID` to find it [DOC-IBM `pmwin.h:2868-2874`]:

| Constant | Value | Control |
|---|---|---|
| `FID_SYSMENU` | `0x8002` | System menu |
| `FID_TITLEBAR` | `0x8003` | Title bar |
| `FID_MINMAX` | `0x8004` | Min/max buttons |
| `FID_MENU` | `0x8005` | Menu |
| `FID_VERTSCROLL` | `0x8006` | Vertical scroll bar |
| `FID_HORZSCROLL` | `0x8007` | Horizontal scroll bar |
| `FID_CLIENT` | `0x8008` | Client window |

### `CREATESTRUCT` - the `WM_CREATE` parameter [DOC-IBM `pmwin.h:717-733`]

`WM_CREATE` delivers, in `mp2`, a pointer to the `CREATESTRUCT` describing the window being
created (its fields mirror the `WinCreateWindow` arguments, in reverse order):

```c
typedef struct _CREATESTRUCT {   /* crst */
    PVOID   pPresParams;
    PVOID   pCtlData;
    ULONG   id;
    HWND    hwndInsertBehind;
    HWND    hwndOwner;
    LONG    cy;
    LONG    cx;
    LONG    y;
    LONG    x;
    ULONG   flStyle;
    PSZ     pszText;
    PSZ     pszClass;
    HWND    hwndParent;
} CREATESTRUCT;
```

### Other window lifecycle / query functions [DOC-IBM]

| Symbol | Prototype | Purpose |
|---|---|---|
| `WinDestroyWindow` | `BOOL APIENTRY WinDestroyWindow(HWND hwnd)` | Destroy a window and its children. |
| `WinShowWindow` | `BOOL APIENTRY WinShowWindow(HWND hwnd, BOOL fShow)` | Show or hide. |
| `WinSetWindowPos` | `BOOL APIENTRY WinSetWindowPos(HWND hwnd, ...)` | Move/size/Z-order/show via `SWP_*` flags (`SWP_SIZE 0x0001`, `SWP_MOVE 0x0002`, `SWP_SHOW 0x0008`, `SWP_ACTIVATE 0x0080`). |
| `WinEnableWindow` | `BOOL APIENTRY WinEnableWindow(HWND hwnd, BOOL fEnable)` | Enable/disable input. |
| `WinWindowFromID` | `HWND APIENTRY WinWindowFromID(HWND hwndParent, ULONG id)` | Find a child by id. |
| `WinQueryWindow` | `HWND APIENTRY WinQueryWindow(HWND hwnd, LONG cmd)` | Walk the window tree (`QW_NEXT 0`, `QW_PREV 1`, `QW_TOP 2`, `QW_BOTTOM 3`, `QW_OWNER 4`, `QW_PARENT 5`). |
| `WinQueryWindowRect` | `BOOL APIENTRY WinQueryWindowRect(HWND hwnd, PRECTL prclDest)` | Window rectangle in window coordinates - **bottom-left origin**, see the note below. |
| `WinSetWindowText` | `BOOL APIENTRY WinSetWindowText(HWND hwnd, PSZ pszText)` | Set title/text. |
| `WinSetMultWindowPos` | `BOOL APIENTRY WinSetMultWindowPos(HAB hab, PSWP pswp, ULONG cswp)` | Apply `WinSetWindowPos` to `cswp` windows at once from an array of `SWP` - the batch reposition used when laying out a dialog's controls together [DOC-IBM - `pm2.txt`]. |

> **`SWP` field order is not the argument order** [DOC-IBM - `pm4.txt`, `SWP`]:
> ```c
> typedef struct _SWP {
>     ULONG fl;                /* SWP_* options            */
>     LONG  cy;                /* height  <- BEFORE width  */
>     LONG  cx;                /* width                    */
>     LONG  y;                 /* y       <- BEFORE x      */
>     LONG  x;                 /* x                        */
>     HWND  hwndInsertBehind;
>     HWND  hwnd;
>     ULONG ulReserved1, ulReserved2;   /* must be 0 */
> } SWP;
> ```
> `WinSetWindowPos` takes `(x, y, cx, cy)` but `SWP` stores `(cy, cx, y, x)`. Filling the struct in
> call order silently swaps width with height and x with y - nothing errors, the window is just the
> wrong shape in the wrong place. Assign by field name, never with a positional initialiser.

Provenance: **[DOC-IBM]** `pmwin.h:335-341, 454-455, 469-485, 540-570`.

> **Coordinate origin - bottom-left, y increasing upward** [DOC-IBM]. Every coordinate above is
> measured from the **bottom-left**: `WinQueryWindowRect` returns a rect whose "bottom left corner is
> at the position (0,0)", and `WinSetWindowPos`'s x/y are "relative to the bottom left corner of its
> parent" (`pm2.txt`). This is inverted from Win32/X11 and fails **silently** - drawing and hit-tests
> land mirrored rather than erroring. In a `RECTL`, `yBottom < yTop`, the opposite of Win32's `RECT`.
> Full rule, including the `RECTL` +/-32767 field-range limit: `gpi-drawing.md` section "Coordinate origin".

### Saving and restoring a window's geometry [OBS-RE]

Persisting "where the window was" needs three things a naive `WinQueryWindowPos` -> INI ->
`WinSetWindowPos` round trip gets wrong.

**1. A maximized frame reports its MAXIMIZED rectangle.** Save that as the geometry and the window
"restores" to full screen for ever after  -  the real size is gone. `swp.fl` carries `SWP_MAXIMIZE`
(`0x0800`) / `SWP_MINIMIZE` (`0x0400`) [`pmwin.h:477-479`], so save the *state* separately and keep
the normal geometry yourself: track it on each `WM_SIZE` where neither bit is set. On restore,
apply the normal geometry **first**, then `SWP_MAXIMIZE`  -  that leaves the frame a sane rectangle
to un-maximize into.

**2. A saved position is not necessarily on the current desktop.** Video-mode changes are the usual
cause: a geometry saved at a larger resolution can put the frame entirely past the right or bottom
edge. Clamp against `WinQuerySysValue(HWND_DESKTOP, SV_CXSCREEN / SV_CYSCREEN)` on restore.

**3. The bottom-left origin makes the dangerous case the TOP one.** `y` is the **bottom** edge, so
the title bar sits at `y + cy`. A saved rectangle taller than the current desktop pushes the title
bar *above* the top of the screen  -  where there is nothing left to grab, and the window cannot be
dragged back. PM will place it there without complaint. Clamp `y + cy <= SV_CYSCREEN` explicitly;
it does not fall out of the horizontal check.

### There is no "always on top" [OBS-RE]

PM has no `WS_EX_TOPMOST` equivalent. `HWND_TOP` is a **placement passed to `WinSetWindowPos`**, not
an attribute the window keeps  -  one call raises the frame once, and the next window to be activated
goes straight over it. An "always on top" menu item implemented as a single `WinSetWindowPos` looks
completely dead.

The workable approximation is to re-assert the placement on a timer:

```c
WinSetWindowPos(hwndFrame, HWND_TOP, 0, 0, 0, 0, SWP_ZORDER);   /* every ~500 ms */
```

`SWP_ZORDER` alone reorders **without** activating, so it does not steal focus from whatever the
user is typing into. Turning the option off must simply stop re-asserting  -  do **not** place the
frame at `HWND_BOTTOM`, which sends it behind everything and is a different behaviour from "no
longer on top".

### Resize flicker: `CS_SIZEREDRAW` and clipping [OBS-RE]

`CS_SIZEREDRAW` (section 4) means "the whole window is redrawn on any size change". A client window whose
children cover it has nothing of its own to redraw  -  its `WM_SIZE` just repositions them  -  so the
flag buys only a full-area background repaint underneath the children on **every mouse-move of the
sizing border**. That is the classic "flickering behind the child control" report.

Two changes remove it: drop `CS_SIZEREDRAW`, and add clipping so the parent cannot paint over its
children at all  -  `CS_CLIPCHILDREN` (`0x20000000`) as a class style, `WS_CLIPCHILDREN` (same value)
as a window style. For a dialog, the window-style field of the `DIALOG` statement is where that
goes; see `resources-and-dialogs.md` section "Resizable dialogs".

---

## 5. The message loop [DOC-IBM]

The heart of a PM thread is the get-and-dispatch loop. Messages posted to the thread's queue are
retrieved with `WinGetMsg`, then handed to `WinDispatchMsg`, which calls the target window's
procedure.

| Symbol | Prototype (from `pmwin.h`) | Purpose |
|---|---|---|
| `WinGetMsg` | `BOOL APIENTRY WinGetMsg(HAB hab, PQMSG pqmsg, HWND hwndFilter, ULONG msgFilterFirst, ULONG msgFilterLast)` | Remove and return the next queued message into `*pqmsg`, blocking the thread until one is available. **Returns `FALSE` when the message is `WM_QUIT`** - the loop's termination signal - and `TRUE` otherwise. `hwndFilter`/`msgFilter*` restrict which messages are returned (all zero = no filter). |
| `WinDispatchMsg` | `MRESULT APIENTRY WinDispatchMsg(HAB hab, PQMSG pqmsg)` | Call the window procedure of `pqmsg->hwnd` with the message, returning its `MRESULT`. |
| `WinPeekMsg` | `BOOL APIENTRY WinPeekMsg(HAB hab, PQMSG pqmsg, HWND hwndFilter, ULONG msgFilterFirst, ULONG msgFilterLast, ULONG fl)` | Non-blocking look at the queue; `fl` is `PM_REMOVE` (`0x0001`) to dequeue or `PM_NOREMOVE` (`0x0000`) to leave the message. Returns `FALSE` if no matching message. |

The idiomatic loop [DOC]:

```c
QMSG qmsg;
while (WinGetMsg(hab, &qmsg, NULLHANDLE, 0, 0))
    WinDispatchMsg(hab, &qmsg);
```

It runs until a `WM_QUIT` makes `WinGetMsg` return `FALSE`.

Provenance: **[DOC-IBM]** `pmwin.h:1054-1068, 1100-1102`.

### `QMSG` - a dequeued message [DOC-IBM `pmwin.h:901-911`]

```c
typedef struct _QMSG {   /* qmsg */
    HWND    hwnd;        /* target window            */
    ULONG   msg;         /* message id (WM_*)        */
    MPARAM  mp1;         /* first packed parameter   */
    MPARAM  mp2;         /* second packed parameter  */
    ULONG   time;        /* message time             */
    POINTL  ptl;         /* mouse position           */
    ULONG   reserved;
} QMSG;
```

### Sending vs. posting [DOC-IBM]

Two ways to deliver a message to a window:

| Symbol | Prototype | Semantics |
|---|---|---|
| `WinSendMsg` | `MRESULT APIENTRY WinSendMsg(HWND hwnd, ULONG msg, MPARAM mp1, MPARAM mp2)` | **Synchronous** - calls the target window procedure directly and returns its `MRESULT`. Does not go through the queue. |
| `WinPostMsg` | `BOOL APIENTRY WinPostMsg(HWND hwnd, ULONG msg, MPARAM mp1, MPARAM mp2)` | **Asynchronous** - places the message on the target's queue and returns immediately (`TRUE` if queued). |
| `WinPostQueueMsg` | `BOOL APIENTRY WinPostQueueMsg(HMQ hmq, ULONG msg, MPARAM mp1, MPARAM mp2)` | Post to a queue by handle rather than by window. |
| `WinBroadcastMsg` | `BOOL APIENTRY WinBroadcastMsg(HWND hwnd, ULONG msg, MPARAM mp1, MPARAM mp2, ULONG rgf)` | Send/post to many windows; `rgf` selects `BMSG_POST 0`, `BMSG_SEND 0x0001`, `BMSG_POSTQUEUE 0x0002`, `BMSG_DESCENDANTS 0x0004`, `BMSG_FRAMEONLY 0x0008`. |
| `WinInSendMsg` | `BOOL APIENTRY WinInSendMsg(HAB hab)` | `TRUE` if the current message is being processed as the result of a `WinSendMsg` from another thread. |

Provenance: **[DOC-IBM]** `pmwin.h:1035-1038, 1070-1073, 1161, 1164-1175, 1226-1229`.

### Queue status and message time [DOC-IBM `pmwin.h:1182-1202`]

`WinQueryQueueStatus(HWND hwndDesktop)` returns a bit mask of pending input classes: `QS_KEY`
(`0x0001`), `QS_MOUSEBUTTON` (`0x0002`), `QS_MOUSEMOVE` (`0x0004`), `QS_MOUSE` (`0x0006`),
`QS_TIMER` (`0x0008`), `QS_PAINT` (`0x0010`), `QS_POSTMSG` (`0x0020`), `QS_SENDMSG` (`0x0400`).
`WinQueryMsgPos` and `WinQueryMsgTime` return the mouse position and timestamp of the last
retrieved message.

---

## 6. The core message set [DOC-IBM]

Message ids are `WM_*` constants; those below `WM_USER` (`0x1000`) are system-defined, and an
application numbers its private messages from `WM_USER` upward. The interpretation of `mp1`/`mp2`
is per-message.

### Lifecycle and window-state messages [DOC-IBM `pmwin.h:914-962`]

| Message | Value | Delivered when / carries |
|---|---|---|
| `WM_NULL` | `0x0000` | No-op / wake. |
| `WM_CREATE` | `0x0001` | Window is being created. `mp2` -> `CREATESTRUCT`; `mp1` -> control data. Returning `TRUE` aborts creation. |
| `WM_DESTROY` | `0x0002` | Window is being destroyed (last chance to release resources). |
| `WM_ENABLE` | `0x0004` | Enable state changed. |
| `WM_SHOW` | `0x0005` | Visibility changed. |
| `WM_MOVE` | `0x0006` | Window moved. |
| `WM_SIZE` | `0x0007` | Window resized. `mp1` = old (cx,cy), `mp2` = new (cx,cy), each two `SHORT`s (`SHORT1FROMMP`/`SHORT2FROMMP`). |
| `WM_ACTIVATE` | `0x000d` | Activation gained/lost. |
| `WM_SETFOCUS` | `0x000f` | Focus gained/lost (`mp2` = TRUE if gaining). |
| `WM_PAINT` | `0x0023` | The window has an invalid region to redraw (Section 7). |
| `WM_COMMAND` | `0x0020` | A command (menu/button/accelerator). See `CMDMSG` below. |
| `WM_SYSCOMMAND` | `0x0021` | A system command. |
| `WM_HELP` | `0x0022` | Help requested. |
| `WM_TIMER` | `0x0024` | A timer fired; `mp1` = `SHORT1FROMMP` timer id (Section 10). |
| `WM_CLOSE` | `0x0029` | The user asked to close the window. The default response posts `WM_QUIT`. |
| `WM_QUIT` | `0x002a` | Terminate the message loop (makes `WinGetMsg` return `FALSE`). |
| `WM_SYSCOLORCHANGE` | `0x002b` | System colors changed. |
| `WM_CONTROL` | `0x0030` | A control is notifying its owner. `SHORT1FROMMP(mp1)` = control id, `SHORT2FROMMP(mp1)` = notification code; **`mp2` means whatever that code says it means** - see below. |
| `WM_VSCROLL` / `WM_HSCROLL` | `0x0031` / `0x0032` | Scroll bar activity. |
| `WM_INITDLG` | `0x003b` | A dialog is initializing (Section 8). |
| `WM_MENUSELECT` | `0x0034` | Menu item highlighted. |

### `CMDMSG` - accessing `WM_COMMAND`/`WM_HELP`/`WM_SYSCOMMAND` [DOC-IBM `pmwin.h:1010-1020`]

```c
#pragma pack(1)
typedef struct _COMMANDMSG {   /* commandmsg */
    USHORT  cmd;       /* mp1 : the command id       */
    USHORT  unused;
    USHORT  source;    /* mp2 : CMDSRC_* origin      */
    USHORT  fMouse;    /* mp2 : mouse-initiated flag  */
} CMDMSG;
#define COMMANDMSG(pmsg) ((PCMDMSG)((PBYTE)pmsg + sizeof(MPARAM)))
```

The command source (`source`) is one of `CMDSRC_PUSHBUTTON` (1), `CMDSRC_MENU` (2),
`CMDSRC_ACCELERATOR` (3), `CMDSRC_FONTDLG` (4), `CMDSRC_FILEDLG` (5), `CMDSRC_PRINTDLG` (6),
`CMDSRC_COLORDLG` (7), or `CMDSRC_OTHER` (0) [DOC-IBM `pmwin.h:994-1002`].

### Frame messages [DOC-IBM `pmwin.h:2794-2818`]

`WM_FOCUSCHANGE` (`0x0043`), `WM_ERASEBACKGROUND` (`0x004f`), `WM_FORMATFRAME` (`0x0041`),
`WM_UPDATEFRAME` (`0x0042`), `WM_MINMAXFRAME` (`0x0046`), `WM_TRANSLATEACCEL` (`0x004b`),
`WM_WINDOWPOSCHANGED` (`0x0055`) - sent to frame windows to manage layout, focus, and the
background of the client.

### Mouse messages [DOC-IBM `pmwin.h:1313-1364`]

All carry the pointer position in `mp1` (two `SHORT`s: x = `SHORT1FROMMP`, y = `SHORT2FROMMP`, in
window coordinates) and hit-test/flags in `mp2`.

| Message | Value | Meaning |
|---|---|---|
| `WM_MOUSEMOVE` | `0x0070` | Pointer moved over the window. |
| `WM_BUTTON1DOWN` | `0x0071` | Button 1 pressed. |
| `WM_BUTTON1UP` | `0x0072` | Button 1 released. |
| `WM_BUTTON1DBLCLK` | `0x0073` | Button 1 double-click. |
| `WM_BUTTON2DOWN` | `0x0074` | Button 2 pressed. |
| `WM_BUTTON2UP` | `0x0075` | Button 2 released. |
| `WM_BUTTON2DBLCLK` | `0x0076` | Button 2 double-click. |
| `WM_BUTTON3DOWN` | `0x0077` | Button 3 pressed. |
| `WM_BUTTON3UP` | `0x0078` | Button 3 released. |
| `WM_BUTTON3DBLCLK` | `0x0079` | Button 3 double-click. |
| `WM_BEGINDRAG` | `0x0420` | Direct-manipulation drag began. |
| `WM_CONTEXTMENU` | `0x0424` | Context-menu request. |

`WM_MOUSEFIRST`/`WM_MOUSELAST` (`0x0070`/`0x0079`) bound the mouse-message range for message
filters.

### Mouse capture, pointer shape, and rubber-band tracking [DOC-IBM]

The messages above tell you *what happened*; these functions are how a window takes control of the
mouse while a drag is in progress.

| Symbol | Prototype (`pmwin.h`) | Purpose |
|---|---|---|
| `WinSetCapture` | `BOOL WinSetCapture(HWND hwndDesktop, HWND hwnd)` [`pmwin.h:1305-1306`] | Route **all** mouse messages to `hwnd`. `NULLHANDLE` releases the capture; `HWND_THREADCAPTURE` (`(HWND)5`, [`pmwin.h:236`]) routes to the thread's queue instead - see the second warning. |
| `WinQueryCapture` | `HWND WinQueryCapture(HWND hwndDesktop)` [`pmwin.h:1309`] | The window currently holding the capture. |
| `WinSetPointer` | `BOOL WinSetPointer(HWND hwndDesktop, HPOINTER hptrNew)` [`pmwin.h:3773-3774`] | Set the pointer shape. |
| `WinQueryPointer` | `HPOINTER WinQueryPointer(HWND hwndDesktop)` [`pmwin.h:3842`] | The current pointer. |
| `WinQueryPointerPos` | `BOOL WinQueryPointerPos(HWND hwndDesktop, PPOINTL pptl)` [`pmwin.h:3843-3844`] | Pointer position, in **desktop** coordinates. |
| `WinLoadPointer` | `HPOINTER WinLoadPointer(HWND hwndDesktop, HMODULE hmod, ULONG idres)` [`pmwin.h:3829-3831`] | Load a pointer from a resource. |
| `WinShowPointer` | `BOOL WinShowPointer(HWND hwndDesktop, BOOL fShow)` [`pmwin.h:3778-3779`] | Show/hide the pointer. |
| `WinTrackRect` | `BOOL WinTrackRect(HWND hwnd, HPS hps, PTRACKINFO pti)` [`pmwin.h:3568-3570`] | Run a modal rubber-band move/resize loop. `TRUE` = the user accepted; `FALSE` is ambiguous - see below. |

The first argument is a desktop handle: pass `HWND_DESKTOP`. These take one because pointer and
capture state is per-desktop, not per-window.

> **Without `WinSetCapture`, a button-up that happens outside your window never arrives.** Mouse
> messages go to the window under the pointer, so a drag that starts inside your window and ends
> outside it delivers the `WM_BUTTON1DOWN` and then simply stops - no `WM_BUTTON1UP`, no error. Any
> state you armed on button-down (a selection, a rubber band, a captured origin) stays armed
> forever, and the window behaves as though the button were still held. The fix is the standard
> pairing: capture on button-down, release with `WinSetCapture(HWND_DESKTOP, NULLHANDLE)` on
> button-up. [DOC-IBM `pm4.txt` - "Capturing mouse input is useful if a window needs to receive all
> mouse input, even when the pointer moves outside the window".]

> **Capturing to the *queue* rather than a window makes messages undispatchable.** Passing
> `HWND_THREADCAPTURE` [`pmwin.h:236`] routes mouse input to the calling thread's queue instead of
> to a window, and then each `QMSG` arrives with `hwnd` set to `NULL`. `WinDispatchMsg` has no
> window to hand those to, so they never reach any window procedure - the message loop itself must
> handle them. Take this route while keeping an ordinary loop and mouse input vanishes silently.
> [DOC-IBM `pm4.txt:23380`.]

> **If you handle `WM_MOUSEMOVE` and do not pass it on, the pointer shape stops being maintained.**
> Setting the pointer is *default* processing: `WinDefWindowProc` calls `WinSetPointer` on every
> `WM_MOUSEMOVE`. A window procedure that swallows the message inherits that job. So either call
> `WinSetPointer` yourself for the whole window, or return the message to `WinDefWindowProc` - a
> handler that does neither leaves whatever shape the last window set, which reads as "the pointer
> is stuck as an I-beam / hourglass over my window". This is also why the hourglass idiom must
> re-assert the shape from `WM_MOUSEMOVE` for the duration of a long operation, not just once
> before it. [DOC-IBM `pm3.txt` "WM_MOUSEMOVE - Default Processing"; `pmv2base.txt`.]

> **`WinTrackRect` returning `FALSE` does not mean the user cancelled.** IBM gives the same return
> two meanings: tracking was cancelled, **or** the pointing device was already captured when the
> call was made. Treating `FALSE` as "user declined" therefore silently swallows a programming
> error - typically your own `WinSetCapture` from the button-down handler that started the drag.
> There is also a precondition worth knowing: the function notes which button was down when it
> began, and only completes when **that same button** is released. [DOC-IBM `pm2.txt:42065`,
> `pm2.txt:42079`.] Only one tracking rectangle may be in use at a time [`pm2.txt:42030`].

`WinTrackRect` drives the whole rubber-band interaction itself - it does not return until the user
commits or cancels. `TRACKINFO` [`pmwin.h:3551-3565`] supplies the border and grid sizes, the
starting `rclTrack`, an `rclBoundary` to confine it to, min/max track sizes, and an `fs` field of
`TF_*` flags [`pmwin.h:3576-3588`]: which edges move (`TF_LEFT`/`TF_TOP`/`TF_RIGHT`/`TF_BOTTOM`, or
`TF_MOVE` = all four, moving rather than sizing), plus `TF_GRID`, `TF_STANDARD`,
`TF_ALLINBOUNDARY` / `TF_PARTINBOUNDARY` and `TF_SETPOINTERPOS`.

### Keyboard message [DOC-IBM `pmwin.h:1385-1408`]

`WM_CHAR` (`0x007a`) delivers every keystroke. `mp1` low word is the **key-flags** word (`KC_*`),
which tells the receiver which fields of the message are valid:

| Flag | Value | Meaning |
|---|---|---|
| `KC_CHAR` | `0x0001` | A character code is present. |
| `KC_VIRTUALKEY` | `0x0002` | A virtual-key code (`VK_*`) is present. |
| `KC_SCANCODE` | `0x0004` | A hardware scan code is present. |
| `KC_SHIFT` | `0x0008` | Shift was down. |
| `KC_CTRL` | `0x0010` | Ctrl was down. |
| `KC_ALT` | `0x0020` | Alt was down. |
| `KC_KEYUP` | `0x0040` | This is a key-release (else key-press). |
| `KC_PREVDOWN` | `0x0080` | The key was already down (auto-repeat). |
| `KC_LONEKEY` | `0x0100` | A shift key pressed and released alone. |
| `KC_DEADKEY` | `0x0200` | The character code is a dead key's glyph (an accent). See *Dead keys* below. |
| `KC_COMPOSITE` | `0x0400` | The character code combines this key with the preceding dead key. |
| `KC_INVALIDCOMP` | `0x0800` | This key does not combine with the preceding dead key. See *Dead keys*. |
| `KC_TOGGLE` | `0x1000` | Defined; not covered here. |
| `KC_INVALIDCHAR` | `0x2000` | The character is not valid for the current translation tables [DOC-IBM - `pm4.txt` *Message Flags*]. |
| `KC_DBCSRSRVD1` | `0x4000` | Reserved (DBCS). |
| `KC_DBCSRSRVD2` | `0x8000` | Reserved (DBCS); IBM's private DBCS header calls it the interim-character flag. See *DBCS characters*. |

Values [DOC-IBM `pmwin.h:1389-1408`]; meanings of the composite and invalid-composite flags
[DOC-IBM - `pm3.txt` *WM_CHAR Field - fsflags*].

`mp1` also carries the repeat count (`CHAR3FROMMP`) and scan code (`CHAR4FROMMP`); `mp2` carries the
character code `usch` (`SHORT1FROMMP`) and the virtual-key code (`SHORT2FROMMP`) - the `CHRMSG`
layout [DOC-IBM `pmwin.h:1429-1436`]. `WM_VIOCHAR` (`0x007b`) is the advanced-VIO keystroke variant.

#### `usch` is a code-page character - convert it before storing it as Unicode [DOC-IBM]

**The trap.** A control that keeps its text as UTF-8 (or UCS-2) inserts `usch` as if it were
already in that encoding. ASCII keys work, so nothing looks wrong until someone types an accented
letter. [OBS-RE - a UTF-8 editor control that inserted `usch` unconverted: Alt+keypad 129
(`u`-umlaut in CP437) was stored as a lone `0x81`, invalid UTF-8; in a document saved back to an
8-bit code page the same keystroke became `0x7F`, a different character, after the save's
conversion substituted it. Both saves reported success.]

**The fact.** `usch` is the key's character "resulting from the current code page" [DOC-IBM -
`pm3.txt` *WM_CHAR Field - usch*]. Which code page is not stated on that page; IBM's DBCS guide
names the **message queue code page** for `WM_CHAR` [DOC-IBM - *DBCS Design Guide and Information for OS/2*, os2books
`dbcs/os2dbcs`, topic *WM_CHAR*], consistent with text entered in a dialog arriving "in the code page
of the queue" [DOC-IBM - `pm5.txt` *Code Pages*]. Read it with `WinQueryCp(HMQ_CURRENT)` [DOC-IBM
`pmwin.h:4163`] and convert through a `UniUconv` object for that code page
(`unicode-conversion.md`). A per-code-page cached object is fine here: SO/SI shift codes belong to
host (EBCDIC) mixed data, and PC data - single- or double-byte - has none [DOC-IBM - *DBCS Design
Guide and Information for OS/2*, *Code Translation*], so a PC code page carries no state from one
character to the next.

**How to verify.** Type Alt plus a keypad code above 127, save, and hexdump the file
(`recipes/setup-test-vm.md` shows the scancodes).

**The tell.** An invalid-byte marker, or the wrong letter after saving, exactly where an accented
character was typed.

#### Dead keys [DOC-IBM]

IBM gives one rule per flag [DOC-IBM - `pm3.txt` *WM_CHAR Field - fsflags*]: for `KC_DEADKEY` the
application shows the dead key's glyph **without advancing the cursor**; `KC_COMPOSITE` carries the
combined character; for `KC_INVALIDCOMP` the application advances past the dead-key glyph and then,
"if the current character is not a space", sounds the alarm and shows the new character.

- **Nothing guarantees what follows a dead key.** `pm3.txt` does not say; `pm4.txt` says only that
  the next `WM_CHAR` is *typically* a `KC_COMPOSITE` message [DOC-IBM - `pm4.txt` *Message Flags*].
  Handle a plain character message after a dead key too.
- **The trap:** a `KC_DEADKEY` message also carries `KC_CHAR` [DOC-IBM - `pm4.txt` *Message Flags*],
  so a handler that inserts every `KC_CHAR` message types the accent *and* then the composite.
- **A worked technique** [SRC - `TYPER.C`, `TyperChar`, in the DBCS sample archive
  `pub/os2/dev/samples/misc/DBCS_1990-03-19.zip` on Hobbes]: store the dead key's glyph, then step
  the insertion point back over it (`typer.c:293`) so the next `KC_COMPOSITE` or `KC_INVALIDCOMP`
  character overwrites it; on `KC_INVALIDCOMP` with a space, step forward over the glyph instead
  (`typer.c:270-274`). That sample beeps on any other invalid composite and does *not* store the new
  character (`typer.c:280`) - narrower than the `pm3.txt` wording.

Not yet observed on a keyboard layout that has dead keys [unverified].

#### The repeat count [DOC-IBM]

When key repeat outruns the application, PM folds the repeats into a single `WM_CHAR` and raises the
count byte; IBM advises checking every message so no keystroke is lost, and also says a program may
ignore the count - arrow keys being the example where skipping ahead is unwanted [DOC-IBM - `pm4.txt`
*Keyboard Messages*].

#### DBCS characters [DOC-IBM]

**The trap.** Searching the Toolkit books for how a double-byte character arrives in `usch` finds
nothing - the `pm3.txt` entry says only "Character code" - and it is tempting to record it as
undocumented and refuse such input. It is documented, in a different book. [Negative result:
`pm2.txt`-`pm5.txt`, `cp*.txt` and both reference corpora were searched first.]

**The fact.**

- With a combined (DBCS) queue code page, a single-byte character is in the low byte of `usch` with
  the high byte zero; a **double-byte character has its first (lead) byte in the low byte and its
  second byte in the high byte** [DOC-IBM - *DBCS Design Guide and Information for OS/2*, os2books `dbcs/os2dbcs`, topic
  *WM_CHAR*]. That is `CHAR1FROMMP(mp2)` and `CHAR2FROMMP(mp2)` [DOC-IBM `pmwin.h:185-186`].
- Characters from the input method arrive as ordinary `WM_CHAR` messages **without a scan code**,
  and DBCS text can also arrive from the clipboard [DOC-IBM - DBCS guide, topics *Input Mechanism in
  DBCS PM* and *Keyboard Input*]. Do not require `KC_SCANCODE` on character messages.
- **`WM_QUERYCONVERTPOS`** (`0x00b0`; replies `QCP_CONVERT` 1, `QCP_NOCONVERT` 0) [DOC-IBM
  `pmwin.h:4514-4518`] asks the focus window whether conversion may start and where its cursor is.
  The default window procedure answers `QCP_CONVERT` with a -1,-1 position [DOC-IBM - `pm3.txt`
  *WM_QUERYCONVERTPOS - Default Processing*], which gives fixed-position conversion; answering
  `QCP_CONVERT` with the cursor rectangle gives on-the-spot conversion [DOC-IBM - DBCS guide,
  *On-The-Spot Conversion in DBCS PM*]. `FCF_DBE_APPSTAT` (`0x80000000`, under `INCL_NLS`)
  [DOC-IBM `pmwin.h:2711`] enables DBCS input and the keyboard status area for a frame [DOC-IBM -
  DBCS guide, *DBCS Input and PM Application Programs*].
- **Interim characters.** The DBCS DDK's *private* header defines `KC_DBE_INTERIMCHAR` as
  `KC_DBCSRSRVD2` under "KC_ flags definition of WM_CHAR", and adds `QCP_VERTICAL` 2 and
  `QCP_SHIELD` 0x8000 as `WM_QUERYCONVERTPOS` replies [DOC-IBM - DBCS DDK `H/os2nlsp.h:34-36`,
  `:228-230`]; the public `H/os2nls.h:374` has `DBE_MCTL_INTERIMREQUEST` for `WinDBCSModeControl`.
  When PM sends interim characters unrequested was not found [unverified]; a handler that inserts
  text should at least not insert a message carrying that bit.

**Prior art that works on non-DBCS OS/2** [SRC - Hobbes]:

- **KIME 0.1.4**, a Korean input method (`pub/os2/util/international/KIME_0-1-4.zip`, source in the
  nested `kimesrc.zip`), posts each finished character as one `WM_CHAR` with `KC_CHAR`, repeat 1,
  scan code 0, lead byte low (`kime/kimehook.c:316-327`). It leaves a window's keystrokes alone
  unless it judges the window DBCS-capable (`kime/kimehook.c:633-634`); when the user toggles
  Hangul mode it re-tests the window by sending `WM_QUERYCONVERTPOS` and requiring `QCP_CONVERT`
  (`kime/kimehook.c:629-631`, `kime/khserver.c:299-313`). Its readme has the user add 949 to
  `CODEPAGE=` and start the target program after `chcp 949`, so the bytes arrive in the target's
  own code page.
- **KShell 0.8.1**, a PM window for VIO programs with DBCS I/O (`pub/os2/util/shell/KShell_0-8-1.zip`,
  nested `kshellsrc.zip`), treats `KC_CHAR` without `KC_SCANCODE` as clipboard or DBCS input and
  forwards the low byte, then the high byte if non-zero (`viodmn.c:827-839`); it pastes DBCS text as
  one `WM_CHAR` per character with the lead byte low (`kshell.c:776-808`), and swallows
  `KC_VIRTUALKEY` messages whose key code is 0x80-0xFF, the DBCS virtual-key range
  (`kshell.c:1204-1205`; `VK_DBCSFIRST`/`VK_DBCSLAST` at `pmwin.h:1525-1526`).

**The consequence worth remembering:** a custom control that leaves `WM_QUERYCONVERTPOS` to
`WinDefWindowProc` answers `QCP_CONVERT`, so it passes KIME's `WM_QUERYCONVERTPOS` test even on
Western OS/2 - whether or not it was written with DBCS in mind. If it then refuses or mangles a
non-zero high byte in `usch`, Korean input breaks there. [Inferred from the default processing
above and KIME's source; not observed with KIME running.]

**Not established** [unverified]: whether a message queue starts in its process's code page
(`pm5.txt` *Code Pages* says so for a GPI presentation space only).

#### AltGr characters: the flags are not documented [DOC-IBM]

`VK_ALTGRAF` is `0x0C` [DOC-IBM `pmwin.h:1467`], but no source found says which `KC_*` shift flags
accompany a *character* produced with AltGr. Searched: `pm2.txt`-`pm5.txt`, `cpgref.txt`, both
reference corpora. (Negative result.) A handler that treats `KC_CTRL | KC_ALT` character messages as
shortcuts may be discarding AltGr characters; observe on a layout that has them before relying on
either reading.

#### `F10` never reaches the focus window [OBS-RE]

PM reserves **F10** for activating the frame's action bar, and takes it before `WM_CHAR` is
delivered. A control cannot see it however correctly it is written - a `case VK_F10` in its `WM_CHAR`
handler is dead code.

Measured by probing every `KC_VIRTUALKEY` message a focused custom control received: pressing
**Shift+F10** delivered `VK_SHIFT` (`0x09`) and nothing else, while `VK_LEFT` (`0x15`) arrived
normally in the same build. The control had focus throughout - `Ctrl+End` reached it and moved the
caret.

This matters when porting, because **Win32 gives Shift+F10 to the application for free**: the system
synthesises `WM_CONTEXTMENU` from it, so Win32 code that opens a context menu from the keyboard
usually has no explicit F10 handling to port, and writing the obvious equivalent produces a key
binding that never fires and no diagnostic anywhere. The route on PM is an **accelerator on the
frame** (`VK_F10, IDM_..., VIRTUALKEY, SHIFT`), which does fire, with the frame then calling into the
control - see `recipes/porting-a-windows-app.md`.

#### A window MUST pass keys it does not use to `WinDefWindowProc` [DOC-IBM]

`WM_CHAR` "is sent by controls to their owner window if they do not process the key stroke
themselves ... the most common means by which the input focus is switched around the various controls
in a dialog box" [DOC-IBM - `pm3.txt`, *WM_CHAR (in Frame Controls)*]. The forwarding is done by the
default procedure: "The default window procedure **sends the message to the owner window if it
exists**, otherwise it takes no action on this message other than to set `rc` to FALSE" [DOC-IBM -
`pm3.txt`, *WM_CHAR Default Processing*].

**So returning `FALSE` from your own window procedure is not the same as not handling the key.** A
`return MRFROMLONG(FALSE)` never reaches `WinDefWindowProc`, so the message never travels up the
owner chain, and everything that depends on that chain silently stops working:

- **frame menu mnemonics** - the menu pulls down and then ignores every keystroke;
- Tab / Backtab focus movement between controls;
- arrow-key movement within a control group;
- Enter and Escape reaching the dialog's default and cancel buttons.

*Tell:* the letter you pressed appears **inside the focused control** instead of activating the
menu item. Consume a key only when you actually used it; otherwise fall through to
`WinDefWindowProc`. [OBS-RE - a Scintilla control that returned `FALSE` for unhandled keys made a
correctly-built menu bar completely inert.]

#### Ctrl+letter arrives as the ASCII control code, not the letter [OBS-RE]

`Ctrl+A` ... `Ctrl+Z` are delivered as `KC_CHAR` with the character code **1-26**, not `'A'`-`'Z'`.
A handler that only inspects printable characters (`ch >= 32`) never sees any Ctrl shortcut at all.
Recover the letter with `'A' + (ch - 1)` before dispatching, and check `KC_CTRL` in the flags word.

#### The traditional OS/2 editing keys [DOC-IBM]

Users expect the CUA bindings, which IBM documents for the built-in text controls [DOC-IBM -
`pmv2base.txt`, entry-field and MLE sections]:

| Keystroke | Action |
|---|---|
| `Ctrl+Insert` | Copy |
| `Shift+Insert` | Paste |
| `Shift+Delete` | Cut |

`WC_ENTRYFIELD` and `WC_MLE` implement these themselves (via `EM_COPY`/`EM_CUT`/`EM_PASTE` and
`MLM_*`). **A custom editing control must provide them explicitly** - normally as accelerators
(section `resources-and-dialogs.md` 9). Ship them *alongside* the Windows-style `Ctrl+C`/`V`/`X`, not
instead of them.

---

## 7. Painting [DOC-IBM]

A window paints in response to `WM_PAINT`. Painting is bracketed by `WinBeginPaint` /
`WinEndPaint`, which yield and release a **presentation space** (`HPS`) clipped to the window's
invalid region; the actual drawing is done with the Gpi functions on that `HPS` (see
`pm-graphics.md`).

| Symbol | Prototype (from `pmwin.h`) | Purpose |
|---|---|---|
| `WinBeginPaint` | `HPS APIENTRY WinBeginPaint(HWND hwnd, HPS hps, PRECTL prclPaint)` | Begin painting; returns a cached or supplied `HPS` and fills `*prclPaint` with the rectangle to redraw. Pass `hps` = `NULLHANDLE` to obtain a cache PS. |
| `WinEndPaint` | `BOOL APIENTRY WinEndPaint(HPS hps)` | End painting; validates the region and releases a cache PS. |
| `WinGetPS` | `HPS APIENTRY WinGetPS(HWND hwnd)` | Obtain a PS for the whole window outside a `WM_PAINT`. |
| `WinReleasePS` | `BOOL APIENTRY WinReleasePS(HPS hps)` | Release a `WinGetPS` presentation space. |
| `WinOpenWindowDC` | `HDC APIENTRY WinOpenWindowDC(HWND hwnd)` | Open the window's device context. |
| `WinInvalidateRect` / `WinInvalidateRegion` | - | Mark a region invalid, causing a later `WM_PAINT`. Its third argument decides whether *descendants* are invalidated too - see the note below. |
| `WinValidateRect` | `BOOL APIENTRY WinValidateRect(HWND hwnd, PRECTL prcl, BOOL fIncludeChildren)` [`pmwin.h:854-856`] | The inverse: remove a rectangle from the update region, cancelling the pending paint for it. |
| `WinQueryUpdateRect` | `BOOL APIENTRY WinQueryUpdateRect(HWND hwnd, PRECTL prcl)` [`pmwin.h:876-877`] | The pending invalid rectangle, **without** beginning a paint. `WinQueryUpdateRegion` [`pmwin.h:879-880`] gives the region form. |
| `WinScrollWindow` | `LONG APIENTRY WinScrollWindow(HWND hwnd, LONG dx, LONG dy, PRECTL prclScroll, PRECTL prclClip, HRGN hrgnUpdate, PRECTL prclUpdate, ULONG rgfsw)` [`pmwin.h:364-371`] | Blit a rectangle of the window by (`dx`,`dy`) instead of repainting it. |
| `WinFillRect` | `BOOL APIENTRY WinFillRect(HPS hps, PRECTL prcl, LONG lColor)` | Fill a rectangle with a color. Fills the **left and bottom** edges but **not** the right and top (see boundary rule below). |

`WinScrollWindow` is how a scrolling view avoids redrawing everything: it moves the pixels that are
still valid and leaves only the newly exposed strip to paint. Pass `SW_INVALIDATERGN` in `rgfsw` to
have that exposed area added to the update region automatically, which produces the `WM_PAINT` for
it; without that flag you are responsible for invalidating it yourself, and the strip keeps stale
pixels. The two flags are `SW_SCROLLCHILDREN` (`0x0001`) and `SW_INVALIDATERGN` (`0x0002`)
[`pmwin.h:386-387`] - child windows are **not** scrolled unless you ask. `prclScroll` = `NULL`
scrolls the whole window. [DOC-IBM `pmv2base.txt:12431` - "If you set the `SW_INVALIDATERGN` flag
for this function, the areas you uncover by scrolling are added to the window's update region
automatically".]

> **The sign of `dy`: IBM's two books read opposite ways - follow the worked example, and verify on
> target.** `pmv2base.txt:12433-12442` scrolls a text editor's content *up* by one line with a
> **negative** `dy` (`-(iVScrollInc)`), describing the newly uncovered area as being at the
> **bottom** of the window - which is self-consistent, since content moving up exposes a strip at
> the bottom. But the parameter description at `pm2.txt:32168` reads "`lDy` - Amount of vertical
> scroll **upward** (in device units)", which taken alone implies the opposite sign.
>
> Do not try to settle it by reasoning from PM's Y-up coordinate convention - that argument does not
> decide the question, and getting it backwards inverts the scroll. Use the worked example (negative
> `dy` moves content up, exposing at the bottom) and confirm against your own window before building
> on it. [DOC-IBM, both cited - the conflict is between IBM's own books.]

> **Invalidating a window that is fully covered by a child repaints nothing visible.** The common
> layout - a client window whose entire area is one child control - means every pixel the user sees
> belongs to the child, so `WinInvalidateRect(hwndClient, NULL, TRUE)` schedules a `WM_PAINT` for a
> window with no exposed area. The symptom is stale pixels left behind by something that used to be
> on top (a dismissed modal dialog is the usual culprit), which then clear as soon as anything makes
> the child redraw for its own reasons - so it reads as an intermittent painting glitch rather than a
> missing call. Invalidate the window that actually owns the pixels. [OBS-RE - a file dialog's
> footprint stayed on screen after it closed, until the editor scrolled.]

> **`WM_CONTROL`'s `mp2` is not one type - switch on the notification code before you dereference
> it.** A single control multiplexes every notification it has through one message, and each code
> defines `mp2` independently: some send a pointer to a structure, some send a handle, some send
> nothing. Reading `mp2` as a pointer without first checking `SHORT2FROMMP(mp1)` therefore
> dereferences whatever the *other* notifications happen to put there - a window handle is a small
> integer, so this is a wild pointer, not a null one, and it faults rather than failing gracefully.
>
> The bug hides well: a handler is usually written while testing one notification, and the wrong
> branch only runs when some *other* notification arrives - which may be gated behind a feature flag
> that is off by default. In one case a Scintilla control's `SCEN_CHANGE` (which puts an `HWND` in
> `mp2`) was being read as the `SCNotification *` that its other notifications pass, and the crash
> stayed dormant until a settings file first restored the guarding feature as enabled. [OBS-RE]
>
> Corollary worth generalising: **adding settings persistence changes your startup conditions**, so
> it wakes latent bugs in code that only ever ran with defaults. Expect a round of them, and bisect
> the settings file - by section, then by key - rather than re-reading the parser.

### Presentation-space ownership - which `HPS` may be released, and how [DOC-IBM]

There are two kinds of `HPS` and they are released differently; releasing the wrong kind, or using a
handle after release, is a defect the API will not report.

- **`WinGetPS` returns a cache "micro presentation space"** [DOC-IBM - `pm2.txt`, *WinGetPS*],
  intended "for simple drawing operations that do not depend on long-term data being stored in the
  presentation space." Its initial state matches a `GpiCreatePS` space, with the color table in
  default color-index mode.
- **`WinReleasePS` releases *only* cache presentation spaces** [DOC-IBM - `pm2.txt`,
  *WinReleasePS*]: "Only cache presentation spaces can be released using this method, after which the
  presentation space is returned to the cache to be used again. **The presentation-space handle
  should not be used following this call.**"
- **`WinBeginPaint` behaves differently depending on what you pass** [DOC-IBM - `pm2.txt`,
  *WinBeginPaint*]: with an existing PS, "its update region is set and the device context of the
  window is associated with the presentation space"; otherwise "a cache presentation space is
  obtained specifically for the window." Either way the window's update region is reset to
  `NULLHANDLE`, and it is *assumed* that the drawing which follows restores the window to a fully
  correct state - PM will not ask again.
- **`WinEndPaint` unwinds whichever it was** [DOC-IBM - `pm2.txt`, *WinEndPaint*]: a cache PS "is
  returned to the cache"; other presentation spaces "have their original drawing state restored,
  including reassociating the original device context (if there was one)."

The practical rule for a port: a PS you obtained from the cache (`WinGetPS`, or `WinBeginPaint` with
`NULLHANDLE`) is borrowed and must be given back within the same handler, and the handle is dead
afterwards. A PS you created with `GpiCreatePS` is yours and outlives the paint bracket.

> **Rectangle boundary rule** - a `RECTL` includes its **left and bottom** edges and excludes its
> **right and top** (inclusive on the *origin-side* edges, since the origin is bottom-left), with the
> top-left and bottom-right corner points included as an exception. Full statement and the
> `WinDrawBorder` counterpart: `gpi-drawing.md` section "Rectangle boundary rule".

The canonical `WM_PAINT` handler [DOC]:

```c
case WM_PAINT: {
    RECTL rcl;
    HPS hps = WinBeginPaint(hwnd, NULLHANDLE, &rcl);
    /* draw with Gpi calls on hps, clipped to rcl */
    WinEndPaint(hps);
    return 0;
}
```

Provenance: **[DOC-IBM]** `pmwin.h:343-362, 389-391`.

---

## 8. Dialogs [DOC-IBM]

A dialog is a frame whose child controls are described by a **dialog template** resource, loaded
from a module. A dialog has its own procedure with the same `PFNWP` signature; unhandled messages
go to `WinDefDlgProc` (the dialog analogue of `WinDefWindowProc`).

| Symbol | Prototype (from `pmwin.h`) | Purpose |
|---|---|---|
| `WinLoadDlg` | `HWND APIENTRY WinLoadDlg(HWND hwndParent, HWND hwndOwner, PFNWP pfnDlgProc, HMODULE hmod, ULONG idDlg, PVOID pCreateParams)` | Create a dialog from a template resource and return its handle (modeless - the caller must run/dispatch it). |
| `WinDlgBox` | `ULONG APIENTRY WinDlgBox(HWND hwndParent, HWND hwndOwner, PFNWP pfnDlgProc, HMODULE hmod, ULONG idDlg, PVOID pCreateParams)` | Load, run **modally**, and destroy a dialog in one call; returns the id passed to `WinDismissDlg`. |
| `WinProcessDlg` | `ULONG APIENTRY WinProcessDlg(HWND hwndDlg)` | Run a (previously loaded) dialog's modal loop; returns the dismiss result. |
| `WinDismissDlg` | `BOOL APIENTRY WinDismissDlg(HWND hwndDlg, ULONG usResult)` | End a modal dialog, making `WinProcessDlg`/`WinDlgBox` return `usResult`. |
| `WinDefDlgProc` | `MRESULT APIENTRY WinDefDlgProc(HWND hwndDlg, ULONG msg, MPARAM mp1, MPARAM mp2)` | Default dialog message handling. |
| `WinGetDlgMsg` | `BOOL APIENTRY WinGetDlgMsg(HWND hwndDlg, PQMSG pqmsg)` | Message-loop helper for modeless dialogs. |
| `WinSendDlgItemMsg` | `MRESULT APIENTRY WinSendDlgItemMsg(HWND hwndDlg, ULONG idItem, ULONG msg, MPARAM mp1, MPARAM mp2)` | Send a message to a control by id. |
| `WinQueryDlgItemText` / `WinSetDlgItemText` | - | Get/set a control's text by id. |
| `WinQueryDlgItemShort` / `WinSetDlgItemShort` | - | Get/set a control's numeric value. |

A dialog procedure receives **`WM_INITDLG`** (`0x003b`) instead of `WM_CREATE`, at which point all
its controls exist and can be initialized; `mp1` is the focus window and `mp2` is the
`pCreateParams` passed to `WinLoadDlg`/`WinDlgBox`.

**Standard item ids** [DOC-IBM `pmwin.h:1626-1628`]: `DID_OK` (1), `DID_CANCEL` (2), `DID_ERROR`
(`0xffff`). These are the values conventionally passed to `WinDismissDlg`.

### Message boxes [DOC-IBM `pmwin.h:1650-1758`]

`WinMessageBox(HWND hwndParent, HWND hwndOwner, PSZ pszText, PSZ pszCaption, ULONG idWindow,
ULONG flStyle)` displays a standard message box and returns the button chosen (`MBID_*`). `flStyle`
combines a button set - `MB_OK` (`0x0000`), `MB_OKCANCEL` (`0x0001`), `MB_RETRYCANCEL` (`0x0002`),
`MB_ABORTRETRYIGNORE` (`0x0003`), `MB_YESNO` (`0x0004`), `MB_YESNOCANCEL` (`0x0005`),
`MB_CANCEL` (`0x0006`) - an icon - `MB_ICONQUESTION` (`0x0010`), `MB_ICONEXCLAMATION` (`0x0020`),
`MB_ICONASTERISK`/`MB_INFORMATION` (`0x0030`), `MB_ICONHAND` (`0x0040`) - a default button
(`MB_DEFBUTTON1`/`2`/`3` = `0x0000`/`0x0100`/`0x0200`), and modality (`MB_APPLMODAL` `0x0000`,
`MB_SYSTEMMODAL` `0x1000`, `MB_MOVEABLE` `0x4000`). Return values are `MBID_OK` (1),
`MBID_CANCEL` (2), `MBID_ABORT` (3), `MBID_RETRY` (4), `MBID_IGNORE` (5), `MBID_YES` (6),
`MBID_NO` (7), `MBID_HELP` (8), `MBID_ENTER` (9), `MBID_ERROR` (`0xffff`).

`WinAlarm(HWND hwndDesktop, ULONG rgfType)` sounds an alarm: `WA_WARNING` (0), `WA_NOTE` (1),
`WA_ERROR` (2) [DOC-IBM `pmwin.h:1631-1638`].

---

## 9. Window words [DOC-IBM]

Each window has a block of per-window storage - reserved at class registration via
`WinRegisterClass`'s `cbWindowData`, plus a set of predefined slots - read and written by index:

| Symbol | Prototype | Purpose |
|---|---|---|
| `WinQueryWindowULong` | `ULONG APIENTRY WinQueryWindowULong(HWND hwnd, LONG index)` | Read a 32-bit window word. |
| `WinSetWindowULong` | `BOOL APIENTRY WinSetWindowULong(HWND hwnd, LONG index, ULONG ul)` | Write a 32-bit window word. |
| `WinQueryWindowUShort` | `USHORT APIENTRY WinQueryWindowUShort(HWND hwnd, LONG index)` | Read a 16-bit window word. |
| `WinSetWindowUShort` | `BOOL APIENTRY WinSetWindowUShort(HWND hwnd, LONG index, USHORT us)` | Write a 16-bit window word. |
| `WinQueryWindowPtr` | `PVOID APIENTRY WinQueryWindowPtr(HWND hwnd, LONG index)` | Read a pointer window word. |
| `WinSetWindowPtr` | `BOOL APIENTRY WinSetWindowPtr(HWND hwnd, LONG index, PVOID p)` | Write a pointer window word. |

**Standard indices** [DOC-IBM `pmwin.h:797-813`]:

| Index | Value | Meaning |
|---|---|---|
| `QWL_USER` / `QWS_USER` | `0` | First application word (base of `cbWindowData`). |
| `QWS_ID` | `-1` | Window (child) id. |
| `QWL_STYLE` | `-2` | Window style bits. |
| `QWP_PFNWP` | `-3` | The window procedure pointer. |
| `QWL_HMQ` | `-4` | The window's message queue. |
| `QWL_RESERVED` | `-5` | Reserved. |

Provenance: **[DOC-IBM]** `pmwin.h:776-813`.

---

## 10. Timers [DOC-IBM `pmwin.h:3461-3475`]

A window timer delivers a periodic `WM_TIMER` to a window:

| Symbol | Prototype | Purpose |
|---|---|---|
| `WinStartTimer` | `ULONG APIENTRY WinStartTimer(HAB hab, HWND hwnd, ULONG idTimer, ULONG dtTimeout)` | Start a timer with id `idTimer` firing every `dtTimeout` milliseconds; `WM_TIMER` is posted to `hwnd`. Returns the timer id (or, if `hwnd` is `NULLHANDLE`, an allocated id). |
| `WinStopTimer` | `BOOL APIENTRY WinStopTimer(HAB hab, HWND hwnd, ULONG idTimer)` | Stop a timer. |
| `WinGetCurrentTime` | `ULONG APIENTRY WinGetCurrentTime(HAB hab)` | Current PM time in milliseconds. |

Reserved timer ids: `TID_CURSOR` (`0xffff`), `TID_SCROLL` (`0xfffe`), `TID_FLASHWINDOW`
(`0xfffd`); `TID_USERMAX` (`0x7fff`) is the highest application timer id. `WM_TIMER` (`0x0024`)
delivers the firing timer's id in `SHORT1FROMMP(mp1)`.

---

## 11. System values [DOC-IBM]

`WinQuerySysValue(HWND hwndDesktop, LONG iSysValue)` returns a system-wide metric or setting;
`WinSetSysValue(HWND hwndDesktop, LONG iSysValue, LONG lValue)` changes a settable one. Selected
`SV_*` indices [DOC-IBM `pmwin.h:3000-3083`]:

| Constant | Value | Meaning |
|---|---|---|
| `SV_SWAPBUTTON` | `0` | Mouse buttons swapped (left-handed). |
| `SV_DBLCLKTIME` | `1` | Double-click interval (ms). |
| `SV_CXDBLCLK` / `SV_CYDBLCLK` | `2` / `3` | Double-click sensitivity box. |
| `SV_CXSIZEBORDER` / `SV_CYSIZEBORDER` | `4` / `5` | Sizing-border thickness. |
| `SV_CURSORRATE` | `9` | Cursor blink rate. |
| `SV_CXSCREEN` / `SV_CYSCREEN` | `20` / `21` | Screen width / height in pixels. |
| `SV_CXVSCROLL` / `SV_CYHSCROLL` | `22` / `23` | Scroll-bar thickness. |
| `SV_CXBORDER` / `SV_CYBORDER` | `26` / `27` | Border width / height. |
| `SV_CYTITLEBAR` | `30` | Title-bar height. |
| `SV_CXICON` / `SV_CYICON` | `38` / `39` | Icon dimensions. |
| `SV_CXPOINTER` / `SV_CYPOINTER` | `40` / `41` | Pointer dimensions. |
| `SV_CMOUSEBUTTONS` | `43` | Number of mouse buttons. |
| `SV_MOUSEPRESENT` | `48` | Non-zero if a mouse is installed. |
| `SV_INSERTMODE` | `59` | Global insert/overtype mode. |

---

## 12. Handle types [DOC-IBM]

All PM handles are `LHANDLE` (`typedef unsigned long LHANDLE`, `os2def.h:76`):

| Type | Tag | Definition | Meaning |
|---|---|---|---|
| `HAB` | *hab* | `os2def.h:258` | Anchor block (per-thread PM handle). |
| `HMQ` | *hmq* | `os2def.h:599` | Message queue (per-thread). |
| `HWND` | *hwnd* | `os2def.h:596` | Window. |
| `HPS` | *hps* | `os2def.h:263` | Presentation space. |
| `HDC` | *hdc* | `os2def.h:266` | Device context. |
| `HMODULE` | *hmod* | `os2def.h:232` | Loaded module (resource source). |
| `HPOINTER` | - | `os2def.h:644` | Mouse pointer / icon. |
| `HACCEL` | *haccel* | `pmwin.h:3480` | Accelerator table. |
| `MPARAM` / `MRESULT` | *mp* / *mres* | `os2def.h:591,593` | Opaque message parameter / result (`VOID *`). |

---

## 13. PM's internal fast mutexes [OBS-RE]

Not an API - internal `PMMERGE.DLL` machinery, but it is load-bearing for anything that
must supply `LINFOSEG.tidCurrent` faithfully. Read from a shipped Warp 4.5 `PMMERGE.DLL`
(`PMREQUESTMUTEXSEM`, object 4 offset `0xFE008`); the peer is `PMRELEASEMUTEXSEM`.

PM keeps a small array of fixed **32-byte** mutex entries in one of its shared data
objects, indexed by an integer the caller passes:

| Offset | Field |
|---|---|
| `+0x00` | *(unexamined)* |
| `+0x08` | **owner token** - the word the lock-free `cmpxchg` operates on |
| `+0x0c` | recursion count |
| `+0x14` | identity stamped at acquire (same value as `+8`) |
| `+0x1c` | **acquirer's return address** - names the PM function holding the lock |

The acquire is lock-free and, critically, derives its identity **fresh on every call**:

```asm
mov   ecx,[<LINFOSEG ptr>]     ; PM caches the LINFOSEG far pointer in its data object
movzx ecx,word [ecx+0x6]       ; LIS_TIDCurrent - re-read every call, never cached
mov   eax,[esp+0x4]            ; mutex index
shl   ecx,0x10                 ; tid << 16
shl   eax,0x5                  ; index * 0x20
lea   edx,[eax+<table base>]
or    ecx,[<PID>]              ; | PID          -> token = (tid << 16) | pid
cmp   [edx+0x8],ecx            ; already the owner?   <-- the recursion test
jz    recursive
lock cmpxchg [edx+0x8],ecx     ; else take it; failure -> the blocking path
recursive:
inc   dword [edx+0x0c]
mov   eax,[esp] / mov [edx+0x1c],eax
mov   [edx+0x14],ecx
```

Three consequences worth stating explicitly:

- **The mutex is recursive, and recursion is detected only by comparing the stored owner
  to a token rebuilt from `LIS_TIDCurrent`.** There is no separate thread-identity source.
  A thread that observes a different `tidCurrent` on re-entry fails its own `cmp`, falls
  into the contended path, and blocks on a lock it already holds.
- **The token embeds the PID**, so these entries are meant to be contended across
  processes, not merely across threads of one process.
- On the contended path PM calls `DosVerifyPidTid` on the *owner's* pid/tid to decide
  whether the owner is still alive and the lock can be stolen. A live-but-parked owner
  therefore blocks the steal indefinitely - correctly, from PM's point of view.

`+0x1c` is the useful debugging field: resolve it through `pmmerge.sym` to name the PM
function that took the lock.

---

## See also
- `message-queue.md` - how a posted message reaches the queue and how a thread blocked in
  `WinGetMsg` is woken (the kernel wake path).
- `infoseg.md` - `LINFOSEG.tidCurrent` (word at `+6`), the per-thread field section 13's
  owner token is built from.
- `pm-controls.md` - the predefined control window classes (`WC_BUTTON`, `WC_ENTRYFIELD`,
  `WC_CONTAINER`, ...) and their notification messages.
- `resources-and-dialogs.md` - dialog templates, resource loading (`WinLoadDlg`/`WinDlgBox`), and
  menu / string / accelerator resources.
- `pm-graphics.md` - the drawing path a `WM_PAINT`/`WinBeginPaint` `HPS` feeds (Gpi -> the display
  DLL federation -> pixels).
- `calling-convention.md` - the `APIENTRY`/`EXPENTRY` linkage every PM entry point and window
  procedure uses, and the `.DEF`-file export requirement for window procedures.
