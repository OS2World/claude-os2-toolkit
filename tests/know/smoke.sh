#!/usr/bin/env bash
# smoke.sh - does the store open, index, answer, refuse and re-check?
#
# One question per case, and every case is written so it can FAIL: the refusal
# cases assert a non-zero exit AND that the row did not land, and the negative
# case is set up so `verify` must report CONTRADICTED. A test that only ever
# confirms is a test that cannot fail.
#
# It builds its own store and its own tiny corpus under a temp directory, sets
# $OS2_KNOW_DB at it, and never reads or writes the user's store or the OS/2
# library.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
KNOW=$HERE/../../tools/know
[ -x "$KNOW" ] || { echo "  ABORT: $KNOW missing or not executable"; exit 2; }
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export OS2_KNOW_DB="$T/know.db"
pass=0; fail=0

ok()   { printf '  ok    %s\n' "$1"; pass=$((pass+1)); }
bad()  { printf '  FAIL  %s\n' "$1"; fail=$((fail+1)); }
check(){ if [ "$1" = "$2" ]; then ok "$3"; else bad "$3 (got $1, want $2)"; fi; }

# ---------------------------------------------------------------- the surface
rc=$("$KNOW" --help >/dev/null 2>&1; echo $?)
check "$rc" 0 "know --help"
for v in init ingest q add absent show log supersede promote stale refresh \
         verify export import stats; do
  rc=$("$KNOW" "$v" --help >/dev/null 2>&1; echo $?)
  check "$rc" 0 "know $v --help"
done
# no verb at all is a usage error, not a silent success
rc=$("$KNOW" >/dev/null 2>&1; echo $?)
[ "$rc" -ne 0 ] && ok "bare \`know\` exits non-zero with usage" \
                || bad "bare \`know\` exited 0"

# ------------------------------------------------------------------- the store
"$KNOW" stats >/dev/null 2>&1 && bad "stats succeeded with no store" \
                              || ok "a missing store is named, not created"
"$KNOW" init >/dev/null || { echo "  ABORT: init failed"; exit 2; }
[ -f "$OS2_KNOW_DB" ] && ok "init created the store at \$OS2_KNOW_DB" \
                      || bad "init did not create \$OS2_KNOW_DB"
"$KNOW" init >/dev/null 2>&1 && ok "init is idempotent" || bad "second init failed"

# ------------------------------------------------------------------ the corpus
mkdir -p "$T/corpus"
cat > "$T/corpus/book.txt" <<'EOF'
=== DosQueryFileInfo - Syntax ===

DosQueryFileInfo returns information about a file, given its handle.
The information level selects which structure is returned; level 1 is
FILESTATUS3 and carries the creation, access and write timestamps.

=== DosQueryFileInfo - Return Value ===

Returns 0 on success. ERROR_INVALID_HANDLE is returned when the handle
does not name an open file.
EOF
cat > "$T/corpus/hdr.h" <<'EOF'
/* a header, chunked as fixed windows */
#define FIL_STANDARD           1
#define FIL_QUERYEASIZE        2
typedef struct _FILESTATUS3 {
    FDATE  fdateCreation;
    FTIME  ftimeCreation;
    ULONG  cbFile;
} FILESTATUS3;
APIRET APIENTRY DosQueryFileInfo(HFILE hf, ULONG ulInfoLevel, PVOID pInfo, ULONG cbInfoBuf);
EOF
cat > "$T/corpus/page.htm" <<'EOF'
<html><head><title>Storage Device Driver Reference</title></head><body>
<h2>Storage Device Driver Reference</h2>
<h3>IORB Request Blocks</h3>
<p>An IORB describes one request to an adapter driver&#046; The
iorbh field carries the length and the command code&#046;</p>
</body></html>
EOF
cat > "$T/corpus/note.md" <<'EOF'
# Notes

## Extended attributes

The FEA2 stride is (cbName + cbValue + 12) rounded up to a dword boundary.
EOF

"$KNOW" ingest inf    "$T/corpus/book.txt" >/dev/null || bad "ingest inf"
"$KNOW" ingest source "$T/corpus/hdr.h"    >/dev/null || bad "ingest source"
"$KNOW" ingest html   "$T/corpus/page.htm" >/dev/null || bad "ingest html"
"$KNOW" ingest md     "$T/corpus/note.md"  >/dev/null || bad "ingest md"
n=$("$KNOW" stats | sed -n 's/^  chunks *\([0-9]*\)$/\1/p')
[ "${n:-0}" -ge 4 ] && ok "four kinds ingested ($n chunks)" \
                    || bad "expected at least 4 chunks, got ${n:-0}"
