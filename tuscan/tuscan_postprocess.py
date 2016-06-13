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
from logging import basicConfig, debug, info, error, warning, INFO, DEBUG
from multiprocessing import Pool, TimeoutError, Manager
from voluptuous import MultipleInvalid
from os import listdir, makedirs, unlink
from os.path import basename, isdir, join
from re import match, search
from signal import signal, SIGINT, SIG_IGN
from sys import stderr
from time import sleep
from yaml import load as yaml_load


def process_bear(output):
    for e in output:
        e["pid"] = int(e["pid"])
        e["ppid"] = int(e["ppid"])
        if "return_code" in e:
            e["return_code"] = int(e["return_code"])
        if "timestamp" in e:
            e["timestamp"] = int(e["timestamp"])

    # output is a mixture of exec and exit data structures. We first
    # homogenise the list by adding the return codes from the exit
    # objects into the corresponding exec object.
    execs = [e for e in output if e["kind"] == "exec"]
    exits = [x for x in output if x["kind"] == "exit"]

    for e in execs:
        e.pop("kind", None)
        e.pop("directory", None)
        e.pop("function", None)
        e["children"] = []

        exit = [x for x in exits if x["pid"] == e["pid"]]
        if not exit:
            e["return_code"] = None
        elif len(exit) == 1:
            e["return_code"] = exit[0]["return_code"]
        else:
            rcs = [x["return_code"] for x in exit]
            if len(rcs) != rcs.count(rcs[0]) and rcs.count(0):
                # There is a mixture of zero and non-zero RCs for this
                # PID. This is weird; we can conclude nothing here.
                e["return_code"] = None
            else:
                # Either there were several RCs for the PID, but the
                # return code was the same for all of them (maybe zero,
                # maybe not). Or there are several different RCs for the
                # same PID, but they're all non-zero. Either way, just
                # pick the first one.
                e["return_code"] = rcs[0]

    new_execs = []
    for e in execs:
        if not [n for n in new_execs if n["pid"] == e["pid"]]:
            new_execs.append(e)
    execs = sorted(new_execs, key=lambda x: x["timestamp"])

    # execs is now a flat list. The algorithm for treeifying the list
    # assumes that there is a root process, which won't always be the
    # case, so we need to synthesise one. It also assumes that each
    # process has a parent. This isn't the case in general, I've
    # observed lots of cases where processes have a PPID that doesn't
    # appear in the process list. Again, synthesise them.

    pids = [e["pid"] for e in execs]
    absent_parents = []
    added = []
    for e in execs:
        if e["ppid"] not in pids and e["ppid"] not in added:
            added.append(e["ppid"])
            absent_parents.append({
                "pid": e["ppid"],
                "ppid": 0,
                "children": [],
                "timestamp": e["timestamp"],
                "return_code": e["return_code"],
                "command": "__unknown__"
            })
    execs = execs + absent_parents + [{
        "pid": 0,
        "ppid": -1,
        "children": [],
        "timestamp": 0,
        "return_code": 0,
        "command": ["__root_process__"]
    }]

    # Now turn execs into a tree showing the parent-child process
    # relationship.

    def iterate(data):
        if not data:
            return []
        def is_decendent(node, parent):
            if node["ppid"] == parent["pid"]:
                parent["children"].append(node)
                parent["children"] = sorted(parent["children"], key=(
                    lambda node: node["timestamp"]))
                return True, parent
            else:
                new_children = []
                added = False
                for child in parent["children"]:
                    ret, new_child = is_decendent(node, child)
                    new_children.append(new_child)
                    if ret:
                        added = True
                parent["children"] = sorted(new_children, key=(
                    lambda node: node["timestamp"]))
                return added, parent
        lst = list(data)
        passes = len(data)
        counter = passes
        total = 0
        limit = passes * passes + 1
        while counter:
            counter -= 1
            total += 1
            # If this happens, the implementation is broken & won't
            # terminate...
            if total > limit:
                error("n^2 passes over list")
                exit(1)
            head, tail = lst[0], lst[1:]
            to_append = head
            new_list = []
            already_added = False
            for t in tail:
                added, new_t = is_decendent(head, t)
                if added:
                    assert(not already_added)
                    already_added = True
                    counter = passes
                    to_append = t
                elif t["ppid"] == head["pid"]:
                    head["children"].append(t)
                    counter = passes
                else:
                    new_list.append(t)
            new_list.append(to_append)
            lst = new_list
        return lst

    execs = iterate(execs)

    # There should be a single root node with pid of -1.
    assert(len(execs)) == 1
    tree = execs[0]

    # Finally, get rid of all the dummy processes that were used during
    # the iteration.

    def squash_unknowns(node):
        new_children = []
        for child in node["children"]:
            if child["command"] == "__unknown__":
                for grandchild in child["children"]:
                    new_children.append(squash_unknowns(grandchild))
            else:
                new_children.append(squash_unknowns(child))
        node["children"] = new_children
        return node

    return squash_unknowns(tree)


