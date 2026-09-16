// ListAnalysisOptions.java - Ghidra headless preScript.
//
// Print every analysis option name and its current value for this program, one
// per line, tagged ANALYSIS_OPTION.  With arguments of the form
// "Some Option Name=false" it also SETS those options first (tagged
// ANALYSIS_SET), which is how a candidate analyzer is ruled in or out
// experimentally without writing a throwaway script per candidate.
//
// Why it exists: analysis options are addressed by free-text name, and a
// misspelled name silently does nothing - which is exactly why
// DisableNoreturnDiscovery.java reports "name drift?" rather than assuming.
// Run this once against the program in question and read the real names out of
// the log instead of guessing them.
//
// Args: ["Option Name=true|false" ...]
import ghidra.app.script.GhidraScript;
import ghidra.framework.options.Options;
import ghidra.program.model.listing.Program;

public class ListAnalysisOptions extends GhidraScript {
    public void run() throws Exception {
        Options o = currentProgram.getOptions(Program.ANALYSIS_PROPERTIES);
        for (String arg : getScriptArgs()) {
            int eq = arg.lastIndexOf('=');
            if (eq < 0) continue;
            String n = arg.substring(0, eq), v = arg.substring(eq + 1);
            if (!o.contains(n)) { println("ANALYSIS_SET\t" + n + "\tNOT PRESENT"); continue; }
            o.setBoolean(n, Boolean.parseBoolean(v));
            println("ANALYSIS_SET\t" + n + "\t= " + v);
        }
        for (String n : o.getOptionNames()) {
            println("ANALYSIS_OPTION\t" + n + "\t= " + o.getObject(n, null));
        }
    }
}
