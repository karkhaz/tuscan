#!/usr/bin/python2
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


"""Generate a HTML report for a single package compilation attempt.

This script should be run after a build attempt has been run on a
package under a particular toolchain. The build attempt will result in a
JSON file being output somewhere; this script reads that data and
formats it nicely.
"""


from argparse import ArgumentParser
from errno import EEXIST
from json import load
from os import makedirs
from os.path import isfile, isdir
from sys import stderr
from textwrap import dedent


def mkdir_p(directory):
    try:
        makedirs(directory)
    except OSError as e:
        if not (e.errno == EEXIST and isdir(directory)):
            raise e


def seconds_to_hhmmss(seconds):
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return "%02d:%02d:%02d" % (hours, minutes, seconds)


def get_json(package, toolchain):
    path = ("results/" + toolchain + "/latest/pkgbuild_markers/"
            + package + ".json")
    try:
        with open(path) as f:
            json = load(f)
    except:
        stderr.write("WARNING: could not load " + path +
                     ", not generating report.\n")
        exit(0)
    return json


def setup_argparse():
    parser = ArgumentParser(
      description="Generate report for a single build attempt.")
    parser.add_argument("--package", dest="package", required=True)
    parser.add_argument("--toolchain", dest="toolchain", required=True)
    return parser.parse_args()


def gen_page(json, toolchain):
    return dedent(
        """\
        <html><head></head><body>
        <h1>Report for %s on toolchain
            <a href="%s">%s</a>
        </h1>
        <p>Return code: %s</p>
        <p>Time to run: %s</p>
        <p>Log output:</p>
        <code><pre><%s></pre></code>
        </body></html>
        """ % (
            json["package"],
            "index.html",
            toolchain,
            json["return_code"],
            seconds_to_hhmmss(json["time"]),
            "\n".join(json["log"])
        )
    )


def cell(contents, attributes=""):
    if contents == True or contents == "yes":
        return "<td class=\"nowrap yes\">x</td>"
    elif contents == False or contents == "no":
        return "<td class=\"nowrap no\">y</td>"
    elif contents == "dunno":
        return "<td class=\"nowrap dunno\">z</td>"
    else:
        return "<td " + attributes + ">" + contents + "</td>"


def built_on_vanilla(package):
    path = ("results/vanilla/latest/pkgbuild_markers/"
            + package + ".json")
    if isfile(path):
        try:
            with open(path) as f:
                json = load(f)
        except:
            return "dunno"
        if json["return_code"]:
            return "no"
        else:
            return "yes"
    else: return "dunno"


def table_row_of(json, toolchain):
    row = "<tr>"

    row += cell(built_on_vanilla(json["package"]))
    row += cell(json["return_code"] == 0)
    row += cell("dunno")
    row += cell(seconds_to_hhmmss(json["time"]),
                attributes="class=\"nowrap\" style=\"width: 6em\"")

    link = "<a href=%s>%s</a>" % (json["package"] + ".html",
                                  json["package"])
    row += cell(link,
                attributes="class=\"nowrap\" style=\"width: 20em\"")

    row += cell("",
                attributes="class=\"last-col\"")

    return row + "</tr>"


def write_row(row, package, toolchain):
    row_dir = "results/" + toolchain + "/latest/rows/"
    mkdir_p(row_dir)

    path = row_dir + package + ".row.html"
    with open(path, "w") as f:
        f.write(row)


def write_page(page, package, toolchain):
    page_dir = "html/" + toolchain
    mkdir_p(page_dir)

    path = page_dir + "/" + package + ".html"
    with open(path, "w") as f:
        f.write(page)


def main():
    args = setup_argparse()
    json = get_json(args.package, args.toolchain)

    table_row = table_row_of(json, args.toolchain)
    write_row(table_row, args.package, args.toolchain)

    page = gen_page(json, args.toolchain)
    write_page(page, args.package, args.toolchain)


if __name__ == "__main__":
    main()
