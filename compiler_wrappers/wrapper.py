#!/usr/bin/env python3

from os.path import basename
from sys import stderr

prog = basename(__file__)

print("tuscan: native invocation of '%s'" % prog, file=stderr)

exit(1)
