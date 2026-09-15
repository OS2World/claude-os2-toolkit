# OS/2 Presentation Manager - Clipboard and Dynamic Data Exchange

The two Presentation Manager (PM) facilities for moving data *between applications*: the
**clipboard**, a single system-wide store used for one-time, user-initiated transfers (Copy /
Paste); and **Dynamic Data Exchange (DDE)**, a message-based protocol for ongoing, program-driven
conversations in which one application (the *client*) requests data or actions from another (the
*server*), optionally establishing a standing link that pushes updates as source data changes. The
two are independent - DDE neither uses nor depends on the clipboard - but they share a data-format
vocabulary (the `CF_*` / `SZFMT_*` names) and both rely on **shareable memory** to move a payload
across process boundaries.

Provenance: **[DOC-IBM]** the OS/2 Toolkit header `pmwin.h` (every prototype, structure, constant
value, and message id below is transcribed from it, cited `pmwin.h:line`); **[DOC-IBM]** the IBM
OS/2 Presentation Manager Programming Reference and Programming Guide, extracted as `pm2.txt`
(clipboard function/message reference), `pm3.txt` (DDE message reference), `pm4.txt` and
`pmv2base.txt` (DDE programming guide), for API semantics. Header symbols require
`INCL_WINCLIPBOARD` (clipboard) or `INCL_WINDDE` (DDE) before `<os2.h>`; the shared format/message
block is compiled under either.

---

## 1. The clipboard model [DOC-IBM]

The clipboard is a single, system-wide container that holds at most one data object *per format*
at a time. An application must **open** the clipboard before reading or writing it, and **close**
it afterward; opening serializes access across the whole system. Around the store sit three
distinguished roles:

- **The setter** - any application that puts data in, via `WinSetClipbrdData`.
- **The owner** - a window (`WinSetClipbrdData` makes the setting window's owner, or set explicitly
  with `WinSetClipbrdOwner`) that receives the clipboard notification messages, and in particular
  is asked to *render* delayed formats and to draw its own display format (Section 4).
- **The viewer** - an optional window, set with `WinSetClipbrdViewer`, that displays the current
  clipboard contents and is told (via `WM_DRAWCLIPBOARD`) whenever they change.

A reader "does not become the owner of the object in it; it must not update or free the object"
[DOC-IBM - pm2.txt, WinOpenClipbrd Remarks].

### Opening, closing, and emptying [DOC-IBM]

| Symbol | Prototype (from `pmwin.h`) | Purpose |
|---|---|---|
| `WinOpenClipbrd` | `BOOL APIENTRY WinOpenClipbrd(HAB hab)` | Open the clipboard for this process, locking out all other threads and processes. **If another thread or process already has it open, this call does not return until the clipboard is closed** (it can still receive messages while blocked). |
| `WinCloseClipbrd` | `BOOL APIENTRY WinCloseClipbrd(HAB hab)` | Close the clipboard, allowing others to open it. If the contents changed while open, this sends the viewer window a `WM_DRAWCLIPBOARD`. |
| `WinEmptyClipbrd` | `BOOL APIENTRY WinEmptyClipbrd(HAB hab)` | Remove and free all data handles in the clipboard (except formats flagged `CFI_OWNERFREE`). Sends the current owner a `WM_DESTROYCLIPBOARD`. The clipboard must be open first. |

Provenance: **[DOC-IBM]** `pmwin.h:3709-3711`; semantics from pm2.txt (WinOpenClipbrd,
WinCloseClipbrd, WinEmptyClipbrd). A data handle returned by a query **must not be used after
`WinCloseClipbrd`** - the reader copies or consumes it while the clipboard is still open
[DOC-IBM - pm2.txt, WinQueryClipbrdData Remarks].

### Owner and viewer [DOC-IBM]

