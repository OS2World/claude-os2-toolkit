# Sources - where to get the material this kit does *not* ship

This kit ships **our** reference (`os2ref/`) and **our** tools - but no IBM/third-party material.
Everything below is freely (or commercially) obtainable; download only what your task needs.

**You usually don't need any of it.** `os2ref/` is a standalone reference; for most app work it's
enough. Grab the **Toolkit headers** if you want Claude to *verify* prototypes against ground truth
(recommended for correctness-critical code); grab the rest only for depth `os2ref/` doesn't cover.

> URLs drift. These are *where to look*, not guaranteed deep links - search the named site/project.

---

> **Rights:** most of what follows is IBM material that is no longer sold and now circulates through
> community archives. That is not the same as a licence to redistribute it. Download for your own
> use, check what your jurisdiction and the original licence allow, and do not re-host it as part of
> a project. This applies to section 1 and section 3 as much as to the Warp images in section 4.

> **Once you have material, `corpus/` turns it into something searchable.**
> `corpus/build-inf-text.sh` extracts `.INF` books to greppable text;
> `corpus/fetch-books.sh` and `corpus/fetch-edm2.sh` mirror the redbook and EDM2 sources below;
> `os2-toolkit:ingest` files the result into your OS/2 library (`PATHS.md`), and `os2-lib grep`
> then searches everything in provenance order and refuses to let an
> encoding or wrong-volume miss read as "IBM never documented this". See `corpus/README.md`.

## 0. Before downloading anything - look on the machine

Much of section 1-section 5 is bulky and widely mirrored, so a machine that has done OS/2 work before often
**already has it**, unpacked, sitting next to the project. Check before fetching:

```sh
# extracted IBM books, toolkits, DevCon trees, wiki mirrors
find ~ -maxdepth 4 -type d \( -iname "*os2*" -o -iname "*toolkit*" -o -iname "*edm2*" \
     -o -iname "inf_text" -o -iname "*developer_connection*" \) 2>/dev/null
```

Whatever turns up, have Claude ingest it (`os2-toolkit:ingest`) rather than pointing a project at
it by path. Two habits make this pay off:

- **Grep the local mirror, not just the headers.** Prototypes live in `/usr/include`; *usage
  patterns, contracts and worked examples* live in the books, in EDM/2 articles, and in Toolkit
  sample source. A symbol's absence from `os2emx.h` says nothing about whether the facility exists
  - it may be in another header, or be a WPS/SOM method rather than a `Win*` call.
- **Use `grep -a`.** Extracted IBM text is often CP850, and plain `grep` treats it as binary and
  reports nothing - a silent false negative (`recipes/read-ibm-books.md`).

This kit's own `os2ref/` is the first thing to search, before either. A Notepad2 port once reported
"no OS/2 equivalent" for printing, shell-namespace enumeration, per-file icons and Unicode
conversion - all four were already documented here or in the books on the same disk. See
`os2-app-dev-guide.md` section 3.

---

## 1. Verification substrate - recommended (small download)

- **IBM OS/2 Developer's Toolkit 4.5 - the `H/` and `INC/` headers.** The single most useful
  companion download: it lets Claude confirm any prototype / constant / struct and cite `file:line`
  (the discipline in `os2-app-dev-guide.md`). Version-correct for Warp 4 / 4.5.
  *Where:* Hobbes (`hobbesarchive.com`) and the Internet Archive (`archive.org`), search "OS/2
  Developer's Toolkit 4.5". EDM2 (`www.edm2.com`) links to mirrors.
  *Point Claude at it* by telling the bootstrap where you unpacked `.../OS2TK45/H`.

## 2. Toolchain - pick one (larger, free)

- **OpenWatcom** - C/C++ + linker (`wcc386`/`wlink`/`wrc`), builds 16- and 32-bit OS/2 (LX/NE).
  *Where:* `openwatcom.org` (1.9) or the maintained fork `open-watcom.github.io` /
  `github.com/open-watcom/open-watcom-v2`. Linux-hosted cross build works.
- **GCC + kLIBC** - the modern GNU toolchain for OS/2 (`gcc -Zomf`, wlink backend). Ships with
  ArcaOS; also from netlabs (`trac.netlabs.org`, "GCC"/"libc").

## 2b. kLIBC / LIBC Next source - for `klibc-runtime-glue.md` (free)

`os2ref/klibc-runtime-glue.md` documents how kLIBC/LIBC Next implements POSIX semantics on
OS/2; its claims are verified against **source code**, not IBM documentation, tagged `[SRC]`
in that doc (see its own preamble for what that tag means and how to re-verify a claim).

