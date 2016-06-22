#!/usr/bin/env python3
#
# Copyright 2016 Kareem Khazem. All Rights Reserved.
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
"""Download all Arch sources & binaries and create Tuscan base image

This stage does three things:

- Downloads binaries of all official Arch Linux packages in the core,
  extra and community repositories, and writes them into a directory
  mounted from the host system.

- Downloads sources corresponding to those binaries, and writes them
  into a different directory mounted from the host system

- Creates a Docker image where the software database is in sync with the
  downloaded sources and binaries. The image is committed, and all other
  Tuscan stages shall be based on that image.

This means that once this stage has successfully run, other stages
should not need to access the network (unless a particular package needs
to do so as part of its build process; this does happen occasionally).
All package transactions shall happen relative to the local binary and
source mirrors, rather than querying remote mirrors.

This script is executed _after_ stages/create_base_image/main.sh, which
installs the basic environment (including Python).
"""


from utilities import timestamp, recursive_chown
from utilities import set_local_repository_location

import requests

import argparse
import codecs
import concurrent.futures
import functools
import json
import logging
import multiprocessing
import os
import os.path
import random
import re
import signal
import shutil
import subprocess
import sys
import time


def get_package_info(pkg_name):
    cmd = "pacman -Si %s" % pkg_name
    proc = subprocess.Popen(cmd.split(), stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT)
    out, _ = proc.communicate()
    if proc.returncode:
        report_failure("sources", "Unable to find package data.", pkg_name)
        return None
    output = codecs.decode(out, errors="replace")
    for line in output.splitlines():
        m = re.match("Version\s+:\s+(?P<ver>.+)", line)
        if m:
            version = m.group("ver")
        m = re.match("Architecture\s+:\s+(?P<arch>.+)", line)
        if m:
            arch = m.group("arch")
        m = re.match("Repository\s+:\s+(?P<repo>.+)", line)
        if m:
            repo = m.group("repo")
    if not version or not repo or not arch:
        report_failure("sources", ("Unable to obtain information "
                                   "for package '{pack}'\n"
                                   "Version: {ver}\n"
                                   "Repo: {repo}\n"
                                   "Arch: {arch}").format(
                                       ver=version, arch=arch,
                                       repo=repo, pack=pkg_name),
                                   pkg_name)
        return None
    return {
        "version": version,
        "arch": arch,
        "repo": repo
    }


def report_failure(kind, message, package_name):
    if kind not in ["mirror", "sources"]:
        raise ValueError("Bad kind '%s'" % kind)
    log_name = os.path.join("/%s" % kind, "%s.log" % package_name)
    with open(log_name, "w") as f:
        f.write("%s\n" % message)
    logging.error("Failed to download %s into %s" % (package_name, kind))


def download_source(path):
    """Download sources for the package whose abs dir is path.

    If sources are not downloaded for some reason, a file called
    /sources/$PKGNAME.log will contain more information about the
    reason.
    """

    abs_name = os.path.basename(path)

    source_dir = os.path.join("/sources", abs_name)
    shutil.copytree(path, source_dir)
    recursive_chown(source_dir)

    # makepkg must be run in the directory where the PKGBUILD is.
    # However, we cannot use os.chdir because the cwd is process-wide,
    # not thread-local, and we're using threading rather than
    # multiprocessing.  Therefore, pass a new cwd to the subprocess.
    #
    # We want to download and extract the source, but not build it.
    # PKGBUILDs also have a prepare() function that gets executed
    # after extraction but before building; we shouldn't run that
    # function either, since it might need some of the packages in
    # `makedepends` to be installed. We should avoid installing those,
    # since we would need to lock otherwise (only one Pacman can be
    # running at a time).
    #
    # We don't pass --syncdeps (so that dependencies don't get
    # installed) and also pass --nodeps (so that makepkg doesn't error
    # out when it notices that not all dependencies are installed),
    # because we're not building anything. Anything that is required for
    # downloading and source extraction should already be installed by
    # the create_base_image/main.sh script.
    #
    # GPG and SHA take forever, and there's a serious risk that we fill
    # up the container's process table with unreaped children if we do
    # integrity checks; so don't bother.
    cmd = ("sudo -u tuscan makepkg --noprepare --nobuild --nocheck"
           " --nodeps --noarchive --skipinteg --nocolor --nosign")
    proc = subprocess.Popen(cmd.split(), stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, cwd=source_dir)
    try:
        out, _ = proc.communicate(timeout=1800)
    except subprocess.TimeoutExpired:
        report_failure("sources", "timed out", abs_name)
        return
    output = codecs.decode(out, errors="replace")
    if proc.returncode:
        shutil.rmtree(source_dir)
        report_failure("sources", output, abs_name)


