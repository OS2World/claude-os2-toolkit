#!/usr/bin/env python3
"""
ne_xref.py - a call cross-reference over a directory of decompiled .c files.

Ghidra's own cross-references live in a project database that the pipeline
deletes after each run (-deleteProject), and the corpus that survives is plain
C text.  This recovers the call graph from that text: any identifier followed
by "(" that is also the name of another decompiled function counts as a call.
It is a text heuristic, not a symbol-table fact - it will miss a call made
through a function pointer, and it cannot tell a call from a same-named macro.
For "who touches this global", use the globals query, which is a plain word
search across the corpus.

Function names come from the filename, which the decompiler writes as
"<name>_<entry point>.c".

Usage:
    ne_xref.py <decompdir> callers <NAME>   who calls NAME
    ne_xref.py <decompdir> callees <NAME>   what NAME calls
    ne_xref.py <decompdir> globals <NAME>   which functions mention NAME
    ne_xref.py <decompdir> leaves           functions that call nothing local
    ne_xref.py <decompdir> roots            functions nobody local calls
    ne_xref.py <decompdir> sizes            functions by decompiled line count
"""
import argparse
import os
import re
import sys

CALL = re.compile(r'\b([A-Za-z_][A-Za-z0-9_]{2,})\s*\(')


def load(d):
    fns = {}
    if not os.path.isdir(d):
        sys.exit("%s: no such directory" % d)
    for fn in os.listdir(d):
        if not fn.endswith('.c'):
            continue
        name = fn.rsplit('_', 1)[0]
        with open(os.path.join(d, fn), errors='replace') as f:
            fns[name] = f.read()
    return fns


def main():
    ap = argparse.ArgumentParser(
        description="Call cross-reference over a directory of decompiled .c files.")
    ap.add_argument("decompdir", help="a decompiled_NN directory from a pipeline run")
    ap.add_argument("query", choices=["callers", "callees", "globals",
                                      "leaves", "roots", "sizes"])
    ap.add_argument("name", nargs="?", help="function or global name (callers/callees/globals)")
    args = ap.parse_args()

    if args.query in ("callers", "callees", "globals") and not args.name:
        ap.error("%s needs a NAME" % args.query)

    fns = load(args.decompdir)
    if not fns:
        sys.exit("%s: no .c files there" % args.decompdir)
    names = set(fns)
    calls = {n: sorted({m for m in CALL.findall(t) if m in names and m != n})
             for n, t in fns.items()}

    if args.query == 'callers':
        for n in sorted(calls):
            if args.name in calls[n]:
                print(n)
    elif args.query == 'callees':
        if args.name not in calls:
            sys.exit("no decompiled function named %s" % args.name)
        print('\n'.join(calls[args.name]))
    elif args.query == 'globals':
        pat = re.compile(r'\b%s\b' % re.escape(args.name))
        for n, txt in sorted(fns.items()):
            if n != args.name and pat.search(txt):
                print(n)
    elif args.query == 'leaves':
        for n in sorted(calls):
            if not calls[n]:
                print(n)
    elif args.query == 'roots':
        called = set()
        for v in calls.values():
            called.update(v)
        for n in sorted(names - called):
            print(n)
    elif args.query == 'sizes':
        for n, t in sorted(fns.items(), key=lambda kv: -len(kv[1].splitlines())):
            print('%5d  %s' % (len(t.splitlines()), n))


if __name__ == '__main__':
    main()
