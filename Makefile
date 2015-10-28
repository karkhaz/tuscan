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
#
# Top-level tuscan Makefile.

ifeq "$(origin VERBOSE)" "undefined"
VERBOSE := >/dev/null
VERBOSE_SWITCH := 
else
VERBOSE := 
VERBOSE_SWITCH := "--verbose"
endif

SWITCHES = $(VERBOSE_SWITCH) --shared-directory /$(DATA)

IGNORE_ERROR = 2>/dev/null || true

BUILD_FILE = $(shell pwd)/output/deps_to_ninja/latest/build.ninja
ECHO = >&2 echo

DIR_DTN = deps_to_ninja
DIR_TEST = test

CONTAINER_DTN = $(DIR_DTN)_container
CONTAINER_TEST = $(DIR_TEST)_container

SCRIPT_DTN = $(DIR_DTN)/$(DIR_DTN).py

DOCKERFILE_DTN = $(DIR_DTN)/Dockerfile
DOCKERFILE_TEST = $(DIR_TEST)/Dockerfile
.INTERMEDIATE: $(DOCKERFILE_DTN)

PULL_ARCH_MARKER = .pull_arch
DATA = tuscan_data

MARKER_DTN = .$(DIR_DTN)_marker
MARKER_TEST = .$(DIR_TEST)_marker
.PRECIOUS: $(PULL_ARCH_MARKER) $(MARKER_DTN)

BUILD_MARKER_DTN = .$(DIR_DTN)_container_marker
BUILD_MARKER_TEST = .$(DIR_TEST)_container_marker
BUILD_MARKER_DATA = .$(DATA)_container_marker
.PRECIOUS: $(BUILD_MARKER_DTN) $(BUILD_MARKER_TEST)

TESTS = $(patsubst test/%,%,$(wildcard $(DIR_TEST)/*.py))
ALL_TESTS_MARKERS = $(patsubst %,$(MARKER_TEST)_%,$(TESTS))

# Top-level targets
# `````````````````
# each target corresponds to a top-level directory in this repository.

default: deps_to_ninja

test: $(ALL_TESTS_MARKERS)

deps_to_ninja: $(BUILD_FILE)


# Data container
# ``````````````

$(BUILD_MARKER_DATA): $(PULL_ARCH_MARKER)
	@$(ECHO) Building data container
	@docker create -v /$(DATA) --name $(DATA) base/arch /bin/true


# Directory 'deps_to_ninja'
# ``````````````````````

$(BUILD_FILE): $(BUILD_MARKER_DTN) $(BUILD_MARKER_DATA)
	@$(ECHO) Calculating dependencies
	@$(call make_output_dir,$(DIR_DTN))
	@docker run -v /$(DATA) --volumes-from $(DATA) \
	  $(CONTAINER_DTN) $(SWITCHES) $(VERBOSE)
	@-ln -s $@ build.ninja $(IGNORE_ERROR)

$(BUILD_MARKER_DTN): $(DOCKERFILE_DTN) $(SCRIPT_DTN) $(PULL_ARCH_MARKER)
	@$(ECHO) Building dependencies container
	@cp ninja_syntax.py deps_to_ninja/ninja_syntax.py
	@docker build -q -t $(CONTAINER_DTN) $(DIR_DTN) $(VERBOSE)
	@touch $@



# Test directory
# ``````````````

$(MARKER_TEST)_%: $(BUILD_MARKER_TEST) $(BUILD_FILE)
	@echo Running test for \
	  $(patsubst %.py,%,$(patsubst $(MARKER_TEST)_%,%,$@))
	@docker run -v /test -v /$(DATA) --volumes-from $(DATA)     \
	  $(CONTAINER_TEST) /test/$(patsubst $(MARKER_TEST)_%,%,$@) \
	  $(SWITCHES)
	@touch $@

$(BUILD_MARKER_TEST): $(DOCKERFILE_TEST) $(PULL_ARCH_MARKER)
	@$(ECHO) Building test container
	@docker build -q -t $(CONTAINER_TEST) $(DIR_TEST) $(VERBOSE)
	@touch $@


# Retrieving Arch image
# `````````````````````

$(PULL_ARCH_MARKER):
	@$(ECHO) Retrieving Arch Linux image
	@docker pull base/arch:latest $(VERBOSE)
	@touch $@


# Cleanup
# ```````

.PHONY: clean_output
clean_output:
	@-rm -rf $(MARKER_DTN) $(ALL_TEST_MARKERS)

clean_docker_builds:
	@-rm -rf $(BUILD_MARKER_DTN)

.PHONY: docker_stop
docker_stop:
	@-docker stop $$(docker ps -a -q) $(IGNORE_ERROR)
	@-docker rm $$(docker ps -a -q)   $(IGNORE_ERROR)
	@-rm $(BUILD_MARKER_DTN) $(IGNORE_ERROR)

# Also delete images
.PHONY: docker_cleanup
docker_cleanup: docker_stop
	@-docker rmi -f $$(docker images -q) $(IGNORE_ERROR)
