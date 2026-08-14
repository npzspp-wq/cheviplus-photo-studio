from pathlib import Path

import cheviplus_network_storage as ns


def test_local_folder_write_check(tmp_path):
    target = tmp_path / "ready"
    ok, message = ns.check_writable_folder(target)
    assert ok, message
    assert target.is_dir()
    assert not list(target.glob(".cheviplus_write_test_*.tmp"))


def test_empty_folder_rejected():
    ok, message = ns.check_writable_folder("")
    assert not ok
    assert "не выбрана" in message.lower()


def test_path_kind_unc():
    assert "UNC" in ns._path_kind(Path(r"\\server\share\photos"))
