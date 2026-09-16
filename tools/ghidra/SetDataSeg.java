// SetDataSeg.java - Ghidra headless preScript.
//
// Pin the DS segment register (and optionally ES) to a constant over every
// executable byte of the program, BEFORE disassembly happens.
//
// Why this is correct rather than a convenience: an NE module declares its
// automatic data segment in the NE header (the autodata field), and the OS/2
// calling contract for a 16-bit component of this kind is that the caller
// enters each entry point with DS already set to that segment.  So DS == the
// autodata segment genuinely holds across the module; it is not an assumption
// made for tidiness.  Check the contract for the module you are analysing
// before applying it - a component with a different convention needs a
// different value, or none.
//
// Without this, Ghidra's 16-bit protected-mode analysis recovers DS only
// where it can prove it locally, so a handful of functions get real global
// names while most render every global as a bare numeric offset
// (*(int *)0xb18).  With DS pinned, the same access decompiles as its real
// symbol name.  On an NE corpus this is the single largest readability
// difference.
//
// Args: <segvalue-decimal-or-hex> [ES]
//   e.g. "5"     -> DS=5 over all executable blocks
//        "5 ES"  -> also pin ES=5.  Do NOT do this where ES is the caller's
//                   buffer selector rather than the module's own data segment,
//                   which is the usual case for a driver or file system.
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.lang.Register;
import ghidra.program.model.listing.ProgramContext;
import ghidra.program.model.mem.MemoryBlock;
import java.math.BigInteger;

public class SetDataSeg extends GhidraScript {
    public void run() throws Exception {
        String[] a = getScriptArgs();
        long val = (a.length > 0) ? Long.decode(a[0]) : 0;
        boolean alsoEs = (a.length > 1 && a[1].equalsIgnoreCase("ES"));

        ProgramContext ctx = currentProgram.getProgramContext();
        Register ds = ctx.getRegister("DS");
        Register es = ctx.getRegister("ES");
        if (ds == null) { println("SetDataSeg: no DS register in this language"); return; }

        int n = 0;
        for (MemoryBlock b : currentProgram.getMemory().getBlocks()) {
            if (!b.isExecute()) continue;
            Address s = b.getStart(), e = b.getEnd();
            ctx.setValue(ds, s, e, BigInteger.valueOf(val));
            if (alsoEs && es != null) ctx.setValue(es, s, e, BigInteger.valueOf(val));
            println("SetDataSeg: DS=0x" + Long.toHexString(val) + " over " + b.getName()
                    + " [" + s + ".." + e + "]");
            n++;
        }
        println("SetDataSeg: pinned over " + n + " executable block(s)");
    }
}
