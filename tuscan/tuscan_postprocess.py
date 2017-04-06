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
import traceback
import voluptuous
import yaml


def is_boring(cmd, boring_list):
    """Is cmd an irrelevant part of the build process?
    See tuscan/boring_commands.yaml for details.
    """
    for pat in boring_list:
        if pat.match(cmd):
            return True
    return False


def process_red(red_output, red_errors, boring_list):
    """Turn a flat list of process invocations into a process tree.

    This function treeifies the list of process execs and exits that are
    output by red. It also removes uninteresting process invocations.

    In many cases, the exit of a process will appear to have come from a
    different thread than its exec. This function fixes all instances of
    that phenomenon.
    """

    # First, match up execs with exits and put them all into a single
    # data structure.
    nodes = {}
    for item in red_output:
        pid = item["pid"]
        if pid not in nodes:
            nodes[pid] = {}
        if item["kind"] == "exit":
            nodes[pid]["return_code"] = item["return_code"]
            if "ppid" not in nodes[pid]:
                nodes[pid]["ppid"] = item["ppid"]
        else:
            nodes[pid]["timestamp"] = item["timestamp"]
            nodes[pid]["command"] = " ".join(item["command"])
            nodes[pid]["function"] = item["function"]
            nodes[pid]["ppid"] = item["ppid"]

    for pid, info in nodes.items():
        for value in ["ppid", "command", "function", "return_code"]:
            if not value in info:
                info[value] = "UNKNOWN"

    # We now want to remove uninteresting nodes. Naiively, we might just
    # remove nodes with UNKNOWN commands or 'boring' commands (like sed
    # and cd or whatever). However, sometimes boring nodes occur in the
    # _middle_ of the tree, with interesting nodes on the leafs; eg
    #   ./configure -> UNKNOWN -> gcc
    # in this case, we shouldn't (yet) get rid of the UNKNOWN node as it
    # would break the gcc node away from the tree.  So for now, iterate
    # until we reach a fixpoint: delete 'boring' leaves, and also any
    # node such that all of that node's descendants are 'boring'.
    for pid, info in nodes.items():
        info["children"] = []
    for pid, info in nodes.items():
        if info["ppid"] in nodes:
            nodes[info["ppid"]]["children"].append(pid)

    to_delete = []
    for pid, info in nodes.items():
        if not info["children"]:
            if ("command" in info and
                    is_boring(info["command"], boring_list)):
                to_delete.append(pid)

    repeat = True
    while repeat:
        repeat = False
        for pid, info in nodes.items():
            if pid in to_delete:
                continue
            delete = True
            for child in info["children"]:
                if child not in to_delete:
                    delete = False
            if delete:
                if ("command" in info and
                        is_boring(info["command"], boring_list)):
                    to_delete.append(pid)
                    repeat = True
    new_nodes = {}
    for pid, node in nodes.items():
        if pid not in to_delete:
            new_nodes[pid] = node
    nodes = new_nodes


    # Now it's time to squash UNKNOWN nodes that are in the middle of
    # the tree. It often happens that a node with a command has no
    # return code, but its parent has a return code but no command. This
    # corresponds to red reporting a slightly different PID for a
    # process exec and exit:
    #
    #   --- PROCESS ----                       ------- PROCESS ------
    #   command: UNKNOWN  |--- parent of --->  command: gcc
    #   return code:  0                        return code:  UNKNOWN
    #   ----------------                       ---------------------
    # So: if we have a node with no command and a return code, with only
    # one child that has a command but no return code, combine them.
    # Also: if we have a node with no command and a return code, and one
    # child that has a command and the _same_ return code, combine them.
    to_delete = []
    for pid, info in nodes.items():
        if info["ppid"] not in nodes:
            continue

        if nodes[info["ppid"]]["command"] != "UNKNOWN":
            continue
        #if len(nodes[info["ppid"]]["children"]) != 1:
        #    continue
        if (info["return_code"] != "UNKNOWN" and info["return_code"] !=
                nodes[info["ppid"]]["return_code"]):
            continue
        parent = info["ppid"]
        grandparent = nodes[info["ppid"]]["ppid"]
        if not grandparent in nodes:
            continue
        info["ppid"] = grandparent
        info["return_code"] = nodes[parent]["return_code"]
        if not "timestamp" in info and "timestamp" in nodes[parent]:
            info["timestamp"] = nodes["parent"]["timestamp"]
        #nodes[grandparent]["children"].remove(parent)
        nodes[grandparent]["children"].append(pid)
        to_delete.append(parent)
    new_nodes = {}
    for pid, node in nodes.items():
        if pid not in to_delete:
            new_nodes[pid] = node
    nodes = new_nodes

    # Convert the fields into sensible types
    new_nodes = {}
    for pid, node in nodes.items():
        for field in ["timestamp", "ppid", "return_code", "command",
                "function"]:
            if field not in node or node[field] == "UNKNOWN":
                node[field] = None

        if node["ppid"]:
            node["ppid"] = int(node["ppid"])

        if node["return_code"]:
            node["return_code"] = int(node["return_code"])

        if node["timestamp"]:
            node["timestamp"] = int(node["timestamp"])
        else:
            node["timestamp"] = 0

        pid = int(pid)
        node["children"] = []
        node["pid"] = pid
        node["errors"] = []
        new_nodes[pid] = node

    nodes = new_nodes

    # Match up red_errors with the process dict.
    for err in red_errors:
        if int(err["pid"]) in nodes:
            nodes[int(err["pid"])]["errors"].append({
                "category": err["category"],
                "info": err["info"],
            })

    # Finally, do the treeification.
    node_list = list(nodes.values())
    to_remove = []
    for node in node_list:
        if node["ppid"] in nodes:
            nodes[node["ppid"]]["children"].append(node)
            to_remove.append(node)
    for node in to_remove:
        node_list.remove(node)

    return node_list


