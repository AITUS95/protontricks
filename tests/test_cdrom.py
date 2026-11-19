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
            return "Device mapping:\nDEV   SCSI CD-ROM   SCSI generic\n0 /dev/sr0 /dev/sg1\n1 /dev/sr1 /dev/sg2\n"
        if args[:2] == ["cdemu", "status"]:
            return "Devices' status:\nDEV LOADED FILENAME\n0 True /discs/one.cue\n1 True /discs/two.cue\n"
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
