# OS/2 Driver ABIs - Physical Device Drivers and Installable File Systems

The contracts a physical device driver (PDD) and an installable file system (FSD) present to the
OS/2 kernel. PDDs load at boot-sequence Stage 6 (`DEVICE=`), FSDs at Stage 7 (`IFS=`).

Provenance: **[DOC-IBM]** IBM DDK PDD reference book (Physical Device Driver Reference, HTML `REF/PDD`),
IFS entry-point / FSHelper headers `fsd.h` / `fsh.h`, request-packet / device-header headers
`reqpkt.h` / `devhdr.h`, `devhlp.inc`, and the version-correct Toolkit `bsedos.h`;
**[OBS-RE]** RE of shipped drivers and file systems for details the DDK samples cover thinly.

*Ratified (2026-07-26): checked against the IBM DDK Physical Device Driver Reference (`REF/PDD`
HTML pages), the DDK headers `devhdr.h`, `reqpkt.h`, `fsd.h`, `fsh.h`, the OS/2 kernel export map
(`os2krnl{b,r,d}.map`, debug17 toolkit), and Toolkit 4.5 `bsedos.h`. Every PDD device-header field,
the ES:BX Strategy ABI, the request-packet header + strategy command codes, the FS_\* entry set, and
the FSHelper family were confirmed in an IBM primary and tagged inline below. Two items could not be
matched to a distinct IBM primary and are noted where they appear: the "DS = driver data segment" on
Strategy entry (ES:BX confirmed, DS convention not separately located) and the remote-FSD
"ERROR_NOT_SUPPORTED from FS_MOUNT" behavior (the FSA_REMOTE distinction itself is in `fsd.h`).*

## Physical Device Drivers (PDD)

