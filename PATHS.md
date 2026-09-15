# The OS/2 library - one place for everything the toolkit knows about on this machine

**Status: DRAFT (rev 2).** Implemented so far: `os2-lib` (`tools/os2lib.py`: root, init, ls, roles,
role, path, grep, new, convert, check, catalog) and the `ingest` skill. Not yet: `os2-lib dupes`,
automated secret screening (the skill screens by hand), and VM dependency checks.
Skills find material by role. Rev 2 folds in a dry run against one real,
heavily scattered machine (~70 items across ~40 locations, 80-100 GB of copies).

OS/2 material arrives piecemeal: a PDF someone downloaded, a folder of INF books, a Toolkit CD
image, a source archive, a debugger session's notes. Left alone it scatters across the disk and gets
copied - into project trees, next to its own archive, onto a second disk "for now". Every tool then
needs to be told where each piece is, and a probe of a wrong location reads as "not documented". So
the toolkit keeps **one library** with a fixed layout, brings material into it when the user
mentions it, and tracks the copies it finds. Nothing committed to the toolkit or to a project names
a location on the user's disk.

The dry run's lesson: **most scatter is duplication, not location.** A library that only records
where things are makes them findable but frees nothing. Knowing which copy is canonical, and
reporting the rest, is half the job (section 7).

## 1. How material gets in

The user just tells Claude, with the plugin installed:

> *"I downloaded the OS/2 Warp Toolkit PDF to ~/Downloads."*
> *"I have a pile of INF books in ../os2books."*
> *"The DDK is unpacked on /mnt/archive/ddk."*

Claude runs the `os2-toolkit:ingest` skill, which for each thing:

1. **Screens it** (section 8): secrets are refused outright; restricted material is filed only on
   the user's explicit say-so.
2. **Identifies** it - what it is, who published it, which edition, its licence class.
3. **Checks the catalogue for the same material** (section 7). If it is already an item, the new
   location is recorded as a *copy* of that item, not filed again.
4. **Chooses a canonical form and a mode** (section 4).
5. **Files it** under one category (section 3) as an *item* with an `ITEM.md` (section 5).
6. **Updates the catalogue** so every later session, tool and search can find it.

A directory is ingested as readily as a file (*"my old OS/2 stuff is in /data"*): `ingest` walks it,
proposes a plan - items, copies, exclusions, questions - and files nothing until the user agrees.

Derived output never lands anywhere but the library. That is the rule that prevents new scatter.

## 2. The root

One setting: **`OS2_LIBRARY`**, the library root.

| Order | Source |
|---|---|
| 1 | the `OS2_LIBRARY` environment variable |
| 2 | `${XDG_CONFIG_HOME:-~/.config}/os2-toolkit/library` - a one-line file holding the path |
| 3 | default: `${XDG_DATA_HOME:-~/.local/share}/os2-toolkit/library` |

The `setup` skill asks once whether the default is fine or the user wants somewhere visible (a data
disk, `~/os2`), and writes the config file. Everything else in this spec is relative to the root.

## 3. Layout

```
$OS2_LIBRARY/
  CATALOG.tsv          generated index of every item and every known copy (section 6)
  docs/                documentation: books, references, manuals, articles, wiki mirrors
  source/              source code and SDK material: headers, import libraries, source trees
  examples/            sample programs and worked examples, from any origin
  re/                  reverse-engineering material: binaries with symbol files, disassembly,
                       decompiler output, memory dumps, derived tables
  media/               install and disc images, installed-system trees, VM disk images and templates
  toolchains/          compilers, linkers and analysis tools the user keeps for OS/2 work
  notes/               OS/2 knowledge sessions established that is not a published reference (section 10)
  state/               the toolkit's own machine-local state: search index, knowledge cache, crawl
                       logs, tool builds, regenerable extractions - never user material
```

A category directory holds only items: `<category>/<slug>/`. **The slug** is lowercase
`publisher-title[-edition]` with `-` separators (`ibm-os2-toolkit-4.5`, `ibm-ddk-2004`,
`edm2-wiki-mirror`, `hobbes-archive-2024-01-11`). Fixed parts of an item:

