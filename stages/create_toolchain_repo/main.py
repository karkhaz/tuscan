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


from utilities import add_package_to_toolchain_repo
from utilities import get_argparser, create_package, log

import os
import os.path
import textwrap


def main():
    """Create empty local toolchain repository.

    Only one instance of this stage should be run, and it should run
    before any instances of the make_package stage run. We don't want to
    be creating the local repository several times concurrently.
    """
    parser = get_argparser()
    args = parser.parse_args()

    # We can't create an empty database. We need to add a fake package
    # to a new database, then remove it again.

    path = "/tmp/dummy_pack"
    pkg_name = "dummy-pack"

    os.makedirs(path, exist_ok=True)
    pkg_info = (textwrap.dedent("""\
          # Generated by makepkg 4.1.2
          # using fakeroot version 1.20
          # Mon 20 Oct 21 14:19:27 UTC 2013
          pkgname = %s
          pkgver = 1.0.0-0
          url = abc.xyz
          builddate 1382364167
          packager = bog
          size = 1000000
          arch = any
          """) % (pkg_name))

    log("info", "Writing fake package .PKGINFO:",
        pkg_info.splitlines())

    with open(os.path.join(path, ".PKGINFO"), "w") as f:
        print(pkg_info, file=f)

    log("info", "Building fake package")
    pkg = create_package(path, pkg_name, args)
    log("info", "Initializing toolchain repo")
    add_package_to_toolchain_repo(pkg, args.toolchain_directory,
                                  remove_name=pkg_name)


if __name__ == "__main__":
    main()
