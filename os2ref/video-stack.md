# The OS/2 video stack - boot to Presentation Manager

How OS/2 owns the screen, from power-on text mode through the Presentation Manager's graphics
mode: which component owns the display at each boot stage, when text mode becomes an OS/2-managed
resource, what loads the video drivers (including the ones no CONFIG.SYS line names), how the
session manager orchestrates screen ownership between sessions, and precisely when - and by whom -
the hardware is switched from text to graphics.

How a display driver gets *installed* or switched in the first place - `DSPINSTL`/`RSPDSPI`, the
`.DSC`/`.DSP` package formats, and what a base-VGA versus GRADD install writes to `CONFIG.SYS` and
`OS2.INI` - is the companion doc `display-driver-install.md`.

Source tags: **[DOC-IBM]** = IBM DDK/Toolkit source or published IBM documentation;
**[OBS]** = a capture from a running system (a program is run, its returns recorded);
**[OBS-RE]** = observed by reverse engineering of the shipped binaries **or the kernel
debugger** (disassembly/decompilation
of `os2ldr`, `os2krnl` (WSeB CP2, SMP debug), `DOSCALL1.DLL`, `PMMERGE.DLL`, `TSHELL.EXE`,
`KBDBASE.SYS`, `BVHWNDW.DLL` - Warp 4.5 vintage with matched `.sym` files unless noted);
**[INF]** = inferred from the other two. Verified 2026-08-16 unless an earlier date is given.

---

## 0. The four ownership regimes, in one table

| Regime | Hardware mode | Who writes the screen | Ends when |
|---|---|---|---|
| **A. Firmware / loader** | BIOS text mode 3 (or the boot-logo graphics mode) | OS2LDR and the kernel's own init code, via BIOS INT 10h and direct port I/O | kernel init completes |
| **B. Kernel boot text** | text (logo restored to text on completion/failure) | kernel init code (~~driver-load messages,~~ Alt-F1 recovery screens) ~~- still BIOS-level output, *not* VIO~~ [2026-10-01: boot messages raised before `DOSCALL1.DLL` is loaded into SYSINIT are *queued*, not printed; the halt path alone writes through the kernel's own direct-to-screen writer. The first flush of the queue is printed through VIO, in SYSINIT, and is the first BVS use; `DEVICE=` driver messages come after it and so belong to regime C. section 4.2a; `config-and-environment.md`, "How a boot-time message is rendered". `[OBS-RE]` + `[OBS]`] | first BVS use [2026-10-01: in SYSINIT, at the kernel's first queued-message flush, before any `DEVICE=` driver - section 4.2a `[OBS]`] |
| **C. BVS text (VIO)** | text | the Base Video Subsystem (resident in `DOSCALL1.DLL`) through a chain of loaded Base Video Handlers (BVHs); per-session logical buffers, physical buffer owned by the foreground session's handler | a PM session's display driver sets a graphics mode - **which never happens if the shell is a VIO program** |
| **D. PM graphics** | graphics (driver-set) | the GRE->display-driver chain, every PM process writing its own mapped VRAM aperture | a full-screen session comes foreground (temporarily back to C via a real hardware mode switch), or shutdown |

The single most load-bearing fact in this table: **the text->graphics transition is not a boot
stage.** The kernel never puts the hardware in a graphics mode for the system proper (the boot
logo is a temporary, self-restoring exception). Graphics mode is set as a side effect of the first
PM process's display-driver bring-up - deep inside the first `WinCreateMsgQueue` of the boot
(section 7). A system whose `PROTSHELL=` is a VIO program (`CMD.EXE`, TSHELL) simply stays in regime C
forever; there is no latent "graphics init" that runs anyway. [OBS-RE section 7; corroborated by the
system running entirely in text with `PROTSHELL=` a 16-bit text shell, observed live on real
hardware/VM 2026-08-09/10.]

---

## 1. Regime A - OS2LDR, and the drivers no CONFIG.SYS line loads

### 1.1 What OS2LDR itself contributes

OS2LDR carries its own micro-FSD, reads `OS2KRNL` (and `OS2KRNLI` at install time, plus
`OS2LDR.MSG` for its own messages and `OS2DBCS.FNT` on DBCS systems) off the boot volume, and
prints its own diagnostics via BIOS services in the firmware's text mode. [OBS-RE: literal
filename strings in the `os2ldr` image at file offset ~0xC7C8; DBCS font co-located with them.]

**The "[four full blocks] OS/2" (CP437 0xDB x4) upper-left boot signature is OS2LDR's.** At file offset `0xC77D` in the SMP
loader (`0xCFE9` in the UNI build - again build-specific, anchor on the byte pattern) the loader
holds it as a **pre-attributed text-cell string** - char/attribute pairs ready to copy directly
into text video memory: `DB 07` x4 (four full-block characters, code 219, white-on-black), then
`20 07 4F 07 53 07 2F 07 32 07` (" OS/2"), `0xFF`-terminated. Its trap banner
("`OS/2 !! SYS00000`", offset 0xCB6) is a separate, plain string. [OBS-RE hexdump; no
equivalent cell string exists anywhere in the kernel's decompressed objects, so the corner
signature is loader-drawn. Corroborated by firsthand observation of real boots: the blocks +
"OS/2" appear top-left immediately, before any kernel output.]

### 1.2 The implicit base-driver lists - the lists are [OBS-RE] byte-exact; how they load is [INF]

**OS2LDR holds a list of base device drivers that no CONFIG.SYS line names.** In the
WSeB-vintage SMP loader (`os2ldr_smp`) two parallel lists sit at file offset `0xB236`, each entry
a null-terminated filename followed by a flag byte `0x01`, each list terminated by an extra NUL.
**The offsets are build-specific - the same lists are at `0xBAC6` in the UNI loader
(`os2ldr_uni`); only the byte *content* is identical between the two.** Anchor on the
`RESOURCE.SYS` string, never on the offset:

| List 1 (offset 0xB236) | List 2 (offset 0xB26D) |
|---|---|
| `RESOURCE.SYS` | `RESOURCE.SYS` |
| `CLOCK01.SYS`  | `CLOCK02.SYS`  |
| `SCREEN01.SYS` | `SCREEN02.SYS` |
| `KBDBASE.SYS`  | `KBDBASE.SYS`  |

Immediately after (offset 0xB2A4), a third list - lowercase, plain null-separated, double-NUL
terminated - names the **mandatory MVDM virtual device drivers**, likewise never present in
CONFIG.SYS: `vbios.sys, vdma.sys, vpic.sys, vflpy.sys, vtimer.sys, vlpt.sys, vkbd.sys, vdsk.sys,
vcmos.sys, vnpx.sys`. (Optional VDDs - `VSVGA.SYS`, `VMOUSE.SYS`, `VCOM.SYS` ... - are the ones a
CONFIG.SYS `DEVICE=` line names; this baseline set is not.)

Selection between list 1 and list 2 is by machine type: the `01` drivers serve ISA/AT-class
machines, the `02` drivers ABIOS (PS/2 MCA-class) machines. [INF from the pairing plus the
drivers' own source: `screen02.asm` implements the "Passthru to Video ABIOS" IOCtl
(`DevHlp_ABIOSCall`) that `screen01.asm` does not - [DOC-IBM] IBM DDK
`video/src/video/screendd/screen01.asm`/`screen02.asm`.] Machine-identification strings
(`EISA`, `COMPAQ`, ...) sit immediately before the lists in the same loader data region. [OBS-RE]

**How these files actually get loaded is NOT established - two mechanisms are in evidence, and
at least one driver clearly belongs to the second.** [INF, flagged rather than resolved
2026-08-16 after an adversarial review; an earlier revision asserted only model A.]

- **Model A** - OS2LDR (the only component with filesystem access this early) reads the files,
  and the kernel INITs them during its own initialization, *before* CONFIG.SYS's `BASEDEV=`/
  `DEVICE=` categories. Evidence: the filename lists are in the loader image and nowhere in the
  kernel (for three of the four).
- **Model B** - the drivers are entries in the kernel's own BASEDEV list, loaded by the traced
  BASEDEV machinery (`InitBaseList` -> `OrderBASEDEVs` -> `InitBASEDEVs` -> `BaseDevLoad`/
  `BaseDevInit`), ordered by the extension-priority table `.SNP.SYS.BID.VSD.TSD.ADD.I13.FLT.DMD`.
  Evidence: `RESOURCE.SYS` is a **`.SNP`-class BASEDEV - the earliest-loading class of all** -
  and its filename sits in the kernel's own data immediately after that priority table.
  Prior art on the priority table itself, cross-referenced 2026-08-29 because this doc reaches
  its conclusion through `OrderBASEDEVs` and did not say where that linkage is established:
  unpublished notes (2026-08-06) publishes the same
  bytes and traces `DS` there as `mov ax,0x47` -> LDT index 8 -> `DOSINITDATA`, caller chain
  `InitBaseDDs` -> `OrderBASEDEVs`. This doc's own reading of the string is independent
  ([OBS-RE], Sources below); the cross-reference is prior art, not this claim's provenance.

The two are not mutually exclusive and the honest reading is probably **both, per driver**:
`RESOURCE.SYS` fits model B on direct evidence, while `CLOCK0x`/`SCREEN0x`/`KBDBASE` appear only
in the loader. What is *observed* either way, and all this doc relies on downstream, is that the
devices these drivers register (`RESMGR$`/`CLOCK$`/`SCREEN$`/`SCREENDD$`/`KBD$`) exist before
CONFIG.SYS's own driver categories are processed. Settling A vs. B means tracing `InitBaseList`'s
population source - untraced.

| File | Device(s) | Role |
|---|---|---|
| `RESOURCE.SYS` | `RESMGR$` | Resource Manager (also named as a literal string inside `os2krnl` itself - [OBS-RE] kernel object 8) |
| `CLOCK0x.SYS` | `CLOCK$` | system clock; holds the GIS read/write selector via `GetDOSVar` |
| `SCREEN0x.SYS` | `SCREEN$` (one header; ~~`SCREENDD$`~~ corrected 2026-10-14: IBM's `bsedev.h` defines `SCREENDD_NAME` as `"SCREEN$"`, and `screen01.asm`/`screen02.asm` declare a single header) | physical-video-memory selector/mapping services + SVGA info/bank/linear-access + ABIOS mode-set passthrough (see section 3) |
| `KBDBASE.SYS` | `KBD$` | base keyboard driver: scan conversion, per-session KIBs, **and the session-switch hotkey classifier** (section 6.4) |

`KBD$`, `CLOCK$` and the BASEDEV extension-priority string `.SNP.SYS.BID.VSD.TSD.ADD.I13.FLT.DMD`
appear as literal strings in the kernel's own data (device-name level). Of the four base-driver
*filenames*, **only `RESOURCE.SYS` appears in `os2krnl`** (kernel object 8, beside the priority
table - the model-B evidence above); `CLOCK0x.SYS`/`SCREEN0x.SYS`/`KBDBASE.SYS` appear in the
loader image only. [OBS-RE: string scan of all decompressed kernel objects vs. the loader image.
An earlier revision generalized this to "no base-driver filename appears anywhere in `os2krnl`",
which its own table contradicted - corrected 2026-08-16.]

CONFIG.SYS *can* name related drivers on top of this baseline - e.g. `BASEDEV=IBMKBD.SYS` (the
keyboard adapter driver layered under `KBDBASE.SYS`) and `BASEDEV=PRINT01.SYS` are ordinary
CONFIG.SYS lines on a stock Warp 4.5 install - but `SCREEN0x`, `CLOCK0x`, `KBDBASE`,
`RESOURCE.SYS` themselves never are.

### 1.3 Early system DLLs

The base system DLL set - `DOSCALL1`, `MSG`, `NLS`, **`BVSCALLS`**, `BKSCALLS`, ... - is loaded
~~during kernel initialization~~, before CONFIG.SYS's driver categories complete and long before any
shell exists (the debug kernel prints each name in parentheses as it loads).
[2026-10-01: for `DOSCALL1` the loader is the SYSINIT process (pid 1), at ring 3: the kernel's
`syiGetLoadableEntries` issues an ordinary `DosLoadModule`/`DosGetProcAddr` for it before any
`DEVICE=` driver, and the loader runs the library's per-process
initialisation in SYSINIT. section 4.2a; `boot-sequence.md` Stage 5a. `[OBS-RE]`. When and by which
importer `MSG`, `NLS`, `BVSCALLS` and `BKSCALLS` load was not re-read; the parenthesised-name
observation cited here was not re-examined.] `BVSCALLS.DLL`
itself is a pure forwarder: the Base Video Subsystem's real code is inside `DOSCALL1.DLL` (section 4).
[OBS-RE: debug-kernel boot output; forwarder audit of `BVSCALLS.DLL`'s export table.]

---

## 2. Regime B - kernel boot video: the logo decision and Alt-F1

All of this stage's output is **BIOS-level** (INT 10h, direct port I/O), not VIO - the VIO/BVS
machinery of section 4 does not exist yet. [OBS-RE, full traces of the named functions in the WSeB SMP
debug kernel.]
[2026-10-01: the claim covers the routines traced here (`dologo`, Alt-F1). Ordinary boot
*messages* of this stage are not written at all: they are queued until SYSINIT has resolved
`DOSCALL1`, then printed through VIO (section 4.2a). The halt path writes through the kernel's own
direct-to-screen writer, `h_WrtToScrn`, whose mechanism was not read. `config-and-environment.md`,
"How a boot-time message is rendered". `[OBS-RE]`]

### 2.1 `dologo` - one global decides logo vs. text

A single kernel global, `dologo`, gates the graphical boot logo, set to 1 only if **two
independent checks both pass**:

- **Hardware gate - `h_syiSetVideoMode`**: saves the BIOS Data Area video state (current mode
  `0x40:0049`, columns/page, cursor shape, CRTC I/O base, equipment word, EGA/VGA rows/char
  height), then attempts a real mode change and verifies the adapter actually entered **BIOS
  mode `0x12` (640x480x16 VGA)**. The attempt is made only if the requested mode is a real
  EGA/VGA-class enhanced mode (`>6`, not the `0xFF` sentinel). Any failure -> `dologo = 0`.
- **File gate - `syiBlastLogo`**: opens the logo file; open failure **or** size < 32 bytes ->
  `syiBMPRestoreBIOSData()` (restore the saved BDA text state) and `dologo = 0`. Otherwise the
  logo is processed (`syiProcessLogoFile`, a 16->32 transition stub; the pixel-blit code itself is
  16-bit).

**The logo file's real format - SOLVED and decode-verified** (2026-08-16; supersedes an
earlier same-day "seven section offsets / not established" reading - that was a misparse of the
same header). The `\OS2LOGO` file (root of the boot drive, hidden+system+read-only, `.LGO` as a
distribution extension - [DOC], from the PMView/community documentation cited below; the kernel
trace never identified the filename, and the decoded artifact here came from install media, so
distribution extension) is **not** a BMP:

- **32-byte header = four `{offset:u32le, length:u32le}` pairs, one per EGA bit-plane**, planes
  stored back-to-back - pair 0's offset is always `0x20` (which is also why `syiBlastLogo`'s
  >=32-byte sanity check is what it is), and pair 3's `offset+length` equals the file size
  exactly.
- **Each plane is compressed with EXEPACK2 - the identical algorithm to LX ITERDATA2 page
  compression** (an LX-page decompressor decodes the planes unmodified).
- A decompressed plane is `WxH/8` bytes: **38400 = 640x480 (Warp 4 / WSeB)** - measured - or,
  per [DOC] only, **32000 = 640x400 on Warp 3** (no Warp 3 file was decoded; unverified). 16 colors, standard EGA palette (none stored in the file); plane order
  0-3 = blue, green, red, intensity.
- **The display mode is 640x480x16 (BIOS mode `0x12`) in both cases** - Warp 3's image is 40
  rows short because the bottom 80 scanlines are reserved for the copyright text, which is why
  the logo *image* is remembered as 640x400 while the hardware gate verifies mode `0x12`. Both
  recollections were right about different layers.

[OBS-RE: the shipped WSeB CP2 `\OS2LOGO` (28,060 bytes) parsed, all four planes
EXEPACK2-decompressed and composited with the standard EGA palette into a correct, visually
verified rendering of the WSeB boot logo at 640x480. Structure description corroborated by the
Just Solve the File Format Problem wiki ("OS/2 Boot Logo") and PMView's LGO documentation
(dimensions, EGA-16 reduction, the Warp-3 80-line copyright reservation).]

Cleanup is symmetric: `h_syiResetVideoMode` restores the saved state **only if** `dologo` was
set - if the logo never showed, the hardware was never touched and the function is a no-op. So
outside the logo window, the hardware sits in whatever text mode the firmware established, and
the system's "default" video state is *text, preserved*, not something the kernel constructs.

**Logo teardown is demand-driven, not scheduled** [OBS-USER, firsthand observation of real boots,
consistent with the traced no-op gate]: the logo (or, on a no-logo boot, the quiet
signature-only screen) stays up until *something needs to write text* - a driver's load/error
message, Alt-F2 verbose output, or a VIO shell's first output - at which point the saved text
state is restored (`h_syiResetVideoMode`'s caller was not identified in the trace; the
observable rule is "restore on first text-output demand"). On a PM boot with the logo showing,
the screen goes **directly from the logo's graphics mode to PM's driver-set mode** (section 7) with no
intermediate text, provided nothing needed to print first.

**Open**: firsthand recollection also holds that the *no-logo* boot text screen does not look
like a standard firmware text mode. The traced mechanism nominally preserves/restores the
firmware's own BDA state, but two inputs remain unresolved that could each explain a
non-default appearance: the "requested video mode" OS2LDR passes in `EBX` (source untraced),
and any kernel/CONFIG.SYS-time font load (`DEVINFO=SCR` / `VIOTBL.DCP`) replacing the glyph set
under the same mode number. ~~Not settled either way.~~

**SETTLED 2026-08-25 for the font half (Rule 1.7): a `DEVINFO=SCR` load DOES replace the glyph
set at the same mode number, and the change is large.** Measured `[OBS]` by decoding a shipped
`VIOTBL.DCP` and diffing its CP437 tables against the VGA BIOS ROM font: **42 of 256** glyphs
differ at 8x16, and **123 of 256** at 8x8. That is more than sufficient to explain a boot text
screen that does not look like a standard firmware text mode. The other input this paragraph
names - the video mode `OS2LDR` passes in `EBX` - remains untraced and is unaffected.
The file's format is `[DOC-IBM]`: `fontfilehdr`/`fonthdr` in
DDK `base/inc/fontfile.inc` (1986), with C equivalents at
DDK `video/src/video/vdh/vdh.h:971-996`; a shipped `VIOTBL.DCP` holds **22 code pages x 5
cell shapes = 106 font tables** (8x8, 8x14, 8x16 FULL; 9x14, 9x16 `PARTIAL|CODEPTS` overlays
naming a base font), which is exactly the set BVHVGA's `ExamineConfig` demands.

#### 2.1.1 The code-page font file (`.DCP`) in detail, and the two 8x8 lineages

*Added 2026-08-27. `[DOC-IBM]` for the layout, `[OBS]` for every measurement, taken by decoding
the font files a Warp 4.5 install ships and the 8x8 table the DDK ships.*

**Where the layout is documented.** `fontfilehdr`/`fonthdr` live in `fontfile.inc` (1986),
which the DDK ships in **two byte-identical copies** - under `base/inc/` and again under
`video/rel/os2c/include/base/os2/inc/`. Neither is more authoritative than the other; the point
worth keeping is that this file is the *only IBM source that documents the layout*, not that
only one copy of it exists. C equivalents (`FONTFILEHDR`/`FONTHDR`) are in the base video
handler's `vdh.h`.

**The record-size identity that validates a parse.** Given `fh_cellcols`, `fh_cellrows`,
`fh_numpoints` and `fh_flags`, a well-formed record satisfies

```
fh_datalen == fh_numpoints * (fh_cellrows + (fh_flags & CODEPTS ? 1 : 0))
```

Note the **one byte per row regardless of cell width**: a 9-dot cell (`9x14`, `9x16`) is stored
as 8-bit rows, because the 9th column is not stored at all - the hardware character generator
replicates column 8 for the line-drawing range. A parser that computes `(cols+7)/8` bytes per
row will reject every 9-dot record. `PARTIAL` records prefix each glyph with its own code-point
byte, which is what the `+1` accounts for; `fh_lowpoint`/`fh_highpoint` bound those code points
but do not enumerate them.