### Device header [DOC-IBM]
A PDD begins with a **device header**: a link to the next device, the **device attribute word**
(character vs block, IOCtl support, etc.), the offset of the **Strategy** routine, the offset of the
IDC entry, and the **`\DEV\` device name** (8 characters, e.g. `SINGLEQ$`). The kernel resolves a
`DosOpen("\DEV\NAME")` against these names - a device name takes precedence over a like-named file.

Confirmed field-for-field in the DDK header `devhdr.h` (`struct SysDev`: `SDevNext` next-header
pointer, `SDevAtt` attribute word, `SDevStrat` strategy offset, `SDevInt` second entry-point offset,
`SDevName[8]`, then prot/real-mode CS/DS) and, for the OS/2 2.0+ level-3 form, `struct SysDev3` which
appends the `SDevCaps` capability DWORD; and in the IBM Physical Device Driver Reference, which
documents each field on its own page: "Pointer to Next Device Header" (`REF/PDD/00021`), "Device
Attribute" (`REF/PDD/00022`), "Offset to Strategy Routine" (`REF/PDD/00023`), "Offset to IDC Entry
Point" (`REF/PDD/00024`), and "Name or Units" (`REF/PDD/00025`). The attribute word's bit 15 (CHR) is
the character-mode bit and bit 14 (IDC) indicates the IDC-entry offset is set (`REF/PDD/00022`); the
device-name-beats-file-name precedence rule is stated explicitly under "Name or Units"
(`REF/PDD/00025`). Note the second entry-point offset is named the **IDC entry point** in the PDD
Reference (`00024`) but the **interrupt entry point** (`SDevInt`) in the C/ASM headers `devhdr.h` /
`reqpkt.h` (`DDHDR.InterruptEP`) - same field, two IBM names. [DOC-IBM]

### Which executable containers `DEVICE=` accepts [OBS-RE - measured]

The same 16-bit character driver (header first in its data segment, Strategy entered with `ES:BX`,
INIT returning status 0100h) was named on a `DEVICE=` line in four link forms, one boot each, on a
Warp 4.5 retail kernel (Warp Server for e-business, FAT16 boot volume). The evidence was a log line
the driver's own INIT wrote, and a `DosOpen` of its `\DEV\` name run from `STARTUP.CMD`:

| Container | Result |
|---|---|
| NE with the library flag (OpenWatcom `system os2_dll initglobal`) | **installed** - INIT ran, the device opened (rc 0) |
| LX, module type physical device (`E32MODPDEV`, 0x20000) behind an MZ stub (`format os2 lx physdevice`) | **installed**, identical |
| the same LX with **no MZ stub** (`option nostub`; "LX" at file offset 0, the shape `OS2DASD.DMD` ships in) | **installed**, identical |
| the same objects as LX module type DLL (`E32MODDLL`, 0x08000) | **refused** - INIT never ran, `DosOpen` returned 3; the boot continued |

So a bare LX is a legitimate driver container, and the kernel selects on the LX module-type field
(`executable-formats.md`). A tool that reads driver files must accept an image with no DOS stub.
Not established by this test: whether the virtual-device type (0x28000) is also refused, and which
`SYS` message the refused case printed.

### The Strategy routine ABI [DOC-IBM]
The kernel calls a PDD's Strategy routine by a **far call with `ES:BX` -> a request packet** (a 16:16
pointer), with **DS = the driver's data segment**. This is a register ABI, not a stack-frame call.

The `ES:BX` -> request-packet convention is stated verbatim in the IBM Physical Device Driver
Reference, "Physical Device Driver Strategy Commands": *"The physical device driver strategy routine
is called with ES:BX pointing to the request packet"* (`REF/PDD/00100`). [DOC-IBM]  (The "DS = the
driver's data segment on entry" part is the standard PDD register convention but was not matched to a
distinct IBM reference page during ratification - treat that sub-clause as [OBS-RE] pending a source.)

### Request packet [DOC-IBM]
The request packet opens with a fixed header - packet length, unit code, **command code**, and a
**status word** the driver writes back - followed by command-specific fields. Command codes cover
INIT, media check, build-BPB, read / write / verify, IOCtl, open / close, and de-install. IOCtl
requests carry the `DosDevIOCtl` category and function (see `dasd-volume.md` for the disk categories).

Confirmed against the DDK header `reqpkt.h`: the request-packet header `struct _RPH` is exactly
`{ UCHAR Len; UCHAR Unit; UCHAR Cmd; USHORT Status; UCHAR Flags; UCHAR Reserved_1[3]; PRPH Link; }`
(packet length, unit, command code, then the 16-bit status word the driver writes back - status bits
`STERR` 0x8000, `STDON` 0x0100, error code in the low byte). The command codes are enumerated as
separate strategy-command pages in the PDD Reference: `0h` INIT (`REF/PDD/00103`), `1h` MEDIA CHECK
(`00108`), `2h` BUILD BPB (`00113`), the read / write / write-verify commands, `10h` GENERIC IOCtl
(`00148`), open / close, and `14h` DEINSTALL (`00164`). IOCtl requests carry `Category` and `Function`
in the packet - `struct _RP_GENIOCTL` in `reqpkt.h` (`RPH rph; UCHAR Category; UCHAR Function;
PUCHAR ParmPacket; PUCHAR DataPacket; USHORT sfn; ...`). [DOC-IBM]

### Services and storage [DOC-IBM]
Drivers call the kernel through **DevHlp** (`kernel-services.md`). Storage adapter drivers (ADD) use
the **IORB** (I/O Request Block) interface and the Resource Manager rather than the classic request
packet.

### The PDD-lifecycle DevHlp calls - registration, IRQ, block/run [DOC - EDM2]
The subset of DevHlp a PDD uses across its own lifecycle (registering itself, hooking an interrupt,
and blocking/waking threads). See `kernel-services.md` for the full DevHlp catalog - only these
lifecycle/ABI calls are detailed here. Each is invoked the same way: the DevHlp code goes in `DL`,
then `CALL [Device_Help]`; unless noted, success is carry-clear / return 0.

**Registration.**
- `DevHelp_RegisterPDD(NPSZ PhysDevName, PFN HandlerRoutine)` - registers a PDD name and its handler
  entry point. Entry: `DS:SI` -> ASCIIZ name, `ES:DI` -> handler. If `ES:DI` is NULL (`0:0`) the call
  *removes* the registration instead; the registered name need not match the string in the device
  header. [DOC - EDM2 "DevHelp_RegisterPDD"]
- `DevHelp_RegisterDeviceClass(NPSZ DeviceString, PFN DriverEP, USHORT DeviceFlags, USHORT DeviceClass, PUSHORT DeviceHandle)` -
  at initialization, registers an adapter device driver's (ADD's) direct-call command-handler entry
  point. `DeviceString` is max 16 chars; for an ADD `DeviceFlags` = 0 and `DeviceClass` = 1. Returns
  a device handle (asm: `DS:SI` -> name, `AX:BX` -> command handler on entry, `AX` = ADDHandle out); on
  failure `AX = ERROR_NOT_ENOUGH_MEMORY` when the class number is out of range or the class table is
  full. The asm entry is spelled `DevHlp_RegisterADD`. [DOC - EDM2 "DevHelp_RegisterDeviceClass"]

**Hooking a hardware interrupt.**
- `DevHelp_SetIRQ(NPFN IRQHandler, USHORT IRQLevel, USHORT SharedFlag)` - binds an IRQ (level 0-0Fh)
  to the PDD's interrupt handler; `SharedFlag` 0 = exclusive, 1 = shared. Entry: `AX` = handler
  offset (in `CS`), `BX` = IRQ level, `DH` = shared flag; `DS` must be the driver's data segment.
  Fails (carry set) if the level is out of range, if it is already owned incompatibly (a shared
  request while another owns it not-shared, or a not-shared request while any owner exists), or if it
  is IRQ 2 (the slave-8259 cascade). Sharing is not supported on all systems. A
  `DevHlp_RegisterStackUsage` call should accompany each SetIRQ. [DOC - EDM2 "DevHelp_SetIRQ"]
- `DevHelp_UnSetIRQ(USHORT IRQLevel)` - removes the handler for an IRQ the caller owns; `DS` must be
  the driver data segment on entry (asm: `BX` = IRQ number). Carry set / error if the caller is not
  an owner of that IRQ. [DOC - EDM2 "DevHelp_UnSetIRQ"]

**Blocking, waking, and deferred task-time work.**
- `DevHelp_ProcRun(ULONG EventId, PUSHORT AwakeCount)` - the companion to `ProcBlock`: wakes every
  thread blocked on `EventId` and returns the count awakened (asm: `AX:BX` = event-id high:low in,
  `AX` = count out). It returns immediately - the woken threads run at the next opportunity - and is
  often called at interrupt time. [DOC - EDM2 "DevHelp_ProcRun"]
- `DevHelp_AllocateCtxHook(NPFN HookHandler, PULONG HookHandle)` - allocates a *context hook* for a
  PDD that needs task-time processing but has no task-time thread; the returned handle is later passed
  to `ArmCtxHook`. When the armed hook fires, the handler is entered with `EAX` = the value supplied
  to `ArmCtxHook` and `EBX` = `0FFFFFFFFh`; the handler must save/restore its own registers, cannot be
  preempted, and must reside in the same segment as the `AllocateCtxHook` call. `DS` = driver data
  segment on entry. Error `ERROR_INVALID_PARAMETER` (87). [DOC - EDM2 "DevHelp_AllocateCtxHook"]

**Character queue and event signalling.**
- `DevHelp_QueueInit(NPBYTE Queue)` - initializes a character-queue structure and must be called
  before any other queue operation. The PDD first allocates a `QUEUEHDR { USHORT QSize; USHORT
  QChrOut; USHORT QCount; BYTE Queue[1]; }` and sets `QSize`; `Queue` is a near (DS-relative) pointer.
  No return code. [DOC - EDM2 "DevHelp_QueueInit"]
- `DevHelp_SendEvent(USHORT EventType, USHORT Parm)` - signals the occurrence of an event to the
  kernel/session manager (asm: `AH` = event, `BX` = argument; carry set on error). Defined event
  numbers: 0 = session-manager hot key from the mouse, 1 = Ctrl+Break, 2 = Ctrl+C, 3 = Ctrl+NumLock
  (arg = foreground session number), 4 = Ctrl+PrtSc, 5 = Shift+PrtSc, 6 = session-manager hot key
  from the keyboard (arg = Hot Key ID, set via the "Set Session Manager Hot Key" IOCtl function 56h),
  7 = reboot key sequence. [DOC - EDM2 "DevHelp_SendEvent"]

## Hardware auto-detection at boot: BASEDEV snoopers and the Resource Manager

*Added 2026-08-02, sourced from the IBM DDK: `REF/PDD` HTML pages 00321/00326/00329/00331/00385-93/
00538-41/00628-29/00636-39 (Resource Manager / RMCALLS.LIB / RMINFO.DLL / Auto Detection Services /
`RMCreateDetected` / snoop-level calls), `EXE/COMBASE/DDK/base/h/rmbase.h` + `rmcalls.h` (structures
and constants), and the shipped DDK sample driver + its README:
`EXE/MMPMDD/DDK/base/src/snooper/mme/pas16/` (`pas16snp.c`, `readme.txt`) - a real, buildable `.SNP`
snooper for the Media Vision Pro AudioSpectrum 16 card. [DOC-IBM]*

**What a `.SNP` is.** A **snooper** is a real, distinct `BASEDEV=` load-order category (`.SNP` is
first in the documented extension order `.SNP .BID .VSD .PDD .I13 .ADD .FLT .DMD`) - **not** a
BIOS/INT13 shim. Per the DDK sample's own README: *"Snoopers are 16-bit ring 0 device drivers
(basedevs) that run only at driver init time."* A snooper's whole job is legacy-ISA hardware
**auto-detection**, done once at boot, before the real driver for that hardware loads. In the
Resource Manager's own driver-type taxonomy (`rmbase.h`) a snooper is `DRT_SERVICE` (7) /
`DRS_SNOOPER` (1) - a distinct role from storage/char/block/network/video/audio driver types.

**The boot-time detection sequence** (DDK sample README, verbatim mechanism description):
1. On boot, the kernel loads the Resource Manager (`RESOURCE.SYS`).
2. The Resource Manager reads a list file (the README calls it both `SNOOP.LST` and
   `SNOOPER.LST` in different places - not resolved which is the shipped name) out of `\OS2\BOOT\`
   and runs each named `.SNP` in the order listed.
3. Each snooper: (a) speculatively allocates the I/O ports/IRQ/DMA it needs to *probe* the device
   (`RMAllocResource`), (b) determines whether the device is actually present, and (c) if found,
   registers the detected device and permanently reserves the **real** driver's bus resources with
   the Resource Manager (`RMCreateDetected(hDriver, &hDetected, &DetectedStruct, pResourceList)`,
   confirmed at `pas16snp.c:749`) - so the real PDD that loads later never has to probe hardware
   itself, and IRQ/DMA/port conflicts between legacy ISA cards are resolved before any real driver
   touches hardware.
4. Only after **all** listed legacy-ISA snoopers have run does the Resource Manager run the PCI
   bus enumerator, then the ISA-PnP enumerator - snoopers are specifically for the non-enumerable
   legacy-ISA case; PCI/PnP hardware identifies itself and needs no snooper.

**Detected-data structure and persistence.** A found device is recorded in a `DETECTEDSTRUCT`
(`rmbase.h`): an ASCII description name, `IDType` (`RM_IDTYPE_EISA`/`_PCI`/`_LEGACY`/`_RM`),
`DeviceID`/`FunctionID`/`CompatibleID`, an adjunct list, vendor ID, and serial number. Detection
results can be **persisted across boots** via `RMSaveDetectedData`, which writes `PREVIOUS.DAT`;
on a later boot, if `PREVIOUS.DAT` exists, the saved snoop values are reused instead of re-running
every probe (`REF/PDD/00628`). The **risk level** a snooper is allowed to probe at is itself
configurable per-boot: `RMGetSnoopLevel`/`RMSetSnoopLevel` take a `SNOOPLEVEL` enum -
`SNP_NO_RISK`, `SNP_LOW_RISK`, `SNP_MEDIUM_RISK`, `SNP_HIGH_RISK`, `SNP_WARP_RISK` - with
`SNP_FLG_DEFAULT`/`SNP_FLG_NEXTBOOT` flags controlling whether a level change is permanent or
one-boot-only (`rmbase.h:743-746`); this exists because some legacy-ISA probe sequences carry a
real risk of hanging or misconfiguring hardware that doesn't respond as expected, so the user (or
an install program) can dial detection aggressiveness up or down. `RMVIEW.EXE /dc` is the shipped
tool for inspecting what a boot actually detected.

### The other BASEDEV extensions: `.BID`/`.VSD`/`.TSD` are LADDR, a superseded pre-Warp storage
driver model [DOC - online, cross-checked, no IBM DDK primary found]

*Added 2026-08-02. No DDK header or DDK HTML reference page found for `.BID`, `.VSD`, or `.TSD`
(checked: full-tree grep of the DDK, the Warp 4.5 toolkit, and the IBM developer connection CDs
found zero hits for any of the three). This section is sourced from two independent online
references instead - os2museum.com ("Ladders and Dragons", Michal Necasek - a recognized OS/2
historian, checked directly) and an EDM2-derived BASEDEV-load-order mirror
(`lueersen.homedns.org/!Config_sys_docu`, cross-checked against a search-engine-surfaced quote of
EDM2's own "LADDR" glossary page, EDM2 itself unreachable this session - anti-bot-blocked). Treat as
**[DOC], online-sourced** - solid corroborated history, not an IBM primary, no DDK confirmation.*

**LADDR** ("Layered Adapter Device DRiver" per os2museum, announced June 1990, codeveloped by
Microsoft/Compaq/Adaptec/NCR/Western Digital) was a **pre-Warp, Microsoft-era storage driver
architecture** - retrofittable to OS/2 1.2, standard in MS OS/2 1.3 (bundled with LAN Manager 2.1).
It is a four-layer stack, each layer a distinct BASEDEV extension:
- **IOS (I/O Supervisor)**, `IOS1X.SYS` - the top layer, supervises all I/O operations.
- **`.TSD` (Type-Specific Driver)** - one per storage device *category*: `DISK.TSD`, `CDROM.TSD`,
  `TAPE.TSD`.
- **`.VSD` (Vendor-Supplied Driver)** - the middle layer where a vendor adds value or compensates
  for hardware quirks; not one-per-vendor-adapter-family in the strict IHV sense but one-per-
  vendor-value-add, e.g. `FT.VSD` (fault tolerance), `FATCACHE.VSD` (enhanced caching), and a
  special "SCSI'izer" VSD that translates generic logical operations into SCSI Command Descriptor
  Blocks for the layers below it.
- **`.BID` (Bus Interface Driver)** - the bottom layer, hardware/bus-specific: `ESDI-506.BID`,
  `AHA154X.BID`, `AHA1574X.BID`, `CPQARRAY.BID`, `DPT201X.BID`, `WD7000EX.BID`.

**Superseded by the OS/2 2.0+ DASD model** (this file's "Physical Device Drivers" section 2.5 storage
layering, `dasd-volume.md`): OS/2 2.0 replaced LADDR with "a model somewhat similar to LADDR"
(os2museum) built from `OS2DASD.DMD` (the generic layer, analogous to `.TSD`) + `.ADD`
(hardware-specific, analogous to `.BID` - e.g. `IBM1FLPY.ADD`, `IBM1S506.ADD`) + `IBMINT13.I13` as a
BIOS-based fallback. `.I13` is separately confirmed against an IBM primary - `IBMINT13.I13` appears
by name in an IBM support document (`warptips.doc`, IBM developer connection archive) which also
confirms `.I13` genuinely is the INT13-BIOS disk-driver category.

**The documented BASEDEV load order** places `.BID`/`.VSD`/`.TSD` between `.SYS` and `.ADD`
(`.SYS .BID .VSD .TSD/.PDD .ADD .I13 .FLT .DMD`) - two independent online sources agree on the
extension set and relative order but disagree on whether `.PDD`/`.TSD` sits in that slot and on
`.I13`'s exact position relative to `.ADD`; not resolved this pass, flagged rather than guessed.
By the Warp era essentially no shipping driver used `.BID`/`.VSD`/`.TSD` - the extension categories
are recognized by the BASEDEV loader for backward compatibility, but real Warp-era hardware support
ships as `.ADD`/`.DMD`/`.FLT`.

## Platform Specific Drivers (PSD) - SMP CPU/interrupt bring-up

*Added 2026-08-02. Provenance is mixed-tier, strongest first: **[OBS-RE]** direct binary inspection
of eight real, shipped OS/2 SMP `.PSD` files (`ALR`, `CAVERUN`, `CRLLRY`, `OS2APIC`, `PROLIANT`,
`TRICRD`, `V1_EBI2`, `WYSE` - the standard `\OS2\BOOT\` set on an OS/2 SMP install) - `strings`
against each reveals its exported `PSD_*` function-table symbol names directly; **[DOC-IBM]** the
real IBM SMP DDK header `smptkv3/toolkit/inc/devhlp.inc:77` (`DHGETDOSV_PSDFLAGS EQU 19 ; Get the
PSD's flags`, marked SMP-only, IBM developer connection archive); **[DOC]** komh.github.io/os2books/
smp (an OS/2 SMP DDK reference republished by a long-standing OS/2 developer, reads as a
transcription of IBM's own SMP DDK chapter on PSDs, not independently confirmed as verbatim IBM
text - treat as online-sourced, not an IBM primary, though every claim below is independently
corroborated by the [OBS-RE]/[DOC-IBM] tiers). This corrects `config-and-environment.md`'s prior
unsourced gloss of `PSD=` as "protected-mode swapper device" - wrong; the scan-order *position*
(first, before `BASEDEV=`) was already right, only the acronym expansion was wrong.*

