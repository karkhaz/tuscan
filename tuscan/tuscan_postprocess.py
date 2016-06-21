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

import functools
import json
import logging
import multiprocessing
import os
import os.path
import re
import signal
import sys
import time
import voluptuous


def process_log_line(line, patterns, counter):
    ret = {"text": line, "category": None, "semantics": {},
           "id": counter, "severity": None}
    for err_class in patterns:
        m = re.search(err_class["pattern"], line)
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

    # Initialise blocker data fields. We need to do a graph iteration
    # over all builds to fill these fields out, so we need to wait for
    # all builds to be processed first.
    data["blocked_by"] = []
    data["blocks"] = []

    return data


def load_and_process(path, patterns, out_dir, args):
    """Processes a JSON result file at path."""
    with open(path) as f:
        data = json.load(f)

    if data["bootstrap"]:
        return

    try:
        make_package_schema(data)
    except MultipleInvalid as e:
        logging.error("Malformed input at %s\n  %s" % (path, str(e)))
        return

    data = process_single_result(data, patterns)

    try:
        post_processed_schema(data)
    except MultipleInvalid as e:
        logging.error("Post-processed data is malformatted: %s\n  %s" %
                (path, str(e)))

    with open(os.path.join(out_dir, os.path.basename(path)), "w") as fh:
        json.dump(data, fh, indent=2)


def propagate_blockers(out_dir):
    """Fill out "blocked_by" and "blocks" fields of data.

    Failing builds can either be "blocked" (failed to build because
    their dependency FTB), or a "blocker" (FTB but all their
    dependencies built correctly). After this function returns, blocked
    builds will have a list of builds that they are blocked by in their
    "blocked_by" field. Builds that block other builds will have those
    builds in their "blocks" field.

    Precondition: blocker builds have the "blocker" field set to true.
    """
    logging.info("Reloading results from disk to calculate blockers")
    results = []
    for f in os.listdir(out_dir):
        with open(os.path.join(out_dir, f)) as fh:
            j = json.load(fh)
        # In order to save RAM, we only copy the fields that we need
        # from the on-disk JSON result into memory.
        r = {}
        r["file"] = os.path.join(out_dir, f)
        r["data"] = {}
        r["data"]["return_code"] = j["return_code"]
        r["data"]["build_name"] = j["build_name"]
        r["data"]["build_depends"] = j["build_depends"]
        r["data"]["category_counts"] = j["category_counts"]
        r["data"]["blocks"] = j["blocks"]
        r["data"]["blocked_by"] = j["blocked_by"]
        results.append(r)

    blockers = [result["data"]["build_name"] for result in results
                if result["data"]["return_code"] and not ("missing_deps"
                in result["data"]["category_counts"])]
    logging.info("%d blockers for this toolchain. Propagating..." % len(blockers))

    iteration = 0
    blocked_by = {}
    stop = False
    while not stop:
        iteration += 1
        added = 0
        stop = True
        result_counter = 0
        result_total = len(results)
        for result in results:
            result_counter += 1
            sys.stderr.write("\rIteration %2d, result %5d/%5d,"
                     " added %d new blocked packages." %
                    (iteration, result_counter, result_total, added))
            data = result["data"]
            if not data["return_code"]:
                continue
            if not "missing_deps" in data["category_counts"]:
                continue
            if data["build_name"] not in blocked_by:
                blocked_by[data["build_name"]] = []
            for dep in data["build_depends"]:
                # Case: this build is directly blocked by a blocker
                for blocker in blockers:
                    pack = os.path.basename(blocker)
                    if dep == pack:
                        if blocker not in blocked_by[data["build_name"]]:
                            stop = False
                            added += 1
                            blocked_by[data["build_name"]].append(blocker)
                            logging.debug("%s directly blocked by %s\n" %
                                    (data["build_name"], blocker))
                # Case: this build is transitively blocked by a blocker
                for blocked, directs in blocked_by.items():
                    pack = os.path.basename(blocked)
                    if pack == dep:
                        for b in directs:
                            if b not in blocked_by[data["build_name"]]:
                                stop = False
                                added += 1
                                blocked_by[data["build_name"]].append(b)
                                logging.debug("%s transitively blocked by %s\n" %
                                        (data["build_name"], b))
        sys.stderr.write("\n")

    blocks = {}
    for blocked, directs in blocked_by.items():
        for blocker in directs:
            if not blocker in blocks:
                blocks[blocker] = []
            blocks[blocker].append(blocked)

    for result in results:
        data = result["data"]
        if data["build_name"] in blockers:
            if data["build_name"] in blocks:
                data["blocks"] = blocks[data["build_name"]]
            # Else, this build is a blocker, but it has no
            # dependencies so it didn't cause anything else to break.
        elif data["build_name"] in blocked_by:
            data["blocked_by"] = blocked_by[data["build_name"]]
        elif data["return_code"]:
            logging.warning("Blocked package %s has no blocked_by entry" %
                    data["build_name"])

        # One or other list should be empty. They might both be empty:
        # if this build succeeded, or if it is a blocker with no
        # dependencies.
        if data["blocked_by"] and data["blocks"]:
            logging.error("%s is both a blocker and blocked!" % data["build_name"])

    logging.info("Finished calculating blockers, re-writing to disk...")
    file_to_result = {}
    for r in results:
        file_to_result[r["file"]] = r["data"]
    for f in os.listdir(out_dir):
        f = os.path.join(out_dir, f)
        if not f in file_to_result:
            logging.error("Could not find result for file '%s'" % f)
            exit(1)
        updated = file_to_result[f]
        with open(f) as fh:
            original = json.load(fh)
        original["blocks"] = updated["blocks"]
        original["blocked_by"] = updated["blocked_by"]
        with open(f, "w") as fh:
            json.dump(original, fh, indent=2)


