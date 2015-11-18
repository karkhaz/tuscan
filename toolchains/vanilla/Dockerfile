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

RUN abs > /dev/null 2>&1

COPY main.py /build/main.py
COPY utilities.py /build/utilities.py
COPY makepkg.conf /etc/makepkg.conf

RUN chmod a+r /etc/makepkg.conf

# wget and curl output unsuitable progress bars even when not connected
# to a TTY. Turn them off.
#RUN echo "verbose = off" >> /etc/wgetrc
#RUN echo "silent" >> /etc/.curlrc
#RUN echo "show-error" >> /etc/.curlrc
ENV CURL_HOME /etc

# User `tuscan' needs to be able to use sudo without being harassed for
# passwords) and so does root (to su into tuscan)
#RUN echo "tuscan ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers
#RUN echo "root ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers
#
#RUN useradd -m -s /bin/bash tuscan

WORKDIR /home/tuscan

ENTRYPOINT ["/usr/bin/python", "-u", "/build/main.py"]
