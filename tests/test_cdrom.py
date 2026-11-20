"""Unit tests for the opt-in CDEmu drive manager."""
import json
import os
from pathlib import Path

import pytest

from protontricks.cdrom import (
    CDROMError, CDEmuDrive, discover_cdemu_drives, has_cdrom_backup,
    restore_cdrom_mapping, set_cdrom_mapping
)


@pytest.fixture
def prefix(tmp_path):
    path = tmp_path / "compatdata" / "100" / "pfx"
    (path / "dosdevices").mkdir(parents=True)
    return path


def test_discover_mounted_cdemu_discs(monkeypatch, tmp_path):
    disc = tmp_path / "Disc Two"
    disc.mkdir()

    def command(args):
        if args[:2] == ["cdemu", "device-mapping"]:
            return (
                "Device mapping:\nDEV   SCSI CD-ROM   SCSI generic\n"
                "0 /dev/sr0 /dev/sg1\n1 /dev/sr1 /dev/sg2\n"
            )
        if args[:2] == ["cdemu", "status"]:
            return (
                "Devices' status:\nDEV LOADED FILENAME\n"
                "0 True /discs/one.cue\n1 True /discs/two.cue\n"
            )
        if args[0] == "findmnt":
            if args[3] == "/dev/sr1":
                return json.dumps({"filesystems": [{"target": str(disc)}]})
            raise CDROMError("Not mounted")
        raise AssertionError(args)

    monkeypatch.setattr("protontricks.cdrom._command", command)
    drives = discover_cdemu_drives()
    assert len(drives) == 1
    assert drives[0] == CDEmuDrive(
        1, Path("/dev/sr1"), disc, "/discs/two.cue"
    )


def test_switch_and_restore_original_mapping(prefix, tmp_path):
    dos = prefix / "dosdevices"
    (dos / "d:").symlink_to("/old/cdrom")
    (dos / "d::").symlink_to("/dev/sr0")
    disc2 = tmp_path / "VTMB_2"
    disc3 = tmp_path / "VTMB_3"
    disc2.mkdir()
    disc3.mkdir()

    set_cdrom_mapping(
        prefix, CDEmuDrive(1, Path("/dev/sr1"), disc2), "D"
    )
    assert os.readlink(dos / "d:") == str(disc2)
    assert os.readlink(dos / "d::") == "/dev/sr1"
    assert has_cdrom_backup(prefix, "D")

    set_cdrom_mapping(
        prefix, CDEmuDrive(2, Path("/dev/sr2"), disc3), "D"
    )
    assert os.readlink(dos / "d:") == str(disc3)
    assert os.readlink(dos / "d::") == "/dev/sr2"

    restore_cdrom_mapping(prefix, "D")
    assert os.readlink(dos / "d:") == "/old/cdrom"
    assert os.readlink(dos / "d::") == "/dev/sr0"
    assert not has_cdrom_backup(prefix, "D")


def test_restore_absent_original_links(prefix, tmp_path):
    mounted = tmp_path / "disc"
    mounted.mkdir()
    set_cdrom_mapping(
        prefix, CDEmuDrive(0, Path("/dev/sr0"), mounted)
    )
    restore_cdrom_mapping(prefix)
    assert not os.path.lexists(prefix / "dosdevices" / "d:")
    assert not os.path.lexists(prefix / "dosdevices" / "d::")


def test_refuse_to_overwrite_regular_file(prefix, tmp_path):
    (prefix / "dosdevices" / "d:").write_text("keep")
    mounted = tmp_path / "disc"
    mounted.mkdir()
    with pytest.raises(CDROMError, match="not a symlink"):
        set_cdrom_mapping(
            prefix, CDEmuDrive(0, Path("/dev/sr0"), mounted)
        )
    assert (prefix / "dosdevices" / "d:").read_text() == "keep"


