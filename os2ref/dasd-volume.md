# OS/2 DASD and Volume Contract

The disk and volume surface an OS/2 application observes - physical-disk and logical-disk
`DosDevIOCtl` categories, the volume/drive query APIs, and the Volume/Drive Parameter Blocks.
Brought up during boot-sequence Stages 4-5.

Provenance: **[DOC-IBM]** IBM Toolkit `bsedev.h` (IOCtl categories and function codes),
`bsedos.h` (the `Dos*` prototypes and ordinals); IBM DDK for the VPB/DPB structures.

Ratified (2026-07-26): checked against IBM Toolkit 4.5 `H/bsedev.h`, `H/bsedos.h`; IBM DDK
`base/h/sas.h`; the DOSCALLS ordinal map derived from IBM's `os2386.lib` import library
(corroborated by EDM2's ordinal table); and IBM's `fsd.h` (`vpfsi`/`vpfsd`). All IOCtl category
and function codes, all `Dos*` prototypes, and ordinals 277/278/287 matched exactly. One
discrepancy corrected: `DosQueryFSInfo` does **not** return the file-system type (see below).

## `DosDevIOCtl` disk categories [DOC-IBM `bsedev.h:40-41`; cross-confirmed DDK `base/h/bsedev.h:33-34`]

| Code | Category | Scope |
|---|---|---|
| 0x08 | `IOCTL_DISK` | logical disk (a mounted drive) |
| 0x09 | `IOCTL_PHYSICALDISK` | physical disk (the whole spindle, partitioning) |

### Category 0x08 `IOCTL_DISK` - `DSK_*` functions [DOC-IBM `bsedev.h:175-191`]

| Func | Name | Purpose |
|---|---|---|
| 0x00 / 0x01 | `DSK_LOCKDRIVE` / `DSK_UNLOCKDRIVE` | lock / unlock the logical drive |
| 0x02 | `DSK_REDETERMINEMEDIA` | re-read the media |
| 0x03 / 0x21 | `DSK_SETLOGICALMAP` / `DSK_GETLOGICALMAP` | logical-drive -> partition map |
| 0x04 / 0x45 | `DSK_BEGINFORMAT` / `DSK_FORMATVERIFY` | format, format + verify |
| 0x20 | `DSK_BLOCKREMOVABLE` | is the media removable |
| 0x40 | `DSK_UNLOCKEJECTMEDIA` | eject |
| 0x43 / 0x63 | `DSK_SETDEVICEPARAMS` / `DSK_GETDEVICEPARAMS` | BPB / geometry |
| 0x44 / 0x64 / 0x65 | `DSK_WRITETRACK` / `DSK_READTRACK` / `DSK_VERIFYTRACK` | track I/O |
| 0x5D | `DSK_DISKETTECONTROL` | diskette control |
| 0x60 | `DSK_QUERYMEDIASENSE` | media type |
| 0x66 | `DSK_GETLOCKSTATUS` | lock state |

### Category 0x09 `IOCTL_PHYSICALDISK` - `PDSK_*` functions [DOC-IBM `bsedev.h:195-200`]

`PDSK_LOCKPHYSDRIVE` (0x00) / `PDSK_UNLOCKPHYSDRIVE` (0x01), `PDSK_GETPHYSDEVICEPARAMS` (0x63),
`PDSK_READPHYSTRACK` (0x64) / `PDSK_WRITEPHYSTRACK` (0x44) / `PDSK_VERIFYPHYSTRACK` (0x65).

## Volume and drive query APIs [DOC-IBM `bsedos.h` - prototypes; ordinals from IBM `os2386.lib`]

Ordinals confirmed against IBM's `os2386.lib` import library (the DOSCALLS import records),
corroborated by the EDM2 DOSCALLS ordinal table.

- `DosPhysicalDisk(function, pBuf, cbBuf, pParams, cbParams)` (ordinal 287) - enumerate
  partitionable disks (`INFO_COUNT_PARTITIONABLE_DISKS` = 1), obtain a disk IOCtl handle
  (`INFO_GETIOCTLHANDLE` = 2 / `INFO_FREEIOCTLHANDLE` = 3), read partition information.
  [DOC-IBM `bsedos.h:2857` prototype, `bsedos.h:2862-2864` function selectors]
  - [DOC - EDM2 "DosPhysicalDisk (FAPI)"] the partitionable disk is named to function 2 by an
    ASCIIZ string of the form `number:` (1-based disk number in ASCII, a colon, then the null
    terminator). The handle returned by function 2 is usable **only** with the Category 9
    (`IOCTL_PHYSICALDISK`) `DosDevIOCtl` calls - it is **not** a file handle and must not be passed
    to handle-based calls such as `DosRead` / `DosClose`. Function-1 count and function-2 handle are
    each returned as a 2-byte value; function 3 takes the 2-byte handle and no data buffer.
    Return codes:

    | rc | Name | Meaning |
    |---|---|---|
    | 0 | `NO_ERROR` | success |
    | 1 | `ERROR_INVALID_FUNCTION` | unsupported function selector |
    | 5 | `ERROR_ACCESS_DENIED` | access to the disk denied |
    | 6 | `ERROR_INVALID_HANDLE` | bad IOCtl handle |
    | 33 | `ERROR_LOCK_VIOLATION` | disk locked by another party |
    | 87 | `ERROR_INVALID_PARAMETER` | bad parameter / buffer length |
- `DosQueryFSInfo(disknum, infolevel, pBuf, cbBuf)` (ordinal 278) - for `FSIL_VOLSER` (2) returns
  the `FSINFO` record: creation date/time (which is the volume **serial number**) plus the
  `VOLUMELABEL`; for `FSIL_ALLOC` (1) returns allocation/geometry info.
  [DOC-IBM `bsedos.h:1720` prototype, `bsedos.h:865-866` info levels, `bsedos.h:921-934`
  `VOLUMELABEL`/`FSINFO`]
  - [DOC - EDM2 "FSINFO"] confirms the `FSINFO` fields are exactly `fdateCreation` / `ftimeCreation`
    (the drive's creation date/time) + `vol` (the `VOLUMELABEL`) - no FS-type field, corroborating
    the correction below. The volume label is limited to 11 bytes, and trailing blanks are stripped
    (not counted as part of, nor returned in, the label).
  - Measured [OBS-RE - Warp Server for e-business 4.50, kernel revision 14.089, HPFS, 32-bit
    probe]: `DosSetFSInfo` with a 12-character label returns 154 `ERROR_LABEL_TOO_LONG` and leaves
    the label unchanged; a label containing `*` returns 123; a 1-byte buffer returns 122
    `ERROR_INSUFFICIENT_BUFFER`; info level 1 returns 124; drive 27 returns 15. Setting the same
    label again returns 0. Trying `A<c>B` for one character `c` at a time, only `*`, `?` and `.`
    were refused (123); every other character tried was accepted, including
    `/ \ | , ; : + = < > [ ] " &`, a space, and `- _ ~ ! @ # $ % ^ ( ) ' { }`.
    `DosQueryFSInfo` with drive 27 returns 15, a 4-byte buffer 111, level 3 124.
  - **CORRECTED (2026-07-26, Rule 1.7):** this line previously read "volume label, **serial
    number**, file-system type." The **file-system type is wrong** - `FSINFO` (`bsedos.h:928-934`)
    carries only creation date/time + volume label; there is no FS-type field. The file-system
    (FSD) name is returned by `DosQueryFSAttach` (`szFSDName`, below), not by `DosQueryFSInfo`.
- `DosQueryFSAttach(pszDeviceName, ulOrdinal, ulFSAInfoLevel, pfsqb, pcbBuf)` (ordinal 277) - which
  FSD is attached to a drive: the `FSQBUFFER2` it fills carries `iType` (local/remote/etc.) and
  `szFSDName` (the FSD name - `FAT` / `HPFS` / `JFS` / ...). [DOC-IBM `bsedos.h:1575-1584` prototype,
  `bsedos.h:840-850` `FSQBUFFER2` with `iType`/`szFSDName`]
- `DosQueryCurrentDisk(pdisknum, plogical)` / `DosSetDefaultDisk(disknum)` - the current drive and
  the logical-drive map (`plogical` = bitmap of valid logical drives).
  [DOC-IBM `bsedos.h:1705-1708`]
- `DosQueryHType(hFile, pType, pAttr)` - whether a handle refers to a disk file
  (`HANDTYPE_FILE` = 0), a character device (`HANDTYPE_DEVICE` = 1), or a pipe (`HANDTYPE_PIPE` = 2).
  [DOC-IBM `bsedos.h:1531` prototype, `bsedos.h:937-939` `HANDTYPE_*`]

## Volume / Drive Parameter Blocks

The names **VPB (Volume Parameter Block)** and **DPB (Drive Parameter Block)** are IBM's own: the
SAS (System Anchor Segment) carries `SAS_file_VPB` ("selector for Volume Parameter Block segment")
and `SAS_dd_DPB_segment` ("selector for Drive Parameter Block segment"). [DOC-IBM DDK
`base/h/sas.h:60-61,116-117`]

- **VPB (Volume Parameter Block)** - per mounted volume. Its file-system-**independent** half is the
  `vpfsi` record: `vpi_vid` (32-bit volume id = **serial number**), `vpi_hDEV` (handle to the owning
  device driver), the geometry it was mounted with (`vpi_bsize` sector size, `vpi_totsec` total
  sectors, `vpi_trksec` sectors/track, `vpi_nhead` heads), and `vpi_text[12]` (volume **label**).
  The file-system-**dependent** half is `vpfsd` (a 36-byte FSD work area). [DOC-IBM `fsd.h` `vpfsi`
  (volume id / device handle / geometry / `vpi_text` label), `vpfsd` (`vpi_work[36]`)]
  - **CORRECTED (2026-07-26, Rule 1.7):** this previously listed "file-system (FSD) name" among the
    VPB contents. `vpfsi` carries the volume id, device-driver handle, geometry, and volume label -
    **not** an FSD-name string; the FSD name is obtained via `DosQueryFSAttach` (`szFSDName`).
- **DPB (Drive Parameter Block)** - per logical drive: the device parameters (BPB / geometry), the
  owning device driver, and media state. [OBS-RE - name confirmed [DOC-IBM] via DDK `sas.h`
  (`SAS_dd_DPB_segment`); a field-level DPB layout could **not** be located in the IBM DDK or
  Toolkit 4.5 headers surveyed as of 2026-07-26, so the field list here is left unconfirmed.]

These are kernel structures; drivers and the file-system layer read them, and their contents surface
to applications through `DosQueryFSInfo` / `DosQueryFSAttach` above.

## Drive-letter assignment (boot time) [DOC-IBM `lvm_data.h`]

Which letter (`C:`, `D:`, ...) a given partition receives is decided by one of two mechanisms,
depending on whether the disk was ever managed by LVM (`LVM.EXE`, OS/2 Warp Server for e-business
and later, all Convenience Package releases, and eComStation) or not. **LVM is not universal
across OS/2 releases** - earlier versions never had it at all, so the classic mechanism below is
not a fallback bolted on for compatibility; for a large share of real OS/2 installs it is the
*only* mechanism that ever ran.

### LVM-managed disks: the Drive Letter Assignment (DLA) table

For every disk that has a partition table, LVM writes a **Drive Letter Assignment Table** into
**the last sector of the track containing that partition table** (partitions are track-aligned,
so that track has otherwise-unused trailing sectors) [DOC-IBM `lvm_data.h`, "NOTE: LVM Drive
Letter Assignment Tables (DLA_Tables) appear on the last sector of each track containing a valid
MBR or EBR"].

```
DLA_Table_Sector                                    (one per disk, at that track's last sector)
    DLA_Signature1        = 0x424D5202              /* DLA_TABLE_SIGNATURE1 */
    DLA_Signature2        = 0x44464D50              /* DLA_TABLE_SIGNATURE2 */
    DLA_CRC                                         /* 32-bit CRC, computed with this field zeroed */
    Disk_Serial_Number
    Boot_Disk_Serial_Number                         /* conflict-resolution tiebreak, see below */
    Install_Flags
    Cylinders / Heads_Per_Cylinder / Sectors_Per_Track
    Disk_Name[DISK_NAME_SIZE]
    Reboot                                          /* install-program bookkeeping */
    DLA_Array[4]                                    /* one per partition-table slot */
```

Each of the four `DLA_Entry` slots (one per partition-table entry) carries [DOC-IBM `lvm_data.h`]:

```
DLA_Entry
    Volume_Serial_Number                            /* the volume this partition belongs to */
    Partition_Serial_Number
    Partition_Size                                  /* sectors */
    Partition_Start                                 /* LBA */
    On_Boot_Manager_Menu                            /* BOOLEAN */
    Installable                                      /* BOOLEAN - the OS install target */
    Drive_Letter                                     /* the assigned letter, e.g. 'C' */
    Volume_Name[VOLUME_NAME_SIZE]
    Partition_Name[PARTITION_NAME_SIZE]
```

**Conflict resolution**: `Boot_Disk_Serial_Number` exists specifically so that if a disk is moved
between machines (or a table is manually altered outside `LVM.EXE`, which itself never permits
letter conflicts), the "foreign" claimant for a given letter can be identified and rejected; if all
claimants agree, letters are assigned first-come-first-served [DOC-IBM `lvm_data.h`].

A **second, distinct signature** exists - the **LVM Signature Sector**, the *last sector of the LVM
partition itself* (not the track containing the partition table), giving per-partition LVM metadata
including its own `Drive_Letter` field, the partition's own serial number, size accounting (raw
size vs. the size reported to the user, after subtracting LVM's own reserved sectors), the LVM
version that created it, and up to 10 active LVM features (drive linking, Bad Block Relocation,
etc.) via `LVM_Feature_Data` entries [DOC-IBM `lvm_data.h`]:

```
LVM_Signature_Sector                                (last sector of the LVM partition itself)
    LVM_Signature1        = 0x4A435332              /* LVM_PRIMARY_SIGNATURE */
    LVM_Signature2        = 0x4252444B              /* LVM_SECONDARY_SIGNATURE */
    Signature_Sector_CRC
    Partition_Serial_Number / Volume_Serial_Number / Boot_Disk_Serial_Number
    Partition_Start / Partition_End / Partition_Sector_Count / LVM_Reserved_Sector_Count
    Partition_Size_To_Report_To_User
    LVM_Major_Version_Number / LVM_Minor_Version_Number
    Partition_Name[] / Volume_Name[] / Comment[] / Disk_Name[]
    LVM_Feature_Array[MAX_FEATURES_PER_VOLUME]       /* up to 10 features, e.g. drive linking, BBR */
    Drive_Letter
    Fake_EBR_Location / Fake_EBR_Allocated           /* synthetic EBR bookkeeping, see below */
```

### Non-LVM disks: the classic MBR/EBR partition-order mechanism

Where no DLA table is present, OS/2 falls back to the classic mechanism: parse the **Master Boot
Record** and any **Extended Boot Records**, and assign letters by partition-table order.
`Master_Boot_Record` and `Extended_Boot_Record` share one layout [DOC-IBM `lvm_data.h`]:

```
Master_Boot_Record / Extended_Boot_Record
    Reserved[446]                                    /* boot code */
    Partition_Table[4]                               /* Partition_Record entries, below */
    Signature             = 0xAA55                   /* MBR_EBR_SIGNATURE - valid-table marker */

Partition_Record
    Boot_Indicator                                   /* 0x80 = active partition */
    Starting_Head / Starting_Sector / Starting_Cylinder   /* CHS start (10-bit cylinder, packed
                                                              across Starting_Sector's high 2 bits) */
    Format_Indicator                                 /* partition type, see below */
    Ending_Head / Ending_Sector / Ending_Cylinder
    Sector_Offset                                     /* sectors on disk before this partition */
    Sector_Count
```

`Format_Indicator` values OS/2 itself distinguishes [DOC-IBM `lvm_data.h`]:
`UNUSED_INDICATOR` 0x00, `FAT12_INDICATOR` 0x01, `FAT16_SMALL_PARTITION_INDICATOR` 0x04,
`EBR_INDICATOR` 0x05 (an extended-partition link, chaining to another `Extended_Boot_Record`),
`FAT16_LARGE_PARTITION_INDICATOR` 0x06, `IFS_INDICATOR` 0x07 (HPFS/other installable FS),
`BOOT_MANAGER_INDICATOR` 0x0A, `FAT16X_LARGE_PARTITION_INDICATOR` 0x0E (FAT16 beyond the 7.875GB
CHS limit, added 2001), `WINDOZE_EBR_INDICATOR` 0x0F, `LVM_PARTITION_INDICATOR` 0x35; bit
`BOOT_MANAGER_HIDDEN_PARTITION_FLAG` 0x10 marks a Boot-Manager-hidden partition.

Boot Manager's own menu (for partitions that predate LVM, migrated forward) uses a 2-entry
**Alias Table** at a fixed offset (`ALIAS_TABLE_OFFSET` 0x18A) inside the EBR - only the first
entry is actually used - and a well-known migration marker string (`"--> LVM "`/`"--> LVM*"`,
exactly `ALIAS_NAME_SIZE`=8 characters) is written into a migrated entry's name field so that older
tools (FDISK, or anything else that only understands the pre-LVM Boot Manager menu format) still
display something for it [DOC-IBM `lvm_data.h`]. Boot Manager's own boot sector carries the
fixed signature string `"APJ&WN"` [DOC-IBM `lvm_data.h`].

### Which mechanism actually assigns the boot drive's letter

Both mechanisms are **assignment-time** facts fixed on disk, not something recomputed by the
session-manager or kernel at every boot - reading a disk's DLA table (if present) or its MBR/EBR
chain (if not) is sufficient to reproduce the correct letter for every drive, including the boot
drive itself. **`OS2DASD.DMD` itself - not only `OS2LVM.DMD` - assigns drive letters** for the
classic/non-LVM case: *"OS/2 DASD device manager driver assigns the drive letters to the installed
drives and partitions"* [DOC - EDM2 `OS2DASD.DMD.html`]; `OS2LVM.DMD` performs the DLA-table-based
assignment above when the disk has been LVM-managed [DOC - EDM2 `Logical_Volume_Manager.html`]. The
value this feeds - `QSV_BOOT_DRIVE` / `SIS_BootDrv` (`infoseg.md`) - is a **number**, 1-26; OS/2
has no assumption that the boot drive is `C:`.

## See also
- `boot-sequence.md` - where volumes are mounted during boot (the DASD/IFS stages).
- `drivers.md` - the PDD / IFS (FSD) driver model that produces the VPB/DPB this doc queries.

---

*"Drive-letter assignment" section added 2026-07-30: checked directly against IBM's `lvm_data.h`
(header dated 1998, IBM Corp., "This module defines the disk structures used by LVM, including
that of the Master Boot Record (MBR) and Extended Boot Records (EBR)") for the
`DLA_Table_Sector`/`DLA_Entry`/`LVM_Signature_Sector`/`Master_Boot_Record`/`Partition_Record`
structures and all signature/indicator constants, plus EDM2-reprinted IBM documentation
(`OS2DASD.DMD.html`, `Logical_Volume_Manager.html`) for which driver performs which mechanism and
LVM's version-availability boundary. All [DOC-IBM]/[DOC - EDM2].*
