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
strategy questions from training instead of from IBM. Start with what the OS/2 library already holds:

```sh
os2-lib root && os2-lib roles      # what is filed, by role
os2-lib check                      # anything missing, unconverted or unmounted
```

- **No library yet** (the root does not exist): set it up, and this is a conversation, not a
  default to impose. Show the user what the library distinguishes - `os2-lib where` prints the
  eight kinds and one line on each - and explain the two different "where"s, because they are easy
  to conflate:
  - the **root** holds the bookkeeping: an `ITEM.md` per item, the symlinks, and converted text. It
    is small, and one directory is fine.
  - a **category home** is where material of that kind lives *when the library has to place some* -
    an import, or derived output. Material that is linked needs no home at all: it stays where it
    already is, which is the common case.

  Then offer both routes plainly:
  - *"defaults for everything"* -> `os2-lib init <root> --save`;
  - *"I already keep some of this somewhere"* -> name those categories and leave the rest to the
    root: `os2-lib init <root> --save --home media=/where/the/isos/are --home source=/where/trees/live`.

  A user who has already organised their disk has told you where things go. Record that; do not
  propose moving any of it, and do not invent a location for a category they did not mention.
- **Material missing** - no `toolkit-headers`, no `toolkit-books`: ask whether the user has it. If
  they do not know, look, and show what you found rather than using it directly:
  ```sh
  find ~ /opt -maxdepth 5 \( -iname "*.INF" -o -iname "bsedos.h" -o -iname "pmwin.h" -o -iname "os2tk45" \) \
       2>/dev/null | grep -vi "wine\|node_modules" | head -20
  ```
  Offer `os2-toolkit:ingest` for what turns up. Never point the project at it by path.

The IBM books (`toolkit-books`, `ddk-books`) are **your verification substrate** -
`recipes/read-ibm-books.md` for how to search them, and note the `grep -a` trap there (which applies
to **any** OS/2-era text, including `.c`/`.h`/`.def`/`.rc` sources, not only books) before trusting
any negative result. Cite Toolkit headers as `file:line` from `os2-lib role toolkit-headers headers`.

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
4. **Toolkit headers?** (`sources.md` section 1) - only ask if the library has no `toolkit-headers`.
   If they have them, ingest them; they are the verification substrate.
5. **Where do its cards live?** A tracker is per project. If it is a Gitea instance, write
   `.os2track` in the project root (`TRACK_URL`, `TRACK_REPO` - never a token) and the
   `os2-toolkit:track` tool finds it from there or any subdirectory;
   `recipes/setup-a-tracker.md` creates one that does not exist yet.
6. **Where does its code live, and what does landing mean?** Ask separately, because it is a
   separate fact. The cases seen in practice: **svn** to a server; **git with a remote** (a public
   host, often, even when the tracker is private); **git, local only, no remote**; and **no version
   control at all**, which is commoner than it sounds. Then ask what landing a change means here -
   commit and push, commit only, or nothing to commit because the tree is unversioned - and whether
   there are branch or message conventions.

**Cards and code are independent.** A private tracker serving a public repository is a normal
arrangement, not a contradiction: issues can be private while the code is not. Never infer one from
the other, and never file a card on a code host's issue tracker unless that is what the project
declared.

## Step 3 - Write the project's `CLAUDE.md`

Create or update `CLAUDE.md` in the **user's project root**. It is auto-loaded every session, so it
holds pointers, not content - and **no filesystem paths into the toolkit or to OS/2 material**: the installed plugin
moves on every update, and OS/2 material is found by role (`os2-lib`). Its stable interface is the plugin name, its skills, and the tool names on
PATH.

- A one-line framing: *"This project builds an OS/2 `<type>`. OS/2 APIs are not in the model's
  training data - never originate an ABI fact."*
- **Grounding:** "At the start of any OS/2 task load the `os2-toolkit:os2-dev` skill (the
  os2-toolkit plugin). Route OS/2 API/internals questions through its `os2ref/README.md` router; do
  not answer them from memory."
- **Verify:** library has `toolkit-headers` -> "confirm every prototype/constant/struct against the
  Toolkit headers (`os2-lib role toolkit-headers headers`) and cite `file:line`." Absent -> "treat
  `os2ref/` as authoritative and flag anything it does not cover rather than inventing it."
- **Tools:** the ones relevant to their work, by PATH name (always `inf2txt.sh` + `lx_disasm.py`;
  `kdb_*.py` only for driver/low-level work with a debug VM).
- **Build + test:** the recipe by name (e.g. "the toolkit's `recipes/build-pm-app.md`") plus the
  project's own target VM details.
- **Material:** "OS/2 books, headers and other material are in the OS/2 library: find them with
  `os2-lib role <role>`, search with `os2-lib grep`, never by a path."
- **Cards:** where this project's tracker is, and that `.os2track` records it - or plainly that it
  has none, so a session does not go looking.
- **Code and landing:** the version control this project uses and what landing means (commit and
  push / commit only / unversioned, so a change is just files on disk). Say it explicitly even when
  the answer is "none": a session that assumes a repo exists will report work as landed when
  nothing was recorded.
- **Contributing:** "Findings that belong in the toolkit go through `os2-toolkit:contribute`."

## Migrating a project that used a copied kit

If the project's `CLAUDE.md` (or `LOOP.md`, `STATUS.md` ...) refers to `claude-os2-toolkit/...`
paths - a clone inside the project, a sibling checkout, or `~/claude-os2-toolkit/...`:

1. **Look for stranded work first.** For each referenced copy that is a git checkout, compare it with
   the toolkit source (located as in the `os2-toolkit:contribute` skill): `git status`, and
   `git log --oneline <source-head>..HEAD` after fetching one into the other. If
   `git merge-base` finds **no common ancestor** (an older, separately initialised history), commits
   prove nothing - compare *content* instead: for each file the copy has or has edited, check its
   paragraphs exist in the source, normalising punctuation (the source has had ASCII-only and
   de-identification passes, so exact greps miss reworded-but-present text). Report any commits,
   edits or content the source lacks and offer `os2-toolkit:contribute` to bring them in. Do not
   discard them. If a check is blocked (sandbox, permissions), say which, and call the copy
   *unverified*, not clean.
2. **Rewrite the references** as plugin pointers: `<kit>/os2ref/X.md` -> "the toolkit's `os2ref/X.md`
   (via `os2-toolkit:os2-dev`)"; `<kit>/tools/foo.py` or `python3 ../tools/foo.py` -> `foo.py`;
   `<kit>/corpus/search.sh` -> `os2-lib grep`. Host paths to OS/2 material the library holds
   (compare with the `original` column of `CATALOG.tsv` under `os2-lib root`) -> `os2-lib role <role>
   [part]`; material it does not hold -> offer `os2-toolkit:ingest` first. Keep every project-specific rule untouched.
3. **Do not delete the copy.** Tell the user it is no longer referenced and can be removed once step 1
   is settled. Back the `CLAUDE.md` up first if the project is not under version control.
