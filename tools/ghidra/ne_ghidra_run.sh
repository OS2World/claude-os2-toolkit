#!/bin/bash
# ne_ghidra_run.sh - decompile a whole OS/2 NE module (16-bit driver, IFS,
# DLL or EXE) with headless Ghidra.  The NE counterpart of lx_ghidra_run.sh.
#
# Everything downstream of the export step is deliberately the SAME code the
# LX pipeline uses (make_blocks.py, LoadAllObjects.java, ApplySymbols.java,
# DecompileAll.java): the manifest.json ne_seg_export.py writes is in exactly
# the shape those consume.  What differs is only what NE needs:
#
#   - segments, not objects: exported with relocations applied and grown to
#     their minimum allocation size (ne_seg_export.py)
#   - a pseudo-flat address space: logical segment N at N << 16, which is the
#     notation IBM's own NE .SYM files use, so no translation is needed
#   - symbols need no image to resolve against (ne_symva.py), because an NE
#     .SYM's segment numbers ARE the module's logical segment numbers
#   - imports get synthetic named stubs, so far calls into other modules read
#     as names rather than as unresolved addresses (ne_impnames.py)
#   - DS is pinned to the module's declared automatic data segment
#     (SetDataSeg.java), without which most globals decompile as bare numeric
#     offsets
#
# Usage: ne_ghidra_run.sh [options] <name> <ne-image> [symfile]
#
# Options:
#   --out DIR      output root (default: ./ghidra-out)
#   --ghidra PATH  Ghidra directory or analyzeHeadless (default: $GHIDRA_HOME)
#   --timeout SEC  auto-analysis timeout per program (default: 1800)
#   --defdir DIR   directory of .DEF files, for naming imported ordinals
#                  (see ne_impnames.py)
#   --no-ds        do not pin DS, even if the module declares an autodata
#                  segment
#
# As in the LX pipeline, a symbol file is optional and is never second-guessed:
# pass one only if you have checked it belongs to the same build as the binary.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$HERE/ghidra_env.sh"

OUTROOT="./ghidra-out"
GHIDRA_ARG=""
TIMEOUT=1800
DEFDIR=""
PIN_DS=1
usage() { awk 'NR>1 { if (/^#/) { sub(/^# ?/, ""); print } else { exit } }' "${BASH_SOURCE[0]}"; exit "${1:-0}"; }
while [ $# -gt 0 ]; do
    case "$1" in
        --out)     OUTROOT="${2:?--out needs a directory}"; shift 2 ;;
        --ghidra)  GHIDRA_ARG="${2:?--ghidra needs a path}"; shift 2 ;;
        --timeout) TIMEOUT="${2:?--timeout needs seconds}"; shift 2 ;;
        --defdir)  DEFDIR="${2:?--defdir needs a directory}"; shift 2 ;;
        --no-ds)   PIN_DS=0; shift ;;
        -h|--help) usage 0 ;;
        --) shift; break ;;
        -*) echo "unknown option: $1" >&2; usage 2 ;;
        *) break ;;
    esac
done

NAME="${1:-}"; NEIMAGE="${2:-}"; SYMFILE="${3:-}"
[ -n "$NAME" ] && [ -n "$NEIMAGE" ] || usage 2
[ -f "$NEIMAGE" ] || { echo "error: no such NE image: $NEIMAGE" >&2; exit 2; }
[ -z "$SYMFILE" ] || [ -f "$SYMFILE" ] || { echo "error: no such symbol file: $SYMFILE" >&2; exit 2; }

GHIDRA="$(ghidra_headless "$GHIDRA_ARG")" || exit 1

mkdir -p "$OUTROOT/$NAME"
OUT="$(cd "$OUTROOT/$NAME" && pwd)"
LOG="$OUT/run.log"
: > "$LOG"
log() { echo "[$NAME] $*" | tee -a "$LOG"; }

log "neimage=$NEIMAGE symfile=${SYMFILE:-<none>}"
log "ghidra=$GHIDRA"

