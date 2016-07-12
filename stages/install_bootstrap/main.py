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

    # Build and install bear
    with tempfile.TemporaryDirectory() as d:
        bear_tar = os.path.join(d, "bear.tar.xz")
        with tarfile.open(bear_tar, "w:xz") as tar:
            tar.add("/bear", arcname="bear")
        shutil.copyfile("/bear/PKGBUILD", os.path.join(d, "PKGBUILD"))
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
        package = glob("bear*.pkg.tar.xz")
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

    # Replace native tools with thin wrappers
    with open("/build/tool_redirect_rules.yaml") as f:
        transforms = yaml.load(f)
    execs = transforms["overwrite"] + list(transforms["replacements"].keys())
    for e in set(execs):
        execs.remove(e)
    if execs:
        log("error", ("The following executables have been specified "
                      "twice in the tool_redirect_rules.yaml: %s" %
                      str(execs)))
        exit(1)

    for e in transforms["overwrite"]:
        transforms["replacements"][e] = e
    transforms.pop("overwrite", None)

    jinja = jinja2.Environment(loader=jinja2.FileSystemLoader(["/build"]))

    wrapper_temp = jinja.get_template("tool_wrapper.c")

    with tempfile.TemporaryDirectory() as tmp_dir:
        for native, toolchain in transforms["replacements"].items():
            wrapper = wrapper_temp.render(
                    native_program=native,
                    toolchain_prefix=transforms["prefix"],
                    toolchain_program=toolchain)

            with tempfile.NamedTemporaryFile("w", suffix=".c") as temp:
                temp.write(wrapper)
                temp.flush()
                cmd = "gcc -o %s %s" % (os.path.join(tmp_dir, native),
                        temp.name)
                proc = subprocess.Popen(cmd.split(), stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT, universal_newlines=True)
                out, _ = proc.communicate()
                if proc.returncode:
                    body = "%s\n%s\n%s" % (cmd, out, wrapper)
                    log("error", "Failed to compile compiler wrapper",
                            body=body)
                    exit(1)
        for wrapper in os.listdir(tmp_dir):
            shutil.move(os.path.join(tmp_dir, wrapper),
                        os.path.join("/usr/bin", wrapper))

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
