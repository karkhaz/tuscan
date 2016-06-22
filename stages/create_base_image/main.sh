#!/usr/bin/env bash
#
# Copyright 2016 Kareem Khazem. All Rights Reserved.
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

set -e
set -o pipefail
set -u
set -x
shopt -s failglob

err() {
  echo "ERROR: $*" >&2
}

pacman(){
  /usr/bin/pacman --noprogressbar --noconfirm $*
}

if [ ! -d "/sources" ]; then
  err "Sources directory not mounted"
  exit 1
fi

if [ ! -d "/mirror" ]; then
  err "Binaries directory not mounted"
  exit 1
fi

# Ensure that the Pacman keyring is up-to-date
pacman-key --init
pacman-key --populate archlinux
pacman-key --refresh-keys

# These need to be up-to-date before doing anything else.
pacman -Syy archlinux-keyring rsync reflector ca-certificates

# Reflector finds and rates a list of Arch Linux mirrors by speed and
# sync time, and saves it to the Pacman mirrorlist.
reflector --sort rate --threads 2 --country "United States" \
  --fastest 30 --age 24 --protocol http --save /etc/pacman.d/mirrorlist

# Re-sync to fast mirrors gotten by Reflector and update software that
# is already on the system
pacman -Syyu

# If Pacman itself was upgraded to a new major version, this might be
# necessary; it's harmless otherwise
pacman-db-upgrade

# Download packages needed by all stages. We should also install
# packages that are required for downloading and extracting source (git,
# unzip etc).
pacman -S base base-devel abs python python-requests parallel \
  git mercurial openssh unzip svn darcs sudo python-jinja python-yaml \
  binutils bison cmake ninja make libunistring patch wget

# Synchronise ABS tree. We need to do this both to obtain sources, and
# to know which binaries to download.
abs core extra community

# Avoid irritating progress bars from curl
sed -ie 's/curl -fC/curl -sSfC/g' /etc/makepkg.conf

# Since we're going to be running makepkg, we need a non-administrative
# user. We need to be able to su into that user without being prompted.
useradd -m -s /bin/bash tuscan
echo "tuscan ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers
echo "root ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers
chown tuscan: /mirror /sources

# Onto downloading and building...
python -u /build/getpkgs.py
