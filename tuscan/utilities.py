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
from os.path import basename, dirname, isdir, join, lexists
from os import chdir, makedirs, remove, symlink, getcwd, listdir, unlink
from datetime import datetime
from json import dumps
from random import random, seed
from re import search
from shutil import move
from subprocess import run, PIPE, Popen, STDOUT, TimeoutExpired, DEVNULL
from sys import stderr
from tempfile import NamedTemporaryFile as tempfile
from textwrap import dedent
from time import sleep


def run_cmd(cmd, as_root=False, output=True):
    time = timestamp()

    if output:
        cmd_out=PIPE
    else:
        cmd_out=DEVNULL

    if not as_root:
        cmd = "sudo -u tuscan " + cmd

    cp = run(cmd.split(), stdout=cmd_out, stderr=STDOUT,
             universal_newlines=True)

    if output:
        lines = cp.stdout.splitlines()
    else:
        lines = []

    if cp.returncode:
        log("die", cmd, lines, time)
        exit(1)
    else:
        log("command", cmd, lines, time)


def interpret_bash_array(pkgbuild, array_name):
    """Return the Bash array array_name in the file at path pkgbuild.

    Returns:
        A list of strings, or an empty string if the array is not
        defined in the PKGBUILD, or None if there was a problem
        interpreting the PKGBUILD.
    """
    cmd = dedent("""\
                 #!/bin/bash
                 . %s
                 for foo in ${%s[@]}; do
                    echo ${foo};
                 done;
                 """ % (pkgbuild, array_name))
    with tempfile(mode="w") as temp:
        temp.write(cmd)
        temp.flush()
        try:
            cp = run(["/bin/bash", temp.name], stdout=PIPE,
                     universal_newlines=True, timeout=20)
        except TimeoutExpired:
            print("Unable to interpret array %s in file %s" %
                  (array_name, pkgbuild), file=stderr)
            exit(1)

    if not cp.stdout:
        return []
    else:
        return [line for line in cp.stdout.splitlines() if line]


def strip_version_info(package_name):
    """Return package_name without version numbers.

    Some packages specified as dependencies have a version number, e.g.
    gcc>=5.1. We shouldn't care about this, we always sync to an
    up-to-date mirror before building packages, so strip this info.
    """
    for pat in [r">=", r"<=", r"=", r"<", r">"]:
        depth = search(pat, package_name)
        if depth:
            package_name = package_name[:depth.start()]
    return package_name


def timestamp():
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def log(kind, string, output=[], start_time=None):
    if kind not in ["command", "info", "die", "provide_info"]:
        raise RuntimeError("Bad kind: %s" % kind)

    if not start_time:
        start_time = timestamp()

    obj = {"time" : start_time,
         "kind" : kind,
         "head" : string,
         "body" : output
    }
    print(dumps(obj), file=stderr)


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
    def __init__(self, args):
        """Arguments:
            args: an argparse object returned from a call to
                  setup_argparser(). This object must have an attribute
                  called 'shared_directory'.
        """
        top_level = args.stage_name
        self.top_level = join(args.shared_directory,  top_level)

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

    parser.add_argument("--mirror-directory",
                        dest="mirror_directory", action="store")
    parser.add_argument("--mirror-volume",
                        dest="mirror_volume", action="store")

    parser.add_argument("--stage-name",
                        dest="stage_name", action="store")

    parser.add_argument("--toolchain-directory",
                        dest="toolchain_directory", action="store")
    parser.add_argument("--toolchain-volume",
                        dest="toolchain_volume", action="store")

    parser.add_argument("--toolchain",
                        dest="toolchain", action="store")

    parser.add_argument("--env-vars", nargs="*",
                        dest="env_vars", action="store")

    return parser


