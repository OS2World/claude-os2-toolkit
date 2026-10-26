# OS/2 Text-Mode I/O - VIO, KBD, and MOU

The three subsystems a character-mode (text) OS/2 program uses to reach the screen, the
keyboard, and the mouse. **VIO** (Video I/O) writes characters and attributes to a text screen
and controls the cursor and video mode; **KBD** (Keyboard) reads keystrokes; **MOU** (Mouse)
reads pointer motion and button events. All three are session-scoped: a program addresses the
console of the session it runs in, and the calls behave identically whether the program owns a
full-screen session or runs inside a VIO window on the Presentation Manager desktop. The APIs
are 16-bit at the ABI (they predate the 32-bit Control Program) and are reached from 32-bit code
through the standard thunk layer; the entry-point names are unprefixed IBM spellings
(`VioWrtTTY`, `KbdCharIn`, `MouReadEventQue`).

Provenance: **[DOC-IBM]** OS/2 Toolkit 4.5 header `bsesub.h` (all prototypes, structures, field
layouts, and constants) and the IBM *Control Program Reference* (semantics of each call, the
status/state bit fields, the cell model). Structure field offsets are computed from the header's
declared types under the `#pragma pack` in force for each struct. Every function, field, and
constant below is transcribed from those two sources.

---

## 1. Common conventions [DOC-IBM: bsesub.h]

- **Return type.** Every call returns `APIRET16` (a `USHORT`); `0` (`NO_ERROR`) means success,
  non-zero is an `ERROR_*` code. The subsystem error ranges are `ERROR_VIO_*`, `ERROR_KBD_*`,
  and `ERROR_MOUSE_*`/`ERROR_MOU_*`.
- **Handles.** `HVIO` (video), `HKBD` (keyboard), and `HMOU` (mouse) are `USHORT` handles. For
  VIO and KBD the handle argument **must be 0** for an ordinary application; a non-zero `HVIO` is
  used only by an Advanced-VIO (AVIO) Presentation Manager application, which obtains a video
  presentation space (`HVPS`) from `VioCreatePS`. A mouse handle is obtained from `MouOpen`.
- **Coordinates** are zero-based: row 0 is the top row, column 0 is the leftmost column.
- **Linkage.** Declared `APIENTRY16` (the 16-bit `_System` far-call convention).

---

## 2. VIO - the text screen

### 2.1 The cell model [DOC-IBM: Control Program Reference - VioWrtCellStr / VioReadCellStr]

A text screen is a grid of **cells**. Each cell is a **character byte plus an attribute byte** -
the character is the code page glyph, the attribute is the standard display-adapter text
attribute (foreground colour, background colour, intensity/blink). A single-byte-character-set
(SBCS) cell is **2 bytes** (char + attribute); a double-byte-character-set (DBCS) cell is **4
bytes**. The exact per-cell size for the current mode is reported by `VIOMODEINFO`
(`fmt_ID`/`attrib`, section 2.5). The VIO calls split into three families by what part of the cell they
touch:

| Call | Writes | One-line purpose |
|---|---|---|
| `VioWrtCharStr` | characters only | Write a character string at (row,col); attributes unchanged. |
| `VioWrtCharStrAtt` | characters + one attribute | Write a character string, all cells given the same attribute. |
| `VioWrtCellStr` | full cells | Write a string of char-attribute cells (2 or 4 bytes each). |
| `VioWrtNChar` | one character, repeated | Write a character `n` times from (row,col). |
| `VioWrtNAttr` | one attribute, repeated | Write an attribute `n` times (characters unchanged). |
| `VioWrtTTY` | characters, TTY-style | Write a string at the cursor, advancing it and scrolling (teletype). |
| `VioReadCellStr` | - (reads cells) | Read a run of char-attribute cells from the screen. |

`VioWrtTTY` is the "printf" primitive: it writes at the current cursor position, advances the
cursor, wraps at the right margin, and scrolls the screen when it passes the bottom row. The
`VioWrt*` positioned calls do **not** move the cursor. [DOC-IBM: Control Program Reference -
VioWrtTTY.]

### 2.2 Character / cell output [DOC-IBM: bsesub.h]

```c
APIRET16 APIENTRY16 VioWrtTTY       (PCH pch,       USHORT cb,
                                     HVIO hvio);
APIRET16 APIENTRY16 VioWrtCharStr   (PCH pchStr,    USHORT cb,
                                     USHORT usRow,  USHORT usColumn, HVIO hvio);
APIRET16 APIENTRY16 VioWrtCharStrAtt(PCH pch,       USHORT cb,
                                     USHORT usRow,  USHORT usColumn,
                                     PBYTE pAttr,   HVIO hvio);
APIRET16 APIENTRY16 VioWrtCellStr   (PCH pchCellStr,USHORT cb,
                                     USHORT usRow,  USHORT usColumn, HVIO hvio);
APIRET16 APIENTRY16 VioWrtNChar     (PCH pchChar,   USHORT cb,
                                     USHORT usRow,  USHORT usColumn, HVIO hvio);
APIRET16 APIENTRY16 VioWrtNAttr     (PBYTE pAttr,   USHORT cb,
                                     USHORT usRow,  USHORT usColumn, HVIO hvio);
APIRET16 APIENTRY16 VioReadCellStr  (PCH pchCellStr,PUSHORT pcb,
                                     USHORT usRow,  USHORT usColumn, HVIO hvio);
```

