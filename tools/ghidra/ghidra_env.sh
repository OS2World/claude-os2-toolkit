#!/bin/sh
# ghidra_env.sh - locate Ghidra's headless analyzer.  Sourced by the pipeline
# runners in this directory; not useful on its own.
#
# Ghidra is not bundled with anything and installs wherever its tarball was
# unpacked, so the location is taken from the environment rather than guessed:
#
#   GHIDRA_HOME   the unpacked Ghidra directory (the one containing support/,
#                 Ghidra/, ghidraRun).  analyzeHeadless lives at
#                 $GHIDRA_HOME/support/analyzeHeadless.
#   --ghidra P    overrides it for one run; P may be the Ghidra directory or
#                 the analyzeHeadless script itself.
#
# Both runners fail immediately, naming GHIDRA_HOME, rather than running a
# partial pipeline that produces an empty output directory.

# ghidra_headless [explicit-path]
# Prints the path of analyzeHeadless on stdout; on failure prints a diagnostic
# on stderr and returns 1.
ghidra_headless() {
    cand="${1:-${GHIDRA_HOME:-}}"
    if [ -z "$cand" ]; then
        echo "error: GHIDRA_HOME is not set." >&2
        echo "  Set it to your unpacked Ghidra directory, e.g." >&2
        echo "    export GHIDRA_HOME=/path/to/ghidra_<version>_PUBLIC" >&2
        echo "  or pass --ghidra <dir>.  If the OS/2 library holds Ghidra," >&2
        echo "  'os2-lib role ghidra' prints its path." >&2
        return 1
    fi
    if [ -d "$cand" ]; then
        hl="$cand/support/analyzeHeadless"
    else
        hl="$cand"
    fi
    if [ ! -x "$hl" ]; then
        echo "error: no executable analyzeHeadless at '$hl'." >&2
        echo "  GHIDRA_HOME (or --ghidra) must name the unpacked Ghidra" >&2
        echo "  directory; analyzeHeadless lives in its support/ subdirectory." >&2
        return 1
    fi
    printf '%s\n' "$hl"
}
