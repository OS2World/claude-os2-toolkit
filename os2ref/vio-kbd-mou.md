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
(For the single-byte-character formats the byte count and the cell count coincide, so this
sentence is exact there. They separate at the minimum-transfer boundary and for 4-byte cells,
and the handler distinguishes them explicitly: only the cell-string write is dispatched as a
byte length. See section 2.2a.)
`VioWrtCharStrAtt` takes a pointer to the single attribute byte applied to every character.
`VioWrtNChar` repeats one character `cb` times; `VioWrtNAttr` repeats one attribute `cb` times.
`VioReadCellStr`'s `pcb` is in/out: on entry the buffer size in bytes, on return the number of
bytes read; the caller must size it in whole cells. [DOC-IBM: bsesub.h; Control Program
Reference - VioReadCellStr / VioWrtCellStr.]

### 2.2a Where a positioned write's row and column are adjudicated

Every positioned VIO write resolves its target address through one routine in the base video
handler, and that routine - not the API layer - is what produces `ERROR_VIO_ROW` and
`ERROR_VIO_COL`. It tests three things, in this order:

1. **the column**, against the mode's `TextCols`;
2. **the row**, against the mode's `TextRows`;
3. **the transfer count**, last.

An out-of-range coordinate is **refused, not clamped**: the routine loads the error code and
jumps to a carry-setting exit, and the calling worker (`call SetBuffAddr` / `.if <nc>` ... /
`sub ax,ax` / `.endif` / `ret`) returns `AX` unchanged, so the code reaches the application.
The general path states the rule in its own pseudocode header:

```
if !( (mincol <= parmcol <= maxcol) &&
      (minrow <= parmrow <= maxrow) )
    exit with error
```

Because the count is read **after** both coordinates, a call with a zero count and a bad
position returns the position error, not `NO_ERROR`.

**A zero transfer count is not an error.** When the count fails the minimum-transfer test the
routine exits `xor ax,ax` - carry set, meaning no transfer took place, but `AX` **zero** - under
the comment *"zero length writes and reads are valid, but do nothing"*. The application sees
`NO_ERROR`.

**The minimum is per transfer type, and only one call uses the byte form.** `BX` on entry
selects the unit: `0` = a count of cells or characters, non-zero = a user buffer length in
bytes. `WriteCellStr` alone passes `mov bx, 1` (*"Move by buffer byte count"*); `WriteCharStr`,
`WriteCharStrAttr`, `WriteNChar`, `WriteNAttr` and `WriteNCell` all pass `sub bx, bx`
(*"in terms of cells"*). With `BX` non-zero the count is first rounded **down** to a whole cell
(`and ds:[si].RepeatFactor,0FFFEh` for a 2-byte cell) and only then tested against zero - so for
the cell-string write a byte count of **0 or 1** is the no-transfer case, while for the other
five only a count of 0 is. The handler's own contract block records exactly this asymmetry:
*"AX = 0 if RepeatFactor = 0 for char or attr move / = 0 or 1 for cell move"*.

A count larger than the space remaining in the buffer is **truncated**, not refused
(`if (parmcount > BytesLeft) parmcount = BytesLeft`) - which is the mechanism behind the
published remark that a write reaching the end of the screen *terminates*.

`VioSetCurPos` does **not** go through that routine; it reaches the handler's set-cursor-info
entry instead. That entry agrees, in both shipped forms - the assembler windowed handler tests
`.if <cx b es:[env_cols]>` for `ERROR_VIO_COL` before `.if <dx b es:[env_rows]>` for
`ERROR_VIO_ROW`, and the C-language SVGA handler reads
`if (ReqCol >= ModeData.col ...) rc = ERROR_VIO_COL; else if (ReqRow >= ModeData.row ...) rc =
ERROR_VIO_ROW;`. The environment buffer is updated only when the return code is still zero. The
C handler additionally bounds the request against the session's scroll rectangle
(`ScrollRect.Left/Right/Top/Bottom`); the assembler handler bounds against `env_cols`/`env_rows`
only.

> **Contrast this with section 2.4, which is the opposite on both axes of the question.** The
> `VioScroll*` family validates **row before column**, and it **clamps** an oversize coordinate
> rather than refusing it - *"If a value greater than the maximum value is specified for TopRow,
> LeftCol, BotRow, RightCol, or Lines, the maximum value for that parameter is used"* - so only
> a rectangle still inverted **after** clamping is an error. The positioned writes and the
> cursor call have no such sentence; their remarks describe only line wrap and end-of-screen
> termination. Consequently, for the analogous both-coordinates-bad input the scroll family
> answers 358 and the write family answers 359. Neither family's rule may be inferred from the
> other's.

[DOC-IBM - `SetBuffAddr` PROC :454 and `FastBuffAddr` PROC :638 in `xgaread.asm`, and
`WriteCellStr` :154 / `WriteCharStr` :298 / `WriteCharStrAttr` :426 / `WriteNChar` :595 /
`WriteNAttr` :763 / `WriteNCell` :898 in `xgawrite.asm` - the modules IBM's own `vdhwndw.lnk`
links (the similarly named `wdhread.asm` and `wdhwrite.asm` carry an older equivalent,
`LocateBuffAddr`, and are linked by no build; ask the link file, since the module prefix names
the author rather than the linker). `SetCursorInfo` PROC :359 in `wdhinfo.asm` and the same
function in `bvhinfo.c`. Published remarks and return-code lists: Control Program Reference,
the individual `VioWrt*`, `VioSetCurPos` and `VioScroll*` pages.]

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

**Where the rectangle is validated - the BVH handler, and nowhere above it.**

The coordinate clamping and the 358/359 rejections (section 2.7) are **entirely the base video
handler's**. Neither the `VIOCALLS` forwarder nor DOSCALL1's BVS layer looks at the rectangle:

* `VIOSCROLLUP` (`DOSCALL1`, `1c04:3ce6`) is four instructions, and it passes **two** arguments
  to the generic VIO router, neither of them a coordinate:

  ```
  1c04:3ce6  B80400   mov ax,0x4      ; per-direction bitmask
  1c04:3ce9  6A12     push byte +0x12 ; per-direction router index
  1c04:3ceb  E842C7   call 0x430      ; viorout
  1c04:3cee  CA1000   retf 0x10       ; 16 bytes of caller args
  ```

  `VIOSCROLLDN` / `LF` / `RT` (`1c04:3cf1` / `3cfc` / `3d07`) are the same four instructions with
  `ax` = `0x08` / `0x10` / `0x20` and the pushed index `0x13` / `0x14` / `0x15`. **Both** arguments
  vary per direction; neither encodes the rectangle.
* `BvsScrollUp` (`1c04:71c4`) copies all four coordinates and the repeat count **verbatim** into
  the `VDHPARM` block (`FuncIndex` 3, then `Row`/`Col`/`Row2`/`Col2`/`RepeatFactor`) and calls
  `AllBuffer`. `BvsScrollDn` (`1c04:7232`), `BvsScrollLf` (`1c04:7236`) and `BvsScrollRt`
  (`1c04:723a`) are not copies of it - they are **literally the same body, entered one
  instruction in**: each is `mov al,N` / `jmp short 0x71c6`, jumping past `BvsScrollUp`'s own
  `mov al,3` onto the `cbw` that follows it. There is one scroll body in DOSCALL1, and the
  direction is the only thing that differs.
* `AllBuffer` (`1c04:1e30`) sets the LVB/PVB flag bits and `ParmLength` (`0x1A`) and calls
  `AllVDH`, which dispatches `BufferUpdate` through the handler's call-vector table. It does not
  read the rectangle either.

The validator is `SetBaseRects` inside the handler - ceiling all four coordinates, then
`ERROR_VIO_ROW` (358) on rows still inverted, then `ERROR_VIO_COL` (359) on columns, and only
then the repeat count, so **an inverted rectangle is an error even when the count is zero**.
[OBS-RE - raw disassembly of a shipped `DOSCALL1.DLL`'s object 4 at the addresses above.
Disassembled rather than read off the Ghidra decompiles on purpose: the decompiles render
`VIOSCROLLUP`'s body as the single call `viorout(0x12)`, dropping the `mov ax` argument entirely.
DOC-IBM - `SetBaseRects`, `xgascrol.asm` PROC :679 ENDP :794, :685-688 /
:705-708 / :720-723 / :729-732 / :749-752 / :763-766 / :780-787, the module IBM's own
`vdhwndw.lnk` and `vdhvga.lnk` both link.]

So on real OS/2 there is exactly one place a scroll rectangle is examined, on every path and for
every one of the four directions, and no caller can reach `BufferUpdate` by a route that skips it.

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

