# Contributing

This kit is two things at once, and both matter:

1. **A reference** - verified, source-tagged facts about OS/2 and about the software people build
   OS/2 programs with.
2. **A finding aid** - pointers to where IBM's own documentation actually lives, and tooling
   (`corpus/`) to make it searchable once you have it.

It is **not** a store of IBM documents. We ship no IBM files. We say where they are, and if you
download them and cite them, that is exactly the intended use.

That distinction is the whole legal posture of the project, and a contributor is the person who can
break it. Everything below follows from it.

> **This file is for humans and for Claude.** The common contribution loop is a user telling a
> session *"update the toolkit with what I just found, and cite the sources"* - so these are written
> as checkable rules, not aspirations. If you are a session doing that: read this first, then apply
> the checklist at the end before you commit.

---

## 1. Facts, not expression

**Trigger:** You are about to add something you learned from an IBM book, header, or any other
copyrighted source.

**Action:** Contribute the *fact*, in your own words, with a citation. Never paste the source's
prose.

| Contribute freely | Never paste |
|---|---|
| Names, values, offsets, struct layouts, field order | IBM's paragraphs describing them |
| Prototypes, ordinals, error codes, flag meanings | Worked examples and sample listings copied whole |
| Call ordering, preconditions, what a return value means | Diagrams, tables lifted entire, page scans |

Facts about a published interface are not anyone's property; the words used to explain them are.

**The seam:** short attributed quotation is fine where IBM's exact wording *is* the fact - a clause
or a sentence, tagged and sourced:

> "the order of the DEVICE and DEVICEHIGH commands ... is important" [DOC-IBM - GG24-3731 section CONFIG.SYS]

A clause, not a section. If you find yourself quoting a paragraph, you are transcribing - restate it
instead.

**Calibration.** You may write *"`WinLoadString` returns the string length; 0 means error"* and cite
`pm2.txt "WinLoadString Return Value - lLength"`. You may not reproduce IBM's paragraph that says so.

**A list of names in functional order is a fact, not expression.** A linker's search order, an
ordinal table, a set of flag values - there is no authorial choice in them, and there is no honest
way to "reword" `_dll.lib, .lib, _s.lib` into something else. Reproduce the list; cite where you read
it. What you must not lift is the prose around it. And **prefer the primary source**: if the
behaviour lives in code, cite the code (`src/emx/src/emxomf/emxomfld.c:924`, `[SRC]`) - repo-relative,
per section 4 - rather than the release note that
once described it - notes go stale, code is what the reader can re-check, and "I found this in a doc
on my disk" is not a citation anyone else can follow.

**Avoid the word "verbatim"** when describing a transcription of names and values. It is accurate
about your process and misleading about what shipped. Prefer *"names and values transcribed from
`bseerr.h`"*.

## 2. Every claim carries its provenance

**Trigger:** You are adding a claim to `os2ref/`.

**Action:** Tag it, and name the source precisely enough for the next reader to re-check it -
`file:line` for headers and source, book plus topic for `.INF` material.

| Tag | Means | Cite |
|---|---|---|
| `[DOC-IBM]` | IBM's word: a Toolkit/DDK header, an IBM book, a redbook | `bsedos.h:2616`, `pm2.txt "WinLoadString - Syntax"` |
| `[OBS-RE]` | Observed by reverse-engineering a binary or a debugger session | what you ran, on what |
| `[DOC]` | Community/secondary: EDM2, osFree, period references | the page or project |
| `[SRC]` | Read from the source of a component that runs *on* OS/2 but is not OS/2 | repo-relative `path:line` |
| `[unverified]` | You could not source it - say so instead of asserting it | - |

Full key: `os2ref/README.md`.

**Never promote a grade.** A community claim does not become IBM's word because it sounded
confident, and a `[SRC]` reading of kLIBC says nothing about what OS/2 itself guarantees.

**If you cannot source it, do not add it.** "I know this" is not a citation - it is unfalsifiable,
and in a corpus whose only value is trustworthiness it is worse than a gap. An honest
`[unverified]` marker is a contribution; a confident guess is damage.

## 3. Non-IBM software is in scope

kLIBC/LIBC Next, GCC, OpenWatcom, netlabs ports, the RPM ecosystem - these are how modern OS/2
development actually happens, and facts about them belong here. `os2ref/klibc-runtime-glue.md` is
the model: source-verified, `[SRC]`-tagged, and explicit that it describes *that component*, not the
platform.

Keep the boundary visible. When a component's behaviour and OS/2's documented behaviour differ, say
which is which rather than blending them.

## 4. No machine paths, ever

**Trigger:** You are about to write a path from your own disk.

**Action:** Replace it with a repo-relative path, a placeholder, or a description of how to find it.

This is not only privacy - it is **portability**. This corpus lands on strangers' machines, which
have different layouts, different mount points, and frequently a different operating system. A path
like `/home/you/src/libc` or `D:\work\toolkit` is guaranteed wrong for almost every reader, and
"wrong but plausible" is the failure mode this whole kit exists to prevent.