For `VioWrtCharStr`, `VioWrtCellStr`, `VioWrtNChar`, and `VioWrtNAttr`, `cb` is the count **in
bytes** - for a cell string that count must be a whole number of cells (a multiple of 2 or 4).
`VioWrtCharStrAtt` takes a pointer to the single attribute byte applied to every character.
`VioWrtNChar` repeats one character `cb` times; `VioWrtNAttr` repeats one attribute `cb` times.
`VioReadCellStr`'s `pcb` is in/out: on entry the buffer size in bytes, on return the number of
bytes read; the caller must size it in whole cells. [DOC-IBM: bsesub.h; Control Program
Reference - VioReadCellStr / VioWrtCellStr.]

### 2.3 Cursor position and shape [DOC-IBM: bsesub.h]

```c
APIRET16 APIENTRY16 VioGetCurPos (PUSHORT pusRow, PUSHORT pusColumn, HVIO hvio);
APIRET16 APIENTRY16 VioSetCurPos (USHORT  usRow,  USHORT  usColumn,  HVIO hvio);
APIRET16 APIENTRY16 VioGetCurType(PVIOCURSORINFO pvioCursorInfo, HVIO hvio);
APIRET16 APIENTRY16 VioSetCurType(PVIOCURSORINFO pvioCursorInfo, HVIO hvio);
```

`VIOCURSORINFO` (struct tag `_VIOCURSORINFO`, "vioci"; default packing) describes the blinking
cursor's scan-line span and visibility:

| Off | Field | Type | Meaning |
|---|---|---|---|
| 0x00 | `yStart` | USHORT | Starting (top) scan line of the cursor within the cell. |
| 0x02 | `cEnd`   | USHORT | Ending (bottom) scan line of the cursor. |
| 0x04 | `cx`     | USHORT | Cursor width (character-cell columns; normally the cell width). |
| 0x06 | `attr`   | USHORT | Cursor attribute; `-1` hides the cursor, otherwise makes it visible. |

Total size **8 bytes**. [DOC-IBM: bsesub.h:469-475.]

### 2.4 Scrolling [DOC-IBM: bsesub.h]

```c
APIRET16 APIENTRY16 VioScrollUp(USHORT usTopRow, USHORT usLeftCol,
                                USHORT usBotRow, USHORT usRightCol,
                                USHORT cbLines,  PBYTE pCell, HVIO hvio);
APIRET16 APIENTRY16 VioScrollDn(USHORT usTopRow, USHORT usLeftCol,
                                USHORT usBotRow, USHORT usRightCol,
                                USHORT cbLines,  PBYTE pCell, HVIO hvio);
APIRET16 APIENTRY16 VioScrollLf(USHORT usTopRow, USHORT usLeftCol,
                                USHORT usBotRow, USHORT usRightCol,
                                USHORT cbCol,    PBYTE pCell, HVIO hvio);
APIRET16 APIENTRY16 VioScrollRt(USHORT usTopRow, USHORT usLeftCol,
                                USHORT usBotRow, USHORT usRightCol,
                                USHORT cbCol,    PBYTE pCell, HVIO hvio);
```

The four calls scroll a rectangular region - defined by its top row, left column, bottom row,
and right column - up, down, left, or right. For `VioScrollUp`/`VioScrollDn`, `cbLines` is the
number of rows shifted in (0 = no scroll); for `VioScrollLf`/`VioScrollRt`, `cbCol` is the
number of columns. `pCell` points to the char-attribute cell (2 or 4 bytes) used to fill the
vacated lines/columns. A full-screen clear is a `VioScrollUp` over the whole region with
`cbLines` = the row count and a blank-space fill cell. [DOC-IBM: bsesub.h:568-598; Control
Program Reference - VioScrollUp.]

### 2.5 Video mode [DOC-IBM: bsesub.h]

```c
APIRET16 APIENTRY16 VioGetMode(PVIOMODEINFO pvioModeInfo, HVIO hvio);
APIRET16 APIENTRY16 VioSetMode(PVIOMODEINFO pvioModeInfo, HVIO hvio);
```

`VIOMODEINFO` (struct tag `_VIOMODEINFO`, "viomi") is declared under **`#pragma pack(1)`** (byte
packed):

| Off | Field | Type | Meaning |
|---|---|---|---|
| 0x00 | `cb`             | USHORT | Structure length in bytes, including `cb` itself (minimum 3). Set on input to `VioSetMode`. |
| 0x02 | `fbType`         | UCHAR  | Mode-characteristics bit mask (see below). |
| 0x03 | `color`          | UCHAR  | Number of colours as a power of 2 (colour-bit count): 0 = monochrome, 1 = 2 colours, 2 = 4, 4 = 16, 8 = 256. |
| 0x04 | `col`            | USHORT | Number of text columns. |
| 0x06 | `row`            | USHORT | Number of text rows. |
| 0x08 | `hres`           | USHORT | Horizontal resolution (pel columns). |
| 0x0A | `vres`           | USHORT | Vertical resolution (pel rows). |
| 0x0C | `fmt_ID`         | UCHAR  | Attribute format identifier. |
| 0x0D | `attrib`         | UCHAR  | Number of attribute bytes in a character cell. |
| 0x0E | `buf_addr`       | ULONG  | 32-bit physical address of the display buffer. |
| 0x12 | `buf_length`     | ULONG  | Display-buffer length. |
| 0x16 | `full_length`    | ULONG  | Full save-buffer length. |
| 0x1A | `partial_length` | ULONG  | Partial save-buffer length. |
| 0x1E | `ext_data_addr`  | PCH    | Address of extended-mode data. |

