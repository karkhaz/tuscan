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

from json import load
from os.path import exists, join
from re import compile
from shutil import copyfile
from subprocess import run, DEVNULL, STDOUT, PIPE
from sys import path, stderr, stdout

def package_file(pack_name):
    cp = run(["pacman", "--query", pack_name],
             universal_newlines=True, stdout=PIPE, stderr=STDOUT)
    if cp.returncode:
        print("Call to pacman -Q failed for package %s" % pack_name,
              file=stderr)
        exit(1)

    name, version = cp.stdout.split()
    assert(name == pack_name)

    for arch in ["any", "x86_64"]:
        pkg_file = ("/var/cache/pacman/pkg/%s-%s-%s.pkg.tar.xz"
                    % (pack_name, version, arch))
        if exists(pkg_file):
            return pkg_file

    print("Could not find file '%s' for package '%s'" %
          (pkg_file, pack_name), file=stderr)
    run(["ls", "/var/cache/pacman/pkg"], stdout=stderr)
    exit(1)



def main():
    parser = get_argparser()
    args = parser.parse_args()

    name_data_file = join(args.shared_directory,
            "get_base_package_names", "latest", "names.json")
    with open(name_data_file) as f:
        name_data = load(f)

    cp = run(["pacman", "-Syyu", "--noconfirm"],
              universal_newlines=True, stdout=DEVNULL, stderr=DEVNULL)

    lst = (["pacman", "-S", "--noconfirm"]
           + name_data["base"]
           + name_data["base_devel"]
           + name_data["break_circular"])
    cp = run(lst, universal_newlines=True, stdout=PIPE,
             stderr=STDOUT)
    if cp.returncode:
        for line in cp.stdout.splitlines():
            print(line, file=stderr)
        exit(1)

    with OutputDirectory(args, __file__) as out_dir:
        packs = (name_data["base"]
               + name_data["base_devel"]
               + name_data["break_circular"])
        for pack_name in packs:
            path = package_file(pack_name)
            dst = join(out_dir, pack_name + ".pkg.tar.xz")
            copyfile(path, dst)
            print("%s.json" % pack_name)
            stdout.flush()
            run(["repo-add", join(out_dir, "repo.db.tar"), dst],
                stdout=DEVNULL, stderr=DEVNULL)


if __name__ == "__main__":
    main()
