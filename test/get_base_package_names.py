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

from unittest.runner import TextTestResult
TextTestResult.getDescription = lambda _, test: test.shortDescription()

class TestGetBasePackageNames(unittest.TestCase):

    def shortDescription(self):
        return self._testMethodDoc

    def test_shared_data_exists(self):
        """Something is horribly wrong---the directory for shared data
        does not exist."""
        self.assertTrue(
            exists("/tuscan_data/"))

    def test_top_level_exists(self):
        """The get_base_package_names container did not create a
        'get_base_package_names' results directory."""
        self.assertTrue(
            exists("/tuscan_data/get_base_package_names/"))

    def test_latest_exists(self):
        """The get_base_package_names container did not create a
        'latest' results directory"""
        self.assertTrue(
            exists("/tuscan_data/get_base_package_names/latest/"))

    def test_names_file_exists(self):
        """The get_base_package_names container did not create a
        file containing base package names"""
        self.assertTrue(
            exists("/tuscan_data/get_base_package_names/latest/names.py"))

    def test_can_import_names(self):
        """It was not possible to import base package names from the
        expected location."""
        path.insert(0, "/tuscan_data/get_base_package_names/latest/")
        from names import base_package_names
        from names import base_devel_package_names

    def test_names_are_packages(self):
        """Each of the package names written by get_base_package_names
        should indeed be the name of a package."""
        path.insert(0, "/tuscan_data/get_base_package_names/latest/")
        from names import base_package_names
        from names import base_devel_package_names
        for pack in base_package_names + base_devel_package_names:
            ret = run(["pacman", "--query", "--info", pack],
                      stdout=DEVNULL, universal_newlines=True)
            self.assertEqual([pack, ret.returncode],
                             [pack, 0])
        for pack in base_devel_package_names:
            ret = run(["pacman", "--query", "--info", pack],
                      stdout=DEVNULL, universal_newlines=True)
            self.assertEqual([pack, ret.returncode],
                             [pack, 0])


    def test_correct_number_of_base_packages(self):
        """There should be 52 packages in base."""
        path.insert(0, "/tuscan_data/get_base_package_names/latest/")
        from names import base_package_names
        self.assertEqual(len(base_package_names), 52)

    def test_correct_number_of_base_packages(self):
        """There should be 25 packages in base-devel."""
        path.insert(0, "/tuscan_data/get_base_package_names/latest/")
        from names import base_devel_package_names
        self.assertEqual(len(base_devel_package_names), 25)


if __name__ == "__main__":
    unittest.main()