| Symbol | Prototype (from `pmwin.h`) | Purpose |
|---|---|---|
| `WinSetClipbrdOwner` | `BOOL APIENTRY WinSetClipbrdOwner(HAB hab, HWND hwnd)` | Set the clipboard-owner window (`NULLHANDLE` releases ownership with no new owner). |
| `WinQueryClipbrdOwner` | `HWND APIENTRY WinQueryClipbrdOwner(HAB hab)` | Return the current owner window (`NULLHANDLE` if none / on error). |
| `WinSetClipbrdViewer` | `BOOL APIENTRY WinSetClipbrdViewer(HAB hab, HWND hwndNewClipViewer)` | Set the clipboard-viewer window (`NULLHANDLE` releases it). The clipboard must be open. |
| `WinQueryClipbrdViewer` | `HWND APIENTRY WinQueryClipbrdViewer(HAB hab)` | Return the current viewer window. |

Provenance: **[DOC-IBM]** `pmwin.h:3684-3685, 3695-3696, 3713-3714`. The owner window receives, at
appropriate times: `WM_DESTROYCLIPBOARD`, `WM_RENDERFMT`, `WM_RENDERALLFMTS`, `WM_PAINTCLIPBOARD`,
`WM_SIZECLIPBOARD`, `WM_HSCROLLCLIPBOARD`, `WM_VSCROLLCLIPBOARD` [DOC-IBM - pm2.txt,
WinSetClipbrdOwner Remarks]. The viewer window receives `WM_DRAWCLIPBOARD` when the contents change
[DOC-IBM - pm2.txt, WinSetClipbrdViewer Remarks].

---

## 2. Putting data in and taking it out [DOC-IBM]

### `WinSetClipbrdData` [DOC-IBM `pmwin.h:3686-3689`]

```c
BOOL APIENTRY WinSetClipbrdData(HAB hab, ULONG ulData, ULONG fmt, ULONG rgfFmtInfo);
```

Puts one data object of format `fmt` into the clipboard. `ulData` is a *general handle* to the
object; `rgfFmtInfo` (the `CFI_*` flags, Section 3) states the object's memory model and usage.
The clipboard must be open. Returns `TRUE` if placed, `FALSE` on error or if `ulData` is `NULL`
without a valid combination.

Key semantics [DOC-IBM - pm2.txt, WinSetClipbrdData]:

- **Ownership transfers to the system.** "An object passed to the clipboard becomes the property of
  the system, and is not deleted when the process that created it terminates." Once set, the setting
  application can no longer use the handle.
- **Data already present in that format is freed** by the call.
- **`CFI_POINTER` memory** must be a flat pointer to memory allocated *unnamed and shareable* by
  `DosAllocSharedMem` with the `OBJ_GIVEABLE` attribute. The system saves the address (accessing it
  from the shell process) so the data survives the setter's termination, and frees the memory from
  the setting process.
- **`ulData == NULLHANDLE` requests delayed rendering** (Section 4): a `WM_RENDERFMT` will be sent
  to the owner when the format is later queried.

### `WinQueryClipbrdData` [DOC-IBM `pmwin.h:3690-3691`]

```c
ULONG APIENTRY WinQueryClipbrdData(HAB hab, ULONG fmt);
```

Returns a handle to the current clipboard data of format `fmt`, or **0 if that format is not
present or on error**. The clipboard must be open. If the format was set for delayed rendering, the
query triggers the owner's `WM_RENDERFMT` and returns the freshly-rendered handle. The returned
handle is only valid until `WinCloseClipbrd`; the caller must not free it or leave it locked.

### `WinEnumClipbrdFmts` [DOC-IBM `pmwin.h:3707-3708`]

```c
ULONG APIENTRY WinEnumClipbrdFmts(HAB hab, ULONG fmt);
```

Walks the list of formats currently present. Pass `fmt = 0` to get the first available format;
pass the last returned value to get the next. **Returns 0 when enumeration is complete** (no more
formats). The clipboard should be open. [DOC-IBM - pm2.txt, WinEnumClipbrdFmts.]

### `WinQueryClipbrdFmtInfo` [DOC-IBM `pmwin.h:3692-3694`]

```c
BOOL APIENTRY WinQueryClipbrdFmtInfo(HAB hab, ULONG fmt, PULONG prgfFmtInfo);
```

Reports whether format `fmt` is present and, if so, writes its `CFI_*` flags to `*prgfFmtInfo`.
Returns `TRUE` (format present, `*prgfFmtInfo` set) or `FALSE` (absent, not set). **This does not
cause the data to be rendered.** The flags returned are those the setter supplied - standard bitmap
/ metafile formats read back `CFI_HANDLE`, text formats read back `CFI_POINTER`, and user-defined
formats read back whatever value was passed to `WinSetClipbrdData` [DOC-IBM - pm2.txt,
WinQueryClipbrdFmtInfo].