Total size **0x22 = 34 bytes** (with the 16:16 `PCH` occupying 4 bytes at 0x1E). `fmt_ID` and
`attrib` together give the cell size (`attrib` = 1 -> 2-byte cells, = 2 -> 4-byte cells).
[DOC-IBM: bsesub.h:494-518; Control Program Reference - VioSetMode.]

`fbType` (`VIOMODEINFO.fbType`) bit mask [DOC-IBM: bsesub.h:521-523 and Control Program
Reference]:

| Bit(s) | Constant | Meaning |
|---|---|---|
| 0 | `VGMT_OTHER` (0x01) | 0 = monochrome-compatible mode; 1 = other. |
| 1 | `VGMT_GRAPHICS` (0x02) | 0 = text mode; 1 = graphics mode. |
| 2 | `VGMT_DISABLEBURST` (0x04) | 0 = enable colour burst; 1 = disable colour burst. |
| 3 | - | 0 = VGA-compatible modes 0-13H; 1 = native mode. |
| 7-4 | - | Reserved, set to zero. |

`color` field constants: `COLORS_2` (0x0001), `COLORS_4` (0x0002), `COLORS_16` (0x0004).
[DOC-IBM: bsesub.h:488-490.]

### 2.6 The Logical Video Buffer (LVB) [DOC-IBM: bsesub.h / Control Program Reference]

```c
APIRET16 APIENTRY16 VioGetBuf (PULONG pLVB, PUSHORT pcbLVB, HVIO hvio);
APIRET16 APIENTRY16 VioShowBuf(USHORT offLVB, USHORT cb, HVIO hvio);
```

`VioGetBuf` returns the address (as a 16:16 far pointer packed into the output `ULONG` - the
offset is not guaranteed to be zero) and byte length of the caller's **Logical Video Buffer**, a
private in-memory copy of the screen. Its length is `rows * columns * cell-size`. A program can
compose a screen in the LVB off-line; `VioShowBuf(offLVB, cb, hvio)` then copies a run of that
buffer (starting at byte offset `offLVB`, length `cb`) to the physical display. Once `VioGetBuf`
has been issued, `VioWrt*` calls made while the program is in the foreground write **both** the
LVB and the physical screen; `VioShowBuf` has effect only for a foreground process that has
called `VioGetBuf`. When a background program is switched to the foreground the physical screen
is refreshed from its LVB. [DOC-IBM: Control Program Reference - VioGetBuf / VioShowBuf.]

### 2.7 Return codes (selected calls)

Non-zero returns for the two VIO calls with a documented code list. `VioWrtCharStr`,
`VioWrtCellStr`, `VioSetCurPos`, etc. draw from the same `ERROR_VIO_*` range.

| Value | Constant | Returned by | Meaning |
|---|---|---|---|
| 0   | `NO_ERROR`                | both | Success. |
| 355 | `ERROR_VIO_MODE`          | `VioWrtCharStrAtt`, `VioScrollUp` | Call not valid in the current video mode. |
| 358 | `ERROR_VIO_ROW`           | `VioWrtCharStrAtt`, `VioScrollUp` | Row value out of range. |
| 359 | `ERROR_VIO_COL`           | `VioWrtCharStrAtt`, `VioScrollUp` | Column value out of range. |
| 421 | `ERROR_VIO_INVALID_PARMS` | `VioWrtCharStrAtt` | A parameter is invalid. |
| 436 | `ERROR_VIO_INVALID_HANDLE`| `VioWrtCharStrAtt`, `VioScrollUp` | `HVIO` handle not valid. |
| 465 | `ERROR_VIO_DETACHED`      | `VioScrollUp` | Caller is a detached (background/non-foreground) process. |

[DOC - EDM2 "VioWrtCharStrAtt", "VioScrollUp (FAPI)".]

For `VioScrollUp`, a coordinate or line count larger than its maximum is **clamped** to that
maximum rather than rejected; `TopRow`=`LeftCol`=0 with `BotRow`=`RightCol`=`Lines`=65535 (-1)
fills the whole screen with the `Cell` char-attribute pair. [DOC - EDM2 "VioScrollUp (FAPI)".]

**Measured: what provokes which code** [OBS-RE - measured on Warp Server for e-business 4.50,
kernel revision 14.089, a full-screen 16-bit program and its 32-bit helper in an 80x25 colour text
mode, VGA and SVGA display drivers; codes named from `bseerr.h`]:

- **A zero length is not an error.** Every write, read and scroll call tried with length 0 (13 of
  them) returned 0; `VioReadCellStr`/`VioReadCharStr` returned 0 bytes. Only the structure calls
  check a size: `VioGetMode`/`VioSetMode` with `cb` 0 or 2, and `VioGetConfig` with `cb` 1, return 438
  `ERROR_VIO_INVALID_LENGTH`; `VioGetMode` with `cb` 2 returns 0 and fills those 2 bytes.
- **The handle must be 0** for a full-screen program: `hvio` 1 returns 436 from every call.
- **"Reserved" words are not checked:** `VioGetCp` and `VioSetCp` with the reserved word set to 1
  return 0.
