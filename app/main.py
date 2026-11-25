"""FastAPI 入口。

- GET  /wechat  微信服务器接口校验（echostr）
- POST /wechat  消息回调：验签 → 落库 → 5 秒内回执
- GET  /healthz 健康检查
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Query, Request
from fastapi.responses import PlainTextResponse

from app.config import Settings, get_settings
from app.parsing.time_norm import TZ
from app.storage.db import init_db
from app.wechat.crypto import check_signature
from app.wechat.gateway import process_callback

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = settings
        app.state.db = init_db(settings.db_path)
        logger.info("database ready: %s", settings.db_path)

        stop_event = asyncio.Event()
        tasks: list[asyncio.Task] = []
        if settings.worker_enabled:
            from app.jobs.worker import worker_loop

            tasks.append(
                asyncio.create_task(worker_loop(settings, stop_event=stop_event))
            )
        if settings.sync_scheduler_enabled:
            from app.calendar.scheduler import sync_loop

            tasks.append(
                asyncio.create_task(sync_loop(settings, stop_event=stop_event))
            )
        if settings.wecom_kf_enabled:
            from app.wecom_kf import kf_loop

            tasks.append(
                asyncio.create_task(kf_loop(settings, stop_event=stop_event))
            )

        try:
            yield
        finally:
            stop_event.set()
            for task in tasks:
                task.cancel()
            for task in tasks:
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            app.state.db.close()

    app = FastAPI(title="SDG WeChat Schedule Agent", lifespan=lifespan)

    @app.get("/healthz")
    def healthz() -> dict[str, object]:
        return {"ok": True, "time": datetime.now(TZ).isoformat()}

    from app.share_api import create_share_router

    app.include_router(create_share_router(settings))

    @app.get("/wechat", response_class=PlainTextResponse)
    def verify_wechat(
        signature: str = Query(default=""),
        timestamp: str = Query(default=""),
        nonce: str = Query(default=""),
        echostr: str = Query(default=""),
    ) -> PlainTextResponse:
        if check_signature(settings.wechat_token, timestamp, nonce, signature):
            return PlainTextResponse(echostr)
        return PlainTextResponse("invalid signature", status_code=403)

    @app.post("/wechat", response_class=PlainTextResponse)
    async def receive_wechat(
        request: Request,
        signature: str = Query(default=""),
        timestamp: str = Query(default=""),
        nonce: str = Query(default=""),
    ) -> PlainTextResponse:
        if not check_signature(settings.wechat_token, timestamp, nonce, signature):
            return PlainTextResponse("invalid signature", status_code=403)

        raw_xml = await request.body()
        try:
            # 指令里的同步会访问本机 CalDAV，放到线程池避免阻塞事件循环
            reply = await asyncio.to_thread(
                process_callback, request.app.state.db, raw_xml, settings
            )
        except Exception:  # 解析失败不能把微信重试拖成死循环
            logger.exception("callback processing failed")
            return PlainTextResponse("success")

        media_type = "application/xml" if reply != "success" else "text/plain"
        return PlainTextResponse(reply, media_type=media_type)

    if settings.radicale_enabled:
        # 单端口同时承载微信回调与 CalDAV；Radicale 延迟到首次访问才初始化。
        from starlette.middleware.wsgi import WSGIMiddleware

        from app.calendar.radicale_mount import LazyRadicale

        app.mount(
            settings.radicale_prefix,
            WSGIMiddleware(LazyRadicale(settings)),
        )

    return app


app = create_app()
