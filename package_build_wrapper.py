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
from json import dumps, load, loads
from os import getcwd
from os.path import basename, splitext
from re import compile, match, sub
from subprocess import Popen, PIPE, STDOUT
from sys import stderr
from time import gmtime, mktime


def get_parser():
    parser = ArgumentParser(
            description="Attempt to build a single package.")

    parser.add_argument("--shared-directory", required=True)
    parser.add_argument("--shared-volume", required=True)

    parser.add_argument("--sources-directory", required=True)
    parser.add_argument("--sources-volume", required=True)

    parser.add_argument("--toolchain-directory", required=True)
    parser.add_argument("--toolchain-volume", required=True)

    parser.add_argument("--toolchain", required=True)

    parser.add_argument("--abs-dir", required=True)

    parser.add_argument("--output-directory", required=True)

    parser.add_argument("output_packages", action="store", nargs="+")
    return parser


def run_container(args):
    start_time = mktime(gmtime())
    command = ("docker run"

               # Arguments to docker:
               " --rm"
               " -v {shared_directory}"
               " --volumes-from {shared_volume}"
               " -v {sources_directory}"
               " --volumes-from {sources_volume}"
               " -v {toolchain_directory}"
               " --volumes-from {toolchain_volume}"
               " -v {cwd}/mirror:/mirror:ro"
               " make_package"

               # Arguments to the make_package stage inside container:
               " --sources-directory {sources_directory}"
               " --shared-directory {shared_directory}"
               " --toolchain-directory {toolchain_directory}"
               " --abs-dir {abs_dir}"
               " --toolchain {toolchain}"
               " {target_package}"

               ).format(shared_directory=args.shared_directory,
                        data_volume=args.data_volume,
                        sources_directory=args.sources_directory,
                        sources_volume=args.sources_volume,
                        toolchain_directory=args.toolchain_directory,
                        toolchain_volume=args.toolchain_volume,
                        pkg_cache_volume=args.pkg_cache_volume,
                        target_package=args.target_package,
                        abs_dir=args.abs_dir,
                        toolchain=args.toolchain,
                        cwd=getcwd())

    p = Popen(command.split(), universal_newlines=True, stdout=PIPE,
              stderr=STDOUT)
    out, _ = p.communicate()
    rc = p.returncode

    json_result = {}
    json_result["return_code"] = p.returncode
    json_result["log"] = []

    # The log() method in utilities.py emits a JSON dictionary rather
    # than a string of plain text. Thus, we should try to parse each
    # line of the log into a dictionary.
    #
    # If an exception was thrown during one of the stages (i.e. a
    # problem with the stage itself rather than an external command),
    # then the stack trace will obviously not be in JSON format, so add
    # the raw lines to a separate array.
    errors = []
    for struct in out.splitlines():
        try:
            json_result["log"].append(loads(struct))
        except:
            errors.append(str(struct))

    if errors:
        stderr.write("Stage error during build of %s\n" % args.abs_dir)
        for line in errors:
            stderr.write(line + "\n")

    json_result["build_name"] = args.abs_dir
    json_result["time"] = int(mktime(gmtime()) - start_time)
    json_result["toolchain"] = args.toolchain
    json_result["errors"] = errors

    pack_list = []
    for package in args.output_packages:
        if package.ends_with(".json"):
            pack_list.append(package[:-5])
        else:
            pack_list.append(package)
    json_result["packages"] = pack_list

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
