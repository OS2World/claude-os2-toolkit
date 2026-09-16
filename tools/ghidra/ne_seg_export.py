#!/usr/bin/env python3
"""
ne_seg_export.py - export every segment of an OS/2 NE (New Executable) module
with relocations applied, the NE counterpart of lx_obj_export.py.

OS/2's 16-bit components - installable file system drivers, device drivers,
many system utilities - are NE modules, not LX, so the LX pipeline cannot
touch them: its first step reads an LX object table.  This writes
outdir/segNN_SSSS.bin per segment plus a manifest.json in exactly the shape
make_blocks.py and LoadAllObjects.java already consume, so everything
downstream is the same code the LX pipeline uses.

Addressing convention (deliberately matching the LX pipeline's flat model):
NE logical segment N is placed at pseudo-flat base N << 16, so Ghidra's
"x86:LE:16:Protected Mode" language renders an address as 000N:offset - which
is byte for byte the notation IBM's own .SYM files use for NE modules
("0001:00000600  FS_CLOSE").  No address translation is needed anywhere in the
pipeline, and ne_symva.py relies on exactly this.

Segments are grown to their minimum allocation size before fixups are applied,
so intra-segment BSS references land inside the block instead of off its end.

Imports: an NE relocation naming another module cannot be resolved to a real
address statically - the target is in a DLL that is not being analysed.
Rather than leaving those as garbage far calls, each distinct (module,
ordinal-or-name) pair is given a slot in a synthetic segment at selector
IMPORT_SEL and written to imports.txt, where each slot holds a lone RETF.
ApplySymbols.java then labels each slot, which is what turns an unresolved far
call into a readable named call in the decompiled output.  ne_impnames.py
turns the MODULE_<ordinal> placeholders into real API names.

Usage: ne_seg_export.py <ne-image> <outdir>

Also writes, beside manifest.json:
  imports.txt   "0xVA MODULE_<ordinal-or-name>" per synthetic import stub
  relocs.json   every relocation record, decoded
  header.json   NE header fields, module table, exports and entry table.
                The pipeline reads 'autodata' from it (see SetDataSeg.java).
"""
import argparse
import json
import os
import struct
import sys

# --- NE segment flag bits [DOC-IBM], NE executable-format specification ---
NESDATA    = 0x0001
NESMOVE    = 0x0010
NESPURE    = 0x0020
NESPRELOAD = 0x0040
NESRONLY   = 0x0080
NESRELOC   = 0x0100
NESDEBUG   = 0x0200
NESDISCARD = 0x1000
NES32BIT   = 0x2000

# relocation source (address) types
SRC_LOBYTE     = 0
SRC_SEGMENT    = 2
SRC_FARADDR    = 3     # 16:16
SRC_OFFSET     = 5     # 16
SRC_FARADDR32  = 11    # 16:32
SRC_OFFSET32   = 13

SRC_NAMES = {0: 'LOBYTE', 2: 'SEGMENT', 3: 'FARADDR16_16', 5: 'OFFSET16',
             11: 'FARADDR16_32', 13: 'OFFSET32'}

# relocation target types (low 2 bits of the flags byte)
RT_INTERNAL = 0
RT_IMPORDINAL = 1
RT_IMPNAME = 2
RT_OSFIXUP = 3
RT_NAMES = {0: 'INTERNALREF', 1: 'IMPORTORDINAL', 2: 'IMPORTNAME', 3: 'OSFIXUP'}
RT_ADDITIVE = 0x04

# synthetic selector for the import thunk table, and bytes reserved per slot.
# 0x00F0 is chosen to sit far above any real logical segment number while
# staying inside the 16-bit selector space the pipeline's pseudo-flat
# addressing uses.
IMPORT_SEL = 0x00F0
IMPORT_STUB = 16


def pstr(buf, off):
    """Read a length-prefixed (Pascal) string."""
    if off >= len(buf):
        return '', off
    n = buf[off]
    return buf[off + 1:off + 1 + n].decode('latin1', 'replace'), off + 1 + n


