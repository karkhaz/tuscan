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
from utilities import toolchain_repo_name, add_package_to_toolchain_repo

from datetime import datetime
from glob import glob
from fnmatch import filter
from json import load
from os import chdir, listdir, walk, makedirs, environ
from os.path import basename, isdir, isfile, join
from re import escape, search, sub
from shutil import chown, copyfile, copytree, rmtree
from subprocess import run, Popen, PIPE, STDOUT
from sys import stderr
from tarfile import open as tar_open


def die(error_code):
    log("info", "Printing config.logs")
    config_logs = []
    for root, dirs, files in walk("/tmp"):
        for f in files:
            if f == "config.log" or f == "configure.log":
                config_logs.append(join(root, f))

    for l in config_logs:
        lines = []
        with open(l, encoding="utf-8") as f:
            for line in f:
                lines.append(line.strip())
            log("command", "Config logfile '%s'" % l, lines)

    exit(error_code)


def recursive_chown(directory):
    """makepkg cannot be run as root.

    This function changes the owner and group owner of a directory tree
    rooted at directory to "tuscan".
    """
    chown(directory, "tuscan", "tuscan")
    for path, subdirs, files in walk(directory):
        for f in subdirs + files:
            chown(join(path, f), "tuscan", "tuscan")


def get_package_source_dir(args):
    """Get the sources for a package.

    PKGBUILDs contain instructions for downloading sources and then
    building them. We don't want to download the sources before every
    build, so this function downloads sources and stores them in a
    standard location so that they can be copied later rather than
    re-downloaded.

    If this function returns successfully, the abs directory for package
    will have been copied to sources_directory, and the sources for that
    package will have been downloaded into it.
    """
    if not isdir(args.abs_dir):
        log("die", "Could not find abs directory for abs_dir '" +
                args.abs_dir + "'")
        exit(1)
    copytree(args.abs_dir, args.permanent_source_dir)
    recursive_chown(args.permanent_source_dir)
    chdir(args.permanent_source_dir)

    # The --nobuild flag to makepkg causes it to download sources, but
    # not build them.
    command = ("sudo -u tuscan makepkg --nobuild --syncdeps "
               "--skipinteg --skippgpcheck --skipchecksums "
               "--noconfirm --nocolor --log --noprogressbar "
               "--nocheck --nodeps")
    time = timestamp()
    cp = run(command.split(), stdout=PIPE, stderr=STDOUT,
             universal_newlines=True)
    log("command", command, cp.stdout.splitlines(), time)

    ret_code = False
    if cp.returncode:
        rmtree(args.permanent_source_dir)
    else:
        ret_code = True

    return ret_code


def copy_and_build(args):
    copytree(args.permanent_source_dir, args.build_dir)
    recursive_chown(args.build_dir)
    chdir(args.build_dir)

    # Add the --host option to invocations of ./configure
    with open("PKGBUILD", encoding="utf-8") as f:
        pkgbuild = f.read().splitlines()

    pkgbuild = [sub(r"configure\s",
                    "configure --host x86_64-unknown-linux ",
                    line) for line in pkgbuild]

    with open("PKGBUILD", "w", encoding="utf-8") as f:
        f.write("\n".join(pkgbuild))

    # The difference between this invocation and the one in
    # get_package_source_dir() is the --noextract flag. Sources should
    # already have been downloaded and extracted by
    # get_package_source_dir(), so we just want to build them.
    #
    # Also, the invocation in get_package_source_dir has the --nodeps
    # option, since we just wanted to download sources there. Here, we
    # do want to install dependencies (from our local toolchain
    # repository), so don't pass the --nodeps flag.
    if args.env_vars == None:
        args.env_vars = []

    command_env = environ.copy()
    for pair in args.env_vars:
        var, val = pair.split("=")
        command_env[var] = val

    command = (
       "sudo -u tuscan " +
       " ".join(args.env_vars) +
       " makepkg --noextract --syncdeps"
       " --skipinteg --skippgpcheck --skipchecksums"
       " --noconfirm --nocolor --log --noprogressbar"
       " --nocheck"
    )
    time = timestamp()

    proc = Popen(command.split(), stdout=PIPE, stderr=STDOUT,
                 universal_newlines=True, env=command_env)

    stdout_data, _ = proc.communicate()

    log("command", command, stdout_data.splitlines(), time)

    return proc.returncode


def sanity_checks(args):
    if not isdir(args.sources_directory):
        log("die", "Could not find source directory '" +
              args.sources_directory + "'")
        die(2)

    if not isdir(args.permanent_source_dir):
        if not(get_package_source_dir(args)):
            log("die", "Unable to get sources for abs_dir '" +
                  args.abs_dir + "'")
            die(3)
        else:
            log("info", "Copied source directory to " +
                    args.permanent_source_dir)
    else:
        log("info", "Found permanent source directory in "
              + args.permanent_source_dir)


