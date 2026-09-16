---
name: know
description: Search the OS/2 knowledge cache before grepping the IBM books, the DDK, the Toolkit or any other reference material - and record what a session establishes, and what it searched for and did NOT find. Use it for any OS/2 fact question before a broad grep over the library, and whenever a session produces a fact worth keeping or hits a dead end worth recording.
---

# The knowledge cache

`know` indexes this machine's OS/2 reference material and answers in
milliseconds what otherwise costs a session several greps and a lot of context.
**Search it before searching the books.**

    know q 'what does DosQuerySysInfo index 31 report'

A PreToolUse hook nudges you here on a broad grep of the reference material. It
is a one-shot block with the escape in its own message.

## Why first, and not instead

Two different things live in the store:

- **The material** (chunked, searchable): whatever the OS/2 library holds -
  IBM books and redbooks, the Toolkit and DDK headers and shipped driver
  source, community article sets, and any RE write-ups and notes the library
  carries. This kit's own `${CLAUDE_PLUGIN_ROOT}/os2ref/` is **not** indexed by
  default - `know ingest md ${CLAUDE_PLUGIN_ROOT}/os2ref` adds it if you want it
  in the same ranking. `know stats` is the
  authority for what is actually indexed. This half is **retrieval, not
  knowledge** - it tells you WHERE to look. Anything load-bearing is then
  re-opened in the primary source: the store is the SUBJECT of verification,
  never the authority.
- **Facts and searches** (curated, verifiable): what a session established, each
  with a `verify_cmd` that re-derives it, and - the part a grep can never give
  you - **negative results**. A grep that returns nothing looks identical
  whether nobody has ever looked or three sessions have proven the thing absent.
  `know` says which.

## Reading a hit, and reading a miss

Hits are ranked, each with its source path and a snippet. Phrase a query in
words, not as a regex; retrieval is full-text with stemming and heading
weighting. If it comes back thin, try IBM's term rather than yours - the
material uses IBM's spelling (`InfoSegGDT`, not "the GIS struct").

**A miss is a result, not a failure.** When the cache does not answer:

1. Search the library itself: `os2-lib grep PATTERN` searches in provenance
   order (this kit's `os2ref/` first, then IBM material, then community
   material, then notes), with per-source counts and a list of what it could
   not search. `os2-lib role toolkit-headers headers` finds material by role
   when you know which item you want.
2. Re-run the blocked command with `# know-miss` appended if you still want the
   raw grep. **Record the miss rather than routing around it** - a miss is the
   only honest signal of what the cache still lacks.
3. If you were verifying a hit against the primary source, append
   `# know-verify` instead. Same effect; it just tells a reader of the transcript
   that this was a verified hit being re-checked, not a gap in the cache. Neither
   escape writes anything: the hook is stateless.

If a role the question needs is missing from the library entirely, say which
material is missing and ask whether the user has it - do not go looking through
the disk on your own.

## Recording what you learn

The cache is only as good as what goes in, and almost nothing goes in
automatically.

    know add --subject 'DosQuerySysInfo' --component doscalls --kind contract \
        --prov DOC-IBM --corrob ibm-doc \
        --cite 'bsedos.h:2616' \
        --verify 'grep -q QSV_MAX "$(os2-lib role toolkit-headers headers)/bsedos.h"' \
        -m 'QSV_ index 30 is per-machine, so a captured value is a fact about one box'

    know absent --question 'is FSH_CALLDRIVER documented in the IBM books' \
        --tier ibm-primary --target 'ibm-books' --verdict absent \
        --verify 'os2-lib grep FSH_CALLDRIVER --role ibm-books' \
        --result 'zero hits across the book set; the contract is DDK-only'

A citation must name something the next reader can open: a `file:line` in a header or
source, library material by role or item path, a binary plus an offset, or **an IBM book
plus a quoted topic** - `pm2.txt "WinLoadString - Syntax"`. The quotes are not decoration:
the book alone is thousands of panels, so `know` refuses it.

**A fact without a `verify_cmd` is a memory, not knowledge.** `know verify --all`
re-runs every one and reports AGREE / DISAGREE / UNCHECKABLE, and re-runs each
negative to catch the dangerous case: a search that found nothing then and finds
something now. A negative you got wrong is retracted with `know supersede`,
which drops it from the sweep while keeping its text and its wrong command - the
command is the lesson.

Three rules the tool enforces, each paid for:

- **A citation is required.** A row without one is a guess wearing a database.
- **A `verify_cmd` must be able to fail on the CONTESTED half.** Ask what the
  command would print if the claim were false in the specific way it can be
  false, then build that case and run it. A verify that checks the half nobody
  doubts reads AGREE forever about the half that is wrong.
- **A fact is about OS/2**, not about a project's own code or state. Project
  state changes every day, so a row keyed to it is stale on arrival and belongs
  in that project's own docs. Recording where *you* looked is different - that
  is what the search ledger is for, and it is project state by nature.

Provenance tags are the ones ratified in `${CLAUDE_PLUGIN_ROOT}/os2ref/README.md`;
the tool refuses combinations that contradict them, and no automated run may
raise a tag on its own.

## How it relates to the rest of the kit

| | |
|---|---|
| `know q` | the cache: derived facts, recorded negatives, and an index of the material. **First.** |
| `os2-lib grep` / `os2-lib role` | the library itself, in provenance order. **After a miss.** |
| `${CLAUDE_PLUGIN_ROOT}/os2ref/` | the permanent, source-tagged reference. Its `README.md` is the router, and it is where a durable fact eventually graduates to - via the `contribute` skill, not by editing an installed plugin. |

## Verbs

| | |
|---|---|
| `q '<question>'` | search; `--limit N` for more hits, `--corpus html\|inf\|md\|redbook\|source` to scope, `--facts` for derived facts only |
| `add` / `absent` | record a fact, or a search that found nothing |
| `verify --all` | re-run every `verify_cmd`; the store's own regression test |
| `show N` / `log` | one row with its provenance; recent activity |
| `supersede` / `promote` | retract a row in place; raise a provenance tag |
| `ingest` | index the library (`--role`/`--category`/`--item`, `-n` to dry-run), or explicit paths |
| `stale` / `refresh` | which ingested files changed; re-index just those |
| `stats` | what the store holds, and where |
| `export DIR` / `import FILE` | readable prose plus a lossless `know.jsonl`; `import --force` restores rather than merges |

The store is machine-local and deliberately unversioned - an OS/2 fact cannot
legally differ between branches, and versioning it would manufacture exactly
that incoherence. It lives at `$OS2_KNOW_DB`, defaulting to
`~/.local/share/os2-toolkit/know.db`, outside any working copy, because a SQLite
file cannot be merged. `know export` is what you commit.
