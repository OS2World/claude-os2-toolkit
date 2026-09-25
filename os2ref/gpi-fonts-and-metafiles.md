# OS/2 Presentation Manager - GPI Fonts, Bitmaps, and Metafiles

The depth topics of the Graphics Programming Interface beyond the core drawing primitives:
the **fonts** an application selects and measures text with, the **bitmaps** it creates,
loads, and block-transfers, and the **metafiles** it records a drawing into and replays.
All three are *resources* addressed through a presentation space (`HPS`): fonts and bitmaps
are given a **local identifier** (a "setid" / `lcid`) that later drawing calls reference, and
a metafile is produced by aiming a device context at a recording target rather than a screen.
This reference documents the model and the representative API surface; the core `Gpi*` drawing
calls, the DC/PS model, and the transform pipeline are in `gpi-drawing.md`, and the internal
engine that executes primitives (GRE / VMAN / the presentation driver) is in `pm-graphics.md`.

Provenance: **[DOC-IBM]** OS/2 Toolkit 4.5 headers - `os2def.h` (`FATTRS`, `FONTMETRICS`,
`PANOSE`, `FATTR_*` / `FM_*` constants, `FIXED`, `STR8`), `pmgpi.h` (all `Gpi*` font / bitmap /
metafile prototypes, `FONT_*` / `QF_*` / `CHS_*` / `TXTBOX_*` / `LCID_ALL` / `ROP_*` / `BBO_*` /
`CBM_INIT` / `HBM_ERROR` / `PMF_*` / `LC_*` / `LT_*` / `RES_*` constants, `KERNINGPAIRS`,
`FACENAMEDESC`, `RASTERIZERCAPS`, `SIZEF`), `pmbitmap.h` (`BITMAPINFOHEADER2` / `BITMAPINFO2` and
the legacy 1.x forms, `RGB2`, `BCA_*` compression, `BITMAPFILEHEADER2`, `BFT_*`), `pmdev.h`
(`DevOpenDC` / `DevCloseDC`, `OD_METAFILE` / `OD_METAFILE_NOQUERY` / `OD_MEMORY` DC types).
**[DOC-IBM]** the IBM *GPI Programming Guide and Reference* (the on-line "GPI Guide and
Reference" book) for behavioural detail - the font-matching algorithm, the bitmap memory-DC
model, `BitBlt` inclusivity/stretch semantics, and metafile playback options - cited per section.

---

## 1. The local-identifier (setid) model [DOC-IBM]

A presentation space keeps a small table of **local identifiers** (`lcid`, also called
*setids*). A logical font, a bitmap, or a pattern set is loaded/created, bound to an `lcid`
the application chooses, and then *selected* into the PS by that number. Drawing calls read
the currently-selected setid - they never take a font or bitmap handle directly. `lcid` values
1 and up are application-assigned; `0` is the reserved **default** setid (the system default
font, released with `GpiSetCharSet(hps, 0)`).

**The range is 0 through 254** - "It must be in the range 0 through 254" [DOC-IBM - `gpi2.txt`,
*GpiCreateLogFont*, `lLcid`] - so a PS supports at most 254 application setids at once. Redefining
an lcid already bound to a logical font simply replaces it, *unless* that lcid is the current
pattern-set or marker-set, or refers to a bitmap, in which case the call errors [DOC-IBM - same].

**The table belongs to the PS, not to the application.** Because setids live in one presentation
space, an object that is shared across several PSs (a font used by more than one window or by a
memory PS as well as the screen) cannot cache "its" lcid - it must hold the *request* (e.g. the
`FATTRS`) and be bound separately in each PS. When the PS is released the setids go with it; do not
call `GpiDeleteSetId` on a PS that is already gone. [OBS-RE - established porting Scintilla to PM,
where one `Font` object is shared by every drawing surface.]

| Call | Purpose |
|---|---|
| `GpiSetCharSet(HPS, LONG lcid)` | Select the logical font at `lcid` as the current font (0 = default) [pmgpi.h:1519] |
| `GpiQueryCharSet(HPS)` | Return the currently selected font `lcid` [pmgpi.h:1522] |
| `GpiDeleteSetId(HPS, LONG lcid)` | Delete a setid; `LCID_ALL` (`-1`) deletes all [pmgpi.h:1656, 1764] |
| `GpiQueryNumberSetIds(HPS)` / `GpiQuerySetIds(...)` | Enumerate the setids in use and their types (`LCIDT_FONT`=6, `LCIDT_BITMAP`=7) [pmgpi.h:1652-1654, 1812-1818] |

A setid must not be deleted while selected: releasing a font (`GpiSetCharSet(hps, 0)`) precedes
`GpiDeleteSetId` [DOC-IBM, `GpiDeleteSetId` example]. Attempting to reuse an in-use setid fails
with `PMERR_SETID_IN_USE` (0x2102).

---

## 2. Fonts

### 2.1 The two font kinds and the selection model [DOC-IBM]

OS/2 fonts are of two kinds:

- **Image (bit-map) fonts** - a fixed raster of glyphs at specific point sizes and device
  resolutions. Sharp at their design size; they do not scale smoothly.
- **Outline (vector) fonts** - glyph contours (Adobe Type 1 via ATM, TrueType) that are scaled,
  rotated, and sheared to any size by the rasterizer. Selected by setting `FATTR_FONTUSE_OUTLINE`
  in the requested attributes; drawn filled unless `FATTR_SEL_OUTLINE` requests hollow glyphs.

An application never names a *physical* font directly. It fills a **`FATTRS`** structure
describing what it wants (face name, size hints, style flags) and calls `GpiCreateLogFont`,
which binds a **logical font** to an `lcid`. The system matches the logical request against the
available physical fonts - those loaded at init, built into the device/driver, or loaded
privately by `GpiLoadFonts` - and **the chosen physical font is fixed at create time and never
re-chosen for that logical font** [DOC-IBM, `GpiCreateLogFont` Remarks].

The matching algorithm (paraphrased from the Remarks): if a face name is given, the system
seeks that face; if empty, a default is chosen. A non-zero `lMatch` requests one exact physical
font (device/driver-specific - discouraged for portability); on any mismatch the search restarts
as if `lMatch` were 0. With `lMatch` 0 and a *bit-map* request, the system searches image fonts
for the requested `lAveCharWidth` / `lMaxBaselineExt`, falling back to an outline font of the
face; with an *outline* request it searches outline fonts by the selection flags, falling back
to a default outline font. A positive `lMatch` selects a PM font, a negative one a device font
[DOC-IBM]. Because a printer or interchange target may substitute a device font, IBM advises
setting **every** field of `FATTRS`, and setting the character box / angle / shear
(`GpiSetCharBox` / `GpiSetCharAngle` / `GpiSetCharShear`) before drawing so a substituted vector
font renders as intended [DOC-IBM].

> **A face name in `FATTRS` is a HINT, and the return code cannot tell you it was ignored.**
> `GpiCreateLogFont` returns `FONT_MATCH` (2) or `FONT_DEFAULT` (1) - but `FONT_MATCH_NEAREST`
> is **also 2** [`pmgpi.h:346,350`], so "2" means *"matched or approximated"*, not *"you got the
> font you asked for"*. There is **no return value that distinguishes an exact match from a
> substitution.**
>
> This bites hardest with the built-in **image** faces (`System VIO`, `System Monospaced`).
> Requesting one by name while also setting `FATTR_FONTUSE_OUTLINE` cannot be satisfied - they
> have no scalable form - so the system silently substitutes a *scalable* font, returns 2, and
> every face the user picks renders as the same default. Nothing anywhere reports an error.
>
> **Pin the font instead of describing it.** Enumerate with `GpiQueryFonts` for the face name,
> then copy the `FONTMETRICS.lMatch` of the entry you want into `FATTRS.lMatch`: that asks for
> one specific physical font rather than "something like this". The same metrics record tells you
> which kind it is, which decides everything else:
>
> | | `fsDefn & FM_DEFN_OUTLINE` set | not set (image font) |
> |---|---|---|
> | `fsFontUse` | `FATTR_FONTUSE_OUTLINE \| FATTR_FONTUSE_TRANSFORMABLE` | **0** - never ask an image font for outline |
> | Size comes from | `GpiSetCharBox` (§2.5) | `FATTRS.lMaxBaselineExt` / `lAveCharWidth`, copied from the metrics |
> | Available sizes | any | only those it was drawn at - pick the nearest `sNominalPointSize`, **not** `lMaxBaselineExt`; see below |
>
> Applying a character box to an image font distorts the glyphs instead of scaling them, so the
> two columns are not interchangeable. Resolve once per face and cache it: the answer depends on
> the installed fonts, not on which presentation space is asking.
>
> [OBS-RE - diagnosed porting Scintilla to PM, where "System VIO" rendered as Courier through
> three successive fixes. Checking the return code was one of the fixes that did not work, because
> `FONT_MATCH == FONT_MATCH_NEAREST`.]

> **An image font exists only at the sizes it was drawn at, and `lMaxBaselineExt` is NOT monotonic
> in the point size** [OBS-RE]. Selecting one by converting points to pels and matching that field
> picks arbitrary instances. System VIO is the worked example - it ships the DOS text cells, normal
> and narrow, and enumerating it gives (nominal pt -> baseline x width):
>
> ```
>  2->12x5   3->16x5   4->10x6   5->14x6   6->15x7   7->25x7
>  8-> 8x8   9->10x8  10->12x8  11->14x8  12->16x8  13->18x8
> 14->18x10 15->16x12 16->20x12 17->22x12 18->30x12
> ```
>
> At 120 dpi a 5pt request converts to 8 pels and matches the **8pt** cell; 6pt converts to 10 and
> matches the **4pt** cell. One step in the size box changes the height and swaps a normal cell for
> a narrow one. Match on `FONTMETRICS.sNominalPointSize` instead - it is in **decipoints**, and "for
> a bit-map font, this field contains the height of the font" [DOC-IBM - `pm4.txt`].

> **Scintilla ports: `FontParameters.size` is whatever `Surface::DeviceHeightFont` returned**
> [OBS-RE]. Scintilla runs the point size through that method before building the `FontParameters`,
> so if your implementation converts points to pels - as the Win32 one does, and as any PM one
> wanting `GpiSetCharBox` will - then `fp.size` is a **device height in pels**, not points. Storing
> it in a field called `pointSize` and converting again is a silent 1.7x at 120 dpi. Name the field
> for what it holds.

### 2.2 `FATTRS` - the logical-font request [DOC-IBM - os2def.h:422]

```c
typedef struct _FATTRS {          /* fat */
   USHORT usRecordLength;         /* = sizeof(FATTRS) */
   USHORT fsSelection;            /* style: FATTR_SEL_* */
   LONG   lMatch;                 /* physical-font match number (0 = let system choose) */
   CHAR   szFacename[FACESIZE];   /* FACESIZE = 32; face name, e.g. "Helvetica" */
   USHORT idRegistry;             /* font registry identifier */
   USHORT usCodePage;             /* code page (0 = PS default) */
   LONG   lMaxBaselineExt;        /* requested height (image-font selection) */
   LONG   lAveCharWidth;          /* requested average width (image-font selection) */
   USHORT fsType;                 /* FATTR_TYPE_* */
   USHORT fsFontUse;              /* FATTR_FONTUSE_* */
} FATTRS;
```

`FACESIZE` is 32 [os2def.h:418]. Flag families [os2def.h:396-415]:

| Field | Constants |
|---|---|
| `fsSelection` | `FATTR_SEL_ITALIC` 0x0001, `_UNDERSCORE` 0x0002, `_OUTLINE` 0x0008 (hollow), `_STRIKEOUT` 0x0010, `_BOLD` 0x0020; the `_MUST_*` flags (0x0100/0x0200/0x0400) fail the call if color / mixed modes / hollow are unavailable |
| `fsType` | `FATTR_TYPE_KERNING` 0x0004, `_MBCS` 0x0008, `_DBCS` 0x0010, `_ANTIALIASED` 0x0020 |
| `fsFontUse` | `FATTR_FONTUSE_NOMIX` 0x0002, `_OUTLINE` 0x0004 (request an outline font), `_TRANSFORMABLE` 0x0008 |

### 2.3 `FONTMETRICS` - the measured description [DOC-IBM - os2def.h:532]

Returned by `GpiQueryFontMetrics` (current font) and `GpiQueryFonts` (one per matching physical
font). It is large; the key groups:

```c
typedef struct _FONTMETRICS {     /* fm */
   CHAR   szFamilyname[FACESIZE]; /* family, e.g. "Courier" */
   CHAR   szFacename[FACESIZE];   /* face,   e.g. "Courier Bold" */
   USHORT idRegistry; USHORT usCodePage;
   LONG   lEmHeight, lXHeight;
   LONG   lMaxAscender, lMaxDescender, lLowerCaseAscent, lLowerCaseDescent;
   LONG   lInternalLeading, lExternalLeading;
   LONG   lAveCharWidth, lMaxCharInc, lEmInc, lMaxBaselineExt;
   SHORT  sCharSlope, sInlineDir, sCharRot;
   USHORT usWeightClass, usWidthClass;
   SHORT  sXDeviceRes, sYDeviceRes;
   SHORT  sFirstChar, sLastChar, sDefaultChar, sBreakChar;
   SHORT  sNominalPointSize, sMinimumPointSize, sMaximumPointSize;
   USHORT fsType, fsDefn, fsSelection, fsCapabilities;
   LONG   lSubscript*, lSuperscript*;          /* sub/superscript size + offset */
   LONG   lUnderscoreSize, lUnderscorePosition;
   LONG   lStrikeoutSize, lStrikeoutPosition;
   SHORT  sKerningPairs, sFamilyClass;
   LONG   lMatch;                 /* match number to force this exact font */
   LONG   FamilyNameAtom, FaceNameAtom;
   PANOSE panose;                 /* 12-byte typographic classification [os2def.h:516] */
} FONTMETRICS;
```

Distinguishing image from outline is read from `fsDefn`: **`FM_DEFN_OUTLINE`** (0x0001) marks an
outline font; the character-set coverage bits (`FM_DEFN_LATIN1` 0x0010, `_CYRILLIC`, `_GREEK`, ...)
and the composite `FM_DEFN_UGL*` masks describe glyph coverage [os2def.h:449-470]. `fsType`
carries `FM_TYPE_FIXED` (0x0001, monospaced), `FM_TYPE_KERNING` (0x0004), `FM_TYPE_DBCS`/`_MBCS`,
`FM_TYPE_UNICODE` [os2def.h:438-447]. `fsSelection` mirrors the applied style
(`FM_SEL_ITALIC`/`_BOLD`/...), and `fsCapabilities` reports what the font cannot do
(`FM_CAP_NO_COLOR`, `FM_CAP_NO_HOLLOW`, ...) [os2def.h:472-511]. `lMatch` is the value to place in
`FATTRS.lMatch` to force exactly this physical font.

### 2.4 Font create / load / query surface [DOC-IBM - pmgpi.h]

| Symbol | Purpose |
|---|---|
| `GpiCreateLogFont(HPS, PSTR8 pName, LONG lLcid, PFATTRS)` | Create a logical font from `FATTRS`, bind to `lLcid`. Returns `FONT_DEFAULT` (1), `FONT_MATCH` (2), or `GPI_ERROR` on failure [pmgpi.h:1648, 1759]. **`FONT_MATCH_NEAREST` is also 2** [pmgpi.h:346], so a 2 does NOT mean the requested face was honoured - see the warning in section 2.1 and pin the font with `FATTRS.lMatch` |
| `GpiSetCharSet` / `GpiDeleteSetId` | Select / delete the font (section 1) |
| `GpiLoadFonts(HAB, PSZ file)` / `GpiUnloadFonts` | Load a private `.FON` font file for this process; `GpiLoadPublicFonts` / `GpiUnloadPublicFonts` make it system-wide [pmgpi.h:1771, 1844] |
| `GpiQueryFonts(HPS, ULONG flOptions, PSZ face, PLONG pReq, LONG cbMetrics, PFONTMETRICS)` | Enumerate physical fonts matching `face` (NULL = all); fill an array of `FONTMETRICS`. `flOptions`: `QF_PUBLIC` 0x0001, `QF_PRIVATE` 0x0002, `QF_NO_GENERIC` 0x0004, `QF_NO_DEVICE` 0x0008. Returns count; call with `*pReq` to size then to fill [pmgpi.h:1730-1734, 1791] |
| `GpiQueryFontMetrics(HPS, LONG cbMetrics, PFONTMETRICS)` | Metrics of the *currently selected* font [pmgpi.h:1799] |
| `GpiQueryLogicalFont(HPS, LONG lcid, PSTR8, PFATTRS, LONG)` | Recover the name + `FATTRS` a logical font was created from [pmgpi.h:1834] |
| `GpiQueryKerningPairs(HPS, LONG, PKERNINGPAIRS)` | Kerning table of the current font - array of `KERNINGPAIRS {sFirstChar, sSecondChar, lKerningAmount}` [pmgpi.h:1660, 1803] |
| `GpiQueryWidthTable(HPS, LONG first, LONG count, PLONG)` | Advance widths for a character range [pmgpi.h:1807] |
| `GpiQueryFaceString(HPS, PSZ family, PFACENAMEDESC, LONG, PSZ out)` | Build a compound face name from a family + `FACENAMEDESC` weight/width/style descriptor [pmgpi.h:1683, 1821] |
| `GpiQueryRasterizerCaps(PRASTERIZERCAPS)` | Report installed scalable-font engines: `RC_ATMAVAIL`/`RC_ATMENABLED` (1), `RC_TTAVAIL`/`RC_TTENABLED` (2) [pmgpi.h:1668-1680] |

The logical-font name (`pName`, type `PSTR8` - a pointer to an 8-character array, `CHAR[8]`
[os2def.h:327]) is an optional 8-char
AVIO/font name; most callers pass `NULL` and reference the font by `lcid` alone.

### 2.5 Text measurement and precise placement [DOC-IBM - pmgpi.h]

Drawing text is `GpiCharStringAt` (see `gpi-drawing.md`); the depth calls measure and place it.

- **`GpiQueryTextBox(HPS, LONG cChars, PCH str, LONG cPts, PPOINTL aptl)`** returns the
  parallelogram that would enclose the string, plus the concatenation point, in
  world coordinates relative to the start point. Fill `TXTBOX_COUNT` (5) points, indexed
  `TXTBOX_TOPLEFT`/`_BOTTOMLEFT`/`_TOPRIGHT`/`_BOTTOMRIGHT`/`_CONCAT` [pmgpi.h:1344-1351, 1510].
  The box height is the font's maximum height (descenders/accents included), **not** the height
  of the actual glyphs, and it does not equal the character box [DOC-IBM, Remarks]. Not valid
  when the drawing mode is *retain*.

- **`GpiCharStringPos(HPS, PRECTL, ULONG flOptions, LONG c, PCH str, PLONG adx)`** and
  `GpiCharStringPosAt` draw a string with per-character advance control (`adx` = increment array)
  and options `flOptions` [pmgpi.h:1180-1185, 1560]: `CHS_OPAQUE` 0x0001 (fill the background
  box), `CHS_VECTOR` 0x0002 (use the `adx` increments), `CHS_LEAVEPOS` 0x0008 (do not move
  current position), `CHS_CLIP` 0x0010 (clip to the supplied `PRECTL`), `CHS_UNDERSCORE` 0x0200,
  `CHS_STRIKEOUT` 0x0400. `GpiQueryCharStringPos` / `GpiQueryCharStringPosAt` return the
  positions each character *would* occupy without drawing [pmgpi.h:1489].

Character presentation attributes that affect both measurement and drawing - `GpiSetCharBox`
(size, `SIZEF` of `FIXED`), `GpiSetCharAngle` (baseline gradient), `GpiSetCharShear`,
`GpiSetCharDirection`, `GpiSetCharMode`, `GpiSetTextAlignment`, `GpiSetCharExtra` /
`GpiSetCharBreakExtra` (inter-character / break spacing, `FIXED`) - are all PS state
[pmgpi.h:1524-1595]. `FIXED` is a `LONG` with an implicit binary point between the 2nd and 3rd
hex digits (i.e. 1/65536 units) [os2def.h:309].

### 2.6 Drawing Unicode: a logical font in code page 1200 or 1208 [OBS-RE]

**The trap.** A program that holds text as Unicode and transcodes it to the 8-bit GPI code page
before drawing (`unicode-conversion.md` section 9.3) sees every character that page lacks come out
as a substitute, and concludes GPI cannot draw them. It can: ask for the logical font in a Unicode
code page.

**The fact.** Setting `FATTRS.usCodePage` (section 2.2) to **1200** (UCS-2, native byte order) or
**1208** (UTF-8) with a Unicode outline face, then drawing with `GpiCharStringAt`, rendered Greek,
Cyrillic, Japanese, `u`-umlaut, `e`-acute and the euro sign. Measured on Warp Server for e-business
4.5, 20-pel character box, next to a code-page-850 control row:

| Face, as `GpiQueryFonts` names it | 1200 | 1208 |
|---|---|---|
| `Times New Roman MT 30` | all drawn | all drawn |
| `Times New Roman WT J` | all drawn | all drawn |
| `Monotype Sans Duospace WT J` (fixed pitch) | all drawn | all drawn |
| `Monotype Sans WT` | Japanese left blank | Japanese left blank |
| `@Times New Roman WT J`, `@Monotype Sans Duospace WT J` | glyphs rotated - vertical-writing faces, not for horizontal text | same |

- `GpiCreateLogFont` returned 2 (`FONT_MATCH`, which is also the nearest-match value - see 2.1) and
  `GpiCharStringAt` succeeded for every row. `WinQueryCpList` on the same system listed both 1200
  and 1208.
- **Positions are per byte, and the byte layout matches a UTF-8 text engine.** In 1208,
  `GpiQueryCharStringPosAt` returned one entry per byte: a character's lead byte carries its start
  x and each continuation byte carries its end x. So text held as UTF-8 can be drawn and measured
  as-is, with none of the source-byte bookkeeping transcoding needs. In 1200 the same holds per
  two-byte code unit.
- **There is no fallback between faces.** A character the chosen face lacks is simply not drawn -
  no box, no substitute - which is what `Monotype Sans WT` did with Japanese.
- **`GpiSetCp(hps, 1200)` on the default font** (no logical font) also worked for Greek, Cyrillic
  and the euro sign; Japanese drew as boxes. The PS code page then applies to *every* later string,
  so an 8-bit label drawn afterwards came out as boxes too. Restore the previous code page.
- `\PSFONTS` on the measured system held `tnrwt_j.ttf`, `mtsans_w.ttf`, `mtsansdj.ttf` and
  `tnrmt30.cmb` alongside the Type 1 faces; which file supplies which of the faces above was not
  checked.

**How to verify.** Enumerate faces with `GpiQueryFonts(hps, QF_PUBLIC | QF_PRIVATE, NULL, ...)`,
create a logical font per candidate face with `usCodePage = 1208`, draw a UTF-8 string of known
non-Latin characters with `GpiCharStringAt`, take a screenshot, and log what
`GpiQueryCharStringPosAt` returns for the same bytes.

**The tell.** Accented or non-Latin text drawing as substitutes in a program that transcodes to the
GPI code page. Try a 1208 logical font in a Unicode face before deciding the platform cannot draw it.

**Not established** [unverified]: whether eComStation and ArcaOS install the same faces; whether
Type 1 or bitmap faces draw anything in 1208; and what `UNICODE.SYS` (loaded from `CONFIG.SYS` on
the measured system) contributes.

**DBCS code pages are per byte too** [DOC-IBM - *DBCS Design Guide and Information for OS/2*, os2books
`dbcs/os2dbcs`, topic *Character vs. Byte*]: with a mixed code page, a string's count is in bytes,
and the increment and position arrays of `GpiCharStringPos(At)` and `GpiQueryCharStringPos(At)`
have one element per byte. For a double-byte character only the first byte's element is meaningful;
IBM says the second byte's increment is ignored and its position is unknown. That differs from what
1208 returned above, where continuation bytes carried the character's end - do not assume one
behaviour from the other.

---

### 2.7 Which PM text goes through GPI - and which does not [OBS / OBS-RE]

**Trap:** assuming that intercepting the `Gpi*` text calls (a `PMGPI.DLL` replacement, or hooks on
its entries) sees all the text PM draws. It does not. PM has two front doors to text, and they meet
only at the engine's dispatch to the display driver (`GreCharStringPos`, dispatch `0x7036`).

Measured on Warp Server for e-business CP2 with one window drawing a distinct marker string
through each path, logged both by a `PMGPI` replacement and by a GRADD engine extension hooking the
text dispatch entries (`pmddim.h` numbers) [OBS]:

| Path | Reaches `PMGPI`? | Reaches the dispatch? |
|---|---|---|
| window title, menu bar, list box item | yes (`Gpi32CharStringPosAt`, `CHS_CLIP`, called from `PMMERGE`) | yes |
| an application's own `GpiCharStringAt` | yes | yes |
| WPS icon labels (container), multi-line edit control (both `PMCTLS`) | yes - the edit control with `CHS_VECTOR` and an increment array | yes |
| `WinDrawText` | **no** | yes |
| static text, push-button label, entry field | **no** (not even in fragments) | yes |
| push-button label *measurement* | **yes** (`QueryTextBox`) - measured through GPI, drawn around it | yes |

**The fact** [OBS-RE - decompile of WSeB `PMMERGE.DLL` with its `.SYM` names, plus a byte scan]:
outside GPI, every text draw in `PMMERGE` runs `WIN32DRAWTEXT` (reached from `PMWIN` ordinal 913)
or `WINDRAWTABBEDTEXT` -> an internal `DrawText` -> `OutputText`, the only `PMMERGE` function that
issues dispatch `0x7036`. The standard controls live inside `PMMERGE` and call those two exports
**from inside the module** - the push button and entry field `WIN32DRAWTEXT`, static text and group
boxes `WINDRAWTABBEDTEXT` - so no forwarder DLL can see them. The 16-bit half of `PMMERGE` has no
text path of its own: `WIN16DRAWTEXT` is a thunk into `WIN32DRAWTEXT`, and no 16-bit object
contains a text function code. Two measurement functions call the engine directly outside that
path (`EngGetTextExtent`, `QueryTabbedTextExtent32`); by their callers they look like seamless
Win-OS/2 support.

**Consequences:**
- A GPI-level text renderer misses most dialog text, and **must not change what `QueryTextBox`
  returns for text it does not also draw** - the push button would measure one way and draw another.
- The only single place all PM text meets is the engine dispatch. Covering the `Win*` path from above
  means patching `WIN32DRAWTEXT` and `WINDRAWTABBEDTEXT` themselves; in `PMMERGE` builds 14.057,
  14.084 (WSeB CP2), 14.103 and 14.106 (eComStation 2.1) they are ordinals 5163 and 5432 and their
  first instructions are identical and stack-relative only.

**How to verify:** draw marker strings through each path and log what arrives; in a decompile,
list the callers of `DrawText` and `OutputText`; scan the executable objects for the dispatch
function codes as `push`/`mov` immediates (`0x7036` draw, `0x5037` text box, `0x5038` character
positions), with the 32-bit object as the positive control.

**The tell:** a `Gpi*` interception that changes titles and menus but leaves dialog labels,
buttons and entry fields untouched.

## 3. Bitmaps

### 3.1 The bitmap model - handle, owning device, memory DC [DOC-IBM]

A bitmap is an off-screen raster owned by a device and referenced by an **`HBITMAP`**. Creating
one requires a PS associated with a DC that names the target *physical* device (any screen window
DC will do), because the bitmap's format belongs to that device [DOC-IBM, `GpiCreateBitmap`
Remarks]. To **draw into** a bitmap - or to use it as the source of most bitmap operations - it
must be **selected into a memory device context** with `GpiSetBitmap`; the memory DC is opened
with `DevOpenDC(..., OD_MEMORY, ...)` [pmdev.h:82] and given a PS. A bitmap is process-private:
it cannot be touched from another process and is auto-deleted at process exit [DOC-IBM]. Only one
memory DC may hold a given bitmap at a time; selecting a new bitmap returns the previously
selected handle [DOC-IBM, `GpiSetBitmap` Remarks].

