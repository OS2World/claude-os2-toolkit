---
name: os2-review
description: Review an OS/2 change before trusting it - dispatch the os2-reviewer agent for a grounded, graded (A-F) review of work touching OS/2 semantics (Dos*/Win*/Vio* APIs and ordinals, PM, VIO, drivers, the LX/NE loader, kernel objects, thunks, the 16/32-bit ABI split), with the change set, claims, evidence, populations and grade history packaged for it. Use when asked to "review this OS/2 change", "grade this", "review before landing", "check this against IBM", or before committing anything that touches OS/2 behaviour. Has a cheap "--citations" mode that only reconciles cited sources against what they are cited for - run that first, and for "check my citations", "did I cite that right", or between graded rounds.
---

# Graded OS/2 review of this session's work

Spawn the **`os2-reviewer`** agent to attack the work, not to admire it. It is
the adversarial-review idea with two things a generic review lacks: it **grounds
itself in primary OS/2 sources first** - the knowledge cache, this kit's
`os2ref/`, the user's OS/2 library by role, IBM's Toolkit and DDK headers and
books - because the model is not trained on OS/2 and would otherwise grade
against its priors; and it returns a **letter grade**, not just a list of
findings.

The reviewer starts blind: it cannot see this conversation. That is the point,
and it is also why the dispatch has to carry everything. "Review the changes"
gets you a generic style report; the grade is only as good as the package.

## 0. Pick the mode - the cheap one first, and often instead

The agent has two modes and the dispatch names one. **A `full` round costs
roughly twenty times a `citations` round**, so choosing `full` by reflex is the
most expensive habit available here.

- **`citations`** - a mechanical pass: open every source the change cites and
  check the sentence is there and says what it is cited for. No grade, no C
  review, no architecture opinion. Measured across three `full` rounds on one
  change, this single activity produced **six of that round's eight findings**;
  it is a grep-shaped job that does not need a judgement pass around it.

  **Run this FIRST whenever the change adds prose that cites sources** - a new
  `.c` file with commentary, a doc correction pass, a table with provenance tags,
  anything carrying `[DOC-IBM]` / `[OBS-RE]` markers or `file:line` references.
  Fix what it finds, and only then spend a `full` round, which now gets to look
  at the code instead of at citation drift.

  It is also the right answer to "is this ready?" between rounds, and to a change
  too small to justify `full` at all.

- **`full`** - grounding, the whole attack order, the letter grade. This is the
  gate; nothing lands without one.

`/os2-toolkit:os2-review --citations [paths]` selects the cheap mode; the default
is `full`.

## 1. Gather the change set - detect the VCS, do not assume one

```sh
git rev-parse --is-inside-work-tree 2>/dev/null   # git
svn info 2>/dev/null                              # subversion
```

- **git**: `git status --porcelain`, then `git diff` plus `git diff --cached`
  for uncommitted work, or `git diff <base>...HEAD` for a branch, or
  `git show <rev>` for one commit. Say which of these "the change under review"
  means.
- **svn**: `svn status`, `svn diff --summarize`, `svn diff`. For a committed
  revision, `svn diff -c <rev>` and `svn log -v -c <rev>`.
- **Neither** (or work outside the working copy): name the paths explicitly in
  the dispatch. The reviewer cannot guess them.

**Untracked and ignored files matter too** - list any probes, build scripts,
captures or test directories you created. **A defect in a test harness
invalidates every result it produced**, so harnesses and captured outputs are in
scope. If the work lives in a different checkout, or the user asked for specific
paths or a revision, use that instead.

## 2. Package the six things the reviewer cannot reconstruct

1. **Files changed** - paths, one line each on what changed and why. Note which
   files are untracked.
2. **Claims** - every statement made to the user that something works, matches
   real OS/2, or is fixed. Include the OS/2 subjects by IBM's exact name (ordinal
   numbers, `Dos*` / `Win*` / `Vio*` / `Kbd*` spellings, structure names, error
   codes by number) so the grounding phase starts on the right headers.
3. **Evidence** - the *exact* output or observation behind each claim: probe
   stdout, a real-OS/2 capture beside the same probe's output here, test counters
   with the baseline they were compared against. Not "tests pass" - the lines,
   and the command that produced them.
4. **Grade history - REQUIRED, and the single most useful line in the dispatch on
   any round after the first.** The reviewer is a fresh agent with no memory of
   the previous round; without this it produces a third independent list instead
   of answering the only question that matters by round two, which is *are we
   converging*. State the round number, every previous grade in order, and the
   rubric line that set each:

   > **Grade history:** round 3. Round 1: C ("a claim asserted without the
   > measurement that would settle it" x3). Round 2: C (same line, x1 - the three
   > named in round 1 were fixed). Findings verified and repaired between rounds:
   > [list].

   A flat sequence is not bad luck and not a harsh reviewer - it is evidence the
   repairs addressed the symptoms the reviewer happened to name while the thing
   generating them kept running. The agent's **Trajectory** section exists to
   name that mechanism, and it cannot run without this field. On round 1, say
   "round 1, no history".
5. **The populations you know of** - the denominators the reviewer will otherwise
   have to guess: how many citations the change contains, how many comments
   assert an OS/2 fact, how many ordinal or dispatch-table rows were touched, how
   many new constants, how many call sites a changed function has. You can count
   these with `grep` in seconds and the reviewer cannot know it has them all.
   This is what makes its **Coverage** section checkable rather than
   self-reported.
