FROM ubuntu:24.04 AS node

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        ca-certificates \
        curl \
        dbus \
        git \
        iproute2 \
        iptables \
        iputils-ping \
        kmod \
        openssh-client \
        openssh-server \
        openssl \
        procps \
        python3 \
        python3-apt \
        python3-yaml \
        sudo \
        systemd \
        systemd-sysv \
    && useradd --create-home --shell /bin/bash ansible \
    && echo 'ansible:jihwija-test' | chpasswd \
    && printf 'ansible ALL=(ALL) NOPASSWD: ALL\n' > /etc/sudoers.d/ansible \
    && chmod 0440 /etc/sudoers.d/ansible \
    && install -d -m 0755 /etc/ssh/sshd_config.d \
    && printf '%s\n' \
        'PasswordAuthentication yes' \
        'PermitRootLogin prohibit-password' \
        'UsePAM yes' \
        > /etc/ssh/sshd_config.d/99-jihwija-test.conf \
    && systemctl enable ssh.service \
    && systemctl mask \
        dev-hugepages.mount \
        sys-fs-fuse-connections.mount \
        systemd-remount-fs.service \
    && truncate --size 0 /etc/machine-id \
    && rm -rf /var/lib/apt/lists/*

COPY generate-test-ssh-key /usr/local/sbin/generate-test-ssh-key
COPY node-entrypoint /usr/local/sbin/node-entrypoint

RUN chmod 0755 \
    /usr/local/sbin/generate-test-ssh-key \
    /usr/local/sbin/node-entrypoint

ENV container=docker

STOPSIGNAL SIGRTMIN+3
ENTRYPOINT ["/usr/local/sbin/node-entrypoint"]
CMD ["/sbin/init"]

FROM ubuntu:24.04 AS operator

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        ansible-core \
        ca-certificates \
        openssh-client \
        sshpass \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace/tests/test-env
CMD ["sleep", "infinity"]