```
GpiCreateBitmap / GpiLoadBitmap -> HBITMAP
        |
   GpiSetBitmap(hpsMem, hbm)  -- selects it into a memory DC's PS
        |
   draw with Gpi* into hpsMem, or read/write raw bits (GpiSet/QueryBitmapBits)
        |
   GpiWCBitBlt(hpsScreen, hbm, ...) -- blit the bitmap onto a window / device
```

### 3.2 `BITMAPINFOHEADER2` / `BITMAPINFO2` - bitmap parameterization [DOC-IBM - pmbitmap.h:119]

The 2.x ("info2") structures are the current form; the 1.x forms
(`BITMAPINFOHEADER` / `BITMAPINFO`, `cbFix` + `USHORT cx,cy,cPlanes,cBitCount` [pmbitmap.h:59-86])
are the compact legacy layout still accepted where a short header suffices.

```c
typedef struct _BITMAPINFOHEADER2 {  /* bmp2 */
   ULONG  cbFix;            /* = sizeof(BITMAPINFOHEADER2); how much of the struct is present */
   ULONG  cx, cy;           /* width, height in pels */
   USHORT cPlanes;          /* colour planes (usually 1) */
   USHORT cBitCount;        /* bits per pel: 1,4,8,16,24 */
   ULONG  ulCompression;    /* BCA_* */
   ULONG  cbImage;          /* size of the pel data in bytes */
   ULONG  cxResolution, cyResolution;   /* target device resolution (pels per usUnits) */
   ULONG  cclrUsed, cclrImportant;      /* palette size / significant colours */
   USHORT usUnits;          /* BRU_METRIC (0) = pels/metre */
   USHORT usReserved;
   USHORT usRecording;      /* BRA_BOTTOMUP (0): scan lines stored bottom-to-top */
   USHORT usRendering;      /* halftone algorithm: BRH_* */
   ULONG  cSize1, cSize2;   /* halftone parameters */
   ULONG  ulColorEncoding;  /* BCE_RGB (0) or BCE_PALETTE (-1) */
   ULONG  ulIdentifier;     /* application use */
} BITMAPINFOHEADER2;

typedef struct _BITMAPINFO2 {   /* bmi2 = header + trailing colour table */
   /* ...same fixed fields as BITMAPINFOHEADER2... */
   RGB2   argbColor[1];     /* palette: RGB2 {bBlue,bGreen,bRed,fcOptions} */
} BITMAPINFO2;
```

