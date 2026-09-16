# Setting up an OS/2 test target (VM + SSH)

To *run* what you build you need a real OS/2. The practical setup: an OS/2 in a VM plus SSH, so you
(or Claude) can copy files over, build (for the GCC/kLIBC path), run, and read results - all from
the command line.

## The VM
- **ArcaOS** (recommended, commercial - `../sources.md` section 4): modern OS/2, ships GCC/kLIBC and the
  Toolkit, has a working RPM/`yum`. Best if you chose GCC/kLIBC.
- An older **Warp 4.52** image also works for OpenWatcom-built apps (verify your licensing rights).
- Run it in **VirtualBox** (`virtualbox.org`). Give it a bridged/NAT network so you can SSH in.

### VM settings that actually bite [OBS-RE - observed on VirtualBox 7.1]

Two environment problems masquerade as bugs in *your* code. Both were diagnosed the expensive way.

- **Give it real memory - 64 MB is not enough to compile C++.** A VM sized for "OS/2 Warp 4" defaults
  to tiny RAM. GCC's `cc1plus` on template-heavy C++ (anything using `<memory>`/`<vector>`/`<string>`)
  wants hundreds of MB for a *single* translation unit, and on a starved box OS/2 swaps until the
  kernel itself takes a **`TRAP 000E` (page-not-present) in `OS2KRNL`** - a full-screen kernel trap
  that looks like a driver bug and is really the memory manager out of room. Symptom to recognize:
  small files compile fine, real ones trap. Raising 64 MB -> 2 GB turned a reproducible kernel trap
  into a clean 38-file build with zero warnings. (Check your OS/2 version's large-RAM guidance and
  `VIRTUALADDRESSLIMIT` in `CONFIG.SYS` before going very large.)
- **Power-cycle, don't warm-reset.** `VBoxManage controlvm <vm> reset` - and warm reboots generally -
  leave OS/2 unstable in a VM. Use a full `poweroff` and `startvm` instead:
  ```sh
  VBoxManage controlvm "<vm>" poweroff     # not: ... reset
  VBoxManage startvm  "<vm>" --type headless
  ```
  If the guest starts behaving oddly after a reset, power-cycle it before you debug anything else.

### Moving files in and out: use a shared folder, not the network [OBS-RE]

**The OS/2 TCP/IP 4.51 stack fails on large file transfers.** A big `scp`/`sftp` copy into or out of
the guest does not reliably complete - and the failure is not always loud, so a truncated file can
reach the guest looking like a successful copy and then fail at build or run time in a way that
points nowhere near the transfer. The exact threshold is not characterized here; treat "large" as
"bigger than a source file" and stop trusting the network for bulk data.

Consequences, in order of usefulness:

1. **Use a VirtualBox shared folder for anything bulky** - source trees, toolchains, `.INF` books,
   built binaries coming back out. This is the reliable path and it needs no network at all.
2. **If you must copy over SSH, verify it.** Split into chunks (~128 KB) and check each with
   `md5sum`/`cksum` on both sides. A transfer that "succeeded" is not evidence the bytes match.

   A measured instance, for calibration: pulling a **3,177,090-byte** `.exe` off the guest with
   `scp` produced a **262,144-byte** file - exactly 256 KB - and closed with `scp: Connection
   closed`. The size is suspiciously round, so a truncation here looks like a buffer boundary
   rather than a random drop, and 256 KB is well under most people's idea of "large". Source files
   (tens of KB) went over the same link all session without trouble.
3. **Keep SSH for what it is good at** - interactive commands, builds, reading output. Those are
   small and work fine.

### Installing the VirtualBox Guest Additions on OS/2

Shared folders need the Additions installed in the guest. VirtualBox ships OS/2 Additions in the
standard `VBoxGuestAdditions.iso`, under `OS2/`: `VBoxGuest.sys`, `VBoxMouse.sys`, **`VBoxSF.ifs`**
(the shared-folder file system), `VBoxService.exe`, `VBoxControl.exe`, a `gengradd.dll`, and the
kLIBC runtime DLLs they need.

Attach the ISO to the VM, then - per VirtualBox's own `OS2/readme.txt` [DOC]:

