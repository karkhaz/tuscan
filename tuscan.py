#!/usr/bin/env python2
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

from argparse import ArgumentParser
from datetime import datetime
from ninja_syntax import Writer
from os import getcwd, listdir
from os.path import dirname, isfile, join
from re import sub
from subprocess import call
from string import Template
from sys import stdout, stderr
from yaml import load


def substitute_vars(data_structure, args):
    """Substitute variables in YAML data files with values.

    Data stored in YAML files can contain variables which need to be
    resolved at runtime. This method returns the dict or list passed in
    as the data_structure argument, with all substitutions applied.
    """
    if isinstance(data_structure, basestring):
        ret = Template(data_structure)
        ret = Template(ret.safe_substitute(TOOLCHAIN=args.toolchain))
        ret = Template(ret.safe_substitute(TOUCH_DIR=args.touch_dir))

        # Up to this point, ret is a Template. Turn it into a string
        # with no-op substitute
        ret = ret.safe_substitute()
    elif isinstance(data_structure, list):
        ret = []
        for e in data_structure:
            ret.append(substitute_vars(e, args))
    elif isinstance(data_structure, dict):
        ret = {}
        for k, v in data_structure.items():
            ret[k] = substitute_vars(v, args)
    else: raise RuntimeError("Impossible type with value %s" %
                             str(data_structure))
    return ret


def run_ninja(args, ninja_file):
    cmd = ["ninja", "-f", ninja_file]
    if args.verbose:
        cmd.append("-v")
    cmd.append("build")

    rc = call(cmd)
    exit(rc)


def create_build_file(args, ninja):
    prereqs = prerequisite_touch_files(ninja, args)

    dc = DataContainers(ninja, args, prereqs)
    dc.write_data_recipies()

    stages = Stages(dc, ninja, args, prereqs)
    stages.write_run_recipies()
    stages.write_build_recipies()

    # The top-level build rule
    ninja.build("build", "phony", touch("run", "make_package",
                                        args))


class DataContainers(object):
    """Representation of data-only containers.

    Data-only containers are defined in the file data_containers.yaml.
    Some of the stages containers will mount these data-only
    containers and write data to them, so the run of those stages
    containers depends on the build of the data-only containers.
    """

    def __init__(self, ninja, args, inputs):
        self.ninja = ninja
        self.args = args
        self.inputs = inputs

        try:
            with open("data_containers.yaml") as f:
                containers = load(f)
        except:
            stderr.write("ERROR: could not find data exp description"
                         " 'data_containers.yaml'.\n")
            exit(1)

        self.containers = substitute_vars(containers, self.args)
        self.data_container_sanity_checks()


    def get(self):
        return self.containers


    def write_data_recipies(self):
        if self.args.verbose:
            devnull = ""
        else:
            devnull = " 2>/dev/null >/dev/null"
        for container in self.containers:
            command = ("docker create "
                       " -v {mountpoint}"
                       " --name {name}"
                       " base/arch /bin/true {devnull} || true"
                       # ${out} is NOT a format string, it needs to be
                       # written like this in the ninja file. So escape
                       # with double-curly brackets.
                       " && touch ${{out}}").format(
                             mountpoint=container["mountpoint"],
                             name=container["name"],
                             devnull=devnull)

            rule_name = "create_data_container_%s" % container["name"]

            self.ninja.rule(rule_name, command, description=
                "Building data-only container '%s'" % container["name"])

            self.ninja.build(touch("build", container["name"],
                             self.args), rule_name, self.inputs)


    def data_container_sanity_checks(self):
        for container in self.containers:
            if not container["name"]: raise
            if not container["mountpoint"]: raise


def data_containers_needed_by(stage, data_containers):
    cont_names = stage["run"]["dependencies"]["data_containers"]
    conts = [c for c in data_containers if c["name"] in cont_names]
    return conts


