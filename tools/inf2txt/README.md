# inf2txt - OS/2 INF/IPF help-file text extractor

Extracts readable article text from OS/2 INF/HLP (IPF) books, e.g. the IBM
Developer Connection library (cpgref, gpi1-4, pm1-5, pddref, mmref...).

- `inf2txt.pas`  - GUI-free console driver over fpGUI's docview INF parser
  (THelpFile/TTopic.GetText). Emits fpGUI richtext tags.
- `build.sh`     - build recipe (needs Free Pascal + fpGUI checkout; see header).
- `inf2txt.sh`   - wrapper: runs inf2txt and strips the richtext tags -> clean text.

Build first (no binary is shipped), then use:

    ./build.sh                              # one-time; writes ~/.local/share/os2-toolkit/inf2txt/inf2txt
    ./inf2txt.sh path/to/book.inf > book.txt

## Third-party note - read before redistributing a build

`inf2txt.pas` is ours (MIT, like the rest of this kit), but it is only a driver: the INF/IPF
parsing is done by **fpGUI**'s docview units (`HelpFile`, `HelpTopic`), which `build.sh` links in
from `docview/src/main/pascal`.

**fpGUI licenses per directory** (see its `LICENSE.txt`, (c) the fpGUI Toolkit authors,
`github.com/graemeg/fpGUI`):

| fpGUI directory | License |
|---|---|
| `framework` | modified LGPL |
| **`docview`** | **GPLv2** |

docview is **GPLv2, with no static-linking exception**. So the binary `build.sh` produces is a
**GPLv2 combined work**, even though our driver source is MIT. If you redistribute that binary you
must do so under GPLv2 and provide the corresponding source - this is copyleft, not a notice
requirement. Building it for your own use is unrestricted.

That is why this directory ships source and a build recipe and no compiled binary.

Provenance note: extracted text is authoritative IBM content -> tag [DOC-IBM]
in the corpus (cite the book, e.g. "IBM Control Program Guide & Reference (cpgref.inf)").