**What a PSD is.** A **Platform Specific Driver** is OS/2 SMP's hardware-abstraction layer for
multiprocessor bring-up - "similar in concept to (but much simpler than) the Windows NT HAL"
(komh.github.io) - covering exactly four responsibilities, confirmed by the real exported symbol
names in every `.PSD` binary: **initialization/installation** (`PSD_INSTALL`, `PSD_DEINSTALL`,
`PSD_INIT`), **processor management** (`PSD_PROC_INIT`, `PSD_START_PROC`, `PSD_GET_NUM_OF_PROCS`,
`PSD_SET_PROC_STATE`), **hardware interrupt management** (`PSD_IRQ_REG`/`PSD_IRQ_MASK`/
`PSD_IRQ_EOI`, `PSD_SET_ADV_INT_MODE`/`PSD_RESET_MODE` - switching the platform's interrupt
controller between legacy 8259 PIC mode and APIC/"advanced" mode), and **interprocessor
communication** (`PSD_GEN_IPI`, `PSD_END_IPI` - generating/acknowledging inter-processor interrupts
to kick a secondary CPU into action). `PROLIANT.PSD` additionally exports `PSD_PORT_IO`, a
Compaq-specific port-I/O primitive.

**Why so many different `.PSD` files existed.** Before the Intel MP Specification + APIC became
the near-universal SMP standard, multiprocessor PC/server vendors used their own proprietary
CPU-bring-up and interrupt-routing mechanisms - hence one PSD per platform family, not one PSD for
all SMP hardware: `OS2APIC.PSD` (the generic, standard Intel-MP-spec/APIC-based PSD), `ALR.PSD`
(Advanced Logic Research), `PROLIANT.PSD` (Compaq ProLiant), `CRLLRY.PSD` (Corollary, Inc. -
maker of the C-bus SMP interconnect licensed to several vendors), `TRICRD.PSD` (Tricord Systems),
`WYSE.PSD` (Wyse Technology), plus `V1_EBI2.PSD` and `CAVERUN.PSD` (specific hardware identity not
resolved - flagged, not guessed). komh.github.io separately lists `VIPERMP.PSD` and `EBI2.PSD` among
OS/2 2.11's shipped SMP PSDs, consistent with different OS/2 SMP release vintages shipping different
platform sets.

