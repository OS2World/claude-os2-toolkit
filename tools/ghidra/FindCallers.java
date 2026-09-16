// FindCallers.java - Ghidra headless postScript.
//
// For each hex address given as a script argument, print every reference TO
// that address, with the containing function of each referring instruction and
// the offset within it.  Run as a postScript so auto-analysis has already
// resolved calls; run against a program built by this pipeline so that
// cross-object calls exist to be found at all.
//
// Args: <addr> [addr ...]
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import ghidra.program.model.symbol.ReferenceManager;

public class FindCallers extends GhidraScript {
    public void run() throws Exception {
        ReferenceManager rm = currentProgram.getReferenceManager();
        for (String arg : getScriptArgs()) {
            Address target = toAddr(Long.decode(arg));
            println("=== references to " + target + " ===");
            ReferenceIterator refs = rm.getReferencesTo(target);
            int count = 0;
            for (Reference r : refs) {
                count++;
                Address from = r.getFromAddress();
                Function f = getFunctionContaining(from);
                String fn = (f != null)
                        ? f.getName() + "+0x" + Long.toHexString(from.subtract(f.getEntryPoint()))
                        : "?";
                println("  " + from + "  (" + r.getReferenceType() + ")  in " + fn);
            }
            if (count == 0) println("  (none found)");
        }
    }
}