```
<category>/<slug>/
  ITEM.md              what this is (section 5) - required
  original             symlink to the canonical form where it lives (link and convert modes)
  files/               the canonical form itself (import mode)
  tree/                extraction of an archive, when the archive is canonical and must be read
  text/                derived greppable text or markdown (convert mode)
```

**One download, several categories.** A Toolkit, DDK or developer disc ships books, headers,
samples and compilers together. It is one item in its primary category, and its parts are exposed
without copying: converted books as a `docs/` item, samples as an `examples/` item, a bundled
compiler as a `toolchains/` item. Each part has its own `ITEM.md` with `part_of:` the parent and
`paths:` pointing into it.

## 4. Canonical form and modes

**Every item has exactly one canonical form**: an `archive` (zip, 7z, tar, ISO, disk image), a
`tree` (a directory), or a `file` (a PDF, an INF). When the same material exists as both an archive
and its extraction, one is canonical and the other is a copy (section 7). Prefer:

- the **archive** for material that is only read occasionally and whose authenticity matters
  (install media, IBM kits as distributed, archive.org downloads with a checksum);
- the **tree** for material read constantly (headers, source trees, a mirror), or when the
  archive is lost or corrupt.

| Mode | When | Canonical form | Library holds |
|---|---|---|---|
| link | usable in place, location stable | stays where it is | `ITEM.md`, `original` symlink |
| convert | not greppable as it stands (INF, HLP, PDF, DjVu, archive of those) | stays where it is | `ITEM.md`, `original`, `text/` (and `tree/` if an archive had to be opened) |
| import | location is temporary (downloads, a mounted disc, a scratch dir), or the user asks | copied or moved in - **the user chooses, and is asked** | `ITEM.md`, `files/`, and `text/`/`tree/` if converted |
| adopt | derived text or an extraction already exists and its source is not on the machine | none on disk | `ITEM.md`, the adopted `text/` or `tree/`, `origin: unknown` (section 5) |

- **Conversion is for citation.** Derived text keeps what a citation needs - page numbers for PDF
  and DjVu (`[[page 123]]`, as `pdf-to-text.sh` and `djvu2txt.py` write them), panel/section titles for INF - and is UTF-8 (IBM text is
  CP850/CP437; convert it, never leave it for `grep` to misread as binary). Markdown only where the
  structure survives conversion.
- **Converters are the toolkit's own** (`inf2txt.sh`, `os2-pdf-to-text`, `djvu2txt.py` ...);
  `ITEM.md` records which one and its settings so `text/` can be regenerated.
- **`tree/` from a canonical archive is regenerable state**, not a second copy: `os2-lib check`
  may rebuild or drop it, and it never counts as a duplicate.
- **A missing original is reported, not skipped** (`os2-lib check`): it usually means an
  unmounted disk, not deleted material.

## 5. `ITEM.md`

YAML frontmatter, then free prose about the item.

```yaml
---
title: IBM OS/2 Warp Toolkit 4.5
category: source
kind: sdk                      # book | book-set | article-set | sdk | headers | source-tree | samples |
                               # binaries | decompile | dump | notes | disc-image | system-tree |
                               # vm-image | toolchain
provides: [toolkit-headers, toolkit-import-libs, toolkit-books, samples]
licence: ibm                   # own | ibm | third-party | private | restricted | unknown (section 8)
mode: link                     # link | convert | import | adopt
canonical: archive             # archive | tree | file
original: "/where/the/canonical/form/is"    # or a URL; "unknown" allowed (adopt)
acquired: 2026-09-15
part_of: null                  # slug of the parent item (multi-part downloads)
derived_from: null             # slug, a description, or "unknown"
converter: null                # e.g. "inf2txt.sh INF2TXT_CP=CP850"; "unknown" for adopted text
regenerable: true              # false when text/ cannot be rebuilt (adopted, source lost)
paths:                         # where the useful parts are inside the canonical form
  headers: original/H
  libs: original/LIB
copies:                        # other locations holding the same material (section 7)
  - path: "/another/place/os2tk45"
    match: size+names          # bytes | sha256 | size+names | name-only
    note: "committed into a project working copy"
vm: null                       # vm-image items only (section 9)
---
```

**`provides`** is how everything else finds material *by role*, without a path. Recommended roles
(extend as needed; `os2-lib roles` lists what this library actually has):