**The `PSD=` CONFIG.SYS statement and load mechanism** (komh.github.io, cross-checked against
`boot-sequence.md` Stage 8's scan-order finding, which already had `PSD` listed first in the
category scan order - independently correct): a PSD is a 32-bit flat DLL named via
`PSD=filename.psd [params]` in CONFIG.SYS - 8.3 filename only, **no drive or path** (too early in
boot for path resolution), searched for in the startup partition's root directory then `\OS2`.
**Processed before `BASEDEV=`/`IFS=`/`DEVICE=`** - necessarily, since SMP CPU bring-up has to
happen before most other driver init can safely assume secondary CPUs' final state. **Multiple
`PSD=` lines are legal**: OS/2 loads and calls each one's Install function in listed order; the
first to install successfully becomes the active PSD (the same "try candidates, take the first
match" shape as `.SNP` snoopers above, for the same reason - no single mechanism could yet identify
1990s-era proprietary SMP hardware generically). An optional parameter string (<= 1024 chars) follows
the filename and is passed verbatim, uninterpreted by OS/2, to the PSD's Install function - matches
a `MODE=8259`-shaped string observed inside one real `.PSD` binary by `strings`, almost certainly
such a parameter.

## Installable File Systems (FSD)

### FSD entry points [DOC-IBM `fsd.h`]
An FSD exports a fixed set of `FS_*` entry points the kernel calls: `FS_INIT` (bootstrap, receives
the DevHlp router and a mini-FSD pointer), `FS_ATTACH` / `FS_MOUNT` (attach an FSD to / recognize a
volume - a *remote* FSD returns `ERROR_NOT_SUPPORTED` from `FS_MOUNT` and attaches via `FS_ATTACH`
instead), `FS_OPENCREATE`, `FS_READ` / `FS_WRITE`, `FS_CLOSE`, `FS_FILEINFO`, `FS_PATHINFO`,
`FS_FINDFIRST` / `FS_FINDNEXT`, `FS_CHDIR`, `FS_MKDIR`, and the rest of the file/directory surface.

