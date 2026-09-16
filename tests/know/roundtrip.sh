#!/usr/bin/env bash
# roundtrip.sh - does `know export` | `know import` actually preserve the store?
#
# The store's durability argument is this round trip: the database itself is a
# machine-local cache nobody backs up, and what survives is the export. A
# previous version of this tool shipped a claim that the store "can be rebuilt
# from" its export while the export silently dropped verify_cmd2, derived_at and
# every negative's verify_cmd -- the commands the CONTRADICTED mechanism depends
# on -- with no importer in existence. A demonstration in a commit message is
# not an instrument: this is.
#
# It also guards the blind spot such a demonstration cannot see. The export
# iterates FACT_COLS/SEARCH_COLS -- the exporter's own hand-maintained lists --
# so a column added by a future migration is invisible to the export AND to any
# check written in terms of it. Check 1 compares those lists against the LIVE
# schema; check 2 compares the round trip by the live schema too, never by the
# lists.
#
# It builds its own store under a temp $OS2_KNOW_DB and never reads or writes
# the user's.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
KNOW=$HERE/../../tools/know
[ -x "$KNOW" ] || { echo "  ABORT: $KNOW missing or not executable"; exit 2; }
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export OS2_KNOW_DB="$T/know.db"
fail=0

"$KNOW" init >/dev/null || { echo "  ABORT: init failed"; exit 2; }

# Seed rows that exercise every column the export has ever dropped: a second
# verify arm, a build string, a negative WITH a command, a negative WITHOUT one,
# and a supersede chain in each table.
"$KNOW" add --subject DosOpen --kind contract --prov DOC-IBM --corrob ibm-doc \
  --cite 'bsedos.h:2616' --verify 'true' --build 'Warp 4.5' --by roundtrip \
  -m 'first claim' >/dev/null || fail=$((fail+1))
"$KNOW" add --subject DosOpen --kind contract --prov DOC-IBM --corrob two-source \
  --cite 'bsedos.h:2616 and pm2.txt "DosOpen - Syntax"' \
  --verify 'true' --verify2 'true' --by roundtrip \
  -m 'corrected claim' >/dev/null || fail=$((fail+1))
"$KNOW" supersede 1 2 -m 'the first reading was wrong' >/dev/null || fail=$((fail+1))
"$KNOW" absent --question 'is there a documented SIQ consumer protocol' \
  --tier ibm-primary --target 'ddk-books' --verify 'false' >/dev/null || fail=$((fail+1))
"$KNOW" absent --question 'a negative with no command' \
  --tier library-docs --target 'docs/nothing' >/dev/null || fail=$((fail+1))
"$KNOW" absent --question 'corrected negative' --tier ibm-primary \
  --target 'ddk-books, wider pattern' --verify 'false' >/dev/null || fail=$((fail+1))
"$KNOW" supersede neg1 neg3 -m 'the first search was too narrow' >/dev/null \
  || fail=$((fail+1))

# 1. the exporter's column lists must still cover the live schema
python3 - "$OS2_KNOW_DB" "$KNOW" <<'PY' || fail=$((fail+1))
import re, sqlite3, sys
src = open(sys.argv[2], encoding="utf-8").read()
def cols(name):
    m = re.search(name + r"\s*=\s*\(([^)]*)\)", src, re.S)
    return {c.strip().strip('"\'') for c in m.group(1).split(",") if c.strip()}
c = sqlite3.connect(sys.argv[1])
bad = 0
for table, const in (("fact", "FACT_COLS"), ("search", "SEARCH_COLS")):
    live = {r[1] for r in c.execute(f"PRAGMA table_info({table})")}
    missing = live - cols(const)
    if missing:
        print(f"  FAIL {const} does not cover {table}: missing {sorted(missing)}")
        print("       a column the exporter forgets is invisible to the export")
        print("       AND to any check written in terms of the same list.")
        bad += 1
    else:
        print(f"  ok   {const} covers all {len(live)} columns of {table}")
sys.exit(1 if bad else 0)
PY

# 2. the round trip itself, compared by LIVE schema, not by the exporter's list
"$KNOW" export "$T/exp" >/dev/null || { echo "  FAIL export"; fail=$((fail+1)); }
[ -s "$T/exp/know.jsonl" ] || { echo "  FAIL export wrote no know.jsonl"; exit 2; }
[ -s "$T/exp/facts.md" ] && [ -s "$T/exp/absent.md" ] \
  || { echo "  FAIL export wrote no readable view"; fail=$((fail+1)); }
