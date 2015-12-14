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

from functools import partial
from glob import glob
from jinja2 import Environment, FileSystemLoader
from json import load
from multiprocessing import Manager, Pool, cpu_count
from os import listdir, remove, makedirs
from os.path import basename, dirname, isdir, join, splitext
from re import match, search
from shutil import rmtree
from sys import stderr
"""Functions to dump a HTML representation of experimental data."""


def get_json(json, lst):
    if not basename(json) == "names":
        with open(json) as f: lst.append(load(f)) 


def load_jsons(file_list):
    man = Manager()
    lst = man.list()

    pool = Pool(cpu_count())
    curry = partial(get_json, lst=lst)
    pool.map(curry, file_list)

    return list(lst)


def default_struct(line):
    return {
        "text": line,
        "format": "none",
        "category": "none",
        "semantics": { }
    }


def transform_line(line):
    """Given a line from command output, returns a dict decorating that
    line with semantic information. See the doc for proc_log(), from
    which this method is invoked.
    """

    if (search("rm: cannot remove", line)
    or search("mv: cannot stat", line)):
        return {
          "text": line,
          "format": "error",
          "category": "install_error",
          "semantics": {
            }
        }

    pat = ": (?P<file>.+?): cannot execute binary file"
    m = search(pat, line)
    if m:
        return {
          "text": line,
          "format": "error",
          "category": "exec_error",
          "semantics": {
              "file": m.group("file")
            }
        }

    pat = "cannot execute binary file: (?P<file>.+)"
    m = search(pat, line)
    if m:
        return {
          "text": line,
          "format": "error",
          "category": "exec_error",
          "semantics": {
              "file": m.group("file")
            }
        }

    pat = "configure: error: (?P<err>.+)"
    m = search(pat, line)
    if m:
        return {
          "text": line,
          "format": "error",
          "category": "configure_error",
          "semantics": {
              "error": m.group("err")
            }
        }

    pat = "tuscan: configure log has no return code"
    m = search(pat, line)
    if m:
        return {
          "text": line,
          "format": "warning",
          "category": "unparseable_config",
          "semantics": { }
        }

    pat = "[-\.\w\/\+]+.(S|s):\d+: (E|e)rror: (?P<err>.+)"
    m = search(pat, line)
    if m:
        return {
          "text": line,
          "format": "error",
          "category": "assembler_error",
          "semantics": {
              "err": m.group("err")
          }
        }

    pat = "[-\.\w\+\/]+:\d+:\d+: error:"
    m = search(pat, line)
    if m:
        return {
          "text": line,
          "format": "error",
          "category": "compile_error",
          "semantics": { }
        }

    pat = "ld: error: cannot find (?P<lib>.+)"
    m = search(pat, line)
    if m:
        return {
          "text": line,
          "format": "error",
          "category": "link_error",
          "semantics": {
              "library": m.group("lib")
          }
        }

    pat = "(?P<head>[-.\w\/]+\.h): No such file or directory"
    m = search(pat, line)
    if m:
        return {
          "text": line,
          "format": "error",
          "category": "missing_header",
          "semantics": {
              "header": m.group("head")
          }
        }

    pat = "==> ERROR: Failure while downloading"
    m = search(pat, line)
    if m:
        return {
          "text": line,
          "format": "error",
          "category": "missing_source",
          "semantics": { }
        }

    pat = "error: target not found: (?P<pkg>[-\.\w]+)"
    m = search(pat, line)
    if m:
        return {
          "text": line,
          "format": "error",
          "category": "missing_deps",
          "semantics": {
              "bad_package": m.group("pkg")
          }
        }

    pat = "error: undefined reference to '(?P<sym>.+)'"
    m = search(pat, line)
    if m:
        return {
          "text": line,
          "format": "error",
          "category": "undefined_reference",
          "semantics": {
              "symbol": m.group("sym")
          }
        }

    pat = "tuscan: native invocation of '(?P<tool>\w+)'"
    m = search(pat, line)
    if m:
        return {
          "text": line,
          "format": "error",
          "category": "native_tool_invocation",
          "semantics": {
              "tool": m.group("tool")
          }
        }

    pat = "(?P<cmd>[-\.\+\/\w]+): command not found"
    m = search(pat, line)
    if m:
        return {
          "text": line,
          "format": "error",
          "category": "command_not_found",
          "semantics": {
              "cmd": m.group("cmd")
          }
        }

    pat = "gcc: error: unrecognized command line option '(?P<opt>.+)'"
    m = search(pat, line)
    if m:
        return {
          "text": line,
          "format": "error",
          "category": "unknown_compiler_flag",
          "semantics": {
              "flag": m.group("opt")
          }
        }

    pat = "gcc: error: unrecognized argument in option '(?P<opt>.+)'"
    m = search(pat, line)
    if m:
        return {
          "text": line,
          "format": "error",
          "category": "unknown_compiler_flag",
          "semantics": {
              "flag": m.group("opt")
          }
        }

    pat = "Unrecognized option : ((--host)|(x86_64-unknown-linux))"
    m = search(pat, line)
    if m:
        return {
          "text": line,
          "format": "error",
          "category": "host_flag_unrecognised",
          "semantics": { }
        }

    pat = "configure: unknown option --host"
    m = search(pat, line)
    if m:
        return {
          "text": line,
          "format": "error",
          "category": "host_flag_unrecognised",
          "semantics": { }
        }

    pat = "unknown option: --host"
    m = search(pat, line)
    if m:
        return {
          "text": line,
          "format": "error",
          "category": "host_flag_unrecognised",
          "semantics": { }
        }

    return default_struct(line)


