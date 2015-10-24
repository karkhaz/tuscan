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

"""Building Arch Linux from source as a ninja build file.

When run in an Arch Linux container, this script generates a ninja [1]
build file. Running that build file shall cause every official Arch
Linux package to be built from source in reverse-dependency order.

In Arch Linux, building from source is done using the Arch Build System
(ABS). This is a set of directories located under /var/abs; each such
directory contains exactly one Bash script called PKGBUILD. Each
PKGBUILD may build one or more packages. PKGBUILDs may specify zero or
more 'makedepends', which are those packages that must be installed
before attempting to build the packages of that PKGBUILD. In order to
build the packages specified by the PKGBUILD, one must cd into the
PKGBUILD's directory and run 'makepkg'.

This is summarized in this diagram, taken from the perspective of a
single PKGBUILD. Note that various PKGBUILDs in Arch might overlap in
the packages that they makedepend on, so building a single package might
satisfy several PKGBUILDs and allow those PKGBUILD's packages to be
built.

    packages  <------------
       ^                  |
       | 1-*              |
       |                  |
       | builds           |
       |                  |
       |               makedepends
    PKGBUILD            are just
       |              other packages
       |                  |
       | depends on       |
       |                  |
       | *                |
       v                  |
    makedepends  --------/

Thus, suppose that we have a PKGBUILD for the directory 'core/foo',
which builds the packages 'p1' and 'p2', and which makedepends on the
packages 'd1' and 'd2'. Conceptually, the ninja build commands that this
script shall generate are:
________________________________________________________________________
rule makepkg
    command = cd /var/abs/${in} && /usr/bin/makepkg

rule emptyrule
    command = /usr/bin/true

build p1.pkg.tar.xz: makepkg core/foo
build p2.pkg.tar.xz: makepkg core/foo

build core/foo: emptyrule  d1.pkg.tar.xz  d2.pkg.tar.xz
________________________________________________________________________
...plus the build commands for d{1,2}.pkg.tar.xz, etc. Note that the
actual output will be slightly different, in order to ensure that
packages are not rebuilt unnecessarily.

[1] http://martine.github.io/ninja/
"""

from utilities import OutputDirectory, setup_argparse

from glob import glob
from multiprocessing import Value, Lock, Pool, cpu_count, Manager
from ninja_syntax import Writer
from os.path import exists
from re import sub
from subprocess import PIPE, Popen, TimeoutExpired, run
from sys import argv, path, stderr, stdout
from tempfile import NamedTemporaryFile as tempfile
from textwrap import dedent

args = setup_argparse()

# We need to import a list of base package names
package_names_dir = (args.shared_directory +
                     "/get_base_package_names/latest")
if not exists(package_names_dir):
    print("Could not find dir for base pakage names at " +
          package_names_dir, file=stderr)
    print("Ensure that get_base_package_names container has run first.")
    exit(1)

path.insert(0, package_names_dir)
from names import base_package_names, base_devel_package_names


def excluded(pkgbuild):
    """Shall we not bother to make packages described by pkgbuild?"""
    return pkgbuild in [
        # Libreoffice internationalisation packs call curl from their
        # buildfile, and they are not required by anything. Skip them
        # for all operations
        "/var/abs/extra/libreoffice-fresh-i18n/PKGBUILD",
        "/var/abs/extra/libreoffice-still-i18n/PKGBUILD",
    ]


def pkgnames_of(pkgbuild):
    """The pkgnames defined by a PKGBUILD file

    A single PKGBUILD may build one or more binary packages when makepkg
    is invoked. This function returns the names of the packages that the
    specified PKGBUILD builds.

    Arguments:
        pkgbuild: an absolute path to a PKGBUILD

    Returns:
        a list of names of packages, or None if we should not build
        packages from this PKGBUILD
    """

    if excluded(pkgbuild): return None

    cmd = dedent("""\
                 #!/bin/bash
                 . %s
                 for pack in ${pkgname[@]}; do
                    echo ${pack};
                 done;
                 """ % (pkgbuild))
    with tempfile(mode="w") as temp:
        temp.write(cmd)
        temp.flush()
        proc = Popen(["/bin/bash", temp.name], stdout=PIPE)
        try:
            proc.wait(5)
        except TimeoutExpired:
            print(pkgbuild + " took too long to source",
                  file=stderr)
            exit(1)
        names = [p.decode().strip() for p in list(proc.stdout)
                 if p.decode().strip()]
        if len(names) == 0:
            print(pkgbuild + " has no pkgname",
                  file=stderr)
            exit(1)

        names = [n for n in names]

        for n in names:
            if(n in base_package_names
            or n in base_devel_package_names):
                return None

        return names