# --- 1. export every segment, relocations applied ---
log "exporting NE segments (relocations applied)..."
python3 "$HERE/ne_seg_export.py" "$NEIMAGE" "$OUT/objs" 2>&1 | tee -a "$LOG"

# --- 2. symbols: real .SYM names plus named import stubs ---
SYMVA="$OUT/symbols_va.txt"
: > "$SYMVA"
if [ -n "$SYMFILE" ]; then
    python3 "$HERE/ne_symva.py" "$SYMFILE" >> "$SYMVA" 2>>"$LOG"
    log "symbols: $(wc -l < "$SYMVA") from $SYMFILE"
fi
if [ -s "$OUT/objs/imports.txt" ]; then
    if [ -n "$DEFDIR" ]; then
        python3 "$HERE/ne_impnames.py" "$OUT/objs/imports.txt" --defdir "$DEFDIR" \
            >> "$SYMVA" 2>>"$LOG"
    else
        cat "$OUT/objs/imports.txt" >> "$SYMVA"
    fi
    log "symbols: +$(wc -l < "$OUT/objs/imports.txt") import stubs"
fi
[ -s "$SYMVA" ] || { SYMVA=""; log "WARNING: no symbols at all - names will be FUN_*"; }

# --- 3. one Ghidra program per bitness present ---
for bits in 16 32; do
    BLOCKS="$OUT/blocks_${bits}.txt"
    PRIMARY_LINE=$(python3 "$HERE/make_blocks.py" "$OUT/objs/manifest.json" "$bits" "$BLOCKS" 2>&1) || {
        log "no $bits-bit executable segment - skipping"; continue; }
    read -r _ PRIMNUM PRIMBASE PRIMFILE <<< "$PRIMARY_LINE"
    log "$bits-bit primary: segment $PRIMNUM @ $PRIMBASE ($PRIMFILE)"

    PROJDIR="$OUT/proj$bits"; DECOMPDIR="$OUT/decompiled_$bits"
    # clear the decompile dir too: otherwise a failed run silently "passes"
    # its file-count check against the previous run's leftover output.
    rm -rf "$PROJDIR" "$DECOMPDIR"; mkdir -p "$PROJDIR" "$DECOMPDIR"

    if [ "$bits" = "32" ]; then PROC="x86:LE:32:default"; CSPEC=()
    else PROC="x86:LE:16:Protected Mode"; CSPEC=(-cspec default); fi

    ARGS=(-preScript DisableNoreturnDiscovery.java)
    ARGS+=(-preScript LoadAllObjects.java "$BLOCKS")
    # Pin DS to the NE header's own automatic-data segment so that data
    # references decompile as real global names instead of bare offsets.
    AUTODATA=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['autodata'])" \
        "$OUT/objs/header.json")
    if [ "$PIN_DS" = "1" ] && [ "$AUTODATA" != "0" ]; then
        ARGS+=(-preScript SetDataSeg.java "$AUTODATA")
        log "pinning DS=$AUTODATA (the module's declared autodata segment) across executable blocks"
    fi
    [ -n "$SYMVA" ] && ARGS+=(-preScript ApplySymbols.java "$SYMVA")
    ARGS+=(-postScript DecompileAll.java "$DECOMPDIR")

    # Ghidra APPENDS to -log; truncate so a stale error from a previous run
    # cannot be mistaken for (or hide) this run's result.
    : > "$OUT/headless_${bits}.log"
    log "running Ghidra headless ($bits-bit)..."
    "$GHIDRA" "$PROJDIR" "${NAME}_${bits}" \
        -import "$PRIMFILE" \
        -loader BinaryLoader -loader-baseAddr "$PRIMBASE" \
        -processor "$PROC" "${CSPEC[@]}" \
        -scriptPath "$HERE" \
        -analysisTimeoutPerFile "$TIMEOUT" \
        "${ARGS[@]}" \
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