Applied to a shipped `\OS2\VIOTBL.DCP`, **104 of its 106 records satisfy that identity
exactly**. The two that do not are the same two in every copy examined, and each over-declares
`fh_datalen` by exactly one cell's worth: **CP852 8x14** declares 3598 where 256 glyphs need
3584, and **CP857 8x8** declares 2056 where they need 2048. Both records' 256 glyphs are
present and correctly strided; only the declared length is long. Treat it as an IBM data quirk,
not a parse failure - but do not *rely* on `fh_datalen` to bound a glyph walk.

**`VIOTBL.ISO` - a second, alternative code-page font file.** A Warp 4.5 install ships
`\OS2\VIOTBL.ISO` (230,105 bytes) alongside `\OS2\VIOTBL.DCP` (225,355 bytes, present twice
and byte-identical at `\OS2\` and `\OS2\BOOT\`). `VIOTBL.ISO` is a complete `.DCP` in the
same format - same header, same record layout - with **96 records over 21 code pages** against
the `.DCP`'s 106 over 22 (it lacks CP921 entirely and carries fewer 9-dot overlays).

What distinguishes it is narrower than its size suggests, and is the useful fact: comparing the
two record-for-record, **every 8x8 and every 8x14 table is byte-identical between the two
files**. All of the difference is in the **8x16** cell - the one a text shell actually uses -
where 15 of the 21 shared code pages carry a different table (CP437 differs in 198 of 256
glyphs; CP1004 in only 5). Rendered, the `.ISO` 8x16 is a **1-pixel-stroke face occupying all
eight columns**, against the `.DCP`'s 2-pixel strokes in seven columns with a right-hand gap.
So `VIOTBL.ISO` is best understood as *the same code-page font set with an alternative 8x16
display face*, not as a different character repertoire.

**NOT ESTABLISHED**: what selects it, or what the `.ISO` name denotes. No IBM prose in any
book, INF, redbook, DDK source or install script found names this file - every DDK `.DSP`
install script and every `DEVINFO=SCR` line found writes `VIOTBL.DCP`. It appears only in
install *manifests* (file lists) with no accompanying description. A plain-language reading is
that the thin-stroke face is an ISO-ergonomics (ISO 9241-class) alternative, but that is a
**guess with no source behind it** and should not be repeated as fact. Since `SetHWFont`'s
priority is USER > code page > ROM (section 4), whichever file `DEVINFO=SCR` names is a live input to
plane 2, so the selection rule is a real gap rather than a curiosity.

**The 8x8 font has two distinct lineages, and they are not interchangeable.** The code-page
lineage and the adapter-ROM lineage differ in **123 of 256** glyphs at 8x8:

| lineage | representative | agreement |
|---|---|---|
| **adapter ROM** | `_CGAFont` + `BldFont`, the 2048-byte 8x8 table the DDK ships in the base video handler's `vdhdata.inc` (change-tagged `@V2.0STJ26 B785343`, "Add unique code for CGA 8x8 fonts") | byte-identical to the 8x8 table in the SeaBIOS VGA BIOS `[OBS, third-party]` |
| **code page** | `VIOTBL.DCP` CP437 8x8 | differs from the Linux kernel's `lib/fonts/font_8x8.c` - itself generated by `cpi2fnt` from a DOS `.CPI` - in only **2 of 256** |

Two independent representatives inside each lineage agree; across lineages they differ by the
same 123.

**Negative result, recorded so the search is not repeated.** A content sweep of ~123,000 files /
~2.5 GB - the DDK, the Toolkit, a shipped Warp 4.5 install and three external OS/2 reference
corpora, searching raw bytes *and* assembler/C source text for character 1's ROM bit pattern -
found the `vdhdata.inc` 8x8 (both copies) and **no VGA ROM 8x16 and no VGA ROM 8x14 table in any
IBM artifact at all**. Those two ROM fonts are not recoverable from IBM's shipped source, only
from an adapter's own ROM image. Two false positives from that sweep, so they are not re-chased:
`\OS2\DLL\SYSFONT.DLL` (the PM system bitmap font) holds a 16-byte run matching character 1's
ROM 8x16 pattern but no ROM `A` and no ROM `0xB0` shade glyph - a coincidental glyph inside a
proportional font resource, not a table; and `\OS2\DLL\PMSPL.DLL` holds the 8-byte 8x8 pattern
with arbitrary bytes where character 0 would be.

**How `ExamineConfig` tells the three cell sizes apart**, since it keys entirely on character 1
and the three differ only in how the smiley's rows are padded (`vdhsubs.c`, the ROM scan):

| bytes at the first `7E` | classified as | base recorded |
|---|---|---|
| `7E 81 A5 81 BD ...` | 8x8 | `i-8` |
| `7E 81 A5 81 81 BD 99 81` and byte `i+8` != `0x81` | 8x14 | `i-16` |
| `7E 81 A5 81 81 BD 99 81` and byte `i+8` = `0x81` | 8x16 | `i-18` |

The 8x16 doubles two of the smiley's rows and the 8x14 doubles one, which is the whole
discriminator. Each slot latches on **first** match in scan order (`0xE0000` before `0xC0000`,
ascending within each), so a table that matches a wider size's signature and sits at a lower
address will capture that size's slot and starve its own. A missing 8x8, or a missing
8x14/9x14, is `INIT_ERROR`.

**What happens when the `DEVINFO=SCR` line names a file that cannot be opened - added
2026-09-08.** Nothing in this section runs at all, and **the adapter keeps the font it already
has**. The kernel's CONFIG.SYS processing opens a `DEVINFO=` file and immediately closes it - it
never reads a byte of a `.DCP` - so a failure is an open failure: **SYS1718** is queued, that one
`DEVINFO=` line is dropped, the CDIB's screen slot is left null, and **the boot continues**. It
does not halt, and it does not halt "before anything can render". IBM states the resulting
fallback `[DOC-IBM]` `cp3.txt`: the display *"defaults to the code page of ROM_0 for the device ...
the device native code page or the lowest addressed ROM code page"* - on a VGA, the ROM 8x16 font
already in plane 2, i.e. the adapter-ROM lineage tabulated above rather than the code-page lineage.
Full failure contract, including which NLS conditions *do* halt: `config-and-environment.md`,
"Boot-time NLS initialisation". The keyboard half of the same directive - the `KEYBOARD.DCP` file's
own layout, which is a different format from the `.DCP` described here - is `vio-kbd-mou.md` section 3.7.

**And when the line CAN be opened, who reads it - added 2026-09-09.** Not the kernel, and not a
device driver: **the base video handler reads its own font file.** `BVHVGA`'s `GETCODEPAGE`
attaches the CDIB by name through `DosGetShrSeg("\SHAREMEM\DOS\CDIB")`, follows
`CDIB_screen_ptr` -> `CDIB_dev_filename_ptr` to the ASCIIZ path the `DEVINFO=SCR` statement
supplied, and `DosOpen`s it. IBM ships the equivalent as source and the shipped handler matches it
operation for operation: `[DOC-IBM]`
DDK `video/src/video/vdh/vdhgetcp.asm` `_GetCodePage` (*"Get CodePage Fonts
from the Font File"*), with a near-identical copy in `.../vdh/idhinfo.asm` `GetCodePage` and a C
consumer in `.../svdh/bvhfont.c`.

**The asymmetry with the keyboard half is the design, and it is what a reimplementation must not
flatten.** That whole path issues **no `DosDevIOCtl` at all** - the handler is already the code
that owns the adapter, so it loads the glyphs into its own buffers and programs the character
generator itself. The keyboard half, by contrast, is read by `DOSCALL1` and must hand its table
across to a *driver* (`KBD$` category 4 function `0x5C`). Same statement, same structure, two
unrelated modules on two unrelated schedules - so a working code-page font implies nothing about
the keyboard table. Identification of `GETCODEPAGE` is `[INF]` (read out of the shipped handler,
corroborated by the IBM source above); the shared-segment name and the call sequence are
`[DOC-IBM]`. Both halves together: `config-and-environment.md`, "The CDIB".

> **CORRECTED 2026-09-11 - READING THE FILE AND PROGRAMMING THE GENERATOR ARE TWO
> SEPARATE ENTRY POINTS, AND LOADING THE HANDLER REACHES ONLY THE FIRST.** The
> paragraph above says `GETCODEPAGE` *"loads the glyphs into its own buffers and
> programs the character generator itself"*. The first half is right; the second
> conflates two steps, and the distinction decides whether a hosted handler shows
> the code-page glyphs or the ROM ones. Read out of the shipped `BVHVGA.DLL`
> (2001-09-10), every offset in object 2, `[OBS-RE]`:
>
> 1. **`GETCODEPAGE` (`+0x58EC`) has exactly ONE caller** - a near call at
>    `+0x011A`, inside **`DEVENABLE`** (`+0x0000`...`+0x0172`, `INITENV` follows),
>    which is the module's **only init export**: the entry table's twenty entries
>    are `DEVENABLE` (ord 13) ~~plus nineteen `ACCESS*`/`SET*` hardware accessors and
>    `_VideoHardware`~~. There is no `BVH_INIT` export and no `GETCODEPAGE` export.
>    [2026-10-01: twenty entries, but only **fifteen are named**: `DEVENABLE` (13), the
>    `ACCESS*` accessors, `SETMAPMASK`, `SET132`, `CHARFONTEND`, `_SetMach32TO60Hz` and
>    `_VideoHardware`; the other five are unnamed. `[OBS-RE]`, the shipped `BVHVGA.DLL`'s entry
>    table and resident-name table, read 2026-10-01. IBM's `vdhvga.def` lists the same family
>    of exports, `[DOC-IBM]` DDK `video/src/video/vdh/vdhvga.def`.]
>    `DEVENABLE` gates the call on a one-shot byte at DGROUP `+0xBC9` that it
>    clears, after `DosGetHugeShift` (#41), `GETSVGACONFIG` and `EXAMINECONFIG`,
>    and then calls it unconditionally on leaving the CVT-fill loop.
> 2. **`GETCODEPAGE` makes no internal call at all** and programs nothing: it
>    `DosAllocSeg`s a work buffer and two segments, reads the 8-byte
>    `fontfilehdr` and the `ffh_numfonts` pointer array, and `DosReallocSeg`-grows
>    an **18-byte-per-font directory** and a font-data segment - one record per
>    (code page x cell shape) it accepts, holding `{CodePageID, BaseRows,
>    BaseColumns, far FontPTR, ...}` at `+0x00/+0x02/+0x04/+0x06`. That is the
>    `RomCP_tbl[]` section 4's `bvhfont.c` note names.
> 3. **The plane-2 download is a different path**: `INITENV` (**CVT 257**) calls
>    `FINDFONT` (`+0x4918`) at `+0x02A3` and `SETHWMODE` (`+0x2542`) at `+0x02B7`;
>    `SETHWMODE` calls `SETHWFONT` (`+0x457A`) at `+0x2C9B`; `SETHWFONT` calls
>    `_AccessFont` (`+0x57F2`) at `+0x47CA`. `SETMODE` (**CVT 269**) reaches the
>    same two, and `SETCURRENTFONT` (**CVT 267**) reaches `SETHWFONT` directly.
>    `SETMODE`, `SETCURRENTFONT` and `GETCURRENTFONT` have **no internal caller** -
>    they are CVT-dispatched only.
>
> **So `DEVENABLE` alone loads the file and changes nothing on screen.** The glyphs
> move only when something dispatches CVT 257 / 267 / 269. A host that registers
> the CVT and never calls through it gets a complete `.DCP` parse and the ROM font
> still on the screen - and no count of bytes opened or fonts parsed can tell the
> two apart.
>
> **Which is observable, and the signature is worth keeping because the obvious
> ones do not work.** `[OBS]`, one boot pair on a 720x400 9x16 text mode, measured
> 2026-09-11 against a shipped `VIOTBL.DCP` (225,355 bytes): after
> `INITENV(Flags=UPDATE_HARDWARE)` plane 2 holds the **CP437 8x16 base with its
> 9x16 `PARTIAL|CODEPTS` overlay applied over it**, and `crc32` of the 4096-byte
> 8x16 region is `0xE971EA75`. (`[INF]` for *why* the overlay is the one chosen:
> `FindCPFont`'s documented `(PelRows, PelColumns, CodePageID)` selection in section 4
> makes the 9-dot cell the discriminator. `FINDFONT`'s body was not read, so that
> is reasoning over the measurement and the signature, not an observation.) With the `DEVINFO=SCR` statement absent the same region
> reads `0xF2BDE6D2`, the unmodified ROM table, and the CDIB's screen pointer is
> `0x0000`. What does **not** discriminate: **character 0x01 is byte-identical in
> the ROM and code-page 8x16 tables**, so a smiley-pattern probe reports success in
> both arms; and the non-zero byte counts over the 8 KB window are **2326 (ROM) vs
> 2322 (code page)**, four bytes apart in ~2300. A presence check is a well-formed
> answer to a question it has no standing on - diff the glyphs, or take the CRC.
>
> > **PROVENANCE CORRECTED 2026-09-11 (Rule 1.7; `[OBS]` kept, its SCOPE narrowed).
> > THE BLOCK ABOVE IS KEPT ENTIRELY, ITS NUMBERS ARE REAL, AND THE PART THAT IS
> > WRONG IS THE FIVE WORDS *"one boot pair"*.** The two arms were not boots. Each
> > was produced by **dispatching CVT 257 directly from a harness**, against a
> > handler brought up by an equally direct `DEVENABLE` on a scratch device slot -
> > a sequence no system performs, since `DEVENABLE` is reached from `BVSDINIT` by
> > way of `DOSLOADVIDEOHANDLER`, and CVT 257 is reached by a session dispatching
> > through the published call table. That harness has since been withdrawn, so
> > the two figures are not currently reproducible by re-running anything; they
> > are reproducible by repeating the direct dispatch.
> >
> > **What that costs this entry, precisely.** The CRCs remain captures of IBM's
> > own handler executing IBM's own `INITENV`, so they are sound as the answer to
> > *"what does this handler write into plane 2 when something dispatches CVT
> > 257"* - which is the question section 3 above asks and the only question they are
> > cited for. They are **not** an answer to *"what does a booted system's plane 2
> > hold"*, and they are **not** evidence that a `DEVINFO=SCR` statement has taken
> > effect on a screen. `[OBS]`'s one-build-one-configuration caveat therefore has
> > to be read as covering the **invocation** as well as the machine: the
> > configuration these were taken in included a caller that does not exist.
> >
> > **The paragraph they support is unaffected, and is sharpened rather than
> > weakened by this.** `DEVENABLE` alone loads the file and changes nothing on
> > screen; the glyphs move only when something dispatches CVT 257 / 267 / 269.
> > A measurement obtained by performing that dispatch by hand is exactly how one
> > would demonstrate the *second* half of that sentence, and it does nothing to
> > establish that any particular system performs it.
> >
> > **The non-discriminators in the three lines above survive untouched, and are
> > the most reusable thing in this entry** - character 0x01 being byte-identical
> > in both lineages, and the 2326-vs-2322 non-zero byte counts - because they are
> > facts about the two font tables, established by comparing the tables. No
> > invocation of anything was needed to establish them, so no defect in an
> > invocation can undermine them.

### 2.2 Alt-F1 and the boot-key cluster

At a fixed early-boot point the kernel decodes a key code (read through the loader-provided I/O
primitives) against five recognized values (`'h'`/`'i'`/`'j'`/`'k'`/`'l'` -> bit patterns in the
flag bytes at kernel data `0xD93`/`0xD91` - a 5-way alternate-boot selector, of which **Alt-F1 is
the `'h'`/bit-`0x1` case**). Its handler, `syiProcessALTF1File`, is a genuine BIOS-level
text-mode loop: INT 10h to display recovery-choice text, INT 16h/15h keyboard poll with a real
countdown that times out as if ESC were pressed, and a PC-speaker beep via port `0x61`. This -
not VIO - is the mechanism behind the text-mode recovery/driver-message screens; it runs
*instead of*, and independently from, the `dologo` path.

Verbose driver-load output (Alt-F2 and the `ALTF2ON.$$$` flag file) belongs to the same
boot-message regime - kernel text output during `BASEDEV=`/`DEVICE=` processing. [INF that it
uses the same BIOS-level path: extrapolated from the Alt-F1 handler, which is the only
boot-message routine actually traced; the kernel's own `SYIDisplayMessage`/`SYISaveMessage`
were not read.]
[2026-10-01: the extrapolation fails for the kernel's ordinary messages. A message raised before
SYSINIT resolves `DOSCALL1` is queued, not printed; from the first flush on, SYSINIT prints through
`syiDisplayMessageR3` -> `DosPutMessage` -> `DosWrite` -> `VioWrtTTY`, i.e. through VIO and BVS.
`[OBS]`: WSeB 4.50 Rev 14.089 HStrict SMP debug kernel, 2026-10-01, kernel-debugger breakpoints on
`VIOWRTTTY`/`DOSPUTMESSAGE`/`BVSMAIN` over two boots (section 4.2a). So a kernel message printed at or
after the first flush does not use a BIOS-level path. Which routine prints the Alt-F2 per-driver lines, and whether they too
go through `syiDisplayMessageR3`, was not read.]

---

## 3. The screen driver: `SCREEN01/02.SYS` (`SCREEN$` / `SCREENDD$`)

*(2026-10-14: "SCREENDD" is IBM's name for this driver, not a second device name. The one device it
registers is `SCREEN$`: DDK `bsedev.h` defines `SCREENDD_NAME` as `"SCREEN$"`, and `screen01.asm`
declares a single header. Where this section writes `SCREENDD$`, read it as `SCREEN$`.)*

One driver, two IOCtl categories ([DOC-IBM] IBM DDK `video/src/video/screendd/` - full breakdown
with the vendor bank tables, `DevHlp_VMProcessToGlobal` global-access mechanism, and the ABIOS
passthrough in a dedicated reference; summary here for stack position only):

- **Category 3 (`SCREEN$`)** - selector allocation onto *physical* video memory
  (`DevHlp_PhysToUVirt`), plus function `0x74`: **passthrough to Video ABIOS**
  (`DevHlp_ABIOSCall`, implemented in `screen02.asm`) ~~- the real low-level mode-set mechanism.~~
  OS/2 does not implement CRTC/sequencer programming in this driver~~; it delegates to the
  machine's ABIOS/video BIOS~~.
  [2026-10-01: function `0x74` is the ABIOS passthrough only in `SCREEN02` (the ABIOS-machine
  driver); in `SCREEN01` the same number is *"Allocate a Selector:Offset"* (`[DOC-IBM]` both
  files' function headers). And the register programming is not delegated to firmware: it is in
  the base video handler, which exports IOPL hardware entry points (`ACCESSHARDWARE`,
  `ACCESSREGISTER`, `SETMAPMASK`, ... - `[DOC-IBM]` `vdh/vdhvga.def`) and loads its own mode and
  font registers (`SETHWMODE` -> `SETHWFONT`, section 2.1.1). `[DOC-IBM]` + `[OBS-RE]`]
- **Category 0x80 (`SCREENDD$`)** - the SVGA extension: chipset/VRAM identification, bank
  switching through per-vendor tables, `GetLinearAccess` (linear mapping of a physical range -
  the preferred, no-banking path), `GetGlobalAccess`/`FreeGlobalAccess`
  (`DevHlp_VMProcessToGlobal` - the primitive behind per-process apertures onto one physical
  VRAM), and APM/ring-0 callback plumbing. `VIDEOPMI` (section 7) is a *client* of this driver
  ("called from VIDEOPMI" - the driver's own source comment at `WaitForAPMCalls`).

The driver is **passive**: it has no session-switch notification (no Cat-0x0B `SGControl`, unlike
`KBD$`/`MOUSE$`) and no mode-*setting* logic of its own beyond the ABIOS passthrough - it is
driven top-down by the BVS/session-manager orchestration (section 6) and by VIDEOPMI. [DOC-IBM, direct
read of `screen01.asm`/`screen02.asm` dispatch.]

[2026-10-01, added: `SCREEN$`'s device header carries only the console-*output* attribute bit
(`DEV_COUT`; `[DOC-IBM]` `screen01.asm` header). The kernel's character-device write and read
paths test that bit per direction, not the device's identity: a `DosWrite` on a handle opened to
`SCREEN$` is diverted to VIO (`VioWrtTTY`), while a `DosRead` on it reaches the driver's strategy
routine. `KBD$` is the mirror image (`DEV_CIN` only: reads diverted to the keyboard subsystem,
writes to its strategy). `[OBS-RE]`, the Warp 4.5 kernel 14.104a's `WriteDev`/`ReadDev`/`FillDeviceSFT`;
what the two strategy routines return for those commands was not read.]

---

### 3.1 One video memory, several apertures

The adapter has **one** video memory. Everything a driver or program touches is a *view* onto
it, and OS/2 provides four:

| view | mechanism | primary user |
|---|---|---|
| the `A0000-BFFFF` real-mode aperture | the VGA/EGA window: planar addressing through the sequencer/graphics-controller latches, plus a **bank register** when VRAM exceeds the window | full-screen VIO handlers, `VioGetPhysBuf` callers, VDMs |
| a linear aperture | `SCREENDD$` `GetLinearAccess` (fn 0x0B) - linear mapping of a physical range, which is the path that avoids bank switching; PM reaches it as `VHMapVRAM` | the PM display-driver chain |
| a ring-3 16:16 selector onto a physical range | `SCREEN$` category 3, `DevHlp_PhysToUVirt` | anything needing a far pointer at video memory |
| a per-process aperture | `SCREENDD$` `GetGlobalAccess`/`FreeGlobalAccess` = `DevHlp_VMProcessToGlobal` | each PM process's own mapping onto the one VRAM |

[DOC-IBM] IBM DDK `video/src/video/screendd/`: the category-0x80 function numbers
(`GetLinearAccess` 0x0B, `GetGlobalAccess` 0x0C, `FreeGlobalAccess` 0x0D) at
`svgarout.asm:272-274`; `DevHlp_PhysToUVirt` on the category-3 path at `screen01.asm:250,315`
and `screen02.asm:297,362`; the per-vendor bank tables in `svgabank.asm`. The
`DevHlp_VMProcessToGlobal` characterization is the driver's own. `VHMapVRAM` as PM's route to
the linear aperture: DDK `GRADD/00067`.

**The `DevHlp_PhysToUVirt` selector:offset contract** (the category-3 view above), because it is
easy to assume the returned selector is based *at* the requested physical address. It is not, in
general: the base is aligned **down to a 4KB boundary** and the returned **offset = `phys & 0xFFF`**
- "if the input physical address is not on a 4KB boundary, the length of the result segment is
limited to 64KB minus the offset from 4KB" ([DOC-IBM] IBM DDK `HTML/REF/PDD/00259.HTM`, PhysToUVirt
Remarks; the SCREEN$ ring-3 exposure via `DosDevIOCtl` category 3 functions `0x75`/`0x76` returns
the pair as `{offset@+0, selector@+2}`, [DOC-IBM] `video/src/video/screendd/screen01.asm`). For a
4KB-aligned physical address - which every standard VGA aperture base is (`0xA0000`, `0xB0000`,
`0xB8000`) - this reduces to base-at-phys, offset 0. Measured on real OS/2 to confirm both halves
([OBS], Warp Server for e-business Convenience Package, syslevel XR04503, via a ring-3
`DosDevIOCtl(SCREEN$, cat 3, fn 0x75/0x76)`): `0xB8000` and `0xA0000` each return **offset 0**,
while a deliberately unaligned `0xB8010` returns **offset `0x10` = `phys & 0xFFF`**. The selector
value itself is a runtime-allocated LDT selector (TI=1, RPL=3) and is neither fixed nor meaningful
across calls. A caller that writes from the returned selector at **its own offset 0** (as a
full-screen BVH's `WriteCharStr` does - it stores at `PVB_Sel : PVBOff`, where `PVBOff` is a 0-based
cell offset and the selector's own returned offset is not added back in) therefore relies on the
aperture base being 4KB-aligned, which the text/graphics buffer bases always are.

> **CORRECTED 2026-08-28 (Rule 1.7) - the BASE half of the paragraph above is `[INF]`, not
> established.** The paragraph is kept whole, including *"base-at-phys, offset 0"*, because it is
> the natural reading of the two cited sources and the next reader will arrive at it too. Split it
> in two:
>
> - **The OFFSET contract and the LENGTH limit stand unchanged.** `offset = phys & 0xFFF`, and a
>   result segment starting off a 4KB boundary is limited to 64KB minus that offset: `[DOC-IBM]`
>   from the PhysToUVirt Remarks quoted above, and separately ~~`[OBS-RE]`~~-confirmed by the
>   `0xB8000`/`0xA0000`/`0xB8010` measurement. [2026-10-01: that measurement is `[OBS]` - a ring-3
>   `DosDevIOCtl` run and its returns recorded, as the paragraph above tags it; `[OBS-RE]` is for
>   a reading of a binary or the debugger.]
> - **That the descriptor's linear BASE equals `phys & ~0xFFF` is inferred from those two, not
>   stated by either.** The Remarks constrain the segment's *length* and imply its *offset*; they
>   say nothing about where the kernel puts the base. And the measurement cannot settle it: the
>   probe read the `{offset, selector}` pair a ring-3 `DosDevIOCtl` hands back, and a descriptor's
>   base is not visible from ring 3 that way - it would take a separate read of the LDT entry.
>
> **What the documented contract does require is weaker: "give me a physical range, receive a
> selector."** Identity between the base and the physical address is not part of it, and OS/2's
> other per-process aperture primitive documents the opposite shape - `VMGlobalToProcess` takes the
> address to be mapped in `EBX` and returns a *kernel-chosen* process linear address in `EAX`
> ([DOC] `kernel-services.md`, Memory/selector table), the same shape the PM display chain sees as
> `INITPROCOUT.ulVRAMVirt`, a virtual address handed back to the caller (`pm-graphics.md`). So
> assuming identity as a general rule is at minimum inconsistent with the primitive next door.
>
> **Not overclaimed:** this does **not** establish that the base differs from the physical address
> on real OS/2. The identity reading is *unproven, not refuted* - and it is unobservable to the
> only kind of caller the contract contemplates, since a caller writing at the returned selector's
> own offset 0 reaches the requested page whatever the base is. Settling it needs a ring-0 or
> kernel-debugger read of the returned selector's LDT descriptor base on a real machine, against a
> known physical address. Recorded so the question is not re-derived (Rule 1.6).

**No-banking wording, corrected 2026-08-22 (Rule 1.7):** an earlier revision of this section put
*"the preferred, no-banking path"* in quotation marks under this `[DOC-IBM]` tag. That string
does not occur anywhere in `screendd/` - `preferred` occurs nowhere in that directory - so the
quotes asserted verbatim IBM text that does not exist. The substance is sound and follows from
the function set above; only the quotation was wrong. Searched, absent: recorded so nobody
re-hunts for the sentence.

Three consequences that are easy to miss, and that a reader coming from a flat-framebuffer model
will get wrong:

- **Per-process apertures are not per-process memory.** `VMProcessToGlobal` exists precisely to
  give N processes N *mappings* of one physical VRAM. Every PM process writing "its own mapped
  VRAM aperture" (section 5) is writing the same bytes; the mapping is per-process, the memory is not.
- **The aperture is a window, not the memory.** Bank switching is only meaningful because VRAM is
  larger than the window it is seen through - so aperture size and VRAM size are different
  quantities, and `GetLinearAccess` exists to escape the distinction.
- **The displayed image is not always *in* video memory.** In a linear graphics mode it is: the
  CRTC scans out the same bytes the driver wrote, which is why a linear framebuffer feels like
  "the screen". In a text mode video memory holds *cells and a font*, and the displayed image is
  **generated** by the character generator as the CRTC scans - it is never stored anywhere. In a
  paletted mode the stored bytes are indices and the RAMDAC transforms them at scan time. Video
  memory and the displayed image coincide in one family of modes and in no others.

---

## 4. Regime C - BVS: when text mode becomes an OS/2-managed resource

### 4.1 Where BVS lives and how a VIO call reaches it

The **Base Video Subsystem** is resident in **`DOSCALL1.DLL`** (16-bit object 4).
`VIOCALLS.DLL` (all ~75 `Vio*` entries), `BVSCALLS.DLL`, `AVIOCALLS` and friends are pure
forwarders into DOSCALLS ordinals; the implementations dispatch through
`AllVDH` (DOSCALL1 obj4+0x1C12 [2026-10-01: `AllVDH` begins at obj4+0x1BAD per the matched
`.sym`; `+0x1C12` is its `lds` instruction, and the far call is at `+0x1C1D`. `[OBS-RE]`]):
function number - 0x100, x4, then a **16:16 far call through
the session's Call Vector Table (CVT)** - `lds bx,[bx+0x360]; sub di,0x100; shl di,2;
call far [bx+di]`. The CVT slots are far pointers into whichever Base Video Handler owns that
function for that session. The BVS dispatcher itself is exported as `DOSCALLS.#845 = BVSMAIN`
(with `#846 BVSREDRAWSIZE`, `#847 BVSGETPTRDRAWNAME`). [OBS-RE, disassembly of the shipped
`DOSCALL1.DLL` + entry-table resolution.]

> **NARROWED 2026-08-27 (Rule 1.7): "the session's Call Vector Table" is the wrong noun, and it
> is the kind of wrong that misleads.** A CVT is not per session. It is **per video device** -
> sixteen of them, system-wide (`bvsgCallTables dd 16 dup (0) ;Allow for WDH and 15 real
> devices`) - and a session holds only a two-byte *index* into that array. The dispatch quoted
> above says so once you know what its operands are: `bx` arrives as `[BVSCB+0x12]`, the
> session's device slot, and `0x360` is the offset of `bvsgCallTables` itself within the BVS
> global segment. The sentence is behaviourally true - the handler reached *is* the one that
> owns that function for that session - but read as ownership it invites "one CVT per session"
> or "one CVT re-registered on every switch", and OS/2 does neither. See section 4.4a.

Control-block layouts for this layer (BVSCB, console areas, the parameter blocks) are IBM-defined:
[DOC-IBM] IBM DDK `base/inc/bvscb.inc`, `bvsequ.inc`, `bvsparms.inc`.

### 4.2 Initialization is lazy - the first BVS call, not a boot stage

`BVSMAIN` opens by testing a byte at DOSCALL1 shared data `0x9817:0AA9`; if clear it calls
**`BVSDINIT`**, which runs `BVSGLOBALINIT` and then loads video handlers (section 4.3). **So "text mode
is initialized" - in the sense of VIO being a live, handler-backed OS/2 service - happens at the
first VIO/BVS call in the system**, whoever makes it, not at a fixed boot stage. Until that
moment the screen still holds whatever regime B left (the kernel's boot text), and ~~nothing about
the *hardware* changes at BVS init - BVS adopts the text mode already in effect;~~ its job is
management (logical buffers, per-session state, fonts, save/restore), not a mode change.
[2026-10-01: the first BVS transaction of a boot *does* include a mode set. The first
`VioWrtTTY` in a process whose screen group is 0, while the latch `SYIsetmodefl` (BVS global
segment `+0x118`) still holds its image value `0xFFFF`, sets the latch to 1 and calls `VioSetMode`
with a static `VIOMODEINFO` (80x25, colour text, 16 colours), then `DosGetCp` and `VioSetCp`, before
writing. On the SMP boot of section 4.2a this is the SYSINIT process's first message, and that write's
`BVSDINIT` entries carry function codes `0x24`, `0x08` (`VioSetMode`), `0x24`, `0x11`. `[OBS-RE]` `DOSCALL1` obj4
`VIOWRTTTY` +0x3BF7..+0x3C46 and the `VIOMODEINFO` at obj7 +0x110, read 2026-10-01; `[OBS]` section 4.2a.
Whether the handler's `SetMode` then reprograms the adapter registers on that call was not read or
observed.]

**`0x0AA9` is NOT a general one-shot latch - it is the "windowed VDH is loaded" flag**
(CORRECTED 2026-08-16 after an adversarial review caught an earlier revision of this section
calling it one; the wrong reading is kept here because the correct mechanism is easy to
misread the same way). `BVSDINIT` writes it in exactly one place: **inside the `param_1 == 0x44`
windowed branch, and only on success**; the `else`/type-3 (full-screen) branch never sets it, and
`ULOADWINTHORNVDH` reads it as its own already-loaded guard. Consequences that matter:

[2026-10-01: IBM's own name for the byte, in the matched `.sym`, is **`FSHELLINITED`**, and
`0x44` is **`vf_ShellInit`** (`vf_ShellInit equ 44h ;68 = VioShellInit`, `[DOC-IBM]` DDK
`base/inc/bvsparms.inc`). The function code reaches `BVSDINIT` as `BVSMAIN`'s `[bp+0x50]`, which is
`ParmList`'s `p_viofunc` - the VIO function code of the call that triggered it (`[DOC-IBM]`
`bvsparms.inc` `ParmList STRUC`; `[OBS-RE]` `BVSMAIN` +0x1866). `vf_ShellInit` is issued by
`VIOSHELLINIT` (`DOSCALLS` ordinal 822), whose only caller inside `DOSCALL1` is the session-manager
initialisation `DOSSMSGINIT` run by `DosSMInitialize` (ordinal 707). So the flag means "the shell's
session-manager initialisation of BVS has succeeded", which in this build is also the moment the
windowed handler is loaded. `[OBS-RE]`: the one writer is obj4 +0x7938; readers +0x185A
(`BVSMAIN`), +0x7D2E (`BVSGETPTRDRAWNAME`), +0x8204 (`BVSGETVIDEOCALLTABLES`), +0x82D2
(`ULOADWINTHORNVDH`); read
2026-10-01.]

- **On a ~~full-screen-only system~~ [2026-10-01: boot on which no shell calls `DosSMInitialize`,
  e.g. a plain `PROTSHELL=CMD.EXE`] `0x0AA9` is never set, so `BVSMAIN` calls `BVSDINIT` on every
  BVS call** - the conclusion "init is lazy, triggered by the first BVS call" survives, but there
  is no one-shot gate in front of it. Do not implement one. [2026-10-01: observed before any
  shell runs: the SYSINIT process's first console write enters `BVSDINIT` four times, section 4.2a.
  `[OBS]`]
- **The real idempotence lives inside `BVSDINIT`**, in two separate guards: `*(byte*)0x98A & 8`
  gates `BVSGLOBALINIT` (a genuine one-time flag, set on success), and the type-3 branch is
  itself conditional on `*(int*)0x97E == 0 && *(int*)0x980 == 0` - since that branch sets
  `0x97E = 3`, every later call falls through ~~both branches~~ and returns having done nothing.
  [2026-10-01: every later call *other than `vf_ShellInit`*. The `0x44` arm has no guard at the
  `BVSDINIT` level: it always writes `FFILLDEVBLK = 1` and calls `ULOADWINTHORNVDH` and
  `BVSGETVIDEOCALLTABLES`; it stops recurring only because its success sets `FSHELLINITED`, after
  which `BVSMAIN` no longer calls `BVSDINIT` at all. Names: `0x98A` is `GLOBALFLAGS`, and `0x97E`
  with `0x980` are the low and high words of one dword, `FFILLDEVBLK` (the `.sym` places
  `MASKFILLDEVBLK` at `0x97A` and the next symbol at `0x982`). `[OBS-RE]` obj4 +0x78DC..+0x7956,
  2026-10-01.]
  A third, separate latch (`*(char*)0x321`) gates the hardcoded fallback chain in
  `UINITGENERICVDH` (section 4.3).

[OBS-RE: `BVSMAIN_1c04:1837.c` (the read) and `BVSDINIT_1c04:78c4.c` (the write and both
guards) read directly, 2026-08-16; the flag's windowed-load role is also stated in the
chain-load trace this section cites.]

`BVSDINIT` takes a ~~type code distinguishing at least two environments~~ [OBS-RE]
[2026-10-01: argument that is the triggering call's VIO function code, and it distinguishes
exactly two cases: `0x44` (`vf_ShellInit`) and everything else. "Type 3" below is not a code
passed in; it is the value the second arm stores into `FFILLDEVBLK`, the same `3` the DDK names
`FnFillInitDevBlock` (`[DOC-IBM]` `vdh/vdh.h`; section 4.4a). `[OBS-RE]` obj4 +0x78F5, +0x794F]:
- **`0x44` - windowed-VIO environment** [2026-10-01: `vf_ShellInit`, from the session manager's
  initialisation; see the note above]: loads `BVHWNDW.DLL` specifically
  (`ULOADWINTHORNVDH` - "Winthorn" being the windowed VDH's internal codename), then builds the
  call tables for that configuration. *(Corrected 2026-08-27, Rule 1.7: this read "the session's
  call tables" - see section 4.4a; the axis is the video device, not the session.)*
- **The default/full-screen path (internal type 3)**: no dedicated loader - it falls into the
  same shared `BVSGETVIDEOCALLTABLES`, which performs the config-driven chain load below.
  [2026-10-01: taken only while `FFILLDEVBLK` is still 0, so in practice only by the boot's
  first BVS call if that call is not `vf_ShellInit`. On the SMP boot of section 4.2a it is the SYSINIT
  process's first message. `[OBS-RE]` + `[OBS]`]

### 4.2a The first BVS call can come from SYSINIT, before any shell `[OBS-RE]`

Read in the Warp 4.5 kernel (14.104a) and DOSCALL1 bytes, 2026-09-30. The facts are about that build.

- **DOSCALL1 initialises in the SYSINIT process.** The kernel's SYSINIT code loads DOSCALL1.DLL with
  an ordinary ring-3 `DosLoadModule`, before `DEVICE=` processing. The loader starts library
  initialisation for it. DOSCALL1's init entry runs its per-process VIO initialisation, and a failure
  there fails the DLL's initialisation.
- **There is always a screen-group control block (SGCB).** The routine that looks up an SGCB builds
  the screen-group table on its first call. It allocates zeroed SGCBs for screen groups 0 and 3 before
  any session manager exists. So VIO routing in SYSINIT runs against a real SGCB.
- **A `DEVICE=` driver's console write reaches BVS.** A driver's INIT-time `DosWrite` to a console
  handle reaches DOSCALL1's `VioWrtTTY` in SYSINIT, in screen group 0 (SYSINIT is pid 1; a running
  system reports pid 1 in session 0, `[OBS]` in `infoseg.md`). The write first sets the boot mode.
  VIO's router then issues a `VioSetCp` on a screen group's first routed call, and that `VioSetCp` is
  the first call to enter `BVSMAIN`. `BVSDINIT` therefore first runs with that function code, not with
  `0x44`, and takes its re-select arm, which polls each candidate handler's power-up entry.
- ~~**Without such a write, `0x44` comes first.** If no `DEVICE=` driver writes to the console during
  INIT, the first `BVSMAIN` entry is the shell's `vf_ShellInit` (`0x44`).~~ [2026-10-01: refuted on
  the SMP kernel by the `[OBS]` note below. With no `DEVICE=` driver writing, the first entry was
  still `0x24`, from the kernel's own boot message in SYSINIT. Unmeasured on a uniprocessor kernel.]

~~Which of the two applies is a property of the `CONFIG.SYS`, decidable from the binaries.~~
[2026-10-01: on the SMP kernel `CONFIG.SYS` does not decide it; the note below.]
~~**Not established:** whether the kernel's own pre-`DEVICE=` messages take this path.~~
[2026-10-01: answered by the note below. They do, and they come first.]

- **2026-10-01, observed `[OBS]`:** they do, and they come first. Machine: WSeB 4.50 Rev 14.089,
  HStrict SMP debug kernel, SMP `DOSCALL1.DLL` (`BVSDINIT` at obj4:`0x8576` in that build), one
  virtual CPU. Method: kernel-debugger hardware breakpoints on `BVSDINIT`, `VIOWRTTTY`,
  `DOSPUTMESSAGE` and `BVSMAIN`, two clean boots. In boot A, every removable `DEVICE=` driver that
  writes to the console was taken out. In boot B, a `DEVICE=` driver that writes a banner at INIT
  was left in. Both boots gave the same first `BVSDINIT` call: function code `0x24`, from SYSINIT
  (pid 1), screen group 0, re-select arm. The caller is the kernel's own message
  `Processors Initialized: 1`, which reaches `VioWrtTTY` via `syiDisplayMessageR3` ->
  `DosPutMessage` -> `DosWrite`. It is printed before the first `DEVICE=` driver runs. So on this
  kernel the two cases above do not decide the first call, and *"0x44 comes first"* does not hold.
  Not measured: a uniprocessor kernel, which may print no such message.

### 4.3 Which handler DLLs load - configuration, probing, and the hardcoded fallback

The handler list is **configuration, resolved at BVS init** [OBS-RE `VREADENVVARS`,
`BVSGETVIDEOCALLTABLES`, `FISPOWERUP`, `UINITGENERICVDH` - all in `DOSCALL1.DLL`]:

1. **`SET VIDEO_DEVICES=`** names a comma-separated list of *class variables* - each entry is
   itself the name of a second environment variable, e.g. `SET VIDEO_DEVICES=VIO_SVGA` +
   `SET VIO_SVGA=DEVICE(BVHVGA,BVHSVGA)`. The `DEVICE(...)` tag holds the actual BVH module
   names (comma-compound = a chained pair: base handler + chained refinement).
2. For each candidate: `DOSLOADVIDEOHANDLER` -> `DOSDRIVERENABLE` - which, one level down, is an
   ordinary `DosLoadModule`/`DosGetProcAddr` pair resolving the module's ~~single exported entry
   point~~ **`DevEnable`** [2026-10-01: the one entry point it resolves, by the literal name
   `"DEVENABLE"`; a handler exports others - section 4.4's correction] - then **`FISPOWERUP`**, a real
   hardware-presence check (calls through
   the loaded handler's descriptor and tests a status bit). A handler whose hardware isn't
   present is unloaded and the next candidate tried.
   [2026-10-01: the poll is not on every load. `FISPOWERUP` has exactly two call sites, both in
   `BVSGETVIDEOCALLTABLES`: the re-select arm taken by a first BVS call that is not
   `vf_ShellInit` (one poll per candidate), and the `vf_ShellInit` arm's promote loop, which
   polls only when more than one device is configured. The per-process re-enable described in
   section 4.4a polls nothing. `[OBS-RE]` obj4 +0x7E54, +0x8137, read 2026-10-01.]
3. **If nothing configured powers up**, a hardcoded 7-entry fallback chain is tried in order
   (static data in DOSCALL1's DGROUP): `BVHVGA,BVH8514A` -> `BVHVGA,BVHVGA2` -> `BVHVGA` ->
   `BVHEGA` -> `BVHCGA` -> `BVHVGA2I` -> `BVHINIT`.

Note what is *absent*: there is no special-cased "always load BVHVGA" step, and the BVH DLLs are
**not** loaded by any CONFIG.SYS `DEVICE=` line and not imported by any PM binary - they are LX
libraries chain-enabled purely through this BVS registry. `DEVINFO=SCR,VGA,VIOTBL.DCP` is a
separate, parallel CONFIG.SYS directive supplying the VIO font/code-page table file - data for
the BVS font machinery (`BvsGetFont`/`BvsSetFont`), not a driver name.

> **NARROWED 2026-08-25 (Rule 1.7): right in substance, wrong consumer.** The file is not read
> by `BvsGetFont`/`BvsSetFont` - those sit *above* it. The actual reader is the **BVH**:
> `GetCodePage()` (DDK `video/src/video/svdh/bvhfont.c`) opens the file named
> in the **CDIB** (`\SHAREMEM\DOS\CDIB`, populated by `COUNTRY=`/`CODEPAGE=`/`DEVINFO=SCR`
> together - one mechanism, not three), reads `FONTFILEHDR` + the `ffh_numfonts` ULONG offset
> table, and builds a `RomCP_tbl[]` of `{CodePageID, FontPTR, BaseRows, BaseColumns}`;
> `FindCPFont(env, PelRows, PelColumns, CodePageID)` then selects on that triple and `SetHWFont`
> programs it. **Selection is by code page and cell dimensions, never by mode number** - which
> is what settles the open question at ~~section 2.2~~ [2026-10-01: section 2.1, the "Open" paragraph; section 2.2 is
> Alt-F1] above. `DEVICE=...\VSVGA.SYS` is
unrelated to all of this (a VDM virtual video driver, LX module type 5, loaded through the
ordinary `DEVICE=` path).

### 4.4 The BVH contract

[DOC-IBM] IBM DDK `video/src/video/svdh/` (the SVGA Video Device Handler - a complete, C-language
chained BVH) plus the XGA BVH (`pmvideo/xgabvh20`):

- A BVH exports ~~**one** entry point~~, `DevEnable`, whose job is to fill/override slots in the
  **CVT** [2026-10-01, on "exports one entry point": `DevEnable` is the one *initialisation*
  export, but a BVH exports others. IBM's `vdhvga.def` lists `DEVENABLE` with fourteen IOPL
  hardware entries declared with parameter-word counts (`SETMAPMASK`, `ACCESSCURSORPOS` ...
  `ACCESSHARDWARE`, `ACCESSREGISTER`, `CHARFONTEND`, `SET132`, ...); `vdhwndw.def` lists `DEVENABLE`
  and `BUFFERUPDATE`; the SVGA handler's makefile adds `SETDIAMONDCLK`, `SETNUMBER9CLK`,
  `_WDPanelOn`. `[DOC-IBM]` DDK `video/src/video/vdh/vdhvga.def`, `vdhwndw.def`, `svdh/makefile`.
  The shipped handlers agree: `BVHVGA.DLL` names fifteen exports, `BVHWNDW.DLL` names `DEVENABLE`,
  `BUFFERUPDATE` and `GETCONFIG`. `[OBS-RE]` resident-name tables, read 2026-10-01.]
  - the 256+-entry function table (function codes from 0x100 up; the dispatcher
  subtracts 0x100) covering `InitEnv`, `GetMode`/`SetMode`, buffer access, cursor, fonts,
  `SaveEnv`/`RestoreEnv` (CVT 258/259), `BufferUpdate`, print-screen, etc. Slots a handler
  leaves untouched keep the previous handler's (or DOSCALL1's own default) pointer - this is
  the **chaining** mechanism: `BVHSVGA` overrides only what it improves over `BVHVGA`; a
  chained handler's own code calls the previous handler's saved entries for the rest
  (`ChainedEntryPoint[]` in `bvhmain.c`).
- **`SaveEnv`/`RestoreEnv` are called by BVS around a screen switch** (`bvhmain.c`'s own header:
  "SaveEnv is called by BVS prior to a screen switch") with a `VDHSAVEREST` parameter block whose
  flags select hardware-register state and/or full/partial **PVB** (Physical Video Buffer)
  save/restore. This is the full-screen handler's burden; a windowed handler's SaveEnv/RestoreEnv
  are no-ops (its output lives in PM windows that survive switches).
- Per-session state is an **ENVIRONMENT** buffer (per screen group), created/sized through the
  same call-table protocol; `InitEnv` establishes the mode for a fresh environment (the SVDH
  source shows `InitEnv` calling its own `SetMode` with a default `VDHMODEINFO`).

### 4.4a Call Vector Table ownership: one table per VIDEO DEVICE, held system-wide

A natural reading of section 4.1's "a far call through the session's Call Vector Table" is that each
session owns a CVT, or that one system CVT is re-registered whenever the active session type
changes. **Neither is what OS/2 does.** There are **sixteen** call tables, one per video device -
the windowed handler plus up to fifteen real displays - all live at once in the BVS global shared
segment; a session holds a two-byte **index** into that array and nothing more. Nothing is
re-registered on a switch.

Both tiers agree, and each supplies half the picture: the DDK names the axis and the fields, the
shipped binary shows the mechanism running.

#### The array is sized for devices, not sessions - `[DOC-IBM]`

The BVS Global Data Segment opens with the call-table array, and IBM's comment names its axis:

```
bvsgdata        STRUC                   ;BVS Global Data Segment
bvsgCallTables  dd      16 dup (0)      ;Allow for WDH and 15 real devices
```

DDK `base/inc/bvscb.inc`, `bvsgdata STRUC`. `bvsgCallTables` is the **first** field, so it is at
offset 0 of the segment the data export `BVSGLOBAL` addresses. Sixteen far pointers: slot 0 for
the **W**indowed **D**evice **H**andler, slots 1..15 for real display devices.

Contrast it with the per-session array in the *same* structure - its **last** field:

```
bvsgSelTable    dd      256 dup (0)     ;Selector table offset          ;@D549
```

256 entries, one per screen group, holding that session's `selt_bvscb`/`selt_envb`/`selt_lvb`.
**IBM sized the two arrays differently on purpose: call tables are per device, selector tables
are per session.** The same file's prose says so, and enumerates what "per device" carries:

> "the following are for **per VDH data**. The per VDH data consists of **a call table**, a device
> string, a real mode pointer draw name string, a protect mode pointer draw name string, a device
> table entry and a word of 'in use' flags. Per VDH data is allocated at the end of BVSCNSEG.
> The segment is reallocated when more space is needed."

DDK `bvscb.inc`, the comment block preceding `ccalltbls`. Note the storage: one segment, grown as
devices are added - not an allocation per session.

| symbol | value | meaning |
|---|---|---|
| `ccalltbls` | `10h` = 16 | number of call tables |
| `cbcalltbl` | `4*11ah` = 1128 | size of one call table |
| `fn_NextAvail` | `11Ah` = 282 | "Next Available Func. #" |

`[DOC-IBM]` `bvscb.inc`, `bvsparms.inc`.

#### A screen group's slot is filled ONCE: create-if-empty, access-if-present - `[OBS-RE]` + `[DOC-IBM]`

`bvsgSelTable[sgid]` is not merely *where* a screen group's record lives; it is the test BVS uses
to decide **whether to make one**. `GetBVSCB` (`DOSCALL1.DLL` object 4, `+0x13D7`) reaches its
allocator only when the slot is zero:

```
0000146A  C1E602        shl si,2                  ; si = sgid * 4  (dd stride)
0000146D  6683BCB60400  cmp dword [si+0x4b6],0    ; bvsgSelTable[sgid]
00001473  752D          jnz 0x14A2                ; ALREADY FILLED -> skip the allocator
00001475  1E            push ds
00001476  8D84B604      lea ax,[si+0x4b6]         ; &bvsgSelTable[sgid]
0000147A  50            push ax
0000147B  FF36B404      push word [0x4b4]         ; bvsgSelTablesz
0000147F  9A3A421EE0    call 0xe01e:0x423a        ; allocate the record
...
00001497  0FB5B4B604    lgs si,[si+0x4b6]         ; gs:si = the entry
0000149C  658C4402      mov [gs:si+0x2],es        ; selt_bvscb = the BVSCB selector
```

and the already-filled branch at `+0x14A2` **reads** the existing entry, checking its selector
against the caller's own per-process instance data before use, and writes nothing back to the
table:

```
000014A2  B81F98        mov ax,0x981f             ; BVHINSTANCE
000014A5  8EE8          mov gs,ax
000014A7  8B84B804      mov ax,[si+0x4b8]         ; the entry's selector half
000014AB  653906AF00    cmp [gs:0xaf],ax          ; do I already have it?
000014B0  7406          jz  0x14B8
000014B2  50            push ax
000014B3  9A00000000    call far ...              ; obtain access to it
000014B8  0FB5B4B604    lgs si,[si+0x4b6]         ; use the EXISTING entry
```

**Where `+0x4B4`/`+0x4B6` come from, since the header does not state them.** Those are
*displacements inside the shipped segment*, not `STRUC` offsets, and the two must not be
conflated. The header supplies the field's name, type, order and count - `bvsgSelTablesz dw`
followed by `bvsgSelTable dd 256 dup (0)`, the last two fields of `bvsgdata STRUC` `[DOC-IBM]`.
The displacements are observed: `[0x4b4]` and `[si+0x4b6]` in the disassembly above, and
independently in the symbol-derived field table of unpublished notes,
which also places `bvsgdata` itself at `+0x360` in `DOSCALL1.DLL` object 2 `[OBS-RE]`. Subtracting
gives the `STRUC` offsets `+0x154`/`+0x156` `[INF]` - a difference of two observations, not a
reading of the header.

> **A trap worth recording** (`[OBS]`, 2026-08-27): walking `bvsgdata STRUC` with a script that
> sizes `db`/`dw`/`dd` and `N dup (...)` but treats a *string* initializer as one element
> undercounts this structure by `0x48` and yields `+0x10C`/`+0x10E`. `bvsgdata` is full of
> string fields (`bvsg_bvscbname`, `bvsg_mouddname`, `bvsg_prtname`, the print-screen titles).
> Derive the offset from the observed displacements, or size the strings.

`selt_bvscb` is at `+2` of the `seltable` STRUC. So **a process that finds a screen group already
established joins it; it does not re-create it**, and IBM's own routine names carry the split -
`InitBVSCB` versus `GetBVSCB`/`AccessBVSCB` (all three present in `DOSCALL1.DLL`'s symbol table).

The `seltable` STRUC says the same thing in its field names, every one of which is a **master**:

```
seltable        STRUC                   ;@S10
selt_size       dw      0               ;size of this structure           ;@D549
selt_bvscb      dw      0               ;Master BVSCB selector ;@S10
selt_flags      dw      0               ;Active config flags ;@S10
selt_envb       dw      0               ;First master ENVB selector ;@S10
selt_lvb        dw      0               ;First master LVB selector ;@S10
selt_nextenvb   dw      0               ;Next master ENVB selector, if any ;@S10
selt_nextlvb    dw      0               ;Next master ENB selector, if any ;@S10
seltable        ENDS                    ;@S10
```

A screen group has one master BVSCB, one *first* master ENVB and one *first* master LVB; where a
screen group needs a further environment or logical buffer, IBM ~~**chains** it~~
(`selt_nextenvb`/`selt_nextlvb`) rather than replacing the master.
[2026-10-01: not a chain: an **array of pairs indexed by configuration number**. `GetBVSCB` walks
the record from `selt_envb` in steps of two words, one ENVB/LVB pair per configured device
(`ILASTVDH` pairs, or one for a windowed group), and later selects the current one by
`(bvs_curconfig - 1) x 4`. `[OBS-RE]` `DOSCALL1` obj4 `GetBVSCB` +0x14D8..+0x1606, read 2026-10-01;
section 5.1 has the allocation detail.] There is no shape in this
design in which a second writer overwrites an established screen group's entry.

> **SHARPENED 2026-08-28 (Rule 1.7) - what "a further environment" MEANS, because leaving it
> unsaid invites a specific wrong reading.** The paragraph above is correct and is kept; it just
> does not say *when* a screen group needs a second ENVB, and the tempting answer - "when a second
> process attaches" - is wrong. Every seltable field carries the change tag `@S10`, and
> `bvscb.inc`'s own change log reads
> `;@S10 = 05/11/89 STJ, Retain separate ENVB/LVB for each config, B701174`. **Per config**, i.e.
> per entry in `SET VIDEO_DEVICES=` (section 4, *A "configuration" is an entry in `SET VIDEO_DEVICES=`*),
> consistent with the neighbouring `selt_flags` *"Active config flags"* and the per-session BVSCB's
> `bvs_numconfigs`/`bvs_confignum`/`bvs_curconfig`. A second **process** does not add a link; it
> obtains its own selector for the existing segment, by name - see section 5.1, which also records how.
> The "joins it, does not re-create it" conclusion above is unaffected and in fact strengthened:
> section 5.1 supplies IBM's actual join routine.

The call target at `0xe01e:0x423a` is **`DOSSMGETMEM`** - `0x1C03423A` in `DOSCALL1.DLL`'s own
symbol table, i.e. the empty-slot branch really does allocate a record of `bvsgSelTablesz` bytes
into `&bvsgSelTable[sgid]`, rather than merely calling something unidentified.

`[DOC-IBM]` DDK `base/inc/bvscb.inc` (`bvsgdata STRUC` field order/types, `seltable STRUC`);
`[OBS-RE]` raw bytes, `ndisasm -b16` over `DOSCALL1.DLL` object 4 at `0x1C040000`, plus that
module's `symbols_va.txt`, 2026-08-27.

#### The same per-device group in the shipped binary, split two ways - `[OBS-RE]`

`DOSCALL1.DLL`'s own symbol table settles the identity of the export and bounds the array:

```
0x13020360  BVSGLOBAL
0x13020360  bvsg_calltables
0x130203a0  bvsg_flags
0x130203aa  bvsg_maxbase
```

`BVSGLOBAL` **is** `bvsg_calltables` - one symbol, two names - at object 7 (`0x9817`, the BVS
global shared segment) `+0x360`, and the next symbol at `+0x3A0` bounds it to `0x40` bytes = 16
far pointers. It is zero in the shipped image and filled at runtime.

The DDK's per-VDH group survives here, split two ways - and all six of its components are
accounted for. Three are hoisted into **parallel 16-entry arrays** walked by
`BVSGETVIDEOCALLTABLES` with the *same* index, bounded `< 0x10`: `PSZDEVICESTRING` (the device
string), `PSZPROTPTRNAMES` and `PSZREALPTRNAMES` (the two pointer-draw name strings), alongside
`bvsg_calltables` itself. The other two stay packed in a per-device block, and its arithmetic
comes out exact:

| offset in the block | what | shown by |
|---|---|---|
| `+0x000` | the *"word of 'in use' flags"* | `FGETFREECALLTABLE` scans for a block whose byte 0 lacks bit `0x08` and sets `\|= 8` to claim it; `UGROWDEVGROUP` zeroes the word on a fresh block |
| `+0x002` | the device-table entry, 714 bytes | `UGROWDEVGROUP` calls `VINITIALIZEENTRY(block+2, ...)`, and `0x2CC - 2 = 714` = the DDK's `cbDevTblEnt` exactly |
| `+0x2CC` | the 26-entry call table, 104 bytes | `FGETFREECALLTABLE` returns `block + 0x2CC` and fills `0x1A` entries |
| total | `0x334` | `UGROWDEVGROUP` allocates `PCHGROWGLOBAL(0x334)`, and `0x2CC + 26*4 = 0x334` |

Same six components, same axis, different packing - a build difference in storage, not in
architecture. *(The DDK says this data is allocated at the end of `BVSCNSEG`; the shipped blocks
are grown onto the tail of the same object 7 that holds `bvsg_calltables`. That these are one
segment under two names is not established here.)*

**Slot assignment, observed:** `ULOADWINTHORNVDH` is entered with the literal far pointer
`&bvsg_calltables[0]` and loads the name at `PSZWINDOWBVH` - **slot 0 is the windowed handler**.
*(`PSZWINDOWBVH` is a far-pointer cell, null in the shipped image; the string `"BVHWNDW"` sits
four bytes past it at `+0xA94`. The identification is by symbol name and adjacency, not by a
resolved pointer.)* Meanwhile `UINITGENERICVDH` writes `bvsg_calltables[1]`, and `BVSGETVIDEOCALLTABLES` swaps the
`FISPOWERUP` winner into `+4` of the parallel arrays - **slot 1 is the selected full-screen
display handler**. Slots 2..15 are the further devices a `SET VIDEO_DEVICES=` list can configure;
slot 0 is not one of them, which is why configuration numbers start at one.

**The slot is fixed by role, not by allocation order** - worth stating because the arithmetic
looks like the opposite. The full-screen block is allocated *first* (at boot) and the windowed
block *second* (with PM), yet they take slots 1 and 0 respectively.

#### Two table shapes, and which one `DevEnable` sees - `[OBS-RE]`

A handler is handed a **function-number-indexed** vector whose length it is told -
`Parm1->TableSize`, which IBM's own handler bounds its fill loop by (`i < Parm1->TableSize`,
`vdhmain.c`) and which BVHWNDW *checks* against `fn_NextAvail` before doing anything
(`.if <[si+4] ae fn_NextAvail> ;Table large enough for this VDH`, `wdhmain.asm`). In both
observed builds that length is 282: `DOSLOADVIDEOHANDLER` takes a `0x468`-byte (= 282 x 4)
scratch buffer, fills entries
`0..0xFF` with `UERRORFUNCTION`, copies the current handlers into `0x100..0x119` (256..281), calls
the chain through `DOSDRIVERENABLE` on the literal string `"DEVENABLE"`, and then copies **26**
entries back into the stored table. The stored table in this build is therefore the compact
26-entry form, which is why the dispatcher indexes it as `fn - 0x100`.

That is what reconciles the two indexings a reader meets. `DevEnable` is documented against - and
IBM's own handler biases into - a table whose element 0 is function 0: *"The far address of the
nth BVH function is the nth DWORD in the table, beginning with Function 0"* `[DOC-IBM]` (Display
Device Driver Reference, *DevEnable*), and `add di,4*fn_BufferUpdate ;ES:DI = target table`
`[OBS]` DDK `video/src/video/vdh/wdhmain.asm`. The dispatcher meets the extracted 26-entry form.
Both are views of the same 26 registrations. *(The DDK-era build kept the full 1128-byte table
in the per-device block - `cbDevGroup equ cbcalltbl+...` - where the shipped build keeps 1128 only
as a scratch buffer. The architecture is invariant across the two; the storage is not.)*

Untouched slots keep the previous handler's entry, which is how the **default** handlers survive:
a freshly allocated table is filled entirely with `UERRORFUNCTION`, then BVS overrides two of its
own - function 277 `VDHPRTSC` and function 278 `VDHWRTTTY` - before any BVH runs. `[OBS-RE]` That
is the mechanism behind a shipped handler's function table carrying explicit zero entries for
print-screen and write-TTY.

#### A "configuration" is an entry in `SET VIDEO_DEVICES=`, and it is numbered - `[DOC-IBM]`

Display Device Driver Reference, *Video Device Handler Identification*:

> "...the environment variables ARTICHOKE and WATERMELON as those defining the active video
> device handlers, with ARTICHOKE used as **configuration number one**, and WATERMELON used as
> **configuration number two**. ... These names represent only those parts of the BVH that need
> to be called to **initialize the Call Vector Table**."

So the configuration list of section 4.3 *is* the index space of `bvsgCallTables`, and each configuration
gets its own table filled by its own handler chain. The application-visible face of the same
concept is `VioGetConfig`'s `ConfigID`: `0` = current, `1` = primary, `2` = secondary
`[DOC-IBM]` *Control Program Reference*. The primary display is *"the default display chosen by
VIO for full-screen sessions ... also the display on which VIO and hard error pop-ups are shown"*
`[DOC-IBM]` Display Device Driver Reference, *Primary Display Identification* - consistent with
slot 1 being the selected full-screen handler.

#### The session holds an index, and the index comes from the SGID

`[DOC-IBM]` the per-session BVSCB carries three device-related words:

```
bvs_numconfigs  dw      0               ;Number of valid configurations
; The following fields are saved/restored as a unit
bvs_confignum   dw      0               ;Configuration number
bvs_curconfig   dw      0               ;Current configuration
```

IBM's *"saved/restored as a unit"* marker sits between the first and the second, so the count
stands outside the saved block while the two indices are saved and restored with the mode data.

Their offsets are not in the header; counting the struct from `bvscb STRUC` puts them at `+0x0E`,
`+0x10` and `+0x12` (`bvs_flags` `+0`, `bvs_bvssize` `+2`, `bvs_envsize` `dd` `+4`, `bvs_lvbsize`
`dd` `+8`, `bvs_ActiveCP` `+0x0C`).

`[OBS-RE]` and the shipped dispatcher reads exactly `+0x12`. `AllVDH`, `DOSCALL1` object 4
`+0x1C03`, raw bytes (the trailing comments are glosses added here, not IBM's):

```
1C03  8E1ED002    mov ds,[0x2d0]      ; DS = this session's BVSCB
1C07  8B5F12      mov bx,[bx+0x12]    ; BX = the session's device-slot index
1C0A  C1E302      shl bx,2
1C0D  B81798      mov ax,0x9817       ; DS = BVS global segment
1C10  8ED8        mov ds,ax
1C12  C59F6003    lds bx,[bx+0x360]   ; DS:BX = bvsg_calltables[index]
1C16  81EF0001    sub di,0x100
1C1A  C1E702      shl di,2
1C1D  FF19        call far [bx+di]    ; CVT[fn-256]
```

That `[0x2d0]` really is the BVSCB selector is IBM's own naming, not an inference: the shipped
symbol table carries `bvsi_bvssel`, `bvsi_envsel`, `bvsi_lvbsel`, `bvsi_sgnum`, `bvsi_gdtsel`,
`bvsi_ldtsel`, `bvsi_level`, `bvsi_flags`, `bvsi_pvbsel`, `bvsi_biosel`, `bvsi_physaddrl` at
object 8 `+0x2D0` onward - **field-for-field, in order, the DDK's `bvsidata STRUC`**, which sits
commented out in `bvscb.inc`. `[OBS-RE]` + `[DOC-IBM]`.

The DDK field at `+0x12` and the shipped field at `+0x12` therefore carry the same meaning under
different names, two builds and roughly a decade apart.

**And the match is on a pair, not a single offset**, which is what makes it more than coincidence:
`InitBVSCB` writes the device count into `+0x0E` and `1` into `+0x12` - the same two fields, in
the same order, as the DDK's `bvs_numconfigs` (*"Number of valid configurations"*) and
`bvs_curconfig` (*"Current configuration"*).

*(How much of the rest of the block agreed was not established. One apparent divergence - a byte
screen-group read at `+0x18` - is not one: `AllVDH` reaches it as `mov ds,[0x2d8]` (`bvsi_gdtsel`)
`/ mov al,[bx+0x18]` with `BX = 0`, so that is **GIS `+0x18` = `SIS_CurScrnGrp`**, not a BVSCB
field at all.)*

**What sets the index** - `GetBVSCB`, object 4 `+0x14BD`, raw (comments added here):

```
14BD  26FF7712        push word [es:bx+0x12]    ; save the old index
14C1  8B0EF408        mov cx,[0x8f4]            ; ILASTVDH
14C5  26C747120100    mov word [es:bx+0x12],1   ; default: slot 1 (full-screen handler)
14CB  3B16AA03        cmp dx,[0x3aa]            ; DX = this session's SGID  vs  bvsg_maxbase
14CF  7607            jna 0x14d8                ; SGID <= maxbase -> keep slot 1
14D1  B90100          mov cx,1
14D4  26895F12        mov [es:bx+0x12],bx       ; else -> the windowed slot
```

**and `bvsg_maxbase` is the full-screen boundary, derived from the Global Info Segment** -
`BVSGLOBALINIT`, object 4 `+0x7C51`, raw (comments added here):

```
7C51  26A1A603    mov ax,[es:0x3a6]      ; bvsg_SISsel
7C58  C45EF8      les bx,[bp-0x8]        ; ES:BX = the Global Info Segment
7C5B  268A4719    mov al,[es:bx+0x19]    ; GIS +0x19 = SIS_MaxScrnGrp
7C5F  2AE4        sub ah,ah
7C61  48          dec ax
7C66  26A3AA03    mov [es:0x3aa],ax      ; bvsg_maxbase = SIS_MaxScrnGrp - 1
```

`[OBS-RE]`, all three verified against the raw object images. So: **a session whose screen-group
id is at or below `SIS_MaxScrnGrp - 1` dispatches through the full-screen handler's table;
one above it dispatches through the windowed handler's.** *(That the "else" branch stores zero is
`[INF]`: `BX` is the BVSCB's offset within its own `\SHAREMEM\BVS\BVSsg` segment and the same
routine zero-fills from offset 0, so `BX = 0` - read from the surrounding code, not from a
literal.)*

IBM's windowed handler applies the same boundary independently, from its own copy:
`mov al,es:[bx].SIS_MaxScrnGrp / cbw / dec al / mov ds:wdh_LastFS,ax`, then
`.if <ax a ds:wdh_LastFS>` (with `ax` = `LIS_CurScrnGrp`) -> `WININITIALIZE` + `GREINITIALIZE`
`[OBS]` DDK `wdhmain.asm`, `DEVENABLE`. Two independent components, two eras, one rule.

This also explains the field's name and a puzzle recorded in `infoseg.md`: `SIS_MaxScrnGrp` bounds
the **full-screen** screen groups, which is why a live system can report `SIS_MaxScrnGrp = 16`
while carrying session ids 17, 18 and 19. It does **not** revive the Warp-3 three-way id table
(`4-15` full-screen / `16-31` windowable VIO / `32-255` PM) that `infoseg.md` measured as no
longer describing Warp 4.5 - the boundary here is two-way, full-screen versus everything else,
and the ids that measurement observed were all above it. [2026-10-01: not all. The started
sessions' ids (16 to 19, and 4080 for a DOS session) were above `bvsg_maxbase` = 15, but the same
capture has screen group 0 (pid 1, SYSINIT) and screen group 1 (the shell, `PMSHELL`) at or below
it. `infoseg.md`, "Measured on a live Warp 4.5 system", `[OBS]`, WSeB CP2 with the PM desktop up,
2026-08-20.] **A capture containing an actual
full-screen session, confirming its id lands at or below `SIS_MaxScrnGrp - 1`, has not been
taken.**

#### Overwriting a slot is the documented mechanism, not a collision - `[DOC-IBM]`

`video/src/video/vdh/vdhdata.h`, above `VDHEntryPoint[]`:

> "Device chaining is not implemented in these video device handlers. If the VDH supports the VDH
> function, DevEnable will **over-write** the current entry in the call vector table. If the VDH
> does not support the VDH function, the call vector table entry **will not be touched**."

(The first sentence scopes the *file*: this source builds the unchained VGA-family handlers, and
its own chaining code sits behind `#if VDH8514A`. The over-write rule it states is `DevEnable`'s
behaviour either way.)

That is how a **chain** is built, and a chain is built **within one device's table**. Display
Device Driver Reference, *A VGA and 8514A Scenario*:

> "During system initialization, BVHVGA is first called to initialize the Call Vector Table...
> Next, BVH8514A is called to initialize **the same** Call Vector Table. However, BVH8514A
> **saves a copy of the Call Vector Table before changing it**. When calls are made to this
> chained BVH, BVH8514A receives the call and passes it to the BVHVGA routine through the saved
> Call Vector Table. ... Device chaining can be viewed as a mechanism to allow one BVH to filter
> function calls to another BVH."

The saved copy is the handler's own private `ChainedCallVectorTable[]` (`vdhdata.h`; the
`ChainedVDH*` macros in `vdh.h`) - not a second CVT. The shipped `DOSDRIVERENABLE` implements
exactly this by walking the comma-separated component list of one `DEVICE(...)` keyword and
calling each component's `DEVENABLE` on the *same* vector `[OBS-RE]`. **Two handlers serving two
different devices never write the same table and never chain.**

#### A handler fills its table once, system-wide - `[DOC-IBM]` + `[OBS-RE]`

IBM's VGA handler guards the whole fill behind `FIRST_INIT`, declared
`UCHAR FIRST_INIT = TRUE; /* Flag to force only one INIT device initialization */`
(`vdhdata.h`) and cleared in `DevEnable` (`vdhmain.c`). The windowed handler expresses the same
guard as `.if <ds:wdh_SISsel eq bx> ;This is 1st call by System` (`wdhmain.asm`). Both flags live
in the handler's **shared** data segment - `_DATA CLASS 'DATA' SHARED` `[DOC-IBM]`
`vdhwndw.def` - so "once" means once for the system, not once per process and not once per
session. *(`vdhvga.def` declares only `DATA LOADONCALL` with no sharing keyword; that this
resolves to a DLL's single shared data segment is `[INF]` about OS/2 LINK defaults, not read from
a source. It is not load-bearing: `FIRST_INIT`'s own comment states the intent - "force only one
INIT device initialization" - and the BVS-side guard below is independent of it.)*

On the BVS side the shape is *not* the same and it is worth being precise, because the difference
cuts the other way: `DOSLOADVIDEOHANDLER` skips only the **allocation** when the slot's pointer is
already non-NULL - it still builds the scratch vector, still calls `DEVENABLE`, and still copies
the 26 entries back, **every time it runs**. So the handler-side one-shot flags are what stop a
refill, not the BVS side.

What bounds it instead is the caller graph, and it is short enough to state whole: `DEVENABLE` is
reached only through `DOSDRIVERENABLE`, which has exactly one caller, `DOSLOADVIDEOHANDLER`, which
has exactly three - `UINITGENERICVDH`, `ULOADWINTHORNVDH` and `BVSGETVIDEOCALLTABLES`. All three
are initialization routines; no screen-switch path reaches any of them. **Nothing re-runs
`DevEnable` on a session switch.** `[OBS-RE]`

[2026-10-01, narrowing "initialization": the initialisation is **per process**, not only per
boot. `BVSGETVIDEOCALLTABLES` has four call sites, and two of them call it with both name-table
arguments null, which selects an arm that re-runs `DOSLOADVIDEOHANDLER` for every configured
device (slots 1..`ILASTVDH`), or `ULOADWINTHORNVDH` when the shell has initialised BVS and the
caller's screen group is above `bvsg_maxbase`: `BVSMAIN` +0x18C0, reached when the process's
`bvsi_gdtsel` is still 0 (its first BVS call), and `BvsInit` +0x1335, for a windowed screen group,
once per process (a bit in the per-process instance data). A handler DLL is loaded per process,
so each process that uses VIO runs `DosLoadModule` and the handler's `DEVENABLE` again; the
handler's own `FIRST_INIT`-style guard (below) is what keeps that from refilling the table. The
conclusion stands: no switch path reaches it. `[OBS-RE]` obj4 +0x1897..+0x18C0, +0x131E..+0x1341,
+0x8200..+0x8270, read 2026-10-01.]

**Two enable subfunctions, both at initialization, both targeting the same table.** `[DOC-IBM]`
Display Device Driver Reference, *Loadable Device Drivers*:

> "If the subfunction is 1 (Fill Logical Device Block), the DevEnable function is requested to add
> **all** of the functions supported by the device handler to the Call Vector Table. If the
> subfunction is 3 (Fill Initialization Device Block), the InitEnable function is requested to add
> **only those functions that can be supported without the use of a loadable device driver**...
> Regardless of the success of the InitEnable function, the DevEnable function is called at Shell
> Initialization time."

`FnFillLogicalDevBlock = 1`, `FnFillInitDevBlock = 3` `[DOC-IBM]` `vdh.h`. The windowed handler
accepts subfunction 1 only (otherwise `PMERR_DEV_FUNC_NOT_INSTALLED`) `[OBS]` `wdhmain.asm` - it
has no pre-`DEVICE=` role. The shipped BVS agrees from the other side: it stores the subfunction in
a global that `DOSLOADVIDEOHANDLER` passes straight through to `DOSDRIVERENABLE`, and sets it to
**1** on the windowed-handler path and **3** on the boot path. `[OBS-RE]`
[2026-10-01: the global is `FFILLDEVBLK` (obj7 `+0x97E`, a dword). The boot path's `3` covers only
the configured-candidate poll: when no configured candidate is left enabled (two sites, one per
arm), `BVSGETVIDEOCALLTABLES` stores **1**
before calling `UINITGENERICVDH`, so the hardcoded fallback chain is enabled with subfunction 1.
Nothing stores 0, so once set it stays 1 or 3 for the boot. `[OBS-RE]` obj4 +0x7EAF..+0x7EBD,
+0x7FF2..+0x8000, and the census of every store to `+0x97E`, read 2026-10-01.]

#### Nothing copies a call table into per-session storage - `[OBS-RE]`, negative result

Searched the `DOSCALL1` decompile for the device-group CVT offset, for 26-entry copy loops and for
the 282-entry vector size. The CVT offset appears in `FGETFREECALLTABLE` only; the 26-entry loop
in `FGETFREECALLTABLE` and `DOSLOADVIDEOHANDLER` only; the 282-entry size in
`DOSLOADVIDEOHANDLER` and `VIOWRTTTY` only. `InitBVSCB` stores an **index** and a device count,
not a table, and `GetBVSCB`, `AccessBVSCB`, `BvsCreateCA`, `BvsRestore` and `BvsSetMode` contain
no CVT copy. **The BVSCB, the session environment and `\SHAREMEM\BVS\BVS<sgid>` hold no call
table.** Every session dispatches through the shared table its two-byte index selects.

#### Corroboration of the layout - `[OBS-RE]`

**Statically, from the shipped image, and this is the stronger half** - it is re-runnable and
needs no live machine. `bvsgCallTables` occupies `0x360`-`0x39F` (16 x 4), so the DDK struct's
scalars must begin at `0x3A0`. They do, and five consecutive fields are readable in the file as
shipped: `bvsgBvscbSize` at `0x3A4` carries its compile-time initializer `0x033E`;
`bvsgPrtsc_Buffer db 134 dup (' ')` is **exactly 134 spaces starting at `0x3BC`**; `bvsgCprTemp`
follows immediately at `0x442` as `1B 5B 30 30 3B 30 30 52 0D` (`ESC [00;00R CR`);
`bvsgBvscbName` follows that as `\SHAREMEM\BVS\BVSsg`; and `bvsgMouddName` as `MOUSE$`. Five
fields, in the struct's order, at the offsets the struct predicts. `bvsg_calltables` itself is
zero in the image - it is filled at runtime.

**Dynamically, from a kernel-debugger dump of a running system taken 2026-07-12** - a clean boot
to the desktop; no new measurement was taken for this section. `BVSGLOBAL` at `9817:0360` holds a
far-pointer array whose slot `[0]` targets a live table of the windowed handler's entry points and
whose slot `[1]` targets a live table of the full-screen VGA handler's, with `[2..]` zero - two
devices enabled, coexisting, neither having displaced the other, and in the slot assignment the
shipped loader code dictates. The same dump reads the scalars at `0x3A0` as
`{0001, 981F, 033E, <SIS sel>, <LIS sel>, 000F, 0006}` - `bvsgFlags` (`bvsg_f_mouactive`),
`bvsgInstance` (and `981F` is independently identified in the same dump as the per-process BVS
instance segment), `bvsgBvscbSize` (agreeing with the static `0x033E`), `bvsgSISsel`,
`bvsgLISsel`, `bvsgMaxBase` and `bvsgInitPid`, in order - and reports the blank text buffer at
`0x3BC`. Note `bvsgMaxBase` reading `000F` on a system whose `SIS_MaxScrnGrp` is 16: the
`BVSGLOBALINIT` arithmetic above, observed live.

The two table addresses in that dump differ by `0x334`, exactly the per-device block size the
shipped allocator requests, and backing off the `0x2CC` table offset places the blocks at `0xE6D`
and `0x11A1` - the first seven bytes past the end of object 7's static image (`0xE66`, measured),
the second exactly one stride further. *`[INF]`, from arithmetic that comes out exact in both
directions: they are the first two per-device blocks grown onto the tail of the segment, in
allocation order - the full-screen one first, which is why slot number does not follow allocation
order.*

### 4.4b A CVT entry number IBM's own prose gets wrong: `GetPhysBuf` is 272, not 275 - `[DOC-IBM]`

Recorded because the **wrong** number is the one a reader meets first: it sits in the function's
own `SUBROUTINE NAME` comment header, the most authoritative-looking text on the page, and the
same error is copied between two BVH trees.

**The prose says 275**, twice, in `svdh/bvhmain.c`'s `GetPhysBuf` header - *"LINKAGE: CALL FAR
( via BVS-DDI call vector table entry 275 )"* and *"ULONG Function ( Call vector table entry =
275 )"*. `vdh/vdhmain.c:1385,~~1391~~` [2026-10-01: `:1393`, checked against the DDK file] carries the identical pair, so it was **copied**, not typed
twice.

**Four independent sources say 272, and they win** (where documentation and implementation
conflict, the implementation is authoritative for behaviour):

| source | says |
|---|---|
| `vdh/vdh.h:283`, `svdh/bvhtype.h:827` | `#define FnGetPhysBuf 272L` |
| `inc/bvsparms.inc:187` | `fn_GetPhysBuf equ 110h ;272` - hex and decimal on one line |
| `svdh/bvhdata.c:155` | the dispatch table entry, annotated `(272) Get Phys Buff` |
| `svdh/bvhmain.c`, four lines below the comment that says 275 | `if ( ( Function == FnGetPhysBuf ) && ...` |

**And 275 is a real, different function** - `fn_SetVarInfo equ 113h ;275` (`bvsparms.inc:190`) -
so acting on the header would dispatch *Set Variable Info*. This is a wrong number, not a typo
for nothing.

**A third witness, at a tier neither doc nor header:** the shipped `DOSCALL1.DLL`'s
`BvsGetPhysBuf` issues `mov di,0x110` immediately before calling `AllVDH`. `110h` **is** 272, in
the instruction stream of a binary compiled from this source. `[OBS-RE]` Documented, coded and
executed all agree on 272; only the prose dissents.

> **The general point, which is why this is a section and not a footnote:** a DDK comment header
> is **documentation** and carries the documentation tier's failure mode, even though it is
> physically inside a `.c` file and reads like source. Proximity to code is not provenance.

### 4.4c What `GetPhysBuf` owes, and its complete error space - `[DOC-IBM]`

`svdh/bvhmain.c`, `GetPhysBuf`. The obligation: *"GetPhysBuf is called by BVS in order to obtain
an **LDT selector** by which to address the display buffer corresponding to the current mode or
the mode specified"*, EXIT-NORMAL *"AX = 0 / An LDT selector to the PVB is returned to caller"*.
The address is `pModes[Mode].BufferAddress` (or a caller-supplied range, validated against
`MIN_PVB_BOTTOM`/`MAX_PVB_TOP`), and the selectors are produced by `DevHlp_PhysToUVirt`, one per
64 KB, written back into the caller's `VIOPHYSBUF.asel[]`.

The **complete** set of things it can return:

| rc | when |
|---|---|
| `NO_ERROR` | selector(s) returned |
| `ERROR_VIO_PTR` | the preset - *"LDTSelector not passed"*; also the answer when the function code, packet length, `Flags > 1`, or the environment selector fail validation |
| `ERROR_VIO_INVALID_PARMS` | the caller's PVB address/length is out of range for this adapter |
| `PhysToUVirt`'s own rc | the mapping failed |

**Every one is a claim about the caller's parameters.** A real adapter always *has* a
`pModes[Mode].BufferAddress`, so IBM had no occasion to define a code meaning *"this machine has
no physical video buffer at all"* - and did not. Note also `Flags` is required to be `<= 1`, so
no foreground/background state is passed to this entry point; that arbitration happens in **BVS,
above the handler**, before `AllVDH` is reached.

### 4.5 The buffer model: LVB -> PVB

Each VIO session owns an **LVB** (Logical Video Buffer) - the cell/attribute array `VioGetBuf`
returns and all Vio writes update. The foreground session's LVB is mirrored into the **PVB**
(the physical buffer - B800:0 text memory for a full-screen text session); a background
session's writes touch only its LVB, and the PVB is refreshed from the LVB when the session
comes foreground ([DOC-IBM] Control Program Reference contract for `VioGetBuf`/`VioShowBuf`).
Inside BVS the mirroring worker is `LVBRectToPVB`, reached from the restore path (section 6.2) and
from `BufferUpdate`. Windowed-VIO sessions have the same LVB contract, but their "PVB" is a PM
window: the shield/AVIO path (section 5) paints the LVB through the graphics engine instead.

`VioGetPhysBuf`/`VioScrLock`/`VioScrUnLock` remain the full-screen app's sanctioned route to the
real physical buffer, with `SCREEN$` (section 3) underneath for selector materialization.

#### The FULL-SCREEN handler maintains BOTH buffers, and the parm block says which - `[DOC-IBM]`

It is easy to read section 4.5 as "windowed sessions have an LVB, full-screen sessions have the PVB".
They do not: a full-screen text session has **both**, and IBM's own full-screen handler is built
to write and read each of them. `vdhvga.lnk` names the fifteen modules BVHVGA is linked from
(DDK `video/src/video/vdh/`); three of them settle it:

- **`xgabufup.asm`**, the `BufferUpdate` entry, **rejects a call in which neither buffer is
  selected** - `test [si].Flags, PVB_SEL_BIT + LVB_SEL_BIT` / `.if <nz>`, otherwise
  `ERROR_VIO_INVALID_PARMS`. Its `SetGenParms` then loads `[bp].LVB_Sel` from the parm block's
  `LogicalBufSel` when `LVB_SEL_BIT` is on and zeroes `[bp].PVB_Sel` when `PVB_SEL_BIT` is off,
  so each buffer is independently addressable per call.
- **`xgawrite.asm`**: every write handler writes the LVB when `LVB_Sel` is non-zero and *then*,
  separately, writes the PVB when `PVB_Sel` is non-zero. `WriteCharStrAttr` is the clearest -
  a `rep movsw`/`lodsb`+`stosw` run into the LVB selector, then a second run into `PVB_Sel` at
  `[bp].PVBOff`.
- **`xgaread.asm`**: every read handler reads **from the LVB when the LVB flag is set**, and its
  own comments say "else read from PVB".

The two buffers are the same shape. `xgaread.asm`'s `FastBuffAddr` - the path taken when
`ParmLength == LogicalBufSel+2` for the cell/char functions, which `SetGenParms` signals by
returning carry set ("PVB format == LVB format == CGA format") - computes
`LVBOff == PVBOff` from the environment's `TextCols`/`TextRows`, with `PVBSkip = 0`. So for an
ordinary text mode the LVB is `TextRows * TextCols * 2` bytes of 2-byte CGA cells at offset 0,
byte-for-byte the layout of the physical buffer.

One caution on how far those three modules reach: **`vdhwndw.lnk` links `xgaread`, `xgascrol` and
`xgawrite` too**, so only `xgabufup` is specific to the full-screen handler. What the shared
modules establish is that *the handler code* honours whichever of the two bits it is given - they
say nothing about which bits a particular caller sends.

#### Column is tested before row - `[DOC-IBM]`, three independent code paths

`SetBuffAddr`/`FastBuffAddr` fix the **order** of the two coordinate errors: the COLUMN is tested
first (`ERROR_VIO_COL`, 359) and the ROW second (`ERROR_VIO_ROW`, 358). Note this is the *read*
path, in `xgaread.asm`, which both handlers link - so it is one path, not two. The cursor paths
are genuinely separate, one per handler, and both agree:

- **`vdhinfo.c`** - the module `vdhvga.lnk` lists second. **No other BVH under
  `video/src/video/vdh/` links it**: every sibling handler carries its own cursor module
  (`infcga`, `infega`, `inf8514a`, `idhinfo`, `infmpa`, `wdhinfo`). So it is the VGA handler's own
  cursor path, not one shared with the windowed handler. (The DBCS VGA-J build links it as well,
  `vdhvga2.lnk`/`vdhvga2i.lnk` - the same device family, so the scope is stated rather than the
  negative left absolute.) It validates set-cursor-position with `rc = ERROR_VIO_COL` on the column and then, under
  `if (!rc)`, `rc = ERROR_VIO_ROW` on the row. Its foreground branch carries an explicit
  `#if VDHVGA` arm (`HardwareColumns()` rather than `Environment->ModeData.col`).
- **`wdhinfo.asm`** `SetCursorInfo` - BVHWNDW's - preloads `ERROR_VIO_COL` and tests `vp_c_col`
  against `env_cols`, then preloads `ERROR_VIO_ROW` and tests `vp_c_row` against `env_rows`.

A caller passing both out of range is therefore told 359.

---

### 4.6 Cursor and blink are hardware, programmed through the CVT

Neither is a software overlay drawn by OS/2; both are adapter state that the handler programs on
the application's behalf, through OS/2-visible entry points.

- **Cursor** - `FnGetCursorInfo`/`FnSetCursorInfo` are **CVT 264/265**, carrying
  `VDH_CURSOR { Length, Flags, Row, Column, TopScanLine, BottomScanLine, Width, Attribute }`.
  `Flags` selects `CURSOR_POSITION` (2) and/or `CURSOR_TYPE` (4), with `UPDATE_HARDWARE`
  deciding whether the call reaches the registers now. That the destination is the real CRTC is
  explicit in the handler's own register image: `HWREGS.CRTCtlRegs.Regs` names `CursorStart`,
  `CursorEnd`, `CursorLocHigh` and `CursorLocLow` at their true offsets inside the 0x18-byte
  CRTC set - i.e. the shape/position contract maps onto CRTC registers 0x0A/0x0B/0x0E/0x0F.
- **Blink** - `VDH_VARIABLE.Blink`, behind flag `VARIABLE_BLINK` (0x02), one of the
  `SetVariableInfo` family alongside overscan, underscore, video-enable and the display mask.
  `BLINK_BIT` (0x08) is the attribute-controller enable bit - the hardware choice between
  "attribute bit 7 means blink" and "attribute bit 7 means bright background".

[DOC-IBM] IBM DDK `video/src/video/vdh/vdh.h`: CVT codes `:275-276`, `VDH_CURSOR` `:1313-1323`,
`HWREGS.CRTCtlRegs` `:1179-1189`, cursor flags `:694-696`, `VARIABLE_BLINK` `:698`,
`VDH_VARIABLE.Blink` `:1339`, `BLINK_BIT` `:748`.

**What is *not* in the contract is the part that matters most for anyone modelling this.** The
CVT carries blink *enable*, cursor *shape* and cursor *position* - and nowhere a rate, a phase,
or a "blink now" call. The on/off phase over time is generated by the CRTC from its own vertical
timing and never crosses into OS/2 at all. So a faithful model has two clocks with different
owners: *what* blinks and *where* the cursor sits change only when a program says so; *whether
either is lit this instant* is a property of the display hardware's refresh. [INF] - from the
absence of any rate/phase field across the whole cursor and variable-info contract, together
with the CRTC register mapping above; no IBM statement asserts it directly.

---

## 5. The three session video environments

A session's **type** - chosen at `DosStartSession` time (`STARTDATA.SessionType`: 1 full-screen,
2 windowable-VIO, 3 PM, 4/7 VDM) and reflected in `DosQueryAppType`/the LIS process-type - selects
which video environment BVS/PM builds for it:

| Session type | Handler / path | Output reaches the screen via |
|---|---|---|
| Full-screen VIO (SGIDs 4-15) | full-screen BVH chain (`BVHVGA`/`BVHSVGA`...) | LVB -> PVB (real B800 text memory) when foreground; hardware-state SaveEnv/RestoreEnv on switch |
| Windowed VIO (SGIDs 16-31) | `BVHWNDW` (+PMVIOP shield) | `BVSDINIT(0x44)` loads BVHWNDW [2026-10-01: first in the process that initialises the session manager, through `vf_ShellInit` (section 4.2); each further process in a windowed group loads it again at its first BVS call (section 4.4a)]; its `InitEnv` -> `ShieldInit` -> `PMVIOP.WinCreateConsole` creates the VioShield frame window; paints via AVIO `GreEntry5`/`BufferUpdate` into the PM screen like any window [OBS-RE, static import `BVHWNDW`->`PMVIOP.WINCREATECONSOLE` + live-driven chain] |
| PM (SGIDs 32-255, one shared screen group) | no BVH - the GRE/display-driver chain (section 7) | each process's own mapped VRAM aperture |
| Hard-error/popup (SGID 0), VIO popups (SGID 3) | BVS popup/save machinery (`VioPopUp`) over whatever is foreground | temporary screen takeover, restored by the same save/restore machinery |

(SGID ranges: [DOC-IBM] *OS/2 Debugging Handbook* glossary - 0 hard-error popups, 1 shell,
2 real mode, 3 VIO popup, 4-15 full-screen, 16-31 windowable VIO, 32-255 PM, all PM sessions
sharing one screen group.)
[2026-10-01: the per-type ranges in the table's first column do not hold on Warp 4.5, and nor
does "one shared screen group" for PM. On a running WSeB CP2 with the PM desktop up, session ids
were allocated from one sequential counter for every type (windowable VIO 17 and 18, PM 16 and
19, each PM session its own id), and `SIS_MaxScrnGrp` read 16. `infoseg.md`, "Measured on a live
Warp 4.5 system", `[OBS]` 2026-08-20. What decides the video path is the two-way boundary of
section 4.4a: an id at or below `SIS_MaxScrnGrp - 1` dispatches through the full-screen handler's
table, one above it through the windowed handler's. Read the ranges as the Debugging Handbook's
(Warp-3-era) description, not as the rule.]

**Note the shell screen group (SGID 1) is its own entry, distinct from the 4-15 full-screen
range** - the latter is for *user-started* full-screen sessions. A VIO `PROTSHELL=` therefore
runs in SGID 1 with a full-screen text environment, not in a 4-15 session. [INF: the SGID table
is [DOC-IBM], but that a VIO PROTSHELL's own screen group is 1 rather than a 4-15 allocation is
inferred from the table's own naming plus the observed `SG=01` for the shell process in the
Debugging Handbook's `.P` worked example - not from traced session-creation code.]


### 5.1 How a session's BVSCB / ENVB / LVB are reached from more than one process - `[DOC-IBM]` + `[INF]`

> **CORRECTED 2026-08-28 (Rule 1.7), same day, before anything was built on it.** The first version
> of this section was titled the same way but claimed **one** mechanism for all three objects:
> *"The segments are NAMED and per SCREEN GROUP"*, `[DOC-IBM]`, citing `bvsgBvscbName`. That
> citation names the **BVSCB only**, and IBM's own source contradicts the generalisation: the ENVB
> and the LVB are `DosAllocSeg(..., SEG_GETTABLE)` segments, and **no `\SHAREMEM\` name for either
> exists anywhere in the DDK** (exhaustive: the only such names under `base/inc` and `video/src` are
> `\SHAREMEM\BVS\BVS[sg]` and `\SHAREMEM\DOS\CDIB`). The error was over-generalisation from a
> real citation, and it is kept marked because the corrected answer below is *better* than the wrong
> one - IBM uses **two different sharing primitives**, and which one applies to which object is the
> whole content of this section.

**There are TWO mechanisms here, not one.** The BVSCB is shared by NAME; the ENVB and the LVB are
per-process allocations marked GETTABLE. Both end with the reader holding **its own selector**,
which is why neither produces a cross-process selector problem - but they get there differently, and
conflating them produces a design IBM does not have.

A screen group's video state is not private to the process that started the session. Any process
in that screen group - a child spawned by the session leader, an AVIO client, a popup - has to
reach the same BVSCB, ENVB and LVB. ~~IBM's mechanism is uniform and has three parts.~~
[2026-10-01: struck as left behind by the 2026-08-28 correction above, which replaced "one
mechanism" with two; the subsections below are the two mechanisms and how `seltable` joins them.]

#### Mechanism 1 - the BVSCB is NAMED, per SCREEN GROUP

[2026-10-01, added - BVS itself does this, for every screen group and every process, so the
model no longer rests on the `EPOCH`-only handler routine below. `DOSCALL1`'s `GetBVSCB` copies
`bvsgBvscbName` to its stack, patches the `sg` placeholder with the screen-group number as two
hex digits, and calls `DosAllocShrSeg` (`DOSCALLS` ordinal 35) for `bvsgBvscbSize` bytes into the
per-process instance cell `bvsi_bvssel`; if that fails it calls `DosGetShrSeg` (ordinal 36) on the same
name. A process that already holds a selector skips both. `[OBS-RE]` obj4 +0x13DC..+0x1463 with the
LX import fixups at +0x142A/+0x1439 resolved, read 2026-10-01; ordinal names `[DOC]` the osfree
ordinal reference. IBM's own statement of what the getter receives: *"The selector returned by
DosGetShrSeg is the same as the one returned by the DosAllocShrSeg call"* (`[DOC]` Control
Program Reference, `DosGetShrSeg` Remarks, as reprinted on EDM2).]

The BVS global data segment carries the name template

```
bvsgBvscbName   db      '\SHAREMEM\BVS\BVSsg',0 ;Name of BVSCB
```

`[DOC-IBM]` `bvscb.inc`, `bvsgdata STRUC`. The trailing `sg` is a two-character placeholder patched
with the screen-group number; the resulting object is an ordinary `\SHAREMEM\` named shared
segment. Alongside it the same structure keeps the screen-group-0 selectors explicitly
(`bvsgSg0Bvssel`, `bvsgSg0Envsel`, `bvsgSg0Lvbsel`) and a 256-entry `bvsgSelTable` of per-screen-group
selector-table offsets.

#### A process obtains its OWN selector, by NAME, and caches it per screen group

`Get_BVSCB` - `[DOC-IBM]` `xgascrol.asm` - is the whole mechanism in one routine. **Read the
conditional-assembly note after it before citing it**: the module is linked into both handlers, but
the routine is not compiled into both.

```asm
BvscbSel    DW  255 Dup (0)             ; Selector for BVSCBnn   (in the handler's _DATA)
BvsSegLabel DB  '\SHAREMEM\BVS\BVS'     ; BVSCB segment label

Get_BVSCB proc near
    lds si, [bp].EnvBufParm             ; the environment buffer
    mov ax, ds:[si].env_sessionNum      ; -> SCREEN GROUP NUMBER
    push _DATA / pop ds                 ; the handler's own per-process data
    mov si, OFFSET BvscbSel
    shl ax,1 / add si,ax                ; BvscbSel[screen group]
    .if <<word ptr ds:[si]> e 0>        ; nothing cached in THIS process yet?
        call BinToHx                    ; patch the label -> '\SHAREMEM\BVS\BVSnn'
        push ds / push bx               ;   far * name
        push ds / push si               ;   far * selector-save word
        call DOSGETSHRSEG               ; obtain THIS process's selector
    .endif
    ret                                 ; AX = BVSCB selector
```

So: the lookup key is the **screen-group number**, taken out of the environment buffer
(`env_sessionNum`, set by `InitEnv` from the session number it also hands `ShieldInit` - `[DOC-IBM]`
`wdhmain.asm`, `wdhequ.inc`); the store is a **per-process array** in the handler's own data
segment, `BvscbSel DW 255 Dup (0)`, one slot per screen group; and a cold slot is filled by
`DosGetShrSeg` on the well-known name. Nothing is inherited, handed over, or read out of another
process's memory.

**Scope of this routine - `IFDEF EPOCH`, and the flag is set for ONE of the two handlers.**
`Get_BVSCB`, the `BvscbSel` array, the `'\SHAREMEM\BVS\BVS'` label and the `env_sessionNum` field
itself all sit inside `IFDEF EPOCH`. In this DDK's `video/src/video/vdh/makefile` that flag is set
on exactly one build rule:

```
.asm{$(O)\wndw}.obj:
        $(AS) $(AFLAGS) $(AINC) -DVDHVGA=1 -DD1348=1 -DDBCSENBL=1 -DEPOCH=1 -DMSKK $<,$@;

.asm{$(O)\vga}.obj:
        $(AS) $(AFLAGS) $(AINC) -DVDHVGA=1 $<,$@;
```

So the **windowed** objects are assembled with `EPOCH` and the **full-screen** objects are not:
`xgascrol` is linked into both handlers (`vdhvga.lnk`, `vdhwndw.lnk`), but this routine is compiled
into `BVHWNDW` and compiled out of `BVHVGA`. Note also that the rule carries `-DMSKK` and
`-DDBCSENBL`, so this makefile is a DBCS-flavoured build; that `EPOCH` was also on for a US retail
BVHWNDW is **not established here**.

What this qualifies, precisely: the *by-name, per-process, lazily-cached* acquisition is documented
for the windowed handler in this tree. It is **corroboration** for the general model, not its
foundation - the two facts the model actually rests on, the screen-group-named segment and the
per-process instance data, are both unconditional (below, and `bvsgBvscbName` above).

#### Mechanism 2 - the ENVB and the LVB are per-process `DosAllocSeg` segments marked `SEG_GETTABLE`

[2026-10-01, on the heading: for the screen group's own ENVB and LVB - the ones `seltable`
holds - the allocator is BVS, not the handler, and the call is `DosAllocHuge`, not
`DosAllocSeg`. When a pair in the screen group's `seltable` record is empty, `GetBVSCB` asks the
handler for the sizes (`AllVDH` function `0x104`) and calls `DosAllocHuge` (`DOSCALLS` ordinal 40) with
`fsAlloc = 2` = `SEG_GETTABLE`, writing the selector **straight into the `seltable` record**.
When the pair is already filled it calls **`DosGetSeg` (ordinal 121) on the selector stored there**
(skipped when the per-process cell at instance-data `+0x2F8` is set, which `GetBVSCB` does only for screen group 3), `DosSizeSeg` (ordinal 126), and `DosReallocHuge` (ordinal 42) if the segment
is too small. It then copies the current configuration's pair into `bvsi_envsel`/`bvsi_lvbsel`.
`[OBS-RE]` obj4 +0x14D8..+0x1606, import fixups +0x150A, +0x1518, +0x153C, +0x1567, +0x158B,
+0x15B4 resolved, read 2026-10-01; ordinal names `[DOC]` osfree. The `CreateAvio` allocations
quoted below are the handler's AVIO presentation space, a different object. So `SEG_GETTABLE` is
right, and the getter is BVS.]

`CreateAvio` allocates the AVIO presentation space - a `wdhenvironment`, i.e. **the ENVB**
(`wdhequ.inc`: `env_viops`, `env_conhandle`, `env_processes`, the mode data) - like this
(`[DOC-IBM]` `avio.asm`, **no `IFDEF`**):

```asm
        mov     cx,size wdhenvironment
        push    cx                               ;length of PS + Shield/Gre Data
        push    ds                               ;recipient seg
        lea     ax,ds:[bx].ppbvs_pssel           ;recipient offset
        push    ax
        push    2                                ;  <-- SEG_GETTABLE
        call    DosAllocSeg
        ...
            mov     ds:[bx].addr_list[si],ax
```

and the LVB, a few lines later in the same routine, identically:

```asm
        push    ax                           ;length of LVB
        push    es                           ;selector for LVB seg recipient
        push    viops_Sel_LogicalVideoBuffer ;offset to receive LVB seg
        push    2                            ;  <-- SEG_GETTABLE
        call    DosAllocSeg
```

`SEG_NONSHARED EQU 0000H` / `SEG_GIVEABLE EQU 0001H` / `SEG_GETTABLE EQU 0002H` - `[DOC-IBM]`
`bsedos16.inc`. So neither object is named, and neither is created in shared memory: each is an
ordinary per-process segment **marked so that another process may obtain access to it**, which under
the `DosAllocSeg`/`DosGetSeg` model gives the recipient **its own selector** for the same storage.
(The full-screen VDH allocates with flag `0` = `SEG_NONSHARED` for its own buffers - `vdhmain.c`,
`vdhfont.c` - so gettability here is a deliberate property of the AVIO/windowed path, not a default.)

**What is NOT established:** a `DosGetSeg` call on the *main* ENVB is not in this tree.
[2026-10-01: established in `DOSCALL1`: `GetBVSCB` makes it, on the selector published in
`seltable` - see the note under this heading. The sentence stays true of the DDK's handler
source, which is all "this tree" covered.] The
`DOSGETSEG` uses present are all `@IBM J-DBCS_A`/`@IBM J-EPOCH_A` - the DBCS second LVB and the
EPOCH BVSCB. So `SEG_GETTABLE` on these two allocations is `[DOC-IBM]` and unconditional, and *that
some process actually gets them* is `[INF]` from the flag. BVS's own implementation
(`BVSMAIN`/`OS2CHAR`) is not in this tree, so its absence here bounds the BVH handlers only.

#### What `seltable` is FOR: discovery, with a per-PS lifetime - `[DOC-IBM]`

This is where the two mechanisms meet, and it is the part the first version of this section got
wrong. `ExtVIO` publishes the AVIO selectors into the screen group's `seltable`
(`[DOC-IBM]` `wdhmain.asm`, no `IFDEF`) - and note **`cx` is the per-process AVIO PS selector**
taken from `addr_list` a few instructions earlier:

```asm
                mov     es:[bx].ppbvs_bvssel,ax
                mov     es:[bx].ppbvs_pssel,cx
                mov     es:[bx].ppbvs_lvbsel,dx ;Local selectors for AVIO
                ...
                mov     ds:[di].selt_bvscb,ax
                mov     ds:[di].selt_envb,cx                       ;<-- per-process PS selector
                mov     ds:[di].selt_lvb,dx ;Update the BVS SelSeg
```

and `vf_DestroyPS` **zeroes the same three fields**, re-deriving the entry from the session number:

```asm
                                sub     bx,bx
                                mov     ds:[di].selt_bvscb,bx
                                mov     ds:[di].selt_envb,bx
                                mov     ds:[di].selt_lvb,bx
```

A set-on-CreatePS / clear-on-DestroyPS lifetime is **not** the lifetime of a table of stable
system-wide values; it is the lifetime of a *registration*. Read together with `SEG_GETTABLE`, the
coherent reading is that `seltable` tells an interested party **which segment to get**, and the
getter then derives its own selector ~~- not that a selector is published for another process to load
directly~~. `[INF]`, but it is the only reading under which both the gettable flag and the teardown
make sense.
[2026-10-01: the struck half is refuted, and the gettable flag does not need it. Under the
`DosAllocSeg`/`DosGetSeg` model **the published selector value is the one the getter uses**: IBM
says the allocating process *"must pass the selector of the segment to the recipient process
using some means of interprocess communication"* and the recipient passes that selector to
`DosGetSeg` (`[DOC]` Control Program Reference, `DosGetSeg` Remarks, as reprinted on EDM2).
`DOSCALL1`'s `GetBVSCB` does exactly that with the selectors in `seltable`: `DosGetSeg` on the
stored value, then that same value into `bvsi_envsel`/`bvsi_lvbsel` (`[OBS-RE]`, the Mechanism 2
note). So `seltable` is a registry of selector values, and "getting" one is a `DosGetSeg` on it,
not a derivation of a different selector.]

**A competing reading, stated so it is not buried:** that a shared-arena selector is numerically
identical in every process (the LDT is tiled, the index is a function of the linear address), so the
published value would be directly usable. That is true for objects in the shared arena - but these
two are `DosAllocSeg` segments, not shared-arena objects, so it does not rescue `selt_envb`
specifically. Anyone depending on a direct cross-process load of `selt_envb` needs the reader's own
code, which is not in this tree.
[2026-10-01: the reader's code is `DOSCALL1`'s `GetBVSCB`, and it does load the published value -
after `DosGetSeg` on it, not directly and not by the tiled-arena argument. See the note above.
`[OBS-RE]`]

#### Per-process selectors live in the handler's INSTANCE data, ~~and are never published for another process to dereference~~

[2026-10-01: the struck clause is contradicted two paragraphs below by the same routine writing
them into `seltable`, and BVS's `GetBVSCB` does dereference published `seltable` selectors in
another process after `DosGetSeg` (the Mechanism 2 note). `[OBS-RE]` + `[DOC-IBM]`]

`[DOC-IBM]` `bvscb.inc`, `bvhidata STRUC` - the BVH instance segment, one per process - holds the
selector set under IBM's own per-process prefix:

```
ppbvs_pssel     dw 0    ;PS selector for base vio
addr_list       dw 129 dup (0)  ;list of Avio PS segments
ppbvs_bvssel    dw 0    ;BVSCBsg Selector
ppbvs_lvbsel    dw 0    ;LVBsg Selector
ppbvs_gdtsel    dw 0    ;DOS Info GDT Selector
ppbvs_ldtsel    dw 0    ;DOS Info LDT Selector
...
bvsi_bvs        dw 0    ;WDH needs this      ; KEPT
bvsi_env        dw 0    ;                    ; TOGETHER
bvsi_lvb        dw 0    ;                    ; !!!!!!!!
```

and the windowed handler's `ExtVIO` fills them from a **per-process** source - **not** inside any
`IFDEF`; the nearest conditional in that file begins after these stores (`[DOC-IBM]`
`wdhmain.asm`):

```asm
les bx, gs:bvh_instance                 ; THIS process's instance data
mov cx, es:[bx][di].addr_list           ; per-process AVIO PS selector
mov ds, cx
mov ax, ds:[viops_Sel_BVSControlBlock]
mov dx, ds:[viops_Sel_LogicalVideoBuffer]
mov es:[bx].ppbvs_bvssel, ax
mov es:[bx].ppbvs_pssel,  cx
mov es:[bx].ppbvs_lvbsel, dx            ; "Local selectors for AVIO"
```

IBM's own comment on that store is **"Local selectors for AVIO"**, and the sibling store two
instructions later is commented **"Update BVS Instance data"**.

The same routine also writes those values into the screen group's `seltable` - see *What `seltable`
is FOR* above, which is where that publication is explained and bounded.

> **SUPERSEDED 2026-08-28 (Rule 1.7), hours after it was written.** This spot previously carried a
> reconciliation reading: *"That is only sound because a shared-arena selector is the same number in
> every process ... so the seltable is a registry of well-known values"*, with a corroboration note
> saying the code *"is self-consistent only under that reading (a per-process-varying selector in a
> system-wide table would be a live bug in shipped IBM code)"*. **The instruction three lines below
> the end of that quote block refutes it**: `mov ds:[di].selt_envb,cx`, where `cx` is the
> per-process AVIO PS selector the same passage annotates as such. IBM does put a per-process
> selector in that table; the `SEG_GETTABLE` + per-PS-teardown reading above is what makes that
> coherent. The tiled-LDT premises themselves are sound and are used above where they apply - to
> shared-arena objects, which these two are not. **The lesson is the stopping point: the quote ended
> exactly where the counter-evidence began.**

**The invariant this section actually supports - `[INF]`, synthesised from both mechanisms:** a
reader in another process ends up holding **its own selector** in every case IBM demonstrates -
by name for the BVSCB (`Get_BVSCB` -> `DosGetShrSeg`), by the gettable-segment model for the ENVB and
LVB. Nothing in the BVH source requires a process to load a selector value that another process
computed. That is the property, and it does not depend on the disputed reading above.
[2026-10-01: narrower than stated. For the BVSCB it holds and is now `[OBS-RE]` in BVS itself
(`DosAllocShrSeg`/`DosGetShrSeg` by name; IBM documents the returned selector as the same number
in every process). For the ENVB and LVB, BVS does load a selector value another process
allocated, after `DosGetSeg` on it - the documented `SEG_GETTABLE` protocol. The property is
"every process obtains *access* before it loads", not "no process loads another's selector
value". `[OBS-RE]` + `[DOC]`]

#### `selt_nextenvb`/`selt_nextlvb` do NOT chain processes - `[DOC-IBM]`; that they ~~chain~~ configurations is ~~`[INF]`~~ [2026-10-01: hold the further configurations' pairs, by position - `[OBS-RE]`, below]

`seltable` is easy to misread as a per-attachment chain, because its fields say "Master", "First"
and "Next":

```
; The seltable structure represents one entry in the selector table
;       which is allocated in BVSGSEG.  The header is the same size
;       as the pairs of ENVB/LVB selectors to allow easy addressing.
seltable        STRUC
selt_size       dw 0    ;size of this structure            ;@D549
selt_bvscb      dw 0    ;Master BVSCB selector             ;@S10
selt_flags      dw 0    ;Active config flags               ;@S10
selt_envb       dw 0    ;First master ENVB selector        ;@S10
selt_lvb        dw 0    ;First master LVB selector         ;@S10
selt_nextenvb   dw 0    ;Next master ENVB selector, if any ;@S10
selt_nextlvb    dw 0    ;Next master ENB selector, if any  ;@S10
seltable        ENDS
```

It is not. Every one of the *selector* fields carries the change tag `@S10` (`selt_size` is `@D549`,
a later rangeless-sessions change), and `bvscb.inc`'s own change log says what `@S10` was:

```
;@S10 = 05/11/89 STJ, Retain separate ENVB/LVB for each config, B701174
```

**"for each config"** - a *configuration* in BVS is an entry in `SET VIDEO_DEVICES=`, numbered one
and two (section 4, *A "configuration" is an entry in `SET VIDEO_DEVICES=`*), which is also why the
neighbouring field is `selt_flags` *"Active config flags"* and why the per-session BVSCB carries
`bvs_numconfigs` / `bvs_confignum` / `bvs_curconfig`. The struct's own header comment says the same
thing structurally - the entry is built out of *"the pairs of ENVB/LVB selectors"*, i.e. one pair
per configuration, laid out so the header and each pair are the same size for easy indexing.

So a second process attaching does **not** add a link to this chain - the refutation is solid, and
it is what this subsection is for.

**The replacement reading is weaker than the refutation, and the strongest evidence for both is a
negative result - `[OBS]`, recorded per the negative-results rule.** `selt_nextenvb` and
`selt_nextlvb` have **zero references in the entire DDK**: no read, no write, in any `.asm`, `.c` or
`.inc`. They are declared and never touched. That kills the per-attachment reading outright (nothing
chains them per attachment) and it equally means nothing chains them per *configuration* either -
so "one ENVB and one LVB per active configuration" is `[INF]` from the `@S10` change-log line plus
field adjacency, not something the code demonstrates.
[2026-10-01: BVS's own code does demonstrate it. `GetBVSCB` fills the record from `selt_envb`
onward in two-word pairs, one per configuration (`ILASTVDH` of them, or one for a windowed group),
and `BvsFree` frees the same run of words (`(bvsgSelTablesz + 2 - 6) / 2`). The fields have no
reader by *name* because BVS addresses them by position. So "one ENVB and one LVB per configured
device, in configuration order" is `[OBS-RE]`: `DOSCALL1` obj4 `GetBVSCB` +0x14D8..+0x15CB, read
2026-10-01; `BvsFree` +0x6E83, read 2026-09-30 (the teardown subsection below).] **Bound on that negative result:** BVS's own
implementation (`BVSMAIN`, `OS2CHAR`) is not in this tree, so "unused" covers the BVH handlers only,
not the system.

What is `[DOC-IBM]` here is narrow and worth keeping separate from what is inferred: the `@S10`
change was *"Retain separate ENVB/LVB for each config"*, and `selt_flags` is *"Active config
flags"*. What those two fields are actually used for by BVS is unestablished.

#### Teardown: for a windowed session the ENVB is the console's presentation space - `[OBS-RE]` + `[DOC-IBM]`

Read in Warp 4.5 DOSCALL1 and PMVIOP bytes and IBM's shipped windowed-BVH source, 2026-09-30.

**Allocation.** BVS's `GetBVSCB` allocates each configuration's ENVB and LVB itself (huge segments)
when the selector table entry has none. It passes them to the handler's `InitEnv` (CVT 257) as the
environment and as the parameter block's LVB selector.

**The windowed handler.** For a session whose type byte is `PROG_WINDOWABLEVIO` (2), the windowed
handler's `InitEnv` lays a `VioPresentationSpace` into the environment. It sets `viops_selLVB` to that
LVB selector and gives the environment to `WinCreateConsole` as the console's presentation space.
IBM's `RegSave` comment calls the environment selector *"PS selector"*. **The windowed console's VIOPS
is therefore the session's ENVB, and its LVB is the session's LVB.**

**Who frees what, at session end** (session type 2):
1. The session manager's child-exit path calls `VioFree`, which enters `BVSMAIN` with `vf_Free`.
   [2026-10-01, conditions the step omits: the child-exit path calls `VioFree` for session-type
   bytes 2 and 3; `VioFree` returns 402 unless the caller is one of the two session-manager pids,
   and enters `BVSMAIN` only when the target group's SGCB word `+0x58` is 0 (otherwise it clears
   that word instead). `[OBS-RE]` `DOSCALL1` obj4 `VIOFREE` +0x4E4B..+0x4F21, read 2026-09-30.]
2. `BvsFree` calls the handler's extended entry ~~with `vf_Free`~~.
   [2026-10-01: the call is `AllVDH` with function `0x114` (the extended entry) and is `[OBS-RE]`;
   that the handler then sees `vf_Free` as its sub-code is `[INF]`: `BVSMAIN` remaps only `AL` and
   leaves the code in `p_viofunc`, but the handler's read of it was not traced.]
3. The windowed handler frees only its DBCS work buffers. Its `ShieldTerm` calls `WinDestroyConsole`.
4. `WinDestroyConsole` posts message `0x333` to the console window. If the queue is full it sleeps
   250 ms and retries.
5. The console window procedure routes `0x333` through its close handling. It sends `0x91` to the
   subclassed task-manager window, and that procedure disposes of the console.
   [2026-10-01: conditionally. The `0x333` arm marks the console closing and releases focus, then
   calls the close handling only if a console word (`+0x108`) is non-zero or a console flag
   (`+0x6C` bit `0x04`) is set; the other branch was not read, so whether every session end
   reaches step 6 is not established. `[OBS-RE]` `PMVIOP` obj1 +0x173F..+0x175C, read 2026-09-30.]
6. The disposal frees the VIOPS's LVB, the NLS work buffer (if separate) and the VIOPS segment, i.e.
   the ENVB and LVB.
   [2026-10-01: in the arm where the console's session-type byte is 2 and its presentation-space
   pointer is non-null; it nulls that pointer first. `[OBS-RE]` `PMVIOP` `DISPOSECONSOLE`.]
7. `BvsFree` skips its own ENVB/LVB frees when `bvs_flags` has `bvs_f_window` or `bvs_f_avio`
   (`0x300`). It frees the BVSCB and the selector-table record unconditionally.

**Not established:** which code sets `bvs_f_window`.

---

## 6. The session manager's place in the video stack

The session manager (screen-group manager - `DOSSM*`/`DOSSG*` family, resident in
`DOSCALL1.DLL`, reached via the `SESMGR.DLL` forwarder) is the **orchestrator of screen
ownership**. It owns no video code of its own; it decides *when* the video layers save, restore,
and re-target, and drives them top-down. Four connection points:

### 6.1 Session creation

`DosStartSession` -> the request-block/`APPSENDREQUEST` pipeline -> session/SGCB creation, and -
per the session type - the matching video environment is established (a windowed-VIO session's
`WinCreateConsole` chain, a full-screen session's BVH environment). The SGCB itself carries
video-adjacent fields (a saved-buffer far pointer written by `VioSavRedrawWait` machinery at
`+0x4C`, the keyboard-focus handle at `+0x88`). Screen-buffer setup is **lazy** - session
creation writes bookkeeping (id/type/parent/name); the video side is populated on first use /
first foreground activation.

### 6.2 The switch: who calls whom

A foreground switch (`DOSSMSWITCH` -> `DOSSMSGSWITCH` -> `DOSSMGSWITCH` -> one of
`DOSSGSWITCHFOREGROUND`/`BACKGROUND`/`POPUP`) drives, in order [OBS-RE, symbol-verified chain]:

1. **Screen save/restore** - `VIOSAVREDRAWWAIT` (gate/record; also the *public*
   `VioSavRedrawWait` a full-screen app blocks on to be told "save now"/"redraw now", with
   `VioModeWait`/`VioModeUndo` as the mode-change sibling pair) and, on the incoming side,
   `DOSSGRESTORE` -> `VIORESTORE` -> `BVSMAIN(fn 0x42)` -> `BvsRestore` -> `RestoreCAS`/`RedrawCAS`
   walking the live console-area list and blitting LVB->PVB. At the handler level this is where
   the BVH's `SaveEnv`/`RestoreEnv` (CVT 258/259) fire - for a full-screen handler that includes
   **real hardware state**, i.e. switching between a full-screen text session and a PM session
   is a genuine hardware mode switch each way.
2. **Device notify** - `DOSSGDDNOTIFY` -> `KBDSWITCHFGND` (table-driven keyboard-focus handoff;
   the one device notified - mouse routes spatially, screen is passive per section 3).
3. **Scheduling** - foreground-priority boost propagation (kernel side,
   `_schSetScreenGroupFgnd` family).

### 6.3 The PM side of a switch: Death and Resurrection

When a full-screen session takes the screen from PM, the PM display driver receives **`GreDeath`**
(stop touching VRAM, accumulate bounds); when PM returns, **`GreResurrection`** - which
**re-executes the entire hardware mode set** (`VMISetMode` -> GRADD `GHI_CMD_SETMODE` -> VIDEOPMI
`SetMode` command lists -> re-map the aperture) and then PM repaints via ordinary `WM_PAINT`
broadcast into the same geometry. So the "switch back to the desktop" path is a full,
routinely-exercised mode-set - geometry never changes across it. [OBS-RE gre2vman
`Death`/`Resurrection` bodies.]

### 6.4 Hotkeys: how a switch is triggered from the keyboard

Producer side (always active, session-type-independent): **`KBDBASE.SYS`'s interrupt-level
`HotKeyCheck`** walks a 16-entry, 6-byte-per-entry `HotKeyTable` comparing scan/shift state; a
match posts the session manager's hotkey event instead of delivering the key. The table is
**configured, not hardcoded**, via `KBD$` category-4 IOCtl **function `0x56` (`SetSMHotKey`)** -
`{length-word, scan-word, hotkey-id}`; Ctrl-Esc and Alt-Esc are the two stock registrations.
[OBS-RE `KBDBASE.SYS` decompile + byte-decoded jump table; DDK kbd source names the mechanism.]
[2026-10-01: the table size and the IOCtl number are also `[DOC-IBM]`: `MaxHotKeyCt equ 16`
(`kbdddr.inc`), `HotKeyTable db MaxHotKeyCt * HKEntrySize dup (0)` (`kbddata.asm`), and
`dd SetSMHotKey ; 56h = Set Session Manager HotKey.` in the category-4 dispatch table
(`kbdioct.asm`), DDK `DBCS/SRC/DEV/KBD/KBDBASE/`. The 6-byte entry size and the stock
registrations were not re-checked.]

Consumer side - two shapes, per shell class:
- **PM shell**: PMMERGE registers the hotkeys itself (`SETKBDHOTKEY`, reached from
  `WIN16INITSESSIONMGR`->`WSHINIT` during PM session-manager init) and classifies them in
  `WINPROCESSHOTKEY` (WM_CHAR + `KC_SCANCODE`+`KC_ALT`) -> `REQUESTSWITCH`/`REQUESTSWITCHWAIT` ->
  the `DOSSMSWITCH` chain above.
- **Non-PM shell** (TSHELL-class): registers via the `KBD$` IOCtl directly and parks a thread on
  **`DosSystemService` (SysServSM)** - the kernel queue (`SMHotKeyQ`~~/`SMDosSessionQ`~~) the driver's
  hotkey event wakes - then calls `DOSSMSWITCH(0, target, 0, 0)` itself. [2026-10-12, Rule 1.7:
  `SMDosSessionQ` is not a hotkey queue. It is service 4's (`SysServVDM`) queue, whose only producer
  is a DOS program inside a VDM calling `DosStartSession`; the hotkey wait is subfunction 0 on
  `SMHotKeyQ` `[OBS-RE]`. See `session-manager.md`, "Where the hotkey thread sleeps" and "A DOS-type
  session start with no VDM".]

**A shell that registers no hotkeys and runs no consumer thread gets no session switching at
all** - the session-manager primitives are a library, not a service that runs itself. `CMD.EXE`
as `PROTSHELL=` is the degenerate case: a working prompt with no switching and no way to detach,
because nothing in the system is playing the switch-consumer role. [OBS-RE TSHELL import surface
+ the primitives' own call requirements; corroborated by CMD's import table containing no SESMGR
entries.]

### 6.5 Session-manager registration and the boot interlock

The session manager is *initialized by its client shell*, not autonomously:
- **`DOSSMINITIALIZE`** (16-bit-only internal, imported by name from SESMGR) registers the
  caller as the session-manager client: a 16-byte block whose two far pointers are stored
  unconditionally into SM globals (semaphore registration), and whose flag word at `+0x0E`
  selects the caller class - `0` = plain shell (TSHELL's value), `1` = PM (`PMMERGE`'s value:
  additionally resolves window-proc callbacks and sets the `[0xA51]` "base shell" authorization
  flag that gates `DOSSMGETSTATUS`/`DOSSMSERVEAPPREQ`/`WinCreateConsole` registration and
  friends).
- **`DOSSMSTART`** (13-word call: 7 zero words, far ptr to an inputs string, far ptr to an
  output buffer, 2 zero words - byte-verified identically in two unrelated shipped binaries)
  kicks off the first session; until it runs, even session 1 is not a valid
  `DosSelectSession` target (`ERROR_SMG_INVALID_SESSION_ID`). TSHELL's own inputs string is
  literally `"/K STARTUP.CMD"`.
- **Kernel interlock**: CONFIG.SYS `RUN=`/`CALL=` entries the kernel classifies as deferrable
  are started only after the kernel's second daemon pass **waits on `DosSMSysInit`** - the
  session manager's init-complete semaphore (the kernel's own panic string: "Error semwaiting
  on DosSMSysInit", `iniproc2.asm`). [OBS-RE `syi2StartDaemonProcesses`.] Which component posts
  that semaphore on a boot whose shell never initializes the session manager (a bare
  `PROTSHELL=CMD.EXE`) is **not established** - open question.

---

## 7. Regime D - PM: the actual text->graphics transition

The full stage-by-stage PM bring-up is its own reference; what belongs in the stack picture is
*where the mode switch lives* [OBS-RE, full trace of the shipped Warp 4.5 binaries]:

1. `PROTSHELL=PMSHELL.EXE` launches (kernel `syiStartShell`, the same `syiStartProgram`
   primitive as `RUN=`). Screen still text.
2. PMSHELL is trivial (~160 bytes of logic): `WinInitialize` -> `WinCreateMsgQueue` -> message
   loop. Loading it attaches PMMERGE (per-process init only). Screen still text.
3. **The first `WinCreateMsgQueue` in the system** runs the once-per-boot bootstrap:
   session-manager init (`Win32InitSessionMgr` -> `WIN16INITSESSIONMGR` -> `WSHINIT`, hotkey
   registration per section 6.4) -> `InitializeSystem` -> display-driver name from OS2.INI
   (`PM_DISPLAYDRIVERS/CURRENTDRIVER` - `GRE2VMAN` for the GRADD stack, or classic 16-bit
   `DISPLAY.DLL` on a VGA-configured install; **which driver is live is per-install INI
   configuration**) -> `DCInit`/`OPENDC32` create the screen DC, and the driver's one-time
   enable runs: `InitVMAN` -> `VMIInit` -> load `GRADD_CHAINS` -> `GHI_CMD_INIT` ->
   **`G2SetMode` -> `VMISetMode` -> GRADD `GHI_CMD_SETMODE` -> VIDEOPMI executing
   `\OS2\SVGADATA.PMI` command lists -> the hardware leaves text mode** -> `VHMapVRAM` (linear
   aperture) -> desktop creation and first `WM_PAINT`.
4. Resolution comes from OS2.INI `PM_DISPLAYDRIVERS/DEFAULTSYSTEMRESOLUTION`; there is **no
   supported live geometry change** - the shipped mechanism is "write the new configuration,
   restart PM" (`RESOLUTION_CHANGED=1` is consumed at the next PM start). The only runtime
   mode-sets the shipped system performs are same-geometry re-sets (Resurrection, section 6.3).

> **Read that narrowly: it is a statement about PM's *desktop geometry*, not about mode changes
> in general.** OS/2 changes video modes routinely and safely - a full-screen VIO app calling
> `VioSetMode`, and every full-screen<->PM session switch (section 6.2/section 6.3). What makes those safe is
> **screen ownership**: the mode belongs to whoever owns the screen, so a mode change happens
> while PM is dead (`GreDeath`) and other sessions are backgrounded writing only their LVBs, and
> the switch back restores PM's *same* geometry. Applications that need to know are told, through
> IBM's own notification pair **`VioModeWait`/`VioModeUndo`** (section 6.2) - the mode-change sibling of
> `VioSavRedrawWait`/`VioSavRedrawUndo`. The thing with no notification contract is narrower
> still: a *PM application* being told the desktop resized underneath it, which is exactly why
> that one case is a restart.

Two structural notes that follow from this:
- **Everything before step 3's driver enable is mode-neutral.** `WinInitialize`, DLL attach,
  even the SM registration change nothing on screen. The transition is driven by *display-driver
  enablement*, keyed to the first PM DC - not by process launch, not by session creation.
- **On a non-PM boot the entire regime-D machinery is simply absent** - VMAN/GRADD/VIDEOPMI are
  not loaded (verified live: `DosQueryModuleHandle("VMAN")` fails on a text-shell boot), and the
  once-per-boot PM heap/GRE-table init that the graphics chain depends on never runs (a
  non-PM-boot process calling into the chain traps in the PM heap allocator). Text mode is not
  "kept" by anything - it persists because nothing ever changes it.

---

## 8. Summary timeline

```
BIOS text mode 3
  | OS2LDR: uFSD, loads OS2KRNL ~~+ implicit base drivers (RESOURCE, CLOCK0x,
  |         SCREEN0x, KBDBASE xmachine-type) + MVDM VDD set~~   [section 1]
  |         [2026-10-01: the lists are in OS2LDR; which component loads
  |          them is not established, section 1.2 models A/B `[INF]`]
  | kernel init: (logo? dologo two-gate check -> mode 0x12 -> restore) [section 2]
  |         Alt-F1/boot keys: BIOS-level text UI              [section 2.2]
  |         base drivers INIT -> SCREEN$/SCREENDD$/KBD$/CLOCK$ exist [section 1.2/section 3]
  |         ~~base DLLs incl. DOSCALL1 (BVS inside) + BVSCALLS forwarder [section 1.3]~~
  |         [2026-10-01: DOSCALL1 (BVS inside) is loaded into the SYSINIT
  |          process (pid 1) by the kernel's ring-3 init, before DEVICE=
  |          INIT, not by kernel init (boot-sequence.md Stage 5a) `[OBS-RE]`]
  | CONFIG.SYS: BASEDEV/DEVICE categories ~~(boot messages still BIOS text)~~
  |         [2026-10-01: see the note below this block]
  |         SET VIDEO_DEVICES / VIO_* / DEVINFO=SCR recorded for later [section 4.3]
  | RUN=/CALL= (immediate ones); deferred ones wait on DosSMSysInit [section 6.5]
  | PROTSHELL= launches                                        [section 7.1]
  +--------------+----------------------------------------------
  | VIO shell    | PMSHELL
  | ~~first VIO  | first WinCreateMsgQueue:
  | call -> BVS   |   SM init + hotkeys -> InitializeSystem
  | lazy init,   |   -> driver per OS2.INI -> GHI_CMD_SETMODE
  | BVH chain    |   -> HARDWARE LEAVES TEXT MODE -> VHMapVRAM
  | loads;~~ text|   -> desktop -> WM_PAINT                      [section 7.3]
  | mode adopted,| full-screen session foreground:
  | never left   |   GreDeath + BVH RestoreEnv -> text mode
  | [2026-10-01: | back to PM: GreResurrection -> full re-SETMODE [section 6.2/6.3]
  |  see below]  |
```

[2026-10-01: two lines of this timeline are refuted by section 4.2a. **"Boot messages still BIOS text"**:
before DOSCALL1 is loaded boot messages are queued, not printed, and the first flush, in the SYSINIT
process before any `DEVICE=` driver, writes through DOSCALL1's `VioWrtTTY` into BVS (`[OBS]`, section 4.2a's
2026-10-01 note; the queue: `config-and-environment.md`, "How a boot-time message is rendered").
**"VIO shell: first VIO call -> BVS lazy init, BVH chain loads"**: BVS's first initialisation
happens in SYSINIT at that message, not in the shell. `BVSGLOBALINIT` running and the choice of
the re-select arm are `[OBS]` there; that the arm then loads and polls the handlers is `[OBS-RE]`
from the bytes, not captured (section 4.2a, section 4.3). [INF] A VIO shell's later calls then meet
`BVSDINIT`'s one-time guards already set (section 4.2). A PM shell's `0x44` call still runs its own arm.
Also see `boot-sequence.md` Stage 5a.]

---

## Sources

- **[DOC-IBM]** IBM DDK: `video/src/video/screendd/screen01.asm`, `screen02.asm` (SCREEN$/
  SCREENDD$); `video/src/video/svdh/bvhmain.c` + siblings (the SVDH chained BVH - DevEnable/CVT/
  InitEnv/SaveEnv/RestoreEnv contract); `video/src/video/pmvideo/xgabvh20/` (XGA BVH);
  `base/inc/bvscb.inc`/`bvsequ.inc`/`bvsparms.inc` (BVS control blocks);
  `video/src/video/vdh/vdh.h` (the BVHVGA-family handler header - CVT function codes,
  `VDH_CURSOR`/`VDH_VARIABLE`, the `HWREGS` CRTC register image; read 2026-08-22 for section 4.6);
  `video/src/video/vdh/vdhmain.c`/`vdhdata.h`/`vdhvga.def` (BVHVGA's `DevEnable`, the
  `VDHEntryPoint[]`/`ChainedCallVectorTable[]` pair and the `FIRST_INIT` guard),
  `video/src/video/vdh/wdhmain.asm`/`vdhwndw.def` (BVHWNDW's `DEVENABLE`, the
  `4*fn_BufferUpdate` bias, the `SIS_MaxScrnGrp`->`wdh_LastFS` boundary), and
  `video/src/video/vdh/vdhvga.lnk`/`vdhwndw.lnk` (the authoritative module lists for the two
  handlers - read these before attributing any module to a handler);
  `video/src/video/vdh/xgascrol.asm` (`Get_BVSCB`/`BinToHx`, the `BvscbSel[255]` per-process
  selector cache and the `'\SHAREMEM\BVS\BVS'` label - read 2026-08-28 for section 5.1; note the `.lnk`
  files put this module in BOTH `vdhvga` and `vdhwndw`); `base/inc/bvscb.inc` again for
  `bvsgdata`/`seltable`/`bvhidata` and its own change log (`@S10`, `@D549`), and
  `video/src/video/vdh/wdhmain.asm` again for `ExtVIO`'s `ppbvs_*` stores - both section 5.1;
  *Display Device Driver
  Reference for OS/2* (the `HTML/REF/DISPLAY` book: *Video Device Handler Identification*,
  *Video Device Chaining*, *A VGA and 8514A Scenario*, *Primary Display Identification*,
  *Loadable Device Drivers*, *DevEnable*, *InitEnable*); *Control Program Reference*
  (`VioGetConfig` `ConfigID`) - all read 2026-08-27 for section 4.4a;
  IBM Toolkit 4.5
  `bsedos.h` (STARTDATA/session types), `bsesub.h` (VIO/AVIO API); *OS/2 Debugging Handbook*
  SG24-4643 (SGID ranges, ordinal tables).
- **[OBS-RE]** Disassembly/decompilation of the shipped binaries (Warp 4.5 / WSeB CP2 vintage,
  matched `.sym` files): `os2ldr` (implicit-driver lists section 1.2, the pre-attributed
  "[four full blocks] OS/2" (CP437 0xDB x4) cell string section 1.1, both builds, read 2026-08-16); the shipped `\OS2LOGO` file
  (WSeB CP2 install media, header decoded and rendered section 2.1, 2026-08-16);
  `os2krnl` SMP debug (`dologo`/`h_syiSetVideoMode`/`syiBlastLogo`/`syiProcessALTF1File`,
  `syiStartShell`/`syi2StartDaemonProcesses`, string scans; 2026-08-06);
  `DOSCALL1.DLL` (`BVSMAIN`/`BVSDINIT`/`BVSGETVIDEOCALLTABLES`/`UINITGENERICVDH`/`VREADENVVARS`/
  `DOSDRIVERENABLE`/`AllVDH`/`BvsRestore` family, the `DOSSM*`/`DOSSG*` switch chain,
  `DOSSMINITIALIZE`/`DOSSMSTART`; 2026-07-29 -> 2026-08-16) + for section 4.4a, 2026-08-27:
  `symbols_va.txt` (`BVSGLOBAL`==`bvsg_calltables`@`+0x360`, `bvsg_flags`@`+0x3a0`,
  `bvsg_maxbase`@`+0x3aa`, `ILASTVDH`, `PSZDEVICESTRING`, `PSZWINDOWBVH`), the decompiles of
  `DOSLOADVIDEOHANDLER`/`FGETFREECALLTABLE`/`UGROWDEVGROUP`/`ULOADWINTHORNVDH`/`InitBVSCB`, and
  raw disassembly of `AllVDH` (obj4+0x1C03), `GetBVSCB` (obj4+0x14BD) and `BVSGLOBALINIT`
  (obj4+0x7C51), each re-verified against the object images rather than read off the decompile); `PMMERGE.DLL` + driver DLLs
  (the PM graphics lifecycle, Death/Resurrection, `WINPROCESSHOTKEY`; 2026-08-05/09);
  `TSHELL.EXE` (shell-side SM/hotkey usage; 2026-08-08/10); `KBDBASE.SYS` (`HotKeyCheck`/
  `SetSMHotKey` fn 0x56; 2026-08-09); `BVHWNDW.DLL` (windowed chain; 2026-08-06). Also
  KDB captures of the switch chain on real OS/2 (VirtualBox, WSeB CP2;
  2026-07-29/30) - the debugger is `[OBS-RE]` by the ratified definition, since
  reading state is an interpretation.
- **[OBS]** Captures from a running system, no interpretation: the non-PM boot
  driver-absence checks and the PM-heap trap (VirtualBox, WSeB CP2; 2026-08-10),
  and the cat-3 fn 0x75/0x76 `DosDevIOCtl` measurement in ~~section 4.2~~ [2026-10-01: section 3.1].
  2026-10-01 (section 4.2a, cited from section 0, section 2, section 4.2, section 8): two clean boots of WSeB 4.50 Rev 14.089, HStrict
  SMP debug kernel with the SMP `DOSCALL1.DLL`, one virtual CPU, under the kernel debugger with
  hardware breakpoints on `BVSDINIT`, `VIOWRTTTY`, `DOSPUTMESSAGE` and `BVSMAIN`. *(Split out of
  the [OBS-RE] entry above 2026-08-31, Rule 1.7: that entry folded live
  behavioural observation under a tag that means reading a binary.)*
- **[OBS-RE], 2026-10-01 validation pass** (Warp 4.5 UNI `DOSCALL1.DLL`, matched `.sym`, object 4
  bytes): `BVSMAIN` +0x1837..+0x18C7, `BVSDINIT` +0x78C4..+0x7981, `AllVDH` +0x1BAD..+0x1C2F,
  `GetBVSCB` +0x13D7..+0x160F with its import fixups resolved, `BvsInit` +0x131E..+0x1341,
  `BVSGETVIDEOCALLTABLES` +0x7DD9..+0x8280, `ULOADWINTHORNVDH`, `UINITGENERICVDH` +0x82F0..,
  `VIOWRTTTY` +0x3BF7..+0x3C47, and every store to obj7 `+0x97E`/`+0xAA9`; the resident-name
  tables of the shipped `BVHVGA.DLL` and `BVHWNDW.DLL`. DDK re-reads the same day:
  `vdh/vdhvga.def`, `vdhwndw.def`, `svdh/makefile`, `screendd/screen01.asm`/`screen02.asm`,
  `base/inc/bvsparms.inc`, `bvscb.inc`, `vdh/vdh.h`, `KBDBASE` `kbdddr.inc`/`kbddata.asm`/
  `kbdioct.asm`.
- **[DOC]** Published third-party documentation, used only where marked: PMView's
  "OS/2 Boot Logo (LGO)" help page and the Just Solve the File Format Problem wiki entry
  (the logo format's plane/EXEPACK2 structure - independently confirmed here by decode - and
  the Warp 3 640x400 / 80-line copyright reservation, which is **not** independently verified,
  no Warp 3 logo file having been decoded). Added 2026-10-01: the Control Program Reference's
  `DosGetSeg` and `DosGetShrSeg` Remarks as reprinted on EDM2, and the osfree ordinal reference for
  the names of `DOSCALLS` ordinals 35, 36, 39, 40, 42, 121 and 126 (section 5.1).
- **[OBS-USER]** Firsthand long-term observation of real OS/2 boots by the author, used in section 2.1 only (the corner signature's appearance, demand-driven logo
  teardown, the 640x400 recollection, and the "no-logo text screen looks non-standard" report
  that remains unexplained). Recorded as its own tag because it is neither IBM documentation
  nor binary RE, and an earlier revision wrongly filed it under [OBS-RE].
- **[INF]** marked inline: the 01/02 machine-type selection mechanism; which component loads
  the implicit drivers (models A/B, section 1.2); the DosSMSysInit poster on a non-SM boot (open);
  that cursor/blink *phase* is CRTC-generated and has no OS/2-visible contract (section 4.6 - argued
  from the absence of any rate or phase field across the cursor and variable-info contract).

## See also

`boot-sequence.md` (the twelve boot stages this doc's regimes overlay), `vio-kbd-mou.md` (the
VIO/KBD/MOU API contract and LVB details), `session-manager.md` (session model, SGCB internals,
switch-list/titles), `pm-graphics.md` (GPI/GRE/driver draw path), `drivers.md` (PDD/BVH/IFS
driver ABIs), `dive-video.md` (the DIVE direct-access video API), `infoseg.md`
(`SIS_CurScrnGrp`/foreground fields).
