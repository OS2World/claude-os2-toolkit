// DumpBytes.java - Ghidra headless postScript.
//
// Print the program's memory block list (name, range, size, permissions,
// initialised state), then optionally write raw bytes from given addresses to
// files.  The block list is the quick check that LoadAllObjects.java mapped
// what you expected, at the bases you expected, with the permissions
// make_blocks.py intended - particularly that opposite-bitness code came in
// non-executable.
//
// The byte dump exists to correlate a flat address with the bytes actually
// mapped there, e.g. to compare against a raw disassembly at a different
// instruction width, or to check a data structure the decompiler rendered as
// an opaque blob.
//
// Args: [space offset length outfile] ...   (arguments in groups of four)
//   space   the address space / segment part, as Ghidra prints it
//   offset  the offset part, hex
//   e.g.  0001 17c0 512 /tmp/seg1_17c0.bin
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.mem.MemoryBlock;
import java.io.FileOutputStream;

public class DumpBytes extends GhidraScript {
    public void run() throws Exception {
        String[] args = getScriptArgs();
        Memory mem = currentProgram.getMemory();
        println("=== MEMORY BLOCKS ===");
        for (MemoryBlock b : mem.getBlocks()) {
            println(b.getName() + " start=" + b.getStart() + " end=" + b.getEnd()
                + " size=" + b.getSize()
                + " perms=" + (b.isRead() ? "R" : "-") + (b.isWrite() ? "W" : "-")
                + (b.isExecute() ? "X" : "-")
                + " initialized=" + b.isInitialized());
        }
        for (int i = 0; i + 3 < args.length; i += 4) {
            String space = args[i];
            String off = args[i + 1];
            int len = Integer.parseInt(args[i + 2]);
            String outfile = args[i + 3];
            Address a = currentProgram.getAddressFactory().getAddress(space + ":" + off);
            byte[] buf = new byte[len];
            int n = mem.getBytes(a, buf);
            FileOutputStream fos = new FileOutputStream(outfile);
            fos.write(buf, 0, n);
            fos.close();
            println("dumped " + n + " bytes from " + a + " to " + outfile);
        }
    }
}
