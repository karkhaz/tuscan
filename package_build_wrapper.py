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

    parser.add_argument("--shared-directory", dest="shared_directory",
                        action="store", required=True)
    parser.add_argument("--shared-volume", dest="shared_volume",
                        action="store", required=True)

    parser.add_argument("--sources-directory", dest="sources_directory",
                        action="store", required=True)
    parser.add_argument("--sources-volume", dest="sources_volume",
                        action="store", required=True)

    parser.add_argument("--toolchain-directory",
                        dest="toolchain_directory",
                        action="store", required=True)
    parser.add_argument("--toolchain-volume",
                        dest="toolchain_volume",
                        action="store", required=True)

    parser.add_argument("--toolchain",
                        dest="toolchain",
                        action="store", required=True)

    parser.add_argument("--abs-dir", dest="abs_dir",
                        action="store", required=True)

    parser.add_argument("--output-directory", dest="output_directory",
                        action="store", required=True)

    parser.add_argument("output_packages", action="store", nargs="+")
    return parser


def run_container(args):
    start_time = mktime(gmtime())

    command = ("docker run --rm -v " + args.shared_directory
               + " --volumes-from " + args.shared_volume

               + " -v " + args.sources_directory
               + " --volumes-from " + args.sources_volume

               + (" -v %s/mirror:/mirror:ro" % getcwd())

               + " -v " + args.toolchain_directory
               + " --volumes-from " + args.toolchain_volume

               + " make_package"

               + " --sources-directory " + args.sources_directory
               + " --shared-directory "  + args.shared_directory
               + " --toolchain-directory "  + args.toolchain_directory
               + " --abs-dir " + args.abs_dir
               + " --toolchain "  + args.toolchain)
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

    json_result["package"] = args.abs_dir
    json_result["time"] = int(mktime(gmtime()) - start_time)
    json_result["toolchain"] = args.toolchain
    json_result["errors"] = errors

    for touch_file in args.output_packages:
        with open(touch_file, "w") as f:
            f.write(dumps(json_result, sort_keys=True, indent=2,
                          separators=(",", ": ")))
            f.flush()


def main():
    parser = get_parser()
    args = parser.parse_args()
    run_container(args)


if __name__ == "__main__":
    main()
