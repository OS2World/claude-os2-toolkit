# `corpus/` - building and searching the OS/2 documentation corpus

> **With the plugin installed, use the OS/2 library instead of a hand-built corpus** (`../PATHS.md`):
> tell Claude what material you have and `os2-toolkit:ingest` files and converts it with these same
> scripts; `os2-lib grep` searches it. The scripts below still fetch material, and `search.sh` still
> works on its own for a corpus under `$OS2DOCS` without the plugin.

`os2ref/` is distilled and verified, but it is not exhaustive. The IBM books are:
they carry the per-function reference, the usage patterns, the contracts, and the worked examples
that no summary preserves. Sessions that consult them get materially better answers than sessions
that reason from `os2ref/` alone.

**This kit ships no IBM material.** These scripts build a corpus **on your machine** from material
you obtain yourself, and then make it searchable in a way that does not lie to you.

---

## Quick start

```sh
export OS2DOCS=~/os2docs                 # where the corpus lives (default)

inf2txt-build                            # one-time: build the INF extractor
./build-inf-text.sh /path/to/your/books  # .INF/.HLP -> greppable UTF-8 text
./fetch-books.sh                         # optional: IBM redbooks + docs mirror
./fetch-edm2.sh                          # optional: EDM2 wiki (community)
./pdf-to-text.sh --scan ~/os2docs        # optional: make the PDF books greppable
./fetch-archive-book.sh os2presentationm0000petz petzold-pm-programming
                                         # optional: a scanned book, page-citable

./search.sh DevOpenDC                    # search everything, in provenance order
```

`online-sources.md` lists more material worth knowing about - the Developer Connection and DDK
sets on archive.org, all four volumes of the OS/2 Debugging Handbook, and the live community sites.

`search.sh` works with **no** corpus at all - it just searches `os2ref/` and tells you the other
sources are absent. Each source you add makes it stronger.

## The scripts

| Script | What it does |
|---|---|
| `build-inf-text.sh` | Finds `.INF`/`.HLP` books and extracts each to `$OS2DOCS/inf_text/<book>.txt` via `tools/inf2txt`. Writes `manifest.tsv` (book, lines, bytes, source). Idempotent - re-extracts only what changed. |
| `fetch-books.sh` | Mirrors `komh.github.io/os2books`: Warp redbooks (GG24-37xx), *Undocumented OS/2*, Toolkit docs, programming FAQ, REXX, DBCS. `[DOC-IBM]`. |
| `fetch-edm2.sh` | Mirrors the EDM2 wiki as raw wikitext via its MediaWiki API (~12,300 pages). Resumable, rate-limited. `[DOC]` - community, secondary. |
| `pdf-to-text.sh` | Extracts PDF books to text with `[[page N]]` markers so hits stay citable, reports which pages had no text layer, optionally OCRs those (`--ocr`) and writes page-range chunks (`--chunk N`). |
| `fetch-archive-book.sh` | Fetches a scanned archive.org book as **archive.org's own OCR** (`_djvu.xml`, not the PDF) and converts it to `$OS2DOCS/pdf_text/<name>.txt`. Uses `_page_numbers.json` so markers carry the book's *printed* page numbers. |
| `djvu2txt.py` | The converter behind it: `_djvu.xml` -> page-marked text + `.coverage` map. Usable on its own if you already have the XML. |
| `search.sh` | Searches every present source **in provenance order** and labels each group. |
| `online-sources.md` | Curated, live-verified pointers: the DevCon/DDK sets on archive.org, all four Debugging Handbook volumes, the community sites, and what is *not* freely available. |

## Why `search.sh` instead of plain `grep`

Three ways an ad-hoc grep silently misleads you about OS/2 documentation. Each one produces an
**empty result**, and an empty result reads as *"IBM never documented this"* - which sends a model
off to invent an answer. That is the single most expensive failure mode in this kit.

1. **Encoding.** Extracted book text is often in an IBM code page, not UTF-8. GNU grep classifies
   such a file as *binary* and prints **nothing at all** - no error, no `Binary file ... matches`, no
   count. `search.sh` always passes `-a`, and `build-inf-text.sh` warns about any book that is not
   UTF-8/ASCII.
2. **Wrong volume.** The books are split (`gpi1`-`gpi4`, `pm1`-`pm5`) and some volumes are
   front-matter stubs - `gpi1.txt` is a few hundred lines while the real GPI reference is `gpi2.txt`
   at ~40,000. Searching one volume and finding nothing looks identical to a genuine absence.
   `search.sh` searches all of them and reports per-source counts.