OS2_KNOW_DB="$T/rt.db" "$KNOW" import "$T/exp/know.jsonl" >/dev/null \
  || { echo "  FAIL import"; fail=$((fail+1)); }
# NO `|| fail=...` on this one: this python has THREE outcomes (0 ok / 1 differ /
# 2 nothing-to-compare) and a `||` collapses the third. After a `||` that
# short-circuits, `$?` is 0; when it does not short-circuit, `$?` is the status
# of the ASSIGNMENT, also 0 -- so the ABORT path would be dead code, and "this
# instrument measured nothing" would be silently downgraded to "a check failed".
python3 - "$OS2_KNOW_DB" "$T/rt.db" <<'PY'
import sqlite3, sys
a, b = sqlite3.connect(sys.argv[1]), sqlite3.connect(sys.argv[2])
bad = 0
for t in ("fact", "search"):
    live = [r[1] for r in a.execute(f"PRAGMA table_info({t})")]
    cols = ",".join(live)
    x = list(a.execute(f"SELECT {cols} FROM {t} ORDER BY id"))
    y = list(b.execute(f"SELECT {cols} FROM {t} ORDER BY id"))
    if not x:
        print(f"  ABORT {t} is empty -- a clean round trip here proves nothing")
        sys.exit(2)
    print(f"  {'ok  ' if x==y else 'FAIL'} {t}: {len(x)} rows, {len(live)} cols, "
          f"{'identical' if x==y else 'DIFFER'}")
    bad += x != y
sys.exit(1 if bad else 0)
PY
rc=$?
if [ $rc -eq 2 ]; then exit 2; elif [ $rc -ne 0 ]; then fail=$((fail+1)); fi

# 3. the round trip must be falsifiable: a deliberately damaged export must be
#    caught, or check 2 proves only that two identical runs agree.
sed 's/"claim": "corrected claim"/"claim": "TAMPERED"/' "$T/exp/know.jsonl" \
  > "$T/bad.jsonl"
if cmp -s "$T/exp/know.jsonl" "$T/bad.jsonl"; then
  echo "  FAIL falsification setup changed nothing -- check 3 cannot fail"
  fail=$((fail+1))
else
  OS2_KNOW_DB="$T/bad.db" "$KNOW" import "$T/bad.jsonl" >/dev/null
  if python3 - "$OS2_KNOW_DB" "$T/bad.db" <<'PY'
import sqlite3, sys
a, b = sqlite3.connect(sys.argv[1]), sqlite3.connect(sys.argv[2])
x = list(a.execute("SELECT claim FROM fact ORDER BY id"))
y = list(b.execute("SELECT claim FROM fact ORDER BY id"))
sys.exit(0 if x == y else 1)
PY
  then
    echo "  FAIL a tampered export compared EQUAL -- check 2 is vacuous"
    fail=$((fail+1))
  else
    echo "  ok   a tampered export is detected (check 2 can fail)"
  fi
fi

# 4. import refuses to overwrite a populated store without --force, and --force
#    is a RESTORE rather than a merge: a row in the store but not in the file
#    must not survive it.
if OS2_KNOW_DB="$T/rt.db" "$KNOW" import "$T/exp/know.jsonl" >/dev/null 2>&1; then
  echo "  FAIL import overwrote a populated store without --force"
  fail=$((fail+1))
else
  echo "  ok   import refuses a populated store without --force"
fi
OS2_KNOW_DB="$T/rt.db" "$KNOW" add --subject Extra --kind behaviour --prov INF \
  --corrob re --cite 'docs/some-item/text/notes.txt:12' -m 'only in the store' \
  >/dev/null
OS2_KNOW_DB="$T/rt.db" "$KNOW" import --force "$T/exp/know.jsonl" >/dev/null \
  || { echo "  FAIL import --force"; fail=$((fail+1)); }
n=$(python3 -c "import sqlite3,sys;print(sqlite3.connect(sys.argv[1]).execute(
\"SELECT COUNT(*) FROM fact WHERE subject='Extra'\").fetchone()[0])" "$T/rt.db")
if [ "$n" = "0" ]; then
  echo "  ok   --force is a restore, not a merge"
else
  echo "  FAIL --force left a row the export does not carry (it merged)"
  fail=$((fail+1))
fi

[ $fail -eq 0 ] && echo "  round trip OK" || echo "  $fail check(s) FAILED"
exit $((fail ? 1 : 0))
