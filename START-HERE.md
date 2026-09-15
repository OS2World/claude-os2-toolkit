# START HERE

This kit is a **Claude Code plugin** (`os2-toolkit`). Its instructions to Claude live in its skills:

- [`skills/os2-dev/SKILL.md`](skills/os2-dev/SKILL.md) - what the kit contains, the disciplines,
  and how to work. Loaded for any OS/2 task.
- [`skills/setup/SKILL.md`](skills/setup/SKILL.md) - wire a project up: inventory the machine,
  interview the user, write the project's `CLAUDE.md`.
- [`skills/contribute/SKILL.md`](skills/contribute/SKILL.md) - write a finding back into the kit.

**With the plugin installed** (see [`README.md`](README.md)): in the project, run
`/os2-toolkit:setup` - or just say "I'm making an OS/2 program".

**Without the plugin** (a plain clone someone pointed you at): read `skills/setup/SKILL.md`, then
`skills/os2-dev/SKILL.md`, and follow them, reading `${CLAUDE_PLUGIN_ROOT}` as this checkout's root
and using `bin/os2-lib` for the OS/2 library (`PATHS.md`; `OS2_LIBRARY` sets where it lives). Put this checkout's `bin/` on
`PATH` so the tools resolve by name. Write the project's `CLAUDE.md` pointers as paths into this
checkout instead of plugin skill names.
