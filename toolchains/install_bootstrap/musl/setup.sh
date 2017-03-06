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

if [ -d "$PKGDIR/bin" ]; then
  # We've already downloaded and built a toolchain
  exit 0
fi

CURL_FLAGS="-L -s -S --connect-timeout 270"


# Binutils

mkdir -p ${SRCDIR}/binutils
curl $CURL_FLAGS http://ftp.gnu.org/gnu/binutils/binutils-2.26.tar.bz2 \
  | tar xj -C ${SRCDIR}/binutils --strip-components=1


# Compiler

URL=https://codeload.github.com/llvm-mirror
# Format: 'release_%d%d' for particular release or 'master' for tip of
# tree
REL=release_38
# Alternative-format release number
REL_NUM=3.8.1

pushd /tmp
curl $CURL_FLAGS "${URL}/llvm/zip/${REL}" > "llvm-${REL}.zip"
unzip "llvm-${REL}.zip"
mv "llvm-${REL}" "${SRCDIR}/llvm"

mkdir -p ${SRCDIR}/llvm/{tools,projects}

curl $CURL_FLAGS "${URL}/clang/zip/${REL}" > "clang-${REL}.zip"
unzip "clang-${REL}.zip"
mv "clang-${REL}" "${SRCDIR}/llvm/tools/clang"

for tool in compiler-rt libcxx libcxxabi libunwind; do
  curl $CURL_FLAGS "${URL}/$tool/zip/${REL}" > "$tool-${REL}.zip"
  unzip "$tool-${REL}.zip"
  mv "$tool-${REL}" "${SRCDIR}/llvm/projects/$tool"
done
popd

pushd ${SRCDIR}/llvm/tools/clang
patch -p1 <<EOF
diff --git a/include/clang/Driver/ToolChain.h b/include/clang/Driver/ToolChain.h
index 7e68d0a..424d9cc 100644
--- a/include/clang/Driver/ToolChain.h
+++ b/include/clang/Driver/ToolChain.h
@@ -258,0 +259,4 @@ public:
+  virtual CXXStdlibType GetDefaultCXXStdlibType() const {
+    return ToolChain::CST_Libcxx;
+  }
+
diff --git a/lib/Driver/ToolChain.cpp b/lib/Driver/ToolChain.cpp
index cbbd485..af5332a 100644
--- a/lib/Driver/ToolChain.cpp
+++ b/lib/Driver/ToolChain.cpp
@@ -547 +547 @@ ToolChain::CXXStdlibType ToolChain::GetCXXStdlibType(const ArgList &Args) const{
-  return ToolChain::CST_Libstdcxx;
+  return GetDefaultCXXStdlibType();
@@ -610,0 +611,2 @@ void ToolChain::AddCXXStdlibLibArgs(const ArgList &Args,
+    CmdArgs.push_back("-lc++abi");
+    CmdArgs.push_back("-lunwind");
diff --git a/lib/Driver/ToolChains.h b/lib/Driver/ToolChains.h
index f940e58..fd4b23e 100644
--- a/lib/Driver/ToolChains.h
+++ b/lib/Driver/ToolChains.h
@@ -803,0 +804,7 @@ public:
+  CXXStdlibType GetDefaultCXXStdlibType() const override {
+    return ToolChain::CST_Libcxx;
+  }
+  RuntimeLibType GetDefaultRuntimeLibType() const override {
+    return ToolChain::RLT_CompilerRT;
+  }
+
EOF
popd


# Standard C library

mkdir -p ${SRCDIR}/musl
curl $CURL_FLAGS http://www.musl-libc.org/releases/musl-1.1.14.tar.gz \
  | tar xz -C ${SRCDIR}/musl --strip-components=1


echo tuscan: Building binutils

rm -rf ${BUILDDIR}/build-binutils && mkdir -p ${BUILDDIR}/build-binutils
pushd ${BUILDDIR}/build-binutils
${SRCDIR}/binutils/configure \
  --prefix=${PKGDIR} \
  --enable-deterministic-archives \
  --enable-gold \
  --enable-plugins \
  --disable-ld \
  --disable-werror \
  --with-sysroot=${PKGDIR}
make
make install
popd

pushd ${PKGDIR}
rm -rf include lib share x86_64-pc-linux-gnu
popd

echo tuscan: Building compiler

rm -rf ${BUILDDIR}/build-clang+llvm-x86_64-archlinux \
  && mkdir -p ${BUILDDIR}/build-clang+llvm-x86_64-archlinux
pushd ${BUILDDIR}/build-clang+llvm-x86_64-archlinux
cmake -GNinja \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX=${PKGDIR} \
  -DLLVM_ENABLE_TIMESTAMPS=OFF \
  -DLLVM_ENABLE_LIBCXX=ON \
  -DLLVM_ENABLE_LIBCXXABI=ON \
  -DLLVM_BINUTILS_INCDIR=/binutils/include \
  -DLLVM_INSTALL_TOOLCHAIN_ONLY=ON \
  -DLLVM_USE_HOST_TOOLS=ON \
  -DLIBCXX_HAS_MUSL_LIBC=ON \
  -DLIBCXXABI_USE_LLVM_UNWINDER=ON \
  -DDEFAULT_SYSROOT=${PKGDIR} \
  ${SRCDIR}/llvm
ninja install
popd

echo tuscan: Building standard C library

rm -rf ${BUILDDIR}/build-musl && mkdir -p ${BUILDDIR}/build-musl
pushd ${BUILDDIR}/build-musl
${SRCDIR}/musl/configure \
  CC=${PKGDIR}/bin/clang \
  LIBCC=-lclang_rt.builtins-x86_64 \
  LDFLAGS=-L${PKGDIR}/lib/clang/${REL_NUM}/lib/linux \
  --prefix=${PKGDIR} \
  --disable-wrapper
make install
popd

echo tuscan: Building crt

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

echo "/sysroot/lib"                     >  /etc/ld.so.conf
echo "include /etc/ld.so.conf.d/*.conf" >> /etc/ld.so.conf

echo tuscan: Finished toolchain setup