`ulCompression` values [pmbitmap.h:101-105]: `BCA_UNCOMP` 0, `BCA_RLE8` 1, `BCA_RLE4` 2,
`BCA_HUFFMAN1D` 3, `BCA_RLE24` 4. Standard uncompressed formats are 1/4/8/16/24-bit per pel; a
device may support others but the standard formats are the portable/convertible set [DOC-IBM].
`cbFix` is a versioning discriminant: a caller sets it to the size of the header form it filled,
so the engine reads only the fields present.

The on-disk `.BMP`/icon/pointer file layout wraps this: `BITMAPFILEHEADER2` = `{usType, cbSize,
xHotspot, yHotspot, offBits, BITMAPINFOHEADER2 bmp2}` [pmbitmap.h:199-207], with `usType` one of
the `BFT_*` signatures - `BFT_BMAP` 0x4D42 (`'BM'`), `BFT_ICON` 0x4349 (`'IC'`), `BFT_POINTER`
0x5450 (`'PT'`), `BFT_COLORICON`/`BFT_COLORPOINTER`, `BFT_BITMAPARRAY` 0x4142 (`'BA'`, a
multi-image container) [pmbitmap.h:226-231].

### 3.3 Bitmap create / load / transfer surface [DOC-IBM - pmgpi.h]

