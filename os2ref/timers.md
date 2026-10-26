# OS/2 Timer and Time Services

The application-visible timer and time surface of the OS/2 Control Program: periodic and
one-shot interval timers that post an event semaphore, a high-resolution free-running counter
for fine-grained measurement, and the wall-clock date/time services. All of these are
`Dos*` APIs declared under `INCL_DOSDATETIME` / `INCL_DOSPROFILE`; the periodic timers are
built on the same 32-bit event semaphores used for general inter-thread signalling, and their
resolution is bounded by the system clock tick (a much coarser unit than the high-resolution
counter). The periodic clock tick itself and the millisecond counters it maintains are part
of the InfoSeg / kernel clock and are documented in `infoseg.md` and `kernel-services.md`;
this reference covers the application call surface and refers to those for the tick.

Provenance: **[DOC-IBM]** OS/2 Toolkit 4.5 headers `bsedos.h`, `basedef.h`, `os2def.h`,
`bseerr.h`, `bseord.h` (prototypes, structures, error codes, ordinals). Semantic notes on
tick granularity cross-reference `infoseg.md` / `kernel-services.md`.

## Symbol summary [DOC-IBM - `bsedos.h`]

| Symbol | Purpose |
|---|---|
| `DosStartTimer` | Start a **periodic** interval timer; posts an event semaphore every interval |
| `DosAsyncTimer` | Start a **one-shot** timer; posts an event semaphore once after the interval |
| `DosStopTimer` | Cancel a running timer (periodic or one-shot) by its handle |
| `DosTmrQueryFreq` | Query the high-resolution timer's frequency (ticks per second) |
| `DosTmrQueryTime` | Query the current high-resolution 64-bit timer count |
| `DosGetDateTime` | Read the current wall-clock date/time into a `DATETIME` |
| `DosSetDateTime` | Set the system wall-clock date/time from a `DATETIME` |

Compatibility aliases are `#define`d for the interval timers: `DosTimerStart` ->
`DosStartTimer`, `DosTimerAsync` -> `DosAsyncTimer`, `DosTimerStop` -> `DosStopTimer`
[DOC-IBM - `bsedos.h`].

## The interval timers [DOC-IBM - `bsedos.h`]

An interval timer counts down a millisecond period and, when it elapses, **posts an event
semaphore** the caller supplies. The caller waits on that semaphore (with the ordinary
event-semaphore wait) to be woken; the timer subsystem never calls back into the caller
directly. A **periodic** timer (`DosStartTimer`) re-arms and posts on every interval until
stopped; an **asynchronous / one-shot** timer (`DosAsyncTimer`) posts exactly once and then
retires. Both return a handle used to cancel the timer with `DosStopTimer`.

```c
typedef LHANDLE HTIMER;          /* timer handle */
typedef HTIMER *PHTIMER;

APIRET APIENTRY DosStartTimer(ULONG msec, HSEM hsem, PHTIMER phtimer);   /* periodic  */
APIRET APIENTRY DosAsyncTimer(ULONG msec, HSEM hsem, PHTIMER phtimer);   /* one-shot  */
APIRET APIENTRY DosStopTimer(HTIMER htimer);
```

[DOC-IBM - `bsedos.h:2118-2129`; `HTIMER` is `LHANDLE`, i.e. `unsigned long` per
`os2def.h:76`.]

| Parameter | Type | Meaning |
|---|---|---|
| `msec` | `ULONG` | Interval in **milliseconds** - the period between posts (periodic) or the delay before the single post (one-shot) |
| `hsem` | `HSEM` | Handle of the **event semaphore** to post when the interval elapses |
| `phtimer` | `PHTIMER` | Out: receives the timer handle used to stop it |

`HSEM` is the generic semaphore-handle type `typedef VOID *HSEM;` [DOC-IBM - `os2def.h:251`];
for these APIs it is an event-semaphore handle previously created by the caller. The waiting
thread blocks on that semaphore and wakes each time the timer posts it.

