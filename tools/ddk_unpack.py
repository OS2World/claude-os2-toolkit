#!/usr/bin/env python3
"""ddk_unpack.py - unpack every IBM DDK archive into ONE merged tree, with a manifest.

What the DDK holds, and why this script exists (measured against the 2004 DDK):

  ZIP/          38 package ZIPs + ZIP/REF/ 13 reference-book ZIPs = 51
  EXE/          the same 51 packages as OS/2 self-extracting EXEs, in some
                distributions already unpacked NEXT TO each EXE into EXE/<PKG>/
  HTML/         IBM's DDK web index + HTML renderings of 15 reference books

So the CONTENT may already be on disk, but only package-by-package: 38 separate
`EXE/<PKG>/DDK/...` trees, each a slice of one IBM install layout, with no view
of the whole - and 10 of the 13 reference-book INF files never unpacked at all.
IBM shipped these as self-extractors meant to be run from a drive root, one
after another, all landing in the same `\\DDK` tree. This script does that on
Linux and writes down what it did.

Layout it produces (a generated tree - regenerate it, do not edit it; the
archives are the artifact worth keeping):

  unpacked/ddk/         the merged IBM DDK install tree - base/, base32/, video/,
                        print/, dbcs/, mme/, wpshell/, testcert/, ibm16/, tools/,
                        docs/ (the .INF books), readme.doc
  unpacked/ddktools/    IBM's DDKTOOLS tree (MASM 6.0 + MSC 6.0, two packages
                        that merge into one `toolkits/` tree)
  unpacked/icatos2/     the ICAT debugger package (its own root, as shipped)
  unpacked/pkg/<pkg>/   packages that ship BARE FILES with no directory at all
                        (IBMTOOL, NDDK, NDISS, WEDGE, plus NICSAMPL's README.DOC).
                        Kept apart because they collide: IBMTOOL and WEDGE both
                        ship a top-level `makefile` with different contents.
  unpacked/MANIFEST.tsv one row per file: path, providing package, bytes, mtime
  unpacked/MANIFEST.md  per-package summary, merged-tree shape, duplicates,
                        collisions, and the ZIP-vs-EXE delta (see below)

Every path component is folded to LOWERCASE (`unzip -LL`). The archives were
made on HPFS, which is case-insensitive, and they disagree with each other:
`DDK/tools` vs `DDK/TOOLS`, `ddk/docs` vs `DDK/DOCS`. On a case-sensitive
filesystem those would split into two directories and a grep would see half the
tree. One rule, applied everywhere, keeps the merge honest and keeps citations
predictable. The as-shipped spelling is still visible in `EXE/<PKG>/`.

Why Info-ZIP `unzip` and not Python's `zipfile`: NDDK.ZIP (23 entries) and
WEDGE.ZIP (22 entries) - the 1980s NDIS packages - use the `implode` and
`shrink` methods, which `zipfile` can LIST but cannot DECOMPRESS
(NotImplementedError). `unzip` 6.0 handles all four methods used here
(deflate 11427, store 284, implode 43, shrink 2). Listing for the manifest and
the ZIP/EXE comparison stays in `zipfile`, which is enough for that.

ZIP vs EXE: 49 of the 51 pairs are content-identical (same CRC set). The two
that differ are both cases where the EXE is NEWER than the ZIP:
  DASD      EXE adds DDK/base/src/dev/dasd/makefile (3629 bytes)
  GRADBOOK  EXE's gradd.inf is dated 1999-06-10 (537,008 bytes); the ZIP's is
            1996-09-03 (530,150 bytes)
`--source exe` unpacks the self-extractors instead, and MANIFEST.md always
carries the computed delta, so this note can be re-derived rather than trusted.

Verification the script does, and how it fails (it must be able to):
  - `unzip` exit code > 1 on any archive aborts; unzip verifies each CRC as it
    extracts, so a corrupt member fails there rather than landing silently.
  - Two packages supplying the same merged path with DIFFERENT bytes is a
    COLLISION: the first is kept, the second reported, and the exit code is 1
    unless `--force` (which lets the later package overwrite).
  - The file count in the output tree is checked against the number of unique
    paths the archives declared, and a mismatch is an error.
  - No `unzip` on PATH is a named, immediate failure, not an empty tree.

Where the archives are: nothing is guessed. With no directory arguments the
tool asks the OS/2 library (see PATHS.md) for the DDK by role, using the parts
of the item that provides `ddk-headers`:

  zips -> the ZIP/ directory      exes -> the EXE/ directory
  ddk  -> the merged tree's ddk/  (so its parent is the default output tree)

A missing role, or a missing part, is a named failure and a non-zero exit -
never a guessed path and never a silent success.

Usage:
  ddk_unpack.py                      # unpack the library's DDK ZIPs
  ddk_unpack.py --clean              # wipe the output tree first
  ddk_unpack.py --source exe         # unpack the self-extractors instead
  ddk_unpack.py --out /some/dir      # elsewhere (the tree is disposable)
  ddk_unpack.py --zip-dir DIR        # archives that are not in the library

Stdlib only, on purpose.
"""

