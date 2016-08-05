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

/usr/bin/python -u /build/main.py $@

SRCDIR=/srcdir
BUILDDIR=/musl_build
PKGDIR=/toolchain_root

if [ -d "$PKGDIR/bin" ]; then
  # We've already downloaded and built a toolchain
  exit 0
fi

die() {
  echo "die: $*" 1>&2
  exit 1
}

mkdir -p ${SRCDIR}/binutils
curl -s -S http://ftp.gnu.org/gnu/binutils/binutils-2.26.tar.bz2 \
  | tar xj -C ${SRCDIR}/binutils --strip-components=1
mkdir -p ${SRCDIR}/llvm
curl -s -S http://llvm.org/releases/3.8.0/llvm-3.8.0.src.tar.xz \
  | tar xJ -C ${SRCDIR}/llvm --strip-components=1
mkdir -p ${SRCDIR}/llvm/tools/clang
curl -s -S http://llvm.org/releases/3.8.0/cfe-3.8.0.src.tar.xz \
  | tar xJ -C ${SRCDIR}/llvm/tools/clang --strip-components=1
mkdir -p ${SRCDIR}/llvm/projects/compiler-rt
curl -s -S http://llvm.org/releases/3.8.0/compiler-rt-3.8.0.src.tar.xz \
  | tar xJ -C ${SRCDIR}/llvm/projects/compiler-rt --strip-components=1
mkdir -p ${SRCDIR}/llvm/projects/libcxx
curl -s -S http://llvm.org/releases/3.8.0/libcxx-3.8.0.src.tar.xz \
  | tar xJ -C ${SRCDIR}/llvm/projects/libcxx --strip-components=1
mkdir -p ${SRCDIR}/llvm/projects/libcxxabi
curl -s -S http://llvm.org/releases/3.8.0/libcxxabi-3.8.0.src.tar.xz \
  | tar xJ -C ${SRCDIR}/llvm/projects/libcxxabi --strip-components=1
mkdir -p ${SRCDIR}/llvm/projects/libunwind
curl -s -S http://llvm.org/releases/3.8.0/libunwind-3.8.0.src.tar.xz \
  | tar xJ -C ${SRCDIR}/llvm/projects/libunwind --strip-components=1
mkdir -p ${SRCDIR}/musl
curl -s -S http://www.musl-libc.org/releases/musl-1.1.14.tar.gz \
  | tar xz -C ${SRCDIR}/musl --strip-components=1

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
+    return ToolChain::CST_Libstdcxx;
+  }
+  RuntimeLibType GetDefaultRuntimeLibType() const override {
+    return ToolChain::RLT_CompilerRT;
+  }
+
EOF
popd

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

rm -rf ${BUILDDIR}/build-binutils && mkdir -p ${BUILDDIR}/build-binutils
pushd ${BUILDDIR}/build-binutils
${SRCDIR}/binutils/configure \
  CC=${BUILDDIR}/clang+llvm-x86_64-bootstrap/bin/clang \
  CXX=${BUILDDIR}/clang+llvm-x86_64-bootstrap/bin/clang++ \
  CXXFLAGS='-stdlib=libc++ -I${BUILDDIR}/clang+llvm-x86_64-bootstrap/include/c++/v1' \
  LDFLAGS='-L${BUILDDIR}/clang+llvm-x86_64-bootstrap/lib -Wl,-rpath,'"'"'$\\$$\$$\\$$\$$ORIGIN/../lib'"'"' -Wl,-z,origin' \
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

rm -rf ${BUILDDIR}/build-clang+llvm-x86_64-archlinux \
  && mkdir -p ${BUILDDIR}/build-clang+llvm-x86_64-archlinux
pushd ${BUILDDIR}/build-clang+llvm-x86_64-archlinux
cmake -GNinja \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_C_COMPILER=${BUILDDIR}/clang+llvm-x86_64-bootstrap/bin/clang \
  -DCMAKE_CXX_COMPILER=${BUILDDIR}/clang+llvm-x86_64-bootstrap/bin/clang++ \
  -DCMAKE_INSTALL_PREFIX=${PKGDIR} \
  -DCMAKE_INSTALL_RPATH='$ORIGIN/../lib' \
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

rm -rf ${BUILDDIR}/build-musl && mkdir -p ${BUILDDIR}/build-musl
pushd ${BUILDDIR}/build-musl
${SRCDIR}/musl/configure \
  CC=${BUILDDIR}/clang+llvm-x86_64-bootstrap/bin/clang \
  LIBCC=-lclang_rt.builtins-x86_64 \
  LDFLAGS=-L${PKGDIR}/lib/clang/3.8.0/lib/linux \
  --prefix=${PKGDIR} \
  --disable-wrapper
make install
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
