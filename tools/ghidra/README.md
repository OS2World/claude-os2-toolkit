# Headless Ghidra pipelines for OS/2 binaries

Decompile a whole OS/2 module - every object, every function - with headless
Ghidra, under the module's own symbol names where a matching `.SYM` exists.

Two pipelines, because OS/2 ships two executable formats:

| Pipeline | Format | Typical input |
|---|---|---|
| `lx_ghidra_run.sh` | **LX**, 32-bit (and mixed 16/32) | 32-bit DLLs, EXEs, the kernel, `.SYS` drivers of LX vintage |
| `ne_ghidra_run.sh` | **NE**, 16-bit | installable file systems, 16-bit device drivers, 16-bit DLLs and utilities |

Everything after the export step is shared code, so the two produce the same
output shape and the same analysis tools work on both.

These scripts ship no decompiler output and no binaries. They are the
procedure; the material is yours.

## Prerequisites

- **Ghidra.** Set `GHIDRA_HOME` to the unpacked Ghidra directory - the one
  containing `support/`, which is where `analyzeHeadless` lives - or pass
  `--ghidra <dir>`. Both runners stop immediately, naming `GHIDRA_HOME`, if it
  is unset or wrong, rather than producing an empty output directory.
  Developed and run against **Ghidra 12.0.1 PUBLIC**; nothing here uses an API
  newer than Ghidra 10-era scripting, but no other version has been tested.
  If Ghidra is filed in your OS/2 library, `os2-lib role ghidra` prints its
  path.
- **Python 3** (3.8 or later; developed on 3.12).
- **`sym2map.py`** from this toolkit's `tools/` directory - the parent of this
  one. The Python scripts here import it for its `.SYM` parser and LX reader
  by computing the path from their own location, so a plain clone works with
  no configuration. They fail with that path named if it is missing.
- **Java**: whatever Ghidra itself requires. The `.java` scripts are Ghidra
  scripts, compiled by Ghidra at run time; nothing here is built separately.

## Getting the input

You need the binary, and ideally a `.SYM` file **from the same build**:

```sh
b=$(os2-lib role os2-binaries-with-symbols) || exit
ls "$b"
```

See [`PATHS.md`](../../PATHS.md) for how material is filed and found by role.

**Symbols come from a matching `.SYM`, or not at all.** A `.SYM` from a
different build of the same module resolves to plausible-looking addresses
that are quietly wrong, which is worse than no names: `FUN_00012a40` announces
that nothing is known, `DosQueryFoo` asserts something false. The runners do
not second-guess the file you hand them - checking that dates and segment
counts agree, and that a few names land where independently known facts say
they should, is the caller's job. The one guard that is automatic: an LX run
whose `.SYM` resolves *zero* symbols treats it as a mismatch, warns, and
continues without names.

Running without a `.SYM` is fully supported. Every function is still
decompiled, under Ghidra's own `FUN_<addr>` names, and the run log records
that there were no symbols so a later reader cannot mistake that for a gap in
the analysis.

## The LX pipeline, end to end

```sh
export GHIDRA_HOME=/path/to/ghidra
tools/ghidra/lx_ghidra_run.sh MODULE /path/to/MODULE.DLL /path/to/MODULE.SYM
```

Output lands in `./ghidra-out/MODULE/` (change the root with `--out`).

Options worth knowing (`lx_ghidra_run.sh --help` for all):

- `--extra-syms FILE` - extra `0xVVVVVVVV  name` lines (two spaces) for functions the `.SYM`
  omits, such as statics or the 32-bit body behind a 16-bit entry stub, so they are seeded and
  decompiled too. Keep the reason for each line in the file.
- `--xrefs` - also write `xrefs_<bits>.tsv`, the cross-reference skeleton (`DumpXrefs.java`):
  `F` function rows, `C` call edges, `D` data references, `S` every symbol. It is for building
  function or data tables without scraping decompiled C, and comes from the same analysis run.
- `--no-decompile` - skip decompiling; with `--xrefs`, the TSV alone, much faster.

**1. Load every object at its real base.** An LX module is not one image: its
objects - code and data, 16-bit and 32-bit - are separate segments that the
loader places at separate, widely spaced flat addresses recorded in the
module's object table. Import one object alone and every cross-object call
points into unmapped memory: the decompiler cannot follow it, and auto-analysis
never finds the code on the far side. So `lx_obj_export.py` exports *all* of
them with fixups applied, `make_blocks.py` picks the first executable object of
a bitness as Ghidra's `-import` primary, and `LoadAllObjects.java` maps the
rest as memory blocks at their true bases. Data objects are mapped too, so an
access to a global decompiles against the bytes that are really there.

Two things the export gets right that are easy to get wrong:

