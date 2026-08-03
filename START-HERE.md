# START HERE - Claude bootstrap for building OS/2 applications

**If a user has pointed you at this directory** (e.g. "I'm making an OS/2 program, reference
`./claude-os2-toolkit`"), this file is your instructions. Follow it once, at the start, to wire the
user's project up; after that their project `CLAUDE.md` carries the pointers and you just work.

This kit exists because **OS/2 internals and APIs are not in your training data** - you will produce
fluent, plausible, *wrong* OS/2 answers by default. The kit replaces guessing with a verified
reference (`os2ref/`), the tools to check facts against IBM's own headers, and the working
disciplines below. Trust the kit over your priors.

---

## Step 1 - Understand what this kit gives you
- **`os2ref/`** - 43 pristine, source-tagged reference docs covering OS/2 internals **and** the full
  application API surface (file/mem/process/IPC/exceptions, PM windows/controls/dialogs/GPI, VIO,
  clipboard/DDE, drag-drop, printing, profiles, EAs, SOM, WPS, REXX, sockets, MMPM/2 ...).
  **`os2ref/README.md` is the router** - it maps a task to the doc(s) to load. Load docs *on demand*,
  not all at once.
- **`tools/`** - `inf2txt/` (read IBM `.INF` books as text), `lx_disasm.py`/`lx_export.py`/
  `lx_entry_parms.py`/`sym2map.py`/`ne_profile.py` (inspect any OS/2 LX/NE binary and its `.SYM`
  symbol file), `kdb_*`/`kdb/` (drive the OS/2 kernel debugger over a VM serial pipe).
  **Run `ls tools/` rather than trusting this list** - it lags, and a tool you don't know about
  is one you will reimplement badly. If a module ships a companion `.SYM`, `sym2map.py` reads it
  and `lx_disasm.py --sym` labels the disassembly; **never hand-roll a `.SYM` parser** (the format
  is undocumented, and a plausible-looking heuristic yields addresses that are wrong by a
  segment base).
- **`corpus/`** - build a **local** searchable corpus of the IBM books (and the redbook / EDM2
  mirrors) from material the user already has or fetches, then search it with
  `corpus/search.sh <pattern>`. **Check early whether a corpus exists** (`ls "$OS2DOCS"` /
  `corpus/search.sh` reports which sources are present): the books carry the usage patterns,
  contracts and worked examples that `os2ref/` summarizes but cannot replace, and a session with
  them answers materially better than one without. `search.sh` also defends against the failure
  mode where an encoding or wrong-volume miss reads as "IBM never documented this".
- **`recipes/`** - how-tos for install/build/test/debug. **`sources.md`** - where to download the
  IBM material and toolchain this kit does not ship.
- **`CONTRIBUTING.md`** - read this **before you write anything back into the kit**. The user may
  well ask you to ("update the toolkit with what I just found and cite the sources"): it is a
  reference *and* a finding aid that grows from real work. The rules that matter: contribute facts
  in your own words and never paste copyrighted prose, tag every claim with its provenance and
  source, strip machine paths and project identifiers, and run the commands you document. Its last
  section is a step-by-step for exactly that request.
- **`os2-app-dev-guide.md`** - the disciplines + build loop (short version in Step 3). And
  **`c-guide.md`** - the deeper craft of *writing* correct OS/2 C (ABI-struct asserts, wire formats,
  memory ownership, honest failure); point the user's `CLAUDE.md` at it for any nontrivial C.

## Step 1.5 - Inventory the machine *before* you advise
**Look before you ask, and look before you recommend.** The material this kit deliberately does not
ship is very often already on the box - and a session that assumes it is absent will answer
strategy questions from training instead of from IBM. Run this first; it costs one command:

```sh
# IBM books, Toolkit headers, converted book text, toolchains
find / \( -iname "*.INF" -o -iname "bsedos.h" -o -iname "pmwin.h" -o -iname "os2tk45" \) \
     2>/dev/null | grep -vi "wine\|node_modules" | head -20
ls ~/os2* ~/toolkit* /opt/*os2* 2>/dev/null      # common unpack locations
```

If you find IBM books (`.INF`, or `inf2txt`-converted `.txt`), **that is your verification
substrate** - `recipes/read-ibm-books.md` for how to search them, and note the `grep -a` trap there
(which applies to **any** OS/2-era text, including `.c`/`.h`/`.def`/`.rc` sources, not only books)
before trusting any negative result. If you find the Toolkit `H/` directory, cite `file:line` from it.

Then read `recipes/choosing-a-toolchain.md` **before** you say anything about toolchains, and check
the size of the relevant `os2ref/` docs (`wc -l`) before you characterize what the corpus covers.
Every one of those is a fact on this disk, not a thing to estimate.

## Step 2 - Interview the user briefly, then write their `CLAUDE.md`
Ask only what you need - and only what Step 1.5 did not already answer:
1. **What are they building?** PM GUI app, console/VIO app, a DLL, a device driver/IFS.
2. **Toolchain?** Lay the choice out for the user - do **not** pick for them. Summarize
   `recipes/choosing-a-toolchain.md`: **OpenWatcom** builds locally on Linux and cross-compiles (fast,
   can build drivers) but v1.9 isn't full C99; **GCC/kLIBC** runs inside OS/2 over SSH (more setup)
   but gives modern C99/C11, POSIX (`fork`/`pipe`/`openpty`/sockets), and RPM packages. Then note
   where their toolchain is (or that they need to install it - `install-openwatcom.md` / `sources.md`).
3. **Test target?** An ArcaOS/OS-2 VM (recommended), or build-only for now (`sources.md` section 4).
4. **Do they have the Toolkit headers?** (`sources.md` section 1) - **search for them first** (Step 1.5);
   only ask if the search came up empty. If present, note the path to `.../H`; it is your
   **verification substrate**. If genuinely absent, say the corpus is usually enough but offer the
   download.

Then **create or update the project's `CLAUDE.md`** (in the user's project root, not here) with:
- A one-line framing: *"This project builds an OS/2 `<type>` application. OS/2 APIs are not in the
  model's training data - use the toolkit below and never originate an ABI fact."*
- **Router:** "OS/2 API/reference questions -> consult `<toolkit>/os2ref/README.md`, then load the
  specific doc(s). Do not answer OS/2 API questions from memory."
- **Verify:** if headers are present -> "confirm every prototype/constant/struct against the Toolkit
  headers at `<path>/H` (grep them) and cite `file:line`." If not -> "treat `os2ref/` as authoritative
  and flag anything it doesn't cover rather than inventing it."
- **Tools:** the `tools/` pointers relevant to their work (always `inf2txt` + `lx_disasm`; add `kdb_*`
  only if they're doing driver/low-level work with a debug VM).
- **Build + test:** the chosen recipe from `recipes/` (and the target VM details if any).
- Keep it short - it is auto-loaded every session, so it must be pointers, not content.

## Step 3 - The disciplines (carry these into the project `CLAUDE.md`)
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
  before claiming no analogue exists), and answering a strategy question before doing Step 1.5.
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

## Step 4 - Then just work
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
