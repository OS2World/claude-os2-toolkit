# Setting up a tracker (self-hosted Gitea, one per project)

A place to put work state: defects found mid-session, tasks queued for later, and questions the
session could not answer. The shape below is a **self-hosted Gitea** used as nothing but an issue
tracker - one repository per project, issues on and everything else off - driven from a shell with
the `track` tool, so a session files a card without leaving the terminal and without a browser.

**Read the last section before you start using it.** The tracker holds *work state*. Durable OS/2
facts do not go in tickets; they go to the reference and the knowledge cache.

## What you need first

- **A Gitea instance you run, or have an account on. The toolkit does not provide one** - no server
  is installed, hosted or bundled here. Gitea is a single Go binary you can run on a spare box, a
  NAS, or a container; a personal instance on the local network is the normal case.
- **`curl` and `jq`.** That is the whole dependency list; `track` is a shell wrapper over the REST
  API.
- The tool speaks **Gitea's `/api/v1`, not GitHub's**. The two are similar enough to mislead and
  different enough to fail: repository units, label descriptions and token scopes are all Gitea
  concepts. Pointing this at `api.github.com` will not work.

## The shape

| piece | what it is | who decides it |
|---|---|---|
| instance | one Gitea, one user account is enough | you |
| repository | one per project, **empty**, **issues the only unit** | server default `DEFAULT_REPO_UNITS = repo.issues`; `init` also forces it |
| type labels | `defect`, `task`, `knowledge-gap` | the vocabulary below; `init` creates all three |
| component labels | one per subsystem, description exactly `subsystem` | the project's own names; the **description is the rule** |
| token | **one token serves every repository** - a token is per user | `write:issue,read:repository` daily; more to create repos |
| config | environment, then a project file, then a user config file holding the token | see "Configuration" |

Nothing in the repository is versioned. There is no code in it, no README, no wiki, no pull
requests - `auto_init` is off, so the repository stays empty and there is nothing to diverge from
whatever really holds the project's source.

**Server settings that make this setup what it is** (in the instance's `app.ini`, if it is yours to
configure):

| key | value | effect |
|---|---|---|
| `[repository] DEFAULT_REPO_UNITS` | `repo.issues` | a new repository gets **only** the issues unit - wiki, pull requests, projects, releases, packages and actions are off from creation |
| `[service] DISABLE_REGISTRATION` | `true` | no self-signup |
| `[server] OFFLINE_MODE` | `true` | no CDN assets; the box need not reach the internet |
| `[actions] ENABLED`, `[cron] ENABLED` | `false` | nothing runs on the server on its own |

That same file holds the instance's server-side secrets. **Do not copy it into a document, an issue,
or a session transcript.**

## The labels, and the rule that makes them work

Three **type** labels, one per card, carrying what kind of thing it is:

| label | means |
|---|---|
| `defect` | something is wrong |
| `task` | work to do, nothing broken |
| `knowledge-gap` | answered rather than fixed |

Then one **component** label per subsystem you want to slice the board by - the project's own names,
however many you need.

**A label is a component if, and only if, its Gitea description is exactly the word `subsystem`.**
That is not a convention the tool merely prefers; it is the test it performs. `track` reads each
label's description to decide which of a card's labels is the component and which is the type, so a
component label carrying any other description still files cards fine and then silently loses its
component when the card is re-labelled. If a re-label drops a component, check the description
first.

## Tokens - the part that is easy to get wrong

These are measured against a live instance, and two of them are counter-intuitive:

- **A token is per USER, not per repository.** One token therefore reaches every repository that
  user owns, including ones created later. You do not mint a token per project, and `init` copies
  the one you have into each new project's config.
- **`write:issue,read:repository` is enough for daily use** - filing, commenting, labelling,
  closing. That is the scope an everyday token wants, and it deliberately cannot create anything.
- **Creating a repository needs `write:user` AND `write:repository`.** `POST /user/repos` sits
  behind both scope categories and refuses `write:repository` alone - the refusal names
  `required=[write:user]`. Read a route's scope from every group it sits in, not from its own line
  in the router; the prose scope docs name fewer things than the router enforces.
- **Minting a token is the one thing no token can do.** `POST /users/{username}/tokens` requires
  HTTP basic auth (your account password), so the first token is created once, by hand, in the web
  UI or with a single `curl -u <user>` call. The value is displayed once and never again. Token
  names are unique per user, so a second mint under the same name is refused - pick another.