Each entry point is prototyped in the DDK header `fsd.h` (SCCS `@(#)fsd.h 6.5 91/12/16`). The
`FS_INIT` "DevHlp router and mini-FSD pointer" claim is exact: `APIRET EXPENTRY FS_INIT(PSZ szParm,
ULONG pDevHlp, PULONG pMiniFSD)` - `pDevHlp` is the DevHlp entry, `pMiniFSD` the mini-FSD pointer.
`FS_ATTACH(USHORT flag, PSZ pDev, struct vpfsd*, struct cdfsd*, PCHAR pParm, PUSHORT pLen)` and
`FS_MOUNT(USHORT flag, struct vpfsi*, struct vpfsd*, USHORT hVPB, PCHAR pBoot)`, plus
`FS_OPENCREATE`, `FS_READ` / `FS_WRITE`, `FS_CLOSE`, `FS_FILEINFO`, `FS_PATHINFO`, `FS_FINDFIRST` /
`FS_FINDNEXT`, `FS_CHDIR`, `FS_MKDIR`, are all present. The remote-vs-local distinction rests on the
`FS_ATTRIBUTE` bit `FSA_REMOTE 0x00000001` (`fsd.h`); the specific "`FS_MOUNT` returns
`ERROR_NOT_SUPPORTED` for a remote FSD" behavior is standard IFS lore but was not matched to a
distinct IBM primary during ratification - treat that parenthetical as [OBS-RE] pending a source.
[DOC-IBM `fsd.h`]

