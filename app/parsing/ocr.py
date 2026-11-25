"""图片 OCR：从活动海报 / 聊天截图里提取文字，再交给规则解析。

RapidOCR（onnxruntime）延迟加载：不装模型时后端照常启动，只有图片入口报不可用。
"""

from __future__ import annotations

import io
import logging
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path

__all__ = [
    "OCRUnavailable",
    "ocr_image_bytes",
    "save_image",
    "cleanup_images",
]

_log = logging.getLogger(__name__)

_engine = None
_engine_lock = threading.Lock()

# 超过这个边长先缩小，否则大图 OCR 会明显变慢
_MAX_SIDE = 1800


class OCRUnavailable(RuntimeError):
    """OCR 依赖未安装或模型加载失败。"""


def _get_engine():
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                try:
                    from rapidocr_onnxruntime import RapidOCR
                except Exception as exc:  # pragma: no cover - 依赖缺失分支
                    raise OCRUnavailable(
                        "OCR 依赖未安装：pip install rapidocr-onnxruntime"
                    ) from exc
                _engine = RapidOCR()
    return _engine


def ocr_image_bytes(data: bytes, *, min_score: float = 0.3) -> str:
    """返回按行拼接的识别文字；没有识别到内容时返回空串。"""
    if not data:
        raise ValueError("empty image")

    import numpy as np
    from PIL import Image, ImageOps, UnidentifiedImageError

    try:
        with Image.open(io.BytesIO(data)) as img:
            img = ImageOps.exif_transpose(img).convert("RGB")
            img.thumbnail((_MAX_SIDE, _MAX_SIDE))
            rgb = np.array(img)
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("unrecognized image format") from exc

    engine = _get_engine()
    # RapidOCR 的 ndarray 入口按 OpenCV 习惯使用 BGR
    bgr = np.ascontiguousarray(rgb[:, :, ::-1])
    result, _elapse = engine(bgr)
    if not result:
        return ""

    lines: list[str] = []
    for item in result:
        if len(item) < 2:
            continue
        text = str(item[1]).strip()
        score = float(item[2]) if len(item) > 2 and item[2] is not None else 1.0
        if text and score >= min_score:
            lines.append(text)
    return "\n".join(lines)


_EXT_BY_FORMAT = {
    "PNG": ".png",
    "JPEG": ".jpg",
    "WEBP": ".webp",
    "GIF": ".gif",
    "BMP": ".bmp",
    "TIFF": ".tiff",
}


def save_image(
    data: bytes,
    root: Path,
    *,
    now: datetime | None = None,
) -> Path:
    """把原图落盘（7 天保留），返回绝对路径。"""
    import io as _io

    from PIL import Image, UnidentifiedImageError

    ext = ".bin"
    try:
        with Image.open(_io.BytesIO(data)) as img:
            ext = _EXT_BY_FORMAT.get((img.format or "").upper(), ".bin")
    except (UnidentifiedImageError, OSError):
        pass

    root.mkdir(parents=True, exist_ok=True)
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    path = root / f"{stamp}-{uuid.uuid4().hex[:8]}{ext}"
    path.write_bytes(data)
    return path


def cleanup_images(
    root: Path,
    *,
    ttl_days: int = 7,
    now: datetime | None = None,
) -> int:
    """删除过期图片，返回删除数量。"""
    if not root.exists():
        return 0
    cutoff = (now or datetime.now()) - timedelta(days=ttl_days)
    removed = 0
    for path in root.glob("*"):
        if not path.is_file():
            continue
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime)
        except OSError:
            continue
        if mtime < cutoff:
            try:
                path.unlink()
                removed += 1
            except OSError:
                _log.warning("could not remove image %s", path)
    return removed
