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


import datetime
import voluptuous
import yaml


# We can't merely specify that strings ought to be of type 'str' in the
# schemata, since Python 2.7 treats unicode strings specially.
_nonempty_string = voluptuous.All(voluptuous.Any(str, unicode), voluptuous.Length(min=1))
_string = voluptuous.All(voluptuous.Any(str, unicode))


"""voluptuous.Schema for the deps.yaml files located in each stage directory"""
stage_deps_schema = voluptuous.Schema({
    # The name of the stage (this does not exist in the deps.yaml file
    # itself, but is added to the data structure after the file is read)
    voluptuous.Required("name"): _nonempty_string,
    # Data needed to build the container
    voluptuous.Required("build"): voluptuous.Schema({
        # Stages that need to have run before we build this stage
        voluptuous.Optional("stages"): [_nonempty_string],
        # Files that we need to copy into the build context (i.e. files
        # that are mentioned in the Dockerfile, or are needed for some
        # other reason)
        voluptuous.Optional("copy_files"): [_nonempty_string],
        # Script that should be run just before the Docker build command
        voluptuous.Optional("script"): _nonempty_string,
    }),
    # Data needed to run the container
    voluptuous.Required("run"): voluptuous.Schema({
        voluptuous.Optional("dependencies"): voluptuous.Schema({
            #Stages that need to have run before we run this stage
            voluptuous.Optional("stages"): [_nonempty_string],
            # Data containers that are used during the run of this stage
            voluptuous.Optional("data_containers"): [_nonempty_string],
            # Directories that will be mounted in this stage's
            # container. This dictionary mounts the local directory to
            # the directory it will be mounted under in the container.
            voluptuous.Optional("local_mounts"): {
                _nonempty_string: _nonempty_string
            },
        }),
        # Instead of doing 'docker run', run a custom command
        voluptuous.Optional("command_override"): _nonempty_string,
        # Redirect the running container's output to a file
        voluptuous.Optional("stdout"): _nonempty_string,
        voluptuous.Optional("stderr"): _nonempty_string,
        # Do a shell command after this stage's container exits
        voluptuous.Optional("post_exit"): _nonempty_string,
        # Indicates that this stage is the root of the dependency tree
        # (the final stage to be run), and may take over the console
        voluptuous.Optional("top_level"): bool,
        # Whether to pass the --rm flag to docker run
        voluptuous.Optional("rm_container"): bool,
    })
})


"""voluptuous.Schema for data_containers.yaml file"""
data_containers_schema = voluptuous.Schema([
    voluptuous.Schema({
        # The Docker name of this data container
        voluptuous.Required("name"): _nonempty_string,
        # Where the data container will be mounted
        voluptuous.Required("mountpoint"): _nonempty_string,
        # We pass the location of data containers to stages using a
        # command line argument. We relate locations to the command line
        # switch using this key, such that if we have a data container
        # specified like this:
        # {"mountpoint": "/toolchain", "switch": "toolchain-dir"}
        # then any stage that uses this data container will get the
        # command-line argument
        # --toolchain-dir /toolchain
        voluptuous.Required("switch"): _nonempty_string
    })
])