class Stages(object):
    """Dependency relationships about stages.

    Each stage container has a subdirectory under stages/.  Some
    stages depend on other stages having been run, or data
    containers being built, before they are run. These dependencies are
    specified in a file called deps.yaml in each stages directory.

    These functions output ninja build information gleaned from the YAML
    files. Sanity checking consists of checking that data-only packages,
    stages and auxiliary files referred to as dependencies actually
    exist.
    """

    def __init__(self, data_containers, ninja, args, inputs):
        self.data_containers = data_containers.get()
        self.ninja = ninja
        self.args = args
        self.inputs = inputs

        stages = []
        for sta in listdir("stages"):
            try:
                with open(join("stages", sta, "deps.yaml")) as f:
                    data = load(f)
                    data["name"] = sta
                    stages.append(data)
            except:
                stderr.write("ERROR: could not find deps file in"
                             " stages directory %s."
                             " Each directory under stages/ should"
                             " contain a deps.yaml file.\n" % sta)
                exit(1)

        self.stages = substitute_vars(stages, self.args)
        self.normalise_containers()
        self.container_sanity_checks()


    def write_run_recipies(self):
        for sta in self.stages:
            sta_inputs = list(self.inputs)

            # Runs of sta always depend on builds of sta
            sta_inputs.append(touch("build", sta["name"], self.args))

            # Runs of sta depend on builds of data containers
            for cont in data_containers_needed_by(sta,
                                    self.data_containers):
                sta_inputs.append(touch("build", cont["name"],
                    self.args))

            # Runs of sta depend on runs of other stages
            for dep in sta["run"]["dependencies"]["stages"]:
                sta_inputs.append(touch("run", dep, self.args))

            build_context = "container_build_dir/%s" % sta["name"]

            commands = []

            if "command_override" in sta["run"]:
                main_command = sta["run"]["command_override"]
            else:
                main_command = "docker run --rm "

                for cont in data_containers_needed_by(sta,
                                self.data_containers):
                    main_command += "-v %s" % cont["mountpoint"]
                    main_command += " --volumes-from %s" % cont["name"]
                    main_command += " "

                main_command += " -t %s" % sta["name"]
                main_command += " --output-directory "
                main_command += self.args.touch_dir
                main_command += " --toolchain %s" % self.args.toolchain

                for cont in data_containers_needed_by(sta,
                                self.data_containers):
                    if "switch" in cont:
                        main_command += (" --%s-directory %s" %
                                         (cont["switch"],
                                          cont["mountpoint"]))

                        main_command += (" --%s-volume %s" %
                                         (cont["switch"],
                                          cont["name"]))

            if sta["run"]["stdout"]:
                main_command += " >%s" % sta["run"]["stdout"]
            if sta["run"]["stderr"]:
                main_command += " 2>%s" % sta["run"]["stderr"]

            commands.append(main_command)

            if "post_exit" in sta["run"]:
                cmd = sta["run"]["post_exit"]
                cmd = sub("\$", "$$", cmd)
                commands.append(cmd.strip())

            commands.append("touch ${out}")

            command = " && ".join(commands)

            rule_name = "run_stage_%s" % sta["name"]

            self.ninja.rule(rule_name, command, description=
                "Running stage '%s'" % sta["name"])

            self.ninja.build(touch("run", sta["name"], self.args),
                        rule_name, sta_inputs)


    def write_build_recipies(self):
        if self.args.verbose:
            quiet = ""
        else:
            quiet = " >/dev/null"
        for sta in self.stages:
            sta_inputs = list(self.inputs)

            # Builds always depend on the files that they copy in
            for f in sta["build"]["copy_files"]:
                sta_inputs.append(f)

            # Builds always depend on the files in the stage
            # directory
            for f in listdir(join("stages", sta["name"])):
                sta_inputs.append(join("stages", sta["name"], f))

            build_context = "container_build_dir/%s" % sta["name"]

            commands = []
            commands.append("mkdir -p %s" % build_context)
            commands.append("cp stages/%s/* %s" %
                            (sta["name"], build_context))

            copyfiles = sta["build"]["copy_files"]
            copyfiles = [("cp %s %s" % (c, build_context))
                         for c in copyfiles]
            commands += copyfiles

            docker = ("docker build -t %s %s%s" %
                        (sta["name"], build_context, quiet))

            commands.append(docker)
            commands.append("touch ${out}")

            command = " && ".join(commands)

            rule_name = "build_stage_%s" % sta["name"]

            self.ninja.rule(rule_name, command, description=
                "Building stage '%s'" % sta["name"])

            self.ninja.build(touch("build", sta["name"], self.args),
                        rule_name, sta_inputs)


    def normalise_containers(self):
        """Ensure all stages have all fields defined.

        YAML files should be easy to write, so the user can skip empty
        lists etc. We want to be able to iterate over values that are
        empty, so give them empty lists or hashes instead of None.
        """
        for sta in self.stages:

            if not "build" in sta:
                raise RuntimeError("%s has no 'build' attribute." %
                                   sta["name"])

            if not "copy_files" in sta["build"]:
                sta["build"]["copy_files"] = []

            if not "run" in sta:
                raise RuntimeError("%s has no 'run' attribute." %
                                   sta["name"])

            if not "dependencies" in sta["run"]:
                sta["run"]["dependencies"] = {}

            if not "data_containers" in sta["run"]["dependencies"]:
                sta["run"]["dependencies"]["data_containers"] = []

            if not "stages" in sta["run"]["dependencies"]:
                sta["run"]["dependencies"]["stages"] = []

            if not "stdout" in sta["run"]:
                sta["run"]["stdout"] = "&1"

            if not "stderr" in sta["run"]:
                sta["run"]["stderr"] = "&2"


    def container_sanity_checks(self):
        for sta in self.stages:

            name = sta["name"]

            for cf in sta["build"]["copy_files"]:
                if not isfile(cf):
                    raise RuntimeError(
                        "Stage '%s' needs to copy file '%s' into its"
                        " working directory in order to build, but that"
                        " file doesn't exist." % (name, cf))

            for script in sta["run"]["dependencies"]["stages"]:
                tmp = [e for e in self.stages if e["name"] == script]
                if not tmp:
                    raise RuntimeError(
                        "Stage '%s' depends on stage '%s' having run,"
                        " but that stage doesn't exist." % (name, sta))

            for cont in sta["run"]["dependencies"]["data_containers"]:
                tmp = [d for d in self.data_containers
                         if d["name"] == cont]
                if not tmp:
                    raise RuntimeError(
                        "Stage '%s' depends on data container '%s'"
                        " having been built, but that container is not"
                        " defined in data_containers.yaml" %
                        (name, cont))


