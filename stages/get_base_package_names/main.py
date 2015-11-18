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

from utilities import OutputDirectory, get_argparser

from subprocess import run, PIPE
from sys import stderr, stdout
from json import dump


def tools():
    return[
        "doxygen", "graphviz", "git", "cmake", "make",
        "w3m", "wget", "pandoc", "gtk-doc", "asciidoc",
        "python", "python2", "ruby", "perl", "ghc",
        "libsasl", "qemu", "jdk7-openjdk", "jdk8-openjdk",
        "jre8-openjdk", "jre7-openjdk", "cabal-install",
        "rubygems", "java-runtime-headless", "linux-headers",
        "libsigc++2.0", "systemd", "gcc-fortran"
    ]


def package_list(group):
    """Get the packages in group 'group'."""
    ret = run(["pacman", "--query", "--groups", group],
              stdout=PIPE, universal_newlines=True)
    if ret.returncode:
        print("Pacman failed to query group " + group, file=stderr)
        exit(1)

    lst = []

    for line in ret.stdout.splitlines():
        pair = line.split(" ")
        if not len(pair) == 2:
            print("Bad output from pacman: " + line, file=stderr)
            exit(1)
        lst.append(pair[1])

    return lst


def format_as_python(package_list, name):
    ret = name + " = ["
    for pack in package_list:
        ret += "\"" + pack + "\", "
    return ret + "]"


def main():
    parser = get_argparser()
    args = parser.parse_args()

    name_data = {}

    name_data["base"] = package_list("base")
    name_data["base_devel"] = package_list("base-devel")
    name_data["tools"] = tools()

    with OutputDirectory(args) as out_dir:
        with open(out_dir + "/names.json", "w") as names:
            dump(name_data, names)
            names.flush()


    # Touch-files need to be created for each of these packages, outside
    # the container (in the results directory). So print their names to
    # stdout and let the top-level script outside the container create
    # the touch-files.
    for cat in ["base", "base_devel", "tools"]:
        for pkg in name_data[cat]:
            print(pkg + ".json")
    stdout.flush()


if __name__ == "__main__":
    main()