"""voluptuous.Schema for JSON files that are generated by the make_package stage"""
make_package_schema = voluptuous.Schema({
    voluptuous.Required("build_name"): _nonempty_string,
    # This will be true for bootstrap packages, and false otherwise.
    # The results of boostrap packages will not fully conform to this
    # schema (see tuscan/empty.json for what fields bootstrap packages
    # have); clients should not attempt to validate results of bootstrap
    # packages.
    voluptuous.Required("bootstrap"): bool,
    voluptuous.Required("return_code"): voluptuous.All(int,
        voluptuous.Range(min=0)), voluptuous.Required("time"):
    voluptuous.All(int, voluptuous.Range(min=0)),
    voluptuous.Required("toolchain"): _nonempty_string,
    voluptuous.Required("errors"): list,
    # What packages are provided by this build? This will be a list of
    # package names, possibly including meta-packages (like 'sh') that
    # don't really exist but are provided by bash.
    voluptuous.Required("build_provides"): list,
    # What packages are depended on by this build? This will be a list of
    # package names, possibly including meta-packages (like 'sh') that
    # don't really exist but are provided by bash.
    voluptuous.Required("build_depends"): list,
    # Map from languages in this build, to how many LOC are written in
    # that language.
    voluptuous.Required("sloc_info"): voluptuous.Schema({
        _nonempty_string: int
    }),
    # Output from the bear tool wrapping the makepkg command.
    voluptuous.Required("bear_output"): voluptuous.Schema([ voluptuous.Any(
        voluptuous.Schema({
            "kind": "exit",
            "pid": _nonempty_string,
            "ppid": _nonempty_string,
            "return_code": _nonempty_string
        }),
        voluptuous.Schema({
            "kind": "exec",
            "timestamp": _nonempty_string,
            "pid": _nonempty_string,
            "ppid": _nonempty_string,
            "directory": _nonempty_string,
            "function": _nonempty_string,
            "command": [ _string ]
        })
    )]),
    # Map from the name of a native tool, to how many times the build
    # invoked that native tool.
    voluptuous.Required("native_tools"): voluptuous.Schema({
        _nonempty_string: int
    }),
    voluptuous.Required("log"): [
        # Logs have a head and body. Typically, for each command that
        # gets executed by the make_package stage, the head will be the
        # command and the body will be the output of that command.
        # Some log structures might have an empty body, though.
        voluptuous.Schema({
            voluptuous.Required("head"): _nonempty_string,
            voluptuous.Required("kind"): voluptuous.Any("command", "info", "die"),
            voluptuous.Required("time"): (lambda s:
                datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%S")),
            voluptuous.Required("body"): [
                voluptuous.Schema(_string)
            ]
        })
    ]
})


with open("tuscan/classification_patterns.yaml") as f:
    _patterns = yaml.load(f)
_categories = [p["category"] for p in _patterns]


"""voluptuous.Schema for JSON files dumped out of the post-processing stage"""
post_processed_schema = voluptuous.Schema({
    voluptuous.Required("build_name"): _nonempty_string,
    voluptuous.Required("bootstrap"): bool,
    voluptuous.Required("return_code"): voluptuous.All(int,
        voluptuous.Range(min=0)), voluptuous.Required("time"):
    voluptuous.All(int, voluptuous.Range(min=0)),
    voluptuous.Required("toolchain"): _nonempty_string,
    voluptuous.Required("build_provides"): list,
    voluptuous.Required("build_depends"): list,
    # Which packages is this build blocking? If this package failed to
    # build but all its dependencies built successfully, then this
    # package is said to be a "blocker" and this list will contain all
    # packages that transitively depend on it.
    voluptuous.Required("blocks"): [_nonempty_string],
    # Which builds are blocking this build? If a build of this package
    # was not attempted because some of its dependencies failed to
    # build, then this list will contain those dependencies. Note that
    # if A blocks B from building and C depends on B, then A (but not B)
    # is said to block C. Note that if a package is a blocker, but it
    # has no dependencies, then it's "blocks" list will be empty.
    voluptuous.Required("blocked_by"): [_nonempty_string],
    voluptuous.Required("sloc_info"): voluptuous.Schema({ _nonempty_string: int }),
    voluptuous.Required("bear_output"): voluptuous.Schema([ voluptuous.Any(
        voluptuous.Schema({
            "kind": "exit",
            "pid": _nonempty_string,
            "ppid": _nonempty_string,
            "return_code": _nonempty_string
        }),
        voluptuous.Schema({
            "kind": "exec",
            "timestamp": _nonempty_string,
            "pid": _nonempty_string,
            "ppid": _nonempty_string,
            "directory": _nonempty_string,
            "function": _nonempty_string,
            "command": [ _string ]
        })
    )]),
    voluptuous.Required("errors"): list,
    # Status of all configure checks in this build, combined.
    # If a single configure check returned non-zero, then False;
    # If all configure checks returned zero, then True;
    # If we couldn't figure out the return code of any configure check,
    #    then None.
    voluptuous.Required("config_success"): voluptuous.Any(bool, None),
    # This counts how many of each kind of error category were
    # encountered for this build. It is a map error_category =>
    # frequency, where the keys for error_category must be one of the
    # categories in tuscan/classification_patterns.yaml.
    voluptuous.Required("category_counts"): voluptuous.Schema({
        voluptuous.Any(*_categories): int
    }),
    voluptuous.Required("native_tools"): voluptuous.Schema({
        _nonempty_string: int
    }),
    voluptuous.Required("log"): [
        voluptuous.Schema({
            voluptuous.Required("head"): _nonempty_string,
            voluptuous.Required("kind"): voluptuous.Any("command", "info", "die"),
            # If this log is a configure log, then this key reports on
            # whether this invocation of config returned successfully.
            # True if it did, False if it didn't, None if we weren't
            # able to tell. This key does not exist in logs that are not
            # config logs.
            voluptuous.Optional("config_success"): voluptuous.Any(bool, None),
            voluptuous.Required("time"): (lambda s:
                datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%S")),
            # Post-processing looks through the output of commands, and
            # decorates each line by transforming them from strings into
            # dictionaries.  For each line in the command output, the
            # line goes into the "text" key. The "category" key is used
            # to describe what kind of error that line represents, if
            # any. The valid categories are those defined in
            # classification_patterns.yaml, or None if the line is not
            # an error message.
            voluptuous.Required("body"): [voluptuous.Schema({
                voluptuous.Required("text"): _string,
                voluptuous.Required("id"): int,
                voluptuous.Required("category"): voluptuous.Any(None,
                    *_categories), voluptuous.Required("severity"):
                voluptuous.Any("error", "diagnostic", None),
                voluptuous.Required("semantics"): voluptuous.Schema({
                    _nonempty_string: _nonempty_string
                })
            })]
        })
    ]
})

"""voluptuous.Schema for error classification patterns"""
classification_schema = voluptuous.Schema([voluptuous.Schema({
    # A regex to match a line from the build log against. If the line
    # matches the pattern, it will be classified as 'category'. If the
    # pattern contains one or more _named_ subgroups, then the
    # post-processed log line will contain a hash as the value of the
    # 'semantics' key; each key of the hash will be the name of a
    # subgroup, and the value will be the value of that subgroup.
    #
    # E.g. if we have:
    #     pattern: ": (?P<file>.+?): cannot execute binary file"
    #     category: "exec_error"
    # And a line from the log file:
    #     Horrible error: ./a.out: cannot execute binary file
    # Then post-processing will turn that line into
    #    {"text": "Horrible error: ./a.out: cannot execute binary file",
    #     "category": "exec_error",
    #     "semantics": {"file": "./a.out"}}
    voluptuous.Required("pattern"): _nonempty_string,
    voluptuous.Required("category"): _nonempty_string,
    voluptuous.Required("severity"): voluptuous.Any("error", "diagnostic")
})])


"""tool_redirect_rules.yaml files for individual toolchains

These are used for specifying what native tools will be overwritten by
a compiler wrapper that prints an error message and redirects the
invocation to a toolchain tool.
"""
tool_redirect_schema = voluptuous.Schema({
    # Prefix that is common to all toolchain tools. Will typically be a
    # directory under /toolchain_root, but may contain trailing
    # characters also. The tool name will be concatenated to this
    # prefix, so if the prefix is a directory it MUST have a trailing
    # slash.
    voluptuous.Required("prefix"): _nonempty_string,
    # A list of executables E such that /usr/bin/E shall be replaced by a
    # wrapper that points to B/E, where B is the value of the "bin" field
    voluptuous.Required("overwrite"): [ _nonempty_string ],
    # A map from N -> E such that /usr/bin/N shall be replaced by a
    # wrapper that points to B/E, where B is the value of the "bin" field
    voluptuous.Required("replacements"): {
        _nonempty_string: _nonempty_string
    }
})
