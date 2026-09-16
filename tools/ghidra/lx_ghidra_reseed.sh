#!/bin/bash
# lx_ghidra_reseed.sh - re-run ONE bitness pass of an existing lx_ghidra_run.sh
# output, seeding a function at every ORPHAN address bitness_index.py found, so
# that routines which today exist only as a wrong-bitness decode get a correct
# one.
#
# Why this rather than a plain re-run: a plain re-run reproduces the defect.
# The guard that was supposed to prevent it (make_blocks.py forcing
# opposite-bitness code objects non-executable) is already in place and has
# already been measured insufficient - Ghidra's auto-analysis creates
# functions inside such a block anyway, in the wrong program.  What is missing
# is not a different analysis, it is a SEED at each orphan entry point in the
# CORRECT-bitness program.  ApplySymbols.java already does exactly that for
# every "0xVA name" line landing in executable memory, so this adds no new
# mechanism: it extends that script's input file with the orphan addresses.
#
# Writes to decompiled_<bits>_reseed/.  The original decompiled_<bits>/ is left
# byte-for-byte alone, so the two are comparable and nothing is lost.
#
# Usage: lx_ghidra_reseed.sh [--ghidra PATH] [--timeout SEC] <module-out-dir> <bits>
#
#   module-out-dir  a directory written by lx_ghidra_run.sh (the one holding
#                   objs/, blocks_*.txt and DECOMPILE_INDEX.tsv)
#   bits            16 or 32 - the pass to redo
#
# Prerequisite: bitness_index.py has been run on that directory, because the
# ORPHAN rows of its DECOMPILE_INDEX.tsv are this script's input.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$HERE/ghidra_env.sh"

GHIDRA_ARG=""
TIMEOUT=1800
usage() { awk 'NR>1 { if (/^#/) { sub(/^# ?/, ""); print } else { exit } }' "${BASH_SOURCE[0]}"; exit "${1:-0}"; }
while [ $# -gt 0 ]; do
    case "$1" in
        --ghidra)  GHIDRA_ARG="${2:?--ghidra needs a path}"; shift 2 ;;
        --timeout) TIMEOUT="${2:?--timeout needs seconds}"; shift 2 ;;
        -h|--help) usage 0 ;;
        --) shift; break ;;
        -*) echo "unknown option: $1" >&2; usage 2 ;;
        *) break ;;
    esac
done

[ $# -eq 2 ] || usage 2
OUT="$(cd "$1" && pwd)"
BITS="$2"
NAME="$(basename "$OUT")"
GHIDRA="$(ghidra_headless "$GHIDRA_ARG")" || exit 1
[ -f "$OUT/DECOMPILE_INDEX.tsv" ] || {
    echo "error: $OUT/DECOMPILE_INDEX.tsv not found - run bitness_index.py first" >&2
    exit 2
}

# Seeds = the module's own symbols (if any) plus every orphan entry point that
# belongs to an object of THIS bitness.
SEEDS="$OUT/reseed_${BITS}_syms.txt"
if [ -f "$OUT/symbols_va.txt" ]; then cp "$OUT/symbols_va.txt" "$SEEDS"; else : > "$SEEDS"; fi
before=$(wc -l < "$SEEDS")
awk -F'\t' -v b="$BITS" '$1=="ORPHAN" && $4=="USE"b {printf "0x%s reseed_%s_%s\n", $2, $5, $2}' \
    "$OUT/DECOMPILE_INDEX.tsv" >> "$SEEDS"
after=$(wc -l < "$SEEDS")
echo "[$NAME] seeds: $before symbols + $((after-before)) orphan entry points"

BLOCKS="$OUT/blocks_${BITS}.txt"
PRIMARY_LINE=$(python3 "$HERE/make_blocks.py" "$OUT/objs/manifest.json" "$BITS" "$BLOCKS")
read -r _ PRIMNUM PRIMBASE PRIMFILE <<< "$PRIMARY_LINE"
PROJDIR="$OUT/proj${BITS}_reseed"; DECOMPDIR="$OUT/decompiled_${BITS}_reseed"
rm -rf "$PROJDIR" "$DECOMPDIR"; mkdir -p "$PROJDIR" "$DECOMPDIR"
if [ "$BITS" = "32" ]; then PROC="x86:LE:32:default"; CSPEC=()
                       else PROC="x86:LE:16:Protected Mode"; CSPEC=(-cspec default); fi

: > "$OUT/headless_${BITS}_reseed.log"
"$GHIDRA" "$PROJDIR" "${NAME}_${BITS}_reseed" \
    -import "$PRIMFILE" -loader BinaryLoader -loader-baseAddr "$PRIMBASE" \
    -processor "$PROC" "${CSPEC[@]}" -scriptPath "$HERE" \
    -analysisTimeoutPerFile "$TIMEOUT" \
    -preScript DisableNoreturnDiscovery.java \
    -preScript LoadAllObjects.java "$BLOCKS" \
    -preScript ApplySymbols.java "$SEEDS" \
    -postScript DecompileAll.java "$DECOMPDIR" \
    -log "$OUT/headless_${BITS}_reseed.log" -deleteProject \
    >> "$OUT/reseed_${BITS}.log" 2>&1 || {
        echo "FAILED - see $OUT/headless_${BITS}_reseed.log" >&2; exit 1; }

new=$(ls "$DECOMPDIR"/*.c 2>/dev/null | wc -l)
old=$(ls "$OUT/decompiled_${BITS}"/*.c 2>/dev/null | wc -l)
echo "[$NAME] $new .c in $DECOMPDIR (original pass had $old)"
