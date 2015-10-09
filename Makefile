# Top-level tuscan Makefile.
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

TIMESTAMP=$(shell date +%Y%m%dT%H%M%S)

define make_log_dir
@mkdir -p logs/$1/$(TIMESTAMP)
@-rm logs/$1/latest
@ln -sf $(shell pwd)/logs/$1/$(TIMESTAMP) logs/$1/latest
endef

BUILD_FILE = $(shell pwd)/logs/deps_to_ninja/latest/build.ninja
ECHO = >&2 echo

# Top-level targets
# `````````````````
# each target corresponds to a top-level directory in this repository.

default: deps_to_ninja

deps_to_ninja: $(BUILD_FILE)


# Directory 'deps_to_ninja'
# ``````````````````````

$(BUILD_FILE): .container_build_deps_to_ninja
	@$(call make_log_dir,deps_to_ninja)
	@$(ECHO) Calculating dependencies
	@docker run                                    \
	  -v $(shell pwd)/logs/deps_to_ninja/$(TIMESTAMP):/build/logs \
	  deps_to_ninja_container
	@-ln -s $@ build.ninja

.container_build_deps_to_ninja: \
	deps_to_ninja/Dockerfile deps_to_ninja/deps_to_ninja.py
	@$(ECHO) Building dependencies container
	@cp ninja_syntax.py deps_to_ninja/.ninja_syntax.py
	@docker build -q -t deps_to_ninja_container deps_to_ninja >/dev/null
	@-rm deps_to_ninja/.ninja_syntax.py
	@touch $@


# docker is a disk space hog.
.PHONY: docker_stop docker_cleanup
docker_stop:
	@-docker stop $$(docker ps -a -q)
	@-docker rm $$(docker ps -a -q)
	@rm .container_build_deps_to_ninja

# Also delete images
docker_cleanup: docker_stop
	@-docker rmi -f $$(docker images -q)
