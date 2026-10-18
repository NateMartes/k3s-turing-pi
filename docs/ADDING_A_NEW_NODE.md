# Adding a New Node to the Cluster

1. On your machine, download a pre-installed Ubuntu image for your node:

   <https://joshua-riek.github.io/ubuntu-rockchip-download/boards/turing-rk1.html>

   Pick an `img.xz` file (the latest is `ubuntu-24.04-preinstalled-server-arm64-turing-rk1.img.xz`).

   *Note:* That is only for RK1s; you'll need a different `.img.xz` (or `.img`)
   file for other hardware.

   Also unpack it! (It will take time.)

   ```bash
   unxz /your/new.img.xz
   ```

2. Ensure your hardware is connected to your Turing Pi board.

3. Ensure your Turing Pi board has power.

4. Ensure your Turing Pi board has access to a network you can access.

   An example of this might be connecting an Ethernet cable to the board and your machine,
   then assigning an IP address to the connection so that you can reach the Turing Pi's BMC.

5. Find your Turing Pi:

   ```bash
   ping turingpi.local
   ```

   It should respond. It also might be `turing.local`.

6. Install the `tpi` tool on the same machine where you downloaded your OS image.

   You can do this with `cargo`:

   ```bash
   curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
   cargo install tpi
   ```

7. Test that you can reach your Turing Pi with `tpi`:

   ```bash
   tpi power status
   ```

   You should be prompted for the BMC credentials,
   which should be `username: root` and `password: turing`.

8. Power off the node (just in case):

   ```bash
   tpi power -n <node number> off
   ```

9. Flash the node:

   ```bash
   tpi flash -n <the node you put the hardware on> -i /your/new.img
   ```

10. Wait for it to fully finish.

11. Power the node on:

    ```bash
    tpi power -n <node number> on
    ```

12. SSH to the Turing Pi's BMC:

    ```bash
    ssh root@turingpi.local
    ```

    or:

    ```bash
    ssh root@turing.local
    ```

    The password is `turing`, or should be.

13. Connect to the new node over the serial port:

    ```bash
    picocom -b 115200 /dev/ttyS<node number>
    ```

14. Log in.

    Depending on your OS, it might be `ubuntu:ubuntu`.

15. Make the `sysadmin` user:

    ```bash
    sudo useradd -m -s /bin/bash sysadmin \
      && echo 'sysadmin:<password>' | sudo chpasswd \
      && sudo usermod -aG sudo sysadmin \
      && echo 'sysadmin ALL=(ALL:ALL) ALL' | sudo tee /etc/sudoers.d/sysadmin >/dev/null \
      && sudo chmod 440 /etc/sudoers.d/sysadmin
    ```

    It's probably a good idea to keep the passwords the same.

16. Sign out of the current user and log in as `sysadmin`.

17. Remove the original user:

    ```bash
    sudo pkill -u ubuntu
    sudo userdel -r ubuntu
    ```

    It might not be `ubuntu`.

18. Install and run SSH:

    ```bash
    sudo apt update && \
    sudo apt install -y openssh-client openssh-server && \
    sudo systemctl enable --now ssh
    ```

That's it! Now you can either start with this node as the first or go on an already existing node
and copy your SSH key to this system:

```bash
ssh-copy-id sysadmin@<node-ip>
```
