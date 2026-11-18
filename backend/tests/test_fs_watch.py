"""drvfs/9p mounts are polled; a normal Linux filesystem is not."""
from pathlib import Path

from app.allsky.fs_watch import filesystem_type, needs_poll

MOUNTS = "\n".join([
    "/dev/sda1 / ext4 rw 0 0",
    "C:\\ /mnt/c 9p rw 0 0",
    "D:\\ /mnt/d drvfs rw 0 0",
])


def test_9p_and_drvfs_need_polling():
    assert filesystem_type(Path("/mnt/c/allsky/data"), MOUNTS) == "9p"
    assert filesystem_type(Path("/mnt/d/allsky"), MOUNTS) == "drvfs"
    assert filesystem_type(Path("/srv/allsky/data"), MOUNTS) == "ext4"
    assert needs_poll(Path("/mnt/c/allsky/data"), MOUNTS) is True
    assert needs_poll(Path("/mnt/d/allsky"), MOUNTS) is True
    assert needs_poll(Path("/srv/allsky/data"), MOUNTS) is False
