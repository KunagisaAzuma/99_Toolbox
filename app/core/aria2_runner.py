"""调用内置 aria2c 进行多线程下载，并通过 RPC 读取每个连接进度。"""

from __future__ import annotations

import json
import os
import secrets
import socket
import subprocess
import sys
import time
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.utils.constants import bundled_aria2_dir

CONNECTIONS = 16


class Aria2Error(Exception):
    """aria2 不可用或下载失败。"""


@dataclass(frozen=True)
class ThreadProgress:
    index: int
    percent: float
    speed_bps: int


def find_aria2c() -> Path | None:
    exe_name = "aria2c.exe" if sys.platform == "win32" else "aria2c"
    bundled = bundled_aria2_dir() / exe_name
    if bundled.is_file():
        return bundled
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        flat = Path(meipass) / exe_name
        if flat.is_file():
            return flat
        nested = Path(meipass) / "aria2" / exe_name
        if nested.is_file():
            return nested
    return None


def ensure_aria2c(progress_cb: Callable[[str], None] | None = None) -> Path:
    found = find_aria2c()
    if found:
        return found
    raise Aria2Error("未找到内置 aria2c，请确认 aria2 目录已随软件分发")


def _creation_flags() -> int:
    if sys.platform == "win32":
        return getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return 0


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _rpc(port: int, token: str, method: str, params: list | None = None) -> object:
    payload = {
        "jsonrpc": "2.0",
        "id": "flm",
        "method": method,
        "params": [f"token:{token}", *(params or [])],
    }
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/jsonrpc",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=2) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    if "error" in body:
        message = body["error"].get("message") if isinstance(body["error"], dict) else body["error"]
        raise Aria2Error(str(message))
    return body.get("result")


def _wait_rpc(port: int, token: str, timeout: float = 8.0) -> None:
    deadline = time.time() + timeout
    last: Exception | None = None
    while time.time() < deadline:
        try:
            _rpc(port, token, "aria2.getVersion")
            return
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(0.15)
    raise Aria2Error(f"aria2 RPC 未就绪: {last}")


def _bitfield_parts(bitfield: str, num_pieces: int, parts: int) -> list[float]:
    bits: list[int] = []
    for char in bitfield:
        try:
            value = int(char, 16)
        except ValueError:
            continue
        for shift in (3, 2, 1, 0):
            bits.append((value >> shift) & 1)
    if num_pieces > 0:
        bits = bits[:num_pieces]
    if not bits:
        return [0.0] * parts
    result: list[float] = []
    total = len(bits)
    for index in range(parts):
        start = index * total // parts
        end = (index + 1) * total // parts
        chunk = bits[start:end]
        if not chunk:
            result.append(100.0 if index and result and result[-1] >= 99.0 else 0.0)
        else:
            result.append(100.0 * sum(chunk) / len(chunk))
    return result


def _thread_progress(status: dict, servers: object) -> list[ThreadProgress]:
    num_pieces = int(status.get("numPieces") or 0)
    bitfield = str(status.get("bitfield") or "")
    percents = _bitfield_parts(bitfield, num_pieces, CONNECTIONS)
    speeds = [0] * CONNECTIONS
    flat: list[int] = []
    if isinstance(servers, list):
        for group in servers:
            if not isinstance(group, dict):
                continue
            for server in group.get("servers") or []:
                if isinstance(server, dict):
                    flat.append(int(server.get("downloadSpeed") or 0))
    for index, speed in enumerate(flat[:CONNECTIONS]):
        speeds[index] = speed
    completed = int(status.get("completedLength") or 0)
    total = int(status.get("totalLength") or 0)
    if not bitfield and total > 0:
        overall = 100.0 * completed / total
        percents = [overall] * CONNECTIONS
    return [
        ThreadProgress(index=i + 1, percent=percents[i], speed_bps=speeds[i])
        for i in range(CONNECTIONS)
    ]


def _emit(
    on_progress: Callable[..., None] | None,
    percent: float,
    text: str,
    threads: list[ThreadProgress] | None = None,
) -> None:
    if on_progress is None:
        return
    try:
        on_progress(percent, text, threads or [])
    except TypeError:
        on_progress(percent, text)


