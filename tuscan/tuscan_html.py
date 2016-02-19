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

from functools import partial
from jinja2 import Environment, FileSystemLoader
from json import load, dumps
from multiprocessing import Pool
from voluptuous import MultipleInvalid
from os import listdir, makedirs, unlink
from os.path import basename, isdir, join
from shutil import copyfile
from signal import signal, SIGINT, SIG_IGN
from sys import stderr
from traceback import print_exc


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


def dump_build_page(json_path, toolchain, jinja, out_dir, args):
    try:
        with open(json_path) as f:
            data = load(f)
        post_processed_schema(data)

        template = jinja.get_template("build.jinja.html")
        data["toolchain"] = toolchain
        data["name"] = basename(data["build_name"])
        data["time"] = s_to_hhmmss(data["time"])
        data["errors"] = get_errors(data["log"])
        html = template.render(data=data)

        out_path = join(out_dir, "%s.html" % basename(data["build_name"]))
        with open(out_path, "w") as f:
            f.write(html.encode("utf-8"))

    except MultipleInvalid as e:
        stderr.write("%s: Post-processed data is malformed: %s\n" %
                     (json_path, str(e)))
        exit(1)
    except Exception as e:
        # Running in a separate process suppresses stack trace dump by
        # default, so do it manually
        print_exc(file=stderr)
        raise e


def do_html(args):
    src_dir = "post"
    dst_dir = "html"

    if not isdir(src_dir):
        stderr.write("directory 'post' does not exist; run './tuscan.py"
                     " post' before './tuscan.py html'\n")
        exit(1)

    jinja = Environment(loader=FileSystemLoader(["tuscan"]))

    copyfile("tuscan/style.css", join(dst_dir, "style.css"))

    pool = Pool(args.pool_size)
    for toolchain in listdir(src_dir):
        toolchain_src = join(src_dir, toolchain)
        toolchain_dst = join(dst_dir, toolchain)

        if not isdir(toolchain_dst):
            makedirs(toolchain_dst)

        for f in listdir(toolchain_dst):
            unlink(join(toolchain_dst, f))

        jsons = [join(toolchain_src, f) for f in listdir(toolchain_src)]

        curry = partial(dump_build_page, out_dir=toolchain_dst,
                        toolchain=toolchain, args=args, jinja=jinja)

        try:
            original = signal(SIGINT, SIG_IGN)
            # Child processes inherit the 'ignore' signal handler
            res = pool.map_async(curry, jsons)
            # Parent process listens to SIGINT.
            signal(SIGINT, original)
            res.get(args.timeout)
        except KeyboardInterrupt:
            pool.terminate()
            pool.join()
            exit(0)
        except TimeoutError:
            stderr.write("Timed out (over %d seconds)\n" % args.timeout)
            pool.terminate()
            pool.join()
            exit(1)
    pool.close()
    pool.join()
