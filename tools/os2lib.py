#!/usr/bin/env python3
"""os2lib.py - the OS/2 library: find material by role, never by path.

Implements PATHS.md. One library root ($OS2_LIBRARY) holds items under fixed
categories; each item is <category>/<slug>/ITEM.md plus the material itself or a
link to it. Tools and skills ask for a ROLE ("toolkit-headers") and get a path,
or a loud, named failure - never an empty success, because an empty probe reads
as "the material says nothing" (see PATHS.md, the whole point of it).

Module:   from os2lib import role, library_root
CLI:      os2-lib {root,init,ls,roles,role,path,grep,new,convert,check,catalog}

Standard library only: ITEM.md frontmatter is a strict YAML subset parsed here
(scalars, quoted strings, [inline, lists], nested maps, lists of scalars or
maps), so the tool runs on a bare Python with nothing installed.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

CATEGORIES = ["docs", "source", "examples", "re", "media", "toolchains", "notes"]
STATE = "state"
KINDS = {"book", "book-set", "article-set", "sdk", "headers", "source-tree", "samples",
         "binaries", "decompile", "dump", "notes", "disc-image", "system-tree",
         "vm-image", "toolchain"}
LICENCES = {"own", "ibm", "third-party", "private", "restricted", "unknown"}
MODES = {"link", "convert", "import", "adopt"}
CANONICAL = {"archive", "tree", "file"}
REQUIRED = ["title", "category", "kind", "provides", "licence", "mode"]
SLUG_RE = re.compile(r"^[a-z0-9]+(?:[.-][a-z0-9]+)*$")
SEARCH = {"text", "original", "both"}
KEY_ORDER = ["title", "category", "kind", "provides", "licence", "mode", "canonical",
             "original", "acquired", "part_of", "derived_from", "converter", "search",
             "regenerable", "paths", "copies", "vm"]

# Search order: IBM's word first, then third-party, then the user's own, then
# anything of unknown standing; notes after all published material.
LICENCE_RANK = {"ibm": 0, "third-party": 1, "own": 2, "private": 2, "unknown": 3, "restricted": 4}
# Kinds whose content is not text; grep skips them unless a role names them.
OPAQUE_KINDS = {"binaries", "disc-image", "vm-image", "dump", "system-tree", "toolchain"}
TEXT_GLOBS = ["*.txt", "*.md", "*.h", "*.hpp", "*.inc", "*.c", "*.cpp", "*.asm", "*.def",
              "*.rc", "*.dlg", "*.idl", "*.cmd", "*.rex", "*.htm", "*.html", "*.xml",
              "*.json", "*.sym.map", "*.map", "*.doc", "*.TXT", "*.H", "*.INC", "*.C",
              "*.ASM", "*.DEF", "*.RC", "*.IDL", "*.CMD", "*.HTM", "*.DOC", "*.MAP"]

HERE = os.path.dirname(os.path.realpath(__file__))
KIT = os.path.dirname(HERE)


class LibError(Exception):
    """A named, user-actionable failure. The CLI prints it and exits 1."""


# ------------------------------------------------------------------ root

def config_file():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "os2-toolkit", "library")


def library_root():
    """$OS2_LIBRARY -> config file -> default (PATHS.md section 2)."""
    v = os.environ.get("OS2_LIBRARY")
    if not v:
        try:
            with open(config_file()) as f:
                v = f.read().strip()
        except OSError:
            v = ""
    if not v:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
        v = os.path.join(base, "os2-toolkit", "library")
    return os.path.abspath(os.path.expanduser(v))


# ------------------------------------------------------------------ YAML subset

def _strip_comment(line):
    out, q = [], None
    for i, ch in enumerate(line):
        if q:
            if ch == q:
                q = None
        elif ch in "\"'":
            q = ch
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            break
        out.append(ch)
    return "".join(out).rstrip()


def _split_inline(s):
    items, cur, q = [], [], None
    for ch in s:
        if q:
            cur.append(ch)
            if ch == q:
                q = None
        elif ch in "\"'":
            q = ch
            cur.append(ch)
        elif ch == ",":
            items.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if "".join(cur).strip():
        items.append("".join(cur).strip())
    return items


def _scalar(s):
    s = s.strip()
    if s == "":
        return None
    if s[0] == s[-1] and s[0] in "\"'" and len(s) >= 2:
        return s[1:-1]
    if s.startswith("[") and s.endswith("]"):
        return [_scalar(x) for x in _split_inline(s[1:-1])]
    if s in ("null", "~"):
        return None
    if s in ("true", "false"):
        return s == "true"
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    return s


def _parse_block(lines, i, indent):
    """Parse lines[i:] at exactly `indent` spaces. Returns (value, next_i)."""
    if i < len(lines) and lines[i][1].startswith("- "):
        seq = []
        while i < len(lines) and lines[i][0] == indent and lines[i][1].startswith("- "):
            rest = lines[i][1][2:]
            m = re.match(r"^([A-Za-z_][\w-]*):(\s|$)(.*)$", rest)
            if m:  # a map item: first key on the dash line, the rest indented by 2
                sub = [(indent + 2, rest)]
                j = i + 1
                while j < len(lines) and lines[j][0] > indent:
                    sub.append(lines[j])
                    j += 1
                val, _ = _parse_block(sub, 0, indent + 2)
                seq.append(val)
                i = j
            else:
                seq.append(_scalar(rest))
                i += 1
        return seq, i
    mapping = {}
    while i < len(lines) and lines[i][0] == indent:
        text = lines[i][1]
        m = re.match(r"^([A-Za-z_][\w-]*):(?:\s+(.*))?$", text)
        if not m:
            raise LibError("cannot parse line: %r" % text)
        key, val = m.group(1), m.group(2)
        i += 1
        if val is None or val == "":
            if i < len(lines) and lines[i][0] > indent:
                val, i = _parse_block(lines, i, lines[i][0])
            else:
                val = None
        else:
            val = _scalar(val)
        mapping[key] = val
    return mapping, i


def parse_frontmatter(text):
    """Return (meta dict, body) for an ITEM.md."""
    if not text.startswith("---"):
        raise LibError("no frontmatter (ITEM.md must start with ---)")
    parts = text.split("\n")
    try:
        end = parts.index("---", 1)
    except ValueError:
        raise LibError("frontmatter is not closed with ---")
    lines = []
    for raw in parts[1:end]:
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise LibError("tabs in indentation")
        line = _strip_comment(raw)
        if line.strip():
            lines.append((len(line) - len(line.lstrip(" ")), line.strip()))
    meta, i = _parse_block(lines, 0, 0) if lines else ({}, 0)
    if i != len(lines):
        raise LibError("unexpected indentation near: %r" % lines[i][1])
    return meta, "\n".join(parts[end + 1:])


def _emit_scalar(v):
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, list):
        return "[" + ", ".join(_emit_scalar(x) for x in v) + "]"
    s = str(v)
    if s == "" or re.search(r"[:#\[\],'\"]|^\s|\s$|^(null|true|false|~|-?\d+)$", s):
        return '"' + s.replace('"', "'") + '"'
    return s


def emit_frontmatter(meta):
    out = ["---"]
    keys = [k for k in KEY_ORDER if k in meta] + [k for k in meta if k not in KEY_ORDER]
    for k in keys:
        v = meta[k]
        if isinstance(v, dict):
            if not v:
                continue
            out.append("%s:" % k)
            for sk, sv in v.items():
                out.append("  %s: %s" % (sk, _emit_scalar(sv)))
        elif isinstance(v, list) and v and isinstance(v[0], dict):
            out.append("%s:" % k)
            for entry in v:
                first = True
                for sk, sv in entry.items():
                    out.append("%s%s: %s" % ("  - " if first else "    ", sk, _emit_scalar(sv)))
                    first = False
        else:
            out.append("%s: %s" % (k, _emit_scalar(v)))
    out.append("---")
    return "\n".join(out) + "\n"


# ------------------------------------------------------------------ items

class Item:
    def __init__(self, root, category, slug):
        self.root, self.category, self.slug = root, category, slug
        self.dir = os.path.join(root, category, slug)
        self.file = os.path.join(self.dir, "ITEM.md")
        self.meta, self.error = {}, None
        try:
            with open(self.file, encoding="utf-8") as f:
                self.meta, _ = parse_frontmatter(f.read())
        except (OSError, LibError, UnicodeDecodeError) as e:
            self.error = str(e)

    def get(self, key, default=None):
        v = self.meta.get(key, default)
        return default if v is None else v

    @property
    def provides(self):
        v = self.get("provides", [])
        return v if isinstance(v, list) else [v]

    def original(self):
        """The canonical form's location, or None. Symlink target need not exist."""
        link = os.path.join(self.dir, "original")
        if os.path.islink(link) or os.path.exists(link):
            return link
        files = os.path.join(self.dir, "files")
        return files if os.path.isdir(files) else None

    def base(self):
        return self.original() or self.dir

    def available(self):
        o = self.original()
        return o is None or os.path.exists(o)


