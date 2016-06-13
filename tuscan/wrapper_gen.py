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


from schemata import binutil_schema

from argparse import ArgumentParser
from jinja2 import Environment, FileSystemLoader
from os.path import exists, join
from sys import stderr
from yaml import load


def main():
    parser = ArgumentParser()
    parser.add_argument("toolchain")
    args = parser.parse_args()

    make_package_dir = join("toolchains", "make_package", args.toolchain)

    required_files = [
        join(make_package_dir, "binutil_transforms.yaml"),
        join(make_package_dir, "Dockerfile"),
        join("tuscan", "compiler_wrapper.py"),
    ]
    for f in required_files:
        if not exists(f):
            stderr.write("File not found: '%s'\n" % f)
            exit(1)

    with open(join(make_package_dir, "binutil_transforms.yaml")) as f:
        transforms = load(f)
    binutil_schema(transforms)
    execs = transforms["overwrite"] + transforms["replacements"].keys()
    for e in set(execs):
        execs.remove(e)
    if execs:
        stderr.write("The following executables have been specified "
                     "twice in the binutil_transforms.yaml for "
                     "toolchain '%s': %s\n" % (args.toolchain, str(execs)))
        exit(1)

    for e in transforms["overwrite"]:
        transforms["replacements"][e] = e
    transforms.pop("overwrite", None)

    jinja = Environment(loader=FileSystemLoader(["tuscan",
        make_package_dir]))

    dockerfile_temp = jinja.get_template("Dockerfile")
    wrapper_temp = jinja.get_template("compiler_wrapper.py")

    wrappers = {}
    out_dir = "container_build_dir/make_package"
    for native, toolchain in transforms["replacements"].items():
        wrapper = wrapper_temp.render(
                native_program=native,
                toolchain_bin=transforms["bin"],
                toolchain_program=toolchain)
        f_name = "%s_wrapper.py" % native
        with open(join(out_dir, f_name), "w") as f:
            f.write(wrapper)
        wrappers[f_name] = native

    dockerfile = dockerfile_temp.render(wrappers=wrappers)
    with open(join(out_dir, "Dockerfile"), "w") as f:
        f.write(dockerfile)


if __name__ == "__main__":
    main()