| Symbol | Purpose |
|---|---|
| `GpiCreateBitmap(HPS, PBITMAPINFOHEADER2, ULONG flOptions, PBYTE pInit, PBITMAPINFO2)` | Create an uninitialised (or, with `CBM_INIT` 0x0004, pre-filled) bitmap; returns `HBITMAP` or `GPI_ERROR` [pmgpi.h:1972, 1982] |
| `GpiLoadBitmap(HPS, HMODULE, ULONG idBitmap, LONG cx, LONG cy)` | Load a bitmap resource from a module (or executable); `cx/cy` request stretching to a size (0 = native) [pmgpi.h:1947] |
| `GpiSetBitmap(HPS, HBITMAP)` | Select a bitmap into a memory-DC PS; returns the previously selected handle, or `HBM_ERROR` (`(HBITMAP)-1`) on failure [pmgpi.h:1933, 1953] |
| `GpiDeleteBitmap(HBITMAP)` | Destroy a bitmap [pmgpi.h:1945] |
| `GpiWCBitBlt(HPS hpsTgt, HBITMAP src, LONG cPts, PPOINTL aptl, LONG lRop, ULONG flOptions)` | Blit from a bitmap **handle** (source need not be selected into a DC) to the target PS's device/bitmap, in target **world** coordinates [pmgpi.h:1956] |
| `GpiBitBlt(HPS hpsTgt, HPS hpsSrc, LONG cPts, PPOINTL aptl, LONG lRop, ULONG flOptions)` | Blit between two PSes (both bound to memory DCs / the device) in **device** coordinates [pmgpi.h:1938] |
| `GpiSetBitmapBits` / `GpiQueryBitmapBits` | Write/read raw pel data by scan-line range; return `BMB_ERROR` (-1) on failure [pmgpi.h:1975, 1988, 2001] |
| `GpiSetBitmapId(HPS, HBITMAP, LONG lcid)` / `GpiQueryBitmapHandle(HPS, LONG lcid)` | Give a bitmap a setid (for use as a pattern) and recover it [pmgpi.h:1997, 2010] |
| `GpiQueryBitmapInfoHeader(HBITMAP, PBITMAPINFOHEADER2)` / `GpiQueryBitmapParameters(HBITMAP, PBITMAPINFOHEADER)` | Read back a bitmap's dimensions/format (2.x / legacy header) [pmgpi.h:2013-2017] |
| `GpiQueryDeviceBitmapFormats(HPS, LONG, PLONG)` | List `(cPlanes, cBitCount)` pairs the device supports [pmgpi.h:2019] |
| `GpiDrawBits(HPS, PVOID bits, PBITMAPINFO2, LONG cPts, PPOINTL, LONG lRop, ULONG flOptions)` | Blit directly from an application memory buffer, no `HBITMAP` [pmgpi.h:2033] |

