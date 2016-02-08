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
from tuscan.schemata import classification_schema

from functools import partial
from json import load, dump
from multiprocessing import Pool, TimeoutError
from voluptuous import MultipleInvalid
from os import listdir, makedirs, unlink
from os.path import basename, isdir, join
from signal import signal, SIGINT, SIG_IGN
from re import search
from sys import stderr
from time import sleep
from yaml import load as yaml_load


def process_log_line(line, patterns):
    ret = {"text": line, "category": None, "semantics": {}}
    for err_class in patterns:
        m = search(err_class["pattern"], line)
        if m:
            ret["category"] = err_class["category"]
            for k, v in m.groupdict().iteritems():
                ret["semantics"][k] = v
            break
    return ret


def process_single_result(data, patterns):
    # Classify errors in each line of the output of commands. The format
    # is in post_processed_schema["log"]["body"].
    new_log = []
    for obj in data["log"]:
        new_body = []
        for line in obj["body"]:
            new_body.append(process_log_line(line, patterns))
        obj["body"] = new_body
        new_log.append(obj)
    data["log"] = new_log

    # Now, count how many of each type of error were accumulated for
    # this package.
    category_counts = {}
    for obj in data["log"]:
        for line in obj["body"]:
            cat = line["category"]
            try:
                category_counts[cat] += 1
            except KeyError:
                category_counts[cat] = 1
    category_counts.pop(None, None)
    data["category_counts"] = category_counts

    return data


def load_and_process(path, out_dir, patterns):
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

    data = process_single_result(data, patterns)

    try:
        post_processed_schema(data)
    except MultipleInvalid as e:
        stderr.write("Post-processed data is malformatted: %s\n" % path)
        return

    with open(join(out_dir, basename(path)), "w") as f:
        dump(data, f)


def do_postprocess(args):
    with open("tuscan/classification_patterns.yaml") as f:
        patterns = yaml_load(f)
    try:
        patterns = classification_schema(patterns)
    except MultipleInvalid as e:
        stderr.write("Classification pattern is malformatted: %s\n%s" %
                     (str(e), str(patterns)))
        exit(1)

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
                        patterns=patterns)
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
