from __future__ import annotations

import os
import socket
import stat
import struct
from pathlib import Path

APP_ID = "omarchy-overhead"


class PathError(RuntimeError):
    pass


def home() -> Path:
    return Path(os.environ.get("HOME") or Path.home())


def _tmp_root() -> Path:
    return Path("/tmp")


def _lstat(path: Path) -> os.stat_result:
    try:
        return os.lstat(path)
    except FileNotFoundError as exc:
        raise PathError(f"{path} does not exist") from exc


def _require_dir(path: Path, st: os.stat_result) -> None:
    if stat.S_ISLNK(st.st_mode):
        raise PathError(f"{path} is a symlink")
    if not stat.S_ISDIR(st.st_mode):
        raise PathError(f"{path} is not a directory")


def _require_private_dir(path: Path, st: os.stat_result) -> None:
    _require_dir(path, st)
    if st.st_uid != os.getuid():
        raise PathError(f"{path} is not owned by the current user")
    if stat.S_IMODE(st.st_mode) & 0o077:
        raise PathError(f"{path} must be mode 0700")


def _reject_symlink_levels(path: Path) -> None:
    current = Path(path.anchor or "/")
    for part in Path(path).parts[1:]:
        current = current / part
        try:
            st = os.lstat(current)
        except FileNotFoundError:
            return
        if stat.S_ISLNK(st.st_mode):
            raise PathError(f"{current} is a symlink")
        if current != path and not stat.S_ISDIR(st.st_mode):
            raise PathError(f"{current} is not a directory")


def _require_existing_private_dir(path: Path) -> Path:
    path = Path(path)
    if not path.is_absolute():
        raise PathError(f"{path} is not an absolute path")
    _reject_symlink_levels(path)
    _require_private_dir(path, _lstat(path))
    return path


def ensure_private_dir(path: Path) -> Path:
    path = Path(path)
    if not path.is_absolute():
        raise PathError(f"{path} is not an absolute path")
    _reject_symlink_levels(path)
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        parent = path.parent
        pst = _lstat(parent)
        _require_dir(parent, pst)
        os.mkdir(path, 0o700)
        os.chmod(path, 0o700)
        st = _lstat(path)
    else:
        _require_dir(path, st)
        if st.st_uid != os.getuid():
            raise PathError(f"{path} is not owned by the current user")
        if stat.S_IMODE(st.st_mode) != 0o700:
            os.chmod(path, 0o700)
            st = _lstat(path)
    _require_private_dir(path, st)
    return path


def runtime_dir() -> Path:
    raw = os.environ.get("XDG_RUNTIME_DIR")
    if raw:
        base = Path(raw)
        if not base.is_absolute():
            raise PathError("XDG_RUNTIME_DIR must be an absolute path")
        _require_existing_private_dir(base)
        return ensure_private_dir(base / APP_ID)
    parent = _tmp_root()
    _reject_symlink_levels(parent)
    _require_dir(parent, _lstat(parent))
    return ensure_private_dir(parent / f"{APP_ID}-{os.getuid()}")


def state_dir() -> Path:
    raw = os.environ.get("XDG_STATE_HOME")
    path = Path(raw) if raw else home() / ".local" / "state"
    dest = path / "omarchy" / "overhead"
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def socket_path() -> Path:
    return runtime_dir() / f"{APP_ID}.sock"


def pid_path() -> Path:
    return runtime_dir() / f"{APP_ID}.pid"


def unlink_socket(path: Path) -> None:
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return
    if stat.S_ISLNK(st.st_mode):
        raise PathError(f"{path} is a symlink")
    if not stat.S_ISSOCK(st.st_mode):
        raise PathError(f"{path} is not a socket")
    if st.st_uid != os.getuid():
        raise PathError(f"{path} is not owned by the current user")
    os.unlink(path)


def bind_private_unix_socket(path: Path) -> socket.socket:
    unlink_socket(path)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    old = os.umask(0o177)
    try:
        server.bind(str(path))
    except OSError:
        server.close()
        raise
    finally:
        os.umask(old)
    try:
        os.chmod(path, 0o600)
        st = _lstat(path)
        if stat.S_ISLNK(st.st_mode):
            raise PathError(f"{path} is a symlink")
        if not stat.S_ISSOCK(st.st_mode):
            raise PathError(f"{path} is not a socket")
        if st.st_uid != os.getuid():
            raise PathError(f"{path} is not owned by the current user")
        if stat.S_IMODE(st.st_mode) & 0o077:
            raise PathError(f"{path} must be mode 0600")
    except Exception:
        try:
            server.close()
        except OSError:
            pass
        try:
            unlink_socket(path)
        except PathError:
            pass
        raise
    return server


def peer_uid(conn: socket.socket) -> int:
    size = struct.calcsize("3i")
    try:
        creds = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, size)
    except (OSError, AttributeError) as exc:
        raise PermissionError("peer credentials unavailable") from exc
    _pid, uid, _gid = struct.unpack("3i", creds)
    return uid


def peer_is_self(conn: socket.socket) -> bool:
    try:
        return peer_uid(conn) == os.getuid()
    except PermissionError:
        return False


def status_path() -> Path:
    return state_dir() / "status.json"


def config_path() -> Path:
    return state_dir() / "config.json"


def plugin_icon_path() -> Path:
    return (
        home()
        / ".config"
        / "omarchy"
        / "plugins"
        / "io.github.mohuddle.overhead"
        / "icon.svg"
    )
