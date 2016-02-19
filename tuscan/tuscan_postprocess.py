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
from multiprocessing import Pool
from voluptuous import MultipleInvalid
from os import listdir, makedirs, unlink
from os.path import basename, isdir, join
from re import match, search
from signal import signal, SIGINT
from sys import stderr
from time import sleep
from yaml import load


def process_log_line(line, patterns, counter):
    ret = {"text": line, "category": None, "semantics": {},
           "id": counter, "severity": None}
    for err_class in patterns:
        m = search(err_class["pattern"], line)
        if m:
            ret["category"] = err_class["category"]
            ret["severity"] = err_class["severity"]
            for k, v in m.groupdict().iteritems():
                ret["semantics"][k] = v
            break
    return ret


def process_single_result(data, patterns):
    # Each line in the log needs its own ID, so that we can refer to
    # them in HTML or other reports
    counter = 0

    # Classify errors in each line of the output of commands. The format
    # is in post_processed_schema["log"]["body"].
    new_log = []
    for obj in data["log"]:
        new_body = []
        for line in obj["body"]:
            counter += 1
            new_line = process_log_line(line, patterns, counter)
            if new_line["category"] == "configure_return_code":
                rc = int(new_line["semantics"]["return_code"])
                obj["config_success"] = False if rc else True
            new_body.append(new_line)
        obj["body"] = new_body
        new_log.append(obj)
    data["log"] = new_log

    # Now, count how many of each type of error were accumulated for
    # this package. Also figure out if configure invocations were
    # successful.
    config_success = None
    category_counts = {}
    for obj in data["log"]:

        if "config_success" in obj:
            if not obj["config_success"]:
                config_success = False
            elif obj["config_success"] and config_success == None:
                config_success = True

        for line in obj["body"]:
            if line["category"] != "configure_return_code":
                cat = line["category"]
                try:
                    category_counts[cat] += 1
                except KeyError:
                    category_counts[cat] = 1
    category_counts.pop(None, None)
    data["category_counts"] = category_counts
    data["config_success"] = config_success

    return data


def load_and_process(path, out_dir, patterns):
    """Processes a JSON result file at path and dumps it to out_dir."""
    with open(path) as f:
        data = load(f)

    try:
        make_package_schema(data)
    except MultipleInvalid as e:
        stderr.write("Problem when reading %s:\n%s\n" %
                     (path, str(e)))
        exit(1)

    process_single_result(data, patterns)

    try:
        post_processed_schema(data)
    except MultipleInvalid as e:
        stderr.write("Post-processed data is malformatted: %s\n%s" %
                     (str(e), str(data)))
        exit(1)

    with open(join(out_dir, basename(path)), "w") as f:
        dump(data, f)


def do_postprocess(args):
    with open("tuscan/classification_patterns.yaml") as f:
        patterns = load(f)
    try:
        patterns = classification_schema(patterns)
    except MultipleInvalid as e:
        stderr.write("Classification pattern is malformatted: %s\n%s" %
                     (str(e), str(patterns)))
        exit(1)

    dst_dir = "post"
    src_dir = "results"

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


        pool = Pool(args.pool_size)
        curry = partial(load_and_process,
                        out_dir=toolchain_dst,
                        patterns=patterns)
        pool.map(curry, paths)
