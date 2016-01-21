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
"""Common utilities.

These utilities are common to all main scripts that run inside
containers.

All such scripts are expected to call setup_argparse() at the beginning
of their main() method, since the command-line switches defined in that
function might be passed by the build environment.
"""

from argparse import ArgumentParser
from os.path import basename, splitext, lexists, join
from os import makedirs, remove, symlink
from datetime import datetime
from sys import stderr

class OutputDirectory():
    """Instantiated using the 'with' statement.

    This class is used to wrap the directory that a container script can
    write to inside a container. Calling it as follows:

    with OutputDirectory(args) as out_dir:
          ...

    means that container scripts do not have to worry about what
    directory they are supposed to be writing to. This class takes care
    of generating a unique output directory path, as well as updating a
    symlink to point to the latest result when the script container has
    finished executing.
    """
    def __init__(self, args, filename):
        """Arguments:
            args: an argparse object returned from a call to
                  setup_argparser(). This object must have an attribute
                  called 'shared_directory'.
        """
        top_level = splitext(basename(filename))[0]
        self.top_level = join(args.shared_directory, top_level)

        timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        self.path = join(self.top_level, timestamp)

    def __enter__(self):
        makedirs(self.path, exist_ok=True)
        return self.path

    def __exit__(self, type, value, traceback):
        latest = join(self.top_level, "latest")
        if lexists(latest):
            remove(latest)
        symlink(self.path, latest)


def get_argparser():
    """Set up command line options.

    Returns:
        an ArgumentParser, to which arguments can be appended before
        calling parse_args() to process them.
    """
    parser = ArgumentParser()
    parser.add_argument("--verbose",
                        dest="verbose", action="store_true")
    parser.add_argument("--output-directory",
                        dest="output_directory", action="store")

    parser.add_argument("--shared-directory",
                        dest="shared_directory", action="store")
    parser.add_argument("--shared-volume",
                        dest="shared_volume", action="store")

    parser.add_argument("--sources-directory",
                        dest="sources_directory", action="store")
    parser.add_argument("--sources-volume",
                        dest="sources_volume", action="store")

    parser.add_argument("--pkg-cache-directory",
                        dest="pkg_cache_directory", action="store")
    parser.add_argument("--pkg-cache-volume",
                        dest="pkg_cache_volume", action="store")

    parser.add_argument("--toolchain",
                        dest="toolchain", action="store")

    parser.add_argument("--env-vars", nargs="*",
                        dest="env_vars", action="store")

    return parser