"$KNOW" ingest source "$T/corpus/hdr.h" >/dev/null
n2=$("$KNOW" stats | sed -n 's/^  chunks *\([0-9]*\)$/\1/p')
check "$n2" "$n" "re-ingesting a file replaces its chunks rather than doubling"

# ---------------------------------------------------------------- retrieval
"$KNOW" q 'which information level returns FILESTATUS3' | grep -q 'book.txt' \
  && ok "a question in words finds the INF section" \
  || bad "the INF section was not returned"
"$KNOW" q 'IORB request block length' | grep -q 'page.htm' \
  && ok "the HTML page is found by its body text" \
  || bad "the HTML page was not returned"
"$KNOW" q 'FEA2 stride' --corpus md | grep -q 'note.md' \
  && ok "--corpus scopes to one kind" || bad "--corpus md returned nothing"
"$KNOW" q 'FEA2 stride' --corpus inf | grep -q 'note.md' \
  && bad "--corpus inf returned an md chunk" || ok "--corpus excludes other kinds"
"$KNOW" q 'zzqqxx nothing at all here' | grep -q 'no hits' \
  && ok "a miss says so, and says it is not a finding" || bad "a miss was silent"

# -------------------------------------------------------------- facts, refused
try_add() { "$KNOW" add --subject S --kind contract --prov "$1" --corrob "$2" \
            --cite "$3" -m 'a claim' >/dev/null 2>&1; }
before=$("$KNOW" stats | sed -n 's/^  facts *\([0-9]*\).*/\1/p')
try_add DOC-IBM self 'bsedos.h:2616' \
  && bad "a fact was accepted with --corrob self" \
  || ok "a FACT corroborated by 'self' is refused"
try_add DOC-IBM ibm-doc 'src/common/virtual_doscalls.c:94' \
  && bad "a citation into a project tree was accepted" \
  || ok "a citation into a project's own tree is refused"
try_add DOC-IBM ibm-doc 'I remember reading it somewhere' \
  && bad "an uncheckable citation was accepted" \
  || ok "a citation naming nothing checkable is refused"
try_add DOC-IBM two-source 'bsedos.h:2616' \
  && bad "two-source was accepted with no verify arms" \
  || ok "two-source without both --verify arms is refused"
after=$("$KNOW" stats | sed -n 's/^  facts *\([0-9]*\).*/\1/p')
check "$after" "$before" "a refused fact leaves no row behind"

# -------------------------------------------------------------- facts, accepted
"$KNOW" add --subject 'DosQueryFileInfo level 1' --kind contract --prov DOC-IBM \
  --corrob ibm-doc --cite 'hdr.h:4 (read with grep)' \
  --verify "grep -q FILESTATUS3 $T/corpus/hdr.h" --by smoke \
  -m 'level 1 returns FILESTATUS3' >/dev/null \
  && ok "a fact with a role/file:line citation is accepted" \
  || bad "a well-formed fact was refused"
"$KNOW" add --subject 'IORB length field' --kind layout --prov DOC \
  --corrob re --cite 'docs/ibm-os2-ddk-2004-books/text/storage.txt "IORB"' \
  -m 'the iorbh field carries the length' >/dev/null \
  && ok "a book-plus-topic citation is accepted" \
  || bad "a book-plus-topic citation was refused"
"$KNOW" q 'DosQueryFileInfo level 1' --facts | grep -q 'fact #1' \
  && ok "a fact is promoted when the query is about its subject" \
  || bad "the fact was not returned for its own subject"

# ------------------------------------------------------- negatives and verify
# One negative whose command still finds nothing, one whose command now finds
# something: `verify` must tell them apart, and must exit non-zero for the
# second. A negative that cannot be contradicted is the row this store exists
# to catch.
"$KNOW" absent --question 'is a KEYUP translate mode documented' \
  --tier ibm-primary --target 'the ingested book text' \
  --verify "grep -l KEYUP $T/corpus/book.txt" >/dev/null || bad "absent (true)"
"$KNOW" absent --question 'is FILESTATUS3 absent from the header' \
  --tier headers-source --target 'the ingested header' \
  --verify "grep -l FILESTATUS3 $T/corpus/hdr.h" >/dev/null || bad "absent (wrong)"