3. **Provenance laundering.** An EDM2 hit is not IBM's word. `search.sh` searches
   `os2ref/` -> IBM books -> IBM redbooks -> PDF books -> EDM2, labels each group with its provenance
   grade, and never merges them.
4. **Case.** Text recovered from typeset or scanned books is case-damaged. One real book here
   renders `WinCreateStdWindow` as `Wincreatestdwindow` and `DosAllocMem` as `DOSAllocMem`, so
   `grep WinCreateStdWindow` finds **zero** in a book that documents both. `search.sh` always
   searches case-insensitively.
5. **Table layout.** IBM lays out much of its reference material in box-drawn tables, which split
   sentences across cell boundaries mid-phrase:

   ```
   |Alphabetic     |Selects the first menu item with the         |
   |character      |specified character as its mnemonic key.     |
   ```

   Grep the whole sentence and you get nothing, from a book that states it plainly. **Search a
   distinctive fragment** - three to five words that fit inside one cell - then read the
   surrounding lines. No tool can fix this for you; it is a habit. This trap nearly caused a
   correct, verbatim IBM citation in this kit to be recorded as unsourced.

On zero hits it prints what to try next rather than letting you conclude absence.

## Provenance - keep the grades straight

| Source | Grade | Means |
|---|---|---|
| `os2ref/` | verified, per-claim tags | Already distilled and sourced. Start here. |
| `inf_text/`, `os2books/` | `[DOC-IBM]` | IBM's own words. Authoritative for meaning. |
| `pdf_text/` | `[DOC-IBM]` or third-party book | Check which: an IBM redbook is IBM's word; a commercial book is its author's reading of OS/2. |
| `edm2/` | `[DOC]` | Community, secondary. Corroboration and terminology, not authority. |

When you take a fact from the corpus into code or docs, carry its grade with it and cite the book
(e.g. *"IBM Control Program Guide & Reference (cpgref.inf)"*). Never promote a `[DOC]` fact to
`[DOC-IBM]` because it sounded confident.

## Rights

Everything these scripts fetch or convert belongs to someone else - mostly IBM, whose OS/2
documentation is no longer sold but still copyrighted, and EDM2, which publishes no
machine-readable licence.

- Build the corpus **for your own use**, on your own machine.
- **Do not redistribute it**, and do not commit it into a project. `$OS2DOCS` is deliberately
  outside this repo, and this kit ships none of it.
- `fetch-edm2.sh` rate-limits itself. Leave that alone.

See `../sources.md` for where each source comes from and the rights note that governs it.

## Notes

- The corpus is large: `inf_text` ~27 MB, `os2books` ~90 MB, `edm2` ~40 MB.
- `search.sh` honours `SEARCH_MAX` (hits shown per source, default 40) and `SEARCH_CONTEXT`
  (grep `-C`, default 0).
- PDFs in `os2books` are not greppable until converted; `fetch-books.sh` prints the `pdftotext`
  one-liner.
- For an archive.org scan, prefer `fetch-archive-book.sh` over downloading the PDF and running
  `pdf-to-text.sh` on it: archive.org has already OCRed the book and publishes the result, so the
  fetch is ~19 MB of XML instead of a ~44 MB PDF you would then have to OCR yourself. It also
  yields the *printed* page numbers, which a PDF's page count does not give you.
- Scanned-book text carries three markers: `[[page N]]` is a printed page number **read off the
  page**; `[[page N ~]]` is one archive.org **interpolated** because it found no folio there (cite
  as approximate - 82 of this book's 931 are inferred); `[[leaf N]]` is a scan image with no printed
  number at all (covers, front matter, plates). Do not cite a leaf as a page.
  `<name>.coverage` lists which leaves yielded no text - check it before reading a search miss as
  the book being silent.
- **The two producers of `pdf_text/` do not agree on what `[[page N]]` means.**
  `fetch-archive-book.sh` emits the book's *printed* page number; `pdf-to-text.sh` emits the *Nth
  page of the PDF*. For a book with front matter these differ by a constant offset (32 in the
  Petzold scan). Check which tool produced a file before citing a page number out of it.
- Already have a corpus from earlier work? Point `OS2DOCS` at it. `search.sh` expects
  `inf_text/`, `os2books/`, `edm2/` under that root and skips whatever is missing.
