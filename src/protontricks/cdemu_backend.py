"""Optional CDEmu device operations for Protontricks's per-game CD/DVD GUI.

CDEmu readers are global. Only the drive-letter mapping is game-specific.
No commands run through a shell and no privileged/forced unmounts are used.
"""
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

from .cdrom import CDROMError, CDEmuDrive, _command, _paths, _save_state


@dataclass(frozen=True)
class OpticalDrive:
    slot: int
    device: Path
    image: str = ""
    mountpoint: Path = None

    @property
    def loaded(self):
        return bool(self.image)


def list_drives():
    """List all CDEmu devices, including empty and unmounted readers."""
    mapping = _command(["cdemu", "device-mapping"])
    status = _command(["cdemu", "status"])
    image_by_slot = {}
    for line in status.splitlines():
        match = re.match(r"^\s*(\d+)\s+(True|False)\s*(.*)$", line)
        if match:
            image = match.group(3).strip()
            if match.group(2) == "True" and not image:
                raise CDROMError(
                    "CDEmu reports a loaded reader without an image path."
                )
            image_by_slot[int(match.group(1))] = (
                image if match.group(2) == "True" else ""
            )

    result = []
    for line in mapping.splitlines():
        match = re.match(r"^\s*(\d+)\s+(/dev/\S+)\s+", line)
        if not match:
            continue
        slot = int(match.group(1))
        if slot not in image_by_slot:
            raise CDROMError(
                "CDEmu did not report status for reader {}.".format(slot)
            )
        device = Path(match.group(2))
        mountpoint = None
        try:
            data = json.loads(_command([
                "findmnt", "--json", "--source", str(device),
                "--output", "TARGET"
            ]))
            filesystems = data.get("filesystems") or []
            if filesystems and filesystems[0].get("target"):
                candidate = Path(filesystems[0]["target"])
                if candidate.is_dir():
                    mountpoint = candidate
        except (CDROMError, ValueError, KeyError, TypeError):
            # A reader can be empty, or its loaded disc may not be mounted.
            pass
        result.append(OpticalDrive(
            slot, device, image_by_slot.get(slot, ""), mountpoint
        ))
    return sorted(result, key=lambda d: d.slot)


def _selected_drive(slot):
    drive = next((d for d in list_drives() if d.slot == slot), None)
    if drive is None:
        raise CDROMError("CDEmu reader {} no longer exists. Refresh.".format(slot))
    return drive


def mount_drive(slot):
    """Wait for optical media probing and tolerate desktop automount races."""
    drive = _selected_drive(slot)
    if not drive.loaded:
        raise CDROMError("Load an image into reader {} first.".format(slot))
    if drive.mountpoint is not None:
        return drive

    last_error = None
    for attempt in range(10):
        drive = _selected_drive(slot)
        if drive.mountpoint is not None:
            return drive
        try:
            _command(["udisksctl", "mount", "-b", str(drive.device)])
        except CDROMError as exc:
            # udisks may not have probed the newly inserted image yet,
            # or a desktop automounter may mount it between the checks.
            last_error = exc
        drive = _selected_drive(slot)
        if drive.mountpoint is not None:
            return drive
        if attempt < 9:
            time.sleep(0.3)

    message = "CDEmu reader {} did not become mounted.".format(slot)
    if last_error is not None:
        message += " Last mount attempt: {}".format(last_error)
    raise CDROMError(message)


def unmount_drive(slot):
    drive = _selected_drive(slot)
    if drive.mountpoint is not None:
        _command(["udisksctl", "unmount", "-b", str(drive.device)])
        drive = _selected_drive(slot)
        if drive.mountpoint is not None:
            raise CDROMError("The filesystem is still mounted.")
    return drive


def eject_drive(slot):
    drive = unmount_drive(slot)
    if drive.loaded:
        _command(["cdemu", "unload", str(slot)])
    return _selected_drive(slot)


