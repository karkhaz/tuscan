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

"""Generation of figures from post-processed data."""


import functools
import jinja2
import json
import logging
import os
import os.path
import subprocess
import sys


class Counter:
    def __init__(self, total):
        self.total = total
        self.count = 0

    def inc(self):
        self.count += 1
        sys.stderr.write("\r%5d/%5d" % (self.count, self.total))

    def finish(self):
        sys.stderr.write("\n")


def render_gnuplot(data, jinja, script_name, out_dir):
    template = jinja.get_template("%s.gnu" % script_name)
    script = template.render(data=data, name=script_name)
    with open(os.path.join(out_dir, "%s.gnu" % script_name), "w") as f:
        f.write(script)


def sloc_distribution(results, jinja, out_dir):
    build_locs = {}
    for build_name, res_struct in results.items():
        for tc, results in res_struct.items():
            build_locs[build_name] = 0
            for _, loc in results["sloc_info"].items():
                build_locs[build_name] += loc
            break
    dist = {}
    for build, loc in build_locs.items():
        bucket = 1
        added = False
        while not added:
            bucket *= 10
            if bucket not in dist:
                dist[bucket] = 0
            if loc < bucket:
                added = True
                dist[bucket] += 1

    buckets = sorted(dist.keys())
    prefixes = ["", " k", " M"]
    x_label = 1
    idx = 0
    data = ""
    for bucket in buckets:
        x_label *= 10
        if x_label == 1000:
            x_label = 1
            idx += 1
        data += '  "< %d%s" %d\n' % (x_label, prefixes[idx],
                dist[bucket])

    render_gnuplot(data.strip(), jinja, "sloc-distribution", out_dir)


def load_results(post_dir):
    results = {}

    logging.info("Loading results...")
    total = len(os.listdir(post_dir)) * len(os.listdir(os.path.join(post_dir,
                                        os.listdir(post_dir)[0])))
    counter = Counter(total)
    for tc in os.listdir(post_dir):
        tc_dir = os.path.join(post_dir, tc)
        for result_file in os.listdir(tc_dir):
            counter.inc()
            with open(os.path.join(tc_dir, result_file)) as f:
                result = json.load(f)
                build_name = os.path.basename(result["build_name"])
                if build_name not in results:
                    results[build_name] = {}
                results[build_name][tc] = result
    counter.finish()
    return results


def do_figures(args):
    logging.basicConfig(format="%(asctime)s %(message)s", level=INFO)

    src_dir = "output/post"
    dst_dir = "output/figures"

    if not os.path.isdir(src_dir):
        sys.stderr.write("directory 'post' does not exist; run './tuscan.py"
                     " post' before './tuscan.py figures'\n")
        exit(1)

    if not os.path.isdir(dst_dir):
        os.makedirs(dst_dir)

    results = load_results(src_dir)

    jinja = jinja2.Environment(loader=jinja2.FileSystemLoader(["tuscan/plots"]))

    sloc_distribution(results, jinja, dst_dir)
