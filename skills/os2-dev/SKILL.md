---
name: os2-dev
description: Grounding for any OS/2 or ArcaOS development - PM/WPS/SOM/VIO/Dos* API code, a DLL or driver, a port via kLIBC/GCC or OpenWatcom, inspecting an LX/NE binary, reading IBM INF books, or the OS/2 kernel debugger. Load it before answering an OS/2 API, ABI, convention or feasibility question, and at the start of OS/2 work in a project whose CLAUDE.md names the os2-toolkit plugin.
---

# OS/2 development with the os2-toolkit

**OS/2 internals and APIs are not in your training data** - by default you produce fluent,
plausible, *wrong* OS/2 answers. This toolkit replaces guessing with a verified reference, tools to
check facts against IBM's own headers and binaries, and the disciplines below. Trust it over your
priors.

**Where things are.** Every relative path below (`os2ref/`, `recipes/`, `c-guide.md`,
`os2-app-dev-guide.md`, `sources.md`, `CONTRIBUTING.md`) is under the plugin root:
`${CLAUDE_PLUGIN_ROOT}`. Read them from there. The tools are on your PATH by name
(`lx_export.py`, `inf2txt.sh`, `kdb_cmd.py`, `os2-lib` ...).

**OS/2 material on this machine lives in the user's OS/2 library** (`PATHS.md`). Find it by role,
never by path: `os2-lib roles` lists what the library holds, `os2-lib role toolkit-headers headers`
prints where the Toolkit headers are, and `os2-lib grep PATTERN` searches this kit's `os2ref/`, then
IBM material, third-party material and notes, in that order. If a role is missing, say which
material is missing and ask whether the user has it - `os2-toolkit:ingest` then files it. Do not go
looking through the disk for it on your own, and never write a path you found into a project.

**Recording what you learn** in the toolkit is a separate, deliberate act: use the
`os2-toolkit:contribute` skill. Never edit files under `${CLAUDE_PLUGIN_ROOT}` when it is an
installed copy - updates overwrite it.

## What the kit gives you

- **`os2ref/`** - 43 pristine, source-tagged reference docs covering OS/2 internals **and** the full
  application API surface (file/mem/process/IPC/exceptions, PM windows/controls/dialogs/GPI, VIO,
  clipboard/DDE, drag-drop, printing, profiles, EAs, SOM, WPS, REXX, sockets, MMPM/2 ...).
  **`os2ref/README.md` is the router** - it maps a task to the doc(s) to load. Load docs *on demand*,
  not all at once.
- **Tools, on your PATH** (plugin `bin/`, sources in `tools/`) - `inf2txt.sh` (read IBM `.INF` books as text; build once with `inf2txt-build`), `lx_disasm.py`/`lx_export.py`/
  `lx_entry_parms.py`/`sym2map.py`/`ne_profile.py` (inspect any OS/2 LX/NE binary and its `.SYM`
  symbol file), `lx_resolve_imports.py` (name what a fixup points at), `lx_symmatch.py` (prove a
  `.SYM` belongs to an image before trusting its names), `extract_omf_lib_ordinals.py` (turn
  `MODULE.#257` into `DosClose`), `driver_re.py` (dissect an LX/NE device driver),
  `ddk_unpack.py` (merge the DDK's packages into one greppable tree), `know` (the knowledge cache -
  **search it before the books**, and record what you establish; see the `os2-toolkit:know` skill),
  `kdb_*.py` (drive the OS/2
  kernel debugger over a VM serial pipe), and `tools/ghidra/` (headless LX and NE decompile
  pipelines; see its README).
  **Run `ls ${CLAUDE_PLUGIN_ROOT}/bin` rather than trusting this list** - it lags, and a tool you don't know about
  is one you will reimplement badly. If a module ships a companion `.SYM`, `sym2map.py` reads it
  and `lx_disasm.py --sym` labels the disassembly; **never hand-roll a `.SYM` parser** (the format
  is undocumented, and a plausible-looking heuristic yields addresses that are wrong by a
  segment base).
- **The OS/2 library** - the user's IBM books, Toolkit and DDK, sources, media and RE material, filed
  once and found by role (`PATHS.md`). **Check early what it holds** (`os2-lib roles`): the books
  carry the usage patterns, contracts and worked examples that `os2ref/` summarizes but cannot
  replace, and a session with them answers materially better than one without. `os2-lib grep`
  searches case-insensitively, in provenance order, with per-source counts and a list of what it
  could not search - the defences against an encoding, case or wrong-volume miss reading as "IBM
  never documented this". `corpus/` holds the scripts that fetch and convert material; `ingest`
  uses them.
- **`recipes/`** - how-tos for install/build/test/debug. **`sources.md`** - where to download the
  IBM material and toolchain this kit does not ship.
- **`CONTRIBUTING.md`** - read this **before you write anything back into the kit**. The user may
  well ask you to ("update the toolkit with what I just found and cite the sources"): it is a
  reference *and* a finding aid that grows from real work. The rules that matter: contribute facts
  in your own words and never paste copyrighted prose, tag every claim with its provenance and
  source, strip machine paths and project identifiers, and run the commands you document. Its last
  section is a step-by-step for exactly that request.
- **`os2-app-dev-guide.md`** - the disciplines + build loop (short version below). And
  **`c-guide.md`** - the deeper craft of *writing* correct OS/2 C (ABI-struct asserts, wire formats,
  memory ownership, honest failure); point the user's `CLAUDE.md` at it for any nontrivial C.

## The disciplines