- `VioSetCurType` with width 2 in text mode returns 356 `ERROR_VIO_WIDTH`; a percentage below -100
  returns 421. `VioScrollUp` with TopRow greater than BotRow returns 358, and with LeftCol greater
  than RightCol 359; out-of-range values are clamped, as described above, not refused.
- `VioSetCp(999)` returns 469 `ERROR_VIO_BAD_CP`; **a valid code page that is not in `CODEPAGE=`
  (852 with `CODEPAGE=437,850`) also returns 469**, not 471 `ERROR_VIO_NA_CP`; `VioSetCp(-1)` with
  no user font set returns 0, not 470. 470 and 471 were not produced by any input tried, including
  a boot with no `CODEPAGE=` line.
- `VioSetCp(850)` then `VioGetCp` reads back 850. After a user font is set with `VioSetFont`,
  `VioGetCp` returns 468 `ERROR_VIO_USER_FONT`.
- **Pointers are not checked.** The VIO read/write paths do no NULL or range check of their own
  [OBS-RE - DOSCALL1's VIO code read], and an invalid far pointer passed to `VioGetPhysBuf` trapped
  the caller [OBS-RE - measured]. Do not expect 421 or 350 for a bad pointer.

**In a background session the answers change** [OBS-RE - same system, three full-screen copies of
the program running at once, only one of them in the foreground]:

| Call | Foreground | Background |
|---|---|---|
| `VioShowBuf`, including with an offset past the LVB or in a graphics mode | 421 / 355 as appropriate | **0** - a no-op that does not check its arguments |
| `VioGetCp` after a user font is set | 468 | 0 |
| `VioGetFont` | the font (for example 9x16, 4096 bytes) | **467** `ERROR_VIO_FONT` - no font can be read |
| `VioSetFont` with the font just read | 0 | 421 (it was handed the empty result) |
| `VioGetConfig` under an SVGA driver | adapter 10, display 0xFFFF | adapter 10, display 19 |

**The tell:** a full-screen program that works when it starts in the foreground and fails only
when started in, or switched to, the background - look first at `VioGetFont`/`VioSetFont`.

> Note: the EDM2 "VioWrtCharStrAtt" page describes the `Attr` argument as the address of **1 or
> 3 attribute bytes** per character (SBCS vs. multi-byte). The header (section 2.2) types it `PBYTE`
> (single attribute byte); header value retained. [DOC - EDM2 "VioWrtCharStrAtt".]

---

## 3. KBD - the keyboard

### 3.1 Reading keystrokes [DOC-IBM: bsesub.h]

```c
APIRET16 APIENTRY16 KbdCharIn    (PKBDKEYINFO pkbci, USHORT fWait, HKBD hkbd);
APIRET16 APIENTRY16 KbdPeek      (PKBDKEYINFO pkbci, HKBD hkbd);
APIRET16 APIENTRY16 KbdStringIn  (PCH pch, PSTRINGINBUF pchIn, USHORT fsWait, HKBD hkbd);
APIRET16 APIENTRY16 KbdFlushBuffer(HKBD hkbd);
APIRET16 APIENTRY16 KbdGetStatus (PKBDINFO pkbdinfo, HKBD hkbd);
APIRET16 APIENTRY16 KbdSetStatus (PKBDINFO pkbdinfo, HKBD hkbd);
```

| Call | One-line purpose |
|---|---|
| `KbdCharIn` | Return one character/key event; wait or return immediately per `fWait`. |
| `KbdPeek` | Return the next key event without removing it from the buffer. |
| `KbdStringIn` | Read a character string (line-input in ASCII mode, or `n` bytes in binary mode). |
| `KbdFlushBuffer` | Discard all characters queued in the keyboard buffer. |
| `KbdGetStatus` / `KbdSetStatus` | Query / set the keyboard mode flags (echo, binary/ASCII, shift state). |

`fWait`/`fsWait` take `IO_WAIT` (0) or `IO_NOWAIT` (1) [DOC-IBM: bsesub.h:122-123]. In ASCII
mode `KbdStringIn` returns when Enter is pressed (line editing / template active); in binary
mode it returns when the buffer is full. No-wait is not supported in ASCII mode. [DOC-IBM:
Control Program Reference - KbdStringIn.]

### 3.2 `KBDKEYINFO` [DOC-IBM: bsesub.h]

Struct tag `_KBDKEYINFO` ("kbci"), declared under **`#pragma pack(2)`**. Filled by `KbdCharIn`
and `KbdPeek`:

| Off | Field | Type | Meaning |
|---|---|---|---|
| 0x00 | `chChar`    | UCHAR  | ASCII character code (scan code translated to ASCII). |
| 0x01 | `chScan`    | UCHAR  | Scan code received from the keyboard. |
| 0x02 | `fbStatus`  | UCHAR  | State of the keystroke event (bit field, below). |
| 0x03 | `bNlsShift` | UCHAR  | NLS shift status (reserved, set to zero). |
| 0x04 | `fsState`   | USHORT | Shift-key state (bit field, section 3.4). |
| 0x06 | `time`      | ULONG  | Time stamp in milliseconds since system start. |

Total size **0x0A = 10 bytes**. [DOC-IBM: bsesub.h:133-141.]

`fbStatus` bit field [DOC-IBM: Control Program Reference - KbdCharIn]:

| Bit(s) | Meaning |
|---|---|
| 7-6 | `00` = undefined; `01` = final character, interim flag off; `10` = interim character; `11` = final character, interim flag on. |
| 5   | 1 = immediate conversion requested. |
| 4-2 | Reserved. |
| 1   | 0 = scan code is a character; 1 = scan code is an extended key code (not a character). |
| 0   | 1 = shift status returned without a character. |

### 3.3 `STRINGINBUF` and `KBDINFO` [DOC-IBM: bsesub.h]

`STRINGINBUF` (struct tag `_STRINGINBUF`, "kbsi"; default packing) - the in/out length record for
`KbdStringIn`:

| Off | Field | Type | Meaning |
|---|---|---|---|
| 0x00 | `cb`    | USHORT | On entry, buffer capacity in bytes (max 255). |
| 0x02 | `cchIn` | USHORT | On return, number of bytes actually read. |

Total size **4 bytes**. [DOC-IBM: bsesub.h:158-162.]

`KBDINFO` (struct tag `_KBDINFO`, "kbst"; default packing) - the mode/status record for
`KbdGetStatus`/`KbdSetStatus`:

| Off | Field | Type | Meaning |
|---|---|---|---|
| 0x00 | `cb`           | USHORT | Structure length in bytes. |
| 0x02 | `fsMask`       | USHORT | Mode flags (echo, binary/ASCII, etc.; constants below). |
| 0x04 | `chTurnAround` | USHORT | Turnaround (line-terminator) character. |
| 0x06 | `fsInterim`    | USHORT | Interim character flags. |
| 0x08 | `fsState`      | USHORT | Shift state (section 3.4). |

Total size **0x0A = 10 bytes**. [DOC-IBM: bsesub.h:205-212.]

`fsMask` constants [DOC-IBM: bsesub.h:174-182]: `KEYBOARD_ECHO_ON` (0x0001),
`KEYBOARD_ECHO_OFF` (0x0002), `KEYBOARD_BINARY_MODE` (0x0004), `KEYBOARD_ASCII_MODE` (0x0008),
`KEYBOARD_MODIFY_STATE` (0x0010), `KEYBOARD_MODIFY_INTERIM` (0x0020),
`KEYBOARD_MODIFY_TURNAROUND` (0x0040), `KEYBOARD_2B_TURNAROUND` (0x0080),
`KEYBOARD_SHIFT_REPORT` (0x0100).

### 3.4 Shift-state bits (`fsState`) [DOC-IBM: bsesub.h]

The `fsState` USHORT shared by `KBDKEYINFO`, `KBDINFO`, and `KBDTRANS` [DOC-IBM:
bsesub.h:186-201]:

| Constant | Value | Meaning |
|---|---|---|
| `KBDSTF_RIGHTSHIFT`     | 0x0001 | Right Shift down. |
| `KBDSTF_LEFTSHIFT`      | 0x0002 | Left Shift down. |
| `KBDSTF_CONTROL`        | 0x0004 | Either Ctrl down. |
| `KBDSTF_ALT`            | 0x0008 | Either Alt down. |
| `KBDSTF_SCROLLLOCK_ON`  | 0x0010 | ScrollLock toggled on. |
| `KBDSTF_NUMLOCK_ON`     | 0x0020 | NumLock toggled on. |
| `KBDSTF_CAPSLOCK_ON`    | 0x0040 | CapsLock toggled on. |
| `KBDSTF_INSERT_ON`      | 0x0080 | Insert toggled on. |
| `KBDSTF_LEFTCONTROL`    | 0x0100 | Left Ctrl down. |
| `KBDSTF_LEFTALT`        | 0x0200 | Left Alt down. |
| `KBDSTF_RIGHTCONTROL`   | 0x0400 | Right Ctrl down. |
| `KBDSTF_RIGHTALT`       | 0x0800 | Right Alt down. |
| `KBDSTF_SCROLLLOCK`     | 0x1000 | ScrollLock key down. |
| `KBDSTF_NUMLOCK`        | 0x2000 | NumLock key down. |
| `KBDSTF_CAPSLOCK`       | 0x4000 | CapsLock key down. |
| `KBDSTF_SYSREQ`         | 0x8000 | SysReq key down. |

On the next `KbdStringIn` call the `cchIn` (received-input length) left in `STRINGINBUF` sets how
many bytes of the prior input the line editor may recall; a value of 0 inhibits line editing for
that request. [DOC - EDM2 "KbdStringIn (FAPI)".]

### 3.5 Return codes (selected calls)

| Value | Constant | Returned by | Meaning |
|---|---|---|---|
| 0   | `NO_ERROR`                 | both | Success. |
| 375 | `ERROR_KBD_INVALID_IOWAIT` | `KbdCharIn`, `KbdStringIn` | `fWait`/`fsWait` value is not `IO_WAIT`/`IO_NOWAIT`. |
| 439 | `ERROR_KBD_INVALID_HANDLE` | `KbdCharIn`, `KbdStringIn` | `HKBD` handle not valid. |
| 445 | `ERROR_KBD_FOCUS_REQUIRED` | `KbdCharIn`, `KbdStringIn` | Handle does not have keyboard focus. |
| 447 | `ERROR_KBD_KEYBOARD_BUSY`  | `KbdCharIn` | Keyboard busy (another handle holds it). |
| 464 | `ERROR_KBD_DETACHED`       | `KbdCharIn`, `KbdStringIn` | Caller is a detached process. |
| 504 | `ERROR_KBD_EXTENDED_SG`    | `KbdCharIn`, `KbdStringIn` | Extended screen-group error. |

[DOC - EDM2 "KbdCharIn (FAPI)", "KbdStringIn (FAPI)".]

### 3.6 Below the API: the KBD$ device driver's real hotkey classification [OBS-RE]

Everything above is the documented `KbdCalls` API. One thing beneath it is worth recording because
it answers a question the API itself gives no hint of: **how does a Ctrl-Esc/Alt-Esc
session-switch keypress actually get recognized?** Found by reading IBM's own shipped
`KBDBASE.SYS` source directly, not inferred:

- The driver's real-time scan-code processing path calls a routine named **`HotKeyCheck`** on
  **every single keystroke**, unconditionally - real header comment: *"Check for Session Manager
  Hot Key with correct Shift State... Called by the Interrupt Handler on every keystroke, and by
  the Monitor Dispatcher notification routine on every keystroke inserted by a monitor. Checks for
  lone press/release of the defined Session Manager hot key, with only the required shift state
  accompanying it."* Its own code explicitly checks the classic **Ctrl+Esc** (Left Ctrl + scan
  `01h`) and **Alt+Esc** (Left Alt + scan `01h`) sequences by name.
