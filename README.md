# claude-os2-toolkit

A **Claude documentation-and-tooling kit for building OS/2 applications.** OS/2's APIs and internals
are not in a language model's training data, so Claude answers OS/2 questions fluently but often
wrongly. This kit supplies what's missing: a verified, source-tagged reference, the tools to check
facts against IBM's own headers, and the working disciplines - so Claude builds OS/2 software
*correctly* instead of guessing.

## How to use it

```sh
mkdir myos2app && cd myos2app
git clone git@github.com:phaelonimaire/claude-os2-toolkit.git claude-os2-toolkit
claude          # start Claude Code
```
Then tell Claude:

> I'm making an OS/2 program. Reference `./claude-os2-toolkit`.

Claude reads [`START-HERE.md`](START-HERE.md), asks a couple of setup questions, and writes your
project's `CLAUDE.md` with the right pointers. After that, just describe what you want ("add a
Settings notebook page", "read a file's extended attributes", "subclass WPDataFile") and Claude
routes into the reference, verifies against the headers, and writes the code. `git pull` to update.

## What's inside (original work - redistributes no IBM or third-party code)

| Path | What |
|---|---|
| `os2ref/` | 43 pristine, project-agnostic OS/2 reference docs - internals, the full app API surface, and (in `klibc-runtime-glue.md`) how the kLIBC/LIBC Next POSIX compatibility layer maps Unix-style fd/`fork`/signal/`malloc`/socket semantics onto it, for porting GCC/Unix code. `os2ref/README.md` is the router. |
| `tools/` | `inf2txt/` (read IBM `.INF` books as text); `lx_export` (objects/exports/imports), `lx_disasm` (disassemble at symbol/VA/`object:offset`), `lx_entry_parms` (per-ordinal parameter words), `sym2map` (`.SYM` -> addresses), `ne_profile` (16-bit NE) to inspect binaries; `kdb_*` (drive the OS/2 kernel debugger). |
| `corpus/` | Scripts to build a **local** searchable corpus of the IBM books/redbooks/EDM2 on your own machine, plus `search.sh`, which searches it in provenance order. Ships none of that material. |
| `recipes/` | Install / build / test / debug how-tos. |
| `scaffolds/` | Starter skeletons (a PM app, a console app). |
| [`sources.md`](sources.md) | Where to download the toolchain and IBM material this kit points at but does not ship. |
| [`START-HERE.md`](START-HERE.md) | Claude's bootstrap instructions. |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | How to add to the kit - facts not expression, provenance, de-identification, and the checklist a session runs before committing. |
| [`os2-app-dev-guide.md`](os2-app-dev-guide.md) | The development workflow + disciplines. |
| [`c-guide.md`](c-guide.md) | How to *write* correct OS/2 C - provenance, ABI-struct asserts, honest failure, memory ownership. |

> **Paths in the recipes.** `recipes/*.md` write tool invocations as `../tools/lx_export.py`, i.e.
> relative to the recipe's own directory. If you are standing in your project root (the usual case),
> that is `claude-os2-toolkit/tools/lx_export.py`. Substitute whatever is right for where you are -
> the recipes assume the toolkit's own layout, not yours.

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

Two tools also shell out to programs you supply: `lx_disasm.py` needs `ndisasm` (NASM), and
`kdb_cmd.py` needs `VBoxManage` (VirtualBox). Both fail with a clear message if absent.

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
