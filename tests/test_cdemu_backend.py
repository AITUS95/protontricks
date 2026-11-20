"""Tests for CDEmu's system-wide operations and per-game ownership."""
import json
from pathlib import Path

import pytest

from protontricks import cdemu_backend as backend
from protontricks.cdrom import CDROMError


def test_list_readers_including_empty_and_unmounted(monkeypatch, tmp_path):
    mount = tmp_path / "Disc Two"
    mount.mkdir()

    def fake_command(args):
        if args[:2] == ["cdemu", "device-mapping"]:
            return (
                "Device mapping:\nDEV SCSI CD-ROM SCSI generic\n"
                "0 /dev/sr0 /dev/sg1\n1 /dev/sr1 /dev/sg2\n"
            )
        if args[:2] == ["cdemu", "status"]:
            return (
                "Devices status:\nDEV LOADED FILENAME\n"
                "0 True /images/disc two.cue\n1 False\n"
            )
        if args[0] == "findmnt":
            if args[3] == "/dev/sr0":
                return json.dumps({
                    "filesystems": [{"target": str(mount)}]
                })
            raise CDROMError("Not mounted")
        raise AssertionError(args)

    monkeypatch.setattr(backend, "_command", fake_command)
    drives = backend.list_drives()
    assert [(d.slot, d.loaded) for d in drives] == [(0, True), (1, False)]
    assert drives[0].mountpoint == mount
    assert drives[0].image == "/images/disc two.cue"
    assert drives[1].mountpoint is None


def test_load_mount_unmount_eject_sequence(monkeypatch, tmp_path):
    image = tmp_path / "test disc.iso"
    image.write_bytes(b"disc")
    mounted = tmp_path / "mount"
    mounted.mkdir()
    drive = [backend.OpticalDrive(0, Path("/dev/sr0"))]
    calls = []

    def fake_command(args):
        calls.append(args)
        if args[:2] == ["cdemu", "load"]:
            drive[0] = backend.OpticalDrive(
                0, Path("/dev/sr0"), str(image)
            )
        elif args[:2] == ["udisksctl", "mount"]:
            drive[0] = backend.OpticalDrive(
                0, Path("/dev/sr0"), str(image), mounted
            )
        elif args[:2] == ["udisksctl", "unmount"]:
            drive[0] = backend.OpticalDrive(
                0, Path("/dev/sr0"), str(image)
            )
        elif args[:2] == ["cdemu", "unload"]:
            drive[0] = backend.OpticalDrive(0, Path("/dev/sr0"))
        return ""

    monkeypatch.setattr(backend, "list_drives", lambda: drive[:])
    monkeypatch.setattr(backend, "_command", fake_command)
    assert backend.load_image(0, image).mountpoint == mounted
    with pytest.raises(CDROMError, match="not empty"):
        backend.load_image(0, image)
    assert backend.eject_drive(0).loaded is False
    assert [c[:2] for c in calls] == [
        ["cdemu", "load"], ["udisksctl", "mount"],
        ["udisksctl", "unmount"], ["cdemu", "unload"]
    ]


def test_create_and_remove_only_owned_last_reader(
        monkeypatch, tmp_path):
    prefix = tmp_path / "pfx"
    (prefix / "dosdevices").mkdir(parents=True)
    drives = [backend.OpticalDrive(0, Path("/dev/sr0"))]
    commands = []

    def fake_command(args):
        commands.append(args)
        if args == ["cdemu", "add-device"]:
            drives.append(backend.OpticalDrive(1, Path("/dev/sr1")))
        elif args == ["cdemu", "remove-device"]:
            drives.pop()
        return ""

    monkeypatch.setattr(backend, "list_drives", lambda: drives[:])
    monkeypatch.setattr(backend, "_command", fake_command)

    with pytest.raises(CDROMError, match="not created"):
        backend.remove_drive(prefix, 0)

    assert backend.add_drive(prefix).slot == 1
    assert backend.get_owned_drives(prefix) == [
        {"slot": 1, "device": "/dev/sr1"}
    ]
    mapping = prefix / "dosdevices" / "d::"
    mapping.symlink_to("/dev/sr1")
    with pytest.raises(CDROMError, match="still mapped"):
        backend.remove_drive(prefix, 1)
    mapping.unlink()

    assert backend.remove_drive(prefix, 1).slot == 1
    assert backend.get_owned_drives(prefix) == []
    assert commands == [
        ["cdemu", "add-device"], ["cdemu", "remove-device"]
    ]


def test_cannot_remove_external_reader(monkeypatch, tmp_path):
    prefix = tmp_path / "pfx"
    (prefix / "dosdevices").mkdir(parents=True)
    monkeypatch.setattr(
        backend, "list_drives",
        lambda: [backend.OpticalDrive(0, Path("/dev/sr0"))]
    )
    with pytest.raises(CDROMError, match="not created"):
        backend.remove_drive(prefix, 0)


def test_external_mount_failure_does_not_force_eject(
        monkeypatch, tmp_path):
    mount = tmp_path / "disc"
    mount.mkdir()
    drive = backend.OpticalDrive(
        0, Path("/dev/sr0"), "/images/disc.iso", mount
    )
    seen = []
    monkeypatch.setattr(backend, "list_drives", lambda: [drive])

    def fake_command(args):
        seen.append(args)
        raise CDROMError("Device busy")

    monkeypatch.setattr(backend, "_command", fake_command)
    with pytest.raises(CDROMError, match="busy"):
        backend.eject_drive(0)
    assert seen == [
        ["udisksctl", "unmount", "-b", "/dev/sr0"]
    ]


def test_failed_replace_attempts_to_restore_old_disc(monkeypatch, tmp_path):
    old_file = tmp_path / "old.iso"
    new_file = tmp_path / "bad.iso"
    old_file.write_bytes(b"old")
    new_file.write_bytes(b"bad")
    mount = tmp_path / "mount"
    mount.mkdir()
    drive = [backend.OpticalDrive(
        0, Path("/dev/sr0"), str(old_file), mount
    )]
    calls = []

    def fake_command(args):
        calls.append(args)
        if args[:2] == ["udisksctl", "unmount"]:
            drive[0] = backend.OpticalDrive(
                0, Path("/dev/sr0"), str(old_file)
            )
        elif args[:2] == ["cdemu", "unload"]:
            drive[0] = backend.OpticalDrive(
                0, Path("/dev/sr0")
            )
        elif args[:2] == ["cdemu", "load"]:
            if args[-1] == str(new_file):
                raise CDROMError("Broken disc image")
            drive[0] = backend.OpticalDrive(
                0, Path("/dev/sr0"), str(old_file)
            )
        elif args[:2] == ["udisksctl", "mount"]:
            drive[0] = backend.OpticalDrive(
                0, Path("/dev/sr0"), str(old_file), mount
            )
        return ""

    monkeypatch.setattr(backend, "list_drives", lambda: drive[:])
    monkeypatch.setattr(backend, "_command", fake_command)
    with pytest.raises(CDROMError, match="Broken disc image"):
        backend.load_image(0, new_file, replace=True)
    assert drive[0].image == str(old_file)
    assert drive[0].mountpoint == mount
    assert [c[:2] for c in calls][-2:] == [
        ["cdemu", "load"], ["udisksctl", "mount"]
    ]
