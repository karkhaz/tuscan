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

import enum

class Status(enum.Enum):
    success = 1
    failure = 2


def die(status, message=None, output=[]):
    if message:
        log("die", message, output)

    def print_logs(pretty_log_name, real_names):
        logs = []
        for root, dirs, files in os.walk("/tmp"):
            for f in files:
                for name in real_names:
                    if f == name:
                        logs.append(os.path.join(root, f))
        if logs:
            log("info", "Printing %s" % pretty_log_name)
        for l in logs:
            lines = []
            with open(l, encoding="utf-8", errors="ignore") as f:
                for line in f:
                    lines.append(line.strip())
                log("command", "%s '%s'" % (pretty_log_name, l), lines)

    print_logs("config logfiles", ["config.log", "configure.log"])
    print_logs("Cmake errors", ["CMakeError.log"])
    print_logs("Cmake output", ["CMakeOutput.log"])

    if status == Status.success:
        exit(0)
    elif status == Status.failure:
        exit(1)
    else:
        raise RuntimeError("Bad call to die with '%s'" % str(status))



import argparse
import datetime
import json
import os
import os.path
import random
import re
import shutil
import subprocess
import sys
import textwrap
import tempfile
import time


def run_cmd(cmd, as_root=False, output=True):
    time = timestamp()

    if output:
        cmd_out=subprocess.PIPE
    else:
        cmd_out=subprocess.DEVNULL

    if not as_root:
        cmd = "sudo -u tuscan " + cmd

    cp = subprocess.run(cmd.split(), stdout=cmd_out, stderr=subprocess.STDOUT,
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
    cmd = textwrap.dedent("""\
                 #!/bin/bash
                 . {pkgbuild}
                 # This is in case the array is actually an array
                 for foo in ${{{array_name}[@]}}; do
                    echo ${{foo}};
                 done;
                 # This is in case the array is actually a single string
                 echo "${{{array_name}}}"
                 """.format(pkgbuild=pkgbuild, array_name=array_name))
    with tempfile.NamedTemporaryFile(mode="w") as temp:
        temp.write(cmd)
        temp.flush()
        try:
            cp = subprocess.run(["/bin/bash", temp.name], stdout=subprocess.PIPE,
                     universal_newlines=True, timeout=20)
        except subprocess.TimeoutExpired:
            print("Unable to interpret array %s in file %s" %
                  (array_name, pkgbuild), file=sys.stderr)
            exit(1)

    if not cp.stdout:
        return []
    else:
        tmp = [line for line in cp.stdout.splitlines() if line]
        ret = []
        for t in tmp:
            ret += t.split()
        return list(set(ret))


def strip_version_info(package_name):
    """Return package_name without version numbers.

    Some packages specified as dependencies have a version number, e.g.
    gcc>=5.1. We shouldn't care about this, we always sync to an
    up-to-date mirror before building packages, so strip this info.
    """
    for pat in [r">=", r"<=", r"=", r"<", r">"]:
        depth = re.search(pat, package_name)
        if depth:
            package_name = package_name[:depth.start()]
    return package_name


def timestamp():
    return datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def log(kind, string, output=[], start_time=None):
    if kind not in ["command", "info", "die", "provide_info",
            "dep_info", "sloc_info", "red", "red_errors"]:
        raise RuntimeError("Bad kind: %s" % kind)

    if not start_time:
        start_time = timestamp()

    obj = {"time" : start_time,
         "kind" : kind,
         "head" : string,
         "body" : output
    }
    print(json.dumps(obj), file=sys.stderr)


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
        self.top_level = os.path.join(args.shared_directory,  top_level)

        timestamp = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        self.path = os.path.join(self.top_level, timestamp)

    def __enter__(self):
        os.makedirs(self.path, exist_ok=True)
        return self.path

    def __exit__(self, type, value, traceback):
        latest = os.path.join(self.top_level, "latest")
        if os.path.lexists(latest):
            os.remove(latest)
        os.symlink(self.path, latest)


def get_argparser():
    """Set up command line options.

    Returns:
        an ArgumentParser, to which arguments can be appended before
        calling parse_args() to process them.
    """
    parser = argparse.ArgumentParser()
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

    parser.add_argument("--red-directory")

    parser.add_argument("--toolchain_root-directory")

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
    if not os.path.lexists(os.path.join(path, ".PKGINFO")):
        raise RuntimeError("No .PKGINFO at " + path)

    owd = os.getcwd()
    os.chdir(path)

    log("info", "Generating .MTREE")
    try: os.unlink(".MTREE")
    except FileNotFoundError: pass
    files = " ".join(os.listdir("."))
    cmd = ("bsdtar -czf .MTREE --format=mtree"
           " --options=!all,use-set,type,uid,mode"
           ",time,size,md5,sha256,link " + files)
    time = timestamp()
    cp = subprocess.run(cmd.split(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
             universal_newlines=True)
    log("command", cmd, cp.stdout.splitlines(), time)
    if cp.returncode:
        exit(1)

    log("info", "Tar-ing up files")
    pkg_name = pkg_name + ".pkg.tar.xz"
    files = " ".join(os.listdir("."))

    tar_cmd = "bsdtar -cf - " + files
    time = timestamp()
    tar_proc = subprocess.Popen(tar_cmd.split(), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                     universal_newlines=False)

    tar_data, tar_error = tar_proc.communicate()

    if tar_proc.returncode:
        log("command", tar_cmd, tar_error.decode("utf-8").splitlines(),
            time)
        exit(1)
    log("command", tar_cmd, [], time)

    xz_cmd = "xz -c -z"
    time = timestamp()
    xz_proc = subprocess.Popen(xz_cmd.split(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, universal_newlines=False)

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
    cp = subprocess.run(cmd.split(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
             universal_newlines=True)
    log("command", cmd, cp.stdout.splitlines(), time)
    if cp.returncode:
        exit(1)

    pkg_path = os.path.join(args.toolchain_directory, pkg_name)
    try: os.remove(pkg_path)
    except: pass
    shutil.move(pkg_name, args.toolchain_directory)

    log("info", "Created package at path %s" % pkg_path)

    os.chdir(owd)
    return pkg_path


def toolchain_repo_name(): return "tuscan"


def recursive_chown(directory):
    """makepkg cannot be run as root.

    This function changes the owner and group owner of a directory tree
    rooted at directory to "tuscan".
    """
    shutil.chown(directory, "tuscan", "tuscan")
    for path, subdirs, files in os.walk(directory):
        for f in subdirs + files:
            shutil.chown(os.path.join(path, f), "tuscan", "tuscan")


def set_local_repository_location(path, repo_name):
    """Point pacman to a local repository.

    This function rewrites pacman.conf so that no remote mirrors are
    used to install packages; instead, the local repository specified
    will be used.

    Arguments:

        path: the absolute path to the directory where the repository
              database (and packages themselves) are located.

        repo_name: the name of the repository database file, without
                   extensions.

    This function will remove all repositories from pacman.conf and add
    the following directive:
    [repo_name]
    Server = file://path
    """

    # Point pacman to our toolchain repository. This means commenting
    # out the official repositories in pacman.conf, and creating a new
    # entry for the local toolchain repository.

    lines = []
    with open("/etc/pacman.conf") as f:
        appending = True
        for line in f:
            if re.search("# REPOSITORIES", line):
                lines.append(line.strip())
                appending = False
            if appending:
                lines.append(line.strip())

    lines.append("[%s]" % repo_name)
    lines.append("Server = file://%s" % path)

    with open("/etc/pacman.conf", "w") as f:
        f.write("\n".join(lines))

    log("info",
        "Removed vanilla repositories from pacman.conf and added:",
        lines[-2:])

    command = "pacman -Syy --noconfirm"
    time = timestamp()
    cp = subprocess.run(command.split(),
             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
             universal_newlines=True)
    log("command", command, cp.stdout.splitlines(), time)
    if cp.returncode:
        die(Status.failure)


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
    if not os.path.isdir(toolchain_repo_dir):
        log("die", "Toolchain directory '%s' doesn't exist. "
                   "Check that the --tolchain-directory "
                   "argument was passed and the data-only "
                   "container was successfully created." %
                   (toolchain_repo_dir))

    repo = os.path.join(toolchain_repo_dir, toolchain_repo_name() + ".db.tar")

    # repo-add and -remove fail if they can't acquire a lock on the
    # database. This will happen quite often, as we're going to be
    # building many packages at once and adding them to the database.
    # So, keep trying to add until it works.

    random.seed()

    max_tries = 80
    attempt = 1
    while attempt <= max_tries:
        log("info",
            "Attempting to access local repository, attempt %d" %
                attempt)

        attempt = attempt + 1
        time.sleep(random.random() * 16)

        if attempt == max_tries:
            log("info", "Couldn't add %s to %s after %d tries, dying."
                % (pkg, repo, max_tries))
            exit(1)

        lock_fail = False

        cmd = "repo-add %s %s" % (repo, pkg)
        cp = subprocess.run(cmd.split(), stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, universal_newlines=True)
        log("command", cmd, cp.stdout.splitlines())

        for line in cp.stdout.splitlines():
            if re.search("ERROR: Failed to acquire lockfile", line):
                lock_fail = True
        if lock_fail:
            continue
        elif cp.returncode:
            exit(1)

        if not remove_name: return

        cmd = "repo-remove %s %s" % (repo, remove_name)
        cp = subprocess.run(cmd.split(), stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, universal_newlines=True)
        log("command", cmd, cp.stdout.splitlines())

        for line in cp.stdout.splitlines():
            if re.search("ERROR: Failed to acquire lockfile", line):
                lock_fail = True
        if lock_fail:
            continue
        elif cp.returncode:
            exit(1)

        return
