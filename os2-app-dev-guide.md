# OS/2 Application Development Guide (for Claude)

The working guide for building an OS/2 application with this kit: the disciplines that keep the code
correct, and the build -> inspect -> test loop. The `setup` skill bootstraps a project; this is the
reference you return to while working. It assumes the reference lives at `os2ref/`, and the tools
(sources in `tools/`) are on `PATH` via the plugin's `bin/`.

## The disciplines (why this kit exists)

OS/2 was frozen by IBM decades ago; its API contracts are **facts to be looked up, not designed**.
The model is not trained on them, so:

1. **Never originate an ABI fact.** Prototype, constant, struct offset, ordinal, error code - if you
   "know" it, that is training, not knowledge, and it is unfalsifiable. Find it in `os2ref/`
   (route via `os2ref/README.md`), then, if you have the Toolkit headers, *verify* it and cite
   `file:line`. If you cannot source it, say so - never supply a plausible value.
2. **Conventions are facts too - and they fail silently.** Rule 1 is scoped to *symbols*, so it does
   not fire on the things that have no symbol to grep: which way an axis runs, which edges of a
   rectangle are inclusive, what code page a string is in, who owns a handle and when it dies, what
   unit a number carries. These are the *most* dangerous gaps, because a wrong constant raises an
   error while a wrong convention just renders upside down, in the wrong glyphs, or against a freed
   handle. Worked examples, each a real trap: PM's origin is **bottom-left** with y increasing
   upward, inverted from Win32/X11 (`os2ref/gpi-drawing.md`); a `RECTL` includes its left/bottom
   edges and excludes right/top; a PM process has **three** independent code pages - process, message
   queue, and GPI (`os2ref/unicode-conversion.md` section 9.1); only *cache* presentation spaces may be
   passed to `WinReleasePS`, and the handle is dead afterwards. When porting, never assume the source
   platform's convention carries over - look it up exactly as you would a prototype.
3. **An empty result is a fact about your probe, not about the world.** This is the most reliably
   repeated mistake in this kit's history, so treat it as a hard rule rather than advice. A tool that
   returns nothing is *usually* telling you the invocation was wrong - wrong path, wrong flag, wrong
   name, wrong file, unreadable encoding - and almost never that the thing does not exist. Reading
   silence as absence is how a session concludes "IBM doesn't document this" or "that isn't
   installed" and then invents a replacement.

   **The rule: when a probe comes back empty, prove the probe works on a case you know is positive
   *before* you believe the negative.** `command -v gcc` next to `command -v g++` settles in one
   second what an hour of reasoning will get wrong.

   Every row below actually happened, each one reported as a finding before being caught:

   | Empty result | Concluded | Actually | The tell |
   |---|---|---|---|
   | `grep "code page" pm5.txt` | IBM never documents code pages | 42 matches | non-UTF-8 text; needs `grep -a` |
   | `grep -c "the" pm1.txt` | - | 2347 matches | same; `LC_ALL=C` does *not* fix it |
   | `command -v wcc386` | no toolchain on this box | OpenWatcom 1.9 in-tree | `command -v` only searches `$PATH` |
   | `command -v g++` | no C++ compiler | `/usr/bin/g++.exe` present | shell mishandles `+` in the name |
   | `ls .../i386-pc-os2-emx/` | `cc1plus` absent | present under `i686-...` | invented the triplet; `ls` printed nothing |
   | `yum list gcc-c++` | C++ install blocked | already installed | guessed Fedora names; repo errored anyway |
   | `ps ax \| grep hello` | the app exited | running fine | OS/2 `ps` rejects `ax` |
   | `file book.txt` -> `ASCII` | already converted | CP850 bytes further in | `file` samples only the head |

   **The same applies to test data.** A fixture you generated is a probe too. A file written on OS/2
   with shell redirection picks up CRLF translation on top of any `\r\n` you asked for, producing
   `\r\r\n` - and an editor loading it shows a blank line between every real line, which reads as a
   line-ending bug in the code under test. `od -c` the fixture before believing what it tells you
   about your program.

   Prefer the authoritative instrument over the convenient one: `rpm -qa` (no repo needed) over
   `yum list`; `find` over `ls` on a path you guessed; `wc -l` before trusting a volume (`gpi1.txt` is
   a 354-line stub - the real GPI reference is `gpi2.txt`); `iconv -f UTF-8 -t UTF-8` over `file`.
   And when searching IBM's books, match *their* wording, not yours - two of this kit's documented
   gaps were found only on a second look after a first search "proved" them absent.
