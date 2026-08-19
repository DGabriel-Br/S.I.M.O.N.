from __future__ import annotations

import errno
import os
import sys
from pathlib import Path
from types import TracebackType
from typing import BinaryIO, Self

if sys.platform == "win32":
    import msvcrt

    def _lock_handle(handle: BinaryIO) -> None:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)

    def _unlock_handle(handle: BinaryIO) -> None:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def _lock_handle(handle: BinaryIO) -> None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock_handle(handle: BinaryIO) -> None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class RuntimeAlreadyActiveError(RuntimeError):
    pass


class RuntimeLock:
    def __init__(self, data_dir: Path) -> None:
        self.path = data_dir / ".runtime.lock"
        self._handle: BinaryIO | None = None

    def __enter__(self) -> Self:
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.release()

    def acquire(self) -> None:
        if self._handle is not None:
            raise RuntimeError("runtime lock já foi adquirido por esta instância")

        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+b")
        try:
            _lock_handle(handle)
        except OSError as exc:
            handle.close()
            if exc.errno in {errno.EACCES, errno.EAGAIN}:
                raise RuntimeAlreadyActiveError(
                    "outra instância do S.I.M.O.N. está usando este diretório de dados"
                ) from exc
            raise

        self._handle = handle

    def release(self) -> None:
        handle = self._handle
        if handle is None:
            return

        self._handle = None
        try:
            _unlock_handle(handle)
        finally:
            handle.close()