def iter_items(root=None, category=None):
    root = root or library_root()
    for cat in ([category] if category else CATEGORIES):
        d = os.path.join(root, cat)
        if not os.path.isdir(d):
            continue
        for slug in sorted(os.listdir(d)):
            if os.path.isdir(os.path.join(d, slug)) and not slug.startswith("."):
                yield Item(root, cat, slug)


def find_item(slug, root=None):
    hits = [it for it in iter_items(root) if it.slug == slug]
    if not hits:
        raise LibError("no item with slug '%s' (os2-lib ls lists them)" % slug)
    return hits[0]


def role(name, part=None, root=None, all_hits=False):
    """Path(s) of the item(s) providing role `name` (optionally a named part).

    Raises LibError - naming the role - when nothing provides it, so a caller
    can never mistake "not in the library" for "the material is empty".
    """
    root = root or library_root()
    hits = [it for it in iter_items(root) if not it.error and name in it.provides]
    if not hits:
        raise LibError("no item provides role '%s' in the library at %s.\n"
                       "If you have this material, tell Claude where it is so it can be "
                       "ingested (os2-toolkit:ingest)." % (name, root))
    paths = []
    for it in hits:
        if part:
            sub = (it.get("paths", {}) or {}).get(part)
            if not sub:
                continue
            p = os.path.join(it.dir, sub)
        else:
            p = it.base()
        if not os.path.exists(p):
            raise LibError("item '%s' provides '%s' but %s does not exist "
                           "(an unmounted disk?)" % (it.slug, name, p))
        paths.append(p)
    if not paths:
        raise LibError("items %s provide role '%s' but none declares a part '%s' in paths:"
                       % (", ".join(it.slug for it in hits), name, part))
    return paths if all_hits else paths[0]