**Blt semantics** [DOC-IBM, `GpiWCBitBlt`/`GpiBitBlt` Remarks]: source and target DCs must be the
same physical device, which must support raster ops. Rectangles are given as point pairs in
`aptl` (`cPts` = 2 for a straight copy, 4 to specify source *and* target rectangles -> stretch /
compress). Source rectangles are noninclusive (left/lower in, right/upper out); the target of
`GpiWCBitBlt` is inclusive-inclusive. If the target rectangle differs in size, the image is
stretched or compressed; `flOptions` (`BBO_OR` 0, `BBO_AND` 1, `BBO_IGNORE` 2 - how eliminated
rows/columns are combined on compression; plus `BBO_PAL_COLORS` 4, `BBO_NO_COLOR_INFO` 8)
[pmgpi.h:1921-1926] controls the reduction. Rotation in the transform rotates the copy.
`lRop` is a **raster operation** combining source, pattern, and destination - `ROP_SRCCOPY`
0x00CC (plain copy), `ROP_SRCAND` 0x0088, `ROP_SRCPAINT` 0x00EE, `ROP_SRCINVERT` 0x0066,
`ROP_PATCOPY` 0x00F0, `ROP_DSTINVERT` 0x0055, `ROP_ONE`/`ROP_ZERO`, and the rest of the ternary
set [pmgpi.h:1904-1919]. Monochrome<->colour conversion uses the target PS's area foreground/
background colours (1-bits -> area colour, 0-bits -> background) - the only format conversion a blit
performs.

