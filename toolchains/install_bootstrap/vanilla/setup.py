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


def toolchain_specific_setup(args):
    log("info", "Running vanilla-specific setup")

    # wget and curl output unsuitable progress bars even when not
    # connected to a TTY. Turn them off.
    with open("/etc/wgetrc", "a") as f:
        print("verbose = off", file=f)

    with open("/etc/.curlrc", "a") as f:
        print("silent", file=f)
        print("show-error", file=f)