---

## 3. Standard formats and the `CFI_*` flags [DOC-IBM]

### Standard clipboard formats (`CF_*`) [DOC-IBM `pmwin.h:3614-3622`]

| Constant | Value | Meaning |
|---|---|---|
| `CF_TEXT` | `1` | Text. Lines end with CR/LF, fields separated by tab, a NULL signals end of data. |
| `CF_BITMAP` | `2` | Bit map (handle). |
| `CF_DSPTEXT` | `3` | Text *display* representation of a private format. |
| `CF_DSPBITMAP` | `4` | Bit-map display representation of a private format. |
| `CF_METAFILE` | `5` | Metafile (handle). |
| `CF_DSPMETAFILE` | `6` | Metafile display representation of a private format. |
| `CF_PALETTE` | `9` | Palette. |
| `CF_MMPMFIRST` | `10` | First of the reserved MMPM/2 (multimedia) format range. |
| `CF_MMPMLAST` | `19` | Last of the MMPM/2 format range. |

Format values above the predefined set are **private formats** created through the system atom
manager: register a name with `WinAddAtom(WinQuerySystemAtomTable(), "...")` and use the returned atom
as the format id; other applications recover the same id with `WinFindAtom`
[DOC-IBM - pm2.txt, WinQueryClipbrdFmtInfo Remarks]. `pmwin.h` also defines the equivalent
`SZFMT_*` *string* names used to register formats by name (`SZFMT_TEXT "#1"`,
`SZFMT_BITMAP "#2"`, ... `SZFMT_DIB "Dib"`, `SZFMT_OEMTEXT "OemText"`) [DOC-IBM `pmwin.h:3626-3644`].

### Format-info flags (`CFI_*`) [DOC-IBM `pmwin.h:3700-3703`]

Passed as `rgfFmtInfo` to `WinSetClipbrdData` and read back by `WinQueryClipbrdFmtInfo`. The flags
split into a **memory model** (exactly one of `CFI_POINTER` / `CFI_HANDLE`, unless
`CFI_OWNERDISPLAY` is used) and **usage flags** (any combination), OR'd together.

| Constant | Value | Kind | Meaning |
|---|---|---|---|
| `CFI_OWNERFREE` | `0x0001` | usage | The handle is **not** freed by `WinEmptyClipbrd`; the owner frees it itself. |
| `CFI_OWNERDISPLAY` | `0x0002` | usage | The owner draws this format in the viewer window via `WM_PAINTCLIPBOARD` (`ulData` should be `NULL`). |
| `CFI_HANDLE` | `0x0200` | memory model | `ulData` is a handle to a metafile or bit map. Required for `CF_BITMAP`, `CF_DSPBITMAP`, `CF_METAFILE`, `CF_DSPMETAFILE`. |
| `CFI_POINTER` | `0x0400` | memory model | `ulData` is a flat pointer to a shareable memory object. Required for `CF_TEXT`, `CF_DSPTEXT`. |

Provenance: **[DOC-IBM]** `pmwin.h:3700-3703`; the memory-model / usage rules and the per-format
requirements from pm2.txt (WinSetClipbrdData flFmtInfo).

---

## 4. Delayed (render-on-demand) rendering [DOC-IBM]

An application that can produce a format only on demand - because rendering is expensive, or it can
supply several formats - uses **delayed rendering**: it calls `WinSetClipbrdData` with
`ulData = NULLHANDLE` for each such format, and **must become the clipboard owner**. The format then
appears present (so `WinEnumClipbrdFmts` / `WinQueryClipbrdFmtInfo` report it), but the data is not
produced until someone asks for it.

- When another application calls `WinQueryClipbrdData` for a delayed format, the system sends the
  owner **`WM_RENDERFMT`**. The owner renders that one format and passes the pointer/handle back via
  `WinSetClipbrdData` (same shareable-memory rules as ordinary data); the query then returns the
  fresh handle. This is simply a deferred execution of the normal set operation
  [DOC-IBM - pm4.txt / pmv2base.txt, DDE-and-clipboard rendering].