def dump_result(result):
    with open(result["file"], "w") as f:
        dump(result["data"], f, indent=2)


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


def process_single_result(data, patterns, args):
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

    if args.treeify_bear:
        data["bear_output"] = process_bear(data["bear_output"])
    else:
        data["bear_output"] = None

    return data


def load_and_process(path, patterns, out_dir, args, results):
    """Processes a JSON result file at path."""
    with open(path) as f:
        data = load(f)

    if data["bootstrap"]:
        return

    try:
        make_package_schema(data)
    except MultipleInvalid as e:
        error("Malformed input at %s\n  %s" % (path, str(e)))
        return

    data = process_single_result(data, patterns, args)

    try:
        post_processed_schema(data)
    except MultipleInvalid as e:
        error("Post-processed data is malformatted: %s\n  %s" %
                (path, str(e)))

    to_dump = {"data": data, "file": join(out_dir,
                                    "%s" % basename(path))}
    if args.calculate_blockers:
        results.append(to_dump)
    else:
        dump_result(to_dump)


def propagate_blockers(results):
    """Fill out "blocked_by" and "blocks" fields of data.

    Failing builds can either be "blocked" (failed to build because
    their dependency FTB), or a "blocker" (FTB but all their
    dependencies built correctly). After this function returns, blocked
    builds will have a list of builds that they are blocked by in their
    "blocked_by" field. Builds that block other builds will have those
    builds in their "blocks" field.

    Precondition: blocker builds have the "blocker" field set to true.
    """
    blockers = [result["data"]["build_name"] for result in results
                if result["data"]["return_code"] and not ("missing_deps"
                in result["data"]["category_counts"])]
    info("%d blockers for this toolchain. Propagating..." % len(blockers))

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
            stderr.write("\rIteration %2d, result %5d/%5d,"
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
                    pack = basename(blocker)
                    if dep == pack:
                        if blocker not in blocked_by[data["build_name"]]:
                            stop = False
                            added += 1
                            blocked_by[data["build_name"]].append(blocker)
                            debug("%s directly blocked by %s\n" %
                                    (data["build_name"], blocker))
                # Case: this build is transitively blocked by a blocker
                for blocked, directs in blocked_by.items():
                    pack = basename(blocked)
                    if pack == dep:
                        for b in directs:
                            if b not in blocked_by[data["build_name"]]:
                                stop = False
                                added += 1
                                blocked_by[data["build_name"]].append(b)
                                debug("%s transitively blocked by %s\n" %
                                        (data["build_name"], b))
        stderr.write("\n")

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
            warning("Blocked package %s has no blocked_by entry" %
                    data["build_name"])

        # One or other list should be empty. They might both be empty:
        # if this build succeeded, or if it is a blocker with no
        # dependencies.
        if data["blocked_by"] and data["blocks"]:
            error("%s is both a blocker and blocked!" % data["build_name"])

    return results


def do_postprocess(args):
    basicConfig(format="%(asctime)s %(message)s", level=INFO)

    with open("tuscan/classification_patterns.yaml") as f:
        patterns = yaml_load(f)
    try:
        patterns = classification_schema(patterns)
    except MultipleInvalid as e:
        info("Classification pattern is malformatted: %s\n%s" %
                     (str(e), str(patterns)))
        exit(1)

    dst_dir = "output/post"
    src_dir = "output/results"

    man = Manager()

    toolchain_counter = 0
    toolchain_total = len(listdir(src_dir))
    for toolchain in listdir(src_dir):
        pool = Pool(args.pool_size)
        results = man.list()

        toolchain_counter += 1
        info("Post-processing results for toolchain "
                "%d of %d [%s]" % (toolchain_counter, toolchain_total,
                    toolchain))
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
                        patterns=patterns,
                        results=results,
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

        if args.calculate_blockers:
            results = propagate_blockers(results._getvalue())
            for result in results:
                dump_result(result)
