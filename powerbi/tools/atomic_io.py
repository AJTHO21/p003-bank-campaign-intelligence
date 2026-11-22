"""Verified file replacement and recoverable scratch space for P003 automation."""
import fcntl
import os
import stat
import tempfile
from contextlib import contextmanager
from pathlib import Path


def check_path(path):
    for component in (path, *path.parents):
        if component.is_symlink():
            raise ValueError(f"Symlink refused: {component}")


def read_existing(path):
    check_path(path)
    if not path.exists():
        return None
    if not path.is_file():
        raise ValueError(f"Expected regular file: {path}")
    return path.read_bytes()


def fsync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def mkdir_durable(path, mode=0o755):
    check_path(path)
    if not path.is_dir():
        mkdir_durable(path.parent)
        path.mkdir(mode=mode, exist_ok=True)
        fsync_directory(path.parent)


def clear_scratch(stage, allowed):
    files = list(stage.iterdir())
    for file in files:
        info = file.lstat()
        if (not allowed(file.name) or not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.geteuid() or info.st_nlink != 1):
            raise ValueError(f"Unexpected staging entry: {file}")
    for file in files:
        file.unlink()


@contextmanager
def scratch_directory(parent, name, allowed):
    """Use one reserved directory while the caller holds the parent lock."""
    stage = parent / name
    check_path(stage)
    stage.mkdir(mode=0o700, exist_ok=True)
    if not stage.is_dir() or stage.stat().st_uid != os.geteuid():
        raise ValueError(f"Invalid staging directory: {stage}")
    clear_scratch(stage, allowed)
    try:
        yield stage
    finally:
        if stage.exists():
            check_path(stage)
            clear_scratch(stage, allowed)
            stage.rmdir()


@contextmanager
def staging_area(parent, name):
    """Serialize access to a reserved scratch directory and reclaim stale files."""
    check_path(parent)
    descriptor = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        with scratch_directory(parent, name, lambda filename: filename.startswith("p003-write-")) as stage:
            yield stage
    finally:
        os.close(descriptor)


def atomic_write(path, contents, *, expected, stage, mode=0o644):
    """Publish complete bytes only if the destination still has expected bytes."""
    if not contents:
        raise ValueError(f"Empty replacement refused: {path}")
    actual = read_existing(path)
    if actual != expected:
        raise ValueError(f"Destination changed before write: {path}")
    if actual == contents:
        return
    if actual is not None:
        mode = stat.S_IMODE(path.stat().st_mode) & 0o777
    if stage.stat().st_dev != path.parent.stat().st_dev:
        raise ValueError(f"Staging and destination are on different filesystems: {path}")
    scratch = None
    try:
        with tempfile.NamedTemporaryFile(prefix="p003-write-", dir=stage, delete=False) as handle:
            scratch = Path(handle.name)
            if handle.write(contents) != len(contents):
                raise OSError(f"Short staged write: {path}")
            handle.flush()
            os.fchmod(handle.fileno(), mode)
            os.fsync(handle.fileno())
        if scratch.read_bytes() != contents:
            raise OSError(f"Staged content verification failed: {path}")
        if read_existing(path) != expected:
            raise ValueError(f"Destination changed during write: {path}")
        os.replace(scratch, path)
        try:
            fsync_directory(path.parent)
        except OSError as error:
            raise OSError(f"Replacement published but directory sync failed: {path}: {error}") from error
    finally:
        if scratch is not None:
            scratch.unlink(missing_ok=True)