- Just before the owning application **terminates** while it still holds delayed formats, the system
  sends **`WM_RENDERALLFMTS`** so the owner can render every format it is capable of and hand each to
  `WinSetClipbrdData`, ensuring the data outlives the owner
  [DOC-IBM - pm3.txt, WM_RENDERALLFMTS].

### Clipboard messages [DOC-IBM `pmwin.h:3602-3609`]

| Message | Value | Sent to | mp1 / carries |
|---|---|---|---|
| `WM_RENDERFMT` | `0x0060` | owner | `SHORT1FROMMP(mp1)` = the `CF_*` format to render now (mp2 reserved 0). |
| `WM_RENDERALLFMTS` | `0x0061` | owner | Render all formats before terminating (mp1/mp2 reserved 0). |
| `WM_DESTROYCLIPBOARD` | `0x0062` | owner | The clipboard was emptied (`WinEmptyClipbrd`). |
| `WM_PAINTCLIPBOARD` | `0x0063` | owner | Draw a `CFI_OWNERDISPLAY` format into the viewer window. |
| `WM_SIZECLIPBOARD` | `0x0064` | owner | Viewer window (owner-display) was resized. |
| `WM_HSCROLLCLIPBOARD` | `0x0065` | owner | Viewer horizontal scroll (owner-display). |
| `WM_VSCROLLCLIPBOARD` | `0x0066` | owner | Viewer vertical scroll (owner-display). |
| `WM_DRAWCLIPBOARD` | `0x0067` | viewer | The clipboard contents changed; the viewer should redisplay. |

Provenance: **[DOC-IBM]** `pmwin.h:3602-3609`; the `WM_RENDERFMT` format field and reserved
parameters from pm3.txt (WM_RENDERFMT / WM_RENDERALLFMTS).

---

## 5. Dynamic Data Exchange - the conversation model [DOC-IBM]

DDE is a **message protocol between two windows**, one per participating application; the windows
need not be visible (they are identified only by handle). The application that starts the exchange
is the **client**; the one that services requests is the **server**. A server can serve many clients
and a client can talk to many servers; an application can be both at once. The unit of work is a
**transaction** - a client request that the server acts on. Data crosses the process boundary in a
**shared-memory object** whose first bytes are a `DDESTRUCT` (Section 7). DDE is independent of the
clipboard [DOC-IBM - pm4.txt, About Dynamic Data Exchange].

A conversation is scoped by a **(application name, topic)** pair at initiation, and thereafter each
transaction names an **item** within the topic and a data **format**. The reserved system topic
`"System"` (`SZDDESYS_TOPIC`) and its items (`SZDDESYS_ITEM_TOPICS "Topics"`,
`SZDDESYS_ITEM_SYSITEMS "SysItems"`, `SZDDESYS_ITEM_FORMATS "Formats"`, `SZDDESYS_ITEM_STATUS`,
`SZDDESYS_ITEM_HELP`, ...) let a client discover what a server supports
[DOC-IBM `pmwin.h:4384-4395`].

### Initiation [DOC-IBM]

A client calls `WinDdeInitiate`, which fills a `DDEINIT` and **sends** (not posts)
`WM_DDE_INITIATE` to *all top-level frame windows whose parent is `HWND_DESKTOP`*. Because it is
sent, the call does not return until every recipient has responded. A potential server subclasses
its top-level frame to receive `WM_DDE_INITIATE`; if the application name matches (or is
zero-length) and it supports the topic (or the topic is zero-length), it replies by calling
`WinDdeRespond`, which sends `WM_DDE_INITIATEACK` back to the client
[DOC-IBM - pm4.txt, Client and Server Interaction / initiation]. Zero-length application or topic
strings are the discovery mechanism: a zero-length topic makes a server acknowledge *once per topic
it supports*, so a client can enumerate servers and topics [DOC-IBM - pm4.txt].

Two applications that already hold each other's window handles (by some other agreement) may
exchange DDE messages directly without the initiate sequence [DOC-IBM - pm4.txt].

### The five transaction types [DOC-IBM `pmwin.h:4487-4494`]

Within an established conversation the client drives one of five transactions, each with its own
message; the server answers with `WM_DDE_ACK`, `WM_DDE_DATA`, or a negative `WM_DDE_ACK`:

