> [!CAUTION]
> **`hxxps[://]protontricks[.]com` IS A FAKE SITE** and not affiliated with any of the Protontricks developers. https://github.com/Matoking/protontricks is the only official page for Protontricks.

Protontricks
============

[![image](https://img.shields.io/pypi/v/protontricks.svg)](https://pypi.org/project/protontricks/)
[![Coverage Status](https://coveralls.io/repos/github/Matoking/protontricks/badge.svg?branch=master)](https://coveralls.io/github/Matoking/protontricks?branch=master)
[![Test Status](https://github.com/Matoking/protontricks/actions/workflows/tests.yml/badge.svg)](https://github.com/Matoking/protontricks/actions/workflows/tests.yml)

[<img width="240" src="https://flathub.org/assets/badges/flathub-badge-en.png">](https://flathub.org/apps/details/com.github.Matoking.protontricks)

Run Winetricks commands for Steam Play/Proton games among other common Wine features, such as launching external Windows executables.

This is a fork of the original project created by sirmentio. The original repository is available at [Sirmentio/protontricks](https://github.com/Sirmentio/protontricks).

# Table of Contents
 - [What is it](#what-is-it)
 - [Requirements](#requirements)
 - [Usage](#usage)
   - [Command-line](#command-line)
   - [Desktop](#desktop) 
 - [Troubleshooting](#troubleshooting)
 - [Installation](#installation)
   - [Community packages](#community-packages-recommended)
   - [Flatpak](#flatpak-recommended)
   - [pipx](#pipx)
   - [pip](#pip-not-recommended)

# What is it?

This is a wrapper script that allows you to easily run Winetricks commands for Steam Play/Proton games among other common Wine features, such as launching external Windows executables. This is often useful when a game requires closed-source runtime libraries or applications that are not included with Proton.

# Requirements

* Python 3.7 or newer
* Winetricks
* Steam
* YAD (recommended) **or** Zenity. Required for GUI.

# Usage

**Protontricks can be launched from desktop or using the `protontricks` command.**

## Command-line

The basic command-line usage is as follows:

```
# Find your game's App ID by searching for it
protontricks -s <GAME NAME>

# or by listing all games
protontricks -l

# Run winetricks for the game.
# Any parameters in <ACTIONS> are passed directly to Winetricks.
# Parameters specific to Protontricks need to be placed *before* <APPID>.
protontricks <APPID> <ACTIONS>

# Run a custom command for selected game
protontricks -c <COMMAND> <APPID>

# Run the Protontricks GUI
protontricks --gui

# Pass arguments to Winetricks when using the Protontricks GUI.
# Everything after "--" is passed directly to Winetricks.
protontricks --gui -- <WINETRICKS_ARGUMENTS>

# Launch a Windows program (executable or command) using Protontricks
protontricks-launch <PROGRAM>

# Launch a Windows program for a specific Steam app using Protontricks
protontricks-launch --appid <APPID> <PROGRAM>

# Print the Protontricks help message
protontricks --help
```

Since this is a wrapper, all commands that work for Winetricks will likely work for Protontricks as well.

If you have a different Steam directory, you can export ``$STEAM_DIR`` to the directory where Steam is.

If you'd like to use a local version of Winetricks, you can set ``$WINETRICKS`` to the location of your local winetricks installation.

You can also set ``$PROTON_VERSION`` to a specific Proton version manually. This is usually the name of the Proton installation without the revision version number. For example, if Steam displays the name as `Proton 5.0-3`, use `Proton 5.0` as the value for `$PROTON_VERSION`.

Protontricks supports `$STEAM_COMPAT_DATA_PATH` variable to set a custom path to a Wine prefix (`WINEPREFIX=$STEAM_COMPAT_DATA_PATH/pfx`). This is supported by Proton and can be set for the game itself under Steam (`STEAM_COMPAT_DATA_PATH=<path> %command%` in game launch options).

[Wanna see Protontricks in action?](https://asciinema.org/a/229323)

## Multi-disc CD/DVD manager (optional CDEmu integration)

The Protontricks GUI provides **Manage CD/DVD drives (CDEmu)** after
selecting a Steam game or a non-Steam installer shortcut. The manager uses
the *selected game's existing Proton prefix* automatically; no AppID needs
to be entered manually.

### Requirements

- CDEmu daemon and `cdemu-client` (`cdemu` command), configured and running.
- `udisksctl` and `findmnt` available in the host environment.
- A YAD or Zenity graphical dialog provider.
- Access to the disc images and CD/DVD device files. In a Flatpak sandbox,
  filesystem/device restrictions may prevent managing host CDEmu readers.

### Workflow

1. **Mount Disc 1 with CDEmu first** (using gCDEmu or the CDEmu CLI), and
   verify the Windows setup executable is visible in the mounted directory.
2. In Steam, add that executable (for example `setup.exe`) as a **non-Steam
   game shortcut**, enable Proton compatibility for the shortcut, and launch
   it through Steam at least once to start installation and create a prefix.
3. When the installer asks for Disc 2, **leave the installer open** and open
   `protontricks --gui`. Select the **same Steam installer shortcut**, then
   choose **Manage CD/DVD drives (CDEmu)**.
4. Select the Windows drive letter required by the installer (usually `D:`).
   The main menu lists the CDEmu readers plus **Add virtual reader** and,
   when the last reader is 2 or higher, **Remove last virtual reader
   (reader N)**. Selecting a reader
   offers only **Load or replace disc image** (native image picker),
   **Eject disc**, **Map disc to D:** and **Back**.
5. **Load or replace disc image** loads, mounts and maps the disc to the
   chosen letter (`d:` mountpoint and `d::` raw device links) in one step.
   **Map disc to D:** mounts a loaded disc if needed before mapping it.
   Return to the installer and click **Retry/OK**. Repeat for each disc.
6. **If Disc 1 cannot be unmounted because the running installer keeps files
   open** ("target is busy"), Protontricks never forces the unmount. After
   **Load or replace disc image** it offers to load the new disc into an
   **empty reader** instead (creating one if none is free) and maps the
   installer's Windows letter (usually `D:`) to it. Disc 1 stays mounted
   until the installer exits; eject it afterwards with **Eject disc**.
7. **Remove last virtual reader** removes any empty last reader, including
   readers created outside Protontricks. CDEmu can only remove its **last**
   reader, and a reader still holding a disc image must be emptied with
   **Eject disc** first. **Readers 0 and 1 are never removed**, so CDEmu
   keeps its default readers when Protontricks is not in use.

**Compatibility:** If CDEmu is not installed, `protontricks --gui` goes
directly to the normal Winetricks GUI without the extra action dialog.
The CDEmu menu only appears when `cdemu` is available on the host.

**Global scope and safety:** CDEmu readers and images are **system-wide
resources**, not game-specific resources. Adding, removing, ejecting and
unmounting a reader can affect unrelated applications. Destructive actions
require confirmation and regular unmounting (never forced); a busy device
will not be forcibly ejected. `cdemu remove-device` can remove **only the
last reader**, and the UI refuses to remove it while it holds a disc image.
It does not automatically delete global readers when the game is removed.

**Per-game scope:** Only the Wine drive mappings (and a backup of the
original ones, under `.protontricks-cdrom` in the prefix) are stored in the
game's Proton prefix. Regular files and mappings changed externally are not
silently overwritten.

**Limitations:** The GUI does not emulate optical drives itself and depends
on the installed CDEmu daemon and udisks. Some older installers may cache
drive information or require other CD-ROM/DRM behavior. Removing a Steam
shortcut may create a different AppID/prefix when added again.

## Desktop

Protontricks comes with desktop integration, adding the Protontricks app shortcut and the ability to launch external Windows executables for Proton apps. To run an executable for a Proton app, select **Protontricks Launcher** when opening a Windows executable (eg. **EXE**) in a file manager.

The **Protontricks** app shortcut should be available automatically after installation. If not, you may need to run `protontricks-desktop-install` in a terminal to enable this functionality.

# Troubleshooting

For common issues and solutions, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

# Installation

You can install Protontricks using a community package, Flatpak or **pipx**. **pip** can also be used, but it is not recommended due to possible problems.

**If you're using a Steam Deck**, Flatpak is the recommended option. Open the **Discover** application store in desktop mode and search for **Protontricks**. 

**If you're using the Flatpak version of Steam**, follow the [Flatpak-specific installation instructions](https://github.com/flathub/com.github.Matoking.protontricks) instead.

## Community packages (recommended)

Community packages allow easier installation and updates using distro-specific package managers. They also take care of installing dependencies and desktop features out of the box, making them **the recommended option if available for your distribution**.

Community packages are maintained by community members and might be out-of-date compared to releases on PyPI.
Note that some distros such as **Debian** / **Ubuntu** often have outdated packages for either Protontricks **or** Winetricks.
If so, install the Flatpak version instead as outdated releases may fail to work properly.

[![Packaging status](https://repology.org/badge/vertical-allrepos/protontricks.svg)](https://repology.org/project/protontricks/versions)

## Flatpak (recommended)

Protontricks is available on the Flathub app store:

[<img width="180" src="https://flathub.org/assets/badges/flathub-badge-en.png">](https://flathub.org/apps/details/com.github.Matoking.protontricks)

To use Protontricks as a command-line application, add shell aliases by running the following commands:

```
echo "alias protontricks='flatpak run com.github.Matoking.protontricks'" >> ~/.bashrc
echo "alias protontricks-launch='flatpak run --command=protontricks-launch com.github.Matoking.protontricks'" >> ~/.bashrc
```

You will need to restart your terminal emulator for the aliases to take effect.

The Flatpak installation is sandboxed and only has access to the Steam
installation directory by default. **You will need to add filesystem permissions when
using additional Steam library locations or running external Windows
applications.** See
[here](https://github.com/flathub/com.github.Matoking.protontricks#configuration)
for instructions on changing the Flatpak permissions.

## pipx

You can use pipx to install the latest version on PyPI or the git repository for the current user. Installing Protontricks using pipx is recommended if a community package doesn't exist for your Linux distro.

**pipx does not install Winetricks and other dependencies out of the box.** You can install Winetricks using the [installation instructions](https://github.com/Winetricks/winetricks#installing) provided by the Winetricks project. 

**pipx requires Python 3.7 or newer.**

**You will need to install pip, setuptools and virtualenv first.** Install the correct packages depending on your distribution:

* Arch Linux: `sudo pacman -S python-pip python-pipx python-setuptools python-virtualenv`
* Debian-based (Ubuntu, Linux Mint): `sudo apt install python3-pip python3-setuptools python3-venv pipx`
* Fedora: `sudo dnf install python3-pip python3-setuptools python3-libs pipx`
* Gentoo:

  ```sh
  sudo emerge -av dev-python/pip dev-python/virtualenv dev-python/setuptools
  python3 -m pip install --user pipx
  ~/.local/bin/pipx ensurepath
  ```

Close and reopen your terminal. After that, you can install Protontricks.

```sh
pipx install protontricks
```

To enable desktop integration as well, run the following command *after* installing Protontricks

```sh
protontricks-desktop-install
```

To upgrade to the latest release:
```sh
pipx upgrade protontricks
```

To install the latest development version (requires `git`):
```sh
pipx install git+https://github.com/Matoking/protontricks.git
# '--spec' is required for older versions of pipx
pipx install --spec git+https://github.com/Matoking/protontricks.git protontricks
```

## pip (not recommended)

You can use pip to install the latest version on PyPI or the git repository. This method should work in any system where Python 3 is available.

**Note that this installation method might cause conflicts with your distro's package manager. To prevent this, consider using the pipx method or a community package instead.**

**You will need to install pip and setuptools first.** Install the correct packages depending on your distribution:

* Arch Linux: `sudo pacman -S python-pip python-setuptools`
* Debian-based (Ubuntu, Linux Mint): `sudo apt install python3-pip python3-setuptools`
* Fedora: `sudo dnf install python3-pip python3-setuptools`
* Gentoo: `sudo emerge -av dev-python/pip dev-python/setuptools`

To install the latest release using `pip`:
```sh
sudo python3 -m pip install protontricks
```

To upgrade to the latest release:
```sh
sudo python3 -m pip install --upgrade protontricks
```

To install Protontricks only for the current user:
```sh
python3 -m pip install --user protontricks
```

To install the latest development version (requires `git`):
```sh
sudo python3 -m pip install git+https://github.com/Matoking/protontricks.git
```
