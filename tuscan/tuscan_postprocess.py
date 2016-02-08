#!/usr/bin/env python2
#
# Copyright 2016 Kareem Khazem. All Rights Reserved.
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

"""Post-processing raw results returned by stages.

This module analyses JSON results that are written by the make_package
stage. It categorises errors by annotating the JSON file with additional
descriptions, and writes the decorated JSON files out to a different
directory. The input and output files are checked for conformance with
the schemata in tuscan/schemata.py.
"""


from tuscan.schemata import make_package_schema, post_processed_schema

from functools import partial
from json import load, dump
from multiprocessing import Pool, TimeoutError
from voluptuous import MultipleInvalid
from os import listdir, makedirs, unlink
from os.path import basename, isdir, join
from signal import signal, SIGINT, SIG_IGN
from sys import stderr
from time import sleep


def process_single_result(data, args):
    return data


def load_and_process(path, out_dir, args):
    """Processes a JSON result file at path and dumps it to out_dir."""
    with open(path) as f:
        data = load(f)

    if data["bootstrap"]:
        return

    try:
        make_package_schema(data)
    except MultipleInvalid as e:
        stderr.write("Malformed input at %s\n" % path)
        return

    data = process_single_result(data, args)

    try:
        post_processed_schema(data)
    except MultipleInvalid as e:
        stderr.write("Post-processed data is malformatted: %s\n" % path)
        return

    with open(join(out_dir, basename(path)), "w") as f:
        dump(data, f)


def do_postprocess(args):
    dst_dir = "post"
    src_dir = "results"
    pool = Pool(args.pool_size)
    for toolchain in listdir(src_dir):
        toolchain_dst = join(dst_dir, toolchain)

        if not isdir(toolchain_dst):
            makedirs(toolchain_dst)

        for f in listdir(toolchain_dst):
            unlink(join(toolchain_dst, f))

        latest_results = sorted(listdir(join(src_dir, toolchain)))[-1]
        latest_results = join(src_dir, toolchain, latest_results,
                              "pkgbuild_markers")
        paths = [join(latest_results, f) for f in listdir(latest_results)]


        curry = partial(load_and_process,
                        out_dir=toolchain_dst,
                        args=args)
        try:
            # Pressing Ctrl-C results in unpredictable behaviour of
            # spawned processes. So make all the children ignore the
            # interrupt; the parent process shall kill them explicitly.
            original = signal(SIGINT, SIG_IGN)
            # Child processes will inherit the 'ignore' signal handler
            res = pool.map_async(curry, paths)
            # Restore original handler; parent process listens for SIGINT
            signal(SIGINT, original)
            res.get(args.timeout)
        except KeyboardInterrupt:
            pool.terminate()
            pool.join()
            exit(0)
        except TimeoutError:
            pool.terminate()
            pool.join()
            exit(1)
    pool.close()
    pool.join()