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

FROM install_bootstrap_repo
MAINTAINER Kareem Khazem <khazem@google.com>

COPY main.py /build/main.py
COPY utilities.py /build/utilities.py
COPY makepkg.conf /etc/makepkg.conf
RUN chmod a+r /etc/makepkg.conf

RUN chmod a+x /usr/bin/*
RUN chmod a+r /usr/bin/*

ENV CURL_HOME /etc


ENTRYPOINT  ["/usr/bin/python", "-u", \
 "/build/main.py", \
 "--sysroot", "sysroot/sysroot", \
 "--env-vars", \
 "PATH=/sysroot/bin:/sysroot/libexec/gcc/arm-linux-androideabi/4.8:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin", \
 "CC=arm-linux-androideabi-gcc", \
 "CXX=arm-linux-androideabi-g++" \
 ]
