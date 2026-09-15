# Kernel debugger (KDB) - for driver / low-level work

Only needed if you're writing a device driver, IFS, or otherwise debugging at the kernel level. A
normal app never needs this. The `tools/kdb_*` scripts drive the OS/2 **kernel debugger** in a VM
over a serial pipe.

## VM setup (VirtualBox)
1. Install the OS/2 **debug kernel** in the VM (the debug build of `OS2KRNL`, from the DDK/ArcaOS).
2. VirtualBox -> the VM -> Serial Port 1: **Host Pipe**, path e.g. `/tmp/dbgport`, *not* "connect to
   existing pipe" (VBox creates it).
3. To break in early, add `RUN=C:\OS2\BREAK.EXE` before `PROTSHELL=` in `CONFIG.SYS` (it executes an
   `INT3` and stops at the debugger prompt during boot).

## Driving it (from Linux)
```sh
export KDB_VM_NAME="os2kdb"
kdb_cmd.py --start-vm  # start + wait for the debugger prompt
kdb_cmd.py "r"         # registers
kdb_cmd.py ".lm"       # loaded modules
kdb_interactive.py     # interactive session (.regs/.stack/.bp/...)
kdb_hang_triage.py     # diagnose a frozen system (never reboot first)
```
`tools/kdb/` is the reusable Python library (connection/parser/session) if you script your own.

## Common flow
Break at the `##` prompt (BREAK.EXE) -> set breakpoints (`bp %<addr>`, or hardware write breakpoints
`ba w4 <addr>`) -> `g` to continue -> inspect at the hit (`r`, `dd`, `u`, `ln <sym>`). Symbol lookup
(`ln`) resolves user-DLL addresses only if the matching `.sym` files are installed next to the DLLs
on the VM. Full tool + command reference: `kdb-reference.md` (boot-phase strategy, hardware
breakpoints, every debugger command, the `tools/kdb/` scripting library). Underlying model:
`../os2ref/drivers.md`.