4. **Don't originate feasibility judgments either.** Rules 1-3 cover *facts*; this one covers
   *advice*, which comes from the same untrustworthy place and steers far more work. "Project X is
   already ported to OS/2", "that library won't build with this toolchain", "that port is about N
   thousand lines", "OS/2 has no equivalent of that API" - these feel like knowledge and are
   training. A wrong offset fails at compile time; a wrong feasibility call costs weeks before it
   fails. Two specific reflexes to distrust:
   - **Assuming OS/2 is maximally alien.** Rule 7 warns you not to assume OS/2 works like POSIX -
     but the inverse error is just as common and this kit caused it at least once. **Presentation
     Manager is architecturally a Win32 cousin**: `WinRegisterClass` / `WinCreateWindow` /
     `WinGetMsg` / `WinDispatchMsg` / `WinDefWindowProc`, a window procedure switching on `WM_*`,
     dialogs from resource templates, and native controls (`WC_BUTTON`, `WC_ENTRYFIELD`, `WC_MLE`,
     `WC_CONTAINER`, `WC_NOTEBOOK` ...). Before telling a user that a Windows concept has no analogue,
     grep `os2ref/pm-window-messaging.md` and `os2ref/pm-controls.md` - it usually does.
   - **Answering a strategy question before reading the kit.** Toolchain viability is settled by
     `recipes/choosing-a-toolchain.md` (GCC/kLIBC is a first-class option, not a fallback); corpus
     coverage is settled by `wc -l` on the relevant `os2ref/` doc; what IBM documents is settled by
     the books on disk. Check, then advise.
   - **Writing "blocked" when you mean "not written yet".** This is the quietest form of the error,
     because it is recorded in a status file rather than said out loud, and it survives the session
     that made it. During the Notepad2 port, nine items were logged as blocked on a missing
     subsystem; exactly **one** was - OS/2 genuinely has no file-change notification API. Two were
     simply misfiled: line-ending conversion is `SCI_SETEOLMODE` + `SCI_CONVERTEOLS` and needs
     nothing new, but sat recorded as gated behind the largest remaining task because in the source
     application its menu sits next to Encoding. Others - printing, Unicode, shell enumeration -
     were already documented in this kit by the same session that called them impossible.

     **Keep the two words apart in writing.** *Blocked* = a platform capability that does not exist,
     and you can cite the probe that establishes it. *Unwritten* = work of some size that nobody has
     done. Size the unwritten thing (an afternoon / medium / large); never let it borrow the word
     that means impossible. A later session reads "blocked on X" and skips tractable work forever -
     the cost is not the wrong label, it is the work that never gets attempted.

   If you cannot source a judgment, present it as a question to verify, not a finding.
5. **Respect provenance.** `os2ref/` marks each claim `[DOC-IBM]` / `[OBS-RE]` / `[DOC]` / `[SRC]`
   (see the key in `os2ref/README.md`). A community/EDM2 fact (`[DOC]`) is weaker than an IBM header
   fact (`[DOC-IBM]`); don't launder one into the other. A `[SRC]` fact - read from the source of a
   component that runs *on* OS/2, such as kLIBC - is authoritative for that component and silent
   about the platform, so it does not override `[DOC-IBM]` on what OS/2 itself does. Use
   `[unverified]` for a claim you could not source - and treat an existing `[unverified]` marker as
   an open task, not a settled answer.
6. **Read the doc before disassembling.** Almost every OS/2 interface is documented - in `os2ref/`,
   or an IBM `.INF` book via `tools/inf2txt`. Reverse-engineering a *documented* contract wastes time
   and invites error.
7. **Fail honestly.** If a call, a control, or a feature isn't understood, stop and say so - never
   fake a success, stub a lie, or route around an error to "make it run." In an OS/2 app a dishonest
   success (a wrong window style, an unhandled message, a bad `.DEF` export) usually crashes far from
   the cause.
