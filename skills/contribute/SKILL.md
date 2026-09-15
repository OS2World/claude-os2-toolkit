---
name: contribute
description: Write an OS/2 finding back into the claude-os2-toolkit source - a fact for os2ref/, a procedure for recipes/, a tool fix - with provenance, in your own words, de-identified, and committed locally. Use when the user says "update the toolkit with what we found", "add this to os2ref", "record this lesson in the kit", or when the setup skill finds work stranded in an old copied kit.
---

# Contribute to the toolkit

## Where the edit goes - never the installed copy

The toolkit source is the user's git checkout of claude-os2-toolkit. Find it in this order:

1. `os2-lib role os2-toolkit-source` - the checkout, filed in the OS/2 library;
2. `${CLAUDE_PLUGIN_ROOT}` itself, if it is a git checkout of the toolkit (a plugin installed from a
   local directory, or a `claude --plugin-dir` session) rather than an installed copy in the plugin
   cache;
3. otherwise ask the user where their clone is, and offer to file it so this is automatic next time:
   ```sh
   os2-lib new source claude-os2-toolkit-checkout --title "claude-os2-toolkit (my checkout)" \
       --kind source-tree --licence own --mode link --original <path> --provides os2-toolkit-source
   ```

Confirm it before touching anything:

```sh
git -C <checkout> remote -v                                  # a claude-os2-toolkit clone
grep '"name"' <checkout>/.claude-plugin/plugin.json          # "os2-toolkit"
git -C <checkout> status -sb                                 # what is already uncommitted there
```

Never edit an installed copy in the plugin cache: the next update overwrites it.

## The rules

Read `<checkout>/CONTRIBUTING.md` **in full** (`wc -l` it; a `head` is not a read). They are
checkable rules, and the one legal claim the project rests on - it redistributes no IBM or
third-party material - depends on them. Then follow its final section, *"For a Claude session
updating the toolkit"*: place it (section 8), tag and cite every claim (section 2), restate rather
than paste (section 1), strip machine paths and project identifiers - including from anything the
user pasted (sections 4-5), use the lessons-learned shape (section 6), run the section 7 checklist
and the commands you documented, and put the section 9 affirmation in the commit message.

A claim you cannot source is left out or marked `[unverified]`. A plausible unsourced fact is the one
failure this corpus cannot absorb.

## Commit, do not push

- Stage only the files you changed; leave unrelated uncommitted work in the checkout alone.
- Commit locally. **Do not `git push`** unless the user explicitly asks in this conversation.
- Make the running plugin see the change:
  ```sh
  claude plugin marketplace update claude-os2-toolkit
  claude plugin update os2-toolkit@claude-os2-toolkit
  ```
  then tell the user to run `/reload-plugins` (or restart the session).
