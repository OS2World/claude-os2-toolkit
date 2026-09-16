---
name: track
description: The work queue - file, find, comment on and close work items on a project's Gitea issue tracker from the shell, with no browser. Use it whenever something out of scope is found mid-task (file it, do not fix it inline), when deciding what to open a session for, when asked what is open or what the backlog says, and for any question about a ticket number, a label or how the tracker is configured. It also carries the rule for what belongs in a ticket and what belongs in the knowledge cache instead.
---

# The work queue

`track` drives a Gitea instance's issue API from the shell, so a session can
file, find, comment on and close work items without a browser.

    track ls                       # what is open
    track new -c loader -t defect -T 'LX forwarder fixup drops the ordinal'
    track show 41
    track close 41 -m 'fixed by the entry-table read'

**One copy of this tool serves every project on the machine.** It is a plugin
tool (`${CLAUDE_PLUGIN_ROOT}/tools/track`, on `PATH` as `track`); which tracker
it talks to is resolved at run time, never edited into the script. Do not copy
it into a project tree - a copy drifts, and the fix you make to one is invisible
to the rest.

## WORK STATE here; KNOWLEDGE in the cache

This is the split that decides where a thing goes, and it is worth getting right
because the two stores fail differently.

| | goes to | why |
|---|---|---|
| a defect, a task, a gap in *our* work | **the tracker** | it is state: it changes, and one day it is closed and gone |
| a durable OS/2 fact | **`know add`** (`os2-toolkit:know`) | it is timeless and was expensive to establish; it outlives every ticket |
| a search that found nothing | **`know absent`** | a recorded negative closes a question; a ticket about it just ages |

**A ticket is not a place to keep an OS/2 fact.** Closing the ticket deletes the
fact from anywhere anyone will look, and a tracker has no citation, no
`verify_cmd` and no provenance tag - the three things that make a fact
checkable. If a card taught you something about OS/2, the card's closing comment
says what was done and `know add` holds what was learned.

The reverse is just as real: project state does not belong in the knowledge
cache. `know` refuses a row keyed to your own code for the same reason - it is
stale on arrival.

## File it the moment you find it

**When you find something out of scope, file it and leave it. Do not fix it
inline.** Document, queue, carry on - including a finding that blocks your own
work, which gets a card *and* a named blocker rather than a quiet workaround.

The reason is not tidiness. A fix smuggled into an unrelated change is a fix
nobody reviewed, in a diff nobody expected it in, and the finding that motivated
it is never written down - so when it turns out to be wrong there is nothing to
read. A card costs one command.

    track new -c doscalls -t defect -T 'ordinal 204 arg_bytes is 0 but the body reads args' \
        -m 'found while doing X; not in scope for this change'

The body is also read from stdin, which is the easy way to file something long:

    track new -c video -t knowledge-gap -T 'where does DEVINFO=SCR load the font' <<'EOF'
    ...
    EOF

## The verbs

| | |
|---|---|
| `new -c COMPONENT -t TYPE -T TITLE [-m BODY]` | file one; body also read from stdin |
| `ls [-c COMPONENT] [-t TYPE] [-s open\|closed\|all]` | the board; defaults to open |
| `show N` | one issue in full, with its comments |
| `search QUERY` | full-text over open and closed |
| `comment N -m TEXT` | add a comment; text also read from stdin |
| `close N [-m TEXT]` | comment (if given) and close |
| `reopen N` | reopen |
| `label N -c COMPONENT [-t TYPE]` | re-file: swap component and/or type, keep the other |
| `labels` | every label with its description - the vocabulary this repo actually has |
| `init -p OWNER/REPO -c COMP[,COMP...] [--project-dir DIR] [--dry-run]` | create a project's tracker |

Run `track` with no arguments, or `track --help`, for the same list.

**Closing is an explicit act.** Nothing closes a card for you: there is no
commit hook, and the tracker knows nothing about your version control. A card is
closed by whoever finished the work, with a comment saying what landed.

## Labels: one type, one component

Every card carries exactly two labels, and `track new` refuses anything else.

- **type** - `defect` (something is wrong), `task` (work to do, nothing broken),
  `knowledge-gap` (answered rather than fixed).
- **component** - one subsystem label per project. A label is a component **iff
  its Gitea description is exactly the word `subsystem`**; that is the only
  thing telling the two kinds apart, and `track label` keys on it. Get that
  description wrong and `track new` still works while `track label -t ...`
  silently drops the component.

`track labels` is the authority for what this project's tracker has. Do not
guess a component name - an unknown one is refused, which is the point.

## Config, and where a project records its repo

Three settings - `TRACK_URL`, `TRACK_REPO`, `TRACK_TOKEN` - resolved **first hit
wins**:

1. the **environment**;
2. **`.os2track`** in the working directory or any ancestor - `TRACK_URL` and
   `TRACK_REPO` only;
3. **`${XDG_CONFIG_HOME:-~/.config}/os2-toolkit/track.env`** - the user default,
   mode 600.

A file fills only names still **unset**, so the environment really does win.
(That is a measured fix. The tool this one descends from sourced its files with
`.`, so a later file overwrote an earlier one and the documented order ran
backwards - a deliberately wrong `TRACK_REPO` in the environment was ignored and
the old repo answered instead, which looks exactly like success.)

**A project records its own repo, in its own tree** - in `.os2track`, and worth
a line in its `CLAUDE.md` so a session knows the queue exists. Never in this
plugin: the plugin is shared by every project on the machine and holds no
project's settings.

**The token is a secret and lives in the user config only.** Never write
`TRACK_TOKEN` into `.os2track` - that file is in a working tree, and a token
there gets committed, pushed and mirrored. `track` refuses to read a project
file that sets it, and refuses a user config that is group- or world-readable
(`chmod 600` it). Unset config fails by name, saying which setting is missing
and where to put it; it never quietly asks an empty URL, because a request that
was never made looks just like a server with nothing to say.

## Creating a project's tracker

    track init -p OWNER/REPO -c loader,doscalls,video --project-dir .

Run it from anywhere the token can reach. Every step is idempotent - an existing
repo, label or config file is reported and kept - and `--dry-run` performs the
reads and prints the writes it would make, so the plan can be read first. It
creates the repository (issues only, no README so it stays empty - nothing is
versioned in a work queue), the three type labels, one `subsystem`-described
label per `-c` name, the user config (URL and token, mode 600), and with
`--project-dir` that project's `.os2track` (URL and repo, no token).

**Token scope, measured:** `write:issue,read:repository` is enough for every
verb but `init`, which also needs **`write:user` and `write:repository`** -
`POST /user/repos` is refused with `write:repository` alone. A Gitea token is
per user, not per repository, so one token reaches every repo that account owns
and serves every project `init` creates. Minting a token is the one thing no
token can do; it needs the web UI or basic auth as the account owner, once.

Note what that scope buys: a token that can create repositories can also
reconfigure and delete them. If that trade is not acceptable, keep the everyday
token narrow and do the one `init` with a separate credential.
