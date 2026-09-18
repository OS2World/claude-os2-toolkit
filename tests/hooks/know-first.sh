#!/usr/bin/env bash
# know-first.sh - does the hook fire on a library search, and ONLY on one?
#
# The hook is a habit-former, so both of its failure directions cost something
# real and they are not symmetric. A missed search (exit 0 where it should have
# been 2) merely leaves the status quo. A WRONG BLOCK (exit 2 on a command that
# was never a library search) stops work and teaches a session to reach for the
# escape marker by reflex - which disarms the hook everywhere, including where
# it was right. So the boundary cases below are the point of this file, not
# decoration.
#
# It builds its own library root under a temp directory and points the hook at
# it with $OS2_LIBRARY, so it never depends on - or touches - the user's own
# library, config or knowledge store. The root is deliberately named so that a
# SIBLING directory shares its full name as a prefix ("<root>" vs "<root>dev"),
# which is the shape that a substring match gets wrong and a boundary match
# gets right.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
HOOK=$HERE/../../hooks/know-first.sh
[ -x "$HOOK" ] || { echo "  ABORT: $HOOK missing or not executable"; exit 2; }
command -v jq >/dev/null 2>&1 || { echo "  SKIP: jq absent - the hook fails open without it"; exit 0; }

T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export OS2_LIBRARY="$T/os2"
mkdir -p "$OS2_LIBRARY/docs" "$T/os2dev/aproject" "$T/os2-work" "$T/os2.old"
pass=0; fail=0

ok()  { printf '  ok    %s\n' "$1"; pass=$((pass+1)); }
bad() { printf '  FAIL  %s\n' "$1"; fail=$((fail+1)); }

# Feed one Bash tool event and report the hook's exit: 0 = let it through,
# 2 = block with the nudge on stderr.
fires() {
  printf '{"tool_name":"Bash","tool_input":{"command":%s}}' \
    "$(printf '%s' "$1" | jq -Rs .)" | "$HOOK" >/dev/null 2>&1
  echo $?
}
want() { # want <exit> <description> <command>
  rc=$(fires "$3")
  if [ "$rc" = "$1" ]; then ok "$2"; else bad "$2 (got $rc, want $1)"; fi
}

# --------------------------------------------- it fires on a library search
want 2 "a grep under the library root"        "grep -rn DosOpen $OS2_LIBRARY/docs/"
want 2 "the root with a trailing slash"       "grep -rn DosOpen $OS2_LIBRARY/"
want 2 "the bare root at end of command"      "grep -rn DosOpen $OS2_LIBRARY"
want 2 "the root inside double quotes"        "grep -rn DosOpen \"$OS2_LIBRARY/docs\""
want 2 "the root spelled via the variable"    'grep -rn DosOpen "$OS2_LIBRARY/docs"'
want 2 "a generic corpus word, outside it"    'grep -rn DosOpen ~/elsewhere/ddk/'
want 2 "rg counts as a search verb"           "rg DosOpen $OS2_LIBRARY/docs/"

# ------------------------------------- it does NOT fire on a path that merely
# ------------------------------------- starts with the root's name
want 0 "a sibling directory: <root>dev/..."   "grep -n TODO $T/os2dev/aproject/NOTES.md"
want 0 "a sibling two levels down"            "grep -rn foo $T/os2dev/aproject/src/"
want 0 "a sibling ending in a hyphen name"    "grep -rn foo $T/os2-work/x"
want 0 "a sibling ending in a dotted name"    "grep -rn foo $T/os2.old/x"
want 0 "an unrelated directory"               'grep -n TODO /tmp/notes.md'

# ------------------------------------------------------- the escapes and the
# ------------------------------------------------------- deliberate exemptions
want 0 "# know-miss lets the search through"  "grep -rn DosOpen $OS2_LIBRARY/docs # know-miss"
want 0 "# know-verify lets it through too"    "grep -rn DosOpen $OS2_LIBRARY/docs # know-verify"
want 0 "os2-lib grep is never blocked"        'os2-lib grep DosOpen'
want 0 "the cache's own tooling is exempt"    "know q 'what does DosOpen return'"

# ------------------------------------------------- only SEARCH verbs are gated
want 0 "cat under the root is not a search"   "cat $OS2_LIBRARY/docs/x.txt"
want 0 "sed -n line range is not a search"    "sed -n 100,120p $OS2_LIBRARY/docs/x.txt"

# ------------------------------------------------------------- it fails open
want 0 "a non-Bash tool event is ignored"     ""   # empty command -> exit 0

printf '\n  %d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