def get_category_counts(build, configure=None):
    category_counts = {}
    for struct in build["log"]:
        if configure == False and "configure_status" in struct:
            continue
        if configure == True and "configure_status" not in struct:
            continue
        for line in struct["body"]:
            cat = line["category"]
            if cat not in category_counts:
                category_counts[cat] = 0
            category_counts[cat] += 1
    category_counts.pop("none", None)
    return category_counts


def overall_semantics(builds, category):
    """ { semantic => count, ...} """
    obj = {}

    for build in builds:
        for struct in build["log"]:
            for line in struct["body"]:
                if line["category"] == category:
                    for sem in line["semantics"]:
                        if not sem in obj:
                            obj[sem] = {}
                        value = line["semantics"][sem]
                        if value not in obj[sem]:
                            obj[sem][value] = 0
                        obj[sem][value] += 1

    tmp = {}
    for sem, value_dict in obj.iteritems():
        lst = []
        for value, count in value_dict.iteritems():
            lst.append((value, count))
        lst = sorted(lst, key=lambda x: x[1], reverse=True)
        tmp[sem] = lst

    return tmp


def add_configure_status(build):
    """Marks configure logs with their exit code, and marks the build
    with a string noting the overall status of all configure scripts
    """
    overall_status = "no log"
    new_log = []

    for struct in build["log"]:
        if not search("Config logfile", struct["head"]):
            new_log.append(struct)
            continue

        local_status = "unknown"
        if overall_status == "no log":
            overall_status = "unknown"

        for line in struct["body"]:
            m = search("configure: exit (?P<rc>\d+)", line)
            if not m:
                m = search("configure.sh: exit (?P<rc>\d+)", line)

            if m and m.group("rc") == "0" and local_status == "unknown":
                local_status = "success"
                if overall_status == "unknown":
                    overall_status = "success"
            elif m:
                local_status = "failure"
                overall_status = "failure"

            elif search("=== FATAL: ", line):
                local_status = "failure"
                overall_status = "failure"

        if local_status == "unknown":
            overal_status = "unknown"

        struct["configure_status"] = local_status
        new_log.append(struct)

    build["log"] = new_log
    build["configure_status"] = overall_status