# ------------------------------------------------------------------ commands

def cmd_root(a):
    print(library_root())


def cmd_init(a):
    root = os.path.abspath(os.path.expanduser(a.path)) if a.path else library_root()
    for c in CATEGORIES + [STATE]:
        os.makedirs(os.path.join(root, c), exist_ok=True)
    if a.save:
        os.makedirs(os.path.dirname(config_file()), exist_ok=True)
        with open(config_file(), "w") as f:
            f.write(root + "\n")
        print("saved %s -> %s" % (config_file(), root))
    print(root)


def cmd_ls(a):
    rows = []
    for it in iter_items(category=a.category):
        if a.role and a.role not in it.provides:
            continue
        if it.error:
            rows.append((it.category + "/" + it.slug, "BROKEN", "", "", it.error))
            continue
        flag = "" if it.available() else "  [original missing]"
        rows.append((it.category + "/" + it.slug, it.get("kind", "?"), it.get("mode", "?"),
                     it.get("licence", "?"), ",".join(map(str, it.provides)) + flag))
    if not rows:
        print("(no items%s in %s)" % (" providing " + a.role if a.role else "", library_root()),
              file=sys.stderr)
        return 1
    w = [max(len(r[i]) for r in rows) for i in range(4)]
    for r in rows:
        print("  ".join(r[i].ljust(w[i]) for i in range(4)) + "  " + r[4])


def cmd_roles(a):
    counts = {}
    for it in iter_items():
        for r in it.provides:
            counts.setdefault(r, []).append(it.slug)
    if not counts:
        print("(no roles: the library at %s has no items)" % library_root(), file=sys.stderr)
        return 1
    for r in sorted(counts):
        print("%-28s %s" % (r, ", ".join(counts[r])))


