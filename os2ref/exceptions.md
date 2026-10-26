# OS/2 Exception and Signal Handling

OS/2 delivers hardware faults, software-raised exceptions, and asynchronous process
signals to an application through a single, per-thread mechanism: a chain of
registration records rooted at `FS:[0]` in the Thread Information Block. A thread
pushes a handler with `DosSetExceptionHandler`, the kernel walks the chain most-recent
first when an exception occurs, and each handler decides whether it resumes the faulting
thread, passes the exception to the next handler, or unwinds the stack. This reference
documents the registration model, the handler contract and its three argument structures,
the `XCPT_*` exception numbering, the handler return codes, and the DOS APIs that raise,
unwind, and gate exceptions.

Provenance: **[DOC-IBM]** OS/2 Toolkit 4.5 headers `bsexcpt.h` (return codes, `XCPT_*`
values, `CONTEXTRECORD`, `EXCEPTIONREPORTRECORD`, `EXCEPTIONREGISTRATIONRECORD`),
`bsedos.h` (the `Dos*` exception/signal prototypes and `SIG_*` focus flags), `bsetib.h`
(the TIB exception-chain root and the must-complete counters); **[DOC]** IBM *Control
Program Programming Guide and Reference* for call semantics not encoded in the headers.

## The model [DOC-IBM / DOC]

Every thread has its own exception-handler chain. The head of the chain is the first
field of the thread's TIB, `tib_pexchain` (offset 0), which is reached through the `FS`
segment register as `FS:[0]` [DOC-IBM `bsetib.h:49`]. Each link is an
`EXCEPTIONREGISTRATIONRECORD` on the thread's stack holding a `prev_structure` pointer to
the next-older record and an `ExceptionHandler` function pointer. The end of the chain is
marked by `END_OF_CHAIN`, defined as `(PEXCEPTIONREGISTRATIONRECORD) -1` [DOC-IBM
`bsexcpt.h:360`].

When an exception is raised on a thread, its handlers are called in turn, newest first. A
handler inspects the exception and returns one of the disposition codes below.
`XCPT_CONTINUE_SEARCH` passes the exception to the next-older handler;
`XCPT_CONTINUE_EXECUTION` resumes the thread using the (possibly modified)
`CONTEXTRECORD`. If the chain is exhausted with no handler continuing execution, the process
terminates. A handler may also initiate an *unwind* (via `DosUnwindException`), which
re-dispatches to the handlers being removed with the `EH_UNWINDING` flag set so they can
release resources before the stack is discarded. [DOC-IBM / DOC]

> **CORRECTED 2026-09-25 - an earlier revision of this paragraph said "the kernel dispatches
> to each handler in turn".** The kernel does not walk the chain. The walk happens **in ring 3,
> in DOSCALL1**; the kernel only builds the records, and later resumes the thread or applies
> the default action.

**How dispatch actually runs** [OBS-RE: os2krnl SMP 14.104a and the `smp_astrict` debug
kernel with IBM's linker map; DOSCALL1; unpublished notes]:

1. **Kernel side.** `_XCPTBuildR3DispatcherStack` (map `0011:00080C60`) fills an
   `EXCEPTIONREPORTRECORD` and a `CONTEXTRECORD` (`ContextFlags` 7), leaves an `0x80`-byte gap
   below the thread's `ESP`, pushes a frame `{0 (return address), trap number, &report,
   &context, report, context}`, and sends the thread to DOSCALL1's ring-3 dispatcher through
   `KMSETFLATDISPATCH(_pfnXcptDispatcher32)` (`_pfnXcptDispatcher32` = map `000C:0002F5A0`). The
   dispatcher is `DOS32R3EXCEPTIONDISPATCHER(ulTrap, pRep, pCtx)`, entered with `DS=ES=SS`,
   `FS` = the TIB selector and `GS` = 0. **Exception to this:** if the chain is empty
   (`FS:[0] == -1`), the process is not being debugged and no floating-point section is
   involved, the kernel applies the default action directly. Guard-page and floating-point
   exceptions always go to ring 3.
2. **Ring-3 side.** The dispatcher walks the `FS:[0]` chain (ending at `-1`, not NULL),
   validating each record (on the stack or the thunk stack; handler memory executable and
   committed), and grows the stack on a guard-page fault. It always finishes by calling
   `DOS32EXCEPTIONCALLBACK(ulTrap, pRep, pCtx, disposition)`, which does not return.
   `DosRaiseException` reaches the same dispatcher.
3. **Resuming is done by the kernel.** `DOS32EXCEPTIONCALLBACK` enters the kernel
   (`_VR32ExceptionCallBack` -> `_xcptExceptionCallBack`). For `XCPT_CONTINUE_EXECUTION`,
   `_xcptRestoreXcptContext` writes the context record's sections back into the thread's saved
   register frame (merging `EFLAGS` with mask `0xCD5`) and returns `ctx_RegEax` as the call's
   `EAX`. For `XCPT_CONTINUE_SEARCH` from the last handler, the kernel falls back to any
   `DosSetVec` vector or the default action. The one part restored in ring 3 is the
   floating-point state, by a DOSCALL1 routine (`DOS32R3FRESTOR`: `frstor`, restore segment
   registers, `lss`, `iret`).

Not independently re-verified: the DOSCALL1 ordinal numbers of these entries (548 for the
dispatcher, 600 for the FP restore, 1043 for the callback, 1074 for the raise path, taken from
the 14.089 export table and unconfirmed for 14.104a), the exact `0xE4`-byte frame layout, and
the dispatcher's C-level body.

## Registering and removing a handler [DOC-IBM `bsedos.h:2379`]

| Function | Prototype | Purpose |
|---|---|---|
| `DosSetExceptionHandler` | `APIRET APIENTRY DosSetExceptionHandler(PEXCEPTIONREGISTRATIONRECORD pERegRec)` | Push `*pERegRec` onto the head of the calling thread's handler chain. |
| `DosUnsetExceptionHandler` | `APIRET APIENTRY DosUnsetExceptionHandler(PEXCEPTIONREGISTRATIONRECORD pERegRec)` | Remove `*pERegRec` from the calling thread's handler chain. |

The caller supplies the `EXCEPTIONREGISTRATIONRECORD` itself (typically a local variable on
the thread's stack); it must remain valid until unregistered, and records must be removed
in last-in-first-out order relative to the stack frame that owns them. [DOC-IBM / DOC]

## The registration record [DOC-IBM `bsexcpt.h:349`]

```c
struct _EXCEPTIONREGISTRATIONRECORD
   {
   struct _EXCEPTIONREGISTRATIONRECORD * volatile prev_structure;   /* +0x00: next-older record */
   _ERR * volatile ExceptionHandler;                               /* +0x04: handler entry point */
   };