- **Request** (`WM_DDE_REQUEST`) - one-time pull of an item in a given format. Server replies
  `WM_DDE_DATA` (success) or negative `WM_DDE_ACK`. A client typically asks for its richest format
  first, then steps down through simpler formats on rejection.
- **Poke** (`WM_DDE_POKE`) - client pushes an unsolicited data item to the server; server replies
  positive/negative `WM_DDE_ACK`.
- **Advise** (`WM_DDE_ADVISE`) - client establishes a standing link on an item; thereafter the
  server posts `WM_DDE_DATA` on every change until unadvised. With `DDE_FNODATA` set the server
  posts only a *notification* (0-byte data) rather than the value. Multiple advise loops with
  different formats may coexist on one item.
- **Unadvise** (`WM_DDE_UNADVISE`) - client tears down a link (a zero-length item name tears down
  *all* links in the conversation). Server replies `WM_DDE_ACK`.
- **Execute** (`WM_DDE_EXECUTE`) - client sends a command string for the server to run; server
  replies positive/negative `WM_DDE_ACK`.

### Termination [DOC-IBM]

Either side ends the exchange by posting `WM_DDE_TERMINATE` (with a zero-length shared-memory
pointer). The recipient is expected to respond promptly by posting its own `WM_DDE_TERMINATE`
(rather than a `WM_DDE_ACK`), after which each side may destroy its DDE window. An application
must end all exchanges before terminating [DOC-IBM - pm4.txt, DDE Termination].

---

## 6. DDE functions [DOC-IBM]

| Symbol | Prototype (from `pmwin.h`) | Purpose |
|---|---|---|
| `WinDdeInitiate` | `BOOL APIENTRY WinDdeInitiate(HWND hwndClient, PSZ pszAppName, PSZ pszTopicName, PCONVCONTEXT pcctxt)` | Client: begin a conversation. Fills a `DDEINIT` and **sends** `WM_DDE_INITIATE` to all desktop-child frame windows. Zero-length app name = any app may respond; zero-length topic = respond once per supported topic. Returns `TRUE` if the message was sent to all appropriate windows. |
| `WinDdeRespond` | `MRESULT APIENTRY WinDdeRespond(HWND hwndClient, HWND hwndServer, PSZ pszAppName, PSZ pszTopicName, PCONVCONTEXT pcctxt)` | Server: acknowledge support for one topic. Fills a `DDEINIT` and sends `WM_DDE_INITIATEACK` to the client. App and topic names must be non-empty; a server responding for several topics uses a different `hwndServer` per topic. |
| `WinDdePostMsg` | `BOOL APIENTRY WinDdePostMsg(HWND hwndTo, HWND hwndFrom, ULONG wm, PDDESTRUCT pddest, ULONG flOptions)` | Post one transaction/response message (`WM_DDE_ACK/ADVISE/DATA/EXECUTE/POKE/REQUEST/TERMINATE/UNADVISE`) carrying a `DDESTRUCT` shared object. Automatically *gives* and then frees the shared object from the sender. |

Provenance: **[DOC-IBM]** `pmwin.h:4454-4458, 4467-4472, 4474-4478`; semantics from pm2.txt
(WinDdeInitiate / WinDdePostMsg / WinDdeRespond).

**`WinDdePostMsg` options** [DOC-IBM `pmwin.h:4480-4481`]:

| Constant | Value | Meaning |
|---|---|---|
| `DDEPM_RETRY` | `0x00000001` | If the target queue is full, retry at 1-second intervals until posted, meanwhile pumping the caller's own queue (`WinPeekMsg`/`WinDispatchMsg`) so the two apps cannot deadlock. Without it, a full queue returns `FALSE` immediately. |
| `DDEPM_NOFREE` | `0x00000002` | Do not free the shared object after posting. |

**Shared-memory discipline** [DOC-IBM - pm4.txt, Shared-Memory Object]: the sender allocates with
`DosAllocSharedMem`, writes a `DDESTRUCT` + item name + data, and calls `WinDdePostMsg` (which gives
the object to the recipient via `DosGiveSharedMem` and frees it from the sender's address space -
no `DosFreeMem` needed by the sender). The sender must not touch the object after posting; the
**recipient** calls `DosFreeMem` when done. The recipient's process id, needed to give the object,
comes from `WinQueryWindowProcess` on the recipient window.

