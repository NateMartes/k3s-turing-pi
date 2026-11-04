If you are adding a Jetson Orion to your cluster, then things will be different than just adding
a RK1...
Follow this gist instead to install everything you need:
https://gist.github.com/NateMartes/7f7eeda60f5954b3d05569183124f839

You will have to do this after you have set up your Jetson, and changed the hostname too:

```bash
echo 'sysadmin ALL=(ALL:ALL) NOPASSWD: ALL' | sudo tee /etc/sudoers.d/sysadmin >/dev/null \
  && sudo chmod 440 /etc/sudoers.d/sysadmin
```

If you don't have internet, here is a Github gist, as of 11/4/2026. See the link above for the latest version:

```bash
#!/usr/bin/env bash

# Kubernetes-ready NVIDIA Jetson Orin NX/Nano flashing for
# Jetson Linux 39.2.0 / JetPack 7.2 on a Turing Pi 2.5/2.5.2
#
# Updated from dudo's original Jetson 36.x gist:
# https://gist.github.com/dudo/4093b5d14f2b003cad507e4f4ac1aa83
#
# IMPORTANT:
# - Do not run this entire file from top to bottom.
# - Run each section on the machine named in its heading.
# - The flash command uses --erase-all and ERASES THE JETSON NVMe.
# - The correct R39.2 source tag is jetson_39.2_GA.


###############################################################################
# FROM THE UBUNTU FLASH HOST
###############################################################################

sudo apt update

sudo apt install -y \
  qemu-user-static \
  git-core \
  make \
  build-essential \
  bc \
  flex \
  bison \
  libssl-dev \
  zstd \
  gcc-aarch64-linux-gnu \
  nfs-kernel-server \
  openssh-client \
  wget

# Use a new directory for R39.2.
export NVIDIA_DIR="$HOME/nvidia-r39.2"

mkdir -p "$NVIDIA_DIR"
cd "$NVIDIA_DIR"


###############################################################################
# OPTIONAL: NFS WORKAROUND ON THE UBUNTU FLASH HOST
###############################################################################

# Initrd flashing uses NFS and SSH over the fc00:1:1::/48 IPv6 range.
#
# If the flasher reports NFS negotiation problems, edit:
#
#   sudoedit /etc/default/nfs-kernel-server
#
# Set:
#
#   RPCMOUNTDOPTS="--manage-gids --no-nfs-version 4"
#
# Then restart NFS:
#
#   sudo systemctl restart nfs-kernel-server
#
# Also ensure that the host firewall permits fc00:1:1::/48.


###############################################################################
# DOWNLOAD JETSON LINUX 39.2.0
###############################################################################

cd "$NVIDIA_DIR"

wget -c -O bsp.tbz2 \
  'https://developer.nvidia.com/downloads/embedded/L4T/r39_Release_v2.0/release/Jetson_Linux_R39.2.0_aarch64.tbz2'

wget -c -O rootfs.tbz2 \
  'https://developer.nvidia.com/downloads/embedded/L4T/r39_Release_v2.0/release/Tegra_Linux_Sample-Root-Filesystem_R39.2.0_aarch64.tbz2'


###############################################################################
# EXTRACT THE BSP AND ROOT FILESYSTEM
###############################################################################

cd "$NVIDIA_DIR"

tar -xpf bsp.tbz2

sudo tar -xpf rootfs.tbz2 \
  -C "$NVIDIA_DIR/Linux_for_Tegra/rootfs/"


###############################################################################
# TURING PI CARRIER-BOARD EEPROM WORKAROUND
###############################################################################

# Turing Pi does not provide the carrier-board EEPROM expected by the NVIDIA
# reference carrier configuration.

sed -i \
  's/cvb_eeprom_read_size = <0x100>/cvb_eeprom_read_size = <0x0>/g' \
  "$NVIDIA_DIR/Linux_for_Tegra/bootloader/generic/BCT/tegra234-mb2-bct-misc-p3767-0000.dts"

grep 'cvb_eeprom_read_size' \
  "$NVIDIA_DIR/Linux_for_Tegra/bootloader/generic/BCT/tegra234-mb2-bct-misc-p3767-0000.dts"

# Expected:
#
#   cvb_eeprom_read_size = <0x0>;


###############################################################################
# APPLY NVIDIA BINARIES AND FLASH PREREQUISITES
###############################################################################

cd "$NVIDIA_DIR/Linux_for_Tegra"

sudo ./apply_binaries.sh
sudo ./tools/l4t_flash_prerequisites.sh


###############################################################################
# CREATE THE DEFAULT HEADLESS USER
###############################################################################

read -rp 'Jetson username: ' JETSON_USER
read -rsp 'Jetson password: ' JETSON_PASSWORD
echo
read -rp 'Jetson hostname [jetson1]: ' JETSON_HOSTNAME

JETSON_HOSTNAME="${JETSON_HOSTNAME:-jetson1}"

sudo ./tools/l4t_create_default_user.sh \
  --accept-license \
  -u "$JETSON_USER" \
  -p "$JETSON_PASSWORD" \
  -a \
  -n "$JETSON_HOSTNAME"

unset JETSON_PASSWORD


###############################################################################
# DOWNLOAD THE CORRECT R39.2 KERNEL SOURCES
###############################################################################

cd "$NVIDIA_DIR/Linux_for_Tegra/source"

./source_sync.sh -k -t jetson_39.2_GA


###############################################################################
# VERIFY THE SOURCE CHECKOUT
###############################################################################

git -C kernel/kernel-noble describe --tags --exact-match
test -f kernel/kernel-noble/scripts/Makefile.defconf

# Expected tag:
#
#   jetson_39.2_GA
#
# If this reports jetson_38.2, the old checkout was not replaced. Move it aside:
#
#   cd "$NVIDIA_DIR/Linux_for_Tegra/source"
#   mv kernel/kernel-noble "$NVIDIA_DIR/kernel-noble-r38-backup"
#   ./source_sync.sh -k -t jetson_39.2_GA
#
# Then verify again:
#
#   git -C kernel/kernel-noble describe --tags --exact-match
#   test -f kernel/kernel-noble/scripts/Makefile.defconf
#
# source_sync.sh may print:
#
#   fatal: not a git repository
#
# for the top-level source directory. That message is not fatal by itself.
# The kernel/kernel-noble checkout must still complete successfully.


###############################################################################
# CONFIGURE THE R39.2 KERNEL
###############################################################################

cd "$NVIDIA_DIR/Linux_for_Tegra/source"

export ARCH=arm64
export CROSS_COMPILE=aarch64-linux-gnu-
export LOCALVERSION=-tegra
export KERNEL_SRC="$PWD/kernel/kernel-noble"
export INSTALL_MOD_PATH="$PWD/../rootfs"

make -C "$KERNEL_SRC" defconfig

"$KERNEL_SRC/scripts/config" --file "$KERNEL_SRC/.config" \
  --enable BPF \
  --enable BPF_SYSCALL \
  --enable CGROUPS \
  --enable BLK_CGROUP \
  --enable NET_SCHED \
  --enable NET_CLS_ACT \
  --enable NETFILTER \
  --enable NETFILTER_ADVANCED \
  --enable NETFILTER_XTABLES \
  --enable NF_CONNTRACK \
  --enable IP_VS \
  --enable XFRM \
  --module NET_CLS_BPF \
  --enable BLK_DEV_THROTTLING \
  --module NET_CLS_CGROUP \
  --enable CGROUP_NET_PRIO \
  --module IP_SET \
  --enable IP_VS_NFCT \
  --enable IP_VS_PROTO_TCP \
  --enable IP_VS_PROTO_UDP \
  --module IP_VS_RR \
  --module CRYPTO_SEQIV \
  --enable XFRM_USER \
  --module INET_ESP \
  --module NETFILTER_XT_TARGET_TPROXY \
  --module NETFILTER_XT_MATCH_MARK \
  --module NETFILTER_XT_MATCH_SOCKET

make -C "$KERNEL_SRC" olddefconfig


###############################################################################
# VERIFY THE KERNEL CONFIGURATION
###############################################################################

for option in \
  NET_CLS_BPF \
  BLK_DEV_THROTTLING \
  NET_CLS_CGROUP \
  CGROUP_NET_PRIO \
  IP_SET \
  IP_VS_NFCT \
  IP_VS_PROTO_TCP \
  IP_VS_PROTO_UDP \
  IP_VS_RR \
  CRYPTO_SEQIV \
  XFRM_USER \
  INET_ESP \
  NETFILTER_XT_TARGET_TPROXY \
  NETFILTER_XT_MATCH_MARK \
  NETFILTER_XT_MATCH_SOCKET
do
  if grep -qE "^CONFIG_${option}=(y|m)$" "$KERNEL_SRC/.config"; then
    grep -E "^CONFIG_${option}=" "$KERNEL_SRC/.config"
  else
    echo "FAIL: CONFIG_${option} is not enabled"
    exit 1
  fi
done


###############################################################################
# BUILD THE KERNEL AND IN-TREE MODULES
###############################################################################

cd "$NVIDIA_DIR/Linux_for_Tegra/source"

# Cache sudo credentials before the long build/install.
sudo -v

make -C "$KERNEL_SRC" \
  -j"$(nproc)" \
  Image modules

sudo make -C "$KERNEL_SRC" \
  ARCH="$ARCH" \
  CROSS_COMPILE="$CROSS_COMPILE" \
  LOCALVERSION="$LOCALVERSION" \
  INSTALL_MOD_PATH="$INSTALL_MOD_PATH" \
  modules_install

cp "$KERNEL_SRC/arch/arm64/boot/Image" \
  "$NVIDIA_DIR/Linux_for_Tegra/kernel/Image"


###############################################################################
# BUILD AND INSTALL NVIDIA OUT-OF-TREE MODULES
###############################################################################

cd "$NVIDIA_DIR/Linux_for_Tegra/source"

export KERNEL_HEADERS="$KERNEL_SRC"
export kernel_name=noble

# This executes many NVIDIA conftest probes.
# Do not interrupt it just because it appears quiet.

make -j"$(nproc)" modules
sudo make \
  ARCH="$ARCH" \
  CROSS_COMPILE="$CROSS_COMPILE" \
  LOCALVERSION="$LOCALVERSION" \
  INSTALL_MOD_PATH="$INSTALL_MOD_PATH" \
  KERNEL_HEADERS="$KERNEL_HEADERS" \
  kernel_name="$kernel_name" \
  modules_install


###############################################################################
# REGENERATE THE INITRD
###############################################################################

cd "$NVIDIA_DIR/Linux_for_Tegra"

sudo ./tools/l4t_update_initrd.sh


###############################################################################
# VALIDATE EVERYTHING BEFORE FLASHING
###############################################################################

cd "$NVIDIA_DIR/Linux_for_Tegra/source"

KERNEL_RELEASE="$(
  make -s -C "$KERNEL_SRC" \
    ARCH=arm64 \
    LOCALVERSION=-tegra \
    kernelrelease
)"

echo "Kernel release: $KERNEL_RELEASE"

test -f "$KERNEL_SRC/arch/arm64/boot/Image" \
  && echo "PASS: kernel Image exists" \
  || echo "FAIL: kernel Image does not exist"

cmp -s \
  "$KERNEL_SRC/arch/arm64/boot/Image" \
  "$NVIDIA_DIR/Linux_for_Tegra/kernel/Image" \
  && echo "PASS: Image copied into BSP" \
  || echo "FAIL: BSP Image does not match"

test -d "$INSTALL_MOD_PATH/lib/modules/$KERNEL_RELEASE" \
  && echo "PASS: modules installed into rootfs" \
  || echo "FAIL: modules missing from rootfs"

test -f "$INSTALL_MOD_PATH/boot/initrd" \
  && echo "PASS: initrd exists" \
  || echo "FAIL: initrd is missing"

for option in \
  NET_CLS_BPF \
  BLK_DEV_THROTTLING \
  NET_CLS_CGROUP \
  CGROUP_NET_PRIO \
  IP_SET \
  IP_VS_NFCT \
  IP_VS_PROTO_TCP \
  IP_VS_PROTO_UDP \
  IP_VS_RR \
  CRYPTO_SEQIV \
  XFRM_USER \
  INET_ESP \
  NETFILTER_XT_TARGET_TPROXY \
  NETFILTER_XT_MATCH_MARK \
  NETFILTER_XT_MATCH_SOCKET
do
  grep -qE "^CONFIG_${option}=(y|m)$" "$KERNEL_SRC/.config" \
    && echo "PASS: CONFIG_${option}" \
    || echo "FAIL: CONFIG_${option}"
done

# Do not flash until every required check passes.


###############################################################################
# OPTIONAL BSP BACKUP
###############################################################################

# This requires a considerable amount of free disk space.
#
# sudo cp -a \
#   "$NVIDIA_DIR/Linux_for_Tegra" \
#   "$NVIDIA_DIR/Linux_for_Tegra_SYNCED"


###############################################################################
# CONNECT THE TURING PI TO THE UBUNTU FLASH HOST
###############################################################################

# Turing Pi 2.5/2.5.2:
#
# Connect a known-good USB data cable between:
#
#   1. The Ubuntu flash host.
#   2. The rear USB-C port labeled USB_OTG on the Turing Pi.
#
# The rear USB-A port is not the flash port on Turing Pi 2.5.
# Do not use the BMC management USB connection.


###############################################################################
# FROM THE TURING PI BMC
###############################################################################

# Replace 4 with the node containing the Jetson.
#
# Depending on the installed tpi version, use one of the following forms.

tpi power off --node 4
tpi usb flash --node 4
tpi power on --node 4


###############################################################################
# FROM THE UBUNTU FLASH HOST: VERIFY FORCED-RECOVERY MODE
###############################################################################

lsusb | grep -iE '0955|nvidia'

# Do not continue unless an NVIDIA APX/recovery device appears.

###############################################################################
# FROM THE UBUNTU FLASH HOST: FLASH QSPI AND NVMe
###############################################################################

# WARNING: --erase-all erases the target Jetson NVMe.

cd "$NVIDIA_DIR/Linux_for_Tegra"

sudo ./tools/kernel_flash/l4t_initrd_flash.sh \
  --external-device nvme0n1p1 \
  -p "-c ./bootloader/generic/cfg/flash_t234_qspi.xml" \
  -c ./tools/kernel_flash/flash_l4t_t234_nvme.xml \
  --showlogs \
  --network usb0 \
  --erase-all \
  jetson-orin-nano-devkit external

# Wait for an explicit successful completion message.
#
# Do not add --flash-only on the initial flash.
# Do not use flash_l4t_external.xml from the old gist.
# The R39.2 NVMe configuration is flash_l4t_t234_nvme.xml.
# The final root device argument is external.


###############################################################################
# USB TIMEOUT RECOVERY ON THE UBUNTU FLASH HOST
###############################################################################

# If the flash fails near:
#
#   Sending mb2_applet
#   ERROR: might be timeout in USB write
#   cvm.bin does not exist
#
# temporarily disable USB autosuspend:

# echo -1 | sudo tee /sys/module/usbcore/parameters/autosuspend

# If it still fails, you need a better usb cable...
# Avoid hubs, docks, smart cables, and virtual machines where possible.


###############################################################################
# FROM THE UBUNTU FLASH HOST: CONNECT AFTER FIRST BOOT
###############################################################################

# Use the username and hostname selected earlier:
#
# ssh-copy-id USERNAME@HOSTNAME.local
# ssh USERNAME@HOSTNAME.local
#
# Example:
#
# ssh-copy-id ubuntu@jetson1.local
# ssh ubuntu@jetson1.local
#
# If mDNS does not work, use the IP address assigned by DHCP.


###############################################################################
# FROM THE JETSON: VERIFY THE RUNNING CUSTOM KERNEL
###############################################################################

uname -r
cat /etc/nv_tegra_release

# Expected kernel:
#
#   6.8.12-tegra
#
# Expected L4T release:
#
#   R39, revision 2.0

for option in \
  NET_CLS_BPF \
  BLK_DEV_THROTTLING \
  NET_CLS_CGROUP \
  CGROUP_NET_PRIO \
  IP_SET \
  IP_VS_NFCT \
  IP_VS_PROTO_TCP \
  IP_VS_PROTO_UDP \
  IP_VS_RR \
  CRYPTO_SEQIV \
  XFRM_USER \
  INET_ESP \
  NETFILTER_XT_TARGET_TPROXY \
  NETFILTER_XT_MATCH_MARK \
  NETFILTER_XT_MATCH_SOCKET
do
  zgrep -E "^CONFIG_${option}=(y|m)$" /proc/config.gz \
    || echo "FAIL: CONFIG_${option}"
done


###############################################################################
# FROM THE JETSON: VERIFY LOADABLE KERNEL MODULES
###############################################################################

sudo modprobe cls_bpf
sudo modprobe cls_cgroup
sudo modprobe ip_set
sudo modprobe ip_vs_rr
sudo modprobe esp4
sudo modprobe xt_TPROXY
sudo modprobe xt_mark
sudo modprobe xt_socket

sudo dmesg --level=err,warn | tail -n 50


###############################################################################
# FROM THE JETSON: CUDA / JETPACK WARNING
###############################################################################

# Do not immediately run:
#
#   sudo apt upgrade
#
# Do not blindly install:
#
#   sudo apt install nvidia-jetpack
#
# The current NVIDIA repository may select R39.2.1 and replace the custom
# R39.2.0 kernel, DTBs, bootloader, initrd, and modules.
#
# First inspect the proposed CUDA-only transaction:

sudo apt update
apt-get -s install nvidia-cuda-dev

# Inspect the output for upgrades to:
#
#   nvidia-l4t-kernel
#   nvidia-l4t-kernel-dtbs
#   nvidia-l4t-bootloader
#   nvidia-l4t-initrd
#   nvidia-l4t-core
#
# If any of those BSP packages will be upgraded from R39.2.0 to R39.2.1,
# stop. Port the custom kernel to R39.2.1 or pin the entire R39.2.0 package
# set before proceeding.
#
# If the simulation only adds compatible CUDA userspace packages:

sudo apt install -y nvidia-cuda-dev

nvcc --version
nvidia-smi

###############################################################################
# FROM THE JETSON: CONFIGURE CUDA ENV
###############################################################################

sudo tee /etc/profile.d/cuda.sh > /dev/null <<'EOF'
export CUDA_HOME=/usr/local/cuda
export PATH="$CUDA_HOME/bin:$PATH"
export LD_LIBRARY_PATH="$CUDA_HOME/lib64:${LD_LIBRARY_PATH:-}"
export CUDACXX="$CUDA_HOME/bin/nvcc"
EOF

sudo chmod 644 /etc/profile.d/cuda.sh
source /etc/profile.d/cuda.sh

###############################################################################
# FROM THE JETSON: INSTALL AND RUN CUDA DEVICEQUERY
###############################################################################

# CUDA Samples now uses cpp/ and CMake.
# The old Samples/1_Utilities/deviceQuery Makefile no longer exists.

sudo apt install -y git cmake build-essential

cd "$HOME"

git clone \
  --branch v13.2update \
  --depth 1 \
  https://github.com/NVIDIA/cuda-samples.git

cd "$HOME/cuda-samples"

cmake \
  -S cpp/1_Utilities/deviceQuery \
  -B build-deviceQuery \
  -DCMAKE_CUDA_ARCHITECTURES=87

cmake --build build-deviceQuery -j"$(nproc)"

./build-deviceQuery/deviceQuery

# Expected final line:
#
#   Result = PASS


###############################################################################
# FROM THE JETSON: INSTALL CONTAINERD AND NVIDIA CONTAINER TOOLKIT
###############################################################################

sudo apt-get update

sudo apt-get install -y --no-install-recommends \
  ca-certificates \
  curl \
  gnupg2 \
  containerd \
  runc

curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey |
  sudo gpg --dearmor \
    -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

curl -sL \
  https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list |
  sed \
    's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' |
  sudo tee \
    /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit

sudo nvidia-ctk runtime configure --runtime=containerd
sudo systemctl restart containerd

nvidia-container-runtime --version
sudo systemctl --no-pager --full status containerd

# If Docker is used instead of containerd:
#
# sudo nvidia-ctk runtime configure --runtime=docker
# sudo systemctl restart docker


###############################################################################
# FROM THE JETSON: INSTALL JTOP
###############################################################################

# This installer avoids Ubuntu 24.04's externally-managed Python restriction.

sudo -v

curl -LsSf \
  https://raw.githubusercontent.com/rbonghi/jetson_stats/master/scripts/install_jtop_torun_without_sudo.sh |
  bash

sudo reboot


###############################################################################
# FROM THE JETSON: FINAL VERIFICATION AFTER REBOOT
###############################################################################

printf 'Kernel: '
uname -r

printf 'L4T: '
head -n 1 /etc/nv_tegra_release

printf 'CUDA: '
nvcc --version | grep 'release'

printf 'GPU: '
nvidia-smi --query-gpu=name --format=csv,noheader

printf 'NVIDIA container runtime: '
nvidia-container-runtime --version | head -n 1

printf 'containerd: '
systemctl is-active containerd

"$HOME/cuda-samples/build-deviceQuery/deviceQuery"

jtop

# Expected:
#
#   Kernel: 6.8.12-tegra
#   L4T: R39 revision 2.0
#   CUDA: release 13.2
#   GPU detected
#   NVIDIA container runtime installed
#   containerd: active
#   deviceQuery: Result = PASS
```