def write_single_package_pages(env, tc, args, vanilla_results):

    def seconds_to_hhmmss(seconds):
        hours, mins = divmod(seconds, 3600)
        mins, secs = divmod(mins, 60)
        return "%02d:%02d:%02d" % (hours, mins, secs)

    def get_vanilla_results_dict(results):
        res = {}
        for data in results:
            name = basename(data["package"])
            res[name] = data["return_code"]
        return res

    makedirs(join("html", tc))
    builds = []

    result_dir = sorted(listdir(join("results", tc)))[-1]
    result_dir = join("results", tc, result_dir, "pkgbuild_markers")

    results = glob(join(result_dir, "*"))
    stderr.write("Loading JSON files for toolchain '%s'\n" % (tc))
    results = load_jsons(results)

    if tc == "vanilla":
        tmp = get_vanilla_results_dict(results)
        for k, v in tmp.iteritems():
            vanilla_results[k] = v

    for data in results:
        package_name, _ = splitext(basename(data["package"]))

        data["time"] = seconds_to_hhmmss(data["time"])
        data["package_name"] = package_name

        add_configure_status(data)

        data["log"] = proc_log(data)

        data["category_counts"] = get_category_counts(data, None)
        data["configure_counts"] = get_category_counts(data, True)
        data["non_configure_counts"] = get_category_counts(data, False)

        templ = env.get_template("single_package.jinja.html")
        html = templ.render(data=data, col=colours(args))

        name = basename(data["package"])
        path = join("html", tc, name, "index.html")

        data["build_name"] = name

        if vanilla_results[name] is None:
            data["built_on_vanilla"] = None
        elif vanilla_results[name] == 0:
            data["built_on_vanilla"] = True
        else:
            data["built_on_vanilla"] = False

        builds.append(data)
        try:
            makedirs(dirname(path))
        except OSError:
            pass
        with open(path, "w") as f:
            f.write(html.encode("utf-8"))
    return builds


