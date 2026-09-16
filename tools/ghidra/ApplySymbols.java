// ApplySymbols.java - Ghidra headless preScript.
//
// Read a "0xVA name" file (from sym2map.py --format flat for LX, or
// ne_symva.py for NE) and, for every symbol landing in the loaded program:
//   1. apply a label, so decompiled code shows the real name; and
//   2. where the address is in EXECUTABLE memory, disassemble it and create a
//      Function there.
//
// Step 2 is not decoration.  A label alone does not make Ghidra's analyzer
// treat an address as a function: if nothing in the imported object calls it,
// the function-start heuristic has no seed, so it never becomes a Function -
// and DecompileAll.java, which iterates FunctionManager.getFunctions(), then
// silently skips it even though the symbol table gives its exact address and
// real name.  The symptom is an executable object that decompiles to zero
// functions despite having named symbols inside it.  Seeding every named
// entry point up front, and letting auto-analysis (which runs after every
// preScript) walk outward from there, is the fix rather than a workaround.
//
// The executable test is deliberate: the pipeline maps opposite-bitness code
// non-executable on purpose, and seeding a function there would produce
// exactly the misdecoded output that arrangement exists to prevent.
//
// Labels are created primary, so when several symbols share one address the
// LAST one applied names the function - which is why ne_symva.py emits linker
// and segment markers before real function names.
//
// Args: <symbol-file>   (lines of "0xVA name"; blank lines ignored)
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.mem.MemoryBlock;
import java.io.BufferedReader;
import java.io.FileReader;

public class ApplySymbols extends GhidraScript {
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 1) {
            println("ApplySymbols: usage: -preScript ApplySymbols.java <symbol-file>");
            return;
        }
        BufferedReader br = new BufferedReader(new FileReader(args[0]));
        String line;
        int applied = 0, skipped = 0, seeded = 0, seedFail = 0;
        while ((line = br.readLine()) != null) {
            line = line.trim();
            if (line.isEmpty()) continue;
            int sp = line.indexOf(' ');
            if (sp < 0) continue;
            long va = Long.decode(line.substring(0, sp));
            String name = line.substring(sp + 1).trim();
            Address a = toAddr(va);
            MemoryBlock blk = currentProgram.getMemory().getBlock(a);
            if (blk == null) { skipped++; continue; }
            try { createLabel(a, name, true); applied++; }
            catch (Exception e) { skipped++; continue; }

            if (blk.isExecute()) {
                try {
                    Function fn = getFunctionContaining(a);
                    if (fn == null) {
                        disassemble(a);
                        fn = createFunction(a, name);
                    }
                    if (fn != null) seeded++; else seedFail++;
                } catch (Exception e) {
                    seedFail++;
                }
            }
        }
        br.close();
        println("ApplySymbols: applied=" + applied + " skipped=" + skipped
                + " seeded=" + seeded + " seedFail=" + seedFail);
    }
}