---

## 7. DDE structures [DOC-IBM]

### `DDEINIT` - initiation data [DOC-IBM `pmwin.h:4413-4420`]

Carried as `mp2` of `WM_DDE_INITIATE` / `WM_DDE_INITIATEACK`. `WinDdeInitiate` / `WinDdeRespond`
fill it automatically; the receiving window procedure extracts the names and (per default
processing) frees the segment.

```c
typedef struct _DDEINIT {   /* ddei */
    ULONG   cb;              /* length of this structure          */
    PSZ     pszAppName;      /* server application name           */
    PSZ     pszTopic;        /* topic name                        */
    ULONG   offConvContext;  /* offset to a CONVCONTEXT (0 = none) */
} DDEINIT;
```

Application names must not contain slashes or backslashes (reserved for future network use)
[DOC-IBM - pm4.txt, DDEINIT pszAppName]. `offConvContext` is a byte offset (not a pointer) to a
`CONVCONTEXT`, recovered with the `DDEI_PCONVCONTEXT(pddei)` macro [DOC-IBM `pmwin.h:4506-4507`].
(An inline `DDEINIT` example in the programming guide still shows an obsolete 16-bit
`USHORT usConvContext` field; the version-correct Toolkit header - `ULONG offConvContext` - supersedes
it, Rule 1.2.)

### `CONVCONTEXT` - national-language conversation context [DOC-IBM `pmwin.h:4400-4409`]

```c
typedef struct _CONVCONTEXT {   /* cctxt */
    ULONG  cb;          /* sizeof(CONVCONTEXT)     */
    ULONG  fsContext;   /* DDECTXT_* flags         */
    ULONG  idCountry;
    ULONG  usCodepage;
    ULONG  usLangID;
    ULONG  usSubLangID;
} CONVCONTEXT;
```

`fsContext` may carry `DDECTXT_CASESENSITIVE` (`0x0001`) [DOC-IBM `pmwin.h:4411`].

### `DDESTRUCT` - the transaction control block [DOC-IBM `pmwin.h:4422-4430`]

The header of every shared-memory transaction object; the item-name string and the data follow it
in the same object, located by the offset fields (offsets, not pointers, so the block is
position-independent across address spaces).

```c
typedef struct _DDESTRUCT {   /* dde */
    ULONG   cbData;         /* length of the data after offabData (0 if none) */
    USHORT  fsStatus;       /* DDE_* status flags                             */
    USHORT  usFormat;       /* data format (DDEFMT_TEXT / a registered atom)  */
    USHORT  offszItemName;  /* offset from struct start to the item-name string */
    USHORT  offabData;      /* offset from struct start to the data           */
} DDESTRUCT;
```

- `offszItemName` points to a **null-terminated** item name; the item name is *always* null
  terminated - if there is no item, a single `0x00` sits at that position.
- `offabData` must be computed whether or not data is present; if there is no data, `cbData` is 0.
- The two helper macros locate the trailing fields:
  `DDES_PSZITEMNAME(pddes)` = `((PSZ)pddes) + pddes->offszItemName`, and
  `DDES_PABDATA(pddes)` = `((PBYTE)pddes) + pddes->offabData` [DOC-IBM `pmwin.h:4500-4504`].

**Status flags (`fsStatus`)** [DOC-IBM `pmwin.h:4433-4440`]:

| Constant | Value | Meaning |
|---|---|---|
| `DDE_FACK` | `0x0001` | Positive acknowledgement. |
| `DDE_FBUSY` | `0x0002` | Recipient is busy (received but cannot respond yet). |
| `DDE_FNODATA` | `0x0004` | Advise link carries notification only, no data. |
| `DDE_FACKREQ` | `0x0008` | Sender requests an acknowledgement. |
| `DDE_FRESPONSE` | `0x0010` | This is a response to a `WM_DDE_REQUEST`. |
| `DDE_NOTPROCESSED` | `0x0020` | The received message was not understood/supported. |
| `DDE_FRESERVED` | `0x00C0` | Reserved; must be 0. |
| `DDE_FAPPSTATUS` | `0xFF00` | Upper 8 bits reserved for application-specific status. |

