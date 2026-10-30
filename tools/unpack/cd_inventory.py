#!/usr/bin/env python3
"""cd_inventory.py - classify every file on an extracted OS/2 install CD by how
an unpacking tool has to treat it, and write the expected result of unpacking
everything as a manifest (test vectors for a reimplementation).

    cd_inventory.py ROOT [--manifest OUT.tsv] [--unpack2 EXE]

Classes:
  pack2      A5 96 FD FF archive              -> unpack every member (+EA stream)
  pack1      A5 96 FE FF / other A5 96        -> unpack every member (+EA stream)
  fi-media   file named by an INSTDATA.INI File=() entry (plain copy; its EAs,
             if any, come from the sidecar named by EAFileSpec)
  fi-eas     NNNNNNNN.EAS sidecar (a bare 16-bit FEALIST)
  fi-ini     INSTDATA.INI itself
  zip/wpi    ZIP/JAR, WarpIN package: payload, not an IBM PACK format
  plain      everything else

Manifest columns (tab-separated):
  kind  container  member  size  md5  ea_md5  fdate  ftime  attr
kind is pack2/pack1 (one row per member; member = stored name) or fi (one row
per INSTDATA File=() entry; container = media file, member = target path).
ea_md5 is the md5 of the FEALIST as the original tool would apply it (PACK2:
cbList patched to the decoded length; PACK1 and FI: verbatim), '-' if none.
"""
import argparse, collections, hashlib, os, re, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ftcomp, pack1, pack2


def md5(b):
    return hashlib.md5(b).hexdigest() if b is not None else "-"


def fi_entries(root):
    """Yield (ini path, media path or None, eas path or None, kv) for every
    File=() entry of every INSTDATA.INI, resolving {variables} through the
    chain of parent-directory INSTDATA.INI files (child overrides parent) and
    MediaPath relative to the directory above the top of the feature tree."""
    inis = {}
    idx = {}
    for dp, dn, fn in os.walk(root):
        for f in fn:
            p = os.path.join(dp, f)
            idx[os.path.normpath(p).lower()] = p
            if f.upper() == "INSTDATA.INI":
                inis[os.path.normpath(dp)] = p

    def text(p):
        return open(p, "rb").read().decode("cp850", "replace").replace("\r", "")

    def variables(t):
        return {m[0].lower(): m[1] for m in re.findall(
            r"\tVariable=\(\n\t\tName=(\S+)\n(?:\t\tDescription=.*\n)?\t\tValue=(.*)\n", t)}

    for d, p in sorted(inis.items()):
        chain, x = [], d
        while x in inis:
            chain.append(x)
            x = os.path.dirname(x)
        mroot = x
        var = {}
        for a in reversed(chain):
            var.update(variables(text(inis[a])))
        sub = lambda s: re.sub(r"\{(\w+)\}", lambda m: var.get(m.group(1).lower(), m.group(0)), s)
        for blk in re.findall(r"\bFile=\((.*?)\n\t\)", text(p), re.S):
            kv = dict(re.findall(r"\t\t(\w+(?:\[\d+\])?)=(.*)", blk))
            mp = sub(sub(kv.get("MediaPath", ""))).replace("\\", "/")
            mf = sub(kv.get("MediaFileName", ""))
            cand = os.path.normpath(os.path.join(mroot, mp, mf)).lower()
            media = idx.get(cand)
            eas = None
            if "EAFileSpec" in kv:
                eas = idx.get(os.path.join(os.path.dirname(cand), kv["EAFileSpec"].lower()))
            kv["_target"] = sub(kv.get("TargetPath", "")) + "\\" + sub(kv.get("TargetFileName", ""))
            yield p, media, eas, kv


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--manifest")
    ap.add_argument("--unpack2", default=pack2.default_tables())
    a = ap.parse_args()
    if not a.unpack2 or not os.path.isfile(a.unpack2):
        sys.exit("cd_inventory.py: needs IBM's UNPACK2.EXE for the codec's tables: pass\n"
                 "  --unpack2 PATH or set OS2_UNPACK2 (it is \\OS2\\UNPACK2.EXE on any OS/2)")
    dec = ftcomp.FtcompDecoder(ftcomp.load_tables(a.unpack2))
    out = open(a.manifest, "w") if a.manifest else None
    cls = collections.Counter()
    nbytes = collections.Counter()
    errors = []

    fi_media, fi_eas = set(), set()
    nfi = fi_missing = 0
    fi_rows = []
    for ini, media, eas, kv in fi_entries(a.root):
        nfi += 1
        if not media:
            fi_missing += 1
            errors.append("FI media missing: %s %s" % (ini, kv.get("MediaFileName")))
            continue
        fi_media.add(media)
        if "EAFileSpec" in kv:
            if not eas:
                errors.append("FI EAS missing: %s %s" % (ini, kv["EAFileSpec"]))
            else:
                fi_eas.add(eas)
        fi_rows.append((media, eas, kv))

    for dp, dn, fn in os.walk(a.root):
        dn.sort()
        for f in sorted(fn):
            p = os.path.join(dp, f)
            rel = os.path.relpath(p, a.root)
            head = open(p, "rb").read(4)
            if head[:2] == b"\xa5\x96":
                d = open(p, "rb").read()
                kind = "pack2" if head == b"\xa5\x96\xfd\xff" else "pack1"
                cls[kind] += 1
                try:
                    if kind == "pack2":
                        for m in pack2.members(d):
                            data, ea = pack2.decode(dec, d, m)
                            nbytes[kind] += len(data)
                            if out:
                                out.write("pack2\t%s\t%s\t%d\t%s\t%s\t%04x\t%04x\t%02x\n" % (
                                    rel, m.name, len(data), md5(data), md5(ea), m.fdate, m.ftime, m.attr))
                    else:
                        for h, data, ea in pack1.members(d):
                            nbytes[kind] += len(data)
                            if out:
                                out.write("pack1\t%s\t%s\t%d\t%s\t%s\t%04x\t%04x\t%02x\n" % (
                                    rel, h.name, len(data), md5(data), md5(ea), h.fdate, h.ftime, h.attr))
                except Exception as e:
                    errors.append("%s: %r" % (rel, e))
                if p in fi_media:
                    cls["  (of which FI media)"] += 1
            elif p in fi_eas:
                cls["fi-eas"] += 1
            elif p in fi_media:
                cls["fi-media"] += 1
            elif f.upper() == "INSTDATA.INI":
                cls["fi-ini"] += 1
            elif head == b"PK\x03\x04":
                cls["zip"] += 1
            elif f.upper().endswith(".WPI"):
                cls["wpi"] += 1
            else:
                cls["plain"] += 1
    if out:
        for media, eas, kv in fi_rows:
            d = open(media, "rb").read()
            e = open(eas, "rb").read() if eas else None
            out.write("fi\t%s\t%s\t%d\t%s\t%s\t%s\t%s\t%s\n" % (
                os.path.relpath(media, a.root), kv["_target"], len(d), md5(d), md5(e),
                kv.get("LastWriteDate", "-"), kv.get("LastWriteTime", "-"), kv.get("AttrFile", "-")))
        out.close()
    print("files by class:", dict(cls))
    print("decoded bytes:", dict(nbytes))
    print("FI entries: %d, media missing: %d, with EAS sidecar: %d" % (nfi, fi_missing, len(fi_eas)))
    for e in errors[:20]:
        print("ERROR", e)
    print("%d errors" % len(errors))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
