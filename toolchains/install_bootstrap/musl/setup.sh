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
BUILDDIR=/musl_build
PKGDIR=/sysroot

mkdir -p ${PKGDIR}

if [ -d "${PKGDIR}/bin" ]; then
  # We've already downloaded and built a toolchain
  exit 0
fi

CURL_FLAGS="-s -S --connect-timeout 270"

# Binutils
mkdir -p ${SRCDIR}/binutils
curl $CURL_FLAGS http://ftp.gnu.org/gnu/binutils/binutils-2.26.tar.bz2 \
  | tar xj -C ${SRCDIR}/binutils --strip-components=1

# LLVM stuff

URL=https://codeload.github.com/llvm-mirror
# Format: 'release_%d%d' for particular release or 'master' for tip of
# tree
REL=release_39
# Alternative-format release number
REL_NUM=3.9.0

pushd /tmp
curl $CURL_FLAGS "${URL}/llvm/zip/${REL}" \
               > "llvm-${REL}.zip"
unzip "llvm-${REL}.zip"
mv "llvm-${REL}" "${SRCDIR}/llvm"
mkdir -p ${SRCDIR}/llvm/{tools,projects}

curl $CURL_FLAGS "${URL}/clang/zip/${REL}" \
               > "clang-${REL}.zip"
unzip "clang-${REL}.zip"
mv "clang-${REL}" "${SRCDIR}/llvm/tools/clang"

for tool in compiler-rt libcxx libcxxabi libunwind; do
  curl $CURL_FLAGS "${URL}/$tool/zip/${REL}" \
                 > "$tool-${REL}.zip"
  unzip "$tool-${REL}.zip"
  mv "$tool-${REL}" "${SRCDIR}/llvm/projects/$tool"
done
popd

# Standard C library
mkdir -p ${SRCDIR}/musl
curl $CURL_FLAGS http://www.musl-libc.org/releases/musl-1.1.14.tar.gz \
  | tar xz -C ${SRCDIR}/musl --strip-components=1

pushd ${SRCDIR}/llvm/tools/clang
patch -p1 <<EOF
diff --git a/lib/Driver/ToolChains.h b/lib/Driver/ToolChains.h
index f940e58..fd4b23e 100644
--- a/lib/Driver/ToolChains.h
+++ b/lib/Driver/ToolChains.h
@@ -803,0 +804,4 @@ public:
+  RuntimeLibType GetDefaultRuntimeLibType() const override {
+    return ToolChain::RLT_CompilerRT;
+  }
+
EOF
popd


echo Building Stage 1 clang

rm -rf ${BUILDDIR}/build-clang+llvm-x86_64-bootstrap \
  && mkdir -p ${BUILDDIR}/build-clang+llvm-x86_64-bootstrap
pushd ${BUILDDIR}/build-clang+llvm-x86_64-bootstrap
cmake -GNinja \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX=${BUILDDIR}/clang+llvm-x86_64-bootstrap \
  -DLLVM_INSTALL_TOOLCHAIN_ONLY=ON \
  ${SRCDIR}/llvm
ninja install
popd


echo Building Binutils

rm -rf ${BUILDDIR}/build-binutils && mkdir -p ${BUILDDIR}/build-binutils
pushd ${BUILDDIR}/build-binutils
${SRCDIR}/binutils/configure \
  CC=${BUILDDIR}/clang+llvm-x86_64-bootstrap/bin/clang \
  CXX=${BUILDDIR}/clang+llvm-x86_64-bootstrap/bin/clang++ \
  CXXFLAGS='-stdlib=libc++ -I${BUILDDIR}/clang+llvm-x86_64-bootstrap/include/c++/v1' \
  LDFLAGS='-L${BUILDDIR}/clang+llvm-x86_64-bootstrap/lib -Wl,-rpath,'"'"'$\\$$\$$\\$$\$$ORIGIN/../lib'"'"' -Wl,-z,origin' \
  --prefix="" \
  --enable-deterministic-archives \
  --enable-gold \
  --enable-plugins \
  --disable-ld \
  --disable-werror \
  --with-sysroot=${PKGDIR}/
make
DESTDIR=${PKGDIR} make install
popd


echo Building Musl

rm -rf ${BUILDDIR}/build-musl && mkdir -p ${BUILDDIR}/build-musl
pushd ${BUILDDIR}/build-musl
${SRCDIR}/musl/configure \
  CC=${BUILDDIR}/clang+llvm-x86_64-bootstrap/bin/clang \
  LIBCC=-lclang_rt.builtins-x86_64 \
  LDFLAGS=-L${BUILDDIR}/clang+llvm-x86_64-bootstrap/lib/clang/${REL_NUM}/lib/linux \
  --disable-wrapper \
  --prefix=""
DESTDIR=${PKGDIR} make install
popd


echo Building Stage 2 Clang

#pushd ${PKGDIR}
#rm -rf include lib share x86_64-pc-linux-gnu
#popd

rm -rf ${BUILDDIR}/build-clang+llvm-x86_64-archlinux \
  && mkdir -p ${BUILDDIR}/build-clang+llvm-x86_64-archlinux
pushd ${BUILDDIR}/build-clang+llvm-x86_64-archlinux
cmake -GNinja \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_C_COMPILER=${BUILDDIR}/clang+llvm-x86_64-bootstrap/bin/clang \
  -DCMAKE_CXX_COMPILER=${BUILDDIR}/clang+llvm-x86_64-bootstrap/bin/clang++ \
  -DCMAKE_INSTALL_PREFIX="" \
  -DLLVM_BINUTILS_INCDIR=/binutils/include \
  -DLLVM_INSTALL_TOOLCHAIN_ONLY=ON \
  -DLIBCXXABI_USE_LLVM_UNWINDER=ON \
  -DDEFAULT_SYSROOT=${PKGDIR} \
  ${SRCDIR}/llvm
DESTDIR=${PKGDIR} ninja install
popd

echo Building Musl stage 2

rm -rf ${BUILDDIR}/build-musl && mkdir -p ${BUILDDIR}/build-musl
pushd ${BUILDDIR}/build-musl
${SRCDIR}/musl/configure \
  CC=${PKGDIR}/bin/clang \
  LIBCC=-lclang_rt.builtins-x86_64 \
  LDFLAGS=-L${PKGDIR}/lib/clang/${REL_NUM}/lib/linux \
  --disable-wrapper \
  --prefix=""
DESTDIR=${PKGDIR} make install
popd


rm -rf ${BUILDDIR}/build-crt && mkdir -p ${BUILDDIR}/build-crt
pushd ${BUILDDIR}/build-crt
touch crtbegin.c crtend.c
${PKGDIR}/bin/clang crtbegin.c -c -o crtbegin.o
${PKGDIR}/bin/clang crtend.c -c -o crtend.o
install crtbegin.o crtend.o ${PKGDIR}/lib/clang/${REL_NUM}/
touch crtbeginS.c crtendS.c
${PKGDIR}/bin/clang crtbeginS.c -c -o crtbeginS.o
${PKGDIR}/bin/clang crtendS.c -c -o crtendS.o
install crtbeginS.o crtendS.o ${PKGDIR}/lib/clang/${REL_NUM}/
popd

chmod -R a+r ${PKGDIR}
chmod -R a+rx ${PKGDIR}/bin

cp -r ${PKGDIR}/* /toolchain_root
