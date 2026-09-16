// DumpStackFrame.java - Ghidra headless postScript.
//
// For a named function, run a fresh decompile and dump the HighFunction's own
// local symbol map: every recovered variable, parameters and locals alike,
// with the storage the decompiler actually used - the stack offset for a
// stack-based variable, the register otherwise.
//
// Why not Function.getParameters(): that list is empty unless a decompile
// result was explicitly committed back to the program database, and a
// whole-module run never commits (it only writes C text).  So the database
// says a function has no parameters while the .c file beside it clearly shows
// several.  This script reports what the decompiler saw, which is the thing
// that produced the C you are reading - the right source for reconstructing a
// calling convention or a frame layout.
//
// With the optional second argument "1", an address that has a symbol but no
// Function object is disassembled and turned into one first.
//
// Args: <symbolName> [seedIfMissing(0/1)]
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.pcode.HighFunction;
import ghidra.program.model.pcode.HighSymbol;
import ghidra.program.model.pcode.LocalSymbolMap;
import ghidra.program.model.symbol.Symbol;
import ghidra.program.model.symbol.SymbolIterator;
import ghidra.program.model.symbol.SymbolTable;
import java.util.Iterator;

public class DumpStackFrame extends GhidraScript {
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 1) {
            println("DumpStackFrame: usage: DumpStackFrame.java <symbolName> [seedIfMissing(0/1)]");
            return;
        }
        String name = args[0];
        boolean seedIfMissing = args.length > 1 && args[1].equals("1");

        SymbolTable st = currentProgram.getSymbolTable();
        SymbolIterator it = st.getSymbols(name);
        Function fn = null;
        Address addr = null;
        while (it.hasNext()) {
            Symbol s = it.next();
            addr = s.getAddress();
            fn = currentProgram.getFunctionManager().getFunctionAt(addr);
            if (fn != null) break;
        }
        if (fn == null && addr != null && seedIfMissing) {
            println(name + ": no Function object, seeding at " + addr);
            disassemble(addr);
            fn = createFunction(addr, null);
            if (fn == null) fn = getFunctionAt(addr);
        }
        if (fn == null) {
            println("FUNCTION NOT FOUND (or not seeded): " + name
                    + (addr != null ? " symbol addr=" + addr : " no symbol either"));
            return;
        }
        println("function: " + fn.getName() + " @ " + fn.getEntryPoint()
                + " callingConv=" + fn.getCallingConventionName());

        DecompInterface dec = new DecompInterface();
        dec.openProgram(currentProgram);
        DecompileResults res = dec.decompileFunction(fn, 120, monitor);
        if (res.getDecompiledFunction() == null) {
            println("DECOMPILE FAILED for " + name + ": " + res.getErrorMessage());
            return;
        }
        HighFunction hf = res.getHighFunction();
        if (hf == null) {
            println("no HighFunction for " + name);
            return;
        }
        LocalSymbolMap lsm = hf.getLocalSymbolMap();
        println("  numParams=" + lsm.getNumParams());
        Iterator<HighSymbol> symIt = lsm.getSymbols();
        while (symIt.hasNext()) {
            HighSymbol hs = symIt.next();
            println("  sym: " + hs.getName()
                    + "  isParam=" + hs.isParameter()
                    + "  slot=" + hs.getCategoryIndex()
                    + "  type=" + hs.getDataType()
                    + "  storage=" + hs.getStorage()
                    + "  pcAddr=" + hs.getPCAddress());
        }
    }
}
