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

FROM karkhaz/arch-tuscan:latest
MAINTAINER Kareem Khazem <khazem@google.com>

RUN pacman -S --noconfirm wget sudo

COPY make_package.py /build/make_package.py
COPY utilities.py /build/utilities.py
COPY makepkg.conf /etc/makepkg.conf
RUN chmod a+r /etc/makepkg.conf

# Add our custom local repository. This should be BEFORE all other
# repositories, thus echoing to a temp file before concatenating the
# rest of pacman.conf
RUN echo '[repo]'                       > /tmp/pacman.conf
RUN echo 'SigLevel = Optional TrustAll' >> /tmp/pacman.conf
RUN echo 'Server = file:///tuscan_data/custom_repository/latest/' >> /tmp/pacman.conf
RUN cat /etc/pacman.conf >> /tmp/pacman.conf
RUN cat /tmp/pacman.conf > /etc/pacman.conf


# wget and curl output unsuitable progress bars even when not connected
# to a TTY. Turn them off.
RUN echo "verbose = off" >> /etc/wgetrc
RUN echo "silent" >> /etc/.curlrc
RUN echo "show-error" >> /etc/.curlrc
ENV CURL_HOME /etc


# User `tuscan' needs to be able to use sudo without being harassed for
# passwords) and so does root (to su into tuscan)
RUN echo "tuscan ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers
RUN echo "root ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers

RUN useradd -m -s /bin/bash tuscan

USER tuscan

WORKDIR /home/tuscan

# Download and unpack NDK
RUN wget -O /home/tuscan/ndk.bin http://dl.google.com/android/ndk/android-ndk-r10e-linux-x86_64.bin
RUN chmod +x /home/tuscan/ndk.bin
RUN /home/tuscan/ndk.bin > /dev/null

# Set up toolchain
RUN /home/tuscan/android-ndk-r10e/build/tools/make-standalone-toolchain.sh --arch=arm --platform=android-21 --install-dir=/tmp/toolchain

RUN chown -R tuscan: /tmp/toolchain
RUN chown -R tuscan: /home/tuscan/android-ndk-r10e

RUN chmod a+rx /tmp/toolchain/bin/*

USER root
ENTRYPOINT  ["/usr/bin/python", "-u", \
 "/build/make_package.py", \
 "--env-vars", \
 "PATH=/tmp/toolchain/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin", \
 "CC=arm-linux-androideabi-gcc", \
 "CXX=arm-linux-androideabi-g++", \
 "SYSROOT=/build/android-ndk-r10e/platforms/android-21/arch-arm"]