def process_log_line(line, patterns, counter, classify):
    ret = {"text": line, "category": None, "semantics": {},
           "id": counter}
    if not classify:
        return ret
    for err_class in patterns:
        m = re.search(err_class["pattern"], line)
        if m:
            ret["category"] = err_class["category"]
            for k, v in m.groupdict().iteritems():
                ret["semantics"][k] = v
            break
    return ret


def process_red_errors(data):
    ret = {}
    for triple in data:
        category = triple["category"]
        info = triple["info"]

        # chop off "rel" and "abs"
        if category[:20] == "hardcoded invocation":
           category = "hardcoded invocation"

           # it might be the case that a so-called hardcoded invocation
           # is just a relative invocation of a proper exec, e.g.
           # calling "clang" instead of /sysroot/bin/clang. Ignore this.
           invoc, transformed = info.split()
           if invoc == os.path.basename(transformed):
               continue

        if category not in ret:
            ret[category] = {}
        if info not in ret[category]:
            ret[category][info] = 0
        ret[category][info] += 1
    return ret


def process_single_result(data, patterns, boring_list, args):
    # Each line in the log needs its own ID, so that we can refer to
    # them in HTML or other reports
    counter = 0

    data["no_source"] = False
    tool_information = {
        "configure": {
            "used": False,
            "success": None,
            "autoconf": False
        },
        "cmake": {
            "used": False,
            "success": None
        }
    }

    # Classify errors in each line of the output of commands. The format
    # is in post_processed_schema["log"]["body"].
    # We don't want to classify errors in the logfiles dumped by
    # configure, cmake, and other tools since these will often be false
    # positives.
    new_log = []
    for obj in data["log"]:
        if obj["head"][:36] == "No source directory in source volume":
            data["no_source"] = True

        classify = True
        if re.match("config logfiles", obj["head"]):
            classify = False
            tool_information["configure"]["used"] = True
            for line in obj["body"]:
                m = re.match("configure: exit (?P<ret>\d+)", line)
                if m:
                    if m.group("ret") == "0":
                        tool_information["configure"]["success"] = True
                    else:
                        tool_information["configure"]["success"] = False
                m = re.search("generated by GNU Autoconf", line)
                if m:
                    tool_information["configure"]["autoconf"] = True
        if re.match("Cmake (errors|output)", obj["head"]):
            classify = False
            tool_information["cmake"]["used"] = True
        new_body = []
        for line in obj["body"]:
            counter += 1
            new_line = process_log_line(line, patterns, counter, classify)
            new_body.append(new_line)
        obj["body"] = new_body
        new_log.append(obj)
    data["log"] = new_log
    data["tool_information"] = tool_information

    # Now that we've categorised the errors on each lines, build up a
    # total count of how many errors were encountered.
    category_counts = {}
    semantics_counts = {}
    for obj in data["log"]:

        if re.match("sudo -u tuscan", obj["head"]):
            data["last_build_log_line"] = obj["body"][-1]["id"]

        for line in obj["body"]:
            # Count how many of each kind of error were accumulated for
            # this build.
            if line["category"] != "configure_return_code":
                cat = line["category"]
                try:
                    category_counts[cat] += 1
                except KeyError:
                    category_counts[cat] = 1

                if cat not in semantics_counts:
                    semantics_counts[cat] = {}
                for k, v in line["semantics"].items():
                    try:
                        semantics_counts[cat][v] += 1
                    except KeyError:
                        semantics_counts[cat][v] = 1

    category_counts.pop(None, None)
    data["category_counts"] = category_counts
    semantics_counts.pop(None, None)
    data["semantics_counts"] = semantics_counts

    # Initialise blocker data fields. We need to do a graph iteration
    # over all builds to fill these fields out, so we need to wait for
    # all builds to be processed first.
    data["blocked_by"] = []
    data["blocks"] = []

    # This function augments the tool_information key by getting extra
    # information from red. Invocations of tools don't always leave a
    # log, so this function walks the red process tree to figure out
    # what tools were invoked and what their return codes were.
    #
    # Information about return code success is ordered in the following
    # way: False > True > None. We only update the tool_information if
    # we have more information than what already exists, according to
    # that ordering. Intuitively, we say that configure failed if a
    # single invocation failed, and we only say that configure succeeded
    # if we see a successful invocation and don't have any information
    # so far.
    #
    # We get a lot of false positives because sometimes there will be an
    # invocation of e.g. pacman -T cmake, which returns 127 and which
    # therefore makes it seem like cmake has failed. Ignore any command
    # that starts with 'pacman' for that reason.
    #
    def tool_info_from_red(red_output, tool_information):
        def tool_info_from_red_aux(record, tool_information):
            if record["command"]:
                tool_patterns = {
                    "configure": ["configure ", "configure$"],
                    "cmake": ["cmake ", "cmake$"],
                }
                for tool, patterns in tool_patterns.items():
                    for pattern in patterns:
                        if (re.search(pattern, record["command"]) and
                        not re.match("pacman", record["command"]) and
                        not re.match("/usr/sbin/pacman", record["command"])):
                            tool_information[tool]["used"] = True
                            if (record["return_code"] == 0 and
                                tool_information[tool]["success"] is None):
                                tool_information[tool]["success"] = True
                            elif (record["return_code"] is not None and
                                  record["return_code"] != 0):
                                tool_information[tool]["success"] = False
            for child in record["children"]:
                tool_info_from_red_aux(child, tool_information)
        for record in red_output:
            tool_info_from_red_aux(record, tool_information)

    if args.no_red:
        data["red_output"] = []
        data["red_errors"] = {}
    else:
        data["red_output"] = process_red(data["red_output"],
                data["red_errors"], boring_list)
        try:
            tool_info_from_red(data["red_output"],
                               data["tool_information"])
        # Stack overflow; don't care
        except RuntimeError: pass
        data["red_errors"] = process_red_errors(data["red_errors"])

    return data


