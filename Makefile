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

ECHO = >&2 echo


define touch
@-mkdir -p .markers
@-touch $1
endef


# Functions to retrieve files associated with containers
# ``````````````````````````````````````````````````````
container    = $1_container
script       = $1/$1.py
dockerfile   = $1/Dockerfile
run_marker   = .markers/$1_run
build_marker = .markers/$1_build
pull_marker  = .markers/$1_pull
test_marker  = .markers/$1_test



# Containers and their markers
# ````````````````````````````

# Containers that are built and then run
DTN  = deps_to_ninja
TEST = test
RUNS   += $(DTN) $(TEST)
BUILDS += $(DTN) $(TEST)

# Data-only container
DATA = tuscan_data
BUILDS += $(DATA)

# Base container, must be pulled before anything else is built. All
# builds should depend on $(call pull_marker,$(ARCH_PULL)).
ARCH_PULL = arch_pull
PULLS += $(ARCH_PULL)

.PRECIOUS: $(patsubst %,$(call run_marker,%),$(RUNS))
.PRECIOUS: $(patsubst %,$(call build_marker,%),$(BUILDS))
.PRECIOUS: $(patsubst %,$(call tull_marker,%),$(PULLS))

TESTS := $(patsubst test/%,%,$(wildcard $(TEST)/*.py))
ALL_TESTS_MARKERS := $(patsubst %.py,$(call test_marker,%),$(TESTS))



# Top-level targets
# `````````````````

default: deps_to_ninja

test: $(ALL_TESTS_MARKERS)

deps_to_ninja: $(call run_marker,$(DTN))



# Data container
# ``````````````

$(call build_marker,$(DATA)): $(call pull_marker,$(ARCH_PULL))
	@$(ECHO) Building data container
	@-docker create -v /$(DATA) --name $(DATA) base/arch /bin/true \
	  $(IGNORE_ERROR)
	$(call touch,$@)



# Container 'deps_to_ninja'
# `````````````````````````

$(call run_marker,$(DTN)): $(call build_marker,$(DTN)) \
	                         $(call build_marker,$(DATA))
	@$(ECHO) Calculating dependencies
	@$(call make_output_dir,$(DTN))
	@docker run -v /$(DATA) --volumes-from $(DATA) \
	  $(call container,$(DTN)) $(SWITCHES) $(VERBOSE)
	@-ln -s $@ build.ninja $(IGNORE_ERROR)
	$(call touch,$@)

$(call build_marker,$(DTN)): $(call dockerfile,$(DTN)) \
                             $(call script,$(DTN))     \
                             $(call pull_marker,$(ARCH_PULL))
	@$(ECHO) Building dependencies container
	@cp ninja_syntax.py deps_to_ninja/ninja_syntax.py
	@docker build -q -t $(call container,$(DTN)) $(DTN) $(VERBOSE)
	$(call touch,$@)



# Test container
# ``````````````

.markers/%_test: $(call build_marker,$(TEST)) \
	               $(call run_marker,%)
	@echo Running test for $(patsubst .markers/%_test,%,$@)
	@docker run -v /test -v /$(DATA) --volumes-from $(DATA) \
	  $(call container,$(TEST))                             \
	  /test/$(patsubst .markers/%_test,%.py,$@)             \
	  $(SWITCHES)
	@#Don't touch, so that tests run every time

$(call build_marker,$(TEST)): $(call dockerfile,$(TEST)) \
	                            $(call pull_marker,$(ARCH_PULL))
	@$(ECHO) Building test container
	@docker build -q -t $(call container,$(TEST)) $(TEST) $(VERBOSE)
	$(call touch,$@)



# Retrieving Arch image
# `````````````````````

$(call pull_marker,$(ARCH_PULL)):
	@$(ECHO) Retrieving Arch Linux image
	@docker pull base/arch:latest $(VERBOSE)
	$(call touch,$@)



# Cleanup
# ```````

.PHONY: clean_runs clean_builds clean_pulls clean_all

clean_runs:
	@-rm $(patsubst %,$(call run_marker,%),$(RUNS)) $(IGNORE_ERROR)

clean_builds:
	@-rm $(patsubst %,$(call build_marker,%),$(BUILDS)) $(IGNORE_ERROR)

clean_pulls:
	@-rm $(patsubst %,$(call pull_marker,%),$(PULLS)) $(IGNORE_ERROR)

clean_all: clean_runs clean_builds clean_pulls
