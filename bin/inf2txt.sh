#!/bin/sh
# PATH shim (plugin bin/): runs tools/inf2txt/inf2txt.sh from this checkout with the same arguments.
root=$(dirname -- "$(dirname -- "$(readlink -f -- "$0")")")
exec "$root/tools/inf2txt/inf2txt.sh" "$@"
