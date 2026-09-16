#!/usr/bin/env bash
# PreToolUse (Bash) hook - search the knowledge cache before re-reading the books.
#
# WHY: the OS/2 reference material is large (IBM books, the Toolkit and DDK,
# redbooks, community articles, RE write-ups), and a session that greps it by
# hand pays the same cost every time. `know q` indexes it and answers in
# milliseconds, AND it surfaces any NEGATIVE RESULT already recorded for the
# question - "searched X, absent, stop looking" - which a fresh grep can never
# tell you. A grep that comes back empty looks identical whether nobody has ever
# looked or three sessions have already proven the thing absent.
#
# WHO IT IS FOR: not mainly the interactive session. Every SUBAGENT re-grounds
# from cold over the same books, so a reviewer and an implementer can re-open
# the same DDK pages on the same question inside one dispatch. This hook fires
# inside a subagent's Bash calls too, which is the population it was built for.
#
# BEHAVIOUR: this is a ONE-SHOT NUDGE, not a wall. It fires only on a SEARCH
# VERB aimed at reference material, and it tells you how to proceed in the same
# message. If `know` does not answer, append `# know-miss` to the command and it
# passes.
#
# WHY A BLOCK RATHER THAN AN ADVISORY: an advisory printed alongside a command
# that already ran is read after the fact and changes nothing. The point is to
# reorder two actions, which only works if the second one pauses. The escape is
# one token and needs no permission.
#
# TWO ESCAPES, BOTH PURE SYNONYMS AT THE PASS/BLOCK LEVEL. `# know-miss` says
# the cache did not answer. `# know-verify` says it DID and you are now checking
# that answer at the primary source - which is the correct next act after a hit,
# not a miss, and under review it is a routine one. They behave identically here
# on purpose: no state, no conditionality, nothing that makes either more
# expensive than the other. Only the miss LEDGER reads differently, and that is
# the whole reason for splitting them.
#
# THE ESCAPE IS LOAD-BEARING. This indexes a CACHE, not an authority. A cache
# miss must therefore stay CHEAP. Nothing here may make a miss more expensive,
# harder to express, or conditional on state. The marker is stateless on
# purpose: no TTL to tune, nothing to go stale between sessions, and it leaves
# the miss visible in the transcript - which is the only honest signal of what
# the cache should hold next.
#
# SCOPE / LIMITS: a regex cannot parse shell quoting, so this is neither sound
# nor complete. It is a habit-former, not a boundary. It deliberately does NOT
# fire on: anything carrying `# know-miss` or `# know-verify`; the know tooling
# itself or this hook (or it would block the work of auditing it); `os2-lib`,
# which is the library-aware search the deny message hands you (a guard that
# blocks the alternative it recommends teaches you to route around it); or a
# NON-SEARCH verb - `sed -n 100,120p`, `cat`, `less` - no matter what file it
# names. It discriminates on VERB, not on file count: `grep PATTERN one-book.txt`
# fires, and should, because searching one book for a fact is the exact target.
#
# IT FAILS OPEN, ALWAYS. No `set -e`: any error, a missing `jq`, an unset or
# unresolvable library, a malformed event - exit 0 and let the command through.
# A hook that breaks a session because a path is not configured is worse than no
# hook at all. It is also shell only, no python and no filesystem walk beyond
# reading one small config file, because a hook has a ~5s timeout.

command -v jq >/dev/null 2>&1 || exit 0

event="$(cat 2>/dev/null)" || exit 0
[ -n "$event" ] || exit 0

tool="$(printf '%s' "$event" | jq -r '.tool_name // "Bash"' 2>/dev/null)" || exit 0
[ "$tool" = "Bash" ] || exit 0

cmd="$(printf '%s' "$event" | jq -r '.tool_input.command // ""' 2>/dev/null)" || exit 0
[ -n "$cmd" ] || exit 0

# explicit escapes, and never interfere with the cache's own tooling, with this
# hook, or with the library search this hook's own message recommends.
case "$cmd" in
  *know-miss*|*know-verify*) exit 0 ;;
  *"know-first"*)            exit 0 ;;
esac

# The cache's own tooling, and `os2-lib` - the library search this hook's own
# deny message hands you. Matched at a COMMAND POSITION, never as a substring.
#
# THAT IS NOT A STYLE CHOICE, IT IS A MEASURED DEFECT. A library root is very
# often spelled with "os2-lib" inside it (`.../os2-library` is the obvious
# name), so a bare `*"os2-lib"*` escape exempted every command naming such a
# root - which is precisely the hook's main case, switched off by its own
# exemption, silently, in the direction that never reports. Measured before the
# fix: `grep -rn DosOpen /srv/os2-library/source/ibm-ddk/tree/` exited 0 where
# it must exit 2; after, it exits 2 while `os2-lib grep ...` still exits 0.
#
# Known limit, accepted: an unquoted `grep know docs/` reads as an invocation of
# the tool and passes. Quoted or path-prefixed forms do not.
printf '%s' "$cmd" |
  grep -Eq '(^|[|;&(){}`[:space:]])([^[:space:];&|(){}`]*/)?(know|os2-lib)([[:space:]]|$)' && exit 0