### The FSHelper (`FSH_*`) contract [DOC-IBM `fsh.h`]
The kernel services an FSD calls back into, by family (every name below is prototyped in the DDK
header `fsh.h`, SCCS `@(#)fsh.h 6.5 91/10/20`, except `FSH_EXTENDTIMESLICE` - see note):
- **Volume I/O** - `FSH_DOVOLIO` (read/write volume sectors), `FSH_GETVOLPARM` (the VPB for a volume
  handle - returns both `vpfsi` and `vpfsd`), `FSH_FINDDUPHVPB`.
- **Driver dispatch** - `FSH_CALLDRIVER`, `FSH_DEVIOCTL` (issue a request packet / IOCtl to the
  underlying block driver).
- **Names** - `FSH_CANONICALIZE`, `FSH_UPPERCASE`, `FSH_WILDMATCH`, `FSH_NAMEFROMSFN`,
  the char-scan helpers (`FSH_FINDCHAR` / `FSH_PREVCHAR` / `FSH_STORECHAR`).
- **Memory** - `FSH_SEGALLOC` / `FSH_SEGFREE` / `FSH_SEGREALLOC`.
- **Synchronization** - `FSH_SEMREQUEST` / `FSH_SEMCLEAR` / `FSH_SEMWAIT` / `FSH_SEMSET`.
- **Sharing / EA / misc** - `FSH_ADDSHARE` / `FSH_REMOVESHARE`, `FSH_CHECKEANAME`, `FSH_PROBEBUF`,
  `FSH_QSYSINFO`, `FSH_INTERR` / `FSH_CRITERROR`, `FSH_YIELD` / `FSH_EXTENDTIMESLICE`.