def cmd_role(a):
    for p in role(a.role, a.part, all_hits=a.all) if a.all else [role(a.role, a.part)]:
        print(p)


def cmd_path(a):
    it = find_item(a.slug)
    p = os.path.join(it.dir, a.subpath) if a.subpath else it.dir
    if not os.path.exists(p):
        raise LibError("%s does not exist" % p)
    print(p)


def _cover(path, excluded):
    """Paths that together cover `path` minus the `excluded` subtrees (realpaths)."""
    rp = os.path.realpath(path)
    if rp in excluded:
        return []
    if not any(e.startswith(rp + os.sep) for e in excluded) or not os.path.isdir(path):
        return [path]
    out = []
    for name in sorted(os.listdir(path)):
        out += _cover(os.path.join(path, name), excluded)
    return out


def _part_originals(it):
    """Realpaths of the originals of items that are part_of `it` - searched as
    those items, so the parent must not search them again."""
    parts = set()
    for other in iter_items(it.root):
        if not other.error and other.get("part_of") == it.slug:
            o = other.original()
            if o and os.path.exists(o):
                parts.add(os.path.realpath(o))
    return parts


def _search_roots(it):
    """(path, filter_to_text_globs) pairs grep should read for an item.

    Derived text/ and tree/ are read whole. The original is read too, filtered to
    text-like files, so a converted book set that also ships .htm or .txt files
    is searched in full. ITEM.md `search: text|original|both` (default both)
    narrows it - e.g. a mirror whose clean text duplicates its HTML."""
    mode = it.get("search", "both")
    roots = []
    if mode in ("text", "both"):
        for sub in ("text", "tree"):
            p = os.path.join(it.dir, sub)
            if os.path.isdir(p):
                roots.append((p, sub == "tree"))
    if mode in ("original", "both") and it.get("mode") in ("link", "convert", "import"):
        o = it.original()
        if o and os.path.exists(o):
            roots.append((o, True))
    excluded = _part_originals(it)
    if excluded:
        roots = [(p, f) for root, f in roots for p in _cover(root, excluded)]
    return roots


def _grep_path(base, path, pattern, filtered):
    cmd = list(base)
    if filtered and os.path.isdir(path):
        cmd += ["--include=" + g for g in TEXT_GLOBS]
    cmd += ["-e", pattern, path]
    r = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    if r.returncode > 1:
        raise LibError("grep failed on %s: %s" % (path, r.stderr.strip()))
    return r.stdout.splitlines()


def _print_group(label, lines, strip, limit):
    print("== %s  - %d match(es) ==" % (label, len(lines)))
    for ln in lines[:limit]:
        print("  " + ln.replace(strip, ""))
    if len(lines) > limit:
        print("  ... %d more (raise --max or narrow the search)" % (len(lines) - limit))


ZERO_HINT = """A zero result is NOT proof that OS/2 lacks the facility. Before concluding that:
  - try IBM's wording, not yours ("presentation space", not "canvas"), and the base name
    without a prefix ("OpenDC", not "DevOpenDC");
  - search a fragment: IBM's box-drawn tables split phrases across cells;
  - check what the library holds (os2-lib roles) and what was NOT searched above;
  - a facility may be a WPS/SOM method or an IOCtl rather than a Win*/Dos* call."""


