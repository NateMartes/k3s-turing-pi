# Adding a New Node to the Cluster

1. On your machine, download a pre-installed ubuntu image for your node
https:/joshua-riek.github.io/ubuntu-rockchip-download/boards/turing-rk1.html

Pick an `img.xz` file (the latest is `ubuntu-24.04-preinstalled-server-arm65-turing-rk1.img.xz`
*Note:* That is only for RK1s, you'll need a different `.img.xz` (or `.img`) file for other hardware

Also unpack it too! (will take time)
`unxz /your/new.img.xz`

2. Ensure your hardware is connected to your Turing Pi board

3. Ensure your Turing Pi board has power

4. Ensure your Turing Pi board has access to a network you can access.

An example of this might be connecting an ethernet cable to the board and your machine,
then assigning an IP address to the connection so that you can reach the Turing Pi's BMC.

5. Find your Turing Pi
`ping turingpi.local`

Should respond, it also might be `turing.local`.

7. Install the `tpi` tool on the same machine you downloaded the your OS image on.

You can do this with `cargo`

`curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh`
`cargo install tpi`

8. Test you can reach your Turing Pi with `tpi`

`tpi power status`

You should be prompted for the creds of the BMC
which should be: `username: root` and `password: turing`

9. Power off the node (just in case)
`tpi power -n <node number> off

10. Flash the node!
`tpi flash -n <the node you put the hardware on> -i /your/new.img

11. Wait for it to fully finish

12. Power the node on
`tpi power -n <node number> on

13. SSH to the Turing Pi's BMC
`ssh root@turingpi.local` or `ssh root@turing.local`

Password is `turing` or should be...

14. Connect to the new node over serial port

`picocom -b 115200 /dev/ttyS<node number>`

15. Log in!
Depending on your OS it might be `ubuntu:ubuntu`

16. Make the `sysadmin` user

```bash
sudo useradd -m -s /bin/bash sysadmin \
  && echo 'sysadmin:<password>' | sudo chpasswd \
  && sudo usermod -aG sudo sysadmin \
  && echo 'sysadmin ALL=(ALL:ALL) ALL' | sudo tee /etc/sudoers.d/sysadmin >/dev/null \
  && sudo chmod 440 /etc/sudoers.d/sysadmin
```

Its probably a good idea to keep the passwords the same...

17. Sign out of the current user and log in as sysadmin

18. Remove the original user
```bash
sudo pkill -u ubuntu
sudo userdel -r ubuntu
```

Might not be `ubuntu`

19. Install and run SSH
```bash
sudo apt update && \
sudo apt install -y openssh-client openssh-server && \
sudo systemctl enable --now ssh
```

Thats it! Now you can either start with this node as the first, or go on an already existing node
and copy your SSH key to this system:
```bash
ssh-copy-id sysadmin@<node-ip>
```

