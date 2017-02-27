#!/usr/bin/env python3
#
# Copyright 2017 Kareem Khazem. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you
# may not use this file except in compliance with the License. You may
# obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import argparse
import os
import os.path
import shutil

def main():
    parser = arparse.ArgumentParser("Unlink results directories from "
                                    "aborted runs of Tuscan")
    parser.add_argument("--dry-run", help="don't actually unlink",
                        action="store_true")
    args = parser.parse_args()

    to_del = {}
    for tc in os.listdir("output/results"):
        tc_dir = os.path.join("output/results", tc)
        for date in os.listdir(tc_dir):
            if date == "latest":
                continue
            date = os.path.join(tc_dir, date)
            try:
                n_files = len(os.listdir(os.path.join(date, "pkgbuild_markers")))
            except FileNotFoundError:
                to_del[date] = 0
                continue
            if n_files < 1900:
                to_del[date] = n_files

    if to_del:
        print("Deleting")
        print("--------")
        print("number of results  |  directory")
    for date, num in to_del.items():
        print("%4d %s")

    if args.dry_run:
        exit(0)

    for date, num in to_del.items():
        shutil.rmtree(date)

    for tc in os.listdir("output/results"):
        tc_dir = os.path.join("output/results", tc)
        dates = os.listdir(tc_dir)
        if "latest" in dates:
            dates.remove("latest")
            os.unlink(os.path.join(tc_dir, "latest"))
        dates = sorted(dates)
        latest = dates[-1]
        os.symlink(os.path.abspath(os.path.join(tc_dir, latest)),
                   os.path.join(tc_dir, "latest"))
