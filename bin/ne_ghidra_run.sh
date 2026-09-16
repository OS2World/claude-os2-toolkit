#!/bin/sh
# PATH shim (plugin bin/): runs tools/ghidra/ne_ghidra_run.sh from this checkout with the same arguments.
root=$(dirname -- "$(dirname -- "$(readlink -f -- "$0")")")
exec "$root/tools/ghidra/ne_ghidra_run.sh" "$@"