def download_binary(pkg_name, session, servers):
    """Download binary package.

    If the binary is not downloaded for some reason, a file called
    /mirror/$PKGNAME.log will contain more information about the
    reason.
    """

    servers = list(servers)
    random.shuffle(servers)
    servers = servers[:DOWNLOAD_ATTEMPTS-1]

    success = False
    errors = []
    for counter in range(DOWNLOAD_ATTEMPTS):
        server = servers[counter]
        info = get_package_info(pkg_name)
        url = ("{server}/{repo}/os/x86_64/{pkg_name}-{ver}-{arch}"
               ".pkg.tar.xz").format(server=server, repo=info["repo"],
                       ver=info["version"], pkg_name=pkg_name,
                       arch=info["arch"])
        try:
            response = session.get(url, timeout=30)
        except requests.exceptions.Timeout:
            errors.append("timed out")
        except Exception as e:
            errors.append(str(e))
        else:
            if response.status_code == requests.codes.ok:
                success = True
                f_name = "{name}-{ver}.pkg.tar.xz".format(
                        name=pkg_name, ver=info["version"])
                with open(os.path.join("/mirror", f_name), "wb") as f:
                    f.write(response.content)
                break
            else:
                errors.append(("Bad response %d for url '%s'.\nHeader:\n%s") %
                              (response.status_code, url,
                               str(response.headers)))
    if success:
        return
    else:
        error_str = "\nDownload attempt:\n".join(errors)
        report_failure("mirror", error_str, pkg_name)


def main():
    paths = []
    logging.basicConfig(format="%(asctime)s %(message)s",
            level=logging.INFO)
    jobs = multiprocessing.cpu_count()
    random.seed()

    # List of all source directories in the ABS.
    for repo in ["core", "extra", "community"]:
        dirs = os.listdir(os.path.join("/var/abs", repo))
        paths += [os.path.join("/var/abs", repo, d) for d in dirs]

    # The list of all binaries will be a superset of the list of source
    # directories. This is because one source directory may create
    # multiple binary packages.
    packages = []
    cmd = "pacman -Sl community core extra"
    cp = subprocess.run(cmd.split(), stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, universal_newlines=True)
    if cp.returncode:
        logging.error(cmd)
        logging.error(cp.stdout)
        exit(1)
    for line in cp.stdout.splitlines():
        m = re.match("\w+\s+(?P<pkg>[-\.@\+\w]+)\s+", line)
        if m:
            packages.append(m.group("pkg"))
        else:
            logging.error("Package '%s' does not match regex" % line)
            exit(1)

    servers = []
    with open("/etc/pacman.d/mirrorlist") as f:
        for line in f:
            m = re.match("Server\s+=\s+(?P<url>http.+)\$repo/os/\$arch",
                    line)
            if m:
                servers.append(m.group("url"))
    if not servers:
        with open("/etc/pacman.d/mirrorlist") as f:
            mirrorlist = f.read()
        logging.error("Could not find remote mirror")
        logging.error("Contents of mirrorlist:\n%s" % mirrorlist)
        exit(1)
    else:
        logging.info("Using servers: '%s'" % "\n".join(servers))

    # We don't want to open a new connection to the mirror every time we
    # want to download from it; this is impolite and the mirror will
    # block us. We need a few more connections than concurrent worker,
    # since when a worker makes a network request another worker will be
    # permitted to execute. Therefore, use a requests.session object.
    #
    # We can't use a session object for downloading source, since that
    # is not under our control (makepkg does the download). But source
    # code comes from many different upstreams, so the load on each of
    # them should be somewhat reduced.
    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(pool_connections=jobs*2,
            pool_maxsize=jobs*2)
    # We only scraped the mirrorlist for HTTP mirrors, not rsync or HTTPS.
    session.mount("http://", adapter)

    download_binary_curry = functools.partial(download_binary,
            session=session, servers=servers)

    jobs_map = {}
    for path in paths:
        jobs_map[path] = download_source
    for pack in packages:
        jobs_map[pack] = download_binary_curry

    original = signal.signal(signal.SIGINT, signal.SIG_IGN)
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
        for item, fun in jobs_map.items():
            pool.submit(fun, item)
        signal.signal(signal.SIGINT, original)

    # Now that we've downloaded all the binaries, we should add them to
    # a local repository. This is because the install_bootstrap stage
    # will later need to install packages. We can't use pacman -U in the
    # install_bootstrap stage, since install_bootstrap does not only
    # install bootstrap packages but also their dependencies. It would
    # therefore install bootstrap packages from the local mirror and
    # dependencies remotely if we passed -U...so create a local
    # repository and install with -S instead.

    local_repo = "/mirror/mirror.db.tar"

    for pack in os.listdir("/mirror"):
        pack = os.path.join("/mirror", pack)
        cmd = "repo-add %s %s" % (local_repo, pack)
        cp = subprocess.run(cmd.split(), stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, universal_newlines=True)
        if cp.returncode:
            logging.error(cmd)
            logging.error(cp.stdout.splitlines())
            exit(1)

    set_local_repository_location(os.path.dirname(local_repo),
        os.path.splitext(os.path.splitext(os.path.basename(local_repo))[0])[0])


# Try multiple different mirrors for each binary download
DOWNLOAD_ATTEMPTS = 4

if __name__ == "__main__":
    main()
