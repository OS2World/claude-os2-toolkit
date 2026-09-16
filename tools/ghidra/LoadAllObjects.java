// LoadAllObjects.java - Ghidra headless preScript.
//
// Merge every object/segment of an OS/2 module into the program that the
// primary -import already created, each at its true base address.
//
// Why this is necessary: an LX or NE module is not one image.  Its objects are
// separate segments loaded at separate, widely-spaced flat addresses recorded
// in the module's own object/segment table.  Import one of them alone and a
// call from that object into another is a reference into unmapped memory:
// Ghidra cannot follow it, the decompiler renders it as a bare address, and
// auto-analysis never discovers the functions on the far side.  Mapping every
// object at its REAL base is what makes cross-object references resolve, and
// it is also what lets a decompiled access to a global show the data that is
// actually there.
//
// KNOWN LIMITATION, recorded rather than glossed over: a Ghidra Program has
// exactly one Language.  OS/2 modules routinely mix 16-bit and 32-bit code
// objects, and only objects matching this program's language disassemble
// correctly.  The pipeline therefore builds one program per bitness and the
// block-spec generator (make_blocks.py) clears the execute bit on
// opposite-bitness CODE objects, so the analyzer does not walk them.  Their
// bytes are still present, correctly based, for pattern search and for manual
// disassembly at the right width - but do not trust any auto-generated
// "function" that lands inside such a block.  bitness_index.py exists to find
// the ones that appear anyway.
//
// Input: a spec file, one line per object: "num base_hex size perm binpath",
// as written by make_blocks.py from an exporter's manifest.json.  The object
// whose base is already mapped (the primary -import) is skipped.
//
// Args: <blocks-spec-file>
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.mem.MemoryBlock;
import java.io.BufferedReader;
import java.io.FileReader;
import java.nio.file.Files;
import java.nio.file.Paths;

public class LoadAllObjects extends GhidraScript {
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 1) {
            println("LoadAllObjects: usage: -preScript LoadAllObjects.java <blocks-spec-file>");
            return;
        }
        String specPath = args[0];
        BufferedReader br = new BufferedReader(new FileReader(specPath));
        String line;
        int added = 0, skipped = 0;
        while ((line = br.readLine()) != null) {
            line = line.trim();
            if (line.isEmpty()) continue;
            String[] parts = line.split("\\s+");
            if (parts.length != 5) continue;
            int num = Integer.parseInt(parts[0]);
            long base = Long.decode(parts[1]);
            long size = Long.parseLong(parts[2]);
            String perm = parts[3];
            String binPath = parts[4];

            if (currentProgram.getMemory().contains(toAddr(base))) {
                println("skip obj " + num + " @0x" + Long.toHexString(base)
                        + " - already mapped (the primary imported block)");
                skipped++;
                continue;
            }

            byte[] data = Files.readAllBytes(Paths.get(binPath));
            if (data.length != size) {
                println("WARNING obj " + num + ": file size " + data.length
                        + " != manifest size " + size);
            }
            Address start = toAddr(base);
            MemoryBlock blk;
            try {
                blk = createMemoryBlock("obj" + num, start, data, false);
            } catch (Exception e) {
                println("FAILED obj " + num + " @0x" + Long.toHexString(base)
                        + ": " + e.getMessage());
                continue;
            }
            blk.setRead(true);
            blk.setWrite(perm.charAt(1) == 'W');
            blk.setExecute(perm.charAt(2) == 'X');
            println("added obj " + num + " @0x" + Long.toHexString(base)
                    + " size=0x" + Long.toHexString(size) + " perm=" + perm);
            added++;
        }
        br.close();
        println("LoadAllObjects: " + added + " blocks added, " + skipped + " skipped (primary)");
    }
}
