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

from tuscan.schemata import data_containers_schema, stage_deps_schema

from datetime import datetime
from glob import glob
from ninja_syntax import Writer
from os import getcwd, listdir
from os.path import dirname, isfile, join
from re import sub
from string import Template
from subprocess import call
from sys import stdout, stderr
from voluptuous import MultipleInvalid
from yaml import load, dump


def substitute_vars(data_structure, args):
    """Substitute variables in YAML data files with values.

    Data stored in YAML files can contain variables which need to be
    resolved at runtime. This method returns the dict or list passed in
    as the data_structure argument, with all substitutions applied.
    """
    if isinstance(data_structure, bool):
        ret = data_structure
    elif isinstance(data_structure, basestring):
        ret = Template(data_structure)
        ret = Template(ret.safe_substitute(TOOLCHAIN=args.toolchain))
        ret = Template(ret.safe_substitute(TOUCH_DIR=args.touch_dir))

        if args.verbose:
            ret = Template(ret.safe_substitute(VERBOSE="-v"))
        else:
            ret = Template(ret.safe_substitute(VERBOSE=""))

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


def create_build_file(args, ninja):
    prereqs = prerequisite_touch_files(ninja, args)

    dc = DataContainers(ninja, args, prereqs)
    dc.write_data_recipies()

    stages = Stages(dc, ninja, args, prereqs)
    stages.write_run_recipies()
    stages.write_build_recipies()


def run_ninja(args, ninja_file):
    cmd = ["ninja", "-f", ninja_file]
    if args.verbose:
        cmd.append("-v")
    cmd.append("build")

    rc = call(cmd)
    exit(rc)



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

        try:
            data_containers_schema(self.containers)
        except MultipleInvalid as e:
            stderr.write("data_containers.yaml is malformatted: %s\n" %
                         str(e))
            exit(1)

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
                       "-v {mountpoint}"
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
    cont_names = stage.run.data_containers
    conts = [c for c in data_containers if c["name"] in cont_names]
    return conts



