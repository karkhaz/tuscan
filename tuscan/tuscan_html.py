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

"""Generation of HTML pages from post-processed data."""


from tuscan.schemata import post_processed_schema


import functools
import jinja2
import json
import multiprocessing
import os
import os.path
import re
import shutil
import signal
import sys
import traceback
import voluptuous
import yaml


def summary_structure(toolchains):
    """A dictionary representing the hierarchy of summaries.

    The dictionary returned by this function describes what summary
    pages are to be generated. A summary page contains a list of builds
    that satisfy some property; that property is predicated on the
    "filter" member of the dictionary. If some other summary pages
    satisfy a superset of the properties of this summary structure, then
    those pages will be in the "children" member of the dictionary.
    """

    with open("tuscan/classification_patterns.yaml") as f:
        _patterns = yaml.load(f)
    categories = set([p["category"] for p in _patterns])

    def native_tool_freq(build):
        total = 0
        for _, freq in build["native_tools"].items():
            total += freq
        return -1 * total

    def error_trees(toolchain):
        error_trees = []
        for category in categories:
            obj = {
                "name": category,
                "filter": (lambda build, category=category,
                            toolchain=toolchain:
                                category in build["category_counts"]),
                "description": ("Builds that exhibited error '%s' on "
                                "toolchain '%s'"
                                % (category, toolchain)),
                "link_text": "%s ({total} builds)" % category
            }
            error_trees.append(obj)
        error_trees.append({
            "name": "native-redirect",
            "filter": (lambda b: b["native_tools"]),
            "description": ("Builds that failed even after their native"
                            " tools were redirected to toolchain tools "
                            "(sorted by number of invocations)"),
            "link_text": "Builds invoking native tools ({total})",
            "sort_fun": native_tool_freq
        })
        error_trees.append({
            "name": "blockers",
            "filter": (lambda build, toolchain=toolchain:
                build["return_code"] and build["toolchain"] == toolchain
                and not "missing_deps" in build["category_counts"]),
            "description": ("Packages whose dependencies all built, "
                            "but which failed to build on toolchain"
                            " '%s'" % toolchain),
            "link_text": "Blockers ({total} builds)"
        })
        error_trees.append({
            "name": "unclassified",
            "filter": (lambda b: b["return_code"]
                         and not b["category_counts"]),
            "description": ("Failing builds that we failed to classify"),
            "link_text": "Unclassified ({total} builds)",
        })
        return error_trees

    vanilla_tree = {
        "title": "vanilla",
        "filter": (lambda b: b["toolchain"] == "vanilla"),
        "toolchains_to_display": ["vanilla"],
        "children": [{
            "name": "pass",
            "filter": (lambda b: not b["return_code"]),
            "description": "Builds that passed on vanilla",
            "link_text": "{total} passed"
        }, {
            "name": "fail",
            "filter": (lambda b: b["return_code"]),
            "description": "Builds that failed on vanilla",
            "link_text": "{total} failed",
            "children": list(error_trees("vanilla"))
        }]
    }

    toolchain_trees = []
    for toolchain in [t for t in toolchains if t != "vanilla"]:
        obj = {
            "title": toolchain,
            "filter": (lambda build, toolchain=toolchain:
                            build["toolchain"] == toolchain),
            "toolchains_to_display": [toolchain],
            "children": [{
                "name": "pass",
                "filter": (lambda build: build["return_code"] == 0),
                "description": ("Builds that passed with toolchain "
                                "'%s'" % toolchain),
                "link_text": "{total} passed",
                "children": [{
                    "name": "native-redirect",
                    "filter": (lambda b: b["native_tools"]),
                    "description": ("Builds that passed only after "
                                    "their native tools were redirected"
                                    " to toolchain tools (sorted by "
                                    "number of invocations)"),
                    "link_text": ("({total} had their native "
                                  "tools redirected)"),
                    "sort_fun": native_tool_freq
                }]
              }, {
                "name": "fail",
                "filter": (lambda build: build["return_code"] != 0),
                "description": ("Builds that failed with toolchain "
                                "'%s'" % toolchain),
                "link_text": "{total} failed. Errors:",
                "children": list(error_trees(toolchain))
              }
            ]
        }
        toolchain_trees.append(obj)

    alternatives = {
        "title": "Builds below this line passed on vanilla",
        "filter": (lambda b: b["vanilla_success"]),
        "children": toolchain_trees
    }

    top_level_tree = {
      "title": "All Builds",
      "toolchains_to_display": toolchains,
      "children" : ([{
          "name": "all",
          "description": "all builds across all toolchains",
          "link_text": "{total} total builds"
          }, {
            "name": "cish-programs",
            "filter": (lambda build: (
                "ansic" in build["sloc_info"] or
                "cpp" in build["sloc_info"]
            )),
            "description": "Builds that contain C/C++ code",
            "link_text": "{total} of these contain C(++) code.",
            "children": [vanilla_tree] + [alternatives]
          }
      ])
    }

    return top_level_tree