**Format (`usFormat`)** [DOC-IBM - pm4.txt, DDESTRUCT usFormat]: `DDEFMT_TEXT` (`0x0001`,
`pmwin.h:4444`) is the system standard text format; otherwise a value registered with the atom
manager, conventionally named by the `SZFMT_*` / `SZDDEFMT_*` strings (`SZFMT_BITMAP`,
`SZFMT_CPTEXT`, `SZFMT_DIF`, `SZFMT_METAFILE`, `SZFMT_METAFILEPICT`, `SZFMT_SYLK`, `SZFMT_TIFF`,
`SZDDEFMT_RTF "Rich Text Format"`, ...) [DOC-IBM `pmwin.h:3626-3644`]. Registering a name in the
system atom table guarantees both applications derive the same format id.

The `MFP` (metafile) and `CPTEXT` (codepage text) payload structures used by the corresponding
formats are defined alongside, packed on a 2-byte boundary [DOC-IBM `pmwin.h:3652-3675`].

`CPTEXT` is four `USHORT`s - `idCountry`, `usCodepage`, `usLangID`, `usSubLangID` - followed by the
text itself (`abText`, declared with one element as the start of a variable-length tail) [DOC-IBM
`pmwin.h:3667-3674`]. Its name string is `SZFMT_CPTEXT`, `"Codepage Text"` [DOC-IBM `pmwin.h:3642`].

> **Codepage Text is documented for DDE, not for the clipboard.** `pmwin.h` introduces the `SZFMT_*`
> names with a comment calling them standard "DDE and clipboard" formats [DOC-IBM `pmwin.h:3624`],
> but IBM's books describe `SZFMT_CPTEXT` only as a DDE data format, for passing "multiple-language
> strings without changing the conversation context" [DOC-IBM - `pm4.txt`, DDESTRUCT `usFormat` and
> *Unique Data Formats*]. Searched `pm2.txt`-`pm5.txt` for any clipboard use of it: none. Before
> building a paste path around it, find out whether any PM application actually offers it.
> (Negative result.)
>
> Clipboard text can contain DBCS characters: IBM lists the clipboard as a source of DBCS input
> alongside the keyboard [DOC-IBM - *DBCS Design Guide and Information for OS/2*, *Keyboard Input*].

---

## 8. DDE messages [DOC-IBM `pmwin.h:4485-4496`]

All DDE messages carry the **sender's window handle in `mp1`**. Initiate messages carry a
`PDDEINIT` in `mp2`; every transaction/response message carries a `PDDESTRUCT` in `mp2`.

| Message | Value | mp2 | Role |
|---|---|---|---|
| `WM_DDE_INITIATE` | `0x00A0` | `PDDEINIT` | Client -> all desktop frames: request a conversation (sent, not posted). Default window proc frees the segment. |
| `WM_DDE_REQUEST` | `0x00A1` | `PDDESTRUCT` | Client -> server: one-time request for an item/format. |
| `WM_DDE_ACK` | `0x00A2` | `PDDESTRUCT` | Acknowledgement; the client/server reads `fsStatus` (`DDE_FACK` vs. not) to see if positive. |
| `WM_DDE_DATA` | `0x00A3` | `PDDESTRUCT` | Server -> client: requested/advised data. If `DDE_FACKREQ` set, recipient must `WM_DDE_ACK`. |
| `WM_DDE_ADVISE` | `0x00A4` | `PDDESTRUCT` | Client -> server: establish a standing update link on an item. |
| `WM_DDE_UNADVISE` | `0x00A5` | `PDDESTRUCT` | Client -> server: cancel a link (zero-length item = all links). |
| `WM_DDE_POKE` | `0x00A6` | `PDDESTRUCT` | Client -> server: push an unsolicited data item. |
| `WM_DDE_EXECUTE` | `0x00A7` | `PDDESTRUCT` | Client -> server: a command string to execute. |
| `WM_DDE_TERMINATE` | `0x00A8` | (empty) | End the conversation; recipient must reply `WM_DDE_TERMINATE`. |
| `WM_DDE_INITIATEACK` | `0x00A9` | `PDDEINIT` | Server -> client: acknowledge a topic (from `WinDdeRespond`). Default window proc frees the segment. |