def cmd_grep(a):
    """Search in provenance order: this kit's os2ref/, then IBM, third-party, own,
    unknown, notes. Case-insensitive by default (scanned and typeset book text is
    case-damaged), always -a (IBM code-page text reads as binary to grep), and
    per-group counts plus a list of what was NOT searched, so a miss can be
    attributed to the probe rather than to the material."""
    items = [it for it in iter_items(category=a.category) if not it.error]
    if a.role:
        items = [it for it in items if a.role in it.provides]
    elif not a.include_restricted:
        items = [it for it in items if it.get("licence") != "restricted"]
    if not a.role:
        items = [it for it in items if it.get("kind") not in OPAQUE_KINDS]
    items.sort(key=lambda it: (it.category == "notes", LICENCE_RANK.get(it.get("licence"), 3), it.slug))
    base = ["grep", "-rna", "--color=never"]
    if not a.case:
        base.append("-i")
    for flag in ("w", "F", "E"):
        if getattr(a, flag):
            base.append("-" + flag)
    if a.context:
        base += ["-C", str(a.context)]
    searched, unsearchable, silent, total = 0, [], [], 0
    if not (a.role or a.category or a.no_os2ref):
        ref = os.path.join(KIT, "os2ref")
        if os.path.isdir(ref):
            searched += 1
            lines = _grep_path(base, ref, a.pattern, True)
            if lines:
                total += len(lines)
                _print_group("os2ref  (this kit: verified, per-claim provenance tags)", lines, KIT + "/", a.max)
            else:
                silent.append("os2ref")
    if not items and not searched:
        raise LibError("nothing to search: no matching items in %s" % library_root())
    for it in items:
        roots = _search_roots(it)
        if not roots:
            why = "original missing" if not it.available() else "no text (convert it?)"
            unsearchable.append("%s (%s)" % (it.slug, why))
            continue
        searched += 1
        lines = []
        for path, filtered in roots:
            lines += _grep_path(base, path, a.pattern, filtered)
        if lines:
            total += len(lines)
            _print_group("%s/%s  (%s, %s)" % (it.category, it.slug, it.get("licence"), it.get("kind")),
                         lines, it.dir + "/", a.max)
        else:
            silent.append(it.slug)
    sys.stdout.flush()
    print("-- %d match(es) in %d searched source(s)" % (total, searched), file=sys.stderr)
    if silent and total:
        print("-- no matches in: " + ", ".join(silent), file=sys.stderr)
    if unsearchable:
        print("-- NOT searched: " + "; ".join(unsearchable), file=sys.stderr)
    if not total:
        print(ZERO_HINT, file=sys.stderr)
    return 0 if total else 1


def cmd_new(a):
    if a.category not in CATEGORIES:
        raise LibError("category must be one of: " + ", ".join(CATEGORIES))
    if not SLUG_RE.match(a.slug):
        raise LibError("slug '%s' must be lowercase publisher-title[-edition], "
                       "letters/digits separated by - or ." % a.slug)
    for field, allowed in (("kind", KINDS), ("licence", LICENCES), ("mode", MODES)):
        if getattr(a, field) not in allowed:
            raise LibError("%s must be one of: %s" % (field, ", ".join(sorted(allowed))))
    if a.search and a.search not in SEARCH:
        raise LibError("search must be one of: " + ", ".join(sorted(SEARCH)))
    if a.canonical and a.canonical not in CANONICAL:
        raise LibError("canonical must be one of: " + ", ".join(sorted(CANONICAL)))
    root = library_root()
    d = os.path.join(root, a.category, a.slug)
    if os.path.exists(d):
        raise LibError("%s already exists" % d)
    clash = [it for it in iter_items(root) if it.slug == a.slug]
    if clash:
        raise LibError("slug '%s' is already used in %s/" % (a.slug, clash[0].category))
    original = None
    if a.original and a.original != "unknown":
        original = os.path.abspath(os.path.expanduser(a.original))
        if not os.path.exists(original):
            raise LibError("original %s does not exist" % original)
    if a.mode in ("link", "convert") and not original:
        raise LibError("mode %s needs --original PATH" % a.mode)
    parts = {}
    for spec in a.part or []:
        name, sep, sub = spec.partition("=")
        if not sep or not name or not sub:
            raise LibError("--part must be NAME=SUBPATH (e.g. headers=original/H), got '%s'" % spec)
        if sub.split("/", 1)[0] == "original":
            real = os.path.join(original or "", sub.split("/", 1)[1] if "/" in sub else "")
            if not original or not os.path.exists(real):
                raise LibError("--part %s: %s does not exist" % (name, real))
        parts[name] = sub
    os.makedirs(d)
    if original and a.mode in ("link", "convert"):
        os.symlink(original, os.path.join(d, "original"))
    if a.mode == "import":
        os.makedirs(os.path.join(d, "files"))
    if a.mode in ("convert", "adopt"):
        os.makedirs(os.path.join(d, "text"), exist_ok=True)
    meta = {
        "title": a.title, "category": a.category, "kind": a.kind,
        "provides": [p for p in (a.provides or "").split(",") if p],
        "licence": a.licence, "mode": a.mode,
        "canonical": a.canonical or ("tree" if original and os.path.isdir(original) else "file"),
        "original": original or ("unknown" if a.mode == "adopt" else a.original),
        "acquired": time.strftime("%Y-%m-%d"),
        "part_of": a.part_of, "derived_from": a.derived_from,
        "converter": None, "search": a.search, "regenerable": a.mode != "adopt", "paths": parts, "copies": [],
    }
    with open(os.path.join(d, "ITEM.md"), "w", encoding="utf-8") as f:
        f.write(emit_frontmatter(meta))
        f.write("\n# %s\n\nWhat this is, which edition, where it came from, and anything a reader "
                "should know before citing it.\n" % a.title)
    write_catalog(root)
    print(d)
    if a.mode == "import":
        print("import mode: copy or move the material into %s/files (ask the user which)" % d,
              file=sys.stderr)