def load_image(slot, image_path, replace=False):
    """Load an image and mount it. Replacement is explicit, never forced.

    A failed replacement load attempts to restore the previously loaded disc.
    If a new image loads but cannot mount, it remains loaded for a retry.
    """
    path = Path(image_path).expanduser()
    if not path.is_file():
        raise CDROMError("Image file does not exist: {}".format(path))
    path = path.resolve()
    old = _selected_drive(slot)
    if old.loaded and not replace:
        raise CDROMError("Reader {} is not empty; eject it first.".format(slot))
    if old.loaded:
        eject_drive(slot)
    try:
        _command(["cdemu", "load", str(slot), str(path)])
    except CDROMError:
        if old.loaded and Path(old.image).is_file():
            try:
                _command(["cdemu", "load", str(slot), old.image])
                if old.mountpoint is not None:
                    mount_drive(slot)
            except CDROMError:
                pass
        raise
    return mount_drive(slot)


def _owned_file(prefix):
    # Leverage the same validated per-prefix location as mapping backups.
    _, link_state = _paths(prefix, "D")
    return link_state.parent / "owned-devices.json"


def get_owned_drives(prefix):
    path = _owned_file(prefix)
    if path.is_symlink() or path.parent.is_symlink():
        raise CDROMError("Unsafe CDEmu ownership file location.")
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        entries = data["devices"]
        if not isinstance(entries, list) or not all(
            isinstance(entry, dict) and type(entry.get("slot")) is int
            and isinstance(entry.get("device"), str)
            and entry["slot"] >= 0
            for entry in entries
        ):
            raise ValueError("Invalid reader ownership records")
        return entries
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise CDROMError("Invalid CDEmu ownership record.") from exc


def _save_owned(prefix, entries):
    _save_state(_owned_file(prefix), {"devices": entries})


def add_drive(prefix):
    """Create a global CDEmu reader, recording it under this game prefix."""
    owned = get_owned_drives(prefix)
    before = {drive.slot for drive in list_drives()}
    _command(["cdemu", "add-device"])
    new = []
    for attempt in range(5):
        new = [drive for drive in list_drives() if drive.slot not in before]
        if len(new) == 1:
            break
        time.sleep(0.2)
    if len(new) != 1:
        raise CDROMError(
            "CDEmu add-device completed, but the new reader could not be "
            "identified. Refresh; do not add another reader yet."
        )
    drive = new[0]
    try:
        _save_owned(prefix, owned + [{
            "slot": drive.slot, "device": str(drive.device)
        }])
    except Exception:
        # Never delete a global reader automatically when persistence fails.
        raise CDROMError(
            "The reader was created but ownership could not be saved; "
            "leave it in place and inspect it manually."
        )
    return drive


def remove_drive(prefix, slot):
    """Only remove the last, empty reader created for this game.

    CDEmu remove-device always removes the LAST device globally. Refuse to
    remove arbitrary devices or a device still referenced by this prefix.
    """
    drives = list_drives()
    if not drives or drives[-1].slot != slot:
        raise CDROMError("Only CDEmu's last reader can be removed.")
    drive = drives[-1]
    owned = get_owned_drives(prefix)
    if {"slot": slot, "device": str(drive.device)} not in owned:
        raise CDROMError(
            "This reader was not created by Protontricks for this game."
        )
    if drive.loaded or drive.mountpoint is not None:
        raise CDROMError("Eject the image before removing this reader.")
    dosdevices = Path(prefix) / "dosdevices"
    for link in dosdevices.iterdir():
        if link.name.endswith("::") and link.is_symlink() and \
                os.readlink(link) == str(drive.device):
            raise CDROMError(
                "This reader is still mapped in Wine. Restore or change "
                "the mapping before removing it."
            )
    remaining = [entry for entry in owned if entry != {
        "slot": slot, "device": str(drive.device)
    }]
    # Retire the ownership record first: a failed write must not leave a
    # stale record that could authorize removal of a newly reused slot.
    _save_owned(prefix, remaining)
    try:
        _command(["cdemu", "remove-device"])
    except Exception:
        _save_owned(prefix, owned)
        raise
    return drive


def to_cdrom_drive(drive):
    if drive.mountpoint is None:
        raise CDROMError("Mount the disc before assigning a Windows drive.")
    return CDEmuDrive(
        drive.slot, drive.device, drive.mountpoint, drive.image
    )
