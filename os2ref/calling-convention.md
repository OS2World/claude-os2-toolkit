# OS/2 API Linkage and Calling Conventions

How an OS/2 program links to and calls the system API: the 32-bit `_System` convention every
`Dos*`/`Win*`/`Gpi*` entry point uses (register volatility, stack cleanup, the `APIRET` return),
how the `EXPENTRY` callback linkage and the 16-bit `_Far16 _Pascal` convention differ from it, and
how a module resolves those calls at link time - by ordinal or by name - through a module-definition
(`.DEF`) file. The 16<->32 thunking machinery that bridges the 32-bit and 16-bit conventions is
described in `thunking.md`; this reference covers the conventions themselves and points there.

Provenance: **[DOC-IBM]** the OS/2 Toolkit headers `os2def.h`, `bsedos.h`, `pmwin.h` (the linkage
macros, the `APIRET` types, the API prototypes) and the Toolkit sample `.DEF` files (the module
definition syntax); **[DOC]** the published x86 "System/syscall" and "Pascal" convention definitions
(register/stack semantics); **[OBS-RE]** the real DOSCALL1/kernel register-preservation behaviour
(cross-referenced to `thunking.md`).

## The two linkage keywords [DOC-IBM]

`os2def.h` defines the API linkage macros. Every OS/2 API is declared with one of these; the macro
selects the compiler's calling convention for that entry point:

| Macro | Expands to | Used for | Width |
|---|---|---|---|
| `APIENTRY` | `_System` | 32-bit API entry points (`DosOpen`, `WinCreateStdWindow`, ...) | 32-bit |
| `EXPENTRY` | `_System` | 32-bit exported callbacks (window procedures, hooks) | 32-bit |
| `APIENTRY16` | `_Far16 _Pascal` | 16-bit API entry points | 16-bit |
| `PASCAL16` | `_Far16 _Pascal` | 16-bit far-Pascal entry points | 16-bit |
| `CDECL16` | `_Far16 _Cdecl` | 16-bit far-C entry points | 16-bit |

Source: `os2def.h:45-50`. Note that `APIENTRY` and `EXPENTRY` are the **same** underlying convention
(`_System`); the distinction is documentary (see "EXPENTRY vs APIENTRY" below), not a difference in
ABI. `FAR` and `NEAR` expand to nothing in the 32-bit (flat) headers (`os2def.h:42-43`).

## The `_System` (32-bit) convention [DOC / OBS-RE]

`_System` (also called the "System" or "syscall" convention) is the standard linkage for the 32-bit
OS/2 API. Its rules:

| Aspect | Rule | Source |
|---|---|---|
| Argument passing | All arguments on the stack, pushed **right-to-left** | [DOC] |
| Stack cleanup | **Caller** removes the arguments after the call returns | [DOC] |
| Return value | `EAX` (an `APIRET`, i.e. `unsigned long`) | type [DOC-IBM] `os2def.h:55`; `EAX` placement [DOC] |
| Volatile (not preserved) | `EAX`, `ECX`, `EDX` | [DOC] |
| Preserved (callee-saved) | `EBX`, `ESI`, `EDI`, `EBP` | [DOC] |

Because arguments are all stack-passed and the **caller** cleans the stack, an OS/2 API can be called
with a variable-shaped frame and the compiler emits the pop on the caller side; a `_System` callee
returns with a plain `ret` (it does not itself remove the arguments). This is the opposite of the
16-bit Pascal convention below, where the callee cleans.

> **Observed refinement [OBS-RE].** The documented convention marks `EAX`, `ECX`, and `EDX` as
> volatile, but the **real** OS/2 kernel / DOSCALLS preserve `ECX` and `EDX` across the API call, and
> callers in the shipped system depend on it. Only `EAX` (the return value) is genuinely clobbered.
> Where the documentation and the shipped binary disagree, the binary is authoritative for behaviour.
> Detail and the thunk that honours it are in `thunking.md` (section "The register-preservation contract").

> **Argument-count note [DOC / unverified vs IBM].** The published "syscall" description also states
> that the size of the parameter list, in doublewords, is passed in `AL`. This detail is not confirmed
> from an IBM primary source and is noted for completeness only.

