# claude-os2-toolkit

A **Claude documentation-and-tooling kit for building OS/2 applications.** OS/2's APIs and internals
are not in a language model's training data, so Claude answers OS/2 questions fluently but often
wrongly. This kit supplies what's missing: a verified, source-tagged reference, the tools to check
facts against IBM's own headers, and the working disciplines - so Claude builds OS/2 software
*correctly* instead of guessing.

## How to use it

Install it once as a **Claude Code plugin**; every project on the machine then has it.

```sh
git clone git@github.com:phaelonimaire/claude-os2-toolkit.git ~/claude-os2-toolkit
claude plugin marketplace add ~/claude-os2-toolkit
claude plugin install os2-toolkit@claude-os2-toolkit
```

Then, in your OS/2 project, start `claude` and run `/os2-toolkit:setup` (or just say *"I'm making an
OS/2 program"*). Claude inventories the machine, asks a couple of setup questions, and writes your
project's `CLAUDE.md` with pointers to the plugin. After that, just describe what you want ("add a
Settings notebook page", "read a file's extended attributes", "subclass WPDataFile") and Claude
routes into the reference, verifies against the headers, and writes the code.

| Skill | What |
|---|---|
| `os2-toolkit:os2-dev` | The map of the kit and the disciplines; loaded for any OS/2 task. |
| `os2-toolkit:setup` | Wire a project up, or migrate one that used a copied kit. |
| `os2-toolkit:contribute` | Write a finding back into your checkout, provenance-tagged and de-identified. |
| `os2-toolkit:ingest` | File OS/2 material you mention (a downloaded PDF, a folder of books, an SDK) into your local OS/2 library - see [`PATHS.md`](PATHS.md). |
| `os2-toolkit:know` | The knowledge cache: search it before the books, and record what a session established - including what it searched for and did *not* find. |

The tools land on your `PATH` (`lx_export.py`, `lx_disasm.py`, `lx_resolve_imports.py`,
`driver_re.py`, `inf2txt.sh`, `ddk_unpack.py`, `kdb_cmd.py`, `os2-lib`, `know` ...).

**Your OS/2 material** - IBM books, the Toolkit and DDK, sources, install media, RE output - goes
into a local **OS/2 library** the plugin manages ([`PATHS.md`](PATHS.md)). Tell Claude what you have
(*"I downloaded the Toolkit to ~/Downloads"*, *"my INF books are in ../books"*) and `ingest` files
it; after that it is found by role (`os2-lib role toolkit-headers headers`) and searched with
`os2-lib grep`. Nothing is tied to a path on your disk, and derived text never lands outside the
library.

**Updating:** `git -C ~/claude-os2-toolkit pull`, then
`claude plugin marketplace update claude-os2-toolkit && claude plugin update os2-toolkit@claude-os2-toolkit`.

**Do not copy the kit into each project.** Copies drift, and what a session learns gets stranded in
them. Findings go into the checkout via `os2-toolkit:contribute`.

**Working on the kit itself:** `claude --plugin-dir ~/claude-os2-toolkit` runs the checkout directly;
`/reload-plugins` picks up edits; `claude plugin validate ~/claude-os2-toolkit` checks the manifest.

## What's inside (original work - redistributes no IBM or third-party code)

| Path | What |
|---|---|
| `os2ref/` | 43 pristine, project-agnostic OS/2 reference docs - internals, the full app API surface, and (in `klibc-runtime-glue.md`) how the kLIBC/LIBC Next POSIX compatibility layer maps Unix-style fd/`fork`/signal/`malloc`/socket semantics onto it, for porting GCC/Unix code. `os2ref/README.md` is the router. |
| `skills/` | The plugin's skills: `os2-dev` (map + disciplines), `setup`, `contribute`. |
| `bin/` | `PATH` shims for the tools and corpus scripts. |
| `hooks/` | A `PreToolUse` nudge: a broad grep of the reference material is blocked once, pointing at the knowledge cache. One-shot, opt out with `# know-miss`, and it fails open. |
| `tools/` | `inf2txt/` (read IBM `.INF` books as text); `ddk_unpack` (merge the DDK's packages into one greppable tree); `lx_export` (objects/exports/imports), `lx_disasm` (disassemble at symbol/VA/`object:offset`), `lx_entry_parms` (per-ordinal parameter words), `lx_resolve_imports` (name a fixup's target), `lx_symmatch` (does this `.SYM` belong to this image?), `sym2map` (`.SYM` -> addresses), `ne_profile` (16-bit NE), `extract_omf_lib_ordinals` (ordinal -> API name), `driver_re` (dissect a device driver) to inspect binaries; `kdb_*` (drive the OS/2 kernel debugger); `ghidra/` (headless LX and NE decompile pipelines); `know` (the knowledge cache over your library). |
| `corpus/` | Scripts to build a **local** searchable corpus of the IBM books/redbooks/EDM2 on your own machine; `ingest` uses them, and `search.sh` works without the plugin. Ships none of that material. |
| `recipes/` | Install / build / test / debug how-tos. |
| `scaffolds/` | Starter skeletons (a PM app, a console app). |
| [`sources.md`](sources.md) | Where to download the toolchain and IBM material this kit points at but does not ship. |
| [`PATHS.md`](PATHS.md) | The OS/2 library: layout, `ITEM.md`, roles, and `os2-lib`. |
| [`START-HERE.md`](START-HERE.md) | Where Claude's instructions live, with or without the plugin. |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | How to add to the kit - facts not expression, provenance, de-identification, and the checklist a session runs before committing. |
| [`os2-app-dev-guide.md`](os2-app-dev-guide.md) | The development workflow + disciplines. |
| [`c-guide.md`](c-guide.md) | How to *write* correct OS/2 C - provenance, ABI-struct asserts, honest failure, memory ownership. |

> **Tools in the recipes** are invoked by name (`lx_export.py MODULE.dll`) because the plugin puts
> `bin/` on `PATH`. Using a plain clone without the plugin, add `<checkout>/bin` to `PATH`, or run
> the scripts in `tools/` directly.

## What it does *not* ship

No IBM headers, DDK, Developer Connection books, or toolchain - those are IBM/third-party and stay
where you download them (see [`sources.md`](sources.md)). The reference is self-sufficient for most
work; the free **Toolkit 4.5 headers** are the one companion worth grabbing, because they let Claude
*verify* prototypes rather than trust the docs.

No compiled binaries either. `tools/inf2txt` ships as source plus a build script: our driver is
MIT, but it links **fpGUI**'s docview INF parser, which is **GPLv2** (fpGUI licenses per directory -
its `framework` is modified-LGPL, but `docview` is GPLv2 with no linking exception). The binary you
build is therefore a GPLv2 combined work: yours to use freely, but redistributable only under GPLv2
with corresponding source. Building it locally rather than receiving it from us keeps that your
choice. See [`tools/inf2txt/README.md`](tools/inf2txt/README.md).

Some tools shell out to programs you supply: `lx_disasm.py` and `driver_re.py` need `ndisasm`
(NASM), `kdb_cmd.py` needs `VBoxManage` (VirtualBox), `ddk_unpack.py` needs Info-ZIP `unzip` (the
DDK's oldest packages use compression methods Python's `zipfile` cannot decompress), and the
`tools/ghidra/` pipelines need Ghidra via `$GHIDRA_HOME`. Each fails with a clear message if absent.

## License

[MIT](LICENSE) - (c) 2026 phaelonimaire.

The grant covers the original authorship here: the prose, its selection and arrangement, the
provenance-tagging scheme, and the tools. It claims nothing over the **facts** it records - API
names, constants, layouts, offsets, error codes and ordinals are facts about a published interface,
not anyone's property - and nothing over the short attributed passages quoted from IBM and other
sources, which remain their owners'. No IBM or third-party material is redistributed here; see
[`sources.md`](sources.md).

OS/2, Presentation Manager, Workplace Shell, Warp and SOM are IBM trademarks; ArcaOS is Arca Noae's.
They are used only to identify the system described. This project is independent and unaffiliated
with, and unendorsed by, IBM or Arca Noae. See [`LICENSE`](LICENSE) for the full scope note.