```

Two 32-bit fields, 8 bytes total. `prev_structure` links toward the older handlers and
ends at `END_OF_CHAIN`; `ExceptionHandler` points at a function matching the `_ERR`
signature below. [DOC-IBM]

## The handler signature [DOC-IBM `bsexcpt.h:340`]

```c
typedef ULONG APIENTRY _ERR(PEXCEPTIONREPORTRECORD    pReportRecord,
                            PEXCEPTIONREGISTRATIONRECORD pRegistrationRecord,
                            PCONTEXTRECORD             pContextRecord,
                            PVOID                      pDispatcherContext);
typedef _ERR *ERR;
```

| Argument | Type | Meaning |
|---|---|---|
| `pReportRecord` | `PEXCEPTIONREPORTRECORD` | Machine-independent description of the exception (number, flags, faulting address, parameters). |
| `pRegistrationRecord` | `PEXCEPTIONREGISTRATIONRECORD` | The record whose `ExceptionHandler` is being invoked. |
| `pContextRecord` | `PCONTEXTRECORD` | The thread's machine state at the point of the exception; may be modified before returning `XCPT_CONTINUE_EXECUTION`. |
| `pDispatcherContext` | `PVOID` | System dispatcher context, used during nested dispatch and unwind. |

The handler returns a disposition (`ULONG`). [DOC-IBM]

## Handler return (disposition) codes [DOC-IBM `bsexcpt.h:39`]

| Constant | Value | Meaning |
|---|---|---|
| `XCPT_CONTINUE_SEARCH` | `0x00000000` | Exception not handled - pass to the next-older handler. |
| `XCPT_CONTINUE_EXECUTION` | `0xFFFFFFFF` | Exception handled - resume the thread from the `CONTEXTRECORD`. |
| `XCPT_CONTINUE_STOP` | `0x00716668` | Exception handled by a debugger (via `DosDebug`). |

## Handler flags - `fHandlerFlags` [DOC-IBM `bsexcpt.h:52`]

These appear in the report record's `fHandlerFlags` field. An application may only *set*
`EH_NONCONTINUABLE`; all others are set by the system.

| Flag | Value | Meaning |
|---|---|---|
| `EH_NONCONTINUABLE` | `0x01` | Exception cannot be continued; returning `XCPT_CONTINUE_EXECUTION` is invalid. |
| `EH_UNWINDING` | `0x02` | An unwind is in progress (handler is being called to clean up). |
| `EH_EXIT_UNWIND` | `0x04` | An exit unwind is in progress. |
| `EH_STACK_INVALID` | `0x08` | Stack is out of limits or misaligned. |
| `EH_NESTED_CALL` | `0x10` | Nested exception-handler call. |
| `EH_SIGFTERM` | `0x20` | Signalled termination context. |

## The report record [DOC-IBM `bsexcpt.h:309`]

```c
#define EXCEPTION_MAXIMUM_PARAMETERS 4

struct _EXCEPTIONREPORTRECORD
   {
   ULONG   ExceptionNum;                          /* +0x00: exception number (XCPT_*) */
   ULONG   fHandlerFlags;                         /* +0x04: EH_* flags */
   struct _EXCEPTIONREPORTRECORD *NestedExceptionReportRecord; /* +0x08 */
   PVOID   ExceptionAddress;                      /* +0x0C: address that raised it */
   ULONG   cParameters;                           /* +0x10: count of valid ExceptionInfo entries */
   ULONG   ExceptionInfo[EXCEPTION_MAXIMUM_PARAMETERS]; /* +0x14: exception-specific info */
   };