def makedepends_of(pkgbuild):
    """The makedepends defined by a PKGBUILD file

    A single PKGBUILD may contain a makedepends array, which indicates
    what packages must be installed in order to build the PKGBUILD. Note
    that even if a PKGBUILD builds multiple packages, the globally-
    defined makedepends array applies to ALL those packages (see [1] or
    search the PKGBUILD manpage for 'Package Splitting').

    Note that all packages are assumed to require all packages from the
    base-devel group [2] in order to be built using makepkg, as noted in
    this wiki page [3]. Therefore this function shall contain at least
    those packages. Furthermore, all Arch Linux systems are expected to
    contain all packages from the base group, so those packages shall
    also be returned.

    [1]: archlinux.org/pacman/PKGBUILD.5.html#_package_splitting
    [2]: archlinux.org/groups/x86_64/base-devel/
    [3]: wiki.archlinux.org/index.php/PKGBUILD#makedepends

    Arguments:
        pkgbuild: an absolute path to a PKGBUILD

    Returns:
        a list of packages that must be installed in order to build that
        PKGBUILD, including (at least) all packages in the base and
        base-devel groups. Or, None if we should not create any packages
        from this PKGBUILD.
    """

    if excluded(pkgbuild): return None

    cmd = dedent("""\
                 #!/bin/bash
                 . %s
                 for dep in ${makedepends[@]}; do
                    echo ${dep};
                 done;
                 """ % (pkgbuild))
    with tempfile(mode="w") as temp:
        temp.write(cmd)
        temp.flush()
        proc = Popen(["/bin/bash", temp.name], stdout=PIPE)
        try:
            proc.wait(5)
        except TimeoutExpired:
            print(pkgbuild + " took too long to source",
                  file=stderr)
            exit(1)

        depends = [p.decode().strip() for p in list(proc.stdout)
                   if p.decode().strip()]

        depends += base_package_names
        depends += base_devel_package_names

        depends = ["binaries/" + d + ".pkg.tar.xz" for d in depends]

        return depends


def print_statistics(out_dir):
    with open(out_dir + "/stats.dat", "w") as dat:
        for n_deps, freq in dependency_frequencies.items():
            print(str(freq) + " " + str(n_deps), file=dat)
            dat.flush()


def ninja_builds_for(abs_dir):
    """Outputs ninja build rules for the packages built from abs_dir.

    Arguments:
        abs_dir: Path to an ABS build directory (e.g.
        "/var/abs/core/glibc").
    """
    pkgbuild = abs_dir + "/PKGBUILD"
    target_packages = pkgnames_of(pkgbuild)
    if not target_packages: return

    target_packages = ["binaries/" + n + ".pkg.tar.xz"
                       for n in target_packages]

    depends = makedepends_of(pkgbuild)

    build_name = sub("/var/abs/\w+/", "", abs_dir)
    build_name = sub("/", "@", build_name)

    if build_name in depends: depends.remove(build_name)

    with lock:
        ninja.build(target_packages, "makepkg", build_name)
        ninja.build(build_name, "phony", depends)
        ninja.output.flush()

        n_deps = len(depends)
        if not n_deps in dependency_frequencies:
            dependency_frequencies[n_deps] = 0
        dependency_frequencies[n_deps] += len(target_packages)

        number_of_packages.value += len(target_packages)
        counter.value += 1
        print("\r" + str(counter.value) + "/" + builds_len +
              ", " + str(number_of_packages.value) +
              " packages found.", file=stderr, end="")


def main():
    """This script should be run inside a container."""
    global builds_len, ninja, dependency_frequencies

    dependency_frequencies = Manager().dict()

    with OutputDirectory(args, __file__) as out_dir:
        if args.verbose:
            print("Output shall be written in " + out_dir,
                  file=stderr)

        with open(out_dir + "/build.ninja", "w") as log:
            ninja = Writer(log, 72)

            ninja.rule("makepkg", "cd /var/abs/${in} && makepkg")
            ninja.rule("phony", "# phony ${out}")

            log.flush()

            builds = glob("/var/abs/*/*")
            builds = [b for b in builds if not excluded(b)]
            builds_len = str(len(builds))

            with Pool(cpu_count()) as p:
                p.map(ninja_builds_for, builds)
            print("", file=stderr)

        if args.statistics:
            print_statistics()


# Globals, referenced from spawned processes. Remember to initialize
# these things in main!
counter = Value("i", 0)
number_of_packages = Value("i", 0)
lock = Lock()
builds_len = ""
ninja = None
dependency_frequencies = None

if __name__ == "__main__":
    main()
