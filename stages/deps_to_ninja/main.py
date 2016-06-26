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
from utilities import strip_version_info, interpret_bash_array

import datetime
import functools
import glob
import json
import multiprocessing
import ninja_syntax
import os.path
import random
import re
import subprocess
import sys
import tempfile
import textwrap


def excluded(info):
    """Shall we not bother to make packages in package info `info'?"""
    return info["pkgbuild"] in [
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
        "/var/abs/community/wine-mono/PKGBUILD",
        "/var/abs/community/winetricks/PKGBUILD",

        # This depends on a virtual package that needs to be installed
        # manually (synce-librapi)
        "/var/abs/community/synce-mcfs/PKGBUILD",

        # The go compiler conflicts with gcc.
        "/var/abs/community/go/PKGBUILD",

        # More trouble than they are worth.
        "/var/abs/extra/mesa-libgl/PKGBUILD",
        "/var/abs/extra/java8-openjdk/PKGBUILD",
        "/var/abs/extra/java7-openjdk/PKGBUILD",
        "/var/abs/extra/libx11/PKGBUILD",
        "/var/abs/extra/libreoffice-fresh/PKGBUILD",
        "/var/abs/extra/libreoffice-still/PKGBUILD",

    ] or (
        # Packages that are in a group are likely to be graphical
        # applications, and are more trouble than they are worth. See
        # https://www.archlinux.org/groups/
        not set(info["groups"]).issubset([
                "base", "base-devel", "texlive-most", "dlang",
                "linux-tools", "texlive-lang"
            ])
    )


def groups_of(pkgbuild):
    """The groups that a pkgbuild file is part of."""

    cmd = textwrap.dedent("""\
                 #!/bin/bash
                 . %s
                 for grp in ${groups[@]}; do
                    echo ${grp};
                 done;
                 """ % (pkgbuild))
    with tempfile.NamedTemporaryFile(mode="w") as temp:
        temp.write(cmd)
        temp.flush()
        proc = subprocess.Popen(["/bin/bash", temp.name], stdout=subprocess.PIPE)
        try:
            proc.wait(40)
        except subprocess.TimeoutExpired:
            print("%s took too long to source" % pkgbuild,
                  file=sys.stderr)
            exit(1)

        return [p.decode().strip() for p in list(proc.stdout)
                if p.decode().strip()]


def build_triples(infos, args):
    """Return a list of build rules as triples

    Given a list of package infos, return a list of build triples.

    Suppose that we have the following package info:
    {
        "pkgbuild": "/var/abs/core/fubar",
        "package_names": ["foo", "bar"]
        "makedepends": ["baz"]
        "depends": ["qux"]
    }
    Then we generate two build rules:

    build foo.json bar.json: makepkg /var/abs/core/fubar

    build /var/abs/core/fubar: phony baz.json qux.json

    Thus, - Any package that depends either on foo or on bar being
            built, will not be built until makepkg has run on the fubar
            directory
          - makepkg will not be attempted on the directory fubar until
            all dependencies of fubar have been built.

    The form of each returned triple shall be (outputs, rule, inputs),
    suitable for passing to ninja.build().
    """
    triples = []
    prefix = os.path.join(args.output_directory, "pkgbuild_markers", "")

    for info in infos:
        # Individual packages depend on makepkg being run on the ABS
        outs = [os.path.join(prefix, name + ".json")
                for name in info["package_names"]]
        ins  = [os.path.dirname(info["pkgbuild"])]
        triples.append((outs, "makepkg", ins))

        # makepkg on the abs depends on dependencies
        outs = [os.path.dirname(info["pkgbuild"])]
        ins = [os.path.join(prefix, dep + ".json")
                for dep in info["depends"] + info["makedepends"]]
        triples.append((outs, "phony", ins))

    return triples


