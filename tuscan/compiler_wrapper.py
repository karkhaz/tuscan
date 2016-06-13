#!/usr/bin/env python3

from os import execv
from os.path import join
from random import seed, randint
from sys import argv, stderr

seed()
with open("/tmp/tuscan-native-%09d" % randint(0, 999999999), "w") as f:
    f.write("{{ native_program }}\n")

prog = join("{{ toolchain_bin }}", "{{ toolchain_program }}")
args = [prog] + argv[1:]

execv(prog, args)