def create_package(path, pkg_name, args):
    """Creates an Arch Linux package from the files in directory path.

    The files in path should include a .PKGINFO at the top-level; all
    standard Arch Linux packages should have one of these anyway. This
    method will create a .MTREE file in path (overwriting any existing
    .MTREE).

    Returns:
        the path to the new package, which will have extension
        .pkg.tar.xz.
    """
    if not lexists(join(path, ".PKGINFO")):
        raise RuntimeError("No .PKGINFO at " + path)

    owd = getcwd()
    chdir(path)

    log("info", "Generating .MTREE")
    try: unlink(".MTREE")
    except FileNotFoundError: pass
    files = " ".join(listdir("."))
    cmd = ("bsdtar -czf .MTREE --format=mtree"
           " --options=!all,use-set,type,uid,mode"
           ",time,size,md5,sha256,link " + files)
    time = timestamp()
    cp = run(cmd.split(), stdout=PIPE, stderr=STDOUT,
             universal_newlines=True)
    log("command", cmd, cp.stdout.splitlines(), time)
    if cp.returncode:
        exit(1)

    log("info", "Tar-ing up files")
    pkg_name = pkg_name + ".pkg.tar.xz"
    files = " ".join(listdir("."))

    tar_cmd = "bsdtar -cf - " + files
    time = timestamp()
    tar_proc = Popen(tar_cmd.split(), stdout=PIPE, stderr=PIPE,
                     universal_newlines=False)

    tar_data, tar_error = tar_proc.communicate()

    if tar_proc.returncode:
        log("command", tar_cmd, tar_error.decode("utf-8").splitlines(),
            time)
        exit(1)
    log("command", tar_cmd, [], time)

    xz_cmd = "xz -c -z"
    time = timestamp()
    xz_proc = Popen(xz_cmd.split(), stdin=PIPE, stdout=PIPE,
                    stderr=PIPE, universal_newlines=False)

    xz_data, xz_error = xz_proc.communicate(input=tar_data)

    if xz_proc.returncode:
        log("command", xz_cmd, xz_error.decode("utf-8").splitlines(),
            time)
        exit(1)
    log("command", xz_cmd, [], time)

    log("info", "Successfully ran " + tar_cmd + " | " + xz_cmd)
    with open(pkg_name, "bw") as f:
        f.write(xz_data)

    cmd = "bsdtar -tqf " + pkg_name + " .PKGINFO"
    time = timestamp()
    cp = run(cmd.split(), stdout=PIPE, stderr=STDOUT,
             universal_newlines=True)
    log("command", cmd, cp.stdout.splitlines(), time)
    if cp.returncode:
        exit(1)

    pkg_path = join(args.toolchain_directory, pkg_name)
    try: remove(pkg_path)
    except: pass
    move(pkg_name, args.toolchain_directory)

    log("info", "Created package at path %s" % pkg_path)

    chdir(owd)
    return pkg_path


def toolchain_repo_name(): return "tuscan"


def add_package_to_toolchain_repo(pkg, toolchain_repo_dir,
                                  remove_name=None):
    """Adds a package to the toolchain repository.

    This function is used when a hybrid package is created from a
    toolchain build. The hybrid package needs to be added to the local
    toolchain repository so that it can be installed if a future build
    depends on the package.

    Arguments:

        pkg: a path to a package (with extension .pkg.tar.xz)

        toolchain_repo_dir: directory where the toolchain repository is
                            stored, typically passed to stages via the
                            --toolchain-directory argument.

        remove_name: remove package with name 'remove_name' from
                     the repository immediately after adding package
                     pkg. This is intended to be used for creating a new
                     empty repository, by adding a 'fake' package and
                     then immediately removing it again.
    """
    if not isdir(toolchain_repo_dir):
        log("die", "Toolchain directory '%s' doesn't exist. "
                   "Check that the --tolchain-directory "
                   "argument was passed and the data-only "
                   "container was successfully created." %
                   (toolchain_repo_dir))

    repo = join(toolchain_repo_dir, toolchain_repo_name() + ".db.tar")

    # repo-add and -remove fail if they can't acquire a lock on the
    # database. This will happen quite often, as we're going to be
    # building many packages at once and adding them to the database.
    # So, keep trying to add until it works.

    seed()

    max_tries = 40
    attempt = 1
    while attempt <= max_tries:
        log("info",
            "Attempting to access local repository, attempt %d" %
                attempt)

        attempt = attempt + 1
        sleep(random() * 3)

        if attempt == int(max_tries / 2):
            log("info",
                "Couldn't add %s to %s after %d tries, "
                "erasing lock file" % (pkg, repo, attempt))
            remove(join(toolchain_repo_dir, repo + ".lck"))

        elif attempt == max_tries:
            log("info", "Couldn't add %s to %s after %d tries, dying."
                % (pkg, repo, max_tries))
            exit(1)

        lock_fail = False

        cmd = "repo-add %s %s" % (repo, pkg)
        cp = run(cmd.split(), stdout=PIPE, stderr=STDOUT,
                 universal_newlines=True)
        log("command", cmd, cp.stdout.splitlines())

        for line in cp.stdout.splitlines():
            if search("ERROR: Failed to acquire lockfile", line):
                lock_fail = True
        if lock_fail:
            continue
        elif cp.returncode:
            exit(1)

        if not remove_name: return

        cmd = "repo-remove %s %s" % (repo, remove_name)
        cp = run(cmd.split(), stdout=PIPE, stderr=STDOUT,
                 universal_newlines=True)
        log("command", cmd, cp.stdout.splitlines())

        for line in cp.stdout.splitlines():
            if search("ERROR: Failed to acquire lockfile", line):
                lock_fail = True
        if lock_fail:
            continue
        elif cp.returncode:
            exit(1)

        return