**How the shipped Base Video Subsystem implements "foreground only"** `[OBS-RE]` (Warp 4.5
`DOSCALL1.DLL`, `BvsShowBuf`; the threshold's writer `BVSGLOBALINIT`): `VioShowBuf` returns **0 and
does nothing** unless the LVB has been exposed by `VioGetBuf` or the mode is graphics. In the
background it goes on **only for a screen group above `bvsgMaxBase`**, which is computed once at
initialisation as `SIS_MaxScrnGrp - 1` = **15** (`video-stack.md` section 4.4a, which also reports the
value read live). So a background `VioShowBuf` from a full-screen session (screen group 15 or
below) is a successful no-op - rc 0, screen and LVB untouched - while one from a windowed session
(above 15) is passed on to the video handler like a foreground call, the handler then deciding what
reaches the screen. The return code is 0 in the first case, not an error.

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

**Measured: what provokes which code** [OBS - measured on Warp Server for e-business 4.50,
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
  the caller [OBS - measured]. Do not expect 421 or 350 for a bad pointer.

**In a background session the answers change** [OBS - same system, three full-screen copies of
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

### 3.6 Below the API: where `chChar` comes from, and what never reaches the buffer [DOC-IBM / OBS-RE]

`KbdCharIn` is a consumer, not a translator. Everything in this section happens
in the **physical keyboard device driver (KBD$)** at interrupt time, before any
API call is involved; IBM's own reference calls the driver's record *"the
character data structure of the API function KbdCharIn"*.
[DOC-IBM: `.../dev/kbd/kbdbase/kbdxlat.asm:10-11`, "Physical Keyboard Device
Driver Translation Routines ... Keyboard scan code translation";
`.../VDEV/vkbd/kbd.doc:99-102`, *"calls on the pdd to translate the current scan
code to a character ... This allows all translation code to remain in the pdd"*;
`HTML/REF/PDD/01219.HTM`.]

**The translate table is one record per scan code, not a set of planes.** The
XlateTable installed by `KBD_SETTRANSTABLE (0x50)` is 127 `KDef` entries of 7
bytes: an action number plus up to five character slots - `Char1` (usually
unshifted), `Char2` (usually shifted/CapsLock), `Char3` (AltGr), `Char4`,
`Char5`. Which slot is used is decided **procedurally**, by a 28-way jump on the
action number, not by indexing a plane.
[DOC-IBM: `base/inc/kbdxlat.inc:21-29` and `:111-121`;
`kbdxlat.asm:244-247` (`And BX,ActionMask`) and `:466-471` (`Jmp CS:[BX]`);
US table at `.../kbdbase/kbddata.asm:1070,1112+`.]

**Ctrl is a different mechanism per KEY CLASS.** It is not a fourth plane, and
it is not one ladder:

| Key class | Rule | Example |
|---|---|---|
| AlphaKey (01h) - letters | **arithmetic**, `Char1 - ('a'-1)` | Ctrl+C = 0x03 ETX |
| FuncKey (06h) - F1...F12 | sets an **extended code**, character stays 0: `Char1 + 93`, or `Char1 + 126` for F11/F12 | Ctrl+F1 = 94, Ctrl+F10 = 103, Ctrl+F11 = 137, Ctrl+F12 = 138 |
| PadKey (07h) - the keypad / navigation block | sets an **extended code from `CtlPadMap`**, indexed by `Char1`; character stays 0 | Ctrl+Home = 119, Ctrl+Up = 141, Ctrl+PgUp = 132, Ctrl+Left = 115, Ctrl+Right = 116, Ctrl+End = 117, Ctrl+Down = 145, Ctrl+PgDn = 118, Ctrl+Ins = 146, Ctrl+Del = 147 |
| SpecCtlKey (08h) | Ctrl selects `Char2` | Ctrl+Enter = 0x0A, Ctrl+Backspace = 0x7F, Ctrl+Esc = 0x1B |
| SpecKey (04h/09h) - **and only these** | a fixed per-**scan-code** ladder in `SKCtlCheck` | scan 3 (`2`) -> 0x00; 7 (`6`) -> 0x1E; 12 (`-`) -> 0x1F; 15 (Tab) -> 0x00 with scan rewritten to 0x94; 26 (`[`) -> 0x1B; 27 (`]`) -> 0x1D; 43 (`\`) -> 0x1C; space unchanged; **anything else undefined** |
| AccentKey - dead keys | accent composition, not a Ctrl plane | the sixth situation `PDD/01082.HTM` Note 4 enumerates; listed for completeness so the rows above are not read as IBM's whole taxonomy |

> **CORRECTED 2026-08-31 (Rule 1.7), same day this section was written.** The
> table above originally had only three rows, the third reading
> *"everything else | a fixed per-**scan-code** ladder"*, with the undefined-key
> rule below it applying to all of it. **That was wrong, and wrong in the
> direction that deletes function:** it puts F-keys and the whole navigation
> cluster into the ladder, where they are undefined, so a reader implementing
> this section drops Ctrl+Left/Right/Home/End/PgUp/PgDn/Ins/Del and
> Ctrl+F1...F12 - every one of which real OS/2 **delivers**. One did.
>
> `SKCtlCheck` is reached from **six** sites, every one of them a SpecKey-family
> action handler and none of them conditional - `kbdxlat.asm:702` (SpecKey),
> `:749` (SpecKeyC), `:795` (SpecKeyA), `:819` (SpecKeyCA), `:2136` (SpecKeyCS),
> `:2180` (SpecKeyAS) - and **FuncKey and PadKey never reach it at all.**
>
> **CORRECTED 2026-09-01 (Rule 1.7).** This read *"exactly four handlers ... plus
> two DBCS sites at `:2136` and `:2180`"*. Both halves were wrong, in opposite
> directions: the count is six, and those two sites are **not** DBCS-conditional
> - all six sit at conditional depth zero, measured by walking the `ifdef`
> nesting rather than by looking for a nearby `ifdef DBCSKBD`. `SpecKeyCS` and
> `SpecKeyAS` are IBM's **country-keyboard / NLS** special keys - action types
> `14h` and `15h`, *"Special key 1 for country keyboard processing"* and
> *"Special key 2 for country keyboard processing"* (`PDD/01082.HTM:153,163`),
> labelled *"Special key for NLS support"* in the action table itself
> (`kbdxlat.asm:500-501`). The **conclusion is unaffected**, which is precisely
> how the wrong count survived review: it was decoration on a sound argument,
> and a number that is not load-bearing does not get re-counted.
>
> **WHERE THE WRONG "DBCS" LABEL CAME FROM - the cause generalises, which is why
> it is recorded.** The two action-table rows *immediately above* the ones being
> described read `dw XShiftKey ; 12 Extended shift key (for DBCS use)` and
> `dw XToggleKey ; 13 Extended toggle key (for DBCS use)` (`kbdxlat.asm:498-499`),
> while the rows actually cited, `:500-501`, say *"Special key for NLS support"*.
> The label was taken from the **adjacent** rows rather than the cited ones -
> the same mistake in kind as classifying `:2136`/`:2180` as DBCS because an
> `ifdef DBCSKBD` block sits somewhere nearby. Both are one error: **judging a
> line by its neighbourhood instead of reading it.** Hence the rule that caught
> the count - *walk the nesting, read the row you are citing* - and hence the
> second correction, since the replacement label was itself produced by the very
> habit the first correction was about.
>
> *(A characterisation with no source is not made safe by being less wrong than
> the one it replaces; in `os2-reference/` it inherits the corpus's authority
> either way. Use IBM's words or cite the code.)*
>
> The error came from misreading a citation's scope, which is the reusable
> lesson: `PDD/01082.HTM` **Note 4 scopes the ladder itself** - it applies to a
> key that is *"a nonalpha character, such as `[`, **but is not an action key,
> such as Enter, Backspace, or an arrow key**"* - and Note 3 (nothing undefined
> is buffered) is competent **only** for that undefined case. Both were used to
> answer questions they do not address. A citation that is true is not thereby
> competent for the question you are asking it.

[DOC-IBM: FuncKey `kbdxlat.asm:895-899` (`.If <CL gt 10> / Add CL,126 / .Else /
Add CL,93`) and `:917` (`Mov [SI].Key.Scan,CL`), F11/F12 `Char1` = 11/12 at
`kbddata.asm:1198-1199`; PadKey `kbdxlat.asm:1031-1039` (`Mov AH,[BX+CtlPadMap]
/ Mov [SI].Key.Scan,AH`), table `kbddata.asm:931-935`, pad `Char1` = 0...12 on
scans 71...83 `kbddata.asm:1182-1194`; `PDD/01082.HTM:74` (type 06h) and `:85`
Note 5 (type 07h).]

> **Where IBM's own doc and IBM's own source CONFLICT, and the source wins.**
> `PDD/01082.HTM:74` says *"Ctrl Sets extended codes 93+Char1. F11 and F12 use
> 143 and 144."* The `93+Char1` half matches `kbdxlat.asm`; the **F11/F12 half
> does not** - the asm computes `126+Char1` = **137 and 138**. The asm is
> right: all four of its modifier branches reproduce the standard PC/AT
> extended codes exactly (plain F11 = `122+11` = 133, Shift = `124+11` = 135,
> Ctrl = `126+11` = 137, Alt = `128+11` = 139), while 143 and 144 are not
> F-key codes at all - they are `CtlPadMap`'s entries for keypad-5 and
> keypad-plus (`kbddata.asm:933`). Recorded because the doc is the more
> reachable source and will be read again. [DOC-IBM, conflict resolved in
> favour of the shipped implementation.]


Note the letter rule is a **subtraction**, not `& 0x1F`; the two agree only
because IBM requires `Char1` of an AlphaKey to be lower case.
[DOC-IBM: `kbdxlat.asm:603` (`Sub AL,"a"-1 ;Convert Char1 to control code`);
`kbdxlat.asm:1304-1307` (`Test DL,CtlFlag ... Mov AL,CH ;use Char2`);
`kbdxlat.asm:4321-4355` (the `SKCtlCheck` ladder, whose `Mov AL,-1` / `UndefKey` tail is at :4353-4355); `PDD/01082.HTM` Note 4
tabulates the identical set.]

**Ctrl+C is special in ASCII (cooked) mode: it becomes a BREAK EVENT and the
keystroke is thrown away - it is not delivered as 0x03.** The translate step
still computes 0x03 by the AlphaKey rule above, but it additionally tags the
packet `PSBreakKey` when the session is in cooked mode, and the scan-code layer
then raises `event_CtrlC` through `DeviceHelp` and discards the key. Only in
**Binary** mode (`XInputMode != 0`) is no such tag set and 0x03 delivered as an
ordinary character. So what an application sees for Ctrl+C depends on the mode
it selected with `KbdSetStatus` (`KEYBOARD_ASCII_MODE 0x0008` vs
`KEYBOARD_BINARY_MODE 0x0004`), and a cooked-mode reader that sits in
`KbdCharIn` waiting for 0x03 will wait forever on real OS/2.
[DOC-IBM: `kbdxlat.asm:609-615` (`.If <CL eq 'c'> / .If <[DI].XInputMode eq 0> /
Or [SI].DDFlags,PSBreakKey`); `PSBreakKey Equ 0012h` `kbdddr.inc:350`;
`kbdscan.asm:1327-1348` (`PsBreakKeyChk ... Mov AH,event_CtrlC / Call
[DeviceHelp] / StC ; Discard key.`); `bsesub.h:176-177`.]

**`PSBreakKey` is a KEY TYPE, not a flag bit - and `ConsInpFilter` tests the
mode a SECOND time.** `DDFlags`' low six bits (`KeyTypeMask 003Fh`) hold a key
*type*, and `Or [SI].DDFlags,PSBreakKey` sets that field to `12h`. The filter
switches on it through `CIFTable`, whose sixteen entries are indexed by
*type - 8* and cover the keys that raise a `DeviceHelp` event; the same field
decides the ordinary cases too - type 0 is a normal character and is **kept**,
types 1...7 are shift/system keys and are **thrown away** (`ShiftMask` is 7), and
types >= `30h` are non-keyboard-generated with only `31h` ("written") kept.
Before the type dispatch runs, the filter folds the KCB's input mode into the
flag word's high byte - `And CH,3Fh / Mov BH,ES:[BX].KCBInpMode /
And BH,INPUTMODE / Or CH,BH` - so `PsBreakKeyChk`'s `Test CH,0C0h` is a
**second** test of the same `INPUTMODE` bit `KbdXlate` already tested. That
second test has a live arm: **in Binary mode `PsBreakKeyChk` skips the whole
event block and falls through with carry clear, i.e. keeps the key**, whose
character the translate step has already made `0x03`. Ctrl+P and Ctrl+S are
tagged by the same `KbdXlate` block and take the same route
(`PSPrintEchoKey`, `PSPauseKey` - `event_CtrlPrtSc` and `event_CtrlScrLk`).
[DOC-IBM: `kbdddr.inc:340,350,351,358,360`; `kbdscan.asm:1160-1199` (the type
dispatch), `:1204-1218` (`CIFTable`), `:1180-1186` (the mode fold),
`:1319-1348` (`PsBreakKeyChk`); `kbdxlat.asm:616-625`.]

**Measured on a running system** [OBS] (WSeB 4.50 SMP, IBMKBD.SYS, a full-screen session; each key followed by
Enter and read with one `KbdCharIn(IO_WAIT)`, so the first record shows whether the key was kept): in ASCII mode
Shift+PrtSc and Ctrl+PrtSc are discarded; in binary mode **Ctrl+PrtSc is discarded too** (the Enter is the first
record), so the shipped driver does not keep it as the `PSPrintEchoKey` reading above would, while binary Ctrl+S is
kept as the 13h record. On this enhanced keyboard **Ctrl+NumLock does not pause** and the key after it is delivered;
Ctrl+S and the Pause key pause the session's VIO calls until the next key, which is discarded.

**The mode that decides all of this is per SESSION, and `XInputMode` is only a
copy of it.** The authority is `KCBInpMode`, one byte in the *keyboard control
block*; the KCBs are *"part of a linked list on a per session basis"*, and the
PDD reference states the scope outright for the IOCtl that writes it: *"The
Keyboard device driver maintains the mode separately for each session."* Its
layout is `1... .... = Binary mode / 0... .... = ASCII mode` and
`.... ...1 = Shift Report`, i.e. `INPUTMODE 80h` and `SHIFTREPORT 1` - the same
two values IBM's userland header spells `ASCII_MODE 0x00` / `BINARY_MODE 0x80`.
`XInputMode`, the byte `KbdXlate` reads, is declared *"Copy of the desired input
mode"* and is filled in per translation: the interrupt path calls `AccessKCB`
and then `Mov AH,ES:[DI].KCBInpMode / Mov [SI].XInputMode,AH`, the strategy path
does the same into `XDRFlagArea`, and that path zeroes it again once
translation completes. There are exactly **two** writers of `KCBInpMode` in the
whole driver - the `KBD_SETINPUTMODE` (51h) handler, which stores the whole
byte, and KCB creation, which stores 0 (*"mode to ASCII + no shift report"*,
matching *"The default input mode is ASCII"*). So every API that changes the
mode converges on that one field.
[DOC-IBM: `kbdddr.inc:442`, `:495-500`, `:621-625`, and the `KCBData` header;
`kbdscan.asm:527-529`; `kbdiocg.asm:1244,1261,1322`; `kbdiocs.asm:573`,
`:2640-2641`; `bsedev.h` "SETINPUTMODE"; PDD reference `KBD_SETINPUTMODE` (51h)
Remarks and `PDD/01090.HTM`.]

**What `event_CtrlC` becomes above the driver: `XCPT_SIGNAL_INTR`, to the
session's SIGNAL FOCUS - not simply "the foreground process".** For a program
using the 16-bit API the focus is chosen by registration: *"When a process
called `DosSetSigHandler`, it became a candidate for the 'signal focus' for its
session. At any point in time, the focus for a session is the last process to
register a signal handler for that signal. When the user presses Ctrl+C on the
keyboard, the system delivers an `XCPT_SIGNAL_INTR` signal to the current
keyboard focus."* The system-exception table says the same from the other side:
`XCPT_SIGNAL_INTR` *"is sent to Thread 1 in the current keyboard-focus
process"*. Three further rules follow, and each of them changes what a
reimplementation owes:

- **It is not always sent.** The kernel *"first checks to see if either this
  counter is greater than zero"* (the `DosSetSignalExceptionFocus` count) *"or
  if the process has registered a 16-bit signal handler for that signal. If
  either of these is true, the signal will be sent."* ~~A session in which
  nothing has registered therefore **swallows Ctrl+C**, and that is correct
  behaviour rather than a missing path.~~ **CORRECTED 2026-10-13: the quoted
  rule holds for the INTR/BREAK signal, but a session with no focus holder does
  not swallow the key.** The kernel's `PostSigFocus` finds no holder for the
  foreground group and runs `KSGKillProcess`, which posts the *kill* signal (3)
  to every process of that group when the group is 4 or higher and below
  `sgMax`; groups 0-3 and the windowed groups get nothing. See section 3.8, "Ctrl+C
  and Ctrl+Break with no focus holder". `[OBS-RE]`, not measured.
- **Dispatch order is fixed.** Every 32-bit exception handler on thread 1 gets
  the first opportunity; if none returns `XCPT_CONTINUE_EXECUTION` the 16-bit
  handler is called; *"if the 32-bit handlers are called and do not handle the
  signal, and there are no 16-bit handlers, the process is terminated."* That
  documented default action - forced process termination - applies to a signal
  that **was** sent and went unhandled, never to one the kernel declined to
  send.
- **Only one is held, and it is held, not queued.** Because typematic could
  repeat the key, the system holds the exception until a handler returns
  `XCPT_CONTINUE_EXECUTION`, or the process calls
  `DosAcknowledgeSignalException`, or calls `DosSetSigHandler` with
  `SIG_ACKNOWLEDGE`. *"However, only one signal exception is actually held;
  they are not queued by the system."*

The 16-bit signal numbers and actions are `SIG_CTRLC 1`, `SIG_KILLPROCESS 3`,
`SIG_CTRLBREAK 4`, `SIG_PFLG_A...C 5...7`, `SIG_CSIGNALS 8` ("number of signals plus
one"; number 2 is *"(UNDEFINED) reserved for future use"*), and `SIGA_KILL 0`,
`SIGA_IGNORE 1`, `SIGA_ACCEPT 2`, `SIGA_ERROR 3`, `SIGA_ACKNOWLEDGE 4`.
**Negative result, recorded because it is expensive to re-derive:** the
register/stack frame such a 16-bit handler is *entered with* is **not stated**
in the DDK, in the Toolkit, or in the Control Program Guide/Reference and PDD
Reference - searched for a `DosSetSigHandler` entry of the shape every
documented function has (`DosSetSignalExceptionFocus` has one; this does not),
and the name appears only in cross-references, one of which points at the *OS/2
Control Program Programming Reference*. Recovering it means reading the
kernel's own signal dispatcher, not another book. [Negative result.]
[DOC-IBM: Control Program Guide, `DosSetSignalExceptionFocus` Remarks and
"Handling Signal Exceptions"; the system-exception table's `XCPT_SIGNAL_INTR`
row; `bsedos.h` `INCL_DOSSIGNALS` block.]

**Any other Ctrl combination ON A SpecKey is UNDEFINED and is discarded**, not
passed through unmodified - "any other" means *within the SpecKey ladder above*,
not across all key classes (see the correction there): `NoXlate` sets `UndefKey`
and the character is forced to -1.
IBM states the consequence plainly: *"no character data records with an
undefined character code are placed in the keyboard input buffer."* So Ctrl+`;`
yields nothing at all - it does **not** yield `;`.
[DOC-IBM: `kbdxlat.asm:4069-4071`; `kbdddr.inc:341`; `PDD/01082.HTM` Note 3.]

**A modifier key's own press is not a character.** Shift/Ctrl/Alt/CapsLock/
NumLock/ScrollLock are XlateTable key types that set `ShiftMask`; for those the
driver **zeroes both the character and the scan code** in one word store and
flags the packet with `fbStatus` bit 0 ("shift status returned without a
character", section 3.2):

```
 .If <BX eq ShiftMask> ...
    Mov Word Ptr [SI].Key.XChar, 0   ;PTM 2244: Zero out Character/Scan Code
    And [SI].Key.Status, NOT EXTENDEDCODE
    Or  [SI].Key.Status,1            ;Flag as shift report packet
```
[DOC-IBM: `kbdxlat.asm:4104-4124`; `ShiftMask=0007h` `kbdddr.inc:360`;
`CharData` layout `kbdddr.inc:233-241`.]

**`ConsInpFilter` is the gate in front of the buffer**, and it is the only one.
Its own header states the contract - *"Carry set = throw key away / Carry clear
= keep key"* - and it guards `PutInKIB` on both paths. What it discards:

- **shift-key packets**, unless the session enabled **Shift Report**: the mode
  test whitelists them, and otherwise every key whose type is below 8 is thrown
  away - `ShiftMask` is 7. **Shift Report is off by default** (the KCB's input
  mode is initialised to 0, *"ASCII + no shift report"*), and ASCII + Shift
  Report is **rejected with a parameter error**, so a session must also ask for
  Binary mode. Consequently a normal application never sees a modifier press.
- **every key break (key-up)**, unconditionally, except SysReq's - and SysReq's
  break is then discarded too. There is **no "translate break"/KEYUP mode**:
  searched `.../kbdbase/*.asm`, `*.inc` and the whole PDD reference for
  `keyup|key-up|report break|break report|translate break` - **absent**. The
  only key-up an application can ever receive is a *modifier* release, and only
  under Binary+Shift-Report. [OBS-RE - negative result.]
- **undefined keys**, as above.

[DOC-IBM: `.../kbdbase/kbdscan.asm:1095-1400`, contract at `:1118-1119`, shift
branch `:1141-1149`, type-below-8 discard `:1163-1169`, break discard
`:1152-1161`, SysReq `:1381-1384`; call sites `kbdscan.asm:884-908` and
`kbdmon.asm:247-252`; defaults `kbdiocs.asm:2640-2641` and `PDD/01090.HTM`;
ASCII+ShiftReport rejection `kbdiocs.asm:437-444`.]

**Keyboard monitors are upstream of the filter and see everything.** Every
packet - modifier makes and breaks included - is written to the monitor chain
*before* `ConsInpFilter` runs, so "the monitor saw it" implies nothing about
whether an application will. [DOC-IBM: `kbdscan.asm:836-845`,
`Mov DX, 0100h + DevHlp_MonWrite`.]

**Bit 1 is set at ONE place, and the test is on the CHARACTER, not the key.**
Every key class falls through to a single common exit, `EndActionCase`, which
turns on `EXTENDEDCODE` when ~~the packet is not undefined~~ **the packet's key type
is 0** (an ordinary character packet) and the translated character is zero (or the
key came in behind an E0 secondary prefix). Its own comment states the intent:
*"This logic tests to see if the current keypacket is for an extended keystroke or
not. If it is then bit 1 of the Status field in the keypacket is turned on."*
~~A shift packet reaches that exit with a zero character too, so IBM sets the bit
and then **clears it again** in the shift branch.~~ **CORRECTED 2026-10-13:** the
test is `Test [SI].DDFlags,UndefKey / .If <z>`, and `UndefKey` is `3Fh`, the whole
key-type mask, so `.If <z>` means "key type 0", not "not undefined". A shift packet
(type 7), an accent key (10h) or any other typed packet never gets the bit; the
clear in the shift branch is a no-op for it. `[OBS-RE]` the shipped binary agrees:
the KBDBASE.SYS decompile `KbdXlate_1008:0728` tests `(DDFlags & 0x3f) == 0` before
`Status |= 2`.
[DOC-IBM: `kbdxlat.asm:4077-4087`; `EXTENDEDCODE Equ 2` `kbdddr.inc:499`;
`UndefKey Equ 003Fh` `kbdddr.inc:341`; the clear at `kbdxlat.asm:4116`;
`PDD/01219.HTM` bit 1.]

> **The API header does not name this bit.** `KBDTRANS.fbStatus` in the Warp-4.5
> Toolkit (`H/bsesub.h:260-265`) defines exactly four constants -
> `KBDTRF_SHIFT_KEY_IN` 0x01, `KBDTRF_CONVERSION_REQUEST` 0x20,
> `KBDTRF_FINAL_CHAR_IN` 0x40, `KBDTRF_INTERIM_CHAR_IN` 0x80 - and there is **no
> 0x02 member**; grepping `KBDTRF` across the whole toolkit `H/` directory
> returns only those four. So bit 1 is recoverable only from the DDK driver
> sources or the PDD reference, never from the header an application author
> would reach for. `[OBS-RE - negative result, checked 2026-09-01.]`

**A zero `chChar` is ambiguous without the other two fields.** Three different
things produce it, and only `fbStatus` and `chScan` separate them:

| What | `chChar` | `chScan` | `fbStatus` | Reaches the buffer? |
|---|---|---|---|---|
| Extended key (F1, arrows) | 0x00 | extended code (F1 = 0x3B) | bit 1 set | **yes** |
| Modifier press/release | 0x00 | **0x00** | bit 0 set | only under Binary+Shift-Report |
| Undefined combination | 0x00 | original scan | - | **no** |

[DOC-IBM: extended keys `kbdxlat.asm:830-917` and `:4077-4087`, `PDD/01082.HTM`
Note 7; the other two rows as cited above.]


### 3.7 Where the translate table comes from: `KEYBOARD.DCP` and `DEVINFO=KBD` [OBS-RE] + [DOC-IBM]

*Added 2026-09-08. section 3.6 describes the table once it is installed; this section is the file it comes
out of and the interface that installs it. The container and directory layout are `[OBS-RE]`, read
out of a shipped Warp 4.5 `\OS2\KEYBOARD.DCP` (315,109 bytes, dated 2001-10-03) and re-derived for
this document; the payload layout, the size arithmetic, the layout-ID table and the IOCtl contract
are `[DOC-IBM]`.*

`DEVINFO=KBD,` **layout** `,` **filename** names both halves of the key: the *layout* selects a
directory entry's ID field, and `CODEPAGE=` selects its code-page field. **The pair is the key.**
`[DOC-IBM]` `cmdref21.txt` (`DEVINFO`, `KBD` and `KEYB` pages).

#### The container

```
+0x0000  DWORD   file offset of the DIRECTORY
+0x0004  ASCII   copyright banner, zero-padded
+0x0061 .. dir   the translate tables, back to back

DIRECTORY (at the DWORD above; runs to EOF):
  +0x00  WORD   number of entries              (measured 247)
  +0x02  WORD   entry size                     (measured 18)
  then n x 18 bytes:
     +0x00  CHAR[8]  layout ID, blank/NUL padded   -- SEE THE BYTE ORDER NOTE BELOW
     +0x08  WORD     code page ID                  e.g. 437, 850, 859, 1004
     +0x0a  WORD     keyboard type  0 = AT, 1 = Enhanced
                                    (`kbdxlat.inc`: `AT Equ 00h` / `EN Equ 01h`)
     +0x0c  DWORD    file offset of this entry's XTSTRUC
     +0x10  WORD     flags     bit 3 = default sub-country, bit 8 = needs one
                                  (the rest UNESTABLISHED -- see below)
```

The shipped file measured above holds **247 tables over 59 layout IDs and 22 code pages** (437,
813, 850, 852, 855, 857, 859, 860, 861, 862, 863, 864, 865, 866, 869, 874, 915, 921, 922, 1004,
1125, 1131).

~~**Unestablished:** the meaning of the `+0x10` flags word. Observed values are 0...7 and
0x100...0x10F - the 0x100 bit is set on roughly half the entries and the low nibble takes 0...7. What
would settle it is the consumer's own test (see "Who reads the file" below), or `KEYB.EXE`.~~

> **TWO OF THE BITS ARE ESTABLISHED, 2026-09-11. The paragraph above is kept (it was the
> right question and it named the right instrument - the consumer's own test is exactly what
> settled it), and the observed value range it records is unchanged.** `[OBS-RE]` the
> matching routine in `DOSCALL1`'s 16-bit code, read from the shipped bytes against a
> matched `.SYM`; `[DOC-IBM]` the confirmation.
>
> **bit 3 (`0x0008`) - THIS ENTRY IS THE DEFAULT SUB-COUNTRY FOR ITS TWO-LETTER
> DESIGNATOR. bit 8 (`0x0100`) - A BARE DESIGNATOR MAY NOT SELECT THIS ENTRY.** The
> consumer has **two matching arms** and reads the flags in only one of them:
>
> * **`DEVINFO=KBD` named a bare designator** (the subtype's bytes 2...7 are all blanks -
>   the routine tests for the word `0x2020` three times, which is also what fixes the pad
>   byte, below): it compares **only the designator word**, then rejects the entry unless
>   `NOT (bit 8 set AND bit 3 clear)`.
> * **a sub-country was given**: all eight bytes are compared, after the *entry's* NUL
>   padding is rewritten to blanks, and **the flags are not consulted at all** - so
>   `DEVINFO=KBD,FR120` reaches a non-default table.
>
> **Confirmed against IBM's own document, which is the check that does not depend on
> reading the code.** `[DOC-IBM]` `cmdref21.txt` "Keyboard - Remarks" names the defaults
> *"FR189 (for France), IT141 (for Italy), and UK166 (for the United Kingdom)"*. In the
> shipped file the swapped IDs `RF189`, `TI141` and `KU166` carry `0x0108` and
> `RF120`, `TI142`, `KU168` do **not**. Swept over the whole directory: eleven designators
> have more than one ID, and ten of them have **exactly one** ID carrying `0x0108`.
> `RA` (Arabic) has **none**, so a bare `DEVINFO=KBD,AR` selects nothing - recorded, not
> explained.
>
> **This is what makes the byte-swap trap below bite in the OTHER direction too.** A reader
> that swaps correctly but takes the *first* designator match in file order selects
> `SUDV` - US Dvorak, which sits earlier than `SU103` - and again nothing faults.
>
> **A THIRD FIELD IS SETTLED BY THE SAME ROUTINE: the device section's 8-byte subtype is
> padded with BLANKS, not NULs.** `cdib.inc` declares it `db 8 dup(?)` and states nothing.
> But the first arm above tests bytes 2...7 for `0x2020`, and takes the bare-designator path
> only when all six are blanks; a NUL-padded subtype would fall into the eight-byte compare
> and match no directory entry at all, so `DEVINFO=KBD,US` could never work - and
> `cmdref21` documents that it does. So the component that fills the block blank-pads.

#### The layout ID is stored with its two-letter half BYTE-SWAPPED

**This is the trap in the whole format, and reading past it identifies the wrong table.** The
directory's ID field and the `XTCountry` field inside the payload header both store the two-letter
country designator as a **word**, so the assembler's `dw 'US'` lands in the file as the bytes
`'S','U'`. The three-digit sub-country that follows is *not* swapped.

So the file's `SU103` **is** IBM's documented `US 103 United States`, and the file's `US153` is
IBM's `SU 153 Finland`. IBM's own layout-ID table settles it `[DOC-IBM]`, `cpgref.txt` "Note 13 -
Category 4, Function 50H", which gives *"SU 153 Finland"*, *"SV 153 Sweden"* and *"US 103 United
States"* - and the shipped file contains all three IDs in swapped form (`US153`, `VS153`, `SU103`).
Three of Note 13's entries appear in the file **unchanged but for the swap**, which is the
strongest single check: `RF120`/`RF189` = `FR120`/`FR189` (France), `TI141`/`TI142` =
`IT141`/`IT142` (Italy), `KU166`/`KU168` = `UK166`/`UK168` (United Kingdom).

The rest of the directory corroborates the swap by **code page**, which does not depend on Note 13
at all: `RA238`/`RA470` carry the code-page-864 tables (Arabic), `HT191` the code-page-874 ones
(Thai), `UR441`/`UR443` code pages 866/1125/1131 (Russian), `AU465` 1125 (Ukrainian), `YB463` 1131
(Belarusian), `TL456`/`VL455` 921 (Lithuanian/Latvian), `KG220`/`KG319` 813 and 869 (Greek),
`EH212` 862 (Hebrew), and `SUDV`/`SUDVL`/`SUDVR` are the US Dvorak variants. Every one of those
reads as a real designator **only** after the swap.

> **Note 13 is not an inventory of this file.** It fixes the two-letter designators, which is all
> the correction above rests on, but its sub-country numbers are a smaller and partly different set
> - it lists `AR 785` and `HE 972` where the shipped file has `RA238`/`RA470` and `EH212`. Do not
> read a file entry's absence from Note 13, or a mismatched three-digit number, as evidence
> against the swap.

**Confirmed independently against the character planes**, which is the check that does not depend
on reading the ID at all `[OBS-RE]`:

Scan codes 2...13, printed as `Char1` `Char2` `Char3` with `.` for a zero byte, read out of the
shipped file:

| directory ID | logical ID | scan 2 ... scan 13 |
|---|---|---|
| `SU103` cp437 type 1 | **US103** | `1!.` `2@.` `3#.` `4$.` `5%.` `6^.` `7&.` `8*.` `9(.` `0).` `-_.` `=+.` - **US English**, and every `Char3` is zero |
| `US153` cp437 type 1 | **SU153** | `1!.` `2"@` `3#GBP ` `4.$` `5%.` `6&.` `7/{` `8([` `9)]` `0=}` `+?\` - the Nordic layout, with an AltGr plane the US table does not have, `+`/`?` where US has `-`/`_`, and scan 13 (`0x01 0x02`, AltGr a vertical bar) carrying **accent-key indices** rather than characters, per `cpgref.txt` Note 15 |

**Therefore the US English, code page 437, Enhanced-keyboard table in the file measured above is
`SU103` at file offset `0x03F93F`, not the `US`-prefixed entry at `0x03706B`.** An implementation
that matches the DEVINFO layout parameter against the ID field literally will silently select the
wrong country's table for every layout whose two letters are not a palindrome - and the failure is
silent, because the wrong table is a perfectly well-formed one.

#### The payload is IBM's `XTSTRUC`

`[DOC-IBM]` `kbdxlat.inc` and `kbdbase/kbdddr.inc`, with the same arithmetic published in
`cpgref.txt` "Note 18 - Category 4, Function 50H":

```
XTSTRUC:
  Header       40 bytes
  KDefs      127 x 7  = 889
  Accents      7 x 46 = 322
                       ----
                       1251        ; kbdddr.inc:508  "XTLen  Equ  1251  ;Derived below."

Header:
  +0x00 WORD    XT_CP          code page of this table
  +0x02 WORD    XTFlags1
  +0x04 WORD    XTFlags2
  +0x06 WORD    XTKbdType      "FUTURE (keyboard type that uses this table)"
  +0x08 WORD    XTKbdSubType   "FUTURE"
  +0x0a WORD    XTLength       length of this table in bytes
  +0x0c WORD    XTEntryCount   127
  +0x0e WORD    XTEntryWidth   7
  +0x10 WORD    XTCountry      the two-letter designator, byte-swapped as above
  +0x12 WORD    XTTableID
  +0x14 CHAR[4] XTSubCountry   e.g. "153 "
  +0x18 WORD[8] XTRes          reserved

KDef (7 bytes, one per scan code 1..127) -- the record 3.6 describes:
  +0x00 WORD  XlateOp   accent flags (bits 9..15) | action number (bits 0..8)
  +0x02 BYTE  Char1     usually unshifted
  +0x03 BYTE  Char2     usually shifted / CapsLock
  +0x04 BYTE  Char3     usually AltGr
  +0x05 BYTE  Char4
  +0x06 BYTE  Char5     "Only used by one keytype (14h)"

AccEntry (46 bytes, 7 of them):
  +0x00 BYTE NonAcChar   char passed when the next char is not accented
  +0x01 BYTE NonAcScan
  +0x02 BYTE CtlAcChar   char passed on Ctrl+[accent key]
  +0x03 BYTE CtlAcScan
  +0x04 BYTE AltAcChar   char passed on Alt+[accent key]
  +0x05 BYTE AltAcScan
  +0x06 BYTE AcMap[20][2]   20 (from, to) pairs: base char -> accented result
```

**1251 is the nominal size, NOT a universal one - do not assume a fixed stride.** Measured across
all 247 tables in the shipped file, `XTEntryCount` is 127 and `XTEntryWidth` is 7 in **every**
table, but **27 tables declare an `XTLength` other than 1251**, ranging 1113 to 1650. Three are
*shorter* than 1251 and twenty-four longer. That is consistent with IBM's own driver code, which
re-reads `XTLength` from the table it is handed and re-verifies access **when the table is longer
than `XTLen`** - extended tables are a supported case, not a corruption. Walk the directory's
`+0x0c` offsets; do not stride by 1251.

#### What installs a table, and what the driver keeps

`[DOC-IBM]`, from the DDK's shipped physical keyboard driver sources (`kbdiocs.asm` handlers,
`kbdioct.asm` jump tables) and `kbdddr.inc`. **The driver never sees a filename - only tables.**

The driver holds a **CPCB (Code Page Control Block)** array. `kbdddr.inc`, verbatim: *"CPCB memory
is allocated at **SYSINIT time**. There are **N+1** CPCB entries, where N is the number of
codepages specified at system configuration time"* (`EntryCount Equ 5`).

```
CPCBEntry:  WORD  CPValue     ; code page number, identical to the CONFIG.SYS value
            WORD  CPUseCount  ; for segment (un)locking
            DWORD CPVAddr     ; physical address of the translate table
            DWORD XTLinear    ; linear address, kept for VMFree
```

| Category 4 fn | name | what it does |
|---|---|---|
| **0x50** | `SetXlateTbl` | verifies read access to `XTLen` bytes, disables the device, copies the caller's whole `XTSTRUC` over the table at `CPCB[0].CPVAddr`, stores the new table's `XT_CP` into `CPCB[0].CPValue`, re-enables, and - if multi-layer CP is on - sends an NLS notify packet down the monitor chain. **It replaces the default (index 0) table in place.** |
| **0x5C** | `SetCodePage` | takes `{ DWORD far pointer to the caller's table; WORD code page value; WORD CPCB index, -1 = a per-process CUSTOM code page }`. Verifies 1251 bytes, re-reads `XTLength` from the table and verifies again if it is longer, then locks the caller's segment - short-term for a CPCB index, **long-term for a custom code page**. |
| **0x58** | `SetInUseCP` | selects which prepared entry a session uses. The per-session KCB carries `KCBFlags` bit 0 (`CUSTOMCP`) and `KCBIxOffCP` = *"CPCB index if flag above = 0, custom code page offset if flag = 1"*. |

So the whole `.DCP` file lives on the far side of these IOCtls.

**Which of `0x50` and `0x5C` the BOOT uses, settled by IBM in the driver's own source.** It is
**`0x5C`**, once per prepared code page - *not* `0x50`. `SetCodePage`'s header block says so
outright `[DOC-IBM]`
DDK `base/src/dev/kbd/kbdbase/kbdiocs.asm:2006-2009`:

> *"NOTE - This routine only replaces the **optional** code page data areas and **NOT** the
> 'hardware default' code page, which is replaced with IOCTL 50h (Set Translate Table)."*

So the two are different jobs, not two spellings of one: `0x50` overwrites the hardware-default
table at `CPCB[0]` in place, and `0x5C` populates the *optional* prepared entries that
`CODEPAGE=` asked for. No boot-time issuer of `0x50` has been identified. Read section 3.6's mention of
`KBD_SETTRANSTABLE (0x50)` accordingly - it is naming the table **format**, not the boot path.

#### Who reads the file at boot - ~~UNESTABLISHED, with three candidates positively ruled out~~ **ANSWERED 2026-09-09**

> **CORRECTED IN PLACE (Rule 1.7). The answer is `DOSCALL1`'s `Init_CP`, and the third
> bullet below - *"Not `DOSCALL1`'s 16-bit code"* - was FALSE. It is kept, marked, because HOW it
> was wrong is worth more than the answer.**
>
> **The chain.** `KbdSetCp` -> `KBDSETCP` -> `ROUTER` -> `_KBDBASESUBSYS` -> `BKSMAIN` -> its
> near-pointer dispatch table -> `SetCodepage` -> **`Init_CP`**, which takes the CDIB selector,
> reads `CDIB_keyboard_ptr`, `DosOpen`s the path written in the `DEVINFO=KBD` statement, reads the
> DWORD directory offset at file offset 0, walks the directory comparing each entry against the
> (byte-swapped) subtype, and hands each matched table to `KBD$` **category 4 function `0x5C`**,
> followed by `0x58` `SetInUseCP`. The 8-byte parameter packet it passes matches `kbdiocs.asm`'s
> `SetCodePage` field for field. `[INF]` - read out of the shipped `DOSCALL1`, corroborated by
> IBM's driver source; entry-point names are IBM's, the offsets behind them are build-keyed and
> are not repeated here. Cross-check on the container: the directory bound and per-entry size the
> code loops on are the same **247 x 18** this section decodes independently above
> ("The container").
>
> **WHY THE THIRD BULLET WAS WRONG, AND IT IS A METHOD LESSON, NOT A SLIP.** It was produced by
> grepping a **decompilation** for `DosOpen` call sites. In a decompile an unresolved import fixup
> renders as an anonymous indirect call, while a symbol merely *named* `DosOpen...` matches the
> grep - so the search counted three symbols by **name** and missed **every actual call**. Read
> from the module's **fixup table** instead, `DOSCALL1` has 22 `DosOpen` call sites, and `Init_CP`
> is one of them. **When asking whether a module calls something, grep the fixup table, not the
> decompile** - a tool that printed nothing useful had been rendered as "the binary does not say".
>
> The first two bullets stand unchanged and are what make the answer land where it does.

This was the open end of `DEVINFO=KBD`. The three candidates as they were recorded:

* **Not the kernel's CONFIG.SYS processing.** `syicpDevInfo` does `DosOpen` and an immediate
  `DosClose`, records the path string, the subtype and the `ROM=` list into the CDIB, and never
  seeks or reads (`config-and-environment.md`, "Boot-time NLS initialisation"). `[OBS-RE]`
* **Not the KBD$ driver.** Its `SetXlateTbl` and `SetCodePage` handlers receive a table and verify
  access to it; no keyboard IOCtl takes a filename. `[DOC-IBM]`
* ~~**Not `DOSCALL1`'s 16-bit code.** The only `DosOpen` call sites in its whole 16-bit decompile
  are the queue and VDD ones; its `KbdSetCp` is a one-line dispatch.~~ **FALSE - see the
  correction block above.** Its `KbdSetCp` really is a one-line dispatch; that was never the
  question, and following it is what leads to `Init_CP`.

What *is* established about the trigger: initialisation calls `VioSetCp` and `KbdSetCp` with the
primary code page immediately after the CDIB is built, before any `DEVICE=` line is processed; and
`DOSCALL1` does read the CDIB's code-page section and the keyboard device section, copying the
8-byte subtype into its own data, before making a call the decompile could not resolve. ~~That
unresolved call is the most likely site.~~ **It was - the call is into `Init_CP`, and following it
is what answered this (correction block above).** Recorded rather than struck, because the
prediction and its confirmation are both the point: two unresolved calls were an invitation to
resolve them, not to describe them.

A caution recorded with the gap: `KEYB.EXE` performs the same job at run time and is a much smaller
binary, but IBM's own prose separates boot-time *preparation* from `KEYB`'s *switching*, so the two
may not share code - do not infer the boot-time reader from `KEYB.EXE`. **The caution held**:
`KEYB.EXE` was deliberately never read, and the answer came out of the boot-time module instead.

**What remains genuinely unread on this path**, so the gap is narrowed rather than declared shut:
where `Init_CP` obtains the CDIB selector it starts from. It reads it out of a `DOSCALL1` data
slot; whether that slot was filled by a `DosGetShrSeg` on `\SHAREMEM\DOS\CDIB` (as the screen
half demonstrably does) or by some earlier initialisation step is **not established**. **-> Answered
(recorded here 2026-10-13; read 2026-10-11): the base keyboard subsystem `BKSMAIN` fills it, on any
keyboard call that finds it zero, with `DosGetShrSeg("\SHAREMEM\DOS\CDIB")` - the same route as
the screen half.** `[OBS-RE]` `DOSCALL1.DLL` `BKSMAIN`, its `CDIB_Sel` cell. Nor is it
established who calls `BVHVGA`'s `GETCODEPAGE` - no direct call to it exists in that module, so it
is reached indirectly or through the entry table. See `config-and-environment.md`, "The CDIB".

### 3.8 How the `Kbd*` calls behave, read from the shipped binaries [OBS-RE] + [DOC-IBM]

*Added 2026-10-13.* Sources: the Warp 4.5 `DOSCALL1.DLL`, uniprocessor build, read against its
matched symbol file (the SMP build compared where stated); IBM's shipped KBDBASE source in the
DDK (`base/src/dev/kbd/kbdbase/`); the SMP kernels 14.104a (retail) and the AStrict debug kernel,
each with its symbol file. **Read, not measured**, unless a line says otherwise. Routine names are
IBM's, from the symbol files.

#### Where the calls live

- Every `Kbd*` entry point is in `DOSCALL1` (DOSCALLS ordinals 745-769). `KBDCALLS.DLL` is
  25 forwarders, its ordinal *n* to DOSCALLS 744+*n*; `BKSCALLS.DLL` forwards its one entry to
  851, `BKSMAIN`, the base keyboard subsystem. All are 16-bit entries. `[OBS-RE]`
- The Warp 4.5 Toolkit declares only the 16-bit family (`bsesub.h`: `KbdCharIn` is
  `KBD16CHARIN`, `APIENTRY16`, `IO_WAIT`/`IO_NOWAIT` only). A later 32-bit keyboard family
  (`KbdGetConsole`, `KbdGetLayout`, `KbdSetLayout`, a `ULONG` wait flag with `IO_PEEK`) is
  documented in a later Control Program reference; no Warp 4.5 module exports or names it.
  `[DOC-IBM]` + `[OBS-RE]`
- Eleven calls are one-line stubs into the router (`ROUTER`, function codes 0x100-0x10D and
  0x110); `KbdCharIn`, `KbdStringIn`, `KbdGetFocus` and `KbdFreeFocus` have bodies of their own;
  `KbdProcessInit` (746), `KbdLoadInstance` and `KbdFree` answer 0; `KbdSetHWID` answers 120.
  `[OBS-RE]`

#### The bracket every call runs

1. `_KbdCheckProcType`: a detached process gets **464**; any process type other than full-screen
   or windowed VIO (a PM process included) gets **504**; if another *process* holds the session's
   API focus (`KbdGetFocus`), **447**. On the session's first keyboard call it initialises the
   session's keyboard block and calls `KbdSetCp(0, process code page, 0)`.
2. A per-session lock (a fast-safe RAM semaphore in the session's control block). The router
   waits for it without limit; `KbdCharIn`, `KbdStringIn` and `KbdGetFocus` wait without limit
   for IOWait 0, not at all for IOWait 1, and answer **375** for any other value. A timed-out
   wait answers **447**. **A thread blocked in `KbdCharIn(IO_WAIT)` or `KbdStringIn(IO_WAIT)`
   holds the lock for the whole block**, so the session's other keyboard calls wait behind it (or
   get 447 with IOWait 1).
3. A registered replacement subsystem, if its mask bit is set; otherwise `BKSMAIN`. A windowed
   session's call goes to the PM VIO-window module's console entries instead of `KBD$`; if that
   module cannot be loaded the call answers **500**. `[OBS-RE]`

#### Returns the binary gives that the reference pages do not list (or list differently)

| call | return | when |
|---|---|---|
| `KbdCharIn` | **95** `ERROR_INTERRUPT` | the blocked read was interrupted (a signal to the reader). `KBD$` ends the block with status 11h; the kernel's status table maps 11h to 95; `DOSCALL1` passes it through. |
| `KbdStringIn` | **376**, **447** | buffer length above 255; the session lock busy |
| `KbdGetFocus` | **446 at once** | any focus is already active in the session - whatever IOWait says. The page says the caller waits for the bond. IOWait only governs the lock. `[OBS]` 2026-10-13 (Warp 4.50, four boots): a second process of a full-screen session called `KbdGetFocus(IO_WAIT, 0)` while the first held the focus for 5 s more, and got 446 after 0 ms. |
| `KbdGetFocus` | **375**, **449** | bad IOWait; the driver refused the bond |
| `KbdFreeFocus` | **439** | a focus is active but this handle is not the bonded one (the page lists 445, which the binary gives only when no focus exists) |
| `KbdSynch` | **504**, **375**, **447** - never **121** | 504 to any caller outside the registered replacement subsystem's code (tested first); a timeout is 447. The page lists 0 and 121, and states the IOWait sense the other way round (the binary: 1 = no wait, like every other `Kbd*` call). |
| `KbdClose` | **0** even if the driver's DestroyKbd fails | see "KbdClose" below |
| `KbdGetHWID` | **373** for a length of 1-3 | and 4 is written into the caller's length word |
| `KbdSetHWID` | **120** always | no reference page; prototype only |
| `KbdShellInit`, `KbdSwitchFgnd` | **407** | the caller is not the keyboard's session manager (the first process to call `KbdShellInit`) |

#### What `KbdSetStatus` checks, in order `[OBS-RE]`

`DOSCALL1`'s `SetStatus` (read as instructions, 2026-10-13): `cb` below 10 -> **376**; Shift Report
(`fsMask` 100h) without Binary (04h) -> **378**. Then `fsMask`'s bits 0-6 are walked in order through a
seven-entry handler table, each handler's answer ending the walk: Echo On (01h) - with Echo Off (02h) also
set **377**, else the process's echo mode := on; Echo Off - echo mode := off; Binary (04h) - with ASCII
(08h) also set **378**, else the input-mode byte gets 80h and goes to `KBD$` as **51h**; ASCII - **51h**
with the Shift-Report bit only; Shift State (10h) - **53h** with `fsState` and `fsInterim`'s high byte;
Interim (20h) - **52h** with `fsInterim`'s low byte; Turnaround (40h) - the turnaround type from `fsMask`
80h (two-byte) and the character from `chTurnAround`'s low byte. A `KBD$` failure ends the walk and is
the call's answer (a reserved interim bit, for example, is 52h's parameter error, **87**). So the echo
mode and the turnaround are the process's; the input mode, interim flags and shift state are the
session's, in `KBD$`.

`KbdGetStatus` builds `fsMask` from those cells: the echo mode, then 04h (or 104h with Shift Report) for
Binary or 08h for ASCII, then 80h for a two-byte turnaround; `chTurnAround` the turnaround character; 72h's
byte as `fsInterim`'s low byte and 73h's DBCS shift byte as its high byte; `fsState` 73h's shift word.

#### Ctrl+C and Ctrl+Break with no focus holder `[OBS-RE]`

The kernel delivers keyboard Ctrl+C/Ctrl+Break (signals 1 and 4) through `PostSigFocus`, to the
signal focus of the **foreground** screen group. When that group has no holder for the signal,
`PostSigFocus` calls `KSGKillProcess` instead, which - only when the foreground group is **4 or
higher and below `sgMax`** - posts signal **3** (the kill signal) to **every process whose screen
group is the foreground one**. Each then sees `XCPT_SIGNAL` with `XCPT_SIGNAL_KILLPROC` on thread
1 and, unless a handler continues it, ends. Groups 0-3, and the windowed groups (`sgMax` and
above), get nothing. Identical in both kernels read. So IBM's rule that the INTR/BREAK signal is
sent only when something registered is true, and an unregistered Ctrl+C in a full-screen session
still ends the session's programs.

#### What `KbdFlushBuffer` reaches in the driver `[DOC-IBM]`

`DOSCALL1` flushes with `DosDevIOCtl` category 0Bh function 01h (`DEV_FLUSHINPUT`). `KBD$`'s
IOCtl entry handles no such function (outside category 4 it takes only 0A40h, 0B60h and 0B41h,
and answers everything else with a command error), so the flush reaches the driver as strategy
command 7, Input Flush: refused in single-queue mode, skipped when multi-layer code pages are on,
otherwise the requesting session's current keyboard queue is purged and its monitors flushed. The
kernel's conversion of 0Bh/01h into command 7 was not read.

#### `KbdStringIn`'s line editor: which key does what `[OBS-RE]` + `[DOC-IBM]`

The editor runs in `DOSCALL1` (not the driver), in ASCII mode only. Each key is looked up in one of
two byte tables (extended keys by scan code, other keys by character); the turnaround character is
tested first and ends the line.

| key | handler | key | handler |
|---|---|---|---|
| F1 | `COPYONE` - one template character | Right | `COPYONE` |
| F2 | `COPYSTR` - template up to a typed character | Left, Backspace, Ctrl+Backspace | `BACKSP` |
| F3 | `COPYLIN` - the rest of the template | Ins | `ENTERINS` |
| F4 | `SKIPSTR` - skip template up to a typed character | Del | `SKIPONE` |
| F5 | `REEDIT` - the line becomes the template | Esc | `KILNEW` - echo `\`, new line, restart |
| F6, Ctrl+Z | `CTRLZ` | Ctrl+W | `WORDDEL` |
| F7 | `TWOESC` | Ctrl+Enter | `PHYCRLF` |
| any other extended key; Ctrl+F | ignored | any other character | stored |

The F1-F5 and Esc meanings are IBM's own, from the Command Reference's `KEYS OFF` list; what every
handler does is below.

#### What each line-editing key does `[OBS-RE]`

Read from the handler bodies in the shipped Warp 4.5 `DOSCALL1.DLL` (the SMP build's copy is the same
length, differing in the bytes checked only by data offsets); not yet observed on a running system. The **template** is the previous line: the contents of
the caller's own buffer, of length min(`cb`, `cchIn`), **used only if the byte just past it is the
turnaround character** (which the previous call left there); otherwise there is no template. The new
line is built separately and reaches the caller's buffer only when the line ends (or at F5). A
template cursor tracks the position in the template.

- **Typing** a character stores it and echoes it. In the default **overtype** mode the template
  cursor advances one character; in **insert** mode it does not. Every new line starts in overtype.
- **Enter** (the turnaround): the line ends. The characters, then the turnaround, are written to the
  caller's buffer; `cchIn` counts the characters only. The echo is **CR without LF** - the caller
  moves to the next row itself.
- **Full buffer**: a character that does not fit is discarded with a short two-tone beep (440 Hz then
  587 Hz, 5 ms each), and **the read continues**; only the turnaround ends it. One byte is always
  kept for the turnaround (two for a two-byte turnaround), so at most `cb` - 1 characters return.
- **F1** or **Right**: copy one template character. **F3**: copy the rest of the template.
  **F2** then a character: copy the template up to, not including, the next occurrence of that
  character, searching from the character **after** the template cursor; if it is not found, or the
  second key is an extended key, nothing happens and that key is consumed. Each copy echoes the
  copied characters, **turns insert mode off**, and stops quietly at the end of the template or when
  the line is full.
- **Del**: skip one template character. **F4** then a character: skip the template up to, not
  including, the next occurrence (same search as F2). Nothing is echoed.
- **Ins**: toggle insert mode. Nothing is echoed and the cursor shape does not change.
- **Backspace**, **Ctrl+Backspace** (7Fh), **Left**: remove the last character, echoed as BS space
  BS - twice for a control character (it was shown as two cells), and as many as the tab occupied
  for a TAB. In overtype mode the template cursor steps back with it.
- **Ctrl+W**: remove the last character, then keep removing while the character before is a letter
  or digit: `foo bar` becomes `foo `, and so does `foo bar `.
- **Esc**: echo `\`, a new row, and spaces to the column where input began; the line is discarded
  and begins again empty, with the template unchanged.
- **F5**: echo `@`, a new row, and spaces to the starting column; **the line typed so far becomes the
  template** (it is written into the caller's buffer at once) and input begins again empty.
- **F6** and **Ctrl+Z** store 1Ah, echoed `^Z`. **F7** stores 00h, echoed `^@`.
- **Ctrl+Enter** (0Ah): echo CR LF and continue the same line on the next row; nothing is stored.
  As the **first** key of a line it is discarded with no echo.
- **Ctrl+F** and any other extended key (Up, Down, Home, F8 ...): ignored. The grey cursor and
  Ins/Del keys act exactly as the keypad ones.

**Echo.** A stored control character other than TAB, 14h and 15h is echoed as `^` followed by the
character plus 40h (`^A` for 01h). A TAB is stored as 09h and echoed as spaces to the next multiple
of 8 columns. Each echoed byte is a single `VioWrtTTY`. **With echo off, every editing key still
works**; nothing is written.

**Where this differs from the reference page.** The Control Program Reference says that in ASCII
mode the call ends *"when a turnaround character is found or when the buffer is full"* and that
*"the turnaround character is not placed in the buffer"*. The code ends ASCII-mode input only on the
turnaround, and stores the turnaround in the buffer immediately after the `cchIn` characters, which
is what lets the next call recall the line. The page's statement holds for what `cchIn` counts.

In double-byte code pages the same keys move, copy and remove whole double-byte characters.

**A buffer too small for a line** `[OBS-RE]` + `[OBS]`: an ASCII-mode call whose `cb` is not larger than the
turnaround's length (`cb` 0 with the usual one-byte turnaround) returns 0 at once with `cchIn` 0 and reads no key.
Measured on Warp 4.50, 2026-10-14 (a 16-bit program in a full-screen session, IBM's own kernel and `DOSCALL1.DLL`):
the keys typed for that call were read by the next one.

#### ANSI: the cursor-position report and key reassignment, on the input side `[OBS-RE]` + `[OBS]`

Both ANSI input features reach a program **only through ASCII-mode `KbdStringIn` with ANSI on** for the session
(`VioGetAnsi`, asked afresh by every such call). `KbdCharIn` and binary-mode `KbdStringIn` never see either.

**The cursor-position report.** Writing `ESC[6n` with `VioWrtTTY` (ANSI on) builds `ESC [ r r ; c c R CR` - the
cursor, 1-based, two decimal digits each - and leaves it **pending in the session's BVS control block**, not in any
process. The next ASCII-mode `KbdStringIn` with ANSI on, **by any process of that session**, returns it as the whole
line: no key is read, nothing is echoed, and `cchIn` counts the delivered bytes **including the CR** (9 when `cb` is
9 or more), unlike a typed line, whose turnaround follows `cchIn`. A `cb` below 9 gets the first `cb` bytes and the
rest is lost; `cb` 0 discards the report. With ANSI off, or in binary mode, the report stays pending and the read is
an ordinary one.

**Key reassignment.** `ESC[` *key* `;` *string* `p` defines a key: the key is one parameter, or two when the first is
0 (an extended key: `0;59` is F1), or `E0` and a scan when `ESC[1q` has enabled the extended keys' own codes. Each
following parameter is one byte of the definition - a quoted string one byte per character, a number its value - and
**the `;` after a closing quote is itself an empty parameter, stored as 0**, so `ESC[0;59;"dir";13p` stores
`d i r 00 0D`. Definitions are kept per screen group and keyboard code page; redefining replaces, and an empty
definition (`ESC[0;59p`) leaves the key behaving as it normally does.

In the line editor each typed key is looked up (before the grey-key `E0` is folded to 0); a defined key is **replaced
by its definition**, which is then fed to the editor one key at a time - stored, echoed and edited exactly like typed
keys:
- a byte other than 00 is a character;
- `00` followed by a non-zero byte is an extended key with that scan code - `00 0D` therefore ends the line, because
  a scan equal to the turnaround is the turnaround;
- `00` followed by `00` (or at the end) is a lone character 0 carrying the previous key's scan, which the editor
  acts on as that key: in `ESC[0;62;"xy";0;75;"z";13p` (F4) the stored `x y 00 00 4B z 00 0D` yields `xyz` - the lone
  0 repeats F4, whose argument is the next key - not `xz`.

**A replay outlasts the call**: a definition holding two lines returns the first from one `KbdStringIn` and the second
from the next, without a keystroke. The replay belongs to the process.

Measured on Warp 4.50, 2026-10-14, 16-bit program, full-screen session: every statement above except "by any
process" and the `E0` arm, which are read from the code only.

**The entry points behind them**: `ANSIINJECT` (DOSCALLS 848, also `ANSICALL.1`) and `ANSIKEYDEF` (849,
`ANSICALL.2`) are the two routines the console uses, callable directly with one far pointer to {buffer, count byte,
action byte, key word}: action 1 reads (the report, or a key's definition - 0x80 bytes at most), any other value
builds the report from the cursor or defines the key. `BVSGETPTRDRAWNAME` (847, `BVSCALLS.1`; configuration, kind,
far pointer out) returns the configured pointer-draw driver's name, `POINTER$` when none is configured, and 0xFFF8
before the shell is initialised, for a configuration other than the one, or for a kind other than 0 (real) and 1
(protected). Measured as described, on the same system.

#### What a pause does `[OBS-RE]`

Ctrl+S, Pause and Ctrl+NumLock (in ASCII mode) raise the driver's pause event; the session
manager's pause thread toggles a pause flag and semaphore in the foreground session's control
block. The VIO router tests that flag on every VIO call and **blocks the call on the semaphore**
until the next toggle, so a paused session's screen output stops while its keyboard calls do not.
The next key ends the pause and is discarded by the driver.

#### `KbdClose` `[OBS-RE]`

If the handle holds the focus, the focus is freed first (its error, if any, is returned). Then,
inside a critical section, for a non-zero handle: the driver's DestroyKbd (category 4 function
5Eh) on the handle, the open count decremented on success (removing the keyboard exit-list routine
at zero), the bond cleared if it named the handle, and `DosClose` of the handle whatever the driver
answered. The call returns the critical-section exit's result, so a failed DestroyKbd is not
reported. Handle 0 does nothing.

#### Per-process and per-session keyboard state `[OBS-RE]` + `[DOC-IBM]`

Echo mode, the turnaround character and the line editor's state are **per process**, in
`DOSCALL1`'s instance data: their defaults are echo on and turnaround CR. The input mode
(ASCII/binary, shift report), the shift and interim state and the translate-table choice are
**per logical keyboard** in the driver, and handle 0's logical keyboard is the session's own - so
every process of a session reading through handle 0 shares one input mode. In a windowed session
`KbdSetStatus` records the requested mode in `DOSCALL1` and nothing reads it back; the window's
console module answers `KbdGetStatus` there.

#### What starts the keyboard, and which session receives keys `[DOC-IBM]` + `[OBS-RE]`

The keyboard driver keeps its own "current session" for interrupt time, apart from the kernel's
foreground variable. It has three writers in IBM's shipped `KBDBASE` source, not two:
- the session manager's pre-switch notification (category 0Bh function 41h, action 20h), which
  clears the outgoing session's active flag, sets the incoming one's, and makes it current;
- **the foreground session's first read** - `FirstReadCheck` (`kbdswap.asm`), run by a read
  (category 4 function 74h) or peek (75h) while the driver's "no read yet" flag is set. When the
  reader's session is `SIS_CurScrnGrp` it clears the flag, marks the first read done, makes the
  reader's session current and active, and moves the shift state saved for session 0 into the
  reader's keyboard control block.

Until that first foreground read the driver drops every key and does not test for session-manager
hot keys; after it, keys reach that session with no notification having been sent. While no process
has set a session-manager hot key (the first caller of function 56h) and no first read has been
done, the flag is set again after each queued key. On a system where a text-mode shell registers
with the session manager, the first foreground read is the registration's own no-wait read in the
shell's session, so from then on keys go to the shell's session until the first switch. The shipped
binary agrees with the source.

A `KbdCharIn` that waits, made from a session that is not in the foreground, does not fail: the base
subsystem first tries to register the caller as the session's keyboard-foreground process, ignores
that step's refusal, and goes on to the driver's read, which blocks on the caller's own session's
queue until that session is current and a key arrives `[OBS-RE]`.

#### The SMP build `[OBS-RE]`

The SMP `DOSCALL1` uses the same session-control-block displacements for all of the above; its own
per-process cells sit 0x50 bytes higher, and it adds keyboard trace hooks. No behavioural
difference was seen.


### 3.6a The KBD$ device driver's hotkey classification (earlier write-up) [OBS-RE]

*Kept for its detail; section 3.6 above is the newer and fuller account, and wins where the two differ.*

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
binaries:

**The real driver's `DosDevIOCtl` contract** - category `0x07` (`IOCTL_POINTINGDEVICE`), function
codes `0x51`-`0x5D` (SET: display mode, scaling factors, event mask, threshold, pointer shape,
collision area define/remove, pointer position, device status) and `0x60`-`0x6D` (GET: the
symmetric read side, plus pointer version/device-ID and, added later, a pointer-confinement
region). Category `0x0A`/`0x0B` (Monitor / General, shared with the keyboard driver) carry mouse
monitor registration and the Session Manager's own screen-group control call into the driver.
[DOC-IBM: IBM's `MOUSE.SYS` source, `mouse.inc`/`ioget.asm`/`ioset.asm`.]

**`MouCalls` itself does not issue those codes directly.** Each public entry point (`MouOpen`,
`MouGetNumButtons`, `MouSetPtrPos`, ...) pushes a small, densely-packed internal opcode (0-0x15)
and calls one shared dispatcher - the **same dispatcher the keyboard side reaches through its own
device-type discriminator**, i.e. keyboard and mouse share one generic internal dispatch layer
inside `DOSCALL1.DLL`, with the category-0x07 driver contract above being what that dispatcher
issues to the actual driver underneath, not what the public API pushes. [OBS-RE: disassembly of
the real Warp 4.5 `DOSCALL1.DLL` against its matching `.SYM` file.]

Full function-code tables, the complete internal opcode-to-`MouCalls`-name mapping, and what each
of the two layers means for a from-scratch implementation vs. hosting the real driver: a dedicated
project research document (outside this reference corpus, since it also covers implementation
choices) - not reproduced field-by-field here to keep this doc to the timeless API/driver *facts*.

### 4.6 The mouse path end to end: the base subsystem, `MOUSE$`, and the pointer-draw driver [DOC-IBM / OBS-RE]

**No 32-bit API.** Every `Mou*` function is `APIENTRY16`; a 32-bit compile maps `MouOpen` to
`MOU16OPEN` and so on, i.e. 32-bit code thunks to the same 16-bit entries. [DOC-IBM: bsesub.h:866-890.]

**The gate every routed call passes first.** 21 of the `Mou*` exports enter one dispatcher in
`DOSCALL1` (`ROUTER`), whose mouse prologue answers, in this order: **385** if no mouse device was
found when the session manager called `MouShellInit` (a presence probe, `DosOpen("\DEV\MOUSE$")`);
**466** for a detached process; **505** for a process that is neither full-screen (type 0) nor
windowable VIO (type 2) - so every routed call from a PM process is 505. Only then does the
alternate-subsystem test and the base subsystem run. `MouGetHotKey`/`MouSetHotKey` always return 0;
`MouInitReal` is session-manager-only (412); `MouRegister`/`MouDeRegister` test the screen group and
process type (415/416) before the same gate. [OBS-RE: `DOSCALL1.DLL` Warp 4.5 UNI, `ROUTER`
`_MouCheckProcType` obj4:0x352C, `ROUTSMINIT` obj4:0x2C1E; OBS: WSeB 4.50 SMP, 2026-09-29, every mouse
driver removed -> all 21 routed calls 385; with a mouse, from an ssh (detached) process -> 466.]

**Most calls are one IOCtl, and its result is the API's result.** The base subsystem's `HMOU` is a
`DosOpen` handle on `\DEV\MOUSE$`. Fifteen routed calls issue exactly one `DosDevIOCtl` category 07h
on it (`MouGetNumButtons` 60h, `MouGetNumMickeys` 61h, `MouGetDevStatus` 62h, `MouGetNumQueEl` 64h,
`MouGetScaleFact` 66h, `MouGetEventMask` 65h, `MouSetScaleFact` 53h, `MouSetEventMask` 54h,
`MouGetPtrShape` 68h, `MouSetPtrShape` 56h, `MouDrawPtr` 57h, `MouRemovePtr` 58h, `MouGetPtrPos`
67h, `MouSetPtrPos` 59h, `MouSetDevStatus` 5Ch); `MouFlushQue` is category 0Bh function 01h;
`MouReadEventQue` (63h), `MouGetThreshold` (69h) and `MouSetThreshold` (55h) are one IOCtl after a
check of their own; `MouOpen`/`MouClose` are `DosOpen`/`DosClose` plus set-up. **No layer maps the
IOCtl's return code.** [OBS-RE: `BMSFUNCTIONS` obj4:0x3968, `BMSMAIN` obj4:0x373A, `_IoctlTable`
obj7+0xE38.] Two checks happen before the driver:
- `MouReadEventQue`: a `ReadType` **above 3 -> 435 `ERROR_MOUSE_INVALID_IOWAIT`**. [OBS-RE:
  `BMSREADEVENTQUE` obj4:0xBB98.]
- `MouGetThreshold`/`MouSetThreshold`: `THRESHOLD.Length` **below 2 or above 10 -> `Length` is
  rewritten to 10 and 387 `ERROR_MOUSE_INV_PARMS`** is returned. [OBS-RE: `BMSGETSETTHRESHOLD`
  obj4:0xBF96.]

**What a driver rejection becomes.** `MOUSE$` fails a bad parameter with request status 8013h, a
general failure with 800Ch, an interrupted wait with 8011h and an unsupported request with 8003h
[DOC-IBM: DDK `base/src/dev/mouse/mouse.inc:134-138`]. The kernel translates a category-07h error
byte through its INT-24 map, which holds **13h -> 87, 0Ch -> 31, 11h -> 95, 03h -> 22** [OBS-RE: the
Warp 4.5 kernel's `ErrorTriage` and its 21-entry map]. So a parameter the driver rejects
(`MouSetPtrPos` outside the mode, a reversed-limits or off-screen `MouRemovePtr` rectangle, an
out-of-range scale factor or event mask, a too-small `MouGetPtrShape` buffer) **reaches the caller as
87, where IBM's pages list 387**. [INF; unverified by capture - see the conflicts below.]

**`MOUSE$` keeps one record per screen group** (`ScrGp_Data`, 0xA4 bytes, a layout shared with the
pointer-draw driver): scaling, the device-status word, the event mask, the open-handle count, the
event queue's head/tail/count and the pid blocked on it, the pointer-draw entry, the display mode,
the pointer (flags, size, position, hot spot, image), the collision area, the display configuration,
the thresholds. Records for groups 0, 1 and 3 exist from initialisation; every other full-screen
group's is allocated when the session manager reports its creation. **A windowable-VIO or PM caller
is served from group 1's record, a detached caller from group 3's.** [DOC-IBM: DDK
`base/src/dev/mouse/sgcb.inc`; `strat.asm:326-370`; `init.asm:445-475`; `util2.asm:1133`.]

**First open.** The first `MouOpen` in a session (open count 0) sets scale 16/8, every event the
button count allows, an empty queue, the settable status bits clear, **the collision area = the whole
screen**, the pointer centred (or at 0,0 with no mode known yet), the default pointer shape, default
thresholds. Later opens in the same session only count. The last `MouClose` removes the pointer (in
the foreground) and flushes the queue. [DOC-IBM: `strat.asm` `OPEN`/`CLOSE`; Control Program
Reference - MouOpen.]

**The event queue** is a FIFO ring, by default **10 elements of 10 bytes**, sized by the driver's
`DEVICE=` line. **When it is full, a new event overwrites the oldest.** A reader blocked with
`MOU_WAIT` is woken when an event is queued. With `MOU_NOWAIT` on an empty queue the driver
**zero-fills the caller's record and reports success**; the `ReadType` word is examined only when the
queue is empty, and the driver accepts only 0 and 1 there. **Only the foreground full-screen
session's record receives events**: at interrupt time the driver scales and clamps the motion,
filters by the session's event mask (a reportable button release is always reported), drops an
event identical to the previous one, and queues it - or hands it to a monitor chain or the
single-queue driver instead. [DOC-IBM: `ioget.asm:293-616`, `move.asm:357-553`,
`util1.asm:397-530`, `data.asm:308`.]

**Who draws the text-mode pointer: the pointer-draw device driver, never `MOUSE$`.** `MouOpen` finds
the session's pointer-draw driver (the one named, else the display configuration's, default
`POINTER$`), opens it and asks it for its entry point with category 03h function 72h, and hands that
to `MOUSE$` with category 07h function 5Ah. `MOUSE$` then far-calls the entry with the session's
record and a function code: **0 draw, 1 remove, 2 free the image (back to the default), 3 check a
display mode, 5 install a new image** (4 is unsupported). In a text mode the IBM driver draws one
cell: it saves the cell from **physical video memory**, then writes `(cell AND andmask) XOR xormask`
- the default text pointer is AND FFFFh, XOR 7700h, i.e. **the character kept and the attribute
XORed with 77h**; removing it writes the saved cell back. [DOC-IBM: PDD Reference
`PTR_GETPTRDRAWADDRESS`; DDK `util1.asm:135-196`, `macs.inc:49-80`; Control Program Reference -
MouSetPtrShape ("reverse block character"); OBS-RE: `POINTDD.SYS`, every function read.] Consequence
[INF]: with no pointer-draw driver loaded, `MouOpen` fails with that driver's `DosOpen` error even
though `MOUSE$` exists.

**When the pointer is visible.** All of: the session is the foreground; interrupt-time drawing is on
(`MouSetDevStatus` with `MOU_NODRAW` turns it off and the application draws its own); the display
mode is supported; a pointer-draw entry is registered; no session switch or mode set is in progress;
and **the pointer's rectangle lies outside the collision area**. So after the first `MouOpen`
**nothing is drawn** until `MouDrawPtr` clears the area; `MouRemovePtr(rect)` replaces the area and
hides the pointer if it is inside; there is one area per session. Mouse motion (at interrupt time),
`MouSetPtrPos` and `MouSetPtrShape` remove the image and redraw it at the new place unless that is in
the area. **VIO does not hide the pointer around `VioWrt*`** - the application is expected to bracket
its writes with `MouRemovePtr`/`MouDrawPtr`; a mode set is the exception: BVS brackets it with
category 07h 51h (remove) and 5Dh (redraw). [DOC-IBM: Control Program Reference - MouOpen,
MouDrawPtr, MouRemovePtr, MouSetPtrShape; `ioset.asm` `IOMW_SM`/`IOMW_DP`/`IOMW_RP`/`IOMW_SP`/
`IOMW_MD`; `util1.asm` `CollisionChk`/`Update_Ptr`; OBS-RE: BVS `BvsSetMode` and `NotifyMouse` in
`DOSCALL1`.]

**What arms the mouse: the session manager's initialisation, not the shell's own program.** Three
things are done only inside `DOSSMSGINIT`, which runs only when a shell calls `DOSSMINITIALIZE`
(DOSCALLS #707). PM's session-manager start calls it, and so does TShell; `CMD.EXE` calls neither.
(1) `DOSSMINITALLOC` opens `MOUSE$` and calls `MouShellInit`, which sets the "a mouse exists" flag
that every routed `Mou*` call tests (otherwise 385). (2) `VioShellInit` sets BVS's system-wide
"mouse present" bit. Only a session control block created after that bit is set is marked
mouse-active, and only a mouse-active session has its display mode sent to `MOUSE$` (category 07h
51h/5Dh, on its first BVS call and around every `VioSetMode`). (3) `DOSSMOPENDD` registers `MOUSE$`
for the switch notices. [OBS-RE: `DOSCALL1` `DOSSMSGINIT` obj3:0x9D40/0x9D47, `DOSSMINITALLOC`
obj3:0xA1A2, `BVSMAIN` `vf_ShellInit` arm obj4:0x1916, `InitBVSCB`; DOC-IBM: `strat.asm` OPEN]
[INF]: with `PROTSHELL=CMD.EXE`, `MouOpen` answers 385 unless some process calls `MouShellInit`
itself. If one does, the session's mode is never known: `MouGetDevStatus` shows bit 3, the pointer
starts at 0,0, and nothing is drawn.

**Where the pointer-draw driver writes** [OBS-RE: `POINTDD.SYS`, two builds]. The text pointer is
written into physical video memory at **B8000h** when the session's mode data has `fbType` bit 0 set,
and at B0000h when it is clear. The later (10.056) build adds a planar-VGA arm at A0000h. When a mode
is checked (51h), it chooses between the arms by reading VGA Graphics Controller register 6, i.e. by
the state of the hardware at that moment. Its planar arm depends on a callback that only an
undocumented function 7Fh of `POINTER$` registers.

**`MOUSE$` can skip the pointer-draw driver because of a field it never initialises.** The record's
GRADD fields - `fTaskPtr` (+8Ch, "a task-time pointer is registered"), `fBlocked` (+90h),
`CursorBlockID` (+94h) - are written only by category 07h function 5Eh (`fTaskPtr`) and by the
GRADD pointer thread's read (`fBlocked` 1/0). `InitFSCB`, which sets up every record, clears the
fields on either side of them and not these, and the record comes from `DevHlp_VMAlloc` (flags 82h).
VMAlloc returned memory from the kernel's resident heap holding old data, and IBM's VMAlloc page does
not say the memory is zeroed. `DrawPointer` and `RemovePointer` test `fTaskPtr` before anything else. When it is
non-zero they **never call the pointer-draw entry**: Draw only wakes the GRADD pointer thread
(`DevHlp_ProcRun` on `CursorBlockID`, if `fBlocked`), and Remove returns. Every other drawing condition
can hold, with every call answering 0 and `MouGetDevStatus` 0000, and still no pointer appears.
[DOC-IBM: DDK `base/src/dev/mouse/sgcb.inc:210-215`, `util1.asm:135-196`, `util2.asm` `InitFSCB`,
`mem.asm` `AllocMem`, `ioset.asm` `IOMW_RG`, `ioget.asm:1341-1363`; PDD Reference `VMAlloc`.]
[OBS: WSeB 4.50 SMP (HStrict kernel, one CPU) under VirtualBox, IBM `MOUSE.SYS`, `POINTDD.SYS`
10.056, SVGA handler, kernel debugger, 2026-10-14. A full-screen session's record held `fTaskPtr` =
FD443278h, `fBlocked` = FD443450h and `CursorBlockID` = FD40D754h, all addresses inside the kernel
resident heap and none a value that 5Eh or the pointer thread writes. `DrawPointer` took the task-time branch, and the
pointer-draw entry was never called on motion. The shipped binary's `InitFSCB` and `AllocMem` match
the DDK source. **With `fTaskPtr` zeroed by hand, the next motion called the entry (remove, then draw):
`Ptr_Flags` became 81h and the cell appeared at the pointer's position in B8000h.**] [INF]
Whether a pointer appears therefore depends on what the heap held before the record was allocated.
So a text session can show a pointer on one boot and none on another, under PM or a private shell.

**Across a session switch.** `MOUSE$` learns of sessions only from the session manager, which opens
`MOUSE$` at start-up, registers it for notices, and sends category 0Bh function 41h on creation,
termination, pre-switch and post-switch. **Pre-switch from a full-screen session: all mouse input is
ignored and that session's pointer is removed** (so the saved cell goes back into video memory).
**Post-switch to a full-screen session: it becomes the foreground record and its pointer is drawn**
(where that session left it, in its own shape and collision area). Post-switch to anything else (PM,
windowable VIO): the foreground record is cleared and text-session mouse processing stops. [DOC-IBM:
DDK `ioset.asm` `SGControl`, `util2.asm` `SGSwitchStart`/`SGSwitchEnd`, `data.asm:529-531`; PDD
Reference `DEV_SYSTEMNOTIFYPDD`.]

**Where IBM's pages and IBM's code disagree** (each settled only by a capture from a full-screen
session on a real console with a mouse and a pointer-draw driver loaded):
1. driver-rejected parameters: 387 on the pages, 87 by the code path (above);
2. `MOU_NOWAIT` on an empty queue: the pages list 393 `NO_ERROR_MOUSE_NO_DATA`, the driver returns
   success and a zero record, and nothing above it maps the code;
3. `ReadType` 2 and 3 reach the driver (rejected only on an empty queue); above 3 is 435, a code the
   page does not list;
4. a bad `HMOU` reaches `DosDevIOCtl`/`DosClose`, whose answer for a bad handle is 6 [INF];
   `MouClose(0)` returns 0 without calling anything [OBS-RE];
5. `MouOpen` with an unusable pointer-draw name: the page lists 390; the code returns the error of
   opening `\DEV\<name>` or of its function 72h [OBS-RE: `BMS_SET_POINTER_DRAW` obj4:0xB798].


### 4.5a The MOUSE$ IOCtl contract and MouCalls' dispatch (earlier write-up) [OBS-RE]

*Kept for the IOCtl table below; section 4.5 is the newer account, and wins where the two differ.*

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
- `config-and-environment.md` "Boot-time NLS initialisation" - what `DEVINFO=KBD` and `CODEPAGE=`
  do at boot, and what happens when the file named in section 3.7 cannot be opened.
