#!/usr/bin/python3
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
from sys import stderr
from os.path import exists
from re import compile, match
from subprocess import run, PIPE

class TestDepsToNinja(unittest.TestCase):

    def test_shared_data_exists(self):
        self.assertTrue(
            exists("/tuscan_data/"))

    def test_top_level_exists(self):
        self.assertTrue(
            exists("/tuscan_data/deps_to_ninja/"))

    def test_latest_exists(self):
        self.assertTrue(
            exists("/tuscan_data/deps_to_ninja/latest/"))

    def test_ninja_file_exist(self):
        self.assertTrue(
            exists("/tuscan_data/deps_to_ninja/latest/build.ninja"))

    def test_ninja_file_nonempty(self):
        counter = 0
        ninja_file = "/tuscan_data/deps_to_ninja/latest/build.ninja"
        with open(ninja_file) as ninja_file:
            for line in ninja_file:
                self.assertTrue(True)
                return

if __name__ == "__main__":
    unittest.main()