- **Chained fixups.** In many modules a fixup record is only the head of a chain:
  the other 32-bit slots on that page are linked through the object's own bytes,
  each holding `(next_offset << 20) | target_offset`, and have no record of their
  own (`../lx_fixchain.py` explains the loader's rule). `sym2map.py` fills only
  zero slots, and a chain slot is never zero, so without chain handling every
  chained reference keeps the link offset in its top 12 bits and decompiles as a
  global at a nonsense address. `lx_obj_export.py` walks the chains first. About
  230 modules of an installed Warp 4.5 carry chains; `lx_fixchain.py MODULE.DLL`
  says whether yours does. Measured on CHKDSK32.DLL with its `.SYM`:

  | | before | after |
  |---|---|---|
  | data references landing inside the module | 17 | 2,327 |
  | data references pointing outside any object | 1,786 | 18 |
  | data references to a named symbol | 3 | 1,499 |

- **BSS.** Each object is zero-filled to its full virtual size. Reading stops at
  the last page stored in the file, and without the fill the symbols living in
  BSS have no memory to be placed on: on CHKDSK32.DLL, 417 of 507 symbols placed
  before, 507 of 508 after (507 from the `.SYM` plus one `--extra-syms` line).

One Ghidra program has exactly one Language, so the runner builds **one program
per bitness present** in the module, and opposite-bitness *code* objects are
mapped **non-executable**. That is not fussiness: Ghidra's analyzer walks any
executable block and decodes it in the program's single language, so a 32-bit
object merged executable into a 16-bit program is misdecoded wholesale, and the
analyzer then "discovers" thousands of functions that do not exist.

**2. Apply symbols from a matching `.SYM`.** `sym2map.py --format flat`
resolves each symbol to a flat VA through the LX object table, and
`ApplySymbols.java` applies a label at each one **and seeds a Function** where
the address is in executable memory. The seeding matters: a label alone gives
the function-start heuristic nothing, so a named routine that nothing in the
imported object calls never becomes a Function, and the decompile step -
which iterates the function manager - silently skips it. The symptom is an
executable object that yields zero functions while plainly containing named
code.

**3. Decompile everything.** Auto-analysis runs, then `DecompileAll.java`
writes one `.c` file per function, named `<function>_<entry point>.c`. It
refuses to emit a file for any function whose entry point is in a
non-executable block, because Ghidra's analysis creates functions inside those
blocks regardless of the mapping, and those files would be real code decoded at
the wrong instruction width - convincing C that means nothing, usually with no
warning inside the file.

**4. Check the result.** `bitness_index.py ghidra-out/MODULE` writes
`DECOMPILE_INDEX.tsv` classifying every decompiled file as OK, GARBAGE (a
wrong-bitness decode with a correct one available) or **ORPHAN** (a
wrong-bitness decode with *no* correct counterpart - the dangerous row, because
a grep finds the only file there is and it is garbage). `--markers` drops a
`.WRONG-BITNESS` note beside each bad file, so the warning is where the file is
read. Nothing is ever deleted or rewritten: the misdecoded files are the
evidence.

**5. Recover the orphans.** `lx_ghidra_reseed.sh ghidra-out/MODULE 16` re-runs
that one bitness pass with a function seeded at every ORPHAN address, into
`decompiled_16_reseed/`, leaving the original pass untouched for comparison.

Output layout per module:

```
ghidra-out/MODULE/
  objs/            exported object images + manifest.json
  blocks_NN.txt    block spec fed to LoadAllObjects.java
  symbols_va.txt   "0xVA name" lines fed to ApplySymbols.java
  decompiled_32/   one .c per 32-bit function
  decompiled_16/   one .c per 16-bit function
  run.log          the driver's own summary
  headless_NN.log  raw Ghidra output
```

## The NE pipeline: what differs

```sh
tools/ghidra/ne_ghidra_run.sh MODULE /path/to/MODULE.IFS /path/to/MODULE.SYM
```

Same shape, same downstream scripts - `ne_seg_export.py` writes a
`manifest.json` in exactly the form `make_blocks.py` and `LoadAllObjects.java`
already consume. Four things are genuinely different:

- **Segments, and a pseudo-flat address space.** NE logical segment N is placed
  at base `N << 16`, so Ghidra's 16-bit protected mode renders an address as
  `000N:offset` - byte for byte the notation IBM's own NE `.SYM` files use. No
  address translation is needed anywhere. Segments are grown to their minimum
  allocation size first, so intra-segment BSS references land inside the block.
- **Symbols need no binary to resolve against.** An NE `.SYM`'s segment numbers
  *are* the module's logical segment numbers, so `ne_symva.py` maps them
  directly. It emits linker and segment markers before real function names,
  because labels are created primary and several names often share one address
  - last applied wins, and you want the real function name to win.
- **Imports get named stubs.** An NE relocation naming another module cannot be
  resolved statically. `ne_seg_export.py` gives each distinct (module, ordinal)
  pair a slot in a synthetic segment, so the call has somewhere real to point;
  `ne_impnames.py` turns `MODULE_487` into an API name using module-definition
  (`.DEF`) files you supply with `--defdir`. An ordinal that no supplied `.DEF`
  names is passed through unchanged and reported - a missing name is a gap to
  look up, never a guess.
- **DS is pinned.** `SetDataSeg.java` sets DS to the module's declared
  automatic data segment across all executable blocks before disassembly.
  Without it, 16-bit analysis recovers DS only where it can prove it locally,
  and most globals decompile as bare numeric offsets instead of their real
  names. Check that your module's calling contract actually guarantees DS on
  entry - for an OS/2 file system driver it does - and use `--no-ds` where it
  does not.

## What each script does

| Script | One line |
|---|---|
| `lx_ghidra_run.sh` | Run the whole LX pipeline: export, symbols, analyse, decompile, per bitness. |
| `ne_ghidra_run.sh` | The same for an NE module, adding import stubs and a pinned DS. |
| `lx_ghidra_reseed.sh` | Re-run one bitness pass with a function seeded at every ORPHAN address. |
| `ghidra_env.sh` | Sourced helper: find `analyzeHeadless` from `GHIDRA_HOME` or `--ghidra`, or fail clearly. |
| `lx_obj_export.py` | Export every LX object at its real base with fixups (chained ones included) applied and BSS zero-filled, plus `manifest.json`. |
| `ne_seg_export.py` | Export every NE segment with relocations applied, plus imports, relocs and header JSON. |
| `make_blocks.py` | Turn a manifest into a block spec for one bitness; name the primary object to import. |
| `lx_entry_table.py` | Resolve an LX module's own export ordinals to flat addresses and names. |
| `bitness_index.py` | Classify every decompiled file as OK / GARBAGE / ORPHAN; optionally mark the bad ones. |
| `ne_symva.py` | Map an NE `.SYM` to `0xVA name` lines in the pipeline's pseudo-flat addressing. |
| `ne_impnames.py` | Rename `MODULE_<ordinal>` import stubs to real API names from `.DEF` files. |
| `ne_datamap.py` | Annotate a data segment with symbol names, gap-derived sizes and initial values. |
| `ne_xref.py` | Call cross-reference over a directory of decompiled `.c` files (text heuristic). |
| `LoadAllObjects.java` | preScript: map every other object as a memory block at its true base. |
| `ApplySymbols.java` | preScript: label each `0xVA name`, and seed a Function where it is executable. |
| `DisableNoreturnDiscovery.java` | preScript: disable the non-returning-function analyzers (they truncate 16-bit callers). |
| `SetDataSeg.java` | preScript: pin DS (optionally ES) over all executable blocks before disassembly. |
| `DecompileAll.java` | postScript: decompile every function to one `.c` each, skipping non-executable blocks. |
| `DumpXrefs.java` | postScript (`--xrefs`): functions, call edges, data references and symbols as TSV. |
| `DecompileByAddr.java` | postScript: decompile named addresses only, seeding a function where none exists. |
| `FindCallers.java` | postScript: every reference to an address, with the containing function. |
| `FindSym.java` | Print symbols whose name contains a substring, with addresses. |
| `SeedFuncs.java` | Seed functions by offset within the first executable block, when there is no `.SYM`. |
| `DumpBytes.java` | List memory blocks, and optionally write raw bytes at given addresses to files. |
| `DumpStackFrame.java` | Dump a function's decompiler-recovered parameters and locals with their storage. |
| `ListAnalysisOptions.java` | List (and optionally set) this program's analysis options by their real names. |
| `ProbeBlocks.java` | Sanity check: image base, every block's range and permissions, first symbols. |

## Reading the output honestly

- **A wrong-bitness decompile looks exactly like a right one.** Run
  `bitness_index.py` before citing anything, and prefer `--markers` if others
  will read the corpus.
- **`halt_baddata()` after a jump to `0:0` is a finding, not a bug.** Thunk
  gates whose far-jump target is filled in at run time carry no static
  relocation at all, so no static analysis can recover the target. The real
  target, when it is knowable, is usually in the instruction just before the
  jump; otherwise it needs a live read.
- **A decompile is evidence about a binary, not documentation.** Under this
  kit's provenance scheme a fact read out of decompiled output is `[OBS-RE]`,
  and it says what one build does - see [`CONTRIBUTING.md`](../../CONTRIBUTING.md).

## Caveats

- Ghidra runs, and therefore whole-module timings, function counts and the
  behaviour of its analyzers, have not been re-verified against any Ghidra
  version other than the one noted above.
- The auto-analysis timeout (`--timeout`, default 1800s) bounds a real failure
  mode: an analyzer can get stuck retrying against a bogus jump target and
  never finish on its own. At the deadline, analysis is abandoned and the
  decompile step still runs against what was found.
- `ne_xref.py` reads C text, not a symbol table: it misses calls through
  function pointers and cannot distinguish a call from a same-named macro.