- On a match it sends an internal event (**`event_SMKey`**) and hands the keystroke to the
  Single Input Queue driver with hot-key information attached - i.e. **hotkey classification
  happens at interrupt time, before the keystroke ever reaches the input queue**, not something
  figured out later by the queue consumer or by PM.
- `HotKeyCheck` short-circuits entirely (does nothing) when the Desktop's lockup state is active -
  the session-switch hotkey is suppressed while the desktop is locked.

[OBS-RE: IBM's real `KBDBASE.SYS` source, the scan-code-processing and hotkey-check routines.]

---

## 4. MOU - the mouse

### 4.1 Open / close and setup [DOC-IBM: bsesub.h]

```c
APIRET16 APIENTRY16 MouOpen        (PSZ pszDvrName, PHMOU phmou);
APIRET16 APIENTRY16 MouClose       (HMOU hmou);
APIRET16 APIENTRY16 MouGetNumButtons(PUSHORT pcButtons, HMOU hmou);
APIRET16 APIENTRY16 MouSetEventMask(PUSHORT pfsEvents, HMOU hmou);
APIRET16 APIENTRY16 MouGetEventMask(PUSHORT pfsEvents, HMOU hmou);
```

`MouOpen` opens the mouse for the current session and returns a handle in `*phmou`. `pszDvrName`
names a pointer-draw device driver; an application that wants the system default passes a
double-word of zeros (a NULL far pointer) instead of a string address. `MouGetNumButtons`
returns the button count (1, 2, or 3). `MouSetEventMask` selects which events reach the queue.
[DOC-IBM: bsesub.h:1073-1076, 999-1000, 1056; Control Program Reference - MouOpen /
MouSetEventMask.]

Immediately after `MouOpen` the pointer is **not visible**: the collision area is defined as the
entire display, so the application must issue `MouDrawPtr` (section 4.3) to remove it before the pointer
is drawn. The initial state also has scale factors 16/8, all events reported, an empty event
queue, all device-status bits reset, and (in a valid display mode) the pointer centred.
[DOC - EDM2 "MouOpen".]

Event-mask / `MOUEVENTINFO.fs` motion+button bits [DOC-IBM: bsesub.h:1045-1051]:

| Constant | Value | Meaning |
|---|---|---|
| `MOUSE_MOTION`               | 0x0001 | Mouse moved, no buttons down. |
| `MOUSE_MOTION_WITH_BN1_DOWN` | 0x0002 | Moved with button 1 down. |
| `MOUSE_BN1_DOWN`             | 0x0004 | Button 1 press/release. |
| `MOUSE_MOTION_WITH_BN2_DOWN` | 0x0008 | Moved with button 2 down. |
| `MOUSE_BN2_DOWN`             | 0x0010 | Button 2 press/release. |
| `MOUSE_MOTION_WITH_BN3_DOWN` | 0x0020 | Moved with button 3 down. |
| `MOUSE_BN3_DOWN`             | 0x0040 | Button 3 press/release. |

### 4.2 Reading events [DOC-IBM: bsesub.h]

```c
APIRET16 APIENTRY16 MouReadEventQue(PMOUEVENTINFO pmouevEvent, PUSHORT pfWait, HMOU hmou);
APIRET16 APIENTRY16 MouGetNumQueEl (PMOUQUEINFO qmouqi, HMOU hmou);
APIRET16 APIENTRY16 MouFlushQue    (HMOU hmou);
```

`MouReadEventQue` reads one event from the mouse's FIFO event queue. `*pfWait` selects behaviour
on an empty queue: `MOU_NOWAIT` (0x0000) returns a null record immediately, `MOU_WAIT` (0x0001)
blocks until an event arrives [DOC-IBM: bsesub.h:1007-1008].

`MOUEVENTINFO` (struct tag `_MOUEVENTINFO`, "mouev"), declared under **`#pragma pack(2)`**:

| Off | Field | Type | Meaning |
|---|---|---|---|
| 0x00 | `fs`   | USHORT | Mouse state at the time of the event (motion+button bits, section 4.1). |
| 0x02 | `time` | ULONG  | Time stamp in milliseconds since system start. |
| 0x06 | `row`  | SHORT  | Row position (absolute, or relative in mickey mode). |
| 0x08 | `col`  | SHORT  | Column position (absolute or relative). |

Total size **0x0A = 10 bytes** (under 2-byte packing the `ULONG time` sits at offset 2, not 4).
[DOC-IBM: bsesub.h:1015-1021; Control Program Reference - MouReadEventQue.]

`MOUQUEINFO` (struct tag `_MOUQUEINFO`, "mouqi"; default packing) returned by `MouGetNumQueEl`:
`cEvents` (USHORT, off 0x00 - events currently queued) and `cmaxEvents` (USHORT, off 0x02 -
queue capacity); size **4 bytes**. [DOC-IBM: bsesub.h:1033-1037.]

### 4.3 Pointer position and image [DOC-IBM: bsesub.h]

```c
APIRET16 APIENTRY16 MouGetPtrPos(PPTRLOC pmouLoc, HMOU hmou);
APIRET16 APIENTRY16 MouSetPtrPos(PPTRLOC pmouLoc, HMOU hmou);
APIRET16 APIENTRY16 MouDrawPtr  (HMOU hmou);
APIRET16 APIENTRY16 MouRemovePtr(PNOPTRRECT pmourtRect, HMOU hmou);
```

`PTRLOC` (struct tag `_PTRLOC`, "moupl"; default packing) - the pointer location:

| Off | Field | Type | Meaning |
|---|---|---|---|
| 0x00 | `row` | USHORT | Pointer row. |
| 0x02 | `col` | USHORT | Pointer column. |

Total size **4 bytes**. [DOC-IBM: bsesub.h:955-959.]

`MouRemovePtr` marks a rectangular region as off-limits to the pointer image (a "collision
area") so the application can draw there without the pointer overwriting it; `MouDrawPtr`
cancels a previous `MouRemovePtr`, returning the region to the pointer driver. The region is
described by `NOPTRRECT` (struct tag `_NOPTRRECT`, "mourt"; default packing): `row`, `col`,
`cRow`, `cCol` (four USHORTs, offsets 0x00/0x02/0x04/0x06; size **8 bytes**). [DOC-IBM:
bsesub.h:1079-1091; Control Program Reference - MouDrawPtr.]

### 4.4 Return codes (selected calls)

| Value | Constant | Returned by | Meaning |
|---|---|---|---|
| 0   | `NO_ERROR`                  | both | Success. |
| 385 | `ERROR_MOUSE_NO_DEVICE`     | `MouOpen`, `MouGetPtrPos` | No mouse device present. |
| 390 | `ERROR_MOUSE_INV_MODULE_PT` | `MouOpen` | Invalid pointer-draw device driver. |
| 466 | `ERROR_MOU_DETACHED`        | `MouOpen`, `MouGetPtrPos` | Caller is a detached process. |
| 501 | `ERROR_MOUSE_NO_CONSOLE`    | `MouOpen`, `MouGetPtrPos` | No console (mouse not available to this session). |
| 505 | `ERROR_MOU_EXTENDED_SG`     | `MouOpen`, `MouGetPtrPos` | Extended screen-group error. |

[DOC - EDM2 "MouOpen", "MouGetPtrPos".]

### 4.5 Below the API: the MOUSE$ device driver and MouCalls' internal dispatch [OBS-RE]

Everything above is the documented `MouCalls` API. Two internal layers sit beneath it, found by
reading IBM's own shipped `MOUSE.SYS` source and by disassembling the real `MOUCALLS`/`DOSCALL1`
binaries - real driver source, not a reconstruction.

**The real driver's `DosDevIOCtl` contract** - category `0x07` (`IOCTL_POINTINGDEVICE`), valid
function-code range `0x50`-`0x6E`:

| Code | Name | Purpose (from the source's own header comment) |
|---|---|---|
| 0x51 | `IOMW_SM` | set display mode |
| 0x53 | `IOMW_SS` | set session scaling factors |
| 0x54 | `IOMW_EM` | set session event mask |
| 0x55 | `IOMW_TH` | set session threshold values |
| 0x56 | `IOMW_PS` | set session pointer shape |
| 0x57 | `IOMW_DP` | remove session collision area and draw pointer |
| 0x58 | `IOMW_RP` | define session collision area |
| 0x59 | `IOMW_SP` | set session pointer position |
| 0x5A | `IOMW_SD` | register pointer-draw routine for a session |
| 0x5C | `IOMW_DS` | set session device status |
| 0x5D | `IOMW_MD` | end of display-mode switch (paired with `IOMW_SM`) |
| 0x60 | `IOMR_NB` | get number of mouse buttons |
| 0x61 | `IOMR_MC` | get mickeys/cm for mouse |
| 0x62 | `IOMR_GS` | get session device status |
| 0x63 | `IOMR_RD` | read session's event queue (10-byte event record) |
| 0x64 | `IOMR_QS` | get event queue status |
| 0x65 | `IOMR_GM` | get session event mask |
| 0x66 | `IOMR_GF` | get session scaling factors |
| 0x67 | `IOMR_GP` | get session pointer position |
| 0x68 | `IOMR_PS` | get session pointer image data |
| 0x69 | `IOMR_TH` | return session threshold values |
| 0x6A | `IOMR_GV` | get mouse version |
| 0x6B | `IOMR_ID` | get pointer device ID |
| 0x6D | `IOMR_CQ` | query the mouse's current constrained region (added later, 1995 change-log) |

Category `0x0A`/`0x0B` (Monitor/General, shared with the keyboard driver) carry mouse-monitor
registration and the Session Manager's own screen-group control call into the driver - see below.
[DOC-IBM: IBM's `MOUSE.SYS` source, `mouse.inc`/`ioget.asm`/`ioset.asm`.]

**`MouCalls` itself does not issue those codes directly.** Each public entry point (`MouOpen`,
`MouGetNumButtons`, `MouSetPtrPos`, ...) pushes a small, densely-packed internal opcode (0-0x15)
and calls one shared dispatcher - the **same dispatcher the keyboard side reaches through its own
device-type discriminator** - i.e. keyboard and mouse share one generic internal dispatch layer
inside `DOSCALL1.DLL`, with the category-0x07 driver contract above being what that dispatcher
issues to the actual driver underneath, not what the public API pushes:

| Opcode | `MouCalls` name | Opcode | `MouCalls` name |
|---|---|---|---|
| 0x0 | `MouGetNumButtons` | 0xA | `MouSetThreshold` |
| 0x1 | `MouGetNumMickeys` | 0xB | `MouOpen` |
| 0x2 | `MouGetDevStatus` | 0xD | `MouGetPtrShape` |
| 0x3 | `MouGetNumQueEl` | 0xE | `MouSetPtrShape` |
| 0x4 | `MouReadEventQue` | 0xF | `MouDrawPtr` |
| 0x5 | `MouGetScaleFact` | 0x10 | `MouRemovePtr` |
| 0x6 | `MouGetEventMask` | 0x11 | `MouGetPtrPos` |
| 0x7 | `MouSetScaleFact` | 0x12 | `MouSetPtrPos` |
| 0x8 | `MouSetEventMask` | 0x14 | `MouFlushQue` |
| 0x9 | `MouGetThreshold` | 0x15 | `MouSetDevStatus` |

(`0xC` not directly checked - the otherwise-contiguous numbering suggests `MouClose`, but that's
inference from the gap, not confirmed.) [OBS-RE: disassembly of the real Warp 4.5 `DOSCALL1.DLL`
against its matching `.SYM` file.]

**The real session-switch mechanism.** The mouse driver has its own Cat B (`0x41`, `SGControl`)
IOCtl, separate from the keyboard-focus notify chain in `session-manager.md`, with real
`PRESWITCH`/`POSTSWITCH`/`CREATION`/`TERMINATION` event types. It tracks a real foreground-session
variable and does real work on a switch: transferring **to** a genuine full-screen session runs a
begin/end-switch sequence through the legacy DOS-mouse-emulation interface; transferring to
anything else - **including a windowed (not full-screen) VIO session, exactly like a PM window,
confirmed directly** (every type comparison in the real driver is a binary "is this full-screen"
test, no separate windowed-VIO branch) - **explicitly disables the driver's own mouse-data
processing**, a deliberate hand-off rather than an omission. This is why PM's own mouse routing
shows no per-session focus table the way keyboard has one: mouse events carry their own screen
coordinate and are delivered by ordinary hit-testing against whichever window is visible on top,
and the driver has already stepped out of the way by the time anything but a genuine full-screen
session is foreground. [OBS-RE: IBM's real `MOUSE.SYS` source, the `SGControl` IOCtl
implementation.]

---

## 5. Symbol summary

| Symbol | Subsystem | Purpose |
|---|---|---|
| `VioWrtTTY` | VIO | Teletype-style write at the cursor (advances, wraps, scrolls). |
| `VioWrtCharStr` / `VioWrtCharStrAtt` | VIO | Positioned character write (chars only / chars + one attribute). |
| `VioWrtCellStr` / `VioReadCellStr` | VIO | Positioned full-cell write / read. |
| `VioWrtNChar` / `VioWrtNAttr` | VIO | Repeat one character / one attribute. |
| `VioGetCurPos` / `VioSetCurPos` | VIO | Query / set cursor position. |
| `VioGetCurType` / `VioSetCurType` | VIO | Query / set cursor shape (`VIOCURSORINFO`). |
| `VioGetMode` / `VioSetMode` | VIO | Query / set video mode (`VIOMODEINFO`). |
| `VioScrollUp` / `Dn` / `Lf` / `Rt` | VIO | Scroll a region in each direction with a fill cell. |
| `VioGetBuf` / `VioShowBuf` | VIO | Obtain the Logical Video Buffer / flush it to the screen. |
| `KbdCharIn` / `KbdPeek` | KBD | Read / peek one key event (`KBDKEYINFO`). |
| `KbdStringIn` | KBD | Read a line / binary string (`STRINGINBUF`). |
| `KbdGetStatus` / `KbdSetStatus` | KBD | Query / set keyboard mode (`KBDINFO`). |
| `KbdFlushBuffer` | KBD | Discard queued keystrokes. |
| `MouOpen` / `MouClose` | MOU | Open / close the mouse for the session. |
| `MouReadEventQue` | MOU | Read one event (`MOUEVENTINFO`). |
| `MouGetPtrPos` / `MouSetPtrPos` | MOU | Query / set pointer position (`PTRLOC`). |
| `MouGetNumButtons` | MOU | Return the button count. |
| `MouDrawPtr` / `MouRemovePtr` | MOU | Release / reserve a screen region for the pointer image. |
| `MouSetEventMask` / `MouGetEventMask` | MOU | Select / query which events are queued. |

## See also
- `session-manager.md` - the VIO sessions these text-mode calls run in; `pm-window-messaging.md` - the PM equivalent for windowed input.
