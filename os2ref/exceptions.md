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
`XCPT_CONTINUE_EXECUTION` resumes the thread using the (possibly modified) `CONTEXTRECORD`.
If the chain is exhausted with no handler continuing execution, the process terminates. A
handler may also initiate an *unwind* (via `DosUnwindException`), which re-dispatches to the
handlers being removed with the `EH_UNWINDING` flag set so they can release resources before
the stack is discarded. [DOC-IBM / DOC]

> **CORRECTED (Rule 1.7):** this paragraph used to say *"the kernel dispatches to each handler
> in turn"*. The kernel does not walk the chain. **The walk happens in ring 3, in DOSCALL1**; the
> kernel builds the records beforehand and resumes the thread (or applies the default action)
> afterwards.

**How dispatch actually runs** [OBS-RE - the Warp 4.5 SMP kernel 14.104a and its debug build with
IBM's symbols; DOSCALL1. The kernel routine names below are present in the 14.104a UNI kernel's
`.sym` as well]:

1. **Kernel side.** `_XCPTBuildR3DispatcherStack` fills an `EXCEPTIONREPORTRECORD` and a
   `CONTEXTRECORD`, leaves a gap below the thread's `ESP`, pushes a frame holding the trap number
   and pointers to the two records, and sends the thread to DOSCALL1's ring-3 dispatcher (through
   the kernel variable `_pfnXcptDispatcher32`). The dispatcher is entered with `FS` = the TIB
   selector. **One exception:** if the chain is empty (`FS:[0]` = `-1`), the process is not being
   debugged and no floating-point state is involved, the kernel applies the default action itself.
   Guard-page and floating-point exceptions always go to ring 3.
2. **Ring-3 side.** The dispatcher walks the `FS:[0]` chain to `END_OF_CHAIN` (`-1`, not NULL),
   validating each record and its handler's memory, and grows the stack on a guard-page fault. It
   always finishes by calling back into the kernel with the final disposition; that call does not
   return. `DosRaiseException` reaches the same dispatcher.
3. **Resuming is done by the kernel.** For `XCPT_CONTINUE_EXECUTION`, `_xcptRestoreXcptContext`
   writes the context record back into the thread's saved register frame, and the record's `EAX`
   becomes the thread's `EAX`. For `XCPT_CONTINUE_SEARCH` from the last handler, the kernel falls
   back to any `DosSetVec` vector or the default action. Only the floating-point state is restored
   in ring 3, by a DOSCALL1 routine.

**The tell** (a consequence of the above, not separately observed): a stack trace taken inside a
handler has DOSCALL1 code between the faulting instruction and the handler. That is the
dispatcher, not a second fault inside DOSCALL1. Not re-verified here: DOSCALL1's ordinals for
these entries and the exact frame layout.

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

## Signals and signal focus [DOC-IBM `bsedos.h:2392`]

Asynchronous signals (Ctrl-C, Ctrl-Break, process termination) are delivered as
`XCPT_SIGNAL` exceptions to the process that holds the *signal focus*. A process claims or
releases the focus with `DosSetSignalExceptionFocus`, and a handler that has processed a
signal exception must acknowledge it with `DosAcknowledgeSignalException` before another of
the same class can be delivered.

| Function | Prototype | Purpose |
|---|---|---|
| `DosSetSignalExceptionFocus` | `APIRET APIENTRY DosSetSignalExceptionFocus(BOOL32 flag, PULONG pulTimes)` | Set (`SIG_SETFOCUS`) or release (`SIG_UNSETFOCUS`) the calling process's Ctrl-C / Ctrl-Break signal focus; `pulTimes` returns the current nesting count. |
| `DosAcknowledgeSignalException` | `APIRET APIENTRY DosAcknowledgeSignalException(ULONG ulSignalNum)` | Acknowledge a signal exception so a further signal of that number can be delivered. |

The focus flag values are `SIG_UNSETFOCUS` (`0`) and `SIG_SETFOCUS` (`1`) [DOC-IBM
`bsedos.h:2374`].

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

## See also
- `process-thread.md` - the per-thread TIB and the `FS:[0]` exception-registration chain the handler list is rooted in.
- `error-codes.md` - the `ERROR_*` return space (distinct from the `XCPT_*` exception codes here).