def get_variations(builds):
    """Returns a list of result-list structures, filtered by criteria.
    """

    variations = []

    variations.append(({"heading": "Basic statistics"}, []))

    obj = {}
    obj["number"] = len(builds)
    obj["file_name"] = "index"
    obj["title"] = "All builds"
    obj["description"] = "built in total"
    obj["semantics"] = {}
    variations.append((obj, builds))

    obj = {}
    new_builds = [b for b in builds if b["return_code"] == 0]
    obj["number"] = len(new_builds)
    obj["file_name"] = "success"
    obj["title"] = "Successful builds"
    obj["description"] = "built successfully"
    obj["semantics"] = {}
    variations.append((obj, new_builds))

    obj = {}
    new_builds = [b for b in builds if b["return_code"] != 0]
    obj["number"] = len(new_builds)
    obj["file_name"] = "fail"
    obj["title"] = "Failed builds"
    obj["description"] = "failed to build successfully"
    obj["semantics"] = {}
    variations.append((obj, new_builds))

    obj = {}
    new_builds = [b for b in builds if (b["return_code"] != 0
                                    and b["built_on_vanilla"])]
    obj["number"] = len(new_builds)
    obj["file_name"] = "tc_fail"
    obj["title"] = "Fails that built successfully on vanilla"
    obj["description"] = "failed but were successful on vanilla"
    obj["semantics"] = {}
    variations.append((obj, new_builds))

    obj = {}
    new_builds = [b for b in builds
                    if "missing_source" in  b["category_counts"]]
    obj["number"] = len(new_builds)
    obj["file_name"] = "missing_source"
    obj["title"] = "Packages with missing sources"
    obj["description"] = "failed because they had no sources"
    obj["semantics"] = overall_semantics(new_builds, "missing_source")
    variations.append((obj, new_builds))

    obj = {}
    new_builds = [b for b in builds
                    if "missing_deps" in  b["category_counts"]]
    obj["number"] = len(new_builds)
    obj["file_name"] = "missing_deps"
    obj["title"] = "Packages whose dependency failed to build"
    obj["description"] = "failed because their dependency didn't build"
    obj["semantics"] = {}
    variations.append((obj, new_builds))

    obj = {}
    new_builds = [b for b in builds if b["return_code"] != 0
                    and "missing_deps" not in  b["category_counts"]]
    obj["number"] = len(new_builds)
    obj["file_name"] = "first_fail"
    obj["title"] = ("Packages that failed to build even though all "
                    " their deps built successfully")
    obj["description"] = "failed despite all their deps building"
    obj["semantics"] = {}
    variations.append((obj, new_builds))

    # TOOLCHAIN-SPECIFIC STUFF =========================================

    variations.append(({"heading":
        "Builds below this line built on vanilla but not with"
        " this toolchain,<br />"
        "and failed for a reason other than no-sources or dep-fail."},
        []))

    builds = [b for b in builds if b["return_code"] != 0
                               and b["built_on_vanilla"]
      and ("missing_source" not in b["category_counts"])
        and ("missing_deps" not in b["category_counts"])]

    obj = {}
    new_builds = builds
    obj["number"] = len(new_builds)
    obj["file_name"] = "toolchain_fails_only"
    obj["title"] = "Toolchain fails, not including no-{sources,deps}"
    obj["description"] = "satisfy the above restriction."
    obj["semantics"] = {}
    variations.append((obj, new_builds))

    # CONFIGURE STUFF ==================================================

    variations.append(({"heading": "Configure statistics"}, []))

    obj = {}
    new_builds = [b for b in builds
                          if b["configure_status"] == "unknown"]
    obj["number"] = len(new_builds)
    obj["file_name"] = "configure_unknown"
    obj["title"] = ("Packages with a configure log whose return code we"
                    " couldn't parse")
    obj["description"] = "had a config.log with unknown return code"
    obj["semantics"] = {}
    variations.append((obj, new_builds))

    obj = {}
    new_builds = [b for b in builds
                          if b["configure_status"] == "no log"]
    obj["number"] = len(new_builds)
    obj["file_name"] = "configure_no_log"
    obj["title"] = "Packages with no configure log"
    obj["description"] = "had no config.log"
    obj["semantics"] = {}
    variations.append((obj, new_builds))

    obj = {}
    new_builds = [b for b in builds
                          if b["configure_status"] == "success"]
    obj["number"] = len(new_builds)
    obj["file_name"] = "configure_success"
    obj["title"] = "Packages where all ./configures were successful"
    obj["description"] = "had all their configure checks successful"
    obj["semantics"] = {}
    variations.append((obj, new_builds))

    obj = {}
    new_builds = [b for b in builds
                          if "configure_error" in b["category_counts"]
                          or b["configure_status"] == "failure"]
    obj["number"] = len(new_builds)
    obj["file_name"] = "configure_failure"
    obj["title"] = "Packages where at least one ./configure failed"
    obj["description"] = "had at least one ./configure fail"
    obj["semantics"] = {}
    variations.append((obj, new_builds))

    # GENERIC STUFF ====================================================

    variations.append(({"heading": "Generic errors"}, []))

    obj = {}
    new_builds = [b for b in builds if "host_flag_unrecognised"
                                    in  b["category_counts"]]
    obj["number"] = len(new_builds)
    obj["file_name"] = "host_flag_unrecognised"
    obj["title"] = "Packages whose configure doesn't understand --host"
    obj["description"] = ("failed because their configure doesn't"
                          " understand --host")
    obj["semantics"] = {}
    variations.append((obj, new_builds))

    obj = {}
    new_builds = [b for b in builds if "configure_ignores_path"
                                    in  b["category_counts"]]
    obj["number"] = len(new_builds)
    obj["file_name"] = "configure_ignores_path"
    obj["title"] = "Builds where ./configure doesn't get $PATH"
    obj["description"] = "failed when configure ignored our $PATH"
    obj["semantics"] = {}
    variations.append((obj, new_builds))

    variations.append(({"heading": "Builds that fail when "
                        "executing an unrunnable binary"}, []))

    obj = {}
    new_builds = [b for b in builds
                          if "exec_error" in  b["configure_counts"]]
    obj["number"] = len(new_builds)
    obj["file_name"] = "exec_error_configure"
    obj["title"] = ("Packages that tried to execute an unrunnable binary"
                    " in their configure script")
    obj["description"] = "...in their configure script"
    obj["semantics"] = overall_semantics(new_builds, "exec_error")
    variations.append((obj, new_builds))

    obj = {}
    new_builds = [b for b in builds
                          if "exec_error" in  b["non_configure_counts"]]
    obj["number"] = len(new_builds)
    obj["file_name"] = "exec_error_non_configure"
    obj["title"] = ("Packages that tried to execute an unrunnable binary"
                    " after their configure script")
    obj["description"] = "...outside their configure script"
    obj["semantics"] = overall_semantics(new_builds, "exec_error")
    variations.append((obj, new_builds))

    variations.append(({"heading": "Builds that fail "
                        "because of an unfound command"}, []))
    obj = {}
    new_builds = [b for b in builds if "command_not_found"
                                    in  b["configure_counts"]]
    obj["number"] = len(new_builds)
    obj["file_name"] = "command_not_found"
    obj["title"] = ("Packages that invoked an unfound command in"
                    " configure")
    obj["description"] = "...in their configure script"
    obj["semantics"] = overall_semantics(new_builds,
                                         "command_not_found")
    variations.append((obj, new_builds))

    obj = {}
    new_builds = [b for b in builds if "command_not_found"
                                    in  b["non_configure_counts"]]
    obj["number"] = len(new_builds)
    obj["file_name"] = "command_not_found_non"
    obj["title"] = ("Packages that invoked an unfound command outside"
                    " configure")
    obj["description"] = "...outside their configure script"
    obj["semantics"] = overall_semantics(new_builds,
                                         "command_not_found")
    variations.append((obj, new_builds))

    variations.append(({"heading": "Builds that fail by supplying an "
                        "unknown flag to the compiler"}, []))

    obj = {}
    new_builds = [b for b in builds if "unknown_compiler_flag"
                                    in  b["configure_counts"]]
    obj["number"] = len(new_builds)
    obj["file_name"] = "unknown_compiler_flag"
    obj["title"] = ("Packages that supplied an unknown flag to the"
                    "compiler in their configure script")
    obj["description"] = "...in their configure script"
    obj["semantics"] = overall_semantics(new_builds,
                                         "unknown_compiler_flag")
    variations.append((obj, new_builds))

    obj = {}
    new_builds = [b for b in builds if "unknown_compiler_flag"
                                    in  b["non_configure_counts"]]
    obj["number"] = len(new_builds)
    obj["file_name"] = "unknown_compiler_flag_non"
    obj["title"] = ("Packages that supplied an unknown flag to the"
                    "compiler outside their configure script")
    obj["description"] = "...outside their configure script"
    obj["semantics"] = overall_semantics(new_builds,
                                         "unknown_compiler_flag")
    variations.append((obj, new_builds))

    variations.append(({"heading": "Builds that fail by invoking a"
                        "native tool"}, []))

    obj = {}
    new_builds = [b for b in builds if "native_tool_invocation"
                                    in  b["configure_counts"]]
    obj["number"] = len(new_builds)
    obj["file_name"] = "native_invocation"
    obj["title"] = ("Packages that tried to invoke the native toolchain"
                    " inside their configure script")
    obj["description"] = "...inside their configure script"
    obj["semantics"] = overall_semantics(new_builds,
                                         "native_tool_invocation")
    variations.append((obj, new_builds))

    obj = {}
    new_builds = [b for b in builds if "native_tool_invocation"
                                    in  b["non_configure_counts"]]
    obj["number"] = len(new_builds)
    obj["file_name"] = "non_native_invocation"
    obj["title"] = ("Packages that tried to invoke the native toolchain"
                    " outside their configure script")
    obj["description"] = "...outside their configure script"
    obj["semantics"] = overall_semantics(new_builds,
                                         "native_tool_invocation")
    variations.append((obj, new_builds))

    variations.append(({"heading": "Builds that fail because of a "
                        "missing header"}, []))

    obj = {}
    new_builds = [b for b in builds if "missing_header"
                                    in  b["configure_counts"]]
    obj["number"] = len(new_builds)
    obj["file_name"] = "missing_header"
    obj["title"] = ("Builds where a header was missing"
                    " inside the configure script")
    obj["description"] = "...inside their configure script"
    obj["semantics"] = overall_semantics(new_builds,
                                         "missing_header")
    variations.append((obj, new_builds))

    obj = {}
    new_builds = [b for b in builds if "missing_header"
                                    in  b["non_configure_counts"]]
    obj["number"] = len(new_builds)
    obj["file_name"] = "non_missing_header"
    obj["title"] = ("Builds where a header was missing"
                    " outside the configure script")
    obj["description"] = "...outside their configure script"
    obj["semantics"] = overall_semantics(new_builds,
                                         "missing_header")
    variations.append((obj, new_builds))

    variations.append(({"heading": "Builds that fail because of an "
                        "assembler error"}, []))

    obj = {}
    new_builds = [b for b in builds if "assembler_error"
                                    in b["configure_counts"]]
    obj["number"] = len(new_builds)
    obj["file_name"] = "assembler_error"
    obj["title"] = "Packages with assembler errors in configure"
    obj["description"] = "...inside their configure script"
    obj["semantics"] = overall_semantics(new_builds,
                                         "assembler_error")
    variations.append((obj, new_builds))

    obj = {}
    new_builds = [b for b in builds if "assembler_error"
                                    in b["non_configure_counts"]]
    obj["number"] = len(new_builds)
    obj["file_name"] = "assembler_error"
    obj["title"] = "Packages with assembler errors outside configure"
    obj["description"] = "...outside their configure script"
    obj["semantics"] = overall_semantics(new_builds,
                                         "assembler_error")
    variations.append((obj, new_builds))

    variations.append(({"heading": "Builds that fail because of a "
                        "compiler error"}, []))

    obj = {}
    new_builds = [b for b in builds if "compile_error"
                                    in b["configure_counts"]]
    obj["number"] = len(new_builds)
    obj["file_name"] = "compile_error"
    obj["title"] = "Packages with compile errors in configure"
    obj["description"] = "...inside their configure script"
    obj["semantics"] = overall_semantics(new_builds,
                                         "compile_error")
    variations.append((obj, new_builds))

    obj = {}
    new_builds = [b for b in builds if "compile_error"
                                    in b["non_configure_counts"]]
    obj["number"] = len(new_builds)
    obj["file_name"] = "non_compile_error"
    obj["title"] = "Packages with compile errors outside configure"
    obj["description"] = "...outside their configure script"
    obj["semantics"] = overall_semantics(new_builds,
                                         "compile_error")
    variations.append((obj, new_builds))

    variations.append(({"heading": "Builds that fail because of a "
                        "linker error"}, []))

    obj = {}
    new_builds = [b for b in builds if "link_error"
                                    in b["configure_counts"]]
    obj["number"] = len(new_builds)
    obj["file_name"] = "link_error"
    obj["title"] = "Packages with link errors in their configure scripts"
    obj["description"] = "...inside their configure scripts"
    obj["semantics"] = overall_semantics(new_builds,
                                         "link_error")
    variations.append((obj, new_builds))

    obj = {}
    new_builds = [b for b in builds if "link_error"
                                    in b["non_configure_counts"]]
    obj["number"] = len(new_builds)
    obj["file_name"] = "non_link_error"
    obj["title"] = ("Packages with link errors outside their configure"
                    " scripts")
    obj["description"] = "...outside their configure scripts"
    obj["semantics"] = overall_semantics(new_builds,
                                         "link_error")
    variations.append((obj, new_builds))

    variations.append(({"heading": "Builds that fail because of an "
                        "undefined reference"}, []))

    obj = {}
    new_builds = [b for b in builds if "undefined_reference"
                                    in b["non_configure_counts"]]
    obj["number"] = len(new_builds)
    obj["file_name"] = "undefined_reference"
    obj["title"] = ("Packages with undefined references during"
                    "compilation")
    obj["description"] = "...during compilation"
    obj["semantics"] = overall_semantics(new_builds,
                                         "undefined_reference")
    variations.append((obj, new_builds))

    obj = {}
    new_builds = [b for b in builds if b["return_code"]
                               and not b["category_counts"]]
    obj["number"] = len(new_builds)
    obj["file_name"] = "unknown_fail"
    obj["title"] = "Packages with unclassified failures"
    obj["description"] = "failed for some unknown reason"
    obj["semantics"] = {}
    variations.append((obj, new_builds))

    return variations