These are the disciplines low-level OS/2 work rewards; each one was paid for the hard way.
- **Never originate an ABI fact.** An offset, size, ordinal, prototype, constant, or error code you
  "just know" is training, not knowledge, and it is unfalsifiable. Look it up in `os2ref/`, then
  verify against the header. If you can't source it, say so - do not supply it.
- **Conventions are facts too, and they fail *silently*.** The rule above covers symbols; it misses
  the things with no symbol to grep - axis direction, rectangle inclusivity, string code page, handle
  ownership, units. A wrong constant errors; a wrong convention just renders upside down or in the
  wrong glyphs. Three real ones: PM's origin is **bottom-left** (inverted from Win32/X11), a `RECTL`
  excludes its right/top edges, and a PM process has **three** independent code pages (process /
  message queue / GPI). Never assume the source platform's convention survives a port - look it up.
- **An empty result is a fact about your probe, not about the world.** The most repeated mistake in
  this kit's history. A tool returning nothing almost always means the *invocation* was wrong - wrong
  path, flag, name, or encoding - not that the thing is absent. **When a probe comes back empty,
  prove it works on a known-positive case before believing the negative** (`command -v gcc` beside
  `command -v g++` settles in a second what reasoning gets wrong). Real cases: `grep` returns nothing
  on non-UTF-8 book text without `-a`; `command -v` misses in-tree tools and names containing `+`;
  `ls` on a guessed path prints nothing; `file` samples only the head. Prefer the authoritative
  instrument - `rpm -qa` over `yum list`, `find` over a guessed `ls`, `wc -l` before trusting a
  volume. Full table in `os2-app-dev-guide.md` section 3.
- **Don't originate feasibility judgments either.** The rules above cover facts; this covers
  *advice*, which is just as training-derived and steers far more work. "That's already ported",
  "that won't build with this toolchain", "that's ~N thousand lines", "OS/2 has no equivalent" -
  check before you say it. Two reflexes to distrust especially: assuming **OS/2 is maximally alien**
  (Presentation Manager is a Win32 *cousin* - `WinRegisterClass`/`WinCreateWindow`/`WinGetMsg`/
  `WinDefWindowProc`, `WM_*` window procs, native `WC_*` controls; grep `os2ref/pm-window-messaging.md`
  before claiming no analogue exists), and answering a strategy question before inventorying the machine (the `setup` skill's Step 1).
- **Provenance:** the corpus tags every claim `[DOC-IBM]` (IBM header/book), `[OBS-RE]` (observed by
  reverse-engineering), `[DOC]` (community/secondary, e.g. EDM2), `[SRC]` (read from the source of a
  component that runs on OS/2 but is not OS/2 - e.g. kLIBC). Preserve that distinction when you
  quote it; a community fact is not IBM's word, and a `[SRC]` fact describes one implementation, not
  the platform. Full key in `os2ref/README.md`.
- **Docs before disassembly.** If an interface is documented (it usually is, in `os2ref/` or an IBM
  `.INF` via `inf2txt`), read the doc - don't reverse-engineer a documented rule or "run to discover"
  a documented contract.
- **Fail honestly.** When something is unimplemented or unknown, stop at the cause and report it -
  never return a fake-success or route around a guard to "make it run." A dishonest success relocates
  the bug somewhere innocent and costs far more than a clean stop.
- **Fix the bug where it lives.** When the defect is in a shipped library, DLL, or program rather
  than your code, **rebuild that package and fix it there** - do not contort your own code around it.
  This is possible far more often than instinct suggests: this ecosystem is source-available (netlabs
  SRPMs, bitwiseworks' GitHub), the ports are maintained, and small fixes land upstream
  (`recipes/rebuild-a-netlabs-package.md` is the mechanics). The workaround is the expensive option:
  it is permanent, it hides the defect from everyone else who will hit it, and it warps your design
  around behaviour that should not exist. Note the asymmetry that settles the choice - a *sound*
  workaround already requires diagnosing the bug precisely enough to fix it, so by the time you can
  safely work around it you can usually just fix it. Two real cases from this corpus: a
  dropped-character bug in the OS/2 `readline` port (section 9.4 of `os2ref/klibc-runtime-glue.md`) that a
  terminal author would otherwise have papered over forever, and a stack of `ENOSYS` stubs in kLIBC
  itself (section 9.1) where the underlying machinery already existed and only the top-level call was
  missing. Both were small patches once located; both would have been permanent scar tissue if
  worked around.
- **Match the platform's shape.** OS/2 is segmented (selector:offset, 64 KB tiling), 16/32-bit mixed,
  `_System` calling convention, LX/NE binaries - not a flat POSIX world. `os2ref/` corrects these.

## Then just work

For any "do X OS/2 thing": route via `os2ref/README.md` -> load the doc -> (verify against headers if
present) -> write the code in IBM-canonical names -> build with the recipe -> test on the target.
`inf2txt` reaches deeper IBM detail on demand; `lx_disasm`/`ne_profile` inspect what you built.

**Open the recipe for the activity you are doing, at the moment you start doing it.** `ls recipes/`
is one command and the filenames say what they cover. This is the failure mode with the highest
observed cost in this kit: not bad answers, but *rediscovering documented answers the expensive
way* - a long session spent inspecting binaries without ever opening `inspect-a-binary.md`, or
reinventing chunked file transfer that `setup-test-vm.md` already specifies. On-demand loading only
works if you notice the demand, and you will not notice it mid-task unless you check at task start.

Corollary, because it has bitten too: **`head -N` on a doc is a probe, and a truncated read is not
a read.** Deciding a recipe "doesn't cover X" after seeing its first 30 lines is the empty-probe
error in section 3 wearing a different hat - `wc -l` it, or grep it for the topic, before concluding the
answer isn't there.
