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


import argparse
import json
import os
import os.path
import re
import subprocess
import sys
import time


def get_parser():
    parser = argparse.ArgumentParser(
            description="Attempt to build a single package.")

    parser.add_argument("--shared-directory", required=True)
    parser.add_argument("--shared-volume", required=True)

    parser.add_argument("--toolchain-directory", required=True)
    parser.add_argument("--toolchain-volume", required=True)

    parser.add_argument("--toolchain", required=True)

    parser.add_argument("--abs-dir", required=True)

    parser.add_argument("--output-directory", required=True)

    parser.add_argument("output_packages", action="store", nargs="+")
    return parser


def run_container(args):
    start_time = time.mktime(time.gmtime())
    command = ("docker run"

               # Arguments to docker:
               " --rm"
               " -v {shared_directory}"
               " --volumes-from {shared_volume}"
               " -v {toolchain_directory}"
               " --volumes-from {toolchain_volume}"
               " -v {cwd}/mirror:/mirror:ro"
               " -v {cwd}/sources:/sources:ro"
               " make_package"

               # Arguments to the make_package stage inside container:
               " --sources-directory /sources"
               " --shared-directory {shared_directory}"
               " --toolchain-directory {toolchain_directory}"
               " --abs-dir {abs_dir}"
               " --toolchain {toolchain}"

               ).format(shared_directory=args.shared_directory,
                        shared_volume=args.shared_volume,
                        toolchain_directory=args.toolchain_directory,
                        toolchain_volume=args.toolchain_volume,
                        abs_dir=args.abs_dir,
                        toolchain=args.toolchain,
                        cwd=os.getcwd())

    p = subprocess.Popen(command.split(), universal_newlines=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
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
            obj = json.loads(struct)

            if obj["kind"] == "provide_info":
                # This list is returned by the make_package stage to
                # tell us what packages are provided by the build. If
                # the build fails, anybody who depends on those packages
                # (transitively) can blame this build.
                json_result["build_provides"] = obj["body"]

            elif obj["kind"] == "dep_info":
                # This list is returned by the make_package stage to
                # tell us what packages are depended on by the build. If
                # the build fails, we can use this list to check if any
                # of the dependencies have also failed.
                json_result["build_depends"] = obj["body"]

            elif obj["kind"] == "sloc_info":
                # This will be a dictionary (encoded as a JSON string)
                # mapping languages to lines-of-code, as reported by
                # SLOCCount.
                json_result["sloc_info"] = json.loads(obj["body"])

            elif obj["kind"] == "bear":
                # This will be an "exec" or "exit" record from libEAR.
                json_result["bear_output"] = obj["body"]

            elif obj["kind"] == "native_tools":
                json_result["native_tools"] = obj["body"]

            else:
                json_result["log"].append(obj)

        except:
            errors.append(str(struct))

    if errors:
        sys.stderr.write("Stage error during build of %s\n" % args.abs_dir)
        for line in errors:
            sys.stderr.write(line + "\n")

    json_result["build_name"] = args.abs_dir
    json_result["time"] = int(time.mktime(time.gmtime()) - start_time)
    json_result["toolchain"] = args.toolchain
    json_result["errors"] = errors
    json_result["bootstrap"] = False

    if not "sloc_info" in json_result:
        json_result["sloc_info"] = {}

    if not "bear_output" in json_result:
        json_result["bear_output"] = []

    if not "native_tools" in json_result:
        json_result["native_tools"] = {}

    for touch_file in args.output_packages:
        with open(touch_file, "w") as f:
            f.write(json.dumps(json_result, sort_keys=True, indent=2,
                          separators=(",", ": ")))
            f.flush()


def main():
    parser = argparse.ArgumentParser(description=
                "Attempt to build a single package.")

    parser.add_argument("--shared-directory", required=True)
    parser.add_argument("--shared-volume", required=True)

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
