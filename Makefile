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

TIMESTAMP=$(shell date +%Y%m%dT%H%M%S)

output_dir = $(shell pwd)/output/$1/$(TIMESTAMP)

ifeq "$(origin VERBOSE)" "undefined"
VERBOSE := >/dev/null
else
VERBOSE := 
endif

IGNORE_ERROR = 2>/dev/null || true

MY_UID = $(shell id -u)
MY_GID = $(shell id -g)
MY_UNAME = $(shell whoami)
MY_GROUP = $(shell groups | awk '{print $$1}')

define make_output_dir
@mkdir -p $(output_dir)
@-rm $(shell pwd)/output/$1/latest $(IGNORE_ERROR)
@ln -sf $(output_dir) $(shell pwd)/output/$1/latest
endef

BUILD_FILE = $(shell pwd)/output/deps_to_ninja/latest/build.ninja
ECHO = >&2 echo

DIR_GFP = get_fundamental_packages
DIR_DTN = deps_to_ninja

CONTAINER_GFP = $(DIR_GFP)_container
CONTAINER_DTN = $(DIR_DTN)_container

SCRIPT_GFP = $(DIR_GFP)/$(DIR_GFP).py
SCRIPT_DTN = $(DIR_DTN)/$(DIR_DTN).py

DOCKERFILE_GFP = $(DIR_GFP)/Dockerfile
DOCKERFILE_DTN = $(DIR_DTN)/Dockerfile

PULL_ARCH_MARKER = .pull_arch

MARKER_GFP = .$(DIR_GFP)_marker
MARKER_DTN = .$(DIR_DTN)_marker
.PRECIOUS: $(PULL_ARCH_MARKER) $(MARKER_GFP) $(MARKER_DTN)

BUILD_MARKER_GFP = .$(DIR_GFP)_container_marker
BUILD_MARKER_DTN = .$(DIR_DTN)_container_marker
.PRECIOUS: $(BUILD_MARKER_DTN) $(BUILD_MARKER_GFP)

# Top-level targets
# `````````````````
# each target corresponds to a top-level directory in this repository.

default: deps_to_ninja

test: deps_to_ninja

deps_to_ninja: $(BUILD_FILE)


# We want docker to create files using our own username and group, so
# that we can access them afterward. Generate Dockerfiles with our
# user's information written in
%/Dockerfile: %/Dockerfile.mk
	@$(ECHO) Generating $@
	@cat dne_message > $@
	@echo "#   $<,"  >> $@
	@printf "#\n# so edit that instead and rerun make.\n#\n" >> $@
	@head -n 3 dne_message | tail -n 1 >> $@
	@sed "s/__USER_NAME/$(MY_UNAME)/g;  \
		    s/__GROUP_NAME/$(MY_GROUP)/g; \
				s/__UID/$(MY_UID)/g;          \
				s/__GID/$(MY_GID)/g;          \
				 /#.*/d;" < $<  >> $@


# Directory 'deps_to_ninja'
# ``````````````````````

$(BUILD_FILE): $(BUILD_MARKER_DTN) $(MARKER_GFP)
	@$(ECHO) Calculating dependencies
	@$(call make_output_dir,$(DIR_DTN))
	@docker run -v $(call output_dir,$(DIR_DTN)):/build/logs \
		$(CONTAINER_DTN) $(VERBOSE)
	@-ln -s $@ build.ninja $(IGNORE_ERROR)

$(BUILD_MARKER_DTN): $(DOCKERFILE_DTN) $(SCRIPT_DTN) $(PULL_ARCH_MARKER)
	@$(ECHO) Building dependencies container
	@cp ninja_syntax.py deps_to_ninja/.ninja_syntax.py
	@docker build -q -t $(CONTAINER_DTN) $(DIR_DTN) $(VERBOSE)
	@-rm deps_to_ninja/.ninja_syntax.py $(IGNORE_ERROR)
	@touch $@


# Directory 'get_fundamental_packages'
# ````````````````````````````````````

$(MARKER_GFP): $(BUILD_MARKER_GFP)
	@$(ECHO) Getting fundamental packages
	@docker run -v $(call output_dir,$(DIR_GFP)):/build/packages \
		$(CONTAINER_GFP) $(VERBOSE)
	@touch $@

$(BUILD_MARKER_GFP): $(DOCKERFILE_GFP) $(SCRIPT_GFP) $(PULL_ARCH_MARKER)
	@$(ECHO) Building fundamental packages container
	@$(call make_output_dir,$(DIR_GFP))
	@docker build -q -t $(CONTAINER_GFP) $(DIR_GFP) $(VERBOSE)
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
	@-rm -r $(MARKER_DTN) $(MARKER_GFP) output $(IGNORE_ERROR)

clean_docker_builds:
	@-rm -r $(BUILD_MARKER_DTN) $(BUILD_MARKER_GFP)

.PHONY: docker_stop
docker_stop:
	@-docker stop $$(docker ps -a -q) $(IGNORE_ERROR)
	@-docker rm $$(docker ps -a -q)   $(IGNORE_ERROR)
	@-rm $(BUILD_MARKER_GFP) $(BUILD_MARKER_DTN) $(IGNORE_ERROR)

# Also delete images
.PHONY: docker_cleanup
docker_cleanup: docker_stop
	@-docker rmi -f $$(docker images -q) $(IGNORE_ERROR)
