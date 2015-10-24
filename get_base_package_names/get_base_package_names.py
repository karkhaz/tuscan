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

from utilities import OutputDirectory, setup_argparse

from subprocess import run, PIPE
from sys import stderr


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
    args = setup_argparse()

    base_list = package_list("base")
    base_devel_list = package_list("base-devel")

    with OutputDirectory(args, __file__) as out_dir:
        with open(out_dir + "/names.py", "w") as names:
            print(format_as_python(base_list, "base_package_names"),
                  file=names)
            print(format_as_python(base_devel_list,
                  "base_devel_package_names"), file=names)


if __name__ == "__main__":
    main()
