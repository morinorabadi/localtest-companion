# Windows setup with Ubuntu in WSL 2

Use the Linux companion inside Ubuntu in WSL 2. Your coding agent can run in
Coder or in that Ubuntu distribution, and your browser can run on Windows.
The companion depends on Linux systemd, Python, SSH, and Mutagen; a native
PowerShell/CMD service implementation is not included.

## 1. Prepare WSL from Windows

In **PowerShell**, inspect existing distributions:

```powershell
wsl --status
wsl --list --verbose
```

If WSL/Ubuntu is not installed, open **PowerShell as Administrator** and run:

```powershell
wsl --install -d Ubuntu
```

Complete any required restart, launch Ubuntu, and create your normal Linux user.
If WSL needs updating, run `wsl --update` from PowerShell. Confirm the chosen
Ubuntu distribution shows `VERSION 2` in `wsl --list --verbose`. Use its actual
distribution name in subsequent commands; `Ubuntu` is the example name here.
Preserve an existing distro and its data instead of reinstalling it.

See Microsoft's [WSL installation guide](https://learn.microsoft.com/en-us/windows/wsl/install)
and [command reference](https://learn.microsoft.com/en-us/windows/wsl/basic-commands).

## 2. Check systemd inside Ubuntu

Open **Ubuntu in WSL** as your normal Linux user:

```bash
ps -p 1 -o comm=
systemctl --user show-environment >/dev/null
```

PID 1 should be `systemd`, and the second command must succeed. Current Ubuntu
WSL installations enable systemd by default; older ones may need configuration.

If required, edit `/etc/wsl.conf` using `sudoedit /etc/wsl.conf`. Merge this
setting into its existing `[boot]` section, preserving other sections/settings:

```ini
[boot]
systemd=true
```

After saving work in that distro, restart just that distro from **PowerShell**:

```powershell
wsl --terminate Ubuntu
wsl --distribution Ubuntu
```

Termination stops that distro's running apps. Recheck systemd after reopening.
If the user manager is still unavailable, inspect the Linux session and required
packages (`systemd`, `systemd-sysv`, `dbus-user-session`) before continuing. Do not
work around a missing user manager by running localtest as root.

Reference: Microsoft's [systemd instructions](https://learn.microsoft.com/en-us/windows/wsl/systemd).

## 3. Install Linux tools and the companion

Run **inside Ubuntu in WSL**, not in PowerShell or Git Bash:

```bash
sudo apt update
sudo apt install -y python3 git openssh-client curl ca-certificates
mkdir -p ~/src
git clone https://github.com/morinorabadi/localtest-companion.git ~/src/localtest-companion
cd ~/src/localtest-companion
bash companion/install.sh
export PATH="$HOME/.local/bin:$PATH"
localtest doctor
```

Install the **Linux Coder CLI inside WSL** using the
[official CLI instructions](https://coder.com/docs/install/cli). Then authenticate
and generate SSH configuration inside the same distro:

```bash
coder login https://YOUR-CODER-DEPLOYMENT
coder config-ssh --yes
coder list
ssh YOUR-WORKSPACE.coder true
```

Windows and WSL have separate home/config directories. An existing Windows Coder
login or SSH configuration does not establish the Linux setup above. Use Linux
Python/Node/package managers required by the app, and select their PATH before
`localtest add`. `command -v coder python3 ssh` helps identify the actual tools.

Keep the tool checkout, source mirrors, environments, and runtime data in the
Linux filesystem, such as `~/src`, `~/localtest`, and `~/.config/localtest`.
Microsoft recommends [Linux filesystem paths for Linux tools](https://learn.microsoft.com/en-us/windows/wsl/filesystems);
avoid placing these under `/mnt/c` or OneDrive-managed Windows folders.

## 4. Add Docker if the application needs it

For Docker Desktop, select its **WSL 2 engine** and enable **WSL Integration** for
your chosen Ubuntu distro. Keep Docker Desktop running while the app needs it.
Validate **inside WSL**:

```bash
docker info
docker compose version
```

Follow Docker's [WSL backend and distro integration instructions](https://docs.docker.com/desktop/features/wsl/).
This path assumes the WSL 2 backend with Linux filesystem access. Docker's
separate Docker VMM backend has different bind-mount restrictions; select the
WSL 2 backend for the Linux-home mirrors described here. Do not install a second
engine as part of the Docker Desktop integration setup. An independently managed
Linux Docker Engine is another option, with its own installation/service setup.

## 5. Configure the app and test from both sides

Complete the root README's [Coder broker](../README.md#1-prepare-coder),
[app registration](../README.md#3-register-your-app-on-ubuntu), and
[named-action bridge](../README.md#4-give-your-agent-access-to-results) steps.
All commands labeled Ubuntu run **inside WSL**. Remote source paths such as
`/home/coder/myapp` still refer to Coder, not Windows or the WSL mirror.

Start with the [Python smoke example](../examples/python-http/README.md).
After its HTTP probe succeeds inside WSL, open
`http://localhost:7088/hello.txt` in your **Windows browser**. Microsoft documents
[access to WSL networking apps through Windows localhost](https://learn.microsoft.com/en-us/windows/wsl/networking).
If Windows access fails, keep the loopback binding and diagnose WSL networking,
VPN/proxy, or firewall settings; a Coder browser is not a Windows-browser test.

The agent should verify all three independently: WSL source sync, a returned
WSL action result through the Coder bridge, and Windows browser reachability.
Treat example workspace names and paths as examples until actually discovered.

## Sessions, sleep, and reboot

Localtest services are enabled inside the distro. Windows startup does not
automatically mean that distro, its user manager, or Docker Desktop has started.
Microsoft notes that systemd services do not themselves keep a WSL instance
alive. Keep a WSL session running during local development; verify the bridge's
actual online status after closing terminals, sleeping, or rebooting Windows.

`loginctl enable-linger` concerns the Linux user manager; it does not arrange
Windows startup or keep the WSL virtual machine alive. A Windows login task or
other persistent-session arrangement is separate setup that should be requested
and tested explicitly. This guide does not install one silently.

On a later session, open Ubuntu and start Docker Desktop if needed, then inspect
`localtest status` and `localtest bridge status NAME`. Start/re-enable the desired
profile/bridge if necessary. `wsl --shutdown` stops every WSL distribution and
disconnects localtest; it is not a way to stop just one project.

## Verification status

The generic Linux installer, unit/bridge tests, and real Mutagen synchronization
test were checked in Coder. These Windows instructions are based on the linked
Microsoft, Docker, and Coder documentation. No end-to-end run on your coworker's
Windows/WSL machine has been observed; their setup agent must collect that proof.