def gather_package_data(abs_dir,
        name_data, args, global_infos, provides):

    # These PKGBUILDs take forever to source, due to their use of wget.
    if (re.search("libreoffice-fresh-i18n", abs_dir)
    or  re.search("libreoffice-still-i18n", abs_dir)):
        return

    info = {}
    pkgbuild = os.path.join(abs_dir, "PKGBUILD")

    info["pkgbuild"] = pkgbuild
    info["groups"] = interpret_bash_array(pkgbuild, "groups")

    info["package_names"] = [strip_version_info(name)
     for name in interpret_bash_array(pkgbuild, "pkgname")]

    info["depends"] = [strip_version_info(name)
     for name in interpret_bash_array(pkgbuild, "depends")]

    info["makedepends"] = [strip_version_info(name)
     for name in interpret_bash_array(pkgbuild, "makedepends")]

    info["provides"] = [strip_version_info(name)
     for name in interpret_bash_array(pkgbuild, "provides")]

    global_infos.append(info)


def resolve_provides(package_infos, provides_dict):
    """Change metapackage names into packages that provide them.

    In Arch Linux, some packages are `metapackages' that are `provided'
    by concrete packages. E.g., the package `sh' is provided by `bash'.
    However, some things may depend on metapackages like sh, which we do
    not know how to install. Therefore we must transform all instances
    of sh into bash.

    This method takes a list of package_infos gotten from
    gather_package_data() on all ABS directories. For each dict in the
    list, this method modifies the packages in the "depends" and
    "makedepends" lists such that they do not contain any metapackages.

    The resolution is done in two ways. Firstly, if the name of a
    metapackage is a key in provides_dict, then it will be converted to
    the value in provides_dict. Otherwise, if the name of a metapackage
    was found in the 'provides' list of some other package_info, then
    the metapackage name will be converted to the package name of that
    package info.
    """
    # First, build a map metapackage_name -> providing package.
    provider_of = {}
    errors = []
    for info in package_infos:
        if info["provides"]:
            if len(info["package_names"]) > 1:
                for meta in info["provides"]:
                    if meta in provides_dict:
                        provider_of[meta] = provides_dict[meta]
                    else:
                        errors.append(info["pkgbuild"])
            else:
                for meta in info["provides"]:
                    provider_of[meta] = info["package_names"][0]
    if errors:
        print("Could not decide what packages provide some meta-"
              "packages.", file=sys.stderr)
        for error in errors:
            print(error, file=sys.stderr)
        exit(1)

    # Now, go through each package info and do the transformation on its
    # lists.
    for info in package_infos:
        for field in ["depends", "makedepends"]:
            tmp = []
            for pkg in info[field]:
                if pkg in provides_dict:
                    tmp.append(provides_dict[pkg])
                elif pkg in provider_of:
                    tmp.append(provider_of[pkg])
                else:
                    tmp.append(pkg)
            info[field] = tmp


def drop_excluded(infos, circulars, name_data):
    """Remove infos for packages that we don't want to build.

    There are a bunch of packages that we don't want to build for
    various reasons. This method removes them and anything that depends
    on them from infos.
    """
    excluded_infos = [info for info in infos
                      if excluded(info) or info in circulars]

    excluded_packages = set()
    for info in excluded_infos:
        excluded_packages.update(info["package_names"])
        infos.remove(info)

    # Iterate until fixpoint is reached.
    reiterate = True
    while reiterate:
        reiterate = False
        tmp = []
        for info in infos:
            blockers = []
            for lst in ["depends", "makedepends"]:
                for pkg in info[lst]:

                    if (pkg in excluded_packages

                    and not set(info["groups"]).intersection(
                            ["base", "base-devel"])

                    and not set(info["package_names"]).intersection(
                        name_data["tools"])):

                        reiterate = True
                        excluded_packages.update(info["package_names"])
                        blockers.append(pkg)

            if not blockers:
                tmp.append(info)
        infos = tmp

    return infos


def drop_tools(infos, name_data):
    """Remove build rules for 'tools'.

    We don't want to build things defined in get_base_package_names as
    'tools'. These are packages which we think don't provide any shared
    libraries, but rather are only ever run. Since building these things
    is fraught with difficulty, and many packages have makedependencies
    on tools (but not _link_ make dependencies), we should just install
    the vanilla package of them and not bother building toolchain
    versions.

    Note that we have to run this method _after_ the drop_excluded
    method, since drop_excluded needs to know about tools.
    """
    return [info for info in infos
            if not set(info["package_names"]).
            intersection(name_data["tools"]
                       + name_data["base"]
                       + name_data["base_devel"])
           ]


