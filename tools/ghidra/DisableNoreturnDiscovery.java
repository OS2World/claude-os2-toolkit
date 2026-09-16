// DisableNoreturnDiscovery.java - Ghidra headless preScript.
//
// Turn off Ghidra's "Non-Returning Functions - Discovered" (and "- Known")
// analyzers for this program.
//
// Why: on 16-bit segmented OS/2 code the discovery heuristic routinely
// misclassifies small leaf helpers - a strlen-class routine is the classic
// case - as non-returning.  Every caller's decompile is then truncated at the
// first call to it, and the rest of each caller's body is orphaned into bogus
// fragment functions.  The damage is silent: the truncated C looks like a
// short function rather than a broken one.
//
// The heuristic buys little on these binaries anyway: genuinely non-returning
// OS/2 paths end in a DosExit-family import, which in a raw-binary program is
// an unresolved external the analyzer cannot reason about either way.  So it
// is disabled wholesale rather than whitelisted per function.
//
// This MUST run as the first preScript: it sets analysis options, and those
// are only consulted when auto-analysis runs, which happens after every
// preScript.  If the option names ever drift, the script says so rather than
// silently doing nothing - run ListAnalysisOptions.java to get the real names.
import ghidra.app.script.GhidraScript;

public class DisableNoreturnDiscovery extends GhidraScript {
    @Override
    public void run() throws Exception {
        ghidra.program.model.listing.Program p = currentProgram;
        ghidra.framework.options.Options opts =
            p.getOptions(ghidra.program.model.listing.Program.ANALYSIS_PROPERTIES);
        // Exact option names as shown in the analysis summary table.
        for (String name : new String[]{
                "Non-Returning Functions - Discovered",
                "Non-Returning Functions - Known"}) {
            if (opts.contains(name)) {
                opts.setBoolean(name, false);
                println("DisableNoreturnDiscovery: disabled '" + name + "'");
            } else {
                println("DisableNoreturnDiscovery: option '" + name + "' not present (name drift?)");
            }
        }
    }
}
