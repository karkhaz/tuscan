#!/usr/bin/env python2
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
#
# Generation of compiler wrappers and Dockerfile for a toolchain.


from schemata import tool_redirect_schema

import argparse
import jinja2
import logging
import os.path
import subprocess
import tempfile
import yaml


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("toolchain")
    args = parser.parse_args()

    logging.basicConfig(format="%(asctime)s %(message)s")

    make_package_dir = os.path.join("toolchains", "make_package",
            args.toolchain)

    required_files = [
        os.path.join(make_package_dir, "tool_redirect_rules.yaml"),
        os.path.join(make_package_dir, "Dockerfile"),
        os.path.join("tuscan", "tool_wrapper.c"),
    ]
    for f in required_files:
        if not os.path.exists(f):
            logging.error("File not found: '%s'" % f)
            exit(1)

    with open(os.path.join(make_package_dir, "tool_redirect_rules.yaml")) as f:
        transforms = yaml.load(f)
    tool_redirect_schema(transforms)
    execs = transforms["overwrite"] + transforms["replacements"].keys()
    for e in set(execs):
        execs.remove(e)
    if execs:
        logging.error("The following executables have been specified "
                      "twice in the tool_redirect_rules.yaml for "
                      "toolchain '%s': %s" % (args.toolchain, str(execs)))
        exit(1)

    for e in transforms["overwrite"]:
        transforms["replacements"][e] = e
    transforms.pop("overwrite", None)

    jinja = jinja2.Environment(loader=jinja2.FileSystemLoader(["tuscan",
        make_package_dir]))

    dockerfile_temp = jinja.get_template("Dockerfile")
    wrapper_temp = jinja.get_template("tool_wrapper.c")

    wrappers = {}
    out_dir = "container_build_dir/make_package"
    for native, toolchain in transforms["replacements"].items():
        wrapper = wrapper_temp.render(
                native_program=native,
                toolchain_bin=transforms["bin"],
                toolchain_program=toolchain)

        wrap_name = "%s_wrapper" % native
        with tempfile.NamedTemporaryFile("w", suffix=".c") as temp:
            temp.write(wrapper)
            temp.flush()
            cmd = "gcc -o %s %s" % (os.path.join(out_dir, wrap_name),
                    temp.name)
            proc = subprocess.Popen(cmd.split(), stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, universal_newlines=True)
            out, err = proc.communicate()
            if proc.returncode:
                logging.error("Failed to compile compiler wrapper")
                logging.error("%s\n%s\n%s" % (out, err, wrapper))
                exit(1)
        wrappers[wrap_name] = native

    dockerfile = dockerfile_temp.render(wrappers=wrappers)
    with open(os.path.join(out_dir, "Dockerfile"), "w") as f:
        f.write(dockerfile)


if __name__ == "__main__":
    main()
