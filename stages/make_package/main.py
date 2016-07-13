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


from utilities import get_argparser, log, create_package, timestamp
from utilities import recursive_chown, set_local_repository_location
from utilities import strip_version_info, interpret_bash_array
from utilities import toolchain_repo_name, add_package_to_toolchain_repo
from utilities import Status, die

import codecs
import datetime
import fnmatch
from  glob import glob
import json
import os
import os.path
import re
import shutil
import subprocess
import tarfile


def log_sloc(sloc_output):
    """Parse output of the SLOCCount tool and log relevant information"""
    locs = {}
    parsing_locs = False
    for line in sloc_output:
        if re.match("Totals grouped by language", line):
            parsing_locs = True
        elif parsing_locs and re.match("^$", line):
            parsing_locs = False
        elif parsing_locs:
            m = re.match("(?P<lang>.+):\s+(?P<loc>\d+)", line)
            if m:
                locs[m.group("lang")] = int(m.group("loc"))
            else:
                log("die", "didn't match LOC line '%s'" % line)
    log("sloc_info", "sloc_info", json.dumps(locs))


def copy_and_build(args):
    try:
        shutil.copytree(args.permanent_source_dir, args.build_dir)
    except shutil.Error as e:
        # e.args will be a list, containing a single list of 3-tuples.
        # We are interested in the third item of each tuple.
        errors = [err[2] for err in e.args[0]]
        die(Status.failure, "No source directory in source volume: %s" %
                args.permanent_source_dir, output=errors)
    recursive_chown(args.build_dir)
    os.chdir(args.build_dir)

    proc = subprocess.Popen(["/usr/bin/sloccount", "src"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out, _ = proc.communicate()
    output = codecs.decode(out, errors="replace")
    if proc.returncode:
        log("die", "SLOCCount failed", output.splitlines())
    else:
        log_sloc(output.splitlines())

    # Add the --host option to invocations of ./configure
    with open("PKGBUILD", encoding="utf-8") as f:
        pkgbuild = f.read().splitlines()

    pkgbuild = [re.sub(r"configure\s",
                    "configure --host x86_64-unknown-linux ",
                    line) for line in pkgbuild]

    with open("PKGBUILD", "w", encoding="utf-8") as f:
        f.write("\n".join(pkgbuild))

    # This invocation of makepkg has the --noextract flag, because
    # sources should already have been extracted during the creation of
    # the base image (see stages/create_base_image/getpkgs.py). We still
    # need to perform all other stages of package building, including
    # the prepare() function that is called just before the build()
    # function.
    #
    # The invocation also has the --syncdeps flag; this is fine, because
    # anything that this package depends on should already have been
    # built and its hybrid package will have been installed.
    if args.env_vars == None:
        args.env_vars = []

    command_env = os.environ.copy()
    for pair in args.env_vars:
        var, val = pair.split("=")
        command_env[var] = val

    command = (
       "sudo -u tuscan " +
       " ".join(args.env_vars) +
       " bear makepkg --noextract --syncdeps"
       " --skipinteg --skippgpcheck --skipchecksums"
       " --noconfirm --nocolor --log --noprogressbar"
       " --nocheck"
    )
    time = timestamp()

    proc = subprocess.Popen(command.split(), stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, env=command_env)

    stdout_data, _ = proc.communicate()
    output = codecs.decode(stdout_data, errors="replace")

    log("command", command, output.splitlines(), time)

    # Pick up output left by bear
    if os.path.exists("compile_commands.json"):
        with open("compile_commands.json") as f:
            bear_output = json.load(f)
        log("bear", "bear", output=bear_output)
    else:
        log("die", "No bear output found in dir '%s'" % os.getcwd())

    native_tools = {}
    for native in glob("/tmp/tuscan-native-*"):
        with open(native) as f:
            tool = f.readlines()
        if tool:
            tool = tool[0].strip()
        if tool not in native_tools:
            native_tools[tool] = 0
        native_tools[tool] += 1
    if native_tools:
        log("native_tools", "native_tools", native_tools)

    return proc.returncode


def path_to_vanilla_pkg(pkg_name, args):
    """Returns the path to a vanilla package in the local mirror.

    This method tries to find a package with name exactly matching
    'pkg_name' in one of the repositories in the local mirror. It aborts
    the stage if such a package isn't found.
    """
    log("info", "Trying to find vanilla package '%s'..." % pkg_name)
    for root, dirs, files in os.walk(args.mirror_directory):
        for f in files:

            if re.search("i686", f): continue
            if not re.search(".pkg.tar.xz$", f): continue

            if re.search(re.escape(pkg_name), f):
                path = os.path.join(root, f)
                cmd = "pacman --query --file " + path
                cp = subprocess.run(cmd.split(), stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        universal_newlines=True)
                log("command", cmd, cp.stdout.splitlines())
                if cp.returncode:
                    exit(1)
                candidate_name = cp.stdout.splitlines()[0].split()[0]
                if pkg_name == candidate_name:
                    return path
    die(Status.failure, "No matching packages found.")


def create_hybrid_packages(args):
    os.chdir(args.build_dir)

    toolchain_packages = glob("*.pkg.tar.xz")
    if not toolchain_packages:
        die(Status.failure, "No built packages found in %s" %
                            args.build_dir)

    hybrid_package_paths = []
    hybrid_packages_dir = "/tmp/hybrid_packages"

    dir_toolchain = "/tmp/toolchain"
    dir_vanilla = "/tmp/vanilla"
    dir_hybrid = "/tmp/hybrid"

    for pkg in toolchain_packages:
        for d in [dir_toolchain, dir_vanilla, dir_hybrid]:
            shutil.rmtree(d, ignore_errors=True)
            os.makedirs(d)

        cmd = "pacman --query --file " + pkg
        cp = subprocess.run(cmd.split(), stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, universal_newlines=True)
        log("command", cmd, cp.stdout.splitlines())
        if cp.returncode:
            exit(1)
        pkg_name = cp.stdout.splitlines()[0].split()[0]
        log("info", "Creating hybrid package for '%s'" % pkg_name)

        vanilla_pkg = path_to_vanilla_pkg(pkg_name, args)

        with tarfile.open(pkg) as t:
            t.extractall(dir_toolchain)
        with tarfile.open(vanilla_pkg) as t:
            t.extractall(dir_vanilla)

        # Copy various directories from dir_toolchain and dir_vanilla
        # into dir_hybrid, and then tar dir_hybrid up.
        #
        # Every top-level directory should be recursively copied from
        # dir_vanilla into the top-level of dir_hybrid.
        #
        # Additionally, /usr/{lib,include} should be copied into
        # dir_hybrid/toolchain/usr/{lib,include}.
        #
        # Note that in Arch Linux, many of the traditional Unix
        # directories that contain (binaries,libraries) are symlinked to
        # (/usr/bin,/usr/lib). see
        # https://wiki.archlinux.org/index.php/Arch_filesystem_hierarchy
        #
        # There are some additional files in Arch packages, as noted in
        #
        # https://wiki.archlinux.org/index.php/Creating_packages
        #
        # .PKGINFO: This should be the same for vanilla and toolchain,
        #           so just copy from vanilla
        # .INSTALL: Not sure if the instructions in this file will
        #           always be portable across toolchains, but just copy
        #           from vanilla and treat failures at INSTALL stage as
        #           edge cases.
        # .MTREE:   This one is evil, it's a binary file containing
        #           hashes that are used to verify integrity. We need to
        #           build our own one; this is handled by the
        #           create_package method in utilities.


        for d in os.listdir(dir_vanilla):
            src = os.path.join(dir_vanilla, d)
            dst = os.path.join(dir_hybrid, d)
            try:
                shutil.copytree(src, dst, symlinks=True)
            except NotADirectoryError:
                # This will be .INSTALL, .MTREE or .PKGINFO, noted above
                shutil.copyfile(src, dst)

        for d in ["usr/lib", "usr/include"]:
            src = os.path.join(dir_toolchain, d)
            dst = os.path.join(dir_hybrid, "toolchain_root", d)
            try:
                shutil.copytree(src, dst, symlinks=True)
            except FileNotFoundError:
                pass


        structure = []
        for root, dirs, files in os.walk(dir_hybrid):
            for f in files:
                path = re.sub(dir_hybrid, "", os.path.join(root, f))
                structure.append(path)
        log("info", "Package file has the following structure:",
            structure)

        pkg_path = create_package(dir_hybrid, pkg_name, args)
        hybrid_package_paths.append(pkg_path)

    return hybrid_package_paths


def dump_build_information(args):
    """Log the packages provided & depended on by this build

    This function logs all packages that will be built if this build
    succeeds. This includes 'virtual' packages, i.e. packages like 'sh'
    that don't really exist but are provided by 'bash'.

    This is so that if this build fails, any build that depends on a
    package provided by this build knows who to blame when it can't
    install its dependencies.

    This function also logs what packages are depended on by this build.
    """
    pkgbuild = os.path.join(args.abs_dir, "PKGBUILD")
    provides = []
    provides += [strip_version_info(name)
        for name in interpret_bash_array(pkgbuild, "pkgname")]
    provides += [strip_version_info(name)
        for name in interpret_bash_array(pkgbuild, "provides")]

    log("provide_info", None, output=provides)

    depends = []
    depends += [strip_version_info(name)
        for name in interpret_bash_array(pkgbuild, "depends")]
    depends += [strip_version_info(name)
        for name in interpret_bash_array(pkgbuild, "makedepends")]

    log("dep_info", "This build depends on the following packages",
            output=depends)


def main():
    parser = get_argparser()
    parser.add_argument("--abs-dir", dest="abs_dir", required=True)
    args = parser.parse_args()
    args.mirror_directory = "/mirror"

    dump_build_information(args)

    pkg_dir = os.path.basename(args.abs_dir)

    if pkg_dir in os.listdir(args.sources_directory):
        args.permanent_source_dir = os.path.join(
                args.sources_directory, pkg_dir)
    else:
        die(Status.failure, "No source directory in source volume: %s" %
                args.sources_directory)

    args.build_dir = os.path.join("/tmp", pkg_dir)

    set_local_repository_location(args.toolchain_directory,
            toolchain_repo_name())

    result = copy_and_build(args)
    if result:
        die(Status.failure)

    paths_to_packages = create_hybrid_packages(args)

    if not paths_to_packages:
        die(Status.failure, "No hybrid packages were created.")

    for path in paths_to_packages:
        add_package_to_toolchain_repo(path, args.toolchain_directory)

    die(Status.success)


if __name__ == "__main__":
    main()
