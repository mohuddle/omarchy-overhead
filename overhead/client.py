from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from .paths import PathError, pid_path, socket_path, unlink_socket
from .protocol import ProtocolError, append_ipc, encode


def _connect() -> socket.socket:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(40)
    sock.connect(str(socket_path()))
    return sock


def daemon_alive() -> bool:
    if not socket_path().exists():
        return False
    try:
        sock = _connect()
        sock.sendall(encode({"op": "ping"}))
        sock.recv(256)
        sock.close()
        return True
    except OSError:
        return False


def stop_daemon() -> None:
    if daemon_alive():
        try:
            request_no_start("quit")
        except (OSError, RuntimeError):
            pass
    pid_file = pid_path()
    if pid_file.is_file():
        try:
            os.kill(int(pid_file.read_text(encoding="utf-8").strip()), 15)
        except (OSError, ValueError):
            pass
        try:
            pid_file.unlink()
        except OSError:
            pass
    sock = socket_path()
    try:
        unlink_socket(sock)
    except (OSError, PathError):
        pass


def request_no_start(op: str, **fields: Any) -> dict[str, Any]:
    sock = _connect()
    try:
        sock.sendall(encode({"op": op, **fields}))
        buf = b""
        while b"\n" not in buf:
            chunk = sock.recv(8192)
            if not chunk:
                break
            buf = append_ipc(buf, chunk)
        if not buf:
            raise RuntimeError("no reply from overhead daemon")
        return json.loads(buf.split(b"\n", 1)[0].decode("utf-8"))
    except ProtocolError as exc:
        raise RuntimeError("daemon reply exceeds size limit") from exc
    finally:
        sock.close()


def start_daemon() -> None:
    if daemon_alive():
        return
    try:
        unlink_socket(socket_path())
    except (OSError, PathError, FileNotFoundError):
        pass
    root = str(Path(__file__).resolve().parents[1])
    env = os.environ.copy()
    env["PYTHONPATH"] = root + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    subprocess.Popen(
        [sys.executable, "-m", "overhead", "daemon"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        cwd=root,
        env=env,
    )
    for _ in range(50):
        time.sleep(0.1)
        if daemon_alive():
            return
    raise RuntimeError("overhead daemon failed to start")


def request(op: str, **fields: Any) -> dict[str, Any]:
    start_daemon()
    return request_no_start(op, **fields)


def follow() -> Iterator[dict[str, Any]]:
    start_daemon()
    sock = _connect()
    sock.settimeout(None)
    sock.sendall(encode({"op": "subscribe"}))
    buf = b""
    try:
        while True:
            chunk = sock.recv(8192)
            if not chunk:
                break
            buf = append_ipc(buf, chunk)
            while b"\n" in buf:
                raw, buf = buf.split(b"\n", 1)
                if raw.strip():
                    yield json.loads(raw.decode("utf-8"))
    finally:
        sock.close()