def set_field(item, key, value):
    with open(item.file, encoding="utf-8") as f:
        text = f.read()
    meta, body = parse_frontmatter(text)
    meta[key] = value
    with open(item.file, "w", encoding="utf-8") as f:
        f.write(emit_frontmatter(meta) + body)


def cmd_convert(a):
    it = find_item(a.slug)
    src = it.original()
    if not src or not os.path.exists(src):
        raise LibError("item '%s' has no available original to convert" % it.slug)
    out = os.path.join(it.dir, "text")
    os.makedirs(out, exist_ok=True)
    if os.path.isdir(src):
        todo = []
        for dp, _, fns in os.walk(src, followlinks=True):
            for fn in sorted(fns):
                if fn.lower().rsplit(".", 1)[-1] in ("inf", "hlp", "pdf"):
                    todo.append(os.path.join(dp, fn))
    else:
        todo = [src]
    if not todo:
        raise LibError("no INF, HLP or PDF files under %s" % src)
    inf2txt = os.path.join(KIT, "tools", "inf2txt", "inf2txt.sh")
    pdf2txt = os.path.join(KIT, "corpus", "pdf-to-text.sh")
    used, done, skipped, failed = set(), 0, 0, []
    for f in todo:
        # A single-file original is reached through the `original` symlink; name
        # the text after the book, not after the link.
        rel = os.path.relpath(f, src) if os.path.isdir(src) else os.path.basename(os.path.realpath(f))
        stem, ext = os.path.splitext(rel)
        dst = os.path.join(out, stem + ".txt")
        if os.path.exists(dst) and os.path.getmtime(dst) >= os.path.getmtime(f) and not a.force:
            skipped += 1
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        ext = ext.lower()
        if ext in (".inf", ".hlp"):
            env = dict(os.environ, INF2TXT_CP=a.cp)
            tmp = dst + ".tmp"
            with open(tmp, "wb") as fh:
                r = subprocess.run([inf2txt, f], stdout=fh, stderr=subprocess.PIPE, env=env)
            ok = r.returncode == 0 and os.path.getsize(tmp) > 0
            if ok:
                os.replace(tmp, dst)
                used.add("inf2txt.sh INF2TXT_CP=%s" % a.cp)
            else:
                os.path.exists(tmp) and os.remove(tmp)
                failed.append("%s: %s" % (rel, r.stderr.decode(errors="replace").strip()[-200:] or "empty output"))
                continue
        else:
            with tempfile.TemporaryDirectory() as td:
                # pdf-to-text.sh names its output after the path it is given, so
                # give it the real file, not the `original` symlink.
                real = os.path.realpath(f)
                r = subprocess.run([pdf2txt, real], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   env=dict(os.environ, OS2DOCS=td))
                produced = os.path.join(td, "pdf_text")
                # It also normalises the name (lowercases it), so take what it
                # wrote - one book in, one full-text .txt out - rather than predict it.
                got = sorted(os.listdir(produced)) if os.path.isdir(produced) else []
                full = [g for g in got if g.endswith(".txt") and not re.search(r"\.p\d+-\d+\.txt$", g)]
                if r.returncode != 0 or len(full) != 1:
                    failed.append("%s: rc=%d, pdf-to-text.sh wrote %s %s" % (
                        rel, r.returncode, got, r.stderr.decode(errors="replace").strip()[-200:]))
                    continue
                stem = os.path.splitext(dst)[0]
                for pf in got:
                    shutil.move(os.path.join(produced, pf), stem + pf[len(os.path.splitext(full[0])[0]):])
                used.add("pdf-to-text.sh")
        done += 1
    if used:
        set_field(Item(it.root, it.category, it.slug), "converter", ", ".join(sorted(used)))
        write_catalog(it.root)
    print("%s: %d converted, %d up to date, %d failed -> %s" % (it.slug, done, skipped, len(failed), out))
    for f in failed:
        print("  FAILED " + f, file=sys.stderr)
    return 1 if failed else 0


