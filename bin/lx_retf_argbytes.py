#!/usr/bin/env python3
# PATH shim (plugin bin/): runs tools/lx_retf_argbytes.py from this checkout with the same arguments.
import os, sys
root = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
os.execv(sys.executable, [sys.executable, os.path.join(root, "tools", "lx_retf_argbytes.py")] + sys.argv[1:])
