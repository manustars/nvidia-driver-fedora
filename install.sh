#!/bin/bash

set -eu

DRIVER_ARCH=${TARGETARCH/amd64/x86_64} && DRIVER_ARCH=${DRIVER_ARCH/arm64/aarch64}
echo "DRIVER_ARCH is $DRIVER_ARCH"

# Packages needed at runtime to unpack the kernel RPMs, build the kernel
# modules, extract the kernel version string and load the modules.
COMMON_PACKAGES="
    libglvnd-glx
    ca-certificates
    curl
    gcc
    make
    binutils
    elfutils-libelf
    elfutils-libelf-devel
    cpio
    rpm
    kmod
    jq
    util-linux
    findutils
    procps-ng
    which
    diffutils
    gzip
    bzip2
    xz
    zstd
    lz4
    pciutils
    "

dep_installer () {
  if [ "$DRIVER_ARCH" = "x86_64" ]; then
    dnf install -y --setopt=install_weak_deps=False $COMMON_PACKAGES glibc.i686
  elif [ "$DRIVER_ARCH" = "aarch64" ]; then
    dnf install -y --setopt=install_weak_deps=False $COMMON_PACKAGES glibc
  else
    echo "DRIVER_ARCH doesn't match a known arch target"
    exit 1
  fi
  dnf clean all
}

nvidia_installer () {
  if [ "$DRIVER_ARCH" = "x86_64" ]; then
    ./nvidia-installer --silent \
                       --no-kernel-module \
                       --install-compat32-libs \
                       --no-nouveau-check \
                       --no-nvidia-modprobe \
                       --no-rpms \
                       --no-backup \
                       --no-check-for-alternate-installs \
                       --no-libglx-indirect \
                       --no-install-libglvnd \
                       --x-prefix=/tmp/null \
                       --x-module-path=/tmp/null \
                       --x-library-path=/tmp/null \
                       --x-sysconfig-path=/tmp/null
  elif [ "$DRIVER_ARCH" = "aarch64" ]; then
    ./nvidia-installer --silent \
                       --no-kernel-module \
                       --no-nouveau-check \
                       --no-nvidia-modprobe \
                       --no-rpms \
                       --no-backup \
                       --no-check-for-alternate-installs \
                       --no-libglx-indirect \
                       --no-install-libglvnd \
                       --x-prefix=/tmp/null \
                       --x-module-path=/tmp/null \
                       --x-library-path=/tmp/null \
                       --x-sysconfig-path=/tmp/null
  else
    echo "DRIVER_ARCH doesn't match a known arch target"
    exit 1
  fi
}

if [ "$1" = "nvinstall" ]; then
  nvidia_installer
elif [ "$1" = "depinstall" ]; then
  dep_installer
else
  echo "Unknown function: $1"
  exit 1
fi