import argparse
import collections
import datetime
import filecmp
import os
import shutil
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.realpath(__file__))
LIB_ROLE = "ddk-headers"
STAGE = ".stage"
MANIFEST_TSV = "MANIFEST.tsv"
MANIFEST_MD = "MANIFEST.md"
BARE_DIR = "pkg"  # where a package's directory-less files go


def die(msg, rc=2):
    print(f"ddk_unpack: ERROR: {msg}", file=sys.stderr)
    sys.exit(rc)


# --- the library: ask for a role, never construct a path ---------------------

def lib_role(part):
    """Path the library gives for `part` of the DDK item, or None with a reason.

    Prefers the module (tools/os2lib.py, beside this script); falls back to the
    `os2-lib` CLI when this script is running without the module next to it.
    Returns (path, None) or (None, "why not"), so the caller decides whether a
    missing part is fatal - it is for the source directory, not for the
    optional ZIP/EXE comparison.
    """
    try:
        sys.path.insert(0, HERE)
        from os2lib import role, LibError  # noqa: E402
    except ImportError:
        pass
    else:
        try:
            return role(LIB_ROLE, part), None
        except LibError as e:
            return None, str(e)
    if shutil.which("os2-lib") is None:
        return None, ("os2lib.py is not beside this script and `os2-lib` is not on PATH, "
                      "so the OS/2 library cannot be asked where the DDK is")
    p = subprocess.run(["os2-lib", "role", LIB_ROLE, part],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        return None, (p.stderr.strip() or p.stdout.strip()
                      or f"os2-lib role {LIB_ROLE} {part} failed (rc={p.returncode})")
    out = p.stdout.strip().splitlines()
    return (out[0], None) if out else (None, f"os2-lib role {LIB_ROLE} {part} printed nothing")


def lib_die(part, why):
    die(f"{why}\n"
        f"  Wanted: the '{part}' part of the OS/2 library item providing '{LIB_ROLE}'.\n"
        f"  Either pass the directory explicitly (--zip-dir/--exe-dir/--out), or file the\n"
        f"  DDK into the library with the os2-toolkit:ingest skill (see PATHS.md) and give\n"
        f"  its ITEM.md a paths: entry for '{part}'.")


def find_archives(src_dir, ext):
    """All *.ext under src_dir (one level of REF/ subdir), case-insensitive."""
    found = []
    for dirpath, dirnames, filenames in os.walk(src_dir):
        # skip anything a previous extraction left next to the EXEs
        dirnames[:] = [d for d in dirnames if d.upper() == "REF"]
        for f in filenames:
            if f.lower().endswith(ext):
                found.append(os.path.join(dirpath, f))
    return sorted(found)


def pkg_name(path):
    return os.path.splitext(os.path.basename(path))[0].upper()


def list_entries(archive):
    """(name, crc, size, (y,m,d,H,M,S)) for every file member, via zipfile.

    zipfile can LIST implode/shrink members even though it cannot extract them,
    which is all the manifest and the ZIP/EXE comparison need.  A self-extracting
    EXE lists fine too: zipfile locates the central directory from the end.
    """
    with zipfile.ZipFile(archive) as zf:
        return [(i.filename, i.CRC, i.file_size, i.date_time)
                for i in zf.infolist() if not i.is_dir()]


def unzip_to(archive, dest):
    """Extract with Info-ZIP unzip, every name lowercased. rc>1 is fatal."""
    os.makedirs(dest, exist_ok=True)
    cmd = ["unzip", "-qq", "-o", "-LL", archive, "-d", dest]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if p.returncode > 1:
        die(f"unzip failed (rc={p.returncode}) on {archive}:\n{p.stdout}")
    # rc 1 = warnings only.  For a self-extractor that is the expected
    # "extra bytes at beginning" notice; anything else is worth seeing.
    if p.returncode == 1 and "extra bytes at beginning" not in p.stdout:
        print(f"  warning from unzip on {os.path.basename(archive)}: {p.stdout.strip()}")


def route(rel_parts, pkg):
    """Where a staged file goes in the merged tree.

    A file that ships inside a directory keeps that directory as its root - every
    package's `DDK/...` lands in the one `ddk/` tree, both DDKTOOLS halves in
    `ddktools/`, ICAT in `icatos2/`.  A BARE file (no directory) goes under
    pkg/<pkg>/, because bare files from different packages collide (IBMTOOL and
    WEDGE both ship a `makefile`).
    """
    if len(rel_parts) == 1:
        return os.path.join(BARE_DIR, pkg.lower(), rel_parts[0])
    return os.path.join(*rel_parts)


def merge_stage(stage_dir, out_dir, pkg, providers, dupes, collisions, force):
    """Move every staged file into place; record provider / dupe / collision."""
    moved = 0
    for dirpath, _dirnames, filenames in os.walk(stage_dir):
        for f in filenames:
            src = os.path.join(dirpath, f)
            rel = os.path.relpath(src, stage_dir)
            dest_rel = route(rel.split(os.sep), pkg)
            dest = os.path.join(out_dir, dest_rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            if os.path.lexists(dest):
                if filecmp.cmp(src, dest, shallow=False):
                    if dest_rel in providers and providers[dest_rel][-1] != pkg:
                        dupes.append((dest_rel, providers[dest_rel][-1], pkg))
                    os.remove(src)
                else:
                    prior = providers.get(dest_rel, ["<pre-existing file>"])[-1]
                    collisions.append((dest_rel, prior, pkg,
                                       os.path.getsize(dest), os.path.getsize(src)))
                    if force:
                        os.replace(src, dest)
                    else:
                        os.remove(src)
            else:
                os.replace(src, dest)  # same filesystem: keeps unzip's mtime
            providers.setdefault(dest_rel, []).append(pkg)
            moved += 1
    return moved


def compare_zip_exe(zip_dir, exe_dir):
    """Per package: are the ZIP and the self-extracting EXE the same content?

    Compares the set of (lowercased name, CRC, size) triples.  Returns
    {pkg: (only_in_zip, only_in_exe)} for the packages that differ, plus the
    count of pairs compared.
    """
    zips = {pkg_name(p): p for p in find_archives(zip_dir, ".zip")}
    exes = {pkg_name(p): p for p in find_archives(exe_dir, ".exe")}
    diffs = {}
    compared = 0
    for pkg in sorted(set(zips) & set(exes)):
        try:
            a = {(n.lower(), c, s, d) for n, c, s, d in list_entries(zips[pkg])}
            b = {(n.lower(), c, s, d) for n, c, s, d in list_entries(exes[pkg])}
        except zipfile.BadZipFile as e:
            diffs[pkg] = ([f"<unreadable: {e}>"], [])
            continue
        compared += 1
        if a != b:
            diffs[pkg] = (sorted(a - b), sorted(b - a))
    unpaired = sorted((set(zips) ^ set(exes)))
    return diffs, compared, unpaired


def fmt_dt(dt):
    y, m, d, H, M, S = dt
    return f"{y:04d}-{m:02d}-{d:02d} {H:02d}:{M:02d}:{S:02d}"


def write_manifests(out_dir, per_pkg, providers, dupes, collisions, zipexe, source, archives):
    # --- MANIFEST.tsv: one row per file, sorted by path -------------------
    rows = []
    for dest_rel in sorted(providers):
        full = os.path.join(out_dir, dest_rel)
        st = os.stat(full)
        mtime = datetime.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        rows.append((dest_rel, "+".join(providers[dest_rel]), st.st_size, mtime))
    with open(os.path.join(out_dir, MANIFEST_TSV), "w") as f:
        f.write("path\tpackage\tbytes\tmtime\n")
        for r in rows:
            f.write("\t".join(str(x) for x in r) + "\n")

    # --- MANIFEST.md: the human summary -----------------------------------
    total_files = len(rows)
    total_bytes = sum(r[2] for r in rows)
    second = collections.Counter()
    for dest_rel, _p, size, _m in rows:
        parts = dest_rel.split("/")
        key = "/".join(parts[:2]) if len(parts) > 2 else parts[0]
        second[key] += 1

    L = []
    L.append("# IBM DDK - merged unpack manifest\n")
    L.append(f"Generated by `ddk_unpack.py --source {source}` on "
             f"{datetime.date.today().isoformat()} from {len(archives)} archives. "
             f"**This directory is generated - regenerate it, do not edit it.** The DDK's own "
             f"ZIP and EXE archives are the artifact worth keeping; the tool's docstring is the "
             f"authority for the layout rules.\n")
    L.append(f"Files: **{total_files}** ({total_bytes/1e6:.1f} MB uncompressed). "
             f"Every path component is lowercased (`unzip -LL`); see the tool for why.\n")

    L.append("## What each package contributes\n")
    L.append("| package | archive | files | MB | lands in |")
    L.append("|---|---|---:|---:|---|")
    for pkg, info in per_pkg:
        roots = ", ".join(f"`{r}` ({n})" for r, n in sorted(info["roots"].items(), key=lambda x: -x[1]))
        L.append(f"| {pkg} | `{info['archive']}` | {info['files']} | {info['bytes']/1e6:.1f} | {roots} |")

    L.append("\n## Shape of the merged tree (files per second-level directory)\n")
    L.append("| directory | files |")
    L.append("|---|---:|")
    for k, n in sorted(second.items(), key=lambda x: (-x[1], x[0])):
        L.append(f"| `{k}` | {n} |")

    L.append(f"\n## Same path, same bytes, supplied by two packages ({len(dupes)})\n")
    L.append("Harmless - one copy kept, both packages recorded in `MANIFEST.tsv`.\n")
    for path, a, b in dupes:
        L.append(f"- `{path}`: {a} and {b}")

    L.append(f"\n## Same path, DIFFERENT bytes ({len(collisions)})\n")
    if collisions:
        L.append("The first package's copy is kept unless `--force` was given. "
                 "A non-empty list here is a finding, not a formatting note.\n")
        for path, a, b, sa, sb in collisions:
            L.append(f"- `{path}`: {a} ({sa} bytes) vs {b} ({sb} bytes)")
    else:
        L.append("None. Bare top-level files are routed under `pkg/<package>/` precisely "
                 "because IBMTOOL and WEDGE both ship a `makefile` that would otherwise collide here.")

    L.append("\n## ZIP vs self-extracting EXE - are the two forms the same content?\n")
    if zipexe is None:
        L.append("Not computed (no EXE directory was available).")
    else:
        diffs, compared, unpaired = zipexe
        L.append(f"Compared {compared} ZIP/EXE pairs by (name, CRC, size, date); "
                 f"**{compared - len(diffs)} identical, {len(diffs)} differ.**"
                 + (f" Unpaired: {', '.join(unpaired)}." if unpaired else "") + "\n")
        for pkg, (only_zip, only_exe) in sorted(diffs.items()):
            L.append(f"- **{pkg}**")
            for e in only_zip:
                L.append(f"  - only in ZIP: " + (f"`{e[0]}` {e[2]} bytes, {fmt_dt(e[3])}" if isinstance(e, tuple) else e))
            for e in only_exe:
                L.append(f"  - only in EXE: `{e[0]}` {e[2]} bytes, {fmt_dt(e[3])}")
    with open(os.path.join(out_dir, MANIFEST_MD), "w") as f:
        f.write("\n".join(L) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__)
    ap.add_argument("--source", choices=["zip", "exe"], default="zip",
                    help="unpack the ZIPs (default) or the self-extracting EXEs")
    ap.add_argument("--zip-dir", help="the DDK's ZIP directory (default: the library's "
                                      f"'{LIB_ROLE}' item, part `zips`)")
    ap.add_argument("--exe-dir", help="the DDK's EXE directory (default: the library's "
                                      f"'{LIB_ROLE}' item, part `exes`)")
    ap.add_argument("--out", help="output tree (default: the parent of the library's "
                                  f"'{LIB_ROLE}' item, part `ddk`)")
    ap.add_argument("--clean", action="store_true", help="remove the output tree first")
    ap.add_argument("--force", action="store_true",
                    help="on a same-path/different-bytes collision, let the later package win")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    if shutil.which("unzip") is None:
        die("Info-ZIP `unzip` is not on PATH. It is required: NDDK.ZIP and WEDGE.ZIP use "
            "the implode/shrink methods that Python's zipfile cannot decompress.")

    # Resolve the three directories.  The one we unpack FROM must exist, so a
    # library miss there is fatal; the other archive form is only wanted for the
    # ZIP/EXE comparison, and its absence is reported in the manifest instead.
    zip_dir, zip_why = (args.zip_dir, None) if args.zip_dir else lib_role("zips")
    exe_dir, exe_why = (args.exe_dir, None) if args.exe_dir else lib_role("exes")
    if args.source == "zip" and zip_dir is None:
        lib_die("zips", zip_why)
    if args.source == "exe" and exe_dir is None:
        lib_die("exes", exe_why)

    out = args.out
    if out is None:
        ddk_dir, ddk_why = lib_role("ddk")
        if ddk_dir is None:
            lib_die("ddk", ddk_why)
        # The library names the merged tree's `ddk/` subdirectory; the tree this
        # tool writes is its parent (it also holds ddktools/, icatos2/, pkg/ and
        # the manifests).  Pass --out to put it anywhere else.
        out = os.path.dirname(os.path.normpath(ddk_dir))

    src_dir = zip_dir if args.source == "zip" else exe_dir
    ext = ".zip" if args.source == "zip" else ".exe"
    if not os.path.isdir(src_dir):
        die(f"source directory does not exist: {src_dir}")
    archives = find_archives(src_dir, ext)
    if not archives:
        die(f"no *{ext} archives under {src_dir} - nothing to unpack, refusing to report success")

    out = os.path.abspath(out)
    if args.clean and os.path.isdir(out):
        # Only wipe something this tool made (or an empty dir): the manifest is the mark.
        if os.listdir(out) and not os.path.exists(os.path.join(out, MANIFEST_MD)):
            die(f"--clean refused: {out} is non-empty and has no {MANIFEST_MD}, so it is not ours")
        shutil.rmtree(out)
    os.makedirs(out, exist_ok=True)
    stage_root = os.path.join(out, STAGE)
    if os.path.exists(stage_root):
        shutil.rmtree(stage_root)

    providers = {}      # dest_rel -> [pkg, ...]
    dupes, collisions = [], []
    per_pkg = []
    declared = set()    # unique routed paths the archives declare, for the final count check
    log = (lambda *a: None) if args.quiet else print

    log(f"ddk_unpack: {len(archives)} archives from {src_dir} -> {out}")
    for archive in archives:
        pkg = pkg_name(archive)
        try:
            entries = list_entries(archive)
        except zipfile.BadZipFile as e:
            die(f"{archive}: not a readable zip archive ({e}) - "
                f"truncated download or corrupt file; nothing from it was unpacked")
        roots = collections.Counter()
        for name, _crc, _size, _dt in entries:
            parts = name.lower().split("/")
            declared.add(route(parts, pkg))
            roots[parts[0] if len(parts) > 1 else f"{BARE_DIR}/{pkg.lower()}"] += 1
        stage = os.path.join(stage_root, pkg)
        unzip_to(archive, stage)
        moved = merge_stage(stage, out, pkg, providers, dupes, collisions, args.force)
        if moved != len(entries):
            die(f"{pkg}: archive declares {len(entries)} files but {moved} were staged")
        per_pkg.append((pkg, {"archive": os.path.relpath(archive, src_dir), "files": len(entries),
                              "bytes": sum(e[2] for e in entries), "roots": dict(roots)}))
        log(f"  {pkg:10s} {len(entries):5d} files  -> " +
            ", ".join(f"{r}/" for r in sorted(roots)))
    shutil.rmtree(stage_root)

    # --- the count check: what is on disk must be what the archives declared --
    on_disk = 0
    for dirpath, _d, filenames in os.walk(out):
        on_disk += sum(1 for f in filenames if f not in (MANIFEST_TSV, MANIFEST_MD))
    if on_disk != len(declared):
        die(f"output tree holds {on_disk} files but the archives declare {len(declared)} unique paths")

    zipexe = None
    if zip_dir and exe_dir and os.path.isdir(zip_dir) and os.path.isdir(exe_dir):
        zipexe = compare_zip_exe(zip_dir, exe_dir)
    elif not args.quiet and exe_dir is None:
        print(f"  (ZIP/EXE comparison skipped: {exe_why})")

    write_manifests(out, per_pkg, providers, dupes, collisions, zipexe, args.source, archives)

    log(f"\n{len(declared)} files, {len(dupes)} identical duplicates, {len(collisions)} collisions")
    if zipexe:
        diffs, compared, unpaired = zipexe
        log(f"ZIP vs EXE: {compared - len(diffs)}/{compared} identical"
            + (f"; differ: {', '.join(sorted(diffs))}" if diffs else ""))
    log(f"manifest: {os.path.join(out, MANIFEST_MD)}")
    if collisions and not args.force:
        for path, a, b, sa, sb in collisions:
            print(f"COLLISION: {path}: kept {a} ({sa} B), dropped {b} ({sb} B)", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
