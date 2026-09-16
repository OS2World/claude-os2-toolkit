#!/bin/bash
# lx_ghidra_run.sh - decompile a whole OS/2 LX module (DLL, EXE, driver) with
# headless Ghidra.
#
# What it does, in order:
#   1. export every LX object at its real base, fixups applied (lx_obj_export.py)
#   2. resolve a matching .SYM to flat VAs (sym2map.py --format flat), if given
#   3. per bitness present in the module:
#        - pick the first executable object of that bitness as the -import
#          primary, merge every other object in as a memory block (make_blocks.py
#          + LoadAllObjects.java), opposite-bitness code forced non-executable
#        - apply the real symbol names AND seed a function at each named
#          executable address (ApplySymbols.java)
#        - run Ghidra's auto-analysis, then decompile every function found
#          (DecompileAll.java) to one .c file each
#
# Usage: lx_ghidra_run.sh [options] <name> <lximage> [symfile]
#
#   name     short tag for this run; output goes to <outdir>/<name>/
#   lximage  the real LX binary
#   symfile  OPTIONAL matching .SYM.  Omitted, the run is still complete -
#            every function is still decompiled, under Ghidra's own FUN_<addr>
#            names - and the log says "no symbols", so a later reader cannot
#            mistake missing names for a gap in the analysis.
#
# Options:
#   --out DIR      output root (default: ./ghidra-out)
#   --ghidra PATH  Ghidra directory or analyzeHeadless (default: $GHIDRA_HOME)
#   --timeout SEC  auto-analysis timeout per program (default: 1800)
#
# SYMBOLS COME FROM A MATCHING .SYM, OR NOT AT ALL.  This script does not
# judge whether the .SYM you hand it belongs to the same build as the binary -
# that judgment (file dates, a few names cross-checked against independently
# known facts) is the caller's.  A .SYM from a different build resolves to
# plausible-looking addresses that are quietly wrong, which is worse than no
# names.  The run log records which symbol file, if any, was used.  As a
# partial guard, a symbol file that resolves ZERO symbols is treated as a
# mismatch and dropped, with a warning, rather than silently accepted.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS="$(cd "$HERE/.." && pwd)"
. "$HERE/ghidra_env.sh"

OUTROOT="./ghidra-out"
GHIDRA_ARG=""
TIMEOUT=1800
usage() {
    awk 'NR>1 { if (/^#/) { sub(/^# ?/, ""); print } else { exit } }' "${BASH_SOURCE[0]}"
    exit "${1:-0}"
}
while [ $# -gt 0 ]; do
    case "$1" in
        --out)     OUTROOT="${2:?--out needs a directory}"; shift 2 ;;
        --ghidra)  GHIDRA_ARG="${2:?--ghidra needs a path}"; shift 2 ;;
        --timeout) TIMEOUT="${2:?--timeout needs seconds}"; shift 2 ;;
        -h|--help) usage 0 ;;
        --) shift; break ;;
        -*) echo "unknown option: $1" >&2; usage 2 ;;
        *) break ;;
    esac
done

NAME="${1:-}"; LXIMAGE="${2:-}"; SYMFILE="${3:-}"
[ -n "$NAME" ] && [ -n "$LXIMAGE" ] || usage 2
[ -f "$LXIMAGE" ] || { echo "error: no such LX image: $LXIMAGE" >&2; exit 2; }
[ -z "$SYMFILE" ] || [ -f "$SYMFILE" ] || { echo "error: no such symbol file: $SYMFILE" >&2; exit 2; }

GHIDRA="$(ghidra_headless "$GHIDRA_ARG")" || exit 1
SYM2MAP="$TOOLS/sym2map.py"
[ -f "$SYM2MAP" ] || { echo "error: sym2map.py not found at $SYM2MAP" >&2; exit 1; }

mkdir -p "$OUTROOT/$NAME"
OUT="$(cd "$OUTROOT/$NAME" && pwd)"
LOG="$OUT/run.log"
: > "$LOG"
log() { echo "[$NAME] $*" | tee -a "$LOG"; }

log "lximage=$LXIMAGE symfile=${SYMFILE:-<none>}"
log "ghidra=$GHIDRA"

# --- 1. export every object, fixups applied ---
log "exporting all objects (fixups applied)..."
python3 "$HERE/lx_obj_export.py" "$LXIMAGE" "$OUT/objs" >> "$LOG" 2>&1

