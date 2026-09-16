// FindSym.java - Ghidra headless script.
//
// Print every symbol whose name contains the given substring, with its
// address.  Useful after ApplySymbols.java to confirm that a .SYM's names
// actually landed in mapped memory, and to find the address of a routine you
// only know by name.  Matching is case-sensitive substring matching; OS/2
// .SYM names are conventionally upper case.
//
// To dump bytes at an address, use DumpBytes.java.
//
// Args: <substring>
import ghidra.app.script.GhidraScript;
import ghidra.program.model.symbol.Symbol;
import ghidra.program.model.symbol.SymbolIterator;
import ghidra.program.model.symbol.SymbolTable;

public class FindSym extends GhidraScript {
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 1) {
            println("FindSym: usage: FindSym.java <substring>");
            return;
        }
        String needle = args[0];
        SymbolTable st = currentProgram.getSymbolTable();
        SymbolIterator it = st.getAllSymbols(true);
        int n = 0;
        while (it.hasNext()) {
            Symbol s = it.next();
            if (s.getName().contains(needle)) {
                println("SYM " + s.getName() + " @ " + s.getAddress()
                        + " (" + s.getSymbolType() + ")");
                n++;
            }
        }
        println("FindSym: " + n + " symbol(s) matching '" + needle + "'");
    }
}
