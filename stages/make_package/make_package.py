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

from utilities import get_argparser

from fnmatch import filter
from logging import basicConfig, info, DEBUG
from os import chdir, listdir, walk
from os.path import isdir, isfile, join
from re import search, sub
from shutil import chown, copytree, rmtree
from subprocess import run, PIPE, STDOUT


def die(success):
    info("Printing config.logs")
    config_logs = []
    for root, dirs, files in walk("/tmp"):
        for log in files:
            if log == "config.log":
                debug("found log at %s" % join(root, log))
                config_logs.append(join(root, log))

    for log in config_logs:
        debug("File %s" % log)
        with open(log, encoding="utf-8") as f:
            debug(str(f.read()))

    debug("Finished printing config.logs")

    if success:
        exit(0)
    else:
        exit(1)


def recursive_chown(directory):
    """makepkg cannot be run as root.

    This function changes the owner and group owner of a directory tree
    rooted at directory to "tuscan".
    """
    chown(directory, "tuscan", "tuscan")
    for path, subdirs, files in walk(directory):
        for f in subdirs + files:
            chown(join(path, f), "tuscan", "tuscan")


def get_package_source_dir(package, sources_directory):
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
    abs_dir = None
    for repo in ["core", "extra", "community"]:
        if isdir(join("/var/abs/", repo, package)):
            if abs_dir:
                debug("Found duplicate package '%s' in both %s and %s" %
                      (package, repo, abs_dir))
                die(False)
            else:
                abs_dir = join("/var/abs/", repo, package)
    if not abs_dir:
        debug("Could not find abs directory for package '%s'" % package)
    package_source_dir = join(sources_directory, package)
    copytree(abs_dir, package_source_dir)
    recursive_chown(package_source_dir)
    chdir(package_source_dir)
    # The --nobuild flag to makepkg causes it to download sources, but
    # not build them.
    command = ("sudo -u tuscan makepkg --nobuild --syncdeps "
               "--skipinteg --skippgpcheck --skipchecksums "
               "--noconfirm --nocolor --log --noprogressbar "
               "--nocheck")
    debug(command)
    cp = run(command.split(), stdout=PIPE, stderr=STDOUT,
             universal_newlines=True)

    for line in (cp.stdout.splitlines()):
        debug(line)

    ret_code = False
    if cp.returncode:
        rmtree(package_source_dir)
    else:
        ret_code = True

    return ret_code


def copy_and_build(args):
    permanent_source_dir = join(args.sources_directory,
                                args.package_name)
    build_dir = join("/tmp/", args.package_name)

    copytree(permanent_source_dir, build_dir)
    recursive_chown(build_dir)
    chdir(build_dir)

    # Add the --host option to invocations of ./configure
    with open("PKGBUILD", encoding="utf-8") as f:
        pkgbuild = f.readlines()

    pkgbuild = [sub(r"configure\s",
                    "configure --host x86_64-unknown-linux ",
                    line) for line in pkgbuild]

    with open("PKGBUILD", "w", encoding="utf-8") as f:
        f.write("\n".join(pkgbuild))

    # The difference between this invocation and the one in
    # get_package_source_dir() is the --noextract flag. Sources should
    # already have been downloaded and extracted by
    # get_package_source_dir(), so we just want to build them.
    if args.env_vars == None:
        args.env_vars = []
    command = (
       "sudo -u tuscan %s"
       " makepkg --noextract --syncdeps"
       " --skipinteg --skippgpcheck --skipchecksums"
       " --noconfirm --nocolor --log --noprogressbar"
       " --nocheck"
       % (" ".join(args.env_vars))
    )
    debug(command)
    cp = run(command.split(), stdout=PIPE, stderr=STDOUT,
             universal_newlines=True)
    for line in (cp.stdout.splitlines()):
        debug(line)

    if cp.returncode:
        die(False)
    else:
        die(True)


def sanity_checks(args):
    cache_files = listdir("/var/cache/pacman/pkg")
    debug("Found %d packages in cache" % len(cache_files))

    if not isdir(args.sources_directory):
        debug("Could not find source directory '%s'" %
              args.sources_directory)
        die(False)

    permanent_source_dir = join(args.sources_directory,
                                args.package_name)
    if not isdir(permanent_source_dir):
        if not(get_package_source_dir(args.package_name,
                                      args.sources_directory)):
            debug("Unable to get sources for package '%s'" %
                  args.package_name)
            die(False)
        else:
            debug("Copied source directory to '%s'" %
                  permanent_source_dir)
    else:
        debug("Found permanent source directory in %s" %
              permanent_source_dir)


def force_synchronise_repository():
    """Synchronise pacman with local repository

    A local repository should have been built by the container
    custom_repository; that container should also have disabled remote
    repositories. This function synchronises pacman to the local
    repository.
    """
    cp = run(["pacman", "-Syy"], stdout=PIPE, stderr=STDOUT,
             universal_newlines=True)
    # If that failed, then either the repository wasn't built correctly
    # (a problem with the custom_repository container) or there is
    # something wrong with the Dockerfile of this container.
    if cp.returncode:
        for line in cp.stdout.splitlines() + cp.stderr.splitlines():
            debug(line)
        die(False)
    for line in (cp.stdout.splitlines()):
        debug(line)


def main():
    parser = get_argparser()
    parser.add_argument("package_name")
    args = parser.parse_args()

    basicConfig(format="tuscan: %(message)s", level=DEBUG)

    sanity_checks(args)
    force_synchronise_repository()

    result = copy_and_build(args)


if __name__ == "__main__":
    main()
