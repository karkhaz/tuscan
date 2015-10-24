#!/usr/bin/env python3
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

import unittest

from os.path import exists
from subprocess import run, DEVNULL
from sys import path

class TestGetBasePackageNames(unittest.TestCase):

    def test_shared_data_exists(self):
        self.assertTrue(
            exists("/tuscan_data/"))

    def test_top_level_exists(self):
        self.assertTrue(
            exists("/tuscan_data/get_base_package_names/"))

    def test_latest_exists(self):
        self.assertTrue(
            exists("/tuscan_data/get_base_package_names/latest/"))

    def test_names_file_exists(self):
        self.assertTrue(
            exists("/tuscan_data/get_base_package_names/latest/names.py"))

    def test_can_import_names(self):
        path.insert(0, "/tuscan_data/get_base_package_names/latest/")
        from names import base
        from names import base_devel

    def test_names_are_packages(self):
        path.insert(0, "/tuscan_data/get_base_package_names/latest/")
        from names import base
        from names import base_devel
        for pack in base:
            ret = run(["pacman", "--query", "--info", pack],
                      stdout=DEVNULL, universal_newlines=True)
            self.assertEqual([pack, ret.returncode],
                             [pack, 0])


if __name__ == "__main__":
    unittest.main()
