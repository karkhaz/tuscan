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


from utilities import get_argparser, log, timestamp, run_cmd
from utilities import recursive_chown

import codecs
import jinja2
from glob import glob
import json
import os
import os.path
import re
import setup
import shutil
import subprocess
import tarfile
import urllib.request
import tempfile
import yaml


def main():
    """Install vanilla bootstrap packages from local mirror.

    Installing all the bootstrap packages is a lengthy (and highly
    disk-IO bound, thus serializing) procedure, so it's best to do it
    only once. Instead of having each container running the make_package
    stage installing the boostrap packages, we install the bootstrap
    packages in this container and then base the make_package containers
    on the image of this container.
    """
    parser = get_argparser()
    args = parser.parse_args()

    # GPG takes time. Remove package signature checks.
    lines = []
    with open("/etc/pacman.conf") as f:
        for line in f:
            if re.search("SigLevel", line):
                lines.append("SigLevel = Never")
            else:
                lines.append(line.strip())
    with open("/etc/pacman.conf", "w") as f:
        for line in lines:
            print(line.strip(), file=f)

    name_data_file = os.path.join(args.shared_directory,
            "get_base_package_names", "latest", "names.json")

    with open(name_data_file) as f:
        name_data = json.load(f)
    bootstrap_packs = (name_data["base"]
                      + name_data["base_devel"]
                      + name_data["tools"]
                      + ["sloccount"])

    cmd = "pacman -S --needed --noconfirm %s" % " ".join(set(bootstrap_packs))
    proc = subprocess.Popen(cmd.split(), stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT)
    out, _ = proc.communicate()
    out = codecs.decode(out, errors="replace")
    if proc.returncode:
        log("die", cmd, out.splitlines())
        exit(1)
    else:
        log("command", cmd, out.splitlines())

    # When building red, we need to supply it with a list of defines
    # suitable for this toolchain. Construct those defines here and
    # write out the PKGBUILD with those defines.

    with open("/build/tool_redirect_rules.yaml") as f:
        transforms = yaml.load(f)

    log("info", "Before rules %s" % yaml.dump(transforms, default_flow_style=False))

    for tool in transforms["overwrite"]:
        transforms["replacements"][tool] = tool

    log("info", "After rules %s" % yaml.dump(transforms, default_flow_style=False))

    defines = []

    for tool, replacement in transforms["replacements"].items():
        # The tool & replacement will be written just like the name of
        # the tool binary, e.g. "scan-view", "clang++", etc. These are
        # not valid identifiers (because they contain - or +), so the
        # libred cmake define variable will write them as SCAN_VIEW and
        # CLANGPP. Do that transformation here, but leave the name of
        # the original tool intact.
        var_name = re.sub("-", "_", tool)
        var_name = re.sub("\+\+", "pp", var_name)
        var_name = var_name.upper()

        path = os.path.join(transforms["bin-dir"],
                            "%s%s" % (transforms["prefix"], replacement))
        defines.append('-DRED_%s="%s"' % (var_name, path))

        log("info", "Redirecting %s to %s" % (var_name, path))

    if transforms["bin-dir"]:
        defines.append('-DRED_ENSURE_PATH="%s"' % transforms["bin-dir"])

    jinja = jinja2.Environment(loader=jinja2.FileSystemLoader(["/build"]))
    pkgbuild_temp = jinja.get_template("red-PKGBUILD")
    pkgbuild = pkgbuild_temp.render(defines=(" ".join(defines)))

    with open("/build/PKGBUILD", "w") as f:
        f.write(pkgbuild)

    log("info", "Generated PKGBUILD for red", output=pkgbuild.splitlines())

    # Build and install red
    with tempfile.TemporaryDirectory() as d:
        red_tar = os.path.join(d, "red.tar.xz")
        with tarfile.open(red_tar, "w:xz") as tar:
            tar.add("/red", arcname="red")
        shutil.copyfile("/build/PKGBUILD", os.path.join(d, "PKGBUILD"))
        shutil.chown(d, user="tuscan")
        os.chdir(d)
        cmd = "sudo -u tuscan makepkg --nocolor"
        cp = subprocess.run(cmd.split(), stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, universal_newlines=True)
        if cp.returncode:
            log("die", cmd, cp.stdout.splitlines())
            exit(1)
        else:
            log("command", cmd, cp.stdout.splitlines())
        package = glob("red*.pkg.tar.xz")
        if not len(package) == 1:
            log("die", "More than one package found", package)
            exit(1)
        cmd = "pacman -U --noconfirm %s" % package[0]
        cp = subprocess.run(cmd.split(), stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, universal_newlines=True)
        if cp.returncode:
            log("die", cmd, cp.stdout.splitlines())
            exit(1)
        else:
            log("command", cmd, cp.stdout.splitlines())

    if not os.path.isdir("/toolchain_root"):
        log("die", "/toolchain_root is not mounted")
        exit(1)

    if os.listdir("/toolchain_root"):
        log("info", ("Skipping toolchain-specific setup as "
                     "/toolchain_root contains files. Listing:"),
                     output=list(os.listdir("/toolchain_root")))
    else:
        log("info", ("/toolchain_root is empty, performing "
                     "toolchain-specific setup"),
                     output=list(os.listdir("/toolchain_root")))
        setup.toolchain_specific_setup(args)

    recursive_chown("/toolchain_root")

    exit(0)


if __name__ == "__main__":
    main()