class NEImage:
    def __init__(self, path):
        self.path = path
        with open(path, 'rb') as f:
            self.buf = f.read()
        b = self.buf
        if b[:2] != b'MZ':
            raise ValueError('not an MZ image')
        self.ne_off = struct.unpack_from('<I', b, 0x3c)[0]
        if b[self.ne_off:self.ne_off + 2] != b'NE':
            raise ValueError('not an NE image (found %r)'
                             % b[self.ne_off:self.ne_off + 2])
        h = self.ne_off
        u16 = lambda o: struct.unpack_from('<H', b, h + o)[0]
        u32 = lambda o: struct.unpack_from('<I', b, h + o)[0]
        self.ver         = b[h + 2]
        self.rev         = b[h + 3]
        self.enttab      = u16(0x04)
        self.cbenttab    = u16(0x06)
        self.crc         = u32(0x08)
        self.flags       = u16(0x0c)
        self.autodata    = u16(0x0e)
        self.heap        = u16(0x10)
        self.stack       = u16(0x12)
        self.csip        = u32(0x14)
        self.sssp        = u32(0x18)
        self.cseg        = u16(0x1c)
        self.cmod        = u16(0x1e)
        self.cbnrestab   = u16(0x20)
        self.segtab      = u16(0x22)
        self.rsrctab     = u16(0x24)
        self.restab      = u16(0x26)
        self.modtab      = u16(0x28)
        self.imptab      = u16(0x2a)
        self.nrestab     = u32(0x2c)   # absolute file offset, unlike the rest
        self.cmovent     = u16(0x30)
        self.align       = u16(0x32) or 9
        self.cres        = u16(0x34)
        self.exetyp      = b[h + 0x36]
        self.flagsothers = b[h + 0x37]
        self._read_segtab()
        self._read_modules()
        self._read_names()
        self._read_enttab()

    # ---- segment table ----
    def _read_segtab(self):
        self.segs = []
        base = self.ne_off + self.segtab
        for i in range(self.cseg):
            sector, cb, flags, minalloc = struct.unpack_from('<HHHH', self.buf, base + i * 8)
            size = cb if cb else (0x10000 if sector else 0)
            alloc = minalloc if minalloc else 0x10000
            self.segs.append({
                'num': i + 1,
                'sector': sector,
                'file_off': sector << self.align,
                'file_len': size,
                'flags': flags,
                'minalloc': alloc,
                'is_data': bool(flags & NESDATA),
                'is_32bit': bool(flags & NES32BIT),
                'movable': bool(flags & NESMOVE),
                'has_reloc': bool(flags & NESRELOC),
            })

    # ---- module reference table -> imported names table ----
    def _read_modules(self):
        self.modules = []
        base = self.ne_off + self.modtab
        for i in range(self.cmod):
            noff = struct.unpack_from('<H', self.buf, base + i * 2)[0]
            name, _ = pstr(self.buf, self.ne_off + self.imptab + noff)
            self.modules.append(name)

    def imported_name(self, name_off):
        s, _ = pstr(self.buf, self.ne_off + self.imptab + name_off)
        return s

    # ---- resident / non-resident name tables (this module's own exports) ----
    def _read_names(self):
        self.modname = '?'
        self.description = ''
        self.resident = []
        off = self.ne_off + self.restab
        first = True   # the first resident entry is the module name itself
        while off < len(self.buf):
            if self.buf[off] == 0:
                break
            s, off = pstr(self.buf, off)
            ordn = struct.unpack_from('<H', self.buf, off)[0]
            off += 2
            if first:
                self.modname = s
                first = False
            else:
                self.resident.append((ordn, s))
        self.nonresident = []
        off = self.nrestab
        first = True   # the first non-resident entry is the module description
        while off < len(self.buf):
            if self.buf[off] == 0:
                break
            s, off = pstr(self.buf, off)
            ordn = struct.unpack_from('<H', self.buf, off)[0]
            off += 2
            if first:
                self.description = s
                first = False
            else:
                self.nonresident.append((ordn, s))

    # ---- entry table (needed to resolve movable-segment internal refs) ----
    def _read_enttab(self):
        """Entry table: bundles of entries.  Fills {ordinal: (seg, off)}."""
        self.entries = {}
        off = self.ne_off + self.enttab
        end = off + self.cbenttab
        ordn = 1
        while off < end:
            cnt = self.buf[off]
            if cnt == 0:
                off += 1
                break
            seg_ind = self.buf[off + 1]
            off += 2
            if seg_ind == 0:            # unused bundle: skip `cnt` ordinals
                ordn += cnt
                continue
            for _ in range(cnt):
                if seg_ind == 0xFF:     # movable-segment entry
                    # flags(1) int3f(2) seg(1) offset(2)
                    seg = self.buf[off + 3]
                    o = struct.unpack_from('<H', self.buf, off + 4)[0]
                    off += 6
                else:                   # fixed-segment entry
                    o = struct.unpack_from('<H', self.buf, off + 1)[0]
                    seg = seg_ind
                    off += 3
                self.entries[ordn] = (seg, o)
                ordn += 1

    # ---- relocations ----
    def relocations(self, seg):
        """Relocation records for a segment, as decoded dicts."""
        if not seg['has_reloc']:
            return []
        p = seg['file_off'] + seg['file_len']
        n = struct.unpack_from('<H', self.buf, p)[0]
        p += 2
        out = []
        for _ in range(n):
            src, flags, srcoff, t1, t2 = struct.unpack_from('<BBHHH', self.buf, p)
            p += 8
            out.append({'src': src, 'flags': flags, 'srcoff': srcoff,
                        'rtype': flags & 3, 'additive': bool(flags & RT_ADDITIVE),
                        't1': t1, 't2': t2})
        return out