| Role | Material |
|---|---|
| `toolkit-headers`, `toolkit-import-libs`, `toolkit-books` | IBM OS/2 Toolkit |
| `ddk-headers`, `ddk-source`, `ddk-books` | Device Driver Kit |
| `ibm-books`, `redbooks` | IBM manuals and Redbooks |
| `format-specs` | LX/NE/OMF and other file-format specifications |
| `community-docs` | EDM2, os2museum and other secondary references |
| `third-party-source` | osFree, Hobbes packages, ported libraries' sources |
| `samples` | example programs |
| `os2-binaries-with-symbols` | IBM binaries with their matching `.SYM` files, one build per item |
| `decompile`, `dumps` | decompiler output / memory and header dumps for a named binary set |
| `install-media`, `system-tree`, `vm-template` | disc images, installed OS/2 drive trees, VM images |
| `toolchain-openwatcom`, `toolchain-visualage`, `toolchain-gcc`, `ghidra` | tools |

**Unknown is an honest answer.** Material often outlives its provenance: text converted years ago
from books no longer on disk, a PDF of unclear authorship. `original: unknown`,
`derived_from: unknown`, `licence: unknown` are valid and are reported by `os2-lib check` as
*provenance gaps*, never guessed. Anything cited from such an item carries that uncertainty.

## 6. Finding things: `os2-lib`

```sh
os2-lib root                        # print $OS2_LIBRARY
os2-lib ls [CATEGORY] [--role R]    # list items: slug, kind, mode, licence, provides
os2-lib role R [PART]               # path of the item(s) providing R (PART from its paths:)
                                    #   exit 1 and "no item provides R" if none - never an empty success
os2-lib path SLUG [SUBPATH]         # an item's path
os2-lib grep PATTERN [--role R | CATEGORY]
                                    # search text/, tree/ and linked text in provenance order
                                    #   (IBM, then third-party, then notes); restricted items excluded
                                    #   unless --include-restricted
os2-lib dupes [PATH...]             # copies: known ones from ITEM.md, plus a scan of PATHs for material
                                    #   matching existing items; reports GB reclaimable
os2-lib check                       # missing originals, missing ITEM.md, stale CATALOG.tsv, unconverted
                                    #   items, provenance gaps, copies that have diverged from canonical
os2-lib catalog                     # rebuild CATALOG.tsv from the ITEM.md files
```

Python tools use the same module: `from os2lib import role; h = role("toolkit-headers", "headers")`.

**Shell idiom** - the `||` must be able to fire:

```sh
h=$(os2-lib role toolkit-headers headers) || exit
grep -an DosOpen "$h/bsedos.h"
```

## 7. Copies and the canonical copy

Duplication is recorded, reported and left for the user to resolve. The toolkit **never deletes,
moves or replaces a copy on its own.**

- **Detection, cheapest first:** same name and size; same file list and sizes for a tree; a
  byte-for-byte compare (`bytes`) or `sha256` only when those agree and the user wants certainty
  (hashing multi-GB media is slow). The `match`
  field records which test was used, so a `name-only` match is never presented as identical.
- **A copy is not always waste.** A project may need material inside its tree; a second disk may be a
  backup. `copies[].note` says why a copy exists when known, and the user can mark one `keep: true`.
- **Divergence is a finding.** A "copy" whose size or file list differs from the canonical form -
  an older partial extract, a patched fork, an encrypted image of the same size - is reported as
  *diverged*, never as a duplicate. It may be a different edition that deserves its own item.
- **Reclaiming** is a separate, confirmed step: `os2-lib dupes` lists candidates with sizes and
  reasons; Claude removes one only when the user names it.

Common shapes the dry run found, and their resolution:

| Shape | Canonical | The other |
|---|---|---|
| Archive beside its own extraction | per section 4 | copy, or `tree/` state if the archive is canonical |
| Compressed copy of an ISO (`.iso.gz`), a `name (1).iso` download duplicate | the plain file | copy |
| Newer and older snapshot of a mirror/corpus on two disks | the superset | copy (verify it really is a subset) |
| Reference material committed into a project's version control | the library item | copy with `note: committed into <project>` - see section 11 |
| Whole stale checkouts of a project | not library material | reported under `dupes` only for the library material they contain |

## 8. Screening: secrets and restricted material

