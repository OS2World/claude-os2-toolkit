# Conformance testing: measure OS/2 first, then build to the measurement

For a project building a component that existing OS/2 programs must be able to use unchanged - a
compatible PM or `DOSCALLS` layer, a driver, a shell - and that therefore has to behave the way
OS/2 does. Those programs were written and tested against what OS/2 does, not against IBM's
books.

The method in one line: **for each family of calls, write down every outcome, make each one
happen on real OS/2, bake what real OS/2 did into a self-checking program, and then build your
version until the same program, unchanged, passes against it.**

It came out of two projects that did exactly this (a compatible `DOSCALLS` layer and a compatible
PM). It is a method to open when you need it, not a gate: nothing here says work may not
land, and its last rule is a brake on its own overuse.

---

## 1. Who decides what the module should do

In this order:

1. **IBM's documentation** - the Toolkit and DDK headers and books (`read-ibm-books.md`).
2. **Reverse-engineering notes** you or others already wrote about IBM's binary. Read them first;
   decode anything new only for the gaps.
3. **Measurements of IBM's module on a real OS/2 system** - the probes this recipe builds.
4. **What real programs depend on** - a corpus of shipped applications and their imports, for
   deciding what to build next (`inspect-a-binary.md`, `lx_resolve_imports.py`).

**When the documentation and a measurement disagree, the measurement wins**: programs were
tested against what the module does. Record the documentation error where your project keeps
corrections, and in `os2ref/` if it is a fact about OS/2 (`os2-toolkit:contribute`). A static
reverse-engineering reading does not outrank the documentation on its own; a probe does.

- **Undocumented behaviour is measured before it is designed against.** If the books and the RE
  do not settle it, the design waits for a probe, and the open item says so.
- **Every claim about IBM's module carries a source** - a citation, a probe result, a corpus
  example, or the word "guess".
- **Rules about IBM's binaries come from tool-read populations, never one example.** "Every
  export of X is a forwarder" cites the `lx_export.py` run that counted all of them. Two
  hand-generalised rules about IBM export tables were measured false in one project before this
  rule existed.

---

## 2. Before any code: take the module's shape from IBM's binary

Your module stands in for IBM's by name, so other IBM binaries will load it and call it exactly as
they called IBM's. Read the shape out of the real file (`inspect-a-binary.md`):

- **Same module name, same ordinals.** Keep IBM's ordinal numbers. Other shipped binaries, and
  IBM's own forwarder DLLs, reach the module by raw ordinal; a renumbered entry breaks callers you
  never looked at. Anything genuinely new gets a number far outside IBM's observed range.
- **Forwarders where IBM has forwarders.** Several IBM system DLLs are pure forwarder modules
  (`os2ref/module-dll.md`, "The forwarder DLLs, and the complete shipped mapping"). Reproduce that
  structure rather than inventing your own split: the module a caller names should be the module
  that owns its entries, its module handle, its initialisation and its **resources** - a caller
  that loads an icon or a string by module name gets nothing from a module that only forwards.
- **Build it up incrementally.** While your module is incomplete, forward the ordinals you have not
  implemented to a renamed copy of IBM's module, and shrink that forwarding to nothing. The
  measured traps of doing this are in `os2ref/module-dll.md`, "Replacing a system DLL with a
  forwarder: measured traps", including how to install a test DLL through `LIBPATH` without
  touching IBM's file.
- **16-bit entries are real, separate entries**, with their own argument shapes and sometimes
  their own answers (`os2ref/thunking.md`, `os2ref/calling-convention.md`).

---

## 3. The family method

A **family** is a set of calls that share state: the queue calls, the event-semaphore calls, the
window-word calls. Work one family at a time.

1. **The matrix is the scope.** Rows are **function x outcome**. The outcomes are every return
   IBM lists for each function, any trap where the caller is observed to be killed, and **any
   return real OS/2 gives that IBM does not list** - keep those, labelled *observed*, because they
   are undocumented behaviour something may depend on. Add one short section on how the
   functions work together. Write it as the family's `CASES.md`, and agree it before writing
   code.