**Resolution.** The `msec` interval is a request; actual delivery is quantized to the system
**clock tick**, so a timer cannot resolve finer than one tick and short intervals are rounded
up to a tick boundary. The tick interval is queryable at run time - `SIS_ClkIntrvl` in the
**global** InfoSeg (units of 0.0001 s) and `QSV_TIMER_INTERVAL` via `DosQuerySysInfo` (tenths
of a millisecond); see `infoseg.md`. *(Corrected 2026-08-26, Rule 1.7: this said*
***local*** *InfoSeg. `SIS_*` is `struct InfoSegGDT` - the GDT-addressed,
system-wide segment - per [DOC-IBM DDK `base/h/infoseg.h`],
and `infoseg.md` section "Global Information Segment" already had it right. The two
are not interchangeable: the local InfoSeg is per-process and has no timer
field at all.)* **The two are also not independent**: the QSV index is a *copy*
of the GIS field, made once at boot - see `infoseg.md`, "How `DosQuerySysInfo`
is answered". Measured on a Warp 4.5-family machine, both read **310**. The default tick is on the order of tens of milliseconds
(nominally ~32 ms) [DOC], which is far coarser than the high-resolution timer below - code
needing sub-tick precision uses `DosTmrQueryTime`, not the interval timers.

## The high-resolution timer [DOC-IBM - `bsedos.h`]

For fine-grained elapsed-time measurement, OS/2 exposes a monotonic, free-running 64-bit
counter independent of the coarse system tick. Two calls describe it: one returns its
frequency (how many counts occur per second), the other returns the current count. Elapsed
time is `(t2 - t1) / freq` seconds. These are declared under `INCL_DOSPROFILE`.

```c
APIRET APIENTRY DosTmrQueryFreq(PULONG  pulTmrFreq);   /* counts per second   */
APIRET APIENTRY DosTmrQueryTime(PQWORD  pqwTmrTime);   /* current 64-bit count */
```

[DOC-IBM - `bsedos.h:3088-3090`.]

| Parameter | Type | Meaning |
|---|---|---|
| `pulTmrFreq` | `PULONG` | Out: timer frequency in counts (ticks) per second |
| `pqwTmrTime` | `PQWORD` | Out: current free-running timer value, 64-bit |

The 64-bit count is a `QWORD`, a two-`ULONG` little-endian pair [DOC-IBM - `basedef.h:244-249`,
identically `os2def.h:153-158`]:

```c
typedef struct _QWORD          /* qword */
{
   ULONG   ulLo;               /* low  32 bits (offset 0x00) */
   ULONG   ulHi;               /* high 32 bits (offset 0x04) */
} QWORD;                       /* 8 bytes */
typedef QWORD *PQWORD;
```

The frequency is fixed for the life of the system, so a caller reads it once with
`DosTmrQueryFreq` and thereafter only reads `DosTmrQueryTime` around the interval it wants to
measure.

## Wall-clock date and time [DOC-IBM - `bsedos.h`]

`DosGetDateTime` and `DosSetDateTime` read and set the system's real-time clock through a
single `DATETIME` structure. They are common (available without `INCL_DOSDATETIME` unless
`INCL_NOCOMMON` is defined).

```c
APIRET APIENTRY DosGetDateTime(PDATETIME pdt);
APIRET APIENTRY DosSetDateTime(PDATETIME pdt);
```

[DOC-IBM - `bsedos.h:2104-2106`.]

### `DATETIME` structure [DOC-IBM - `bsedos.h:2090-2101`]

```c
typedef struct _DATETIME       /* date */
{
   UCHAR   hours;              /* offset 0x00 */
   UCHAR   minutes;            /* offset 0x01 */
   UCHAR   seconds;            /* offset 0x02 */
   UCHAR   hundredths;         /* offset 0x03 */
   UCHAR   day;                /* offset 0x04 */
   UCHAR   month;              /* offset 0x05 */
   USHORT  year;              /* offset 0x06 */
   SHORT   timezone;           /* offset 0x08 */
   UCHAR   weekday;            /* offset 0x0A */
} DATETIME;                    /* 11 bytes    */
typedef DATETIME *PDATETIME;
```

| Offset | Field | Type | Meaning |
|---|---|---|---|
| 0x00 | `hours` | `UCHAR` | Hour of day |
| 0x01 | `minutes` | `UCHAR` | Minute |
| 0x02 | `seconds` | `UCHAR` | Second |
| 0x03 | `hundredths` | `UCHAR` | Hundredths of a second |
| 0x04 | `day` | `UCHAR` | Day of month |
| 0x05 | `month` | `UCHAR` | Month |
| 0x06 | `year` | `USHORT` | Year (full 4-digit) |
| 0x08 | `timezone` | `SHORT` | Timezone as a signed offset (minutes) from GMT |
| 0x0A | `weekday` | `UCHAR` | Day of week |