- **Prerequisite:** the guest must already be using the generic VESA `gengradd` video driver.
- Boot to an OS/2 command prompt (Alt+F1 while the white blob shows during early boot, then F2).
- Copy all the `OS2/` files into `C:\VBoxAdd`.
- **Back up `C:\os2\dll\gengradd.dll`**, then copy the Additions' `gengradd.dll` over it, and copy
  the `libc06*.dll` files into `C:\os2\dll`.
- In `C:\config.sys`: comment out `device=C:\os2\boot\mouse.sys` (prefix it `rem`), then append

  ```
  device=C:\VBoxAdd\vboxguest.sys
  device=C:\VBoxAdd\vboxmouse.sys
  ifs=C:\VBoxAdd\vboxsf.ifs
  ```

- Add `C:\VBoxAdd` to `PATH` (needed for `VBoxControl.exe`), add `C:\VBoxAdd\VBoxService.exe` to the
  start of `C:\startup.cmd`, and reboot.

There is also `VBoxOs2AdditionsInstall.exe` (run with `--do-install`; `--help` for options), aimed at
unattended installs.

> **Caveat, from the same readme:** OS/2 shared-folder support arrived in VirtualBox 6.0 and is
> described by Oracle as **beta quality**. It is still far more reliable than a large transfer over
> TCP/IP 4.51, but verify anything that matters - and prefer it for *moving* files, not as a live
> build directory.

### Mapping a shared folder to a drive letter

**Host side** - define the share (verified against VirtualBox 7.1):

```sh
VBoxManage sharedfolder add "<vm>" --name=work --hostpath=/path/on/host \
           --automount --auto-mount-point=F:
```

`--auto-mount-point` takes a **drive letter** on an OS/2 guest (`F:`), not a path.

**Guest side** - with `--automount` and `VBoxService.exe` running, the drive appears by itself.
Otherwise map it by hand:

```
VBoxControl sharedfolder use F: work      REM attach
VBoxControl sharedfolder list             REM what the host is offering
VBoxControl sharedfolder unuse F:         REM detach
```

Shares are also reachable by UNC without a drive letter - `dir \\vboxsf\work\` (also `\\vboxsvr\`,
`\\vboxsrv\`).

### Driving and observing the guest from the host [OBS-RE]

A GUI bug that compiles cleanly is only visible on screen, and VirtualBox can supply both halves of
the loop without a human at the keyboard:

```sh
VBoxManage controlvm "<vm>" screenshotpng /tmp/shot.png     # see what actually rendered
VBoxManage controlvm "<vm>" keyboardputstring "some text"   # type
VBoxManage controlvm "<vm>" keyboardputscancode 38 21 a1 b8 # Alt+F  (make/break pairs)
VBoxManage controlvm "<vm>" keyboardputscancode e0 52 e0 d2 # extended keys: E0 prefix
```

Scancodes are sent as make/break pairs (`0x38` down, `0xB8` up); extended keys - Insert, Delete,
arrows, PgUp/PgDn - take an `E0` prefix. These go to the VM directly and do not need the host window
focused. Pair each input with a screenshot: that is how an inverted axis, a swapped colour channel,
or a dialog that ignores the keyboard become obvious rather than mysterious.

**Typing a character outside ASCII on a US-layout guest** goes through Alt plus the decimal code
on the numeric keypad, sent as scancodes: Alt down `38`, then each keypad digit as a make/break
pair, then Alt up `b8`. The keypad makes are `52` (0), `4f` (1), `50` (2), `51` (3), `4b` (4),
`4c` (5), `4d` (6), `47` (7), `48` (8), `49` (9); each break is the make plus `0x80`.

```sh
VBoxManage controlvm "<vm>" keyboardputscancode 38 4f cf 50 d0 49 c9 b8   # Alt+129: u-umlaut in CP437
```

- **Generate scancode sequences from a table and check the output against a known string first.**
  A wrong scancode does not fail - it types a different character, and the test then reports on
  input you never meant to send.
- **Judge text input by the bytes that were stored, not by the screen.** Save the document and
  hexdump it: a glyph on screen does not say which encoding holds it. This is how a typed accented
  letter stored as a lone invalid byte, and as a *different* character after an 8-bit save, was
  found (`os2ref/pm-window-messaging.md`, keyboard message).
- **When comparing screenshots across builds pixel by pixel, leave out the caret's column.** The
  caret blinks; one differing column exactly as tall as the caret is the blink, not a regression.

[OBS-RE - keypad codes 1, 2 and 9 and the Alt make/break used as shown; the others are the standard
set-1 keypad makes, not individually exercised.]

### The mouse is much harder than the keyboard [OBS-RE]

**`VBoxManage controlvm` has no mouse command.** Keyboard and screenshots are first-class -
`keyboardputscancode`, `keyboardputstring`, `keyboardputfile`, `screenshotpng` - and they inject
straight into the VM with no window focus and no host display. There is no mouse equivalent
(verified against VirtualBox 7.1). So anything that needs a click has to be driven a different way,
and that asymmetry should shape your tests: **prefer keyboard paths - mnemonics, Tab traversal,
accelerators - wherever a feature can be reached both ways.** They are testable head-lessly and
mouse paths are not.

When you do need the mouse, drive the **host pointer over the VM's window** with `xdotool`:

```sh
# the VM must have a real window - NOT --type headless.
# it can live on a nested X display so it never touches your desktop:
Xvfb :99 -screen 0 1280x1024x24 & export DISPLAY=:99

