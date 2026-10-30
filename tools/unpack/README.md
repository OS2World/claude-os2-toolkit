# Unpacking IBM's packed install files, without OS/2

OS/2 install disks, CDs, fixpaks and the Developer Connection CDs store most files compressed in
IBM's own formats - the files whose names end in `_` (`FDISK.CO_`, `INSTALL.IN_`). On OS/2,
`UNPACK.EXE` and `UNPACK2.EXE` expand them. These tools do the same on Linux, so install media can
be read, inventoried or fed to the other tools in this kit without booting anything.

| Tool | On `PATH` as | Reads |
|---|---|---|
| `pack1.py` | `os2-unpack` | IBM's original PACK format: magic `A5 96`, version word `FFFE` / `FFFF` / `0A0A` / `0A14` / `0A1E` / `1400` - what `UNPACK.EXE` decodes itself |
| `pack2.py` | `os2-unpack2` | PACK2 archives: magic `A5 96 FD FF` - what `UNPACK2.EXE` handles; one archive can hold many members |
| `ftcomp.py` | - | the PACK2 codec (FTCOMP), used by `pack2.py` |
| `cd_inventory.py` | - | classifies every file under an extracted install tree by how it has to be unpacked, and writes the expected unpacked result as a manifest - test vectors for anyone writing their own unpacker |

```sh
os2-unpack  list    FILE...                     # what a PACK file holds
os2-unpack  extract FILE... -d DIR [--ea-dir DIR]
os2-unpack2 list    ARCHIVE...                  # like UNPACK2 /SHOW /SIZES
os2-unpack2 extract ARCHIVE... -d DIR [-n NAME] [--flat] [--ea-dir DIR]
```

Extended attributes stored with a file are written to `--ea-dir` as `<name>.fealist` (the raw
`FEALIST`, one per file) rather than dropped; without `--ea-dir` they are not written.

**PACK2 needs IBM's `UNPACK2.EXE`** for the codec's constant tables, which `ftcomp.py` reads out of
the executable at run time: pass `--unpack2 PATH` or set `OS2_UNPACK2`. It is `\OS2\UNPACK2.EXE` on
any installed OS/2 - copy it off a system you have. This kit ships no IBM binaries or data.
`os2-unpack2 list` and all of `os2-unpack` work without it.

## How far it has been checked

The formats are written up in [`PACK_FORMAT.md`](PACK_FORMAT.md) and
[`FTCOMP_FORMAT.md`](FTCOMP_FORMAT.md), each with its validation table. In short: every PACK2
archive on a Warp Server for e-business install ISO (285 archives, 2,685 members, 112 MB) decoded
with 0 errors and 0 size mismatches; output matched files on an installed system except 9 that
install itself modifies; and the codec was compared against IBM's own code run under an emulator, 0
differences. PACK versions `FFFF` and the OS/2 1.x variants were found on no media and are
implemented from the code but untested.
