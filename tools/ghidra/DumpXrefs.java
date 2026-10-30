// DumpXrefs.java - Ghidra headless postScript.
// Writes the cross-reference skeleton of the current program as TSV, for
// tooling that builds per-function / per-global documentation tables without
// scraping decompiled C text.  Arg 0: output file.
//
// Only functions whose entry point is in an EXECUTABLE block are emitted -
// the same rule DecompileAll.java applies, for the same reason (opposite-
// bitness objects are mapped non-executable and anything Ghidra invents in
// them is a wrong-bitness decode).
//
// Row types (first column):
//   F  entry  name  body_min  body_max  body_bytes  n_instr  block
//   C  from_entry  to_entry  to_name  site          (call / unconditional-jump-to-function from inside from's body)
//   D  from_entry  target  target_sym  target_sym_addr  reftype  site   (non-flow reference to memory)
//   S  addr  name  block  exec(0/1)                   (every primary symbol, for data catalogs)
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSetView;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionManager;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.RefType;
import ghidra.program.model.symbol.Symbol;
import ghidra.program.model.symbol.SymbolIterator;
import ghidra.program.model.symbol.SymbolTable;
import java.io.PrintWriter;

public class DumpXrefs extends GhidraScript {
    private String symAt(Address a, SymbolTable st) {
        Symbol s = st.getPrimarySymbol(a);
        return s == null ? "-" : s.getName();
    }

    public void run() throws Exception {
        String[] args = getScriptArgs();
        PrintWriter pw = new PrintWriter(args[0]);
        FunctionManager fm = currentProgram.getFunctionManager();
        SymbolTable st = currentProgram.getSymbolTable();
        int nf = 0;
        for (Function fn : fm.getFunctions(true)) {
            if (monitor.isCancelled()) break;
            MemoryBlock eb = currentProgram.getMemory().getBlock(fn.getEntryPoint());
            if (eb == null || !eb.isExecute()) continue;
            nf++;
            AddressSetView body = fn.getBody();
            int ni = 0;
            InstructionIterator it = currentProgram.getListing().getInstructions(body, true);
            StringBuilder rows = new StringBuilder();
            while (it.hasNext()) {
                Instruction ins = it.next();
                ni++;
                for (Reference r : ins.getReferencesFrom()) {
                    Address to = r.getToAddress();
                    if (!to.isMemoryAddress()) continue;
                    RefType rt = r.getReferenceType();
                    if (rt.isFlow()) {
                        if (rt.isCall() || rt.isJump()) {
                            Function tf = fm.getFunctionAt(to);
                            if (tf != null && (rt.isCall() || !tf.getEntryPoint().equals(fn.getEntryPoint()))) {
                                if (rt.isCall() || !body.contains(to)) {
                                    rows.append("C\t").append(fn.getEntryPoint()).append('\t')
                                        .append(to).append('\t').append(tf.getName()).append('\t')
                                        .append(ins.getAddress()).append('\n');
                                }
                            } else if (rt.isCall()) {
                                rows.append("C\t").append(fn.getEntryPoint()).append('\t')
                                    .append(to).append('\t').append(symAt(to, st)).append('\t')
                                    .append(ins.getAddress()).append('\n');
                            }
                        }
                        continue;
                    }
                    // data reference: resolve to nearest preceding symbol
                    Symbol s = st.getPrimarySymbol(to);
                    Address sa = to;
                    if (s == null) {
                        SymbolIterator si = st.getSymbolIterator(to, false);
                        if (si.hasNext()) { s = si.next(); sa = s.getAddress(); }
                    }
                    rows.append("D\t").append(fn.getEntryPoint()).append('\t').append(to).append('\t')
                        .append(s == null ? "-" : s.getName()).append('\t').append(s == null ? "-" : sa.toString())
                        .append('\t').append(rt.getName()).append('\t').append(ins.getAddress()).append('\n');
                }
            }
            pw.print("F\t" + fn.getEntryPoint() + "\t" + fn.getName() + "\t" + body.getMinAddress() + "\t"
                     + body.getMaxAddress() + "\t" + body.getNumAddresses() + "\t" + ni + "\t" + eb.getName() + "\n");
            pw.print(rows);
        }
        SymbolIterator si = st.getAllSymbols(false);
        while (si.hasNext()) {
            Symbol s = si.next();
            if (!s.isPrimary() || !s.getAddress().isMemoryAddress()) continue;
            MemoryBlock b = currentProgram.getMemory().getBlock(s.getAddress());
            pw.print("S\t" + s.getAddress() + "\t" + s.getName() + "\t" + (b == null ? "-" : b.getName())
                     + "\t" + (b != null && b.isExecute() ? 1 : 0) + "\n");
        }
        pw.close();
        println("DumpXrefs: " + nf + " functions written to " + args[0]);
    }
}