# a bare Xvfb has no session, and VirtualBox refuses to start with "No active
# display server" until you tell it the session is X11.  Starting VirtualBoxVM
# directly also avoids the launcher handing off to an already-running GUI on
# another display, which is how the VM ends up on your real desktop by mistake.
XDG_SESSION_TYPE=x11 XDG_RUNTIME_DIR=/run/user/$(id -u) \
    VirtualBoxVM --startvm "<vm>" &

WID=$(xdotool search --name '<vm>.*VirtualBox' | head -1)
xdotool windowactivate "$WID"          # no window manager under Xvfb - focus explicitly
xdotool mousemove 420 300              # move first (see below)
xdotool click 1
import -window root /tmp/shot.png      # or: VBoxManage controlvm "<vm>" screenshotpng ...
```

Things that cost time if you learn them the hard way:

- **Move before you click.** Many UIs hit-test at the *last known* pointer position, so a bare
  `click` can land wherever the pointer happened to be.
- **`click` is an instantaneous down+up.** A control whose state machine needs a frame between press
  and release (drag, capture, hover) needs `mousedown 1; sleep 0.3; mouseup 1` instead.
- **A screenshot's pixels *are* guest pixels; `xdotool`'s are host-screen pixels.** This is the one
  conversion you need, and it is worth writing down once rather than re-deriving it. `screenshotpng`
  captures the guest framebuffer alone - no window chrome - so a coordinate you read off that image
  is already a guest coordinate. To click it, add the VM window's origin plus the height of the
  chrome above the framebuffer:

  ```sh
  eval $(xdotool getwindowgeometry --shell "$WID")   # sets X, Y, WIDTH, HEIGHT
  xdotool mousemove $((X + gx)) $((Y + CHROME + gy)) # gx,gy read off the screenshot
  ```

  Measure `CHROME` rather than guessing: it was **25** here (the VM window's menu bar), and
  `HEIGHT - <guest height>` gives you the total chrome - 814 - 768 = 46, i.e. a 25px menu bar on top
  and a 21px status bar below. Turn the run of a screenshot into a habit: pass `none` instead of a
  button to move the pointer *without* clicking, screenshot, and confirm the pointer is drawn where
  you meant before you commit to a click.

- **A relative PS/2 mouse is not the blocker it looks like.** The reasoning is sound - the guest owns
  its pointer, so host coordinates need not map - but measured against an OS/2 4.52 guest with a
  **PS/2 mouse and no Guest Additions installed**, the formula above hit every target it was aimed
  at: menu bar, toolbar buttons, an entry field 22px tall, and pushbuttons, repeatably across a whole
  session. While the pointer is *uncaptured*, VirtualBox positions the guest pointer from the host
  pointer's position over the window, so absolute addressing works. Install `VBoxMouse.sys` or set
  `--mouse=usbtablet` if you want to rely on exact pixels, but **verify before you conclude you are
  blocked** - the cost of checking is one `mousemove ... none` and one screenshot.
- **Check you are still driving the display your VM is on.** `xdotool` addresses a *display*, and
  `xdotool search --name ...` finds whatever window is on it - not necessarily yours. If a second
  `Xvfb` claims the same display number, or your own X server dies and is replaced, every command
  keeps succeeding and `xdotool getmouselocation` keeps reporting the pointer at exactly the
  coordinate you asked for, while the guest never moves. That is the same symptom as a dead guest
  mouse and it is not one. Confirm the display is yours before concluding anything about the guest:

  ```sh
  pgrep -a Xvfb                                  # whose server is on :99, and at what geometry?
  DISPLAY=:99 xdotool search --name VirtualBox   # is there even a VM window there?
  VBoxManage showvminfo "<vm>" --machinereadable | grep VMState
  ```

  A VM whose frontend loses its X server is left in state **`aborted`** - the equivalent of pulling
  the plug, so expect a `CHKDSK` on the next boot. `Qt WARNING: The X11 connection broke` in the
  frontend's output is the tell. **This matters most when more than one automated session shares a
  machine**: pick a display number per session rather than defaulting everyone to `:99`.

- **Suspect your arithmetic before you suspect the harness.** The one time clicks in this session
  landed somewhere unintended, the cause was subtracting the window origin from a coordinate already
  in guest space - the pointer went exactly where it was told, which the screenshot showed plainly.
  "The mouse is drifting" is a much more expensive theory than "I converted twice", so check the
  cheap one first.
- **A ~200-byte PNG means the capture failed**, not that the screen is blank - usually the guest was
  too busy to service the display. Treat screenshot size as a liveness signal.
- **Poll for a marker, not a fixed `sleep`.** A click sent before the target window exists does
  nothing at all, silently.
- **Clean up between runs** - `pkill -9 Xvfb` and remove `/tmp/.X<N>-lock` and
  `/tmp/.X11-unix/X<N>`. Leaked servers and stale lock files are the usual cause of "it worked, and
  now it doesn't."

The same `Xvfb` + `xdotool` + `import` rig drives any X11 program, so it is worth knowing for the
host-side tooling you build around the VM as well.

**Mixing the two input paths is the point.** `VBoxManage keyboardputscancode` and `xdotool` reach the
guest by completely different routes, and in this rig only the first one worked for keys - `xdotool
key Escape` aimed at the VM window never arrived, while scancodes always did. So the working split is
**`xdotool` for the mouse, `VBoxManage` for the keyboard**, and there is no need to make either one
do both.

**Injected keystrokes go to whatever the guest thinks has focus, which is not always what you just
opened.** A PM *modeless* dialog - `WinLoadDlg` + `WinShowWindow`, the usual Find/Replace shape - is
created without being activated: it appears on screen with a **grey** title bar while the frame
behind it keeps the **blue** one and keeps the focus. Type into that and the letters never reach the
dialog. Worse, they are not merely lost: a bare letter arriving at a frame is offered to the menu as
a **mnemonic**, so typing `count` at an unfocused dialog opened the Launch menu's `~Command...` item
and left `ount` sitting in the Run dialog it spawned. Nothing errored, and the screenshot looked like
the application had corrupted itself.

Two habits make this a non-event. **Read the title bar colour in your screenshot** - it tells you
where the keys are about to go, before you send any. And **click a control in the dialog first**;
that both activates it and puts the caret where you want the text. Both are one screenshot's worth of
work, against a failure mode that otherwise reads as a bug in the application under test.

### Test data written on the guest gets CRLF translation [OBS-RE]

Creating a fixture with shell redirection on OS/2 applies text-mode translation **on top of**
whatever you wrote, so an explicit `\r\n` becomes `\r\r\n`:

```sh
printf "line one\r\nline two\r\n" > test.txt    # you asked for CRLF
od -c test.txt                                    # you got \r \r \n
```

A text editor loading that file renders a blank line between every real line - which looks exactly
like a line-ending bug in the code under test. **Verify a fixture with `od -c` before believing what
it makes your program do.** Write `\n` only and let the platform translate, or build the file on the
host and copy it over.

The general rule (`START-HERE.md` section 3) is usually applied to *probes*; it applies to **test data**
just as hard. A wrong fixture produces a confident, wrong diagnosis in code that is working fine.

### Read colours out of a screenshot with code, not with your eyes

A screenshot is the right instrument for a GUI bug, but it is a lossy one: it is scaled, it may be
recompressed, and small anti-aliased glyphs pick up the colour of whatever is behind them. Judging a
*colour* by looking is unreliable in a way that judging *layout* is not.

During a syntax-highlighting change, one line of a three-line comment appeared to keep its old colour
while the other two changed - a convincing partial-restyle bug. It was not one. `SCI_GETSTYLEAT`
reported the same style number for all three, and sampling the image settled it:

```sh
python3 -c "
from PIL import Image
im = Image.open('shot.png').convert('RGB')
d = {}
for x in range(100, 700):
    p = im.getpixel((x, 355))
    if sum(p) < 600:           # skip near-white background
        d[p] = d.get(p, 0) + 1
