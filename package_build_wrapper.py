#!/usr/bin/env python2
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

from argparse import ArgumentParser
from json import dumps, load
from re import compile, match
from subprocess import Popen, PIPE, STDOUT
from sys import stderr
from time import gmtime, mktime


def run_container(args):
    stderr.write("Running container for " + args.target_package)
    start_time = mktime(gmtime())
    command = ("docker run -v " + args.shared_directory
               + " --volumes-from " + args.data_volume
               + " -v " + args.sources_directory
               + " --volumes-from " + args.sources_volume
               + " -v /var/cache/pacman/pkg"
               + " --volumes-from " + args.pkg_cache_volume
               + " -v logs:/logs make_package"
               + " --sources-directory " + args.sources_directory
               + " --shared-directory "  + args.shared_directory
               + " " + args.target_package)
    p = Popen(command.split(), universal_newlines=True, stdout=PIPE,
              stderr=STDOUT)
    out, _ = p.communicate()
    rc = p.returncode

    json_result = {}
    json_result["return_code"] = p.returncode
    json_result["log"] = [command] + out.splitlines()
    json_result["package"] = args.target_package
    json_result["time"] = int(mktime(gmtime()) - start_time)

    for touch_file in args.output_packages:
        with open(touch_file, "w") as f:
            f.write(dumps(json_result, sort_keys=True, indent=2,
                          separators=(",", ": ")))
            f.flush()


def main():
    parser = ArgumentParser(description=
                "Attempt to build a single package.")

    parser.add_argument("--shared-directory", required=True)
    parser.add_argument("--shared-volume", required=True)

    parser.add_argument("--sources-directory", required=True)
    parser.add_argument("--sources-volume", required=True)

    parser.add_argument("--toolchain-directory", required=True)
    parser.add_argument("--toolchain-volume", required=True)

    parser.add_argument("--toolchain", required=True)

    parser.add_argument("--output-directory", required=True)

    parser.add_argument("--abs-dir", required=True)

    parser.add_argument("output_packages", action="store", nargs="+")
    args = parser.parse_args()

    run_container(args)


if __name__ == "__main__":
    main()