def proc_log(build):
    """Adds semantic information to the bodies of structs.

    Arguments:
        data["log"]:
            a list of log dicts as generated by utilities.log(). In
            particular, each dict is expected to have a body, which is a
            list of strings---each string corresponds to a line in the
            output of some command. i.e.
             [
                {
                    "head": "command_to_execute",
                    "body": [
                    ____________________________________________________
                        "output line 1",            <<< EACH OF THESE
                                                        WILL BE CHANGED
                    ____________________________________________________
                        ...
                    ]
                },
                ...
             ]
    Returns:
        a new log, but with each line in the body of each log dict
        replaced with a dict that contains semantic information about
        the line. This method attempts to detect error-indicating lines
        in the bodies of log dicts.
             [
                {
                    "head": "command_to_execute",
                    "body": [
                    ____________________________________________________
                        {                                   <
                            "text": "output line 1",        <
                            "format": "error",              <
                            "category": "dependency_fail",  < INTO
                            "semantics": {                  < THIS
                                "bad_package": "foo"        <
                            }                               <
                        }                                   <
                    ____________________________________________________
                        ...
                    ]
                },
                ...
             ]
        Within each dict, the "text", "format", "category" and
        "semantics" keys are guaranteed to exist (semantics may be
        empty).  Fields within "semantics" depend on what "category" is.
    """
    ret = []
    for struct in build["log"]:
        # Modify a copy
        new_body = []

        # If this struct is a configure log, we don't want to flag any
        # 'errors' in the log if configure actually returned
        # successfully. This is because configure will run the compiler
        # on things which are expected to fail.

        if "configure_status" in struct:
            if struct["configure_status"] == "success":
                for line in struct["body"]:
                    new_body.append(default_struct(line))

            elif struct["configure_status"] == "failure":
                for line in struct["body"]:
                    new_body.append(transform_line(line))

            elif struct["configure_status"] == "unknown":
                new_body.append(transform_line(
                    "tuscan: configure log has no return code"))
                if build["return_code"] == 0:
                    for line in struct["body"]:
                        new_body.append(default_struct(line))
                else:
                    for line in struct["body"]:
                        new_body.append(transform_line(line))

            else: raise RuntimeError(str(struct["configure_status"]))
        else:
            for line in struct["body"]:
                new_body.append(transform_line(line))

        new_struct = dict(struct)
        new_struct["body"] = new_body
        ret.append(new_struct)

    # Add a log line that indicates if the $PATH has been lost.

    for struct in ret:
        seen_platform = False
        seen_toolchain_path = False
        marked_with_error = False
        for line in struct["body"]:
            m = match("## Platform. ##", line["text"])
            if m:
                seen_platform = True
                continue
            m = match("PATH: /toolchain_root/bin", line["text"])
            if m and seen_platform:
                seen_toolchain_path = True
                continue
            m = match("PATH: .+", line["text"])
            if m and not seen_toolchain_path and not marked_with_error:
                marked_with_error = True
                line["format"] = "error"
                line["category"] = "configure_ignores_path"
    return ret