6. **The exception list** - every allowlisted known divergence, skipped case, or
   out-of-scope finding recorded and left, each with its citation. A new
   allowlist entry is itself a finding the reviewer will report; say it up front
   rather than have it found. Include anything you recorded this iteration, since
   a reviewer cannot tell a pre-existing item from one created to satisfy it.

**Before you dispatch, ask the knowledge cache what is already known** about the
subjects in field 2: `know q '<question>'`. A recorded negative ("searched X,
absent") belongs in the package - it saves the reviewer the same dead end, and it
is evidence the question was taken seriously.

## 3. Launch

`Agent(subagent_type: "os2-reviewer", ...)`. Do not paste the persona, the attack
order, or the rubric - the agent file carries them and is their source of record.
The prompt is the package:

> Review and grade the following work. You have none of the author's context.
>
> **Mode:** full | citations
> **OS/2 subjects:** [ordinals / APIs / structures / subsystems, IBM spelling]
> **VCS and change set:** [git or svn, the exact command that shows the change,
> and the paths; note untracked files]
> **Files changed:** [paths + one line each]
> **What the author claims works:** [each claim]
> **Evidence the author relies on:** [the exact output behind each claim]
> **Grade history:** [round N; each previous grade + the rubric line that set it;
> what was repaired between rounds - or "round 1, no history"]
> **Populations:** [citations N, OS/2-fact comments N, ordinal rows touched N,
> new constants N, call sites of <fn> N - as many as you counted]
> **Exception list:** [allowlisted divergences / skipped cases / recorded
> out-of-scope findings, each with its citation - or "none"]
> **Tree state:** [checkout path, the revision or commit, whether the tests were
> run at this exact state]

One reviewer per subsystem for a large session, in parallel; otherwise give one
reviewer the **whole** change set - cross-file ownership and lifetime bugs are
exactly what a fresh reader catches.

## 4. After it reports

- **Read the Grounding note first.** If it is thin, unsourced, or grounded on the
  project's own headers and status docs instead of the IBM material, `os2ref/`
  and the RE sources, the grade measures the reviewer's priors, not the work:
  discard it and re-dispatch with the subjects spelled out more precisely. If it
  says a role was missing from the library (`os2-lib roles` shows what is
  present), that is material the user needs to ingest - `os2-toolkit:ingest` -
  not something to grade around.
- **Read the Coverage section second, and read it as the size of the report.**
  Six findings out of six citations opened and six out of twenty-eight are
  different results with the same finding count. A dimension marked
  `exhausted (n/n)` is closed - you can stop working on it, which is the only way
  a good grade is ever earned rather than sampled into. A dimension that is not
  exhausted comes with the unopened items named: those are the next round's
  starting point, and **feeding them back in the next dispatch is how three
  rounds stop re-sampling the same population.** A report with no Coverage
  section is a report of unknown size - send it back.
- **On round two and later, read Trajectory before the findings.** If it names a
  mechanism, that is the thing to repair; repairing the individual findings under
  a flat grade buys exactly one round. If it says "no history supplied", the
  dispatch was missing field 4 and that is your error, not the reviewer's.
- **Weigh findings by consequence class, not position.** `[BEHAVIOUR]` findings
  are what block landing; `[BELIEF]` findings are real and expensive, but a pile
  of them is usually one mechanism (see Trajectory) rather than N repairs;
  `[COSMETIC]` never blocks anything. Report all three classes to the user with
  their labels intact.
- **Findings are hypotheses.** Verify each against the code (and a run, if cheap)
  before changing anything. Findings about the *evidence* outrank findings about
  the code - if a test proved nothing, everything downstream of it is unsupported
  and must be re-established. And a finding about evidence can itself rest on a
  premise your own dispatch supplied: an adversarial reader cannot falsify a
  premise you handed it.
- **Report every finding to the user**, including the ones you disagree with,
  with your assessment. Never silently drop one.
- **Report the grade and the rubric line that set it.** Below A-, nothing lands;
  say what the reviewer said would raise it one step, and whether you intend to
  do that or escalate.
- **Out-of-scope findings get recorded and left**, not fixed in this change - the
  rubric's "fixed instead of recorded" is an automatic F. Where they belong
  depends on the project: its issue system, its plan, or `know absent` for a
  dead end the review closed.
- **Record what the review established.** A durable OS/2 fact the reviewer had to
  source, or a search it proved empty, is worth more than the review: `know add`
  (with a `--verify` command that can fail on the contested half) and `know
  absent`. Read the `os2-toolkit:know` skill for the flags. Never record a fact
  about the project's own code - that is project state, and it is stale on
  arrival. A fact that is general, sourced and de-identified is then a candidate
  for `os2-toolkit:contribute`.
- The reviewer is read-only and cannot see runtime reality any more than you can;
  a "could not verify" from it is a measurement you still owe.

## What this is not

Not a substitute for running the tests: the reviewer grades evidence you bring
it; it does not generate it. Not a general code review either - for correctness
and cleanup on non-OS/2 code, the generic review tooling is cheaper. This is for
work whose correctness is a question about **OS/2**, where the expensive failure
is a fluent wrong answer nobody can falsify.