def initialize_repositories(args):
    """Point pacman to toolchain builds.

    Ensure that pacman only installs toolchain builds of packages during
    the build process by pointing pacman.conf to the toolchain
    repository.
    """

    # Point pacman to our toolchain repository. This means commenting
    # out the official repositories in pacman.conf, and creating a new
    # entry for the local toolchain repository.

    lines = []
    with open("/etc/pacman.conf") as f:
        appending = True
        for line in f:
            if search("# REPOSITORIES", line):
                appending = False
            if appending:
                lines.append(line.strip())

    lines.append("[%s]" % toolchain_repo_name())
    lines.append("Server = file://%s" % args.toolchain_directory)

    with open("/etc/pacman.conf", "w") as f:
        for line in lines:
            print(line, file=f)

    log("info",
        "Removed vanilla repositories from pacman.conf and added:",
        lines[-2:])

    command = "pacman -Syy --noconfirm"
    time = timestamp()
    cp = run(command.split(),
             stdout=PIPE, stderr=STDOUT, universal_newlines=True)
    log("command", command, cp.stdout.splitlines(), time)
    if cp.returncode:
        die(6)


def path_to_vanilla_pkg(pkg_name, args):
    """Returns the path to a vanilla package in the local mirror.

    This method tries to find a package with name exactly matching
    'pkg_name' in one of the repositories in the local mirror. It aborts
    the stage if such a package isn't found.
    """
    log("info", "Trying to find vanilla package '%s'..." % pkg_name)
    for root, dirs, files in walk(args.mirror_directory):
        for f in files:

            if search("i686", f): continue
            if not search(".pkg.tar.xz$", f): continue

            if search(escape(pkg_name), f):
                path = join(root, f)
                cmd = "pacman --query --file " + path
                cp = run(cmd.split(), stdout=PIPE, stderr=STDOUT,
                         universal_newlines=True)
                log("command", cmd, cp.stdout.splitlines())
                if cp.returncode:
                    exit(1)
                candidate_name = cp.stdout.splitlines()[0].split()[0]
                if pkg_name == candidate_name:
                    return path
    log("die", "No matching packages found.")
    exit(1)


def create_hybrid_packages(args):
    chdir(args.build_dir)

    toolchain_packages = glob("*.pkg.tar.xz")
    if not toolchain_packages:
        log("die", "No built packages found in %s" % args.build_dir)
        exit(7)

    hybrid_package_paths = []
    hybrid_packages_dir = "/tmp/hybrid_packages"

    dir_toolchain = "/tmp/toolchain"
    dir_vanilla = "/tmp/vanilla"
    dir_hybrid = "/tmp/hybrid"

    for pkg in toolchain_packages:
        for d in [dir_toolchain, dir_vanilla, dir_hybrid]:
            rmtree(d, ignore_errors=True)
            makedirs(d)

        cmd = "pacman --query --file " + pkg
        cp = run(cmd.split(), stdout=PIPE, stderr=STDOUT,
                 universal_newlines=True)
        log("command", cmd, cp.stdout.splitlines())
        if cp.returncode:
            exit(1)
        pkg_name = cp.stdout.splitlines()[0].split()[0]
        log("info", "Creating hybrid package for '%s'" % pkg_name)

        vanilla_pkg = path_to_vanilla_pkg(pkg_name, args)

        with tar_open(pkg) as t: t.extractall(dir_toolchain)
        with tar_open(vanilla_pkg) as t: t.extractall(dir_vanilla)

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


        for d in listdir(dir_vanilla):
            src = join(dir_vanilla, d)
            dst = join(dir_hybrid, d)
            try: copytree(src, dst, symlinks=True)
            except NotADirectoryError:
                # This will be .INSTALL, .MTREE or .PKGINFO, noted above
                copyfile(src, dst)

        for d in ["usr/lib", "usr/include"]:
            src = join(dir_toolchain, d)
            dst = join(dir_hybrid, "toolchain_root", d)
            try: copytree(src, dst, symlinks=True)
            except FileNotFoundError: pass


        structure = []
        for root, dirs, files in walk(dir_hybrid):
            for f in files:
                path = sub(dir_hybrid, "", join(root, f))
                structure.append(path)
        log("info", "Package file has the following structure:",
            structure)

        pkg_path = create_package(dir_hybrid, pkg_name, args)
        hybrid_package_paths.append(pkg_path)

    return hybrid_package_paths


def main():
    parser = get_argparser()
    parser.add_argument("--abs-dir", dest="abs_dir", required=True)
    args = parser.parse_args()
    args.mirror_directory = "/mirror"

    pkg_dir = basename(args.abs_dir)

    args.permanent_source_dir = join(args.sources_directory, pkg_dir)
    args.build_dir = join("/tmp", pkg_dir)

    sanity_checks(args)
    initialize_repositories(args)

    result = copy_and_build(args)
    if result:
        die(5)

    paths_to_packages = create_hybrid_packages(args)

    if not paths_to_packages:
        log("die", "No hybrid packages were created.")
        exit(1)

    for path in paths_to_packages:
        add_package_to_toolchain_repo(path, args.toolchain_directory)

    die(0)


if __name__ == "__main__":
    main()
