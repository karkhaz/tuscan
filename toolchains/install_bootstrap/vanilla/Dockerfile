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
# Arch Linux container for building all dependencies of all Arch Linux
# packages.
#
# USAGE:
#   docker run container_name

FROM tuscan_base_image:latest
MAINTAINER Kareem Khazem <khazem@google.com>

COPY main.py /build/main.py
COPY utilities.py /build/utilities.py
COPY tool_wrapper.c /build/tool_wrapper.c
COPY red-PKGBUILD /build/red-PKGBUILD
COPY tool_redirect_rules.yaml /build/tool_redirect_rules.yaml
COPY setup.py /build/setup.py

ENTRYPOINT ["/usr/bin/python", "-u", "/build/main.py"]