# Drop HEREDOC BODIES before matching. Writing prose that MENTIONS the reference
# material - a doc edit, a commit message, this comment - is not searching it,
# and scanning the whole command string made every such command a false positive
# whenever any unrelated `grep` appeared elsewhere in it.
#
# Three things this stripper gets right, each of which was a defect once:
#  1. all THREE legal delimiter quotings are recognised (`<<EOF`, `<<'EOF'`,
#     `<<"EOF"`), because a double-quoted heredoc whose body is not stripped is
#     exactly the false positive the stripper exists to prevent;
#  2. a C/Python LEFT SHIFT (`1<<PAGE_SHIFT`) is not a heredoc: the scan is
#     TWO-PASS and treats `<<WORD` as an opener only if its terminator actually
#     occurs on a later line, so a stray shift cannot swallow the rest of the
#     command and blind the hook. It fails toward firing, not toward going blind;
#  3. `<<-` allows a tab-indented terminator, so the terminator search strips
#     leading whitespace when the opener was `<<-`.
#
# Known residual gap, left alone deliberately: TWO heredocs opened on one line
# (`cmd <<A <<B`) - B's body is not recognised and its prose can fire the hook.
# That is a false positive costing one token, and tracking a stack of pending
# terminators is where this stops being a regex and starts being a shell parser.
stripped="$(printf '%s\n' "$cmd" | awk '
  { L[NR] = $0 }
  END {
    for (i = 1; i <= NR; i++) {
      line = L[i]; rest = line; end = 0
      while (match(rest, /<<-?[\047\042]?[A-Za-z_][A-Za-z0-9_]*[\047\042]?/)) {
          rs = RSTART; rl = RLENGTH
          t = substr(rest, rs, rl)
          dash = (substr(t, 3, 1) == "-")
          gsub(/^<<-?[\047\042]?|[\047\042]$/, "", t)
          for (j = i + 1; j <= NR; j++) {
              s = L[j]; if (dash) sub(/^[ \t]+/, "", s)
              if (s == t || s == t ";") { end = j; break }
          }
          if (end) break
          rest = substr(rest, rs + rl)
      }
      print line
      if (end) i = end
    }
  }' 2>/dev/null)" || exit 0
[ -n "$stripped" ] || exit 0

# a SEARCH verb - reading one known file is not what this is about. `awk` and
# `sed` are deliberately ABSENT despite `awk /pat/ f` and `sed -n /pat/p f`
# being searches: adding them fires on far more commands that are not knowledge
# questions than it catches ones that are. False positives cost more than false
# negatives here - a wrong block stops work and teaches evasion, a wrong pass is
# merely the status quo - so the trade is refused.
printf '%s' "$stripped" |
  grep -Eq '(^|[|;&(){}`[:space:]])(grep|rg|ag|ack|zgrep|fgrep|egrep)([[:space:]]|$)' || exit 0

# ...aimed at the OS/2 reference material.
#
# Resolve the library root the way PATHS.md section 2 documents: $OS2_LIBRARY,
# else the one-line path in ${XDG_CONFIG_HOME:-~/.config}/os2-toolkit/library,
# else the default ${XDG_DATA_HOME:-~/.local/share}/os2-toolkit/library. One
# small file read, no walk, no stat of the tree - the root does not have to
# EXIST for a command naming it to be a search of the library, and an unset or
# unreadable config is not an error here, it just leaves the generic words below
# to decide.
lib="${OS2_LIBRARY:-}"
if [ -z "$lib" ]; then
  cfg="${XDG_CONFIG_HOME:-$HOME/.config}/os2-toolkit/library"
  if [ -r "$cfg" ]; then
    lib="$(head -n 1 "$cfg" 2>/dev/null | tr -d '\r' | sed 's/[[:space:]]*$//')"
  fi
fi
[ -n "$lib" ] || lib="${XDG_DATA_HOME:-$HOME/.local/share}/os2-toolkit/library"
case "$lib" in "~/"*) lib="$HOME/${lib#~/}" ;; esac

hit=0
# a target under the library root, spelled literally or through the variable
case "$stripped" in
  *"$lib"*|*'$OS2_LIBRARY'*|*'${OS2_LIBRARY}'*) hit=1 ;;
esac

# ...or a few generic OS/2 corpus words, so material outside the library (a
# download not yet ingested, a corpus on another volume) is recognised too.
# Deliberately short and bounded: each word names IBM material, a book set, or
# this kit's own reference, and none of them is ordinary English.
if [ "$hit" -eq 0 ]; then
  printf '%s' "$stripped" |
    grep -Eqi '(^|[^A-Za-z0-9])(ddk|os2tk45|os2docs|os2ref|inf_text|edm2|redbooks?|toolkit-headers|ibm-books|debugging_handbook)([^A-Za-z0-9]|$)' && hit=1
fi

[ "$hit" -eq 1 ] || exit 0

cat >&2 <<'MSG'
The knowledge cache indexes this machine's OS/2 reference material and answers
in milliseconds. Try it first:

    know q '<your question in words>'

It also reports any NEGATIVE result already recorded ("searched X, absent") --
which a grep returning nothing cannot distinguish from "nobody has looked".

If it does not answer, search the library itself with `os2-lib grep PATTERN`
(provenance order, per-source counts, and a list of what it could not search),
or re-run this command with `# know-miss` appended and it will proceed.
The miss is the point: it shows up in this session's transcript, which is the
only honest signal of what the cache still lacks. (This hook writes nothing -
it is stateless; the escape is a marker, not a ledger entry.)

If it DID answer and you are now checking that answer against the primary
source, append `# know-verify` instead. Same effect here; it just tells anyone
reading the transcript that this was a verified hit being re-checked, not a gap
in the cache.
MSG
exit 2
