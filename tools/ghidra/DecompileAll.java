// DecompileAll.java - Ghidra headless postScript.
//
// Decompile EVERY function Ghidra found in the current program to C, one file
// per function, named "<function>_<entry point>.c" under the directory given
// as script argument 0 (default: "decompiled" in the working directory).
// Functions are decompiled with a 30-second cap each, so one pathological
// function cannot stall a whole-module run.
//
// SKIPS any function whose entry point is not in an EXECUTABLE memory block.
// This filter is the honest one, and it is load-bearing.  The pipeline marks
// opposite-bitness CODE objects non-executable on purpose (make_blocks.py),
// LoadAllObjects.java honours that and ApplySymbols.java seeds only where the
// block is executable - but Ghidra's own auto-analysis does not: measured, it
// creates hundreds to thousands of functions inside such blocks, most of them
// analyzer-invented FUN_* names, and without this check the script faithfully
// writes a .c file for every one.  Those files are a module's real code
// decoded at the wrong instruction width: plausible-looking C that means
// nothing, and over half of them carry no Ghidra warning at all.
//
// Turning off the reference analyzers instead was tried and REJECTED on
// measurement: on a 16-bit pass, disabling the x86 constant-reference,
// subroutine-reference, scalar-operand and data-reference analyzers only
// halved the bad functions while losing dozens of genuine ones.  The block's
// execute flag is the property that is actually correct and actually set, so
// the filter belongs here, at the point a file is emitted.  Such functions
// still exist in Ghidra's database (harmless there); they simply stop
// becoming files that a later reader mistakes for evidence.
//
// Args: [output-directory]
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionManager;
import ghidra.util.task.ConsoleTaskMonitor;
import java.io.File;
import java.io.PrintWriter;

public class DecompileAll extends GhidraScript {
    public void run() throws Exception {
        String[] args = getScriptArgs();
        String outDirPath = (args.length > 0) ? args[0] : "decompiled";
        File outdir = new File(outDirPath);
        outdir.mkdirs();

        DecompInterface dec = new DecompInterface();
        dec.openProgram(currentProgram);

        FunctionManager fm = currentProgram.getFunctionManager();
        int total = fm.getFunctionCount();
        println("DecompileAll: " + total + " functions to decompile");

        int ok = 0, fail = 0, n = 0, skippedNonExec = 0;
        for (Function fn : fm.getFunctions(true)) {
            n++;
            if (monitor.isCancelled()) break;
            ghidra.program.model.mem.MemoryBlock eb =
                    currentProgram.getMemory().getBlock(fn.getEntryPoint());
            if (eb == null || !eb.isExecute()) {
                skippedNonExec++;
                continue;
            }
            String safeName = fn.getName().replaceAll("[^A-Za-z0-9_.$@-]", "_");
            File out = new File(outdir, safeName + "_" + fn.getEntryPoint() + ".c");
            try {
                DecompileResults res = dec.decompileFunction(fn, 30, new ConsoleTaskMonitor());
                String c = (res.getDecompiledFunction() == null)
                        ? "// decompile failed: " + res.getErrorMessage()
                        : res.getDecompiledFunction().getC();
                PrintWriter pw = new PrintWriter(out);
                pw.println("// " + fn.getName() + " @ " + fn.getEntryPoint());
                pw.println(c);
                pw.close();
                if (res.getDecompiledFunction() != null) ok++; else fail++;
            } catch (Exception e) {
                fail++;
                println("EXCEPTION on " + fn.getName() + ": " + e.getMessage());
            }
            if (n % 200 == 0) println("progress: " + n + "/" + total);
        }
        println("DecompileAll: done. ok=" + ok + " fail=" + fail + " total=" + total
                + " skipped_non_executable=" + skippedNonExec);
    }
}
