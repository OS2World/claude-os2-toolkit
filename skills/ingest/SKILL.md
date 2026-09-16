---
name: ingest
description: Bring OS/2 material into the user's OS/2 library - a downloaded PDF or INF book, a folder of docs, an SDK or DDK, a source tree, install media, binaries with symbols, RE output, research notes. Use when the user says they downloaded, have, found or unpacked OS/2 material somewhere ("I downloaded the Toolkit to ~/Downloads", "my OS/2 docs are in ../somedir"), or asks to add something to the library.
---

# Ingest material into the OS/2 library

The library is specified in `${CLAUDE_PLUGIN_ROOT}/PATHS.md` - read sections 1, 3-5 and 8 before your
first ingest in a session. `os2-lib` (on PATH) does the filing; you do the judgement.

**The rule this exists for:** derived output goes into the library and nowhere else, and nothing is
moved, copied or deleted outside it without the user's say-so.

## 0. The library exists

```sh
os2-lib root && os2-lib check
```

If the root does not exist, ask the user where it should live - the default printed by `os2-lib
root`, or somewhere visible like a data disk - then `os2-lib init <path> --save` (or `os2-lib init`
for the default). Do not create it without asking.

## 1. Screen - before reading anything

List what is there by **name, size and `file` type only**. Never `cat`, `head` or `strings` an
unidentified file - that is how secrets get printed.

- **Secrets are refused:** private keys (`ssh_host_*_key`, `id_rsa`/`id_ed25519` without `.pub`,
  anything `file` calls a private key), password databases (`master.passwd`, `spwd.db`, `pwd.db`,
  `shadow`), licence/registration keys (`*.key`, `*reg.key`), token files. Report only the path and
  the reason; exclude them from the plan. Never open one to check.
- **Project material** (a project's own source, build output, logs, plans, test VMs) is not library
  material. Say so and leave it.

## 2. Identify

What is it, who published it, which edition or version. Record `--provenance ibm` for IBM's own
material, `community` for third-party books and sites, `own` for the user's work - it only orders
search results; leave it `unknown` if unclear. Read a README, a title page, a version banner - the
minimum. If you cannot establish something, record `unknown`; do not guess.

## 3. Is it already in the library?

```sh
os2-lib ls
grep -i '<distinctive name fragment>' "$(os2-lib root)/CATALOG.tsv"
```

If the same material is already an item (same title/edition; compare names and sizes), do **not**
file it again: add the new location to that item's `copies:` in its `ITEM.md` (`match: size+names`
or `name-only` - say which you actually checked), note why the copy exists if known, and tell the
user how large it is. A differing "copy" (other edition, partial extract, patched fork) is either its
own item or reported as diverged - ask.

## 4. Choose canonical form, category, slug, mode

- **Category:** `docs` `source` `examples` `re` `media` `toolchains` `notes` (PATHS.md section 3).
- **Slug:** lowercase `publisher-title[-edition]`, e.g. `ibm-os2-toolkit-4.5`.
- **Canonical form** (section 4): archive for install media and kits as distributed; tree for
  material read constantly; one of them only.
- **Mode:** `link` is the **default** - the material has a home already and keeps it. `convert`
  (INF/HLP/PDF: link the original, derived text goes into the library) - `import` ONLY when there is
  no home to keep: a downloads folder, a mounted disc, something loose in `$HOME`, and then **ask**
  whether to copy or move - `adopt` (existing converted text whose source is gone).
- **Respect a layout the user already maintains.** If they keep every ISO in one directory, their
  VMs under the hypervisor, or source trees where they cloned them, do not propose moving any of it:
  file it where it is. A user who has already categorised their material has told you where things
  go - the library records that, it does not overrule it.
- **Virtual machines are never moved** (PATHS.md section 9): the hypervisor owns their registration
  and snapshot chains. Record which machine is a template or has a special use, and link it.
- **Multi-part downloads** (Toolkit, DDK, developer discs): one item in the primary category, plus
  part items (`--part-of <parent>`) for the books (`docs`), samples (`examples`), bundled compilers
  (`toolchains`), each linking into the parent's tree.
- **VM images:** `media`, `link` only, never moved (section 9); fill in `vm:` by hand.

**For a directory of many things, stop here and show the user a plan** - a table of proposed items
(category/slug, mode, provides), copies found, exclusions (secrets, project material) and
questions - and file nothing until they agree.

## 5. File it

```sh
os2-lib new <category> <slug> --title "<Title>" --kind <kind> [--provenance ibm|community|own] \
    --mode <mode> --original <path> --provides <role,role> [--canonical archive|tree|file] \
    [--part headers=original/H --part libs=original/LIB ...] \
    [--part-of <slug>] [--derived-from <slug|unknown>]
```

Roles: use the recommended vocabulary in PATHS.md section 5 (`os2-lib roles` shows what is already in
use) so tools can find it. `--part` names the useful parts inside the original, so
`os2-lib role toolkit-headers headers` resolves; `new` refuses a part that does not exist. Then edit
the new `ITEM.md` prose: what it is, edition, where it came from, anything a reader should know
before citing it (and `copies:` / `vm:` by hand when they apply).

Import mode: copy or move the material into `<item>/files/` - whichever the user chose.

## 6. Convert (convert mode)

```sh
os2-lib convert <slug>          # INF/HLP via inf2txt.sh, PDF via pdf-to-text.sh -> <item>/text/
```

`inf2txt.sh` needs a one-time `inf2txt-build`; PDFs need `pdftotext`. If a book converts to garbage,
retry with `--cp CP437 --force`. Report failures - a book that did not convert is a gap, not an empty
book. Scanned books from archive.org use `djvu2txt.py` by hand (see `corpus/README.md`).

## 7. Verify and report

```sh
os2-lib catalog && os2-lib check
os2-lib role <a role you set> [part]      # proves it resolves
os2-lib grep '<a term you know is in it>' --role <role>
```

Tell the user: what was filed (category/slug, mode), what was converted and what failed, copies you
recorded and their size, what you excluded and why, and any provenance gaps (`unknown` fields).