def test_detect_external_changes(prefix, tmp_path):
    mounted = tmp_path / "disc"
    mounted.mkdir()
    drive = CDEmuDrive(0, Path("/dev/sr0"), mounted)
    set_cdrom_mapping(prefix, drive)
    link = prefix / "dosdevices" / "d:"
    link.unlink()
    link.symlink_to("/external/change")

    with pytest.raises(CDROMError, match="outside Protontricks"):
        set_cdrom_mapping(prefix, drive)
    with pytest.raises(CDROMError, match="externally"):
        restore_cdrom_mapping(prefix)
    assert os.readlink(link) == "/external/change"


def test_mapping_is_per_prefix(prefix, tmp_path):
    other = tmp_path / "compatdata" / "200" / "pfx"
    (other / "dosdevices").mkdir(parents=True)
    mounted = tmp_path / "disc"
    mounted.mkdir()
    set_cdrom_mapping(prefix, CDEmuDrive(0, Path("/dev/sr0"), mounted))
    assert not (other / "dosdevices" / "d:").is_symlink()


def test_invalid_drive_letter(prefix, tmp_path):
    mounted = tmp_path / "disc"
    mounted.mkdir()
    with pytest.raises(CDROMError, match="drive letter"):
        set_cdrom_mapping(
            prefix, CDEmuDrive(0, Path("/dev/sr0"), mounted), "C"
        )


def test_command_reports_missing_tool(monkeypatch):
    from protontricks import cdrom

    def missing(*args, **kwargs):
        raise FileNotFoundError("cdemu")

    monkeypatch.setattr(cdrom.subprocess, "run", missing)
    with pytest.raises(CDROMError, match="cdemu-client"):
        cdrom._command(["cdemu", "status"])


def test_command_reports_failing_tool(monkeypatch):
    from protontricks import cdrom
    from subprocess import CompletedProcess

    def failed(args, **kwargs):
        return CompletedProcess(args, 1, "", "D-Bus disconnected")

    monkeypatch.setattr(cdrom.subprocess, "run", failed)
    with pytest.raises(CDROMError, match="D-Bus disconnected"):
        cdrom._command(["cdemu", "status"])


def test_mapping_rollback_if_second_symlink_fails(
        prefix, monkeypatch, tmp_path):
    from protontricks import cdrom

    dosdevices = prefix / "dosdevices"
    (dosdevices / "d:").symlink_to("/old/mount")
    (dosdevices / "d::").symlink_to("/dev/sr0")
    mounted = tmp_path / "disc2"
    mounted.mkdir()

    original_symlink = cdrom.os.symlink

    def fail_on_raw_device(target, destination, *args, **kwargs):
        if str(destination).endswith("d::.protontricks-new"):
            raise OSError("simulated write failure")
        return original_symlink(target, destination, *args, **kwargs)

    monkeypatch.setattr(cdrom.os, "symlink", fail_on_raw_device)
    with pytest.raises(OSError, match="simulated write failure"):
        set_cdrom_mapping(
            prefix, CDEmuDrive(1, Path("/dev/sr1"), mounted)
        )
    assert os.readlink(dosdevices / "d:") == "/old/mount"
    assert os.readlink(dosdevices / "d::") == "/dev/sr0"
    assert not has_cdrom_backup(prefix)


def test_stale_temp_backup_reports_path_and_restores_links(
        prefix, tmp_path):
    temporary = prefix / ".protontricks-cdrom" / "d.tmp"
    temporary.parent.mkdir()
    temporary.write_text("stale")
    mounted = tmp_path / "disc"
    mounted.mkdir()
    with pytest.raises(CDROMError) as excinfo:
        set_cdrom_mapping(
            prefix, CDEmuDrive(1, Path("/dev/sr1"), mounted)
        )
    assert str(temporary) in str(excinfo.value)
    assert not (prefix / "dosdevices" / "d:").is_symlink()
    assert not (prefix / "dosdevices" / "d::").is_symlink()
    assert temporary.read_text() == "stale"