Confirmed against `fsh.h`: all of the above are declared there (e.g. `FSH_DOVOLIO`, `FSH_GETVOLPARM`,
`FSH_CALLDRIVER`, `FSH_DEVIOCTL`, `FSH_CANONICALIZE`, `FSH_SEGALLOC`/`SEGFREE`/`SEGREALLOC`,
`FSH_SEMREQUEST`/`SEMCLEAR`/`SEMWAIT`/`SEMSET`, `FSH_ADDSHARE`/`REMOVESHARE`, `FSH_QSYSINFO`,
`FSH_INTERR`/`CRITERROR`, `FSH_YIELD`). `FSH_EXTENDTIMESLICE` is absent from this 6.5 `fsh.h` but is
a genuine kernel-exported FSHelper - it appears in the OS/2 kernel export map (`os2krnlb.map` /
`os2krnlr.map` / `os2krnld.map`, debug17 toolkit) as `FSH_EXTENDTIMESLICE`. [DOC-IBM `fsh.h` +
kernel export map]

### The volume model [DOC-IBM]
The **VPB (Volume Parameter Block)** ties a mounted volume to its FSD (name, serial, label), and the
**DPB (Drive Parameter Block)** ties a logical drive to its device driver and geometry
(`dasd-volume.md`). An FSD receives volume and drive references as handles and resolves them through
the FSHelper.

