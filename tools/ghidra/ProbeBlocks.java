// ProbeBlocks.java - Ghidra headless script.
//
// Print the program's image base, every memory block with its range, size,
// permissions and initialised state, and the first symbols Ghidra knows about.
// This is the one-line sanity check for a pipeline run: it answers "did the
// objects land where the module's own table says they should, with the
// permissions the block spec asked for", before any conclusion is drawn from
// a decompile.
//
// Args: [maxSymbols]   (default 40)
import ghidra.app.script.GhidraScript;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.Symbol;
import ghidra.program.model.symbol.SymbolTable;

public class ProbeBlocks extends GhidraScript {
    public void run() throws Exception {
        String[] args = getScriptArgs();
        int max = (args.length > 0) ? Integer.parseInt(args[0]) : 40;
        println("IMAGEBASE=" + currentProgram.getImageBase());
        for (MemoryBlock b : currentProgram.getMemory().getBlocks()) {
            println(String.format("BLOCK %-12s start=%s end=%s size=0x%x r=%b w=%b x=%b init=%b",
                b.getName(), b.getStart(), b.getEnd(), b.getSize(),
                b.isRead(), b.isWrite(), b.isExecute(), b.isInitialized()));
        }
        SymbolTable st = currentProgram.getSymbolTable();
        int n = 0;
        for (Symbol s : st.getAllSymbols(true)) {
            if (n++ >= max) break;
            println("SYM " + s.getName() + " @ " + s.getAddress() + " (" + s.getSymbolType() + ")");
        }
        println("ProbeBlocks: " + n + " symbol(s) shown");
    }
}
