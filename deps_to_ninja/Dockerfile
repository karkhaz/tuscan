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

FROM base/arch:latest
MAINTAINER Kareem Khazem <khazem@google.com>

RUN pacman-key --refresh-keys     && \
    pacman -Syu --noconfirm base-devel

RUN pacman-db-upgrade && \
    pacman -S --noconfirm abs python

# Sync Arch Build System repository
RUN abs

COPY deps_to_ninja.py /build/deps_to_ninja.py
COPY .ninja_syntax.py /build/ninja_syntax.py

ENTRYPOINT ["/usr/bin/python", "-u", "/build/deps_to_ninja.py"]