---

## 4. Metafiles

### 4.1 The metafile as a recorded order stream [DOC-IBM]

A **metafile** is a device-independent recording of GPI drawing orders - the sequence of
primitives, attribute changes, and resource definitions issued to a PS - that can be stored,
transported, and replayed onto any device later. It is *not* a raster snapshot; it is the
drawing *program*, so replay re-executes at the target device's resolution.

A metafile is created not by a dedicated "create" call but by aiming a **device context** at a
metafile recorder:

```
DevOpenDC(hab, OD_METAFILE, "*", ...)  -> HDC   (a recording DC)
GpiCreatePS / GpiAssociate               -- attach a PS; all Gpi* now records into the metafile
   ...draw...
DevCloseDC(hdc)                          -> HMF  (the finished metafile handle)
```

`DevOpenDC` type `OD_METAFILE` (7) records with full query support; `OD_METAFILE_NOQUERY` (9) is
a faster recorder that rejects query calls made against it [pmdev.h:81-83]. `DevCloseDC` returns
the **`HMF`** (metafile handle) instead of the usual boolean when closing a metafile DC
[pmdev.h:228]. There is no `GpiCreateMetaFile` function in the API - the recording DC *is* the
creation mechanism.

### 4.2 Playing and manipulating a metafile [DOC-IBM - pmgpi.h]