## The `APIRET` return type [DOC-IBM]

Most `Dos*` APIs return an `APIRET` - zero on success, a non-zero `ERROR_*` code otherwise. The three
width variants are defined in `os2def.h`:

| Type | Definition | Width | Source |
|---|---|---|---|
| `APIRET` | `unsigned long` | 32-bit | `os2def.h:55` |
| `APIRET16` | `unsigned short` | 16-bit (the 16-bit API return) | `os2def.h:56` |
| `APIRET32` | `unsigned long` | 32-bit (explicit alias) | `os2def.h:57` |

A few APIs do not return a code and are declared `VOID` - e.g. `VOID APIENTRY DosExit(ULONG action,
ULONG result)` (`bsedos.h:101`), which never returns to the caller. Presentation Manager APIs commonly
return other types (a `BOOL`, an `HWND`, an `HPS`, an `MRESULT`) rather than an `APIRET`; the linkage
(`APIENTRY`/`EXPENTRY` = `_System`) is unchanged.

## `EXPENTRY` vs `APIENTRY` [DOC-IBM]

`EXPENTRY` and `APIENTRY` both expand to `_System` (`os2def.h:45-46`), so they are identical at the
ABI level. The convention is which direction the call crosses the application/system boundary:

- **`APIENTRY`** marks a routine the application **calls** - an API the system exports.
- **`EXPENTRY`** marks a routine the application **exports** for the system to call back - most
  importantly a **window procedure**. The window-procedure type is
  `typedef MRESULT (EXPENTRY FNWP)(HWND, ULONG, MPARAM, MPARAM);` with `PFNWP` its pointer form
  (`pmwin.h:223-224`). A window procedure receives `(HWND, message, MPARAM mp1, MPARAM mp2)` and
  returns an `MRESULT`; `MPARAM` and `MRESULT` are both `VOID *` (`os2def.h:591-593`).

Because both are `_System`, a callback registered with the system (e.g. via `WinRegisterClass`) is
called with the same register/stack rules as any API.

## The 16-bit far-Pascal convention, at a glance [DOC-IBM / DOC]

The 16-bit API linkage is `APIENTRY16` / `PASCAL16` = `_Far16 _Pascal` (`os2def.h:48-49`). Two things
combine here:

- **`_Far16`** - the call is a **far** (16:16 segmented) call, and pointer parameters are 16:16 far
  pointers, not 32-bit flat pointers. `os2def.h` uses the related `_Seg16` qualifier for 16-bit
  pointer typedefs, e.g. `typedef UCHAR * _Seg16 PUCHAR16;` (`os2def.h:99-100`). [DOC-IBM]
- **`_Pascal`** - the Pascal convention: arguments are pushed **left-to-right**, the **callee** removes
  them from the stack (a far `ret n`), and an ordinal result is returned in `AL`/`AX` (8-/16-bit) or
  `DX:AX` (32-bit value on a 16-bit system). [DOC] The 16-bit API return type is `APIRET16`
  (`os2def.h:56`).

This is the mirror image of `_System` on both axes that matter: **left-to-right** vs right-to-left
argument order, and **callee-cleans** vs caller-cleans. That mismatch - plus the 16:16-vs-flat pointer
difference - is exactly why a call cannot cross the 16/32 boundary directly.

### Where the callee-pop count `n` is recoverable from [OBS-RE]

Because the callee cleans up, every 16-bit API entry point has one correct argument-byte count
baked into it, and getting it wrong strands the caller's arguments on its stack. **The kernel
states that count per ordinal, in its own entry stub.** Each public 16-bit DOSCALLS entry point
in `OS2KRNL` is a stub whose entire body is a call to the shared syscall prologue with this
entry's byte count as the sole argument - rendered `pre_sci(N)` by a decompiler, e.g.
`DOSMKDIR` -> `pre_sci(8)`, `DOSMKDIR2` -> `pre_sci(0xc)`, `DOSOPEN` -> `pre_sci(0x1a)`. `N` is the
`RETF` immediate the entry returns with, and it equals the sum of the parameter widths in the
16-bit prototype (`DosOpen`: 4+4+4+4+2+2+2+4 = 26 = `0x1a`).

