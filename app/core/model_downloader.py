"""使用 aria2 多镜像、多线程下载 ONNX 模型。优先国内镜像。"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from app.core.aria2_runner import Aria2Error, ThreadProgress, aria2_download
from app.core.depth_models import DEPTH_MODELS, DepthModelSpec, depth_models_dir

# 国内 GitHub 加速镜像（按优先级）。官方地址放在最后。
_MIRROR_PREFIXES = (
    "https://ghproxy.net/",
    "https://ghfast.top/",
    "https://mirror.ghproxy.com/",
    "https://gh-proxy.com/",
    "https://gitdl.cn/",
    "https://gh.ddlc.top/",
    "https://github.moeyy.xyz/",
)


class DownloadCancelled(Exception):
    """用户取消下载。"""


class DownloadError(Exception):
    """全部镜像均失败。"""


ProgressCb = Callable[[int, str], None]
ThreadCb = Callable[[list[ThreadProgress]], None]


def candidate_urls(official: str) -> list[str]:
    urls: list[str] = []
    for prefix in _MIRROR_PREFIXES:
        urls.append(f"{prefix}{official}")
    if official.startswith("https://github.com/"):
        urls.append(official.replace("https://github.com/", "https://kkgithub.com/", 1))
        urls.append(official.replace("https://github.com/", "https://bgithub.xyz/", 1))
    urls.append(official)
    seen: set[str] = set()
    unique: list[str] = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            unique.append(url)
    return unique


def local_model_path(spec: DepthModelSpec) -> Path:
    return depth_models_dir() / spec.filename


def _looks_like_html(head: bytes) -> bool:
    stripped = head.lstrip()
    lower = stripped[:32].lower()
    return lower.startswith((b"<", b"{", b"<!")) or b"<html" in lower or b"<!doctype" in lower


def is_valid_onnx_file(path: Path, expected_bytes: int = 0) -> bool:
    if not path.is_file():
        return False
    size = path.stat().st_size
    if size <= 1024:
        return False
    try:
        with path.open("rb") as handle:
            head = handle.read(64)
    except OSError:
        return False
    if _looks_like_html(head):
        return False
    if expected_bytes > 0:
        if size < int(expected_bytes * 0.98):
            return False
        if size > int(expected_bytes * 1.05) + 1024 * 1024:
            return False
    return True


def purge_incomplete_download(dest: Path) -> None:
    dest.unlink(missing_ok=True)
    Path(str(dest) + ".aria2").unlink(missing_ok=True)
    dest.with_suffix(dest.suffix + ".part").unlink(missing_ok=True)
    dest.with_suffix(dest.suffix + ".aria2").unlink(missing_ok=True)


def is_model_ready(spec: DepthModelSpec) -> bool:
    return is_valid_onnx_file(local_model_path(spec), spec.expected_bytes)


def missing_models() -> list[DepthModelSpec]:
    return [spec for spec in DEPTH_MODELS if spec.url and not is_model_ready(spec)]


def any_model_ready() -> bool:
    return any(is_model_ready(spec) for spec in DEPTH_MODELS)


def combo_label(spec: DepthModelSpec) -> str:
    status = "已下载" if is_model_ready(spec) else "未下载"
    return f"{spec.speed_tag} · {spec.short_name}（{spec.size_label}）[{status}]"


def delete_model(spec: DepthModelSpec) -> bool:
    path = local_model_path(spec)
    existed = path.is_file()
    purge_incomplete_download(path)
    return existed


def delete_all_models() -> int:
    count = 0
    for spec in DEPTH_MODELS:
        if delete_model(spec):
            count += 1
    return count


def format_bytes(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024.0 or unit == "GB":
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{size} B"


def download_with_mirrors(
    official_url: str,
    dest: Path,
    expected: int,
    cancelled: Callable[[], bool],
    on_progress: Callable[..., None] | None = None,
) -> None:
    if is_valid_onnx_file(dest, expected):
        return
    last_error = "全部镜像均失败"
    for url in candidate_urls(official_url):
        if cancelled():
            raise DownloadCancelled("已取消")
        purge_incomplete_download(dest)
        try:
            aria2_download(
                [url],
                dest,
                cancelled,
                on_progress,
                expected_bytes=expected,
            )
        except InterruptedError as exc:
            purge_incomplete_download(dest)
            raise DownloadCancelled(str(exc)) from exc
        except Aria2Error as exc:
            last_error = str(exc)
            purge_incomplete_download(dest)
            continue
        if is_valid_onnx_file(dest, expected):
            return
        last_error = "下载完成但文件校验失败（大小或内容不正确）"
        purge_incomplete_download(dest)
    raise DownloadError(f"aria2 下载失败: {last_error}")


def download_models(
    specs: list[DepthModelSpec],
    progress_cb: ProgressCb | None = None,
    cancelled: Callable[[], bool] | None = None,
    thread_cb: ThreadCb | None = None,
) -> None:
    pending = [spec for spec in specs if spec.url and not is_model_ready(spec)]
    if not pending:
        if progress_cb:
            progress_cb(100, "模型已就绪")
        return

    totals = [spec.expected_bytes or 1 for spec in pending]
    grand = sum(totals)

    def cancelled_fn() -> bool:
        return bool(cancelled and cancelled())

    done_before = 0
    for index, spec in enumerate(pending):
        if cancelled_fn():
            raise DownloadCancelled("已取消")
        dest = local_model_path(spec)
        expected = spec.expected_bytes or 1
        label = spec.title
        if progress_cb:
            progress_cb(
                int(done_before * 100 / max(grand, 1)),
                f"aria2 开始下载 {label}（{index + 1}/{len(pending)}）",
            )
        if thread_cb:
            thread_cb([])

        def on_progress(
            percent: float,
            text: str,
            threads: list[ThreadProgress] | None = None,
            _expected=expected,
            _label=label,
        ) -> None:
            overall = done_before + _expected * min(percent, 100.0) / 100.0
            value = int(min(99, overall * 100 / max(grand, 1)))
            if progress_cb:
                progress_cb(value, f"{_label} · {text}（{percent:.0f}%）")
            if thread_cb:
                thread_cb(threads or [])

        download_with_mirrors(
            spec.url or "",
            dest,
            expected,
            cancelled_fn,
            on_progress=on_progress,
        )
        done_before = sum(totals[: index + 1])

    if progress_cb:
        progress_cb(100, "下载完成")
