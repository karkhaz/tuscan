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

from utilities import log

from subprocess import run, STDOUT, PIPE

def toolchain_specific_setup(args):
    log("info", "Running vanilla-specific setup")

    # wget and curl output unsuitable progress bars even when not
    # connected to a TTY. Turn them off.
    with open("/etc/wgetrc", "a") as f:
        print("verbose = off", file=f)

    with open("/etc/.curlrc", "a") as f:
        print("silent", file=f)
        print("show-error", file=f)

    # User `tuscan' needs to be able to use sudo without being harassed
    # for passwords) and so does root (to su into tuscan)
    with open("/etc/sudoers", "a") as f:
        print("tuscan ALL=(ALL) NOPASSWD: ALL", file=f)
        print("root ALL=(ALL) NOPASSWD: ALL", file=f)

    cmd = "useradd -m -s /bin/bash tuscan"
    cp = run(cmd.split(), stdout=PIPE, stderr=STDOUT,
            universal_newlines=True)

    log("command", cmd, cp.stdout.splitlines())
    if cp.returncode:
        exit(1)