def colours(args):
    if args.you_are_an_engineer:
        return {
            "dark": "#002b36",
            "light": "#839496",
            "bg": "#002b36",
            "fg": "#839496",
            "bgh": "#073642",
            "fgh": "#93a1a1",
            "red": "#dc322f",
            "blue": "#268bd2",
            "green": "#859900",
            "yellow": "#b58900",
            "cyan": "#2aa198",
            "orange": "#cb4b16",
            "magenta": "#d33682",
            "violet": "#6c71c4",
        }
    else:
        return {
            "dark": "#212121",
            "light": "#fafafa",
            "bg": "#fff",
            "fg": "#212121",
            "bgh": "#e0e0e0",
            "fgh": "#000",
            "red": "#f44336",
            "blue": "#2196f3",
            "green": "#4db6ac",
            "yellow": "#ffeb3b",
            "cyan": "#00bcd4",
            "orange": "#ff9800",
            "magenta": "#e91e63",
            "violet": "#42a5f5",
        }


def do_html(args):
    """Top-level function called when running tuscan.py html."""
    rmtree("html", ignore_errors=True)
    makedirs("html")

    env = Environment(loader=FileSystemLoader(["site_gen"]))

    vanilla_builds = []

    # We want to process the vanilla toolchain first if it exists, in
    # order to get the "build on vanilla" column on other toolchains
    toolchains = listdir("results")
    if isdir("results/vanilla"):
        toolchains.remove("vanilla")
        toolchains = ["vanilla"] + toolchains

    # This should get populated with build_name -> return_code on the
    # first run of the loop, and is used by write_single_package_pages
    # in subsequent iterations.
    vanilla_results = {}

    for tc in toolchains:
        results = write_single_package_pages(env, tc, args,
                                             vanilla_results)

        variations = get_variations(results)

        for desc, results in variations:
            if not results:
                continue

            results = {"toolchain": tc,
                      "packages": results,
                      "title": desc["title"],
                      "variations": [vs[0] for vs in variations],
                      "verbose": args.verbose,
                      "semantics": desc["semantics"],
                      "col": colours(args),
                    }
            templ = env.get_template("toolchain.jinja.html")
            html = templ.render(data=results, toolchains=toolchains)
            path = join("html", tc, desc["file_name"] + ".html")
            with open(path, "w") as f:
                f.write(html.encode("utf-8"))
    stderr.write("\n")

    templ = env.get_template("top_level.jinja.html")
    html = templ.render(toolchains=toolchains)
    path = join("html", "index.html")
    with open(path, "w") as f:
        f.write(html.encode("utf-8"))