8. **Fix the bug where it lives.** If the defect turns out to be in a shipped library, DLL, or
   program rather than in your code, **rebuild that package and fix it there** - don't contort your
   own code around it. That is available far more often than instinct suggests: this ecosystem is
   source-available (netlabs SRPMs, bitwiseworks' GitHub), and `recipes/rebuild-a-netlabs-package.md`
   is the mechanics, end to end. The workaround is the expensive branch - permanent, invisible to
   everyone else who hits the same bug, and it bends your design around behaviour that shouldn't
   exist. The asymmetry that settles it: a *sound* workaround already requires diagnosing the bug
   precisely enough to fix it, so once you can safely work around it you can usually just fix it.
9. **Think in OS/2 shapes.** Selector:offset addressing, 64 KB tiling, 16/32-bit mixing, the
   `_System`/`APIENTRY` calling convention, `HWND`/`HPS`/`HAB` handle types, the message-driven PM
   model, LX/NE executables. `os2ref/` corrects the POSIX/flat-memory instincts that mislead here.

**Porting an existing Windows application?** Read `recipes/porting-a-windows-app.md` first - the
Win32->PM mapping table, the six *silent* differences that compile cleanly and fail invisibly
(`WM_INITDLG`'s inverted return, the bottom-left origin, colour-index mode, ...), and the
verification steps that actually catch them.

For the deeper craft of *writing* the C - asserting every ABI struct's size (`_Static_assert`),
treating packed/shared structs as wire formats, tracking whose memory a pointer belongs to, and
commenting load-bearing weirdness - see **`c-guide.md`**.

## The build loop

1. **Route.** Task -> `os2ref/README.md` -> load the 1-3 relevant docs (e.g. a dialog: `pm-controls.md`
   + `resources-and-dialogs.md`; a folder subclass: `wps-classes.md` + `som.md`). Don't load all 42.
2. **Write** in IBM-canonical names. Enable the right include switches (`#define INCL_WIN`,
   `INCL_GPI`, `INCL_DOSFILEMGR`, `INCL_WINWORKPLACE`, ...) - `os2ref/` and the headers name them.
3. **Verify** each nontrivial prototype/constant against the Toolkit header if present
   (`grep -rn WinCreateStdWindow .../H`) and cite it in a comment. If no headers, lean on `os2ref/`
   and flag anything it doesn't cover.
4. **Declare exports/imports** correctly: a `.DEF` module-definition file (`LIBRARY`/`NAME`,
   `EXPORTS`, `DATA`/`CODE` attributes) - see `os2ref/calling-convention.md` and
   `os2ref/module-dll.md`. Wrong ordinal/`.DEF` linkage is a top cause of `SYS`-error load failures.
5. **Build** with the recipe for the chosen toolchain (`recipes/build-pm-app.md`). OpenWatcom:
   `wcc386` -> `wlink`, `wrc` for `.RC` resources. GCC/kLIBC: `gcc -Zomf`, `wlink` backend, `wrc`.
6. **Inspect** the result: `lx_export.py` lists an LX binary's objects, exports (entry table +
   names, forwarders included) and imports (module list + the ordinals/names its fixups reference);
   `lx_disasm.py` disassembles at a symbol, VA, or `object:offset`; `ne_profile.py` profiles
   16-bit NE. Use these to confirm the module actually exports/imports what you intended before you
   ship it to the VM.
7. **Test** on a real OS/2 (`recipes/setup-test-vm.md`): copy over (or build over SSH) and run.
   OS/2 records unhandled exceptions to `C:\POPUPLOG.OS2` - read it to diagnose a crash (the process,
   the failing address, and for load failures the missing `MODULE.ordinal`).

## When something fails

(Fuller workflow - crash triage, error diagnosis, getting debug output - in
`recipes/debugging-an-app.md`; kernel/driver level in `recipes/kdb-reference.md`.)

- **`SYS0002`/`SYS1804` (file/module not found), `SYS2070` (bad ordinal / demand-load failed):** a
  linkage or LIBPATH problem, not your logic. Check the `.DEF` exports, the imported DLL name/ordinal
  (`lx_export.py` on both sides), and that dependent DLLs are on `LIBPATH`/`BEGINLIBPATH`.
- **A PM call returns `FALSE`/`NULLHANDLE`:** query `WinGetLastError(hab)` and look the `PMERR_*` up
  in `os2ref/` (error semantics) - PM reports *why* through the error, not the return value.
- **A crash (`SYS3175`) in `C:\POPUPLOG.OS2`:** note the module + offset; disassemble with
  `lx_disasm.py` at that object:offset to find the faulting instruction.
- **Low-level / driver work:** the OS/2 kernel debugger (`tools/kdb_*`, `recipes/setup-kdb-vm.md`)
  drives a debug-kernel VM over a serial pipe - breakpoints, registers, module/symbol lookup.

## Deeper than `os2ref/`

`os2ref/` is a representative reference, not exhaustive. For a call or field it doesn't cover, read
the IBM source book directly: `inf2txt.sh <book.inf>` turns a compiled `.INF`
(`cpgref`, `pmwin`-family, `gpi*`, `pddref`, `somref`, `wps*`, `rexxpg`, ...) into text
(`recipes/read-ibm-books.md`; get the books per `sources.md` section 3). Tag anything you take from them
`[DOC-IBM]` with the book name.
