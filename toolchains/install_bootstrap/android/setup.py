#!/usr/bin/python3
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
#
# Arch Linux container for building all dependencies of all Arch Linux
# packages.


from utilities import log, timestamp, run_cmd

import os
import os.path
import subprocess


def toolchain_specific_setup(args):
    log("info", "Running android-specific setup")

    # wget and curl output unsuitable progress bars even when not
    # connected to a TTY. Turn them off.
    with open("/etc/wgetrc", "a") as f:
        print("verbose = off", file=f)

    with open("/etc/.curlrc", "a") as f:
        print("silent", file=f)
        print("show-error", file=f)

    log("info", "Downloading & unpacking NDK")
    os.chdir("/home/tuscan")

    setup_file = "/home/tuscan/ndk.bin"

    cmd = ("wget -O %s"
           " http://dl.google.com/android/ndk/android-"
           "ndk-r10e-linux-x86_64.bin" % (setup_file))
    run_cmd(cmd)

    cmd = "chmod +x " + setup_file
    run_cmd(cmd)

    run_cmd(setup_file, output=False)

    log("info", "Setting up toolchain")

    cmd = ("/home/tuscan/android-ndk-r10e/build/tools/"
           "make-standalone-toolchain.sh"
           " --arch=arm --platform=android-21 "
           " --install-dir=" + "/toolchain_root")
    run_cmd(cmd)

    cmd = "chown -R tuscan: " + "/toolchain_root"
    run_cmd(cmd, as_root=True)

    cmd = "chown -R tuscan: /home/tuscan/android-ndk-r10e"
    run_cmd(cmd, as_root=True)

    for f in os.listdir(os.path.join("/toolchain_root", "bin")):
        f = os.path.join("/toolchain_root", "bin", f)
        cmd = "chmod a+rx %s" % f
        run_cmd(cmd, as_root=True)
