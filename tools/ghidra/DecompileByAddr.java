// DecompileByAddr.java - Ghidra headless postScript.
//
// Decompile one or more functions named by ADDRESS, rather than the whole
// program, writing "<function>_<address>.c" per function into the output
// directory given as argument 0.  Use it to re-examine a handful of routines
// (with a longer per-function timeout than the whole-module run allows), or
// to reach code that auto-analysis never turned into a function at all: if
// there is no function at or containing the address, the script disassembles
// there and creates one.
//
// Addresses are flat values as the module's own tables give them, e.g.
// 0x1e830100.  In a 16-bit program Ghidra renders the same address segmented.
//
// Args: <output-directory> <addr> [addr ...]
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.util.task.ConsoleTaskMonitor;
import java.io.File;
import java.io.PrintWriter;

public class DecompileByAddr extends GhidraScript {
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 2) {
            println("DecompileByAddr: usage: -postScript DecompileByAddr.java "
                    + "<output-directory> <addr> [addr ...]");
            return;
        }
        File outdir = new File(args[0]);
        outdir.mkdirs();

        DecompInterface dec = new DecompInterface();
        dec.openProgram(currentProgram);

        for (int i = 1; i < args.length; i++) {
            Address addr = toAddr(Long.decode(args[i]));
            Function fn = getFunctionContaining(addr);
            if (fn == null) {
                disassemble(addr);
                fn = createFunction(addr, null);
            }
            if (fn == null) { println("NO FUNCTION at " + args[i]); continue; }
            DecompileResults res = dec.decompileFunction(fn, 120, new ConsoleTaskMonitor());
            String c = (res.getDecompiledFunction() == null)
                    ? "// decompile failed: " + res.getErrorMessage()
                    : res.getDecompiledFunction().getC();
            String safeName = fn.getName().replaceAll("[^A-Za-z0-9_.$@-]", "_");
            File out = new File(outdir, safeName + "_" + fn.getEntryPoint() + ".c");
            PrintWriter pw = new PrintWriter(out);
            pw.println("// " + fn.getName() + " @ " + fn.getEntryPoint()
                    + "  (requested " + addr + ")");
            pw.println(c);
            pw.close();
            println("WROTE " + out.getPath());
        }
    }
}
