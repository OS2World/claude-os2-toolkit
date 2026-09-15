---
name: setup
description: Wire an OS/2 project up to the os2-toolkit plugin - inventory the machine for IBM books, Toolkit headers and toolchains, interview the user briefly, and write (or migrate) the project's CLAUDE.md. Use when the user starts an OS/2 program ("I'm making an OS/2 program"), asks to set the OS/2 toolkit up in a project, or a project CLAUDE.md still points at a copied claude-os2-toolkit directory.
---

# Set up an OS/2 project

Run once per project. Load the `os2-toolkit:os2-dev` skill first if it is not already loaded - it
is the map of what the kit contains, and every relative path below is under
`${CLAUDE_PLUGIN_ROOT}`.

## Step 1 - Inventory the machine *before* you advise

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

## Step 2 - Interview the user briefly

Ask only what you need - and only what Step 1 did not already answer:
1. **What are they building?** PM GUI app, console/VIO app, a DLL, a device driver/IFS, a port.
2. **Toolchain?** Lay the choice out - do **not** pick for them. Summarize
   `recipes/choosing-a-toolchain.md`: **OpenWatcom** builds locally on Linux and cross-compiles (fast,
   can build drivers) but v1.9 isn't full C99; **GCC/kLIBC** runs inside OS/2 over SSH (more setup)
   but gives modern C99/C11, POSIX (`fork`/`pipe`/`openpty`/sockets), and RPM packages. Note where
   their toolchain is, or that they need to install it (`recipes/install-openwatcom.md`, `sources.md`).
3. **Test target?** An ArcaOS/OS-2 VM (recommended), or build-only for now (`sources.md` section 4).
4. **Toolkit headers?** (`sources.md` section 1) - only ask if Step 1 found none. If present, note the
   path to `.../H`; it is the verification substrate.

## Step 3 - Write the project's `CLAUDE.md`

Create or update `CLAUDE.md` in the **user's project root**. It is auto-loaded every session, so it
holds pointers, not content - and **no filesystem paths into the toolkit**: the installed plugin
moves on every update. Its stable interface is the plugin name, its skills, and the tool names on
PATH.

- A one-line framing: *"This project builds an OS/2 `<type>`. OS/2 APIs are not in the model's
  training data - never originate an ABI fact."*
- **Grounding:** "At the start of any OS/2 task load the `os2-toolkit:os2-dev` skill (the
  os2-toolkit plugin). Route OS/2 API/internals questions through its `os2ref/README.md` router; do
  not answer them from memory."
- **Verify:** headers present -> "confirm every prototype/constant/struct against the Toolkit
  headers at `<path>/H` and cite `file:line`." Absent -> "treat `os2ref/` as authoritative and flag
  anything it does not cover rather than inventing it."
- **Tools:** the ones relevant to their work, by PATH name (always `inf2txt.sh` + `lx_disasm.py`;
  `kdb_*.py` only for driver/low-level work with a debug VM).
- **Build + test:** the recipe by name (e.g. "the toolkit's `recipes/build-pm-app.md`") plus the
  project's own target VM details.
- **Corpus:** if their book corpus is not at `${user_config.os2docs}` (or, when that is an unset
  placeholder, `~/os2docs`), record where it is.
- **Contributing:** "Findings that belong in the toolkit go through `os2-toolkit:contribute`."

## Migrating a project that used a copied kit

If the project's `CLAUDE.md` (or `LOOP.md`, `STATUS.md` ...) refers to `claude-os2-toolkit/...`
paths - a clone inside the project, a sibling checkout, or `~/claude-os2-toolkit/...`:

1. **Look for stranded work first.** For each referenced copy that is a git checkout, compare it with
   the toolkit source at `${user_config.toolkit_checkout}` (unset placeholder: `~/claude-os2-toolkit`): `git status`, and
   `git log --oneline <source-head>..HEAD` after fetching one into the other. Report any commits or
   uncommitted edits the source lacks and offer `os2-toolkit:contribute` to bring them in. Do not
   discard them.
2. **Rewrite the references** as plugin pointers: `<kit>/os2ref/X.md` -> "the toolkit's `os2ref/X.md`
   (via `os2-toolkit:os2-dev`)"; `<kit>/tools/foo.py` or `python3 ../tools/foo.py` -> `foo.py`;
   `<kit>/corpus/search.sh` -> `os2-corpus-search`. Keep every project-specific rule untouched.
3. **Do not delete the copy.** Tell the user it is no longer referenced and can be removed once step 1
   is settled. Back the `CLAUDE.md` up first if the project is not under version control.
