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

from functools import partial
from logging import basicConfig, debug, info, error, warning, INFO
from jinja2 import Environment, FileSystemLoader
from json import load
from os import listdir, makedirs
from os.path import basename, join, isdir, splitext
from subprocess import Popen, PIPE
from sys import stderr


class Counter:
    def __init__(self, total):
        self.total = total
        self.count = 0

    def inc(self):
        self.count += 1
        stderr.write("\r%5d/%5d" % (self.count, self.total))

    def finish(self):
        stderr.write("\n")


def render_gnuplot(data, jinja, script_name, out_dir):
    template = jinja.get_template("%s.gnu" % script_name)
    script = template.render(data=data, name=script_name)
    with open(join(out_dir, "%s.gnu" % script_name), "w") as f:
        f.write(script)


def load_results(post_dir):
    results = {}

    info("Loading results...")
    total = len(listdir(post_dir)) * len(listdir(join(post_dir,
                                        listdir(post_dir)[0])))
    counter = Counter(total)
    for tc in listdir(post_dir):
        tc_dir = join(post_dir, tc)
        for result_file in listdir(tc_dir):
            counter.inc()
            with open(join(tc_dir, result_file)) as f:
                result = load(f)
                build_name = basename(result["build_name"])
                if build_name not in results:
                    results[build_name] = {}
                results[build_name][tc] = result
    counter.finish()
    return results


def do_figures(args):
    basicConfig(format="%(asctime)s %(message)s", level=INFO)

    src_dir = "output/post"
    dst_dir = "output/figures"

    if not isdir(src_dir):
        stderr.write("directory 'post' does not exist; run './tuscan.py"
                     " post' before './tuscan.py figures'\n")
        exit(1)

    if not isdir(dst_dir):
        makedirs(dst_dir)

    results = load_results(src_dir)

    jinja = Environment(loader=FileSystemLoader(["tuscan/plots"]))