print(sorted(d.items(), key=lambda kv: -kv[1])[:3])
"
```

All three lines were `(255, 0, 0)`. The rendering was correct and the *reading* of the screenshot was
wrong. When a screenshot suggests a colour bug, sample the pixels before changing any code - and
prefer a labelled render test ("this bar MUST be pure red") over judging a hue by eye. [OBS-RE]

### A program launched over SSH is a DETACHED process - some APIs cannot work there

This one silently invalidates whole test runs. An `sshd`-spawned process on OS/2 is **detached**:
IBM's definition is a program that runs in the background, runs asynchronously from its parent, and
**does not use the keyboard, mouse, or screen**. That is exactly an SSH session's child, and
`nohup ... &` guarantees it.

The consequence is not subtle. **`DosStartSession` returns `ERROR_SMG_INVALID_CALL` (418) when
called from a detached process** - documented under *DosStartSession - Remarks* in the Control
Program reference - "regardless of whether the session is to be started in the foreground or in the
background." So any feature that launches another program cannot be exercised over SSH at all, and
the failure looks like a bug in your `STARTDATA`. It is not: the same binary works when started from
a real session.

Backgrounding on the *host* side (`ssh vm 'exec ./app'` run in your own background) does not help -
the guest process is still an `sshd` child with no session.

**To test session-manager or desktop-integration behaviour, drive a real session on the guest:**
switch to an on-screen `CMD.EXE` with injected `Alt+Esc`, type the command with
`keyboardputscancode`, and take screenshots as usual. It is slower than SSH and it is the only way
these calls can succeed.

More generally: **the way you launch the program under test is part of the test.** Process type,
session type and detachment are all inherited from the launcher, and each of them gates a different
part of the API. [OBS-RE - a Launch menu was debugged three times over before the harness, not the
code, turned out to be the problem.]

### OS/2 `ps` is not the POSIX one

`ps ax` is rejected, and the COMMAND column shows the program name **without** its `.exe`. So the
habitual invocations both lie:

```sh
ps ax | grep myapp        # error - reads as "not running"
ps | grep myapp.exe       # no match - reads as "not running"
ps | awk '$5=="myapp"'    # correct
```

Both wrong forms return nothing, which is easy to read as "the app exited" when it is running fine -
the general trap in `START-HERE.md` section 3, in its most common local form.

`pkill` has the same problem from the other side: it matches nothing and **exits quietly**, so a
test-rebuild loop that starts with `pkill myapp` silently leaves the old copy running. Read the PID
out of `ps` and `kill -9` it. The symptom of getting this wrong is in "A running `.EXE` is locked" below.

### ...and `kill` does not always work [OBS-RE]

OS/2's `DosKillProcess` is **cooperative**: the target is asked to exit. Native OS/2 programs oblige;
ported Unix programs frequently do not - a shell spinning in a tight loop absorbs `kill -9`
indefinitely. There is no `SIGKILL` guarantee without kernel help.

For a test loop that spawns such programs, install a **ring-0 killer** (Hobbes carries several, e.g.
`hkilldd.sys` plus a `hardkill.exe` front end, enabled with a `DEVICE=` line in `CONFIG.SYS`).
Without one, a single runaway child pegs a core, and on a VM that starves everything else: SSH
sessions start dropping and builds fail in ways that look like network or toolchain faults. **If the
guest suddenly turns flaky, look for a spinning process before debugging anything else.**

Two `DosKillProcess` details that bite test harnesses:

- **`action` 0 is `DKP_PROCESSTREE`** - it terminates the target *and every descendant*
  (`DKP_PROCESS` = 1 kills only the named process) [DOC-IBM - bsedos.h; see
  `../os2ref/process-thread.md`]. A harness whose cleanup does `DosKillProcess(0, child)` will
  therefore kill the child's whole subtree on every exit path - which **masks
  signal-delivery tests**: "did my `^C` kill the grandchildren?" passes vacuously because
  cleanup killed them regardless [OBS-RE: a strict-libc trace showed the grandchildren dying
  of the cleanup's SIGTERM while the signal under test had never been sent at all]. Verify
  the observable *before* cleanup runs - park the harness at a checkpoint after the action
  and inspect `ps` there, not after it exits.
- kLIBC delivers an incoming `DosKillProcess` as **SIGTERM** on the receiving side
  (`XCPT_SIGNAL`/`XCPT_SIGNAL_KILLPROC` -> `SIGTERM`; mapping table in
  `../os2ref/klibc-runtime-glue.md` section 4.2, confirmed in a live trace [OBS-RE]) - so in a
  strict/log-flavor libc trace a cooperative kill shows up as `iSignalNo=15`, useful for
  telling "my test's signal" from "the harness's cleanup" after the fact.

### A running `.EXE` is locked - rebinding resources fails

OS/2 holds an executable open while it runs, so re-binding resources into a live program fails:

```
Error! E007: Error renaming temporary file "__RCTMP8043__.tmp" to "myapp.exe": Permission denied.
```

`wrc` reports this and **still prints nothing else**, so a build script that only greps for the word
"error" in the compile step will sail past it and you will test the *previous* binary - a
particularly nasty variant of the honest-failure problem, because everything downstream looks fine
and simply reflects stale code. Kill the running copy before re-binding, and check that the `.exe`
timestamp actually moved.

**The lock is narrower than "you cannot build while it runs", though** [OBS-RE]. Measured on Warp
Server with an app running from a shared-folder drive: the *compile and link* wrote
`/tmp/build/app.exe` fine and reported success, and `wrc` re-bound resources into that same file
fine  -  what failed was **copying the finished binary over the running one**:

```
cp: cannot create regular file 'F:/proj/app.exe': Permission denied
```

So the failure can surface a step later than expected, in the deploy rather than the build. Check
the exit status of the *copy*, not only of the build, and confirm the destination's size or
checksum changed. Two files with the same name in different directories is the situation that makes
this confusing: one is locked, the other is not.

### Harness discipline for anything that spawns a program [OBS-RE]

Each of these was paid for with a runaway that had to be killed by hand:

- **Never do a bare blocking `read()` on a pipe/pty you own.** If the child produces nothing you
  block forever, never reach your cleanup, and leak *both* processes. Use `select()` with a timeout
  plus an overall deadline.
- **Kill the child on every exit path**, including the timeout path - and see above: a cooperative
  kill may not suffice.
- **A timeout on your side does not stop work on the guest.** Killing an `ssh` client leaves the
  remote command running. After any aborted run, list processes on the guest and clean up explicitly.

And one rule that is not about processes: **a test that cannot distinguish the terminal's own echo
from the program's output is not a test.** A tty echoes what you write to it, so "the text came back"
proves nothing about whether the program ever read it. Make the program emit something only it could
produce, or disable echo in the harness. (Getting this wrong produces confident false PASSes for as
long as you care to run it.)

## Cloning a template VM: clone, use, discard

Once a VM is installed and configured the way you want it, stop treating it as *the* test machine.
Snapshot it as a **template** and make every test run a throwaway clone. A run that corrupts the
system, wedges the desktop or leaves a half-installed driver behind then costs one `unregistervm`
instead of a reinstall, and two runs cannot contaminate each other.

**Full clones, never linked.** A linked clone keeps a reference to the parent's disk chain, so the
template cannot be improved while any clone exists without corrupting the clones - and the whole
point of a template is that it keeps improving. A full clone also flattens its disks to base type,
which is what makes the offline mount below possible at all: a snapshot chain is not directly
mountable.

```sh
TEMPLATE="my-os2-template"          # the VM you snapshotted
SNAP="baseline"                     # the snapshot to clone from
CLONE="os2test-$$"                  # name it after the run - the name IS the tracking