def create_summary_pages(summary, ret, parent_name, builds, toolchains, jinja):
    """A dict containing summary pages and a side bar.

    This function returns a dict with the following keys:
    - sidebar: a HTML sidebar that links to all the summary pages
    - pages: a dict containing HTML summary pages and metadata.

    The summary pages are generated by filtering the list of builds
    using the summary_structure function.
    """
    ret_list = []
    new_builds = list(builds)
    if "filter" in summary:
        new_builds = filter(summary["filter"], new_builds)

    # No need to create a summary page & sidebar entry if no builds
    # match the criteria
    if not new_builds:
        return None

    new_toolchains = list(toolchains)
    if "toolchains_to_display" in summary:
        new_toolchains = summary["toolchains_to_display"]

    if "name" in summary:
        name = "%s-%s" % (parent_name, summary["name"])
    elif "title" in summary:
        name = "%s-%s" % (parent_name, re.sub("\s", "-",
            summary["title"]).lower())

    if "children" in summary:
        child_list = []
        for child in summary["children"]:
            child_ret = create_summary_pages(child, ret=ret,
                parent_name=name, builds=list(new_builds),
                toolchains=list(new_toolchains), jinja=jinja)
            if child_ret and child_ret["sidebar"]:
                child_list.append(child_ret["sidebar"])
        child_list = "\n".join(child_list)
    else:
        child_list = ""

    if "name" in summary:
        if "sort_fun" in summary:
            _order = sorted(new_builds, key=summary["sort_fun"])
        else:
            _order = sorted(new_builds, key=(lambda b: b["build_name"]))
        _order = [os.path.basename(build["build_name"]) for build in _order]
        order = []
        for e in _order:
            if e not in order:
                order.append(e)

        organised = organise_builds(new_builds, new_toolchains)
        template = jinja.get_template("package_list.html.jinja")
        html = template.render(builds=organised, toolchains=new_toolchains)
        ret["pages"].append({
            "name": name,
            "html": html,
            "description": summary["description"],
            "length": len(organised)
        })

        link_text = summary["link_text"].format(
                total=len(new_builds) / len(new_toolchains))
        list_text = ('<li>\n<a href="{name}.html">{link_text}</a>\n'
                     '\n{child_list}\n</li>').format(
                        name=name, link_text=link_text,
                        child_list=child_list)
        ret_list.append(list_text)
    else:
        list_text = ("<li>\n{title}\n{child_list}\n</li>".format(
            title=summary["title"], child_list=child_list))
        ret_list.append(list_text)

    sidebar = "<ul>%s</ul>" % ("\n".join(ret_list))
    return {"sidebar": sidebar, "pages": ret["pages"]}


def write_summary_pages(dst_dir, toolchains, builds, jinja):
    """Dumps lists of builds that satisfy certain properties."""

    # When building summary pages, we want the toolchains to appear in
    # order; vanilla first, then everything else
    def toolchain_sorter(toolchain):
        return "" if toolchain == "vanilla" else toolchain
    toolchains = sorted(toolchains, key=toolchain_sorter)

    summary_return = { "sidebar": "", "pages": [] }
    summaries = create_summary_pages(parent_name="tuscan",
            ret=summary_return, summary=summary_structure(toolchains),
            builds=builds, toolchains=toolchains, jinja=jinja)

    template = jinja.get_template("package_summary.html.jinja")
    for s in summaries["pages"]:
        html = template.render(title=s["name"],
                description=s["description"], build_list=s["html"],
                length=s["length"], sidebar=summaries["sidebar"])

        with open(os.path.join(dst_dir, "%s.html" % s["name"]), "w") as f:
            f.write(html)

    shutil.copyfile(os.path.join(dst_dir, "tuscan-all-builds-all.html"),
             os.path.join(dst_dir, "index.html"))