def check_items(root):
    problems = []
    def p(where, what):
        problems.append("%s: %s" % (where, what))
    if not os.path.isdir(root):
        p(root, "library root does not exist (os2-lib init)")
        return problems
    for name in sorted(os.listdir(root)):
        full = os.path.join(root, name)
        if os.path.isdir(full) and name not in CATEGORIES + [STATE] and not name.startswith("."):
            p(name, "unknown top-level directory (categories: %s)" % ", ".join(CATEGORIES + [STATE]))
    slugs = {}
    for it in iter_items(root):
        where = "%s/%s" % (it.category, it.slug)
        if it.error:
            p(where, "ITEM.md unreadable: " + it.error)
            continue
        slugs.setdefault(it.slug, []).append(where)
        if not SLUG_RE.match(it.slug):
            p(where, "slug is not lowercase publisher-title[-edition]")
        for k in REQUIRED:
            if it.meta.get(k) in (None, "", []):
                p(where, "missing required field '%s'" % k)
        if it.get("search") and it.get("search") not in SEARCH:
            p(where, "search '%s' is not one of %s" % (it.get("search"), ", ".join(sorted(SEARCH))))
        if it.get("category") and it.get("category") != it.category:
            p(where, "category field says '%s' but the item is filed under %s/" % (it.get("category"), it.category))
        for field, allowed in (("kind", KINDS), ("licence", LICENCES), ("mode", MODES)):
            v = it.get(field)
            if v and v not in allowed:
                p(where, "%s '%s' is not one of %s" % (field, v, ", ".join(sorted(allowed))))
        o = os.path.join(it.dir, "original")
        if os.path.islink(o) and not os.path.exists(o):
            p(where, "original is missing: %s (unmounted disk? moved?)" % os.readlink(o))
        if it.get("mode") in ("link", "convert") and not os.path.lexists(o):
            p(where, "mode %s but no original symlink" % it.get("mode"))
        if it.get("mode") == "import" and not os.path.isdir(os.path.join(it.dir, "files")):
            p(where, "mode import but no files/")
        textdir = os.path.join(it.dir, "text")
        if it.get("mode") in ("convert", "adopt") and not (os.path.isdir(textdir) and os.listdir(textdir)):
            p(where, "mode %s but text/ is empty (unconverted)" % it.get("mode"))
        for k in ("original", "derived_from", "licence", "converter"):
            if it.get(k) == "unknown":
                p(where, "provenance gap: %s is unknown" % k)
        for part, sub in (it.get("paths", {}) or {}).items():
            if not os.path.exists(os.path.join(it.dir, str(sub))):
                p(where, "paths.%s -> %s does not exist" % (part, sub))
        if it.get("part_of") and not any(x.slug == it.get("part_of") for x in iter_items(root)):
            p(where, "part_of '%s' is not an item" % it.get("part_of"))
    for slug, wheres in slugs.items():
        if len(wheres) > 1:
            p(slug, "slug used more than once: " + ", ".join(wheres))
    cat = os.path.join(root, "CATALOG.tsv")
    newest = max([os.path.getmtime(it.file) for it in iter_items(root) if os.path.exists(it.file)] or [0])
    if newest and (not os.path.exists(cat) or os.path.getmtime(cat) < newest):
        p("CATALOG.tsv", "stale (os2-lib catalog)")
    return problems


def cmd_check(a):
    problems = check_items(library_root())
    for pr in problems:
        print(pr)
    print("-- %d problem(s) in %s" % (len(problems), library_root()), file=sys.stderr)
    return min(len(problems), 125)