def aria2_download(
    urls: list[str],
    dest: Path,
    cancelled: Callable[[], bool],
    on_progress: Callable[..., None] | None = None,
    expected_bytes: int = 0,
) -> None:
    aria2c = ensure_aria2c()
    dest.parent.mkdir(parents=True, exist_ok=True)
    control = Path(str(dest) + ".aria2")
    port = _free_port()
    token = secrets.token_hex(8)
    cmd = [
        str(aria2c),
        "--enable-rpc=true",
        "--rpc-listen-all=false",
        f"--rpc-listen-port={port}",
        f"--rpc-secret={token}",
        f"--stop-with-process={os.getpid()}",
        f"--max-connection-per-server={CONNECTIONS}",
        f"--split={CONNECTIONS}",
        "--min-split-size=1M",
        "--max-tries=8",
        "--retry-wait=2",
        "--connect-timeout=20",
        "--timeout=120",
        "--file-allocation=trunc",
        "--continue=false",
        "--allow-overwrite=true",
        "--auto-file-renaming=false",
        "--always-resume=false",
        "--http-accept-gzip=false",
        "--quiet=true",
        "--enable-color=false",
        "--console-log-level=error",
        "--dir",
        str(dest.parent),
    ]
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=_creation_flags(),
    )
    try:
        _wait_rpc(port, token)
        gid = str(
            _rpc(
                port,
                token,
                "aria2.addUri",
                [
                    urls,
                    {
                        "dir": str(dest.parent),
                        "out": dest.name,
                        "split": str(CONNECTIONS),
                        "max-connection-per-server": str(CONNECTIONS),
                        "min-split-size": "1M",
                        "continue": "false",
                        "allow-overwrite": "true",
                        "auto-file-renaming": "false",
                        "always-resume": "false",
                        "file-allocation": "trunc",
                        "http-accept-gzip": "false",
                        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) FLM-Toolbox",
                    },
                ],
            )
        )
        keys = [
            "status",
            "totalLength",
            "completedLength",
            "downloadSpeed",
            "numPieces",
            "pieceLength",
            "bitfield",
            "connections",
            "errorMessage",
        ]
        while True:
            if cancelled():
                try:
                    _rpc(port, token, "aria2.forceRemove", [gid])
                except Exception:
                    pass
                raise InterruptedError("已取消")
            status = _rpc(port, token, "aria2.tellStatus", [gid, keys])
            if not isinstance(status, dict):
                raise Aria2Error("无法读取下载状态")
            state = str(status.get("status") or "")
            total = int(status.get("totalLength") or 0)
            done = int(status.get("completedLength") or 0)
            speed = int(status.get("downloadSpeed") or 0)
            if expected_bytes > 0 and total > 0 and total < int(expected_bytes * 0.98):
                try:
                    _rpc(port, token, "aria2.forceRemove", [gid])
                except Exception:
                    pass
                raise Aria2Error(
                    f"镜像返回的文件过小（{total} 字节，期望约 {expected_bytes} 字节）"
                )
            percent = 100.0 * done / total if total else 0.0
            try:
                servers = _rpc(port, token, "aria2.getServers", [gid])
            except Exception:
                servers = []
            threads = _thread_progress(status, servers)
            conn = status.get("connections") or 0
            text = f"aria2 多线程下载 · {conn} 连接 · {_fmt_speed(speed)}"
            _emit(on_progress, min(99.0, percent), text, threads)
            if state == "complete":
                done_threads = [
                    ThreadProgress(index=i + 1, percent=100.0, speed_bps=0)
                    for i in range(CONNECTIONS)
                ]
                _emit(on_progress, 100.0, "aria2 下载完成", done_threads)
                break
            if state in {"error", "removed"}:
                raise Aria2Error(str(status.get("errorMessage") or state))
            time.sleep(0.25)
        try:
            _rpc(port, token, "aria2.forceShutdown")
        except Exception:
            pass
        process.wait(timeout=5)
        if not dest.is_file() or dest.stat().st_size <= 1024:
            raise Aria2Error("aria2 下载结果无效")
        if expected_bytes > 0 and dest.stat().st_size < int(expected_bytes * 0.98):
            raise Aria2Error(
                f"下载文件过小（{dest.stat().st_size} 字节，期望约 {expected_bytes} 字节）"
            )
    except InterruptedError:
        raise
    except Aria2Error:
        raise
    except Exception as exc:  # noqa: BLE001
        raise Aria2Error(str(exc)) from exc
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
        control.unlink(missing_ok=True)


def _fmt_speed(bps: int) -> str:
    value = float(max(0, bps))
    for unit in ("B/s", "KB/s", "MB/s", "GB/s"):
        if value < 1024.0 or unit == "GB/s":
            if unit == "B/s":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{bps} B/s"