def export(path, outdir):
    ne = NEImage(path)
    os.makedirs(outdir, exist_ok=True)

    # ---- pass 1: collect distinct imports, so stub addresses can be assigned ----
    import_slots = {}     # (modname, ordinal-or-name) -> flat address
    next_slot = (IMPORT_SEL << 16)
    for seg in ne.segs:
        for r in ne.relocations(seg):
            if r['rtype'] == RT_IMPORDINAL:
                key = (ne.modules[r['t1'] - 1], r['t2'])
            elif r['rtype'] == RT_IMPNAME:
                key = (ne.modules[r['t1'] - 1], ne.imported_name(r['t2']))
            else:
                continue
            if key not in import_slots:
                import_slots[key] = next_slot
                next_slot += IMPORT_STUB

    # ---- pass 2: emit segment bytes with fixups applied ----
    manifest = []
    relocs_dump = []
    for seg in ne.segs:
        n = seg['num']
        base = n << 16
        if seg['file_off'] and seg['file_len']:
            data = bytearray(ne.buf[seg['file_off']:seg['file_off'] + seg['file_len']])
        else:
            data = bytearray()
        if len(data) < seg['minalloc']:
            data.extend(b'\0' * (seg['minalloc'] - len(data)))

        applied = unresolved = 0
        for r in ne.relocations(seg):
            tsel = toff = None
            label = None
            if r['rtype'] == RT_INTERNAL:
                tseg, tofs = r['t1'] & 0xFF, r['t2']
                if tseg == 0xFF:                     # movable: t2 is an ordinal
                    ent = ne.entries.get(tofs)
                    if ent:
                        tseg, tofs = ent
                    else:
                        tseg = None
                if tseg:
                    tsel, toff = tseg, tofs
                    label = 'seg%d:%04x' % (tseg, tofs)
            elif r['rtype'] == RT_IMPORDINAL:
                mod = ne.modules[r['t1'] - 1]
                addr = import_slots[(mod, r['t2'])]
                tsel, toff = addr >> 16, addr & 0xFFFF
                label = '%s.#%d' % (mod, r['t2'])
            elif r['rtype'] == RT_IMPNAME:
                mod = ne.modules[r['t1'] - 1]
                nm = ne.imported_name(r['t2'])
                addr = import_slots[(mod, nm)]
                tsel, toff = addr >> 16, addr & 0xFFFF
                label = '%s.%s' % (mod, nm)

            # Walk the fixup chain.  In a non-additive record the slot holds
            # the offset of the NEXT site needing the same target, ending at
            # 0xFFFF; an additive record is applied once.  The guard counter
            # bounds a corrupt or self-referential chain.
            off = r['srcoff']
            guard = 0
            while True:
                guard += 1
                if guard > 4096:
                    break
                if off + 1 >= len(data) or off == 0xFFFF:
                    break
                nxt = struct.unpack_from('<H', data, off)[0] if off + 2 <= len(data) else 0xFFFF
                if tsel is None:
                    unresolved += 1
                else:
                    if r['src'] == SRC_SEGMENT:
                        struct.pack_into('<H', data, off, tsel)
                    elif r['src'] == SRC_OFFSET:
                        struct.pack_into('<H', data, off, toff)
                    elif r['src'] == SRC_FARADDR:
                        if off + 4 <= len(data):
                            struct.pack_into('<HH', data, off, toff, tsel)
                    elif r['src'] == SRC_LOBYTE:
                        data[off] = toff & 0xFF
                    elif r['src'] == SRC_OFFSET32:
                        if off + 4 <= len(data):
                            struct.pack_into('<I', data, off, toff)
                    elif r['src'] == SRC_FARADDR32:
                        if off + 6 <= len(data):
                            struct.pack_into('<IH', data, off, toff, tsel)
                    applied += 1
                relocs_dump.append({
                    'seg': n, 'off': off, 'src': SRC_NAMES.get(r['src'], str(r['src'])),
                    'type': RT_NAMES[r['rtype']], 'additive': r['additive'],
                    'target': label,
                })
                if r['additive']:
                    break
                if nxt == 0xFFFF or nxt == off:
                    break
                off = nxt

        fn = os.path.join(outdir, 'seg%02d_%04x.bin' % (n, n))
        with open(fn, 'wb') as f:
            f.write(data)
        manifest.append({
            'num': n, 'base': base, 'size': len(data),
            'bits': 32 if seg['is_32bit'] else 16,
            'perm': ('RW-' if seg['is_data'] else 'R-X'),
            'exec': not seg['is_data'],
            'file': os.path.abspath(fn),
            'flags': seg['flags'], 'movable': seg['movable'],
            'file_off': seg['file_off'], 'file_len': seg['file_len'],
            'reloc_applied': applied, 'reloc_unresolved': unresolved,
        })

    # synthetic import segment: one RETF per slot
    if import_slots:
        size = len(import_slots) * IMPORT_STUB
        fn = os.path.join(outdir, 'seg_imports_%04x.bin' % IMPORT_SEL)
        with open(fn, 'wb') as f:
            f.write(b'\xcb' * size)
        manifest.append({
            'num': 200, 'base': IMPORT_SEL << 16, 'size': size, 'bits': 16,
            'perm': 'R-X', 'exec': True, 'file': os.path.abspath(fn),
            'flags': 0, 'movable': False, 'synthetic': 'imports',
            'file_off': 0, 'file_len': size,
            'reloc_applied': 0, 'reloc_unresolved': 0,
        })

    with open(os.path.join(outdir, 'manifest.json'), 'w') as f:
        json.dump(manifest, f, indent=1)
    with open(os.path.join(outdir, 'imports.txt'), 'w') as f:
        for (mod, what), addr in sorted(import_slots.items(), key=lambda kv: kv[1]):
            nm = ('%s_%s' % (mod, what)) if isinstance(what, str) else ('%s_%d' % (mod, what))
            f.write('0x%08x %s\n' % (addr, nm))
    with open(os.path.join(outdir, 'relocs.json'), 'w') as f:
        json.dump(relocs_dump, f, indent=1)
    with open(os.path.join(outdir, 'header.json'), 'w') as f:
        json.dump({
            'module': ne.modname, 'description': ne.description,
            'ne_off': ne.ne_off, 'ver': '%d.%d' % (ne.ver, ne.rev),
            'flags': ne.flags, 'cseg': ne.cseg, 'align': ne.align,
            'autodata': ne.autodata, 'heap': ne.heap, 'stack': ne.stack,
            'csip': ne.csip, 'sssp': ne.sssp,
            'modules': ne.modules,
            'exports_resident': ne.resident,
            'exports_nonresident': ne.nonresident,
            'entries': {str(k): v for k, v in ne.entries.items()},
        }, f, indent=1)

    print('module %s (%s)' % (ne.modname, ne.description))
    print('%d segments, %d modules imported, %d distinct imports'
          % (len(ne.segs), len(ne.modules), len(import_slots)))
    for m in manifest:
        print('  seg %3d @ %04x:0000 size=0x%-5x %s %s fixups=%d%s'
              % (m['num'], m['base'] >> 16, m['size'], m['perm'],
                 'CODE' if m['exec'] else 'DATA', m['reloc_applied'],
                 '  UNRESOLVED=%d' % m['reloc_unresolved'] if m['reloc_unresolved'] else ''))
    return ne, manifest


def main():
    ap = argparse.ArgumentParser(
        description="Export every NE segment with relocations applied, plus a "
                    "manifest.json for the Ghidra pipeline.")
    ap.add_argument("neimage", help="the NE module (.IFS, .SYS, .DLL, .EXE)")
    ap.add_argument("outdir", help="directory to write segNN_SSSS.bin and manifest.json into")
    args = ap.parse_args()
    try:
        export(args.neimage, args.outdir)
    except (OSError, ValueError, struct.error) as e:
        sys.exit("%s: %s" % (args.neimage, e))


if __name__ == '__main__':
    main()
