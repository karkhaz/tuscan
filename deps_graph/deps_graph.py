#!/usr/bin/env python3
#
# Copyright 2015 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Outputs dependency relationships between all Arch packages in the ABS.

This script generates a list of 3-tuples of the form

  pack1  pack2  [depends] OR [makedepends] OR [checkdepends]

(the square brackets are actually printed).
Each such item means that pack2 is a dependency of pack1; the third item
describes what kind of dependency it is.
"""

from datetime import datetime
from glob import glob
from os import kill
from os import waitpid
from os import WNOHANG
from os.path import basename
import re
from signal import SIGKILL
from subprocess import PIPE
from subprocess import Popen
from subprocess import TimeoutExpired
from sys import stderr
import tempfile
from textwrap import dedent
import time


class Dependency(object):
    # pylint: disable=too-few-public-methods
    """A triple describing a dependency relationship.

    Attributes:
        src: a package that depends on dst.
        dst: a package depended on by src.
        kind: the kind of dependency; one of depends, makedepends, or
              checkdepends.
    """

    def __init__(self, src, dst, kind):
        self.src = src

        # Some dependencies are specified as needing a certain version,
        # i.e.  glibc>=4.8 or java-runtime=8. We don't want the part
        # from >= onwards, as we shall always have an up-to-date system.
        for pat in [r">=", r"<=", r"=", r"<", r">"]:
            depth = re.search(pat, dst)
            if depth:
                dst = dst[:depth.start()]
        self.dst = dst
        self.kind = kind

    def __str__(self):
        res = self.src + " " + self .dst + " "
        label = {
                "depends": "[depends]",
                "makedepends": "[makedepends]",
                "checkdepends": "[checkdepends]"
        }
        res += label.get(self.kind, ";")
        return res


def immediate_deps_of(abs_dir):
    """Get a list of immediate dependencies of package."""
    pkgbuild_path = abs_dir + "/PKGBUILD"
    package_name = basename(abs_dir)
    dependencies = []
    for kind in ["depends", "makedepends", "checkdepends"]:
        cmd = dedent("""\
                     #!/bin/bash
                     . %s
                     for depend in "${%s[@]}"; do
                         echo ${depend};
                     done;
                     """ % (pkgbuild_path, kind))
        with tempfile.NamedTemporaryFile(mode="w+") as temp:
            temp.write(cmd)
            temp.flush()
            start = datetime.now()
            proc = Popen(["/bin/bash", temp.name], stdout=PIPE)
            try:
              proc.wait(5)
            except TimeoutExpired:
              return []
            for line in proc.stdout:
                line = line.decode().strip()
                if not line:
                    continue
                dep = Dependency(package_name, line, kind)
                dependencies.append(dep)
    return dependencies


def main():
    """This script should be run inside a container."""
    with open("/build/logs/deps", "w") as log:
        builds = glob("/var/abs/*/*")
        counter = 0
        for abs_dir in builds:
            counter += 1
            deps = immediate_deps_of(abs_dir)
            if deps:
                for dep in deps:
                    log.write(str(dep) + "\n")
            else:
                log.write(basename(abs_dir) + " __NONE__ [__NONE__]\n")
            print("\r" + str(counter) + "/" + str(len(builds)),
                  file=stderr, end="")
        print("", file=stderr)


if __name__ == "__main__":
    main()