**Secrets are refused.** `ingest` never files, converts, prints or quotes: private keys (`-----BEGIN
... PRIVATE KEY-----`, `ssh_host_*_key`, `id_*` without `.pub`), password databases (`master.passwd`,
`spwd.db`, `pwd.db`, `shadow`), licence and registration keys (`*.key` that are not source,
`*reg.key`), token files. It detects them by name and by a header check of the first bytes -
**never by displaying content** - and reports only the path and the reason. A directory containing
secrets is still ingestible; the secret files are listed under `excluded:` in the plan and skipped.

**Licence classes** travel with the item and are enforced downstream:

| Class | Meaning | Contributions | Search |
|---|---|---|---|
| `own` | the user's own work | free | yes |
| `third-party` | published by someone else under a licence | facts + short attributed quotation | yes |
| `ibm` | IBM material | facts + short attributed quotation | yes |
| `private` | personal copies not meant to leave the machine (VM images, backups) | facts only, no quotation | yes |
| `restricted` | employer, customer or NDA material | **never** | only with `--include-restricted` |
| `unknown` | licence not established | treated as `restricted` for contributions | yes |

Restricted material is filed only when the user explicitly asks for it, and nothing under `re/` or
any `restricted`/`unknown` item is ever copied into a contribution.

## 9. VM images

VM disks and templates are `media/` items in **link mode only**. The hypervisor owns their files:
moving a disk breaks its registration, and snapshot chains make disks depend on each other (one
VM's snapshot may be the parent of another VM's differencing disk). So:

```yaml
kind: vm-image
provides: [vm-template]
licence: private
mode: link
vm:
  hypervisor: virtualbox        # virtualbox | qemu | vmware | other
  name: "the VM's registered name"
  role: template                # template | test | archive
  depends_on: []                # other VM items whose snapshots this VM's disks descend from
  guest: "OS/2 Warp Server for e-business 4.52 CP2"
```

Test machines a project spins up are project material, not items; only templates and archived
reference installs belong in the library. `os2-lib check` warns before anyone relocates a VM whose
item has dependents.

## 10. Notes

`notes/` holds OS/2 knowledge established by sessions and research that is not published anywhere
else - the dry run found it is one of the busiest categories. Each notes item is a folder of
markdown about **one subject** (`notes/os2-session-manager`, `notes/lx-loader-behaviour`), with
`ITEM.md` listing the provenance of its claims (the same tags as `os2ref/`).

- **OS/2 facts only.** A document that mixes OS/2 facts with a project's design is split: the OS/2
  part becomes or joins a notes item, the project part stays with the project, and each links to
  the other. `ingest` proposes the split; it does not guess silently.
- **Notes are a staging area for `os2ref/`.** A note that is sourced, general and de-identified is a
  candidate for `os2-toolkit:contribute`; `ITEM.md` records `contributed: <os2ref doc>` once it lands.
- **RE findings** about a specific binary live with that binary's `re/` item, not in `notes/`.

## 11. Projects and the library

A project's own source, build outputs, test logs, plans and VM names belong to the project and its
`CLAUDE.md`, never to the library. The link runs one way - **projects refer to library items by
role**:

```markdown
<!-- a project CLAUDE.md -->
- Toolkit headers: `os2-lib role toolkit-headers headers`
- Kernel symbols: `os2-lib role os2-binaries-with-symbols`
```

A project that needs a fixed path inside its tree (a build system that cannot call `os2-lib`)
creates a symlink to the item and does not commit the target. When `os2-lib dupes` finds library
material committed into a project's version control, it reports that as a finding with its size;
whether to remove it from the repository is the project owner's decision, made outside the library.

## 12. Rules for everything committed

1. **Refer to roles and categories, never host paths.** A skill says "the `toolkit-headers` item";
   a recipe writes `$(os2-lib role toolkit-headers headers)/bsedos.h`. Guest paths inside OS/2
   (`C:\OS2\DLL`, `/@unixroot/usr/lib`) are platform facts and are fine.
2. **No role, no guessing.** If `os2-lib role` finds nothing, Claude says which material is missing
   and asks whether the user has it - it does not search the disk on its own.
3. **The library is machine-local and never published.** It holds licensed material and machine
   paths; only the toolkit's tools and this spec are public.