`WM_DDE_FIRST` (`0x00A0`) and `WM_DDE_LAST` (`0x00AF`) bound the DDE message range for filters
[DOC-IBM `pmwin.h:4485,4496`]. During processing of `WM_DDE_INITIATE` / `WM_DDE_INITIATEACK` a
modal window (e.g. a message box) must **not** be invoked [DOC-IBM - pm3.txt, WM_DDE_INITIATE /
WM_DDE_INITIATEACK Remarks].

---

## 9. Passing a short string to another process - there is no `WM_COPYDATA` [OBS-RE]

Win32's one-instance idiom is `FindWindow` plus `WM_COPYDATA`. **PM has neither.** `WinPostMsg`
carries two `MPARAM`s and nothing else, and a pointer in one of them is meaningless in the receiving
process - it addresses the sender's memory. DDE (section 5) is the documented answer for a *conversation*,
but it is a lot of machinery for handing over one filename.

For a short string, the **system atom table** is the small answer. It "can be accessed by any
process in the system ... created at boot time and cannot be destroyed" [DOC-IBM `pm2.txt`,
*WinQuerySystemAtomTable - Remarks*], and an atom is exactly a string with a system-wide integer
name. So the string goes in the table and only the `ATOM` travels in the message:

```c
/* sender */
HATOMTBL tbl  = WinQuerySystemAtomTable();
ATOM     atom = WinAddAtom(tbl, (PCSZ)pszFullPath);
if (!WinPostMsg(hwndOther, MY_MSG, MPFROMLONG((LONG)atom), 0))
    WinDeleteAtom(tbl, atom);          /* nobody will collect it */

/* receiver */
WinQueryAtomName(WinQuerySystemAtomTable(), atom, (PSZ)szBuf, sizeof(szBuf));
WinDeleteAtom(WinQuerySystemAtomTable(), atom);   /* the delete is the release */
```

**Deleting the atom is not optional** - it is what drops the use count. An atom added and never
deleted stays in a table that lives until the machine reboots. Delete it on the failure path too, as
above, or the string leaks whenever the post fails.

**Finding the other instance** has no `FindWindow` either. Enumerate the desktop's frame children,
take each one's client, and compare class names:

```c
HENUM henum = WinBeginEnumWindows(HWND_DESKTOP);
while ((hwndFrame = WinGetNextWindow(henum)) != NULLHANDLE) {
    HWND hwndClient = WinWindowFromID(hwndFrame, FID_CLIENT);
    if (hwndClient && WinQueryClassName(hwndClient, sizeof(szClass), (PCH)szClass) > 0 &&
        strcmp(szClass, MY_CLIENT_CLASS) == 0) { /* found */ }
}
WinEndEnumWindows(henum);
```

Run that **before** creating your own window and there is no need to exclude yourself. Qualify any
path you send with `DosQueryPathInfo(..., FIL_QUERYFULLNAME, ...)` first: the two processes need not
share a working directory.

> **Testing note.** A one-instance feature usually hangs off a *persisted* setting, and a menu
> toggle changes the running instance's memory, not the file - so a second instance launched
> straight after the toggle still reads the old value and quietly opens its own window. The
> screenshot then shows the expected document and the test looks like it passed. **Count the
> processes**, which is the thing that actually distinguishes a hand-off from a second window.

---

## See also
- `pm-window-messaging.md` - the anchor block / message queue, the window procedure, `WinSendMsg` /
  `WinPostMsg`, `WinDefWindowProc`, and the `MPFROM*` / `*FROMMP` parameter-packing macros the
  clipboard and DDE messages use; and `HWND_DESKTOP`, the parent whose frame children receive
  `WM_DDE_INITIATE`.
- `memory-api.md` - `DosAllocSharedMem` (`OBJ_GIVEABLE`), `DosGiveSharedMem`, `DosFreeMem`: the
  shareable-memory objects that carry `CFI_POINTER` clipboard data and every DDE transaction.
- `gpi-drawing.md` - bit-map, metafile, and palette handles exchanged as `CF_BITMAP` / `CF_METAFILE`
  / `CF_PALETTE`.