def touch(kind, stage_name, args):
    """Return a name for a touch file for stage_name.

    All touch-files are dumped in a timestamped directory. Each stage
    has a touch-file to indicate that its container has been built, and
    another one to indicate that the container has been run.  Stages
    depend on each other's touch-files, so the naming must be
    consistent.
    """
    if not (kind == "build" or kind == "run" or kind == "prereq"): raise
    return join(args.touch_dir, "container_markers",
                "%s_%s" % (stage_name, kind))


def prerequisite_touch_files(ninja, args):
    """Return a list of touch files that all builds depend on.

    Some tasks must be run every time, before everything else. Thus,
    everything depends on the touch-files for these tasks. This
    function returns a touch-file for everything to depend on, and
    writes the build rule to ninja.
    """
    if args.verbose:
        devnull = ""
    else:
        devnull = " >/dev/null"
    touch_file = touch("prereq", "prereq", args)
    rule_name = "prerequisite"
    wd = getcwd()
    command = ("docker pull karkhaz/arch-tuscan:latest {devnull}"
               " && mkdir -p {mkdir_dst}"
               " && ln -fns {ln_dir_src} {ln_dir_dst}").format(
                    devnull=devnull,
                    mkdir_dst=join(args.touch_dir, container_markers)
                    ln_dir_src=join(wd, args.touch_dir),
                    ln_dir_dst=join(
                        wd,dirname(dirname(args.touch_dir)), "latest"))

    ninja.rule(rule_name, command, description=
        "Performing prerequisite tasks")
    ninja.build(touch_file, rule_name)

    return [touch_file]


def main():
    parser = ArgumentParser(description=
               "Run corpus-based toolchain experiments.")

    toolchains = listdir("toolchains")
    parser.add_argument("toolchain", choices=toolchains,
            help="a toolchain, configured in a subdirectory of"
                 " toolchains/.")
    parser.add_argument("-v", "--verbose", action="store_true",
            help="show Docker output")

    args = parser.parse_args()

    timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    args.touch_dir = join("results", args.toolchain, timestamp, "")

    ninja_file = "tuscan.ninja"
    with open(ninja_file, "w") as f:
        ninja = Writer(f, 72)
        create_build_file(args, ninja)

    run_ninja(args, ninja_file)


if __name__ == "__main__":
    main()