def get_errors(log):
    error_lines = []
    for struct in log:
        error_lines += [line for line in struct["body"] if line["category"]]
    # Transform list of {category: foo, text: bar} into dictionary
    # mapping categories to list of texts, so that errors of the same
    # category can be grouped together on the web page. Also include the
    # error ID, so that we can link to that line on the web page
    ret = {}
    for struct in error_lines:
        if struct["category"] not in ret:
            ret[struct["category"]] = []
        obj = {"text": struct["text"], "id": struct["id"]}
        ret[struct["category"]].append(obj)
    return ret


def s_to_hhmmss(seconds):
    mins, secs = divmod(seconds, 60)
    hours, mins = divmod(mins, 60)
    return "%02dh %02dm %02ds" % (hours, mins, secs)


def pretty_process(proc):
    """The HTML list item for a single build process."""
    if proc["return_code"] is None:
        rc = '<span class="no-return">?</span>'
    elif proc["return_code"]:
        rc = '<span class="bad-return">%s</span>' % proc["return_code"]
    else:
        rc = '<span class="good-return">%s</span>' % proc["return_code"]
    command = "<code>%s</code>" % proc["command"]
    return "%s %s" % (rc, command)


def list_of_process_tree(tree, indent=0):
    """Generate a nested HTML list from a process tree

    This cannot be implemented in jinja, since the tree is a recursive
    data structure.
    """
    pad = "  " * indent
    next_pad = "  " * (indent + 1)
    tree = sorted(tree, key=(lambda item: item["timestamp"]))
    output = []
    output.append('%s<ul class="level-%s">' % (pad, indent))
    for item in tree:
        output.append("%s<li>%s" % (next_pad, pretty_process(item)))
        output.append(list_of_process_tree(item["children"], indent+2))
        output.append("%s</li>" % (next_pad))
    output.append("%s</ul>" % pad)
    return "\n".join(output)


def dump_build_page(json_path, toolchain, jinja, out_dir, args,
        results_list):
    try:
        with open(json_path) as f:
            data = json.load(f)
        post_processed_schema(data)

        # First, dump the process tree

        tree = list_of_process_tree(data["bear_output"])
        template = jinja.get_template("build_tree.html.jinja")
        html = template.render(
                build_name=os.path.basename(data["build_name"]),
                tree=tree, toolchain=data["toolchain"])
        tree_path = os.path.join(out_dir, "%s-tree.html" %
                os.path.basename(data["build_name"]))
        with open(tree_path, "w") as f:
            f.write(html.encode("utf-8"))

        # Now, the build log. Link to the process tree.

        template = jinja.get_template("build.jinja.html")
        data["toolchain"] = toolchain
        data["name"] = os.path.basename(data["build_name"])
        data["time"] = s_to_hhmmss(data["time"])
        data["errors"] = get_errors(data["log"])
        data["blocks"] = [os.path.basename(b) for b in data["blocks"]]
        data["blocked_by"] = [os.path.basename(b) for b in data["blocked_by"]]
        data["tree_path"] = os.path.basename(tree_path)
        html = template.render(data=data)

        out_path = os.path.join(out_dir, "%s.html" %
                os.path.basename(data["build_name"]))
        with open(out_path, "w") as f:
            f.write(html.encode("utf-8"))

        # We now want to return this build to the top-level so that it
        # can generate summary pages of all builds. There is no need to
        # keep the build log for the summary, and it uses a lot of
        # memory, so remove it from the data structure.
        data.pop("log", None)
        data.pop("bear_output", None)
        results_list.append(data)

    except voluptuous.MultipleInvalid as e:
        sys.stderr.write("%s: Post-processed data is malformed: %s\n" %
                     (json_path, str(e)))
        exit(1)
    except Exception as e:
        # Running in a separate process suppresses stack trace dump by
        # default, so do it manually
        traceback.print_exc(file=sys.stderr)
        raise e


