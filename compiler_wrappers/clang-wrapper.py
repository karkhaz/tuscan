#!/usr/bin/env python3

from os.path import basename
from sys import stderr

prog = basename(__file__)

print("tuscan: ignoring sysroot when invoking '%s'" % prog, file=stderr)

exit(1)
