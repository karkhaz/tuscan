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

from utilities import get_argparser, log, timestamp, run_cmd
from utilities import recursive_chown
from setup import toolchain_specific_setup

from glob import glob
from os import chdir, listdir, mkdir, walk
from os.path import basename, isdir, exists, join
from re import search
import urllib.request
from subprocess import run, PIPE, STDOUT
from shutil import chown, copy, copytree
from sys import stderr, stdout
import tarfile
import tempfile
from json import load


def main():
    """Install vanilla bootstrap packages from local mirror.

    Installing all the bootstrap packages is a lengthy (and highly
    disk-IO bound, thus serializing) procedure, so it's best to do it
    only once. Instead of having each container running the make_package
    stage installing the boostrap packages, we install the bootstrap
    packages in this container and then base the make_package containers
    on the image of this container.
    """
    parser = get_argparser()
    args = parser.parse_args()

    # GPG takes time. Remove package signature checks.
    lines = []
    with open("/etc/pacman.conf") as f:
        for line in f:
            if search("SigLevel", line):
                lines.append("SigLevel = Never")
            else:
                lines.append(line.strip())
    with open("/etc/pacman.conf", "w") as f:
        for line in lines:
            print(line.strip(), file=f)

    name_data_file = join(args.shared_directory,
            "get_base_package_names", "latest", "names.json")

    with open(name_data_file) as f:
        name_data = load(f)
    bootstrap_packs = (name_data["base"]
                      + name_data["base_devel"]
                      + name_data["tools"]
                      + ["sloccount"])

    vanilla = "file://" + args.mirror_directory + "/$repo/os/$arch"
    log("info", "Printing %s to mirrorlist" % vanilla)
    with open("/etc/pacman.d/mirrorlist", "w") as f:
        print("Server = " + vanilla, file=f)

    cmd = "pacman -Syy --noconfirm"
    time = timestamp()
    cp = run(cmd.split(), stdout=PIPE, stderr=STDOUT,
             universal_newlines=True)
    log("command", cmd, cp.stdout.splitlines(), time)
    if cp.returncode:
        exit(1)

    cmd = "pacman -Su --noconfirm " + " ".join(bootstrap_packs)
    time = timestamp()
    cp = run(cmd.split(), stdout=PIPE, stderr=STDOUT,
             universal_newlines=True)
    log("command", cmd, cp.stdout.splitlines(), time)
    if cp.returncode:
        exit(1)

    run_cmd("useradd -m -s /bin/bash tuscan", as_root=True)

    # User 'tuscan' needs to be able to use sudo without being harassed
    # for passwords) and so does root (to su into tuscan)
    with open("/etc/sudoers", "a") as f:
        print("tuscan ALL=(ALL) NOPASSWD: ALL", file=f)
        print("root ALL=(ALL) NOPASSWD: ALL", file=f)

    # Download and install bear
    with tempfile.TemporaryDirectory() as d:
        url = ("https://github.com/karkhaz/Bear/blob/master/"
               "bear-2.1.5-1-x86_64.pkg.tar.xz?raw=true")
        response = urllib.request.urlopen(url)
        tar_file = response.read()
        pkg_name = "bear.pkg.tar.xz"
        with open(join(d, pkg_name), "wb") as f:
            f.write(tar_file)
        chdir(d)
        cmd = "pacman -U --noconfirm %s" % pkg_name
        cp = run(cmd.split(), stdout=PIPE, stderr=STDOUT,
                universal_newlines=True)
        log("command", cmd, cp.stdout.splitlines())
        if cp.returncode:
            exit(1)

    mkdir("/toolchain_root")
    chown("/toolchain_root", "tuscan")

    toolchain_specific_setup(args)

    exit(0)


if __name__ == "__main__":
    main()
