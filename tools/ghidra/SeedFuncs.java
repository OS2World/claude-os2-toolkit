// SeedFuncs.java - Ghidra headless preScript.
//
// Seed functions by OFFSET within the program's first executable block, for
// the case where there is no .SYM at all and the entry points are known from
// somewhere else: a driver's own header, an entry table, a dump, or a hand
// disassembly.  Each argument is "offset[:name]" in hex, relative to the
// start of that block; without a name the function is called fn_<offset>.
//
// When addresses are known as flat VAs rather than offsets, use
// ApplySymbols.java with a "0xVA name" file instead - it is the same
// mechanism (disassemble, then createFunction) driven from a file, and it
// checks that the address is in executable memory.
//
// Args: <off[:name]> [off[:name] ...]     e.g.  1a4:Init  2e0:ReadSector
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.mem.MemoryBlock;

public class SeedFuncs extends GhidraScript {
    public void run() throws Exception {
        String[] a = getScriptArgs();
        if (a.length < 1) {
            println("SeedFuncs: usage: SeedFuncs.java <off[:name]> [off[:name] ...]");
            return;
        }
        MemoryBlock code = null;
        for (MemoryBlock b : currentProgram.getMemory().getBlocks()) {
            if (b.isExecute()) { code = b; break; }
        }
        if (code == null) { println("SeedFuncs: no executable block in this program"); return; }
        println("code block " + code.getName() + " @ " + code.getStart());

        for (String spec : a) {
            String[] p = spec.split(":");
            long off = Long.parseLong(p[0], 16);
            String nm = (p.length > 1) ? p[1] : ("fn_" + p[0]);
            Address addr = code.getStart().add(off);
            try {
                disassemble(addr);
                createFunction(addr, nm);
                println("seeded " + nm + " @ " + addr);
            } catch (Exception e) {
                println("FAIL " + nm + " @ " + addr + ": " + e);
            }
        }
    }
}