2. **Provoke every cell on real OS/2.** One honest attempt per listed return. A cell that will not
   happen stays **NOT PROVOKED**, with the recipe that was tried and what came back - that is a
   result, not a gap to fill.
3. **One program per family, simple but complete:**
   - a **functional mode**: one straight-line block per row, checked against a baked value;
   - a **stress mode**: the same calls intermixed across threads and, where it applies, processes;
   - **several copies at once** (per-instance names, plus one shared-name variant); rows that
     exhaust a system-wide limit run single-copy only;
   - a child-process helper only where a row needs one (a trap, cross-process ownership, an owner
     that dies).
4. **Bake and keep.** Hard-code the real-OS/2 values into the program, with a provenance header
   (machine, build, date). Commit the raw captures beside it. **Show that one deliberately wrong
   expectation FAILS** - a checker never seen to fail has not been shown to check anything.
5. **Build your version from the contract, and validate it with the same program, unchanged.**
6. **YAGNI.** Every function, argument, mode, fixture and case in the program traces to a matrix
   row, a stress loop or the copies run. A surprise found while testing - a crash, a flake, a doc
   sentence that over-claims - is recorded and filed, and the program does not grow to chase it.

---

## 4. The three values per case

Every case keeps three values, and the method exists to keep them apart:

| value | from | written |
|---|---|---|
| **expected** | IBM's books / headers / RE notes, with a citation | before the run, as a hypothesis |
| **real** | the program run on real OS/2 | by the run, never by hand |
| **yours** | the same program on your implementation | by the run |

**expected != real** is a correction to the documentation (or to your reading of it).
**real != yours** is your bug. Collapsing the three into pass/fail destroys the one thing the
comparison produces - and a summary that says "3 cases fail" has done exactly that.

**Case table format** - each row needs: a stable case ID (a name, not a number, so inserting a
row shifts nothing); the expected value with its provenance tag and citation; how it is asserted
(rc alone, rc plus a named query); and the three result columns, filled in by runs.

---

## 5. Building a probe that can be trusted

- **Captures are piped, never retyped.** `ssh ... 'PROBE.EXE' | tr -d '\r' > probe.real.out`,
  provenance header added afterwards. Hand transcription drops exactly the bytes a comparison
  depends on. A program launched over ssh is a *detached* process and some APIs refuse it
  (`setup-test-vm.md`); probes that need a session should run as an ordinary program and write
  their results to a file.
- **Compare by case key, not by line position**, in both directions: a key only on one side is a
  disagreement too.
- **Declare which fields are comparable**, per probe, with a one-line reason for every field you
  strip. A filter needs a true *reason*, not just a true conclusion, or it will swallow a real
  divergence later.
- **A known divergence is an allowlist entry with a citation that pins the divergent value**, not
  just the case name - keyed on the name alone, a different bug landing on the same case stays
  green. Never a silent skip; never a deleted case.
- **Put any case that can kill the probe last**, after all cleanup. A trap in the middle denies
  coverage to every case after it (one first-call NULL ended a probe silently and hid eleven
  cases).
- **16-bit and 32-bit are separate probes.** Never assume the other width, or a sibling call in
  the same width, behaves the same - measure each; agreement is a result, not a prior.
- **Test enforcement, not only persistence.** "The value round-trips" and "OS/2 acts on it later"
  are different claims; a settable property needs a case for what it is supposed to *cause*.
- **One API's suite exercises one API.** Another API used to observe an effect is called the same
  fixed way everywhere, never swept across its own parameters; prefer a query to a mutation for
  observing. If the observing call disagrees between real and yours, record the ambiguity rather
  than blaming the subject.
