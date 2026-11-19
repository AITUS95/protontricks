"""Manage CDEmu-backed Wine CD-ROM drive mappings for one Proton prefix.

This module does not mount or eject images: discs must already be mounted by
the desktop or CDEmu. It only changes the selected prefix's dosdevices links.
"""
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


class CDROMError(Exception):
    """An expected CD-ROM discovery or mapping failure."""


@dataclass(frozen=True)
class CDEmuDrive:
    slot: int
    device: Path
    mountpoint: Path
    image: str = ""


def _command(args):
    try:
        result = subprocess.run(
            args, capture_output=True, text=True, check=False
        )
    except FileNotFoundError as exc:
        raise CDROMError(
            "CDEmu and findmnt are required. Install cdemu-client and "
            "mount the image before using this manager."
        ) from exc
    if result.returncode:
        raise CDROMError(
            "{} failed: {}".format(args[0], result.stderr.strip())
        )
    return result.stdout


def discover_cdemu_drives():
    """Return loaded, mounted CDEmu devices, without assuming /dev/sr numbers."""
    mapping = _command(["cdemu", "device-mapping"])
    status = _command(["cdemu", "status"])
    images = {}
    for line in status.splitlines():
        match = re.match(r"^\s*(\d+)\s+(True|False)\s*(.*)$", line)
        if match and match.group(2) == "True":
            images[int(match.group(1))] = match.group(3).strip()

    drives = []
    for line in mapping.splitlines():
        match = re.match(r"^\s*(\d+)\s+(/dev/\S+)\s+", line)
        if not match:
            continue
        slot = int(match.group(1))
        if slot not in images:
            continue
        device = Path(match.group(2))
        try:
            data = json.loads(_command([
                "findmnt", "--json", "--source", str(device),
                "--output", "TARGET"
            ]))
        except (CDROMError, json.JSONDecodeError):
            # Loaded images are not necessarily mounted.
            continue
        filesystems = data.get("filesystems") or []
        if not filesystems:
            continue
        target = filesystems[0].get("target")
        if not target:
            continue
        mountpoint = Path(target)
        if not mountpoint.is_dir():
            continue
        drives.append(CDEmuDrive(slot, device, mountpoint, images[slot]))

    return sorted(drives, key=lambda d: d.slot)


def _paths(prefix, letter):
    if not re.fullmatch(r"[D-Yd-y]", letter):
        raise CDROMError("Choose a drive letter from D: through Y:.")
    prefix = Path(prefix)
    dosdevices = prefix / "dosdevices"
    if not dosdevices.is_dir() or dosdevices.is_symlink():
        raise CDROMError("The selected Proton prefix has no valid dosdevices directory.")
    letter = letter.lower()
    links = (dosdevices / (letter + ":"), dosdevices / (letter + "::"))
    state = prefix / ".protontricks-cdrom" / (letter + ".json")
    return links, state


def _targets(links):
    targets = []
    for link in links:
        if link.is_symlink():
            targets.append(os.readlink(link))
        elif os.path.lexists(link):
            raise CDROMError(
                "{} exists but is not a symlink; refusing to overwrite it.".format(link)
            )
        else:
            targets.append(None)
    return targets


def _set_links(links, targets):
    """Replace symlinks without following them. Roll back if a write fails."""
    old = _targets(links)
    try:
        for link, target in zip(links, targets):
            if target is None:
                if link.is_symlink():
                    link.unlink()
                continue
            temp = link.with_name(link.name + ".protontricks-new")
            if os.path.lexists(temp):
                raise CDROMError("Temporary mapping already exists: {}".format(temp))
            os.symlink(target, temp)
            try:
                os.replace(temp, link)
            finally:
                if temp.is_symlink():
                    temp.unlink()
    except Exception:
        # Restore the previous mappings, including a previously absent link.
        for link, target in zip(links, old):
            if target is None:
                if link.is_symlink():
                    link.unlink()
            else:
                temp = link.with_name(link.name + ".protontricks-rollback")
                if not os.path.lexists(temp):
                    os.symlink(target, temp)
                    os.replace(temp, link)
        raise


def _save_state(path, state):
    if path.parent.is_symlink():
        raise CDROMError("Refusing to use a symlinked backup directory.")
    path.parent.mkdir(mode=0o700, exist_ok=True)
    if path.is_symlink():
        raise CDROMError("Refusing to overwrite a symlinked CD-ROM backup.")
    temp = path.with_suffix(".tmp")
    if os.path.lexists(temp):
        raise CDROMError("A temporary CD-ROM backup already exists.")
    try:
        with temp.open("x", encoding="utf-8") as file:
            json.dump(state, file)
            file.write("\n")
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def _load_state(path):
    if path.is_symlink() or path.parent.is_symlink():
        raise CDROMError("Refusing to read a symlinked CD-ROM backup.")
    if not path.exists():
        return None
    try:
        with path.open(encoding="utf-8") as file:
            state = json.load(file)
        original, current = state["original"], state["current"]
        if not all(
            isinstance(pair, list) and len(pair) == 2 and
            all(value is None or isinstance(value, str) for value in pair)
            for pair in (original, current)
        ):
            raise ValueError("Invalid mapping state")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise CDROMError("Invalid CD-ROM backup: {}".format(path)) from exc
    return state


def has_cdrom_backup(prefix, letter="D"):
    _, path = _paths(prefix, letter)
    return os.path.lexists(path)


def set_cdrom_mapping(prefix, drive, letter="D"):
    """Point a Windows letter and its raw-device link to a mounted CDEmu disc.

    The original mapping is saved once, and later changes preserve it.
    Refuse to clobber a mapping changed by Wine or another program meanwhile.
    """
    links, path = _paths(prefix, letter)
    if not drive.mountpoint.is_dir():
        raise CDROMError("The selected CDEmu disc is not mounted.")
    previous = _targets(links)
    state = _load_state(path)
    if state and previous != state["current"]:
        raise CDROMError(
            "The mapping was changed outside Protontricks. Restore or "
            "resolve the mapping manually before continuing."
        )
    target = [str(drive.mountpoint), str(drive.device)]
    new_state = {
        "original": state["original"] if state else previous,
        "current": target
    }
    if target == previous:
        return
    _set_links(links, target)
    try:
        _save_state(path, new_state)
    except Exception:
        _set_links(links, previous)
        raise


def restore_cdrom_mapping(prefix, letter="D"):
    """Restore both original links; refuse if another tool modified them."""
    links, path = _paths(prefix, letter)
    state = _load_state(path)
    if not state:
        raise CDROMError("There is no CD-ROM mapping to restore.")
    if _targets(links) != state["current"]:
        raise CDROMError("Drive mappings changed externally; refusing to overwrite.")
    _set_links(links, state["original"])
    path.unlink()
