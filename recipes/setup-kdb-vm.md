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

**Keep a client on the debug pipe for the whole session.** With VirtualBox's host-pipe serial
mode, a guest whose debug pipe has **no client connected** has been seen to freeze intermittently.
Screenshots showed no progress, and breaking in found the CPU in ordinary kernel code, not idle, with
no breakpoint set; the freeze cleared the moment any client connected. The one-shot tools connect
and disconnect per command, which leaves the pipe empty between commands - exactly that condition.
So start the passthrough first and point everything at its proxy:
```sh
kdb_passthrough.py > /tmp/kdb_passthrough.log 2>&1 &
export KDB_DBGPORT=/tmp/dbgport_proxy      # or: kdb_cmd.py --socket /tmp/dbgport_proxy ...
```
With the passthrough running, a workload that had reliably triggered the freeze (an editor in a
VIO window) stopped doing so. The mechanism is not established; nothing in IBM's debugger
documentation involves modem-control lines (it specifies a three-wire null-modem cable), so this
is most likely VirtualBox's pipe behaviour rather than the debugger's protocol. [OBS - one VM,
observed repeatedly]

## Common flow
Break at the `##` prompt (BREAK.EXE) -> set breakpoints (`bp %<addr>`, or hardware write breakpoints
`ba w4 <addr>`) -> `g` to continue -> inspect at the hit (`r`, `dd`, `u`, `ln <sym>`). Symbol lookup
(`ln`) resolves user-DLL addresses only if the matching `.sym` files are installed next to the DLLs
on the VM. Full tool + command reference: `kdb-reference.md` (boot-phase strategy, hardware
breakpoints, every debugger command, the `tools/kdb/` scripting library). Underlying model:
`../os2ref/drivers.md`.
