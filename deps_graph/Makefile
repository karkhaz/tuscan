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
# Makefile for launching a single docker container. Invoke as
#
# 	make PACKAGE_NAME
#
#	If no PACKAGE_NAME is given, this Makefile defaults to building
#	cmus.

LOG_DIR=$(shell pwd)/logs/$(shell date +%Y%m%dT%H%M%S)
CONTAINER=deps-graph-container

$(shell pwd)/logs/latest/deps: .container_build
	@mkdir -p $(LOG_DIR)
	@-rm $(shell pwd)/logs/latest
	@ln -sf $(LOG_DIR) $(shell pwd)/logs/latest
	@docker run -v $(LOG_DIR):/build/logs $(CONTAINER) $(PACKAGE)

.container_build: Dockerfile deps_graph.py
	@docker build -t $(CONTAINER) .
	@touch $@

deps_graph.py:
	@pylint --reports=n $@