- **LIBC Next (bitwiseworks' maintained kLIBC fork)** - `github.com/bitwiseworks/libc`. Clone
  it and the file:line citations in `klibc-runtime-glue.md` (given relative to the repo
  root, e.g. `src/emx/src/lib/sys/__read.c:74`) resolve directly. Clone it wherever suits your
  project - every citation is repo-relative, so none of them depend on where it lives.
- **Original kLIBC** (unmaintained upstream LIBC Next forked from) -
  `trac.netlabs.org/libc/wiki`, for history/comparison only; LIBC Next is the actively
  maintained tree and what `klibc-runtime-glue.md` was checked against.

## 3. Deeper IBM reference - optional (large)

Only if `os2ref/` doesn't cover something. Once downloaded, read the compiled `.INF` books with
`inf2txt.sh <book.inf>` (see `recipes/read-ibm-books.md`).

- **IBM Developer Connection for OS/2 (Device Driver Kit + docs).** The `.INF` programming books
  (`cpgref`, `gpi1-4`, `pm1-5`, `pddref`, `mmref`, `somref`, `wps1-3`, `rexxpg`, ...) that `os2ref/`
  was built from. *Where:* `archive.org`, search "IBM Developer Connection OS/2".
- **IBM OS/2 DDK** (driver development - PDD/IFS/GRADD/DISPLAY reference). *Where:* `archive.org`
  identifiers `cdrinc_The_Developer_Connection_Device_Driver_Kit_for_OS2_IBM` and `IBMDDKit2004`
  (both verified live); also Hobbes. `corpus/online-sources.md` lists these and the DevCon volumes.
- **OS/2 Warp redbooks** (GG24-37xx etc.) - `komh.github.io/os2books` mirrors many as HTML/PDF.

## 3b. Third-party programming books - optional (scanned, on archive.org)

Commercial books, not IBM manuals. They earn their place by being *tutorial*: the IBM reference
tells you what `WinCreateStdWindow` takes, these tell you why the frame and client are separate
windows and what happens when you get it wrong. **Grade them `[DOC]`** - an author's reading of
OS/2, not IBM's word - and corroborate anything load-bearing against the IBM books.

`corpus/fetch-archive-book.sh <archive-id> <name>` fetches archive.org's own OCR (not the PDF) and
converts it to `$OS2DOCS/pdf_text/<name>.txt` with `[[page N]]` markers carrying the book's
**printed** page numbers, so a hit is citable as "Petzold p.144". Then ingest the result (`os2-toolkit:ingest`).

- **Charles Petzold, *OS/2 Presentation Manager Programming*** (Ziff-Davis, 1994; ISBN 1562761234).
  934 pages, 18 chapters, PM-only and 32-bit - the closest thing to a PM tutorial that exists.
  Chapters: the PM architecture and message loop (1-3), text output to a client window (4), GPI
  primitives, bitmaps/blits and advanced graphics (5-7), keyboard, mouse and timer (8-10), control
  windows, resources, menus and dialogs (11-14), clipboard (15), DLLs (16), multithreading (17),
  printing (18). Chapter 4 is the one to read first for a PM port - client-window text output,
  presentation spaces, the coordinate system and scroll bars.
  *Where:* `archive.org` identifier **`os2presentationm0000petz`** (verified live).
  ```sh
  corpus/fetch-archive-book.sh os2presentationm0000petz petzold-pm-programming
  ```
  *Caveat:* it targets OS/2 2.x with IBM C Set++, so the toolchain material (makefiles, `IBMDLL.CMD`,
  `-Ge-`) is period-specific - the PM and GPI content is not. Scanned-book text is OCR, so it is
  case-damaged and hyphenation-damaged: search fragments, case-insensitively, exactly as
  `os2-lib grep` does by default.

## 4. Test + debug target - for running what you build (commercial or free)

- **A running OS/2** to test on. **ArcaOS** (`arcanoae.com`, modern, commercial - the recommended
  target; ships GCC/kLIBC + Toolkit) or an older Warp 4.52 image (archive; abandonware, verify your
  rights). Run it in **VirtualBox** (`virtualbox.org`).
- **Kernel debugger (KDB)** - needs the OS/2 **debug kernel** installed in the VM + a VirtualBox
  host-pipe serial port. Drives with `tools/kdb_*` (see `recipes/setup-kdb-vm.md`). Only for
  low-level/driver work.
- **Build-and-run over SSH** - install OpenSSH on the VM and Claude can compile+run remotely
  (see `recipes/setup-test-vm.md`). Generate your *own* keys/passwords - none are shipped here.

## 5. Community references (live, for corroboration)

- **EDM2** (`www.edm2.com`) - the OS/2 developer wiki (per-function pages). `[DOC]`-grade, secondary.
- **Hobbes** (`hobbesarchive.com`) - the OS/2 software/source archive. The old `hobbes.nmsu.edu`
  is dead; `hobbes.os-2.in` still works as a mirror.
- **os2museum.com**, **os2world.com**, **komh.github.io/os2books** - internals, community, book mirror.