| Symbol | Purpose |
|---|---|
| `GpiPlayMetaFile(HPS, HMF, LONG cOpt, PLONG alOpt, PLONG pSegCount, LONG cDesc, PSZ pszDesc)` | Execute (replay) the metafile into a PS; `alOpt` is an option array controlling load/resolve behaviour; `pszDesc` receives the metafile's descriptor string [pmgpi.h:2280] |
| `GpiLoadMetaFile(HAB, PSZ file)` | Load a `.MET` file from disk into memory, returning an `HMF` [pmgpi.h:2272] |
| `GpiSaveMetaFile(HMF, PSZ file)` | Write a metafile handle to a disk file (consumes the handle) [pmgpi.h:2305] |
| `GpiCopyMetaFile(HMF)` | Duplicate a metafile handle (e.g. before a destructive play) [pmgpi.h:2267] |
| `GpiDeleteMetaFile(HMF)` | Free a metafile handle [pmgpi.h:2269] |
| `GpiQueryMetaFileLength(HMF)` / `GpiQueryMetaFileBits(HMF, LONG off, LONG len, PBYTE)` | Query size, then copy raw metafile bytes out (for embedding/transport) [pmgpi.h:2297, 2302] |
| `GpiSetMetaFileBits(HMF, LONG off, LONG len, PBYTE)` | Write raw bytes back into a metafile handle [pmgpi.h:2314] |
| `GpiResumePlay` / `GpiSuspendPlay(HPS)` | Suspend/resume playback (banded output) [pmgpi.h:2264] |