Four properties worth knowing before relying on it:

- **It is stable across kernel builds; the address is not.** `DOSMKDIR` is `pre_sci(8)`,
  `DOSMKDIR2` is `pre_sci(0xc)` and `DOSOPEN` is `pre_sci(0x1a)` in the SMP and UNI kernels alike
  and in both their base and debug variants - while the *object* the stub lives in differs
  between them (`000f:` on UNI, `0010:` on SMP). The count is an ABI fact; the address is a build
  fact.
- **The count is a PUSH, and the push is authoritative however the body renders.** The stub
  really is `push <argbytes>` / `call <prologue>`. Where a decompiler recognises the pair it
  prints `pre_sci(0xc)`; where it inlines the prologue instead it prints a bare `pre_sci()` with
  the value a few lines above as a stack store (`*(undefined2 *)(sp + -2) = 0xc;`). Same value,
  two renderings of one instruction sequence - read the push, not the argument list.

  **This is safe by construction, not by sampling, and `pre_sci`'s own code is why.** `pre_sci`
  reads the pushed value at `[esp+0xa]`, rounds it up to a multiple of 4, and uses it to index a
  table - **and uses it for nothing else**. The table's entries are IBM's own named return stubs
  `SCIReturn0`, `SCIReturn2`, ... `SCIReturn36`, each `popfd; retfd <N>`, with
  `table[count] == SCIReturn<count>` exactly (plus a compensating `sub ...,2` so the net pop equals
  the un-rounded count). **IBM's naming states the semantic: the pushed argument selects the
  return stub, so the pushed argument IS the callee-pop count.** A body's shape cannot change
  that, so an unrecognised rendering is a decompiler artifact with no bearing on the contract.
  Measured at scale: 189 named kernel entries per debug image open `push imm; call (mp)pre_sci`,
  and raw bytes agree with the decompile's first value 189 of 189 times. **[OBS-RE.]**

  **The two renderings coexist inside one image, function by function** - the debug-SMP image
  renders `DOSMKDIR2`, `DOSMAKENMPIPE` and `DOSQNMPHANDSTATE` inlined while rendering `DOSIOPENL`
  in that same image as a plain `pre_sci(0x24)`. So there is no image to trust wholesale and none
  to discard; check the shape at each symbol, take the push, and move on.
- **The SMP 16-bit stubs call `mppre_sci`**, not `pre_sci`, in raw disassembly. It is the same
  declaration under an MP-specific name - **measured, not assumed**: the two are byte-identical
  through the argument prologue (same table, same rounding) and diverge only after the argument
  has been consumed, and 26 entries that call `mppre_sci` on SMP call `pre_sci` on UNI with
  identical immediates. **[OBS-RE.]**
- **Not every entry is a single-statement stub** - but where such an entry still opens
  `push imm; call (mp)pre_sci`, that immediate is still the count, for the `SCIReturn` reason
  above. What genuinely falls outside this rule is an entry that does not route through the
  shared prologue at all: those validate arguments and call the worker directly, and have no
  argument-byte declaration to read. Distinguish the two by whether the prologue is called, not
  by how many statements the body decompiles to.

**`OS2KRNL` is not the only home.** The session-manager family (`DOSSMSWITCH`,
`DOSSTOPSESSION`, `DOSSELECTSESSION` and their siblings) lives in `DOSCALL1.DLL`, which has no
`pre_sci` stubs at all; there the count is read directly off the entry's own `retf n` - e.g.
`DOSSTOPSESSION` (obj3+0x97d6) ends `retf 0x8` at `DOSSTOPSESSION_POSTDT` (obj3+0x987d), matching
`USHORT DosStopSession(USHORT, USHORT, ULONG)` = 2+2+4. Scanning for a `0xCB` byte to find that
`retf` is unreliable - the same byte occurs inside earlier instructions - so the entry must be
disassembled from its published start, not searched for.

