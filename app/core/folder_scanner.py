"""文件夹视频扫描模块."""

from __future__ import annotations

from pathlib import Path

from app.utils.constants import MAX_BATCH_FILES, VIDEO_EXTENSIONS


class FolderScanner:
    """递归扫描目录中的视频文件."""

    def __init__(self, max_files: int = MAX_BATCH_FILES) -> None:
        self.max_files = max_files

    def scan(
        self,
        directory: str | Path,
        existing: set[str] | None = None,
    ) -> tuple[list[str], bool]:
        """返回 (视频路径列表, 是否因上限截断)."""
        root = Path(directory).resolve()
        if not root.is_dir():
            return [], False

        existing = existing or set()
        found: list[str] = []
        truncated = False

        for dirpath, dirnames, filenames in os_walk_safe(root):
            # 跳过符号链接目录
            dirnames[:] = [
                d
                for d in dirnames
                if not (Path(dirpath) / d).is_symlink()
            ]
            for name in sorted(filenames):
                path = Path(dirpath) / name
                if path.is_symlink():
                    continue
                if path.suffix.lower() not in VIDEO_EXTENSIONS:
                    continue
                abs_path = str(path.resolve())
                if abs_path in existing:
                    continue
                if abs_path in found:
                    continue
                found.append(abs_path)
                if len(found) >= self.max_files:
                    truncated = True
                    return sorted(found), truncated

        return sorted(found), truncated

    def collect_paths(
        self,
        paths: list[str],
        existing: set[str] | None = None,
    ) -> tuple[list[str], bool, int]:
        """混合处理文件与文件夹。

        返回: (去重后的视频路径, 是否截断, 扫描到的原始数量)
        """
        existing = set(existing or set())
        collected: list[str] = []
        truncated = False
        raw_count = 0

        for raw in paths:
            path = Path(raw)
            if path.is_dir():
                scanned, was_truncated = self.scan(path, existing | set(collected))
                raw_count += len(scanned)
                for item in scanned:
                    if item not in existing and item not in collected:
                        collected.append(item)
                if was_truncated:
                    truncated = True
            elif path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS:
                abs_path = str(path.resolve())
                raw_count += 1
                if abs_path not in existing and abs_path not in collected:
                    collected.append(abs_path)
            if len(collected) >= self.max_files:
                truncated = True
                collected = collected[: self.max_files]
                break

        if len(collected) > self.max_files:
            truncated = True
            collected = collected[: self.max_files]

        return collected, truncated, raw_count


def os_walk_safe(root: Path):
    """包装 os.walk，避免权限错误中断扫描."""
    import os

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        yield dirpath, dirnames, filenames