The structure is 11 bytes: four one-byte time fields, two one-byte date fields, a two-byte
year, a signed two-byte `timezone`, and a one-byte `weekday`. (`bsedos.h` states no size and
declares the structure outside any `pack(1)` block; the 11 bytes is the length the kernel copies
from the caller [OBS-RE - `w_SetDateTime`]. The `/* 11 bytes */` comment in the listing above is
ours, not the header's.) On `DosGetDateTime` the kernel
fills all fields; `DosSetDateTime` sets the clock from the caller-supplied fields. The same
per-tick time-of-day breakdown is mirrored in the local InfoSeg
(`SIS_HrsTime`/`SIS_MinTime`/`SIS_SecTime`/`SIS_HunTime`); see `infoseg.md`, which a program
can read directly to avoid a call.

**Field ranges and validation on set** [DOC - EDM2 "DosSetDateTime (OS/2 1.x)"]. `DosSetDateTime`
validates the supplied fields and rejects an out-of-range or impossible value with
`ERROR_TS_DATETIME` (327). The accepted ranges are `hours` 0-23, `minutes` 0-59, `seconds` 0-59,
`hundredths` 0-99, `day` 1-31, `month` 1-12, `year` 1980-2079, and `timezone` ~~-720...720~~
**-780...780** on Warp 4.5 (see *Measured behaviour* below; the 1.x text says +/-720). The day
is additionally checked against the month and year - leap years included - so an impossible date
(e.g. 30 February) is rejected. `weekday` is **ignored on set**: the kernel recomputes it from the
date rather than trusting the caller's value.

**`timezone` sign convention** [DOC - EDM2 "DosSetDateTime (OS/2 1.x)"]. The value is minutes
**west** of UTC: **positive** when the local zone is earlier than UTC (Eastern Standard Time =
300, i.e. five hours earlier), **negative** when later (Western Europe / GMT+1 = -60). (This
clarifies the sign of the "signed offset from GMT" noted in the field table above; the header
type is unchanged.)

### Measured behaviour - Warp Server for e-business 4.50, rev 14.089 (SMP) [OBS]

Captured 2026-09-29 by paired 32-bit and 16-bit probes run on a real system; the kernel
checks are those of `w_SetDateTime` [OBS-RE - kernel 14.104a SMP].

- **Validation** matches the list above, with the timezone range **+/-780** (+/-781 -> 327). The
  checks run in order: time fields, timezone, then the date against the 1980-2079 calendar
  [OBS-RE - the order is the kernel's; single-field captures cannot show it].
- **`weekday` is not validated** on set (9 is accepted) and a later `DosGetDateTime` returns
  the computed day of week.
- **A set `timezone` is kept**: a later `DosGetDateTime` returns it, and it appears in the
  Global InfoSeg. The kernel writes it to the InfoSeg itself, before the clock-device write
  [OBS-RE].
- **Bad (NULL) `pdt` - the two widths are mirror images**, and 87 appears on neither page:

  | | 32-bit | 16-bit |
  |---|---|---|
  | `DosGetDateTime` | caller ends by unhandled exception (`TC_EXCEPTION`) | returns 87 |
  | `DosSetDateTime` | returns 87 | caller traps (`TC_TRAP`, #GP) |

### The clock device (`CLOCK$`) [DOC-IBM - DDK I/O reference "Physical CLOCK$ Device Driver", driver source `clockdd.asm`/`clock01.asm`] + [OBS]

The kernel sets the clock by writing a 6-byte record to the clock device; the device's
driver maintains the InfoSeg date/time fields. The device is identified by the `DEV_CLOCK`
attribute bit, not by its name. A program can also open it and read or write the record.

| Byte | 0-1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| Field | days since 1-1-1980 (WORD) | minutes | hours | hundredths | seconds |

| Operation | Result [OBS, rev 14.089] |
|---|---|
| read >= 6 bytes | 0, exactly 6 bytes returned |
| read < 6 bytes | 30 `ERROR_READ_FAULT`, 0 bytes |
| write exactly 6 bytes | 0 - **no validation of the record**: minutes = 99 is accepted and a later `DosGetDateTime` returns it |
| write != 6 bytes | 29 `ERROR_WRITE_FAULT`, count 0 |
| IOCtl category 13, function 60h (read CMOS; parameter `{BYTE addr; BYTE count}`) | 0; 87 if `addr` < 0Ah or > 3Fh or `count` = 0; 87 if either buffer is NULL or declared with length 0 (decided outside the driver, which never reads the declared lengths). A non-zero declared length is not compared against what is needed (a parameter length of 1 over a 2-byte buffer answers 0): the driver checks the memory, not the length. The address compare is **signed** [DOC-IBM - driver source; not measured], so 80h and above also answer 87 |
| IOCtl category 13, function 61h (toggle a system-wide driver flag) | 0 |
| any other IOCtl function, or another category | 22 `ERROR_BAD_COMMAND` |

The driver's own header states that checking the record is the caller's job, and
`DosSetDateTime` is that caller. A clock-device failure during `DosSetDateTime` halts the
kernel rather than returning an error [OBS-RE].

## Error codes [DOC-IBM - `bseerr.h`]

The timer/time services report through the `APIRET` convention (0 = success). The dedicated
timer-service (`TS`) error codes are [DOC-IBM - `bseerr.h:439-443`]:

| Constant | Value | Sense (from the symbolic name) |
|---|---|---|
| `ERROR_TS_WAKEUP` | 322 | Wake-up / post failure on the timer's semaphore |
| `ERROR_TS_SEMHANDLE` | 323 | Invalid semaphore handle passed to the timer call |
| `ERROR_TS_NOTIMER` | 324 | No timer available to satisfy the request |
| `ERROR_TS_HANDLE` | 326 | Invalid timer handle (e.g. to `DosStopTimer`) |
| `ERROR_TS_DATETIME` | 327 | Invalid date/time value passed to `DosSetDateTime` |

(The value 325 is not defined in this range.) The one-line senses above are read from the IBM
symbolic names; consult the IBM Control Program reference for the exact per-call return set.

Per-call, EDM2 documents `DosSetDateTime` as returning only `NO_ERROR` (0) or `ERROR_TS_DATETIME`
(327) - the latter for any out-of-range field or an impossible day-of-month [DOC - EDM2
"DosSetDateTime"]. (The remaining `TS` codes above pertain to the interval-timer calls; EDM2 has
no pages for `DosStartTimer` / `DosAsyncTimer` / `DosStopTimer` / `DosTmrQueryFreq` /
`DosTmrQueryTime` / `DosGetDateTime`, so their per-call return sets are not enumerated here.)

## Ordinals [DOC-IBM - `bseord.h`]

Both 16-bit and 32-bit entry-point ordinals exist for the timer/time surface:

| Function | 16-bit ordinal | 32-bit ordinal |
|---|---|---|
| `DosSetDateTime` | 28 (`ORD_DOSSETDATETIME`) | 292 (`ORD_DOS32SETDATETIME`) |
| `DosGetDateTime` | 33 (`ORD_DOSGETDATETIME`) | 230 (`ORD_DOS32GETDATETIME`) |
| `DosAsyncTimer` (`DosTimerAsync`) | 29 (`ORD_DOSTIMERASYNC`) | 350 (`ORD_DOS32ASYNCTIMER`) |
| `DosStartTimer` (`DosTimerStart`) | 30 (`ORD_DOSTIMERSTART`) | 351 (`ORD_DOS32STARTTIMER`) |
| `DosStopTimer` (`DosTimerStop`) | 31 (`ORD_DOSTIMERSTOP`) | 290 (`ORD_DOS32STOPTIMER`) |
| `DosTmrQueryFreq` | - | 420 (`ORD_DOSTMRQUERYFREQ`) |
| `DosTmrQueryTime` | - | 421 (`ORD_DOSTMRQUERYTIME`) |

[DOC-IBM - `bseord.h:267-272, 414, 473-475, 524-525, 550-551`.] The high-resolution timer
calls are 32-bit-only in this Toolkit's ordinal set.

## Choosing among them

- **Wake a thread periodically or after a delay** -> `DosStartTimer` / `DosAsyncTimer` posting
  an event semaphore. Resolution is one system tick (~tens of ms); do not expect sub-tick
  precision.
- **Measure a short elapsed interval precisely** -> `DosTmrQueryFreq` once, then two
  `DosTmrQueryTime` reads.
- **Read or set the wall clock / calendar** -> `DosGetDateTime` / `DosSetDateTime`, or read the
  InfoSeg time fields directly (`infoseg.md`) to avoid the call.
