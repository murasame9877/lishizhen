"""定时同步循环：默认 10 分钟，静默执行。"""

from __future__ import annotations

import asyncio
import logging

from app.calendar.sync import sync_all_users
from app.config import Settings

logger = logging.getLogger(__name__)

__all__ = ["sync_loop"]


async def sync_loop(settings: Settings, stop_event: asyncio.Event | None = None) -> None:
    interval = max(60, int(settings.sync_interval_min * 60))
    logger.info("定时同步已启动，周期 %s 秒", interval)

    while True:
        await asyncio.sleep(interval)
        if stop_event is not None and stop_event.is_set():
            break
        try:
            await asyncio.to_thread(sync_all_users, settings)
        except Exception:  # noqa: BLE001
            logger.exception("定时同步循环异常")
