# Reading IBM `.INF` books as text (`inf2txt`)

The IBM programming books ship as compiled `.INF` (IPF) files - binary, not greppable. `inf2txt`
extracts the article text so you (or Claude) can read a subsystem `os2ref/` doesn't fully cover.
Get the books per `../sources.md` section 3.

```sh
# one-time build (Linux): needs Free Pascal + a fpGUI checkout (see tools/inf2txt/README.md)
inf2txt-build                                  # produces the inf2txt binary

# use it
./inf2txt.sh /path/to/cpgref.inf > cpgref.txt  # -> clean UTF-8 text on stdout
grep -a -n "DosOpen" cpgref.txt                # then grep the topic you need
```

## An empty grep result does not mean "IBM doesn't document it"

**This is the most dangerous failure mode in the whole kit, because it fakes a successful
verification.** The text inside an `.INF` is stored in an IBM PC code page (CP850 for the OS/2
programming books), not UTF-8. If that text reaches a file untranscoded, `file` reports it as
`ISO-8859 text` and **GNU grep classifies it as binary and prints nothing at all** - no error, no
`Binary file ... matches`, no count, just an empty result and exit status 1. Demonstrated on a real
book:

```
$ grep -c "code page" pm5.txt        # raw CP850 bytes
$                                    # <- nothing. exit 1. looks like "0 matches"
$ grep -ac "code page" pm5.txt       # same file, -a
42
```

Read literally, the first result says *IBM never documents code pages* - in the volume whose
section "Code Pages" defines the entire model. A model that then "can't find it in the docs" will fall back
on training and invent an answer, which is precisely what `os2ref/` exists to prevent.

Two defences, use both:

1. **`inf2txt.sh` now transcodes to UTF-8** (CP850 by default; override with `INF2TXT_CP=CP437`).
   Books converted with it are greppable normally. Re-convert any `.txt` you generated with an
   older version:

   ```sh
   # test: silent = already UTF-8, error = still needs converting
   iconv -f UTF-8 -t UTF-8 < book.txt >/dev/null

   # convert in place (back up first)
   iconv -c -f CP850 -t UTF-8//TRANSLIT book.txt > book.new && mv book.new book.txt
   ```

   **Do not use `file` to decide this.** It samples only the head of the file, so a book that is
   ASCII for its first few KB and CP850 later is reported as plain `ASCII text` - a false clean
   bill. It also reports valid-UTF-8 books as `data` when they contain many OEM glyph bytes
   (`0x07`, `0x10`, `0x1E`, `0x1F` - bullets and arrows in the IPF source, which CP850 defines as
   control codes), a false alarm in the other direction. `iconv -f UTF-8 -t UTF-8` reads the whole
   file and answers the question you actually care about.
2. **Always pass `grep -a`** when searching converted books, regardless. It costs nothing and it is
   the only thing that saves you if a file slipped through untranscoded. `LC_ALL=C` does **not**
   fix this - only `-a` does.

### This is not a books-only trap [OBS-RE]

The same silence hits **any** OS/2-era text file, and the case that actually costs you time is
**source code**. OS/2 sources are routinely CP437/CP850 - an author's name in a copyright header
is enough. A real instance: XWorkplace's `src/filesys/filedlg.c` is `Non-ISO extended-ASCII`
because the copyright line reads "Ulrich Moller" with an o-umlaut on that 'o' (byte 0x94 under
CP850), and:

```
$ grep -c "#include" filedlg.c            # a 1724-line C file
$                                         # <- nothing at all. exit 1.
$ LC_ALL=C grep -ac "#include" filedlg.c
31
```

Read literally, the first result says *this C file has no includes* - and a dependency analysis
built on that is worthless. The same applies to `.DEF`, `.RC`, `.CMD`, `README`, and `.TMF` help
sources shipped by OS/2 projects.

So: **pass `-a` to every `grep` in this ecosystem, not just the ones aimed at books.** And when
any search returns nothing, re-run it against a string you *know* is present before believing the
negative - the general rule in `START-HERE.md` section 3, of which this is the most common concrete form.

Also sanity-check the file before trusting a negative: `wc -l` it. `gpi1.txt` is a 354-line stub
(front matter only) while the real GPI reference is `gpi2.txt` at ~40 000 lines - searching the
wrong volume produces the same false "not documented" answer by a different route.

**Search fragments, not sentences.** IBM lays out much of its reference material in box-drawn
tables, so a statement is split across cell boundaries mid-phrase:

```
|Alphabetic     |Selects the first menu item with the         |
|character      |specified character as its mnemonic key.     |
```

`grep "selects the first menu item with the specified character"` finds **nothing** here - the
book says it, the line breaks hide it. Grep three to five words that fit inside one cell
(`"as its mnemonic key"`), then read the lines around the hit. This is the failure mode most
likely to make you believe an accurate quotation was invented.

No binary is shipped - `inf2txt-build` (`tools/inf2txt/build.sh`) produces `~/.local/share/os2-toolkit/inf2txt/inf2txt` locally (one-time, ~30 s). It
links fpGUI's docview parser, so the build needs an fpGUI checkout; `tools/inf2txt/README.md` has
the prerequisites.

Useful books and what they hold: `cpgref` (Control Program / `Dos*`), `pm1`-`pm5`/`pmv2base` (PM),
`gpi1`-`gpi4` (GPI), `pddref` (drivers), `mmref1`-`3` (multimedia), `somref`/`somguide` (SOM),
`wps1`-`wps3`/`wpsguide` (Workplace Shell), `rexxpg`/`rexxbase` (REXX). The same books also live in
the OS/2 Toolkit's `BOOK/` directory.

**Provenance:** text from these books is authoritative IBM - tag facts `[DOC-IBM]` and name the book.
