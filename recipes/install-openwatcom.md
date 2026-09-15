# Installing OpenWatcom (Linux host, cross-compiling to OS/2)

OpenWatcom builds OS/2 binaries **from Linux** - no OS/2 needed to compile. Get it from
`../sources.md` section 2 (`openwatcom.org` for 1.9, or the maintained `open-watcom.github.io` v2 fork).

## Install
The Linux distribution ships a `binl/` directory of ELF host binaries (`wcc386`, `wlink`, `wrc`, ...)
plus the `h/` (headers) and `lib*/` (libraries) trees, including OS/2-specific ones (`h/os2`).

Set the environment (adjust the path to where you unpacked it):
```sh
export WATCOM=/opt/watcom
export PATH="$WATCOM/binl:$PATH"
export INCLUDE="$WATCOM/h;$WATCOM/h/os2"     # both dirs, ';'-separated: os2.h is in h/os2/
export EDPATH="$WATCOM/eddat"
export WIPFC="$WATCOM/wipfc"                  # for INF/help authoring (optional)
```
(Add these to your shell profile, or a project `env.sh` you `source`.)

## Verify
```sh
wcl386                    # no args: prints the usage banner + version
echo 'int main(void){return 0;}' > t.c
wcl386 -bt=os2 -l=os2v2 t.c -fe=t.exe && ls -l t.exe   # produced an OS/2 LX .exe
```
`file t.exe` should show it's not a Linux ELF (it's an OS/2 LX module). Confirm with
`lx_export.py t.exe`.

## Notes
- **C standard:** OpenWatcom 1.9 is **not full C99** - avoid mid-block declarations, VLAs, and some
  `<stdint.h>`/`<complex.h>` features, or use the v2 fork. Write conservative C.
- **Resources:** compile `.rc` with `wrc -r foo.rc` then bind with `wrc foo.res foo.exe`.
- **Drivers:** OpenWatcom is also the path for 16-bit device drivers (with the DDK); different link
  flags and a driver `.def` - see `../os2ref/drivers.md`.
- You still need an OS/2 target to *run* the result - `setup-test-vm.md`.