**The trade, stated once so it is a decision and not an accident:** `write:repository` can also
delete or reconfigure any of that account's repositories, and `write:user` can change the account's
own settings, mail address and keys. On a single-user instance used only as a tracker that is
usually accepted. If it is not acceptable to you, keep two tokens - a wide one used only when
creating a project's tracker, and the narrow daily one everywhere else - or create the repository by
hand in the UI and let `track` do the rest.

## Creating a project's tracker

`track`'s `init` verb takes the repository to create and the component names to create labels for.
Run `track --help` for the verbs and their exact flags; run `init` with its dry-run
option first (see below). It performs, in order:

1. **The repository.** Looks it up; creates it only if absent, with auto-init off, so the repository
   comes out empty - no README, no `.gitignore`, no licence.
2. **Issues only.** Reads the repository's units and switches off anything but issues. On a server
   with `DEFAULT_REPO_UNITS = repo.issues` this is a no-op; the step is what makes the result the
   same on a server configured otherwise.
3. **Labels.** The three type labels, then one `subsystem`-described label per component name.
   Names already present are left alone.
4. **Config.** Writes the user-level config file (mode 600) with the instance URL, the token, and
   this project's repository. An existing file is left alone.

Then, in the project, list the labels to confirm the set, and file the first card. Hand the project
this recipe too, so whoever reads the board knows what the three type labels mean.

## Configuration, and why the order matters

`track` resolves its settings, **first hit wins**:

1. the **environment**
2. a project-level **`.os2track`** in the project directory - URL and repository only, **never a
   token**; it is the file that says *which* tracker this directory talks to, and it is safe to
   commit
3. **`${XDG_CONFIG_HOME:-~/.config}/os2-toolkit/track.env`**, mode 600 - the user-level file, and
   the only one that holds the token

The rule that makes that order real: **a configuration file may only fill in names that are still
unset.** Sourcing files with `.` does the opposite - each assignment overwrites the last, so the
*last* file read wins and the environment never does. That was a real defect, not a hypothetical:
the documented order was exactly reversed, so a deliberately wrong repository name set in the
environment was silently ignored and the tool cheerfully answered from the configured one instead.
An override that does not override is worse than one that is missing, because it reports success.

Check it the same way: set the repository to a name that does not exist, ask for its labels, and
confirm you get an honest `HTTP 404` rather than somebody else's board.

Keeping the token in the user-level file, outside every working copy, is deliberate: one file serves
every branch and every checkout of the project, and no clone of the project ever contains a
credential.

## Idempotence, and seeing the plan first

Every step above is idempotent. An existing repository, label or config file is **reported and
kept**, never recreated and never overwritten - so running `init` twice changes nothing and says so,
line by line, which is also the cheapest way to audit an existing tracker against this recipe.

The dry-run option performs all the reads and prints the writes it *would* make, without making
them. Use it the first time against a real instance: it is how you find out that the token cannot
create a repository before you have half a tracker.

## What belongs in the tracker - and what does not

**The tracker holds WORK STATE only.** A card is something that must be done, fixed, or decided. It
is temporary by construction: it is opened, it is worked, it is closed.

An **OS/2 fact is not work state**, and a ticket is the wrong home for one. Facts outlive the work
that found them, and a closed issue is not somewhere anyone searches. So:

- a durable OS/2 fact - a structure layout, an ordinal's contract, an error code's meaning - goes
  into the reference (`../os2ref/`), tagged with its provenance;
- a fact established by a session, with the command that re-checks it, goes into the knowledge cache
  (`know add`) - and so does a **negative** result, a "searched here, it is not there", which is
  expensive to produce and free to record;
- what stays on the board is the work: this is broken (`defect`), this needs doing (`task`), this
  question is blocking us and nobody has answered it (`knowledge-gap`).

A `knowledge-gap` card is the one that looks like an exception and is not. The card is the *open
question*; when it is answered, the answer goes to the reference or the cache and the card closes
pointing at it. If you find yourself pasting a struct layout into a comment thread, it belongs
somewhere else.

Where each kind of material lives, and how the library is laid out: `../PATHS.md`. The recording
disciplines themselves - provenance, honest failure, negative results as findings - are in
`../os2-app-dev-guide.md` and `../c-guide.md`.