def load_and_process(path, patterns, out_dir, args, boring_list):
    try:
        """Processes a JSON result file at path."""
        with open(path) as f:
            data = json.load(f)

        if data["bootstrap"]:
            return

        if args.validate:
            try:
                make_package_schema(data)
            except voluptuous.MultipleInvalid as e:
                logging.error("Malformed input at %s\n  %s" % (path,
                                                            str(e)))
                return
        try:
            data = process_single_result(data, patterns, boring_list, args)
        except RuntimeError as e:
            logging.exception("Error for '%s'" % path)
            return
        if args.validate:
            try:
                post_processed_schema(data)
            except voluptuous.MultipleInvalid as e:
                logging.error("Post-processed data is malformatted: "
                              "%s\n  %s" % (path, str(e)))
            except RuntimeError as e:
                # Occasionally the process graph is so huge that it exceeds
                # Python's recursion depth limit.
                logging.exception("Error for '%s'" % path)

        with open(os.path.join(out_dir,
                               os.path.basename(path)), "w") as fh:
            json.dump(data, fh, indent=2)
    except Exception as e:
        traceback.print_exc()
        exit(1)


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
    logging.basicConfig(format="%(asctime)s %(message)s", level=logging.INFO)

    with open("tuscan/classification_patterns.yaml") as f:
        patterns = yaml.load(f)
    try:
        patterns = classification_schema(patterns)
    except voluptuous.MultipleInvalid as e:
        logging.info("Classification pattern is malformatted: %s\n%s" %
                     (str(e), str(patterns)))
        exit(1)

    with open("tuscan/boring_commands.yaml") as f:
        boring_list = yaml.load(f)
    # Some commands might be invoked as absolute paths
    boring_list = (boring_list
        + ["/usr/bin/%s" % cmd for cmd in boring_list]
        + ["/usr/sbin/%s" % cmd for cmd in boring_list]
        + ["/bin/%s" % cmd for cmd in boring_list]
    )
    boring_list = [re.compile(pat) for pat in boring_list]

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
                        boring_list=boring_list,
                        args=args)
        try:
            # Pressing Ctrl-C results in unpredictable behaviour of
            # spawned processes. So make all the children ignore the
            # interrupt; the parent process shall kill them explicitly.
            original = signal.signal(signal.SIGINT, signal.SIG_IGN)
            # Child processes will inherit the 'ignore' signal handler
            res = pool.map_async(curry, paths)
            # Restore original handler; parent process listens for SIGINT
            signal.signal(signal.SIGINT, original)
            res.get(args.timeout)
        except KeyboardInterrupt:
            pool.terminate()
            pool.join()
            exit(0)
        except multiprocessing.TimeoutError:
            pool.terminate()
            pool.join()
            exit(0)
        pool.close()
        pool.join()

        propagate_blockers(toolchain_dst)
