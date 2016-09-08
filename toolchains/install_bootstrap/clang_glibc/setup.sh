#!/usr/bin/env bash
#
# Copyright 2016 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you
# may not use this file except in compliance with the License. You may
# obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

set -e
set -o pipefail
set -x

/usr/bin/python -u /build/main.py $@

SRCDIR=/srcdir
BUILDDIR=/glibc_build
PKGDIR=/sysroot

mkdir -p ${PKGDIR}

if [ -d "$PKGDIR/bin" ]; then
  # We've already downloaded and built a toolchain
  exit 0
fi

die() {
  echo "die: $*" 1>&2
  exit 1
}

CURL_FLAGS="-s -S --connect-timeout 270 "

mkdir -p ${SRCDIR}/binutils
curl $CURL_FLAGS http://ftp.gnu.org/gnu/binutils/binutils-2.26.tar.bz2 \
  | tar xj -C ${SRCDIR}/binutils --strip-components=1
mkdir -p ${SRCDIR}/llvm
curl $CURL_FLAGS http://llvm.org/releases/3.8.0/llvm-3.8.0.src.tar.xz \
  | tar xJ -C ${SRCDIR}/llvm --strip-components=1
mkdir -p ${SRCDIR}/llvm/tools/clang
curl $CURL_FLAGS http://llvm.org/releases/3.8.0/cfe-3.8.0.src.tar.xz \
  | tar xJ -C ${SRCDIR}/llvm/tools/clang --strip-components=1
mkdir -p ${SRCDIR}/llvm/projects/compiler-rt
curl $CURL_FLAGS http://llvm.org/releases/3.8.0/compiler-rt-3.8.0.src.tar.xz \
  | tar xJ -C ${SRCDIR}/llvm/projects/compiler-rt --strip-components=1
mkdir -p ${SRCDIR}/llvm/projects/libcxx
curl $CURL_FLAGS http://llvm.org/releases/3.8.0/libcxx-3.8.0.src.tar.xz \
  | tar xJ -C ${SRCDIR}/llvm/projects/libcxx --strip-components=1
mkdir -p ${SRCDIR}/llvm/projects/libcxxabi
curl $CURL_FLAGS http://llvm.org/releases/3.8.0/libcxxabi-3.8.0.src.tar.xz \
  | tar xJ -C ${SRCDIR}/llvm/projects/libcxxabi --strip-components=1
mkdir -p ${SRCDIR}/llvm/projects/libunwind
curl $CURL_FLAGS http://llvm.org/releases/3.8.0/libunwind-3.8.0.src.tar.xz \
  | tar xJ -C ${SRCDIR}/llvm/projects/libunwind --strip-components=1
mkdir -p ${SRCDIR}/glibc
curl $CURL_FLAGS https://ftp.gnu.org/gnu/glibc/glibc-2.24.tar.xz \
  | tar xJ -C ${SRCDIR}/glibc --strip-components=1

rm -rf ${BUILDDIR}/build-binutils && mkdir -p ${BUILDDIR}/build-binutils
pushd ${BUILDDIR}/build-binutils
${SRCDIR}/binutils/configure \
  --prefix="" \
  --enable-deterministic-archives \
  --enable-gold \
  --enable-plugins \
  --disable-ld \
  --disable-werror \
  --with-sysroot=${PKGDIR}
make
DESTDIR=${PKGDIR} make install
popd

pushd ${PKGDIR}
rm -rf include lib share x86_64-pc-linux-gnu
popd

rm -rf ${BUILDDIR}/build-clang+llvm-x86_64-archlinux \
  && mkdir -p ${BUILDDIR}/build-clang+llvm-x86_64-archlinux
pushd ${BUILDDIR}/build-clang+llvm-x86_64-archlinux
cmake -GNinja \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX="/" \
  -DLLVM_ENABLE_TIMESTAMPS=OFF \
  -DLLVM_BINUTILS_INCDIR=/binutils/include \
  -DLLVM_INSTALL_TOOLCHAIN_ONLY=ON \
  -DLLVM_USE_HOST_TOOLS=ON \
  -DDEFAULT_SYSROOT=${PKGDIR} \
  ${SRCDIR}/llvm
DESTDIR=${PKGDIR} ninja install
popd

rm -rf ${BUILDDIR}/build-glibc && mkdir -p ${BUILDDIR}/build-glibc
pushd ${BUILDDIR}/build-glibc
${SRCDIR}/glibc/configure \
  --prefix=${PKGDIR}
make -j
DESTDIR=${PKGDIR} make install
popd

rm -rf ${BUILDDIR}/build-crt && mkdir -p ${BUILDDIR}/build-crt
pushd ${BUILDDIR}/build-crt
touch crtbegin.c crtend.c
${PKGDIR}/bin/clang crtbegin.c -c -o crtbegin.o
${PKGDIR}/bin/clang crtend.c -c -o crtend.o
install crtbegin.o crtend.o ${PKGDIR}/lib/clang/3.8.0/
touch crtbeginS.c crtendS.c
${PKGDIR}/bin/clang crtbeginS.c -c -o crtbeginS.o
${PKGDIR}/bin/clang crtendS.c -c -o crtendS.o
install crtbeginS.o crtendS.o ${PKGDIR}/lib/clang/3.8.0/
popd

chmod -R a+r ${PKGDIR}
chmod -R a+rx ${PKGDIR}/bin

cp -r ${PKGDIR}/* /toolchain_root
