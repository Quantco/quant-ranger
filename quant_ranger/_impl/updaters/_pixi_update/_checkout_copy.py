import os
import shutil
import stat
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from quant_ranger._impl.helpers import app_tempdir

MAX_LOCKFILE_SIZE_BYTES = 50 * 1024 * 1024


class LockfileCopyError(Exception):
    """The lockfile in a checkout copy cannot be transferred to the checkout."""


@contextmanager
def checkout_copy(checkout_path: Path) -> Generator[Path]:
    """Copy a checkout, including `.git`, into a fresh temporary directory.

    The copy keeps the directory layout and name of the checkout. Symlinks are copied as
    symlinks and file contents are copied rather than hardlinked, so nothing done in the
    copy affects the checkout.
    """
    with app_tempdir(prefix="quant-ranger-pixi-workspace-") as tempdir:
        copy_path = tempdir.resolve() / checkout_path.name
        shutil.copytree(checkout_path, copy_path, symlinks=True)
        yield copy_path


def copy_back_lockfile(
    copy_path: Path,
    relative_lockfile_path: Path,
    destination: Path,
) -> None:
    """Replace `destination` with the lockfile at `relative_lockfile_path` in the copy.

    The lockfile in the copy is controlled by the sandbox, so it is only read if it is
    a regular file. Otherwise, a symlink or hard link could make us read a file that the
    sandbox itself cannot read. `destination` is left untouched if the lockfile cannot
    be used.

    The sandbox can also replace its writable working directory, i.e. the lockfile
    directory or `copy_path` itself, with a symlink. The path is therefore opened one
    component at a time, starting from the parent of `copy_path`, which the sandbox
    cannot write to, and no component may be a symlink.
    """
    display_path = relative_lockfile_path.as_posix()
    try:
        fd = _open_without_symlinks(
            copy_path.parent, Path(copy_path.name) / relative_lockfile_path
        )
    except OSError as error:
        raise LockfileCopyError(
            f"{display_path} could not be opened: {error.strerror}"
        ) from error
    try:
        status = os.fstat(fd)
        if not stat.S_ISREG(status.st_mode) or status.st_nlink != 1:
            raise LockfileCopyError(f"{display_path} is not a regular file.")
        with os.fdopen(fd, "rb", closefd=False) as file:
            content = file.read(MAX_LOCKFILE_SIZE_BYTES + 1)
    finally:
        os.close(fd)
    if len(content) > MAX_LOCKFILE_SIZE_BYTES:
        raise LockfileCopyError(
            f"{display_path} exceeds the maximum size of "
            f"{MAX_LOCKFILE_SIZE_BYTES} bytes."
        )

    # Remove `destination` first so that a symlink committed to the repository is
    # replaced instead of written through.
    destination.unlink(missing_ok=True)
    destination.write_bytes(content)


def _open_without_symlinks(root: Path, relative_path: Path) -> int:
    """Open `root / relative_path` for reading without following symlinks below
    `root`."""
    *directories, name = relative_path.parts
    directory_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for directory in directories:
            next_fd = os.open(
                directory,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=directory_fd,
            )
            os.close(directory_fd)
            directory_fd = next_fd
        # O_NONBLOCK keeps opening a FIFO from blocking.
        return os.open(
            name,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=directory_fd,
        )
    finally:
        os.close(directory_fd)