def depends_on_cycle(info, package_map, no_cycles, in_a_cycle, seen,
        name_data):
    """Classify info and all its deps as being or not being in a cycle.

    Arguments:
        info:
            an info to start exploring from
        package_map:
            a dict mapping package names to the info containing them,
            i.e. for every name in package_map, this holds:
            name in package_map[name]["package_name"]
        no_cycles:
            a set of infos known to not be involved in any cycles
        in_a_cycle:
            a set of infos known to involved in some cycle

    Returns:
        Whether this info was involved in a cycle. Also mutates
        no_cycles and in_a_cycle
    """
    for pkg in info["package_names"]:
        if pkg in (name_data["tools"] + name_data["base"] +
                   name_data["base_devel"]):
            return False

    if info in no_cycles: return False
    if info in in_a_cycle: return True

    if info in seen: # Cycle detected!
        in_a_cycle.append(info)
        return True

    dep_involved_in_cycle = False
    for dep in info["depends"] + info["makedepends"]:
        try:
            dep_info = package_map[dep]
        except KeyError:
            continue
        if depends_on_cycle(dep_info, package_map, no_cycles,
                            in_a_cycle, seen + [info], name_data):
            dep_involved_in_cycle = True
    if dep_involved_in_cycle:
        in_a_cycle.append(info)
        return True
    else:
        no_cycles.append(info)
        return False


def infos_with_circular_deps(infos, name_data):
    """Returns all infos that are in a circular dependency chain."""
    no_cycles = []
    in_a_cycle = []

    # dict: package name --> info that contains it
    package_map = {}
    for info in infos:
        for package in info["package_names"]:
            package_map[package] = info

    for info in infos:
        depends_on_cycle(info, package_map, no_cycles, in_a_cycle, [],
                         name_data)

    return in_a_cycle


def main():
    """This script should be run inside a container."""

    parser = get_argparser()
    args = parser.parse_args()

    name_data_file = os.path.join(args.shared_directory,
            "get_base_package_names", "latest", "names.json")
    with open(name_data_file) as f:
        name_data = json.load(f)

    with open("/build/provides.json") as f:
        provides = json.load(f)

    abss = glob.glob("/var/abs/*/*")

    # Build a list of package information. This involves interpreting
    # Bash files, so split across multiple processes for speed.
    man = multiprocessing.Manager()
    global_infos = man.list()

    curry_gather = functools.partial(gather_package_data,
            name_data=name_data, args=args, global_infos=global_infos,
            provides=provides)

    with multiprocessing.Pool(multiprocessing.cpu_count()) as p:
        p.map(curry_gather, abss)

    # Back to sequential mode. Do various cleanups on the list of
    # package information

    infos = [info for info in global_infos]
    resolve_provides(infos, provides)
    circulars = infos_with_circular_deps(infos, name_data)
    infos = drop_excluded(infos, circulars, name_data)

    infos = drop_tools(infos, name_data)

    # Finally, get a list of builds and write them out.
    builds = build_triples(infos, args)

    ninja  = ninja_syntax.Writer(sys.stdout, 72)

    ninja.rule("makepkg",
               ("container_build_dir/package_build_wrapper.py"
               " --shared-directory {shared_directory}"
               " --shared-volume {shared_volume}"
               " --sources-directory {sources_directory}"
               " --sources-volume {sources_volume}"
               " --toolchain-directory {toolchain_directory}"
               " --toolchain-volume {toolchain_volume}"
               " --toolchain {toolchain}"
               " --output-directory {output_directory}"
               # ${in} and ${out} are NOT format strings, they need to
               # be written out like this to the ninja file. So (python)
               # escape by using double-curly brackets
               " --abs-dir ${{in}}"
               " ${{out}}"
    ).format(shared_directory=args.shared_directory,
             shared_volume=args.shared_volume,
             sources_directory=args.sources_directory,
             sources_volume=args.sources_volume,
             output_directory=args.output_directory,
             toolchain_directory=args.toolchain_directory,
             toolchain_volume=args.toolchain_volume,
             toolchain=args.toolchain))

    for outs, rule, ins in builds:
        ninja.build(outs, rule, ins)

    sys.stdout.flush()


if __name__ == "__main__":
    main()
