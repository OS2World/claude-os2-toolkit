# Inspecting an OS/2 binary (LX / NE)

After building - or to understand an existing DLL/EXE - inspect it before shipping it to the VM.
These tools read the module tables directly; no OS/2 needed.

```sh
# 32-bit LX modules (.EXE / .DLL)
lx_export.py MODULE.dll                    # object table, exports, imports, forwarders
lx_disasm.py MODULE.dll <object>:<offset>  # disassemble at a location
lx_entry_parms.py MODULE.dll               # entry-table / parameter view

# 16-bit NE modules
ne_profile.py MODULE.dll                   # format ID + NE segment/reloc/import profile
                                             # (--list FILE to profile many at once;
                                             #  also writes ne_profile_result.json to CWD)

# symbol maps (.sym -> text), when you have them
sym2map.py MODULE.sym
lx_symmatch.py MODULE.dll MODULE.sym       # does this .SYM belong to THIS build? check before trusting names

# naming what the code calls
lx_resolve_imports.py --all-objects --summary MODULE.dll   # every fixup -> module+ordinal/name
lx_fixchain.py MODULE.dll                  # does it use chained fixups (slots with no record)?
extract_omf_lib_ordinals.py os2386.lib DOSCALLS   # IBM's ordinal->name map, from an import library

# 16-bit exports: how many argument bytes each entry pops
lx_retf_argbytes.py MODULE.dll [--ord N]   # read from each 16-bit entry's own `retf N`

# device drivers (LX or NE)
driver_re.py all DRIVER.SYS                # device header, IOCtl table, imports, DevHlp call sites

# a whole module, decompiled (needs Ghidra - tools/ghidra/README.md)
lx_ghidra_run.sh <name> MODULE.dll [MODULE.sym]   # LX: every object, every function
ne_ghidra_run.sh <name> MODULE.DLL [MODULE.sym]   # NE: 16-bit DLLs, drivers, IFSs
lx_ghidra_run.sh --xrefs --no-decompile <name> MODULE.dll [MODULE.sym]   # call graph + data refs as TSV

# install media and message files
os2-unpack  extract FILE_ -d DIR           # IBM PACK files (names ending in _) - tools/unpack/README.md
os2-unpack2 extract ARCHIVE -d DIR         # PACK2 archives (needs UNPACK2.EXE's tables)
msgdump.py OSO001.MSG                      # every message in an MKMSGF .MSG file, by number
```

Which tool answers which question:
- **`lx_symmatch.py` before any `.SYM`.** `sym2map.py` never fails: a `.SYM` from a different build of
  the same module resolves cleanly to wrong addresses, and the disassembly then starts mid-instruction.
- **`lx_resolve_imports.py`** names the `call far 0:0` sites in `lx_disasm.py` output - the real target
  is in the fixup records, not the code. In a module with **chained fixups** most internal pointers
  have no record of their own - one record heads a chain threaded through the object bytes - so it
  also lists those slots, marked `(chained)`; `lx_fixchain.py` counts them. A tool that applies only
  the records leaves every chained pointer holding a link value, not an address.
- **`extract_omf_lib_ordinals.py`** turns a by-ordinal import into a name. Many system DLLs export by
  ordinal only, so the names exist nowhere in the DLL; IBM's import library is the authored map.
- **`lx_retf_argbytes.py`** for calling or reimplementing a 16-bit export: the argument block must be
  popped exactly as the callee does. The entry table's parameter count is filled in for only a few
  entries, and decompilers invent argument lists.
- **`driver_re.py`** gathers facts about a shipped driver; its DevHlp census is a lead list, not a
  specification.
- **The Ghidra pipelines** decompile a whole module under its own symbol names where a matching `.SYM`
  exists; they ship no output, only the procedure. `--xrefs` adds the call graph and data references
  as TSV, for building tables without scraping decompiled C.
- **`msgdump.py`** reads the system's message files - the text behind `SYS`-numbered errors and
  `DosGetMessage` - without OS/2.

Common uses:
- **Confirm your `.def` worked** - does the module export the names/ordinals you intended, and import
  the DLLs/ordinals you expect? (A mismatch is the usual `SYS2070`/`SYS1804` cause.)
- **Diagnose a crash** - `C:\POPUPLOG.OS2` gives `MODULE object:offset`; `lx_disasm.py` shows the
  faulting instruction there. Pass the pair verbatim (decimal object, hex offset); `--sym` is
  optional and only adds symbol labels.
- **Read a shipped DLL's surface** - before you link against it, see what it actually exports.

- **Find out which module really owns an API** - the module you link is often not the one that
  implements the function (`PMWIN` is ~738 forwarders into `PMMERGE`). `--exports`/`--imports` on
  both sides settles it in two commands. See `../os2ref/module-dll.md` section "Where the PM APIs
  actually live".

## Getting the binary off the OS/2 box first

Inspecting a *shipped* module means copying it to the host, and that step has its own traps - the
OS/2 TCP/IP 4.51 stack does not reliably complete large transfers (so `scp` can truncate quietly),
and OS/2 pipes corrupt binary data by LF->CRLF translation. **`setup-test-vm.md` section "Moving files in
and out" has the working method**, including how to install the Guest Additions and map a share;
read it before improvising. Short form: prefer a VirtualBox shared folder (host dir mounted as e.g.
`F:`) and `cksum` both sides to prove the copy, rather than trusting any transfer.

## Reading disassembly honestly [OBS-RE]

Three ways to draw a confident wrong conclusion from `lx_disasm.py` output:

- **`call` targets are not resolved to symbols, and many are not real targets.** An
  `E8 00000000` (`call <next instruction>`, rel32 = 0) is an **unrelocated fixup** - the loader
  patches it at load time. Its apparent target is meaningless; do not tabulate it as a callee.
- **Do not map an address to "the nearest preceding symbol".** Across a large image with a partial
  symbol table this manufactures plausible nonsense - in one real case it attributed 31 calls in a
  file dialog to `ctrpQueryWidgetIndexFromHWND`, a widget-container helper. If you cannot resolve
  a target through the fixup records, report it as unresolved.
- **A function prologue is good evidence; infer from it, but say so.** Reading argument slots
  (`[ebp+8]`, `[ebp+0xc]`, `[ebp+0x10]`) and what the function stores into them is legitimate and
  often decisive - e.g. a write of `2` into `[param3+0x0c]` identifies `param3` as a `PFILEDLG`
  and the store as `lReturn = DID_CANCEL`. Mark it `[OBS-RE]`, and prefer the source or header if
  one exists (`os2ref/`, an IBM `.INF`, or a published GPL tree) - **docs before disassembly**.

Cross-check anything structural against the export table before building on it; when a `.SYM`
disagrees with the entry table, the entry table wins.

Format details are in `../os2ref/executable-formats.md`; the import/export/forwarder model is in
`../os2ref/module-dll.md`.
