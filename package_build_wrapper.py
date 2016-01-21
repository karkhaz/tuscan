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
    stderr.write("Running container for %s",  args.target_package)
    start_time = mktime(gmtime())
    command = ("docker run"

               # Arguments to docker:
               " -v {shared_directory}"
               " --volumes-from {data_volume}"
               " -v {sources_directory}"
               " --volumes-from {sources_volume}"
               " -v {/var/cache/pacman/pkg}"
               " --volumes-from {pkg_cache_volume}"
               " -v logs:/logs"
               " make_package"

               # Arguments to the make_package stage inside container:
               " --sources-directory {sources_directory}"
               " --shared-directory {shared_directory}"
               " {target_package}"

               ).format(shared_directory=args.shared_directory,
                        data_volume=args.data_volume,
                        sources_directory=args.sources_directory,
                        sources_volume=args.sources_volume,
                        pkg_cache_volume=args.pkg_cache_volume,
                        target_package=args.target_package)

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

    parser.add_argument("--shared-directory", dest="shared_directory",
                        action="store", required=True)
    parser.add_argument("--shared-volume", dest="data_volume",
                        action="store", required=True)
    parser.add_argument("--sources-directory", dest="sources_directory",
                        action="store", required=True)
    parser.add_argument("--sources-volume", dest="sources_volume",
                        action="store", required=True)
    parser.add_argument("--target-package", dest="target_package",
                        action="store", required=True)
    parser.add_argument("--pkg-cache-volume", dest="pkg_cache_volume",
                        action="store", required=True)
    parser.add_argument("--output-directory", dest="output_directory",
                        action="store", required=True)
    parser.add_argument("output_packages", action="store", nargs="+")

    args = parser.parse_args()

    run_container(args)


if __name__ == "__main__":
    main()
