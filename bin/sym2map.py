#!/usr/bin/env python3
# PATH shim (plugin bin/): runs tools/sym2map.py from this checkout with the same arguments.
import os, sys
root = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
target = os.path.join(root, "tools", "sym2map.py")
os.execv(sys.executable, [sys.executable, target] + sys.argv[1:])
