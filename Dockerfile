ARG FEDORA_VERSION=43
ARG CUDA_IMAGE=nvcr.io/nvidia/cuda:13.3.1-base-ubi9

# Only used to ship the NGC DL license file, as the upstream images do.
FROM ${CUDA_IMAGE} AS cuda

FROM fedora:${FEDORA_VERSION} AS build

ARG TARGETARCH
ARG GOLANG_VERSION=1.27.2

# Arg to indicate if driver type is either of passthrough/baremetal or vgpu
ARG DRIVER_TYPE=passthrough

SHELL ["/bin/bash", "-c"]

RUN dnf install -y --setopt=install_weak_deps=False git-core tar gzip && dnf clean all

# download appropriate binary based on the target architecture for multi-arch builds
RUN OS_ARCH=${TARGETARCH/x86_64/amd64} && OS_ARCH=${OS_ARCH/aarch64/arm64} && \
    curl -fsSL https://go.dev/dl/go${GOLANG_VERSION}.linux-${OS_ARCH}.tar.gz \
    | tar -C /usr/local -xz

ENV PATH=/usr/local/go/bin:$PATH

WORKDIR /work

# vgpu-util is only needed for vGPU guests; keep the stage cheap otherwise.
RUN touch /work/vgpu-util.placeholder && \
    if [ "$DRIVER_TYPE" = "vgpu" ]; then \
    git clone --depth 1 https://github.com/NVIDIA/gpu-driver-container driver && \
    cd driver/vgpu/src && \
    go build -o vgpu-util && \
    mv vgpu-util /work; fi

FROM fedora:${FEDORA_VERSION}

ARG TARGETARCH
ENV TARGETARCH=$TARGETARCH

ARG HTTP_PROXY
ENV HTTP_PROXY=$HTTP_PROXY
ARG HTTPS_PROXY
ENV HTTPS_PROXY=$HTTPS_PROXY

SHELL ["/bin/bash", "-c"]

#ARG BASE_URL=http://us.download.nvidia.com/XFree86/Linux-x86_64
ARG BASE_URL=https://us.download.nvidia.com/tesla
ENV BASE_URL=${BASE_URL}
ARG DRIVER_VERSION
ENV DRIVER_VERSION=$DRIVER_VERSION
# Major version of the driver (e.g. 595), used to pick the kernel module type
ARG DRIVER_BRANCH
ENV DRIVER_BRANCH=$DRIVER_BRANCH
ARG GIT_COMMIT

# Arg to indicate if driver type is either of passthrough/baremetal or vgpu
ARG DRIVER_TYPE=passthrough
ENV DRIVER_TYPE=$DRIVER_TYPE
ARG VGPU_LICENSE_SERVER_TYPE=NLS
ENV VGPU_LICENSE_SERVER_TYPE=$VGPU_LICENSE_SERVER_TYPE
# Enable vGPU version compability check by default
ARG DISABLE_VGPU_VERSION_CHECK=true
ENV DISABLE_VGPU_VERSION_CHECK=$DISABLE_VGPU_VERSION_CHECK
# Avoid dependency of container-toolkit for driver container
ENV NVIDIA_VISIBLE_DEVICES=void

RUN test -n "$DRIVER_VERSION" || { echo "DRIVER_VERSION build arg is required" >&2; exit 1; }

ADD install.sh /tmp/

RUN sh /tmp/install.sh depinstall && \
    curl -fsSL -o /usr/local/bin/donkey https://github.com/3XX0/donkey/releases/download/v1.1.0/donkey && \
    curl -fsSL -o /usr/local/bin/extract-vmlinux https://raw.githubusercontent.com/torvalds/linux/master/scripts/extract-vmlinux && \
    chmod +x /usr/local/bin/donkey /usr/local/bin/extract-vmlinux && \
    ln -s /sbin/ldconfig /sbin/ldconfig.real

ADD drivers drivers/

# Fetch the installer automatically for passthrough/baremetal types
RUN if [ "$DRIVER_TYPE" != "vgpu" ]; then \
    cd drivers && \
    DRIVER_ARCH=${TARGETARCH/amd64/x86_64} && DRIVER_ARCH=${DRIVER_ARCH/arm64/aarch64} && \
    curl -fsSL -O $BASE_URL/$DRIVER_VERSION/NVIDIA-Linux-$DRIVER_ARCH-$DRIVER_VERSION.run && \
    chmod +x  NVIDIA-Linux-$DRIVER_ARCH-$DRIVER_VERSION.run; fi

COPY nvidia-driver /usr/local/bin

WORKDIR /usr/src/nvidia-$DRIVER_VERSION

COPY common.sh /usr/local/bin

COPY --from=build /work/vgpu-util* /usr/local/bin/

WORKDIR /drivers

ARG PUBLIC_KEY=empty
COPY ${PUBLIC_KEY} kernel/pubkey.x509

ARG PRIVATE_KEY
ARG KERNEL_VERSION=latest

ARG FEDORA_VERSION
ARG BUILD_TIMESTAMP

LABEL io.k8s.display-name="NVIDIA Driver Container"
LABEL name="NVIDIA Driver Container"
LABEL vendor="NVIDIA"
LABEL version="${DRIVER_VERSION}"
LABEL release="N/A"
LABEL summary="Provision the NVIDIA driver through containers"
LABEL description="Provision the NVIDIA driver through containers on Fedora ${FEDORA_VERSION}"
LABEL org.opencontainers.image.base.name="registry.fedoraproject.org/fedora:${FEDORA_VERSION}"
LABEL org.opencontainers.image.created="${BUILD_TIMESTAMP}"
LABEL org.opencontainers.image.revision="${GIT_COMMIT}"
LABEL org.opencontainers.image.version="${DRIVER_VERSION}-fedora${FEDORA_VERSION}"
LABEL org.opencontainers.image.licenses="Apache-2.0"

# Add NGC DL license from the CUDA image
COPY --from=cuda /NGC-DL-CONTAINER-LICENSE /licenses/NGC-DL-CONTAINER-LICENSE

# Install / upgrade packages here that are required to resolve CVEs
ARG CVE_UPDATES
RUN if [ -n "${CVE_UPDATES}" ]; then \
        dnf update -y ${CVE_UPDATES} && \
        dnf clean all; \
    fi

ENTRYPOINT ["nvidia-driver", "init"]