The FSD-visible VPB is `struct vpfsi` in `fsd.h`: `vpi_vid` (32-bit volume ID), `vpi_hDEV` (handle to
device driver), `vpi_bsize` (sector size), `vpi_totsec`, `vpi_trksec`, `vpi_nhead`,
`vpi_text[VPBTEXTLEN=12]` (volume name), `vpi_drive`, `vpi_unit`. An FSD resolves a volume handle to
this structure via `FSH_GETVOLPARM(hVPB, &pVPBfsi, &pVPBfsd)` (`fsh.h`). [DOC-IBM `fsd.h` / `fsh.h`]

### Extended attributes [DOC-IBM]
An FSD that supports EAs implements them through the `FEA2` / `GEA2` / `EAOP2` structures surfaced by
`DosQueryPathInfo` / `DosSetPathInfo`.

Confirmed in Toolkit 4.5 `bsedos.h`: `typedef struct _FEA2 { ... } FEA2;` and `FEA2LIST`, `GEA2` and
`GEA2LIST`, and `typedef struct _EAOP2 { ... } EAOP2;` are all defined there (the `EAOP2` block is what
`DosQueryPathInfo` / `DosSetPathInfo` at info level `FIL_QUERYEASFROMLIST` / the EA levels take).
[DOC-IBM Toolkit 4.5 `bsedos.h`]