class Stage(object):

    class Build(object):
        def __init__(self, copy_files=[], stages=[]):
            self.copy_files = copy_files
            self.stages = stages

        @staticmethod
        def load(data):
            bs = Stage.Build()
            if "copy_files" in data:
                bs.copy_files = data["copy_files"]
            if "stages" in data:
                bs.stages = data["stages"]
            return bs


    class Run(object):
        def __init__(self, dependencies=[], data_containers=[],
                     local_mounts=[], stages=[], stdout=None,
                     stderr=None,  command_override=None,
                     post_exit=None, top_level=False, rm_container=True):
            self.dependencies = dependencies
            self.data_containers = data_containers
            self.local_mounts = local_mounts
            self.stages = stages
            self.stdout = stdout
            self.stderr = stderr
            self.command_override = command_override
            self.post_exit = post_exit
            self.top_level = top_level
            self.rm_container = rm_container

        @staticmethod
        def load(data):
            rs = Stage.Run()
            if "dependencies" in data:
                rs.dependencies = data["dependencies"]
            if "data_containers" in rs.dependencies:
                rs.data_containers = rs.dependencies["data_containers"]
            if "local_mounts" in rs.dependencies:
                rs.local_mounts = rs.dependencies["local_mounts"]
            if "stages" in rs.dependencies:
                rs.stages = rs.dependencies["stages"]
            if "stdout" in data:
                rs.stdout = data["stdout"]
            if "stderr" in data:
                rs.stderr = data["stderr"]
            if "command_override" in data:
                rs.command_override = data["command_override"]
            if "post_exit" in data:
                rs.post_exit = data["post_exit"]
            if "top_level" in data:
                rs.top_level = data["top_level"]
            if "rm_container" in data:
                rs.rm_container = data["rm_container"]
            return rs


    def __init__(self, d, args):
        """Argument: a dictionary deserialised from a YAML file"""
        self.name = d["name"]
        d = substitute_vars(d, args)
        try:
            stage_deps_schema(d)
        except MultipleInvalid as e:
            stderr.write("Schema error for stage '%s': %s\n" %
                    (d["name"], str(e)))
            exit(1)

        self.build = Stage.Build.load(d["build"])
        self.run = Stage.Run.load(d["run"])

    def yaml(self):
        return dump({"build": self.build, "run": self.run})



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
        for stage in listdir("stages"):
            try:
                with open(join("stages", stage, "deps.yaml")) as f:
                    data = load(f)
                    data["name"] = stage
                    stages.append(Stage(data, args))
            except OSError:
                stderr.write("ERROR: could not find deps file in"
                             " stages directory %s.\n"
                             "Each directory under stages/ should"
                             " contain a deps.yaml file.\n" % stage)
                exit(1)

        self.stages = stages
        self.container_sanity_checks()


    def write_run_recipies(self):
        for stage in self.stages:
            stage_inputs = list(self.inputs)

            # Runs of stage always depend on builds of stage
            stage_inputs.append(touch("build", stage.name, self.args))

            # Runs of stage depend on builds of data containers
            for cont in data_containers_needed_by(stage,
                                    self.data_containers):
                stage_inputs.append(touch("build", cont["name"],
                    self.args))

            # Runs of stage depend on runs of other stages
            for dep in stage.run.stages:
                stage_inputs.append(touch("run", dep, self.args))

            build_context = "container_build_dir/%s" % stage.name

            commands = []

            if stage.run.command_override:
                main_command = stage.run.command_override
            else:
                main_command = "docker run "

                if stage.run.rm_container:
                    main_command += "--rm "

                for cont in data_containers_needed_by(stage,
                                self.data_containers):
                    main_command += "-v %s" % cont["mountpoint"]
                    main_command += " --volumes-from %s" % cont["name"]
                    main_command += " "

                for mount in stage.run.local_mounts:
                    main_command += ("-v %s/%s:/%s:ro" %
                                     (getcwd(), mount, mount))

                main_command += (" --name %s %s --output-directory %s"
                                 " --toolchain %s --stage-name %s"
                                 % (stage.name, stage.name,
                                 self.args.touch_dir,
                                 self.args.toolchain, stage.name
                                ))

                for cont in data_containers_needed_by(stage,
                                self.data_containers):
                    main_command += (" --%s-directory %s" %
                                     (cont["switch"],
                                      cont["mountpoint"]))

                    main_command += (" --%s-volume %s" %
                                     (cont["switch"],
                                          cont["name"]))

                for mount in stage.run.local_mounts:
                    main_command += (" --%s-directory /%s" %
                                     (mount, mount))

            if stage.run.stdout:
                main_command += " >" + stage.run.stdout
            if stage.run.stderr:
                main_command += " 2>" + stage.run.stderr

            # If we purposely don't delete containers after we exit,
            # then it's okay if docker run fails because the container
            # already exists.
            if not stage.run.rm_container:
                main_command += " || true"

            commands.append(main_command)

            if stage.run.post_exit:
                cmd = stage.run.post_exit
                cmd = sub("\$", "$$", cmd)
                commands.append(cmd.strip())

            commands.append("touch ${out}")

            command = " && ".join(commands)

            rule_name = "run_stage_%s" % stage.name

            if (self.args.top_level == stage.name or stage.run.top_level):
                if not self.args.run:
                    command = "/bin/true"

                self.ninja.rule(rule_name, command, description=
                                "Running stage '%s'" % stage.name,
                                pool="console")

                self.ninja.build("build", "phony",
                                 touch("run", stage.name, self.args))
            else:
                self.ninja.rule(rule_name, command, description=
                                "Running stage '%s'" % stage.name)

            self.ninja.build(touch("run", stage.name, self.args),
                             rule_name, stage_inputs)


    def write_build_recipies(self):
        if self.args.verbose:
            quiet = ""
        else:
            quiet = " >/dev/null"
        for stage in self.stages:
            stage_inputs = list(self.inputs)

            # Builds always depend on the files that they copy in
            for f in stage.build.copy_files:
                stage_inputs.append(f)

            # Builds always depend on the files in the stage
            # directory
            for f in listdir(join("stages", stage.name)):
                stage_inputs.append(join("stages", stage.name, f))

            # Some builds depend on some other stages having run
            # directory
            for dep in stage.build.stages:
                stage_inputs.append(touch("run", dep, self.args))

            build_context = join("container_build_dir",  stage.name)

            commands = []
            commands.append("mkdir -p %s" % build_context)
            commands.append("cp %s/* %s" %
                            (join("stages", stage.name), build_context))

            copyfiles = stage.build.copy_files
            copyfiles = [("cp %s %s" % (c, build_context))
                         for c in copyfiles]
            commands += copyfiles

            docker = ("docker build -t %s %s %s" %
                      (stage.name, build_context, quiet))

            commands.append(docker)
            commands.append("touch ${out}")

            command = " && ".join(commands)

            rule_name = "build_stage_%s" % stage.name

            self.ninja.rule(rule_name, command, description=
                "Building stage '%s'" % stage.name)

            self.ninja.build(touch("build", stage.name, self.args),
                        rule_name, stage_inputs)


    def container_sanity_checks(self):
        for stage in self.stages:
            for cf in stage.build.copy_files:
                if not isfile(cf):
                    raise RuntimeError(
                        "Stage %s needs to copy file %s into its"
                        " working directory in order to build, but"
                        " that file doesn't exist." % (stage.name, cf))

            for script in stage.run.stages:
                tmp = [e for e in self.stages if e.name == script]
                if not tmp:
                    raise RuntimeError(
                        "Stage %s depends on stage %s having run, but"
                        " that stage doesn't exist." %
                        (stage.name, script))

            for cont in stage.run.data_containers:
                tmp = [d for d in self.data_containers
                         if d["name"] == cont]
                if not tmp:
                    raise RuntimeError(
                        "Stage %s depends on data container '%s' having"
                        " been built, but that container is not defined"
                        " in data_containers.yaml" % (stage.name, cont))


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
    command = ("docker pull karkhaz/arch-tuscan:latest {devnull}"
               " && mkdir -p {markers_dir}"
               " && ln -fns {touch_dir} {latest_dir}").format(
                devnull=devnull,
                markers_dir=join(args.touch_dir, "container_markers"),
                touch_dir=join(getcwd(), args.touch_dir),
                latest_dir = join(getcwd(),
                                  dirname(dirname(args.touch_dir)),
                                  "latest"))

    ninja.rule(rule_name, command, description=
        "Performing prerequisite tasks")
    ninja.build(touch_file, rule_name)

    return [touch_file]


def do_build(args):
    """Top-level function called when running tuscan.py build."""
    if args.run == None:
        args.run = True

    timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    args.touch_dir = join("results", args.toolchain, timestamp, "")

    ninja_file = "tuscan.ninja"
    with open(ninja_file, "w") as f:
        ninja = Writer(f, 72)
        create_build_file(args, ninja)

    run_ninja(args, ninja_file)