def write_catalog(root):
    rows = ["slug\tcategory\tkind\tmode\tlicence\tcanonical\tprovides\tpart_of\tcopies\toriginal"]
    for it in iter_items(root):
        if it.error:
            continue
        o = it.original()
        rows.append("\t".join(str(x) for x in (
            it.slug, it.category, it.get("kind", ""), it.get("mode", ""), it.get("licence", ""),
            it.get("canonical", ""), ",".join(map(str, it.provides)), it.get("part_of", ""),
            len(it.get("copies", []) or []), os.path.realpath(o) if o else it.get("original", ""))))
    tmp = os.path.join(root, ".CATALOG.tsv.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(rows) + "\n")
    os.replace(tmp, os.path.join(root, "CATALOG.tsv"))
    return len(rows) - 1


def cmd_catalog(a):
    n = write_catalog(library_root())
    print("CATALOG.tsv: %d item(s)" % n)


# ------------------------------------------------------------------ CLI

def main(argv=None):
    ap = argparse.ArgumentParser(prog="os2-lib", description="The OS/2 library (PATHS.md): find material by role.")
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("root", help="print the library root").set_defaults(fn=cmd_root)
    s = sp.add_parser("init", help="create the library layout")
    s.add_argument("path", nargs="?"); s.add_argument("--save", action="store_true",
                   help="also record PATH as the library root in the config file")
    s.set_defaults(fn=cmd_init)
    s = sp.add_parser("ls", help="list items"); s.add_argument("category", nargs="?", choices=CATEGORIES)
    s.add_argument("--role"); s.set_defaults(fn=cmd_ls)
    sp.add_parser("roles", help="list roles and the items providing them").set_defaults(fn=cmd_roles)
    s = sp.add_parser("role", help="print the path of the item providing ROLE")
    s.add_argument("role"); s.add_argument("part", nargs="?"); s.add_argument("--all", action="store_true")
    s.set_defaults(fn=cmd_role)
    s = sp.add_parser("path", help="print an item's path"); s.add_argument("slug"); s.add_argument("subpath", nargs="?")
    s.set_defaults(fn=cmd_path)
    s = sp.add_parser("grep", help="search the library's text in provenance order")
    s.add_argument("pattern"); s.add_argument("category", nargs="?", choices=CATEGORIES)
    s.add_argument("--role"); s.add_argument("--include-restricted", action="store_true")
    s.add_argument("--max", type=int, default=int(os.environ.get("SEARCH_MAX", "40")))
    for flag in "wFE":
        s.add_argument("-" + flag, action="store_true")
    s.add_argument("-i", action="store_true", help="accepted for habit; case-insensitive is the default")
    s.add_argument("--case", action="store_true", help="case-sensitive (off by default: book text is case-damaged)")
    s.add_argument("-C", "--context", type=int, default=int(os.environ.get("SEARCH_CONTEXT", "0")))
    s.add_argument("--no-os2ref", action="store_true", help="skip this kit's os2ref/")
    s.set_defaults(fn=cmd_grep)
    s = sp.add_parser("new", help="create an item (used by the ingest skill)")
    s.add_argument("category"); s.add_argument("slug")
    s.add_argument("--title", required=True); s.add_argument("--kind", required=True)
    s.add_argument("--licence", required=True); s.add_argument("--mode", required=True)
    s.add_argument("--original"); s.add_argument("--provides"); s.add_argument("--canonical")
    s.add_argument("--part-of"); s.add_argument("--derived-from")
    s.add_argument("--search", help="text | original | both (default both): what grep reads")
    s.add_argument("--part", action="append", metavar="NAME=SUBPATH",
                   help="a useful part inside the item, e.g. headers=original/H (repeatable)")
    s.set_defaults(fn=cmd_new)
    s = sp.add_parser("convert", help="convert an item's INF/HLP/PDF original into text/")
    s.add_argument("slug"); s.add_argument("--cp", default="CP850"); s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_convert)
    sp.add_parser("check", help="report problems; exit = count").set_defaults(fn=cmd_check)
    sp.add_parser("catalog", help="rebuild CATALOG.tsv").set_defaults(fn=cmd_catalog)
    a = ap.parse_args(argv)
    try:
        return a.fn(a) or 0
    except LibError as e:
        print("os2-lib: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
