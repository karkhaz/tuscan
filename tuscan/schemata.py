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


from datetime import datetime
from voluptuous import All, Any, Length, Optional, Range, Required
from voluptuous import Schema


# We can't merely specify that strings ought to be of type 'str' in the
# schemata, since Python 2.7 treats unicode strings specially.
_nonempty_string = All(Any(str, unicode), Length(min=1))
_string = All(Any(str, unicode))


"""Schema for the deps.yaml files located in each stage directory"""
stage_deps_schema = Schema({
    # The name of the stage (this does not exist in the deps.yaml file
    # itself, but is added to the data structure after the file is read)
    Required("name"): _nonempty_string,
    # Data needed to build the container
    Required("build"): Schema({
        # Stages that need to have run before we build this stage
        Optional("stages"): [_nonempty_string],
        # Files that we need to copy into the build context (i.e. files
        # that are mentioned in the Dockerfile, or are needed for some
        # other reason)
        Optional("copy_files"): [_nonempty_string],
    }),
    # Data needed to run the container
    Required("run"): Schema({
        Optional("dependencies"): Schema({
            #Stages that need to have run before we run this stage
            Optional("stages"): [_nonempty_string],
            # Data containers that are used during the run of this stage
            Optional("data_containers"): [_nonempty_string],
            # Directories that will be mounted in this stage's # container
            Optional("local_mounts"): [_nonempty_string],
        }),
        # Instead of doing 'docker run', run a custom command
        Optional("command_override"): _nonempty_string,
        # Redirect the running container's output to a file
        Optional("stdout"): _nonempty_string,
        Optional("stderr"): _nonempty_string,
        # Do a shell command after this stage's container exits
        Optional("post_exit"): _nonempty_string,
        # Indicates that this stage is the root of the dependency tree
        # (the final stage to be run), and may take over the console
        Optional("top_level"): bool,
        # Whether to pass the --rm flag to docker run
        Optional("rm_container"): bool,
    })
})


"""Schema for JSON files that are generated by the make_package stage"""
make_package_schema = Schema({
    Required("build"): _nonempty_string,
    Required("return_code"): All(int, Range(min=0)),
    Required("time"): All(int, Range(min=0)),
    Optional("toolchain"): _nonempty_string,
    Optional("errors"): list,
    Optional("bad_deps"): list,
    Required("log"): [
        # Logs have a head and body. Typically, for each command that
        # gets executed by the make_package stage, the head will be the
        # command and the body will be the output of that command.
        # Some log structures might have an empty body, though.
        Schema({
            Required("head"): _nonempty_string,
            Required("kind"): Any("command", "info", "die"),
            Required("time"): (lambda s:
                datetime.strptime(s, "%Y-%m-%dT%H:%M:%S")),
            Required("body"): [
                Schema(_string)
            ]
        })
    ]
})


"""Schema for JSON files dumped out of the post-processing stage

This is currently identical to make_package_schema, but will change as
more features are added to the post-processing pass.
"""
post_processed_schema = Schema({
    Required("build"): _nonempty_string,
    Required("return_code"): All(int, Range(min=0)),
    Required("time"): All(int, Range(min=0)),
    Optional("toolchain"): _nonempty_string,
    Optional("errors"): list,
    Optional("bad_deps"): list,
    Required("log"): [
        Schema({
            Required("head"): _nonempty_string,
            Required("kind"): Any("command", "info", "die"),
            Required("time"): (lambda s:
                datetime.strptime(s, "%Y-%m-%dT%H:%M:%S")),
            Required("body"): [
                Schema(_string)
            ]
        })
    ]
})