- **Fixture safety.** A probe that creates or deletes things owns one hard-coded name nothing
  else touches, and deletes only what it can prove this run created. Every state a case can set
  must be one the probe can unset - or it persists into every later run. A 16-bit probe's file
  names must be 8.3 unless it is linked with `NEWFILES` (`os2ref/file-io.md`).
- **Check every setup helper's return value**, even where it "cannot fail": a swallowed setup
  failure makes a later assertion pass for the wrong reason.

### The stress mode

- Every wait is bounded; a broken primitive must report FAIL, not hang the run. Name the two
  timeout tiers by meaning ("should happen" / "should not happen"), not by milliseconds.
- Worker threads make no C-runtime calls and report through `volatile` flags; only the main
  thread prints.
- Synchronise on each worker's own completion flag, and still call `DosWaitThread` afterwards to
  reap - a thread that ends with nobody waiting can become unwaitable, and unreaped threads end
  in `ERROR_NOT_ENOUGH_MEMORY` from `DosCreateThread` that looks like a resource bug in your
  code (`os2ref/process-thread.md`).
- **Give every concurrent section a serial control.** Serial passing while concurrent fails is
  the diagnosis.
- A bound printed in a message must be the bound the code enforces (`DosSleep(1)` rounds up to a
  timer tick, so a loop counting iterations against milliseconds lies).
- Run the stress mode on real OS/2 at least once: the threading scaffolding rests on the same
  untested assumptions as everything else.

---

## 6. Running it on real OS/2

Use a **disposable full clone** of a template VM for every run, and delete it afterwards:
`setup-test-vm.md`, "Cloning a template VM: clone, use, discard". The template stays clean and
keeps improving; a run that corrupts its clone costs nothing. Install your module on the clone
the way `os2ref/module-dll.md` describes (a directory at the front of `LIBPATH`), never over
IBM's file.

Keep each batch's raw logs, the exact script that ran, and the build that ran, so a result can be
re-read rather than re-asserted.

---

## 7. Validating your version: the same program, then differential runs

- **The family programs are the acceptance test.** Run each one, unchanged, on your
  implementation; the third column fills in.
- **For a whole subsystem, run differentially**: the same application under IBM's module and
  under yours, on the same VM image, and compare what can be recorded on both - message traces
  (PM's own hooks, `WinSetHook` with `HK_SENDMSG` / `HK_INPUT`, record both sides alike, so your
  version implements hooks early), screenshots under masks for clocks and timestamps, the probe
  results.
- **Measure the instrument before trusting it**: the noise floor (real vs. real, expect 0
  differences) and a deliberate perturbation (expect exactly the difference you caused) come
  first.
- **Keep every delta switchable.** Each behaviour your version adds beyond plain replacement can
  be turned off, so the first step with any bug is to turn the deltas off and see whether it
  persists.

---

## 8. When a probe finds something outside its family

It will - a suite exercises shared helpers nothing else tests. **Record it, file it, and leave
it**, even when it turns your own case red: mark the case as a cited known divergence so the
family is green-with-exceptions, and hand the fix to its own piece of work. Fixing a shared
helper from inside another family's pass is the cross-API edit the one-API rule exists to
prevent. Two families flagging the same helper is corroboration - say so.

A real OS/2 fact the probes surface belongs in `os2ref/` (`os2-toolkit:contribute`) and the
knowledge cache (`os2-toolkit:know`), not only in the family's `CASES.md`.

---

## 9. Keep it small

*"These shouldn't be tomes of edge cases and complex wiring. They should be simple, but
complete."* The matrix bounds the program; the program does not grow past it.

The receipt for this rule: one probe was scoped from doubts in the project's own reference text
instead of from a matrix, and grew to **1,732 lines** of crash bisection, skip machinery and cases
written to make a doc sentence true - after its questions were already answered - and was rebuilt
from a matrix. If the scratch tooling for a change is bigger than the change, stop and ask whether
building it *is* the work.
