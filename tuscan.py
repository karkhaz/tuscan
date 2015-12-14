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

from tuscan.tuscan_html import do_html
from tuscan.tuscan_build import do_build

from argparse import ArgumentParser
from os import listdir


def get_argparser():
    parser = ArgumentParser(description=
               "Run corpus-based toolchain experiments.")

    subparsers = parser.add_subparsers(dest="command")

    # ./tuscan.py build
    build_parser = subparsers.add_parser("build",
            help="Build all packages with a particular toolchain.")
    build_parser.set_defaults(func=do_build)

    toolchains = listdir("toolchains")
    build_parser.add_argument("toolchain", choices=toolchains,
            help="a toolchain, configured in a subdirectory of"
                 " toolchains/.")

    build_parser.add_argument("-v", "--verbose", action="store_true",
            help="show Docker output")

    build_parser.add_argument("--top-level", dest="top_level",
            metavar="TARGET",
            help="override the top-level target to build.")

    build_parser.add_argument("--no-run", action="store_false",
            dest="run", help="Set up containers, but don't run ninja.")

    # ./tuscan.py html
    html_parser = subparsers.add_parser("html",
            help="Generate HTML output for results.")

    html_parser.add_argument("-v", "--verbose", action="store_true",
            dest="verbose",
            help="Show verbose information in results page")

    html_parser.add_argument("--im-an-engineer", action="store_true",
            dest="you_are_an_engineer",
            help="Use Solarized colour scheme")

    html_parser.set_defaults(func=do_html)

    return parser


def main():
    parser = get_argparser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