out=$("$KNOW" verify --all --cwd "$T" 2>&1); rc=$?
echo "$out" | grep -q 'STILL ABSENT' \
  && ok "a negative that still finds nothing reads STILL ABSENT" \
  || bad "no STILL ABSENT row"
echo "$out" | grep -q 'CONTRADICTED' \
  && ok "a negative whose search now hits reads CONTRADICTED" \
  || bad "a wrong negative was not contradicted"
echo "$out" | grep -q '^AGREE' && ok "a fact's verify_cmd re-runs and agrees" \
                               || bad "no AGREE row"
echo "$out" | grep -q 'UNCHECKABLE' \
  && ok "a fact with no verify_cmd reads UNCHECKABLE, not AGREE" \
  || bad "a fact with no verify_cmd was not reported"
[ "$rc" -ne 0 ] && ok "verify exits with the disagreement count ($rc)" \
                || bad "verify exited 0 with a CONTRADICTED row"
"$KNOW" verify --all --cwd "$T/nowhere" >/dev/null 2>&1 \
  && bad "--cwd accepted a directory that does not exist" \
  || ok "--cwd names a bad working directory rather than silently using another"

# ---------------------------------------------------------------- supersede
"$KNOW" absent --question 'is a KEYUP translate mode documented' \
  --tier ibm-primary --target 'book text, wider pattern' \
  --verify "grep -l 'KEY UP' $T/corpus/book.txt" >/dev/null
"$KNOW" supersede neg1 neg3 -m 'the first pattern was too narrow' >/dev/null \
  && ok "a negative can be superseded" || bad "supersede of a negative failed"
"$KNOW" supersede neg1 neg3 -m 'again' >/dev/null 2>&1 \
  && bad "an already-superseded row was re-pointed" \
  || ok "re-pointing an already-superseded row is refused"
"$KNOW" supersede 1 neg3 -m 'cross table' >/dev/null 2>&1 \
  && bad "a cross-table supersede was accepted" \
  || ok "a cross-table supersede is refused"
"$KNOW" show neg1 | grep -q 'SUPERSEDED BY' \
  && ok "the superseded row is KEPT and points at its correction" \
  || bad "the superseded row lost its pointer"
"$KNOW" q 'KEYUP translate mode' | grep -q 'SUPERSEDED BY' \
  && ok "a retracted negative is still shown, marked" \
  || bad "a retracted negative was hidden from the query"

# ------------------------------------------------------------------ staleness
"$KNOW" stale >/dev/null && ok "a fresh index reports current" \
                         || bad "a fresh index reported stale"
printf '\n=== A new section ===\n\nWith enough body text to survive the minimum chunk size, several times over, so that the chunker keeps it as its own section rather than merging it away.\n' \
  >> "$T/corpus/book.txt"
"$KNOW" stale >/dev/null 2>&1 && bad "a changed source file was not detected" \
                              || ok "a changed source file is reported CHANGED"
"$KNOW" q 'DosQueryFileInfo' | grep -q 'STALE' \
  && ok "hits from a changed file are marked [STALE]" \
  || bad "a stale hit was returned unmarked"
"$KNOW" refresh >/dev/null && ok "refresh re-ingests what changed" || bad "refresh failed"
"$KNOW" stale >/dev/null && ok "the index is current again after refresh" \
                         || bad "still stale after refresh"

# -------------------------------------------------------------- library ingest
# With no library configured, `ingest` with no paths must exit non-zero and name
# what is missing. It must never go looking for material elsewhere on the disk.
out=$(OS2_LIBRARY="$T/no-library" XDG_CONFIG_HOME="$T/noconf" \
      "$KNOW" ingest 2>&1); rc=$?
[ "$rc" -ne 0 ] && ok "ingest with no library exits non-zero" \
                || bad "ingest with no library exited 0"
echo "$out" | grep -q "$T/no-library" \
  && ok "it names the library root it looked for" || bad "it did not name the root"
echo "$out" | grep -qi 'ingest skill\|os2-toolkit:ingest' \
  && ok "it points at the os2-toolkit:ingest skill" \
  || bad "it does not say how to add material"
n=$("$KNOW" stats | sed -n 's/^  chunks *\([0-9]*\)$/\1/p')
[ "${n:-0}" -gt 0 ] && ok "the failed library ingest changed nothing" \
                    || bad "the store lost its chunks"

echo "  $pass passed, $fail failed"
exit $((fail ? 1 : 0))