```

`ExceptionInfo` carries per-exception detail; which entries are valid is given by
`cParameters` and by the specific `XCPT_*` value (see the tables below). No system
exception uses more than `EXCEPTION_MAXIMUM_PARAMETERS` (4) entries; user-defined
exceptions raised with `DosRaiseException` are not bound by that limit. [DOC-IBM]

## The context record [DOC-IBM `bsexcpt.h:229`]

`CONTEXTRECORD` (`struct _CONTEXT`) holds the thread's machine state. Which portions are
valid is controlled by the leading `ContextFlags` field; only the flagged portions are
returned when capturing state, and only the flagged portions are restored when a handler
continues execution.

| `ContextFlags` bit | Value | Registers covered |
|---|---|---|
| `CONTEXT_CONTROL` | `0x00000001` | `SS:ESP`, `CS:EIP`, `EFLAGS`, `EBP` |
| `CONTEXT_INTEGER` | `0x00000002` | `EAX`, `EBX`, `ECX`, `EDX`, `ESI`, `EDI` |
| `CONTEXT_SEGMENTS` | `0x00000004` | `DS`, `ES`, `FS`, `GS` |
| `CONTEXT_FLOATING_POINT` | `0x00000008` | numeric coprocessor state |
| `CONTEXT_FULL` | (CONTROL\|INTEGER\|SEGMENTS\|FLOATING_POINT) | all four categories, including floating-point state |

Field layout (fields are `ULONG` unless noted) [DOC-IBM `bsexcpt.h:229-291`]:

| Field | Section (flag) | Notes |
|---|---|---|
| `ContextFlags` | - | which sections are valid |
| `ctx_env[7]`, `ctx_stack[8]` | `CONTEXT_FLOATING_POINT` | `ctx_stack` is 8 x `FPREG` (coprocessor stack) |
| `ctx_SegGs`, `ctx_SegFs`, `ctx_SegEs`, `ctx_SegDs` | `CONTEXT_SEGMENTS` | segment registers |
| `ctx_RegEdi`, `ctx_RegEsi`, `ctx_RegEax`, `ctx_RegEbx`, `ctx_RegEcx`, `ctx_RegEdx` | `CONTEXT_INTEGER` | general registers |
| `ctx_RegEbp`, `ctx_RegEip`, `ctx_SegCs`, `ctx_EFlags`, `ctx_RegEsp`, `ctx_SegSs` | `CONTEXT_CONTROL` | control/flow registers |

`FPREG` is a packed coprocessor stack-register element: `ULONG losig; ULONG hisig; USHORT
signexp;` [DOC-IBM `bsexcpt.h:218`].

## Exception numbering [DOC-IBM `bsexcpt.h:67`]

An exception value is a 32-bit field: two severity bits (`00` success, `01` informational,
`10` warning, `11` error), a customer-code flag, a facility code, and a 16-bit status
code. System exceptions use facility 0; OS/2-specific exceptions such as `XCPT_SIGNAL` use
facility 1. The decoding masks are:

| Constant | Value |
|---|---|
| `XCPT_FATAL_EXCEPTION` / `XCPT_SEVERITY_CODE` | `0xC0000000` |
| `XCPT_CUSTOMER_CODE` | `0x20000000` |
| `XCPT_FACILITY_CODE` | `0x1FFF0000` |
| `XCPT_EXCEPTION_CODE` | `0x0000FFFF` |

### Portable non-fatal software exceptions [DOC-IBM `bsexcpt.h:125`]

| Constant | Value | `ExceptionInfo` |
|---|---|---|
| `XCPT_GUARD_PAGE_VIOLATION` | `0x80000001` | [0] access code (`XCPT_READ_ACCESS`/`XCPT_WRITE_ACCESS`); [1] fault address |
| `XCPT_UNABLE_TO_GROW_STACK` | `0x80010001` | - |

### Portable fatal hardware exceptions [DOC-IBM `bsexcpt.h:134`]

| Constant | Value | `ExceptionInfo` |
|---|---|---|
| `XCPT_ACCESS_VIOLATION` | `0xC0000005` | [0] access code; [1] fault address, or selector (`XCPT_SPACE_ACCESS`), or -1 (`XCPT_LIMIT_ACCESS`) |
| `XCPT_DATATYPE_MISALIGNMENT` | `0xC000009E` | [0] access code; [1] alignment; [2] fault address |
| `XCPT_BREAKPOINT` | `0xC000009F` | - |
| `XCPT_SINGLE_STEP` | `0xC00000A0` | - |
| `XCPT_ILLEGAL_INSTRUCTION` | `0xC000001C` | - |
| `XCPT_PRIVILEGED_INSTRUCTION` | `0xC000009D` | - |
| `XCPT_INTEGER_DIVIDE_BY_ZERO` | `0xC000009B` | - |
| `XCPT_INTEGER_OVERFLOW` | `0xC000009C` | - |
| `XCPT_FLOAT_DENORMAL_OPERAND` | `0xC0000094` | - |
| `XCPT_FLOAT_DIVIDE_BY_ZERO` | `0xC0000095` | - |
| `XCPT_FLOAT_INEXACT_RESULT` | `0xC0000096` | - |
| `XCPT_FLOAT_INVALID_OPERATION` | `0xC0000097` | - |
| `XCPT_FLOAT_OVERFLOW` | `0xC0000098` | - |
| `XCPT_FLOAT_STACK_CHECK` | `0xC0000099` | - |
| `XCPT_FLOAT_UNDERFLOW` | `0xC000009A` | - |

The `ExceptionInfo` access-code (violation) flags used above are: `XCPT_UNKNOWN_ACCESS`
`0x00000000`, `XCPT_READ_ACCESS` `0x00000001`, `XCPT_WRITE_ACCESS` `0x00000002`,
`XCPT_EXECUTE_ACCESS` `0x00000004`, `XCPT_SPACE_ACCESS` `0x00000008`, `XCPT_LIMIT_ACCESS`
`0x00000010`, `XCPT_DATA_UNKNOWN` `0xFFFFFFFF` [DOC-IBM `bsexcpt.h:108`].

### Portable fatal software exceptions [DOC-IBM `bsexcpt.h:166`]

| Constant | Value | `ExceptionInfo` |
|---|---|---|
| `XCPT_IN_PAGE_ERROR` | `0xC0000006` | [0] fault address |
| `XCPT_PROCESS_TERMINATE` | `0xC0010001` | - |
| `XCPT_ASYNC_PROCESS_TERMINATE` | `0xC0010002` | [0] TID of the terminating thread |
| `XCPT_NONCONTINUABLE_EXCEPTION` | `0xC0000024` | - |
| `XCPT_INVALID_DISPOSITION` | `0xC0000025` | - |

### Non-portable fatal exceptions [DOC-IBM `bsexcpt.h:178`]

| Constant | Value |
|---|---|
| `XCPT_INVALID_LOCK_SEQUENCE` | `0xC000001D` |
| `XCPT_ARRAY_BOUNDS_EXCEEDED` | `0xC0000093` |
| `XCPT_B1NPX_ERRATA_02` | `0xC0010004` |

### Unwind and signal exceptions [DOC-IBM `bsexcpt.h:184`]

| Constant | Value | `ExceptionInfo` |
|---|---|---|
| `XCPT_UNWIND` | `0xC0000026` | - |
| `XCPT_BAD_STACK` | `0xC0000027` | - |
| `XCPT_INVALID_UNWIND_TARGET` | `0xC0000028` | - |
| `XCPT_SIGNAL` | `0xC0010003` | [0] signal number |

The signal numbers carried by `XCPT_SIGNAL` are `XCPT_SIGNAL_INTR` (1),
`XCPT_SIGNAL_KILLPROC` (3), `XCPT_SIGNAL_BREAK` (4), and `XCPT_SIGNAL_APTERM` (8) [DOC-IBM
`bsexcpt.h:118`].

## Raising and unwinding [DOC-IBM `bsedos.h:2383`]

| Function | Prototype | Purpose |
|---|---|---|
| `DosRaiseException` | `APIRET APIENTRY DosRaiseException(PEXCEPTIONREPORTRECORD pexcept)` | Raise an exception on the calling thread; the report record supplies the number, flags, and parameters. |
| `DosUnwindException` | `APIRET APIENTRY DosUnwindException(PEXCEPTIONREGISTRATIONRECORD phandler, PVOID pTargetIP, PEXCEPTIONREPORTRECORD pERepRec)` | Unwind the handler chain up to `phandler`, calling each removed handler with `EH_UNWINDING`, then transfer control to `pTargetIP`. |
| `DosSendSignalException` | `APIRET APIENTRY DosSendSignalException(PID pid, ULONG exception)` | Send a signal exception to another process. |

`DosUnwindException` accepts `UNWIND_ALL` (value `0`) for `phandler` to unwind every
handler [DOC-IBM `bsexcpt.h:63`]. Non-continuable exceptions are marked with
`EH_NONCONTINUABLE`; the corresponding failure conditions surface as
`XCPT_NONCONTINUABLE_EXCEPTION`, `XCPT_INVALID_DISPOSITION`, and `XCPT_INVALID_UNWIND_TARGET`.
[DOC-IBM / DOC]

### What `DosUnwindException` resumes, and in which context

IBM documents `pTargetIP` only as *"where DosUnwindException branches after calling all
applicable handlers"*, and `phandler = 0` (`UNWIND_ALL`) as an exit unwind that *"removes all
exception handlers from the thread, and ends the thread"* [DOC-IBM `cp1.txt`,
"DosUnwindException Parameter - phandler" and "- pTargetIP"]. The register state at the target
is not documented anywhere; the implementation fixes it, as follows.

**The target runs in the caller's context.** `DOS32UNWINDEXCEPTION` builds a `CONTEXTRECORD`
before it unwinds anything: `ContextFlags = 3` (`CONTEXT_CONTROL|CONTEXT_INTEGER`), `EAX = 0`,
the caller's `EBX`/`ECX`/`EDX`/`ESI`/`EDI`, the caller's `EBP`, `ESP` = the address just past the
return address (the arguments are still on the stack, since the caller's own cleanup has not
run), `EIP` = the return address, and `CS`, `SS` and `EFLAGS` as they were at the call
[OBS-RE: the entry's prologue, each store landing on the `struct _CONTEXT` offset for its field].
`_xcptUnwindDispatcher` then replaces exactly one field - `ctx_RegEip` = `pTargetIP` - and
resumes that context through `DOS32EXCEPTIONCALLBACK`, both for a registration-record target and
for `END_OF_CHAIN` (`-1`) [OBS-RE: the dispatcher]. At `pTargetIP` the caller's general
registers, `EBP`, post-call `ESP` and arithmetic flags are therefore intact and `EAX` is 0 -
which is what a C runtime `longjmp` built on this call depends on, since it reads its `jmp_buf`
through `EBP` at the target.

Measured for both target forms [OBS: WSeB CP2, 2026-09-17 - a 32-bit program seeds
`EBX`/`ECX`/`EDX`/`ESI`/`EDI` with distinct values and the flags with `mov al,0x7F; add al,1`
(`AH = 0x92`), records its `EBP` and pre-call `ESP`, calls `DosUnwindException(phandler, T,
NULL)`, and at `T` recovers `AH` with `LAHF`]: all five registers, `EBP`, `ESP` and `AH` were
the caller's, `EAX` was 0, and the call did not return. Only the `LAHF` flags
(`SF`/`ZF`/`AF`/`PF`/`CF`) were observed; `DF`, `IF` and `OF` at the target were not.

**Each handler being unwound is given that same context**, not one of its own, together with the
unwind report. With `pERepRec = NULL` the report is synthesised: `ExceptionNum = XCPT_UNWIND`
(`0xC0000026`) and `ExceptionAddress` = the context's `ctx_RegEip`, which is still the caller's
return address at that point [OBS-RE: the dispatcher]. Measured [OBS: same capture]: an
intervening handler saw `0xC0000026` with `ExceptionAddress` equal to the call's return address,
and a `CONTEXTRECORD` carrying `ContextFlags = 3`, the caller's `CS` and `EIP`, `ESP`, `EBP`,
`EAX = 0` and `EBX`/`ECX`/`EDX`/`ESI`/`EDI`.

**`EH_EXIT_UNWIND` marks only `UNWIND_ALL`.** The dispatcher ORs `EH_UNWINDING|EH_EXIT_UNWIND`
into the report's flags when `phandler` is 0, and `EH_UNWINDING` alone otherwise -
`END_OF_CHAIN` included, although it also unwinds the whole chain [OBS-RE: the dispatcher;
OBS: the same capture, for a record target and for `END_OF_CHAIN`]. On the `UNWIND_ALL` path
`pTargetIP` is never stored; what the final callback's `0x65796C4B` argument selects was not
read, and IBM's statement is that the thread ends.

**A target record that is not in the chain** is refused before anything is unwound: the
dispatcher walks the chain first and raises `XCPT_INVALID_UNWIND_TARGET` if the record is absent
[OBS-RE: the dispatcher].

**`pTargetIP = NULL` is not special-cased.** `ctx_RegEip` becomes 0 and the thread resumes at
`EIP 0` and traps [OBS: WSeB CP2, 2026-09-17 - the same program with a NULL target ended in
`SYS3175` `c0000005` at `CS:EIP = 005b:00000000`]. Code that wants the handlers run and control
back must supply a real target.

**A report that already carries `EH_STACK_INVALID` (`0x08`) stops the call**: nothing is
unwound, control does not reach `pTargetIP`, the report is left as it was, and the call returns
`1` (`ERROR_INVALID_FUNCTION`) [OBS-RE: the dispatcher's whole body sits under that flag test,
and the entry returns 1 when it comes back; OBS: WSeB CP2, 2026-09-17, a caller-supplied
`XCPT_UNWIND` report with `fHandlerFlags = 0x08`, a valid record target and a real `pTargetIP`].

## How a hardware fault reaches the handler chain

This section covers the path from a processor fault in a protected-mode OS/2 process to its
handlers, and what happens when none of them takes the fault. It covers faults in 32-bit code,
in 16-bit code, and in 16-bit code running in a DLL's ring-2 (IOPL) segment such as a video
handler.

### Which handlers see a fault, and in what order [DOC-IBM]

IBM states the order in the *Control Program Programming Guide*, "System Exceptions"
(`cp2.txt`, the paragraph beginning "OS/2 delivers exceptions that occur in 16-bit as well as
32-bit code"):

- *"When an exception occurs in 32-bit code, the system gives control only to the 32-bit
  exception handlers registered for the current thread."*
- *"When an exception occurs in 16-bit code, the system first gives control to the 32-bit
  exception handlers registered for the current thread. If the exception is not handled by one
  of these handlers, control is passed to the 16-bit handler, if one exists for the given
  exception. If there is no 16-bit handler for the exception, the system default action occurs."*

So a fault in 16-bit code goes to the **same `FS:[0]` chain** as a 32-bit fault, and it goes
there first. The "16-bit handler" is a `DosSetVec` vector. The kernel keeps vectors only for
traps 0, 4, 5, 6, 7 and 0x10 (and 0x21), and consults one only when the faulting `CS` is an LDT
selector and the 32-bit chain has declined [OBS-RE: 14.104a SMP kernel, `h_w_SetVec`,
`_xcptExceptionCallBack` -> `_xcpt2Trap` -> `TRAPArmExceptHandler`]. **An access violation has no
16-bit vector**, so for a 16-bit program an access violation goes to the 32-bit chain and then
to the default action. IBM's DDK says the same from the 16-bit side: *"Under 16-bit OS/2
architecture, a process cannot handle access violations. In the event of an access violation,
the system terminates the process"* [DOC-IBM DDK `HTML/REF/PDR/00040.HTM`, "Per-Thread Exception
Management"].

A fault taken in ring-2 code goes on the ring-3 stack. The kernel switches the client to the
ring-3 `SS:SP` that the call gate saved at the top of the ring-2 stack, then pushes the dispatch
frame there [OBS-RE: `_XCPTBuildR3DispatcherStack`]. The handlers therefore see a fault in a
video handler's IOPL segment exactly as they see a fault in the program's own code.

### The state a handler is entered with [OBS-RE]

The kernel pushes its dispatch frame on the faulting thread's stack, 0x80 bytes below the fault's
`ESP`. It then enters DOSCALL1's dispatcher (ordinal 548) with `CS` = the flat code selector,
`DS = ES = SS`, `FS` = the TIB selector and `GS = 0`, **whatever the faulting code had loaded**
[OBS-RE: `_XCPTBuildR3DispatcherStack`, `KMSETFLATDISPATCH`]. The dispatcher walks `FS:[0]`
newest first. A handler of a fault in 16-bit code therefore runs with the TIB in `FS`, although
the 16-bit code may have had something else there.

The `CONTEXTRECORD` a handler receives has `ContextFlags = 7` (`CONTEXT_CONTROL |
CONTEXT_INTEGER | CONTEXT_SEGMENTS`). The floating-point section is added only for the seven
`XCPT_FLOAT_*` codes. `ctx_SegCs`/`ctx_RegEip` and `ctx_SegSs`/`ctx_RegEsp` are the raw
selector:offset pairs of the fault, 16-bit ones included [OBS-RE: `_XCPTBuildR3DispatcherStack`].

When a handler returns `XCPT_CONTINUE_EXECUTION`, the kernel writes back **only the sections
`ContextFlags` names**. `CONTEXT_CONTROL` restores `EBP`, `EIP`, `CS`, `ESP`, `SS` and `EFLAGS`.
`CONTEXT_INTEGER` restores the six general registers, and `CONTEXT_SEGMENTS` restores `DS`, `ES`,
`FS` and `GS`. Of `EFLAGS`, only the bits in mask `0xCD5` (the arithmetic flags and `DF`) come
from the record; the rest keep the faulting thread's values [OBS-RE: `_xcptRestoreXcptContext`,
`& 0xcd5 | old & 0xfffff32a`]. A handler that resumes 32-bit code after a fault in 16-bit code
therefore gets the `CS` and `SS` it put in the record.

### What a trap is reported as [OBS-RE]

`ExceptionAddress` is the **linear address of the faulting instruction**. It is the client
`EIP` for the flat code selector, and `_SELVirtToLin(EIP, CS)` for any other selector. It is not
the address of the data that could not be reached [OBS-RE: `_XCPTBuildR3DispatcherStack`;
[DOC-IBM] `cp2.txt` "XCPT_ACCESS_VIOLATION": *"The ExceptionAddress field in the
ExceptionReportRecord points to the instruction that caused the exception"*]. The exception
number and `ExceptionInfo` come from a per-trap formatter [OBS-RE: `XCPTFormatAndSendException`
and the `xcpt*` formatters of the 14.104a SMP kernel, each read from its bytes]:

| trap | exception | `ExceptionInfo[0]`, `[1]` |
|---|---|---|
| 0x0E page fault | `XCPT_ACCESS_VIOLATION` | `XCPT_WRITE_ACCESS` (2) if error-code bit 1 is set, else `XCPT_READ_ACCESS` (1); `CR2` |
| 0x0C stack fault, error code != 0 | `XCPT_ACCESS_VIOLATION` | `XCPT_SPACE_ACCESS` (8); the error code |
| 0x0C stack fault, error code 0 | `XCPT_ACCESS_VIOLATION` | `XCPT_LIMIT_ACCESS` (0x10); `XCPT_DATA_UNKNOWN` (-1) |
| 0x0D general protection, error code != 0 | `XCPT_ACCESS_VIOLATION` | `XCPT_SPACE_ACCESS` (8); the error code |
| 0x0D, error code 0 | see below | |
| 9, 0x0A, 0x0B (after a failed demand load) | `XCPT_ACCESS_VIOLATION` | `XCPT_UNKNOWN_ACCESS` (0); -1 |

For a general-protection fault with error code 0, `xcptGPFault` reads the four bytes at `CS:EIP`.
It reports `XCPT_PRIVILEGED_INSTRUCTION` (0xC000009D) with no parameters when the first byte is
`CLI`/`STI` (`FA`/`FB`), `HLT` (`F4`), `INS`/`OUTS` (`6C`-`6F`), `IN`/`OUT` (`E4`-`E7`,
`EC`-`EF`), or `0F` followed by `00`, `01` or `06`. It reports `{XCPT_LIMIT_ACCESS, -1}` for any
other `0F` opcode, and `{XCPT_UNKNOWN_ACCESS, -1}` for everything else or when the bytes cannot
be read. Two of its prefix tests do not do what they appear to [OBS-RE: `xcptGPFault`,
0x000FEFB4-0x000FEFD3]:

- After a `66` prefix it shifts the dword right by **four** bits, not eight (`shr eax,4`).
- Its `REP` test masks the byte with `0xFC` and then compares it with `0xF2`, which can never be
  equal.

So neither a `66`- nor a `REP`-prefixed `INS`/`OUTS` is reported as privileged.

For a **selector fault**, the error code the CPU pushes is the selector with its RPL bits
cleared (index and TI bit) [x86 architecture]. That value is what `ExceptionInfo[1]` carries, next
to `XCPT_SPACE_ACCESS`.

### Faults on a 16:16 pointer [OBS-RE / OBS]

A 16-bit routine reaches a caller's far pointer with `les`/`lds`. Two cases follow from the table
above and the x86 architecture:

- **A selector that does not resolve.** It has no valid descriptor in the process's LDT, or it
  lies beyond the LDT's limit. The load itself faults with a general-protection fault whose error
  code is the selector, which is reported as `XCPT_ACCESS_VIOLATION {XCPT_SPACE_ACCESS, selector
  & 0xFFFC}` at the `les`. Measured [OBS: WSeB 4.50 Rev 14.089, retail SMP kernel, 2026-09-15]: a
  16-bit program called `DOSCALLS.#707` with `7FF8:1234`. The popup log recorded `SYS3175
  c0000005 P2=00007ff8` at `DOSCALL1.DLL 0003:0000bdc7`, which is the routine's `les di,[bp+0x6]`.
  A descriptor that is present-bit-clear raises trap 0x0B instead. The kernel first tries a
  demand load; if that fails, the fault is reported `{XCPT_UNKNOWN_ACCESS, -1}` [OBS-RE:
  `UserSegmentNPFault`, `xcptAccessViolation`].
- **The null selector** (0-3). It loads without a fault [x86 architecture]. The **first use**
  faults, with a general-protection fault with error code 0, which is reported `{XCPT_UNKNOWN_ACCESS,
  -1}` at the using instruction. Measured the same day, same call, with `0000:0000`: `SYS3175
  c0000005`, `ES=0000`, at `0003:0000bdca`, the `cmp word [es:di],+0x10` one instruction after
  the `les`.

Neither case is refused by the called routine. It has no null test and no validation, and the
fault is the program's, delivered as above.

**The 16-bit kernel APIs report differently.** The kernel's SCI stub arms a recovery address
before it touches a 16-bit API's pointer arguments. On a fault there, `UsrArgFault` queues
`XCPT_ACCESS_VIOLATION {XCPT_UNKNOWN_ACCESS, -1}` with trap number 0x0D *for the caller*,
whichever kind of bad pointer it was, and the caller resumes in its exception handler. A 16-bit
kernel API therefore raises; it does not return `ERROR_INVALID_ADDRESS` [OBS-RE: `sci`/`mpsci`,
`UsrFaultHandler`, `UsrArgFault`].

### A NULL-page access by 32-bit code [OBS-RE / OBS]

Address 0 is not mapped in an OS/2 process. A 32-bit access to it is an ordinary page fault,
reported `XCPT_ACCESS_VIOLATION {XCPT_READ_ACCESS or XCPT_WRITE_ACCESS, the address}`, and it
reaches the chain like any other. A transfer of control to address 0 faults the same way
[OBS: WSeB CP2, 2026-09-17, `DosUnwindException` with `pTargetIP = NULL` ended in `SYS3175
c0000005` at `CS:EIP = 005b:00000000`, see "What `DosUnwindException` resumes" above].

### When no handler takes the fault [OBS-RE / OBS]

With no handler returning `XCPT_CONTINUE_EXECUTION`, and no `DosSetVec` vector that applies,
`_xcptDefaultAction` runs. Unless a just-in-time debugger is registered (see below), it formats
the `SYS3170`-`SYS3192` popup for the code (`SYS3175` for `XCPT_ACCESS_VIOLATION`), logs it, and
marks the process to die [OBS-RE: `_xcptDefaultAction`, `_xcptFormatAndSendHardErr`,
`DelayHardErrSub` -> `_TKDieSoonPTDA`]. What the parent's `DosExecPgm`/`DosWaitChild` then
returns in `RESULTCODES` [DOC-IBM `cp2.txt` "RESULTCODES Field - codeTerminate": `TC_TRAP` (2)
*"Trap operation for a 16-bit child process"*, `TC_EXCEPTION` (4) *"Exception operation for a
32-bit child process"*] was measured [OBS: WSeB 4.50, 2026-09-29]:

- **A 32-bit program** that ~~faulted~~ faulted in 32-bit code, or raised with no handler taking
  it, reported `codeTerminate = TC_EXCEPTION` and `codeResult =` the low word of the exception
  code (5 for `XCPT_ACCESS_VIOLATION`). **Corrected 2026-09-30:** "faulted" was too wide; a
  32-bit program's fault in 16-bit code reports `TC_TRAP` and the trap number, measured below
  [OBS].
- **A 16-bit program**'s divide error with no `DosSetVec` vector reported `TC_TRAP` and
  `codeResult =` the trap number (0).

~~Not established: whether the 16-bit/32-bit choice is made by the program's type or by the
bitness of the faulting `CS`. The fault that distinguishes them is a trap in 16-bit code of a
32-bit program. Settle it by disassembling the `AX` (kind) setup that `_xcptFormatAndSendHardErr`
makes before it reaches `DelayHardErrSub`, or by measuring that fault. Also not measured: the
`codeResult` of a 16-bit program's general-protection fault. The trap number 0x0D is `[INF]`, by
analogy with the divide error.~~ **Measured, and the program's type does not decide it**
[OBS: WSeB 4.50 Rev 14.089, retail SMP kernel, 2026-09-30]. Each program called
`VioGetMode(0000:0000, 0)` with no handler registered, in a windowed and then a full-screen
session, and its parent read `RESULTCODES` after a synchronous `DosExecPgm`:

- **A 32-bit program** whose fault was in 16-bit code reported `codeTerminate = TC_TRAP` (2) and
  `codeResult = 13` (0x0D). The popup log placed the `SYS3175` fault (`P1=00000000
  P2=ffffffff`) in the video handler: `BVHWNDW.DLL 0001:000008c8` in the windowed session,
  `BVHVGA.DLL 0002:00001a43` in the full-screen one. A 32-bit program's fault in 32-bit code
  reports `TC_EXCEPTION`, above, so the kind follows the faulting code, not the program.
- **A 16-bit program**, same call and same two fault sites, reported `TC_TRAP` and
  `codeResult = 13`. The general-protection fault's trap number is now `[OBS]`, not `[INF]`.

The mechanism, the `AX` setup in `_xcptFormatAndSendHardErr`, was not read.

## Signals and signal focus [DOC-IBM `bsedos.h:2392`]

Asynchronous signals (Ctrl-C, Ctrl-Break, process termination) are delivered as
`XCPT_SIGNAL` exceptions to the process that holds the *signal focus*. A process claims or
releases the focus with `DosSetSignalExceptionFocus`. ~~A handler that has processed a
signal exception must acknowledge it with `DosAcknowledgeSignalException` before another of
the same class can be delivered.~~ **Corrected 2026-10-14:** a 32-bit handler that *returns*
`XCPT_CONTINUE_EXECUTION` has already acknowledged; `DosAcknowledgeSignalException` is needed
only when the handler does not return (it leaves by `longjmp`). See "Holding, acknowledgement
and re-delivery" below.

| Function | Prototype | Purpose |
|---|---|---|
| `DosSetSignalExceptionFocus` | `APIRET APIENTRY DosSetSignalExceptionFocus(BOOL32 flag, PULONG pulTimes)` | Set (`SIG_SETFOCUS`) or release (`SIG_UNSETFOCUS`) the calling process's Ctrl-C / Ctrl-Break signal focus; `pulTimes` returns the current nesting count. |
| `DosAcknowledgeSignalException` | `APIRET APIENTRY DosAcknowledgeSignalException(ULONG ulSignalNum)` | Acknowledge a signal exception so a further signal of that number can be delivered. |

The focus flag values are `SIG_UNSETFOCUS` (`0`) and `SIG_SETFOCUS` (`1`) [DOC-IBM
`bsedos.h:2374`].

### Holding, acknowledgement and re-delivery (Ctrl-C = 1, Ctrl-Break = 4)

**IBM's rule** [DOC-IBM: *Control Program Guide*, "Handling Signal Exceptions"]: to keep
receiving signals the process must return `XCPT_CONTINUE_EXECUTION` from a 32-bit handler,
or acknowledge with `DosSetSigHandler(SIGA_ACKNOWLEDGE)` (16-bit), or call
`DosAcknowledgeSignalException`. *"The system holds these exceptions until an exception
handler returns XCPT_CONTINUE_EXECUTION, or calls DosAcknowledgeSignalException. However,
only one signal exception is actually held; they are not queued by the system."*

**How the kernel implements it** [OBS-RE, Warp 4.5 SMP kernel 14.104a]. Thread 1 carries three
signal words: *pending* (posted, not yet dispatched), *holding* (deferred by `DosHoldSignal` or
a must-complete section) and *current* (dispatched, not yet acknowledged). IBM's "held" is the
*current* word.

1. **Posting** a signal fails with 162 `ERROR_SIGNAL_PENDING` only if it is already *pending*
   (or *holding*). Otherwise it is marked *pending*, and thread 1 is forced to the signal path
   **only if the signal is not *current***. A thread blocked interruptibly is woken with its
   wait interrupted.
2. **Dispatch** happens when thread 1 next leaves the kernel: the bit moves from *pending* to
   *current* and `XCPT_SIGNAL` (`ExceptionInfo[0]` = the signal) is raised on thread 1 if it has
   a 32-bit handler, otherwise the 16-bit `DosSetSigHandler` handler is called.
3. **Handler returns `XCPT_CONTINUE_EXECUTION`**: the dispatcher's return to the kernel
   (`DosExceptionCallBack`) acknowledges the signal - it runs the same acknowledge as
   `DosSetSigHandler(SIGA_ACKNOWLEDGE)` and `DosAcknowledgeSignalException`. **This is an
   implicit acknowledgement**; the interrupted call then returns with the context's `EAX`.
4. **Every handler returns `XCPT_CONTINUE_SEARCH`**: the signal is re-posted past the
   exception route - to a 16-bit handler if there is one, else the default action (below).
5. **`DosAcknowledgeSignalException(n)`**: 209 for a number other than 1, 3, 4, 8; otherwise
   clears *current* for `n` and returns **0 - also when nothing was outstanding** (a second
   acknowledge is a harmless no-op). It acts on thread 1 whichever thread calls it, and a held
   instance is dispatched at thread 1's next kernel exit.

**A signal arriving while one is outstanding** (*current* set - the handler is still running, or
left by `longjmp` without acknowledging): the **first** such instance is recorded as *pending*
but not dispatched - that is the one "held" signal; it is delivered once, right after the
acknowledgement. **Further** instances are refused with 162 and lost - "not queued". [OBS-RE]

**No handler - the default action.**
- No process of the **foreground** session holds the focus for the signal: the kernel sends
  `XCPT_SIGNAL_KILLPROC` (signal 3) to every process of that session when its screen group
  is 4 or above and below the global info segment's `sgMax`; any other group gets nothing
  (see `vio-kbd-mou.md`) [OBS-RE; observed: in a session whose one process registered nothing,
  Ctrl-C ended the process].
- The focus is held but thread 1 has no 32-bit handler and no 16-bit handler, or all 32-bit
  handlers return `XCPT_CONTINUE_SEARCH` and there is no 16-bit handler: **the process is
  terminated** (normal termination; exit lists run) unless the signal's disposition is
  ignore/error or the process is already ending [OBS-RE; DOC-IBM: *"the process is
  terminated"*].

**A blocked read is interrupted, not completed.** A `KbdCharIn(IO_WAIT)` waiting when Ctrl-C
is posted to its thread answers **95 `ERROR_INTERRUPT`** - a return not on IBM's `KbdCharIn`
page: the keyboard driver's wait ends interrupted, the driver reports device status 11h, and the
kernel's status-to-error table maps 11h to 95; `KbdCharIn` returns that unchanged [OBS-RE].
The handler runs on the way out of that call, before the caller sees the 95 [INF].

**Observed** [OBS, Warp 4.5, 2026-10-13]: thread 1 with a counting handler returning
`XCPT_CONTINUE_EXECUTION` and the focus set. Ctrl-C during a blocked `KbdCharIn` -> the
handler ran once and the read answered 95; `DosAcknowledgeSignalException(1)` -> 0; two
Ctrl-C about 1 s apart while thread 1 looped on `DosSleep(100)` -> **both** delivered (count 2)
with no acknowledge call between - each handler return had acknowledged; a further
acknowledge -> 0 and nothing more. Not observed: a second Ctrl-C *during* a running handler
(the RE above predicts it is delivered once right after the handler returns, and a third is
lost).


**`DosSetSignalExceptionFocus`, measured** [OBS - measured on Warp Server for e-business 4.50,
kernel revision 14.089, 32-bit probe; the suite kept a results table, not the raw output]:
`*pulTimes` is the net count (set, set, unset leaves 1). Unsetting at a count of 0 returns 300
`ERROR_ALREADY_RESET`; a flag other than 0 or 1 returns 1; setting at the count 0xFFFF returns 650
`ERROR_NESTING_TOO_DEEP`. **A NULL `pulTimes`, or one at or above 512 MB, ends the process** with an
exception - it is not answered with 87. The one code IBM maps to a condition, 303 for a PM process,
was not reachable on the measuring system.

**Sending signals, measured** [OBS - measured on Warp Server for e-business 4.50, 32-bit and
16-bit probes]:

| Call | Result |
|---|---|
| `DosSendSignalException(own pid, n)` for n = 0, 2, 3, 9 | 209 `ERROR_INVALID_SIGNAL_NUMBER` |
| `DosSendSignalException(own pid, 1 or 4)` (`XCPT_SIGNAL_INTR` / `_BREAK`) | 1 |
| `DosSendSignalException` to a pid that does not exist | **205** `ERROR_NO_SIGNAL_SENT`, not 303 `ERROR_INVALID_PROCID` - IBM lists both and maps neither to a condition [DOC-IBM `cp1.txt`, "DosSendSignalException Return Value"] |
| 16-bit `DosSendSignal` to a child that registered no disposition | 205 |
| the same, to a child that registered `SIGA_IGNORE` | 0 |
| `DosKillProcess(DKP_PROCESS` or `DKP_PROCESSTREE`, nonexistent pid) | 303 |
| `DosKillProcess` with action 9, nonexistent pid | 13 - the action is checked before the pid |

So 205 means "no process accepted the signal": the 16-bit send selects on whether the target has a
disposition for it.

## Must-complete sections [DOC-IBM `bsedos.h:2395`]

A *must-complete* section defers asynchronous signal exceptions so a critical region runs
to completion without being interrupted by Ctrl-C / Ctrl-Break termination. The sections
nest.

| Function | Prototype | Purpose |
|---|---|---|
| `DosEnterMustComplete` | `APIRET APIENTRY DosEnterMustComplete(PULONG pulNesting)` | Begin (or nest deeper into) a must-complete section; `pulNesting` returns the new nesting level. |
| `DosExitMustComplete` | `APIRET APIENTRY DosExitMustComplete(PULONG pulNesting)` | Leave one level of must-complete section; `pulNesting` returns the remaining level. |

The per-thread must-complete state is held in the system TIB2 as `tib2_usMCCount` (the
nesting count) and `tib2_fMCForceFlag` (the force flag) [DOC-IBM `bsetib.h:40-41`].

## Related [DOC-IBM `bsedos.h:2401`]

`DosQueryThreadContext(TID tid, ULONG level, PCONTEXTRECORD pcxt)` captures another
thread's `CONTEXTRECORD` (subject to the requested `level`), the read-only counterpart to
the context a handler receives.

## Just-in-time debugging - the unhandled-exception handoff [OBS-RE]

When an exception reaches the kernel's default action with nothing having
handled it, OS/2 can hand the dying process to a **registered debugger** instead
of terminating it. The mechanism spans the kernel and `DOSCALL1.DLL`, and it is
**enabled by default** - the environment variable turns it OFF.

**Established from the shipped binaries. IBM documents none of it**: `NOJIT`,
`JITDBGREG=` and `JITDBGFLGS=` appear in *no* INF book, EDM2 page, DDK or
Toolkit header on this machine, nor in EDM2's own CONFIG.SYS statement list or
IBM's environment-variable reference online. The kernel symbols below are in
**both** the retail (`os2krnlb`) and debug (`os2krnld`) builds, identical sets
of seven, so this is not debug-only scaffolding.

**The chain, in order.**

| step | where | what |
|---|---|---|
| register | `syiRegisterJITDebug` (SYSINIT, ring 3) | reads **already-parsed** CONFIG.SYS data (`syiCopyConfigSysData`), walks two category-list entries, stores pointer/length pairs into kernel globals. Two statements - `JITDBGREG=` and `JITDBGFLGS=` |
| wait | `SysServJIT` / `SysServJIT2`, `_SysServWakeJIT` | a wait/wake pair, **not** a daemon body: test a flag, `SysServWait()`, retest, return `0x5f` if already signalled |
| decide | `_xcptDefaultAction` | the gate, below |
| launch | `_tkLaunchJITSession`, `_tkJITProcessLaunchRequest` | takes the **per-process** debugger at `PTDA+0x38` first, falling back to `_GlobalJITDbg` only when that is null |
| inherit | `_tkInheritJIT` | propagates the registration across process creation |

**THE GATE, and it is the part that matters for anyone deciding whether to
build this.** `_xcptDefaultAction` launches a JIT session only if **all** of:

```c
_JITDBGOveride == 0                          /* IBM's own kill switch, spelled thus */
&& *(int *)(_pPTDACur + 0x48) == 0
&& (*(byte *)(_pPTDACur + 0x3f) & 0x10) == 0
&& (*(int *)(_pPTDACur + 0x38) != 0 || _GlobalJITDbg != 0)   /* per-process OR global */
&& (*(uint *)(_pPTDACur + 0x3c) & 0x20000000) == 0
&& (*(uint *)(_pPTDACur + 0x3c) & 0x10000000) == 0
&& _tkLaunchJITSession(_pPTDACur) == 0
```

**With no debugger registered by either route the conjunction fails, no session
is launched, and control falls through to building the exception report and
terminating the process** - the ordinary crash path. So a system with no
`JITDBGREG=` behaves as though the subsystem were absent, which is why its
absence is invisible.

`_GlobalJITDbg` is read by `_xcptDefaultAction`, `_XCPTBuildR3DispatcherStack`
and `UserBPFault` - the unhandled-exception path, the ring-3 dispatcher stack
builder, and the user breakpoint fault handler. That set, rather than the "JIT"
in the names, is what establishes this as debugger machinery: a name is a hint,
not evidence.

**The session-manager end, and IBM's off switch.** `DOSCALL1`'s `INITDOSCALL1`
calls `DosScanEnv("NOJIT")` during session-manager init (the name is a string
constant in shared object 5):

- **not found** -> a 16->32 thunk reaches `JITInit2`, which `DosCreateThread`s a
  daemon with a 4096-byte stack; its ids land in `_JITDaemonTid` /
  `_JITDaemonTid2`
- **found** -> IBM skips the block entirely

The block is guarded once-per-**system** by a byte at obj5+0x14, in a SHARED
object, over state that is per process.

**So `NOJIT` is an opt-OUT: unset is the default and starts the daemon.**
Setting it is a supported configuration in which IBM's own code does not start
it - which is the honest way for an implementation without a debugger to decline
the subsystem, as against faking the daemon's return.

**Not established** (recorded rather than inferred): whether `DOSCALL1`'s
`JITInit2` daemon and the kernel's `SysServJIT` wait are the same rendezvous -
both are JIT-named and both wait, and the connection has not been traced;
what `JITDBGFLGS=` selects; and what the three non-registration gates above
(`PTDA+0x48`, flag `0x10` at `+0x3f`, and the two process-type bits at `+0x3c`)
test.

## See also
- `process-thread.md` - the per-thread TIB and the `FS:[0]` exception-registration chain the handler list is rooted in.
- `error-codes.md` - the `ERROR_*` return space (distinct from the `XCPT_*` exception codes here).