Two more `DOSCALL1.DLL`-resident blocks read the same way, and they show the two shapes that turn
up there. The **16-bit named-pipe family** `#399`-`#412` is fourteen thin argument-forwarding
shims - `enter 0,0`, re-push the caller's words, one far call, `leave`, `retf n` - whose
immediates run `0x14, 0xa, 0x2, 0x2, 0x6, 0x4, 0x14, 0x8, 0x12, 0x18, 0xc, 0xc, 0x8, 0xa`, each
equal to the sum of its 16-bit prototype's parameter widths. `DOSCLOSEMESSAGEFILE` (obj3+0x6f00,
the target of `MSG.DLL` ordinal 9) is the degenerate case: it ends in a **bare `retf`** - opcode
`0xCB`, no immediate - so its count is **0**, corroborated by a decompiled signature taking no
parameters. A bare `retf` is a real answer, not a failed read; do not go looking for a missing
immediate.

#### The CALLER states it too, in a 32->16 universal-thunk slot [DOC-IBM / OBS-RE]

Everything above reads the count off the **callee**. There is an independent **caller-side**
statement of the same number, and where both exist they must agree - the callee's `retf n` pops
exactly what the caller pushed, so a disagreement is a real defect rather than a matter of taste.

A 32-bit module that calls a 16-bit entry through the universal thunk emits a small trampoline
slot per target. IBM's own `UniThunk3216` macro generates it, and states the encoding exactly
(`thk2asm`'s `systhunk.inc`, Developer Connection). The lines below are IBM's, including the one
comment, with one elision: in the source `sub ecx,ecx` sits inside an `ifb <hTypes>` conditional,
and `mov ecx,&hTypes` is emitted in its place when a high half is supplied.

```
DB      0B8h                ;mov eax,imm32
DW      OFFSET &c2
DW      SEG    &c2
@@:     mov     edx,&lTypes
        sub     ecx,ecx
        jmp     THK32_UNITHUNK
```

The `mov eax,imm32` operand is the 16:16 target - offset half then selector half - which is why a
module's LX import fixups for that target land at slot+1 and slot+3.

`lTypes` (with `hTypes`, forming one 64-bit value consumed LSB-first) is the **parameter-list
descriptor**: a count nibble followed by a per-parameter tag - DWORD, WORD, or pointer with a
size class - so summing the pushed widths it describes yields the callee's frame size in bytes.
The grammar itself is documented in `thunking.md`; the point here is only that the number is
recoverable from the caller.

Worked instance, `[OBS-RE]`, from the shipped Warp 4.50 binaries. `PMMERGE.DLL` obj4+0x2104 is
such a slot, its `mov eax,imm32` operand carrying the two LX import fixups (`stype=5` offset at
+1, `stype=2` selector at +3) that name `DOSCALLS.575`:

```
B8 00 00 00 00      mov eax,<16:16 DOSCALLS.575>
BA 44 EF 00 00      mov edx,0EF44h            ; lTypes
2B C9               sub ecx,ecx               ; hTypes = 0
```

`0EF44h` decodes as count=4 - DWORD, pointer, pointer, DWORD - = 16 bytes, and the callee,
`DOSPMMUXSEMWAIT` at `DOSCALL1.DLL` obj3+0x02f4, ends `retf 0x10`. The two sides agree.

**The control.** That object carries 1838 `DOSCALLS` fixup records over 128 distinct ordinals, but
only **thirteen** of them are `stype=2` selector halves - i.e. thirteen trampoline slots. Decoding
all thirteen descriptors yields a frame size for each, and for the **nine** whose callee is
resident in `DOSCALL1.DLL` the callee's own `retf` immediate is recoverable as well. All nine
agree:

| ordinal | callee | descriptor decodes to | callee `retf` |
|---|---|---|---|
| 140 | obj3+0x00a0 | 8 | 8 |
| 141 | obj3+0x00f5 | 4 | 4 |
| 143 | obj3+0x0190 | 4 | 4 |
| 575 | obj3+0x02f4 | **16** | **16** |
| 790 | obj4+0x3b2d | 6 | 6 |
| 791 | obj4+0x3b4e | 6 | 6 |
| 814 | obj4+0x3e15 | 8 | 8 |
| 817 | obj4+0x3e36 | 6 | 6 |
| 819 | obj4+0x3e59 | 6 | 6 |

The remaining four slots - ordinals 8, 22, 101 and 160 - are answered by the kernel rather than by
`DOSCALL1.DLL`, so that file holds no `retf` for them and the caller-side descriptor is the only
statement of their frame size available from these two binaries. The reading is therefore
controlled rather than fitted to one case.

**Two cautions.** The descriptor is an **instruction immediate**, so it is invisible to any text
search of sources, symbol tables or documentation - it is found only by disassembling the slot.

And **the slot shape varies, so the operand is not at a fixed displacement from the fixup.** The
same macro emits a second form, and IBM's source is explicit about it - the `@@:` label sits on
the `mov edx`, not at the top of the slot, precisely so that later slots can jump back to it:

```
        ifidn   <lTypes>,<shared>
            jmp     @B
        else
@@:         mov     edx,&lTypes
            ...
            jmp     THK32_UNITHUNK
        endif
```

So when the author writes the literal token `shared` in place of a descriptor, the slot gets no
`mov edx`/`sub ecx` at all: just the `mov eax,imm32` and a two-byte jump to the nearest preceding
`@@:`, i.e. to the descriptor of the last slot that spelled one out. Ordinals 791, 817 and 819 in
the table above are all of that form, all three chaining back to ordinal 790's:

```
B8 00 00 00 00      mov eax,<16:16 DOSCALLS.791>
EB EA               jmp short  -> the mov edx,15D2h inside ordinal 790's slot
90                  pad
```

Read a doubleword where the inline form keeps `lTypes` and you get the jump displacement, the pad
and the next slot's `B8` opcode - a number with no meaning. **Follow the jump.** Matching only the
inline shape and discarding the rest is the other failure: it would drop three of these thirteen
slots as "not trampolines" when they are, and lose two thirds of the control above.

## Why 16<->32 thunking exists -> `thunking.md`

Because the 32-bit (`_System`, flat) and 16-bit (`_Far16 _Pascal`, segmented) conventions differ in
argument order, stack-cleanup responsibility, stack width, and pointer format, every call that crosses
the boundary must be adapted: convert 16:16 <-> flat pointers, rebuild the argument frame in the target's
order, switch stacks, and perform the ring/selector transition. That adaptation is the **thunk**.
`thunking.md` documents the thunk mechanism (the universal thunk, the control-word grammar, the stack
switch, and the register-preservation contract). This reference does not duplicate it.

## Selected API prototypes [DOC-IBM]

Concrete `_System` (`APIENTRY`) prototypes, transcribed from the Toolkit headers, to show the shape:

| Prototype | Source |
|---|---|
| `APIRET APIENTRY DosOpen(PCSZ pszFileName, PHFILE pHf, PULONG pulAction, ULONG cbFile, ULONG ulAttribute, ULONG fsOpenFlags, ULONG fsOpenMode, PEAOP2 peaop2);` | `bsedos.h:1255-1262` |
| `APIRET APIENTRY DosRead(HFILE hFile, PVOID pBuffer, ULONG cbRead, PULONG pcbActual);` | `bsedos.h:1345` |
| `APIRET APIENTRY DosWrite(HFILE hFile, ...);` | `bsedos.h:1356` |
| `APIRET APIENTRY DosClose(HFILE hFile);` | `bsedos.h:1340` |
| `APIRET APIENTRY DosAllocMem(PPVOID ppb, ...);` | `bsedos.h:1849` |
| `VOID APIENTRY DosExit(ULONG action, ULONG result);` | `bsedos.h:101` |
| `HWND APIENTRY WinCreateStdWindow(HWND hwndParent, ULONG flStyle, PULONG pflCreateFlags, PCSZ pszClientClass, PCSZ pszTitle, ULONG styleClient, HMODULE hmod, ULONG idResources, PHWND phwndClient);` | `pmwin.h:2762-2770` |

Handle types are defined in `os2def.h`: `HFILE` is `LHANDLE` (`unsigned long`) with `PHFILE` its
pointer (`os2def.h:235-236`); function-pointer types `PFN`/`NPFN` are `APIENTRY`-linkage pointers
(`os2def.h:111-114`).

## Ordinal vs by-name imports, and the `.DEF` module-definition file [DOC-IBM]

An executable or DLL resolves each imported API to a specific export of a specific module. An export
can be referenced two ways:

- **By ordinal** - a small integer assigned to the export by the providing module. The import binds to
  "export number *N* of module *M*". This is the compact, position-stable form and is how the core
  system DLLs (DOSCALLS, PMWIN, ...) are imported.
- **By name** - the import binds to a named export of module *M*, resolved by string match.

Both the exports a module provides and the imports it requires are declared in a **module-definition
file** (`.DEF`) that the linker consumes. The relevant statements (all transcribed from Toolkit sample
`.DEF` files):

| Statement | Meaning | Example (source) |
|---|---|---|
| `LIBRARY <name>` | This module is a DLL named `<name>` | `LIBRARY DLLIB` (`SAMPLES/OS2/DLLAPI/dllib.def`) |
| `NAME <name> [type]` | This module is a program; `type` e.g. `WINDOWAPI`, `WINDOWCOMPAT` | `NAME DLLAPI WINDOWAPI` (`SAMPLES/OS2/DLLAPI/dllapi.def`) |
| `EXPORTS` | Names (and optional ordinals) this module makes callable | see below |
| `IMPORTS` | Names this module imports from other modules | see below |
| `DATA` / `CODE` | Segment attributes (`MULTIPLE READWRITE`, `LOADONCALL`, ...) | `DATA MULTIPLE READWRITE LOADONCALL` (`dllib.def`) |
| `STACKSIZE` / `HEAPSIZE` | Stack / local-heap size in bytes | `STACKSIZE 8192` (`SAMPLES/MM/DIVE/show.def`) |
| `PROTMODE` | Protected-mode-only module | `PROTMODE` (`dllib.def`) |
| `DESCRIPTION '...'` | Text stamped into the module | `DESCRIPTION 'DLL Sample ...'` (`dllib.def`) |

### EXPORTS - assigning ordinals [DOC-IBM]

An `EXPORTS` entry names an exported symbol and may pin it to an explicit ordinal with `@N`:

```
EXPORTS     SearchFile    @1
            ReadFileProc  @2
            CalCulProc    @3
```

(`SAMPLES/OS2/DLLAPI/dllib.def`.) An export may also alias an external (exported) name to a different
internal name with `exportedname=internalname`:

```
EXPORTS
    _S_GETHOSTBYNAME=_s_gethostbyname
    _s_gethostbyname                          @1
```

(`SAMPLES/TCPIPTK/SAMPDLL/sampdllb.def`.)

### IMPORTS - by ordinal or by name [DOC-IBM]

An `IMPORTS` entry names the local symbol and the module it comes from. Referencing the module export
by **ordinal** uses `MODULE.N`; by **name** uses `MODULE.EXPORTNAME`:

```
IMPORTS     SearchFile   = DLLIB.1        ; by ordinal - export #1 of DLLIB
            ReadFileProc = DLLIB.2
            CalCulProc   = DLLIB.3
```

(`SAMPLES/OS2/DLLAPI/dllapi.def` - the importer side of the `dllib.def` exports above.)

```
IMPORTS
    ftpget    = FTPAPI.FTPGET              ; by name - export "FTPGET" of FTPAPI
    ftpput    = FTPAPI.FTPPUT
```

(`SAMPLES/TCPIPTK/RCOPY/rcopyb.def`.) A shorter form omits the local-name alias and imports the
export directly, e.g. `IMPORTS CAP.ccInitialize` (`SAMPLES/MM/CAPSAMP/capsamp.def`).

The calling convention (`_System` for 32-bit, `_Far16 _Pascal` for 16-bit) is a property of the
declared prototype, independent of whether the import was resolved by ordinal or by name - the resolved
target is the same code either way.
