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

from utilities import OutputDirectory, get_argparser

from functools import partial
from glob import glob
from json import load
from multiprocessing import Value, Lock, Pool, cpu_count, Manager
from ninja_syntax import Writer
from os.path import exists, join
from random import shuffle
from re import search, sub
from subprocess import PIPE, Popen, TimeoutExpired, run
from sys import argv, path, stderr, stdout
from tempfile import NamedTemporaryFile as tempfile
from textwrap import dedent

def excluded(pkgbuild):
    """Shall we not bother to make packages described by pkgbuild?"""
    return pkgbuild in [
        # Libreoffice internationalisation packs call curl from their
        # buildfile, and they are not required by anything. Skip them
        # for all operations
        "/var/abs/extra/libreoffice-fresh-i18n/PKGBUILD",
        "/var/abs/extra/libreoffice-still-i18n/PKGBUILD",

        # virtualbox depends on some 32-bit libraries in multilib, we
        # don't want to get into that.
        "/var/abs/community/virtualbox/PKGBUILD",
        "/var/abs/community/virtualbox-host-dkms/PKGBUILD",
        "/var/abs/community/virtualbox-guest-iso/PKGBUILD",
        "/var/abs/community/virtualbox-modules/PKGBUILD",
        "/var/abs/community/virtualbox-modules-lts/PKGBUILD",
        # Same with lmms, it makedepends on wine.
        "/var/abs/community/lmms/PKGBUILD",
        "/var/abs/community/ogmrip/PKGBUILD",
    ]


def canonicalize_pkgname(pkgname, provides):
    """Transform pkgname to a standard form."""

    # Some packages specified as dependencies have a version number,
    # e.g. gcc>=5.1. We shouldn't care about this, we always sync to an
    # up-to-date mirror before building packages, so strip this info.
    for pat in [r">=", r"<=", r"=", r"<", r">"]:
        depth = search(pat, pkgname)
        if depth:
            pkgname = pkgname[:depth.start()]

    # Some packages 'provide' others, e.g. bash provides sh. Transform
    # sh into bash, since sh isn't a real package.
    if pkgname in provides:
        pkgname = provides[pkgname]

    return pkgname


def pkgnames_of(pkgbuild, name_data, provides):
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
            print("%s took too long to source" % pkgbuild,
                  file=stderr)
            exit(1)
        names = [p.decode().strip() for p in list(proc.stdout)
                 if p.decode().strip()]

        if len(names) == 0:
            print("%s has no pkgname" % pkgbuild,
                  file=stderr)
            exit(1)

        names = [n for n in names
                   if n not in name_data["base"]
                   and n not in name_data["base_devel"]
                   and n not in name_data["break_circular"]]
        names = [canonicalize_pkgname(n, provides) for n in names]
        return names


def makedepends_of(pkgbuild, name_data, provides):
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
            print("%s took too long to source" % pkgbuild,
                  file=stderr)
            exit(1)

        depends = [p.decode().strip() for p in list(proc.stdout)
                   if p.decode().strip()]

        depends += name_data["base"]
        depends += name_data["base_devel"]

        depends = [canonicalize_pkgname(d, provides) for d in depends]

        depends = [("%.json" % d) for d in depends]

        return depends


def ninja_builds_for(abs_dir, name_data, args,
                     global_builds, global_deps, provides):
    """Adds ninja build rules and dependency info to shared variables.

    Arguments:
        abs_dir: Path to an ABS build directory (e.g.
        "/var/abs/core/glibc").
    """
    pkgbuild = "%s/PKGBUILD" % abs_dir
    target_packages = pkgnames_of(pkgbuild, name_data, provides)
    if not target_packages: return

    target_packages = [("%s.json" % n) for n in target_packages]

    depends = makedepends_of(pkgbuild, name_data, provides)

    build_name = sub("/var/abs/\w+/", "", abs_dir)
    build_name = sub("/", "@", build_name)

    if build_name in depends: depends.remove(build_name)

    build(target_packages, "makepkg", build_name, args, global_builds)
    build(build_name, "phony", depends, args, global_builds)

    global_deps.append("%s %s" % (build_name, " ".join(depends)))


def build(outputs, rule, inputs, args, build_list):
    """Add a triple representing a ninja build to build_list.

    Assumes that build_list is a list that has been synchronised to be
    process-safe, somehow. This method appends a triple (o, r, i) to
    build_list, where the tuple represents the outputs, rule and inputs
    of a ninja build.
    """
    prefix = (join(args.output_directory, "pkgbuild_markers", ""))

    if isinstance(inputs, str):
        inputs = [inputs]
    if isinstance(outputs, str):
        outputs = [outputs]

    prefixed_inputs = [prefix + i for i in inputs]
    prefixed_outputs = [prefix + o for o in outputs]
    if rule == "makepkg":
        build_list.append((prefixed_outputs, rule, inputs))
    elif rule == "phony":
        build_list.append((outputs, rule, prefixed_inputs))
    else:
        raise("Impossible rule '%s'" % rule )


def main():
    """This script should be run inside a container."""

    parser = get_argparser()
    args = parser.parse_args()

    name_data_file = join(args.shared_directory,
            "get_base_package_names", "latest", "names.json")
    with open(name_data_file) as f:
        name_data = load(f)

    with open("/build/provides.json") as f:
        provides = load(f)

    builds = glob("/var/abs/*/*")
    builds = [b for b in builds if not excluded(b)]


    # Build a list of ninja builds across multiple processes for speed.
    man = Manager()
    global_builds = man.list()
    global_deps = man.list()

    ninja_curry = partial(ninja_builds_for, name_data=name_data,
                          args=args, global_builds=global_builds,
                          global_deps=global_deps, provides=provides)

    with Pool(cpu_count()) as p:
        p.map(ninja_curry, builds)

    ninja  = Writer(stdout, 72)

    ninja.rule("makepkg", (
               "./package_build_wrapper.py"
               " --shared-directory {shared_directory}"
               " --shared-volume {shared_volume}"
               " --sources-directory {sources_directory}"
               " --sources-volume {sources_volume}"
               " --pkg-cache-volume {pkg_cache_volume}"
               " --output-directory {output_directory}"
               # ${in} and ${out} are NOT format strings, they need
               # to be written out like this to the ninja file. So
               # escape by using double-curly brackets
               " --target-package ${{in}} ${{out}}"
               ).format(shared_directory=args.shared_directory,
                   shared_volume=args.shared_volume,
                   sources_directory=args.sources_directory,
                   sources_volume=args.sources_volume,
                   pkg_cache_volume=args.pkg_cache_volume,
                   output_directory=args.output_directory))

    for outs, rule, ins in global_builds:
        ninja.build(outs, rule, ins)

    stdout.flush()


if __name__ == "__main__":
    main()