`GpiPlayMetaFile`'s **option array** (`alOpt`, indexed by the `PMF_*` constants
[pmgpi.h:2197-2208]) tunes replay:

| Index (`PMF_*`) | Controls (values) |
|---|---|
| `PMF_SEGBASE` (0) | Base segment identifier for retained segments |
| `PMF_LOADTYPE` (1) | `LT_DEFAULT` 0 / `LT_NOMODIFY` 1 / `LT_ORIGINALVIEW` 4 - how transforms are applied |
| `PMF_RESOLVE` (2) | `RS_DEFAULT` 0 / `RS_NODISCARD` 1 - name resolution |
| `PMF_LCIDS` (3) | `LC_DEFAULT` 0 / `LC_NOLOAD` 1 / `LC_LOADDISC` 3 - how the metafile's setids (fonts/bitmaps) are loaded/discarded |
| `PMF_RESET` (4) | `RES_DEFAULT` 0 / `RES_NORESET` 1 / `RES_RESET` 2 - reset the PS from the metafile's saved state |
| `PMF_SUPPRESS` (5) | `SUP_*` - suppress actual drawing (load resources only) |
| `PMF_COLORTABLES` (6) | `CTAB_*` - replace / keep the colour table |
| `PMF_COLORREALIZABLE` (7) | `CREA_*` - palette realization |
| `PMF_DEFAULTS` (8) | `DDEF_*` - treatment of default attributes |
| `PMF_DELETEOBJECTS` (9) | `DOBJ_*` - delete recorded objects after play |
| `PMF_PERPAGEINFOPTR` (12) | pointer to a `PERPAGEINFO` for multi-page play (a range/list of pages) [pmgpi.h:2214] |

Playback interacts with the PS drawing mode (`GpiSetDrawingMode`): with a *retain* mode, replayed
chained segments are appended to the segment chain (an error if a nonzero segment id collides); no
segment may be open across the call [DOC-IBM, `GpiPlayMetaFile` Remarks]. Because playback can
alter PS state, `GpiResetPS` beforehand (or the `RES_RESET` option) restores a clean space; the
`RES_RESET` option is itself invalid when the target PS is associated with a metafile DC
(`PMERR_INCOMPATIBLE_METAFILE`).

---

## 5. Common error codes [DOC-IBM - gpi book / pmerr.h]

Values seen across these subsystems (`WinGetLastError`):
`PMERR_INV_HPS` 0x207F, `PMERR_PS_BUSY` 0x20F4, `PMERR_INV_SETID` 0x20CA,
`PMERR_SETID_IN_USE` 0x2102, `PMERR_INV_FONT_ATTRS` 0x2072, `PMERR_FONT_NOT_LOADED` 0x202F,
`PMERR_KERNING_NOT_SUPPORTED` 0x20D5, `PMERR_INV_DC_TYPE` 0x2060,
`PMERR_INV_FOR_THIS_DC_TYPE` 0x2074, `PMERR_INV_METAFILE` 0x209D,
`PMERR_INCOMPATIBLE_METAFILE` 0x203B [DOC-IBM, GPI Reference error lists].

---

## 6. See also

- `gpi-drawing.md` - the DC/PS model, coordinate/transform pipeline, and core primitives
  (lines, areas, paths, `GpiCharStringAt`).
- `pm-graphics.md` - the internal engine (GRE / VMAN / presentation driver) that executes the
  orders a metafile records and the pels a blit moves.
- `printing-spooler.md` - the queued DC, where metafile-style device independence meets output.