# --- 2. flat VA symbol file, if a .SYM was given ---
SYMVA=""
if [ -n "$SYMFILE" ]; then
    SYMVA="$OUT/symbols_va.txt"
    python3 "$SYM2MAP" "$SYMFILE" --lx "$LXIMAGE" --format flat \
        | grep -E '^[0-9a-f]{8}  ' | sed 's/^/0x/' > "$SYMVA" || true
    n=$(wc -l < "$SYMVA")
    log "symbol file: $n VA-resolved symbols written to $SYMVA"
    if [ "$n" -eq 0 ]; then
        log "WARNING: 0 symbols resolved - the .SYM's segments do not match this"
        log "WARNING: binary's objects, so it is probably a different build."
        log "WARNING: Continuing WITHOUT names."
        SYMVA=""
    fi
fi

# --- 3. one Ghidra program per bitness present ---
for bits in 32 16; do
    BLOCKS="$OUT/blocks_${bits}.txt"
    PRIMARY_LINE=$(python3 "$HERE/make_blocks.py" "$OUT/objs/manifest.json" "$bits" "$BLOCKS" 2>&1) || {
        log "no $bits-bit executable object - skipping"
        continue
    }
    read -r _ PRIMNUM PRIMBASE PRIMFILE <<< "$PRIMARY_LINE"
    log "$bits-bit primary: object $PRIMNUM @ $PRIMBASE ($PRIMFILE)"

    PROJDIR="$OUT/proj$bits"
    DECOMPDIR="$OUT/decompiled_$bits"
    # clear both: otherwise a failed run silently "passes" its file-count
    # check against the previous run's leftover output.
    rm -rf "$PROJDIR" "$DECOMPDIR"
    mkdir -p "$PROJDIR" "$DECOMPDIR"

    if [ "$bits" = "32" ]; then
        PROC="x86:LE:32:default"
        CSPEC_ARGS=()
    else
        PROC="x86:LE:16:Protected Mode"
        CSPEC_ARGS=(-cspec default)
    fi

    # DisableNoreturnDiscovery MUST come first: it sets analysis options, and
    # those are only consulted when auto-analysis runs, which happens after
    # every preScript.
    SCRIPT_ARGS=(-preScript DisableNoreturnDiscovery.java)
    SCRIPT_ARGS+=(-preScript LoadAllObjects.java "$BLOCKS")
    if [ -n "$SYMVA" ]; then
        SCRIPT_ARGS+=(-preScript ApplySymbols.java "$SYMVA")
    fi
    SCRIPT_ARGS+=(-postScript DecompileAll.java "$DECOMPDIR")

    # Ghidra APPENDS to -log; truncate so a stale error from a previous run
    # cannot be mistaken for (or hide) this run's result.
    : > "$OUT/headless_${bits}.log"
    log "running Ghidra headless ($bits-bit)..."
    # -analysisTimeoutPerFile bounds the auto-analysis phase itself, which is
    # separate from DecompileAll's own per-function decompile cap.  It is not
    # belt-and-braces: one of Ghidra's own analyzers can get stuck in a retry
    # loop against a bogus jump target (an address in no object), emitting
    # tens of thousands of identical "unable to read bytes" warnings with no
    # sign of terminating.  At the deadline, auto-analysis is abandoned and
    # DecompileAll still runs against whatever was found up to that point.
    "$GHIDRA" "$PROJDIR" "${NAME}_${bits}" \
        -import "$PRIMFILE" \
        -loader BinaryLoader -loader-baseAddr "$PRIMBASE" \
        -processor "$PROC" "${CSPEC_ARGS[@]}" \
        -scriptPath "$HERE" \
        -analysisTimeoutPerFile "$TIMEOUT" \
        "${SCRIPT_ARGS[@]}" \
        -log "$OUT/headless_${bits}.log" \
        -deleteProject >> "$LOG" 2>&1 || { log "FAILED ($bits-bit) - see $OUT/headless_${bits}.log"; continue; }

    # A script that fails to load does NOT fail the run: -deleteProject still
    # exits 0, so the run looks successful with an empty output directory.
    if grep -q "SCRIPT ERROR" "$OUT/headless_${bits}.log"; then
        log "ERROR: a Ghidra script failed to load/run - see $OUT/headless_${bits}.log"
        grep -m3 "SCRIPT ERROR" "$OUT/headless_${bits}.log" | tee -a "$LOG"
    fi
    n_c=$(ls "$DECOMPDIR" 2>/dev/null | wc -l)
    ok=$(grep -oE 'ok=[0-9]+' "$OUT/headless_${bits}.log" | tail -1 || echo "ok=?")
    fail=$(grep -oE 'fail=[0-9]+' "$OUT/headless_${bits}.log" | tail -1 || echo "fail=?")
    log "$bits-bit result: $n_c files written, $ok $fail"
done

log "done. summary: $LOG"
log "next: bitness_index.py $OUT   (flags any wrong-bitness decompiles)"