def do_postprocess(args):
    logging.basicConfig(format="%(asctime)s %(message)s", level=INFO)

    with open("tuscan/classification_patterns.yaml") as f:
        patterns = yaml_json.load(f)
    try:
        patterns = classification_schema(patterns)
    except MultipleInvalid as e:
        logging.info("Classification pattern is malformatted: %s\n%s" %
                     (str(e), str(patterns)))
        exit(1)

    dst_dir = "output/post"
    src_dir = "output/results"

    man = multiprocessing.Manager()

    toolchain_counter = 0
    toolchain_total = len(args.toolchains)
    for toolchain in args.toolchains:
        pool = multiprocessing.Pool(args.pool_size)

        toolchain_counter += 1
        logging.info("Post-processing results for toolchain "
                "%d of %d [%s]" % (toolchain_counter, toolchain_total,
                    toolchain))
        toolchain_dst = os.path.join(dst_dir, toolchain)

        if not os.path.isdir(toolchain_dst):
            os.makedirs(toolchain_dst)

        for f in os.listdir(toolchain_dst):
            os.unlink(os.path.join(toolchain_dst, f))

        latest_results = sorted(os.listdir(os.path.join(src_dir, toolchain)))[-1]
        latest_results = os.path.join(src_dir, toolchain, latest_results,
                              "pkgbuild_markers")
        paths = [os.path.join(latest_results, f) for f in os.listdir(latest_results)]


        curry = functools.partial(load_and_process,
                        patterns=patterns,
                        out_dir=toolchain_dst,
                        args=args)
        try:
            # Pressing Ctrl-C results in unpredictable behaviour of
            # spawned processes. So make all the children ignore the
            # interrupt; the parent process shall kill them explicitly.
            original = signal.signal(SIGINT, SIG_IGN)
            # Child processes will inherit the 'ignore' signal handler
            res = pool.map_async(curry, paths)
            # Restore original handler; parent process listens for SIGINT
            signal.signal(SIGINT, original)
            res.get(args.timeout)
        except KeyboardInterrupt:
            pool.terminate()
            pool.os.path.join()
            exit(0)
        except TimeoutError:
            pool.terminate()
            pool.os.path.join()
            exit(1)
        pool.close()
        pool.os.path.join()

        propagate_blockers(toolchain_dst)