VBoxManage clonevm "$TEMPLATE" --snapshot "$SNAP" --mode machine --name "$CLONE" --register
```

**If the template has a debug serial port, repoint it before starting the clone.** The clone
inherits the host pipe path (`uartmode2 server /tmp/dbgport`), so two clones - or a clone and the
template - fight over the same socket:

```sh
VBoxManage modifyvm "$CLONE" --uartmode2 server "/tmp/dbgport-$CLONE"
# ...and export KDB_DBGPORT / KDB_REAL_DBGPORT to match if you drive the kernel debugger
# (recipes/setup-kdb-vm.md).
VBoxManage startvm "$CLONE" --type headless
```

**Find the clone by MAC, not by a remembered address.** `clonevm` regenerates the MAC, so the clone
takes its own DHCP lease:

```sh
MAC=$(VBoxManage showvminfo "$CLONE" --machinereadable \
      | sed -n 's/^macaddress1="\(..\)\(..\)\(..\)\(..\)\(..\)\(..\)"/\1:\2:\3:\4:\5:\6/p')
NET=${NET:-192.168.0}                           # set this to YOUR LAN prefix
for j in $(seq 1 254); do (ping -c1 -W1 $NET.$j >/dev/null 2>&1 &); done; sleep 3
IP=$(ip neigh | grep -i "$MAC" | awk '{print $1}' | head -1)
```

**ssh to a clone with host-key checking off.** Every clone carries the template's host keys and
clones reuse DHCP addresses, so `known_hosts` reports mismatches that read like MITM warnings:

```sh
ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "os2@$IP"
```

**Discard when the run is done:**

```sh
VBoxManage controlvm "$CLONE" poweroff
VBoxManage unregistervm "$CLONE" --delete
ssh-keygen -R "$IP"
```

### Bulk data in and out: mount the clone's JFS disk offline [OBS-RE]

When ssh or the shared folder is awkward - bulk data, or files carrying extended attributes - power
the clone **off** and mount its disk on the host. Linux reads OS/2 JFS.

```sh
sudo modprobe nbd max_part=8 ; sudo modprobe jfs
sudo qemu-nbd --connect=/dev/nbd1 -f vdi "$HOME/VirtualBox VMs/$CLONE/$CLONE-disk1.vdi"
sudo mount -t jfs /dev/nbd1p5 /mnt/os2d        # partition type 0x35 = OS/2 JFS
# ... work ...
sudo sync; sudo umount /mnt/os2d; sudo qemu-nbd --disconnect /dev/nbd1
```

Three traps, each of which costs a round if you meet it cold:

- **The JFS volume is usually `p5`, a logical partition inside an extended partition** (`p1` is the
  extended container), not `p1`.
- **`qemu-nbd --read-only` sets a STICKY read-only flag on the nbd device.** After one read-only
  attach, `/sys/block/nbdN/ro` stays `1`, and every later mount of that device is silently forced
  read-only: `mount` prints *"source write-protected, mounted read-only"* and still **exits 0**. Use
  a different `/dev/nbdN`, and believe the warning rather than the exit status.
- **`getfattr` may not be installed.** `python3 -c "import os,sys; print(os.listxattr(sys.argv[1]))" FILE`
  needs nothing extra.

### Extended attributes survive the round trip [OBS-RE]

Measured both ways on a JFS volume, not assumed. It works because JFS came *from* OS/2: the Linux
driver is the same lineage rather than a reimplementation, and it ships a dedicated OS/2 attribute
handler (`jfs_os2_xattr_handler` and the `os2.` namespace prefix, `fs/jfs/xattr.c`).

| step | result |
|---|---|
| OS/2 `SysPutEA("D:\eatest.txt","TESTEA","HELLO-FROM-OS2")` | rc=0 |
| Linux `os.listxattr` on that file, disk mounted offline | `os2.TESTEA = b'HELLO-FROM-OS2'` |
| Linux writes a new file and `os.setxattr(..., "os2.LINUXEA", ...)` | ok |
| Linux adds another EA to the **OS/2-created** file | ok, the existing EA intact |
| OS/2 `SysGetEA` after boot | all three EAs readable, values unchanged |

**Also worth knowing:** kLIBC stores unix metadata as OS/2 EAs, so a kLIBC-created file carries
`os2.UID os2.GID os2.MODE os2.INO os2.RDEV os2.GEN os2.FLAGS`, each value prefixed with the binary
EA type marker (`\xfe\xff`). An EA written by `SysPutEA` has no such prefix. "The EAs on this file"
is therefore not a homogeneous set - check the prefix before parsing a value.

**Bounds, so this is not over-read:** file data and EAs are proven, in both directions. ACLs and
LVM-level metadata are **not** tested. And this says nothing about HPFS or FAT volumes, where Linux
has no EA support at all.

## SSH (build + run over the wire)
Install an SSH server on the VM (OpenSSH is in the netlabs RPM repos: `yum install openssh`).
Generate **your own** keys and credentials - this kit ships none.
```sh
ssh os2@<vm-ip> 'echo hello from OS/2'
scp hello.exe os2@<vm-ip>:/home/os2/          # push a build
```
Server-setup specifics (they trip people up):
- After editing the password files (`/@unixroot/etc/passwd` + `master.passwd`), rebuild the password
  database with **`pwd_mkdb`** - sshd reads the compiled `pwd.db`/`spwd.db`, not the text files.
- The account's home/shell come from that db; the login shell is typically **`sh.exe`** (ash).
- OS/2 environment variable **names are matched uppercase** - set the user via `SET USER=OS2`
  (uppercase `USER`), not `set user=`.
- Put your public key in the account's `.ssh/authorized_keys` for key auth (recommended).

Gotchas (OS/2/kLIBC SSH):
- Paths use `/@unixroot/...` and drive letters (`C:/...`).
- **Console programs' stdout/stderr may not come back over a no-PTY SSH session** - redirect to a
  file and read it back: `ssh os2@vm 'prog.exe >out.txt 2>&1'; ssh os2@vm 'cat out.txt'`.
- Set `BEGINLIBPATH` so the app finds non-standard DLLs: `export BEGINLIBPATH=/path/to/dlls`.

## Scripting on the VM - CMD.EXE is limited; prefer sh/REXX
The kLIBC `sh.exe` (ash) over SSH is the easy path - but **it is ash, not bash** [OBS-RE].
`${PIPESTATUS[0]}` fails outright with

```
sh.exe: 6: Bad substitution
```

and that aborts the rest of the remote script, so a build step you meant to check silently never
runs. Since the whole point of a remote build is capturing the compiler's exit status, redirect and
read `$?` directly instead of piping:

```sh
g++ ... -o out.o > /tmp/build.log 2>&1
echo "EXIT=$?"
tail -20 /tmp/build.log
```

The same trap applies **on the host side**: `scp ... | tail` reports `tail`'s status, not the
transfer's, so a failed copy reads as success. Never take an exit code through a pipe when it is
the thing you are testing.

If you must use the native OS/2 `CMD.EXE` (a
`.cmd` batch), it is **not** the NT `cmd.exe` - none of these work: `SETLOCAL`/`ENDLOCAL`,
`CALL :label` internal subroutines, `%~dp0` (tilde arg modifiers), `2>&1` redirection, single-line
`IF ... ELSE`. `del *` prompts for confirmation, and a `>nul` guard doesn't suppress errors the NT way
(use `md foo 2>nul`). For anything nontrivial on OS/2, script in **REXX** (the system scripting
language) or a Makefile - not CMD.EXE.

## Diagnosing a run
OS/2 logs unhandled exceptions and load failures to **`C:\POPUPLOG.OS2`** (kernel-written on each
fault). Read it after a crash:
```sh
ssh os2@<vm-ip> 'cat C:/POPUPLOG.OS2' | tail -40
```
It gives the process, the fault type (`SYS3175` access violation, `SYS2070` bad-ordinal/demand-load),
the failing address, and for load failures the missing `MODULE.ordinal`. Map that back with
`inspect-a-binary.md`.