Write `src/emx/src/lib/sys/__read.c:74` (repo-relative, resolves in anyone's clone).
Write "the Toolkit's `H/` directory, wherever you unpacked it".
Never write where *yours* is.

## 5. De-identify before you submit

**Trigger:** The fact you are contributing came out of work on your own project.

**Action:** Keep the OS/2 fact. Strip everything that identifies where you learned it.

The best contributions come from people deep inside a real project - that is what produces a fact
worth recording - and that is exactly where private detail leaks from. Before submitting, remove:

- your project's or employer's name, and internal codenames
- machine paths, hostnames, VM names, usernames
- references to internal documents ("see our `DESIGN.md`") - the reader has no such file
- dates that map to your working calendar, and internal incident names
- your project's architecture, module layout, or implementation status

A war story keeps its teeth without any of that. *"A `memset` through a server-backed shared mapping
wiped another process's live data system-wide"* teaches the lesson; naming the codebase adds
nothing.

## 6. The lessons-learned format

This is what distinguishes this corpus from a manual. A manual says what the API is; this says what
it costs to get wrong.

A strong contribution has four parts:

1. **The trap** - what looked right and wasn't, or what you expected to find and didn't.
2. **The fact** - the thing that actually resolved it, tagged and sourced.
3. **How to verify it** - the grep, the header line, the command that shows it.
4. **The tell** - how someone recognizes this situation before losing an afternoon to it.

**Negative results are contributions.** *"Searched the DDK for a documented SIQ consumer protocol -
absent; stop looking"* converts an open-ended search into a closed question, and it is expensive to
produce and free to record. Record it with what you searched and how, so the next person can tell
your negative from a failed search.

**Corrections supersede in place.** If you find something here is wrong, do not silently replace it:
mark the old claim, cite what overturned it, and say why the wrong reading was natural. The next
reader will have the same plausible thought.

## 7. Verify before you commit

Most defects found in this repo's own audits were not wrong facts - they were **documented commands
that had never been run** and counts that had drifted. Check these:

- **If you document a command, run it.** Exactly as written, from the directory the doc implies.
- **If you add a tool flag, confirm it exists.** A documented flag the code lacks is a lie with a
  helpful tone.
- **If you add an `os2ref/` doc:** add it to the router table *and* the contents list in
  `os2ref/README.md`, and update the doc count in `README.md`, `skills/os2-dev/SKILL.md`, and
  `os2-app-dev-guide.md` (all three state it).
- **Check your links.** Every `](path)` and every backticked `dir/file.md` must resolve.
- **Write 7-bit ASCII only** - docs, scaffolds and tools alike. These files get read and edited on
  OS/2, where text is CP850 or CP437, not UTF-8. Most of what a model reaches for by habit (em
  dash, `->` as an arrow glyph, ellipsis, box drawing) exists in *neither* code page, and the few
  that do exist disagree between them: the section, multiplication and copyright signs are CP850
  only; the less-or-equal and greater-or-equal signs are CP437 only. Pick either code page and the
  file renders wrong for whoever has the other.
  ASCII is byte-identical in CP437, CP850, Windows-1252 and UTF-8, so it is the one safe answer.
  This matters most in `scaffolds/` - a stray U+2014 in a comment is what turns a `.c` file into
  `Non-ISO extended-ASCII`, and then `grep` goes silent on it (`recipes/read-ibm-books.md`).
  Check with:

  ```sh
  grep -rnP '[^\x00-\x7F]' $(git ls-files | grep -v '^tools/inf2txt/fpGUI/')   # must print nothing
  ```
- **Do not commit downloaded material.** The OS/2 library (`PATHS.md`) lives outside the repo for this reason. No
  `.INF`, no PDFs, no book text, no header dumps.
- **Re-read your diff for machine paths and project names** (section 4, section 5).

## 8. Where things go

| Path | Content |
|---|---|
| `os2ref/` | Facts about OS/2 and about what runs on it. Provenance-tagged. |
| `recipes/` | Procedures: install, build, test, debug, port. Runnable commands. |
| `c-guide.md` | The craft of writing correct OS/2 C. |
| `corpus/` | Tooling to build and search a local documentation corpus. |
| `scaffolds/` | Minimal working programs. They are copied - so they must model the kit's own disciplines, including checking every return value. |
| `sources.md`, `corpus/online-sources.md` | Where the real documentation lives. |

## 9. Contributor affirmation

Include this in your pull request (or your commit message, if you push directly):

> I affirm that this contribution states facts in my own words, does not paste copyrighted text
> beyond short attributed quotation, cites its sources, and contains no paths, names, or details
> specific to my machine or my project.

This is not paperwork. It is the single check that keeps the project's licensing claim true -
that it redistributes no IBM or third-party material - and that claim is worth more to every user
than any individual contribution.

---

## For a Claude session updating the toolkit

When a user says *"update the toolkit with what I just found and cite the sources"*:

1. Decide where it belongs (section 8) - a fact goes in `os2ref/`, a procedure in `recipes/`.
2. Tag every claim and name its source (section 2). If the user's finding came from a book, cite the book
   and topic; from a header, `file:line`; from your own run, `[OBS-RE]` with what you ran.
3. Restate - never paste (section 1).
4. Strip machine paths and project identifiers (section 4, section 5) - including from anything the user pasted at
   you.
5. Write it in the lessons-learned shape (section 6): the trap, the fact, how to verify, the tell.
6. Run the section 7 checklist. Actually run the commands you documented.
7. Include the section 9 affirmation in the commit message.

If you cannot source a claim, say so and leave it out, or mark it `[unverified]`. Adding a plausible
unsourced fact to this corpus is the one failure it cannot absorb.
