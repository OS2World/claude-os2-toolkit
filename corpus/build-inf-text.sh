#!/bin/sh
# build-inf-text.sh - turn IBM .INF/.HLP books into greppable UTF-8 text.
#
# This is the highest-value corpus step: the IBM programming books hold the
# usage patterns, contracts and worked examples that headers do not, but they
# ship as compiled IPF binaries. Extracted, they become the substrate that
# answers "how is this actually used" instead of just "what is the prototype".
#
# Usage:
#   ./build-inf-text.sh [DIR-OR-FILE ...]
#
# With no arguments it scans a default set of likely locations (see SCAN below).
# Output goes to $OS2DOCS/inf_text/<book>.txt  (OS2DOCS defaults to ~/os2docs).
#
# Re-running is cheap: a book is re-extracted only if its source is newer than
# the existing text. Safe to run after adding more books.
#
# RIGHTS: the books are IBM's. This script converts material you already have;
# it downloads nothing and it does not give you the right to redistribute the
# output. Keep the corpus local. See ../sources.md.
set -e

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
: "${OS2DOCS:=$HOME/os2docs}"
inf2txt="$here/../tools/inf2txt/inf2txt.sh"
out="$OS2DOCS/inf_text"
manifest="$out/manifest.tsv"

[ -x "$inf2txt" ] || {
    echo "build-inf-text.sh: $inf2txt not found" >&2; exit 127; }
: "${INF2TXT_HOME:=${XDG_DATA_HOME:-$HOME/.local/share}/os2-toolkit/inf2txt}"
[ -x "$INF2TXT_HOME/inf2txt" ] || [ -x "$here/../tools/inf2txt/inf2txt" ] || {
    echo "build-inf-text.sh: the inf2txt binary is not built yet." >&2
    echo "  run: inf2txt-build   (or $here/../tools/inf2txt/build.sh)" >&2
    exit 127
}

# A book whose extracted text is legitimately tiny: front matter only, with the
# real content in a sibling volume. Named so a small output is not mistaken for a
# broken extraction, and so a search miss here is not read as "IBM does not
# document it" (see ../recipes/read-ibm-books.md). Verified: gpi1 is 354 lines
# against gpi2's ~39,700. Add others only after checking them the same way.
STUB_HINT="gpi1 (354 lines; the real GPI reference is gpi2)"

if [ $# -gt 0 ]; then
    SCAN="$*"
else
    SCAN="$OS2DOCS/books $OS2DOCS $HOME/os2books"
    # Toolkit BOOK/ dirs, wherever the toolkit landed.
    for d in "$OS2DOCS"/os2tk45 "$HOME"/OS2TK45 /opt/OS2TK45; do
        [ -d "$d" ] && SCAN="$SCAN $d"
    done
fi

mkdir -p "$out"
echo "corpus: $out"
echo "scanning: $SCAN"

# Collect candidate books (case-insensitive .inf/.hlp, non-trivial size).
tmp=$(mktemp); trap 'rm -f "$tmp"' EXIT
for p in $SCAN; do
    [ -e "$p" ] || continue
    if [ -f "$p" ]; then
        printf '%s\n' "$p" >> "$tmp"
    else
        find "$p" -type f \( -iname '*.inf' -o -iname '*.hlp' \) -size +20k \
             2>/dev/null >> "$tmp" || true
    fi
done
sort -u "$tmp" -o "$tmp"

total=$(wc -l < "$tmp" | tr -d ' ')
[ "$total" -gt 0 ] || {
    echo "build-inf-text.sh: no .INF/.HLP books found." >&2
    echo "  Pass a directory explicitly, or see ../sources.md section 3 for where to get them." >&2
    exit 1
}
echo "found $total candidate book(s)"
echo

built=0; skipped=0; failed=0; stubs=""
printf 'book\tlines\tbytes\tsource\n' > "$manifest.new"

while IFS= read -r src; do
    base=$(basename "$src"); stem=${base%.*}
    # Lowercase the stem so CPGREF.INF and cpgref.inf land in one place.
    stem=$(printf '%s' "$stem" | tr 'A-Z' 'a-z')
    dst="$out/$stem.txt"

    if [ -f "$dst" ] && [ "$dst" -nt "$src" ]; then
        skipped=$((skipped + 1))
    else
        printf '  %-16s <- %s\n' "$stem.txt" "$src"
        if "$inf2txt" "$src" > "$dst.tmp" 2>"$dst.err"; then
            mv "$dst.tmp" "$dst"; rm -f "$dst.err"
            built=$((built + 1))
        else
            # Never leave a half-written book in place: a truncated book is a
            # silent false negative for every later search.
            rm -f "$dst.tmp"
            echo "     FAILED: $(head -1 "$dst.err" 2>/dev/null)" >&2
            failed=$((failed + 1))
            continue
        fi
    fi

    [ -f "$dst" ] || continue
    lines=$(wc -l < "$dst" | tr -d ' ')
    bytes=$(wc -c < "$dst" | tr -d ' ')
    printf '%s\t%s\t%s\t%s\n' "$stem" "$lines" "$bytes" "$src" >> "$manifest.new"
    if [ "$lines" -lt 1000 ]; then
        stubs="$stubs $stem($lines)"
    fi
done < "$tmp"

mv "$manifest.new" "$manifest"

echo
echo "built $built, up-to-date $skipped, failed $failed"
echo "manifest: $manifest"

if [ -n "$stubs" ]; then
    echo
    echo "NOTE - these came out under 1000 lines:$stubs"
    echo "  Some books really are front-matter stubs, with the content in a sibling"
    echo "  volume. Known case: $STUB_HINT."
    echo "  Check with 'wc -l' before concluding that a search miss means IBM did"
    echo "  not document something."
fi

# Encoding is the other silent-failure mode: non-UTF-8 text makes GNU grep treat
# the file as binary and print NOTHING, which reads as "not documented".
if command -v file >/dev/null 2>&1; then
    bad=$(find "$out" -name '*.txt' -exec sh -c \
          'file -b "$1" | grep -qi "utf-8\|ascii" || echo "$1"' _ {} \; 2>/dev/null)
    if [ -n "$bad" ]; then
        echo
        echo "WARNING - not UTF-8/ASCII, grep will silently find nothing in these:"
        printf '  %s\n' $bad
        echo "  Re-extract them, or always search with 'grep -a'."
    fi
fi