def organise_builds(build_list, toolchains):
    """Transform a list of flat dicts into a name -> toolchain -> dict

    When outputting summary pages, we want the table to be organised by
    name, then toolchain, and then the rest of the data. This function
    transforms an dict returned by dump_build_page into that form.
    """
    ret = {}
    for build in build_list:
        d = dict(build)
        if d["toolchain"] not in toolchains:
            continue
        build_name = d["build_name"]
        build_name = os.path.basename(build_name)
        d.pop("build_name", None)
        if not build_name in ret:
            ret[build_name] = {}
        toolchain = d["toolchain"]
        d.pop("toolchain", None)
        ret[build_name][toolchain] = d
    return ret


def add_vanilla_success(results, toolchains):
    ret = []
    results = organise_builds(results, toolchains)
    for name, build_dict in results.items():
        if "vanilla" in build_dict:
            success = build_dict["vanilla"]["return_code"] == 0
        else:
            success = None
        for tc, build in build_dict.items():
            build = dict(build)
            build["vanilla_success"] = success
            build["build_name"] = name
            build["toolchain"] = tc
            ret.append(build)
    return ret


def do_html(args):
    src_dir = "output/post"
    dst_dir = "output/html"

    if not os.path.isdir(src_dir):
        sys.stderr.write("directory 'post' does not exist; run './tuscan.py"
                     " post' before './tuscan.py html'\n")
        exit(1)

    jinja = jinja2.Environment(loader=jinja2.FileSystemLoader(["tuscan"]))

    if not os.path.isdir(dst_dir):
        os.makedirs(dst_dir)
    for f in os.listdir(dst_dir):
        if os.path.isdir(os.path.join(dst_dir, f)):
            shutil.rmtree(os.path.join(dst_dir, f))
        else:
            os.unlink(os.path.join(dst_dir, f))
    shutil.copyfile("tuscan/style.css", os.path.join(dst_dir, "style.css"))
    shutil.copyfile("tuscan/summary.css", os.path.join(dst_dir, "summary.css"))

    man = multiprocessing.Manager()
    results_list = man.list()

    pool = multiprocessing.Pool(args.pool_size)
    toolchain_total = len(os.listdir(src_dir))
    toolchain_counter = 0
    toolchains = []
    for toolchain in os.listdir(src_dir):
        toolchains.append(toolchain)
        toolchain_counter += 1
        sys.stderr.write("Generating individual build reports for "
                     "toolchain %d of %d [%s]\n" %
                     (toolchain_counter, toolchain_total, toolchain))

        toolchain_src = os.path.join(src_dir, toolchain)
        toolchain_dst = os.path.join(dst_dir, toolchain)

        if not os.path.isdir(toolchain_dst):
            os.makedirs(toolchain_dst)

        for f in os.listdir(toolchain_dst):
            os.unlink(os.path.join(toolchain_dst, f))

        jsons = [os.path.join(toolchain_src, f) for f in os.listdir(toolchain_src)]

        curry = functools.partial(dump_build_page, out_dir=toolchain_dst,
                        toolchain=toolchain, args=args, jinja=jinja,
                        results_list=results_list)

        try:
            original = signal.signal(signal.SIGINT, signal.SIG_IGN)
            # Child processes inherit the 'ignore' signal handler
            res = pool.map_async(curry, jsons)
            # Parent process listens to SIGINT.
            signal.signal(signal.SIGINT, original)
            res.get(args.timeout)
        except KeyboardInterrupt:
            pool.terminate()
            pool.join()
            exit(0)
        except multiprocessing.TimeoutError:
            sys.stderr.write("Timed out (over %d seconds)\n" % args.timeout)
            pool.terminate()
            pool.join()
            exit(1)
    pool.close()
    pool.join()

    sys.stderr.write("Generating summary pages\n")

    # We need to add an extra key to each build, indicating if the build
    # was successful on vanilla.
    results_list = add_vanilla_success(results_list._getvalue(), toolchains)
    write_summary_pages(dst_dir, toolchains, results_list, jinja)
